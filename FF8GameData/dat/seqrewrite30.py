"""Rewrite an entity's animation sequences (monster section 5, weapon section 4, Edea
section 6, reduced weapon section 2) for a model converted to real 30 fps.

Why: once a battle model is converted to 30 fps, FFNx (True30FPS) runs its sequence VM on
every 30 Hz host frame instead of every 15 Hz battle tick, and every animation has exactly
2n frames for the n it had (an n-frame animation holds the VM for n ticks, FF8_EN.exe
AnimSeq_UpdateEntityPerFrame @0x504290). Everything the byte-code counts in animation frames
then doubles on its own (`C3 0A` countdowns, `d * C3 09 / C3 0A` moves). Everything it counts
in TICKS has to be doubled by hand, and every per-tick step halved, so the sequence keeps
its wall-clock timing. Study: D:/FFNxMenu30fps/gf_study/DAT30FPS_STUDY.md section 2.

The rules (study 2.2 / 2.4), each one tagged in the report under the RULE_* name:

- B9 N waits exactly N ticks (0x504C5D): N x2, over several B9 when 2N > 255 (B9 0 = 256).
- BA (one extra frame advance, 0x5051D2): one vanilla frame = two converted frames -> BA BA.
- A straight-line A1 (a one-tick yield outside any loop) -> A1 A1.
- Task durations 84 (wobble), 9E (move to target), AD/AE (drag target), and the cumulative
  tick stamps of 9F: x2. 96, 99/B1, 81, A6 and A8 run hardcoded 15-tick tasks that FFNx keeps
  at 15 Hz: their data is left alone. AB (Renzokuken) is handled by an FFNx hook on
  getAnimationFrameCount: the AB list (up to its A1) is left alone too.
- Tick loops (a backward jump around an A1/A9 yield), by where their counter comes from:
    * from the animation (`C3 0A`): nothing to do, it doubles with the frames;
    * from a literal: the literal x2, the per-tick steps of anything the loop accumulates /2
      (an odd step is rounded half a unit per tick: reported), the constants that live in the
      counter's unit (a `k - counter` ratio: k + N, a divisor: x2);
    * an endless per-tick loop, or one ended by a position: accumulators /2;
    * polling an external flag (effect handshake): nothing (level flag, polled twice);
    * any other or unknown counter origin: the FALLBACK, every A1 of the loop doubled - the
      loop keeps the vanilla 15 Hz cadence exactly, its motion is stepped.
  Events fired from inside a smooth loop (sound, hit effect, texture step...) would fire on
  every 30 Hz tick, twice as often: each one is gated on the counter's parity
  (`C3 ctr D6 01 E9/EA skip`) so it fires once per vanilla tick, on the first 30 Hz tick of the
  pair. An event already guarded by a frame-index test (below) fires once and is not gated.
- Frame-index literals: `C3 09` reads the frames read so far (pose index + 1). A vanilla
  value c is reached at 30 Hz as 2c-1 at the same instant: an equality test literal c -> 2c-1,
  an offset or a threshold added to a frame value -> 2c.
- Frame parity / modulo tests (soldier family, `C3 09 D5 m ... C1 r CB`): the mask
  m = 2^j - 1 -> 2m + 1, a modulo M -> 2M, the residue r -> (2r - 1) mod the new modulus. The
  test then holds exactly on the first 30 Hz tick of each vanilla frame it held on.
- Background sequences (9A, re-run from their first byte every tick, 0x5042B5): the whole
  body is gated on a toggle (`C3 v DD 01 E5 v E9 -> the A1`) in a 0x78-0x7F variable that no
  sequence of the file uses, so it runs on every other 30 Hz tick: exactly the vanilla 15 Hz
  cadence (texture steps, sprite counters, blink timers).

What the rewriter cannot settle is reported, never guessed: SequenceReport.manual_list
says why, and the caller shows it as a manual decision.

Verification: tests/dat30_verifier.py bakes the original at 15 Hz (n-frame animations) and
the rewrite at 30 Hz (2n-frame animations) with the sequence interpreter, in three battle
contexts, and compares wall time, event order and motion (tests/test_seq_rewrite30.py runs
it over every vanilla sequence).
"""
from .sequencecommand import is_jump
from .sequencerelink import (SequenceNode, SequenceRelinkError, parse_node_list,
                             assemble_node_list)

STATUS_UNCHANGED = "unchanged"   # nothing in it counts ticks: correct as it is
STATUS_REWRITTEN = "rewritten"   # rewritten with the smooth rules only
STATUS_FALLBACK = "fallback"     # at least one loop kept at 15 Hz cadence (A1 A1)
STATUS_MANUAL = "manual"         # something could not be settled: see manual_list
STATUS_REFUSED = "refused"       # the sequence cannot be parsed for editing: left untouched

RULE_B9 = "B9 wait x2"
RULE_B9_SPLIT = "B9 wait x2, split over several B9"
RULE_BA = "BA doubled"
RULE_STRAIGHT_A1 = "straight A1 doubled"
RULE_DURATION = "task duration x2 (84/9E/AD/AE)"
RULE_9F = "9F tick stamps x2"
RULE_LITERAL_COUNTER = "loop counter from a literal x2"
RULE_SECONDARY_COUNTER = "secondary loop counter x2"
RULE_COUNTER_CONSTANT = "counter-typed constant (ratio)"
RULE_STEP_HALF = "per-tick step /2"
RULE_ODD_STEP = "odd per-tick step rounded"
RULE_EVENT_GATE = "per-tick event gated on counter parity"
RULE_FRAME_INDEX = "frame-index literal"
RULE_FRAME_PARITY = "frame parity / modulo"
RULE_FALLBACK = "loop kept at 15 Hz cadence (A1 A1 fallback)"
RULE_BACKGROUND = "background sequence gated to 15 Hz"
RULE_FRAME_LOOP = "loop counted from the animation (nothing to do)"
RULE_POLL = "loop polling an external flag (nothing to do)"
RULE_ENDLESS = "endless per-tick loop"
RULE_POSITION_LOOP = "loop ended by a position (steps /2)"

