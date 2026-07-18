import json
import os

from FF8GameData.gamedata import GameData
# The 68-byte entry format and the shared mngrp render source live in FF8GameData,
# so both the Zone (mmag.bin) and Moomba (mmag2.bin) editors build on them.
from FF8GameData.menu.magpage import MagPageEntry, OverlaySlot, UNUSED_ID
from FF8GameData.menu.magpagemanager import TEXTURE_CATEGORIES, MagPageManager
from FF8GameData.menu.mngrp.string.sectionstring import SectionString
from FF8GameData.menu.mngrp.tkmnmes.sectiontkmnmes import SectionTkmnmes

BOOK_TEXT_FIRST_RAW_FILE = 87  # text file index n loads mngrp.bin raw file 87 + n

# kernel.bin Duel (Zell limit break) section: the header is a flat table of u32
# section offsets, and the Duel one lives in the slot at 0x5C. Each of the 10
# moves is a 32-byte FF8KernelZellLimitDuell whose button sequence is 5 u16 at
# offset 16, terminated by 0xFFFF (Menu_ItemMagazine_DrawPage walks it that way).
DUEL_SECTION_OFFSET_SLOT = 0x5C
DUEL_ENTRY_SIZE = 32
DUEL_NB_MOVE = 10
DUEL_SEQUENCE_OFFSET = 16
DUEL_SEQUENCE_MAX = 5
DUEL_SEQUENCE_END = 0xFFFF

# A Duel button code is a pad bitmask. The engine masks out bits 8-11 (Select,
# L3, R3, Start - never part of a combo), takes the lowest bit still set, and
# adds 128 to get the icon.sp1 id: 128-131 = L2/R2/L1/R1, 132-135 = the four face
# buttons, 140-143 = the four d-pad directions.
BUTTON_CODE_MASK = 0xF0FF
BUTTON_ICON_FIRST = 128

# The item's type icon: byte_B88024 in the exe maps the mitem.bin row's item type
# to one of 7 icons, and the draw adds 223 to reach the icon.sp1 id.
ITEM_TYPE_ICON_TABLE = (0, 0, 0, 1, 1, 1, 2, 3, 4, 5, 6, 1,
                        3, 3, 3, 3, 6, 1, 1, 6, 6, 0, 0, 0)
ITEM_TYPE_ICON_FIRST = 223

# The footer line Menu_Magazine_Draw draws when the entry's footer flag is set:
# getMenuString(1, 13, 28) resolves to tkmnmes3.bin, the scroll hint of the multi-page books.
FOOTER_RAW_FILE = 2  # tkmnmes3.bin
FOOTER_SECTION = 13
FOOTER_INDEX = 28

WEAPONS_MONTHLY_ISSUES = ["1st", "March", "April", "May", "June", "July", "August"]
OCCULT_FAN_ISSUES = ["I", "II", "III", "IV"]

# Kernel Duel move list order (byte 0x1A) and savemap Angelo move order (byte 0x1B).
DUEL_MOVE_NAMES = ["Punch Rush", "Booya", "Heel Drop", "Mach Kick", "Dolphin Blow",
                   "Meteor Strike", "Burning Rave", "Meteor Barret", "Different Beat",
                   "My Final Heaven"]
ANGELO_MOVE_NAMES = ["Angelo Rush", "Angelo Recover", "Angelo Reverse", "Angelo Search",
                     "Angelo Cannon", "Angelo Strike", "Invincible Moon", "Wishing Star"]


