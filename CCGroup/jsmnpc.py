"""
NPCs of a field script: which ones play cards, the texts of their card game, and giving a card
game to one that has none.

A vanilla card NPC's talk script (e.g. seito6 in bghall_1) is always the same recipe:

    UCOFF; PCTURN                          the NPC turns to the player
    REQEW cardgamemaster.<region>_maeshori0   copy the region's rules into vars 292/293
    AASK "Will you play cards with me? / Yes / No"
    if answer == Yes:
        push Deck ID, var 292, var 293, rare %, AI search, AI strategy, levels; CARDGAME
        if I[0] < 5: AMESW "You need 5 or more cards to play."
        else:        REQEW cardgamemaster.<region>_shori0   (the Queen's rule spreading)
    var 292 = 0; UCON; RET

Adding a card game appends that recipe at the end of the script data and points the NPC's talk
entry at it (append-only: no existing byte moves, so no other script or jump can break). In the
maps that have the cardgamemaster entity (every map with a vanilla card player), its two calls are
copied from an existing card player of the same map. In the other maps the rules are read straight
from the region's savemap variables (272 + region / 280 + region): same rules, but without the
Queen of Cards' rule spreading.
"""
import struct
from collections import Counter

from CCGroup.jsmcardgame import (JsmCardGameFile, CardGamePlayer, OPCODE_PSHN_L, OPCODE_PSHI_L, OPCODE_PSHM_B,
                                 OPCODE_POPM_B, OPCODE_CAL, CARDGAME_DWORD)
from CCGroup.jsmvariant import decode_instructions, CAL_EQ, CAL_LS

REGIONS = ["bal", "gal", "tra", "cen", "dol", "fsh", "spa", "est"]
REGION_NAMES = ["Balamb", "Galbadia", "Trabia", "Centra", "Dollet", "Fisherman's Horizon", "Space", "Esthar"]
VAR_REGION_RULES = 272  # + region index
VAR_REGION_TRADE = 280  # + region index
VAR_CURRENT_RULES = 292

OPCODE_JMP = 0x02
OPCODE_JPF = 0x03
OPCODE_LBL = 0x05
OPCODE_RET = 0x06
OPCODE_UCON = 0x4D
OPCODE_UCOFF = 0x4E
OPCODE_PCTURN = 0x92
OPCODE_AASK = 0x6F
OPCODE_AMESW = 0x64
REQ_OPCODES = set(range(0x14, 0x1A))  # REQ, REQSW, REQEW, PREQ, PREQSW, PREQEW
# Message opcodes: number of values popped (the message id is always the 2nd value pushed)
MESSAGE_OPCODES = {0x46: 2, 0x47: 2, 0x4A: 6, 0x64: 4, 0x65: 4, 0x6F: 8}
QUESTION_OPCODES = (0x4A, 0x6F)

# Window of the vanilla card questions (seito6 & co)
MESSAGE_X, MESSAGE_Y = 180, 20
DEFAULT_QUESTION = "Will you play cards with me?\nYes\nNo"
DEFAULT_NOT_ENOUGH_CARDS = "You need 5 or more\ncards to play."
# Starting values of an added card game (edited afterwards like any card player)
DEFAULT_CARD_GAME = [0, 0, 0, 0, 0, 0, 0b11]  # Deck ID 0, rules/trade replaced below, 0 %, AI 0/0, Lv1-2

ON_NO_NOTHING = "nothing"
ON_NO_ORIGINAL = "original"

ROLE_QUESTION = "Question"
ROLE_NOT_ENOUGH = "Not enough cards"
ROLE_DIALOGUE = "Dialogue"


def encode(opcode: int, param: int = 0):
    """4-byte instruction: opcode in the high byte and a 24-bit param, or the zero-high-byte
    form for the opcodes >= 0x100 (CARDGAME)."""
    if opcode >= 0x100:
        return struct.pack("<I", opcode)
    return struct.pack("<I", (opcode << 24) | (param & 0xFFFFFF))


