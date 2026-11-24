"""Keep a character's weapon in its hand on the in-between frames of a 30 fps conversion.

A weapon file (dXwYYY.dat) is not attached to a bone of its body: the engine poses each model
on its own and places the weapon by its own per-frame root position, which the animators made
trace the hand (BattleModel_BuildBoneMatricesFromPose 0x508C90; Ifrit3D/ifrit3dwidget.py,
_current_attached_verts: weapon vertices + 1.6 * (weapon root - body root), in vertex units).
On the original frames the grip of the weapon sits in the hand.

The conversion (dat30) blends each file on its own: the body's hand goes along the arc its arm
turns through, while the weapon root goes straight, and its own bones turn their own way. On a
fast swing the new in-between frame leaves the weapon off the hand (Selphie d5w028 anim 20:
2.2 vertex units; anim 30's last in-between: 5.8), back on it the next frame: at 30 Hz the
weapon shivers against the hand.

pin_family_grips moves the weapon root of each in-between so the grip lands where the hand is,
at the offset half-way between the two original frames around it. The grip is found on the
original frames: the point fixed to a weapon bone that stays fixed to a body bone (the least
squares pair over every frame of every animation). A point, not a vertex: Selphie's four
nunchaku share one animation, but only the Flail (d5w028) has a vertex on the pivot her hand
holds. An in-between is pinned only when the grip is in the hand on both original frames around
it (a thrown weapon, or one that leaves the hand, is left as blended).

Frames are 2k = original frame k, 2k + 1 = the in-between after it (dat30: 2n frames for n).
"""
import numpy as np

# Vertex units (raw / 128): how far the grip may sit from its place in the hand on an original
# frame and still count as held (Selphie's grip: 0.2 at most while held).
HELD_DISTANCE = 0.5
# Below this the in-between is already in the hand: left untouched.
MIN_CORRECTION = 0.01
# A grip is pinned only when it really holds over the original frames (mean distance, vertex
# units). Squall, Irvine, Rinoa, Selphie, Seifer: 0.008-0.011; Quistis 0.032. Laguna's machine
# gun (d8w035, 0.21: 15% of its frames 0.5-1.0 off) and Ward's harpoon (daw039, 1.4: no point of
# it stays in his hand) have no steady grip: pinning one would move the weapon for nothing.
MAX_GRIP_SPREAD = 0.1
# Weapon root -> vertex units (Ifrit3D: get_pos_world is raw / 204.8, vertices raw / 128).
ROOT_TO_VERTEX = 1.6
# Vertex local axes as IfritManager._transform_vertex reads them.
_FLIP = np.array([1.0, -1.0, -1.0])


def _ensure_matrices(frame, bones):
    if frame.bone_matrices is None:
        frame._reset_matrix_lists(len(bones))
        frame.set_all_bones_matrix(bones)


def _bone_frames(frame, bones):
    """((B, 3, 3) rotations, (B, 3) translations) of every bone: a point p fixed to bone b is at
    rotation[b] @ (p * _FLIP) + translation[b] (IfritManager._transform_vertex)."""
    _ensure_matrices(frame, bones)
    rotation = np.array([[[m.M11, m.M12, m.M13], [m.M21, m.M22, m.M23], [m.M31, m.M32, m.M33]]
                         for m in frame.bone_matrices])
    translation = np.array([[m.M41, m.M42, m.M43] for m in frame.bone_matrices])
    return rotation, translation


def _root(frame):
    return np.array([position.get_pos_world() for position in frame.position[:3]])


def _pairs(body_model, weapon_model):
    """[(anim id, body frames, weapon frames)] the two models share (same id, same frame count)."""
    result = []
    for anim_id, (body_anim, weapon_anim) in enumerate(zip(body_model.animation_data.animations,
                                                           weapon_model.animation_data.animations)):
        if body_anim.frames and len(body_anim.frames) == len(weapon_anim.frames):
            result.append((anim_id, body_anim.frames, weapon_anim.frames))
    return result


class Grip:
    """A point fixed to weapon bone `weapon_bone` that stays on a point fixed to body bone
    `body_bone` (each in its bone's local vertex space)."""

    def __init__(self, weapon_bone, weapon_point, body_bone, body_point, spread):
        self.weapon_bone, self.weapon_point = weapon_bone, weapon_point
        self.body_bone, self.body_point = body_bone, body_point
        self.spread = spread

    def offset(self, body_model, weapon_model, body_frame, weapon_frame):
        """How far the weapon's grip is from the hand's on one frame (vertex units, 3D)."""
        rotation_w, translation_w = _bone_frames(weapon_frame, weapon_model.bone_data.bones)
        rotation_b, translation_b = _bone_frames(body_frame, body_model.bone_data.bones)
        weapon_point = (rotation_w[self.weapon_bone] @ (self.weapon_point * _FLIP)
                        + translation_w[self.weapon_bone]
                        + ROOT_TO_VERTEX * (_root(weapon_frame) - _root(body_frame)))
        body_point = (rotation_b[self.body_bone] @ (self.body_point * _FLIP)
                      + translation_b[self.body_bone])
        return weapon_point - body_point


