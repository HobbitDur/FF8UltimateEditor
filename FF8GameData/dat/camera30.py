"""Convert battle camera data to real 30 fps, for FFNx True30FPS.

With 30 fps on, FFNx runs the battle camera (the keyframe player ProcessCameraAnimation 0x5035E0
and the camera script VM BS_UpdateCameraSequence 0x509610) on every 30 Hz host frame and expects
EVERY camera source to be converted - there is no marker, nothing in a converted file tells it
apart (study D:/FFNxMenu30fps/gf_study/DAT30FPS_STUDY.md section 3, user decision "expect 30 fps
camera everywhere"). One function set here serves every tool:

- the bare keyframe collections: monster .dat section 6, character dXc section 5 (Ifrit);
- the camera tracks {header, script, collection}: battle stage a0stgXXX.x (Alexander), r0win.dat
  section 2 (Watts), the 221 effect tracks of the exe and their FFNx effect_NNN.bcam files, the
  camera of a GF cinematic MAGxxx_B.00 (Fujin).

KEYFRAMES (FF8GameData.dat.cameracollection). Each keyframe's u16 duration counts battle ticks:
BS_Camera_ReadAnimation 0x503C70 adds 16*duration per keyframe into a signed 16-bit time line,
ProcessCameraAnimation adds 16 per call (0x503A7C). Bit 15 of the word ends the block, so a
duration is at most 0x7FFF. Conversion: every duration x factor (2 for 30 fps, 4 for 60 fps).
Easing (0x503FE0), FOV/roll and the natural spline (0x50D010/0x50D060/0x50D240) only read the
normalised time (current << 12) / total, so the curves keep their shape exactly. Limit: the
block total 16*sum(duration) must stay a positive int16 that the +16 step can reach without
wrapping, sum(duration) <= 2047 per block (vanilla max 300 in the exe tracks, 85 in c0m).
A block over it is refused, never clamped.

CAMERA SCRIPT VM (CameraSeq_DispatchActionOpcode 0x509810 + computeAnimationSequence 0x50DB40),
classification of every op code for timing (IDA, 2026-10-28):

    00 XX   play keyframe animation XX          - unchanged: its length is in the collection
    01      yield to the next tick              - a tick: see below
    02      end and clear the script            - unchanged
    03      capture the return view             - unchanged (an event)
    04 XX   CameraSeq04_ReturnViewEaseTask 0x509930: an AnimSeq-queue task, u8 counter +1 per
            tick, Battle_Camera_ReturnViewBlend = sin((t << 10) / XX), ends when t >= XX: XX is
            a duration in ticks -> XX x factor (u8: refused over 255). Never used in vanilla.
    05 XX   play the animation whose id is variable XX - unchanged
    06 07   set / clear camera flag 0x8000      - unchanged
    08      stop the shot, snap to the return view (blend 4096 at once) - unchanged
    09 XX   no operation                        - unchanged
    other < C0: the default case = 08 + end and clear - unchanged
    C0-F3   the shared arithmetic and jumps     - unchanged (no tick of their own)
    reads (CameraSeq_ReadSpecialVar_C3 0x509640): 0-7 camera variables, 0x10 shot flag
            (g_BattleCam_ScriptShotActive), 0x11 random, 0x13/0x1B party counts, 0x15 target
            camera category, 0x16 target status, 0x17 action count, 0x18/0x19 attacker/target
            slot, 0x1A affected targets, 0x1C-0x22 random % 2..8, 0x23 witch-fight stage
            (sub_50E4E0), > 0x77 the stack: no timer anywhere.

01 is the only tick op code. In a loop that polls the shot flag (C3 0x10) it waits for the shot to
end, and the shot is twice as long once its keyframes are converted: the wait doubles by itself,
nothing to change. Anywhere else (a straight-line wait, a loop counting ticks in a variable) it
waits one tick, which is half the time at 30 Hz: it becomes `01` x factor (the exact vanilla
timing; jumps keep landing on the first one). Vanilla corpus (163 stages, r0win, 221 exe tracks,
46 MAG tracks): 01 only in shot-flag loops, 04 never - every vanilla script converts unchanged
and every converted track keeps its size.

Idempotency: nothing marks a converted file. looks_converted() is a cheap guess for a WARNING
only (every keyframe duration a multiple of the factor, which vanilla collections seldom are).
"""
import struct
from dataclasses import dataclass, field

