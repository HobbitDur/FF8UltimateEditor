"""Untextured preview of a GF cinematic mesh: faces filled with their primitive colour and a
simple directional shade, painter's algorithm. Drag to rotate, wheel to zoom.

The meshes' textures live in VRAM rectangles described by a table in FF8_EN.exe, so they are not
sampled here; textured faces show their vertex colour."""
import math

from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QPainter, QColor, QPolygonF, QPen
from PyQt6.QtWidgets import QWidget


class MeshPreview(QWidget):
    def __init__(self):
        QWidget.__init__(self)
        self.mesh = None
        self.yaw, self.pitch, self.zoom = 0.6, -0.4, 1.0
        self.wireframe = False
        self._drag = None
        self.setMinimumSize(300, 300)

    def set_mesh(self, mesh):
        self.mesh = mesh
        self.zoom = 1.0
        self.update()

    def _project(self):
        vertices = self.mesh.vertices
        cy, sy, cp, sp = math.cos(self.yaw), math.sin(self.yaw), math.cos(self.pitch), math.sin(self.pitch)
        xs = [v[0] for v in vertices] or [0]
        ys = [v[1] for v in vertices] or [0]
        zs = [v[2] for v in vertices] or [0]
        centre = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2)
        radius = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs), 1) / 2
        scale = min(self.width(), self.height()) * 0.42 / radius * self.zoom
        out = []
        for x, y, z in vertices:
            x, y, z = x - centre[0], y - centre[1], z - centre[2]
            x, z = x * cy - z * sy, x * sy + z * cy          # yaw around Y
            y, z = y * cp - z * sp, y * sp + z * cp          # pitch around X
            # PSX: +Y is down on screen already
            out.append((self.width() / 2 + x * scale, self.height() / 2 + y * scale, z * scale))
        return out

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(40, 40, 48))
        if self.mesh is None or not self.mesh.vertices:
            painter.setPen(QColor(200, 200, 200))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Select a mesh")
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        points = self._project()
        if not self.mesh.faces:  # morph target / vertex cloud
            painter.setPen(QPen(QColor(255, 200, 80), 3))
            for x, y, _z in points:
                painter.drawPoint(QPointF(x, y))
            return
        faces = []
        for prim_type, indices, rgb in self.mesh.faces:
            corners = [points[i] for i in indices]
            if len(corners) == 4:  # PSX quad order 0-1-3-2
                corners = [corners[0], corners[1], corners[3], corners[2]]
            depth = sum(c[2] for c in corners) / len(corners)
            faces.append((depth, corners, rgb))
        faces.sort(key=lambda face: face[0], reverse=True)
        for _depth, corners, rgb in faces:
            # light from the viewer: shade by how much the face normal points at the screen
            a = [corners[1][k] - corners[0][k] for k in range(3)]
            b3 = [corners[2][k] - corners[0][k] for k in range(3)]
            normal = (a[1] * b3[2] - a[2] * b3[1], a[2] * b3[0] - a[0] * b3[2], a[0] * b3[1] - a[1] * b3[0])
            length = math.sqrt(sum(n * n for n in normal)) or 1
            shade = 0.35 + 0.65 * abs(normal[2]) / length
            r, g, b = rgb & 0xFF, (rgb >> 8) & 0xFF, (rgb >> 16) & 0xFF
            if r == g == b == 0:
                r = g = b = 128
            color = QColor(min(255, int(r * shade * 1.4)), min(255, int(g * shade * 1.4)), min(255, int(b * shade * 1.4)))
            polygon = QPolygonF([QPointF(c[0], c[1]) for c in corners])
            if self.wireframe:
                painter.setPen(QPen(color, 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
            else:
                painter.setPen(QPen(color.darker(130), 0.5))
                painter.setBrush(color)
            painter.drawPolygon(polygon)

    def mousePressEvent(self, event):
        self._drag = event.position()

    def mouseMoveEvent(self, event):
        if self._drag is None:
            return
        delta = event.position() - self._drag
        self._drag = event.position()
        self.yaw += delta.x() * 0.01
        self.pitch = max(-1.5, min(1.5, self.pitch + delta.y() * 0.01))
        self.update()

    def mouseReleaseEvent(self, event):
        self._drag = None

    def wheelEvent(self, event):
        self.zoom *= 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.update()
