import json
import os
import struct

from FF8GameData.gamedata import GameData

ENTRY_SIZE = 68
NB_OVERLAY_SLOTS = 4
UNUSED_ID = 0xFF
BOOK_TEXT_FIRST_RAW_FILE = 87  # text file index n loads mngrp.bin raw file 87 + n

# Page texture category -> (name, base raw file inside mngrp.bin); the loaded
# picture file is base + texture_page. Any other category uses the page number
# directly as the raw file index.
TEXTURE_CATEGORIES = {
    0: ("Weapons Monthly", 28),
    1: ("Combat King", 20),
    2: ("Pet Pals", 24),
    3: ("Occult Fan", 44),
    4: ("Cards (unused)", 48),
    5: ("Card rules / battle tutorial", 71),
    6: ("Card icon explanation", 180),
}

WEAPONS_MONTHLY_ISSUES = ["1st", "March", "April", "May", "June", "July", "August"]
OCCULT_FAN_ISSUES = ["I", "II", "III", "IV"]

# Kernel Duel move list order (byte 0x1A) and savemap Angelo move order (byte 0x1B).
DUEL_MOVE_NAMES = ["Punch Rush", "Booya", "Heel Drop", "Mach Kick", "Dolphin Blow",
                   "Meteor Strike", "Burning Rave", "Meteor Barret", "Different Beat",
                   "My Final Heaven"]
ANGELO_MOVE_NAMES = ["Angelo Rush", "Angelo Recover", "Angelo Reverse", "Angelo Search",
                     "Angelo Cannon", "Angelo Strike", "Invincible Moon", "Wishing Star"]


def decode_string_section(game_data: GameData, section_data):
    """Decode a mngrp string section (offset table + FF8-encoded strings). The offsets are
    positional (a text id is an offset slot, zero offsets = empty string), like the game
    reads them."""
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
        text_list.append(game_data.translate_hex_to_str(section_data[offset:end]))
    return text_list


class ZoneOverlay:
    """One 4-byte overlay slot: {uint16 x, uint8 y, uint8 id}, id 0xFF = unused.

    Picture overlays index the SP2 quad-list sprite table at Pos 4 of mngrp.bin,
    text overlays index the book-text string section (raw file 87 + text_file_index)."""

    def __init__(self, x=0, y=0, id=UNUSED_ID):
        self.x = x
        self.y = y
        self.id = id

    @property
    def used(self):
        return self.id != UNUSED_ID

    @classmethod
    def from_bytes(cls, data):
        x, y, slot_id = struct.unpack("<HBB", data)
        return cls(x, y, slot_id)

    def to_bytes(self):
        return struct.pack("<HBB", self.x, self.y, self.id)

    def __str__(self):
        if not self.used:
            return "unused"
        return f"id {self.id} at ({self.x},{self.y})"


