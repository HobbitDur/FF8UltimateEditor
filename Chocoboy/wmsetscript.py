"""The world-map script bytecode of ``wmsetxx.obj`` (sections 7, 9, 11 and 36).

Every instruction is 4 bytes: a signed int16 opcode (always ``0xFFxx``, so always negative)
followed by either one uint16 parameter or two uint8 parameters. A section is an offset table
(one uint32 per entry point, ended by a ``0x00000000`` sentinel) followed by one single stream
of instructions; each table entry is a byte offset *into the section* where one script starts.

Two things the game does that the older notes get wrong, both checked against the interpreter
(``Wmset_warpConditionSystem``, FF8_EN.exe 0x545F10) and against the shipped ``wmsetus.obj``:

- ``GOTO`` jumps to an offset counted **from the start of the section**, the same numbers the
  offset table uses - not from the start of the current script. So moving one instruction moves
  every jump target after it, wherever in the section it lives.
- A script does not stop at the next table offset, it stops at its own ``RETURN``. The offset
  table is not sorted either - in ``wmsetus.obj`` two of section 36's scripts are stored out of
  table order - so "this script runs to the next offset" would give one of them a negative
  length. That is why this module keeps one instruction stream per section rather than a private
  copy of the bytes per script.
"""

import struct

# kind: what the instruction does, which is also how the pseudo-code prints it.
CONTROL = "control"        # IF / THEN / ELSE / END structure
CONDITION = "condition"    # tested inside an IF, passes or fails
ACTION = "action"          # run inside a THEN block
TERMINATOR = "terminator"  # ends the script

# params: how the 2 bytes after the opcode are read.
NO_PARAM = "none"  # both bytes ignored by the game (still stored, still written back)
WORD = "word"      # one uint16 = param1 + param2 * 256
TWO_BYTES = "two"  # two independent uint8


class Opcode:
    """One entry of the world-map instruction set.

    ``aliases`` are the names the FF8ModdingWiki uses where this tool renamed an opcode to say
    what it actually does; they are still accepted when text is pasted back in, so a script
    written against the wiki still imports.
    """

    def __init__(self, code, name, kind, params, description, aliases=()):
        self.code = code  # the 0xFFxx value as stored, e.g. 0xFF27
        self.name = name
        self.kind = kind
        self.params = params
        self.description = description
        self.aliases = tuple(aliases)

    @property
    def signed_code(self):
        return self.code - 0x10000

    def __str__(self):
        return self.name