# Variables (C3 reads / E5 writes) by what they hold, study 2.3.
_LOCAL = frozenset(range(0x00, 0x08)) | frozenset(range(0x78, 0x100))
_FRAME = frozenset((0x09, 0x0A))
_EXTERNAL = frozenset((0x08, 0x0B, 0x18, 0x19, 0x1A, 0x1B, 0x1C, 0x1F, 0x22, 0x23, 0x28, 0x29,
                       0x2E, 0x33, 0x37))
_POSITION = frozenset((0x0D, 0x0E, 0x0F, 0x12, 0x13, 0x17, 0x24, 0x25, 0x26, 0x27, 0x2C, 0x2D,
                       0x30, 0x31, 0x32, 0x34))
_SCRATCH_BANK = range(0x78, 0x80)   # persistent per-entity scratch (main bank / bg bank)

# Action op codes whose effect is an event (fired once each time they run).
_EVENT_OPS = frozenset((0x80, 0x81, 0x84, 0x91, 0x93, 0x96, 0x97, 0x98, 0x99, 0x9B, 0xA5, 0xA6,
                        0xA8, 0xAA, 0xAF, 0xB0, 0xB1, 0xB2, 0xB4, 0xB5, 0xB6, 0xB7, 0xB8, 0xBB,
                        0xBD, 0xBF))
_TICK_YIELD = frozenset((0xA1, 0xA9))
_A1 = 0xA1
_AB = 0xAB
_B9 = 0xB9
_BA = 0xBA
_JUMP_ALWAYS = (0xE6, 0xED)
_JUMP_IF_ZERO = 0xE9      # int8 form; jumps when current value == 0
_JUMP_IF_NOT_ZERO = 0xEA  # int8 form; jumps when current value != 0
_JUMP_EQUALITY = frozenset((0xE9, 0xEA, 0xF0, 0xF1))
_LOAD_CONST = (0xC0, 0xC1, 0xC2)
_ADD_CONST = (0xC4, 0xC5, 0xC6)
_SUB_CONST = (0xC8, 0xC9, 0xCA)
_DIV_CONST = (0xD0, 0xD1, 0xD2)
_AND_CONST = (0xD4, 0xD5, 0xD6)
_MOD_CONST = (0xE0, 0xE1, 0xE2)
_WRITE = 0xE5
_READ = 0xC3

# Op code families of the arithmetic VM (computeAnimationSequence @0x50DB40): the high bits
# are the operation, the two low bits the operand (0 = i16, 1 = i8, 2 = u8, 3 = variable).
_OPERATION_LOAD = 0xC0
_OPERATION_ADD = 0xC4
_OPERATION_SUB = 0xC8
_OPERATION_DIV = 0xD0


class SequenceReport:
    """What the rewrite did to one sequence, and what it could not settle."""

    def __init__(self, seq_id=None):
        self.seq_id = seq_id
        self.status = STATUS_UNCHANGED
        self.rule_set = set()
        self.note_list = []          # readable, one line per notable edit (odd steps...)
        self.manual_list = []        # why the sequence needs a manual decision
        self.odd_step_list = []      # (offset in the original, step, rounded step)
        self.fallback_list = []      # (loop start offset, loop end offset, reason)
        self.is_background = False

    def __repr__(self):
        return (f"SequenceReport(seq {self.seq_id}, {self.status}, rules={sorted(self.rule_set)}, "
                f"manual={self.manual_list})")


class _Value:
    """Abstract value of the VM accumulator at one point of a linear walk: `base` var (None for
    a constant) + `delta`, the set of variables it was computed from, and whether anything
    else (mul, div, mask...) went into it."""
    __slots__ = ("base", "delta", "source", "complex")

    def __init__(self, base=None, delta=0, source=frozenset(), complex_=False):
        self.base, self.delta, self.source, self.complex = base, delta, source, complex_

    def all_source(self):
        return set(self.source) | ({self.base} if self.base is not None else set())


def _operand(node):
    """('var', id) or ('const', value) of an arithmetic node."""
    case = node.op_code & 3
    if case == 3:
        return "var", node.parameters[0]
    if case == 0:
        return "const", int.from_bytes(node.parameters[:2], "little", signed=True)
    if case == 1:
        return "const", int.from_bytes(node.parameters[:1], "little", signed=True)
    return "const", node.parameters[0]


def _set_constant(node, value):
    """Write a new literal into an arithmetic node, widening it to i16 when needed."""
    value = int(value)
    case = node.op_code & 3
    if case == 1 and not -128 <= value <= 127:
        case = 0
    elif case == 2 and not 0 <= value <= 255:
        case = 0
    if not -32768 <= value <= 32767:
        raise SequenceRelinkError(f"constant {value} does not fit in 16 bits")
    node.op_code = (node.op_code & 0xFC) | case
    if case == 0:
        node.parameters = bytearray(value.to_bytes(2, "little", signed=True))
    elif case == 1:
        node.parameters = bytearray(value.to_bytes(1, "little", signed=True))
    else:
        node.parameters = bytearray([value])


