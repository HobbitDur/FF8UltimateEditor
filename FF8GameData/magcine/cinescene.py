"""3D scene of a simulated GF cinematic, tick by tick: where every bone is and what it draws.

Built on a CineSimulation (per-tick outAngle/outPos of every live bone, the node builder / parent /
draw handler / mesh each bone uses, the battle camera of op 0x39) and the mag containers holding
the meshes. The engine's node matrices embed the camera (node 0); here the camera is left out, so
every node becomes a WORLD transform and the scene can be looked at from anywhere - or through the
simulated battle camera.

Node builders (what a bone's own node is), camera left out:
  0x66 / 0x116: translation outPos          0x67 / 0x6A / 0xC4 / 0x104 / 0x105: rotation outAngle + outPos
  0x65: rotation from outPos used as angles 0x69: parent bone's node x (outAngle, outPos)
  0x7A: parent bone's node                  0xCB: look-at from one bone to another
A drawn bone is placed in its PARENT node (op 0x68, default node 0 = the camera): mesh handler 1
at outPos, 2 with the scale outAngle x 16, 3 (the creature) at outPos scaled by outAngle x 16, 7 under
the camera. Approximations: bone handlers 2, 4, 8-11 are not evaluated (see CineSimulation),
billboards face nothing in particular, textures are not sampled.

Coordinates are the engine's: 4096 = one turn, +Y points down.
"""
import math
from dataclasses import dataclass

import numpy as np

TURN = 4096.0


def rotation(ax, ay, az):
    """Engine rotation matrix (GTE RotMatrix: X, then Y, then Z)."""
    rx, ry, rz = (a * 2 * math.pi / TURN for a in (ax, ay, az))
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    mx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    my = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    mz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return mx @ my @ mz


def affine(rot=None, pos=(0, 0, 0), scale=None):
    m = np.identity(4)
    r = np.identity(3) if rot is None else rot
    if scale is not None:
        r = r @ np.diag(scale)
    m[:3, :3] = r
    m[:3, 3] = pos
    return m


def look_at(eye, target, down=(0.0, 1.0, 0.0)):
    """World matrix of an object at `eye` whose +Z looks at `target`, +X = screen right, +Y =
    screen down (the engine's axes: right x down = forward)."""
    eye, target, down = np.asarray(eye, float), np.asarray(target, float), np.asarray(down, float)
    forward = target - eye
    norm = np.linalg.norm(forward)
    if norm < 1e-6:
        return affine(pos=eye)
    forward /= norm
    right = np.cross(down, forward)
    if np.linalg.norm(right) < 1e-6:
        right = np.array([1.0, 0.0, 0.0])
    right /= np.linalg.norm(right)
    down = np.cross(forward, right)
    m = np.identity(4)
    m[:3, 0], m[:3, 1], m[:3, 2], m[:3, 3] = right, down, forward, eye
    return m


@dataclass
class SceneItem:
    bone: int
    kind: str                 # mesh / creature / marker
    matrix: np.ndarray        # world transform
    mesh: object = None       # CineMesh (mesh) / CreatureFrame (creature)
    draw: int = 0             # draw handler id
    label: str = ""


@dataclass
class CreatureFrame:
    vertices: np.ndarray      # (n, 3) engine units
    faces: list               # [indices]


