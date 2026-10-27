"""A battle camera script as a list of editable steps: the user-friendly view of the script
(Common.camerascripteditor), driven by camera_script.json.

A step is one command as a modder thinks of it: "Play camera animation set 1 slot 2", "value += a
random number", "if value is not 0, go to step 3". The byte details are derived when the steps are
written back (script_bytes):
- a number gets the smallest of the sbyte/ubyte/int16 forms that holds it (the form it was read
  with when it still does, so an unedited script writes back byte for byte);
- a jump points at a step, not at an offset: inserting, removing or moving steps keeps it on its
  step, and it becomes the int16 form when the 8-bit offset no longer reaches.
A jump that does not land on a command start (a hand-made script) keeps its raw offset.
"""
from dataclasses import dataclass

from .sequencecommand import get_jump_target, iter_command


def _hex(value) -> int:
    return int(value, 16) if isinstance(value, str) else value


class CameraScriptInfo:
    """camera_script.json, with its hex strings read as numbers and indexed for the editor."""

    def __init__(self, data_json: dict):
        self.data = data_json
        self.commands = []
        self.command_of_op_code = {}
        for command in data_json["commands"]:
            command = dict(command, op_codes=[_hex(op) for op in command["op_codes"]])
            self.commands.append(command)
            for op_code in command["op_codes"]:
                self.command_of_op_code[op_code] = command
        self.command_by_id = {command["id"]: command for command in self.commands}
        self.operations = [dict(operation, variable_op_code=_hex(operation["variable_op_code"]),
                                number_op_codes={kind: _hex(op) for kind, op in operation["number_op_codes"].items()})
                           for operation in data_json["operations"]]
        self.number_types = {kind["id"]: (kind["min"], kind["max"]) for kind in data_json["number_types"]}
        self.conditions = [dict(condition, op_codes={kind: _hex(op) for kind, op in condition["op_codes"].items()})
                           for condition in data_json["conditions"]]
        self.params = data_json["params"]
        self.read_variables = {_hex(variable["id"]): variable for variable in data_json["read_variables"]}
        self.write_variables = [_hex(variable_id) for variable_id in data_json["write_variables"]]
        self.info = data_json["info"]
        # op code -> (operation, operand kind): kind is a number type id or "variable"
        self.value_op_codes = {}
        for operation in self.operations:
            self.value_op_codes[operation["variable_op_code"]] = (operation, "variable")
            for kind, op_code in operation["number_op_codes"].items():
                self.value_op_codes[op_code] = (operation, kind)
        self.jump_op_codes = {}   # op code -> (condition, "sbyte"/"int16")
        for condition in self.conditions:
            for kind, op_code in condition["op_codes"].items():
                self.jump_op_codes[op_code] = (condition, kind)

    def variable_label(self, variable_id: int) -> str:
        variable = self.read_variables.get(variable_id)
        if variable is not None:
            return variable["label"]
        return self.data["other_variable"]["label"].format(variable_id)

    def variable_help(self, variable_id: int, context: str = "") -> str:
        """What a battle value is; `context` ("stage", "spell") adds what it holds there."""
        variable = self.read_variables.get(variable_id)
        if variable is None:
            return self.data["other_variable"]["help"]
        if context and variable.get(context):
            return f"{variable['help']} {variable[context]}"
        return variable["help"]

    def info_html(self, context: str = "") -> str:
        """The Script tab's info text: what every script does, then what this kind of track's does."""
        paragraphs = list(self.info["common"]) + list(self.info.get(context, []))
        return ("<br/><br/>".join(paragraphs)
                + f"<br/><br/>Format and op codes: <a href=\"{self.info['wiki']}\">wiki</a>.")


@dataclass(eq=False)
class ScriptStep:
    """One command. `value` is the parameter shown to the user: the animation index (play), a
    variable id (play_var, store, a value with a variable operand), a number, a byte. A jump has
    `target` (a step, or None for the end of the script) unless `raw_offset` keeps an offset that
    lands on no command."""
    command_id: str
    op_code: int
    value: int = 0
    operation: str = ""      # value: an operations id
    operand: str = ""        # value: "variable" or the number type it was read as
    condition: str = ""      # jump: a conditions id
    target: "ScriptStep" = None
    raw_offset: int = None
    jump_int16: bool = False
    raw: bytes = b""         # an op code the script does not know: it and everything after it

    @property
    def is_jump(self):
        return self.command_id == "jump"


def _signed(data, size) -> int:
    return int.from_bytes(bytes(data[:size]), "little", signed=True)


