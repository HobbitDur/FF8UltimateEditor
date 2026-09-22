"""Timeline of a simulated GF cinematic: one row per bone, a bar from spawn to death, and a
marker for every notable instruction it ran (camera, sound, draw setup, particles...).

Painted by hand (thousands of bones and markers): only the visible rows are drawn, the view
scrolls through a QScrollArea and zooms horizontally with Ctrl+wheel.
"""
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QSize
from PyQt6.QtGui import QPainter, QColor, QPen, QFontMetrics
from PyQt6.QtWidgets import QWidget, QToolTip

TICKS_PER_SECOND = 15

CATEGORY_COLORS = {
    "camera": QColor(66, 133, 244),
    "sound": QColor(219, 68, 55),
    "draw": QColor(15, 157, 88),
    "model": QColor(171, 71, 188),
    "particle": QColor(244, 160, 0),
    "file": QColor(120, 120, 120),
    "node": QColor(0, 172, 193),
    "freeze": QColor(233, 30, 99),
    "light": QColor(255, 214, 0),
    "fog": QColor(141, 110, 99),
    "flag": QColor(96, 125, 139),
    "sequence": QColor(0, 0, 0),
}


class TimelineCanvas(QWidget):
    """The painted timeline. `bone_clicked(index)` / `event_clicked(offset)` on clicks."""

    bone_clicked = pyqtSignal(int)
    event_clicked = pyqtSignal(int)

    ROW_HEIGHT = 16
    LABEL_WIDTH = 230
    RULER_HEIGHT = 22

    def __init__(self):
        QWidget.__init__(self)
        self.simulation = None
        self.rows = []              # bone indices, in display order
        self.depth = {}             # bone index -> nesting depth (spawn tree)
        self.labels = {}
        self.pixels_per_tick = 3.0
        self.hidden_categories = set()
        self.selected_bone = -1
        self.setMouseTracking(True)

    # ------------------------------------------------------------------ data
    def set_simulation(self, simulation, labels=None):
        self.simulation = simulation
        self.labels = labels or {}
        self._build_rows()
        self._resize()
        self.update()

    def _build_rows(self):
        """Spawn tree order: every bone right under the bone that spawned it."""
        self.rows, self.depth = [], {}
        if self.simulation is None or not self.simulation.bones:
            return
        children = {}
        for bone in self.simulation.bones:
            children.setdefault(bone.parent, []).append(bone.index)
        stack = [(index, 0) for index in reversed(children.get(-1, []))]
        while stack:
            index, depth = stack.pop()
            self.rows.append(index)
            self.depth[index] = depth
            stack.extend((child, depth + 1) for child in reversed(children.get(index, [])))

    def total_ticks(self):
        return max(1, self.simulation.tick) if self.simulation else 1

    def set_zoom(self, pixels_per_tick):
        self.pixels_per_tick = max(0.2, min(40.0, pixels_per_tick))
        self._resize()
        self.update()

    def _resize(self):
        width = self.LABEL_WIDTH + int(self.total_ticks() * self.pixels_per_tick) + 40
        height = self.RULER_HEIGHT + len(self.rows) * self.ROW_HEIGHT + 4
        self.setMinimumSize(QSize(width, height))
        self.resize(width, height)

    def sizeHint(self):
        return self.minimumSize()

    # ------------------------------------------------------------------ geometry
    def _x(self, tick):
        return self.LABEL_WIDTH + int(tick * self.pixels_per_tick)

    def _row_at(self, y):
        row = (y - self.RULER_HEIGHT) // self.ROW_HEIGHT
        return row if 0 <= row < len(self.rows) else -1

    def _event_at(self, pos):
        row = self._row_at(pos.y())
        if row < 0 or self.simulation is None:
            return None
        bone = self.simulation.bones[self.rows[row]]
        best, best_distance = None, 5
        for event in bone.events:
            if event.category in self.hidden_categories:
                continue
            distance = abs(self._x(event.tick) - pos.x())
            if distance < best_distance:
                best, best_distance = event, distance
        return best

    def bone_label(self, bone):
        name = self.labels.get(bone.program, f"{bone.program:04X}")
        text = f"#{bone.index} {name}"
        if bone.draw:
            text += f"  [{bone.draw}]"
        return text

    # ------------------------------------------------------------------ painting
    def paintEvent(self, event):
        painter = QPainter(self)
        clip = event.rect()
        painter.fillRect(clip, self.palette().base())
        if self.simulation is None:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Load a GF mag file and run the simulation")
            return
        text_color = self.palette().text().color()
        grid = QColor(text_color)
        grid.setAlpha(40)
        metrics = QFontMetrics(painter.font())

        # Ruler: a line per second, labelled
        painter.setPen(text_color)
        step = TICKS_PER_SECOND if self.pixels_per_tick * TICKS_PER_SECOND >= 30 else TICKS_PER_SECOND * 5
        for tick in range(0, self.total_ticks() + 1, step):
            x = self._x(tick)
            if x < clip.left() - 60 or x > clip.right() + 60:
                continue
            painter.setPen(grid)
            painter.drawLine(x, self.RULER_HEIGHT, x, self.height())
            painter.setPen(text_color)
            painter.drawText(x + 2, 15, f"{tick // TICKS_PER_SECOND}s")

        first = max(0, (clip.top() - self.RULER_HEIGHT) // self.ROW_HEIGHT)
        last = min(len(self.rows), (clip.bottom() - self.RULER_HEIGHT) // self.ROW_HEIGHT + 1)
        end_tick = self.total_ticks()
        for row in range(first, last):
            bone = self.simulation.bones[self.rows[row]]
            y = self.RULER_HEIGHT + row * self.ROW_HEIGHT
            if bone.index == self.selected_bone:
                painter.fillRect(QRect(0, y, self.width(), self.ROW_HEIGHT), self.palette().highlight())
            # label, indented by spawn depth
            painter.setPen(text_color)
            indent = min(self.depth.get(bone.index, 0), 12) * 8
            label = metrics.elidedText(self.bone_label(bone), Qt.TextElideMode.ElideRight,
                                       self.LABEL_WIDTH - 6 - indent)
            painter.drawText(4 + indent, y + self.ROW_HEIGHT - 4, label)
            # lifetime bar
            death = bone.death_tick if bone.death_tick >= 0 else end_tick
            bar = QRect(self._x(bone.spawn_tick), y + 4, max(2, self._x(death) - self._x(bone.spawn_tick)),
                        self.ROW_HEIGHT - 8)
            painter.fillRect(bar, QColor(150, 150, 150, 110))
            # events
            for sim_event in bone.events:
                if sim_event.category in self.hidden_categories:
                    continue
                x = self._x(sim_event.tick)
                if x < clip.left() - 3 or x > clip.right() + 3:
                    continue
                painter.setPen(QPen(CATEGORY_COLORS.get(sim_event.category, text_color), 3))
                painter.drawLine(x, y + 2, x, y + self.ROW_HEIGHT - 2)
        painter.setPen(QPen(QColor(0, 0, 0), 2))
        if self.simulation.finished_tick >= 0:
            x = self._x(self.simulation.finished_tick)
            painter.drawLine(x, 0, x, self.height())

    # ------------------------------------------------------------------ interaction
    def mouseMoveEvent(self, event):
        if self.simulation is None:
            return
        pos = event.position().toPoint()
        sim_event = self._event_at(pos)
        row = self._row_at(pos.y())
        if sim_event is not None:
            QToolTip.showText(event.globalPosition().toPoint(),
                              f"tick {sim_event.tick} ({sim_event.tick / TICKS_PER_SECOND:.2f}s)\n"
                              f"{sim_event.offset:05X}: {sim_event.text}\n[{sim_event.category}]", self)
        elif row >= 0:
            bone = self.simulation.bones[self.rows[row]]
            death = f"dies at tick {bone.death_tick}" if bone.death_tick >= 0 else "alive at the end"
            parent = f", spawned by #{bone.parent} at {bone.spawned_at:05X}" if bone.parent >= 0 else ""
            QToolTip.showText(event.globalPosition().toPoint(),
                              f"{self.bone_label(bone)}\nspawn tick {bone.spawn_tick}, {death}{parent}\n"
                              f"{len(bone.events)} events", self)
        else:
            QToolTip.hideText()

    def mousePressEvent(self, event):
        if self.simulation is None:
            return
        pos = event.position().toPoint()
        sim_event = self._event_at(pos)
        row = self._row_at(pos.y())
        if row >= 0:
            self.selected_bone = self.rows[row]
            self.update()
            self.bone_clicked.emit(self.selected_bone)
        if sim_event is not None:
            self.event_clicked.emit(sim_event.offset)
        elif row >= 0:
            self.event_clicked.emit(self.simulation.bones[self.rows[row]].program)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.25 if event.angleDelta().y() > 0 else 0.8
            self.set_zoom(self.pixels_per_tick * factor)
            event.accept()
        else:
            event.ignore()


class MotionCanvas(QWidget):
    """outAngle / outPos of one bone over the simulated ticks (6 curves, each auto-scaled)."""

    NAMES = ["angle X", "angle Y", "angle Z", "pos X", "pos Y", "pos Z"]
    COLORS = [QColor(229, 57, 53), QColor(67, 160, 71), QColor(30, 136, 229),
              QColor(255, 152, 0), QColor(142, 36, 170), QColor(0, 137, 123)]

    def __init__(self):
        QWidget.__init__(self)
        self.bone = None
        self.total_ticks = 1
        self.visible = [True] * 6
        self.setMinimumHeight(180)

    def set_bone(self, bone, total_ticks):
        self.bone = bone
        self.total_ticks = max(1, total_ticks)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().base())
        text_color = self.palette().text().color()
        if self.bone is None or len(self.bone.track) < 2:
            painter.setPen(text_color)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Click a bone on the timeline to plot its motion (outAngle / outPos)")
            return
        left, top, right, bottom = 60, 10, self.width() - 10, self.height() - 20
        track = self.bone.track
        t0, t1 = track[0][0], max(track[-1][0], track[0][0] + 1)
        painter.setPen(text_color)
        painter.drawText(4, bottom + 14, f"tick {t0}")
        painter.drawText(right - 60, bottom + 14, f"tick {t1}")
        legend_x = left
        for component in range(6):
            if not self.visible[component]:
                continue
            values = [sample[1 + component] for sample in track]
            low, high = min(values), max(values)
            span = (high - low) or 1
            painter.setPen(QPen(self.COLORS[component], 1.5))
            previous = None
            for sample in track:
                x = left + (sample[0] - t0) * (right - left) / (t1 - t0)
                y = bottom - (sample[1 + component] - low) * (bottom - top) / span
                if previous is not None:
                    painter.drawLine(int(previous[0]), int(previous[1]), int(x), int(y))
                previous = (x, y)
            painter.drawText(legend_x, top + 10, f"{self.NAMES[component]} [{low}..{high}]")
            legend_x += 150
