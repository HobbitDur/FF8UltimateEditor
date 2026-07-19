"""Per-tool "unsaved changes" tracking.

A tool gets a ``dirty_state`` (a DirtyState) that flips to dirty on a real user edit and back to
clean on load/save. The shared header uses it to show a ``*`` in the window title. It is wired in
one line - ``install_dirty_tracking(self)`` - after a tool has built its widgets and its
FileBindings: the helper connects every editable widget's *edit* signal to mark dirty, and clears
(and re-scans for newly built widgets) whenever one of the tool's files loads.

Design notes:
- Marking is O(1) and only emits on a real flip, so the signal noise a load fires while populating
  widgets is cheap; it is wiped by the clear() that runs right after the load callback.
- Edit signals are chosen to be user-only where Qt offers one (QLineEdit.textEdited,
  QComboBox.activated, QAbstractButton.clicked), so merely navigating between entries - which
  well-behaved tools also do with signals blocked - does not falsely mark dirty. For spin boxes /
  text edits / editable lists there is no user-only signal, so those rely on the tool blocking
  signals during programmatic updates (the common pattern) plus the clear-after-load.
- The Save button is NOT gated on this (it stays enabled while a file is loaded), so a missed edit
  signal can never leave the user unable to save - the worst case is a missing/extra ``*``.
"""
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import (QWidget, QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox,
                             QComboBox, QAbstractButton, QAbstractSlider, QListWidget, QTableWidget)


class DirtyState(QObject):
    """Whether a tool has unsaved edits. Emits changed(bool) only when the value actually flips."""

    changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        QObject.__init__(self, parent)
        self._dirty = False
        self._tracked = set()  # id() of widgets already connected, so track() is idempotent

    @property
    def dirty(self):
        return self._dirty

    def mark(self, *_args):
        if not self._dirty:
            self._dirty = True
            self.changed.emit(True)

    def clear(self, *_args):
        if self._dirty:
            self._dirty = False
            self.changed.emit(False)

    def track(self, root: QWidget):
        """Connect every not-yet-tracked editable widget under root to mark(). Safe to call again
        after a load that built new widgets."""
        for widget in root.findChildren(QWidget):
            key = id(widget)
            if key in self._tracked:
                continue
            signal = self._edit_signal(widget)
            if signal is not None:
                signal.connect(self.mark)
                self._tracked.add(key)

    @staticmethod
    def _edit_signal(widget):
        # User-only signals first (fire on user action, never on programmatic set) so navigation
        # between entries doesn't mark dirty; then the rest, which rely on signal-blocking + clear.
        if isinstance(widget, QLineEdit):
            return widget.textEdited
        if isinstance(widget, QComboBox):
            return widget.activated
        if isinstance(widget, QAbstractButton) and widget.isCheckable():
            return widget.clicked
        if isinstance(widget, (QPlainTextEdit, QTextEdit)):
            return widget.textChanged
        if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
            return widget.valueChanged
        if isinstance(widget, QAbstractSlider):
            return widget.valueChanged
        if isinstance(widget, (QListWidget, QTableWidget)):
            return widget.itemChanged
        return None


def install_dirty_tracking(tool):
    """Give ``tool`` a ``tool.dirty_state`` that marks on edit and clears when its files load.

    Call once, in the tool's __init__, after its widgets AND its FileBindings exist. Returns the
    DirtyState (also stored as ``tool.dirty_state``)."""
    state = DirtyState(tool)
    tool.dirty_state = state
    state.track(tool)
    bindings = tool.file_bindings() if hasattr(tool, "file_bindings") else []
    for binding in bindings:
        # After a file loads (populate has already run and may have marked dirty), pick up any new
        # widgets and reset to clean. file_opened carries the path; we ignore it.
        binding.file_opened.connect(lambda _path, t=tool, s=state: (s.track(t), s.clear()))
    return state
