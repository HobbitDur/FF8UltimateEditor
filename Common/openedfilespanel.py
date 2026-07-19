from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QListWidget

from Common.fileregistry import FileRegistry


class OpenedFilesPanel(QWidget):
    """Inline, collapsible view of the files currently open in the shared registry.

    Replaces the old pop-up: files show up in the list as they are opened by any tool (the
    header keeps their count), and the list collapses to just its header to stay out of the way.
    """

    MAX_LIST_HEIGHT = 140  # a few rows, then the list scrolls instead of growing further

    def __init__(self, registry: FileRegistry):
        QWidget.__init__(self)
        self.registry = registry

        self.header_button = QPushButton()
        self.header_button.setCheckable(True)
        self.header_button.setChecked(False)  # start collapsed: just the count is shown
        self.header_button.setToolTip("The FF8 files currently opened, shared by all the tools. "
                                      "Click to expand or collapse the list.")
        self.header_button.toggled.connect(self._set_expanded)

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.file_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.file_list.hide()

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.header_button)
        layout.addWidget(self.file_list)
        # Keep the header + list packed at the top; any spare height in the column goes here, not
        # as a gap between the rows.
        layout.addStretch(1)
        self.setLayout(layout)

        self.registry.file_changed.connect(self._refresh)
        self._refresh()

    def _set_expanded(self, expanded):
        self.file_list.setVisible(expanded)
        if expanded:
            self._fit_list_height()
        self._update_header()

    def _update_header(self):
        arrow = "▾" if self.header_button.isChecked() else "▸"  # ▾ expanded / ▸ collapsed
        self.header_button.setText(f"{arrow} Opened files ({len(self.registry.paths)})")

    def _fit_list_height(self):
        """Size the list to exactly its rows (up to MAX_LIST_HEIGHT), so an expanded panel with only
        a couple of files doesn't leave a big empty box - the rows stay packed at the top."""
        count = self.file_list.count()
        row_height = self.file_list.sizeHintForRow(0) if count else 0
        if row_height <= 0:
            row_height = 20  # nothing to measure yet (empty / not laid out): a sensible row height
        content = row_height * max(count, 1) + 2 * self.file_list.frameWidth() + 2
        self.file_list.setFixedHeight(min(content, self.MAX_LIST_HEIGHT))

    def _refresh(self, _file_name=None):
        self._update_header()
        self.file_list.clear()
        for file_name, file_path in sorted(self.registry.paths.items()):
            self.file_list.addItem(f"{file_name}:  {file_path}")
        if not self.file_list.isHidden():
            self._fit_list_height()