OPCODE_LIST = [
    # --- Control flow -------------------------------------------------------------------------
    Opcode(0xFF01, "IF", CONTROL, NO_PARAM,
           "Starts the script's own condition list: every instruction from here to the DO is "
           "tested. There is no ELSE for it - the moment one of them fails the script is over "
           "and nothing in it runs. That is what makes it different from IF_BLOCK."),
    Opcode(0xFF04, "DO", CONTROL, NO_PARAM,
           "The IF list above passed: here start the actions. Not the same as THEN, which closes "
           "an IF_BLOCK and has an ELSE to fall to; reaching DO means the script is already "
           "committed to running.",
           aliases=("EXEC", "THEN_ALWAYS")),
    Opcode(0xFF05, "END", CONTROL, NO_PARAM,
           "Ends an action block. Also ends the whole event when the global event runner meets it.",
           aliases=("ENDIF", "END_ACTIONS")),
    Opcode(0xFF0A, "IF_BLOCK", CONTROL, NO_PARAM,
           "Opens a branch inside the actions: its conditions run up to the THEN, and if one "
           "fails the ELSE_IF / ELSE chain after gets its turn instead of the script stopping.",
           aliases=("IFBLOCK",)),
    Opcode(0xFF0B, "THEN", CONTROL, NO_PARAM,
           "The IF_BLOCK or ELSE_IF above passed: run the actions up to the next END. Had it "
           "failed, the ELSE_IF / ELSE after that END would have had their turn - a failed "
           "condition here picks another branch, it does not end the script the way the "
           "script's own IF does.",
           aliases=("ELSE",)),
    Opcode(0xFF0C, "ELSE_IF", CONTROL, NO_PARAM,
           "The previous conditions failed: test this new condition list instead.",
           aliases=("NESTEDIF",)),
    Opcode(0xFF0D, "ELSE", CONTROL, NO_PARAM,
           "Every condition above failed: run the actions up to the next END.",
           aliases=("NESTEDELSE",)),
    Opcode(0xFF0E, "GOTO", CONTROL, WORD,
           "Jump to a byte offset counted from the start of the section (same origin as the "
           "offset table), not from the start of this script."),
    Opcode(0xFF16, "RETURN", TERMINATOR, NO_PARAM,
           "Ends this script. Every script of sections 7, 11 and 36 ends with one."),
    Opcode(0xFF15, "SET_RETURN_VALUE", ACTION, WORD,
           "Sets the value the script hands back without stopping it. 3 takes the special "
           "vehicle-warp path of section 11."),
    Opcode(0xFF08, "WARP_TO_FIELD", TERMINATOR, WORD,
           "Ends the script and warps: the parameter is an entrance id in wm2field.tbl.",
           aliases=("RETURN_WITH_VALUE",)),
    Opcode(0xFF2B, "START_BATTLE", TERMINATOR, WORD,
           "Ends the script and starts a battle: the parameter is the encounter (scene) id.",
           aliases=("RETURN_WITH_CODE_3",)),

    # --- Conditions ---------------------------------------------------------------------------
    Opcode(0xFF02, "STORY_AT_LEAST", CONDITION, WORD,
           "Story progress has reached the parameter (param <= world_story_progress).",
           aliases=("LTEQ_THAN", "GTEQ_THAN")),
    Opcode(0xFF03, "STORY_BELOW", CONDITION, WORD,
           "Story progress has not reached the parameter yet (param > world_story_progress).",
           aliases=("GREATER_THAN", "LESS_THAN")),
    Opcode(0xFF06, "CHECK_REGION_NUMBER", CONDITION, WORD,
           "The player stands in world-map region number param."),
    Opcode(0xFF07, "CHECK_TILE_POSITION", CONDITION, WORD,
           "The player stands on the 2048-unit map square param = tile_x + tile_y * 128."),
    Opcode(0xFF09, "CHECK_VEHICLE_TYPE", CONDITION, WORD,
           "The vehicle the player rides matches param. 33 bike, 49 the two big ships, 128 on "
           "foot, 129 the walking party, 130 Galbadia aircraft, 131 trains, 132/133 cars. "
           "48 and 50 are the Ragnarok and the mobile Balamb Garden, but which is which is not "
           "settled: the community notes and the IDB's own model tables disagree."),
    Opcode(0xFF0F, "X_GREATER_THAN", CONDITION, WORD,
           "param is greater than the player X inside the current segment (X & 0x1FFF)."),
    Opcode(0xFF10, "Y_GREATER_THAN", CONDITION, WORD,
           "param is greater than the player Y inside the current segment (Y & 0x1FFF)."),
    Opcode(0xFF11, "X_LESS_THAN", CONDITION, WORD,
           "param is less than the player X inside the current segment (X & 0x1FFF)."),
    Opcode(0xFF12, "Y_LESS_THAN", CONDITION, WORD,
           "param is less than the player Y inside the current segment (Y & 0x1FFF)."),
    Opcode(0xFF17, "CHECK_ENTITY_PROXIMITY", CONDITION, WORD,
           "A world object of model class param is spawned, visible and on screen."),
    Opcode(0xFF18, "CHECK_VEHICLE_APPROACHING", CONDITION, WORD,
           "Vehicle param is in its approach state: 50 needs world state 6, 48 needs 9. Only "
           "those two values ever pass. See CHECK_VEHICLE_TYPE on what 48 and 50 are.",
           aliases=("CHECK_VEHICLE_ENTERING", "CHECK_VEHICLE_DOCKING_IN_PROGRESS")),
    Opcode(0xFF19, "CHECK_VEHICLE_ACTIVE", CONDITION, WORD,
           "Vehicle param is boarded and active: 50 needs world state 5, 48 needs 8. Only those "
           "two values ever pass. See CHECK_VEHICLE_TYPE on what 48 and 50 are.",
           aliases=("CHECK_VEHICLE_BOARDED", "CHECK_VEHICLE_DOCKED")),
    Opcode(0xFF1A, "CHECK_TOUCHED_ENTITY", CONDITION, WORD,
           "The object the player just touched has model class param.",
           aliases=("CHECK_CHARACTER_LOCATION",)),
    Opcode(0xFF1B, "CHECK_TOUCHED_ENTITY_NO_VEHICLE", CONDITION, WORD,
           "Same as CHECK_TOUCHED_ENTITY, but the 7 reserved party/vehicle slots do not count.",
           aliases=("CHECK_CHARACTER_LOCATION_EX",)),
    Opcode(0xFF1C, "CHECK_FACED_ENTITY", CONDITION, WORD,
           "The object the player faces has model class param and the player looks within "
           "512 angle units (~11 degrees) of it.",
           aliases=("CHECK_CHARACTER_LOCATION_2",)),
    Opcode(0xFF1D, "CHECK_FACED_ENTITY_NO_VEHICLE", CONDITION, WORD,
           "Same as CHECK_FACED_ENTITY, but the 7 reserved party/vehicle slots do not count.",
           aliases=("CHECK_CHARACTER_DISTANCE",)),
    Opcode(0xFF1E, "FAIL", CONDITION, NO_PARAM,
           "Always fails, which forces the ELSE branch."),
    Opcode(0xFF20, "CHECK_BUTTON_INPUT", CONDITION, WORD,
           "A button was pressed this frame. param is a button mask; 0xFFFF means any button or "
           "a stick push past 45. Never passes after CONSUME_INPUT."),
    Opcode(0xFF21, "CHECK_BATTLE_STATE", CONDITION, WORD,
           "The party save flag at offset 109 (battle just resolved) equals param."),
    Opcode(0xFF22, "CHECK_LOCATION_ENTRY_INDEX", CONDITION, WORD,
           "The location block currently being drawn is entry number param.",
           aliases=("CHECK_LOCATION_DRAW_REGISTER",)),
    Opcode(0xFF25, "CHECK_WORLD_MAP_STATE", CONDITION, WORD,
           "The world-map state byte equals param. 0 normal, 5 Ragnarok active, 6 Ragnarok "
           "approaching, 7 Shumi train, 8 Garden active, 9 Garden approaching, 10 draw point, "
           "13 leaving to a field, 14 vehicle transition."),
    Opcode(0xFF27, "CHECK_BIT_FLAG", CONDITION, TWO_BYTES,
           "Save-game world bit param1 (0-63) equals param2 (0 or 1). This is the side-quest "
           "flag the world map keeps in the save file."),
    Opcode(0xFF29, "CHECK_DIALOG_ANSWERED", CONDITION, WORD,
           "Message window param has an answer picked, and remembers which one for "
           "COMPARE_DIALOG_RESPONSE.",
           aliases=("CHECK_DIALOG_STATE", "CHECK_DIALOG_CHOICE_PICKED")),
    Opcode(0xFF2A, "COMPARE_DIALOG_RESPONSE", CONDITION, WORD,
           "The answer remembered by CHECK_DIALOG_ANSWERED equals param."),
    Opcode(0xFF2C, "CHECK_DIALOG_OPEN", CONDITION, TWO_BYTES,
           "Message window param1 being open equals param2 (1 open, 0 closed).",
           aliases=("CHECK_DIALOG_ACTIVE", "CHECK_DIALOG_CONFIRMED")),
    Opcode(0xFF2D, "COMPARE_SCRIPT_VAR", CONDITION, TWO_BYTES,
           "Save-game script byte param1 (0 or 1) equals param2."),
    Opcode(0xFF2F, "CHECK_RANDOM_NUMBER", CONDITION, WORD,
           "A random 16-bit draw is below param. 0 never passes, 65535 always does."),
    Opcode(0xFF30, "COMPARE_SCRIPT_VAR_GT", CONDITION, TWO_BYTES,
           "param2 is greater than save-game script byte param1."),
    Opcode(0xFF31, "COMPARE_SCRIPT_VAR_LT", CONDITION, TWO_BYTES,
           "param2 is less than save-game script byte param1."),
    Opcode(0xFF32, "CHECK_LOCATION_FLAG", CONDITION, WORD,
           "Bit 3 of the drawn location block's flag byte, inverted, equals param."),
    Opcode(0xFF33, "COMPARE_LOCATION_BYTE", CONDITION, TWO_BYTES,
           "The drawn location block's byte at offset 13 equals param1."),
    Opcode(0xFF34, "CHECK_COMBAT_SCENE_ID", CONDITION, WORD,
           "The last encounter (scene) id equals param."),
    Opcode(0xFF35, "CHECK_BATTLE_ESCAPED", CONDITION, WORD,
           "Whether the last battle was escaped from equals param (1 escaped, 0 not). The "
           "parameter IS read, whatever the older notes say: wm_scriptCheckCondition compares "
           "a1[1] against the escaped flag like every other condition.",
           aliases=("CHECK_BATTLE_RESULT",)),
    Opcode(0xFF38, "CHECK_MOVEMENT", CONDITION, WORD,
           "The player moving equals param (1 moving, 0 standing still)."),
    Opcode(0xFF39, "CHECK_BATTLEVAR", CONDITION, WORD,
           "An as-yet unidentified save-game battle variable equals param."),

    # --- Actions ------------------------------------------------------------------------------
    Opcode(0xFF13, "ADD_ENTITY", ACTION, TWO_BYTES,
           "Spawns world object of model class param1 at position record param2 of section 10 "
           "(0xFF means it places itself). Model classes are their own numbering, not the vehicle "
           "codes: 0 Squall, 1 and 64/65 the Garden and the Ragnarok, 2/3 the two big ships, "
           "70 a train, 73-87 cars and chocobos, 94 the Jumbo Cactuar (spawned only while GF 13, "
           "Cactuar, is not owned). Section 9 only."),
    Opcode(0xFF14, "ADD_ENTITY_ALT", ACTION, TWO_BYTES,
           "Same fields and same handling as ADD_ENTITY."),
    Opcode(0xFF1F, "SHOW_TEXT_BOX", ACTION, TWO_BYTES,
           "Opens message window param1 (0-12) on text param2 of section 13."),
    Opcode(0xFF23, "SHOW_CHOICE_BOX", ACTION, TWO_BYTES,
           "Opens message window param1 on text param2 of section 13, with two selectable "
           "lines. Read the answer back with CHECK_DIALOG_ANSWERED."),
    Opcode(0xFF24, "CLOSE_TEXT_BOX", ACTION, WORD,
           "Closes message window param."),
    Opcode(0xFF26, "SET_WORLD_MAP_STATE", ACTION, TWO_BYTES,
           "Sets the world-map state byte to param1. See CHECK_WORLD_MAP_STATE for the values."),
    Opcode(0xFF28, "SET_BIT_FLAG", ACTION, TWO_BYTES,
           "Sets save-game world bit param1 (0-63) to param2 (0 or 1)."),
    Opcode(0xFF2E, "SET_SCRIPT_VAR", ACTION, TWO_BYTES,
           "Sets save-game script byte param1 (0 or 1) to param2."),
    Opcode(0xFF36, "CONSUME_INPUT", ACTION, NO_PARAM,
           "Eats this frame's button press, so no later CHECK_BUTTON_INPUT passes.",
           aliases=("SET_GLOBAL_EVENT_TRIGGERED",)),
    Opcode(0xFF37, "ADD_ITEM", ACTION, TWO_BYTES,
           "Puts param2 copies of item param1 in the inventory."),
]

