import os

from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QPointF
from PyQt6.QtGui import QPixmap, QPainter, QColor, QPen, QBrush
from PyQt6.QtWidgets import QWidget


class DrawMapWidget(QWidget):
    """World-map view for locating / placing world draw points.

    Draw points are anchored to a 128 x 96 block grid. A record's block is
    ``blockX = x & 0x7F`` (west->east), ``blockY = 2*y + (x >> 7)`` (north->south),
    which maps linearly onto the world map image. Clicking the map converts the
    pixel back to a block and emits :attr:`position_picked` with the encoded
    ``(x, y)`` record bytes.
    """

    BLOCK_COLS = 128
    BLOCK_ROWS = 96
    position_picked = pyqtSignal(int, int)  # encoded record bytes (x, y)

    def __init__(self, map_path, parent=None):
        super().__init__(parent)
        self._pixmap = QPixmap(map_path) if map_path and os.path.exists(map_path) else QPixmap()
        self._draw_list = []
        self._selected_index = -1  # index into _draw_list, or -1
        self.setMinimumHeight(280)
        self.setToolTip("Click to place the selected world draw point")

    def set_draw_list(self, draw_list):
        self._draw_list = draw_list
        self.update()

    def set_selected(self, index):
        self._selected_index = index
        self.update()

    def refresh(self):
        self.update()

    def _image_rect(self) -> QRectF:
        if self._pixmap.isNull():
            return QRectF(0, 0, self.width(), self.height())
        pixmap_w, pixmap_h = self._pixmap.width(), self._pixmap.height()
        scale = min(self.width() / pixmap_w, self.height() / pixmap_h)
        width, height = pixmap_w * scale, pixmap_h * scale
        return QRectF((self.width() - width) / 2, (self.height() - height) / 2, width, height)

    def _block_to_point(self, block_x, block_y, rect: QRectF) -> QPointF:
        px = rect.x() + block_x / self.BLOCK_COLS * rect.width()
        py = rect.y() + block_y / self.BLOCK_ROWS * rect.height()
        return QPointF(px, py)

    @staticmethod
    def _is_placed(draw):
        # Draw ID 256 (and any unset world row) sits at block (0,0); treat as unplaced.
        return not (draw.x == 0 and draw.y == 0)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(18, 24, 48))
        rect = self._image_rect()
        if not self._pixmap.isNull():
            painter.drawPixmap(rect.toRect(), self._pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        selected_point = None
        for index, draw in enumerate(self._draw_list):
            if not draw.is_world() or not self._is_placed(draw):
                continue
            block_x, block_y = draw.get_block_xy()
            point = self._block_to_point(block_x, block_y, rect)
            if index == self._selected_index:
                selected_point = (point, draw)
                continue
            painter.setPen(QPen(QColor(255, 235, 120), 1))
            painter.setBrush(QBrush(QColor(235, 60, 60)))
            painter.drawEllipse(point, 3.0, 3.0)

        # Draw the selected marker last so it stays on top.
        if selected_point is not None:
            point, draw = selected_point
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            painter.setBrush(QBrush(QColor(0, 200, 255)))
            painter.drawEllipse(point, 6.0, 6.0)
            label = f"ID {draw.get_id()}"
            painter.setPen(QPen(QColor(255, 255, 255)))
            painter.drawText(QPointF(point.x() + 9, point.y() + 4), label)
        painter.end()

    def mousePressEvent(self, event):
        if self._selected_index < 0:
            return
        rect = self._image_rect()
        pos = event.position()
        if not rect.contains(pos):
            return
        norm_x = (pos.x() - rect.x()) / rect.width()
        norm_y = (pos.y() - rect.y()) / rect.height()
        block_x = max(0, min(self.BLOCK_COLS - 1, round(norm_x * self.BLOCK_COLS)))
        block_y = max(0, min(self.BLOCK_ROWS - 1, round(norm_y * self.BLOCK_ROWS)))
        x = (block_x & 0x7F) | ((block_y & 1) << 7)
        y = block_y >> 1
        self.position_picked.emit(x, y)
