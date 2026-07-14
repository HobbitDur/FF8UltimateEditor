import os

from FF8GameData.gamedata import GameData


class OverlaySlot:
    """One 4-byte overlay slot of a mmag/mmag2 entry (picture or text overlay).

    Layout (little endian):
        - offset 0 (int16): X position, relative to the window position
        - offset 2 (byte) : Y position
        - offset 3 (byte) : id (SP2 sprite id for picture slots, string id for text slots),
                            0xFF = slot unused
    """

    SIZE = 4
    UNUSED_ID = 0xFF

    def __init__(self, x=0, y=0, id=UNUSED_ID):
        self.x = x
        self.y = y
        self.id = id

    @classmethod
    def from_bytes(cls, slot_bytes):
        x = int.from_bytes(slot_bytes[0:2], byteorder='little', signed=True)
        return cls(x=x, y=slot_bytes[2], id=slot_bytes[3])

    def to_bytes(self):
        slot_bytes = bytearray()
        slot_bytes.extend((self.x & 0xFFFF).to_bytes(2, byteorder='little'))
        slot_bytes.append(self.y & 0xFF)
        slot_bytes.append(self.id & 0xFF)
        return slot_bytes

    @property
    def unused(self):
        return self.id == self.UNUSED_ID

    def __str__(self):
        if self.unused:
            return "OverlaySlot(unused)"
        return f"OverlaySlot(x: {self.x}, y: {self.y}, id: {self.id})"