from .cameracollection import parse_camera_collection
from .camerascriptsteps import CameraScriptInfo, ScriptStep, read_steps, script_bytes
from .sequencecommand import get_jump_target, is_jump, iter_command

FACTOR_30FPS = 2
MAX_BLOCK_TICKS = 2047        # 16 * 2047 = 32752: the last int16 the +16 step reaches exactly
MAX_DURATION = 0x7FFF         # bit 15 of the duration word ends the block
MAX_EASE_TICKS = 0xFF         # 04 XX: XX is a byte

OP_PLAY = 0x00
OP_WAIT = 0x01
OP_EASE = 0x04
SHOT_FLAG_VARIABLE = 0x10
# value op codes whose operand is a variable id (C3 set, C7 add, CB sub ... E3 mod)
_VARIABLE_OPERAND_OPS = frozenset(range(0xC3, 0xE4, 4))


class CameraConversionError(ValueError):
    """The camera cannot be converted (nothing was changed)."""


@dataclass
class CameraConversionReport:
    nb_keyframe: int = 0           # keyframe durations multiplied (each stored keyframe once)
    nb_block: int = 0
    max_block_ticks: int = 0       # longest block once converted, in ticks
    nb_ease: int = 0               # 04 XX operands multiplied
    nb_wait_doubled: int = 0       # 01 repeated (a one-tick wait)
    nb_shot_wait: int = 0          # 01 kept (it waits for a shot to end)
    size_before: int = 0
    size_after: int = 0
    warning_list: list = field(default_factory=list)

    def merge(self, other: "CameraConversionReport"):
        for name in ("nb_keyframe", "nb_block", "nb_ease", "nb_wait_doubled", "nb_shot_wait",
                     "size_before", "size_after"):
            setattr(self, name, getattr(self, name) + getattr(other, name))
        self.max_block_ticks = max(self.max_block_ticks, other.max_block_ticks)
        self.warning_list.extend(other.warning_list)

    def summary(self) -> str:
        text = f"{self.nb_keyframe} keyframe(s) in {self.nb_block} block(s), longest {self.max_block_ticks} ticks"
        if self.nb_ease or self.nb_wait_doubled or self.nb_shot_wait:
            text += (f"; script: {self.nb_ease} ease(s), {self.nb_wait_doubled} wait(s) repeated, "
                     f"{self.nb_shot_wait} shot wait(s) kept")
        return text


def _check_factor(factor: int):
    if factor not in (2, 4):
        raise CameraConversionError(f"factor {factor}: only 2 (30 fps) and 4 (60 fps) are supported")


# ---------------------------------------------------------------------------- keyframes
def _unique_blocks(collection):
    """Every stored block once (slots may share an animation): [(set, slot, block index, block)]."""
    seen, blocks = set(), []
    for camera_set in collection.sets:
        for animation in camera_set.animations:
            if animation.empty:
                continue
            for block_index, block in enumerate(animation.blocks):
                if block.offset in seen:
                    continue
                seen.add(block.offset)
                blocks.append((camera_set.index, animation.slot, block_index, block))
    return blocks


def collection_problem_list(collection, factor: int) -> list:
    """Why the collection cannot be converted (empty list: it can)."""
    problems = []
    for set_index, slot, block_index, block in _unique_blocks(collection):
        durations = [frame.duration.get() for frame in block.frames]
        total = sum(durations) * factor
        if total > MAX_BLOCK_TICKS:
            problems.append(f"set {set_index} slot {slot} block {block_index}: {sum(durations)} ticks, "
                            f"{total} once converted (a block holds at most {MAX_BLOCK_TICKS})")
        elif any(duration * factor > MAX_DURATION for duration in durations):
            problems.append(f"set {set_index} slot {slot} block {block_index}: a keyframe longer than "
                            f"{MAX_DURATION} ticks once converted")
    return problems


