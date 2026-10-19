"""The Scan screen's own graphics around the model: backdrop panel, spinner, stat board and bars.

When the Scan screen opens (FF8_EN.exe, MAG_040_SCAN), the Dimmer has hidden the battle stage and
the other entities. What fills the screen:

  * ScanBars (MAG_040_SCAN_DrawScanBars 0x84F0B0, from the zoom-in until the screen is closed):
    5 rows x 3 columns of 128x64 textured quads (opaque, code 0x2C) over the whole screen, the
    scan lines of mag039-067.tim (tpage 0xBA, CLUT 0x3C94, u 128 -> 0, v 0 -> 64), scrolling down
    one pixel a tick (top = (frame & 63) - 64), faded in to full brightness (128) during the zoom;
    their black texels are transparent;

and four effect models the exe carries in its data (Effect_RenderPrimModel models,
MAG_040_SCAN_DrawHudModel 0x84D8B0 draws each one):

  * Backdrop (Backdrop_State0_Init 0x84FA50): the blue panel behind the model, at view position
    (-3968, 3840, 32767), scale 4608, fading in from black by 512/4096 per tick;
  * Spinner (Spinner_State0_Init 0x84F390): a small shape at (-128, -160, 1152), turning by
    192/4096 a tick about Y and 96/4096 about Z (Spinner_Tick 0x84F300), fading in by 256 a tick;
  * StatBoard (StatBoard_State0_Init 0x84F4A0): one textured quad at (-64, -88, 576), its texture
    in the Scan effect's mag039-067.tim;
  * 8 StatBars (StatBar_State0_Init 0x84F5C0) around the board, placed by a table of the exe
    (x, y, Z turn, delay, pulse phase; position = board + x/2, y/2): bars 0-1 HP (up to 999),
    2-6 STR, VIT, MAG, SPR, SPD (up to 127), 7 EVA (up to 25). Each one appears after its delay,
    grows by 768 a tick up to its length (16384 = 4x at the top value) and pulses: fade =
    (sin(phase) + 4096) / 6, the phase moving 256 a tick (StatBar_Tick 0x84F520).

DrawHudModel's matrix is RotZ * RotX * RotY scaled per axis (4096 = 1), translated, with no camera:
the models live in view space and project with the scan lens (576) around the screen centre -
at z 576 one unit is one pixel. The render header has flags 0xF0: every face is two-sided and
every colour is depth-cued (GTE DPCS / DPCT) towards black by the fade value (4096 = black).

Every primitive of these models is semi-transparent; the board's tpage (0xBA) sets additive
blending, which the untextured ones that follow use too. Over the black screen the additive
backdrop is its own colour, so it is drawn under the model, and the HUD parts are added over it.

The model data, the bar table and the texture always come from the user's files (the FF8 exe,
mag039-067.tim); the numbers above are code immediates of the functions named.
"""
import math
import struct
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

SCREEN_W, SCREEN_H = 320, 240
CENTRE_X, CENTRE_Y = 160, 120
LENS = 576
ONE = 4096

# Effect_RenderPrimModel's 8 primitive sections, in file order: (name, entry size)
SECTIONS = (("F3", 12), ("F4", 12), ("FT3", 20), ("FT4", 24), ("G3", 20), ("G4", 24), ("GT3", 28), ("GT4", 36))
SEMI_TRANSPARENT_BIT = 0x02     # in the primitive's GPU code byte