OPCODE_BY_CODE = {opcode.code: opcode for opcode in OPCODE_LIST}
OPCODE_BY_NAME = {}
for _opcode in OPCODE_LIST:
    OPCODE_BY_NAME[_opcode.name] = _opcode
    for _alias in _opcode.aliases:
        OPCODE_BY_NAME.setdefault(_alias, _opcode)

RETURN_CODE = 0xFF16
GOTO_CODE = 0xFF0E
END_CODE = 0xFF05


class Instruction:
    """One 4-byte world-map instruction, kept as read so an unknown opcode still round-trips."""

    def __init__(self, code, param1=0, param2=0):
        self.code = code & 0xFFFF
        self.param1 = param1 & 0xFF
        self.param2 = param2 & 0xFF
        # What a text edit wrote around this line. The .obj has nowhere to keep either, so they
        # live in this session only - and in whatever text file they were imported from.
        self.comments = []  # whole lines (comments, blank lines) written just above it
        self.trailing = ""  # the "; ..." note written at the end of its own line

    @classmethod
    def from_bytes(cls, data, offset):
        code, param1, param2 = struct.unpack_from("<HBB", data, offset)
        return cls(code, param1, param2)

    @property
    def is_padding(self):
        """A zero word: the filler a section ends on, not an instruction the game would run."""
        return self.code == 0 and self.param1 == 0 and self.param2 == 0

    def to_bytes(self):
        return struct.pack("<HBB", self.code, self.param1, self.param2)

    @property
    def opcode(self):
        """The known Opcode, or None when the bytes are not an instruction this tool knows."""
        return OPCODE_BY_CODE.get(self.code)

    @property
    def name(self):
        opcode = self.opcode
        return opcode.name if opcode else f"RAW_{self.code:04X}"

    @property
    def word(self):
        """The two parameter bytes read as the single uint16 the game uses for WORD opcodes."""
        return self.param1 + self.param2 * 256

    def set_word(self, value):
        value &= 0xFFFF
        self.param1 = value & 0xFF
        self.param2 = value >> 8

    def param_text(self):
        """The parameters the way the game reads them for this opcode."""
        opcode = self.opcode
        if opcode is None:
            return f"{self.param1}, {self.param2}"
        if opcode.params == NO_PARAM:
            return ""
        if opcode.params == WORD:
            return str(self.word)
        return f"{self.param1}, {self.param2}"

    def __str__(self):
        parameters = self.param_text()
        return f"{self.name} {parameters}".strip()