class MagPageEntry:
    """One 68-byte page entry, the format shared by mmag.bin and mmag2.bin.

    Layout documented on the FF8ModdingWiki (Menu_mmag.md). All fields are kept, even the
    ones the Chocobo World screen (mmag2.bin) never reads (text file index, unlock block),
    so a load + save is byte-exact on both files. Zone (the mmag.bin editor) reuses this
    class and OverlaySlot for its own parsing.
    """

    SIZE = 68
    NB_OVERLAY_SLOTS = 4

    def __init__(self, entry_id=0):
        self.entry_id = entry_id
        # Text window rectangle
        self.window_x = 0
        self.window_y = 0
        self.window_width = 0
        self.window_height = 0
        # Page picture quad
        self.picture_x = 0
        self.picture_y = 0
        self.picture_width = 0  # 0 = no page picture
        self.picture_height = 0
        self.picture_scale_x = 0  # Multiplied by the zoom factor, /128
        self.picture_scale_y = 0
        self.picture_scale_z = 0
        # Paper background (PS1 GPU E1/E2 primitive bits)
        self.paper_param_a = 0
        self.paper_param_b = 0
        # The string section loaded for the book text is raw file 87 + this value
        # (unused by mmag2.bin, whose text comes from raw file 90)
        self.text_file_index = 0
        # Page texture: the loaded picture is raw file (category base) + page
        self.texture_category = 0
        self.texture_page = 0
        # Unlock block, only processed by the item-menu magazine reader (0xFF = none);
        # unused by mmag2.bin but preserved
        self.weapon_index = 0xFF
        self.weapon_line_spacing = 0xFF
        self.duel_move_id = 0xFF
        self.angelo_move_id = 0xFF
        self.weapon_list_x = 0
        self.weapon_list_y = 0
        self.weapon_quantity_column_x = 0
        self.duel_combo_x = 0
        self.duel_combo_y = 0
        # 1 = draw the "To be continued"-style footer line
        self.footer_flag = 0
        self.picture_overlays = [OverlaySlot() for _ in range(self.NB_OVERLAY_SLOTS)]
        self.text_overlays = [OverlaySlot() for _ in range(self.NB_OVERLAY_SLOTS)]

    @classmethod
    def from_bytes(cls, entry_id, entry_bytes):
        entry = cls(entry_id)

        def int16(offset):
            return int.from_bytes(entry_bytes[offset:offset + 2], byteorder='little', signed=True)

        entry.window_x = int16(0x00)
        entry.window_y = int16(0x02)
        entry.window_width = int16(0x04)
        entry.window_height = int16(0x06)
        entry.picture_x = int16(0x08)
        entry.picture_y = int16(0x0A)
        entry.picture_width = int16(0x0C)
        entry.picture_height = int16(0x0E)
        entry.picture_scale_x = entry_bytes[0x10]
        entry.picture_scale_y = entry_bytes[0x11]
        entry.picture_scale_z = entry_bytes[0x12]
        entry.paper_param_a = entry_bytes[0x13]
        entry.paper_param_b = entry_bytes[0x14]
        entry.text_file_index = entry_bytes[0x15]
        entry.texture_category = entry_bytes[0x16]
        entry.texture_page = entry_bytes[0x17]
        entry.weapon_index = entry_bytes[0x18]
        entry.weapon_line_spacing = entry_bytes[0x19]
        entry.duel_move_id = entry_bytes[0x1A]
        entry.angelo_move_id = entry_bytes[0x1B]
        entry.weapon_list_x = int16(0x1C)
        entry.weapon_list_y = entry_bytes[0x1E]
        entry.weapon_quantity_column_x = entry_bytes[0x1F]
        entry.duel_combo_x = int16(0x20)
        entry.duel_combo_y = entry_bytes[0x22]
        entry.footer_flag = entry_bytes[0x23]
        entry.picture_overlays = [
            OverlaySlot.from_bytes(entry_bytes[0x24 + i * OverlaySlot.SIZE:0x24 + (i + 1) * OverlaySlot.SIZE])
            for i in range(cls.NB_OVERLAY_SLOTS)]
        entry.text_overlays = [
            OverlaySlot.from_bytes(entry_bytes[0x34 + i * OverlaySlot.SIZE:0x34 + (i + 1) * OverlaySlot.SIZE])
            for i in range(cls.NB_OVERLAY_SLOTS)]
        return entry

    def to_bytes(self):
        entry_bytes = bytearray()

        def put_int16(value):
            entry_bytes.extend((value & 0xFFFF).to_bytes(2, byteorder='little'))

        put_int16(self.window_x)
        put_int16(self.window_y)
        put_int16(self.window_width)
        put_int16(self.window_height)
        put_int16(self.picture_x)
        put_int16(self.picture_y)
        put_int16(self.picture_width)
        put_int16(self.picture_height)
        entry_bytes.append(self.picture_scale_x & 0xFF)
        entry_bytes.append(self.picture_scale_y & 0xFF)
        entry_bytes.append(self.picture_scale_z & 0xFF)
        entry_bytes.append(self.paper_param_a & 0xFF)
        entry_bytes.append(self.paper_param_b & 0xFF)
        entry_bytes.append(self.text_file_index & 0xFF)
        entry_bytes.append(self.texture_category & 0xFF)
        entry_bytes.append(self.texture_page & 0xFF)
        entry_bytes.append(self.weapon_index & 0xFF)
        entry_bytes.append(self.weapon_line_spacing & 0xFF)
        entry_bytes.append(self.duel_move_id & 0xFF)
        entry_bytes.append(self.angelo_move_id & 0xFF)
        put_int16(self.weapon_list_x)
        entry_bytes.append(self.weapon_list_y & 0xFF)
        entry_bytes.append(self.weapon_quantity_column_x & 0xFF)
        put_int16(self.duel_combo_x)
        entry_bytes.append(self.duel_combo_y & 0xFF)
        entry_bytes.append(self.footer_flag & 0xFF)
        for slot in self.picture_overlays:
            entry_bytes.extend(slot.to_bytes())
        for slot in self.text_overlays:
            entry_bytes.extend(slot.to_bytes())
        return entry_bytes

    def __str__(self):
        return (f"MagPageEntry(id: {self.entry_id}, window: {self.window_width}x{self.window_height}, "
                f"texture: cat {self.texture_category} page {self.texture_page})")


