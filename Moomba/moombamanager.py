from FF8GameData.gamedata import GameData
# The 68-byte entry format and the shared mngrp render source live in FF8GameData,
# so Moomba (mmag2.bin) and Zone (mmag.bin) build on the same base.
from FF8GameData.menu.magpage import MagPageEntry, OverlaySlot
from FF8GameData.menu.magpagemanager import MagPageManager
from FF8GameData.menu.mngrp.string.sectionstring import SectionString

MNGRP_TEXT_RAW_FILE = 90  # The Chocobo World strings (story 0-4, manual 5-14)


class MoombaManager(MagPageManager):
    """mmag2.bin editor logic: the 12 pages of the save-point Chocobo World screen
    (Mog story slides + Solo RPG manual), sharing the 68-byte entry format of mmag.bin (Zone).

    Differences from the magazine viewer in how the fields are used
    (Menu_ChocoboWorld_Draw at 0x4D1D30):
      - the text overlay ids reference the strings of mngrp.bin raw file 90 (story = ids 0-4,
        manual = ids 5-14), the text file index at 0x15 is not used;
      - the picture overlay ids are sprite ids 58-76 of the SP2 quad-list table at Pos 4;
      - the page textures are all category 6: raw file 180 (story) / 181 (manual) pictures;
      - **only the two overlay layers are drawn** - no window, paper, mat, unlock block or
        footer; those are the Chocobo World screen's own chrome, not part of the mmag2 entry.
    Unused fields are preserved byte-exact.

    Named after the Moombas, the evolved form of the Shumi — Mog's fellow treasure hunter
    on the Chocobo World screen is a Moomba."""

    FILE_LABEL = "mmag2.bin"

    # The Chocobo World screen composites only the picture and text overlays onto its
    # own background; the magazine's window / paper / mat / unlock / footer are absent.
    DRAWS_BACKGROUND = False
    DRAWS_MAT = False
    DRAWS_UNLOCK = False
    DRAWS_FOOTER = False

    NB_ENTRIES = 12
    MNGRP_TEXT_RAW_FILE = MNGRP_TEXT_RAW_FILE
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
        super().__init__(game_data)
        self._raw90_texts = None  # Strings of mngrp raw file 90, indexed by text overlay id

    def get_entry_name(self, entry_id):
        """Chocobo World page map of the English PC release (unmodded entry layout)."""
        if 0 <= entry_id < len(self.DEFAULT_ENTRY_NAMES) and len(self.entries) == self.NB_ENTRIES:
            return self.DEFAULT_ENTRY_NAMES[entry_id]
        return f"Page {entry_id}"

    def load_mngrp(self, mngrp_path, mngrphd_path=""):
        """Load mngrp.bin and decode its raw file 90 (the Chocobo World strings).
        Returns the number of strings, for the mngrp-load feedback."""
        super().load_mngrp(mngrp_path, mngrphd_path)
        return len(self.raw90_texts())

    def _on_mngrp_loaded(self):
        self._raw90_texts = None

    def raw90_texts(self):
        """The strings of mngrp raw file 90, by slot (empty list without mngrp)."""
        if self._raw90_texts is None:
            data = self.get_raw_file(self.MNGRP_TEXT_RAW_FILE)
            self._raw90_texts = (SectionString(game_data=self.game_data,
                                               data_hex=bytearray(data)).get_text_by_slot()
                                 if data else [])
        return self._raw90_texts

    def overlay_text_by_id(self, text_id):
        """Preview string for a text overlay id (empty if unused or mngrp not loaded)."""
        if text_id == OverlaySlot.UNUSED_ID:
            return ""
        texts = self.raw90_texts()
        if not texts:
            return ""
        if 0 <= text_id < len(texts):
            return texts[text_id]
        return f"(no string {text_id} in mngrp raw file {self.MNGRP_TEXT_RAW_FILE})"

    def get_overlay_text(self, entry, overlay):
        """The string a text overlay slot draws (all mmag2 text is raw file 90, so the
        entry is irrelevant — the id indexes the section directly)."""
        if overlay.unused:
            return ""
        return self.overlay_text_by_id(overlay.id)
