"""Static simulation of a GF cinematic script: who runs when.

Replays the engine's scheduler tick by tick (15 ticks per second in battle) without the game:
the bone order list, the three channels per bone with their waits, calls/returns, loop counters,
the shared sync flag word (op 0x05) and per-bone flags (0x10C/0x10D), bone spawns (0x32 & co)
and kills (0x00 on channel 0), plus the motion integrator for the generic write opcodes
(0x0A-0x17), so every bone gets a lifetime, an event list and its outPos/outAngle per tick.

What cannot be known without the battle is chosen, not guessed at random:
 - branches on battle state (targets, entities, stage) fall through, except 0xAE which iterates
   `target_count` targets; ctx->flags (0x9E/0x9F/0xA0) is 0 as the summon setup leaves it;
 - random opcodes (0xA1 branch, 0xB0 wait, 0x12-0x17 random adds) draw from a seeded generator:
   the same seed replays the same run, another seed shows another possible run;
 - "wait until the file load / stream / texture is ready" opcodes are ready at once;
 - 0x140 (wait scaled by the battle slot) uses factor 1;
 - bone handlers 0/1 (outPos = accumulator), 3 (polar around a bone), 5 (copy a bone), 6 (lerp
   between two bones) and 7 (a bone + accumulator) are evaluated; the others keep outPos;
 - opcodes reading the battle (entity positions, joints, targets' size) leave the bone unmoved.
So the result is the vanilla choreography as the scripts describe it, a close approximation of
the game's timing - not a frame-exact replay.
"""
import math
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
# Opcodes other than the generic writes that change a bone's motion (handled by _motion_op).
_MOTION_OPS = {0x2F, 0x37, 0x61, 0x62, 0x91, 0x82, 0xC0, 0x87, 0xAC, 0xB9, 0xD2, 0x7C, 0x117,
               0x1A, 0xA4, 0xCC, 0xF2, 0x110}
