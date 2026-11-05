"""The Data tab's prim model editor (FF8GameData.psxgpu.primmodel): an effect's mesh - its vertices, its primitives
(kind, vertices, colours, texture corners) - drawn in a preview the mouse turns, scaled or moved as a whole. A model whose
entry gives its vertex count keeps its vertices (its code reads them by number, into blocks of that many: they move, they
are not added or removed); one that is also same_size keeps its primitives (its code copies it whole); a vertex a
primitive uses stays."""
import math

from PyQt6.QtCore import QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import (QComboBox, QDoubleSpinBox, QHBoxLayout, QHeaderView, QLabel, QPushButton, QSpinBox,
                             QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from FF8GameData.psxgpu.primmodel import KINDS, encode_model, new_primitive, parse_model

PRIMITIVE_COLUMNS = ("Kind", "Vertices", "Colours (RRGGBB)", "Texture corners (u,v)", "Semi-transparent")


def colour_text(rgb):
    return "%02X%02X%02X" % tuple(rgb)


class ModelPreview(QWidget):
    """The model's primitives, filled with their first colour, from a direction the mouse turns (drag)."""

    def __init__(self):
        super().__init__()
        self.model = None
        self.yaw, self.pitch = 0.6, -0.4
        self.selected_vertex, self.selected_primitive = -1, -1
        self._drag = None
        self.setMinimumSize(220, 220)

    def show_model(self, model):
        self.model = model
        self.update()

    def _project(self):
        cy, sy, cp, sp = math.cos(self.yaw), math.sin(self.yaw), math.cos(self.pitch), math.sin(self.pitch)
        points = []
        for x, y, z, _pad in self.model.vertices:
            rx, rz = x * cy - z * sy, x * sy + z * cy
            ry, rz = y * cp - rz * sp, y * sp + rz * cp
            points.append((rx, ry, rz))
        if not points:
            return [], 1
        extent = max(1, max(max(abs(p[0]), abs(p[1])) for p in points))
        scale = 0.45 * min(self.width(), self.height()) / extent
        return points, scale

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(24, 24, 28))
        if self.model is None or not self.model.vertices:
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        points, scale = self._project()
        cx, cy = self.width() / 2, self.height() / 2
        screen = [QPointF(cx + p[0] * scale, cy + p[1] * scale) for p in points]     # y down, as the game's
        order = []
        for index, primitive in enumerate(self.model.primitives):
            corners = primitive.indices
            if primitive.corners == 4:                  # the GPU's quad order: 0 1 3 2 around
                corners = [corners[0], corners[1], corners[3], corners[2]]
            depth = sum(points[k][2] for k in corners) / len(corners)
            order.append((depth, index, corners))
        for _depth, index, corners in sorted(order, reverse=True):
            primitive = self.model.primitives[index]
            r, g, b = primitive.colours[0]
            fill = QColor(min(255, r * 2), min(255, g * 2), min(255, b * 2), 110 if primitive.semi_transparent else 200)
            painter.setBrush(fill)
            pen = QPen(QColor(255, 200, 60) if index == self.selected_primitive else QColor(0, 0, 0, 160))
            pen.setWidthF(2 if index == self.selected_primitive else 1)
            painter.setPen(pen)
            painter.drawPolygon(QPolygonF([screen[k] for k in corners]))
        if 0 <= self.selected_vertex < len(screen):
            painter.setBrush(QColor(255, 80, 80))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(screen[self.selected_vertex], 4, 4)

    def mousePressEvent(self, event):
        self._drag = event.position()

    def mouseMoveEvent(self, event):
        if self._drag is not None:
            delta = event.position() - self._drag
            self._drag = event.position()
            self.yaw += delta.x() * 0.01
            self.pitch = max(-1.5, min(1.5, self.pitch + delta.y() * 0.01))
            self.update()

    def mouseReleaseEvent(self, _event):
        self._drag = None