def _is_arithmetic(op_code):
    return op_code is not None and 0xC0 <= op_code <= 0xE3


def _half_step(step):
    """A per-tick step halved; an odd one rounds away from zero (half a unit per tick)."""
    if step % 2 == 0:
        return step // 2
    return (step + (1 if step > 0 else -1)) // 2


class _Rewriter:
    def __init__(self, vm, data, seq_id, report):
        self.vm = vm
        self.report = report
        self.node_list, self.end = parse_node_list(vm, data)
        self.index_of = {id(node): index for index, node in enumerate(self.node_list)}
        self.ab_data = self._ab_data_set()
        self.state_list = self._dataflow()
        self.loop_list = self._loop_list()
        self.constant_edit = {}      # id(node) -> (node, new value)
        self.double_after = set()    # id(node): emit a copy right after it (A1, BA)
        self.gate_list = []          # (event node, counter var, fire on parity 0/1)
        self.guarded_event = self._frame_guarded_event_set()

    # ---------------------------------------------------------------- analysis
    def _ab_data_set(self):
        """The commands of an AB list (anim ids, A0 bucket separators, up to the A1 that
        ends it) are data the AB handler consumes (0x504E5B), not commands: never edited."""
        data_set = set()
        inside = False
        for node in self.node_list:
            if inside:
                data_set.add(id(node))
                if node.op_code == _A1:
                    inside = False
            elif node.op_code == _AB:
                inside = True
        return data_set

    def _dataflow(self):
        """Linear abstract walk: the accumulator value BEFORE each node (control flow ignored,
        good enough for the straight bodies the corpus loops are made of)."""
        local_source = {}
        value = _Value()
        state_list = []
        for node in self.node_list:
            state_list.append(value)
            op_code = node.op_code
            if _is_arithmetic(op_code):
                kind, operand = _operand(node)
                operation = op_code & 0xFC
                operand_source = frozenset()
                if kind == "var":
                    operand_source = frozenset([operand]) | local_source.get(operand, frozenset())
                if operation == _OPERATION_LOAD:
                    value = (_Value(None, operand) if kind == "const"
                             else _Value(operand, 0, operand_source))
                elif operation in (_OPERATION_ADD, _OPERATION_SUB) and kind == "const":
                    delta = operand if operation == _OPERATION_ADD else -operand
                    value = _Value(value.base, value.delta + delta, value.source, value.complex)
                else:
                    value = _Value(value.base, value.delta, value.source | operand_source, True)
            elif op_code == _WRITE:
                var = node.parameters[0]
                source = set(value.all_source())
                if value.base is not None and value.base != var:
                    source |= local_source.get(value.base, frozenset())
                source |= set().union(*[local_source.get(v, frozenset()) for v in value.source]) \
                    if value.source else set()
                source.discard(var)
                local_source[var] = frozenset(source)
        self.local_source = local_source
        return state_list

    def _loop_list(self):
        """(first index, last index) of every backward jump."""
        loop_list = []
        for index, node in enumerate(self.node_list):
            if node.target is not None and node.target is not self.end:
                target_index = self.index_of[id(node.target)]
                if target_index <= index:
                    loop_list.append((target_index, index))
        return loop_list

    def _frame_derived(self, var_set):
        return any(v in _FRAME or (self.local_source_frame.get(v, False)) for v in var_set)

    def _frame_guarded_event_set(self):
        """Events skipped by a conditional forward jump whose condition comes from the frame
        index (`C3 09` tests): they fire on chosen frames only, already once per vanilla tick
        after the frame-index rules, so the counter parity gate must not touch them."""
        # which locals hold a frame-derived value (transitively)
        frame_local = {}
        for node, state in zip(self.node_list, self.state_list):
            if node.op_code == _WRITE:
                frame_local[node.parameters[0]] = bool(
                    state.all_source() & _FRAME
                    or any(frame_local.get(v, False) for v in state.all_source()))
        self.local_source_frame = frame_local
        guarded = set()
        for index, node in enumerate(self.node_list):
            # only an equality test picks single ticks; a window (<, <=...) still fires on
            # every tick inside it and is gated like any per-tick event
            if node.op_code not in _JUMP_EQUALITY or node.target is self.end:
                continue
            target_index = self.index_of[id(node.target)]
            if target_index <= index:
                continue
            state = self.state_list[index]
            if not self._frame_derived(state.all_source()):
                continue
            for inner in self.node_list[index + 1:target_index]:
                if inner.op_code in _EVENT_OPS:
                    guarded.add(id(inner))
        return guarded

    def _writes(self, first, last):
        """(index, var, state) of every E5 between first and last (inclusive)."""
        return [(index, self.node_list[index].parameters[0], self.state_list[index])
                for index in range(first, last + 1) if self.node_list[index].op_code == _WRITE]

    def _constant_feeding(self, write_index, low=0):
        """The C0/C1/C2 load nearest before a write (the literal it stores)."""
        index = write_index - 1
        while index >= low and self.node_list[index].op_code not in _LOAD_CONST:
            index -= 1
        return index if index >= low else None

    # ---------------------------------------------------------------- rules
    def _edit_constant(self, node, value):
        self.constant_edit[id(node)] = (node, value)

    def _frame_constants(self):
        """Literals that live in animation frames.

        Two kinds of frame values: the frame INDEX (`C3 09`, frames read so far) and frame
        COUNTS (`C3 0A`, the total, and what is computed from it). At 30 Hz an index c of
        vanilla is reached as 2c-1 at the same instant, a count n is 2n. So:
        - a literal compared with an index: k -> 2k-1 (`c == k`, `c < k`, `c <= k` all keep
          their exact tick);
        - an offset added to a count: k -> 2k; and when that count is then compared with an
          index (a window `total/2 + k > c`), the -1 of the index rule goes into the offset:
          + k -> 2k-1, - k -> 2k+1;
        - an index masked with 2^j-1 or taken modulo M (parity tests): mask -> 2m+1,
          modulo -> 2M, the residue r -> (2r-1) mod the new modulus;
        - (d * index) / k, a frame count written as a literal: k -> 2k.
        """
        frame_local = {}     # var -> "index" | "count" | "scaled" | ("residue", modulus)
        current = None
        const_node = None
        offset_node = None   # last count offset of the current expression: (node, sign)
        for index, node in enumerate(self.node_list):
            op_code = node.op_code
            if id(node) in self.ab_data:
                continue
            if op_code == _READ:
                var = node.parameters[0]
                current = ("index" if var == 0x09 else "count" if var == 0x0A
                           else frame_local.get(var))
                const_node, offset_node = None, None
            elif op_code in _LOAD_CONST:
                current, const_node, offset_node = None, node, None
            elif op_code in _AND_CONST or op_code in _MOD_CONST:
                if current == "index":
                    _, value = _operand(node)
                    if op_code in _AND_CONST:
                        if value <= 0 or value & (value + 1):
                            self.report.manual_list.append(
                                f"frame index masked with {value} at offset {node.origin}: "
                                f"not a 2^j-1 mask")
                            current = None
                            continue
                        new_value, modulus = 2 * value + 1, 2 * (value + 1)
                    else:
                        if value <= 0:
                            current = None
                            continue
                        new_value, modulus = 2 * value, 2 * value
                    self._edit_constant(node, new_value)
                    self.report.rule_set.add(RULE_FRAME_PARITY)
                    current = ("residue", modulus)
                elif current is not None:
                    self.report.manual_list.append(f"frame value {current} masked/modulo at "
                                                   f"offset {node.origin}")
                    current = None
                const_node = None
            elif op_code in _ADD_CONST + _SUB_CONST:
                _, value = _operand(node)
                if current == "count" and not self._is_self_update(index):
                    self._edit_constant(node, 2 * value)
                    offset_node = (node, 1 if op_code in _ADD_CONST else -1)
                    self.report.rule_set.add(RULE_FRAME_INDEX)
                elif current == "index" and not self._is_self_update(index):
                    # index + k compared later: same-instant mapping of the sum (2(c+k)-1)
                    self._edit_constant(node, 2 * value)
                    self.report.rule_set.add(RULE_FRAME_INDEX)
                elif isinstance(current, tuple):
                    self._edit_constant(node, (2 * value - 1) % current[1])
                    self.report.rule_set.add(RULE_FRAME_PARITY)
                const_node = None
            elif op_code in (_OPERATION_ADD | 3, _OPERATION_SUB | 3):   # C7 / CB: +/- var
                var = node.parameters[0]
                kind_of_var = ("index" if var == 0x09 else "count" if var == 0x0A
                               else frame_local.get(var))
                if kind_of_var is not None and const_node is not None and current is None:
                    _, value = _operand(const_node)
                    if isinstance(kind_of_var, tuple):
                        self._edit_constant(const_node, (2 * value - 1) % kind_of_var[1])
                        self.report.rule_set.add(RULE_FRAME_PARITY)
                    elif kind_of_var == "index":
                        self._edit_constant(const_node, 2 * value - 1)
                        self.report.rule_set.add(RULE_FRAME_INDEX)
                    elif kind_of_var == "count":
                        self._edit_constant(const_node, 2 * value)
                        self.report.rule_set.add(RULE_FRAME_INDEX)
                    current = kind_of_var
                elif (kind_of_var == "index" and current == "count" and offset_node is not None
                      and op_code == (_OPERATION_SUB | 3)):
                    offset, sign = offset_node
                    _, value = _operand(offset)
                    self._edit_constant(offset, 2 * value - 1 if sign > 0 else 2 * value + 1)
                    current = None
                elif kind_of_var is not None and current is None:
                    current = kind_of_var
                const_node, offset_node = None, None
            elif op_code in (_OPERATION_DIV | 3,):   # x / frame: a ratio, no longer a frame
                var = node.parameters[0]
                if var in _FRAME or frame_local.get(var) in ("index", "count", "scaled"):
                    current = None
                const_node = None
            elif op_code == 0xCF:   # x * frame: proportional to the frame (d * C3 09)
                var = node.parameters[0]
                if var == 0x09 or frame_local.get(var) == "index":
                    current = "scaled"
                const_node = None
            elif op_code in _DIV_CONST and current == "scaled":
                # (d * C3 09) / k: k is a frame count written as a literal -> 2k
                _, value = _operand(node)
                self._edit_constant(node, 2 * value)
                self.report.rule_set.add(RULE_FRAME_INDEX)
                current, const_node = None, None
            elif _is_arithmetic(op_code):
                const_node = None
            elif op_code == _WRITE:
                frame_local[node.parameters[0]] = current

    def _next_jump_or_write(self, index):
        for node in self.node_list[index + 1:]:
            if node.is_jump() or node.op_code == _WRITE:
                return node
        return None

    def _is_self_update(self, index):
        """`C3 v ADD k E5 v`: a variable stepped by a constant (a counter), not a frame
        offset."""
        if index == 0 or self.node_list[index - 1].op_code != _READ:
            return False
        var = self.node_list[index - 1].parameters[0]
        following = self._next_jump_or_write(index)
        return (following is not None and following.op_code == _WRITE
                and following.parameters[0] == var)

    def _counter_constants(self, first, last, counter, nb_tick):
        """Inside a literal-counted loop, constants in the counter's unit.

        The doubled counter is twice the vanilla one at the same instant (c'(2i) = 2 c(i)), so
        a constant compared or combined with it doubles too: `k - counter` -> 2k, `counter - k`
        -> 2k, a divisor of a counter-derived value -> 2k. One exception keeps the ratio idiom
        `(N + 1 - counter) / N` exact at its END (it reaches 1 on the last tick): when k is
        within one of the counter's start N, k -> k + N, i.e. the +1 offset is not doubled.
        """
        typed = {counter}
        counter_value, const_node = False, None
        for index in range(first, last + 1):
            node = self.node_list[index]
            op_code = node.op_code
            if op_code == _READ:
                counter_value, const_node = node.parameters[0] in typed, None
            elif op_code in _LOAD_CONST:
                counter_value, const_node = False, node
            elif op_code in (0xC7, 0xCB):
                if node.parameters[0] in typed:
                    if const_node is not None and not counter_value:
                        _, value = _operand(const_node)
                        self._edit_constant(const_node, value + nb_tick if abs(value - nb_tick) <= 1
                                            else 2 * value)
                        self.report.rule_set.add(RULE_COUNTER_CONSTANT)
                    counter_value = True
                const_node = None
            elif op_code in _ADD_CONST + _SUB_CONST and counter_value:
                following = self._next_jump_or_write(index)
                if (following is not None and following.is_jump()
                        and not self._is_self_update(index)):
                    _, value = _operand(node)
                    self._edit_constant(node, 2 * value)
                    self.report.rule_set.add(RULE_COUNTER_CONSTANT)
                const_node = None
            elif op_code in _DIV_CONST and counter_value:
                _, value = _operand(node)
                self._edit_constant(node, 2 * value)
                self.report.rule_set.add(RULE_COUNTER_CONSTANT)
                counter_value = False
            elif op_code in _MOD_CONST + _AND_CONST and counter_value:
                # every M-th tick: c' = 2c on the first tick of the pair, so c' % 2M == 2r
                # holds there and never on the second (odd) one
                _, value = _operand(node)
                if op_code in _AND_CONST and (value <= 0 or value & (value + 1)):
                    self.report.manual_list.append(f"counter masked with {value} at offset "
                                                   f"{node.origin}: not a 2^j-1 mask")
                else:
                    self._edit_constant(node, 2 * value if op_code in _MOD_CONST else 2 * value + 1)
                    self.report.rule_set.add(RULE_COUNTER_CONSTANT)
                const_node = None
            elif op_code in (0xCF, 0xD3):
                if node.parameters[0] in typed:
                    counter_value = True
                const_node = None
            elif op_code == _WRITE:
                if counter_value:
                    typed.add(node.parameters[0])
                elif node.parameters[0] in typed and node.parameters[0] != counter:
                    typed.discard(node.parameters[0])
            elif _is_arithmetic(op_code):
                const_node = None

    def _counter_parity_at(self, first, event_index, counter, init_parity):
        """Parity of the counter when the event runs on the first iteration."""
        if init_parity is None:
            return None
        parity = init_parity
        for index, var, state in self._writes(first, event_index - 1):
            if var == counter and state.base == counter and not state.complex:
                parity = (parity + state.delta) % 2
        return parity

    def _rewrite_loops(self):
        tick_loop_list = []
        for first, last in self.loop_list:
            ops = {node.op_code for node in self.node_list[first:last + 1]
                   if id(node) not in self.ab_data}
            if ops & _TICK_YIELD:
                tick_loop_list.append((first, last))
        for first, last in tick_loop_list:
            # A loop around another tick loop is judged on its OWN commands only: the inner
            # loop's counter, A1 and events are the inner loop's business.
            inner = set()
            for other in tick_loop_list:
                if other != (first, last) and first <= other[0] and other[1] <= last:
                    inner.update(range(other[0], other[1] + 1))
            own = [index for index in range(first, last + 1)
                   if index not in inner and id(self.node_list[index]) not in self.ab_data]
            for index in range(first, last + 1):
                self.in_tick_loop.add(id(self.node_list[index]))
            own_ops = {self.node_list[index].op_code for index in own}
            if not own_ops & _TICK_YIELD and not inner:
                continue
            mode, counter, init_parity = self._classify_loop(first, last, own, own_ops)
            if mode == "fallback":
                for index in own:
                    if self.node_list[index].op_code == _A1:
                        self.double_after.add(id(self.node_list[index]))
                continue
            if mode is None:
                continue
            # smooth: halve the accumulated steps, gate the per-tick events
            for index, var, state in self.loop_accumulator:
                self._halve_step(first, index, state.delta)
            if counter is not None:
                for index in own:
                    node = self.node_list[index]
                    if node.op_code in _EVENT_OPS and id(node) not in self.guarded_event:
                        parity = self._counter_parity_at(first, index, counter, init_parity)
                        self.gate_list.append((node, counter, parity))
                        self.report.rule_set.add(RULE_EVENT_GATE)

    def _halve_step(self, first, write_index, step):
        index = write_index - 1
        while index >= first and self.node_list[index].op_code not in _ADD_CONST + _SUB_CONST:
            index -= 1
        if index < first:
            return
        node = self.node_list[index]
        _, value = _operand(node)
        new_value = _half_step(value)
        self._edit_constant(node, new_value)
        self.report.rule_set.add(RULE_STEP_HALF)
        if value % 2:
            self.report.rule_set.add(RULE_ODD_STEP)
            self.report.odd_step_list.append((node.origin, value, new_value))
            self.report.note_list.append(f"odd per-tick step {value} at offset {node.origin} "
                                         f"-> {new_value} per 30 Hz tick (rounded)")

    def _classify_loop(self, first, last, own, body_ops):
        """('smooth' | 'fallback' | None, counter var or None, counter parity at loop entry).
        `own` is the index list of the loop's commands, inner tick loops left out."""
        self.loop_accumulator = []
        condition_list = [(index, self.state_list[index]) for index in own
                          if self.node_list[index].is_jump()
                          and self.node_list[index].op_code not in _JUMP_ALWAYS]
        condition_source = set()
        for index, state in condition_list:
            condition_source |= state.all_source()
        own_set = set(own)
        write_list = [item for item in self._writes(first, last) if item[0] in own_set]
        events = body_ops & _EVENT_OPS
        if condition_source & _EXTERNAL and not (condition_source & _LOCAL - _EXTERNAL):
            self.report.rule_set.add(RULE_POLL)
            return None, None, None
        counter_list = [v for v in condition_source if v in _LOCAL and any(
            var == v and state.base == v and not state.complex and state.delta != 0
            for index, var, state in write_list)]
        all_condition = set()
        for index, state in condition_list:
            all_condition |= state.all_source()
            for v in state.all_source():
                all_condition |= self.local_source.get(v, frozenset())
        if not counter_list and condition_source & _LOCAL and all_condition & _EXTERNAL:
            self.report.rule_set.add(RULE_POLL)
            return None, None, None
        accumulator = [(index, var, state) for index, var, state in write_list
                       if state.base == var and not state.complex and state.delta != 0
                       and var not in counter_list and var != 0x08]
        if not condition_list and self.node_list[last].op_code in _JUMP_ALWAYS:
            if events:
                return self._fallback(first, last, "endless loop firing events every tick")
            self.report.rule_set.add(RULE_ENDLESS)
            self.loop_accumulator = accumulator
            return "smooth", None, None
        if counter_list:
            counter = counter_list[0]
            origin_set, literal_init, init_parity = set(), [], 0
            for v in counter_list:
                init_list = [(index, state) for index, var, state in self._writes(0, first - 1)
                             if var == v]
                if not init_list:
                    origin_set.add("none")
                    continue
                index, state = init_list[-1]
                source = state.all_source()
                if state.base is None and not state.complex:
                    origin_set.add("literal")
                    literal_init.append((v, state.delta, index))
                elif source & _FRAME:
                    origin_set.add("frame")
                    if v == counter:
                        init_parity = (state.delta % 2 if state.base == 0x0A and not state.complex
                                       else None)
                elif source & _EXTERNAL:
                    origin_set.add("external")
                else:
                    origin_set.add("other")
            if origin_set == {"frame"}:
                self.report.rule_set.add(RULE_FRAME_LOOP)
                self.loop_accumulator = accumulator
                return "smooth", counter, init_parity
            if origin_set == {"literal"} and not body_ops & {_B9}:
                if any(op_code is not None and op_code < 0x80 for op_code in body_ops):
                    return self._fallback(first, last, "the loop also waits for an animation")
                for v, nb_tick, write_index in literal_init:
                    load_index = self._constant_feeding(write_index)
                    if load_index is None:
                        return self._fallback(first, last, "counter literal not found")
                    self._edit_constant(self.node_list[load_index], 2 * nb_tick)
                    self.report.rule_set.add(RULE_LITERAL_COUNTER)
                    self._counter_constants(first, last, v, nb_tick)
                # secondary counters: other vars stepped by +-1 from a literal before the loop
                for item in list(accumulator):
                    index, var, state = item
                    if abs(state.delta) != 1:
                        continue
                    init_list = [(j, st) for j, v2, st in self._writes(0, first - 1) if v2 == var]
                    if init_list and init_list[-1][1].base is None and not init_list[-1][1].complex:
                        load_index = self._constant_feeding(init_list[-1][0])
                        if load_index is not None:
                            nb_tick = init_list[-1][1].delta
                            self._edit_constant(self.node_list[load_index], 2 * nb_tick)
                            self._counter_constants(first, last, var, nb_tick)
                            accumulator.remove(item)
                            self.report.rule_set.add(RULE_SECONDARY_COUNTER)
                self.loop_accumulator = accumulator
                return "smooth", counter, 0
            return self._fallback(first, last, "counter starts from "
                                  + "/".join(sorted(origin_set)) + " value")
        if condition_source & _POSITION:
            if events:
                return self._fallback(first, last, "position loop firing events every tick")
            self.report.rule_set.add(RULE_POSITION_LOOP)
            self.loop_accumulator = accumulator
            return "smooth", None, None
        if condition_source & _FRAME:
            self.report.manual_list.append(f"loop at offsets {self.node_list[first].origin}-"
                                           f"{self.node_list[last].origin} is ended by a frame "
                                           f"value directly")
            return None, None, None
        return self._fallback(first, last, "loop condition of unknown kind")

    def _fallback(self, first, last, reason):
        self.report.rule_set.add(RULE_FALLBACK)
        self.report.fallback_list.append((self.node_list[first].origin,
                                          self.node_list[last].origin, reason))
        self.report.note_list.append(f"loop at offsets {self.node_list[first].origin}-"
                                     f"{self.node_list[last].origin} kept at 15 Hz cadence: "
                                     f"{reason}")
        return "fallback", None, None

    # ---------------------------------------------------------------- output
    def rewrite(self) -> bytes:
        self.in_tick_loop = set()
        self._frame_constants()
        self._rewrite_loops()
        out = []
        gate_by_event = {}
        for event, counter, parity in self.gate_list:
            gate_by_event.setdefault(id(event), (event, counter, parity))
        # Jumps that landed on a gated event now land on its gate.
        gate_head = {}
        for event_id, (event, counter, parity) in gate_by_event.items():
            gate_head[event_id] = SequenceNode(_READ, bytes([counter]))
        for node in self.node_list:
            if node.target is not None and id(node.target) in gate_head:
                node.target = gate_head[id(node.target)]
        for index, node in enumerate(self.node_list):
            if id(node) in gate_by_event:
                event, counter, parity = gate_by_event[id(node)]
                following = self.node_list[index + 1] if index + 1 < len(self.node_list) else self.end
                out.append(gate_head[id(node)])
                out.append(SequenceNode(0xD6, bytes([1])))   # AND 1
                # parity 0: skip when odd (value != 0); parity 1 (or unknown): skip when even
                skip = SequenceNode(_JUMP_IF_NOT_ZERO if parity == 0 else _JUMP_IF_ZERO, b"\x00")
                skip.target = following
                out.append(skip)
            out.extend(self._rewrite_node(node))
            if id(node) in self.ab_data:
                continue
            if node.op_code == _BA:
                out.append(SequenceNode(_BA))
                self.report.rule_set.add(RULE_BA)
            elif node.op_code == _A1 and (id(node) in self.double_after
                                          or id(node) not in self.in_tick_loop):
                out.append(SequenceNode(_A1))
                if id(node) not in self.double_after:
                    self.report.rule_set.add(RULE_STRAIGHT_A1)
        for node, value in self.constant_edit.values():
            _set_constant(node, value)
        return bytes(assemble_node_list(out, self.end, promote_jump=True))

    def _rewrite_node(self, node):
        """The node itself, with its tick parameters scaled (B9 may become two nodes)."""
        if id(node) in self.ab_data:
            return [node]
        op_code = node.op_code
        if op_code == _B9 and node.parameters:
            nb_tick = node.parameters[0] or 256
            doubled = 2 * nb_tick
            if doubled <= 255:
                node.parameters[0] = doubled
                self.report.rule_set.add(RULE_B9)
                return [node]
            if doubled == 256:
                node.parameters[0] = 0       # B9 00 waits 256 ticks
                self.report.rule_set.add(RULE_B9)
                return [node]
            # B9 a; B9 b waits a + b ticks
            self.report.rule_set.add(RULE_B9_SPLIT)
            node.parameters[0] = 255
            node_list = [node]
            remaining = doubled - 255
            while remaining > 0:
                chunk = min(remaining, 255)
                node_list.append(SequenceNode(_B9, bytes([chunk])))
                remaining -= chunk
            return node_list
        duration_index = {0x84: 0, 0x9E: 1, 0xAD: 3, 0xAE: 4}.get(op_code)
        if duration_index is not None and len(node.parameters) > duration_index:
            value = node.parameters[duration_index] * 2
            if value > 255:
                self.report.manual_list.append(f"{op_code:02X} duration {value // 2} at offset "
                                               f"{node.origin} does not fit a byte once doubled")
            else:
                node.parameters[duration_index] = value
                self.report.rule_set.add(RULE_DURATION)
        elif op_code == 0x9F:
            stamp_list = []
            for stamp in node.parameters:
                if stamp == 0xFF:
                    stamp_list.append(stamp)
                elif stamp * 2 >= 0xFF:
                    self.report.manual_list.append(f"9F tick stamp {stamp} at offset {node.origin} "
                                                   f"does not fit a byte once doubled")
                    stamp_list.append(stamp)
                else:
                    stamp_list.append(stamp * 2)
            node.parameters = bytearray(stamp_list)
            self.report.rule_set.add(RULE_9F)
        return [node]


