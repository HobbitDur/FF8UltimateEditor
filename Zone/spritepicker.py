"""Pick a picture overlay's sprite by seeing it: the page's whole picture with every sprite's
rectangles drawn over it (SmallWidget/spritecanvas.py), instead of an id in a list."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QListWidget,
                             QListWidgetItem, QVBoxLayout, QCheckBox)

from SmallWidget.spritecanvas import (PAGE_SIZE, SCALE, UNUSED_ID, SpriteCanvas, sprite_at, sprite_rects,
                                      sprite_size, usable_sprites)

__all__ = ["SpritePickerDialog", "sprite_at", "UNUSED_ID"]


class SpritePickerDialog(QDialog):
    """Choose a sprite on the page's picture. selected_id() is the choice (UNUSED_ID = none)."""

    def __init__(self, picture, sprites, current_id=UNUSED_ID, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowTitle("Pick a sprite")
        self.sprites = usable_sprites(sprites)
        self._selected = current_id

        self.canvas = SpriteCanvas(picture, self.sprites)
        self.canvas.picked.connect(self.select)
        self.canvas.hovered.connect(self._show_hover)

        self.sprite_list = QListWidget()
        self.sprite_list.setMinimumWidth(170)
        none_item = QListWidgetItem(f"{UNUSED_ID}: none (slot unused)")
        none_item.setData(Qt.ItemDataRole.UserRole, UNUSED_ID)
        self.sprite_list.addItem(none_item)
        for sprite in self.sprites:
            width, height = sprite_size(sprite)
            parts = len(sprite.quads)
            label = f"{sprite.sprite_id}: {width}x{height}" + (f" ({parts} parts)" if parts > 1 else "")
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, sprite.sprite_id)
            self.sprite_list.addItem(item)
        self.sprite_list.currentItemChanged.connect(self._list_changed)
        self.sprite_list.itemDoubleClicked.connect(lambda _item: self.accept())

        self.show_all_check = QCheckBox("Show every sprite's outline")
        self.show_all_check.setChecked(True)
        self.show_all_check.toggled.connect(self._toggle_all)

        self.info_label = QLabel()
        self.info_label.setMinimumWidth(PAGE_SIZE * SCALE)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        left = QVBoxLayout()
        left.addWidget(QLabel("The page's picture (256x256 texture page, at 2x). Click a rectangle to pick its "
                              "sprite;\nwhere several overlap, the smallest is picked. Double-click picks and closes."))
        left.addWidget(self.canvas)
        left.addWidget(self.show_all_check)
        left.addWidget(self.info_label)
        body = QHBoxLayout()
        body.addLayout(left)
        body.addWidget(self.sprite_list)
        layout = QVBoxLayout()
        layout.addLayout(body)
        layout.addWidget(buttons)
        self.setLayout(layout)
        self.select(current_id)

    def selected_id(self):
        return self._selected

    def select(self, sprite_id):
        self._selected = sprite_id
        self.canvas.selected_id = sprite_id
        self.canvas.update()
        for row in range(self.sprite_list.count()):
            item = self.sprite_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == sprite_id:
                if self.sprite_list.currentRow() != row:
                    self.sprite_list.setCurrentRow(row)
                break
        self._show_info(sprite_id, "Picked")

    def _list_changed(self, item, _previous):
        if item is not None and item.data(Qt.ItemDataRole.UserRole) != self._selected:
            self.select(item.data(Qt.ItemDataRole.UserRole))

    def _toggle_all(self, checked):
        self.canvas.show_all = checked
        self.canvas.update()

    def _show_hover(self, sprite_id):
        self._show_info(sprite_id if sprite_id >= 0 else self._selected,
                        "Under the mouse" if sprite_id >= 0 else "Picked")

    def _show_info(self, sprite_id, what):
        sprite = self.canvas._sprite(sprite_id)
        if sprite is None:
            self.info_label.setText(f"{what}: none (the slot shows nothing)" if sprite_id == UNUSED_ID
                                    else f"{what}: {sprite_id} (not in the sprite table)")
            return
        width, height = sprite_size(sprite)
        rects = ", ".join(f"({x},{y}) {w}x{h}" for x, y, w, h in sprite_rects(sprite))
        self.info_label.setText(f"{what}: sprite {sprite_id}, drawn {width}x{height}; cut from {rects}")
