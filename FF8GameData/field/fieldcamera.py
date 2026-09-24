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

    def height_at(self, triangle_id: int, x: float, y: float):
        """Z of the triangle's plane at (x, y) (what SET does for a position without Z)."""
        if not 0 <= triangle_id < len(self.triangles):
            return 0.0
        a, b, c = self.triangles[triangle_id]
        normal = np.cross(b - a, c - a)
        if abs(normal[2]) < 1e-9:
            return float(np.mean([a[2], b[2], c[2]]))
        return float(a[2] - (normal[0] * (x - a[0]) + normal[1] * (y - a[1])) / normal[2])