def convert_collection(collection, factor: int = FACTOR_30FPS, report: CameraConversionReport = None):
    """Multiply every keyframe duration of a parsed CameraCollection, in place (its bytes are
    patched; the size never changes). All or nothing: CameraConversionError, nothing changed."""
    _check_factor(factor)
    report = report if report is not None else CameraConversionReport()
    if collection.is_empty():
        return report
    problems = collection_problem_list(collection, factor)
    if problems:
        raise CameraConversionError("; ".join(problems))
    seen_frame = set()
    for _set_index, _slot, _block_index, block in _unique_blocks(collection):
        report.nb_block += 1
        total = 0
        for frame in block.frames:
            value = frame.duration.get() * factor
            total += value
            if frame.offset not in seen_frame:   # a frame shared by two blocks is stored once
                seen_frame.add(frame.offset)
                frame.duration.set(value)
                report.nb_keyframe += 1
        report.max_block_ticks = max(report.max_block_ticks, total)
    return report


def convert_collection_bytes(data, factor: int = FACTOR_30FPS, report: CameraConversionReport = None) -> bytes:
    """A bare collection (monster section 6, character section 5) converted. Empty data (a
    model with no camera) comes back as it is."""
    if len(data) < 6:
        return bytes(data)
    collection = parse_camera_collection(bytes(data))
    convert_collection(collection, factor, report)
    return bytes(collection.get_bytes())


def collection_looks_converted(collection, factor: int = FACTOR_30FPS) -> bool:
    """A guess, for a warning only: every non-zero keyframe duration is a multiple of the factor
    (at least 4 of them, so a tiny collection says nothing)."""
    if collection is None or collection.is_empty():
        return False
    durations = [frame.duration.get() for _s, _a, _b, block in _unique_blocks(collection)
                 for frame in block.frames if frame.duration.get()]
    return len(durations) >= 4 and all(duration % factor == 0 for duration in durations)


# ---------------------------------------------------------------------------- script
@dataclass
class ScriptCommandTiming:
    address: int
    op_code: int
    parameters: bytes
    timing: str           # "unchanged", "ease x factor", "wait: shot", "wait: tick"


def _loop_ranges(command_list):
    """(first address, jump address) of every backward jump (a loop) of the script."""
    loops = []
    for address, op_code, parameters in command_list:
        if is_jump(op_code):
            target = get_jump_target(address, op_code, parameters)
            if target <= address:
                loops.append((target, address))
    return loops


def _reads_shot_flag(command_list, first, last) -> bool:
    return any(first <= address <= last and op_code in _VARIABLE_OPERAND_OPS
               and parameters and parameters[0] == SHOT_FLAG_VARIABLE
               for address, op_code, parameters in command_list)


def _command_list(vm, script: bytes) -> list:
    command_list = []
    for address, op_code, parameters in iter_command(vm, bytes(script)):
        if parameters is None:
            raise CameraConversionError(f"unknown op code 0x{op_code:02X} at {address}: the script "
                                        "cannot be read past it")
        command_list.append((address, op_code, bytes(parameters)))
    return command_list


def classify_script(vm, script: bytes) -> list:
    """[ScriptCommandTiming] of every command: what a conversion does to it."""
    command_list = _command_list(vm, script)
    loops = _loop_ranges(command_list)
    result = []
    for address, op_code, parameters in command_list:
        timing = "unchanged"
        if op_code == OP_EASE:
            timing = "ease x factor"
        elif op_code == OP_WAIT:
            shot = any(first <= address <= last and _reads_shot_flag(command_list, first, last)
                       for first, last in loops)
            timing = "wait: shot" if shot else "wait: tick"
        result.append(ScriptCommandTiming(address, op_code, parameters, timing))
    return result


