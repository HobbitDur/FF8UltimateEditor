from PyQt6.QtCore import QObject, Qt
from PyQt6.QtWidgets import QLabel, QStackedWidget, QVBoxLayout, QWidget


class ClosedFileView(QObject):
    """Clears a fixed-file tool's view once its file is removed from the Opened files panel.

    The tool's whole content moves into an inner page of a stack, next to a "No file loaded"
    page. When every main (edited) binding given here has been removed, the stack shows that page
    so the removed file's data is no longer on screen; the next file opened on any of those
    bindings brings the content back (the tool reloads its data as usual). The tool's own layout
    object is kept as is - only re-hosted - so its code keeps working unchanged.

    Before any removal the tool looks exactly as it did: a freshly started tool still shows its
    own empty state, not this page.
    """

    def __init__(self, tool: QWidget, bindings):
        QObject.__init__(self, tool)
        self._bindings = [binding for binding in bindings if not binding.read_only]
        self.content = QWidget()
        self.content.setLayout(tool.layout())  # re-hosts the layout AND its widgets in the page
        names = ", ".join(binding.file_name for binding in self._bindings)
        self.placeholder = QLabel(f"No file loaded - {names} was removed from the opened files.\n"
                                  "Use Import to open one.")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setWordWrap(True)
        self.placeholder.setStyleSheet("color:#888;")
        self.stack = QStackedWidget()
        self.stack.addWidget(self.content)
        self.stack.addWidget(self.placeholder)
        layout = QVBoxLayout(tool)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stack)
        for binding in self._bindings:
            binding.file_closed.connect(self._on_file_closed)
            binding.file_opened.connect(self._on_file_opened)

    @property
    def is_blank(self):
        """Whether the "No file loaded" page is showing (the tool has nothing to save)."""
        return self.stack.currentWidget() is self.placeholder

    def _on_file_closed(self, _path):
        if not any(binding.is_loaded for binding in self._bindings):
            self.stack.setCurrentWidget(self.placeholder)

    def _on_file_opened(self, _path):
        self.stack.setCurrentWidget(self.content)


def install_closed_file_view(tool: QWidget, bindings=None):
    """Give ``tool`` a ``tool.closed_file_view`` (see ClosedFileView). ``bindings`` defaults to
    the tool's file_bindings(). Returns the ClosedFileView."""
    if bindings is None:
        bindings = tool.file_bindings()
    tool.closed_file_view = ClosedFileView(tool, bindings)
    return tool.closed_file_view
