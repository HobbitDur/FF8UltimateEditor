import os
import math
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QRectF, QPointF, QSignalBlocker, QThreadPool
from PyQt6.QtGui import QPixmap, QPainter, QColor, QPen, QPolygonF
from PyQt6.QtWidgets import QWidget, QApplication, QToolTip, QVBoxLayout, QLabel, QCheckBox, QPushButton, QHBoxLayout, QScrollArea

from Cid.worldlandscape import GROUND_NAMES
from Cid.terrainrender import TerrainRenderTask


class DrawMapWidget(QWidget):
    """Block overview, optional wmx triangle resolution, and drag-only movement."""
    BLOCK_COLS, BLOCK_ROWS = 128, 96
    NO_PHASE = -1
    GUIDE_WIDTH = 200
    position_picked = pyqtSignal(int, int, int)  # encoded x, y, triangle (-1 = keep)
    selection_picked = pyqtSignal(int)

    def __init__(self, map_path, parent=None):
        super().__init__(parent)
        self._pixmap = QPixmap(map_path) if map_path and os.path.exists(map_path) else QPixmap()
        self._reference_pixmap = self._pixmap
        self._plain_pixmap = self._pixmap
        self._textured_pixmap = QPixmap()
        self._textures_requested = True
        self.landscape = None
        self._render_generation = 0
        self._texture_tasks = {}
        tasks = self._texture_tasks
        self.destroyed.connect(lambda: [task.cancelled.set() for task in tasks.values()])
        self._draw_list = []
        self._selected_index = -1
        self._press = None
        self._press_selected = False
        self._dragging = False
        self._drag_point = None
        self._zoom = 1.0
        self._pan = QPointF()
        self._pan_press = None
        self._phases = frozenset((*range(5), self.NO_PHASE))
        self._landmarks = []
        self.geometry = None
        self._mesh_pixmap = QPixmap()
        self.setMinimumHeight(280)
        self.setMinimumWidth(480)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setToolTip('Click a marker to select; click and drag any marker to move. Ctrl+Z undoes a move. Mouse wheel zooms. '
                        'Right drag pans; wheel click resets the view. '
                        'Without wmx.obj, markers show approximate block centres; numbers count overlapping records.')
        self.fullscreen_button = QPushButton('Map full screen', self)
        self.fullscreen_button.setCheckable(True)
        self.fullscreen_button.setProperty('read_only_preview', True)
        self.fullscreen_button.setToolTip('Fill the CID tool with the world map')
        self.fullscreen_button.setStyleSheet(
            'QPushButton { color: #e5ebf6; background: #202b48; border: 1px solid #63708e; '
            'border-radius: 3px; padding: 5px 9px; } '
            'QPushButton:hover { background: #304367; } '
            'QPushButton:checked { background: #315b82; }')
        self.fullscreen_button.adjustSize()
        self.fullscreen_button.move(12, 12)
        self._guide = QScrollArea(self)
        self._guide.setProperty('read_only_preview', True)
        self._guide.setWidgetResizable(True)
        self._guide.setStyleSheet('QScrollArea { border: none; background: #121830; } '
                                 'QLabel, QCheckBox { color: #e5ebf6; }')
        self._guide_content = QWidget()
        self._guide_content.setObjectName('cidMapGuide')
        self._guide_content.setStyleSheet('QWidget#cidMapGuide { background: #121830; }')
        self._guide.setWidget(self._guide_content)
        guide_layout = QVBoxLayout(self._guide_content)
        guide_layout.setContentsMargins(12, 12, 12, 12)
        guide_layout.setSpacing(4)
        guide_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        title = QLabel('<b>Map controls</b>')
        guide_layout.addWidget(title)
        self.mesh_check = QCheckBox('Mesh')
        self.mesh_check.setEnabled(False)
        self.mesh_check.setToolTip('Show the terrain triangles from read-only wmx.obj')
        self.mesh_check.toggled.connect(self.set_mesh_visible)
        mesh_row = QHBoxLayout()
        mesh_row.addWidget(self.mesh_check)
        self.reset_button = QPushButton('Reset view')
        self.reset_button.setToolTip('Reset zoom and centre the map (also: middle mouse button)')
        self.reset_button.clicked.connect(self.reset_view)
        mesh_row.addWidget(self.reset_button)
        guide_layout.addLayout(mesh_row)
        self.landmarks_check = QCheckBox('Locations')
        self.landmarks_check.setChecked(True)
        self.landmarks_check.setEnabled(False)
        self.landmarks_check.setToolTip('Reference locations and names from wmsetxx.obj. '
                                        'Fixed references; they do not follow story-phase availability or moving Gardens.')
        self.landmarks_check.toggled.connect(self.update)
        background_row = QHBoxLayout()
        background_row.addWidget(self.landmarks_check)
        self.textures_check = QCheckBox('Textures')
        self.textures_check.setEnabled(False)
        self.textures_check.setToolTip('Use the original low-resolution terrain textures from wmsetxx.obj. '
                                      'Requires wmx.obj; built once in the background. Static base world.')
        self.textures_check.toggled.connect(self.set_textured)
        background_row.addWidget(self.textures_check)
        guide_layout.addLayout(background_row)
        self._texture_status = QLabel('Textures: load wmset and wmx.')
        self._texture_status.setWordWrap(True)
        guide_layout.addWidget(self._texture_status)
        guide_layout.addWidget(QLabel('<b>Landscape</b>'))
        self.terrain_info = QLabel('Load wmx.obj for terrain details.')
        self.terrain_info.setTextFormat(Qt.TextFormat.PlainText)
        self.terrain_info.setWordWrap(True)
        self.terrain_info.setToolTip('Elevation is in game units above sea level; slope is in degrees. '
                                    'Region and reference area names need wmset. The preview uses base-world terrain.')
        guide_layout.addWidget(self.terrain_info)
        self._guide_note = QLabel('Load wmx.obj to see the triangles used for draw-point placement.')
        self._guide_note.setWordWrap(True)
        guide_layout.addWidget(self._guide_note)
        for gesture, action in (('Left click', 'Select point'), ('Left drag', 'Move point'),
                                ('Click again', 'Cycle overlaps'), ('Right drag', 'Pan map'),
                                ('Wheel', 'Zoom at pointer'), ('Wheel click', 'Reset view'),
                                ('Ctrl+Z', 'Undo'), ('Ctrl+Y', 'Redo')):
            control = QLabel(f'<b>{gesture}</b> {action}')
            control.setWordWrap(True)
            guide_layout.addWidget(control)
        self._guide.setToolTip('Redo also supports Ctrl+Shift+Z.')
        self._place_guide()

    def set_draw_list(self, draw_list):
        self._draw_list = draw_list
        self._press, self._dragging, self._drag_point = None, False, None
        self.update()

    def set_landmarks(self, landmarks):
        self._landmarks = list(landmarks)
        self.landmarks_check.setEnabled(bool(self._landmarks))
        self.update()

    def set_landscape(self, landscape):
        self.landscape = landscape
        self._invalidate_textures()
        self._show_terrain()

    def _invalidate_textures(self):
        for task in self._texture_tasks.values():
            task.cancelled.set()
        self._render_generation += 1
        self._textured_pixmap = QPixmap()
        self._pixmap = self._plain_pixmap
        available = self.geometry is not None and self.landscape is not None and self.landscape.textures is not None
        self.textures_check.setEnabled(available)
        if available:
            self._texture_status.setText('Textures ready to build.')
            self._texture_status.setToolTip('')
            self.set_textured(self._textures_requested)
        else:
            with QSignalBlocker(self.textures_check):
                self.textures_check.setChecked(False)
            error = self.landscape.texture_error if self.landscape else ''
            self._texture_status.setText('Textures unavailable.' if error else 'Textures: load wmset and wmx.')
            self._texture_status.setToolTip(error)
        self.update()

    def set_textured(self, visible):
        self._textures_requested = bool(visible)
        visible = bool(visible and self.textures_check.isEnabled())
        with QSignalBlocker(self.textures_check):
            self.textures_check.setChecked(visible)
        if visible and self._textured_pixmap.isNull():
            generation = self._render_generation
            if generation not in self._texture_tasks:
                task = TerrainRenderTask(generation, self.geometry, self.landscape.textures)
                self._texture_tasks[generation] = task
                task.signals.finished.connect(self._on_textures_ready)
                self._texture_status.setText('Building textures…')
                QThreadPool.globalInstance().start(task)
        self._pixmap = self._textured_pixmap if visible and not self._textured_pixmap.isNull() else self._plain_pixmap
        self.update()

    @pyqtSlot(int, bytes, str)
    def _on_textures_ready(self, generation, data, error):
        self._texture_tasks.pop(generation, None)
        if generation != self._render_generation:
            return
        if error or not data or not self._textured_pixmap.loadFromData(data):
            with QSignalBlocker(self.textures_check):
                self.textures_check.setChecked(False)
            self._texture_status.setText('Textures unavailable; using colours.')
            self._texture_status.setToolTip(error or 'Could not render the texture preview')
            self._pixmap = self._plain_pixmap
        else:
            self._texture_status.setText('Textures cached (base world).')
            self._texture_status.setToolTip('Static original textures from wmset. Story replacement terrain and animations are not simulated.')
            self.set_textured(self.textures_check.isChecked())
        self.update()

    def _show_terrain(self, position=None):
        if self.geometry is None:
            self.terrain_info.setText('Load wmx.obj for terrain details.')
            return
        draw = None
        if position is not None:
            if not self._map_viewport().contains(position) or not self._image_rect().contains(position):
                position = None
            else:
                hits = self._hits(position)
                if hits:
                    index = self._selected_index if self._selected_index in hits else hits[0]
                    draw = self._draw_list[index]
        if position is None and 0 <= self._selected_index < len(self._draw_list):
            candidate = self._draw_list[self._selected_index]
            if self._visible(candidate):
                draw = candidate
        if draw is not None:
            position = self._marker(draw, self._image_rect())
        if position is None:
            self.terrain_info.setText('Hover over the map or select a world draw point.')
            return
        x, y = self._map_position(position, self._image_rect())
        try:
            info = self.geometry.terrain_at(x, y, draw.sub_id if draw else None)
        except (ValueError, IndexError):
            info = None
        if info is None:
            self.terrain_info.setText('No triangle at this position.')
            return
        lines = [f'Draw ID {draw.get_id()}' if draw else 'Under pointer']
        if self.landscape:
            place = self.landscape.location_at(x, y)
            if place.get('location_name'):
                lines.append(place['location_name'])
            if place.get('region') is not None:
                lines.append(f"Region: {place['region_name']} ({place['region']})")
        ground = info['ground']
        lines.extend((f"Ground: {GROUND_NAMES.get(ground, 'Unknown')} ({ground})",
                      f"Block: {info['block_x']}, {info['block_y']} · Triangle: {info['triangle']}",
                      f"Height: {info['height']:.1f} game units", f"Slope: {info['slope']:.1f}°"))
        self.terrain_info.setText('\n'.join(lines))

    def leaveEvent(self, event):
        self._show_terrain()
        super().leaveEvent(event)

    def _paint_landmarks(self, painter, rect, viewport):
        if not self.landmarks_check.isChecked():
            return
        occupied = []
        metrics = painter.fontMetrics()
        for name, x, y in self._landmarks:
            point = self._block_to_point(x, y, rect)
            if not viewport.contains(point):
                continue
            painter.setPen(QPen(QColor(255, 224, 150), 1))
            painter.setBrush(QColor(30, 35, 45, 220))
            painter.drawRect(QRectF(point.x() - 3, point.y() - 3, 6, 6))
            width, height = metrics.horizontalAdvance(name) + 8, metrics.height() + 4
            for dx, dy in ((7, -height / 2), (7, -height - 5), (7, 5), (-width - 7, -height / 2)):
                label = QRectF(point.x() + dx, point.y() + dy, width, height)
                if viewport.contains(label) and not any(label.intersects(other) for other in occupied):
                    painter.fillRect(label, QColor(18, 24, 38, 210))
                    painter.setPen(QColor(255, 224, 150))
                    painter.drawText(label, Qt.AlignmentFlag.AlignCenter, name)
                    occupied.append(label.adjusted(-2, -2, 2, 2))
                    break

    def set_geometry(self, geometry, overview=None):
        self.geometry = geometry
        self._mesh_pixmap = QPixmap()
        self.mesh_check.setEnabled(geometry is not None)
        self._guide_note.setText('A draw point covers a triangle. Enable Mesh and zoom in to choose its location.'
                                 if geometry else 'Load wmx.obj to see the triangles used for draw-point placement.')
        self.set_mesh_visible(self.mesh_check.isChecked() and geometry is not None)
        self._pixmap = overview if overview is not None else self._reference_pixmap
        self._plain_pixmap = self._pixmap
        self._invalidate_textures()
        self.reset_view()

    def set_mesh_visible(self, visible):
        visible = bool(visible and self.geometry is not None)
        if visible and self._mesh_pixmap.isNull():
            try:
                if not self._mesh_pixmap.loadFromData(self.geometry.mesh_png()):
                    raise ValueError('Could not build the triangle overlay')
            except Exception as error:
                visible = False
                self._guide_note.setText(f'Mesh unavailable: {error}')
        with QSignalBlocker(self.mesh_check):
            self.mesh_check.setChecked(visible)
        self.update()

    def reset_view(self):
        self._zoom, self._pan = 1., QPointF()
        self._pan_press = None
        self._press, self._dragging, self._drag_point = None, False, None
        self.unsetCursor()
        self._show_terrain()
        self.update()

    def _map_viewport(self):
        return QRectF(0, 0, max(1, self.width() - self.GUIDE_WIDTH), self.height())

    def _place_guide(self):
        self._guide.setGeometry(int(self._map_viewport().width()), 0, self.GUIDE_WIDTH, self.height())

    def resizeEvent(self, event):
        self._place_guide()
        super().resizeEvent(event)

    def set_selected(self, index):
        self._selected_index = index
        self._press, self._dragging, self._drag_point = None, False, None
        self._show_terrain()
        self.update()

    def set_phase(self, phase):
        self.set_phases(range(5) if phase is None else (phase,))

    def set_phases(self, phases):
        self._phases = frozenset(phases)
        self._press, self._dragging, self._drag_point = None, False, None
        self.update()

    def refresh(self):
        self._show_terrain()
        self.update()

    def _image_rect(self):
        w, h = (self._pixmap.width(), self._pixmap.height()) if not self._pixmap.isNull() else (128, 96)
        viewport = self._map_viewport()
        scale = min(viewport.width() / w, viewport.height() / h) * self._zoom
        return QRectF(viewport.center().x() - w * scale / 2 + self._pan.x(),
                      viewport.center().y() - h * scale / 2 + self._pan.y(), w * scale, h * scale)

    def _block_to_point(self, x, y, rect):
        return QPointF(rect.x() + x / 128 * rect.width(), rect.y() + y / 96 * rect.height())

    def _map_position(self, point, rect):
        return ((point.x() - rect.x()) / rect.width() * 128,
                (point.y() - rect.y()) / rect.height() * 96)

    def _visible(self, draw):
        if not draw.is_world() or not draw.position_loaded:
            return False
        if not draw.world_phases:
            return self.NO_PHASE in self._phases
        return bool(self._phases.intersection(draw.world_phases))

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
        if not self._map_viewport().contains(position):
            return []
        rect = self._image_rect()
        candidates = [(i, self._marker(draw, rect)) for i, draw in enumerate(self._draw_list)
                      if self._visible(draw)]
        candidates = [(i, point) for i, point in candidates if (point - position).manhattanLength() <= 10]
        if not candidates:
            return []
        nearest = min(candidates, key=lambda item: (item[1] - position).manhattanLength())[1]
        # A nearby selected marker must not steal a drag from the marker under
        # the pointer. Preserve cycling only for records at the same position.
        return [i for i, point in candidates if (point - nearest).manhattanLength() < .01]

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(18, 24, 48))
        viewport = self._map_viewport()
        painter.setClipRect(viewport)
        rect = self._image_rect()
        if not self._pixmap.isNull():
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.drawPixmap(rect.toRect(), self._pixmap)
        if self.mesh_check.isChecked() and not self._mesh_pixmap.isNull():
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.drawPixmap(rect.toRect(), self._mesh_pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._paint_landmarks(painter, rect, viewport)
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
                label_x = max(2., min(point.x() + 9, viewport.right() - metrics.horizontalAdvance(label) - 2))
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
        if not self._map_viewport().contains(event.position()):
            return
        if event.button() == Qt.MouseButton.MiddleButton:
            self.reset_view()
            event.accept()
            return
        if event.button() == Qt.MouseButton.RightButton:
            self._pan_press = (event.position(), QPointF(self._pan))
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        hits = self._hits(event.position())
        if hits:
            was_selected = self._selected_index in hits
            if not was_selected:
                self.set_selected(hits[0])
                self.selection_picked.emit(hits[0])
            # Selection callbacks reset the drag state; arm this gesture afterwards.
            self._press_selected = was_selected
            self._press = event.position()
            self.setFocus(Qt.FocusReason.MouseFocusReason)

    def mouseMoveEvent(self, event):
        if self._pan_press is not None:
            if event.buttons() & Qt.MouseButton.RightButton:
                origin, start_pan = self._pan_press
                self._pan = start_pan + event.position() - origin
                self._show_terrain(event.position())
                self.update()
                event.accept()
                return
            self._pan_press = None
            self.unsetCursor()
        self._show_terrain(event.position())
        if self._press is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            hits = self._hits(event.position())
            if hits:
                precision = ('terrain triangle positions' if self.geometry else
                             'approximate block centres; load wmx.obj to separate their triangles')
                header = (f'{len(hits)} records at this marker ({precision}).\n' if len(hits) > 1 else '')
                QToolTip.showText(event.globalPosition().toPoint(), header + '\n'.join(
                    f'ID {self._draw_list[i].get_id()} - Magic ID {self._draw_list[i].magic_index} '
                    f'{self._draw_list[i].get_magic_name()} (triangle {self._draw_list[i].sub_id})'
                    + (' - No phase (unused)' if not self._draw_list[i].world_phases else '')
                    for i in hits), self)
            elif self.landmarks_check.isChecked():
                for name, x, y in self._landmarks:
                    if (self._block_to_point(x, y, self._image_rect()) - event.position()).manhattanLength() <= 10:
                        QToolTip.showText(event.globalPosition().toPoint(), name + ' (reference location)', self)
                        break
            return
        if (event.position() - self._press).manhattanLength() >= QApplication.startDragDistance():
            self._dragging = True
            self._drag_point = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self._pan_press = None
            self.unsetCursor()
            event.accept()
            return
        press, dragging = self._press, self._dragging
        self._press, self._dragging = None, False
        self._drag_point = None
        self.unsetCursor()
        self.update()
        if event.button() != Qt.MouseButton.LeftButton or press is None:
            return
        if not dragging:
            hits = self._hits(event.position())
            if self._press_selected and len(hits) > 1 and self._selected_index in hits:
                self.selection_picked.emit(hits[(hits.index(self._selected_index) + 1) % len(hits)])
            return
        rect = self._image_rect()
        if not self._map_viewport().contains(event.position()) or not rect.contains(event.position()):
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
        if not self._map_viewport().contains(event.position()):
            event.ignore()
            return
        old = self._image_rect()
        zoom = max(1., min(12., self._zoom * (1.25 if event.angleDelta().y() > 0 else .8)))
        ratio = zoom / self._zoom
        self._zoom = zoom
        if zoom == 1:
            self._pan = QPointF()
        else:
            centre = self._map_viewport().center()
            self._pan = event.position() + (old.center() - event.position()) * ratio - centre
        self.update()
        event.accept()