class ScriptSection:
    """One generic script section of wmsetxx.obj: an offset table plus one instruction stream.

    The instructions are held once, in file order, and ``entry_offsets`` points into them. That
    is how the game reads the section, and it is the only way to keep the two entries of section
    36 that jump into a script owned by another entry.
    """

    def __init__(self, index, section_data):
        self.index = index
        self.entry_offsets = []  # byte offset, from the start of the section, of each script
        self.script_names = {}  # entry index -> the name a text edit gave that script
        self.script_trailing_comments = {}  # entry index -> comment lines written after its end
        self.instructions = []
        self.padding = b""  # the zero word most sections end with, kept so saving is byte-exact
        self.original_data = section_data  # for a section holding no script at all (see to_bytes)
        self._parse(section_data)

    def _parse(self, section_data):
        read = 0
        while read + 4 <= len(section_data):
            offset = struct.unpack_from("<I", section_data, read)[0]
            read += 4
            if offset == 0:  # sentinel: the table ends here and the instructions start
                break
            self.entry_offsets.append(offset)
        self.table_size = read
        stream = section_data[read:]
        while len(stream) >= 4 and stream[-4:] == b"\x00\x00\x00\x00":
            self.padding = stream[-4:] + self.padding
            stream = stream[:-4]
        for offset in range(0, len(stream) - len(stream) % 4, 4):
            self.instructions.append(Instruction.from_bytes(stream, offset))

    # -- offsets ------------------------------------------------------------------------------

    def instruction_offset(self, index):
        """Where instruction ``index`` sits, counted from the start of the section."""
        return self.table_size + index * 4

    def index_at_offset(self, offset):
        """The instruction a section offset points at, or None when it points outside the stream."""
        index = (offset - self.table_size) // 4
        if 0 <= index < len(self.instructions) and (offset - self.table_size) % 4 == 0:
            return index
        return None

    def script_range(self, entry_index):
        """The instructions of one script, as a ``(first, last_excluded)`` index pair.

        A script runs from its entry point to its own RETURN, which is what the interpreter does.
        Sections without a RETURN (section 9 spawn lists end on END instead) stop at the next
        entry point, and a script with neither stops at the end of the section.
        """
        start = self.index_at_offset(self.entry_offsets[entry_index])
        if start is None:
            return 0, 0
        for index in range(start, len(self.instructions)):
            if self.instructions[index].code == RETURN_CODE:
                return start, index + 1
        following = [self.index_at_offset(offset) for offset in self.entry_offsets]
        after = [index for index in following if index is not None and index > start]
        return start, min(after) if after else len(self.instructions)

    def entry_points_at(self, index):
        """Which scripts start on instruction ``index`` (usually one, sometimes none)."""
        offset = self.instruction_offset(index)
        return [entry for entry, entry_offset in enumerate(self.entry_offsets) if entry_offset == offset]

    # -- editing ------------------------------------------------------------------------------

    def insert_instruction(self, index, instruction):
        """Insert before instruction ``index``, moving every entry point and GOTO that follows.

        A target sitting exactly on ``index`` stays put, so the new instruction joins the script
        you are editing instead of being appended to the one before it.
        """
        self.instructions.insert(index, instruction)
        self._shift_targets(self.instruction_offset(index), 4)

    def delete_instruction(self, index):
        """Delete instruction ``index``, moving every entry point and GOTO that follows.

        A target sitting exactly on ``index`` stays put, so it now points at what came after the
        deleted instruction.
        """
        offset = self.instruction_offset(index)
        del self.instructions[index]
        self._shift_targets(offset, -4)

    def _shift_targets(self, offset, delta):
        self.entry_offsets = [entry + delta if entry > offset else entry
                              for entry in self.entry_offsets]
        for instruction in self.instructions:
            if instruction.code == GOTO_CODE and instruction.word > offset:
                instruction.set_word(instruction.word + delta)

    # -- snapshots (undo) ---------------------------------------------------------------------

    def snapshot(self):
        """Everything about this section that an edit can change, as comparable plain values.

        Not just the bytes: the names and comments a text import brought in have nowhere to live
        in the .obj, so undoing back past an import has to bring them back too.
        """
        return (self.to_bytes(),
                tuple(sorted(self.script_names.items())),
                tuple(sorted((entry, tuple(lines))
                             for entry, lines in self.script_trailing_comments.items())),
                tuple((tuple(instruction.comments), instruction.trailing)
                      for instruction in self.instructions))

    def restore_snapshot(self, snapshot):
        data, names, trailing_comments, notes = snapshot
        self.entry_offsets = []
        self.instructions = []
        self.padding = b""
        self._parse(data)
        self.script_names = dict(names)
        self.script_trailing_comments = {entry: list(lines) for entry, lines in trailing_comments}
        for instruction, (comments, trailing) in zip(self.instructions, notes):
            instruction.comments = list(comments)
            instruction.trailing = trailing

    # -- checking -----------------------------------------------------------------------------

    def dangling_gotos(self):
        """The GOTO instructions whose target is not the start of an instruction any more.

        Nothing here produces one - both edits move the targets - but a hand-edited file can,
        and the game would read those 4 bytes as an instruction wherever they land.
        """
        dangling = []
        for index, instruction in enumerate(self.instructions):
            if instruction.code == GOTO_CODE and self.index_at_offset(instruction.word) is None:
                dangling.append(index)
        return dangling

    def problems(self, must_return):
        """Everything structurally wrong with this section, as ``(entry, offset, message)``.

        Only what the interpreter would actually trip over, checked against how it walks the
        bytes - not style. ``must_return`` says whether this section's scripts are run through
        the interpreter (7, 11 and 36, which end on RETURN) or as a plain action list (9).
        """
        found = []
        for entry in range(len(self.entry_offsets)):
            start, end = self.script_range(entry)
            if start >= end:
                found.append((entry, self.entry_offsets[entry],
                              "starts outside the section's instructions"))
                continue
            found.extend(self._script_problems(entry, start, end, must_return))
        return found

    def _script_problems(self, entry, start, end, must_return):
        """One script's problems.

        The only structure that can be checked without knowing which conditions pass is the
        IF_BLOCK chain, and it is not a plain nesting: an END closes the *branch*, and an
        ELSE_IF or ELSE right after it opens the next branch of the same chain. An END with no
        chain open is fine - that is the one closing the script's own DO block.
        """
        found = []
        last = self.instructions[end - 1]
        if must_return and last.code != RETURN_CODE:
            found.append((entry, self.instruction_offset(end - 1),
                          f"ends on {last.name} instead of RETURN, so the interpreter reads "
                          "straight into whatever follows"))
        branch_has_actions = []  # one flag per open chain: whether its current branch has a THEN
        for index in range(start, end):
            instruction = self.instructions[index]
            offset = self.instruction_offset(index)
            code = instruction.code
            if code == 0xFF0A:
                branch_has_actions.append(False)
            elif code == 0xFF0B:
                if not branch_has_actions:
                    found.append((entry, offset, "THEN with no IF_BLOCK or ELSE_IF before it"))
                else:
                    branch_has_actions[-1] = True
            elif code in (0xFF0C, 0xFF0D):
                if not branch_has_actions:
                    found.append((entry, offset,
                                  f"{instruction.name} with no IF_BLOCK chain to continue"))
                else:  # an ELSE runs its actions straight away, an ELSE_IF still needs its THEN
                    branch_has_actions[-1] = code == 0xFF0D
            elif code == END_CODE:
                if branch_has_actions:
                    if not branch_has_actions[-1]:
                        found.append((entry, offset,
                                      "the branch this closes has no THEN, so its conditions can "
                                      "pass with nothing to run"))
                    following = (self.instructions[index + 1].code if index + 1 < end else None)
                    if following not in (0xFF0C, 0xFF0D):  # no next branch: the chain is over
                        branch_has_actions.pop()
            elif code == GOTO_CODE:
                target = self.index_at_offset(instruction.word)
                if target is None:
                    found.append((entry, offset,
                                  f"jumps to {instruction.word}, which is not the start of an "
                                  "instruction"))
                elif not start <= target < end:
                    found.append((entry, offset,
                                  f"jumps to {instruction.word}, outside this script - legal, "
                                  "but nothing in the shipped file does it"))
        for _ in branch_has_actions:
            found.append((entry, self.instruction_offset(end - 1),
                          "an IF_BLOCK chain is left open when the script ends"))
        return found

    # -- writing ------------------------------------------------------------------------------

    def replace_scripts(self, scripts, names=None, trailing_comments=None):
        """Lay the whole section out again from a list of scripts, each a list of Instructions.

        This is what a text import does. The scripts are written back to back in table order, so
        one that grew, shrank, appeared or disappeared is fine - even the offset table changing
        size, which shifts every script. GOTO targets are NOT touched here: the caller resolves
        them (the text format names its jump targets, so it can).
        """
        self.table_size = 4 * (len(scripts) + 1)
        self.entry_offsets = []
        self.instructions = []
        offset = self.table_size
        for script in scripts:
            self.entry_offsets.append(offset)
            self.instructions.extend(script)
            offset += 4 * len(script)
        self.script_names = dict(names or {})
        self.script_trailing_comments = dict(trailing_comments or {})

    def to_bytes(self):
        if not self.entry_offsets:  # empty, or not a script section at all: hand the bytes back
            return self.original_data
        table_size = 4 * (len(self.entry_offsets) + 1)
        if table_size != self.table_size:
            raise ValueError(f"Section {self.index}: the offset table and the script count "
                             f"disagree ({table_size} != {self.table_size})")
        data = bytearray()
        for offset in self.entry_offsets:
            data += struct.pack("<I", offset)
        data += b"\x00\x00\x00\x00"
        for instruction in self.instructions:
            data += instruction.to_bytes()
        data += self.padding
        return bytes(data)


