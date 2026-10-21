"""3D view of a simulated GF cinematic (CineScene): meshes, the creature and a marker for every
other bone, at one tick. Painted with QPainter (painter's algorithm). Textured faces sample the
VRAM the script has built at that tick (CineVram), affinely per triangle like the PlayStation GPU;
semi-transparent bones use its blend modes (average / additive / subtractive / + quarter).

Two cameras: Free (drag to orbit, right-drag to pan, wheel to zoom) and Game (the battle camera the
script drives with opcode 0x39). Click a bone's marker or mesh to select it."""
import math

import numpy as np
from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPolygonF, QPen, QBrush, QImage, QTransform, QPainterPath
from PyQt6.QtWidgets import QWidget

from FF8GameData.magcine.cinescene import look_at

_MARKER_COLORS = {0: QColor(150, 150, 150), 4: QColor(255, 255, 255), 5: QColor(244, 160, 0),
                  6: QColor(255, 120, 40), 21: QColor(120, 120, 120), 22: QColor(244, 160, 0)}
_CREATURE_COLOR = (205, 150, 110)


class SceneView(QWidget):
    bone_clicked = pyqtSignal(int)

    NEAR = 50.0

    def __init__(self):
        QWidget.__init__(self)
        self.scene = None
        self.tick = 0
        self.selected_bone = -1
        self.game_camera = False
        self.show_helpers = True
        self.wireframe = False
        self.textured = True
        self._images = {}     # (vram version, tpage, clut) -> (QImage, its RGBA buffer)
        self.yaw, self.pitch, self.distance = 0.8, -0.35, 12000.0
        self.target = np.zeros(3)
        self._drag = None
        self._drag_button = None
        self._picks = []      # (screen x, y, bone) of the last paint
        self.setMinimumSize(400, 300)
        self.setMouseTracking(False)

    # ------------------------------------------------------------------ state
    def set_scene(self, scene):
        self.scene = scene
        self._images = {}
        self.tick = 0
        self.frame_all()

    def set_tick(self, tick):
        self.tick = tick
        self.update()

    def frame_all(self):
        """Point the free camera at the middle of everything the summon places."""
        if self.scene is None or not self.scene.sim.frames:
            return
        points = [out[3:6] for frame in self.scene.sim.frames[::10] for out in frame.values()]
        if points:
            array = np.asarray(points, float)
            low, high = np.percentile(array, 10, axis=0), np.percentile(array, 90, axis=0)
            self.target = (low + high) / 2
            self.distance = max(3000.0, float(np.linalg.norm(high - low)) * 1.2)
        self.update()

    # ------------------------------------------------------------------ camera
    def _camera_world(self):
        if self.game_camera and self.scene is not None:
            view = self.scene.camera(self.tick)
            if view is not None:
                return look_at(*view)
        eye = self.target + self.distance * np.array([
            math.cos(self.pitch) * math.sin(self.yaw),
            math.sin(self.pitch),
            -math.cos(self.pitch) * math.cos(self.yaw)])
        return look_at(eye, self.target)

    def _focal(self):
        return min(self.width(), self.height()) * 0.9

    # ------------------------------------------------------------------ painting
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(28, 30, 38))
        self._picks = []
        if self.scene is None or not self.scene.tick_count:
            painter.setPen(QColor(200, 200, 200))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Load a GF mag file")
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        camera = self._camera_world()
        view = np.linalg.inv(camera)
        rot, trans = view[:3, :3], view[:3, 3]
        focal, cx, cy = self._focal(), self.width() / 2, self.height() / 2

        def to_camera(points):
            return points @ rot.T + trans

        self._draw_grid(painter, to_camera, focal, cx, cy)

        polygons = []   # (depth, points, colour, texture) - texture = (QImage, uvs, blend) or None
        markers = []
        vram = self.scene.vram if self.textured else None
        for item in self.scene.items(self.tick, show_helpers=self.show_helpers):
            matrix = item.matrix
            if item.kind == "marker":
                point = to_camera((matrix[:3, 3])[None, :])[0]
                if point[2] > self.NEAR:
                    markers.append((point, item))
                continue
            state = item.texture_state
            if item.kind == "mesh":
                vertices = np.asarray(item.mesh.vertices, float)
                faces = [(face[1], face[2], face[3]) for face in item.mesh.faces]
            else:
                vertices = item.mesh.vertices
                textures = item.mesh.textures or [None] * len(item.mesh.faces)
                faces = [(indices, None, texture) for indices, texture in zip(item.mesh.faces, textures)]
                state = (0, 0, 0, False)      # the creature's words are absolute
            if not len(vertices):
                continue
            world = vertices @ matrix[:3, :3].T + matrix[:3, 3]
            cam = to_camera(world)
            z = cam[:, 2]
            safe = np.where(z > self.NEAR, z, np.inf)
            sx = cx + focal * cam[:, 0] / safe
            sy = cy + focal * cam[:, 1] / safe
            selected = item.bone == self.selected_bone
            for indices, rgb, texture in faces:
                order = [0, 1, 3, 2] if len(indices) == 4 else [0, 1, 2]   # PSX quad order
                indices = [indices[k] for k in order]
                if any(z[i] <= self.NEAR for i in indices):
                    continue
                corners = cam[indices]
                normal = np.cross(corners[1] - corners[0], corners[2] - corners[0])
                length = np.linalg.norm(normal) or 1.0
                shade = 0.35 + 0.65 * abs(normal[2]) / length
                if rgb is None:
                    r, g, b = _CREATURE_COLOR
                else:
                    r, g, b = rgb & 0xFF, (rgb >> 8) & 0xFF, (rgb >> 16) & 0xFF
                    if r + g + b < 30:
                        r = g = b = 128
                colour = QColor(min(255, int(r * shade * 1.5)), min(255, int(g * shade * 1.5)),
                                min(255, int(b * shade * 1.5)))
                if selected:
                    colour = QColor(min(255, colour.red() + 80), colour.green(), min(255, colour.blue() + 40))
                points = [QPointF(sx[i], sy[i]) for i in indices]
                sampled = None
                if vram is not None and texture is not None:
                    sampled = self._texture(vram, texture, state, order)
                polygons.append((float(np.mean(z[indices])), points, colour, sampled))
            origin = to_camera(matrix[:3, 3][None, :])[0]
            if origin[2] > self.NEAR:
                self._picks.append((cx + focal * origin[0] / origin[2], cy + focal * origin[1] / origin[2], item.bone))

        polygons.sort(key=lambda entry: entry[0], reverse=True)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        for _depth, points, colour, sampled in polygons:
            if self.wireframe:
                painter.setPen(QPen(colour, 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPolygon(QPolygonF(points))
            elif sampled is not None:
                self._draw_textured(painter, points, sampled)
            else:
                painter.setPen(QPen(colour.darker(125), 0.5))
                painter.setBrush(QBrush(colour))
                painter.drawPolygon(QPolygonF(points))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        for point, item in markers:
            x, y = cx + focal * point[0] / point[2], cy + focal * point[1] / point[2]
            self._picks.append((x, y, item.bone))
            colour = _MARKER_COLORS.get(item.draw, QColor(90, 200, 255))
            size = 7 if item.bone == self.selected_bone else 4
            painter.setPen(QPen(QColor(255, 255, 0) if item.bone == self.selected_bone else colour.darker(150), 1))
            painter.setBrush(colour)
            painter.drawEllipse(QPointF(x, y), size, size)
            if item.bone == self.selected_bone:
                painter.drawText(QPointF(x + 8, y - 8), item.label)

        if not self.game_camera:
            self._draw_battle_camera(painter, to_camera, focal, cx, cy)
        painter.setPen(QColor(220, 220, 220))
        mode = "Game camera (op 0x39)" if self.game_camera else "Free camera: drag = orbit, right-drag = pan, wheel = zoom"
        painter.drawText(8, 16, f"tick {self.tick} ({self.tick / 15:.2f} s) - {mode}")

    # ------------------------------------------------------------------ textures
    def _texture(self, vram, texture, state, order):
        """(QImage of the texture page, [(u, v)] in drawing order, blend mode or None) of a face."""
        uvs, clut, tpage = texture
        tpage_or, clut_add, uv_add, semi = state
        tpage = (tpage | tpage_or) & 0xFFFF
        clut = (clut + clut_add) & 0xFFFF
        words = [(uvs[k] + uv_add) & 0xFFFF for k in order]
        image = self._page_image(vram, tpage, clut)
        blend = (tpage >> 5) & 3 if semi else None
        return image, [(w & 0xFF, (w >> 8) & 0xFF) for w in words], blend

    def _page_image(self, vram, tpage, clut):
        key = (vram.version(self.tick), tpage & 0x19F, clut)
        entry = self._images.get(key)
        if entry is None:
            if len(self._images) > 256:
                self._images.clear()
            rgba = np.ascontiguousarray(vram.page_rgba(self.tick, tpage, clut))
            image = QImage(rgba.data, 256, 256, 256 * 4, QImage.Format.Format_RGBA8888)
            entry = (image, rgba)  # keep the buffer alive as long as the image
            self._images[key] = entry
        return entry[0]

    @staticmethod
    def _draw_textured(painter, points, sampled):
        """Affine-map the texture page onto the polygon, one triangle at a time (like the GPU)."""
        image, uvs, blend = sampled
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        if blend == 1 or blend == 3:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            if blend == 3:
                painter.setOpacity(0.25)
        elif blend == 0:
            painter.setOpacity(0.5)
        elif blend == 2:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Difference)
        for a, b, c in ((0, 1, 2), (0, 2, 3)) if len(points) == 4 else ((0, 1, 2),):
            (u0, v0), (u1, v1), (u2, v2) = uvs[a], uvs[b], uvs[c]
            det = (u1 - u0) * (v2 - v0) - (u2 - u0) * (v1 - v0)
            if det == 0:
                continue
            p0, p1, p2 = points[a], points[b], points[c]
            # screen = A * (u, v) + t, solved from the three corners
            m11 = ((p1.x() - p0.x()) * (v2 - v0) - (p2.x() - p0.x()) * (v1 - v0)) / det
            m21 = ((p2.x() - p0.x()) * (u1 - u0) - (p1.x() - p0.x()) * (u2 - u0)) / det
            m12 = ((p1.y() - p0.y()) * (v2 - v0) - (p2.y() - p0.y()) * (v1 - v0)) / det
            m22 = ((p2.y() - p0.y()) * (u1 - u0) - (p1.y() - p0.y()) * (u2 - u0)) / det
            dx = p0.x() - m11 * u0 - m21 * v0
            dy = p0.y() - m12 * u0 - m22 * v0
            path = QPainterPath()
            path.addPolygon(QPolygonF([p0, p1, p2]))
            painter.setTransform(QTransform())
            painter.setClipPath(path)
            painter.setTransform(QTransform(m11, m12, m21, m22, dx, dy))
            left, top = min(u0, u1, u2), min(v0, v1, v2)
            source = QRectF(left, top, max(u0, u1, u2) - left + 1, max(v0, v1, v2) - top + 1)
            painter.drawImage(source, image, source)
        painter.restore()

    def _draw_grid(self, painter, to_camera, focal, cx, cy):
        """Battle floor (y = 0) grid, 1024 units per cell."""
        painter.setPen(QPen(QColor(70, 75, 90), 1))
        extent, step = 8192, 1024
        for value in range(-extent, extent + 1, step):
            for a, b in (((value, 0, -extent), (value, 0, extent)), ((-extent, 0, value), (extent, 0, value))):
                segment = to_camera(np.array([a, b], float))
                if segment[0][2] <= self.NEAR or segment[1][2] <= self.NEAR:
                    continue
                painter.drawLine(QPointF(cx + focal * segment[0][0] / segment[0][2], cy + focal * segment[0][1] / segment[0][2]),
                                 QPointF(cx + focal * segment[1][0] / segment[1][2], cy + focal * segment[1][1] / segment[1][2]))

    def _draw_battle_camera(self, painter, to_camera, focal, cx, cy):
        view = self.scene.camera(self.tick)
        if view is None:
            return
        eye, target = to_camera(np.asarray(view, float))
        painter.setPen(QPen(QColor(66, 133, 244), 2))
        if eye[2] > self.NEAR:
            ex, ey = cx + focal * eye[0] / eye[2], cy + focal * eye[1] / eye[2]
            painter.drawRect(int(ex) - 6, int(ey) - 4, 12, 8)
            painter.drawText(QPointF(ex + 8, ey), "battle camera")
            if target[2] > self.NEAR:
                painter.setPen(QPen(QColor(66, 133, 244), 1, Qt.PenStyle.DashLine))
                painter.drawLine(QPointF(ex, ey), QPointF(cx + focal * target[0] / target[2], cy + focal * target[1] / target[2]))

    # ------------------------------------------------------------------ interaction
    def mousePressEvent(self, event):
        self._drag = event.position()
        self._drag_button = event.button()
        self._press = event.position()

    def mouseMoveEvent(self, event):
        if self._drag is None or self.game_camera:
            return
        delta = event.position() - self._drag
        self._drag = event.position()
        if self._drag_button == Qt.MouseButton.LeftButton:
            self.yaw += delta.x() * 0.01
            self.pitch = max(-1.5, min(1.5, self.pitch + delta.y() * 0.01))
        else:
            camera = self._camera_world()
            scale = self.distance / self._focal()
            self.target = self.target - camera[:3, 0] * delta.x() * scale - camera[:3, 1] * delta.y() * scale
        self.update()

    def mouseReleaseEvent(self, event):
        moved = (event.position() - self._press).manhattanLength() if self._drag is not None else 99
        self._drag = None
        if moved < 4 and self._picks:
            x, y = event.position().x(), event.position().y()
            best = min(self._picks, key=lambda p: (p[0] - x) ** 2 + (p[1] - y) ** 2)
            if (best[0] - x) ** 2 + (best[1] - y) ** 2 < 15 ** 2:
                self.selected_bone = best[2]
                self.bone_clicked.emit(best[2])
                self.update()

    def wheelEvent(self, event):
        if self.game_camera:
            return
        self.distance *= 0.87 if event.angleDelta().y() > 0 else 1 / 0.87
        self.update()
