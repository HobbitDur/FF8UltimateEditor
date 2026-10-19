"""Cached, cancellable top-down texture rendering away from the UI thread."""
import threading

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal, QPointF, QBuffer, QIODevice, Qt
from PyQt6.QtGui import QImage, QPainter, QBrush, QPolygonF, QTransform, QColor


def render_textured_png(geometry, textures, cancelled=lambda: False, scale=32):
    land, sea, roads = textures.images()
    image = QImage(128 * scale, 96 * scale, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(28, 55, 120))
    painter = QPainter(image)
    painter.setPen(Qt.PenStyle.NoPen)
    brushes = {key: QBrush(value) for key, value in land.items()}
    sea_brush, road_brush = QBrush(sea), QBrush(roads)
    try:
        for by in range(96):
            if cancelled():
                return b''
            for bx in range(128):
                base, vertices, count = geometry.read_block(bx, by)
                faces = []
                for index in range(count):
                    face = geometry.data[base + 4 + index * 16:base + 20 + index * 16]
                    if any(i >= len(vertices) for i in face[:3]):
                        raise ValueError('Invalid textured triangle vertex')
                    faces.append((sum(-vertices[i][1] for i in face[:3]), face))
                # Render bridges/city surfaces above underlying ground in this flat preview.
                for _, face in sorted(faces, key=lambda entry: entry[0]):
                    points = [(scale * (bx + vertices[i][0] / 2048),
                               scale * (by - vertices[i][2] / 2048)) for i in face[:3]]
                    area = ((points[1][0] - points[0][0]) * (points[2][1] - points[0][1])
                            - (points[2][0] - points[0][0]) * (points[1][1] - points[0][1]))
                    if abs(area) < 1e-8:
                        continue
                    if face[14] & 0x20:
                        texture, brush, factor = roads, road_brush, 1.
                    elif (face[14] & 0x60) == 0x40:
                        texture, brush, factor = sea, sea_brush, 1.
                    else:
                        key = (face[12] >> 4, face[12] & 15)
                        texture, brush, factor = land[key], brushes[key], .5
                    u0, v0, u1, v1, u2, v2 = [value * factor for value in face[6:12]]
                    du1, dv1, du2, dv2 = u1 - u0, v1 - v0, u2 - u0, v2 - v0
                    determinant = du1 * dv2 - du2 * dv1
                    polygon = QPolygonF([QPointF(x, y) for x, y in points])
                    if abs(determinant) < 1e-8:
                        painter.setBrush(texture.pixelColor(int(u0) % texture.width(), int(v0) % texture.height()))
                    else:
                        (x0, y0), (x1, y1), (x2, y2) = points
                        a = ((x1 - x0) * dv2 - (x2 - x0) * dv1) / determinant
                        b = ((y1 - y0) * dv2 - (y2 - y0) * dv1) / determinant
                        c = (du1 * (x2 - x0) - du2 * (x1 - x0)) / determinant
                        d = (du1 * (y2 - y0) - du2 * (y1 - y0)) / determinant
                        brush.setTransform(QTransform(a, b, c, d, x0 - a * u0 - c * v0, y0 - b * u0 - d * v0))
                        painter.setBrush(brush)
                    painter.drawPolygon(polygon)
    finally:
        painter.end()
    if cancelled():
        return b''
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, 'PNG'):
        raise ValueError('Could not encode terrain preview')
    return bytes(buffer.data())


class _RenderSignals(QObject):
    finished = pyqtSignal(int, bytes, str)


class TerrainRenderTask(QRunnable):
    def __init__(self, generation, geometry, textures):
        super().__init__()
        self.generation, self.geometry, self.textures = generation, geometry, textures
        self.cancelled = threading.Event()
        self.signals = _RenderSignals()

    def run(self):
        try:
            data = render_textured_png(self.geometry, self.textures, self.cancelled.is_set)
            self.signals.finished.emit(self.generation, data, '')
        except Exception as error:
            self.signals.finished.emit(self.generation, b'', str(error))