# Task parameters (code immediates)
BACKDROP_POSITION, BACKDROP_SCALE, BACKDROP_FADE_STEP = (-3968, 3840, 32767), 4608, 512
SPINNER_POSITION, SPINNER_TURN_Y, SPINNER_TURN_Z, SPINNER_FADE_STEP = (-128, -160, 1152), 192, 96, 256
BOARD_POSITION = (-64, -88, 576)
BAR_GROW_STEP, BAR_PULSE_STEP, BAR_PULSE_DIVISOR = 768, 256, 6
BAR_COUNT = 8
BAR_STATS = ("hp", "hp", "str", "vit", "mag", "spr", "spd", "eva")
FINAL_TICK = 1000                # a tick by which every part has finished appearing
# DrawScanBars' quads (screen pixels)
SCAN_BARS_TILE = (128, 64)
SCAN_BARS_COLUMNS, SCAN_BARS_ROWS = 3, 5
SCAN_BARS_UVS = ((128, 0), (0, 0), (128, 64), (0, 64))
SCAN_BARS_CLUT, SCAN_BARS_TPAGE, SCAN_BARS_CODE = 0x3C94, 0xBA, 0x2C
SCAN_BARS_BRIGHTNESS = 128


def bar_length(stat: str, value: int) -> int:
    """StatBar_State0_Init: the bar's X scale (4096 = 1) for a stat value."""
    value = max(0, int(value))
    if stat == "hp":
        return (((min(value, 999) << 14) * 2201224481) >> 32) >> 9
    if stat == "eva":
        return (((min(value, 25) << 14) * 1374389535) >> 32) >> 3
    return (((min(value, 127) << 14) * 2164392969) >> 32) >> 6


@dataclass
class Prim:
    kind: str
    code: int
    indices: list                  # vertex numbers
    colors: list                   # [(r, g, b)] - one, or one per vertex (Gouraud)
    uvs: list = field(default_factory=list)
    clut: int = 0
    tpage: int = 0

    @property
    def textured(self):
        return "T" in self.kind

    @property
    def semi_transparent(self):
        return bool(self.code & SEMI_TRANSPARENT_BIT)


class PrimModel:
    """An Effect_RenderPrimModel model: u32 offset of the sections, u32 vertex count, the vertices
    (4 x s16: x, y, z, pad), then 8 sections, each a u32 count and its entries. Vertex numbers are
    stored in 4-byte units (x2)."""

    def __init__(self, vertices, prims):
        self.vertices = np.asarray(vertices, dtype=float).reshape(-1, 3)
        self.prims = prims

    @classmethod
    def from_bytes(cls, data: bytes, offset: int = 0):
        sections_offset, vertex_count = struct.unpack_from("<II", data, offset)
        vertices = [struct.unpack_from("<hhh", data, offset + 8 + 8 * i) for i in range(vertex_count)]
        position = offset + sections_offset
        prims = []
        for kind, size in SECTIONS:
            count, = struct.unpack_from("<I", data, position)
            position += 4
            for k in range(count):
                prims.append(_parse_prim(kind, data[position + k * size:position + (k + 1) * size]))
            position += count * size
        model = cls(vertices, prims)
        model.size = position - offset
        if any(index >= vertex_count for prim in prims for index in prim.indices):
            raise ValueError("a primitive uses a vertex the model does not have")
        return model


def _rgb(word: int):
    return word & 0xFF, (word >> 8) & 0xFF, (word >> 16) & 0xFF