def convert_script(vm, script: bytes, factor: int = FACTOR_30FPS,
                   report: CameraConversionReport = None) -> bytes:
    """The camera script converted (see the module doc). Same bytes when nothing ticks, same
    size when only 04 operands change; a one-tick 01 is repeated, the jumps relinked."""
    _check_factor(factor)
    report = report if report is not None else CameraConversionReport()
    timing_list = classify_script(vm, script)
    data = bytearray(script)
    tick_wait_list = []
    for command in timing_list:
        if command.timing == "ease x factor":
            ticks = command.parameters[0] * factor
            if ticks > MAX_EASE_TICKS:
                raise CameraConversionError(f"04 {command.parameters[0]} at {command.address}: the return-view "
                                            f"ease would last {ticks} ticks (a byte holds at most 255)")
            data[command.address + 1] = ticks
            report.nb_ease += 1
        elif command.timing == "wait: shot":
            report.nb_shot_wait += 1
        elif command.timing == "wait: tick":
            tick_wait_list.append(command.address)
    if not tick_wait_list:
        return bytes(data)
    script_json = getattr(vm, "script_json", None)
    if not script_json:
        raise CameraConversionError("the camera script needs a wait repeated, which needs camera_script.json "
                                    "(GameData.load_camera_sequence_data)")
    info = CameraScriptInfo(script_json)
    steps = read_steps(vm, info, bytes(data))
    address_of_step = {}
    for address_command, step in zip(_command_list(vm, bytes(data)), steps):
        address_of_step[id(step)] = address_command[0]
    new_steps = []
    for step in steps:
        new_steps.append(step)
        if address_of_step.get(id(step)) in tick_wait_list:
            new_steps.extend(ScriptStep("wait", OP_WAIT) for _ in range(factor - 1))
            report.nb_wait_doubled += 1
    return script_bytes(info, new_steps)


# ---------------------------------------------------------------------------- whole track
def convert_track(vm, track, factor: int = FACTOR_30FPS, report: CameraConversionReport = None):
    """Convert a CameraTrack (FF8GameData.dat.cameratrack) in place: its script and its keyframes.
    All or nothing: CameraConversionError and the track as it was."""
    report = report if report is not None else CameraConversionReport()
    local = CameraConversionReport()
    before = track.to_bytes()
    local.size_before = len(before)
    new_script = convert_script(vm, track.script, factor, local)
    collection = parse_camera_collection(bytes(track.collection.get_bytes()))
    convert_collection(collection, factor, local)
    if new_script != track.script:
        if len(new_script) <= track.exe_script_size:
            # keep the track's room: fill after the last command like the script editor does
            filler = track.exe_script_size - len(new_script)
            new_script = new_script + b"\x01" * (filler % 2) + b"\x09\x00" * (filler // 2)
        track.script = new_script
    track.collection = collection
    local.size_after = len(track.to_bytes())
    report.merge(local)
    return report


def convert_track_bytes(vm, data: bytes, factor: int = FACTOR_30FPS,
                        report: CameraConversionReport = None) -> bytes:
    """A whole camera track (header + script + keyframes) converted. Same size for every vanilla
    track; a script that needed a wait repeated grows."""
    from .cameratrack import CameraTrack
    track = CameraTrack.from_bytes(vm, bytes(data))
    convert_track(vm, track, factor, report)
    return track.to_bytes()


def track_looks_converted(track, factor: int = FACTOR_30FPS) -> bool:
    return collection_looks_converted(track.collection, factor)


def track_bytes_look_converted(vm, data: bytes, factor: int = FACTOR_30FPS) -> bool:
    from .cameratrack import read_track_parts
    try:
        collection = read_track_parts(vm, bytes(data))[3]
    except (ValueError, struct.error):
        return False
    return collection_looks_converted(collection, factor)