class ZoneEntry:
    """One 68-byte entry of mmag.bin: a single magazine page view. The format is
    shared with mmag2.bin (the Chocobo World screens, see the Moomba tool).

    The unlock fields (weapon_id/duel_move_id/angelo_move_id and their layout
    coordinates) are only processed by the item-menu reader (entries 0-42):
    displaying the page is what unlocks the weapon/move in the savemap. The
    tutorial-book viewer (entries 43-67) ignores them."""

    def __init__(self):
        # Text window rect (24,8,336,184/208 in all retail entries)
        self.window_x = 0
        self.window_y = 0
        self.window_width = 0
        self.window_height = 0
        # Page picture rect (width 0 = no picture) and /128 scale factors
        self.picture_x = 0
        self.picture_y = 0
        self.picture_width = 0
        self.picture_height = 0
        self.picture_scale_x = 0
        self.picture_scale_y = 0
        self.picture_scale_z = 0
        # Paper background PS1 GPU primitive parameters
        self.paper_e1 = 0  # E1 texture page bits
        self.paper_e2 = 0  # E2 texture window bits
        # Book text: string section is mngrp raw file 87 + this
        self.text_file_index = 0
        # Page picture texture (see TEXTURE_CATEGORIES)
        self.texture_category = 0
        self.texture_page = 0
        # Unlock block (0xFF = none)
        self.weapon_id = UNUSED_ID  # unlocked-weapons bit + mwepon.bin remodel line
        self.weapon_line_spacing = 0
        self.duel_move_id = UNUSED_ID  # Zell Duel move (kernel Duel data)
        self.angelo_move_id = UNUSED_ID  # Angelo move
        self.weapon_list_x = 0
        self.weapon_list_y = 0
        self.weapon_quantity_x_offset = 0
        self.duel_combo_x = 0
        self.duel_combo_y = 0
        # 1 = draw the "To be continued"-style footer line
        self.footer_flag = 0
        self.picture_overlays = [ZoneOverlay() for _ in range(NB_OVERLAY_SLOTS)]
        self.text_overlays = [ZoneOverlay() for _ in range(NB_OVERLAY_SLOTS)]

    @classmethod
    def from_bytes(cls, data):
        if len(data) != ENTRY_SIZE:
            raise ValueError(f"mmag entry must be {ENTRY_SIZE} bytes, got {len(data)}")
        entry = cls()
        (entry.window_x, entry.window_y, entry.window_width, entry.window_height,
         entry.picture_x, entry.picture_y, entry.picture_width, entry.picture_height) = \
            struct.unpack_from("<8H", data, 0x00)
        (entry.picture_scale_x, entry.picture_scale_y, entry.picture_scale_z,
         entry.paper_e1, entry.paper_e2, entry.text_file_index,
         entry.texture_category, entry.texture_page,
         entry.weapon_id, entry.weapon_line_spacing,
         entry.duel_move_id, entry.angelo_move_id) = struct.unpack_from("<12B", data, 0x10)
        entry.weapon_list_x, entry.weapon_list_y, entry.weapon_quantity_x_offset = \
            struct.unpack_from("<HBB", data, 0x1C)
        entry.duel_combo_x, entry.duel_combo_y, entry.footer_flag = \
            struct.unpack_from("<HBB", data, 0x20)
        entry.picture_overlays = [ZoneOverlay.from_bytes(data[0x24 + i * 4:0x28 + i * 4])
                                  for i in range(NB_OVERLAY_SLOTS)]
        entry.text_overlays = [ZoneOverlay.from_bytes(data[0x34 + i * 4:0x38 + i * 4])
                               for i in range(NB_OVERLAY_SLOTS)]
        return entry

    def to_bytes(self):
        data = bytearray()
        data.extend(struct.pack("<8H", self.window_x, self.window_y,
                                self.window_width, self.window_height,
                                self.picture_x, self.picture_y,
                                self.picture_width, self.picture_height))
        data.extend(struct.pack("<12B", self.picture_scale_x, self.picture_scale_y,
                                self.picture_scale_z, self.paper_e1, self.paper_e2,
                                self.text_file_index, self.texture_category,
                                self.texture_page, self.weapon_id,
                                self.weapon_line_spacing, self.duel_move_id,
                                self.angelo_move_id))
        data.extend(struct.pack("<HBB", self.weapon_list_x, self.weapon_list_y,
                                self.weapon_quantity_x_offset))
        data.extend(struct.pack("<HBB", self.duel_combo_x, self.duel_combo_y,
                                self.footer_flag))
        for overlay in self.picture_overlays:
            data.extend(overlay.to_bytes())
        for overlay in self.text_overlays:
            data.extend(overlay.to_bytes())
        return bytes(data)

    @property
    def book_text_raw_file(self):
        """mngrp.bin raw file index of the book-text string section."""
        return BOOK_TEXT_FIRST_RAW_FILE + self.text_file_index

    @property
    def texture_raw_file(self):
        """mngrp.bin raw file index of the page picture TIM."""
        if self.texture_category in TEXTURE_CATEGORIES:
            return TEXTURE_CATEGORIES[self.texture_category][1] + self.texture_page
        return self.texture_page


