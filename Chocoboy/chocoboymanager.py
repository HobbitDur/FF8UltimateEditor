"""Reading and writing the parts of ``wmsetxx.obj`` that drive world-map events.

The file is 48 sections behind a header of 48 absolute offsets, closed by a zero word the way
the sections' own offset tables are. This tool opens six of them - the four script sections and
the two text sections the scripts talk to - and copies the other 42 through untouched. Saving
rebuilds the header, so a section is free to change size.
"""

import struct

from Chocoboy.wmsetscript import ScriptSection

NB_SECTION = 48
HEADER_SIZE = NB_SECTION * 4

SCRIPT_SECTION_LIST = [7, 9, 11, 36]
SPAWN_POSITION_SECTION = 10  # where the entities the section 9 scripts spawn are placed
DIALOG_SECTION = 13
LOCATION_NAME_SECTION = 31
TEXT_SECTION_LIST = [DIALOG_SECTION, LOCATION_NAME_SECTION]

SECTION_NAME = {
    7: "Player-location scripts",
    9: "Entity-spawn scripts",
    11: "Vehicle-warp scripts",
    36: "Global event scripts",
    13: "Dialog texts",
    31: "Location names",
}

SECTION_DESCRIPTION = {
    7: "Run when the player walks onto a location entry: field warps at docks and stations, "
       "and what a location offers when the game asks it what it could trigger.",
    9: "Run when the map loads, to spawn the world objects of the current state: party, "
       "vehicles, landmarks. These end on END rather than RETURN.",
    11: "Run when the player boards or rides a vehicle. They answer through SET_RETURN_VALUE.",
    36: "Evaluated every frame while the world map is up: side-quest flags, dialogs, item "
        "rewards, forced battles, docking states.",
    13: "The dialog strings SHOW_TEXT_BOX and SHOW_CHOICE_BOX open, by id.",
    31: "The world-map location names (towns, Gardens, Tears' Point...).",
}


class TextEntry:
    """One string of a text section, with the bytes it was read from.

    An untouched string is written back exactly as it came in, padding included, so opening and
    saving a file without editing anything gives the same bytes back.
    """

    def __init__(self, text, original_data):
        self.text = text
        self.original_text = text
        self.original_data = original_data

    @property
    def is_edited(self):
        return self.text != self.original_text


class TextSection:
    """A text section of wmsetxx.obj: an offset table, then FF8-encoded strings.

    Strings are stored padded to a 4-byte boundary, terminator included. Their count is fixed
    here: a script points at a string by index, so adding or removing one would renumber every
    dialog the scripts open.
    """

    def __init__(self, index, section_data, game_data):
        self.index = index
        self.game_data = game_data
        self.entries = []
        self.original_data = section_data  # for a section holding no string at all (see to_bytes)
        self._parse(section_data)

    def _parse(self, section_data):
        offsets = []
        read = 0
        while read + 4 <= len(section_data):
            offset = struct.unpack_from("<I", section_data, read)[0]
            read += 4
            if offset == 0:
                break
            offsets.append(offset)
        bounds = offsets + [len(section_data)]
        for index, start in enumerate(offsets):
            data = section_data[start:bounds[index + 1]]
            self.entries.append(TextEntry(self.game_data.translate_hex_to_str(list(data)), data))

    def to_bytes(self):
        if not self.entries:  # empty, or not a text section at all: hand the bytes back
            return self.original_data
        table_size = 4 * (len(self.entries) + 1)
        blobs = []
        for entry in self.entries:
            if entry.is_edited:
                encoded = bytes(self.game_data.translate_str_to_hex(entry.text)) + b"\x00"
                encoded += b"\x00" * (-len(encoded) % 4)  # every string starts on a 4-byte boundary
                blobs.append(encoded)
            else:
                blobs.append(entry.original_data)
        data = bytearray()
        offset = table_size
        for blob in blobs:
            data += struct.pack("<I", offset)
            offset += len(blob)
        data += b"\x00\x00\x00\x00"
        for blob in blobs:
            data += blob
        return bytes(data)

    def lookup(self):
        """``string id -> text``, for showing a dialog next to the opcode that opens it."""
        return {index: entry.text for index, entry in enumerate(self.entries)}


class SpawnPositionSection:
    """Section 10: where each world object an ADD_ENTITY spawns is placed.

    No header, 16 bytes per record. ``ADD_ENTITY``'s second parameter is an index into this
    list (``World_BuildObjectInstanceList``, FF8_EN.exe 0x544860, reads
    ``spawn_positions + 16 * param2``); ``0xFF`` means the object brings its own position, from
    the save game or from the code.
    """

    RECORD_SIZE = 16
    NO_POSITION = 0xFF

    def __init__(self, section_data):
        self.records = []
        for start in range(0, len(section_data) - len(section_data) % self.RECORD_SIZE,
                           self.RECORD_SIZE):
            x, y, z, yaw, pitch = struct.unpack_from("<iiihh", section_data, start)
            self.records.append({"x": x, "y": y, "z": z, "yaw": yaw, "pitch": pitch})

    # Model classes that ignore the position record and read their own saved position instead
    # (World_BuildObjectInstanceList special-cases each of them before the table lookup).
    SAVED_POSITION_MODELS = {1: "its saved position", 64: "its saved position",
                             65: "its saved position"}

    def describe(self, model_class, index):
        """One line about where an ADD_ENTITY puts the object it spawns."""
        saved = self.SAVED_POSITION_MODELS.get(model_class)
        if saved:
            return f"model {model_class} ignores the record and spawns at {saved}"
        if index == self.NO_POSITION:
            return "no position record: the object places itself"
        if not 0 <= index < len(self.records):
            return f"position record {index}, which section 10 does not have"
        record = self.records[index]
        return (f"position record {index}: x {record['x']}, y {record['y']}, z {record['z']}, "
                f"yaw {record['yaw']}")


