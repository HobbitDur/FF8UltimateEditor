import os

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog,
                             QListWidget, QGroupBox, QMessageBox, QAbstractItemView)

from FF8GameData.gamedata import GameData
from Odine.odinemanager import OdineManager

CATEGORIES = [
    ("offensive", "Offensive"),
    ("supportive", "Supportive"),
    ("disruptive", "Disruptive"),
]


class OdineWidget(QWidget):
    """magsort.bin editor: assigns each magic spell to the Offensive, Supportive or Disruptive
    category used to sort the in-game Magic menu, and lets you reorder spells within a category
    (the order shown here is the order the menu displays them in).

    Named after Dr. Odine, the Esthar scientist who invented para-magic and the junction system."""

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData"):
        QWidget.__init__(self)

        self.game_data = GameData(game_data_folder)
        self.game_data.load_magic_data()
        self.manager = OdineManager(self.game_data)

        self.setWindowTitle("Odine")
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'hobbitdur.ico')))

        # File section
        self.file_dialog = QFileDialog()
        self.load_button = QPushButton()
        self.load_button.setIcon(QIcon(os.path.join(icon_path, 'folder.png')))
        self.load_button.setIconSize(QSize(30, 30))
        self.load_button.setFixedSize(40, 40)
        self.load_button.setToolTip("Open a magsort.bin file")
        self.load_button.clicked.connect(self.load_file)

        self.save_button = QPushButton()
        self.save_button.setIcon(QIcon(os.path.join(icon_path, 'save.svg')))
        self.save_button.setIconSize(QSize(30, 30))
        self.save_button.setFixedSize(40, 40)
        self.save_button.setToolTip("Save all modifications in the opened magsort.bin (irreversible)")
        self.save_button.clicked.connect(self.save_file)

        self.file_label = QLabel("No file loaded")

        file_section_layout = QHBoxLayout()
        file_section_layout.addWidget(self.load_button)
        file_section_layout.addWidget(self.save_button)
        file_section_layout.addWidget(self.file_label)
        file_section_layout.addStretch(1)

        # Available spells (left side): every spell not currently in a category
        self.available_list = QListWidget()
        self.available_list.setFixedWidth(220)
        self.available_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        available_group = QGroupBox("Available spells")
        available_layout = QVBoxLayout()
        available_layout.addWidget(self.available_list)
        available_group.setLayout(available_layout)

        # One column per category (right side)
        self.category_lists = {}
        categories_layout = QHBoxLayout()
        for key, title in CATEGORIES:
            categories_layout.addWidget(self._build_category_column(key, title))

        self.editor_container = QWidget()
        editor_layout = QHBoxLayout()
        editor_layout.addWidget(available_group)
        editor_layout.addLayout(categories_layout)
        self.editor_container.setLayout(editor_layout)
        self.editor_container.setEnabled(False)

        main_layout = QVBoxLayout()
        main_layout.addLayout(file_section_layout)
        main_layout.addWidget(self.editor_container)
        self.setLayout(main_layout)

    def _build_category_column(self, key, title):
        list_widget = QListWidget()
        list_widget.setFixedWidth(220)
        self.category_lists[key] = list_widget

        add_button = QPushButton(f"Add → {title}")
        add_button.clicked.connect(lambda: self._add_to_category(key))

        remove_button = QPushButton("Remove")
        remove_button.clicked.connect(lambda: self._remove_from_category(key))

        up_button = QPushButton("Move up")
        up_button.clicked.connect(lambda: self._move_in_category(key, -1))

        down_button = QPushButton("Move down")
        down_button.clicked.connect(lambda: self._move_in_category(key, 1))

        buttons_layout = QHBoxLayout()
        buttons_layout.addWidget(remove_button)
        buttons_layout.addWidget(up_button)
        buttons_layout.addWidget(down_button)

        group = QGroupBox(title)
        layout = QVBoxLayout()
        layout.addWidget(add_button)
        layout.addWidget(list_widget)
        layout.addLayout(buttons_layout)
        group.setLayout(layout)
        return group

    def load_file(self):
        file_name = self.file_dialog.getOpenFileName(parent=self, caption="Search magsort.bin file",
                                                     filter="*.bin", directory=os.getcwd())[0]
        if file_name:
            self.manager.load_file(file_name)
            self.file_label.setText(os.path.basename(file_name))
            self.editor_container.setEnabled(True)
            self._refresh_lists()

    def save_file(self):
        if not self.manager.file_path:
            return

        self._apply_lists_to_manager()

        unused_ids = self.manager.unused_magic_ids()
        if unused_ids:
            unused_names = ", ".join(self.manager.get_magic_name(magic_id) for magic_id in unused_ids)
            proceed = QMessageBox.question(
                self, "Unused spells",
                "The following spells are not assigned to any category and will not appear "
                f"in the Magic menu:\n\n{unused_names}\n\nSave anyway?"
            )
            if proceed != QMessageBox.StandardButton.Yes:
                return

        try:
            self.manager.save_file()
        except ValueError as e:
            QMessageBox.critical(self, "Error", str(e))

    def _refresh_lists(self):
        used_ids = set(self.manager.offensive + self.manager.supportive + self.manager.disruptive)

        self.available_list.clear()
        for magic_id in self.manager.all_magic_ids():
            if magic_id not in used_ids:
                self._add_list_item(self.available_list, magic_id)

        for key, _ in CATEGORIES:
            list_widget = self.category_lists[key]
            list_widget.clear()
            for magic_id in getattr(self.manager, key):
                self._add_list_item(list_widget, magic_id)

    def _add_list_item(self, list_widget, magic_id):
        list_widget.addItem(f"{magic_id}: {self.manager.get_magic_name(magic_id)}")
        list_widget.item(list_widget.count() - 1).setData(Qt.ItemDataRole.UserRole, magic_id)

    def _add_to_category(self, key):
        selected_items = self.available_list.selectedItems()
        if not selected_items:
            return
        list_widget = self.category_lists[key]
        for item in selected_items:
            self._add_list_item(list_widget, item.data(Qt.ItemDataRole.UserRole))
            self.available_list.takeItem(self.available_list.row(item))

    def _remove_from_category(self, key):
        list_widget = self.category_lists[key]
        for item in list_widget.selectedItems():
            self._add_list_item(self.available_list, item.data(Qt.ItemDataRole.UserRole))
            list_widget.takeItem(list_widget.row(item))

    def _move_in_category(self, key, direction):
        list_widget = self.category_lists[key]
        row = list_widget.currentRow()
        new_row = row + direction
        if row < 0 or not (0 <= new_row < list_widget.count()):
            return
        item = list_widget.takeItem(row)
        list_widget.insertItem(new_row, item)
        list_widget.setCurrentRow(new_row)

    def _apply_lists_to_manager(self):
        for key, _ in CATEGORIES:
            list_widget = self.category_lists[key]
            magic_ids = [list_widget.item(i).data(Qt.ItemDataRole.UserRole) for i in range(list_widget.count())]
            setattr(self.manager, key, magic_ids)
