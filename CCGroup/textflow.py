"""
The text flow of a card player's script: its messages, card games and branches, in script order.

The script is cut into the structured if/else / while blocks the field-script compiler emits
(see jsmvariant): ``<condition> JPF +n`` skips the "then" block when the condition is false,
a JMP ending that block skips the "else" block, and a JMP back to the condition makes a loop.

A message is "on the path" of a card game unless an if/else puts them on opposite sides: such a
message is never shown in the same talk as that card game (another variant's question, the
NPC's normal talk on the other button...). The roles only look at the messages on the path, so
the variants of one script each get their own: the card question is the last question before
the card game, "not enough cards" the first message after it, the others are dialogue.
"""
from CCGroup.jsmcardgame import JsmCardGameFile, CardGamePlayer, OPCODE_PSHN_L
from CCGroup.jsmnpc import (MESSAGE_OPCODES, QUESTION_OPCODES, ROLE_QUESTION, ROLE_NOT_ENOUGH, ROLE_DIALOGUE,
                            CARD_BUTTON_TEMP, script_bounds)
from CCGroup.jsmvariant import (OPCODE_JMP, OPCODE_JPF, OPCODE_PSHI_L, OPCODE_POPI_L, OPCODE_RND,
                                CARDGAME_OPCODE, I0_RESULT_OPCODES, CAL_EQ, CAL_NT, CAL_LS, build_expression,
                                i0_random_indexes)

OPCODE_RET = 0x06

# What I[0] holds when a branch tests it (or ("answer", message id, first choice line))
I0_TALK_BUTTON = "button"  # the talk's start: CARD_BUTTON_TEMP when the card button started it, else 0
I0_RANDOM = "random"
I0_CARD_GAME = "card game"  # after CARDGAME: I[0] = cards the player owns, I[1] = the match result
MIN_OWNED_CARDS = 5
MATCH_RESULTS = {0: ("won", "did not win"), 1: ("lost", "did not lose"), 2: ("drew", "did not draw"),
                 -1: ("refused the rules", "accepted the rules")}


def _tokens_text(tokens):
    return "".join(token if isinstance(token, str) else str(token.value) for token in tokens)


class FlowMessage:
    """A message box the script shows. message_id None: chosen while the game runs."""

    def __init__(self, instruction_index: int, opcode: int, message_id, path: tuple):
        self.instruction_index = instruction_index
        self.message_id = message_id
        self.is_question = opcode in QUESTION_OPCODES
        self.path = path  # ((branch instruction index, side), ...) from the outermost block
        self.role = None  # set for the selected card game (ROLE_*)
        self.on_path = True


class FlowCardGame:
    """A CARDGAME call of the script."""

    def __init__(self, instruction_index: int, player: CardGamePlayer, path: tuple):
        self.instruction_index = instruction_index
        self.player = player
        self.path = path
        self.on_path = True


class FlowExit:
    """A jump out of the script part (e.g. into the NPC's own talk after an added card game)."""

    def __init__(self, instruction_index: int, path: tuple):
        self.instruction_index = instruction_index
        self.path = path
        self.on_path = True


class FlowBranch:
    """An if/else or a while loop. condition: the decoded test (see condition_parts), None when
    the test is not a plain push/CAL expression."""

    def __init__(self, jpf_index: int, is_loop: bool, condition, path: tuple):
        self.jpf_index = jpf_index
        self.is_loop = is_loop
        self.condition = condition
        self.then_nodes = []
        self.else_nodes = None  # None: no else block
        self.path = path
        self.on_path = True


class Condition:
    """A branch test, readable: kind "button" (card / talk button), "answer" (the line picked in a
    question), else "expression" with its text and the text of its else block."""

    def __init__(self, kind: str, text: str = "", negated_text: str = "", equals: bool = True,
                 message_id: int = None, line: int = None):
        self.kind = kind
        self.text = text
        self.negated_text = negated_text
        self.equals = equals  # "button": the card button (True) or the talk button; "answer": == or !=
        self.message_id = message_id
        self.line = line  # "answer": the message line of the choice