def find_grip(body_model, weapon_model, pairs):
    """The Grip that holds best over the original (even) frames, or None. For every pair of
    bones, the least squares points p (weapon bone) and c (body bone) with
    R_w p + T_w + root delta = R_b c + T_b on every frame; the pair that fits best is the grip."""
    weapon_list, body_list = [], []
    for _anim_id, body_frames, weapon_frames in pairs:
        for body_frame, weapon_frame in zip(body_frames[0::2], weapon_frames[0::2]):
            rotation_w, translation_w = _bone_frames(weapon_frame, weapon_model.bone_data.bones)
            rotation_b, translation_b = _bone_frames(body_frame, body_model.bone_data.bones)
            delta = ROOT_TO_VERTEX * (_root(weapon_frame) - _root(body_frame))
            weapon_list.append((rotation_w * _FLIP, translation_w + delta))
            body_list.append((rotation_b * _FLIP, translation_b))
    if not weapon_list:
        return None
    rotation_w = np.array([rotation for rotation, _ in weapon_list])         # (F, Bw, 3, 3)
    translation_w = np.array([translation for _, translation in weapon_list])  # (F, Bw, 3)
    rotation_b = np.array([rotation for rotation, _ in body_list])
    translation_b = np.array([translation for _, translation in body_list])
    nb_frame = rotation_w.shape[0]
    best = None
    for weapon_bone in range(rotation_w.shape[1]):
        for body_bone in range(rotation_b.shape[1]):
            # [R_w  -R_b] [p; c] = T_b - T_w, stacked over every frame
            matrix = np.concatenate([rotation_w[:, weapon_bone], -rotation_b[:, body_bone]], axis=2)
            matrix = matrix.reshape(3 * nb_frame, 6)
            target = (translation_b[:, body_bone] - translation_w[:, weapon_bone]).reshape(-1)
            solution, *_ = np.linalg.lstsq(matrix, target, rcond=None)
            error = (matrix @ solution - target).reshape(nb_frame, 3)
            spread = float(np.linalg.norm(error, axis=1).mean())
            if best is None or spread < best.spread:
                best = Grip(weapon_bone, solution[:3], body_bone, solution[3:], spread)
    return best


def pin_weapon_grip(body_model, weapon_model) -> dict:
    """Pin one converted weapon's grip to its converted body's hand on the in-between frames.
    Returns {'grip': Grip or None, 'steady': bool, 'nb_pinned': int, 'worst_before': float,
    'worst_after': float} (the worst distance of an in-between's grip from the hand, vertex units).
    A grip that does not hold (spread over MAX_GRIP_SPREAD) is reported, not pinned."""
    report = {'grip': None, 'steady': False, 'nb_pinned': 0, 'worst_before': 0.0, 'worst_after': 0.0}
    pairs = _pairs(body_model, weapon_model)
    grip = find_grip(body_model, weapon_model, pairs)
    if grip is None:
        return report
    report['grip'] = grip
    report['steady'] = grip.spread <= MAX_GRIP_SPREAD
    if not report['steady']:
        return report

    for anim_id, body_frames, weapon_frames in pairs:
        def offset(index):
            return grip.offset(body_model, weapon_model, body_frames[index], weapon_frames[index])

        changed = False
        for index in range(1, len(weapon_frames), 2):
            before = offset(index - 1)
            after = offset(index + 1) if index + 1 < len(weapon_frames) else before
            if np.linalg.norm(before) > HELD_DISTANCE or np.linalg.norm(after) > HELD_DISTANCE:
                continue        # not in the hand around this in-between: leave it as blended
            now = offset(index)
            report['worst_before'] = max(report['worst_before'], float(np.linalg.norm(now)))
            correction = (before + after) / 2 - now
            if np.linalg.norm(correction) >= MIN_CORRECTION:
                for axis, position in enumerate(weapon_frames[index].position[:3]):
                    position.move_world(correction[axis] / ROOT_TO_VERTEX)
                report['nb_pinned'] += 1
                changed = True
                now = offset(index)
            report['worst_after'] = max(report['worst_after'], float(np.linalg.norm(now)))
        if changed:
            weapon_model.animation_data.animations[anim_id]._recompute_frame_storage_types()
    return report


def pin_family_grips(model_by_name: dict) -> dict:
    """{weapon file name: pin_weapon_grip report} for a converted character family
    ({file name: loaded model}): every weapon (dXw) pinned to the first body (dXc) of the same
    character. A family without a body is left as it is."""
    def kind(name):
        name = name.lower()
        return name[2] if len(name) > 2 and name[0] == 'd' else ''

    body_list = [(name, model) for name, model in model_by_name.items()
                 if kind(name) == 'c' and model.bone_data and model.bone_data.bones]
    result = {}
    for name, model in model_by_name.items():
        if kind(name) != 'w' or not (model.bone_data and model.bone_data.bones):
            continue
        if not model.animation_data.animations:
            continue
        for body_name, body_model in body_list:
            if body_name[1].lower() == name[1].lower():
                result[name] = pin_weapon_grip(body_model, model)
                break
    return result