ROOT_ANGLES = (256, 768, 0)  # g_GfCinematic_RootAngleX/Y/Z set by SetupSectionPtrs
NODE_BUILDERS = {0x65, 0x66, 0x67, 0x69, 0x6A, 0xCB, 0x7A, 0x84, 0xC4, 0x104, 0x105, 0x116}
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
    parent_id: int = 0             # bone+0x14: id of the spawning bone
    grandparent_id: int = 0        # bone+0x16: that bone's +0x14
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
    props: list = field(default_factory=list)  # (tick, key, value): draw handler, mesh, node...
    handler: int = 0               # bone handler id (+0x18): how accumPos becomes outPos
    handler_words: tuple = ()      # its parameter block (op 0x1A), bone refs for handlers 5/6/7
    handler_ref: int = 0           # +0xB0 reference bone (handler 3, ops 0xA4/0xCC)
    out_pos: list = field(default_factory=lambda: [0, 0, 0])

    @property
    def alive(self):
        return self.death_tick < 0

    def out(self):
        """(outAngle xyz, outPos xyz) - outPos as the bone handler derived it."""
        return tuple(_s16(a >> 16) for a in self.accum[:3]) + tuple(self.out_pos)

    def prop(self, key, tick, default=None):
        """Value of a property (see CineSimulation._record_props) as it was at `tick`."""
        value = default
        for when, name, item in self.props:
            if when > tick:
                break
            if name == key:
                value = item
        return value


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
        self.ctx_flags = 0         # ctx->flags (ops 0x9E/0x9F/0xA0): 0 in battle
        self.scene_counters = {}   # op 0xA7/0xA8
        self.target_index = 0
        self.tick = 0
        self.finished_tick = -1    # tick of op 0x01 (sequence end)
        self.warnings = []
        # For the 3D scene: per tick, every live bone's (outAngle xyz, outPos xyz), and the battle
        # camera written by op 0x39 sub-op 0 (eye bone index, look-at bone index, projection, roll).
        self.frames = []
        self.cameras = {}
        # VRAM uploads in execution order, for CineVram: (tick, "tex"/"clut", (id,)),
        # (tick, "raw", (texture RECT id, file slot, byte offset)), (tick, "rawrect", (RECT, file slot))
        self.vram_events = []
        self._last_load = None     # file slot of the last streamed load (op 0x06)
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
            # the engine also copies handlerId and the +0xB0..+0xB7 handler words
            bone.handler, bone.handler_words, bone.handler_ref = parent.handler, parent.handler_words, parent.handler_ref
            bone.out_pos = list(parent.out_pos)
            bone.parent_id = parent.bone_id
            bone.grandparent_id = parent.parent_id
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
                self.frames.append({index: self.bones[index].out() for index in self.order})
            self.tick += 1

    def _integrate(self):
        for index in self.order:
            bone = self.bones[index]
            if not bone.alive:
                continue
            self._integrate_bone(bone)

    def _apply_handler(self, bone):
        """BoneHandlerTable[handler]: outPos from the accumulators (0xB262E0.. in the Ifrit module)."""
        accum = [_s16(a >> 16) for a in bone.accum[3:]]
        handler = bone.handler
        if handler in (3, 5, 6, 7):
            words = bone.handler_words
            if handler == 3:
                ref = self.resolve_ref(bone, bone.handler_ref)
                angle = (bone.accum[5] >> 16) * 2 * math.pi / 4096
                radius = bone.accum[3] / 65536.0
                bone.out_pos = [_s16(ref.out_pos[0] + int(math.sin(angle) * radius)),
                                _s16(ref.out_pos[1] + accum[1]),
                                _s16(ref.out_pos[2] + int(math.cos(angle) * radius))]
            elif handler == 5 and words:
                bone.out_pos = list(self.resolve_ref(bone, words[0]).out_pos)
            elif handler == 6 and len(words) >= 2:
                a, b = self.resolve_ref(bone, words[0]), self.resolve_ref(bone, words[1])
                ratios = [r >> 16 for r in bone.accum[:3]]
                bone.out_pos = [_s16(int(ratios[i] * (b.out_pos[i] - a.out_pos[i]) / 256) + a.out_pos[i] + accum[i])
                                for i in range(3)]
            elif handler == 7 and words:
                ref = self.resolve_ref(bone, words[0])
                bone.out_pos = [_s16(ref.out_pos[i] + accum[i]) for i in range(3)]
            return
        if handler in (0, 1, 9):
            bone.out_pos = accum
        # 2, 4, 8, 10, 11: outPos left untouched

    def _integrate_bone(self, bone):
        for i in range(6):
            if bone.accel[i]:
                bone.vel[i] = _s32(bone.vel[i] + (bone.accel[i] << 12))
            bone.accum[i] = _s32(bone.accum[i] + bone.vel[i])
        self._apply_handler(bone)
        if any(bone.vel) or bone.handler in (3, 5, 6, 7) or not bone.track:
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
        self._record_props(bone, ins)

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
        if code in (0x9E, 0x9F, 0xA0):                # ctx->flags: cleared by the summon setup
            bit = 0x2000 if code == 0xA0 else 0x8000   # (MAG_201_sub_B25820) and never set by a script
            taken = bool(self.ctx_flags & bit) == (code == 0x9F)
            return ("goto", at + w[0]) if taken else None
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
            self._apply_handler(bone)
            return None
        if code in _MOTION_OPS and self.track_motion:
            self._motion_op(bone, code, op, w)
            self._apply_handler(bone)
            return None
        return None

    def _motion_op(self, bone, code, op, w):
        """Opcodes that move a bone other than the generic writes (see gf_cinematic_opcodes.json)."""
        if code == 0x2F:                                   # StopMotion
            bone.vel, bone.accel = [0] * 6, [0] * 6
        elif code == 0x37:                                 # ResetAccum
            bone.accum = [0] * 6
        elif code in (0x61, 0x62):                         # Copy accum (op word 0x0061 exactly) / vel
            source = self.resolve_ref(bone, w[1])
            field_name = "accum" if op == 0x0061 else "vel"
            for i in range(6):
                if w[0] & (1 << i):
                    getattr(bone, field_name)[i] = getattr(source, field_name)[i]
        elif code == 0x91:                                 # accum = another bone's outputs
            source = self.resolve_ref(bone, w[1])
            outputs = source.out()
            for i in range(6):
                if w[0] & (1 << i):
                    bone.accum[i] = outputs[i] << 16
        elif code in (0x82, 0xC0):                         # move onto a bone in N ticks
            target = self.resolve_ref(bone, w[0]) if code == 0x82 else (self._bone_with_id(bone.parent_id) or self.bones[0])
            frames = (w[1] if code == 0x82 else w[0]) or 1
            for i in range(3, 6):
                bone.vel[i] = _s32(int((target.accum[i] - bone.accum[i]) / frames))
        elif code == 0x87:                                 # scale toward the origin over N ticks
            frames = w[1] or 1
            for i in range(6):
                if (op >> 10) & (0x20 >> i):
                    bone.vel[i] = _s32(int(((bone.accum[i] >> 16) * (w[0] - 256) << 8) / frames))
        elif code == 0xAC:                                 # accelerate to reach a target in N ticks
            frames = w[0] or 1
            mask = (op >> 10) & 0x3F
            if op & 0x200:
                values = iter(w[1:])
                targets = {i: next(values, 0) << 16 for i in range(6) if mask & (0x20 >> i)}
            else:
                other = self.resolve_ref(bone, w[1])
                targets = {i: other.accum[i] for i in range(6) if mask & (0x20 >> i)}
            for i, target in targets.items():
                gap = target - bone.accum[i] - frames * bone.vel[i]
                bone.accel[i] = max(-32768, min(32767, int(2 * gap / (frames * (frames + 1)) / 4096)))
        elif code in (0xB9, 0xD2):                         # negate one motion value
            index = w[0]
            if (code == 0xD2 or index > 0) and 0 <= index < 12:
                block = bone.accum if index < 6 else bone.vel
                block[index % 6] = _s32(-block[index % 6])
        elif code == 0x7C:                                 # random point on an ellipse (XZ)
            angle = self.rng.randrange(4096) * 2 * math.pi / 4096
            bone.accum[5] = _s32(bone.accum[5] + int((w[0] + self._rand(w[1])) * math.cos(angle) * 65536))
            bone.accum[3] = _s32(bone.accum[3] + int((w[2] + self._rand(w[3])) * math.sin(angle) * 65536))
        elif code == 0x117:                                # rotation relative to the root angles
            for i, root in enumerate(ROOT_ANGLES):
                bone.accum[i] = _s32((w[i] - root) << 16)
        elif code == 0x1A:                                 # bone handler + parameter block
            bone.handler, bone.handler_words = (w[0] >> 8) & 0xFF, tuple(w[1:])
        elif code == 0xA4:                                 # bone handler + reference bone
            bone.handler, bone.handler_ref = w[0] & 0xFF, w[1] & 0xFFFF
            if bone.handler == 3:                          # convert to polar around the reference
                ref = self.resolve_ref(bone, bone.handler_ref)
                dx, dz = bone.out_pos[0] - ref.out_pos[0], bone.out_pos[2] - ref.out_pos[2]
                bone.accum[5] = int(math.atan2(dx, dz) * 4096 / (2 * math.pi)) << 16
                bone.accum[3] = int(math.hypot(dx, dz)) << 16
                bone.accum[4] = (bone.out_pos[1] - ref.out_pos[1]) << 16
        elif code == 0xCC:                                 # handler 7 relative to a bone
            bone.handler, bone.handler_words = 7, (w[0],)
        elif code == 0xF2:                                 # bake outPos, back to handler 0
            bone.accum[3:] = [v << 16 for v in bone.out_pos]
            bone.handler = 0
        elif code == 0x110:                                # midpoint of two bones
            a, b = self.resolve_ref(bone, w[0]), self.resolve_ref(bone, w[1])
            bone.handler = a.handler
            for i in range(3, 6):
                bone.accum[i] = _s32((a.accum[i] + b.accum[i]) // 2)

    def _rand(self, bound):
        """The engine's rand(n): 0..n-1 (sign of n kept), 0 for n == 0."""
        if not bound:
            return 0
        value = self.rng.randrange(abs(bound))
        return value if bound > 0 else -value

    def _record_props(self, bone, ins):
        """What the 3D scene needs to know about a bone, with the tick it changed:
        draw (draw handler id), mesh / model (object ids), node (the node-builder instruction the
        bone runs: code, op, words), parent (parentNodeId ref of op 0x68), handler (bone handler)."""
        code, op, w = ins.code, ins.op, ins.words
        record = lambda key, value: bone.props.append((self.tick, key, value))
        if code == 0x3D:
            record("draw", w[0] & 0xFF)
            record("mesh", w[1] & 0xFFFF)
        elif code == 0x4A:
            record("draw", op >> 9)
            record("mesh", w[0] & 0xFFFF)
        elif code == 0x54:
            record("draw", 1)
            record("mesh", w[0] & 0xFFFF)
        elif code in (0x43, 0x44):
            record("draw", w[0] & 0xFF)
        elif code == 0x4D:
            record("draw", 4)
        elif code == 0x58:
            record("draw", 6)
        elif code == 0x3F:
            record("draw", 3)
            record("model", (w[0] & 0xFF, (w[0] >> 8) & 0xFF))
        elif code == 0xD0:
            record("hidden", True)
        elif code == 0xEB:
            record("hidden", False)
        elif code == 0x68:
            parent = self.resolve_ref(bone, w[0])
            record("parent", parent.index if parent is not bone else -1)
        elif code == 0x1A:
            record("handler", (w[0] >> 8) & 0xFF)
        elif code in NODE_BUILDERS:
            # node builders run every tick: record only a change of builder
            if bone.prop("node", self.tick, (None,))[0] != code:
                refs = ()
                if code == 0x69:
                    refs = (self.resolve_ref(bone, w[1]).index,)
                elif code == 0x7A:
                    refs = (self.resolve_ref(bone, w[0]).index if w[0] else -1,)
                elif code == 0xCB:
                    refs = tuple(self.resolve_ref(bone, r).index if r else bone.index for r in w[:2])
                record("node", (code, op, tuple(w), refs))
        elif code in (0x52, 0x78, 0x92, 0x23):
            record("tex_op", (code, op, tuple(w)))   # texture page / CLUT / uv of the bone's meshes
        elif code == 0x06:
            slot = (op >> 9) & 0x3F
            if not (op & 0x8000 and slot & 0x20):    # (a shared MA8DEF_P file otherwise)
                self._last_load = slot
        elif code in (0x27, 0x28, 0x29):
            self._record_upload(code, op, w)
        elif code == 0x39 and op >> 12 == 0:
            target = self.resolve_ref(bone, w[0])
            self.cameras[self.tick] = (bone.index, target.index if target else -1)

    def _record_upload(self, code, op, w):
        events = self.vram_events
        if code == 0x27:
            events += [(self.tick, "tex", (w[0],)), (self.tick, "clut", (w[0],))]
        elif code == 0x28:
            events.append((self.tick, "clut", (w[0],)))
        elif op & 0x8000:                             # raw pages of the last streamed file
            events.append((self.tick, "raw", (w[0], self._last_load, 0)))
        elif op & 0x4000:                             # file slot + n x 4 KB
            events.append((self.tick, "raw", (w[0], w[1] & 0x7F, (w[2] & 0xFFFF) << 12)))
        elif op & 0x2000:                             # inline RECT
            events.append((self.tick, "rawrect", (tuple(w[:4]), self._last_load)))
        else:
            events.append((self.tick, "tex", (w[0],)))

    def resolve_ref(self, bone, ref):
        """The engine's bone reference (GfCinematic_GetRotationVector 0xB65370): an id, 0x4000|n =
        the bone's battle slot + n, 0xFFFF = the spawner, 0xFFFE its spawner, 0xFFFD / 0xFFFC one
        and two levels higher; not found = the root bone."""
        ref &= 0xFFFF
        if ref >= 0xFFF0:
            level = (~ref) & 3
            if level == 0:
                wanted = bone.parent_id
            elif level == 1:
                wanted = bone.grandparent_id
            else:
                holder = self._bone_with_id(bone.grandparent_id)
                if holder is None:
                    return self.bones[0]
                wanted = holder.parent_id if level == 2 else holder.grandparent_id
        elif ref & 0x4000:
            wanted = ref & 0x3FFF  # battle slot + n: the slot is unknown here, take n
        else:
            wanted = ref
        return self._bone_with_id(wanted) or self.bones[0]

    def _bone_with_id(self, bone_id):
        for index in self.order:
            if self.bones[index].bone_id == bone_id:
                return self.bones[index]
        return None

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
