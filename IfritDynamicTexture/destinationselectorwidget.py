from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import QCheckBox, QLabel, QGroupBox, QVBoxLayout


class DestinationSelectorWidget(QGroupBox):
    """Widget for selecting which destinations to display for current entry"""

    selectionChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("Destinations to Show", parent)
        self.checkboxes = []

        layout = QVBoxLayout(self)
        self.dest_layout = QVBoxLayout()
        layout.addLayout(self.dest_layout)
        layout.addStretch()

    def update_destinations(self, dest_count: int, selected_indices: set):
        """Update the list of destination checkboxes"""
        # Clear existing
        for cb in self.checkboxes:
            cb.deleteLater()
        self.checkboxes.clear()

        # Clear layout
        for i in reversed(range(self.dest_layout.count())):
            item = self.dest_layout.takeAt(i)
            if item.widget():
                item.widget().deleteLater()

        if dest_count == 0:
            label = QLabel("No destinations for this entry")
            self.dest_layout.addWidget(label)
            return

        # Add "Select All" checkbox
        self.select_all_cb = QCheckBox("Select All")
        self.select_all_cb.stateChanged.connect(self._on_select_all)
        self.dest_layout.addWidget(self.select_all_cb)

        # Add destination checkboxes
        for i in range(dest_count):
            cb = QCheckBox(f"Destination {i}")
            cb.setChecked(i in selected_indices)
            cb.stateChanged.connect(self._on_selection_changed)
            self.checkboxes.append(cb)
            self.dest_layout.addWidget(cb)

        # Manually update select all state after creating checkboxes
        self.select_all_cb.blockSignals(True)
        all_checked = all(cb.isChecked() for cb in self.checkboxes) if self.checkboxes else False
        self.select_all_cb.setChecked(all_checked)
        self.select_all_cb.blockSignals(False)

    def _on_select_all(self, state):
        """Handle select all checkbox"""
        # Block signals while setting all checkboxes
        for cb in self.checkboxes:
            cb.blockSignals(True)
            cb.setChecked(state == Qt.CheckState.Checked.value)
            cb.blockSignals(False)
        self.selectionChanged.emit()

    def _on_selection_changed(self):
        """Handle individual checkbox changes"""
        # Temporarily block signals to avoid recursion
        self.select_all_cb.blockSignals(True)

        # Update select all state
        all_checked = all(cb.isChecked() for cb in self.checkboxes) if self.checkboxes else False
        self.select_all_cb.setChecked(all_checked)

        self.select_all_cb.blockSignals(False)
        self.selectionChanged.emit()

    def get_selected_indices(self) -> set:
        """Get set of selected destination indices"""
        return {i for i, cb in enumerate(self.checkboxes) if cb.isChecked()}


