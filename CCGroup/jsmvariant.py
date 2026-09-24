"""
Card-game "variants": when one NPC script holds several CARDGAME calls, which one plays.

Many NPCs have more than one CARDGAME call in the same script, each with its own deck,
rules and AI, and the script branches to one of them: on a random roll (Joker: RND < 85,
< 170, else - a third each) or on the story state (Dr. Kadowaki: bits of savemap var 475).

The branches are the structured if/else the field-script compiler emits:

    <condition> JPF +n        ; if the condition is false, skip the "then" block
      then block              ; ends with JMP +m when there is an else block
    else block                ; [JPF target, JMP target)

so the conditions that lead to a CARDGAME are the JPFs whose then/else region contains it.
Conditions shared by every CARDGAME of the script (e.g. "the player answered yes") are left
out: what remains is what picks one variant over another.

The literal operands of those conditions (85, 170, the bit masks...) are 4-byte PSHN_L
instructions that can be patched in place like the CARDGAME parameters.
"""
import struct

OPCODE_CAL = 0x01
OPCODE_JMP = 0x02
OPCODE_JPF = 0x03
OPCODE_PSHN_L = 0x07
OPCODE_PSHI_L = 0x08
OPCODE_POPI_L = 0x09
PUSH_VARIABLE_OPCODES = {0x0A: "", 0x0C: " (word)", 0x0E: " (long)",
                         0x10: " (signed)", 0x11: " (signed word)", 0x12: " (signed long)"}
OPCODE_PSHAC = 0x13
OPCODE_RND = 0xE8
CARDGAME_OPCODE = 0x13A
# Opcodes that leave a result in I[0] (other than RND): I[0] then no longer holds the random roll.
I0_RESULT_OPCODES = {0x4A, 0x5B, 0x66, 0x6D, 0x6E, 0x6F, 0x129, 0x136, 0x13A, 0x15E, 0x15F, 0x160}

CAL_ADD, CAL_SUB, CAL_MUL, CAL_DIV, CAL_MOD, CAL_MIN = range(6)
CAL_EQ, CAL_GT, CAL_GE, CAL_LS, CAL_LE, CAL_NT, CAL_AND, CAL_OR, CAL_EOR = range(6, 15)
CAL_SYMBOLS = {CAL_ADD: "+", CAL_SUB: "-", CAL_MUL: "*", CAL_DIV: "/", CAL_MOD: "%",
               CAL_EQ: "==", CAL_GT: ">", CAL_GE: ">=", CAL_LS: "<", CAL_LE: "<=", CAL_NT: "!=",
               CAL_AND: "&", CAL_OR: "|", CAL_EOR: "^"}
COMPARISON_NEGATION = {CAL_EQ: CAL_NT, CAL_NT: CAL_EQ, CAL_GT: CAL_LE, CAL_LE: CAL_GT,
                       CAL_GE: CAL_LS, CAL_LS: CAL_GE}
RANDOM_NAME = "random"
KNOWN_VARIABLES = {256: "story progress (var 256)"}
NB_RANDOM_VALUES = 256  # RND gives 0-255


def sign_extend_24(value: int):
    return value - 0x1000000 if value & 0x800000 else value


class ScriptLiteral:
    """A PSHN_L literal of a condition, editable in place."""

    def __init__(self, file_offset: int, value: int):
        self.file_offset = file_offset
        self.value = value
        self.original_value = value

    def is_modified(self):
        return self.value != self.original_value

    def to_dword(self):
        return (OPCODE_PSHN_L << 24) | (self.value & 0xFFFFFF)


class Expression:
    """Node of a condition: 'literal' (ScriptLiteral), 'name' (variable/register text),
    'unary' (negate) or 'binary' (CAL operator)."""

    def __init__(self, kind: str, value=None, operator: int = None, operands=()):
        self.kind = kind
        self.value = value
        self.operator = operator
        self.operands = list(operands)

    def names(self):
        if self.kind == "name":
            return {self.value}
        return set().union(*[operand.names() for operand in self.operands]) if self.operands else set()

    def literals(self):
        if self.kind == "literal":
            return [self.value]
        return [literal for operand in self.operands for literal in operand.literals()]

    def evaluate(self, env: dict):
        if self.kind == "literal":
            return self.value.value
        if self.kind == "name":
            return env[self.value]
        if self.kind == "unary":
            return -self.operands[0].evaluate(env)
        left, right = (operand.evaluate(env) for operand in self.operands)
        operator = self.operator
        if operator == CAL_ADD: return left + right
        if operator == CAL_SUB: return left - right
        if operator == CAL_MUL: return left * right
        if operator == CAL_DIV: return int(left / right) if right else 0
        if operator == CAL_MOD: return left % right if right else 0
        if operator == CAL_EQ: return int(left == right)
        if operator == CAL_GT: return int(left > right)
        if operator == CAL_GE: return int(left >= right)
        if operator == CAL_LS: return int(left < right)
        if operator == CAL_LE: return int(left <= right)
        if operator == CAL_NT: return int(left != right)
        if operator == CAL_AND: return left & right
        if operator == CAL_OR: return left | right
        return left ^ right

    def tokens(self, negate: bool = False, top: bool = True):
        """Infix rendering as a list of str and ScriptLiteral (the UI turns literals into
        spinboxes). ``negate`` renders the false branch (a comparison is inverted)."""
        if negate:
            if self.kind == "binary" and self.operator in COMPARISON_NEGATION:
                return Expression("binary", operator=COMPARISON_NEGATION[self.operator],
                                  operands=self.operands).tokens(top=top)
            return ["not ("] + self.tokens(top=True) + [")"]
        if self.kind == "literal":
            return [self.value]
        if self.kind == "name":
            return [self.value]
        if self.kind == "unary":
            return ["-"] + self.operands[0].tokens(top=False)
        inner = (self.operands[0].tokens(top=False) + [f" {CAL_SYMBOLS[self.operator]} "]
                 + self.operands[1].tokens(top=False))
        return inner if top else ["("] + inner + [")"]


