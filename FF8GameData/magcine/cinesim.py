"""Static simulation of a GF cinematic script: who runs when.

Replays the engine's scheduler tick by tick (15 ticks per second in battle) without the game:
the bone order list, the three channels per bone with their waits, calls/returns, loop counters,
the shared sync flag word (op 0x05) and per-bone flags (0x10C/0x10D), bone spawns (0x32 & co)
and kills (0x00 on channel 0), plus the motion integrator for the generic write opcodes
(0x0A-0x17), so every bone gets a lifetime, an event list and its outPos/outAngle per tick.

What cannot be known without the battle is chosen, not guessed at random:
 - branches on battle state (targets, entities, stage) fall through, except 0xAE which iterates
   `target_count` targets;
 - random opcodes (0xA1 branch, 0xB0 wait, 0x12-0x17 random adds) draw from a seeded generator:
   the same seed replays the same run, another seed shows another possible run;
 - "wait until the file load / stream / texture is ready" opcodes are ready at once;
 - 0x140 (wait scaled by the battle slot) uses factor 1;
 - bone handlers other than 0/1 (polar, lerp, copy of another bone...) are not evaluated, those
   bones keep outPos = accumPos.
So the result is the vanilla choreography as the scripts describe it, a close approximation of
the game's timing - not a frame-exact replay.
"""
import random
import struct
from dataclasses import dataclass, field

from .cinescript import CineOpcodeTable, decode_instruction

WAIT_UNIT = 128          # default chanWaitSpeed: one tick
SKIP_SENTINEL = 0x7654   # generic write: leave this component unchanged

# Generic write opcodes: code -> (mode, field). Field: accum / vel8 / accel / vel16.
_GENERIC = {0x0A: ("set", "accum"), 0x0B: ("set", "vel8"), 0x0C: ("set", "accel"),
            0x0D: ("setall", "accum"), 0x0E: ("setall", "vel8"), 0x0F: ("setall", "accel"),
            0x10: ("add", "accum"), 0x11: ("set", "vel16"), 0x12: ("addrand", "accum"),
            0x13: ("addrand", "vel8"), 0x14: ("addrand", "accel"), 0x15: ("addrand", "vel16"),
            0x16: ("addrandall", "accum"), 0x17: ("addrandpair", "accum")}

# Opcodes worth showing as events on the timeline (code -> category).
EVENT_CATEGORIES = {
    0x39: "camera", 0x2D: "camera", 0x47: "camera",
    0x2B: "sound", 0x2C: "sound", 0xC3: "sound",
    0x3D: "draw", 0x43: "draw", 0x44: "draw", 0x4A: "draw", 0x4D: "draw", 0x54: "draw",
    0x58: "draw", 0x3F: "model", 0x89: "model",
    0x59: "particle",
    0x06: "file", 0x27: "file", 0x29: "file", 0xB6: "file", 0x96: "file", 0xDA: "file",
    0x65: "node", 0x66: "node", 0x67: "node", 0x69: "node", 0x6A: "node", 0xCB: "node",
    0x7A: "node", 0x84: "node", 0xC4: "node", 0x104: "node", 0x105: "node", 0x116: "node",
    0x07: "freeze", 0x93: "light", 0xC6: "fog", 0x11B: "fog",
    0x05: "flag", 0x10C: "flag", 0x01: "sequence",
}
_REPEATING = {"node"}  # re-run every tick by "keep node updated" loops: only the first one is kept


@dataclass
class SimEvent:
    tick: int
    offset: int
    code: int
    category: str
    text: str