def rewrite_sequence(vm, data, seq_id=None):
    """(new bytes, SequenceReport) of a MAIN sequence. A sequence that cannot be parsed for
    editing comes back unchanged with STATUS_REFUSED."""
    report = SequenceReport(seq_id)
    data = bytes(data)
    try:
        new_data = _Rewriter(vm, data, seq_id, report).rewrite()
    except SequenceRelinkError as error:
        report.status = STATUS_REFUSED
        report.manual_list.append(f"cannot be edited: {error}")
        return data, report
    report.status = _status_of(report, new_data != data)
    return new_data, report


def _status_of(report, changed):
    if report.manual_list:
        return STATUS_MANUAL
    if report.fallback_list:
        return STATUS_FALLBACK
    return STATUS_REWRITTEN if changed else STATUS_UNCHANGED


def background_sequence_id_set(vm, sequence_by_id) -> set:
    """Ids some 9A of the file runs as a background sequence."""
    from .sequencecommand import iter_command
    id_set = set()
    for data in sequence_by_id.values():
        for _address, op_code, parameters in iter_command(vm, bytes(data or b"")):
            if op_code == 0x9A and parameters and parameters[0]:
                id_set.add(parameters[0])
    return id_set


def find_free_scratch_variable(vm, sequence_by_id):
    """A 0x78-0x7F variable no sequence of the file reads or writes, or None."""
    from .sequencecommand import iter_command
    used = set()
    for data in sequence_by_id.values():
        for _address, op_code, parameters in iter_command(vm, bytes(data or b"")):
            if parameters and ((_is_arithmetic(op_code) and op_code & 3 == 3) or op_code == _WRITE
                               or op_code == 0x9B):
                used.update(parameters[-1:] if op_code == 0x9B else parameters[:1])
    for var in _SCRATCH_BANK:
        if var not in used:
            return var
    return None


