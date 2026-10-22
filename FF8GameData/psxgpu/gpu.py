"""A software PlayStation GPU for previews: GP0 drawing packets -> an RGBA frame.

FF8's battle effects draw by queueing PlayStation GPU packets (the PC build runs them through
Square's GPU emulation): polygons (flat / Gouraud, 3 or 4 points, textured or not), sprites,
lines and draw-mode words. This module decodes those packets and rasterises them the way the
console does, close enough to preview an effect:

 - screen space: the GTE already projected every point; the game's window is 320 x 224 (GTE OFX
   160, OFY 112 in battle). A Gpu draws any window of that plane (origin, width, height), so
   geometry the game would clip can be shown too;
 - textures come from a 1024 x 512 16-bit VRAM image (Vram): tpage = 64-pixel column x 256-line
   row + colour depth (4/8-bit through a CLUT, or 15-bit direct), a texel 0x0000 is transparent;
 - a textured colour is modulated by the vertex colour (128 = unchanged) unless the packet says
   "raw texture"; Gouraud colours and UVs are interpolated across the triangle (affine, as the
   console does);
 - semi-transparency (packet bit 1; for textured pixels only where the texel's STP bit is set)
   uses the tpage's mode: 0 = B/2 + F/2, 1 = B + F, 2 = B - F, 3 = B + F/4.

Not emulated: dithering, the mask bit, texture windows, interlacing; lines are drawn 1 pixel wide.
No Qt here (numpy only), so it is testable without a window.
"""
import numpy as np

SCREEN_W, SCREEN_H = 320, 224
VRAM_W, VRAM_H = 1024, 512


class Vram:
    """The console's 1024 x 512 video memory, 16-bit words (BGR555 + STP bit)."""

    def __init__(self):
        self.words = np.zeros((VRAM_H, VRAM_W), np.uint16)
        self.written = np.zeros((VRAM_H, VRAM_W), bool)

    def upload(self, x, y, w, h, words):
        """Write a w x h rectangle of 16-bit words at (x, y) (wrapping like the console)."""
        data = np.asarray(words, np.uint16).reshape(h, w)
        ys = (np.arange(h) + y) % VRAM_H
        xs = (np.arange(w) + x) % VRAM_W
        self.words[np.ix_(ys, xs)] = data
        self.written[np.ix_(ys, xs)] = True

    def copy(self, sx, sy, dx, dy, w, h):
        ys, xs = (np.arange(h) + sy) % VRAM_H, (np.arange(w) + sx) % VRAM_W
        block = self.words[np.ix_(ys, xs)].copy()
        self.upload(dx, dy, w, h, block)

    def page_written(self, tpage):
        x, y = (tpage & 0xF) * 64, ((tpage >> 4) & 1) * 256
        return bool(self.written[y:y + 256, x:x + 64].any())


def _s11(value):
    """A signed 11-bit packet coordinate."""
    value &= 0x7FF
    return value - 0x800 if value & 0x400 else value


def _xy(word):
    return _s11(word), _s11(word >> 16)


def _raw_xy(word):
    """A packet coordinate as a signed 16-bit value (the GPU keeps 11 bits; kept here to see where
    off-screen geometry would land)."""
    x, y = word & 0xFFFF, (word >> 16) & 0xFFFF
    return (x - 0x10000 if x & 0x8000 else x), (y - 0x10000 if y & 0x8000 else y)


def _rgb(word):
    return word & 0xFF, (word >> 8) & 0xFF, (word >> 16) & 0xFF


def _bgr555_to_rgb(words):
    words = words.astype(np.uint32)
    r = (words & 0x1F) * 255 // 31
    g = ((words >> 5) & 0x1F) * 255 // 31
    b = ((words >> 10) & 0x1F) * 255 // 31
    return np.stack((r, g, b), -1).astype(np.float32)


