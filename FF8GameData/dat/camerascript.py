"""Run a battle camera script (camera_sequence_info.json) to find which keyframe animation it plays.

A camera track (spell/attack effect, battle stage, r0win.dat) starts with a byte-code script that
BS_UpdateCameraSequence (EN 0x509610) runs each frame. It computes an animation index from the
battle state - the opening shot, the attacker and target slots, the target's status and camera
category, random values... (CameraSeq_ReadSpecialVar_C3, EN 0x509640) - and plays it with 00/05.
The animation index picks set (index >> 4) & 15, slot index & 7 of the track's collection
(BS_GetCameraAnimationPointer).

This module reproduces that run from inputs a preview lets the user set (CameraScriptInputs), so
a preview films what the game would. The arithmetic and jumps are the shared VM's
(computeAnimationSequence), like FF8GameData.dat.sequencebake for the entity VM. Effect tracks
never loop across frames: they run to 01/02 in their first frame, so one run is the whole script.

A battle stage's script does wait across frames (run_camera_script_frames): 01 ends the frame and
the next frame goes on after it, 02 ends the script for good. Every stage plays the intro byte
(variable 0), waits while the shot flag (C3 0x10) says a shot is playing, then saves the view the
shot ended on as the battle's return view (03) and ends (BS_CameraInit 0x500F70 installs it at the
battle start; nothing runs it again).
"""
from dataclasses import dataclass, field

from .sequencebake import _c_div, _c_mod
from .sequencecommand import get_jump_target, iter_command

MAX_STEPS = 10000  # an endless loop inside one frame (jump to itself) stops here
MAX_FRAMES = 3000  # a script still waiting after this many frames (200 s at 15 fps) is cut there

# CURRENT_CAMERA_ANIMATION[0] as cameraWhenDoingAction (EN 0x506190) leaves it for the effect's
# script: the character's opening shot (0-5), 8 for a monster's Magic, -1 when no opening shot
# played (on-model targeting, or a command without one).
OPENING_NONE = -1
OPENING_MONSTER_MAGIC = 8

# C3 0x16 reads the target's animation status (EntityAnimationFlagStatus, low byte)
STATUS_LOW_HEALTH = 0x01   # also set for a character with Poison/Sleep/Curse; cleared for a monster
STATUS_DEAD = 0x02


def camera_category_value(category: int) -> int:
    """cameraDataRelated from section 7 byte 246 (initAnimationSequenceAtStartBattle); C3 0x15
    reads it from the target. Characters always have 0."""
    if category & 8:
        return 5
    if category & 4:
        return 4
    return (3 - category) & 0xFF


def animation_index_parts(index: int):
    """(set, slot) of an animation index, as BS_GetCameraAnimationPointer decodes it (bit 3 unused)."""
    return (index >> 4) & 0xF, index & 7


def camera_animation_at(collection, index: int):
    """The CameraAnimation an index plays in a collection, or None (no such set, empty slot)."""
    set_index, slot = animation_index_parts(index)
    if collection is None or set_index >= len(collection.sets):
        return None
    animation = collection.sets[set_index].animations[slot]
    return None if animation.empty else animation


@dataclass
class CameraScriptInputs:
    """The battle state a camera script reads (C3 ids in the comments)."""
    opening: int = 0              # 0x00 camera variable 0: the opening shot (see OPENING_*)
    attacker_slot: int = 0        # 0x18 (party 0-2, monsters 3-10)
    target_slot: int = 3          # 0x19
    target_status: int = 0        # 0x16 low byte of the target's animation status
    target_category: int = 0      # 0x15 the target's cameraDataRelated (camera_category_value)
    action_count: int = 0         # 0x17 the action's count minus 1
    affected_targets: int = 1     # 0x1A
    random: int = 0               # 0x11, and 0x1C-0x22 use it modulo 2..8
    party_alive: int = 3          # 0x13 party members alive
    party_ok: int = 3             # 0x1B party members with no animation status
    shot_flag: int = 0            # 0x10 g_BattleCam_ScriptShotActive (low byte)
    value_23: int = 0             # 0x23 sub_50E4E0
    variables: dict = field(default_factory=dict)  # camera variables 1-7 and the stack (>0x77)


