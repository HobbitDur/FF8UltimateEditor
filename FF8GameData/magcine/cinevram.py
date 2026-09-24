"""VRAM of a GF cinematic, tick by tick: the texture and CLUT uploads the script makes, replayed.

Nothing is in VRAM when the summon starts; the script uploads everything itself (opcodes recorded by
CineSimulation.vram_events):
  0x27 texture id + CLUT id, 0x28 CLUT id, 0x29 texture id - or raw pages: a texture RECT (or an
  inline RECT) filled from a streamed file (the last one loaded by 0x06, or file slot k + n x 4 KB).
Texture id -> RECT, bpp and file slot come from the GF's descriptor in FF8_EN.exe
(Resources/json/gf_cinematic_vram.json); the data is in the file of that slot (0 = .00, 1 = .01,
k = battle/magNNN_b.0k), at its texture / CLUT table entry. VRAM areas are reused during the summon,
so the order matters: state(tick) applies every upload made up to that tick.

The script has two upload paths (op 0xA0 on ctx->flags bit 13): one uploads every texture and CLUT
by id, the other streams raw pages and never uploads some CLUTs (Ifrit's creature palettes 19/20)
- they are in VRAM in the game anyway. So VRAM starts from a baseline holding every texture and CLUT
the loaded files contain (in id order), and the replayed uploads are applied on top of it.

decode_page(tpage, clut) turns a 256x256 texture page into RGBA (15-bit colour 0 = transparent), as
the PlayStation GPU reads it: 4 bpp (16-colour CLUT), 8 bpp (256-colour CLUT) or 15 bpp direct.
"""
import json
import os
import struct

import numpy as np

from FF8GameData.packagepath import RESOURCES_JSON_FOLDER

_DESCRIPTOR_PATH = str(RESOURCES_JSON_FOLDER / "gf_cinematic_vram.json")
VRAM_WIDTH, VRAM_HEIGHT = 1024, 512
CLUT_BASE = 14356  # sceneHdr+0x1C set by SetupSectionPtrs: CLUT id of (320, 224), base of op 0x78


def load_descriptor(gf):
    with open(_DESCRIPTOR_PATH, encoding="utf-8") as f:
        return json.load(f)["gfs"].get(gf)


def texture_tpage(descriptor, texture_id, abr=0):
    """GfCinematic_GetTexTpage: the tpage word of a texture id (its RECT's page, its bpp)."""
    x, y, _w, _h, slot = descriptor["textures"][texture_id]
    return (abr & 0x60) | (slot & 0x80) | (((y & 0x100) | ((x >> 2) & 0x3F0)) >> 4)


def clut_id(descriptor, index):
    """GfCinematic_GetClutId: the CLUT word of a CLUT id."""
    x, y = descriptor["cluts"][index][:2]
    return ((x >> 4) & 0x3F) | ((y & 0x1FF) << 6)