def read_steps(vm, info: CameraScriptInfo, script: bytes) -> list:
    """The steps of a script (bytes as camera_sequence_info.json reads them)."""
    script = bytes(script)
    steps, at_address, jumps = [], {}, []
    for address, op_code, parameters in iter_command(vm, script):
        command = info.command_of_op_code.get(op_code)
        if parameters is None or command is None:
            steps.append(ScriptStep("raw", op_code, raw=script[address:]))
            break
        step = ScriptStep(command["id"], op_code)
        if command["id"] == "value":
            operation, kind = info.value_op_codes[op_code]
            step.operation, step.operand = operation["id"], kind
            step.value = parameters[0] if kind in ("variable", "ubyte") else _signed(parameters, 2 if kind == "int16" else 1)
        elif command["id"] == "jump":
            condition, kind = info.jump_op_codes[op_code]
            step.condition, step.jump_int16 = condition["id"], kind == "int16"
            jumps.append((step, get_jump_target(address, op_code, parameters), address))
        elif parameters:
            step.value = parameters[0]
        at_address[address] = step
        steps.append(step)
    for step, target, address in jumps:
        if target in at_address:
            step.target = at_address[target]
        elif target != len(script):          # past the last command: the end of the script
            step.raw_offset = target - address
    return steps


def _number_kind(info, value, current):
    if current in info.number_types:
        low, high = info.number_types[current]
        if low <= value <= high:
            return current
    for kind in ("sbyte", "ubyte", "int16"):
        low, high = info.number_types[kind]
        if low <= value <= high:
            return kind
    raise ValueError(f"{value} does not fit a camera script number (-32768 to 32767)")


def _step_body(info, step: ScriptStep) -> bytes:
    """The step's bytes but a jump's offset (written once the addresses are known)."""
    if step.command_id == "raw":
        return bytes(step.raw)
    if step.command_id == "value":
        operation = next(operation for operation in info.operations if operation["id"] == step.operation)
        if step.operand == "variable":
            return bytes([operation["variable_op_code"], step.value & 0xFF])
        kind = _number_kind(info, step.value, step.operand)
        step.operand = kind
        size = 2 if kind == "int16" else 1
        return bytes([operation["number_op_codes"][kind]]) + step.value.to_bytes(size, "little", signed=kind != "ubyte")
    if step.is_jump:
        condition = next(condition for condition in info.conditions if condition["id"] == step.condition)
        step.op_code = condition["op_codes"]["int16" if step.jump_int16 else "sbyte"]
        return bytes([step.op_code]) + bytes(2 if step.jump_int16 else 1)
    command = info.command_by_id[step.command_id]
    if step.op_code not in command["op_codes"]:
        step.op_code = command["op_codes"][0]
    return bytes([step.op_code]) + (bytes([step.value & 0xFF]) if command["params"] else b"")


def script_bytes(info: CameraScriptInfo, steps: list) -> bytes:
    """The script the steps make. A jump whose 8-bit offset no longer reaches its step becomes
    the int16 form (which moves what follows: repeated until every offset fits)."""
    while True:
        bodies = [_step_body(info, step) for step in steps]
        addresses, address = {}, 0
        for step, body in zip(steps, bodies):
            addresses[id(step)] = address
            address += len(body)
        end = address
        grown = False
        data = bytearray()
        for step, body in zip(steps, bodies):
            body = bytearray(body)
            if step.is_jump:
                here = addresses[id(step)]
                if step.raw_offset is not None:
                    offset = step.raw_offset
                else:
                    offset = (end if step.target is None or id(step.target) not in addresses
                              else addresses[id(step.target)]) - here
                if not step.jump_int16 and not -128 <= offset <= 127:
                    step.jump_int16 = True
                    grown = True
                    break
                body[1:] = offset.to_bytes(2 if step.jump_int16 else 1, "little", signed=True)
            data += body
        if not grown:
            return bytes(data)


def jump_sources(steps: list) -> dict:
    """{id(step): [index of each step that jumps to it]}, to show where a loop comes back."""
    sources = {}
    for index, step in enumerate(steps):
        if step.is_jump and step.raw_offset is None and step.target is not None:
            sources.setdefault(id(step.target), []).append(index)
    return sources


def new_step(info: CameraScriptInfo, command_id: str) -> ScriptStep:
    """A step as it starts when the user picks a command (a jump starts at the end of the script)."""
    command = info.command_by_id[command_id]
    step = ScriptStep(command_id, command["op_codes"][0])
    if command_id == "value":
        step.operation, step.operand = "set", "sbyte"
    elif command_id == "jump":
        step.condition = "always"
    return step



def reachable_steps(steps: list) -> set:
    """id() of the steps a run can reach from the first one (the others are filler: never run)."""
    seen, todo = set(), [0] if steps else []
    index_of = {id(step): index for index, step in enumerate(steps)}
    while todo:
        index = todo.pop()
        if not 0 <= index < len(steps) or id(steps[index]) in seen:
            continue
        step = steps[index]
        seen.add(id(step))
        if step.command_id in ("end", "raw", "hang"):
            continue
        if step.is_jump:
            if step.raw_offset is None and step.target is not None and id(step.target) in index_of:
                todo.append(index_of[id(step.target)])
            if step.condition == "always":
                continue
        todo.append(index + 1)
    return seen
