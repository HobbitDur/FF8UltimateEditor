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
        geometry_data = enemy.geometry_data
        faces = [list(t) for t in geometry_data.get_triangles()]
        faces += [[q[0], q[1], q[3], q[2]] for q in geometry_data.get_quads()]
        animations = []
        for anim_id, anim in enumerate(enemy.animation_data.animations):
            frames = []
            for frame_id in range(len(anim.frames)):
                viewer = np.asarray(manager.get_animated_vertices(anim_id, frame_id), float)
                engine = np.column_stack((viewer[:, 0] * AXIS[0], viewer[:, 1] * AXIS[1], viewer[:, 2] * AXIS[2])) * _VIEWER_SCALE
                frames.append(CreatureFrame(engine, faces))
            animations.append(frames)
        return animations
