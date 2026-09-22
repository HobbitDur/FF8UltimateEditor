"""The creature of a GF cinematic (draw handler 3), posed per animation frame.

The creature is an ordinary battle model embedded in the mag file (object with .dat sections 1-3:
skeleton, geometry, animation). It is rebuilt as a temporary battle .dat and posed by
IfritManager (same code as the Ifrit tool), then brought back to engine units for the scene."""
import os
import struct
import tempfile

import numpy as np

from FF8GameData.magcine.cinescene import CreatureFrame

# IfritManager poses in its viewer space (/2048)
_VIEWER_SCALE = 2048.0
# viewer Y is up, the engine's is down; the facing (X/Z sign) is not verified against the game yet
AXIS = (1, -1, 1)


def build_dat(sections):
    """A 11-section battle .dat from skeleton/geometry/animation, the other sections empty."""
    sections = list(sections) + [b""] * (11 - len(sections))
    out = bytearray(struct.pack("<I", 11))
    position = 4 + 11 * 4 + 4
    for section in sections:
        out += struct.pack("<I", position)
        position += len(section)
    out += struct.pack("<I", position)
    for section in sections:
        out += section
    return bytes(out)


class CreatureLoader:
    """creature_provider for CineScene: object id -> [animation][frame] CreatureFrame."""

    def __init__(self, containers):
        self.containers = containers
        self._manager = None

    def _ifrit_manager(self):
        if self._manager is None:
            from Ifrit.ifritmanager import IfritManager
            self._manager = IfritManager()
        return self._manager

    def model_object(self, object_id):
        for container in self.containers:
            for obj in container.objects:
                if obj.index == object_id and obj.kind == "model":
                    return container, obj
        return None, None

    def __call__(self, object_id):
        container, obj = self.model_object(object_id)
        if obj is None:
            return None
        skeleton, geometry, animation = obj.info["sections"]
        end = obj.offset + obj.info["size"]
        data = container.data
        path = os.path.join(tempfile.gettempdir(), f"laguna_creature_{os.getpid()}_{object_id}.dat")
        with open(path, "wb") as f:
            f.write(build_dat([data[skeleton:geometry], data[geometry:animation], data[animation:end]]))
        manager = self._ifrit_manager()
        try:
            enemy = manager.parse_file(path)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        manager.enemy = enemy
        faces, textures = self._faces(enemy.geometry_data)
        animations = []
        for anim_id, anim in enumerate(enemy.animation_data.animations):
            frames = []
            for frame_id in range(len(anim.frames)):
                viewer = np.asarray(manager.get_animated_vertices(anim_id, frame_id), float)
                engine = np.column_stack((viewer[:, 0] * AXIS[0], viewer[:, 1] * AXIS[1], viewer[:, 2] * AXIS[2])) * _VIEWER_SCALE
                frames.append(CreatureFrame(engine, faces, textures))
            animations.append(frames)
        return animations

    @staticmethod
    def _faces(geometry):
        """Faces (quads in PlayStation order 0-1-3-2, like the mag meshes) and, per face, its texture
        ([uv words], CLUT word, tpage word) - absolute VRAM words for the creature - or None."""
        faces, textures = [], []
        uv = lambda t: (t.get_u_raw() & 0xFF) | ((t.get_v_raw() & 0xFF) << 8)
        offset = 0
        for obj in geometry.object_data:
            for tri in obj.triangles:
                if not tri.is_hidden():   # vertices C, A, B carry uvs a, b, c (see get_triangles_with_uv)
                    faces.append([tri.vertex_indexes[2] + offset, tri.vertex_indexes[0] + offset,
                                  tri.vertex_indexes[1] + offset])
                    textures.append(([uv(tri.vta), uv(tri.vtb), uv(tri.vtc)], tri.tex_id_1, tri.tex_id_2))
            for quad in obj.quads:
                if not quad.is_hidden():
                    faces.append([quad.vertex_indexes[i] + offset for i in (0, 1, 3, 2)])
                    textures.append(([uv(quad.vta), uv(quad.vtb), uv(quad.vtd), uv(quad.vtc)],
                                     quad.tex_id_1, quad.tex_id_2))
            for tri in obj.colored_triangles:
                faces.append([i + offset for i in tri.vertex_indexes[:3]])
                textures.append(None)
            for quad in obj.colored_quads:
                faces.append([quad.vertex_indexes[i] + offset for i in (0, 1, 3, 2)])
                textures.append(None)
            offset += sum(vd.nb_vertices for vd in obj.vertices_data)
        return faces, textures
