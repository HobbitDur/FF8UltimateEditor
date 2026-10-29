"""The battle effects' sprite sequences: flipbooks of textured quads in FF8_EN.exe's data.

Every billboard / sprite an effect draws goes through InitEffectSequenceFromData (0x571C80, cloned
into most effect modules) and EffectSprite_EmitFramePrims (its +0x140): the caller names a
sequence and a frame, the emitter draws that frame's pieces as textured quads around the sprite's
position. About 330 sequences lie in the exe's data (file offset = address - 0x400000):

    +0  u32  0x00010524 (the signature, 24 05 01 00)
    +4  u8[4] default palette-row parameters (a piece's flags >> 12 picks one; a caller may override)
    +8  u16  frame count
    +10 u16[frames] frame offsets from the sequence's start, then 0xFFFF
    frame: u32 piece count (bit 31: a draw-mode word E1000020 goes first), then 20 bytes per piece:
      +0 u8 width (texels; the quad is 16 units per texel), +1 u8 intensity (colour = rgb * it >> 7),
      +2 u8 height, +3 u8 GPU code (0x2C textured quad, +2 semi-transparent, +1 raw texture),
      +4 u8 u, +5 u8 v, +6 u16 CLUT (+ parameter << 6: the palette row moves), +8 s16 x,
      +10 s16 y (the quad's top-left from the sprite's position, texels), +12 s16 angle (4096 = a
      turn), +14 u16 flags (bits 0-8 the texture page word, 0xC00 rotate / scale about the quad's
      centre, bits 12-15 the palette-row parameter), +16 s16 scale x, +18 s16 scale y (4096 = 1).

No Qt here.
"""
import re
import struct
from dataclasses import dataclass, field

IMAGE_BASE = 0x400000
SIGNATURE = bytes((0x24, 0x05, 0x01, 0x00))
PIECE_SIZE = 20
MAX_FRAMES = 1024
MAX_PIECES = 256


@dataclass(frozen=True)
class SpritePiece:
    width: int
    intensity: int
    height: int
    gpu_code: int
    u: int
    v: int
    clut: int
    x: int
    y: int
    angle: int
    flags: int
    scale_x: int
    scale_y: int

    @property
    def tpage(self):
        return self.flags & 0x1FF

    @property
    def parameter(self):
        """Which of the sequence's four palette-row parameters moves this piece's CLUT."""
        return self.flags >> 12

    @property
    def transformed(self):
        """Rotated / scaled about its centre (angle, scale_x, scale_y apply)."""
        return bool(self.flags & 0xC00)

    @property
    def semi_transparent(self):
        return bool(self.gpu_code & 2)

    @property
    def depth(self):
        return (self.tpage >> 7) & 3

    @property
    def clut_xy(self):
        return (self.clut & 0x3F) * 16, (self.clut >> 6) & 0x1FF

    @property
    def page_xy(self):
        return (self.tpage & 0xF) * 64, ((self.tpage >> 4) & 1) * 256

    @property
    def blend_mode(self):
        """The page's semi-transparency: 0 B/2+F/2, 1 B+F, 2 B-F, 3 B+F/4."""
        return (self.tpage >> 5) & 3

    def clut_for(self, parameters):
        """The CLUT word drawn, the sequence's (or caller's) palette-row parameter added."""
        return (self.clut + (parameters[self.parameter & 3] << 6)) & 0xFFFF


@dataclass
class SpriteFrame:
    pieces: list = field(default_factory=list)
    draw_mode: bool = False             # an E1000020 draw-mode word before the pieces


@dataclass
class SpriteSequence:
    address: int                        # in FF8_EN.exe's memory (0x400000-based)
    parameters: tuple = (0, 0, 0, 0)
    frames: list = field(default_factory=list)
    size: int = 0                       # bytes, from the signature to the last frame's end

    def pieces(self):
        """Every distinct piece of the sequence."""
        return {piece for frame in self.frames for piece in frame.pieces}


def parse_sequence(data, offset, address=None):
    """The SpriteSequence at file offset `offset` of an exe image, or None when the bytes there are
    not one."""
    if data[offset:offset + 4] != SIGNATURE or offset + 12 > len(data):
        return None
    parameters = tuple(data[offset + 4:offset + 8])
    count = struct.unpack_from("<H", data, offset + 8)[0]
    if not 0 < count <= MAX_FRAMES or offset + 10 + 2 * count > len(data):
        return None
    offsets = struct.unpack_from(f"<{count}H", data, offset + 10)
    sequence = SpriteSequence(address if address is not None else offset + IMAGE_BASE, parameters)
    end = 10 + 2 * count
    for frame_offset in offsets:
        if frame_offset < 10 + 2 * count or offset + frame_offset + 4 > len(data):
            return None
        word = struct.unpack_from("<I", data, offset + frame_offset)[0]
        pieces = word & 0x7FFFFFFF
        start = offset + frame_offset + 4
        if pieces > MAX_PIECES or start + pieces * PIECE_SIZE > len(data):
            return None
        frame = SpriteFrame(draw_mode=bool(word >> 31))
        for index in range(pieces):
            values = struct.unpack_from("<BBBBBBHhhhHhh", data, start + index * PIECE_SIZE)
            piece = SpritePiece(*values)
            if piece.gpu_code & 0xFC != 0x2C:
                return None
            frame.pieces.append(piece)
        sequence.frames.append(frame)
        end = max(end, frame_offset + 4 + pieces * PIECE_SIZE)
    sequence.size = end
    return sequence


def find_sequences(data):
    """{address: SpriteSequence} of every sprite sequence in an exe image (FF8_EN.exe's bytes)."""
    found = {}
    for match in re.finditer(re.escape(SIGNATURE), data):
        sequence = parse_sequence(data, match.start())
        if sequence is not None:
            found[sequence.address] = sequence
    return found


_CACHE = {}


def exe_sequences(path):
    """find_sequences of an exe file, cached per file (path, size, modification time)."""
    import os
    try:
        stat = os.stat(path)
    except OSError:
        return {}
    key = (os.path.abspath(path), stat.st_size, stat.st_mtime_ns)
    if key not in _CACHE:
        with open(path, "rb") as file:
            _CACHE.clear()
            _CACHE[key] = find_sequences(file.read())
    return _CACHE[key]


def piece_rect(piece):
    """(u0, v0, u1, v1) of the texels a piece takes (u1 / v1 excluded, at most 256)."""
    return piece.u, piece.v, min(256, piece.u + piece.width), min(256, piece.v + piece.height)