def rewrite_background_sequence(vm, data, toggle_var, seq_id=None):
    """(new bytes, SequenceReport) of a background (9A) sequence.

    The driver re-runs it from its first byte every tick until its first yield (0x5042B5),
    so everything in it is per tick. Gating the whole body on a toggle variable makes it run
    on every other 30 Hz tick, i.e. exactly at the vanilla rate:

        C3 v / DD 01 / E5 v / E8|EF -> A1      (toggle; skip the body when it became 0)

    Only a straight body is gated: no backward jump, no animation op code, every forward
    jump landing at or before the A1 that ends it. Anything else is a manual decision.
    """
    report = SequenceReport(seq_id)
    report.is_background = True
    data = bytes(data)
    try:
        node_list, end = parse_node_list(vm, data)
    except SequenceRelinkError as error:
        report.status = STATUS_REFUSED
        report.manual_list.append(f"background sequence cannot be edited: {error}")
        return data, report
    yield_node = next((node for node in node_list if node.op_code in _TICK_YIELD), None)
    reason = ""
    if toggle_var is None:
        reason = "no free 0x78-0x7F variable for the 15 Hz toggle"
    elif yield_node is None:
        reason = "no yield ends the body"
    else:
        yield_index = node_list.index(yield_node)
        for index, node in enumerate(node_list[:yield_index]):
            if node.op_code < 0x80 or node.op_code in (0xA2, 0xA7, 0xAC, _B9, _BA, _AB):
                reason = f"op code {node.op_code:02X} at offset {node.origin} in the body"
                break
            if node.is_jump():
                target_index = (len(node_list) if node.target is end
                                else node_list.index(node.target))
                if target_index <= index or target_index > yield_index:
                    reason = f"jump at offset {node.origin} leaves the straight body"
                    break
    if reason:
        report.status = STATUS_MANUAL
        report.manual_list.append(f"background sequence not gated: {reason}")
        return data, report
    gate = [SequenceNode(_READ, bytes([toggle_var])), SequenceNode(0xDD, bytes([1])),
            SequenceNode(_WRITE, bytes([toggle_var])), SequenceNode(_JUMP_IF_ZERO, b"\x00")]
    gate[3].target = yield_node
    new_data = bytes(assemble_node_list(gate + node_list, end, promote_jump=True))
    report.rule_set.add(RULE_BACKGROUND)
    report.status = STATUS_REWRITTEN
    return new_data, report