def indent_depths(section, entry_index):
    """How deep each instruction of a script sits, as a list parallel to its instructions.

    This is the interpreter's own structure: IF opens a condition list, THEN / ELSE / ELSE_IF
    open an action block, END closes one. ELSE_IF and ELSE do not step back out first, because
    the END that closed the branch before them already did.
    """
    start, end = section.script_range(entry_index)
    depths = []
    depth = 0
    for index in range(start, end):
        code = section.instructions[index].code
        if code in (0xFF01, 0xFF0A):  # IF / IF_BLOCK: the conditions go one level in
            depths.append(depth)
            depth += 1
        elif code in (0xFF0B, 0xFF04):  # THEN / THEN_ALWAYS: back out, then the actions go in
            depth = max(depth - 1, 0)
            depths.append(depth)
            depth += 1
        elif code in (0xFF0C, 0xFF0D):  # ELSE_IF / ELSE: already back out, so just go in
            depths.append(depth)
            depth += 1
        elif code == END_CODE:
            depth = max(depth - 1, 0)
            depths.append(depth)
        else:
            depths.append(depth)
    return depths


# How each structure opcode reads in the pseudo-code. "require" and "do" for the script's own
# condition list, because a failure there ends the script rather than picking another branch -
# which "if" / "then" would hide, since that is exactly what IF_BLOCK / THEN do instead.
PSEUDO_CODE_WORD = {
    0xFF01: "require", 0xFF04: "do",
    0xFF0A: "if", 0xFF0B: "then", 0xFF0C: "else if", 0xFF0D: "else", END_CODE: "end",
}