class ZoneManager(MagPageManager):
    """mmag.bin editor logic (in-menu magazine page definitions).

    Named after Zone, the Forest Owls member and devoted collector of "The Girl
    Next Door" magazine — no one in FF8 cares more about magazine pages.

    mmag.bin is an array of 68-byte entries with no header (69 entries in the
    English PC release): each entry is one page view of the item-menu magazines
    (Weapons Monthly, Combat King, Pet Pals, Occult Fan) or the tutorial-menu
    books (whose entry ranges come from mtmag.bin, see the Piet tool).

    The full magazine page is drawn, so every DRAWS_* layer stays on (inherited)."""

    FILE_LABEL = "mmag.bin"

    def __init__(self, game_data: GameData):
        super().__init__(game_data)
        self.weapon_name_list = self._load_weapon_names()
        self._book_text_cache = {}
        # The unlock block only draws with these: kernel.bin gives Zell's Duel button
        # sequences, mwepon.bin the weapon remodel item lists. Loaded on demand.
        self._duel_sequences = None
        self._weapon_upgrades = None
        # icon.sp1 (+ icon.TEX) draws the unlock block's icons, mitem.bin says
        # which type icon an item uses.
        self._icons = None
        self._icon_tex = None
        self._icon_cache = {}
        self._menu_items = None

    def _load_weapon_names(self):
        file_path = os.path.join(self.game_data.resource_folder_json, "weapon.json")
        with open(file_path, encoding="utf8") as f:
            weapon_data = json.load(f)
        return [weapon["name"] for weapon in weapon_data["weapons"]]

    def _on_mngrp_loaded(self):
        self._book_text_cache = {}

    @staticmethod
    def book_text_raw_file(entry: MagPageEntry):
        """mngrp.bin raw file index of the entry's book-text string section."""
        return BOOK_TEXT_FIRST_RAW_FILE + entry.text_file_index

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

    def get_weapon_name(self, weapon_index):
        if weapon_index == UNUSED_ID:
            return "None"
        if 0 <= weapon_index < len(self.weapon_name_list):
            return self.weapon_name_list[weapon_index]
        return f"Weapon {weapon_index}"

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

    def load_kernel(self, kernel_path):
        """Read Zell's Duel button sequences out of kernel.bin.

        Only the Duel section is parsed: the magazine draw needs nothing else from
        the kernel, and SolomonRing is the editor for the rest of it."""
        with open(kernel_path, "rb") as in_file:
            data = in_file.read()
        section_offset = int.from_bytes(
            data[DUEL_SECTION_OFFSET_SLOT:DUEL_SECTION_OFFSET_SLOT + 4], byteorder='little')
        end = section_offset + DUEL_ENTRY_SIZE * DUEL_NB_MOVE
        if not 0 < section_offset < len(data) or end > len(data):
            raise ValueError(f"Not a kernel.bin file: the Duel section offset "
                             f"({section_offset}) does not fit in {len(data)} bytes")
        sequences = []
        for move_id in range(DUEL_NB_MOVE):
            entry = data[section_offset + DUEL_ENTRY_SIZE * move_id:]
            sequence = []
            for i in range(DUEL_SEQUENCE_MAX):
                offset = DUEL_SEQUENCE_OFFSET + i * 2
                code = int.from_bytes(entry[offset:offset + 2], byteorder='little')
                if code == DUEL_SEQUENCE_END:
                    break
                sequence.append(code)
            sequences.append(sequence)
        self._duel_sequences = sequences

    @property
    def kernel_loaded(self):
        return self._duel_sequences is not None

    def duel_sequence(self, move_id):
        """The button codes of a Duel move (empty when kernel.bin is not loaded)."""
        if not self.kernel_loaded or not 0 <= move_id < len(self._duel_sequences):
            return []
        return self._duel_sequences[move_id]

    def load_mwepon(self, mwepon_path):
        """Read the weapon remodel item lists out of mwepon.bin (Junkshop owns the format)."""
        from Junkshop.junkshopmanager import JunkshopManager
        junkshop = JunkshopManager(self.game_data)
        junkshop.load_file(mwepon_path)
        self._weapon_upgrades = junkshop.weapon_upgrades

    @property
    def mwepon_loaded(self):
        return self._weapon_upgrades is not None

    def weapon_items(self, weapon_index):
        """The [item_id, quantity] pairs of a weapon's remodel line, empty ones dropped."""
        if not self.mwepon_loaded or not 0 <= weapon_index < len(self._weapon_upgrades):
            return []
        return [(item_id, quantity)
                for item_id, quantity in self._weapon_upgrades[weapon_index].items if item_id]

    def load_icons(self, icon_sp1_path):
        """Load the menu icon table (icon.sp1) and its texture (icon.TEX, read from
        the same folder). Minimog owns both formats."""
        from FF8GameData.tex.texfile import TexFile
        from Minimog.minimogmanager import MinimogManager
        tex_path = os.path.join(os.path.dirname(icon_sp1_path), "icon.TEX")
        if not os.path.exists(tex_path):
            raise FileNotFoundError(f"icon.TEX holds the pixels icon.sp1 points at, "
                                    f"not found at: {tex_path}")
        minimog = MinimogManager(self.game_data)
        minimog.load_file(icon_sp1_path)
        self._icons = minimog
        self._icon_tex = TexFile.read(tex_path)
        self._icon_cache = {}

    @property
    def icons_loaded(self):
        return self._icons is not None

    def icon_image(self, icon_id):
        """(image, dx, dy) of a menu icon, the offsets being where its top-left
        sits relative to the position the engine draws it at. None when there is
        no such icon, or icon.sp1 is not loaded."""
        if not self.icons_loaded or not 0 <= icon_id < len(self._icons.icons):
            return None
        if icon_id not in self._icon_cache:
            image = self._icons.render_icon(icon_id, self._icon_tex)
            box = self._icons.icons[icon_id].bounding_box()
            self._icon_cache[icon_id] = None if image is None else (image, box[0], box[1])
        return self._icon_cache[icon_id]

    @staticmethod
    def button_icon_id(button_code):
        """The icon.sp1 id of a Duel button code, the way the engine picks it."""
        masked = button_code & BUTTON_CODE_MASK
        for bit in range(16):
            if masked & (1 << bit):
                return BUTTON_ICON_FIRST + bit
        return None

    def load_mitem(self, mitem_path):
        """Load mitem.bin for the items' types (Kadowaki owns the format)."""
        from Kadowaki.kadowakimanager import KadowakiManager
        if not self.game_data.item_data_json:
            self.game_data.load_item_data()  # KadowakiManager names its rows as it loads
        kadowaki = KadowakiManager(self.game_data)
        kadowaki.load_file(mitem_path)
        self._menu_items = kadowaki.menu_items

    @property
    def mitem_loaded(self):
        return self._menu_items is not None

    def item_icon_id(self, item_id):
        """The icon.sp1 id of an item's type icon (None without mitem.bin)."""
        if not self.mitem_loaded or not 0 <= item_id < len(self._menu_items):
            return None
        type_id = self._menu_items[item_id].type_id
        if not 0 <= type_id < len(ITEM_TYPE_ICON_TABLE):
            return None
        return ITEM_TYPE_ICON_FIRST + ITEM_TYPE_ICON_TABLE[type_id]

    def get_item_name(self, item_id):
        """The item's display name. It gets drawn as FF8 text, so it has to be
        spelled with characters the game's font table has (the engine reads these
        names out of kernel.bin itself, getTextBattleItem at 0x47EA30; item.json
        is the tools' copy of them)."""
        if not self.game_data.item_data_json:
            self.game_data.load_item_data()
        for item in self.game_data.item_data_json["items"]:
            if item["id"] == item_id:
                return item["name"]
        return f"Item {item_id}"

    def get_footer_text(self):
        """The footer line of the multi-page books: menu string 1/13/28, the
        "{CrossLeft} {CrossRight} to scroll" hint (empty when mngrp is not loaded).

        Menu_Magazine_Draw calls getMenuString(1, 13, 28, 0) at 0x4C9611."""
        data = self.get_raw_file(FOOTER_RAW_FILE)
        if not data:
            return ""
        subsection = SectionTkmnmes(game_data=self.game_data,
                                    data_hex=bytearray(data)).get_text_section_by_slot(FOOTER_SECTION)
        if not subsection:
            return ""
        texts = subsection.get_text_by_slot()
        entry = 2 * FOOTER_INDEX  # variant 0
        return texts[entry] if entry < len(texts) else ""

    def get_book_texts(self, text_file_index):
        """Decoded strings of the book-text string section raw file 87 + text_file_index
        (empty list when no mngrp is loaded or the raw file is invalid)."""
        if not self.mngrp_loaded:
            return []
        if text_file_index not in self._book_text_cache:
            raw_file = BOOK_TEXT_FIRST_RAW_FILE + text_file_index
            section_data = self.get_raw_file(raw_file)
            texts = []
            if section_data:
                texts = SectionString(game_data=self.game_data,
                                      data_hex=bytearray(section_data)).get_text_by_slot()
            self._book_text_cache[text_file_index] = texts
        return self._book_text_cache[text_file_index]

    def get_overlay_text(self, entry: MagPageEntry, overlay: OverlaySlot):
        """Resolve a text overlay slot to its string (needs load_mngrp first)."""
        if overlay.unused:
            return ""
        texts = self.get_book_texts(entry.text_file_index)
        if 0 <= overlay.id < len(texts):
            return texts[overlay.id]
        return f"(no string {overlay.id} in mngrp raw file {self.book_text_raw_file(entry)})"
