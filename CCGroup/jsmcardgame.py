"""
Parser/patcher for the CARDGAME (0x13A) calls inside field script files (.jsm).

A .jsm file contains the scripts of every entity of a field. The CARDGAME opcode
pops 7 bytes off the script stack to set up a Triple Triad match, so each call is
preceded by 7 push instructions. This module locates those calls, names them using
the matching .sym file, and lets the caller edit the pushed values in place
(instructions are fixed-size 4-byte words, so patching never moves any offset).

Reference: FF8ModdingWiki, Field Opcodes 13A_CARDGAME.
"""
import os
import struct

# Push opcodes (instruction = opcode << 24 | param24)
OPCODE_PSHN_L = 0x07  # push literal
OPCODE_PSHI_L = 0x08  # push temporary variable
OPCODE_PSHM_B = 0x0A  # push savemap variable (byte)
OPCODE_PSHM_W = 0x0C
OPCODE_PSHM_L = 0x0E
OPCODE_PSHSM_B = 0x10  # push savemap variable (signed)
OPCODE_PSHSM_W = 0x11
OPCODE_PSHSM_L = 0x12
OPCODE_PSHAC = 0x13
OPCODE_CAL = 0x01
OPCODE_POPM_B = 0x0B
OPCODE_RND = 0xE8  # I[0] = random 0-255
CAL_AND = 0x0C
CAL_OR = 0x0D

VARIABLE_PUSH_OPCODES = (OPCODE_PSHM_B, OPCODE_PSHM_W, OPCODE_PSHM_L,
                         OPCODE_PSHSM_B, OPCODE_PSHSM_W, OPCODE_PSHSM_L)
PUSH_OPCODES = (OPCODE_PSHN_L, OPCODE_PSHI_L, OPCODE_PSHAC) + VARIABLE_PUSH_OPCODES

CARDGAME_DWORD = 0x0000013A  # opcodes >= 0x100 are stored with a zero high byte
NB_CARDGAME_PARAMS = 7
# SETCARD pops the card id (pushed last) then the location (pushed first) and moves the card there.
SETCARD_DWORD = 0x0000015E

# Savemap variables conventionally used by the card-game scripts.
# 292/293 are filled by the cardgamemaster "maeshori" script with the ruleset of the
# current region (the one the Queen of Cards spreads/abolishes rules in).
VAR_CURRENT_REGION_GAME_RULES = 292
VAR_CURRENT_REGION_TRADE_RULE = 293
# A few NPCs push their level mask from a savemap variable that their own map script rolls
# at random right before the match (e.g. the bghall_1 students: var 1041 = one of 7, 11, 13,
# 14, 15; Joker: var 1024 = (random & 31) | 22). Those variables (1024+) are per-map scratch
# variables: another map does not set them. See JsmCardGameFile.level_mask_options.

# The 7 parameters in push order (first pushed -> last pushed)
PARAM_DECK_ID = 0
PARAM_GAME_RULES = 1
PARAM_TRADE_RULES = 2
PARAM_RARE_CHANCE = 3
PARAM_AI_SEARCH = 4
PARAM_AI_STRATEGY = 5
PARAM_LEVEL_MASK = 6

PARAM_NAMES = ["Deck ID", "Game rules", "Trade rules", "Rare card chance",
               "AI search profile", "AI strategy profile", "Allowed card levels"]

GAME_RULE_BITS = [(0x01, "Open"), (0x02, "Same"), (0x04, "Plus"), (0x08, "Random"),
                  (0x10, "Sudden Death"), (0x40, "Same Wall"), (0x80, "Elemental")]

TRADE_RULE_NAMES = ["None", "One", "Difference", "Direct", "All"]

AI_STRATEGY_NAMES = ["0 - Territory (weakest)", "1 - Hoarder (keeps strong cards in hand)",
                     "2 - Power-hungry (plays/defends strong cards)", "3 - Territory + randomness",
                     "4 - Greedy (overvalues its own captures)", "5 - Very greedy",
                     "6 - Territory (same as 0)", "7 - Territory (same as 0)"]

AI_SEARCH_DEPTH_NAMES = ["0 - Beginner (greedy, ~1 move ahead)", "1 - Very shallow (~2 moves mid-game)",
                         "2 - Shallow", "3 - Average (up to 3 moves ahead)",
                         "4 - Good (up to 4 moves ahead)", "5 - Strong",
                         "6 - Very strong", "7 - Grandmaster (deepest search)"]
