"""Ifrit3D timeline: what changed in the animations, bone by bone and frame by frame.

A dope sheet like in animation software: one column per frame of the current animation, one row per
bone (plus a summary row and the model position), and a dot on every cell that differs from the
reference - the file as it was opened, or a vanilla file the user picks. The dot grows with the size
of the change. A strip above lists every animation, with a dot on the changed ones.

Clicking a cell jumps the 3D view to that frame and selects the bone (Ctrl+click adds it to the
selection); right-click reverts cells to the reference. The comparison itself is FF8GameData.dat.
animdiff; this module only paints it and reports what the user clicked.
"""
from PyQt6.QtCore import Qt, QRect, QRectF, QPoint, QSize, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QFont
from PyQt6.QtWidgets import (QAbstractScrollArea, QComboBox, QHBoxLayout, QLabel, QMenu, QPushButton,
                             QScrollArea, QSizePolicy, QToolTip, QVBoxLayout, QWidget)

from FF8GameData.dat.animdiff import (ROW_POSITION, STATUS_CHANGED, STATUS_NEW, STATUS_REMOVED,
                                      raw_to_degrees)

ROW_SUMMARY = -2

CHANGE_COLOUR = QColor("#E8743B")
NEW_COLOUR = QColor("#8E7BE0")
PLAYHEAD_COLOUR = QColor(80, 140, 230, 70)
SELECTED_ROW_COLOUR = QColor(232, 116, 59, 40)

# Rotation change (degrees) -> dot radius
DOT_LEVELS = ((2.0, 2.5), (15.0, 4.0), (float("inf"), 5.5))


def dot_radius(degrees: float) -> float:
    for limit, radius in DOT_LEVELS:
        if degrees < limit:
            return radius
    return DOT_LEVELS[-1][1]


def describe_cell(diff, row: int, frame: int, row_label: str) -> str:
    """Tooltip text of a cell."""
    reference_frame = diff.frame_map[frame] if diff and frame < len(diff.frame_map) else frame
    where = f"{row_label}, frame {frame}"
    if diff and diff.retimed:
        where += f" (compared with reference frame {reference_frame})"
    cell = diff.cells.get((row, frame)) if diff else None
    if cell is None:
        return f"{where}: same as the reference"
    if cell.new_bone:
        return f"{where}: this bone is not in the reference"
    if row == ROW_POSITION:
        x, y, z = cell.position
        return f"{where}: position moved by X {x:+d}, Y {y:+d}, Z {z:+d} (raw)"
    parts = [f"{axis} {raw_to_degrees(value):+.1f}°" for axis, value in zip("XYZ", cell.rotation) if value]
    text = f"{where}: rotation " + ", ".join(parts) if parts else f"{where}:"
    if cell.scale_changed:
        text += ("," if parts else "") + " scale " + ", ".join(
            f"{axis} {value / 1024:+.3f}" for axis, value in zip("XYZ", cell.scale) if value)
    return text


