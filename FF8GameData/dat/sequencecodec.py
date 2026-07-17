"""The IfritSeq-code language: a byte-code sequence as editable text.

One line per command, `func_name(arg, arg, ...)`, names from the VM's json (func_name
field). The encoding variant is part of the name (set_i8 vs set_i16, jump vs jump16), so a
line maps to exactly one byte string and the code view round trips:
code_to_sequence(sequence_to_code(data)) == data for every vanilla sequence
(tests/test_seq_codec.py).

Arguments:
- anim/anim_async: the animation id, decimal (entity VM only);
- jumps: the signed byte offset, decimal (relative to the op code's own address);
- value ops: the literal, decimal (signed for i8/i16) - except _var/store_var, whose
  variable id is hexadecimal (0xNN);
- everything else: the raw parameter bytes, hexadecimal (0xNN each). Variable-size op
  codes are checked against normalize_parameters: a hit_target whose flag byte promises
  three extra bytes but gives two is an error on that line, not a silent shift of the
  rest of the sequence.

`# comment` (whole line or trailing) and blank lines are ignored.

Built on sequencecommand (the one walker): the codec never re-implements sizes. Every public
function takes a GameData (the entity VM, as before) or a SequenceVM (e.g. the camera VM);
what is op-code-family-specific comes from the VM, not from hard-coded constants.
"""
import html
import re

from .sequencecommand import (SequenceCommand, read_sequence, write_sequence,
                              normalize_parameters, get_op_code_info,
                              is_jump, is_jump_int16)
from .sequencevm import as_sequence_vm

_LINE_RE = re.compile(r"^\s*(?P<name>\w+)\s*\(\s*(?P<args>[^)]*)\)\s*(?:#.*)?$")
_COMMENT_OR_BLANK_RE = re.compile(r"^\s*(#.*)?$")

# Encoding kinds, keyed by how the argument text maps to parameter bytes
_KIND_ANIM = "anim"
_KIND_JUMP8 = "jump8"
_KIND_JUMP16 = "jump16"
_KIND_I8 = "i8"
_KIND_I16 = "i16"
_KIND_U8 = "u8"
_KIND_VAR = "var"
_KIND_SIMPLE = "simple"  # fixed-size op: one semantic argument per json param_type
_KIND_RAW = "raw"


def _op_kind(vm, op_code: int) -> str:
    if op_code < vm.animation_op_code_max:
        return _KIND_ANIM
    if is_jump(op_code):
        return _KIND_JUMP16 if is_jump_int16(op_code) else _KIND_JUMP8
    if 0xC0 <= op_code < 0xE4:
        return (_KIND_I16, _KIND_I8, _KIND_U8, _KIND_VAR)[op_code & 3]
    if op_code == 0xE5:
        return _KIND_VAR
    if _simple_spec(vm, op_code) is not None:
        return _KIND_SIMPLE
    return _KIND_RAW


def _simple_spec(vm, op_code: int):
    """[param_type] when the op code is fixed-size with each parameter byte covered by
    exactly one json param_type, in order - the condition for `name(value, value, ...)`
    semantic arguments. None otherwise (the line then uses raw hex bytes)."""
    info = get_op_code_info(vm, op_code)
    if info is None or info.get('complexity') != 'simple' or info['size'] < 0:
        return None
    types = info.get('param_type', [])
    indexes = info.get('param_index', [])
    if len(types) != len(indexes):
        return None
    position = 0
    for param_type, param_index in zip(types, indexes):
        if param_index != position:
            return None
        position += 2 if param_type == "int16" else 1
    if position != info['size']:
        return None
    return types


def _func_name_table(vm) -> dict:
    """{func_name: op_code}, cached on the VM (entity and camera have different names)."""
    if vm._func_name_table is None:
        table = {}
        for info in vm.data_json["op_code_info"]:
            name = info.get("func_name")
            if name:
                table[name] = info["op_code"]
        vm._func_name_table = table
    return vm._func_name_table


