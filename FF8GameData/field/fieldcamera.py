"""
Field camera (.ca) and walkmesh (.id): project a field position onto the background image.

.ca (38 bytes, or 0x28 per camera when there are several): three camera axes as int16
vectors (4096 = 1.0), a copy of axis_z.z, a translation (3 x int32), 4 unused bytes and the
zoom (u16). A field point P goes to camera space as C = (axes / 4096) . P + translation, and to
the screen as (C.x * zoom / C.z, C.y * zoom / C.z), relative to the background origin (the
field's (0, 0) tile position, see fieldbackground.render_background). Checked by projecting
the walkmesh of bghall_1: it lands exactly on the floor, stairs and bridge of the picture.

.id: u32 triangle count, then per triangle 3 vertices of (int16 x, y, z, padding).
"""
import struct

import numpy as np

CAMERA_ENTRY_SIZE = 0x28
AXIS_ONE = 4096.0
WALKMESH_TRIANGLE_SIZE = 24


WHOLE_POSITION_STEPS = 8


def _inside(corners, x, y):
    (ax, ay), (bx, by), (cx, cy) = corners
    sides = ((bx - ax) * (y - ay) - (by - ay) * (x - ax), (cx - bx) * (y - by) - (cy - by) * (x - bx),
             (ax - cx) * (y - cy) - (ay - cy) * (x - cx))
    return all(side >= 0 for side in sides) or all(side <= 0 for side in sides)


class FieldCamera:
    def __init__(self, ca_data: bytes, camera_index: int = 0):
        offset = camera_index * CAMERA_ENTRY_SIZE
        self.axes = np.array(struct.unpack_from("<9h", ca_data, offset), dtype=float).reshape(3, 3) / AXIS_ONE
        self.translation = np.array(struct.unpack_from("<3i", ca_data, offset + 20), dtype=float)
        (self.zoom,) = struct.unpack_from("<H", ca_data, offset + 36)

    def project(self, point):
        """Screen position (relative to the background origin) of a field point, or None when
        it is behind the camera."""
        camera_space = self.axes @ np.asarray(point, dtype=float) + self.translation
        if camera_space[2] <= 0:
            return None
        return (camera_space[0] * self.zoom / camera_space[2], camera_space[1] * self.zoom / camera_space[2])

    def ray(self, screen):
        """(origin, direction) in field space of what shows at a screen position."""
        inverse = np.linalg.inv(self.axes)
        return inverse @ -self.translation, inverse @ np.array((screen[0] / self.zoom, screen[1] / self.zoom, 1.0))

    def depth(self, point):
        return (self.axes @ np.asarray(point, dtype=float) + self.translation)[2]


class Walkmesh:
    def __init__(self, id_data: bytes):
        (nb_triangles,) = struct.unpack_from("<I", id_data, 0)
        self.triangles = []
        for triangle in range(nb_triangles):
            offset = 4 + triangle * WALKMESH_TRIANGLE_SIZE
            if offset + WALKMESH_TRIANGLE_SIZE > len(id_data):
                break
            self.triangles.append([np.array(struct.unpack_from("<3h", id_data, offset + vertex * 8), dtype=float)
                                   for vertex in range(3)])

    def contains(self, triangle_id: int, x: float, y: float) -> bool:
        """Whether a position lies in a triangle, seen from above; its edges count."""
        if not 0 <= triangle_id < len(self.triangles):
            return False
        return _inside([vertex[:2] for vertex in self.triangles[triangle_id]], x, y)

    def point_at(self, camera: FieldCamera, screen):
        """The whole-number (x, y, triangle) of the walkmesh at a screen position, None off it. Where it overlaps
        itself on screen, a bridge over a path, the surface nearest the camera."""
        origin, direction = camera.ray(screen)
        best = None
        for triangle_id, vertices in enumerate(self.triangles):
            corners = [camera.project(vertex) for vertex in vertices]
            if None in corners or not _inside(corners, *screen):
                continue
            a, b, c = vertices
            normal = np.cross(b - a, c - a)
            facing = normal @ direction
            if abs(facing) < 1e-9:
                continue
            point = origin + direction * (normal @ (a - origin) / facing)
            depth = camera.depth(point)
            if depth > 0 and (best is None or depth < best[0]):
                best = depth, point, triangle_id
        if best is None:
            return None
        return self._whole_position(best[2], best[1])

    def _whole_position(self, triangle_id, point):
        """Rounding can step out of a thin triangle: walk toward its middle until it is back in."""
        middle = np.mean(self.triangles[triangle_id], axis=0)
        for step in range(WHOLE_POSITION_STEPS + 1):
            spot = point + (middle - point) * step / WHOLE_POSITION_STEPS
            x, y = round(float(spot[0])), round(float(spot[1]))
            if self.contains(triangle_id, x, y):
                return x, y, triangle_id
        return None

    def height_at(self, triangle_id: int, x: float, y: float):
        """Z of the triangle's plane at (x, y) (what SET does for a position without Z)."""
        if not 0 <= triangle_id < len(self.triangles):
            return 0.0
        a, b, c = self.triangles[triangle_id]
        normal = np.cross(b - a, c - a)
        if abs(normal[2]) < 1e-9:
            return float(np.mean([a[2], b[2], c[2]]))
        return float(a[2] - (normal[0] * (x - a[0]) + normal[1] * (y - a[1])) / normal[2])
