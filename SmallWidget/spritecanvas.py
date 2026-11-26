"""A texture page with the SP2 sprites' rectangles drawn over it: see where each sprite cuts the
picture, hover one, click to pick it. Used by Zone's sprite picker and Shiva's Sprites tab.

A sprite of the SP2 table (mngrp.bin, Shiva > Sprites) is a list of quads, each a rectangle
(u, v, width, height) cut out of the page picture and drawn 1:1. Every magazine sprite cuts from
whatever picture the page shows, so the rectangles are drawn over a page picture.
"""
from PyQt6.QtCore import Qt, QRect, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QDialog, QWidget

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

    def __init__(self, picture=None, sprites=None, parent=None):
        QWidget.__init__(self, parent)
        self.setMouseTracking(True)
        self.setFixedSize(PAGE_SIZE * SCALE, PAGE_SIZE * SCALE)
        self.sprites = []
        self.selected_id = -1
        self.hover_id = -1
        self.show_all = True
        self._pixmap = None
        self.set_picture(picture)
        self.set_sprites(sprites)

    def set_picture(self, picture):
        """The picture (a PIL image, or None) the rectangles are drawn over."""
        self._pixmap = None
        if picture is not None:
            rgba = picture.convert("RGBA")
            image = QImage(rgba.tobytes("raw", "RGBA"), rgba.width, rgba.height,
                           QImage.Format.Format_RGBA8888).copy()
            self._pixmap = QPixmap.fromImage(image).scaled(
                rgba.width * SCALE, rgba.height * SCALE,
                Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)
        self.update()

    def set_sprites(self, sprites):
        """The sprites to outline (only the usable ones are kept); call again after an edit."""
        self.sprites = usable_sprites(sprites)
        self.update()

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