# --------------------------------------------------------------- bytes -> code
def command_to_code(command: SequenceCommand) -> str:
    """One command as one line of IfritSeq-code (no comment, no indent)."""
    vm = command.vm
    info = get_op_code_info(vm, command.op_code)
    if command.is_unknown() or info is None or not info.get("func_name"):
        # An op code the language cannot name: keep it as raw bytes so nothing is lost
        byte_list = ", ".join(f"0x{byte:02X}" for byte in command.to_bytes())
        return f"raw({byte_list})"
    name = info["func_name"]
    kind = _op_kind(vm, command.op_code)
    parameters = bytes(command.parameters or b"")
    if kind == _KIND_ANIM:
        return f"anim({command.op_code})"
    if vm.async_anim_op_code is not None and command.op_code == vm.async_anim_op_code:
        return f"anim_async({parameters[0]})"  # the id reads better in decimal
    if kind in (_KIND_JUMP8, _KIND_I8):
        value = int.from_bytes(parameters[:1], "little", signed=True)
        return f"{name}({value})"
    if kind in (_KIND_JUMP16, _KIND_I16):
        value = int.from_bytes(parameters[:2], "little", signed=True)
        return f"{name}({value})"
    if kind == _KIND_U8:
        return f"{name}({parameters[0]})"
    if kind == _KIND_VAR:
        return f"{name}(0x{parameters[0]:02X})"
    if kind == _KIND_SIMPLE:
        values = []
        position = 0
        for param_type in _simple_spec(vm, command.op_code):
            if param_type == "int16":
                values.append(str(int.from_bytes(parameters[position:position + 2],
                                                 "little", signed=True)))
                position += 2
            elif param_type == "sbyte":
                values.append(str(int.from_bytes(parameters[position:position + 1],
                                                 "little", signed=True)))
                position += 1
            else:  # ubyte, anim_id, effect_id, fade_effect_id...
                values.append(str(parameters[position]))
                position += 1
        return f"{name}({', '.join(values)})"
    byte_list = ", ".join(f"0x{byte:02X}" for byte in parameters)
    return f"{name}({byte_list})" if byte_list else f"{name}()"


def sequence_to_code(game_data, sequence: bytes) -> str:
    """The whole sequence as IfritSeq-code, one command per line."""
    vm = as_sequence_vm(game_data)
    return "\n".join(command_to_code(command)
                     for command in read_sequence(vm, bytes(sequence)))


# --------------------------------------------------------------- code -> bytes
def _parse_int(text: str, line_number: int) -> int:
    text = text.strip()
    try:
        return int(text, 16) if text.lower().startswith("0x") else int(text)
    except ValueError:
        raise SeqCodeError(line_number, f"'{text}' is not a number")


def _parse_args(args_text: str, line_number: int) -> list:
    args_text = args_text.strip()
    if not args_text:
        return []
    return [_parse_int(part, line_number) for part in args_text.split(",")]


def _require_args(name, args, nb, line_number):
    if len(args) != nb:
        raise SeqCodeError(line_number, f"{name}() takes {nb} argument(s), {len(args)} given")


def _check_range(name, value, low, high, line_number):
    if not low <= value <= high:
        raise SeqCodeError(line_number, f"{name}(): {value} is out of range [{low}, {high}]")


class SeqCodeError(ValueError):
    """A line of IfritSeq-code that cannot be turned into bytes. line_number is 1-based."""

    def __init__(self, line_number: int, message: str):
        super().__init__(f"line {line_number}: {message}")
        self.line_number = line_number