@dataclass
class SimBone:
    index: int                     # spawn order (0 = root bone)
    spawn_tick: int
    program: int                   # file offset of its channel 0 script
    parent: int = -1               # index of the spawning bone
    spawned_at: int = -1           # offset of the spawning instruction
    bone_id: int = 0
    death_tick: int = -1           # -1 = still alive at the end
    channels: list = field(default_factory=lambda: [None, None, None])  # ip per channel
    waits: list = field(default_factory=lambda: [0, 0, 0])
    stacks: list = field(default_factory=lambda: [[], [], []])
    counters: list = field(default_factory=lambda: [0, 0, 0, 0])
    flags: int = 0                 # bone+0x4A flag word
    accum: list = field(default_factory=lambda: [0] * 6)   # rot xyz, pos xyz (16.16)
    vel: list = field(default_factory=lambda: [0] * 6)
    accel: list = field(default_factory=lambda: [0] * 6)
    draw: str = ""                 # last draw/model setup opcode name
    events: list = field(default_factory=list)
    track: list = field(default_factory=list)  # (tick, outAngle xyz, outPos xyz)
    visited: set = field(default_factory=set)  # instruction offsets executed

    @property
    def alive(self):
        return self.death_tick < 0

    def out(self):
        return tuple(_s16(a >> 16) for a in self.accum)


def _s16(value):
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def _s32(value):
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value