AI_SEARCH_NO_GUESS_BIT = 0x10


class CardGameParam:
    """One of the 7 values pushed before a CARDGAME call (a single 4-byte instruction)."""

    def __init__(self, param_index: int, file_offset: int, opcode: int, value: int):
        self.param_index = param_index
        self.name = PARAM_NAMES[param_index]
        self.file_offset = file_offset  # absolute offset of the push instruction in the .jsm
        self.opcode = opcode
        self.value = value
        self.original_opcode = opcode
        self.original_value = value

    def is_literal(self):
        return self.opcode == OPCODE_PSHN_L

    def is_variable(self):
        return self.opcode in VARIABLE_PUSH_OPCODES

    def is_editable(self):
        # A literal can be edited, and a variable push can be overridden by a literal
        return self.is_literal() or self.is_variable()

    def is_modified(self):
        return self.opcode != self.original_opcode or self.value != self.original_value

    def set_literal(self, value: int):
        """Set a literal value (overrides a variable push if there was one)."""
        self.opcode = OPCODE_PSHN_L
        self.value = value & 0xFFFFFF

    def set_variable(self, variable: int, opcode: int = OPCODE_PSHM_B):
        """Make the param read a savemap variable instead of a literal."""
        self.opcode = opcode
        self.value = variable & 0xFFFFFF

    def restore_original(self):
        self.opcode = self.original_opcode
        self.value = self.original_value

    def to_dword(self):
        return (self.opcode << 24) | (self.value & 0xFFFFFF)


class CardGamePlayer:
    """One CARDGAME call: an NPC (entity script) that starts a Triple Triad match."""

    def __init__(self, entity_name: str, script_name: str, cardgame_file_offset: int, params: list):
        self.entity_name = entity_name
        self.script_name = script_name
        self.cardgame_file_offset = cardgame_file_offset
        self.params = params  # list of 7 CardGameParam in push order

    def is_modified(self):
        return any(param.is_modified() for param in self.params)

    def __str__(self):
        return f"{self.entity_name}::{self.script_name} @0x{self.cardgame_file_offset:X}"


class LevelMaskOption:
    """One way a field script sets a level-mask variable: a fixed value, or a random roll
    ``(random & random_bits) | always_bits``."""

    def __init__(self, always_bits: int, random_bits: int = 0):
        self.always_bits = always_bits & 0xFF
        self.random_bits = random_bits & 0xFF

    def is_random(self):
        return bool(self.random_bits & ~self.always_bits)

    def union_mask(self):
        """Every level this option can enable."""
        return self.always_bits | self.random_bits

    def roll(self, rng):
        return (rng.randrange(256) & self.random_bits) | self.always_bits

    def __eq__(self, other):
        return (isinstance(other, LevelMaskOption) and self.always_bits == other.always_bits
                and self.random_bits == other.random_bits)

    def __hash__(self):
        return hash((self.always_bits, self.random_bits))

    def __repr__(self):
        if self.is_random():
            return f"LevelMaskOption((rnd & {self.random_bits}) | {self.always_bits})"
        return f"LevelMaskOption({self.always_bits})"


class CardMove:
    """A SETCARD with literal arguments: a script moving a card to a location (Deck ID)."""

    def __init__(self, map_name: str, entity_name: str, script_name: str, card_id: int, location: int):
        self.map_name = map_name
        self.entity_name = entity_name
        self.script_name = script_name
        self.card_id = card_id
        self.location = location

    def __str__(self):
        return f"{self.map_name} {self.entity_name}::{self.script_name}: card {self.card_id} -> {self.location}"