class Gpu:
    """Draws GP0 packets into an RGB frame over a VRAM."""

    def __init__(self, vram=None, width=SCREEN_W, height=SCREEN_H, background=(16, 16, 24), origin=(0, 0),
                 scale=1.0):
        """width x height pixels showing the screen plane from `origin`, `scale` pixels per screen unit."""
        self.vram = vram or Vram()
        self.width, self.height = width, height
        self.origin = origin            # screen point drawn at the frame's top-left corner
        self.scale = scale
        self.frame = np.zeros((height, width, 3), np.float32)
        self.frame[:] = background
        self.tpage = 0                  # the draw-mode word (E1): sprites' page, semi-transparency mode
        self.missing_pages = set()      # textured prims whose page holds nothing (drawn untextured)
        self.counts = {"polygons": 0, "sprites": 0, "lines": 0, "other": 0}

    def _point(self, word):
        x, y = _raw_xy(word)
        return (x - self.origin[0]) * self.scale, (y - self.origin[1]) * self.scale

    # ------------------------------------------------------------------ packets
    def draw_packet(self, words):
        """Draw one OT packet: its words may hold several commands (a draw-mode word + a prim)."""
        index = 0
        while index < len(words):
            code = words[index] >> 24
            used = self._command(words, index, code)
            if used <= 0:
                break
            index += used

    def _command(self, words, index, code):
        if 0x20 <= code < 0x40:
            return self._polygon(words, index, code)
        if 0x40 <= code < 0x60:
            return self._line(words, index, code)
        if 0x60 <= code < 0x80:
            return self._sprite(words, index, code)
        if code == 0xE1:
            self.tpage = words[index] & 0xFFFF
            return 1
        if 0xE2 <= code <= 0xE6 or code == 0:
            return 1
        if code == 0x02 and index + 2 < len(words):        # fill rectangle
            x, y = (words[index + 1] & 0x3F0) - self.origin[0], ((words[index + 1] >> 16) & 0x1FF) - self.origin[1]
            w, h = words[index + 2] & 0x3FF, (words[index + 2] >> 16) & 0x1FF
            self.frame[max(0, y):max(0, y + h), max(0, x):max(0, x + w)] = _rgb(words[index])
            return 3
        self.counts["other"] += 1
        return 0                                           # unknown: stop this packet

    def _polygon(self, words, index, code):
        gouraud, quad, textured = bool(code & 0x10), bool(code & 0x08), bool(code & 0x04)
        semi, raw = bool(code & 0x02), bool(code & 0x01)
        points = 4 if quad else 3
        size = 1 + points * (1 + textured) + (points - 1) * gouraud
        if index + size > len(words):
            return 0
        position, colours, uvs = index + 1, [_rgb(words[index])], []
        xys, clut, tpage = [], 0, self.tpage
        for point in range(points):
            if point and gouraud:
                colours.append(_rgb(words[position]))
                position += 1
            xys.append(self._point(words[position]))
            position += 1
            if textured:
                word = words[position]
                uvs.append((word & 0xFF, (word >> 8) & 0xFF))
                if point == 0:
                    clut = word >> 16
                elif point == 1:
                    tpage = word >> 16
                position += 1
        if not gouraud:
            colours = colours * points
        triangles = [(0, 1, 2)] + ([(1, 3, 2)] if quad else [])
        if textured and not self.vram.page_written(tpage):
            self.missing_pages.add(tpage)
            textured = False
        for triangle in triangles:
            self._triangle([xys[i] for i in triangle], [colours[i] for i in triangle],
                           [uvs[i] for i in triangle] if textured else None, clut, tpage, semi, raw)
        self.counts["polygons"] += 1
        return size

    def _sprite(self, words, index, code):
        textured, semi, raw = bool(code & 0x04), bool(code & 0x02), bool(code & 0x01)
        kind = (code >> 3) & 3
        size = 2 + textured + (kind == 0)
        if index + size > len(words):
            return 0
        x, y = self._point(words[index + 1])
        position, u, v, clut = index + 2, 0, 0, 0
        if textured:
            word = words[position]
            u, v, clut = word & 0xFF, (word >> 8) & 0xFF, word >> 16
            position += 1
        if kind == 0:
            w, h = words[position] & 0x3FF, (words[position] >> 16) & 0x1FF
        else:
            w = h = (1, 8, 16)[kind - 1]
        colour = _rgb(words[index])
        if textured and not self.vram.page_written(self.tpage):
            self.missing_pages.add(self.tpage)
            textured = False
        sw, sh = w * self.scale, h * self.scale
        corners = [(x, y), (x + sw, y), (x, y + sh), (x + sw, y + sh)]
        uvs = [(u, v), (u + w, v), (u, v + h), (u + w, v + h)] if textured else None
        for triangle in ((0, 1, 2), (1, 3, 2)):
            self._triangle([corners[i] for i in triangle], [colour] * 3,
                           [uvs[i] for i in triangle] if uvs else None, clut, self.tpage, semi, raw)
        self.counts["sprites"] += 1
        return size

    def _line(self, words, index, code):
        gouraud, poly, semi = bool(code & 0x10), bool(code & 0x08), bool(code & 0x02)
        points, colours, position = [], [_rgb(words[index])], index + 1
        while position < len(words):
            if poly and words[position] & 0xF000F000 == 0x50005000 and len(points) >= 2:
                position += 1
                break
            if points and gouraud:
                colours.append(_rgb(words[position]))
                position += 1
            if position >= len(words):
                break
            points.append(self._point(words[position]))
            position += 1
            if not poly and len(points) == 2:
                break
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            steps = max(abs(x1 - x0), abs(y1 - y0), 1)
            xs = np.round(np.linspace(x0, x1, steps + 1)).astype(int)
            ys = np.round(np.linspace(y0, y1, steps + 1)).astype(int)
            keep = (xs >= 0) & (xs < self.width) & (ys >= 0) & (ys < self.height)
            self._blend(ys[keep], xs[keep], np.tile(np.asarray(colours[0], np.float32), (int(keep.sum()), 1)),
                        np.full(int(keep.sum()), semi), (self.tpage >> 5) & 3)
        self.counts["lines"] += 1
        return position - index

    # ------------------------------------------------------------------ raster
    def _triangle(self, xys, colours, uvs, clut, tpage, semi, raw):
        (x0, y0), (x1, y1), (x2, y2) = xys
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if area == 0:
            return
        left, right = max(int(np.floor(min(x0, x1, x2))), 0), min(int(np.ceil(max(x0, x1, x2))), self.width - 1)
        top, bottom = max(int(np.floor(min(y0, y1, y2))), 0), min(int(np.ceil(max(y0, y1, y2))), self.height - 1)
        if left > right or top > bottom:
            return
        ys, xs = np.mgrid[top:bottom + 1, left:right + 1]
        px, py = xs + 0.5, ys + 0.5
        w0 = ((x1 - px) * (y2 - py) - (x2 - px) * (y1 - py)) / area
        w1 = ((x2 - px) * (y0 - py) - (x0 - px) * (y2 - py)) / area
        w2 = 1.0 - w0 - w1
        inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not inside.any():
            return
        ys, xs, w0, w1, w2 = ys[inside], xs[inside], w0[inside], w1[inside], w2[inside]
        colour = np.asarray(colours, np.float32)
        shade = w0[:, None] * colour[0] + w1[:, None] * colour[1] + w2[:, None] * colour[2]
        blend = np.full(len(xs), semi)
        if uvs is not None:
            u = np.floor(w0 * uvs[0][0] + w1 * uvs[1][0] + w2 * uvs[2][0]).astype(int) & 0xFF
            v = np.floor(w0 * uvs[0][1] + w1 * uvs[1][1] + w2 * uvs[2][1]).astype(int) & 0xFF
            texel = self._texels(u, v, clut, tpage)
            opaque = texel != 0
            if not opaque.any():
                return
            ys, xs, shade, texel, blend = ys[opaque], xs[opaque], shade[opaque], texel[opaque], blend[opaque]
            rgb = _bgr555_to_rgb(texel)
            shade = rgb if raw else np.clip(rgb * shade / 128.0, 0, 255)
            blend = blend & ((texel & 0x8000) != 0)
        self._blend(ys, xs, shade, blend, (tpage >> 5) & 3)

    def _texels(self, u, v, clut, tpage):
        base_x, base_y, depth = (tpage & 0xF) * 64, ((tpage >> 4) & 1) * 256, (tpage >> 7) & 3
        rows = (base_y + v) % VRAM_H
        words = self.vram.words
        if depth == 2:
            return words[rows, (base_x + u) % VRAM_W]
        clut_x, clut_y = (clut & 0x3F) * 16, (clut >> 6) & 0x1FF
        if depth == 0:
            index = (words[rows, (base_x + u // 4) % VRAM_W] >> ((u % 4) * 4)) & 0xF
        else:
            index = (words[rows, (base_x + u // 2) % VRAM_W] >> ((u % 2) * 8)) & 0xFF
        return words[clut_y, (clut_x + index.astype(int)) % VRAM_W]

    def _blend(self, ys, xs, colour, semi, mode):
        if not len(xs):
            return
        result = np.asarray(colour, np.float32).copy()
        if semi.any():
            back = self.frame[ys[semi], xs[semi]]
            front = result[semi]
            result[semi] = (back / 2 + front / 2, back + front, back - front, back + front / 4)[mode]
        self.frame[ys, xs] = np.clip(result, 0, 255)

    def image(self):
        """The frame as an (H, W, 3) uint8 array."""
        return self.frame.astype(np.uint8)