class CineSimulation:
    MAX_STEPS_PER_SLICE = 2000

    def __init__(self, data: bytes, root: int, max_ticks: int = 3000, target_count: int = 1,
                 table: CineOpcodeTable = None, track_motion: bool = True, seed: int = 0):
        self.data = data
        self.root = root
        self.table = table or CineOpcodeTable.default()
        self.max_ticks = max_ticks
        self.target_count = target_count
        self.track_motion = track_motion
        self.rng = random.Random(seed)
        self.bones = []
        self.order = []            # indices of live bones, in order-list order
        self.sync_flags = 0        # shared flag word (op 0x05)
        self.scene_counters = {}   # op 0xA7/0xA8
        self.target_index = 0
        self.tick = 0
        self.finished_tick = -1    # tick of op 0x01 (sequence end)
        self.warnings = []
        self._next_id = 0x8000
        self._cursor = 0           # position in the order list of the bone after the running one
        self._cache = {}
        self._run()

    # ------------------------------------------------------------------ helpers
    def _decode(self, offset):
        instruction = self._cache.get(offset)
        if instruction is None:
            instruction = decode_instruction(self.data, offset, self.table)
            self._cache[offset] = instruction
        return instruction

    def _spawn(self, parent, program, at, bone_id=None):
        bone = SimBone(len(self.bones), self.tick, program, parent.index if parent else -1, at)
        if parent is not None:
            bone.accum = list(parent.accum)
            bone.bone_id = self._next_id
            self._next_id += 1
        if bone_id is not None:
            bone.bone_id = bone_id
        bone.channels[0] = program
        self.bones.append(bone)
        self.order.append(bone.index)
        return bone

    def _find_bone(self, ref):
        ref &= 0xFFFF
        if ref >= 0xFFF0:
            return None  # relative references (self/parent) - not resolved
        for index in self.order:
            if self.bones[index].bone_id == ref:
                return self.bones[index]
        return None

    def _event(self, bone, instruction, category):
        if category in _REPEATING and any(e.code == instruction.code for e in bone.events):
            return
        from .cinescript import format_instruction
        bone.events.append(SimEvent(self.tick, instruction.offset, instruction.code, category,
                                    format_instruction(instruction)))

    # ------------------------------------------------------------------ main loop
    def _run(self):
        self._spawn(None, self.root, -1)
        while self.tick < self.max_ticks and self.order and self.finished_tick < 0:
            # The engine walks the live order list: a bone spawned this tick (appended) also runs
            # this tick, a killed bone is removed and the cursor steps back onto the next one.
            self._cursor = 0
            while self._cursor < len(self.order):
                bone = self.bones[self.order[self._cursor]]
                self._cursor += 1
                for channel in range(3):
                    if bone.channels[channel] is None or not bone.alive:
                        continue
                    if bone.waits[channel] > 0:
                        bone.waits[channel] -= WAIT_UNIT
                        continue
                    self._run_slice(bone, channel)
                if self.finished_tick >= 0:
                    break
            if self.track_motion:
                self._integrate()
            self.tick += 1

    def _integrate(self):
        for index in self.order:
            bone = self.bones[index]
            if not bone.alive:
                continue
            for i in range(6):
                if bone.accel[i]:
                    bone.vel[i] = _s32(bone.vel[i] + (bone.accel[i] << 12))
                bone.accum[i] = _s32(bone.accum[i] + bone.vel[i])
            if any(bone.vel) or not bone.track:
                bone.track.append((self.tick,) + bone.out())

    def _run_slice(self, bone, channel):
        ip = bone.channels[channel]
        for _ in range(self.MAX_STEPS_PER_SLICE):
            instruction = self._decode(ip)
            if instruction.error:
                self.warnings.append((self.tick, ip, instruction.error))
                bone.channels[channel] = None
                return
            bone.visited.add(ip)
            result = self._execute(bone, channel, instruction)
            if result is None:          # fall through
                ip += instruction.length
                continue
            kind, value = result
            if kind == "goto":
                ip = value
            elif kind == "wait":       # yield; value = ticks, ip_after = where to resume
                wait, resume = value
                bone.channels[channel] = resume
                bone.waits[channel] = max(0, (wait - 1) * WAIT_UNIT)
                return
            elif kind == "stop":
                bone.channels[channel] = None
                return
            elif kind == "kill":
                self._kill(bone)
                return
            elif kind == "finish":
                self.finished_tick = self.tick
                return
        self.warnings.append((self.tick, ip, "channel ran 2000 instructions without waiting"))
        bone.channels[channel] = None

    def _kill(self, bone):
        bone.death_tick = self.tick
        bone.channels = [None, None, None]
        if bone.index in self.order:
            if self.order.index(bone.index) < self._cursor:
                self._cursor -= 1
            self.order.remove(bone.index)
        if self.track_motion:
            bone.track.append((self.tick,) + bone.out())

    # ------------------------------------------------------------------ opcodes
    def _execute(self, bone, channel, ins):
        code, op, w, at = ins.code, ins.op, ins.words, ins.offset
        nxt = at + ins.length
        category = EVENT_CATEGORIES.get(code)
        if category and not (category == "flag" and (op >> 12) not in (0, 1)):
            self._event(bone, ins, category)
        if category in ("draw", "model"):
            bone.draw = ins.name

        if code == 0x00:
            return ("kill", None) if channel == 0 else ("stop", None)
        if code == 0x01:
            return ("finish", None)
        if code == 0x02:
            return ("goto", at + w[0])
        if code == 0x03:
            if len(bone.stacks[channel]) >= 2:
                self.warnings.append((self.tick, at, "call stack overflow (2 levels)"))
            bone.stacks[channel].append(nxt)
            return ("goto", at + w[0])
        if code == 0x04:
            if not bone.stacks[channel]:
                self.warnings.append((self.tick, at, "return without call"))
                return ("stop", None)
            return ("goto", bone.stacks[channel].pop())
        if code == 0x05:
            return self._flag_op(op >> 12, w, at, nxt, "sync")
        if code == 0x10C:
            return self._flag_op((op >> 12) & 0xF, w, at, nxt, bone)
        if code == 0x10D:
            other = self._find_bone(w[0])
            if other is not None and not (other.flags & w[1] & 0x3FFF):
                return ("wait", (1, at))
            return None
        if code == 0x09:
            ticks = op >> 9
            return ("wait", (ticks, nxt)) if ticks else None
        if code == 0xB0:
            ticks = self._rand(w[0])
            return ("wait", (ticks, nxt)) if ticks else None
        if code == 0x140:
            return ("wait", (w[0], nxt)) if w[0] > 0 else None
        if code == 0x1E:
            bone.counters[(op >> 14) & 3] = w[0] & 0xFF
            return None
        if code == 0x1F:
            index = (op >> 14) & 3
            bone.counters[index] = (bone.counters[index] - 1) & 0xFF
            return ("goto", at + w[0]) if bone.counters[index] else None
        if code == 0xA7:
            self.scene_counters[w[0]] = w[1] & 0xFF
            return None
        if code == 0xA8:
            value = (self.scene_counters.get(w[0], 0) - 1) & 0xFF
            self.scene_counters[w[0]] = value
            return ("goto", at + w[1]) if value else None
        if code == 0xAE:
            if self.target_index < self.target_count:
                self.target_index += 1
                return None
            return ("goto", at + w[0])
        if code == 0xA1:
            return ("goto", at + w[1]) if self.rng.randrange(256) <= w[0] else None
        if code in (0x26, 0x8B):
            wanted = w[0]
            slots = [wanted] if 1 <= wanted <= 2 else [1, 2]
            for slot in slots:
                if slot <= 2 and (wanted or bone.channels[slot] is None):
                    bone.channels[slot] = at + w[1]
                    bone.waits[slot] = 0
                    bone.stacks[slot] = []
                    break
            return None
        if code in (0x32, 0x9C):
            self._spawn(bone, at + w[0], at)
            return None
        if code == 0x135:
            self._spawn(bone, at + w[0], at, bone_id=w[1] & 0xFFFF)
            return None
        if code == 0x5D:
            for _ in range(self.target_count):
                self._spawn(bone, at + w[0], at)
            return None
        if code == 0x33:
            bone.bone_id = w[0] & 0xFFFF
            return None
        if code == 0x1D:
            if self._find_bone(w[0]) is not None:
                return ("wait", (1, at))
            return ("kill", None) if channel == 0 else ("stop", None)
        if code in _GENERIC and self.track_motion:
            self._generic_write(bone, code, op, w)
            return None
        return None

    def _rand(self, bound):
        """The engine's rand(n): 0..n-1 (sign of n kept), 0 for n == 0."""
        if not bound:
            return 0
        value = self.rng.randrange(abs(bound))
        return value if bound > 0 else -value

    def _flag_op(self, sub, w, at, nxt, target):
        flags = self.sync_flags if target == "sync" else target.flags
        mask = w[0] & 0xFFFF
        result = None
        if sub == 0:
            flags |= mask
        elif sub == 1:
            flags &= ~mask
        elif sub == 2:
            result = ("goto", at + w[1]) if flags & mask else None
        elif sub == 3:
            result = ("goto", at + w[1]) if not flags & mask else None
        elif sub == 4:
            result = ("wait", (1, at)) if flags & mask else None
        elif sub == 5:
            result = ("wait", (1, at)) if not flags & mask else None
        if target == "sync":
            self.sync_flags = flags & 0xFFFF
        else:
            target.flags = flags & 0xFFFF
        return result

    def _generic_write(self, bone, code, op, w):
        mode, fld = _GENERIC[code]
        mask = (op >> 10) & 0x3F
        components = [i for i in range(6) if mask & (0x20 >> i)]
        values = list(w)
        if mode in ("setall", "addrandall"):
            value = values[0] if mode == "setall" else self._rand(values[0])
            values = [value] * len(components)
        elif mode == "addrand":
            values = [self._rand(v) for v in values]
        elif mode == "addrandpair":
            # base +- rand(spread): the sign of the spread word picks a negative base
            values = [(-values[2 * i] if values[2 * i + 1] < 0 else values[2 * i]) + self._rand(values[2 * i + 1])
                      for i in range(len(components))]
        for component, value in zip(components, values):
            if value == SKIP_SENTINEL and mode in ("set", "add"):
                continue
            add = mode.startswith("add")
            if fld == "accum":
                target, raw = bone.accum, value << 16
            elif fld == "vel8":
                target, raw = bone.vel, value << 8
            elif fld == "vel16":
                target, raw = bone.vel, value << 16
            else:
                target, raw = bone.accel, (value << 4) if add else (value >> 4)
            target[component] = _s32(target[component] + raw) if add else _s32(raw)


def root_program_offset(data: bytes) -> int:
    return struct.unpack_from("<I", data, 4)[0]