class DopeSheetView(QAbstractScrollArea):
    """The painted grid. The name column and the frame header stay in place while the cells scroll."""
    cell_clicked = pyqtSignal(int, int, bool)            # frame (-1 = name column), bone (-1 = none), ctrl
    revert_requested = pyqtSignal(list)                  # [(row, frame), ...]

    NAME_WIDTH = 170
    ROW_HEIGHT = 18
    HEADER_HEIGHT = 18
    MIN_CELL, MAX_CELL = 6, 44

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []            # (row id, label, depth): ROW_SUMMARY, ROW_POSITION, then bone ids
        self._diff = None          # AnimationDiff of the shown animation, None = no reference
        self._changed_rows = set()
        self._nb_frames = 0
        self._current_frame = 0
        self._selected_bones = set()
        self._cell_width = 18
        self._can_revert = False
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    # ── Data ───────────────────────────────────────────────────────────────
    def set_rows(self, bone_rows):
        """bone_rows: (bone id, label, depth) of every bone, in display order."""
        self._rows = [(ROW_SUMMARY, "All bones", 0), (ROW_POSITION, "Model position", 0)] + list(bone_rows)
        self._update_scrollbars()
        self.viewport().update()

    def set_animation(self, nb_frames: int, diff, can_revert: bool):
        self._nb_frames = nb_frames
        self._diff = diff
        self._changed_rows = diff.changed_rows() if diff else set()
        self._can_revert = can_revert
        self._update_scrollbars()
        self.viewport().update()

    def set_current_frame(self, frame: int):
        if frame != self._current_frame:
            self._current_frame = frame
            self._ensure_frame_visible(frame)
            self.viewport().update()

    def set_selected_bones(self, bones):
        self._selected_bones = set(bones)
        self.viewport().update()

    def row_label(self, row: int) -> str:
        for row_id, label, _ in self._rows:
            if row_id == row:
                return label
        return f"Bone {row}"

    # ── Geometry ───────────────────────────────────────────────────────────
    def sizeHint(self):
        return QSize(600, self.HEADER_HEIGHT + self.ROW_HEIGHT * 10)

    def _update_scrollbars(self):
        width = max(0, self.viewport().width() - self.NAME_WIDTH)
        height = max(0, self.viewport().height() - self.HEADER_HEIGHT)
        content_w = self._nb_frames * self._cell_width
        content_h = len(self._rows) * self.ROW_HEIGHT
        self.horizontalScrollBar().setRange(0, max(0, content_w - width))
        self.horizontalScrollBar().setPageStep(width)
        self.horizontalScrollBar().setSingleStep(self._cell_width)
        self.verticalScrollBar().setRange(0, max(0, content_h - height))
        self.verticalScrollBar().setPageStep(height)
        self.verticalScrollBar().setSingleStep(self.ROW_HEIGHT)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_scrollbars()

    def _ensure_frame_visible(self, frame: int):
        bar = self.horizontalScrollBar()
        left = frame * self._cell_width
        width = self.viewport().width() - self.NAME_WIDTH
        if left < bar.value():
            bar.setValue(left)
        elif left + self._cell_width > bar.value() + width:
            bar.setValue(left + self._cell_width - width)

    def frame_x(self, frame: int) -> int:
        return self.NAME_WIDTH + frame * self._cell_width - self.horizontalScrollBar().value()

    def row_y(self, index: int) -> int:
        return self.HEADER_HEIGHT + index * self.ROW_HEIGHT - self.verticalScrollBar().value()

    def hit(self, pos: QPoint):
        """(frame or -1 in the name column / None outside, row index or None in the header)."""
        row_index = None
        if pos.y() >= self.HEADER_HEIGHT:
            row_index = (pos.y() - self.HEADER_HEIGHT + self.verticalScrollBar().value()) // self.ROW_HEIGHT
            if row_index >= len(self._rows):
                row_index = None
        if pos.x() < self.NAME_WIDTH:
            return -1, row_index
        frame = (pos.x() - self.NAME_WIDTH + self.horizontalScrollBar().value()) // self._cell_width
        return (frame if frame < self._nb_frames else None), row_index

    # ── Painting ───────────────────────────────────────────────────────────
    def paintEvent(self, event):
        painter = QPainter(self.viewport())
        palette = self.palette()
        base = palette.base().color()
        alt = palette.alternateBase().color()
        text = palette.text().color()
        grid = QColor(text)
        grid.setAlpha(35)
        muted = QColor(text)
        muted.setAlpha(140)
        painter.fillRect(self.viewport().rect(), base)
        width, height = self.viewport().width(), self.viewport().height()
        cells_clip = QRect(self.NAME_WIDTH, self.HEADER_HEIGHT, width - self.NAME_WIDTH, height - self.HEADER_HEIGHT)

        first_frame = max(0, self.horizontalScrollBar().value() // self._cell_width)
        last_frame = min(self._nb_frames, first_frame + (width - self.NAME_WIDTH) // self._cell_width + 2)
        first_row = max(0, self.verticalScrollBar().value() // self.ROW_HEIGHT)
        last_row = min(len(self._rows), first_row + (height - self.HEADER_HEIGHT) // self.ROW_HEIGHT + 2)

        # Cells
        painter.save()
        painter.setClipRect(cells_clip)
        for index in range(first_row, last_row):
            row = self._rows[index][0]
            y = self.row_y(index)
            if index % 2:
                painter.fillRect(QRect(self.NAME_WIDTH, y, width, self.ROW_HEIGHT), alt)
            if row in self._selected_bones:
                painter.fillRect(QRect(self.NAME_WIDTH, y, width, self.ROW_HEIGHT), SELECTED_ROW_COLOUR)
        if 0 <= self._current_frame < self._nb_frames:
            painter.fillRect(QRect(self.frame_x(self._current_frame), self.HEADER_HEIGHT,
                                   self._cell_width, height), PLAYHEAD_COLOUR)
        painter.setPen(QPen(grid, 1))
        for frame in range(first_frame, last_frame + 1):
            x = self.frame_x(frame)
            painter.drawLine(x, self.HEADER_HEIGHT, x, height)
        self._paint_dots(painter, first_frame, last_frame, first_row, last_row)
        painter.restore()

        # Frame header
        painter.save()
        painter.setClipRect(QRect(self.NAME_WIDTH, 0, width - self.NAME_WIDTH, self.HEADER_HEIGHT))
        painter.fillRect(QRect(0, 0, width, self.HEADER_HEIGHT), alt)
        step = 1 if self._cell_width >= 16 else (5 if self._cell_width >= 8 else 10)
        font = QFont(self.font())
        font.setPointSizeF(max(7.0, font.pointSizeF() - 1.5))
        painter.setFont(font)
        for frame in range(first_frame, last_frame):
            if frame % step:
                continue
            x = self.frame_x(frame)
            current = frame == self._current_frame
            painter.setPen(text if current else muted)
            painter.drawText(QRect(x - 10, 0, self._cell_width + 20, self.HEADER_HEIGHT),
                             Qt.AlignmentFlag.AlignCenter, str(frame))
        painter.restore()

        # Name column
        painter.save()
        painter.setClipRect(QRect(0, self.HEADER_HEIGHT, self.NAME_WIDTH, height - self.HEADER_HEIGHT))
        painter.fillRect(QRect(0, self.HEADER_HEIGHT, self.NAME_WIDTH, height), alt)
        for index in range(first_row, last_row):
            row, label, depth = self._rows[index]
            y = self.row_y(index)
            if row in self._selected_bones:
                painter.fillRect(QRect(0, y, self.NAME_WIDTH, self.ROW_HEIGHT), SELECTED_ROW_COLOUR)
            changed = row in self._changed_rows if row >= ROW_POSITION else bool(self._changed_rows)
            font = QFont(self.font())
            font.setBold(changed)
            painter.setFont(font)
            painter.setPen(text if row >= 0 or changed else muted)
            painter.drawText(QRect(6 + depth * 8, y, self.NAME_WIDTH - 8 - depth * 8, self.ROW_HEIGHT),
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                             painter.fontMetrics().elidedText(label, Qt.TextElideMode.ElideRight,
                                                               self.NAME_WIDTH - 8 - depth * 8))
        painter.restore()
        painter.setPen(QPen(grid, 1))
        painter.drawLine(self.NAME_WIDTH, 0, self.NAME_WIDTH, height)
        painter.drawLine(0, self.HEADER_HEIGHT, width, self.HEADER_HEIGHT)
        painter.end()

    def _paint_dots(self, painter, first_frame, last_frame, first_row, last_row):
        diff = self._diff
        if diff is None or diff.status in (STATUS_NEW, STATUS_REMOVED):
            return
        painter.setPen(Qt.PenStyle.NoPen)
        summary = {}
        for (row, frame), cell in diff.cells.items():
            size = 5.5 if row == ROW_POSITION or cell.new_bone else dot_radius(cell.rotation_degrees)
            summary[frame] = max(summary.get(frame, 0), size)
        row_index = {row: index for index, (row, _, _) in enumerate(self._rows)}
        for (row, frame), cell in diff.cells.items():
            index = row_index.get(row)
            if index is None or not (first_row <= index < last_row and first_frame <= frame < last_frame):
                continue
            centre_x = self.frame_x(frame) + self._cell_width / 2
            centre_y = self.row_y(index) + self.ROW_HEIGHT / 2
            if cell.new_bone:
                painter.setBrush(QBrush(NEW_COLOUR))
                radius = 4.0
            elif row == ROW_POSITION:
                painter.setBrush(QBrush(CHANGE_COLOUR))
                radius = 4.0
            elif any(cell.rotation):
                painter.setBrush(QBrush(CHANGE_COLOUR))
                radius = dot_radius(cell.rotation_degrees)
            else:                                   # scale only: a ring
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(CHANGE_COLOUR, 1.5))
                painter.drawEllipse(QRectF(centre_x - 3.5, centre_y - 3.5, 7, 7))
                painter.setPen(Qt.PenStyle.NoPen)
                continue
            radius = min(radius, self._cell_width / 2 - 1)
            painter.drawEllipse(QRectF(centre_x - radius, centre_y - radius, radius * 2, radius * 2))
        summary_index = row_index[ROW_SUMMARY]
        if first_row <= summary_index < last_row:
            faded = QColor(CHANGE_COLOUR)
            faded.setAlpha(150)
            painter.setBrush(QBrush(faded))
            for frame, radius in summary.items():
                if first_frame <= frame < last_frame:
                    radius = min(radius, self._cell_width / 2 - 1)
                    centre_x = self.frame_x(frame) + self._cell_width / 2
                    centre_y = self.row_y(summary_index) + self.ROW_HEIGHT / 2
                    painter.drawEllipse(QRectF(centre_x - radius, centre_y - radius, radius * 2, radius * 2))

    # ── Mouse ──────────────────────────────────────────────────────────────
    def _row_at(self, row_index):
        return self._rows[row_index][0] if row_index is not None else None

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        frame, row_index = self.hit(event.position().toPoint())
        if frame is None and row_index is None:
            return
        row = self._row_at(row_index)
        bone = row if row is not None and row >= 0 else -1
        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        self.cell_clicked.emit(-1 if frame is None else frame, bone, ctrl)

    def event(self, event):
        if event.type() == event.Type.ToolTip:
            pos = self.viewport().mapFromGlobal(event.globalPos())
            frame, row_index = self.hit(pos)
            row = self._row_at(row_index)
            if row is not None and frame is not None and frame >= 0 and row >= ROW_POSITION:
                QToolTip.showText(event.globalPos(), describe_cell(self._diff, row, frame, self.row_label(row)))
            elif row is not None and frame == -1 and row >= 0:
                QToolTip.showText(event.globalPos(), f"{self.row_label(row)} - click to select this bone")
            else:
                QToolTip.hideText()
            return True
        return super().event(event)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            step = 2 if event.angleDelta().y() > 0 else -2
            self._cell_width = max(self.MIN_CELL, min(self.MAX_CELL, self._cell_width + step))
            self._update_scrollbars()
            self._ensure_frame_visible(self._current_frame)
            self.viewport().update()
            event.accept()
            return
        super().wheelEvent(event)

    def contextMenuEvent(self, event):
        frame, row_index = self.hit(event.pos())
        row = self._row_at(row_index)
        diff = self._diff
        menu = QMenu(self)
        if not self._can_revert or diff is None or not diff.cells:
            action = menu.addAction(self._why_no_revert())
            action.setEnabled(False)
            menu.exec(event.globalPos())
            return
        cells = diff.cells
        if row is not None and row >= ROW_POSITION and frame is not None and frame >= 0:
            if (row, frame) in cells:
                menu.addAction(f"Revert {self.row_label(row)} at frame {frame}",
                               lambda: self.revert_requested.emit([(row, frame)]))
        if row is not None and row >= ROW_POSITION:
            row_cells = [key for key in cells if key[0] == row]
            if row_cells:
                menu.addAction(f"Revert {self.row_label(row)} in the whole animation",
                               lambda: self.revert_requested.emit(row_cells))
        if frame is not None and frame >= 0:
            frame_cells = [key for key in cells if key[1] == frame]
            if frame_cells:
                menu.addAction(f"Revert frame {frame} (every bone)",
                               lambda: self.revert_requested.emit(frame_cells))
        menu.addSeparator()
        menu.addAction("Revert the whole animation", lambda: self.revert_requested.emit(list(cells)))
        menu.exec(event.globalPos())

    def _why_no_revert(self) -> str:
        diff = self._diff
        if diff is None:
            return "No reference to revert to"
        if diff.status == STATUS_NEW:
            return "Not in the reference: nothing to revert to"
        if diff.retimed:
            return "Frame count changed: frames cannot be matched one to one"
        if not diff.cells:
            return "Same as the reference"
        return "Cannot revert"


class AnimationStrip(QWidget):
    """One chip per animation: its id, a dot when changed, "new" when not in the reference."""
    animation_clicked = pyqtSignal(int)
    CHIP_WIDTH = 38
    HEIGHT = 22

    def __init__(self, parent=None):
        super().__init__(parent)
        self._diffs = []
        self._nb_animations = 0
        self._current = 0
        self.setFixedHeight(self.HEIGHT)

    def set_animations(self, nb_animations: int, diffs, current: int):
        self._nb_animations = nb_animations
        self._diffs = diffs or []
        self._current = current
        self.setFixedWidth(max(1, nb_animations * self.CHIP_WIDTH + 2))
        self.update()

    def set_current(self, anim_id: int):
        self._current = anim_id
        self.update()

    def _status(self, anim_id):
        if anim_id < len(self._diffs):
            return self._diffs[anim_id].status
        return None

    def paintEvent(self, event):
        painter = QPainter(self)
        text = self.palette().text().color()
        border = QColor(text)
        border.setAlpha(60)
        font = QFont(self.font())
        font.setPointSizeF(max(7.0, font.pointSizeF() - 1))
        painter.setFont(font)
        for anim_id in range(self._nb_animations):
            rect = QRectF(anim_id * self.CHIP_WIDTH + 1, 1, self.CHIP_WIDTH - 3, self.HEIGHT - 3)
            current = anim_id == self._current
            painter.setPen(QPen(QColor(80, 140, 230) if current else border, 1.5 if current else 1))
            painter.setBrush(QBrush(QColor(80, 140, 230, 50)) if current else Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect, 3, 3)
            status = self._status(anim_id)
            painter.setPen(text)
            label_rect = rect.adjusted(3, 0, -9 if status in (STATUS_CHANGED, STATUS_NEW) else 0, 0)
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, str(anim_id))
            if status in (STATUS_CHANGED, STATUS_NEW):
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(CHANGE_COLOUR if status == STATUS_CHANGED else NEW_COLOUR))
                painter.drawEllipse(QRectF(rect.right() - 9, rect.center().y() - 3, 6, 6))
        painter.end()

    def mousePressEvent(self, event):
        anim_id = int(event.position().x() // self.CHIP_WIDTH)
        if 0 <= anim_id < self._nb_animations:
            self.animation_clicked.emit(anim_id)

    def event(self, event):
        if event.type() == event.Type.ToolTip:
            anim_id = int(event.pos().x() // self.CHIP_WIDTH)
            status = self._status(anim_id)
            text = {STATUS_CHANGED: "changed", STATUS_NEW: "new (not in the reference)",
                    "same": "same as the reference"}.get(status, "")
            if 0 <= anim_id < self._nb_animations:
                QToolTip.showText(event.globalPos(), f"Animation {anim_id}" + (f": {text}" if text else ""))
            return True
        return super().event(event)


class AnimTimelinePanel(QWidget):
    """Collapsible panel (same look as the bone editor) holding the reference picker, the animation
    strip and the dope sheet. Collapsed, it costs nothing: the host only refreshes it while open."""
    expanded_changed = pyqtSignal(bool)
    reference_changed = pyqtSignal(int)                 # index in the "Compare with" list
    load_reference_requested = pyqtSignal()
    animation_clicked = pyqtSignal(int)

    CONTENT_HEIGHT = 250

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = QWidget()
        self.header.setStyleSheet("background:#2a2a2f; padding:5px;")
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(8, 4, 8, 4)
        self.expand_arrow = QLabel("▶")
        self.expand_arrow.setStyleSheet("color:white; font-size:12px; font-weight:bold;")
        self.expand_arrow.setFixedWidth(20)
        header_layout.addWidget(self.expand_arrow)
        title = QLabel("Timeline")
        title.setStyleSheet("color:white; font-weight:bold;")
        header_layout.addWidget(title)
        self.summary_label = QLabel("What changed, frame by frame")
        self.summary_label.setStyleSheet("color:#aaa; font-size:10px;")
        header_layout.addWidget(self.summary_label)
        header_layout.addStretch()
        self.header.mousePressEvent = lambda event: self.set_expanded(not self.expanded)
        layout.addWidget(self.header)

        self.content = QWidget()
        self.content.setVisible(False)
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(8, 6, 8, 6)
        content_layout.setSpacing(4)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Compare with:"))
        self.reference_combo = QComboBox()
        self.reference_combo.addItem("File as opened")
        self.reference_combo.setToolTip("The file as it was when opened in the editor, or a vanilla\n"
                                        "file loaded with the button next to this list.")
        # A different reference is a view choice, never an edit of the model
        self.reference_combo.setProperty("ifritViewOnly", True)
        self.reference_combo.activated.connect(self.reference_changed.emit)
        controls.addWidget(self.reference_combo)
        self.load_reference_button = QPushButton("Load vanilla file…")
        self.load_reference_button.setToolTip("Pick the original .dat of this model to compare with it,\n"
                                              "e.g. when the file was already modified before this session.")
        self.load_reference_button.clicked.connect(self.load_reference_requested.emit)
        controls.addWidget(self.load_reference_button)
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color:#aaa;")
        controls.addWidget(self.status_label, 1)
        hint = QLabel("Click: go to frame/bone · Right-click: revert · Ctrl+wheel: zoom")
        hint.setStyleSheet("color:#888; font-size:10px;")
        controls.addWidget(hint)
        content_layout.addLayout(controls)

        self.strip = AnimationStrip()
        self.strip.animation_clicked.connect(self.animation_clicked.emit)
        self.strip_scroll = QScrollArea()
        self.strip_scroll.setWidget(self.strip)
        self.strip_scroll.setWidgetResizable(False)
        self.strip_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.strip_scroll.setFixedHeight(AnimationStrip.HEIGHT + 14)
        self.strip_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content_layout.addWidget(self.strip_scroll)

        self.sheet = DopeSheetView()
        self.sheet.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.sheet.setFixedHeight(self.CONTENT_HEIGHT - 70)
        content_layout.addWidget(self.sheet)
        layout.addWidget(self.content)

    @property
    def expanded(self) -> bool:
        return not self.content.isHidden()

    def set_expanded(self, expanded: bool):
        self.content.setVisible(expanded)
        self.expand_arrow.setText("▼" if expanded else "▶")
        self.expanded_changed.emit(expanded)

    def set_reference_names(self, names, current: int):
        self.reference_combo.blockSignals(True)
        self.reference_combo.clear()
        self.reference_combo.addItems(names)
        self.reference_combo.setCurrentIndex(current)
        self.reference_combo.blockSignals(False)

    def set_overview(self, nb_animations: int, diffs, current_anim: int, reference_name: str):
        self.strip.set_animations(nb_animations, diffs, current_anim)
        if diffs is None:
            self.summary_label.setText("No reference")
            return
        changed = sum(1 for d in diffs if d.status == STATUS_CHANGED)
        new = sum(1 for d in diffs if d.status == STATUS_NEW)
        removed = sum(1 for d in diffs if d.status == STATUS_REMOVED)
        parts = [f"{changed} of {nb_animations} animations changed"]
        if new:
            parts.append(f"{new} new")
        if removed:
            parts.append(f"{removed} removed")
        self.summary_label.setText(", ".join(parts) + f" vs {reference_name}")

    def set_animation_status(self, diff):
        if diff is None:
            text = ""
        elif diff.status == STATUS_NEW:
            text = "This animation is not in the reference"
        elif diff.retimed:
            text = (f"Frame count changed ({diff.nb_reference_frames} → {diff.nb_frames}): "
                    "compared at the same point in time")
        elif diff.cells:
            text = f"{len(diff.changed_frames())} frames, {len(diff.changed_rows())} rows changed"
        else:
            text = "Same as the reference"
        self.status_label.setText(text)