def _parse_prim(kind, entry: bytes) -> Prim:
    words = struct.unpack_from(f"<{len(entry) // 4}I", entry)
    code = words[0] >> 24
    corners = 4 if kind.endswith("4") else 3
    indices = [half // 2 for half in struct.unpack_from(f"<{corners}H", entry, 4)]
    index_words = 2  # 3 or 4 u16 numbers, padded to 2 words
    colors = [_rgb(words[0])]
    rest = list(words[1 + index_words:])
    if kind.startswith("G"):
        colors += [_rgb(word) for word in rest[:corners - 1]]
        rest = rest[corners - 1:]
    prim = Prim(kind, code, indices, colors)
    if "T" in kind:
        # uv0 + CLUT, uv1 + tpage, then uv2 (and uv3): a 4-corner entry has a word for them, a
        # 3-corner one keeps uv2 in the u16 after its 3 vertex numbers (FT3 20 / GT3 28 bytes)
        uv0, uv1 = rest[0], rest[1]
        uv23 = rest[2] if corners == 4 else struct.unpack_from("<H", entry, 10)[0]
        uvs = [(uv0 & 0xFF, (uv0 >> 8) & 0xFF), (uv1 & 0xFF, (uv1 >> 8) & 0xFF),
               (uv23 & 0xFF, (uv23 >> 8) & 0xFF)]
        if corners == 4:
            uvs.append(((uv23 >> 16) & 0xFF, (uv23 >> 24) & 0xFF))
        prim.uvs, prim.clut, prim.tpage = uvs, uv0 >> 16, uv1 >> 16 & 0xFFFF
    return prim


# ------------------------------------------------------------------ the exe's data
@dataclass
class ScanBackgroundData:
    backdrop: PrimModel
    spinner: PrimModel
    board: PrimModel
    bars: list                      # BAR_COUNT PrimModel
    bar_layout: list                # BAR_COUNT (x, y, z_turn, delay, phase)


def background_from_exe(exe: bytes, exe_data_json: dict) -> ScanBackgroundData:
    """The Scan screen models and bar table of an FF8 exe (exe.json scan_background_offset)."""
    from Xu.xumanager import exe_language_prefix
    offsets = exe_data_json["scan_background_offset"]
    prefix = exe_language_prefix(exe, exe_data_json)
    shift = offsets[f"{prefix}_offset"] if prefix else 0

    def model(key):
        return PrimModel.from_bytes(exe, offsets[key] + shift)

    try:
        table = offsets["bar_layout"] + shift
        layout = [struct.unpack_from("<5h", exe, table + 10 * i) for i in range(BAR_COUNT)]
        return ScanBackgroundData(model("backdrop"), model("spinner"), model("board"),
                                  [model(f"bar{i}") for i in range(BAR_COUNT)], layout)
    except struct.error as error:
        raise ValueError(f"the exe is too short for the Scan screen models ({error})") from error


# ------------------------------------------------------------------ the texture (VRAM)
class TimTexture:
    """A TIM as it sits in VRAM: its 4/8-bit image and its CLUT rows, looked up the way the GPU
    does for a primitive's tpage + CLUT. Texel 0x0000 is transparent; a texel with the STP bit
    blends (semi-transparent primitive), the others are opaque."""

    def __init__(self, data: bytes):
        magic, flags = struct.unpack_from("<II", data, 0)
        if magic != 0x10:
            raise ValueError("not a TIM file")
        self.bpp = flags & 3
        if self.bpp not in (0, 1):
            raise ValueError("only 4-bit and 8-bit TIM textures are used here")
        position = 8
        self.clut = None
        if flags & 8:
            size, x, y, w, h = struct.unpack_from("<IHHHH", data, position)
            self.clut_x, self.clut_y = x, y
            self.clut = np.frombuffer(data, "<u2", w * h, position + 12).reshape(h, w)
            position += size
        size, x, y, w, h = struct.unpack_from("<IHHHH", data, position)
        self.image_x, self.image_y = x, y          # in 16-bit VRAM units
        raw = np.frombuffer(data, np.uint8, w * 2 * h, position + 12).reshape(h, w * 2)
        if self.bpp == 0:
            raw = np.stack((raw & 0xF, raw >> 4), axis=2).reshape(h, w * 4)
        self.texels = raw                           # palette indices, one per texel

    @classmethod
    def from_file(cls, path):
        with open(path, "rb") as file:
            return cls(file.read())

    def lookup(self, u, v, tpage, clut):
        """(rgb float array, mask drawn, mask semi-transparent) of texel coordinates."""
        per_unit = 2 if self.bpp == 1 else 4
        page_x = (tpage & 0xF) * 64
        page_y = ((tpage >> 4) & 1) * 256
        column = (page_x - self.image_x) * per_unit + (u.astype(int) & 0xFF)
        row = page_y - self.image_y + (v.astype(int) & 0xFF)
        inside = (row >= 0) & (row < self.texels.shape[0]) & (column >= 0) & (column < self.texels.shape[1])
        index = np.where(inside, self.texels[np.clip(row, 0, self.texels.shape[0] - 1),
                                             np.clip(column, 0, self.texels.shape[1] - 1)], 0)
        clut_row = (clut >> 6) - self.clut_y
        clut_column = (clut & 0x3F) * 16 - self.clut_x
        if self.clut is None or not 0 <= clut_row < self.clut.shape[0]:
            return np.zeros(index.shape + (3,)), np.zeros(index.shape, bool), np.zeros(index.shape, bool)
        colors = self.clut[clut_row, np.clip(clut_column + index, 0, self.clut.shape[1] - 1)].astype(int)
        rgb = np.stack(((colors & 0x1F), (colors >> 5) & 0x1F, (colors >> 10) & 0x1F), axis=-1) * (255 / 31)
        drawn = inside & (colors != 0)
        return rgb, drawn, drawn & (colors & 0x8000 != 0)


# ------------------------------------------------------------------ drawing
def _rotation(axis, angle):
    c, s = math.cos(angle * 2 * math.pi / ONE), math.sin(angle * 2 * math.pi / ONE)
    if axis == "x":
        return np.array(((1., 0., 0.), (0., c, -s), (0., s, c)))
    if axis == "y":
        return np.array(((c, 0., s), (0., 1., 0.), (-s, 0., c)))
    return np.array(((c, -s, 0.), (s, c, 0.), (0., 0., 1.)))


def hud_matrix(turn=(0, 0, 0), scale=(ONE, ONE, ONE)):
    """DrawHudModel: RotZ * RotX * RotY (each premultiplied), then the per-axis scale."""
    rx, ry, rz = turn
    matrix = _rotation("z", rz) @ _rotation("x", rx) @ _rotation("y", ry)
    return matrix * (np.asarray(scale, float) / ONE)


class Canvas:
    """A 320x240 (x supersample) float RGB buffer the parts are added into (additive blending,
    like the GPU's semi-transparency mode 1), opaque texels replacing what is under them."""

    def __init__(self, supersample=2, height=SCREEN_H):
        self.scale = supersample
        self.rgb = np.zeros((height * supersample, SCREEN_W * supersample, 3))
        self.alpha = np.zeros((height * supersample, SCREEN_W * supersample))

    def image(self, opaque=True) -> Image.Image:
        """The buffer as an RGBA image: opaque (black where nothing is drawn) or with alpha =
        where something was drawn (for the additive layer)."""
        rgb = np.clip(self.rgb, 0, 255).astype(np.uint8)
        alpha = np.full(rgb.shape[:2], 255, np.uint8) if opaque else (self.alpha > 0).astype(np.uint8) * 255
        return Image.fromarray(np.dstack((rgb, alpha)), "RGBA")

    def draw_screen_prim(self, prim: Prim, points, texture=None):
        """Draw a primitive given in screen pixels (no projection), like a GPU packet."""
        points = np.asarray(points, float)
        colors = np.array(prim.colors if len(prim.colors) > 1 else prim.colors * len(prim.indices), float)
        triangles = [(0, 1, 2)] if len(prim.indices) == 3 else [(0, 1, 2), (1, 3, 2)]
        for triangle in triangles:
            uvs = np.array([prim.uvs[i] for i in triangle], float) if prim.textured else None
            self._triangle(points[list(triangle)] * self.scale, colors[list(triangle)], prim, uvs, texture)

    def draw_model(self, model: PrimModel, position, matrix, fade=0, texture=None):
        """Project and draw a model at a view-space position; fade 0-4096 = towards black."""
        view = model.vertices @ matrix.T + np.asarray(position, float)
        z = np.where(view[:, 2] > 0, view[:, 2], np.nan)
        screen = np.stack((CENTRE_X + view[:, 0] * LENS / z, CENTRE_Y + view[:, 1] * LENS / z), axis=1)
        keep = 1 - max(0, min(fade, ONE)) / ONE
        for prim in model.prims:
            points = screen[prim.indices]
            if np.isnan(points).any():
                continue
            colors = np.array(prim.colors if len(prim.colors) > 1 else prim.colors * len(prim.indices), float)
            colors *= keep
            triangles = [(0, 1, 2)] if len(prim.indices) == 3 else [(0, 1, 2), (1, 3, 2)]
            for triangle in triangles:
                uvs = np.array([prim.uvs[i] for i in triangle], float) if prim.textured else None
                self._triangle(points[list(triangle)] * self.scale, colors[list(triangle)], prim, uvs, texture)

    def _triangle(self, points, colors, prim, uvs, texture):
        if prim.textured and texture is None:
            return
        height, width = self.alpha.shape
        x0, y0 = np.floor(points.min(axis=0)).astype(int)
        x1, y1 = np.ceil(points.max(axis=0)).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, width), min(y1, height)
        if x0 >= x1 or y0 >= y1:
            return
        (ax, ay), (bx, by), (cx, cy) = points
        area = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay)
        if abs(area) < 1e-9:
            return
        px, py = np.meshgrid(np.arange(x0, x1) + .5, np.arange(y0, y1) + .5)
        w0 = ((bx - px) * (cy - py) - (cx - px) * (by - py)) / area
        w1 = ((cx - px) * (ay - py) - (ax - px) * (cy - py)) / area
        w2 = 1 - w0 - w1
        inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not inside.any():
            return
        weights = np.stack((w0, w1, w2), axis=-1)
        shade = weights @ colors                         # Gouraud (or flat: equal colours)
        region = (slice(y0, y1), slice(x0, x1))
        if prim.textured:
            uv = weights @ uvs
            texel, drawn, blended = texture.lookup(uv[..., 0], uv[..., 1], prim.tpage, prim.clut)
            color = texel * shade / 128                  # 0x80 = the texel's own colour
            inside &= drawn
            if not prim.semi_transparent:
                blended = np.zeros_like(drawn)
            opaque = inside & ~blended
            target = self.rgb[region]
            target[opaque] = color[opaque]
            target[inside & blended] += color[inside & blended]
        else:
            if prim.semi_transparent:
                self.rgb[region][inside] += shade[inside]
            else:
                self.rgb[region][inside] = shade[inside]
        self.alpha[region][inside] = 1