class Condition:
    """One branch on the way to a CARDGAME: ``expression`` is true (then block) or false."""

    def __init__(self, jpf_index: int, expression: Expression, is_true: bool):
        self.jpf_index = jpf_index
        self.expression = expression
        self.is_true = is_true

    def key(self):
        return self.jpf_index, self.is_true

    def holds(self, env: dict):
        return bool(self.expression.evaluate(env)) == self.is_true

    def tokens(self):
        return self.expression.tokens(negate=not self.is_true)

    def text(self):
        return "".join(token if isinstance(token, str) else str(token.value) for token in self.tokens())


def decode_instructions(data: bytes, offset_script: int):
    """(opcode, param) per instruction; param is the sign-extended 24-bit value, None for the
    zero-high-byte encoding of opcodes >= 0x100."""
    instructions = []
    for offset in range(offset_script, len(data) - 3, 4):
        (dword,) = struct.unpack_from("<I", data, offset)
        if dword >> 24:
            instructions.append((dword >> 24, sign_extend_24(dword & 0xFFFFFF)))
        else:
            instructions.append((dword & 0xFFFF, None))
    return instructions


def i0_random_indexes(instructions: list, start: int, end: int):
    """Instruction indexes of the script where I[0] holds the RND roll, following the control
    flow from the script start (each instruction taken once, fall-through first)."""
    holds_random = set()
    visited = set()
    stack = [(start, False)]
    while stack:
        index, is_random = stack.pop()
        while start <= index < end and index not in visited:
            visited.add(index)
            if is_random:
                holds_random.add(index)
            opcode, param = instructions[index]
            if opcode == OPCODE_RND:
                is_random = True
            elif opcode in I0_RESULT_OPCODES or (opcode == OPCODE_POPI_L and param == 0):
                is_random = False
            if opcode == OPCODE_JMP and param is not None:
                index += param
                continue
            if opcode == OPCODE_JPF and param is not None:
                stack.append((index + param, is_random))
            if opcode == 0x06:  # RET
                break
            index += 1
    return holds_random


def build_expression(instructions: list, jpf_index: int, start: int, offset_script: int,
                     literals: dict, random_indexes: set):
    """Expression popped by the JPF at jpf_index, or None if it is not a plain push/CAL tree."""
    need = 1
    index = jpf_index - 1
    while index >= start:
        opcode, param = instructions[index]
        if opcode in (OPCODE_PSHN_L, OPCODE_PSHI_L, OPCODE_PSHAC) or opcode in PUSH_VARIABLE_OPCODES:
            need -= 1
        elif opcode == OPCODE_CAL and param == CAL_MIN:
            pass
        elif opcode == OPCODE_CAL and param in CAL_SYMBOLS:
            need += 1
        else:
            return None
        if need == 0:
            break
        index -= 1
    if need != 0:
        return None
    stack = []
    for position in range(index, jpf_index):
        opcode, param = instructions[position]
        if opcode == OPCODE_PSHN_L:
            file_offset = offset_script + position * 4
            literal = literals.setdefault(file_offset, ScriptLiteral(file_offset, param))
            stack.append(Expression("literal", literal))
        elif opcode == OPCODE_PSHI_L:
            name = RANDOM_NAME if param == 0 and position in random_indexes else f"I[{param}]"
            stack.append(Expression("name", name))
        elif opcode in PUSH_VARIABLE_OPCODES:
            known = KNOWN_VARIABLES.get(param)
            stack.append(Expression("name", known if known else f"var {param}{PUSH_VARIABLE_OPCODES[opcode]}"))
        elif opcode == OPCODE_PSHAC:
            stack.append(Expression("name", f"actor {param}"))
        elif param == CAL_MIN:
            stack.append(Expression("unary", operands=[stack.pop()]))
        else:
            right = stack.pop()
            stack.append(Expression("binary", operator=param, operands=[stack.pop(), right]))
    return stack[0]