@dataclass
class CameraScriptRun:
    played: list = field(default_factory=list)   # animation indexes played, in order
    reads: list = field(default_factory=list)    # [(C3 id, value)] each id once, first read
    events: list = field(default_factory=list)   # other camera commands met (wobble, return...)
    stop_reason: str = ""
    steps: int = 0

    @property
    def chosen(self):
        """The animation the camera ends up playing (the last one started), or None."""
        return self.played[-1] if self.played else None


def _int16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


class _CameraScriptRunner:
    def __init__(self, inputs: CameraScriptInputs):
        self.inputs = inputs
        self.variables = {index: 0 for index in range(8)}
        self.variables.update(inputs.variables)
        self.variables[0] = _int16(inputs.opening)
        self.shot_flag = inputs.shot_flag & 0xFF
        self.run = CameraScriptRun()

    def read(self, parameter: int) -> int:
        value = self._read(parameter)
        if all(read_id != parameter for read_id, _value in self.run.reads):
            self.run.reads.append((parameter, value))
        return value

    def _read(self, parameter: int) -> int:
        inputs = self.inputs
        if parameter < 8 or parameter > 0x77:  # camera variables, the camera stack: words
            return _int16(self.variables.get(parameter, 0))
        if 0x1C <= parameter <= 0x22:
            return (inputs.random & 0x7FFF) % (parameter - 26)
        value = {0x10: self.shot_flag, 0x11: inputs.random, 0x13: inputs.party_alive,
                 0x15: inputs.target_category, 0x16: inputs.target_status,
                 0x17: inputs.action_count, 0x18: inputs.attacker_slot, 0x19: inputs.target_slot,
                 0x1A: inputs.affected_targets, 0x1B: inputs.party_ok,
                 0x23: inputs.value_23}.get(parameter, parameter - 16)  # the reader's default
        return value & 0xFF  # returned in AL

    def write(self, parameter: int, value: int):
        if parameter == 0x10:
            self.shot_flag = value & 0xFF
        elif parameter < 8 or parameter > 0x77:
            self.variables[parameter] = _int16(value)

    def execute(self, vm, script: bytes, max_steps=MAX_STEPS, address=0, waits=False) -> CameraScriptRun:
        """Run from `address`. `waits`: run one frame of a script that waits across frames - 01 stops
        it at the next command (self.resume), a shot played sets its bit of the shot flag as
        BS_GetCameraAnimationPointer does."""
        commands = {}
        order = []
        for command_address, op_code, parameters in iter_command(vm, bytes(script)):
            commands[command_address] = (op_code, None if parameters is None else bytes(parameters))
            order.append(command_address)
        next_address = {command_address: (order[i + 1] if i + 1 < len(order) else len(script))
                        for i, command_address in enumerate(order)}
        run, current = self.run, 0
        self.resume = None
        while True:
            if run.steps >= max_steps:
                run.stop_reason = "endless loop (stopped after %d commands)" % max_steps
                return run
            if address not in commands:
                run.stop_reason = ("runs past the end of the script" if address >= len(script)
                                   else f"jumps into the middle of a command (offset {address})")
                return run
            run.steps += 1
            op_code, parameters = commands[address]
            following = next_address[address]
            if parameters is None:
                run.stop_reason = f"unknown op code 0x{op_code:02X}: ends the script"
                return run
            if op_code < 0xC0:
                if op_code in (0x00, 0x05):
                    index = parameters[0] if op_code == 0x00 else self.read(parameters[0]) & 0xFF
                    run.played.append(index)
                    if waits and self.shot_length(index) > 0:   # no shot starts for a missing set
                        self.shot_flag |= 1 << (index & 7)
                elif op_code == 0x01:
                    if waits:
                        self.resume = following
                        run.stop_reason = "end: waits for the next frame"
                        return run
                    run.stop_reason = "end: the camera script stops"
                    return run
                elif op_code == 0x02:
                    run.stop_reason = "end_clear: the camera script stops"
                    return run
                elif op_code == 0x03:
                    run.events.append("capture_return: saves the current view as the return view")
                elif op_code == 0x04:
                    run.events.append(f"wobble({parameters[0]}): eases back to the return view over {parameters[0]} frames")
                elif op_code == 0x08:
                    self.shot_flag = 0
                    run.events.append("return_view: blends back to the return view")
                elif op_code not in (0x06, 0x07, 0x09):
                    run.stop_reason = f"op code 0x{op_code:02X}: ends the script"
                    return run
                address = following
                continue
            if op_code == 0xE4:
                run.stop_reason = "E4 never advances: the game hangs here"
                return run
            if op_code == 0xE5:
                self.write(parameters[0], current)
                address = following
                continue
            if op_code >= 0xE6:
                condition = (op_code - 0xE6) % 7
                taken = (condition == 0 or (condition == 1 and current > 0)
                         or (condition == 2 and current >= 0) or (condition == 3 and current == 0)
                         or (condition == 4 and current != 0) or (condition == 5 and current <= 0)
                         or (condition == 6 and current < 0))
                address = get_jump_target(address, op_code, parameters) if taken else following
                continue
            case = op_code & 3
            if case == 0:
                value = int.from_bytes(parameters[:2], "little", signed=True)
            elif case == 1:
                value = int.from_bytes(parameters[:1], "little", signed=True)
            elif case == 2:
                value = parameters[0]
            else:
                value = self.read(parameters[0])
            operation = op_code & 0xFC
            if operation == 0xC0:
                current = value
            elif operation == 0xC4:
                current += value
            elif operation == 0xC8:
                current -= value
            elif operation == 0xCC:
                current *= value
            elif operation == 0xD0:
                current = _c_div(current, value)
            elif operation == 0xD4:
                current &= value
            elif operation == 0xD8:
                current |= value
            elif operation == 0xDC:
                current ^= value
            elif operation == 0xE0:
                current = _c_mod(current, value)
            address = following


