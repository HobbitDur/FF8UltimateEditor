"""Run something on the next event-loop tick, tied to the widget that asked for it.

Several editors need to finish a job one tick later, once Qt has laid the widgets out and they
have real sizes: restore a scroll position after a rebuild, size a splitter from its true width,
clear a "still loading" flag. The obvious way to write that is QTimer.singleShot(0, callback).

It has a trap. The pending call outlives the widget: close the file (or let the tests drop it, or
tear the window down) before the tick arrives and the callback still runs, on Python wrappers
whose C++ objects Qt has already deleted. That raises RuntimeError inside a Qt slot, and PyQt does
not report those - it aborts the whole process, with no traceback and no message. It cost a test
suite that died mid-run for no visible reason, and it can equally take the editor down while
someone is using it.

Qt has a version of singleShot that takes a context object and drops the call when that object
dies, but PyQt6 does not expose it. What it does honour is ownership: a QTimer created as a CHILD
of the widget is destroyed with it, and a destroyed timer never fires. That is all this is.
"""
from PyQt6.QtCore import QTimer


def defer(owner, callback, msec: int = 0) -> QTimer:
    """Call `callback` after `msec`, unless `owner` is destroyed first.

    `owner` must be the QObject whose C++ objects the callback touches - usually the widget that
    schedules it. Returns the timer, which callers can keep to cancel the call early; ignoring it
    is fine, `owner` owns it.
    """
    timer = QTimer(owner)
    timer.setSingleShot(True)
    timer.timeout.connect(callback)
    timer.start(msec)
    return timer
