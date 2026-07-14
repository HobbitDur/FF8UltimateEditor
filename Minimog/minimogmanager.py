"""icon.sp1 (menu icon UV table) reader/writer.

The menu module describes each icon drawable by the text engine (control code
0x05+n) as a list of textured quads cropped from the icon texture (icon.TEX on
PC, one 256x256 4bpp VRAM page). On-disk layout::

    0x00  UInt32 icon count (329 in the vanilla icon.sp1)
    0x04  Directory, one UInt32 per icon id:
              {UInt16 offset from file start, UInt16 quad count}
    ...   Quads, 8 bytes each

Each quad is two packed UInt32:

* DWord 0: bits 0-15 = texture UV (byte U, byte V) - bits 16-26 = CLUT selector
  (the primitive CLUT is 0x3810 + these bits, so the TEX palette index is the
  selector >> 6) - bit 27 = semi-transparency (ABE) - bits 28-29 unused
  (preserved) - bits 30-31 = texture page (E1 bits 5-6).
* DWord 1: byte 0 = width - byte 1 = signed X offset - byte 2 = height -
  byte 3 = signed Y offset.

Icon ids 128-139 are the confirm/cancel/etc. button icons: the engine never
reads their quads and redirects them to a dedicated renderer that remaps them
through the controller key configuration. Their file content (the default PSX
button glyphs) is exposed read-only by the GUI.

Saving rebuilds the directory canonically (quads contiguous, in icon id order,
right after the directory), which reproduces the vanilla file byte-exact.
"""
import struct

QUAD_SIZE = 8
CLUT_BASE = 0x3810  # primitive CLUT = CLUT_BASE + quad CLUT selector

# Icon ids redirected to the key-config button renderer (quads unused in-game).
BUTTON_ICON_RANGE = range(128, 140)
BUTTON_ICON_NAMES = {
    128: "L2", 129: "R2", 130: "L1", 131: "R1",
    132: "Triangle", 133: "Circle", 134: "Cross", 135: "Square",
    136: "Select", 137: "L3", 138: "R3", 139: "Start",
}


class Sp1Quad:
    """One 8-byte textured quad of an icon."""

    def __init__(self, u=0, v=0, clut=0, semi_transparent=False, texture_page=0,
                 unknown_bits=0, width=0, dx=0, height=0, dy=0):
        self.u = u
        self.v = v
        self.clut = clut  # 11-bit CLUT selector (primitive CLUT = 0x3810 + clut)
        self.semi_transparent = semi_transparent  # bit 27 (ABE)
        self.texture_page = texture_page  # bits 30-31 (E1 bits 5-6)
        self.unknown_bits = unknown_bits  # bits 28-29, always 0 in vanilla, kept lossless
        self.width = width
        self.dx = dx  # signed X offset from the icon draw position
        self.height = height
        self.dy = dy  # signed Y offset

    @classmethod
    def from_bytes(cls, data, offset=0):
        dword0, = struct.unpack_from("<I", data, offset)
        width, dx, height, dy = struct.unpack_from("<BbBb", data, offset + 4)
        return cls(
            u=dword0 & 0xFF,
            v=(dword0 >> 8) & 0xFF,
            clut=(dword0 >> 16) & 0x7FF,
            semi_transparent=bool((dword0 >> 27) & 1),
            unknown_bits=(dword0 >> 28) & 3,
            texture_page=(dword0 >> 30) & 3,
            width=width, dx=dx, height=height, dy=dy,
        )

    def to_bytes(self):
        dword0 = ((self.u & 0xFF)
                  | ((self.v & 0xFF) << 8)
                  | ((self.clut & 0x7FF) << 16)
                  | ((1 << 27) if self.semi_transparent else 0)
                  | ((self.unknown_bits & 3) << 28)
                  | ((self.texture_page & 3) << 30))
        return struct.pack("<I", dword0) + struct.pack("<BbBb", self.width & 0xFF,
                                                       self.dx, self.height & 0xFF, self.dy)

    @property
    def primitive_clut(self):
        """The PSX CLUT id actually written in the GPU primitive."""
        return CLUT_BASE + self.clut

    @property
    def palette_index(self):
        """TEX palette index: the CLUT selector counts 64-unit VRAM rows."""
        return self.clut >> 6

    def __str__(self):
        flags = []
        if self.semi_transparent:
            flags.append("semi-transparent")
        if self.unknown_bits:
            flags.append(f"unk28-29={self.unknown_bits}")
        flags = (" " + " ".join(flags)) if flags else ""
        return (f"UV({self.u},{self.v}) {self.width}x{self.height} "
                f"offset({self.dx:+},{self.dy:+}) clut={self.clut} "
                f"(palette {self.palette_index}) tpage={self.texture_page}{flags}")