class SectionReport:
    """The rewrite of every sequence of one section."""

    def __init__(self):
        self.sequence_report = {}    # seq id -> SequenceReport
        self.background_id_set = set()
        self.toggle_var = None

    def count(self) -> dict:
        result = {}
        for report in self.sequence_report.values():
            result[report.status] = result.get(report.status, 0) + 1
        return result

    def manual_report_list(self):
        return [report for report in self.sequence_report.values()
                if report.status in (STATUS_MANUAL, STATUS_REFUSED)]

    def not_fully_automatic_list(self):
        return [report for report in self.sequence_report.values()
                if report.status in (STATUS_MANUAL, STATUS_REFUSED, STATUS_FALLBACK)]


def rewrite_sequence_dict(vm, sequence_by_id: dict):
    """({id: new bytes}, SectionReport) for every sequence of a section ({id: bytes})."""
    section_report = SectionReport()
    section_report.background_id_set = background_sequence_id_set(vm, sequence_by_id)
    if section_report.background_id_set:
        section_report.toggle_var = find_free_scratch_variable(vm, sequence_by_id)
    called_as_main = _sequence_called_as_main(vm, sequence_by_id)
    new_by_id = {}
    for seq_id, data in sequence_by_id.items():
        data = bytes(data or b"")
        if not data:
            new_by_id[seq_id] = data
            section_report.sequence_report[seq_id] = SequenceReport(seq_id)
            continue
        if seq_id in section_report.background_id_set:
            if seq_id in called_as_main:
                report = SequenceReport(seq_id)
                report.is_background = True
                report.status = STATUS_MANUAL
                report.manual_list.append("runs as a background sequence (9A) AND is started as "
                                          "a normal sequence: cannot be gated for one use only")
                new_by_id[seq_id] = data
            else:
                new_by_id[seq_id], report = rewrite_background_sequence(
                    vm, data, section_report.toggle_var, seq_id)
        else:
            new_by_id[seq_id], report = rewrite_sequence(vm, data, seq_id)
        section_report.sequence_report[seq_id] = report
    return new_by_id, section_report


def _sequence_called_as_main(vm, sequence_by_id) -> set:
    """Ids another sequence starts as a normal one (A7 goto, AC/BF queue)."""
    from .sequencecommand import iter_command
    id_set = set()
    for data in sequence_by_id.values():
        for _address, op_code, parameters in iter_command(vm, bytes(data or b"")):
            if op_code in (0xA7, 0xAC, 0xBF) and parameters and parameters[0]:
                id_set.add(parameters[0])
    return id_set


def rewrite_seq_animation_data(vm, seq_animation_data) -> SectionReport:
    """Rewrite a MonsterAnalyser.seq_animation_data in place (every sequence's 'data')."""
    sequence_list = (seq_animation_data or {}).get('seq_animation_data', [])
    sequence_by_id = {sequence['id']: bytes(sequence['data']) for sequence in sequence_list}
    new_by_id, section_report = rewrite_sequence_dict(vm, sequence_by_id)
    for sequence in sequence_list:
        sequence['data'] = bytearray(new_by_id[sequence['id']])
    return section_report