class CineVram:
    def __init__(self, gf, files, events):
        """files: {slot: bytes} (0 = .00, 1 = .01, k = streamed part k); events: the simulation's
        vram_events [(tick, kind, args)] in execution order."""
        self.descriptor = load_descriptor(gf) or {"textures": [], "cluts": []}
        self.files = files
        self.events = events
        self.missing = set()           # file slots an upload needed but that are not loaded
        self._vram = np.zeros((VRAM_HEIGHT, VRAM_WIDTH), np.uint16)
        self._apply_baseline()
        self._applied = 0              # events applied to self._vram
        self._pages = {}               # (version, tpage, clut) -> RGBA array

    # ------------------------------------------------------------------ state
    def version(self, tick):
        """How many uploads are done at `tick` (identifies the VRAM content)."""
        count = 0
        for when, _kind, _args in self.events:
            if when > tick:
                break
            count += 1
        return count

    def state(self, tick):
        version = self.version(tick)
        if version < self._applied:        # going back in time: replay from the baseline
            self._vram[:] = 0
            self._apply_baseline()
            self._applied = 0
        while self._applied < version:
            self._apply(*self.events[self._applied][1:])
            self._applied += 1
        return self._vram

    def _apply_baseline(self):
        missing = set(self.missing)
        for index in range(len(self.descriptor["textures"])):
            self._upload_table(index, texture=True)
        for index in range(len(self.descriptor["cluts"])):
            self._upload_table(index, texture=False)
        self.missing = missing             # only the script's own uploads report missing files

    def _apply(self, kind, args):
        if kind == "tex":
            self._upload_table(args[0], texture=True)
        elif kind == "clut":
            self._upload_table(args[0], texture=False)
        elif kind == "raw":           # texture RECT id, source slot, byte offset
            rect_id, slot, offset = args
            if 0 <= rect_id < len(self.descriptor["textures"]):
                self._blit(self.descriptor["textures"][rect_id][:4], slot, offset)
        elif kind == "rawrect":       # inline RECT, source slot
            rect, slot = args
            self._blit(rect, slot, 0)

    def _upload_table(self, index, texture):
        table = self.descriptor["textures" if texture else "cluts"]
        if not 0 <= index < len(table):
            return
        x, y, w, h, slot_byte = table[index]
        slot = slot_byte & 0x7F if texture else slot_byte
        data = self.files.get(slot)
        if data is None:
            self.missing.add(slot)
            return
        header = struct.unpack_from("<12I", data, 0)
        base = header[5] if texture else header[2]         # texture table 0x14 / CLUT table 0x08
        entry = struct.unpack_from("<I", data, base + 4 * index)[0]
        if not entry:
            return
        self._write((x, y, w, h), data, base + (entry & 0xFFFFFF))

    def _blit(self, rect, slot, offset):
        data = self.files.get(slot)
        if data is None:
            self.missing.add(slot)
            return
        self._write(rect, data, offset)

    def _write(self, rect, data, offset):
        x, y, w, h = rect
        if w <= 0 or h <= 0:
            return
        count = min(w * h, max(0, (len(data) - offset) // 2))
        if count <= 0:
            return
        pixels = np.zeros(w * h, np.uint16)
        pixels[:count] = np.frombuffer(data, np.uint16, count, offset)
        pixels = pixels.reshape(h, w)
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(VRAM_WIDTH, x + w), min(VRAM_HEIGHT, y + h)
        if x1 > x0 and y1 > y0:
            self._vram[y0:y1, x0:x1] = pixels[y0 - y:y1 - y, x0 - x:x1 - x]

    # ------------------------------------------------------------------ texture pages
    def page_rgba(self, tick, tpage, clut):
        """256x256 RGBA of a texture page as the GPU samples it with that CLUT (alpha 0 = transparent)."""
        version = self.version(tick)
        key = (version, tpage & 0x19F, clut & 0x7FFF)
        page = self._pages.get(key)
        if page is None:
            if len(self._pages) > 256:
                self._pages.clear()
            page = decode_page(self.state(tick), tpage, clut)
            self._pages[key] = page
        return page


def decode_page(vram, tpage, clut):
    x0, y0 = (tpage & 0xF) * 64, ((tpage >> 4) & 1) * 256
    mode = (tpage >> 7) & 3
    width = {0: 64, 1: 128}.get(mode, 256)            # halfwords covering 256 texels
    region = np.zeros((256, width), np.uint16)
    available = vram[y0:y0 + 256, x0:x0 + width]
    region[:available.shape[0], :available.shape[1]] = available
    if mode == 0:                                      # 4 bpp: 4 texels per halfword, low nibble first
        nibbles = np.stack([(region >> shift) & 0xF for shift in (0, 4, 8, 12)], axis=-1).reshape(256, 256)
        palette = _clut_row(vram, clut, 16)
        colours = palette[nibbles]
    elif mode == 1:                                    # 8 bpp: 2 texels per halfword, low byte first
        indices = np.stack([region & 0xFF, region >> 8], axis=-1).reshape(256, 256)
        palette = _clut_row(vram, clut, 256)
        colours = palette[indices]
    else:                                              # 15 bpp direct
        colours = region[:, :256]
    return _to_rgba(colours)


def _clut_row(vram, clut, count):
    cx, cy = (clut & 0x3F) * 16, (clut >> 6) & 0x1FF
    row = np.zeros(count, np.uint16)
    available = vram[cy, cx:cx + count] if cy < VRAM_HEIGHT else row[:0]
    row[:len(available)] = available
    return row


def _to_rgba(colours):
    rgba = np.empty(colours.shape + (4,), np.uint8)
    rgba[..., 0] = (colours & 0x1F) << 3
    rgba[..., 1] = ((colours >> 5) & 0x1F) << 3
    rgba[..., 2] = ((colours >> 10) & 0x1F) << 3
    rgba[..., 3] = np.where(colours == 0, 0, 255)
    return rgba
