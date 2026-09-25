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

from CCGroup.jsmvariant import analyze_variants, decode_instructions

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
OPCODE_SETMODEL = 0x2B  # param = entry index in the field's chara.one
OPCODE_SET = 0x1D  # pops x, y; param = walkmesh triangle
OPCODE_SET3 = 0x1E  # pops x, y, z; param = walkmesh triangle
CAL_AND = 0x0C
CAL_OR = 0x0D

VARIABLE_PUSH_OPCODES = (OPCODE_PSHM_B, OPCODE_PSHM_W, OPCODE_PSHM_L,
                         OPCODE_PSHSM_B, OPCODE_PSHSM_W, OPCODE_PSHSM_L)
PUSH_OPCODES = (OPCODE_PSHN_L, OPCODE_PSHI_L, OPCODE_PSHAC) + VARIABLE_PUSH_OPCODES

# Minimum script similarity (0-1) to name a modded entity/script after its vanilla counterpart
ENTITY_NAME_MATCH_MIN = 0.5

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
        self.variant = None  # jsmvariant.VariantInfo: what picks this call among its script's ones

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

    def __init__(self, jsm_path: str, sym_path: str = "", sym_fallbacks=(), name_reference=None):
        """sym_path, then each of sym_fallbacks, is used only if it matches the script's entity
        table (a modded .jsm may have more entities than the vanilla .sym describes); with none
        matching, the scripts are named after name_reference (the vanilla JsmCardGameFile of the
        same map) by matching each entity to the vanilla entity with the most similar scripts, and
        whatever stays unmatched gets a generic name ("entity3", "script2")."""
        self.name_reference = name_reference
        self.jsm_path = jsm_path
        self.sym_path = sym_path
        self.sym_candidates = [path for path in [sym_path, *sym_fallbacks] if path]
        self.names_from_sym = False  # True when a .sym matching the entity table named the scripts
        # Layered loading (CardGameFolderManager): where this map comes from
        self.rel_path = os.path.basename(jsm_path)  # path relative to the field folder(s)
        self.vanilla_path = jsm_path
        self.modified_path = ""
        self.asset_folders = [os.path.dirname(jsm_path)]  # searched in order for the map's other files
        self.map_name = os.path.splitext(os.path.basename(jsm_path))[0]
        with open(jsm_path, "rb") as jsm_file:
            self.data = bytearray(jsm_file.read())
        self.players = []
        self.card_moves = []  # SETCARD calls with literal arguments
        self.offset_script = 0
        self.script_positions = []
        self.script_literals = {}  # editable literals of the variant conditions, by file offset
        self.script_names = []  # (entity, script) per script entry, from the .sym
        self.__analyze()
        analyze_variants(self)

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
        self.offset_script = offset_script
        self.script_positions = script_positions

        self.script_positions = script_positions
        script_names = self.__read_script_names(nb_entity)
        self.script_names = script_names

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

    def __entity_instructions(self, entity_name: str):
        """(index, opcode, param) of the instructions of an entity's scripts, init first."""
        instructions = decode_instructions(self.data, self.offset_script)
        for script_index, name in enumerate(self.script_names):
            if name is None or name[0] != entity_name or script_index >= len(self.script_positions):
                continue
            start = self.script_positions[script_index] // 4
            end = min((position // 4 for position in self.script_positions if position // 4 > start),
                      default=len(instructions))
            for index in range(start, min(end, len(instructions))):
                yield (index,) + instructions[index]

    def entity_model_index(self, entity_name: str):
        """Model of an entity: its first SETMODEL = entry index in the field's chara.one
        (usually in the init script, sometimes in the default one). None if not found."""
        for _, opcode, param in self.__entity_instructions(entity_name):
            if opcode == OPCODE_SETMODEL:
                return param
        return None

    def entity_position(self, entity_name: str):
        """Initial position of an entity: its first SET3 (x, y, z, triangle) or SET (x, y, None,
        triangle - the game takes Z from the walkmesh triangle) with literal coordinates."""
        instructions = decode_instructions(self.data, self.offset_script)
        for index, opcode, param in self.__entity_instructions(entity_name):
            nb_coordinates = {OPCODE_SET3: 3, OPCODE_SET: 2}.get(opcode)
            if nb_coordinates is None or index < nb_coordinates:
                continue
            pushes = instructions[index - nb_coordinates:index]
            if any(push_opcode != OPCODE_PSHN_L for push_opcode, _ in pushes):
                return None  # position computed at runtime
            coordinates = [value for _, value in pushes]
            z = coordinates[2] if nb_coordinates == 3 else None
            return coordinates[0], coordinates[1], z, param
        return None

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
        """(entity, script) per script entry point.

        The .sym starts with a list of entity names, then one group per entity: a line with the
        entity name (its init script) followed by one "entity::method" line per method. The groups
        follow the entities sorted by their first script (entity entry = count | first << 7, with
        count + 1 scripts each); the name list at the top can be one line short, so the groups
        start on the line just before the first "::" line (checked on the 849 vanilla fields).
        A .sym whose groups do not match the entity table is not used."""
        entities = sorted((struct.unpack_from("<H", self.data, 8 + 2 * index)[0] for index in range(nb_entity)),
                          key=lambda entry: entry >> 7)
        for sym_path in self.sym_candidates:
            groups = self.__read_sym_groups(sym_path)
            if groups is None or len(groups) != len(entities) or any(
                    len(group) != (entry & 0x7F) + 1 for group, entry in zip(groups, entities)):
                continue
            self.sym_path = sym_path
            self.names_from_sym = True
            return self.__names_from_groups(groups, entities)
        generic = [[(f"entity{index}", "init")] + [(f"entity{index}", f"script{script}")
                                                   for script in range(1, (entry & 0x7F) + 1)]
                   for index, entry in enumerate(entities)]
        if self.name_reference is not None and self.name_reference.names_from_sym:
            generic = self.__names_matched_to_reference(entities, generic)
        return self.__names_from_groups(generic, entities)

    def entity_script_bodies(self):
        """Per entity (sorted by first script): the instruction list of each of its scripts, LBL
        left out (it holds the script index, which shifts when a mod adds scripts)."""
        instructions = decode_instructions(self.data, self.offset_script)
        nb_entity = sum(self.data[0:4])
        entries = sorted((struct.unpack_from("<H", self.data, 8 + 2 * index)[0] for index in range(nb_entity)),
                         key=lambda entry: entry >> 7)
        bodies = []
        for entry in entries:
            scripts = []
            for script_index in range(entry >> 7, (entry >> 7) + (entry & 0x7F) + 1):
                if script_index >= len(self.script_positions):
                    break
                start = self.script_positions[script_index] // 4
                end = min((position // 4 for position in self.script_positions if position // 4 > start),
                          default=len(instructions))
                scripts.append(tuple(instruction for instruction in instructions[start:end]
                                     if instruction[0] != 0x05))
            bodies.append(scripts)
        return bodies

    def __names_matched_to_reference(self, entities, generic):
        """Name a modded script from the vanilla one: each entity takes the name of the vanilla
        entity whose scripts look the most alike (greedy, best similarity first), and each of its
        scripts the name of the most similar vanilla script of that entity."""
        from difflib import SequenceMatcher
        reference = self.name_reference
        reference_bodies = reference.entity_script_bodies()
        reference_groups = []
        for scripts in reference_bodies:
            reference_groups.append([])
        # Names of the reference, per entity in the same (sorted) order as its bodies
        reference_entries = sorted((struct.unpack_from("<H", reference.data, 8 + 2 * index)[0]
                                    for index in range(sum(reference.data[0:4]))), key=lambda entry: entry >> 7)
        for index, entry in enumerate(reference_entries):
            reference_groups[index] = [reference.script_names[script_index]
                                       for script_index in range(entry >> 7, (entry >> 7) + (entry & 0x7F) + 1)
                                       if script_index < len(reference.script_names)]
        own_bodies = self.entity_script_bodies()

        def similarity(first, second):
            if first == second:
                return 1.0
            first_flat = [instruction for script in first for instruction in script]
            second_flat = [instruction for script in second for instruction in script]
            if not first_flat or not second_flat:
                return 0.0
            matcher = SequenceMatcher(None, first_flat, second_flat, autojunk=False)
            # Cheap upper bounds first: most pairs are unrelated entities
            if matcher.real_quick_ratio() < ENTITY_NAME_MATCH_MIN or matcher.quick_ratio() < ENTITY_NAME_MATCH_MIN:
                return 0.0
            return matcher.ratio()

        # Unchanged entities (most of a modded script) match exactly: pair them first, then only
        # compare the remaining ones
        scores = []
        exact_reference = {}
        for ref_index, ref in enumerate(reference_bodies):
            exact_reference.setdefault(tuple(ref), []).append(ref_index)
        exact_pairs = set()
        for own_index, own in enumerate(own_bodies):
            candidates = exact_reference.get(tuple(own))
            if candidates:
                exact_pairs.add((own_index, candidates.pop(0)))
        exact_own = {own_index for own_index, _ in exact_pairs}
        exact_ref = {ref_index for _, ref_index in exact_pairs}
        scores = [(1.0, own_index, ref_index) for own_index, ref_index in exact_pairs]
        scores += sorted(((similarity(own, ref), own_index, ref_index)
                          for own_index, own in enumerate(own_bodies) if own_index not in exact_own
                          for ref_index, ref in enumerate(reference_bodies) if ref_index not in exact_ref),
                         reverse=True)
        matched_own, matched_reference = set(), set()
        for score, own_index, ref_index in scores:
            if score < ENTITY_NAME_MATCH_MIN or own_index in matched_own or ref_index in matched_reference:
                continue
            matched_own.add(own_index)
            matched_reference.add(ref_index)
            names = reference_groups[ref_index]
            if not names or names[0] is None:
                continue
            entity_name = names[0][0]
            group = [(entity_name, "init")]
            used = set()
            for own_script in own_bodies[own_index][1:]:
                best = max(((SequenceMatcher(None, own_script, ref_script, autojunk=False).ratio(), position)
                            for position, ref_script in enumerate(reference_bodies[ref_index])
                            if position > 0 and position not in used and position < len(names)),
                           default=(0.0, None))
                if best[1] is not None and best[0] >= ENTITY_NAME_MATCH_MIN:
                    used.add(best[1])
                    group.append((entity_name, names[best[1]][1]))
                else:
                    group.append((entity_name, f"script{len(group)}"))
            generic[own_index] = group
        return generic

    @staticmethod
    def __read_sym_groups(sym_path: str):
        if not os.path.isfile(sym_path):
            return None
        with open(sym_path, "r", encoding="ascii", errors="replace") as sym_file:
            lines = [line.strip() for line in sym_file if line.strip()]
        first_method = next((index for index, line in enumerate(lines) if "::" in line), None)
        if not first_method:
            return None
        groups = []
        for line in lines[first_method - 1:]:
            if "::" not in line:
                groups.append([(line, "init")])
            elif groups:
                groups[-1].append(tuple(line.split("::", 1)))
        return groups

    def __names_from_groups(self, groups, entities):
        names = [None] * len(self.script_positions)
        for group, entry in zip(groups, entities):
            first_script = entry >> 7
            for script_offset, name in enumerate(group[:(entry & 0x7F) + 1]):
                if first_script + script_offset < len(names):
                    names[first_script + script_offset] = name
        return names

    def __find_script_name(self, instruction_offset: int, script_positions: list,
                           script_names: list, script_data_size: int):
        start = max((position for position in script_positions if position <= instruction_offset), default=None)
        if start is not None:
            name = script_names[script_positions.index(start)]
            if name is not None:
                return name
        return "entity?", f"offset 0x{instruction_offset:X}"

    def is_modified(self):
        return (any(player.is_modified() for player in self.players)
                or any(literal.is_modified() for literal in self.script_literals.values()))

    def apply_params(self):
        """Write the current param values (and variant condition literals) back into the data."""
        for player in self.players:
            for param in player.params:
                struct.pack_into("<I", self.data, param.file_offset, param.to_dword())
        for literal in self.script_literals.values():
            struct.pack_into("<I", self.data, literal.file_offset, literal.to_dword())

    def save(self, output_path: str = ""):
        """Patch the params and write the .jsm back to disk (in place by default)."""
        self.apply_params()
        if not output_path:
            output_path = self.jsm_path
        with open(output_path, "wb") as jsm_file:
            jsm_file.write(self.data)
        self.mark_saved()

    def asset_path(self, file_name: str):
        """A file of this map (background, camera, chara.one...): the modified folder's copy when it
        has one, else the vanilla one. "" when no folder has it."""
        for folder in self.asset_folders:
            path = os.path.join(folder, file_name)
            if os.path.isfile(path):
                return path
        return ""

    def mark_saved(self):
        """The current values become the reference ones (after a save, or when there was nothing
        to write because the patched file equals vanilla)."""
        for player in self.players:
            for param in player.params:
                param.original_opcode = param.opcode
                param.original_value = param.value
        for literal in self.script_literals.values():
            literal.original_value = literal.value


class SaveReport:
    """What CardGameFolderManager.save_all did."""

    def __init__(self):
        self.written = []  # JsmCardGameFile written to disk
        self.identical_to_vanilla = []  # modified-folder maps that now equal vanilla again (not written)


def collect_jsm_paths(folder: str):
    """{path relative to folder: absolute path} of every .jsm under folder."""
    paths = {}
    if not folder:
        return paths
    for root, _, files in os.walk(folder):
        for file_name in files:
            if file_name.lower().endswith(".jsm"):
                path = os.path.join(root, file_name)
                paths[os.path.relpath(path, folder)] = path
    return paths


class CardGameFolderManager:
    """Gathers every card player of a field folder, optionally with a modified folder on top.

    The vanilla folder holds the whole game; the modified folder (e.g. a mod's field folder) only
    the maps it changes, at the same relative paths. A map is read from the modified folder when
    it has it, else from vanilla. With a modified folder, saving writes there only, and only the
    maps that differ from vanilla; without one, files are saved in place."""

    def __init__(self):
        self.jsm_files = []
        self.card_moves = []  # every literal SETCARD of the folder, card players or not
        self.vanilla_folder = ""
        self.modified_folder = ""

    def load_folder(self, folder_path: str, modified_folder: str = ""):
        self.jsm_files = []
        self.card_moves = []
        self.vanilla_folder = folder_path
        self.modified_folder = modified_folder
        vanilla_paths = collect_jsm_paths(folder_path)
        modified_paths = collect_jsm_paths(modified_folder)
        for rel_path in sorted(set(vanilla_paths) | set(modified_paths)):
            vanilla_path = vanilla_paths.get(rel_path, "")
            modified_path = modified_paths.get(rel_path, "")
            jsm_path = modified_path or vanilla_path
            syms = [os.path.splitext(path)[0] + ".sym" for path in (modified_path, vanilla_path) if path]
            try:
                jsm_file = JsmCardGameFile(jsm_path, syms[0], syms[1:])
                if not jsm_file.names_from_sym and modified_path and vanilla_path:
                    # The modded script no longer matches the vanilla .sym: name it by similarity
                    name_reference = JsmCardGameFile(vanilla_path, os.path.splitext(vanilla_path)[0] + ".sym")
                    jsm_file = JsmCardGameFile(jsm_path, syms[0], syms[1:], name_reference=name_reference)
            except (OSError, struct.error) as error:
                print(f"CCGroup: could not read {jsm_path}: {error}")
                continue
            jsm_file.rel_path = rel_path
            jsm_file.vanilla_path = vanilla_path
            jsm_file.modified_path = modified_path
            jsm_file.asset_folders = [os.path.dirname(path) for path in (modified_path, vanilla_path) if path]
            self.card_moves.extend(jsm_file.card_moves)
            if jsm_file.players:
                self.jsm_files.append(jsm_file)
        return self.jsm_files

    def nb_from_modified_folder(self):
        return sum(1 for jsm_file in self.jsm_files if jsm_file.modified_path)

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
        return len(self.save_all_report().written)

    def save_all_report(self):
        """Save every modified map. Without a modified folder: in place. With one: to
        <modified folder>/<same relative path>, and only when the patched bytes differ from the
        vanilla file (a map edited back to vanilla is not written; if the modified folder already
        had it, it is listed in identical_to_vanilla so the caller can offer to delete it)."""
        report = SaveReport()
        for jsm_file in self.jsm_files:
            if not jsm_file.is_modified():
                continue
            if not self.modified_folder:
                jsm_file.save()
                report.written.append(jsm_file)
                continue
            jsm_file.apply_params()
            vanilla_data = None
            if jsm_file.vanilla_path:
                with open(jsm_file.vanilla_path, "rb") as vanilla_file:
                    vanilla_data = vanilla_file.read()
            if vanilla_data == bytes(jsm_file.data):
                jsm_file.mark_saved()
                if jsm_file.modified_path:
                    report.identical_to_vanilla.append(jsm_file)
                continue
            target = os.path.join(self.modified_folder, jsm_file.rel_path)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            jsm_file.save(target)
            if not jsm_file.modified_path:
                jsm_file.modified_path = target
                jsm_file.jsm_path = target
                jsm_file.asset_folders.insert(0, os.path.dirname(target))
            report.written.append(jsm_file)
        return report

    def delete_from_modified_folder(self, jsm_file):
        """Remove a map's .jsm from the modified folder (it equals vanilla): vanilla is used again."""
        if not jsm_file.modified_path:
            return
        os.remove(jsm_file.modified_path)
        modified_dir = os.path.dirname(jsm_file.modified_path)
        if not os.listdir(modified_dir):  # the map's folder only held this script
            os.rmdir(modified_dir)
        if modified_dir in jsm_file.asset_folders:
            jsm_file.asset_folders.remove(modified_dir)
        jsm_file.modified_path = ""
        jsm_file.jsm_path = jsm_file.vanilla_path