class NpcEntity:
    """An entity with a model and a talk script: an NPC the player can talk to."""

    def __init__(self, entity_name: str, talk_script: int, model_index: int, players: list):
        self.entity_name = entity_name
        self.talk_script = talk_script  # script index of its talk method
        self.model_index = model_index
        self.players = players  # its CARDGAME calls (empty: no card game)
        self.is_main_character = False  # its model is a party member's (set by the folder manager)

    def plays_cards(self):
        return bool(self.players)


def entities(jsm_file: JsmCardGameFile):
    """(entity name, first script index, number of scripts) sorted by first script."""
    nb_entity = sum(jsm_file.data[0:4])
    entries = sorted((struct.unpack_from("<H", jsm_file.data, 8 + 2 * index)[0] for index in range(nb_entity)),
                     key=lambda entry: entry >> 7)
    result = []
    for entry in entries:
        first = entry >> 7
        if first < len(jsm_file.script_names) and jsm_file.script_names[first] is not None:
            result.append((jsm_file.script_names[first][0], first, (entry & 0x7F) + 1))
    return result


def talk_script_index(jsm_file: JsmCardGameFile, first: int, count: int):
    """The entity's talk method: the script named "talk", else (no .sym names) the 3rd script."""
    for script_index in range(first, first + count):
        name = jsm_file.script_names[script_index] if script_index < len(jsm_file.script_names) else None
        if name is not None and name[1] == "talk":
            return script_index
    if not jsm_file.names_from_sym and count > 2:
        return first + 2
    return None


def list_npcs(jsm_file: JsmCardGameFile):
    """Every entity with a model (SETMODEL) and a talk script, card players included."""
    npcs = []
    for entity_name, first, count in entities(jsm_file):
        talk = talk_script_index(jsm_file, first, count)
        if talk is None:
            continue
        model_index = jsm_file.entity_model_index(entity_name)
        if model_index is None:
            continue
        players = [player for player in jsm_file.players if player.entity_name == entity_name]
        npcs.append(NpcEntity(entity_name, talk, model_index, players))
    return npcs


def has_card_master(jsm_file: JsmCardGameFile):
    return any(name is not None and name[0].startswith("cardgamemaster") for name in jsm_file.script_names)


def script_bounds(jsm_file: JsmCardGameFile, instruction_index: int):
    """(start, end) instruction indexes of the script holding an instruction."""
    offset = instruction_index * 4
    start = max((position for position in jsm_file.script_positions if position <= offset), default=0)
    end = min((position for position in jsm_file.script_positions if position > offset),
              default=len(jsm_file.data) - jsm_file.offset_script)
    return start // 4, end // 4


def card_master_calls(jsm_file: JsmCardGameFile):
    """The cardgamemaster calls of an existing card player of this map: {"maeshori": 3 encoded
    instructions (push priority, push label, REQ*), "shori": same, "region": "bal"...}, or None."""
    instructions = jsm_file.instructions()
    for player in jsm_file.players:
        cardgame_index = (player.cardgame_file_offset - jsm_file.offset_script) // 4
        start, end = script_bounds(jsm_file, cardgame_index)
        calls = {}
        for index in range(start + 2, end):
            opcode, _ = instructions[index]
            if opcode not in REQ_OPCODES or instructions[index - 1][0] != OPCODE_PSHN_L \
                    or instructions[index - 2][0] != OPCODE_PSHN_L:
                continue
            label = instructions[index - 1][1]
            name = jsm_file.script_names[label] if 0 <= label < len(jsm_file.script_names) else None
            if name is None:
                continue
            raw = bytes(jsm_file.data[jsm_file.offset_script + (index - 2) * 4:jsm_file.offset_script + (index + 1) * 4])
            if name[1].endswith("_maeshori0") and index < cardgame_index and "maeshori" not in calls:
                calls["maeshori"] = raw
                calls["region"] = name[1][:3]
            elif name[1].endswith("_shori0") and index > cardgame_index and "shori" not in calls:
                calls["shori"] = raw
        if "maeshori" in calls and "shori" in calls:
            return calls
    return None


