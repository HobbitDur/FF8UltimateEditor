"""The test run must not read or write the machine's own GUI preferences.

The tools remember their state in QSettings - Ifrit's "show skeleton" checkbox, last folders,
window geometry - which on Windows is the real registry of whoever runs the tests. That cut both
ways: a test asserting a default failed on a machine where the developer had once ticked the box
in the real application (test_add_bone_shortcut_adds_child_of_selected did exactly that, and only
for them), and the tests wrote their own values back into the developer's settings.

conftest.py reroutes QSettings to a throwaway ini for the whole session. These tests check the
reroute is in place, because when it silently stops working the symptom is a test that fails on
one machine and passes on every other.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings


def test_settings_go_to_a_file_and_not_the_registry():
    """The constructor the tools use - QSettings(organisation, application) - is the one that has
    to be rerouted; setDefaultFormat() does NOT reach it, which is the trap this guards."""
    settings = QSettings("FF8UltimateEditor", "FF8UltimateEditor")
    assert settings.format() == QSettings.Format.IniFormat
    assert "HKEY" not in settings.fileName().upper()
    assert settings.fileName().endswith(".ini")


def test_the_run_starts_from_the_coded_defaults():
    """Nothing the developer once clicked in the real application may leak in: an unwritten key
    has to come back as the default the caller asks for."""
    settings = QSettings("FF8UltimateEditor", "FF8UltimateEditor")
    assert settings.value("ifrit/3d/show_skeleton", False, type=bool) is False


def test_a_value_written_by_a_test_stays_inside_the_run():
    settings = QSettings("FF8UltimateEditor", "FF8UltimateEditor")
    settings.setValue("tests/scratch_value", 1234)
    settings.sync()
    assert os.path.exists(settings.fileName())
    # ...in the throwaway folder, not anywhere the user's own settings live
    assert "ff8ue-test-settings-" in settings.fileName().replace("\\", "/")
    settings.remove("tests/scratch_value")
