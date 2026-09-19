"""Qt objects die deterministically at the test boundary - never by the garbage collector.

Most GUI tests build a real top-level widget (often with a 3D view) and simply drop it. The
dropped tree is cyclic (lambda signal connections), so left alone it dies through Python's
garbage collector - and PyQt6 (6.11) on Python 3.14 does not survive that: the collector tears
the tree's Python side apart (tp_clear) while destroying its C++ side, destructor-cascade
signals and still-armed timers reach slots whose closures are already cleared, and the process
dies on an access violation with no Python traceback, blamed on whichever innocent test was
running. Python 3.14's incremental old-generation collection makes it worse (a pass can land
mid-event-pump and leave the C++ half alive across slices), but even a full gc.collect() at a
safe point can crash finalizing such a tree. The mechanism and the native stack that pinned it
down are documented in Common/deferredcall.py; the crash showed up as tests/test_single_pane.py
dying mid-run.

The cure is a collection that never lets the GC destroy C++: DEBUG_SAVEALL turns a collect pass
into pure DISCOVERY (unreachable objects are parked in gc.garbage, nothing cleared, nothing
freed), every Qt object found gets its C++ half deleted explicitly while its Python half is
still fully intact (destructor signals fire into live, not half-cleared, objects), and only
then does a real collect reclaim the now inert Python remains. The automatic collector stays
off during tests so the unsafe path cannot run behind our back; per-test garbage cannot pile up
because every boundary collects everything. None of this changes what any test asserts - it is
the same determinism pytest-qt's qtbot enforces by deleting registered widgets at teardown.
"""
import gc
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QObject

gc.disable()

# The QApplication lives for the whole run. Test files get it from a module-scoped `qapp`
# fixture (`QApplication.instance() or QApplication(...)`); when the module that created it
# ended, its fixture dropped the last reference and the application was destroyed. The next
# module then built a second QApplication, and destroying a 3D (OpenGL) view made under that
# second application crashed the process (access violation), blamed on whichever test was
# running - e.g. a SolomonRing test followed by Alexander's stage viewer. Creating it here, once,
# and holding it means every fixture's `instance()` finds it and it is never recreated.
from PyQt6.QtWidgets import QApplication  # noqa: E402 - after QT_QPA_PLATFORM is set

_APPLICATION = QApplication.instance() or QApplication([])
_APPLICATIONS = [_APPLICATION]


def _collect_qt_garbage_safely():
    """gc.collect() that cannot crash on Qt objects: discover, delete C++, then free."""
    gc.set_debug(gc.DEBUG_SAVEALL)
    try:
        gc.collect()                       # discovery only: everything lands in gc.garbage
    finally:
        gc.set_debug(0)
    for obj in gc.garbage:
        if isinstance(obj, QCoreApplication):
            if obj not in _APPLICATIONS:
                _APPLICATIONS.append(obj)  # the application outlives every test: keep it
            continue
        if isinstance(obj, QObject) and not sip.isdeleted(obj):
            sip.delete(obj)                # parents first or not - isdeleted() guards children
    gc.garbage.clear()
    gc.collect()                           # the same graph again, C++ already gone: inert


@pytest.fixture(autouse=True)
def _finalize_qt_garbage_at_test_boundary():
    # gc.disable() is re-asserted per test: a test may legitimately re-enable the collector
    # (the test_playback_gc_timer contract tests do), and that must not switch the automatic
    # collector back on for every test that happens to run after it.
    gc.disable()
    yield
    _collect_qt_garbage_safely()


def pytest_sessionfinish(session, exitstatus):
    _collect_qt_garbage_safely()           # last boundary: don't leave trees to exit-time GC
