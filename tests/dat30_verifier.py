"""Test helper: check a 30 fps sequence rewrite against the original, by running both.

The original runs at 15 Hz with its n-frame animations, the rewrite at 30 Hz with 2n-frame
animations, in the sequence interpreter of FF8GameData.dat.sequencebake, in three battle
contexts (study DAT30FPS_STUDY.md 2.6). The rewrite is accepted when:
- both stop the same way, and a finite sequence lasts twice as many ticks (+-2);
- the same events (op code + parameters; the parameters the rewrite scales are ignored) fire
  in the same order, each at the same vanilla tick +-1, and as many of them within the
  common time span - so a per-tick event firing twice as often is caught even in a sequence
  that never ends;
- position, 9E move, yaw and scale stay within one vanilla step at every vanilla tick;
- the same animation and the same hidden-part mask are shown.

The interpreter is subclassed, not patched, to follow the exe where the preview's bake
deliberately or not differs (the subclass is local to this helper, IfritSeq's preview is
untouched):
- B9 N resumes the VM exactly N ticks later (0x504C5D sets delay = N-1, 0x5044A7);
- C3 09 is the number of frames read, pose index + 1 (pre_Battle_ReadAnimation 0x509440
  reads frame 0 at queue time);
- C3 2C reads back what E5 2C wrote (both are original_sceneout_position_x, 0x504A83);
- AB consumes its animation list up to the A1 that ends it (0x504E5B), it does not run it.
"""
import struct

from FF8GameData.dat import sequencebake as bake_module
from FF8GameData.dat.sequencecommand import iter_command

CONTEXT_LIST = [dict(), dict(target_distance=4096, seed=3),
                dict(target_is_self=True, target_was_hit=False, seed=7)]

_NOT_EVENT = {0xA1, 0xE5, 0xA0, 0xBA, 0xB9} | set(range(0xC0, 0xF4))   # B9 is a wait
_PARAMETER_SCALED = {0xB9, 0x96, 0x9E, 0xAD, 0xAE, 0x9F, 0x84}


