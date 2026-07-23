"""Project-wide pytest configuration.

Some tests need original FF8 game files (.jsm, .dat, kernel.bin, ...) that cannot be
committed to the repo for copyright reasons. Those tests are marked with @pytest.mark.ff8data
and are skipped automatically when the files are not present next to this conftest.

Run only those tests locally with:      pytest -m ff8data
The CI excludes them completely with:   pytest -m "not ff8data"

The run is also cut off from the machine's saved GUI preferences: see _isolate_qsettings.
"""
import pathlib
import tempfile

import pytest

PROJECT_ROOT = pathlib.Path(__file__).parent

# The one QApplication of the run, kept alive here — see _keep_qapplication_alive.
_QAPPLICATION = None


def _isolate_qsettings():
    """Point every QSettings at a throwaway folder, before a single widget is built.

    The tools remember their state (Ifrit's "show skeleton" checkbox, last folders, window
    geometry...) in QSettings, which on Windows is the real registry of whoever runs the tests.
    Left alone, that cuts both ways: a test asserting the default state fails on a machine where
    the developer once ticked the box in the real application, and the tests write their own
    values back into it. Neither is acceptable, so the whole run reads and writes an empty
    temporary ini instead - every tool starts from its coded defaults, exactly as on a fresh
    install, and the user's own preferences are left untouched.

    It has to be done by swapping the class: setDefaultFormat() does NOT reach the
    QSettings(organisation, application) constructor the tools use, which stays on the native
    format - the registry - whatever the default is. The swap happens in pytest_configure, before
    any test module, and therefore any tool, is imported.
    """
    from PyQt6 import QtCore

    folder = pathlib.Path(tempfile.mkdtemp(prefix="ff8ue-test-settings-"))
    real_qsettings = QtCore.QSettings

    class IsolatedQSettings(real_qsettings):
        """QSettings(organisation, application), rerouted to an ini file of its own.

        Only that form is rerouted - it is the one that would otherwise reach the registry, and
        the only one this project uses. Anything else (a settings object already pointed at a
        file of its own, above all) is left exactly as it was written.
        """

        def __init__(self, *args, **kwargs):
            is_org_app_form = (not kwargs and 1 <= len(args) <= 2
                               and all(isinstance(a, str) for a in args))
            if not is_org_app_form:
                super().__init__(*args, **kwargs)
                return
            name = "-".join(a for a in args if a) or "default"
            super().__init__(str(folder / f"{name}.ini"), real_qsettings.Format.IniFormat)

    QtCore.QSettings = IsolatedQSettings


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "ff8data(*files): test needs original FF8 game files that are not committed "
        "for copyright reasons, skipped when the files are missing from the project root",
    )
    _isolate_qsettings()


def pytest_collection_modifyitems(config, items):
    for item in items:
        marker = item.get_closest_marker("ff8data")
        if marker:
            missing = [file_name for file_name in marker.args if not (PROJECT_ROOT / file_name).exists()]
            if missing:
                item.add_marker(pytest.mark.skip(
                    reason=f"FF8 game files not available (copyright, not in repo): {', '.join(missing)}"))


def pytest_runtest_setup(item):
    _keep_qapplication_alive()


def _keep_qapplication_alive():
    """Hold a reference to the QApplication for the whole session.

    Qt allows exactly one QApplication per process, so the widget test modules each ask for it
    with `QApplication.instance() or QApplication(sys.argv)` from a MODULE-scoped fixture. The
    first module to run therefore ends up owning it: when that module's tests are over, pytest
    drops the fixture's value, the last Python reference goes with it and the QApplication is
    destroyed - while the widgets built by other modules are still alive. Destroying the
    application out from under live widgets aborts the process from C++ (exit 0xC0000409), after
    every test has passed but before pytest can print its summary, so a completely green run
    looks like a crash. On its own a module never sees it: nothing else is left standing.

    One reference held here outlives every fixture and keeps the application alive to the end of
    the session, where pytest_sessionfinish takes it down in a defined order.
    """
    global _QAPPLICATION
    if _QAPPLICATION is None:
        from PyQt6.QtWidgets import QApplication
        _QAPPLICATION = QApplication.instance()


def pytest_sessionfinish(session, exitstatus):
    """Tear the GUI down in a defined order, while the QApplication is still alive.

    Closing and deleting the top-level widgets here, then draining the event queue, destroys the
    OpenGL contexts at a point where that is still legal, and leaves nothing for Python's own
    disorderly shutdown to trip over.
    """
    global _QAPPLICATION

    app = _QAPPLICATION
    _QAPPLICATION = None
    if app is None:
        return
    app.closeAllWindows()
    for widget in list(app.topLevelWidgets()):
        widget.deleteLater()
    # Twice: deleteLater()d objects are freed on the next loop, and freeing one can post the next.
    app.processEvents()
    app.processEvents()
