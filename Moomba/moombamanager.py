import os

from FF8GameData.gamedata import GameData
# The 68-byte entry format is shared with mmag.bin (the Zone editor): it lives in FF8GameData.
from FF8GameData.menu.magpage import MagPageEntry, OverlaySlot
from FF8GameData.menu.menutext import decode_string_section


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
        self.mngrp_text_list = decode_string_section(self.game_data, section_data)
        return len(self.mngrp_text_list)

    def get_overlay_text(self, text_id):
        """Preview string for a text overlay id (empty if unused or mngrp not loaded)."""
        if text_id == OverlaySlot.UNUSED_ID or not self.mngrp_text_list:
            return ""
        if 0 <= text_id < len(self.mngrp_text_list):
            return self.mngrp_text_list[text_id]
        return f"(no string {text_id} in mngrp raw file {self.MNGRP_TEXT_RAW_FILE})"