class JsmCardGameFile:
    """A .jsm field script file and the card players found inside it."""

    def __init__(self, jsm_path: str, sym_path: str = ""):
        self.jsm_path = jsm_path
        self.sym_path = sym_path
        self.map_name = os.path.splitext(os.path.basename(jsm_path))[0]
        with open(jsm_path, "rb") as jsm_file:
            self.data = bytearray(jsm_file.read())
        self.players = []
        self.card_moves = []  # SETCARD calls with literal arguments
        self.__analyze()

    def __analyze(self):
        if len(self.data) < 8:
            return
        nb_entity = self.data[0] + self.data[1] + self.data[2] + self.data[3]
        offset_section1, offset_script = struct.unpack_from("<HH", self.data, 4)
        if offset_script > len(self.data) or offset_section1 > offset_script:
            return

        # Entry point of each script: position relative to the script data, in dwords
        nb_script_entries = (offset_script - offset_section1) // 2
        script_positions = []
        for entry_index in range(nb_script_entries):
            entry = struct.unpack_from("<H", self.data, offset_section1 + entry_index * 2)[0]
            script_positions.append((entry & 0x7FFF) * 4)

        script_names = self.__read_script_names(nb_entity)

        script_data_size = len(self.data) - offset_script
        nb_instruction = script_data_size // 4
        for instruction_index in range(nb_instruction):
            instruction_offset = instruction_index * 4
            (dword,) = struct.unpack_from("<I", self.data, offset_script + instruction_offset)
            if dword == SETCARD_DWORD and instruction_index >= 2:
                self.__add_card_move(offset_script, instruction_offset, script_positions, script_names,
                                     script_data_size)
                continue
            if dword != CARDGAME_DWORD:
                continue
            if instruction_index < NB_CARDGAME_PARAMS:
                continue
            params = []
            for param_index in range(NB_CARDGAME_PARAMS):
                push_offset = instruction_offset - (NB_CARDGAME_PARAMS - param_index) * 4
                (push_dword,) = struct.unpack_from("<I", self.data, offset_script + push_offset)
                params.append(CardGameParam(param_index, offset_script + push_offset,
                                            push_dword >> 24, push_dword & 0xFFFFFF))
            entity_name, script_name = self.__find_script_name(instruction_offset, script_positions,
                                                               script_names, script_data_size)
            self.players.append(CardGamePlayer(entity_name, script_name,
                                               offset_script + instruction_offset, params))

    def __instructions(self):
        """(opcode, param) of every instruction of the script section."""
        offset_script = struct.unpack_from("<H", self.data, 6)[0]
        instructions = []
        for offset in range(offset_script, len(self.data) - 3, 4):
            (dword,) = struct.unpack_from("<I", self.data, offset)
            instructions.append((dword >> 24, dword & 0xFFFFFF) if dword >> 24 else (dword & 0xFFFF, None))
        return instructions

    def level_mask_options(self, variable: int):
        """How the scripts of this map write a level-mask variable, from the patterns the vanilla
        card players use: ``PSHN_L x / POPM_B var`` (fixed value) and
        ``PSHM_B var / PSHN_L a / CAL AND / POPM_B var`` + ``... CAL OR ...`` on a random byte
        (``RND / PSHI_L 0 / POPM_B var``); a lone ``CAL OR`` adds its levels to every option found.
        Returns the distinct LevelMaskOption found (may be empty)."""
        if len(self.data) < 8:
            return []
        instructions = self.__instructions()
        options = []
        extra_or_bits = []
        pending_and = None
        for index, (opcode, param) in enumerate(instructions):
            if opcode != OPCODE_POPM_B or param != variable or index < 1:
                continue
            previous_opcode, previous_param = instructions[index - 1]
            if previous_opcode == OPCODE_PSHN_L:
                options.append(LevelMaskOption(previous_param))
                pending_and = None
            elif previous_opcode == OPCODE_CAL and index >= 3:
                push_var, push_value = instructions[index - 3], instructions[index - 2]
                if push_var != (OPCODE_PSHM_B, variable) or push_value[0] != OPCODE_PSHN_L:
                    continue
                if previous_param == CAL_AND:
                    pending_and = push_value[1]
                elif previous_param == CAL_OR and pending_and is not None:
                    options.append(LevelMaskOption(push_value[1], pending_and | push_value[1]))
                    pending_and = None
                elif previous_param == CAL_OR:
                    extra_or_bits.append(push_value[1])  # conditional extra levels (e.g. bghall1b +Lv5)
        for or_bits in extra_or_bits:
            options += [LevelMaskOption(option.always_bits | or_bits, option.random_bits | or_bits)
                        for option in list(options)]
        unique = []
        for option in options:
            if option not in unique:
                unique.append(option)
        return unique

    def __add_card_move(self, offset_script: int, instruction_offset: int, script_positions: list,
                        script_names: list, script_data_size: int):
        location_dword, card_dword = struct.unpack_from("<II", self.data, offset_script + instruction_offset - 8)
        if location_dword >> 24 != OPCODE_PSHN_L or card_dword >> 24 != OPCODE_PSHN_L:
            return  # computed at runtime (e.g. from a savemap variable), nothing to show statically
        entity_name, script_name = self.__find_script_name(instruction_offset, script_positions,
                                                           script_names, script_data_size)
        self.card_moves.append(CardMove(self.map_name, entity_name, script_name,
                                        card_dword & 0xFFFFFF, location_dword & 0xFFFFFF))

    def __read_script_names(self, nb_entity: int):
        """The .sym file lists the entity names, then for each entity (in script-table order)
        the entity name followed by one line per method script ("entity::method")."""
        if not self.sym_path or not os.path.isfile(self.sym_path):
            return []
        with open(self.sym_path, "r", encoding="ascii", errors="replace") as sym_file:
            lines = [line.strip() for line in sym_file if line.strip()]
        script_names = []
        for line in lines[nb_entity:]:
            if "::" in line:
                entity_name, script_name = line.split("::", 1)
                script_names.append((entity_name, script_name))
            else:
                script_names.append((line, "init"))
        return script_names

    def __find_script_name(self, instruction_offset: int, script_positions: list,
                           script_names: list, script_data_size: int):
        for script_index in range(len(script_names)):
            if script_index >= len(script_positions):
                break
            start = script_positions[script_index]
            if script_index + 1 < len(script_positions):
                end = script_positions[script_index + 1]
            else:
                end = script_data_size
            if start <= instruction_offset < end:
                return script_names[script_index]
        return "entity?", f"offset 0x{instruction_offset:X}"

    def is_modified(self):
        return any(player.is_modified() for player in self.players)

    def apply_params(self):
        """Write the current param values back into the in-memory file data."""
        for player in self.players:
            for param in player.params:
                struct.pack_into("<I", self.data, param.file_offset, param.to_dword())

    def save(self, output_path: str = ""):
        """Patch the params and write the .jsm back to disk (in place by default)."""
        self.apply_params()
        if not output_path:
            output_path = self.jsm_path
        with open(output_path, "wb") as jsm_file:
            jsm_file.write(self.data)
        for player in self.players:
            for param in player.params:
                param.original_opcode = param.opcode
                param.original_value = param.value