class Sp1Icon:
    """One icon id: a list of quads composited at draw time."""

    def __init__(self, icon_id, quads=None):
        self.icon_id = icon_id
        self.quads = quads if quads is not None else []

    @property
    def is_button_icon(self):
        """Ids 128-139 are remapped through the key config, quads unused in-game."""
        return self.icon_id in BUTTON_ICON_RANGE

    @property
    def name(self):
        if self.is_button_icon:
            return f"Icon {self.icon_id} [{BUTTON_ICON_NAMES[self.icon_id]} button]"
        return f"Icon {self.icon_id}"

    def bounding_box(self):
        """(min_x, min_y, max_x, max_y) over the quads' draw rectangles."""
        if not self.quads:
            return 0, 0, 0, 0
        min_x = min(q.dx for q in self.quads)
        min_y = min(q.dy for q in self.quads)
        max_x = max(q.dx + q.width for q in self.quads)
        max_y = max(q.dy + q.height for q in self.quads)
        return min_x, min_y, max_x, max_y


class MinimogManager:
    """icon.sp1 editor logic: parse, edit and rebuild the quad table."""

    def __init__(self, game_data=None):
        self.game_data = game_data
        self.file_path = ""
        self.icons = []

    # ------------------------------------------------------------------ load
    def load_file(self, file_path):
        self.file_path = file_path
        with open(file_path, "rb") as in_file:
            self.load_bytes(in_file.read())

    def load_bytes(self, data):
        icon_count, = struct.unpack_from("<I", data, 0)
        directory_end = 4 + 4 * icon_count
        if directory_end > len(data):
            raise ValueError(f"sp1 too small: {icon_count} icons need a "
                             f"{directory_end}-byte directory but file is {len(data)} bytes")
        self.icons = []
        for icon_id in range(icon_count):
            offset, quad_count = struct.unpack_from("<HH", data, 4 + 4 * icon_id)
            if offset + quad_count * QUAD_SIZE > len(data):
                raise ValueError(f"icon {icon_id}: quads at 0x{offset:X} "
                                 f"(count {quad_count}) run past end of file")
            quads = [Sp1Quad.from_bytes(data, offset + k * QUAD_SIZE)
                     for k in range(quad_count)]
            self.icons.append(Sp1Icon(icon_id, quads))

    # ------------------------------------------------------------------ save
    def to_bytes(self):
        """Rebuild the file: directory then quads, contiguous in icon id order."""
        directory_end = 4 + 4 * len(self.icons)
        directory = bytearray()
        quad_block = bytearray()
        for icon in self.icons:
            offset = directory_end + len(quad_block)
            if offset > 0xFFFF:
                raise ValueError(f"icon {icon.icon_id}: quad offset 0x{offset:X} "
                                 f"does not fit the UInt16 directory entry")
            directory += struct.pack("<HH", offset, len(icon.quads))
            for quad in icon.quads:
                quad_block += quad.to_bytes()
        return struct.pack("<I", len(self.icons)) + bytes(directory) + bytes(quad_block)

    def save_file(self, file_path=""):
        if not file_path:
            file_path = self.file_path
        with open(file_path, "wb") as out_file:
            out_file.write(self.to_bytes())

    # ------------------------------------------------------------------ edit
    def add_quad(self, icon_id, quad=None):
        """Append a quad to an icon (the directory is rebuilt on save)."""
        icon = self.icons[icon_id]
        if quad is None:
            quad = Sp1Quad(width=16, height=16, clut=32)  # clut 32 = palette 0, the most common
        icon.quads.append(quad)
        return quad

    def remove_quad(self, icon_id, quad_index):
        return self.icons[icon_id].quads.pop(quad_index)

    # --------------------------------------------------------------- preview
    def render_icon(self, icon_id, tex_file, scale=1):
        """Composite an icon's quads from a decoded icon.TEX into a PIL image.

        Each quad is cropped at (u, v, width, height) with the palette its CLUT
        selector points to, then pasted at its (dx, dy) draw offset. Returns
        None for an icon without visible quads."""
        from PIL import Image

        icon = self.icons[icon_id]
        min_x, min_y, max_x, max_y = icon.bounding_box()
        if max_x <= min_x or max_y <= min_y:
            return None
        image = Image.new("RGBA", (max_x - min_x, max_y - min_y), (0, 0, 0, 0))
        for quad in icon.quads:
            if quad.width == 0 or quad.height == 0:
                continue
            palette = min(quad.palette_index, tex_file.num_palettes - 1)
            crop = tex_file.to_image(palette).crop(
                (quad.u, quad.v,
                 min(quad.u + quad.width, tex_file.width),
                 min(quad.v + quad.height, tex_file.height)))
            image.alpha_composite(crop, (quad.dx - min_x, quad.dy - min_y))
        if scale > 1:
            image = image.resize((image.width * scale, image.height * scale),
                                 Image.NEAREST)
        return image