class VariantInfo:
    """What picks this CARDGAME among the ones of the same script."""

    def __init__(self, conditions: list, siblings: list, index: int):
        self.conditions = conditions  # distinguishing Condition list (all must hold)
        self.siblings = siblings  # every CardGamePlayer of the script, this one included
        self.index = index  # position among the siblings (0-based)

    def is_variant(self):
        return len(self.siblings) > 1

    def literals(self):
        seen = []
        for condition in self.conditions:
            for literal in condition.expression.literals():
                if literal not in seen:
                    seen.append(literal)
        return seen

    def random_rolls(self):
        """The RND values (0-255) that pick this variant, or None when not decided by RND alone."""
        if not self.conditions:
            return None
        names = set().union(*[condition.expression.names() for condition in self.conditions])
        if names != {RANDOM_NAME}:
            return None
        return [roll for roll in range(NB_RANDOM_VALUES)
                if all(condition.holds({RANDOM_NAME: roll}) for condition in self.conditions)]

    def random_ranges_text(self):
        """e.g. 'random 85-169' (None when not decided by RND alone)."""
        rolls = self.random_rolls()
        if rolls is None:
            return None
        if not rolls:
            return "never"
        ranges = []
        first = previous = rolls[0]
        for roll in rolls[1:] + [None]:
            if roll is not None and roll == previous + 1:
                previous = roll
                continue
            ranges.append(f"{first}" if first == previous else f"{first}-{previous}")
            if roll is not None:
                first = previous = roll
        return f"{RANDOM_NAME} " + ", ".join(ranges)

    def random_chance(self):
        """Percentage of RND rolls that pick this variant, when only the random roll decides."""
        if not self.conditions:
            return None
        names = set().union(*[condition.expression.names() for condition in self.conditions])
        if names != {RANDOM_NAME}:
            return None
        matching = sum(1 for roll in range(NB_RANDOM_VALUES)
                       if all(condition.holds({RANDOM_NAME: roll}) for condition in self.conditions))
        return 100 * matching / NB_RANDOM_VALUES


def script_range(script_positions: list, script_data_size: int, instruction_offset: int):
    """(start, end) byte offsets of the script holding an instruction."""
    start = max((position for position in script_positions if position <= instruction_offset), default=0)
    end = min((position for position in script_positions if position > instruction_offset),
              default=script_data_size)
    return start, end


def analyze_variants(jsm_file):
    """Fill player.variant (VariantInfo) for every card player of a JsmCardGameFile, and
    jsm_file.script_literals (file offset -> ScriptLiteral) with the editable condition literals."""
    jsm_file.script_literals = {}
    if not jsm_file.players:
        return
    offset_script = jsm_file.offset_script
    instructions = decode_instructions(jsm_file.data, offset_script)
    players_by_script = {}
    for player in jsm_file.players:
        start, end = script_range(jsm_file.script_positions, len(jsm_file.data) - offset_script,
                                  player.cardgame_file_offset - offset_script)
        players_by_script.setdefault((start // 4, end // 4), []).append(player)

    for (start, end), players in players_by_script.items():
        random_indexes = i0_random_indexes(instructions, start, end)
        regions = []  # (first, end, jpf_index, is_true)
        for index in range(start, end):
            opcode, param = instructions[index]
            if opcode != OPCODE_JPF or param is None or param <= 0:
                continue
            target = index + param
            regions.append((index + 1, target, index, True))
            if start <= target - 1 < end:
                jump_opcode, jump_param = instructions[target - 1]
                if jump_opcode == OPCODE_JMP and jump_param is not None and jump_param > 0:
                    regions.append((target, target - 1 + jump_param, index, False))
        expressions = {}
        player_conditions = []
        for player in players:
            cardgame_index = (player.cardgame_file_offset - offset_script) // 4
            conditions = []
            for first, region_end, jpf_index, is_true in regions:
                if not first <= cardgame_index < region_end:
                    continue
                if jpf_index not in expressions:
                    expressions[jpf_index] = build_expression(instructions, jpf_index, start, offset_script,
                                                              jsm_file.script_literals, random_indexes)
                if expressions[jpf_index] is not None:
                    conditions.append(Condition(jpf_index, expressions[jpf_index], is_true))
            player_conditions.append(conditions)
        # Left out: the branches every call goes through, and the same test repeated in each branch
        # (e.g. "the player answered yes" asked again inside every variant).
        common = set.intersection(*[{condition.key() for condition in conditions}
                                    for conditions in player_conditions])
        common_texts = set.intersection(*[{condition.text() for condition in conditions}
                                          for conditions in player_conditions])
        for index, (player, conditions) in enumerate(zip(players, player_conditions)):
            distinguishing = [condition for condition in conditions
                              if condition.key() not in common and condition.text() not in common_texts]
            player.variant = VariantInfo(distinguishing, players, index)
