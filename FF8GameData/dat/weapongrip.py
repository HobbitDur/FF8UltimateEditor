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


def vanilla_grip(body_model, weapon_model):
    """The Grip of a weapon not converted yet (15 fps, like its body), or None: each original
    frame doubled, so find_grip reads them as the original frames of a conversion."""
    pairs = [(anim_id, [frame for frame in body_frames for _ in (0, 1)],
              [frame for frame in weapon_frames for _ in (0, 1)])
             for anim_id, body_frames, weapon_frames in _pairs(body_model, weapon_model)]
    return find_grip(body_model, weapon_model, pairs)


def has_steady_grip(body_model, weapon_model) -> bool:
    """Whether a weapon not converted yet (15 fps, like its body) holds a steady grip in its
    hand (spread at most MAX_GRIP_SPREAD): its in-betweens will be pinned there."""
    grip = vanilla_grip(body_model, weapon_model)
    return grip is not None and grip.spread <= MAX_GRIP_SPREAD


def pin_frames(grip, body_model, weapon_model, body_frames, weapon_frames) -> dict:
    """Pin the grip in the hand on the in-between (odd) frames of one converted animation pair:
    each in-between whose two original frames around it hold the grip gets its weapon root
    moved so the grip sits at the offset half-way between theirs. Returns {'nb_pinned',
    'worst_before', 'worst_after'} (vertex units). The caller re-encodes the weapon frames."""
    report = {'nb_pinned': 0, 'worst_before': 0.0, 'worst_after': 0.0}

    def offset(index):
        return grip.offset(body_model, weapon_model, body_frames[index], weapon_frames[index])

    for index in range(1, min(len(body_frames), len(weapon_frames)), 2):
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
            now = offset(index)
        report['worst_after'] = max(report['worst_after'], float(np.linalg.norm(now)))
    return report


def _weapon_points(weapon_model):
    """(bone ids, local points * _FLIP) of every vertex of the weapon."""
    bone_list, point_list = [], []
    for obj in weapon_model.geometry_data.object_data:
        for vertex_data in obj.vertices_data:
            for vertex in vertex_data.vertices:
                bone_list.append(vertex_data.bone_id)
                point_list.append(vertex.get_list())
    return np.array(bone_list, dtype=int), np.array(point_list, dtype=float).reshape(-1, 3) * _FLIP


def _hand_space(grip, body_model, weapon_model, points, body_frame, weapon_frame):
    """The weapon's vertices seen from the hand (the grip's body bone): (V, 3)."""
    bone_ids, local = points
    rotation_w, translation_w = _bone_frames(weapon_frame, weapon_model.bone_data.bones)
    rotation_b, translation_b = _bone_frames(body_frame, body_model.bone_data.bones)
    world = (np.einsum('nij,nj->ni', rotation_w[bone_ids], local) + translation_w[bone_ids]
             + ROOT_TO_VERTEX * (_root(weapon_frame) - _root(body_frame)))
    return (world - translation_b[grip.body_bone]) @ rotation_b[grip.body_bone]


def _with_model_rotations(frame, model_list, parent_list, bones):
    """A copy of frame whose bones turn as model_list says (rotations in the model's space)."""
    import copy
    from FF8GameData.dat import rotation3d
    from FF8GameData.monsterdata import Animation, RotationType
    new_frame = copy.deepcopy(frame)
    for bone_index, parent in enumerate(parent_list):
        model = [list(row) for row in model_list[bone_index]]
        local = model if parent is None else rotation3d.multiply(
            rotation3d.transpose([list(row) for row in model_list[parent]]), model)
        pose = rotation3d.matrix_to_euler_raw(local, Animation._bone_pose_raw(frame, bone_index))
        new_frame.rotation_vector_data[bone_index] = [RotationType(True, 0, raw) for raw in pose]
    new_frame._reset_matrix_lists(len(bones))
    new_frame.set_all_bones_matrix(bones)
    return new_frame