@dataclass
class BarValues:
    """What the stat bars read from the battle slot."""
    hp: int = 0
    str: int = 0
    vit: int = 0
    mag: int = 0
    spr: int = 0
    spd: int = 0
    eva: int = 0

    @classmethod
    def from_info_stat(cls, info_stat, level: int, current_hp: int):
        """A monster at a level (AI stat multipliers at their default x1)."""
        from FF8GameData.dat.monsterstatcurve import monster_stat
        values = {name: monster_stat(name, list(info_stat[name][:4]), level)
                  for name in ("str", "vit", "mag", "spr", "spd", "eva") if info_stat.get(name)}
        return cls(hp=current_hp, **values)


class ScanBackground:
    """Draws the Scan screen's backdrop (under the model) and HUD parts (added over it) at a tick
    after the screen opened. texture: the TimTexture of mag039-067.tim (None: no stat board)."""

    def __init__(self, data: ScanBackgroundData, texture=None, supersample=2):
        self.data = data
        self.texture = texture
        self.supersample = supersample
        self._backdrop_full = None
        self._scan_bars = None      # (rgb, drawn mask) at scroll 0; the pattern repeats every 64 px

    def scan_bars(self, tick=0):
        """(rgb, drawn) of the scrolling scan line tiles (None without the texture)."""
        if self.texture is None:
            return None
        width, height = SCAN_BARS_TILE
        if self._scan_bars is None:
            # one period of the pattern, as tall as the 5 rows, scrolled by rolling it
            canvas = Canvas(self.supersample, height=SCAN_BARS_ROWS * height)
            gray = (SCAN_BARS_BRIGHTNESS,) * 3
            for row in range(SCAN_BARS_ROWS):
                top = row * height
                for column in range(SCAN_BARS_COLUMNS):
                    left = column * width
                    corners = np.array(((left, top), (left + width, top), (left, top + height),
                                        (left + width, top + height)), float)
                    prim = Prim("FT4", SCAN_BARS_CODE, [0, 1, 2, 3], [gray], list(SCAN_BARS_UVS),
                                SCAN_BARS_CLUT, SCAN_BARS_TPAGE)
                    canvas.draw_screen_prim(prim, corners, self.texture)
            self._scan_bars = np.clip(canvas.rgb, 0, 255).astype(np.uint16), canvas.alpha > 0
        rgb, drawn = self._scan_bars
        shift = (tick & (height - 1)) * self.supersample   # top row at (frame & 63) - 64
        rows = SCREEN_H * self.supersample
        return np.roll(rgb, shift, axis=0)[:rows], np.roll(drawn, shift, axis=0)[:rows]

    def underlay(self, tick=FINAL_TICK) -> Image.Image:
        """What is behind the model: the scan line tiles, with the backdrop added over them."""
        fade_tick = min(tick, 1 + ONE // BACKDROP_FADE_STEP)  # faded in by then
        if getattr(self, "_backdrop_u16_tick", None) != fade_tick:
            self._backdrop_u16 = np.asarray(self.backdrop(fade_tick))[..., :3].astype(np.uint16)
            self._backdrop_u16_tick = fade_tick
        bars = self.scan_bars(tick)
        rgb = self._backdrop_u16 if bars is None else bars[0] + self._backdrop_u16
        rgb = np.minimum(rgb, 255).astype(np.uint8)
        return Image.fromarray(np.dstack((rgb, np.full(rgb.shape[:2], 255, np.uint8))), "RGBA")

    def backdrop(self, tick=FINAL_TICK) -> Image.Image:
        """The backdrop over the black screen (Backdrop task: from tick 1, fading in 512 a tick)."""
        if tick < 1:
            return Canvas(self.supersample).image()
        if self._backdrop_full is None:
            canvas = Canvas(self.supersample)
            canvas.draw_model(self.data.backdrop, BACKDROP_POSITION,
                              hud_matrix(scale=(BACKDROP_SCALE,) * 3))
            self._backdrop_full = canvas.rgb
        fade = max(0, ONE - BACKDROP_FADE_STEP * (tick - 1))
        rgb = np.clip(self._backdrop_full * (1 - fade / ONE), 0, 255).astype(np.uint8)
        return Image.fromarray(np.dstack((rgb, np.full(rgb.shape[:2], 255, np.uint8))), "RGBA")

    def hud(self, tick=FINAL_TICK, values: BarValues = None) -> Image.Image:
        """The spinner, the board and the bars (an image to add over the frame)."""
        canvas = Canvas(self.supersample)
        canvas.draw_model(self.data.board, BOARD_POSITION, hud_matrix(), texture=self.texture)
        values = values or BarValues()
        for index in range(BAR_COUNT):
            x, y, z_turn, delay, phase = self.data.bar_layout[index]
            shown_from = 1 + delay + 1          # spawned on tick 1, hidden until its delay runs out
            if tick < shown_from:
                continue
            target = bar_length(BAR_STATS[index], getattr(values, BAR_STATS[index]))
            length = min(target, BAR_GROW_STEP * (tick - shown_from))
            if length <= 0:
                continue
            angle = (phase + BAR_PULSE_STEP * tick) & 0xFFF
            fade = int((int(ONE * math.sin(angle * 2 * math.pi / ONE)) + ONE) / BAR_PULSE_DIVISOR)
            position = (BOARD_POSITION[0] + int(x / 2), BOARD_POSITION[1] + int(y / 2), BOARD_POSITION[2])
            canvas.draw_model(self.data.bars[index], position, hud_matrix((0, 0, z_turn), (length, ONE, ONE)),
                              fade=fade)
        turn = ((0, SPINNER_TURN_Y * (tick + 1), SPINNER_TURN_Z * (tick + 1)))
        canvas.draw_model(self.data.spinner, SPINNER_POSITION, hud_matrix(turn),
                          fade=max(0, ONE - SPINNER_FADE_STEP * tick))
        return canvas.image(opaque=False)