def code_line_to_command(game_data, line: str, line_number: int = 1):
    """One line of IfritSeq-code as a SequenceCommand, or None for blank/comment lines."""
    vm = as_sequence_vm(game_data)
    if _COMMENT_OR_BLANK_RE.match(line):
        return None
    match = _LINE_RE.match(line)
    if match is None:
        raise SeqCodeError(line_number, f"cannot read '{line.strip()}' "
                                        f"(expected: func_name(arg, ...))")
    name = match.group("name")
    args = _parse_args(match.group("args"), line_number)
    if name == "raw":  # verbatim bytes, the escape hatch of the language
        if not args:
            raise SeqCodeError(line_number, "raw() needs at least the op code byte")
        for value in args:
            _check_range("raw", value, 0, 255, line_number)
        return SequenceCommand(vm, args[0], bytearray(args[1:]))
    if vm.animation_op_code_max > 0 and name in ("anim", "anim_async"):
        _require_args(name, args, 1, line_number)
        _check_range(name, args[0], 0, vm.animation_op_code_max - 1, line_number)
        if name == "anim":
            return SequenceCommand(vm, args[0])
        return SequenceCommand(vm, vm.async_anim_op_code, bytearray([args[0]]))
    op_code = _func_name_table(vm).get(name)
    if op_code is None:
        raise SeqCodeError(line_number, f"unknown command '{name}'")
    kind = _op_kind(vm, op_code)
    if kind in (_KIND_JUMP8, _KIND_I8):
        _require_args(name, args, 1, line_number)
        _check_range(name, args[0], -128, 127, line_number)
        return SequenceCommand(vm, op_code,
                               bytearray(args[0].to_bytes(1, "little", signed=True)))
    if kind in (_KIND_JUMP16, _KIND_I16):
        _require_args(name, args, 1, line_number)
        _check_range(name, args[0], -32768, 32767, line_number)
        return SequenceCommand(vm, op_code,
                               bytearray(args[0].to_bytes(2, "little", signed=True)))
    if kind in (_KIND_U8, _KIND_VAR):
        _require_args(name, args, 1, line_number)
        _check_range(name, args[0], 0, 255, line_number)
        return SequenceCommand(vm, op_code, bytearray([args[0]]))
    if kind == _KIND_SIMPLE:
        spec = _simple_spec(vm, op_code)
        _require_args(name, args, len(spec), line_number)
        parameters = bytearray()
        for param_type, value in zip(spec, args):
            if param_type == "int16":
                _check_range(name, value, -32768, 32767, line_number)
                parameters += value.to_bytes(2, "little", signed=True)
            elif param_type == "sbyte":
                _check_range(name, value, -128, 127, line_number)
                parameters += value.to_bytes(1, "little", signed=True)
            else:
                _check_range(name, value, 0, 255, line_number)
                parameters.append(value)
        return SequenceCommand(vm, op_code, parameters)
    # Raw parameter bytes; sizes checked against what the engine will consume
    for value in args:
        _check_range(name, value, 0, 255, line_number)
    parameters = bytearray(args)
    normalized = normalize_parameters(vm, op_code, parameters)
    if normalized != parameters:
        raise SeqCodeError(
            line_number,
            f"{name}({', '.join(f'0x{byte:02X}' for byte in parameters)}) is "
            f"{len(parameters)} parameter byte(s), but with these values the engine "
            f"would consume {len(normalized)}: {' '.join(f'{byte:02X}' for byte in normalized)}")
    return SequenceCommand(vm, op_code, parameters)


def code_to_sequence(game_data, code: str) -> bytearray:
    """IfritSeq-code back to sequence bytes. Raises SeqCodeError with the line number."""
    vm = as_sequence_vm(game_data)
    command_list = []
    for line_number, line in enumerate(code.splitlines(), start=1):
        command = code_line_to_command(vm, line, line_number)
        if command is not None:
            command_list.append(command)
    return write_sequence(command_list)


# ------------------------------------------------------------------- help page
# One line of guidance per argument kind, shown next to every command that uses it in
# the help page - the same _op_kind() the parser itself dispatches on, so the page can
# never claim an encoding the parser does not actually accept.
_ARG_KIND_NOTE = {
    _KIND_ANIM: "id: animation id, 0-127, decimal",
    _KIND_JUMP8: "offset: signed byte, decimal, relative to this command's own address",
    _KIND_JUMP16: "offset: signed 16-bit, decimal, relative to this command's own address",
    _KIND_I8: "value: signed byte, decimal",
    _KIND_I16: "value: signed 16-bit, decimal",
    _KIND_U8: "value: unsigned byte, decimal",
    _KIND_VAR: "0xNN: the special-variable id, hexadecimal",
    _KIND_SIMPLE: "one decimal value per argument (signed where the game reads it signed)",
    _KIND_RAW: "raw parameter bytes, hexadecimal (0xNN, 0xNN, ...) - see the description "
               "for what each one means; the count must match what the flag byte(s) "
               "make the engine actually consume",
}


