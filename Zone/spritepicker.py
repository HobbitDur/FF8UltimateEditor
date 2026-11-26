"""Pick a picture overlay's sprite by seeing it: the page's whole picture with every sprite's
rectangles drawn over it, instead of an id in a list.

A sprite of the SP2 table (mngrp.bin, Shiva > Sprites) is a list of quads, each a rectangle
(u, v, width, height) cut out of the page picture and drawn 1:1. Every magazine sprite cuts from
whatever picture the page shows, so the rectangles are drawn over this page's picture.
"""
from PyQt6.QtCore import Qt, QRect, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QListWidget,
                             QListWidgetItem, QVBoxLayout, QWidget, QCheckBox)

UNUSED_ID = 0xFF
SCALE = 2
# The texture page the sprites cut from is 256 texels wide; the pictures are 256x192, a few
# sprites reach below them, so the canvas shows the whole 256x256 page.
PAGE_SIZE = 256


def sprite_rects(sprite):
    """The rectangles (u, v, width, height) a sprite cuts out of the picture."""
    return [(quad.u, quad.v, quad.width, quad.height) for quad in sprite.quads]


def sprite_size(sprite):
    """Width x height of the sprite as drawn (its quads' bounding box, offsets included)."""
    width = max(q.dx + q.width for q in sprite.quads) - min(q.dx for q in sprite.quads)
    height = max(q.dy + q.height for q in sprite.quads) - min(q.dy for q in sprite.quads)
    return width, height


def usable_sprites(sprites):
    """The sprites a page can show: used, with quads, not the 'unused' id."""
    return [sprite for sprite in sprites or []
            if sprite.used and sprite.quads and sprite.sprite_id != UNUSED_ID]


def sprite_at(sprites, u, v):
    """The sprite whose rectangles hold texel (u, v), the smallest one when several do (so a small
    sprite inside a big one can still be clicked), or None."""
    best = None
    best_area = None
    for sprite in sprites:
        for x, y, width, height in sprite_rects(sprite):
            if x <= u < x + width and y <= v < y + height:
                area = width * height
                if best_area is None or area < best_area:
                    best, best_area = sprite, area
    return best


class SpriteCanvas(QWidget):
    """The picture at 2x with the sprites' rectangles; hover shows one, click picks it."""

    picked = pyqtSignal(int)    # a sprite id, clicked
    hovered = pyqtSignal(int)   # a sprite id under the mouse, or -1

    def __init__(self, picture, sprites, parent=None):
        QWidget.__init__(self, parent)
        self.setMouseTracking(True)
        self.setFixedSize(PAGE_SIZE * SCALE, PAGE_SIZE * SCALE)
        self.sprites = sprites
        self.selected_id = -1
        self.hover_id = -1
        self.show_all = True
        self._pixmap = None
        if picture is not None:
            rgba = picture.convert("RGBA")
            image = QImage(rgba.tobytes("raw", "RGBA"), rgba.width, rgba.height,
                           QImage.Format.Format_RGBA8888).copy()
            self._pixmap = QPixmap.fromImage(image).scaled(
                rgba.width * SCALE, rgba.height * SCALE,
                Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)

    def _sprite(self, sprite_id):
        for sprite in self.sprites:
            if sprite.sprite_id == sprite_id:
                return sprite
        return None

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(24, 24, 32))
        if self._pixmap is not None:
            painter.drawPixmap(0, 0, self._pixmap)
        else:
            painter.setPen(QColor(200, 200, 200))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "No picture for this page\n(open mngrp.bin, or pick its page texture)")
        if self.show_all:
            painter.setPen(QPen(QColor(255, 255, 255, 90), 1))
            for sprite in self.sprites:
                for x, y, width, height in sprite_rects(sprite):
                    painter.drawRect(QRect(x * SCALE, y * SCALE, width * SCALE - 1, height * SCALE - 1))
        self._outline(painter, self.hover_id, QColor(80, 200, 255), fill=QColor(80, 200, 255, 50))
        self._outline(painter, self.selected_id, QColor(255, 220, 0), fill=QColor(255, 220, 0, 60), width=3)

    def _outline(self, painter, sprite_id, color, fill, width=2):
        sprite = self._sprite(sprite_id)
        if sprite is None:
            return
        for x, y, w, h in sprite_rects(sprite):
            box = QRect(x * SCALE, y * SCALE, w * SCALE - 1, h * SCALE - 1)
            painter.fillRect(box, fill)
            painter.setPen(QPen(color, width))
            painter.drawRect(box)
        x, y, _w, _h = sprite_rects(sprite)[0]
        painter.setPen(QColor(0, 0, 0))
        painter.fillRect(QRect(x * SCALE, y * SCALE, 34, 16), color)
        painter.drawText(QRect(x * SCALE, y * SCALE, 34, 16), Qt.AlignmentFlag.AlignCenter,
                         str(sprite.sprite_id))

    def _sprite_under(self, event):
        position = event.position()
        sprite = sprite_at(self.sprites, int(position.x()) // SCALE, int(position.y()) // SCALE)
        return sprite.sprite_id if sprite is not None else -1

    def mouseMoveEvent(self, event):
        sprite_id = self._sprite_under(event)
        if sprite_id != self.hover_id:
            self.hover_id = sprite_id
            self.hovered.emit(sprite_id)
            self.update()

    def leaveEvent(self, _event):
        self.hover_id = -1
        self.hovered.emit(-1)
        self.update()

    def mousePressEvent(self, event):
        sprite_id = self._sprite_under(event)
        if sprite_id >= 0:
            self.picked.emit(sprite_id)

    def mouseDoubleClickEvent(self, event):
        self.mousePressEvent(event)
        window = self.window()
        if isinstance(window, QDialog) and self._sprite_under(event) >= 0:
            window.accept()


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
