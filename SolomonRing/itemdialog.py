from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QVBoxLayout, QFormLayout, QComboBox,
    QCheckBox, QLineEdit, QLabel,
)


class ItemCreationDialog(QDialog):
    def __init__(self, definitions, template_id=1, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add item")
        self.definitions = definitions
        self.template = QComboBox()
        for item_id, name in definitions.names().items():
            if item_id:
                self.template.addItem(f"{item_id}: {name or '(unnamed)'}", item_id)
        self.template.setCurrentIndex(max(0, self.template.findData(template_id)))
        self.name = QLineEdit(f"New item {definitions.count}")
        self.description = QLineEdit(definitions.text(template_id, 1))
        self.battle = QCheckBox("Usable in battle")
        self.battle.setChecked(definitions.existing_battle_row(template_id) is not None)
        self.battle.setEnabled(definitions.count < 255)
        if definitions.count == 255:
            self.battle.setChecked(False)
        self.battle.setToolTip("Item 255 is field-only. Added battle items use IDs 199-254.")
        self.template.currentIndexChanged.connect(self._template_changed)
        form = QFormLayout()
        form.addRow("New item ID:", QLabel(str(definitions.count)))
        form.addRow("Copy settings from:", self.template)
        form.addRow("Name:", self.name)
        form.addRow("Description:", self.description)
        form.addRow(self.battle)
        note = QLabel(
            "Field behavior and price are copied from the template. Battle settings use "
            "the template when available, otherwise Potion. You can edit them after creation.\n"
            "Requires FFNx AddMoreItems for the 2013 English game.")
        note.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(self.name.text().strip()))
        self.name.textChanged.connect(lambda text: buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(text.strip())))
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addWidget(buttons)

    def _template_changed(self):
        item_id = self.template.currentData()
        self.description.setText(self.definitions.text(item_id, 1))
        self.battle.setChecked(self.definitions.count < 255 and self.definitions.existing_battle_row(item_id) is not None)
