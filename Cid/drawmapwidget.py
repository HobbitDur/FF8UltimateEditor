import os
import math
from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QPointF
from PyQt6.QtGui import QPixmap, QPainter, QColor, QPen, QPolygonF
from PyQt6.QtWidgets import QWidget, QApplication, QToolTip


class DrawMapWidget(QWidget):
    """Block overview, optional wmx triangle resolution, and drag-only movement."""
    BLOCK_COLS, BLOCK_ROWS = 128, 96
    NO_PHASE = -1
    position_picked = pyqtSignal(int, int, int)  # encoded x, y, triangle (-1 = keep)
    selection_picked = pyqtSignal(int)

    def __init__(self, map_path, parent=None):
        super().__init__(parent)
        self._pixmap = QPixmap(map_path) if map_path and os.path.exists(map_path) else QPixmap()
        self._reference_pixmap = self._pixmap
        self._draw_list = []
        self._selected_index = -1
        self._press = None
        self._dragging = False
        self._drag_point = None
        self._zoom = 1.0
        self._pan = QPointF()
        self._phase = 0
        self.geometry = None
        self.setMinimumHeight(280)
        self.setMouseTracking(True)
        self.setToolTip('Click a marker to select; drag the selected marker to move. Mouse wheel zooms. '
                        'Without wmx.obj, markers show approximate block centres; numbers count overlapping records.')

    def set_draw_list(self, draw_list):
        self._draw_list = draw_list
        self._press, self._dragging, self._drag_point = None, False, None
        self.update()

    def set_geometry(self, geometry, overview=None):
        self.geometry = geometry
        self._pixmap = overview if overview is not None else self._reference_pixmap
        self._zoom, self._pan = 1., QPointF()
        self._press, self._dragging, self._drag_point = None, False, None
        self.update()

    def set_selected(self, index):
        self._selected_index = index
        self._press, self._dragging, self._drag_point = None, False, None
        self.update()

    def set_phase(self, phase):
        self._phase = phase
        self._press, self._dragging, self._drag_point = None, False, None
        self.update()

    def refresh(self):
        self.update()

    def _image_rect(self):
        w, h = (self._pixmap.width(), self._pixmap.height()) if not self._pixmap.isNull() else (128, 96)
        scale = min(self.width() / w, self.height() / h) * self._zoom
        return QRectF((self.width() - w * scale) / 2 + self._pan.x(),
                      (self.height() - h * scale) / 2 + self._pan.y(), w * scale, h * scale)

    def _block_to_point(self, x, y, rect):
        return QPointF(rect.x() + x / 128 * rect.width(), rect.y() + y / 96 * rect.height())

    def _map_position(self, point, rect):
        return ((point.x() - rect.x()) / rect.width() * 128,
                (point.y() - rect.y()) / rect.height() * 96)

    def _visible(self, draw):
        if not draw.is_world() or not draw.position_loaded:
            return False
        if self._phase == self.NO_PHASE:
            return not draw.world_phases
        return bool(draw.world_phases) and (self._phase is None or self._phase in draw.world_phases)

    def _marker(self, draw, rect):
        triangle = self._triangle(draw)
        if triangle:
            return self._block_to_point(sum(p[0] for p in triangle) / 3,
                                        sum(p[1] for p in triangle) / 3, rect)
        bx, by = draw.get_block_xy()
        return self._block_to_point(bx + .5, by + .5, rect)

    def _triangle(self, draw):
        try:
            return self.geometry.triangle(draw) if self.geometry else None
        except (ValueError, IndexError):
            # A malformed destination block must not raise through a Qt paint callback.
            return None

    def _hits(self, position):
        rect = self._image_rect()
        return [i for i, draw in enumerate(self._draw_list)
                if self._visible(draw) and (self._marker(draw, rect) - position).manhattanLength() <= 10]

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(18, 24, 48))
        rect = self._image_rect()
        if not self._pixmap.isNull():
            painter.drawPixmap(rect.toRect(), self._pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        groups = {}
        for index, draw in enumerate(self._draw_list):
            if not self._visible(draw):
                continue
            point = self._marker(draw, rect)
            groups.setdefault((round(point.x(), 2), round(point.y(), 2)), []).append(index)
            painter.setPen(QPen(QColor(255, 235, 120), 1))
            painter.setBrush(QColor(235, 60, 60))
            painter.drawEllipse(point, 3., 3.)
        painter.setPen(QColor('white'))
        for (x, y), indices in groups.items():
            if len(indices) > 1:
                painter.drawText(QPointF(x + 5, y - 5), str(len(indices)))
        if 0 <= self._selected_index < len(self._draw_list):
            draw = self._draw_list[self._selected_index]
            if self._visible(draw):
                bx, by = draw.get_block_xy()
                triangle = self._triangle(draw)
                painter.setPen(QPen(QColor(0, 220, 255), 1))
                painter.setBrush(QColor(0, 200, 255, 65))
                if triangle:
                    painter.drawPolygon(QPolygonF([self._block_to_point(*p, rect) for p in triangle]))
                else:
                    painter.drawRect(QRectF(self._block_to_point(bx, by, rect),
                                            self._block_to_point(bx + 1, by + 1, rect)))
                point = self._marker(draw, rect)
                painter.setPen(QPen(QColor('white'), 2))
                painter.setBrush(QColor(0, 200, 255))
                painter.drawEllipse(point, 6., 6.)
                name = draw.get_magic_name()
                label = f'ID {draw.get_id()}' + (f' - {name}' if name else '')
                metrics = painter.fontMetrics()
                label_x = max(2., min(point.x() + 9, self.width() - metrics.horizontalAdvance(label) - 2))
                label_y = max(float(metrics.ascent() + 2),
                              min(point.y() + 4, self.height() - metrics.descent() - 2))
                painter.drawText(QPointF(label_x, label_y), label)
        if self._dragging and self._drag_point is not None:
            painter.setPen(QPen(QColor('white'), 2, Qt.PenStyle.DashLine))
            painter.setBrush(QColor(0, 200, 255, 120))
            painter.drawEllipse(self._drag_point, 7., 7.)
        painter.end()

    def mousePressEvent(self, event):
        self._press, self._dragging = None, False
        self._drag_point = None
        if event.button() != Qt.MouseButton.LeftButton:
            return
        hits = self._hits(event.position())
        if self._selected_index in hits:
            self._press = event.position()
        elif hits:
            self.selection_picked.emit(hits[0])

    def mouseMoveEvent(self, event):
        if self._press is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            hits = self._hits(event.position())
            if hits:
                precision = ('terrain triangle positions' if self.geometry else
                             'approximate block centres; load wmx.obj to separate their triangles')
                header = (f'{len(hits)} records near this marker ({precision}).\n' if len(hits) > 1 else '')
                QToolTip.showText(event.globalPosition().toPoint(), header + '\n'.join(
                    f'ID {self._draw_list[i].get_id()} - Magic ID {self._draw_list[i].magic_index} '
                    f'{self._draw_list[i].get_magic_name()} (triangle {self._draw_list[i].sub_id})'
                    + (' - No phase (unused)' if not self._draw_list[i].world_phases else '')
                    for i in hits), self)
            return
        if (event.position() - self._press).manhattanLength() >= QApplication.startDragDistance():
            self._dragging = True
            self._drag_point = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.update()

    def mouseReleaseEvent(self, event):
        press, dragging = self._press, self._dragging
        self._press, self._dragging = None, False
        self._drag_point = None
        self.unsetCursor()
        self.update()
        if event.button() != Qt.MouseButton.LeftButton or press is None:
            return
        if not dragging:
            hits = self._hits(event.position())
            if len(hits) > 1 and self._selected_index in hits:
                self.selection_picked.emit(hits[(hits.index(self._selected_index) + 1) % len(hits)])
            return
        rect = self._image_rect()
        if not rect.contains(event.position()):
            return
        x, y = self._map_position(event.position(), rect)
        if self.geometry:
            try:
                picked = self.geometry.pick(x, y)
            except (ValueError, IndexError):
                picked = None
            if picked:
                self.position_picked.emit(*picked)
        else:
            bx, by = min(127, math.floor(x)), min(95, math.floor(y))
            self.position_picked.emit(bx | ((by & 1) << 7), by >> 1, -1)

    def wheelEvent(self, event):
        old = self._image_rect()
        zoom = max(1., min(12., self._zoom * (1.25 if event.angleDelta().y() > 0 else .8)))
        ratio = zoom / self._zoom
        self._zoom = zoom
        if zoom == 1:
            self._pan = QPointF()
        else:
            centre = QPointF(self.width() / 2, self.height() / 2)
            self._pan = event.position() + (old.center() - event.position()) * ratio - centre
        self.update()
        event.accept()