class ExeInterpreter(bake_module._Interpreter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.scene_out_x = None

    def _execute(self, command, address):
        if command.op_code == 0xAB and command.parameters is not None:
            data = self._sequence(self.seq_id)
            next_address = address + command.get_size()
            for sub_address, op_code, _parameters in iter_command(self.vm, data[next_address:]):
                if op_code == 0xA1:
                    return next_address + sub_address + 1, False
            return len(data), False
        return super()._execute(command, address)

    def _execute_action_op_code(self, op_code, parameters, next_address):
        if op_code == 0xB9 and parameters:
            self.wait_frame = (parameters[0] - 1) & 0xFF
            return next_address, True
        return super()._execute_action_op_code(op_code, parameters, next_address)

    def _read_special(self, parameter):
        if parameter == 0x09:
            return min(self.anim_frame + 1, self.anim_total)
        if parameter == 0x2C and self.scene_out_x is not None:
            return self.scene_out_x
        return super()._read_special(parameter)

    def _write_special(self, parameter, value):
        if parameter == 0x2C:
            self.scene_out_x = value
        super()._write_special(parameter, value)

    def _state_key(self):
        return super()._state_key() + (self.scene_out_x,)


def bake(vm, sequence_by_id, seq_id, frame_count, context_kw, max_frame, as_background=False,
         detect_loop=False):
    """bake_sequence with the exe-faithful interpreter.

    Loop detection is off by default: a sequence that never ends is played up to max_frame,
    so a per-tick event firing twice as often shows over the whole span (with detection, an
    idle loop stops after one period and the comparison would see almost nothing)."""
    context = bake_module.BattleContext(**context_kw)
    interpreter = ExeInterpreter(vm, sequence_by_id, seq_id,
                                 bake_module._frame_count_function(frame_count), context,
                                 False, as_background)
    frame_list, seen, loop_from = [], {}, None
    while len(frame_list) < max_frame:
        key = interpreter._state_key() if detect_loop else len(frame_list)
        if key in seen:
            loop_from = seen[key]
            interpreter._stop(bake_module.STOP_LOOP)
            break
        seen[key] = len(frame_list)
        frame_list.append(interpreter.run_frame())
        if interpreter.stop_reason is not None:
            break
    else:
        interpreter._stop(bake_module.STOP_MAX_FRAMES)
    return bake_module.BakeResult(frame_list, interpreter.stop_reason, interpreter.stop_detail,
                                  loop_from, interpreter.assumption_list,
                                  sorted(interpreter.background_used))


def _event_list(result, divisor):
    event_list = []
    for frame in result.frame_list:
        for command in frame.command_list:
            if command.op_code in _NOT_EVENT:
                continue
            parameters = b"" if command.op_code in _PARAMETER_SCALED else bytes(command.parameters or b"")
            event_list.append((frame.index // divisor, command.op_code, parameters))
    return event_list


def compare(result_15, result_30, drift_per_tick=0, anim_alias=None):
    """[problem text] between the 15 Hz original and the 30 Hz rewrite (empty = match).

    drift_per_tick widens the motion tolerance by that much per vanilla tick elapsed: an odd
    per-tick step rounded by half a unit per 30 Hz tick drifts by one unit per vanilla tick
    (accepted by design, and reported by the rewriter).
    anim_alias maps an animation id of the 30 Hz side to the vanilla one it stands for (the
    parts of a split animation)."""
    alias = anim_alias or {}
    problem_list = []
    length_15, length_30 = len(result_15.frame_list), len(result_30.frame_list)
    finite = result_15.stop_reason not in (bake_module.STOP_LOOP, bake_module.STOP_MAX_FRAMES)
    if result_15.stop_reason != result_30.stop_reason:
        problem_list.append(f"stop {result_15.stop_reason} vs {result_30.stop_reason}")
    if finite and abs(length_30 - 2 * length_15) > 2:
        problem_list.append(f"length {length_15} -> {length_30} ticks (want {2 * length_15})")
    event_15, event_30 = _event_list(result_15, 1), _event_list(result_30, 2)
    # the bare op code playing part 2+ of a split animation is the same play as part 1's
    event_30 = [event for event in event_30 if not (event[1] < 0x80 and event[1] in alias)]
    if finite:
        if len(event_15) != len(event_30):
            problem_list.append(f"event count {len(event_15)} vs {len(event_30)}")
    else:
        horizon = min(length_15, length_30 // 2) - 2
        count_15 = sum(1 for event in event_15 if event[0] < horizon)
        count_30 = sum(1 for event in event_30 if event[0] < horizon)
        if abs(count_15 - count_30) > 1:
            problem_list.append(f"event count {count_15} vs {count_30} over {horizon} ticks")
    for a, b in zip(event_15, event_30):
        if a[1:] != b[1:]:
            problem_list.append(f"event order {a} vs {b}")
            break
        if abs(a[0] - b[0]) > 1:
            problem_list.append(f"event time {a} vs {b}")
            break

    def vector(frame):
        return (list(frame.position) + list(frame.move_position) + [frame.rotation_y]
                + list(frame.scale))

    for k in range(min(length_15, length_30 // 2)):
        frame_30a = result_30.frame_list[2 * k]
        frame_30b = result_30.frame_list[min(2 * k + 1, length_30 - 1)]
        v15, v30a, v30b = vector(result_15.frame_list[k]), vector(frame_30a), vector(frame_30b)
        previous = vector(result_15.frame_list[max(k - 1, 0)])
        following = vector(result_15.frame_list[min(k + 1, length_15 - 1)])
        for i in range(len(v15)):
            tolerance = (max(abs(v15[i] - previous[i]), abs(following[i] - v15[i])) + 4
                         + drift_per_tick * (k + 1))
            if min(abs(v30a[i] - v15[i]), abs(v30b[i] - v15[i])) > tolerance:
                problem_list.append(f"motion at tick {k} component {i}: {v15[i]} vs "
                                    f"{v30a[i]}/{v30b[i]} (tolerance {tolerance})")
                break
        anim_15 = result_15.frame_list[k].anim_id
        anim_30 = (alias.get(frame_30a.anim_id, frame_30a.anim_id),
                   alias.get(frame_30b.anim_id, frame_30b.anim_id))
        if anim_15 is not None and anim_15 not in anim_30:
            problem_list.append(f"animation at tick {k}: {anim_15} vs {frame_30a.anim_id}")
            break
        if result_15.frame_list[k].hidden_part_mask not in (frame_30a.hidden_part_mask,
                                                            frame_30b.hidden_part_mask):
            problem_list.append(f"hidden part mask at tick {k}")
            break
        if len(problem_list) > 6:
            break
    return problem_list


def verify_sequence(vm, sequence_15, sequence_30, seq_id, frame_15, frame_30,
                    as_background=False, max_frame=240, drift_per_tick=0, anim_alias=None):
    """[problem text] of one sequence over the three battle contexts (empty = match)."""
    for context_kw in CONTEXT_LIST:
        try:
            result_15 = bake(vm, sequence_15, seq_id, frame_15, context_kw, max_frame,
                             as_background)
            result_30 = bake(vm, sequence_30, seq_id, frame_30, context_kw, 2 * max_frame,
                             as_background)
            problem_list = compare(result_15, result_30, drift_per_tick, anim_alias)
        except Exception as error:  # a bake crash is a failure to report, not to hide
            problem_list = [f"bake error {type(error).__name__}: {error}"]
        if problem_list:
            return problem_list
    return []


# ------------------------------------------------------------------ fast corpus reader
_SEQUENCE_SECTION = {12: 5, 9: 4, 11: 6, 6: 2}   # nb sections -> sequence section
_ANIMATION_SECTION = {12: 3, 9: 3, 8: 3, 11: 3}


def _section_list(data):
    nb_section = struct.unpack_from("<I", data, 0)[0] + 1
    position = [0] + [struct.unpack_from("<I", data, 4 + 4 * i)[0] for i in range(nb_section)]
    section = []
    for i in range(nb_section):
        end = position[i + 1] if i + 1 < nb_section else len(data)
        section.append(data[position[i]:end])
    return nb_section, section


def read_frame_count_list(data):
    """Frame count of every animation of a battle .dat, from the raw bytes (no decoding)."""
    nb_section, section = _section_list(data)
    if nb_section not in _ANIMATION_SECTION:
        return []
    raw = section[_ANIMATION_SECTION[nb_section]]
    if len(raw) < 4:
        return []
    nb = struct.unpack_from("<I", raw, 0)[0]
    return [raw[struct.unpack_from("<I", raw, 4 + 4 * i)[0]] for i in range(nb)]


def read_sequence_dict(data):
    """{seq id: bytes} of a battle .dat, split exactly like MonsterAnalyser does (a sequence
    runs to the next larger offset, the last one to the end of the section)."""
    nb_section, section = _section_list(data)
    if nb_section not in _SEQUENCE_SECTION:
        return {}
    raw = section[_SEQUENCE_SECTION[nb_section]]
    if len(raw) < 2:
        return {}
    nb = struct.unpack_from("<H", raw, 0)[0]
    offset_list = [struct.unpack_from("<H", raw, 2 + 2 * i)[0] for i in range(nb)]
    sequence = {}
    for index, offset in enumerate(offset_list):
        if offset == 0:
            sequence[index + 1] = b""
            continue
        following = [o for o in offset_list if o > offset]
        sequence[index + 1] = bytes(raw[offset:min(following) if following else len(raw)])
    return sequence