class TextFlow:
    """The flow of the script holding a card player's CARDGAME, with each node's role and on_path
    set for that card game."""

    def __init__(self, jsm_file: JsmCardGameFile, player: CardGamePlayer):
        self.jsm_file = jsm_file
        self.player = player
        self.instructions = jsm_file.instructions()
        self.cardgame_index = (player.cardgame_file_offset - jsm_file.offset_script) // 4
        self.start, self.end = script_bounds(jsm_file, self.cardgame_index)
        self.__players = {(other.cardgame_file_offset - jsm_file.offset_script) // 4: other
                          for other in jsm_file.players}
        self.__random_indexes = i0_random_indexes(self.instructions, self.start, self.end)
        self.__i0 = self.__i0_sources()
        self.nodes = self.__parse(self.start, self.end, ())
        selected_path = next((node.path for node in self.walk() if isinstance(node, FlowCardGame)
                              and node.instruction_index == self.cardgame_index), ())
        self.selected_sides = dict(selected_path)  # branch -> side leading to the selected card game
        self.__set_on_path()
        self.__set_roles()

    def walk(self, nodes=None):
        """Every node in script order (a branch before its blocks)."""
        for node in self.nodes if nodes is None else nodes:
            yield node
            if isinstance(node, FlowBranch):
                yield from self.walk(node.then_nodes)
                if node.else_nodes is not None:
                    yield from self.walk(node.else_nodes)

    def messages(self):
        return [node for node in self.walk() if isinstance(node, FlowMessage)]

    # ------------------------------------------------------------------ parsing

    def __parse(self, start: int, end: int, path: tuple):
        nodes = []
        index = start
        while index < end:
            opcode, param = self.instructions[index]
            branch = self.__branch_at(index, end, path) if opcode == OPCODE_JPF else None
            if branch is not None:
                nodes.append(branch[0])
                index = branch[1]
                continue
            nb_values = MESSAGE_OPCODES.get(opcode)
            if nb_values is not None and index - nb_values + 1 >= self.start:
                push_opcode, message_id = self.instructions[index - nb_values + 1]
                nodes.append(FlowMessage(index, opcode, message_id if push_opcode == OPCODE_PSHN_L else None, path))
            elif opcode == CARDGAME_OPCODE and index in self.__players:
                nodes.append(FlowCardGame(index, self.__players[index], path))
            elif opcode == OPCODE_JMP and param is not None and not self.start <= index + param < self.end:
                nodes.append(FlowExit(index, path))
            index += 1
        return nodes

    def __branch_at(self, jpf_index: int, end: int, path: tuple):
        """(FlowBranch, index after it) for a structured JPF, else None."""
        param = self.instructions[jpf_index][1]
        if param is None or param <= 0 or jpf_index + param > end:
            return None
        target = jpf_index + param
        then_end, else_end, is_loop = target, None, False
        jump_opcode, jump_param = self.instructions[target - 1]
        if target - 1 > jpf_index and jump_opcode == OPCODE_JMP and jump_param is not None:
            if jump_param < 0 and target - 1 + jump_param <= jpf_index:
                then_end, is_loop = target - 1, True
            elif jump_param > 0 and target - 1 + jump_param <= end:
                then_end, else_end = target - 1, target - 1 + jump_param
        elif self.instructions[target - 1][0] == OPCODE_RET and target < end:
            else_end = end  # the "then" block returns: the rest of the block only runs otherwise
        branch = FlowBranch(jpf_index, is_loop, self.__condition(jpf_index), path)
        branch.then_nodes = self.__parse(jpf_index + 1, then_end, path + ((jpf_index, True),))
        if else_end is not None:
            branch.else_nodes = self.__parse(target, else_end, path + ((jpf_index, False),))
        return branch, else_end if else_end is not None else target

    # ------------------------------------------------------------------ conditions

    def __i0_sources(self):
        """What I[0] holds at each instruction of the script (I0_*, ("answer", message id, first choice
        line), or None), following the control flow from the script start."""
        sources = {}
        stack = [(self.start, I0_TALK_BUTTON)]
        while stack:
            index, source = stack.pop()
            while self.start <= index < self.end and index not in sources:
                sources[index] = source
                opcode, param = self.instructions[index]
                if opcode == OPCODE_RND:
                    source = I0_RANDOM
                elif opcode in QUESTION_OPCODES:
                    nb_values = MESSAGE_OPCODES[opcode]
                    (push_opcode, message_id), (first_opcode, first_line) = self.instructions[
                        index - nb_values + 1:index - nb_values + 3]
                    source = ("answer", message_id, first_line)                         if push_opcode == OPCODE_PSHN_L and first_opcode == OPCODE_PSHN_L else None
                elif opcode == CARDGAME_OPCODE:
                    source = I0_CARD_GAME
                elif opcode in I0_RESULT_OPCODES or (opcode == OPCODE_POPI_L and param == 0):
                    source = None
                if opcode == OPCODE_JMP and param is not None:
                    index += param
                    continue
                if opcode == OPCODE_JPF and param is not None:
                    stack.append((index + param, source))
                if opcode == OPCODE_RET:
                    break
                index += 1
        return sources

    def __condition(self, jpf_index: int):
        expression = build_expression(self.instructions, jpf_index, self.start, self.jsm_file.offset_script,
                                      {}, self.__random_indexes)
        if expression is None:
            return None
        source = self.__i0.get(jpf_index)
        operands = expression.operands
        if (expression.kind == "binary" and len(operands) == 2 and operands[0].kind == "name"
                and operands[1].kind == "literal"):
            name, value = operands[0].value, operands[1].value.value
            equals = expression.operator == CAL_EQ
            if expression.operator in (CAL_EQ, CAL_NT) and name == "I[0]":
                if source == I0_TALK_BUTTON and value in (0, CARD_BUTTON_TEMP):
                    # SCRIPT_LBL zeroes the temp vars, then I[0] = 1 when the card button started the talk
                    return Condition("button", equals=equals == (value == CARD_BUTTON_TEMP))
                if isinstance(source, tuple):
                    return Condition("answer", equals=equals, message_id=source[1], line=source[2] + value)
            if source == I0_CARD_GAME:
                if name == "I[0]" and expression.operator == CAL_LS and value == MIN_OWNED_CARDS:
                    return Condition("expression", f"the player has fewer than {MIN_OWNED_CARDS} cards (no match)",
                                     f"the player has {MIN_OWNED_CARDS} cards or more")
                if name == "I[1]" and expression.operator in (CAL_EQ, CAL_NT) and value in MATCH_RESULTS:
                    results = MATCH_RESULTS[value]
                    return Condition("expression", f"the player {results[0 if equals else 1]}",
                                     f"the player {results[1 if equals else 0]}")
        return Condition("expression", _tokens_text(expression.tokens()), _tokens_text(expression.tokens(negate=True)))

    # ------------------------------------------------------------------ selected card game

    def side_on_path(self, branch: FlowBranch, side: bool):
        """Whether a block of a branch (then: True) can run in the same talk as the selected card game."""
        return branch.on_path and self.selected_sides.get(branch.jpf_index, side) == side

    def __set_on_path(self):
        for node in self.walk():
            node.on_path = all(self.selected_sides.get(branch, side) == side for branch, side in node.path)

    def __set_roles(self):
        """The card question is the last question on the path before the card game (a menu asked
        before it, like the Queen's pub talk, is dialogue)."""
        on_path = [message for message in self.messages() if message.message_id is not None and message.on_path]
        question = next((message for message in reversed(on_path) if message.is_question
                         and message.instruction_index < self.cardgame_index), None)
        not_enough = next((message for message in on_path if message.instruction_index > self.cardgame_index), None)
        for message in self.messages():
            if message.message_id is None:
                continue
            message.role = ROLE_QUESTION if message is question else ROLE_NOT_ENOUGH if message is not_enough                 else ROLE_DIALOGUE