def smooth_in_betweens(grip, body_model, weapon_model, body_frames, weapon_frames) -> dict:
    """After pin_frames: each in-between of a held weapon whose pose, seen from the hand, is not
    between the two original frames around it (a 1/30 s jump) takes the pose that is, of:
    - as blended (dat30's step plan: a far turn blended in the model, the long way round when it
      carries a spin on, a snap held where it is in the model);
    - every bone turned the short way, in the model;
    - the pose of the frame before, or after, carried rigidly by the hand (a snap: the weapon
      keeps its pose in the hand while the hand moves on, then snaps, as vanilla shows it).
    A plan is right for the battle models, where the body holds the snaps with its weapons; on a
    pose whose body blends on (r0win.dat) a held snap leaves the weapon still while the hand moves
    (Selphie's victory pose: her nunchaku 6.6 vertex units off for 1/30 s), and a spin read on a
    snapped step sends a bone the long way (frame 12: 224 deg instead of 136). The chosen pose is
    pinned in the hand. Returns {'nb_changed', 'worst_before', 'worst_after'}: how far the worst
    in-between sits from the middle of its two neighbours, seen from the hand (vertex units)."""
    from FF8GameData.dat import rotation3d
    from FF8GameData.monsterdata import Animation
    bones = weapon_model.bone_data.bones
    report = {'nb_changed': 0, 'worst_before': 0.0, 'worst_after': 0.0}
    parent_list = []
    for bone_index, bone in enumerate(bones):
        parent = None if bone.parent_id == 0xFFFF else bone.parent_id
        if parent is not None and not 0 <= parent < bone_index:
            return report        # not stored parents first: no model space to work in
        parent_list.append(parent)
    points = _weapon_points(weapon_model)
    if not len(points[0]):
        return report

    def hand_space(index, weapon_frame=None):
        return _hand_space(grip, body_model, weapon_model, points, body_frames[index],
                           weapon_frames[index] if weapon_frame is None else weapon_frame)

    def hand_rotation(index):
        _ensure_matrices(body_frames[index], body_model.bone_data.bones)
        return _bone_frames(body_frames[index], body_model.bone_data.bones)[0][grip.body_bone]

    def pinned(index, weapon_frame):
        """weapon_frame with its root moved so the grip sits half-way between its neighbours'."""
        before = grip.offset(body_model, weapon_model, body_frames[index - 1], weapon_frames[index - 1])
        after = grip.offset(body_model, weapon_model, body_frames[index + 1], weapon_frames[index + 1])
        correction = (before + after) / 2 - grip.offset(body_model, weapon_model, body_frames[index], weapon_frame)
        for axis, position in enumerate(weapon_frame.position[:3]):
            position.move_world(correction[axis] / ROOT_TO_VERTEX)
        weapon_frame._reset_matrix_lists(len(bones))
        weapon_frame.set_all_bones_matrix(bones)
        return weapon_frame

    for index in range(1, min(len(body_frames), len(weapon_frames)) - 1, 2):
        frame_a, frame_b = weapon_frames[index - 1], weapon_frames[index + 1]
        if (np.linalg.norm(grip.offset(body_model, weapon_model, body_frames[index - 1], frame_a)) > HELD_DISTANCE
                or np.linalg.norm(grip.offset(body_model, weapon_model, body_frames[index + 1], frame_b))
                > HELD_DISTANCE):
            continue
        middle = (hand_space(index - 1) + hand_space(index + 1)) / 2

        def distance(weapon_frame):
            """(farthest vertex + mean vertex, farthest vertex) from the middle of the neighbours:
            a pose is chosen on both, the farthest alone took for Selphie's victory frame 97 a
            pose 0.02 closer there that drew her free stick 1.4 out from behind the held one
            (mean 0.50 -> 0.84), in sight for 1/30 s (filmed)."""
            gap = np.linalg.norm(hand_space(index, weapon_frame) - middle, axis=1)
            return float(gap.max() + gap.mean()), float(gap.max())
        best_frame = weapon_frames[index]
        best, farthest = distance(best_frame)
        report['worst_before'] = max(report['worst_before'], farthest)
        rotation_a = Animation._model_rotation_list(frame_a, parent_list)
        rotation_b = Animation._model_rotation_list(frame_b, parent_list)
        hand = hand_rotation(index)
        candidate_list = [
            [rotation3d.slerp_matrix(a, b, 0.5) for a, b in zip(rotation_a, rotation_b)],
            [(hand @ hand_rotation(index - 1).T @ np.array(a)).tolist() for a in rotation_a],
            [(hand @ hand_rotation(index + 1).T @ np.array(b)).tolist() for b in rotation_b]]
        for model_list in candidate_list:
            candidate = pinned(index, _with_model_rotations(weapon_frames[index], model_list, parent_list, bones))
            score, candidate_farthest = distance(candidate)
            if score < best - MIN_CORRECTION:
                best_frame, best, farthest = candidate, score, candidate_farthest
        if best_frame is not weapon_frames[index]:
            weapon_frames[index] = best_frame
            report['nb_changed'] += 1
        report['worst_after'] = max(report['worst_after'], farthest)
    return report


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
        frame_report = pin_frames(grip, body_model, weapon_model, body_frames, weapon_frames)
        report['nb_pinned'] += frame_report['nb_pinned']
        report['worst_before'] = max(report['worst_before'], frame_report['worst_before'])
        report['worst_after'] = max(report['worst_after'], frame_report['worst_after'])
        if frame_report['nb_pinned']:
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