class CardGameFolderManager:
    """Scans a folder (recursively) for .jsm files and gathers every card player found."""

    def __init__(self):
        self.jsm_files = []
        self.card_moves = []  # every literal SETCARD of the folder, card players or not

    def load_folder(self, folder_path: str):
        self.jsm_files = []
        self.card_moves = []
        for root, _, files in os.walk(folder_path):
            for file_name in sorted(files):
                if not file_name.lower().endswith(".jsm"):
                    continue
                jsm_path = os.path.join(root, file_name)
                sym_path = os.path.splitext(jsm_path)[0] + ".sym"
                try:
                    jsm_file = JsmCardGameFile(jsm_path, sym_path)
                except (OSError, struct.error) as error:
                    print(f"CCGroup: could not read {jsm_path}: {error}")
                    continue
                self.card_moves.extend(jsm_file.card_moves)
                if jsm_file.players:
                    self.jsm_files.append(jsm_file)
        return self.jsm_files

    def file_of(self, player: CardGamePlayer):
        for jsm_file in self.jsm_files:
            if player in jsm_file.players:
                return jsm_file
        return None

    def players_with_deck_id(self, deck_id: int):
        """(jsm_file, player) of every card player whose Deck ID is currently this literal value."""
        return [(jsm_file, player) for jsm_file in self.jsm_files for player in jsm_file.players
                if player.params[PARAM_DECK_ID].is_literal() and player.params[PARAM_DECK_ID].value == deck_id]

    def moves_to_location(self, location: int):
        """The SETCARD calls that move a card to this location."""
        return [move for move in self.card_moves if move.location == location]

    def nb_players(self):
        return sum(len(jsm_file.players) for jsm_file in self.jsm_files)

    def save_all(self):
        """Save every file that has modifications. Returns the number of files written."""
        nb_saved = 0
        for jsm_file in self.jsm_files:
            if jsm_file.is_modified():
                jsm_file.save()
                nb_saved += 1
        return nb_saved