def to_pseudo_code(section, entry_index, text_lookup=None):
    """Render one script the way the interpreter walks it: an IF / THEN / ELSE tree.

    ``text_lookup`` is an optional ``id -> string`` mapping of section 13, used to show the
    dialog a SHOW_TEXT_BOX opens next to it.
    """
    start, end = section.script_range(entry_index)
    depths = indent_depths(section, entry_index)
    lines = []
    for index in range(start, end):
        instruction = section.instructions[index]
        for entry in section.entry_points_at(index):
            if entry != entry_index:
                lines.append(f"       <- script #{entry} starts here too")
        indent = "    " * depths[index - start]
        word = PSEUDO_CODE_WORD.get(instruction.code)
        text = word if word else _instruction_line(instruction, text_lookup)
        lines.append(f"{section.instruction_offset(index):>5}  {indent}{text}")
    return "\n".join(lines)


def _instruction_line(instruction, text_lookup):
    line = str(instruction)
    if text_lookup is not None and instruction.code in (0xFF1F, 0xFF23):
        text = text_lookup.get(instruction.param2)
        if text is not None:
            line += "   ; " + text.replace("\n", " / ")
    return line


# The world map reads the PSX pad button word straight out of the input layer, so a
# CHECK_BUTTON_INPUT mask is a set of DualShock bits (bit 6 = Cross, which is why every "press to
# interact" script on the world map tests 64). Same bit order as FF8GameData's button_config.json.
PAD_BUTTON_NAMES = ["L2", "R2", "L1", "R1", "Triangle", "Circle", "Cross", "Square",
                    "Select", "L3", "R3", "Start"]