class ModelEditor(QWidget):
    """A prim model's vertices and primitives."""
    edited = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.model = None
        self.tail = b""
        self.fixed_vertices = None                      # the vertex count its code reads by number, or None
        self.same_size = False                          # its code copies it whole: its primitives stay too
        self.summary = QLabel()
        self.preview = ModelPreview()
        self.vertices = QTableWidget(0, 3)
        self.vertices.setHorizontalHeaderLabels(["x", "y (down)", "z"])
        self.vertices.itemChanged.connect(self._vertex_changed)
        self.vertices.currentCellChanged.connect(lambda row, *_: self._select(vertex=row))
        self.primitives = QTableWidget(0, len(PRIMITIVE_COLUMNS))
        self.primitives.setHorizontalHeaderLabels(PRIMITIVE_COLUMNS)
        self.primitives.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.primitives.itemChanged.connect(self._primitive_changed)
        self.primitives.currentCellChanged.connect(lambda row, *_: self._select(primitive=row))
        tables = QTabWidget()
        tables.addTab(self.vertices, "Vertices")
        tables.addTab(self.primitives, "Primitives")
        # the whole model: scaled, moved
        self.scale = QDoubleSpinBox()
        self.scale.setRange(0.01, 100)
        self.scale.setValue(1)
        self.scale.setSingleStep(0.1)
        self.offsets = []
        whole = QHBoxLayout()
        whole.addWidget(QLabel("Scale x"))
        whole.addWidget(self.scale)
        for axis in "xyz":
            spin = QSpinBox()
            spin.setRange(-0x8000, 0x7FFF)
            whole.addWidget(QLabel(f"move {axis}"))
            whole.addWidget(spin)
            self.offsets.append(spin)
        transform = QPushButton("Apply to every vertex")
        transform.clicked.connect(self.transform)
        whole.addWidget(transform)
        whole.addStretch(1)
        self.kind = QComboBox()
        self.kind.addItems([k[0] for k in KINDS])
        buttons = QHBoxLayout()
        for text, slot in (("Add vertex", self.add_vertex), ("Remove vertex", self.remove_vertex)):
            button = QPushButton(text)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        buttons.addWidget(self.kind)
        for text, slot in (("Add primitive", self.add_primitive), ("Remove primitive", self.remove_primitive)):
            button = QPushButton(text)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        buttons.addStretch(1)
        self.error = QLabel()
        self.error.setStyleSheet("color: #c0392b")
        self.error.setWordWrap(True)
        body = QSplitter()
        body.addWidget(self.preview)
        body.addWidget(tables)
        body.setStretchFactor(1, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.summary)
        layout.addLayout(whole)
        layout.addWidget(body, 1)
        layout.addLayout(buttons)
        layout.addWidget(self.error)

    def load(self, data):
        self.model = parse_model(data, 0, 0)
        # what follows the model in its entry (Double's morph pair: a second model) is kept as it is
        self.tail = bytes(data[self.model.size:]) if self.model is not None else b""
        self.error.setText("" if self.model is not None else "Not a prim model: its bytes are kept as they are.")
        self._fill()

    def data(self):
        return encode_model(self.model) + self.tail if self.model is not None else None

    # ---- tables ----
    def _fill(self):
        model = self.model
        self.vertices.blockSignals(True)
        self.primitives.blockSignals(True)
        self.vertices.setRowCount(len(model.vertices) if model else 0)
        self.primitives.setRowCount(len(model.primitives) if model else 0)
        if model is not None:
            for row, vertex in enumerate(model.vertices):
                for column in range(3):
                    self.vertices.setItem(row, column, QTableWidgetItem(str(vertex[column])))
            for row, primitive in enumerate(model.primitives):
                kind = QTableWidgetItem(primitive.kind)
                kind.setFlags(kind.flags() & ~Qt.ItemFlag.ItemIsEditable)
                cells = [kind, QTableWidgetItem(" ".join(map(str, primitive.indices))),
                         QTableWidgetItem(" ".join(colour_text(c) for c in primitive.colours)),
                         QTableWidgetItem(" ".join(f"{u},{v}" for u, v in primitive.uvs)),
                         QTableWidgetItem("yes" if primitive.semi_transparent else "no")]
                if not primitive.uvs:
                    cells[3].setFlags(cells[3].flags() & ~Qt.ItemFlag.ItemIsEditable)
                for column, cell in enumerate(cells):
                    self.primitives.setItem(row, column, cell)
        self.vertices.blockSignals(False)
        self.primitives.blockSignals(False)
        if model is not None:
            counts = ", ".join(f"{model.count(k[0])} {k[0]}" for k in KINDS if model.count(k[0]))
            kept = " (its effect's code reads them by number: they stay, they move)" if self.fixed_vertices else ""
            whole = " (its effect's code copies the model whole: they stay)" if self.same_size else ""
            self.summary.setText(f"{len(model.vertices)} vertices{kept}, {len(model.primitives)} primitives{whole}: {counts}")
        else:
            self.summary.clear()
        self.preview.show_model(model)

    def _select(self, vertex=None, primitive=None):
        if vertex is not None:
            self.preview.selected_vertex = vertex
        if primitive is not None:
            self.preview.selected_primitive = primitive
        self.preview.update()

    def _refuse(self, text):
        self.error.setText(text)
        self._fill()

    def _vertex_changed(self, item):
        try:
            value = int(item.text(), 0)
            if not -0x8000 <= value <= 0x7FFF:
                raise ValueError
        except ValueError:
            return self._refuse("A vertex coordinate: a number from -32768 to 32767")
        self.error.clear()
        self.model.vertices[item.row()][item.column()] = value
        self.preview.update()
        self.edited.emit()

    def _primitive_changed(self, item):
        primitive = self.model.primitives[item.row()]
        words = item.text().replace(",", " ").split() if item.column() != 3 else item.text().split()
        try:
            if item.column() == 1:
                vertices = [int(w, 0) for w in words]
                if len(vertices) != primitive.corners or not all(0 <= v < len(self.model.vertices) for v in vertices):
                    raise ValueError(f"{primitive.corners} vertex numbers from 0 to {len(self.model.vertices) - 1}")
                for corner, vertex in enumerate(vertices):
                    primitive.set_index(corner, vertex)
            elif item.column() == 2:
                colours = [bytes.fromhex(w) for w in words]
                if len(colours) != len(primitive.colours) or any(len(c) != 3 for c in colours):
                    raise ValueError(f"{len(primitive.colours)} colours as RRGGBB")
                for corner, rgb in enumerate(colours):
                    primitive.set_colour(corner, rgb)
            elif item.column() == 3:
                uvs = [tuple(int(n, 0) for n in w.split(",")) for w in words]
                if len(uvs) != len(primitive.uvs) or any(len(uv) != 2 or not all(0 <= n <= 255 for n in uv) for uv in uvs):
                    raise ValueError(f"{len(primitive.uvs)} corners as u,v (0 to 255)")
                for corner, uv in enumerate(uvs):
                    primitive.set_uv(corner, uv)
            elif item.column() == 4:
                if item.text().strip().lower() not in ("yes", "no"):
                    raise ValueError("yes or no")
                primitive.raw[3] = primitive.raw[3] & ~2 | (2 if item.text().strip().lower() == "yes" else 0)
        except ValueError as error:
            return self._refuse(f"{PRIMITIVE_COLUMNS[item.column()]}: {error}")
        self.error.clear()
        self.preview.update()
        self.edited.emit()

    # ---- whole model, add / remove ----
    def transform(self):
        """Every vertex scaled about the origin, then moved."""
        if self.model is None:
            return
        factor = self.scale.value()
        moved = [spin.value() for spin in self.offsets]
        for vertex in self.model.vertices:
            for axis in range(3):
                vertex[axis] = max(-0x8000, min(0x7FFF, round(vertex[axis] * factor) + moved[axis]))
        self.scale.setValue(1)
        for spin in self.offsets:
            spin.setValue(0)
        self._fill()
        self.edited.emit()

    def _kept(self, what):
        """Why `what` (vertices, primitives) may not be added or removed, or None."""
        if what == "vertices" and self.fixed_vertices is not None:
            return f"Its effect's code reads its {self.fixed_vertices} vertices by number: it keeps them (move them instead)."
        if self.same_size:
            return "Its effect's code copies it whole into a block of its size: it keeps its vertices and primitives."
        return None

    def add_vertex(self):
        if self.model is None:
            return
        if self._kept("vertices"):
            return self._refuse(self._kept("vertices"))
        row = self.vertices.currentRow()
        source = self.model.vertices[row] if 0 <= row < len(self.model.vertices) else [0, 0, 0, 0]
        self.model.vertices.append(list(source))
        self._fill()
        self.vertices.setCurrentCell(len(self.model.vertices) - 1, 0)
        self.edited.emit()

    def remove_vertex(self):
        """The last vertex, when no primitive uses it (removing one from the middle would renumber the others)."""
        if self.model is None or len(self.model.vertices) <= 1:
            return
        last = len(self.model.vertices) - 1
        if self._kept("vertices"):
            return self._refuse(self._kept("vertices"))
        if any(last in p.indices for p in self.model.primitives):
            return self._refuse(f"Vertex {last} (the last) is used by a primitive: change or remove that first.")
        del self.model.vertices[last]
        self.error.clear()
        self._fill()
        self.edited.emit()

    def add_primitive(self):
        if self.model is None:
            return
        if self._kept("primitives"):
            return self._refuse(self._kept("primitives"))
        primitive = new_primitive(self.kind.currentText(), self.model)
        kinds = [k[0] for k in KINDS]
        at = max((i for i, p in enumerate(self.model.primitives) if kinds.index(p.kind) <= kinds.index(primitive.kind)),
                 default=-1) + 1                        # where its list's records end (the encoded order)
        self.model.primitives.insert(at, primitive)
        self._fill()
        self.primitives.setCurrentCell(at, 1)
        self.edited.emit()

    def remove_primitive(self):
        row = self.primitives.currentRow()
        if self.model is None or not 0 <= row < len(self.model.primitives):
            return
        if self._kept("primitives"):
            return self._refuse(self._kept("primitives"))
        del self.model.primitives[row]
        self._fill()
        self.edited.emit()
