"""Shared logic for the mmag.bin / mmag2.bin editors.

Both files are a headerless array of 68-byte MagPageEntry rows, and both draw a
page the same way at the low level: picture overlays are SP2 sprites (mngrp Pos 4)
cropping a page-texture TIM, text overlays are strings out of a mngrp string
section. This base class holds that common ground — the entry array, the
mngrp-backed render source (page textures, the SP2 table, raw-file access) the
PageRenderer reads — so Zone (mmag.bin) and Moomba (mmag2.bin) only add what
actually differs between the two viewers:

* which raw file the text overlays resolve against (mmag: book text 87 + entry
  byte 0x15; mmag2: always raw 90) — `get_overlay_text` is left abstract;
* which layers the viewer draws — the `DRAWS_*` flags. `Menu_Magazine_Draw`
  (0x4C9330) / `Menu_ItemMagazine_DrawPage` (0x4FD6E0) draw the full magazine
  page (window, paper mat, overlays, unlock block, footer); `Menu_ChocoboWorld_Draw`
  (0x4D1D30) draws only the two overlay layers onto the Chocobo World screen.
"""
import os

# Page texture category -> (name, base raw file inside mngrp.bin); the loaded
# picture file is base + texture_page. Any other category uses the page number
# directly as the raw file index. (Menu_Magazine_LoadPageTexture, 0x4C9920.)
TEXTURE_CATEGORIES = {
    0: ("Weapons Monthly", 28),
    1: ("Combat King", 20),
    2: ("Pet Pals", 24),
    3: ("Occult Fan", 44),
    4: ("Cards (unused)", 48),
    5: ("Card rules / battle tutorial", 71),
    6: ("Card icon explanation / Chocobo World", 180),
}

# The SP2 quad-list sprite table the picture overlays index (mngrp Pos 4).
SP2_SPRITE_RAW_FILE = 7

# The magazine paper (parchment) tile: a standalone 32x32 8bpp TIM whose header
# places it at VRAM (896, 192) with CLUT (512, 219) - exactly what
# Menu_Magazine_DrawPaperBackground samples through the entry's E1/E2 bytes.
# Found by scanning every game file for a TIM declaring that placement: this is
# the only one, so the "uploaded separately" tile is simply this raw file.
PAPER_TILE_RAW_FILE = 12


class MagPageManager:
    """Base for the mmag.bin / mmag2.bin editors (see the module docstring)."""

    # The 68-byte entry array is the same; only the human label differs.
    FILE_LABEL = "mmag"

    # Which render layers this page family draws. Overridden per viewer.
    DRAWS_BACKGROUND = True
    DRAWS_MAT = True
    DRAWS_PICTURES = True
    DRAWS_UNLOCK = True
    DRAWS_TEXT = True
    DRAWS_FOOTER = True

    def __init__(self, game_data):
        self.game_data = game_data
        self.file_path = ""
        self.entries = []
        # mngrp.bin, loaded on demand for the render (page textures, sprites, text)
        self._mngrp_data = None
        self._mngrp_header_entries = None
        self._sp2_sprites = None

    def load_file(self, file_path):
        from FF8GameData.menu.magpage import MagPageEntry
        with open(file_path, "rb") as in_file:
            file_data = in_file.read()
        if len(file_data) % MagPageEntry.SIZE != 0:
            raise ValueError(f"Not a {self.FILE_LABEL} file: size {len(file_data)} is not a "
                             f"multiple of {MagPageEntry.SIZE} bytes")
        self.file_path = file_path
        self.entries = [
            MagPageEntry.from_bytes(entry_id, file_data[entry_id * MagPageEntry.SIZE:
                                                        (entry_id + 1) * MagPageEntry.SIZE])
            for entry_id in range(len(file_data) // MagPageEntry.SIZE)]

    def save_file(self, file_path=""):
        if not file_path:
            file_path = self.file_path
        with open(file_path, "wb") as out_file:
            for entry in self.entries:
                out_file.write(entry.to_bytes())

    # --- mngrp render source -------------------------------------------------

    def load_mngrp(self, mngrp_path, mngrphd_path=""):
        """Load mngrp.bin (+ its mngrphd.bin section table, auto-detected next to it
        when not given) so page textures, sprites and text can be resolved."""
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
        self._sp2_sprites = None
        self._on_mngrp_loaded()

    def _on_mngrp_loaded(self):
        """Hook for subclasses to drop caches that depend on mngrp.bin."""

    @property
    def mngrp_loaded(self):
        return self._mngrp_data is not None

    def get_raw_file(self, raw_file):
        """The bytes of one mngrp.bin raw file (empty when absent or not loaded)."""
        if not self.mngrp_loaded or not 0 <= raw_file < len(self._mngrp_header_entries):
            return b""
        header_entry = self._mngrp_header_entries[raw_file]
        if header_entry.invalid_value:
            return b""
        return self._mngrp_data[header_entry.seek:header_entry.seek + header_entry.size]

    def get_sp2_sprites(self):
        """The SP2 sprite table the picture overlays index (mngrp Pos 4), or None.

        Parsed with Joker's Sp2File, which owns the quad-list format."""
        if self._sp2_sprites is None and self.mngrp_loaded:
            from Joker.jokermanager import Sp2File
            data = self.get_raw_file(SP2_SPRITE_RAW_FILE)
            if data:
                self._sp2_sprites = Sp2File.from_bytes(bytes(data)).sprites
        return self._sp2_sprites

    @staticmethod
    def texture_raw_file(entry):
        """mngrp.bin raw file index of an entry's page picture TIM."""
        if entry.texture_category in TEXTURE_CATEGORIES:
            return TEXTURE_CATEGORIES[entry.texture_category][1] + entry.texture_page
        return entry.texture_page

    # --- overlay text (each viewer resolves it against a different section) ---

    def get_overlay_text(self, entry, overlay):
        """The string a text overlay slot draws (empty when unused / mngrp absent)."""
        raise NotImplementedError