# byte_2036B70, the world-map state, as CHECK_WORLD_MAP_STATE and SET_WORLD_MAP_STATE see it.
WORLD_MAP_STATE_NAMES = {
    0: "normal", 5: "vehicle 50 active", 6: "vehicle 50 approaching", 7: "Shumi train",
    8: "vehicle 48 active", 9: "vehicle 48 approaching", 10: "draw point open",
    13: "leaving to a field", 14: "player cannot move (a dialog is up)",
}

# CHECK_VEHICLE_TYPE values. 48 and 50 are left unnamed on purpose: the community notes call 48
# Balamb Garden and 50 the Ragnarok, while the IDB's own model tables say the opposite
# (Wm_ModelIdToVehicleCode maps world model 1 -> 50 and models 64/65 -> 48, and the same
# function's callers name model 1 the Garden). Nothing checked so far settles it, so the tool
# does not put a name on a number it cannot back up.
VEHICLE_NAMES = {
    33: "bike", 49: "the two big ships", 128: "on foot", 129: "the walking party",
    130: "Galbadia aircraft", 131: "trains", 132: "cars", 133: "cars",
}


def button_mask_text(mask):
    """The buttons a CHECK_BUTTON_INPUT mask stands for."""
    if mask == 0xFFFF:
        return "any button, or the stick pushed past 45"
    names = [name for bit, name in enumerate(PAD_BUTTON_NAMES) if mask & (1 << bit)]
    unknown = mask & ~((1 << len(PAD_BUTTON_NAMES)) - 1)
    if unknown:
        names.append(f"unknown bits 0x{unknown:04X}")
    return " + ".join(names) if names else "no button"


def value_text(instruction):
    """What this instruction's parameter stands for, when the tool can say ("" when it cannot)."""
    code = instruction.code
    if code == 0xFF20:
        return button_mask_text(instruction.word)
    if code == 0xFF25:
        return WORLD_MAP_STATE_NAMES.get(instruction.word, "")
    if code == 0xFF26:
        return WORLD_MAP_STATE_NAMES.get(instruction.param1, "")
    if code == 0xFF09:
        return VEHICLE_NAMES.get(instruction.word, "")
    return ""