def region_by_folder(files):
    """Most used region per map-folder prefix ("bg" -> "bal"...), from the maps' card players."""
    votes = {}
    for jsm_file in files:
        calls = card_master_calls(jsm_file) if jsm_file.players else None
        if calls is not None:
            votes.setdefault(jsm_file.map_name[:2], Counter())[calls["region"]] += 1
    return {prefix: counter.most_common(1)[0][0] for prefix, counter in votes.items()}


class MessageUse:
    """A message a card player's script shows."""

    def __init__(self, role: str, message_id: int, instruction_index: int):
        self.role = role
        self.message_id = message_id
        self.instruction_index = instruction_index


def player_messages(jsm_file: JsmCardGameFile, player: CardGamePlayer):
    """The messages of the script holding a CARDGAME, in script order, with their role: the
    yes/no question before the match, the "not enough cards" line right after it, other lines."""
    instructions = jsm_file.instructions()
    cardgame_index = (player.cardgame_file_offset - jsm_file.offset_script) // 4
    start, end = script_bounds(jsm_file, cardgame_index)
    uses = []
    first_after = True
    for index in range(start, end):
        opcode, _ = instructions[index]
        nb_values = MESSAGE_OPCODES.get(opcode)
        if nb_values is None or index < nb_values:
            continue
        push_opcode, message_id = instructions[index - nb_values + 1]
        if push_opcode != OPCODE_PSHN_L:
            continue  # message chosen at runtime
        if index < cardgame_index:
            role = ROLE_QUESTION if opcode in QUESTION_OPCODES else ROLE_DIALOGUE
        elif first_after:
            role, first_after = ROLE_NOT_ENOUGH, False
        else:
            role = ROLE_DIALOGUE
        uses.append(MessageUse(role, message_id, index))
    return uses


def build_card_game_block(label: int, question_id: int, not_enough_id: int, card_game: list, calls=None,
                          region: int = 0, original_talk_index: int = None, block_start: int = 0):
    """Instructions (bytes) of an added card game talk script. card_game = the 7 CARDGAME values
    (the rules / trade ones are replaced by the region's). original_talk_index = where the
    player's "No" jumps (the original talk code, after its LBL), None = end silently."""
    code = []

    def add(opcode, param=0):
        code.append(encode(opcode, param))
        return len(code) - 1

    def add_raw(raw: bytes):
        for offset in range(0, len(raw), 4):
            code.append(raw[offset:offset + 4])

    def patch_jump(index, target):
        opcode = struct.unpack("<I", code[index])[0] >> 24
        code[index] = encode(opcode, target - index)

    add(OPCODE_LBL, label)
    add(OPCODE_UCOFF)
    add(OPCODE_PSHN_L, 0)
    add(OPCODE_PSHN_L, 12)
    add(OPCODE_PCTURN)
    if calls is not None:
        add_raw(calls["maeshori"])
    for value in (0, question_id, 1, 2, 1, 2, MESSAGE_X, MESSAGE_Y):  # channel, message, options 1-2, default 1, cancel 2
        add(OPCODE_PSHN_L, value)
    add(OPCODE_AASK)
    add(OPCODE_PSHI_L, 0)
    add(OPCODE_PSHN_L, 0)
    add(OPCODE_CAL, CAL_EQ)
    jump_no = add(OPCODE_JPF)
    for param_index, value in enumerate(card_game):
        if param_index == 1:  # game rules
            add(OPCODE_PSHM_B, VAR_CURRENT_RULES if calls is not None else VAR_REGION_RULES + region)
        elif param_index == 2:  # trade rule
            add(OPCODE_PSHM_B, VAR_CURRENT_RULES + 1 if calls is not None else VAR_REGION_TRADE + region)
        else:
            add(OPCODE_PSHN_L, value)
    code.append(struct.pack("<I", CARDGAME_DWORD))
    add(OPCODE_PSHI_L, 0)
    add(OPCODE_PSHN_L, 5)
    add(OPCODE_CAL, CAL_LS)
    jump_played = add(OPCODE_JPF)
    for value in (0, not_enough_id, MESSAGE_X, MESSAGE_Y):
        add(OPCODE_PSHN_L, value)
    add(OPCODE_AMESW)
    jump_cleanup = add(OPCODE_JMP)
    patch_jump(jump_played, len(code))
    if calls is not None:
        add_raw(calls["shori"])
    patch_jump(jump_cleanup, len(code))

    def add_end():
        if calls is not None:
            add(OPCODE_PSHN_L, 0)
            add(OPCODE_POPM_B, VAR_CURRENT_RULES)
        add(OPCODE_UCON)

    add_end()
    add(OPCODE_RET, 8)
    patch_jump(jump_no, len(code))
    add_end()
    if original_talk_index is None:
        add(OPCODE_RET, 8)
    else:
        jump = add(OPCODE_JMP)
        code[jump] = encode(OPCODE_JMP, original_talk_index - (block_start + jump))
    return b"".join(code)