def run_camera_script(vm, script: bytes, inputs: CameraScriptInputs = None,
                      max_steps=MAX_STEPS) -> CameraScriptRun:
    """Run one camera script (camera VM from sequencevm.camera_sequence_vm) with the given battle
    state. The result tells which animation indexes it played and what it read to decide."""
    return _CameraScriptRunner(inputs or CameraScriptInputs()).execute(vm, script, max_steps)


@dataclass
class CameraScriptTimeline:
    shots: list = field(default_factory=list)    # [(frame, animation index)] in the order played
    events: list = field(default_factory=list)   # [(frame, text)] other camera commands
    stop_reason: str = ""
    frames: int = 0                              # frames the script ran


def run_camera_script_frames(vm, script: bytes, inputs: CameraScriptInputs = None, shot_length=None,
                             max_frames=MAX_FRAMES) -> CameraScriptTimeline:
    """Run a script that waits across frames (a battle stage's), one run per frame as
    BS_UpdateCameraSequence does. shot_length(index) is how many frames an animation plays (0: none
    plays, e.g. a set the collection does not have); its bit of the shot flag stays set that long."""
    runner = _CameraScriptRunner(inputs or CameraScriptInputs())
    shot_length = runner.shot_length = shot_length or (lambda _index: 0)
    timeline, address, ends = CameraScriptTimeline(), 0, {}
    for frame in range(max_frames):
        runner.shot_flag = 0
        for bit, end in ends.items():
            if frame < end:
                runner.shot_flag |= bit
        played, events = len(runner.run.played), len(runner.run.events)
        run = runner.execute(vm, script, address=address, waits=True)
        for index in run.played[played:]:
            timeline.shots.append((frame, index))
            ends[1 << (index & 7)] = frame + shot_length(index)
        timeline.events += [(frame, text) for text in run.events[events:]]
        timeline.frames = frame + 1
        if runner.resume is None:
            timeline.stop_reason = run.stop_reason
            return timeline
        address = runner.resume
    timeline.stop_reason = f"still running after {max_frames} frames"
    return timeline