class ZoneManager:
    """mmag.bin editor logic (in-menu magazine page definitions).

    Named after Zone, the Forest Owls member and devoted collector of "The Girl
    Next Door" magazine — no one in FF8 cares more about magazine pages.

    mmag.bin is an array of 68-byte entries with no header (69 entries in the
    English PC release): each entry is one page view of the item-menu magazines
    (Weapons Monthly, Combat King, Pet Pals, Occult Fan) or the tutorial-menu
    books (whose entry ranges come from mtmag.bin, see the Piet tool)."""

    def __init__(self, game_data: GameData):
        self.game_data = game_data
        self.file_path = ""
        self.entries = []
        self.weapon_name_list = self._load_weapon_names()
        # mngrp.bin (for the text overlay preview), decoded lazily per text file index
        self._mngrp_data = None
        self._mngrp_header_entries = None
        self._book_text_cache = {}

    def _load_weapon_names(self):
        file_path = os.path.join(self.game_data.resource_folder_json, "weapon.json")
        with open(file_path, encoding="utf8") as f:
            weapon_data = json.load(f)
        return [weapon["name"] for weapon in weapon_data["weapons"]]

    def load_file(self, file_path):
        with open(file_path, "rb") as in_file:
            file_data = in_file.read()
        if len(file_data) % ENTRY_SIZE != 0:
            raise ValueError(f"mmag file size must be a multiple of {ENTRY_SIZE} bytes, "
                             f"got {len(file_data)}")
        self.file_path = file_path
        self.entries = [ZoneEntry.from_bytes(file_data[i:i + ENTRY_SIZE])
                        for i in range(0, len(file_data), ENTRY_SIZE)]

    def save_file(self, file_path=""):
        if not file_path:
            file_path = self.file_path
        with open(file_path, "wb") as out_file:
            for entry in self.entries:
                out_file.write(entry.to_bytes())

    @staticmethod
    def entry_name(index):
        """Magazine map of the English PC release (unmodded entry layout)."""
        if 0 <= index <= 27:
            issue = WEAPONS_MONTHLY_ISSUES[index // 4]
            return f"Weapons Monthly {issue} Issue {index % 4 + 1}/4"
        if 28 <= index <= 32:
            return f"Combat King {index - 27:03d}"
        if 33 <= index <= 38:
            return f"Pet Pals Vol.{index - 32}"
        if 39 <= index <= 42:
            return f"Occult Fan {OCCULT_FAN_ISSUES[index - 39]}"
        if 43 <= index <= 50:
            return f"Battle tutorial {index - 42}/8"
        if 51 <= index <= 63:
            return f"Card rules {index - 50}/13"
        if 64 <= index <= 67:
            return f"Card icon explanation {index - 63}/4"
        if index == 68:
            return "Empty terminator"
        return f"Entry {index}"

    def get_weapon_name(self, weapon_id):
        if weapon_id == UNUSED_ID:
            return "None"
        if 0 <= weapon_id < len(self.weapon_name_list):
            return self.weapon_name_list[weapon_id]
        return f"Weapon {weapon_id}"

    @staticmethod
    def get_duel_move_name(move_id):
        if move_id == UNUSED_ID:
            return "None"
        if 0 <= move_id < len(DUEL_MOVE_NAMES):
            return DUEL_MOVE_NAMES[move_id]
        return f"Duel move {move_id}"

    @staticmethod
    def get_angelo_move_name(move_id):
        if move_id == UNUSED_ID:
            return "None"
        if 0 <= move_id < len(ANGELO_MOVE_NAMES):
            return ANGELO_MOVE_NAMES[move_id]
        return f"Angelo move {move_id}"

    @staticmethod
    def get_texture_category_name(category):
        if category in TEXTURE_CATEGORIES:
            return TEXTURE_CATEGORIES[category][0]
        return f"Direct raw file (category {category})"

    def load_mngrp(self, mngrp_path, mngrphd_path=""):
        """Load mngrp.bin (+ its mngrphd.bin section table, auto-detected next to it
        when not given) so text overlay ids can be resolved to the actual strings."""
        from FF8GameData.FF8HexReader.mngrphd import Mngrphd
        if not mngrphd_path:
            mngrphd_path = os.path.join(os.path.dirname(mngrp_path), "mngrphd.bin")
        if not os.path.exists(mngrphd_path):
            raise FileNotFoundError(f"mngrphd.bin is needed to locate the sections of mngrp.bin, "
                                    f"not found at: {mngrphd_path}")
        with open(mngrphd_path, "rb") as in_file:
            header = Mngrphd(game_data=self.game_data, data_hex=bytearray(in_file.read()))
        with open(mngrp_path, "rb") as in_file:
            self._mngrp_data = in_file.read()
        self._mngrp_header_entries = header.get_entry_list()
        self._book_text_cache = {}

    @property
    def mngrp_loaded(self):
        return self._mngrp_data is not None

    def get_book_texts(self, text_file_index):
        """Decoded strings of the book-text string section raw file 87 + text_file_index
        (empty list when no mngrp is loaded or the raw file is invalid)."""
        if not self.mngrp_loaded:
            return []
        if text_file_index not in self._book_text_cache:
            raw_file = BOOK_TEXT_FIRST_RAW_FILE + text_file_index
            texts = []
            if 0 <= raw_file < len(self._mngrp_header_entries):
                header_entry = self._mngrp_header_entries[raw_file]
                if not header_entry.invalid_value:
                    section_data = self._mngrp_data[header_entry.seek:
                                                    header_entry.seek + header_entry.size]
                    texts = decode_string_section(self.game_data, section_data)
            self._book_text_cache[text_file_index] = texts
        return self._book_text_cache[text_file_index]

    def get_overlay_text(self, entry: ZoneEntry, overlay: ZoneOverlay):
        """Resolve a text overlay slot to its string (needs load_mngrp first)."""
        if not overlay.used:
            return ""
        texts = self.get_book_texts(entry.text_file_index)
        if 0 <= overlay.id < len(texts):
            return texts[overlay.id]
        return f"<string {overlay.id} not found in mngrp raw file {entry.book_text_raw_file}>"