def end_entry_index(jsm_file: JsmCardGameFile):
    """Index of the end-of-script entry: the script entry table holds one entry per script
    (entities' count + 1 each), then the end of the script data, then a 0 padding entry when
    needed to keep the table 4-byte aligned (checked on the vanilla fields: 424 without, 442 with)."""
    nb_entity = sum(jsm_file.data[0:4])
    return sum((struct.unpack_from("<H", jsm_file.data, 8 + 2 * index)[0] & 0x7F) + 1
               for index in range(nb_entity))


def add_card_game(jsm_file: JsmCardGameFile, npc: NpcEntity, question_id: int, not_enough_id: int,
                  region: int = 0, on_no: str = ON_NO_NOTHING, card_game=None):
    """Give an NPC a card game (append-only patch, see the module doc). Returns its new player."""
    if npc.plays_cards():
        raise ValueError(f"{npc.entity_name} already plays cards")
    calls = card_master_calls(jsm_file) if has_card_master(jsm_file) else None
    if has_card_master(jsm_file) and calls is None:
        raise ValueError("This map has a cardgamemaster but no card player to copy its calls from")
    card_game = list(card_game or DEFAULT_CARD_GAME)
    data = jsm_file.data
    offset_section1, offset_script = struct.unpack_from("<HH", data, 4)
    eof_entry = offset_section1 + end_entry_index(jsm_file) * 2
    (eof_value,) = struct.unpack_from("<H", data, eof_entry)
    if (eof_value & 0x7FFF) * 4 != len(data) - offset_script:
        raise ValueError("Unexpected script table layout (no end-of-script entry after the last script):"
                         " the card game cannot be added safely to this map")
    talk_entry = offset_section1 + npc.talk_script * 2
    (talk_value,) = struct.unpack_from("<H", data, talk_entry)
    original_talk_start = talk_value & 0x7FFF
    block_start = (len(data) - offset_script) // 4
    block = build_card_game_block(npc.talk_script, question_id, not_enough_id, card_game, calls, region,
                                  original_talk_start + 1 if on_no == ON_NO_ORIGINAL else None, block_start)
    new_eof = block_start + len(block) // 4
    if new_eof > 0x7FFF:
        raise ValueError("The script data would exceed the 128 KB the entry table can address")
    data.extend(block)
    struct.pack_into("<H", data, talk_entry, (talk_value & 0x8000) | block_start)
    struct.pack_into("<H", data, eof_entry, (eof_value & 0x8000) | new_eof)
    jsm_file.reanalyze()
    jsm_file.structure_modified = True
    return next(player for player in jsm_file.players
                if player.entity_name == npc.entity_name
                and (player.cardgame_file_offset - offset_script) // 4 >= block_start)