class ChocoboyManager:
    """The open ``wmsetxx.obj``: its six editable sections, and the raw bytes of the other 42."""

    def __init__(self, game_data):
        self.game_data = game_data
        self.file_path = ""
        self.header_tail = b""  # what sits between the 48 offsets and section 0, kept as read
        self.raw_sections = []  # every section as read, so untouched ones are written back as-is
        self.script_sections = {}  # section index -> ScriptSection
        self.text_sections = {}  # section index -> TextSection
        self.spawn_positions = None  # SpawnPositionSection, what ADD_ENTITY points at

    @property
    def is_loaded(self):
        return bool(self.raw_sections)

    def load_file(self, file_path):
        with open(file_path, "rb") as in_file:
            file_data = in_file.read()
        if len(file_data) < HEADER_SIZE:
            raise ValueError(f"{file_path} is too small to be a wmsetxx.obj")
        offsets = [struct.unpack_from("<I", file_data, index * 4)[0] for index in range(NB_SECTION)]
        if offsets[0] < HEADER_SIZE or offsets[0] > len(file_data):
            raise ValueError("This does not look like a wmsetxx.obj: section 0 starts at "
                             f"{offsets[0]}, which is not after the 48-offset header")
        self.header_tail = file_data[HEADER_SIZE:offsets[0]]
        bounds = offsets + [len(file_data)]
        self.raw_sections = [file_data[bounds[index]:bounds[index + 1]] for index in range(NB_SECTION)]
        self.script_sections = {index: ScriptSection(index, self.raw_sections[index])
                                for index in SCRIPT_SECTION_LIST}
        self.text_sections = {index: TextSection(index, self.raw_sections[index], self.game_data)
                              for index in TEXT_SECTION_LIST}
        self.spawn_positions = SpawnPositionSection(self.raw_sections[SPAWN_POSITION_SECTION])
        self.file_path = file_path

    def save_file(self, file_path=""):
        if not file_path:
            file_path = self.file_path
        sections = list(self.raw_sections)
        for index, script_section in self.script_sections.items():
            sections[index] = script_section.to_bytes()
        for index, text_section in self.text_sections.items():
            sections[index] = text_section.to_bytes()
        file_data = bytearray()
        offset = HEADER_SIZE + len(self.header_tail)
        for section in sections:
            file_data += struct.pack("<I", offset)
            offset += len(section)
        file_data += self.header_tail
        for section in sections:
            file_data += section
        with open(file_path, "wb") as out_file:
            out_file.write(file_data)
        self.file_path = file_path

    def dialog_lookup(self):
        text_section = self.text_sections.get(DIALOG_SECTION)
        return text_section.lookup() if text_section else {}

    def find_instruction_users(self, match, describe):
        """Every instruction of every script section that ``match`` accepts, as text lines.

        ``match(instruction)`` says whether an instruction counts, ``describe(instruction)`` says
        what it does with the thing being looked up. This is how the tool answers "what else
        touches this?" - which, for a save-game flag shared by half a side quest, is the only way
        to see the whole of it.
        """
        users = []
        for index in SCRIPT_SECTION_LIST:
            section = self.script_sections[index]
            for entry in range(len(section.entry_offsets)):
                start, end = section.script_range(entry)
                for position in range(start, end):
                    instruction = section.instructions[position]
                    if match(instruction):
                        users.append(f"Section {index}, script #{entry}, offset "
                                     f"{section.instruction_offset(position)}: "
                                     f"{describe(instruction)}")
        return users

    def find_flag_users(self, flag):
        """Everywhere save-game world bit ``flag`` (0-63) is read or written."""
        return self.find_instruction_users(
            lambda instruction: (instruction.code in (0xFF27, 0xFF28)
                                 and instruction.param1 == flag),
            lambda instruction: ("checks it is " if instruction.code == 0xFF27 else "sets it to ")
                                + str(instruction.param2))

    def find_script_var_users(self, var):
        """Everywhere save-game script byte ``var`` (0 or 1) is read or written."""
        compare = {0xFF2D: "checks it equals", 0xFF30: "checks it is under",
                   0xFF31: "checks it is over", 0xFF2E: "sets it to"}
        return self.find_instruction_users(
            lambda instruction: instruction.code in compare and instruction.param1 == var,
            lambda instruction: f"{compare[instruction.code]} {instruction.param2}")

    def find_message_window_users(self, window):
        """Everywhere message window ``window`` (0-12) is opened, closed or tested."""
        opened = {0xFF1F: "opens it on text", 0xFF23: "opens it as a choice on text"}
        return self.find_instruction_users(
            lambda instruction: (
                (instruction.code in opened and instruction.param1 == window)
                or (instruction.code == 0xFF24 and instruction.word == window)
                or (instruction.code == 0xFF2C and instruction.param1 == window)),
            lambda instruction:
                f"{opened[instruction.code]} {instruction.param2}" if instruction.code in opened
                else ("closes it" if instruction.code == 0xFF24
                      else f"checks it is {'open' if instruction.param2 else 'closed'}"))

    def find_text_users(self, text_id):
        """Every SHOW_TEXT_BOX / SHOW_CHOICE_BOX opening dialog ``text_id``, as text lines.

        A dialog is only ever reached from a script, so this is how you find out what a string
        is for - and what would break if you rewrote it.
        """
        return self.find_instruction_users(
            lambda instruction: (instruction.code in (0xFF1F, 0xFF23)
                                 and instruction.param2 == text_id),
            lambda instruction: f"{instruction.name} in window {instruction.param1}")