class MoombaManager:
    """mmag2.bin editor logic: the 12 pages of the save-point Chocobo World screen
    (Mog story slides + Solo RPG manual), sharing the 68-byte entry format of mmag.bin (Zone).

    Differences from the magazine viewer in how the fields are used:
      - the text overlay ids reference the strings of mngrp.bin raw file 90 (story = ids 0-4,
        manual = ids 5-14), the text file index at 0x15 is not used;
      - the picture overlay ids are sprite ids 58-76 of the SP2 quad-list table at Pos 4;
      - the page textures are all category 6: raw file 180 (story) / 181 (manual) pictures;
      - the unlock block (0x18-0x22) is never processed.
    Unused fields are preserved byte-exact.

    Named after the Moombas, the evolved form of the Shumi — Mog's fellow treasure hunter
    on the Chocobo World screen is a Moomba."""

    NB_ENTRIES = 12
    MNGRP_TEXT_RAW_FILE = 90
    TEXTURE_CATEGORY = 6  # Raw file 180 (story pictures) + page, page 1 = raw 181 (manual)
    SP2_SPRITE_FIRST = 58  # Sprite ids of mngrp Pos 4 belonging to the Chocobo World screen
    SP2_SPRITE_LAST = 76

    DEFAULT_ENTRY_NAMES = [
        "Story slide 1 (Mog leaves)",
        "Story slide 2 (No one can stop him)",
        "Story slide 3 (Help Mog!)",
        "Manual 1/8: What is Solo-RPG!?",
        "Manual 2/8: Basic Operation",
        "Manual 3/8: Walk Screen",
        "Manual 4/8: Event Screen",
        "Manual 5/8: Battle Screen",
        "Manual 6/8: Map Screen and Movement",
        "Manual 7/8: Status Screen",
        "Manual 8/8: Optical Communication",
        "Manual 8/8: ChocoboWorld",
    ]

    def __init__(self, game_data: GameData):
        self.game_data = game_data
        self.file_path = ""
        self.entries = []
        self.mngrp_text_list = []  # Strings of mngrp raw file 90, indexed by text overlay id

    def get_entry_name(self, entry_id):
        """Chocobo World page map of the English PC release (unmodded entry layout)."""
        if 0 <= entry_id < len(self.DEFAULT_ENTRY_NAMES) and len(self.entries) == self.NB_ENTRIES:
            return self.DEFAULT_ENTRY_NAMES[entry_id]
        return f"Page {entry_id}"

    def load_file(self, file_path):
        with open(file_path, "rb") as in_file:
            file_data = in_file.read()
        if len(file_data) % MagPageEntry.SIZE != 0:
            raise ValueError(f"Not a mmag2.bin file: size {len(file_data)} is not a multiple "
                             f"of {MagPageEntry.SIZE} bytes")
        self.file_path = file_path
        self.entries = []
        for entry_id in range(len(file_data) // MagPageEntry.SIZE):
            offset = entry_id * MagPageEntry.SIZE
            self.entries.append(MagPageEntry.from_bytes(entry_id, file_data[offset:offset + MagPageEntry.SIZE]))

    def save_file(self, file_path=""):
        if not file_path:
            file_path = self.file_path
        file_data = bytearray()
        for entry in self.entries:
            file_data.extend(entry.to_bytes())
        with open(file_path, "wb") as out_file:
            out_file.write(file_data)

    def load_mngrp(self, mngrp_path, mngrphd_path=""):
        """Decode the Chocobo World strings (raw file 90 of mngrp.bin) for text overlay preview.
        mngrphd.bin is searched next to mngrp.bin if not given. Returns the number of strings."""
        from FF8GameData.FF8HexReader.mngrphd import Mngrphd
        if not mngrphd_path:
            mngrphd_path = os.path.join(os.path.dirname(mngrp_path), "mngrphd.bin")
        if not os.path.exists(mngrphd_path):
            raise FileNotFoundError(f"mngrphd.bin is needed to locate the sections of mngrp.bin, "
                                    f"not found at: {mngrphd_path}")
        with open(mngrphd_path, "rb") as in_file:
            mngrphd = Mngrphd(game_data=self.game_data, data_hex=bytearray(in_file.read()))
        header_entry = mngrphd.get_entry_list()[self.MNGRP_TEXT_RAW_FILE]
        if header_entry.invalid_value:
            raise ValueError(f"mngrp raw file {self.MNGRP_TEXT_RAW_FILE} is empty in this mngrphd.bin")
        with open(mngrp_path, "rb") as in_file:
            in_file.seek(header_entry.seek)
            section_data = in_file.read(header_entry.size)
        self.mngrp_text_list = self._decode_string_section(section_data)
        return len(self.mngrp_text_list)

    def _decode_string_section(self, section_data):
        """Decode a mngrp string section (offset table + FF8-encoded strings). The offsets are
        positional (a text id is an offset slot, zero offsets = empty string), like the game reads them."""
        nb_offset = int.from_bytes(section_data[0:2], byteorder='little')
        offset_list = [int.from_bytes(section_data[2 + i * 2:4 + i * 2], byteorder='little')
                       for i in range(nb_offset)]
        sorted_offsets = sorted(offset for offset in offset_list if offset != 0)
        text_list = []
        for offset in offset_list:
            if offset == 0:
                text_list.append("")
                continue
            next_index = sorted_offsets.index(offset) + 1
            end = sorted_offsets[next_index] if next_index < len(sorted_offsets) else len(section_data)
            text_list.append(self.game_data.translate_hex_to_str(section_data[offset:end]))
        return text_list

    def get_overlay_text(self, text_id):
        """Preview string for a text overlay id (empty if unused or mngrp not loaded)."""
        if text_id == OverlaySlot.UNUSED_ID or not self.mngrp_text_list:
            return ""
        if 0 <= text_id < len(self.mngrp_text_list):
            return self.mngrp_text_list[text_id]
        return f"(no string {text_id} in mngrp raw file {self.MNGRP_TEXT_RAW_FILE})"
