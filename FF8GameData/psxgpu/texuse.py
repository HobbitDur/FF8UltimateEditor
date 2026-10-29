"""Which images an effect's primitives take their texels from, and which pieces of them: per tick.

A textured primitive samples a 256 x 256 texel page of VRAM (its tpage: page, colour depth) through
a palette (its CLUT, for 4/8-bit) at the UVs of its points. The image it comes from is what was
uploaded there (a V / B line of the recording: a TIM's picture, a model's texture), so a sheet is
that upload's rectangle read with the primitive's depth and palette, and its pieces are the UV
rectangles the primitives take - several pages can lie in one upload (an 8-bit picture 256 words
wide spans two). Without an upload covering it, the sheet is the page itself.

No Qt here (numpy only).
"""
from dataclasses import dataclass, field

import numpy as np

from FF8GameData.psxgpu.gpu import VRAM_H, VRAM_W, Gpu

TEXELS_PER_WORD = {0: 4, 1: 2, 2: 1, 3: 1}      # colour depth -> texels in one 16-bit VRAM word
DEPTH_NAMES = {0: "4-bit", 1: "8-bit", 2: "15-bit", 3: "15-bit"}


class _TextureUses(Gpu):
    """The software Gpu's packet decoding, keeping each textured triangle's page, palette and UV
    bounds instead of drawing it."""

    def __init__(self, vram):
        super().__init__(vram, 1, 1)
        self.uses = []          # [(tpage, clut, u0, v0, u1, v1)], u1 / v1 excluded

    def _triangle(self, xys, colours, uvs, clut, tpage, semi, raw):
        if uvs is not None:
            us, vs = [int(uv[0]) for uv in uvs], [int(uv[1]) for uv in uvs]
            u0, v0 = min(us), min(vs)
            self.uses.append((tpage, clut, u0, v0, max(max(us), u0 + 1), max(max(vs), v0 + 1)))

    def _blend(self, ys, xs, colour, semi, mode):
        pass                    # lines: no texture


def texture_uses(tick, vram, parts=None):
    """[(tpage, clut, u0, v0, u1, v1)] of the textured triangles a tick draws (these effect parts'
    only), in draw order; a page holding nothing in `vram` counts as untextured, as when drawing."""
    collector = _TextureUses(vram)
    packets = tick.part_packets(parts)
    packets = packets if tick.ordered else sorted(packets, key=lambda p: (-p[0], -p[1]))
    for _bucket, _order, words in packets:
        collector.draw_packet(words)
    return collector.uses


@dataclass
class TextureSheet:
    """An image in VRAM read with one depth and palette, and the pieces taken from it."""
    x: int                  # VRAM rectangle, in 16-bit words
    y: int
    width: int
    height: int
    depth: int              # 0: 4-bit, 1: 8-bit (through `clut`), 2: 15-bit direct colour
    clut: int               # the palette's CLUT word (x / 16 in bits 0-5, y in bits 6-14); 0 for 15-bit
    pieces: dict = field(default_factory=dict)      # tick -> {(u0, v0, u1, v1)} in this sheet's texels

    @property
    def texel_width(self):
        return self.width * TEXELS_PER_WORD[self.depth]

    @property
    def clut_xy(self):
        return (self.clut & 0x3F) * 16, (self.clut >> 6) & 0x1FF

    def all_pieces(self):
        return set().union(*self.pieces.values()) if self.pieces else set()

    def ticks_of(self, piece):
        return sorted(tick for tick, pieces in self.pieces.items() if piece in pieces)


def _uploaded_rects(recording):
    rects = []
    for upload in list(recording.pre_uploads) + [u for tick in recording.ticks for u in tick.uploads]:
        if upload[0] == "V":
            rects.append(upload[1:5])
        else:                           # a VRAM copy: lands at (u, v)
            _kind, _x, _y, w, h, u, v = upload
            rects.append((u, v, w, h))
    return rects


