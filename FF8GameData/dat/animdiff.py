"""What changed in a model's animations compared with a reference (the file as it was opened, or a
vanilla file): the data behind Ifrit3D's timeline.

A snapshot keeps only the raw numbers of every frame - so it is small, and a reference survives any
edit of the live model:
    snapshot[anim_id][frame_id] = (position, rotations, scales)
    position  = (x, y, z) raw
    rotations = one (rx, ry, rz) raw triple per bone (4096 = one turn)
    scales    = one (sx, sy, sz) raw triple per bone (1024 = 1.0) when the frame's scale mode bit is
                set, else None (the engine ignores the scale payloads then)

The diff is per animation and per cell: a row (ROW_POSITION, or a bone id) at a frame. Only cells
that differ are kept.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

ROTATION_RAW_PER_TURN = 4096
SCALE_NEUTRAL_RAW = 1024
ROW_POSITION = -1

STATUS_SAME = "same"
STATUS_CHANGED = "changed"
STATUS_NEW = "new"            # the reference has no animation with this id
STATUS_REMOVED = "removed"    # the reference has it, the model no longer does

NEUTRAL_SCALE = (SCALE_NEUTRAL_RAW,) * 3


def snapshot_frame(frame) -> tuple:
    position = tuple(int(p.get_pos_raw()) for p in frame.position) if frame.position else (0, 0, 0)
    rotations = tuple(tuple(int(axis.get_rotate_raw()) for axis in bone) for bone in frame.rotation_vector_data)
    scales = None
    if frame.mode_bit == 1:
        scales = tuple((s.get_scale_raw(0), s.get_scale_raw(1), s.get_scale_raw(2))
                       for s in frame.rotation_vector_data_supp)
    return position, rotations, scales


def snapshot_animation(animation) -> list:
    return [snapshot_frame(frame) for frame in animation.frames]


def snapshot_animations(animation_section) -> list:
    return [snapshot_animation(animation) for animation in animation_section.animations]


def wrap_rotation(raw: int) -> int:
    """The shortest equivalent turn of a raw rotation delta, in [-2048, 2048)."""
    return (raw + ROTATION_RAW_PER_TURN // 2) % ROTATION_RAW_PER_TURN - ROTATION_RAW_PER_TURN // 2


def raw_to_degrees(raw: float) -> float:
    return raw * 360.0 / ROTATION_RAW_PER_TURN


@dataclass
class CellDiff:
    """How one row differs at one frame. For a bone: rotation deltas (raw, shortest turn) and scale
    deltas; for ROW_POSITION: position deltas. new_bone = the reference has no such bone."""
    rotation: Tuple[int, int, int] = (0, 0, 0)
    scale: Tuple[int, int, int] = (0, 0, 0)
    position: Tuple[int, int, int] = (0, 0, 0)
    new_bone: bool = False

    @property
    def rotation_degrees(self) -> float:
        """Largest per-axis rotation difference, in degrees."""
        return raw_to_degrees(max(abs(r) for r in self.rotation))

    @property
    def scale_changed(self) -> bool:
        return any(self.scale)


@dataclass
class AnimationDiff:
    anim_id: int
    status: str
    nb_frames: int = 0
    nb_reference_frames: int = 0
    # current frame -> the reference frame it is compared with (same point in time when the frame
    # counts differ, e.g. after a 30 fps conversion doubled them)
    frame_map: List[int] = field(default_factory=list)
    cells: Dict[Tuple[int, int], CellDiff] = field(default_factory=dict)   # (row, frame) -> diff

    @property
    def retimed(self) -> bool:
        return self.status == STATUS_CHANGED and self.nb_frames != self.nb_reference_frames

    def changed_frames(self) -> set:
        return {frame for (_, frame) in self.cells}

    def changed_rows(self) -> set:
        return {row for (row, _) in self.cells}


def reference_frame_map(nb_frames: int, nb_reference_frames: int) -> List[int]:
    if nb_reference_frames <= 0:
        return []
    if nb_frames == nb_reference_frames:
        return list(range(nb_frames))
    if nb_frames <= 1:
        return [0] * nb_frames
    scale = (nb_reference_frames - 1) / (nb_frames - 1)
    return [min(nb_reference_frames - 1, round(f * scale)) for f in range(nb_frames)]


def _diff_frame(current, reference, frame_id, cells):
    position, rotations, scales = current
    ref_position, ref_rotations, ref_scales = reference
    if position != ref_position:
        cells[(ROW_POSITION, frame_id)] = CellDiff(
            position=tuple(a - b for a, b in zip(position, ref_position)))
    for bone, rotation in enumerate(rotations):
        if bone >= len(ref_rotations):
            cells[(bone, frame_id)] = CellDiff(new_bone=True)
            continue
        ref_rotation = ref_rotations[bone]
        scale = scales[bone] if scales and bone < len(scales) else NEUTRAL_SCALE
        ref_scale = ref_scales[bone] if ref_scales and bone < len(ref_scales) else NEUTRAL_SCALE
        if rotation == ref_rotation and scale == ref_scale:
            continue
        delta = tuple(wrap_rotation(a - b) for a, b in zip(rotation, ref_rotation))
        scale_delta = tuple(a - b for a, b in zip(scale, ref_scale))
        if any(delta) or any(scale_delta):
            cells[(bone, frame_id)] = CellDiff(rotation=delta, scale=scale_delta)


def diff_animation(anim_id: int, current: Optional[list], reference: Optional[list]) -> AnimationDiff:
    if current is None:
        return AnimationDiff(anim_id, STATUS_REMOVED, 0, len(reference or []))
    if reference is None:
        return AnimationDiff(anim_id, STATUS_NEW, len(current), 0)
    result = AnimationDiff(anim_id, STATUS_SAME, len(current), len(reference),
                           reference_frame_map(len(current), len(reference)))
    for frame_id, frame in enumerate(current):
        if frame_id < len(result.frame_map):
            reference_frame = reference[result.frame_map[frame_id]]
            if frame != reference_frame:
                _diff_frame(frame, reference_frame, frame_id, result.cells)
    if result.cells or len(current) != len(reference):
        result.status = STATUS_CHANGED
    return result


def diff_animations(current: list, reference: list) -> List[AnimationDiff]:
    """One AnimationDiff per animation id present in either snapshot."""
    return [diff_animation(anim_id,
                           current[anim_id] if anim_id < len(current) else None,
                           reference[anim_id] if anim_id < len(reference) else None)
            for anim_id in range(max(len(current), len(reference)))]
