"""Pick a picture overlay's sprite by seeing it: the page's whole picture with every sprite's
rectangles drawn over it (SmallWidget/spritecanvas.py's SpriteView, shared with Shiva's Sprites tab),
instead of an id in a list."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QHBoxLayout, QListWidget, QListWidgetItem, QVBoxLayout

from SmallWidget.spritecanvas import UNUSED_ID, SpriteView, sprite_at, sprite_size, usable_sprites

__all__ = ["SpritePickerDialog", "sprite_at", "UNUSED_ID"]


class SpritePickerDialog(QDialog):
    """Choose a sprite on the page's picture. selected_id() is the choice (UNUSED_ID = none)."""

    def __init__(self, picture, sprites, current_id=UNUSED_ID, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowTitle("Pick a sprite")
        self.sprites = usable_sprites(sprites)

        self.view = SpriteView("The page's picture (its 256x256 texture page, at 2x). Click a rectangle to pick "
                               "its sprite (the smallest where several overlap); double-click picks and closes.")
        self.view.set_picture(picture)
        self.view.set_sprites(self.sprites)
        self.view.picked.connect(self.select)

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

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        body = QHBoxLayout()
        body.addWidget(self.view)
        body.addWidget(self.sprite_list)
        layout = QVBoxLayout(self)
        layout.addLayout(body)
        layout.addWidget(buttons)
        self.select(current_id)

    def selected_id(self):
        return self.view.selected_id()

    def select(self, sprite_id):
        self.view.select(sprite_id)
        for row in range(self.sprite_list.count()):
            if self.sprite_list.item(row).data(Qt.ItemDataRole.UserRole) == sprite_id:
                if self.sprite_list.currentRow() != row:
                    self.sprite_list.setCurrentRow(row)
                break

    def _list_changed(self, item, _previous):
        if item is not None and item.data(Qt.ItemDataRole.UserRole) != self.selected_id():
            self.select(item.data(Qt.ItemDataRole.UserRole))