class CineScene:
    def __init__(self, simulation, containers, creature_provider=None):
        """containers: MagContainers (the .00 first, then .01 and streamed parts), searched in
        order for an object id. creature_provider(object_id) -> (animations) where animations is a
        list of lists of CreatureFrame, or None."""
        self.sim = simulation
        self.objects = {}
        for container in containers:
            for obj in container.objects:
                self.objects.setdefault(obj.index, obj)
        self.creature_provider = creature_provider
        self._creatures = {}

    @property
    def tick_count(self):
        return len(self.sim.frames)

    # ------------------------------------------------------------------ camera
    def camera(self, tick):
        """(eye, target) of the simulated battle camera at `tick`, or None before the first 0x39."""
        record = None
        for when in range(min(tick, self.tick_count - 1), -1, -1):
            if when in self.sim.cameras:
                record = self.sim.cameras[when]
                break
        if record is None:
            return None
        eye_bone, target_bone = record
        eye = self._position(eye_bone, tick)
        target = self._position(target_bone, tick) if target_bone >= 0 else None
        if eye is None:
            return None
        if target is None or np.allclose(eye, target):
            target = np.asarray(eye) + np.array([0.0, 0.0, 1.0])
        return np.asarray(eye, float), np.asarray(target, float)

    def camera_matrix(self, tick):
        view = self.camera(tick)
        return look_at(*view) if view else np.identity(4)

    def _position(self, bone, tick):
        """outPos of a bone at `tick`, or its last known one after it died."""
        for when in range(min(tick, self.tick_count - 1), -1, -1):
            out = self.sim.frames[when].get(bone)
            if out is not None:
                return out[3:6]
        return None

    # ------------------------------------------------------------------ nodes
    def node(self, bone, tick, cache=None, depth=0):
        """World matrix of the node a bone builds (None if it builds none)."""
        cache = {} if cache is None else cache
        if bone in cache:
            return cache[bone]
        cache[bone] = None  # cycle guard
        out = self.sim.frames[tick].get(bone)
        node = self.sim.bones[bone].prop("node", tick) if bone >= 0 else None
        if out is None or node is None or depth > 16:
            return None
        code, _op, words, refs = node
        rot, pos = rotation(*out[:3]), out[3:6]
        if code in (0x66, 0x116, 0x84):
            matrix = affine(pos=pos) if code != 0x116 else affine(rot, pos)
        elif code == 0x65:
            matrix = affine(rotation(*out[3:6]))
        elif code == 0x69:
            parent = self.node(refs[0], tick, cache, depth + 1) if refs else None
            matrix = (parent if parent is not None else np.identity(4)) @ affine(rot, pos)
        elif code == 0x7A:
            parent = self.node(refs[0], tick, cache, depth + 1) if refs and refs[0] >= 0 else None
            matrix = parent if parent is not None else affine(pos=pos)
        elif code == 0xCB:
            eye, target = (self._position(r, tick) for r in refs[:2])
            if eye is None or target is None:
                matrix = affine(pos=pos)
            else:
                matrix = look_at(eye, target)
                matrix[:3, 3] = target if _op & 0x1000 else eye
        else:  # 0x67, 0x6A, 0xC4, 0x104, 0x105
            matrix = affine(rot, pos)
        cache[bone] = matrix
        return matrix

    def parent_matrix(self, bone, tick, cache):
        """The node a drawn bone is placed in: op 0x68's parent, default node 0 = the camera."""
        parent = self.sim.bones[bone].prop("parent", tick)
        if parent is not None and parent >= 0:
            matrix = self.node(parent, tick, cache)
            if matrix is not None:
                return matrix
        return self.camera_matrix(tick)

    # ------------------------------------------------------------------ items
    def items(self, tick, show_helpers=True):
        """Everything to draw at `tick`."""
        if not 0 <= tick < self.tick_count:
            return []
        cache = {}
        result = []
        for bone, out in self.sim.frames[tick].items():
            sim_bone = self.sim.bones[bone]
            draw = sim_bone.prop("draw", tick, 0) or 0
            if sim_bone.prop("hidden", tick, False):
                draw = 0
            angle, pos = out[:3], out[3:6]
            label = f"#{bone}"
            if draw in (1, 2, 9, 27, 7):
                mesh = self.objects.get(sim_bone.prop("mesh", tick, -1))
                if mesh is not None and mesh.kind == "mesh" and mesh.mesh is not None and mesh.mesh.faces:
                    if draw == 7:
                        base = self.camera_matrix(tick)
                        scale = [max(1, angle[2] * 16) / TURN] * 3
                    else:
                        base = self.parent_matrix(bone, tick, cache)
                        scale = [a * 16 / TURN if a else 1.0 for a in angle] if draw == 2 else None
                        if draw == 27:
                            scale = [max(1, angle[2] * 16) / TURN] * 3
                    position = (0, 0, 0) if draw == 9 else pos
                    result.append(SceneItem(bone, "mesh", base @ affine(pos=position, scale=scale),
                                            mesh.mesh, draw, label))
                    continue
            if draw == 3:
                frame = self._creature_frame(sim_bone, tick)
                if frame is not None:
                    base = self.parent_matrix(bone, tick, cache)
                    # SetupParentXformScaled: parent node, outPos, outAngle x 16 = XYZ scale (256 = 1)
                    scale = [a * 16 / TURN for a in angle]
                    result.append(SceneItem(bone, "creature", base @ affine(pos=pos, scale=scale),
                                            frame, draw, label))
                    continue
            if draw or show_helpers:
                node = self.node(bone, tick, cache)
                matrix = node if node is not None else self.parent_matrix(bone, tick, cache) @ affine(pos=pos)
                result.append(SceneItem(bone, "marker", matrix, None, draw, label))
        return result

    def _creature_frame(self, sim_bone, tick):
        model = sim_bone.prop("model", tick)
        if model is None or self.creature_provider is None:
            return None
        object_id, anim_id = model
        if object_id not in self._creatures:
            self._creatures[object_id] = self.creature_provider(object_id)
        animations = self._creatures[object_id]
        if not animations:
            return None
        frames = animations[min(anim_id, len(animations) - 1)]
        if not frames:
            return None
        started = next((when for when, key, _v in sim_bone.props if key == "model"), sim_bone.spawn_tick)
        return frames[(tick - started) % len(frames)]