def _overlaps(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def texture_sheets(recording, parts=None):
    """[TextureSheet] these effect parts take texels from over the recording, in the order they
    first do; the VRAM all uploads leave decides what is textured."""
    vram = recording.vram_at(len(recording.ticks) - 1) if recording.ticks else None
    uploads = _uploaded_rects(recording)
    groups = {}                         # (page, depth, clut) -> {tick: {(u0, v0, u1, v1)}}
    for index, tick in enumerate(recording.ticks):
        for tpage, clut, u0, v0, u1, v1 in texture_uses(tick, vram, parts):
            depth = (tpage >> 7) & 3
            key = (tpage & 0x1F, depth, clut if depth < 2 else 0)
            groups.setdefault(key, {}).setdefault(index, set()).add((u0, v0, u1, v1))
    sheets = {}
    for (page, depth, clut), by_tick in groups.items():
        per_word = TEXELS_PER_WORD[depth]
        page_x, page_y = (page & 0xF) * 64, ((page >> 4) & 1) * 256
        pieces = set().union(*by_tick.values())
        x0 = page_x + min(p[0] for p in pieces) // per_word
        x1 = page_x + -(-max(p[2] for p in pieces) // per_word)
        y0, y1 = page_y + min(p[1] for p in pieces), page_y + max(p[3] for p in pieces)
        covering = [r for r in uploads if _overlaps(r, (x0, y0, x1 - x0, y1 - y0))]
        if covering:
            left, top = min(r[0] for r in covering), min(r[1] for r in covering)
            right, bottom = max(r[0] + r[2] for r in covering), max(r[1] + r[3] for r in covering)
        else:
            left, top, right, bottom = page_x, page_y, page_x + 256 // per_word, page_y + 256
        left, top = max(0, min(left, page_x)), max(0, min(top, page_y))
        right, bottom = min(VRAM_W, right), min(VRAM_H, bottom)
        sheet = sheets.setdefault((left, top, depth, clut),
                                  TextureSheet(left, top, right - left, bottom - top, depth, clut))
        sheet.width, sheet.height = max(sheet.width, right - left), max(sheet.height, bottom - top)
        shift_u, shift_v = (page_x - left) * per_word, page_y - top
        for tick, tick_pieces in by_tick.items():
            sheet.pieces.setdefault(tick, set()).update(
                (u0 + shift_u, v0 + shift_v, u1 + shift_u, v1 + shift_v) for u0, v0, u1, v1 in tick_pieces)
    return sorted(sheets.values(), key=lambda s: (min(s.pieces), s.y, s.x, s.clut))


def named_sheet(recording, x, y, clut, width, height):
    """(TextureSheet, (u0, v0, u1, v1)) of an image a part's values name - VRAM (x, y) in words,
    its palette, width x height texels - read like a sheet the effect takes texels from there (its
    depth and upload), or None when nothing the effect draws comes from that place."""
    found = [s for s in texture_sheets(recording) if s.x <= x < s.x + s.width and s.y <= y < s.y + s.height]
    if not found:
        return None
    base = next((s for s in found if s.clut == clut), found[0])
    sheet = TextureSheet(base.x, base.y, base.width, base.height, base.depth, clut if base.depth < 2 else 0)
    u0, v0 = (x - sheet.x) * TEXELS_PER_WORD[sheet.depth], y - sheet.y
    return sheet, (u0, v0, u0 + max(1, width), v0 + max(1, height))


def sheet_rgba(vram, sheet):
    """The sheet as an (height, texel width, 4) uint8 image: its texels through its palette, the
    transparent ones (colour 0x0000) with alpha 0."""
    words = vram.words[sheet.y:sheet.y + sheet.height, sheet.x:sheet.x + sheet.width].astype(np.uint32)
    if sheet.depth >= 2:
        colours = words
    else:
        bits = 4 if sheet.depth == 0 else 8
        shifts = np.arange(0, 16, bits, dtype=np.uint32)
        indices = ((words[..., None] >> shifts) & ((1 << bits) - 1)).reshape(words.shape[0], -1)
        clut_x, clut_y = sheet.clut_xy
        colours = vram.words[clut_y, (clut_x + indices) % VRAM_W].astype(np.uint32)
    rgba = np.zeros(colours.shape + (4,), np.uint8)
    rgba[..., 0] = (colours & 0x1F) * 255 // 31
    rgba[..., 1] = ((colours >> 5) & 0x1F) * 255 // 31
    rgba[..., 2] = ((colours >> 10) & 0x1F) * 255 // 31
    rgba[..., 3] = np.where(colours == 0, 0, 255)
    return rgba