def _signature_for(vm, op_code: int, name: str) -> str:
    """The `name(args)` syntax shown in the help page - built from the same kind
    dispatch code_line_to_command()/command_to_code() use, so it cannot drift from what
    is actually accepted."""
    if op_code == 0x00 and vm.animation_op_code_max > 0:
        return "anim(id)"
    kind = _op_kind(vm, op_code)
    if kind in (_KIND_JUMP8, _KIND_JUMP16):
        return f"{name}(offset)"
    if kind in (_KIND_I8, _KIND_I16, _KIND_U8):
        return f"{name}(value)"
    if kind == _KIND_VAR:
        return f"{name}(0xNN)"
    if kind == _KIND_SIMPLE:
        return f"{name}({', '.join(_simple_spec(vm, op_code))})"
    return f"{name}(0xNN, 0xNN, ...)"


def generate_help_entries(game_data) -> list:
    """[{signature, op_code, description, note}] for every command the language knows,
    in op code order - the data behind the IfritSeq-code help page. Built straight from
    the VM's json (func_name/text) plus the parser's own kind dispatch, so the page is
    generated from the same source the parser reads and cannot go stale."""
    vm = as_sequence_vm(game_data)
    entries = []
    for info in vm.data_json["op_code_info"]:
        op_code = info["op_code"]
        name = info.get("func_name")
        if not name:
            continue
        kind = _op_kind(vm, op_code)
        anim_range = op_code == 0x00 and vm.animation_op_code_max > 0
        entries.append({
            "signature": _signature_for(vm, op_code, name),
            "op_code": "0x00-0x7F" if anim_range else f"0x{op_code:02X}",
            "description": info.get("text", ""),
            "note": _ARG_KIND_NOTE.get(kind, ""),
        })
    return entries


def generate_help_html(game_data) -> str:
    """The IfritSeq-code reference page, as HTML for a QTextBrowser/QTextEdit."""
    intro = (
        "<h2>IfritSeq-code reference</h2>"
        "<p>One command per line: <code>func_name(arg, arg, ...)</code>. The engine "
        "reads the sequence top to bottom; a bare op code below 0x80 plays that "
        "animation and waits for it to finish before moving on.</p>"
        "<p>Blank lines and <code># comments</code> (whole-line or trailing) are "
        "ignored.</p>"
        "<p><b>Arguments</b> are decimal by default (signed where the game reads a "
        "signed byte/word) - except a special-variable id (<code>set_var</code>, "
        "<code>store_var</code>, the jump-condition <code>*_var</code> family...), "
        "which is hexadecimal (<code>0xNN</code>), and the handful of commands whose "
        "parameter bytes are flag-driven (sound, hit effects, walk effects...), which "
        "take raw hexadecimal bytes - see each command's note below.</p>"
        "<p><code>raw(0xNN, 0xNN, ...)</code> is the escape hatch: the first value is "
        "the op code byte, the rest are its parameter bytes verbatim. Anything - "
        "including a command this language does not otherwise name - can be written "
        "and read back exactly through it.</p>"
        "<p>A line that doesn't parse, has the wrong argument count, an out-of-range "
        "value, or a parameter block that doesn't match what its flag byte says it "
        "needs is refused with the line number, before it can shift the rest of the "
        "sequence.</p>"
        "<table border='1' cellspacing='0' cellpadding='4'>"
        "<tr><th align='left'>Command</th><th align='left'>Op code</th>"
        "<th align='left'>What it does</th><th align='left'>Arguments</th></tr>"
    )
    rows = "".join(
        f"<tr><td><code>{html.escape(entry['signature'])}</code></td>"
        f"<td>{entry['op_code']}</td>"
        f"<td>{html.escape(entry['description'])}</td>"
        f"<td>{html.escape(entry['note'])}</td></tr>"
        for entry in generate_help_entries(game_data)
    )
    return intro + rows + "</table>"
