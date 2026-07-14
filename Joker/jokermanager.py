import os
import struct

from FF8GameData.FF8HexReader.mngrp import Mngrp
from FF8GameData.FF8HexReader.mngrphd import Mngrphd
from FF8GameData.gamedata import GameData


class Sp2Quad:
    """One 12-byte textured quad of an SP2 sprite record.

    The quad only carries UV/CLUT rectangles and draw offsets: the texture itself is a TIM
    already uploaded to VRAM by the menu module (face1/face2.TEX for face.sp2, the card
    texture for cardanm.sp2, the magazine page picture for mngrp Pos 4).
    """

    SIZE = 12
    # The game reads the texture page field masked with 0x9FF (PS1 GPU E1 bits).
    # The raw UInt16 is preserved as-is so untouched quads stay byte-exact.
    TEXPAGE_MASK = 0x9FF

    def __init__(self, u=0, v=0, clut=0, width=0, height=0, dx=0, dy=0, texpage=0):
        self.u = u
        self.v = v
        self.clut = clut
        self.width = width
        self.height = height
        self.dx = dx  # Signed X offset from the sprite draw position
        self.dy = dy  # Signed Y offset from the sprite draw position
        self.texpage = texpage

    @classmethod
    def from_bytes(cls, quad_bytes):
        u, v, clut, width, height, dx, dy, texpage = struct.unpack("<BBHHHbbH", quad_bytes)
        return cls(u=u, v=v, clut=clut, width=width, height=height, dx=dx, dy=dy, texpage=texpage)

    def to_bytes(self):
        return struct.pack("<BBHHHbbH", self.u, self.v, self.clut, self.width, self.height,
                           self.dx, self.dy, self.texpage)

    def __str__(self):
        return (f"Sp2Quad(uv: ({self.u}, {self.v}), clut: 0x{self.clut:04X}, "
                f"size: {self.width}x{self.height}, offset: ({self.dx}, {self.dy}), "
                f"texpage: 0x{self.texpage:04X})")


class Sp2Sprite:
    """One sprite id of an SP2 table: a list of quads, or an unused id (offset 0 in the directory).

    An unused sprite keeps its quads in memory so it can be re-enabled without losing them,
    but they are not written to the file (its directory offset is saved as 0).
    """

    def __init__(self, sprite_id, quads=None, used=True):
        self.sprite_id = sprite_id
        self.quads = quads if quads is not None else []
        self.used = used

    def __str__(self):
        if not self.used:
            return f"Sp2Sprite(id {self.sprite_id}: unused)"
        return f"Sp2Sprite(id {self.sprite_id}: {len(self.quads)} quad(s))"


class Sp2File:
    """An SP2 quad-list sprite table (face.sp2, cardanm.sp2, mngrp.bin Pos 4).

    Layout: UInt32 sprite count, UInt32 offsets[count] from the start of the file (0 = unused id),
    then the sprite records. Each record is an Int32 quad count followed by 12 bytes per quad.
    The three known files store their records contiguously in sprite id order, which is also
    how to_bytes() rebuilds the directory, so an unmodified load/save is byte-exact.
    """

    HEADER_COUNT_SIZE = 4
    OFFSET_SIZE = 4

    def __init__(self, sprites=None):
        self.sprites = sprites if sprites is not None else []

    @classmethod
    def from_bytes(cls, data):
        if len(data) < cls.HEADER_COUNT_SIZE:
            raise ValueError(f"SP2 data too short ({len(data)} bytes), no sprite count")
        count = struct.unpack_from("<I", data, 0)[0]
        directory_end = cls.HEADER_COUNT_SIZE + cls.OFFSET_SIZE * count
        if directory_end > len(data):
            raise ValueError(f"SP2 sprite count {count} does not fit in {len(data)} bytes, "
                             f"not an SP2 file")
        sprites = []
        for sprite_id in range(count):
            offset = struct.unpack_from("<I", data, cls.HEADER_COUNT_SIZE + cls.OFFSET_SIZE * sprite_id)[0]
            if offset == 0:
                sprites.append(Sp2Sprite(sprite_id, used=False))
                continue
            if offset + 4 > len(data):
                raise ValueError(f"Sprite {sprite_id} offset 0x{offset:X} is outside the file")
            quad_count = struct.unpack_from("<i", data, offset)[0]
            quads_end = offset + 4 + Sp2Quad.SIZE * quad_count
            if quad_count < 0 or quads_end > len(data):
                raise ValueError(f"Sprite {sprite_id} quad count {quad_count} at offset 0x{offset:X} "
                                 f"is outside the file")
            quads = []
            for quad_index in range(quad_count):
                quad_offset = offset + 4 + Sp2Quad.SIZE * quad_index
                quads.append(Sp2Quad.from_bytes(data[quad_offset:quad_offset + Sp2Quad.SIZE]))
            sprites.append(Sp2Sprite(sprite_id, quads=quads))
        return cls(sprites)

    def to_bytes(self):
        """Rebuild the whole file, records contiguous in sprite id order (offsets recomputed)."""
        directory = bytearray()
        records = bytearray()
        records_start = self.HEADER_COUNT_SIZE + self.OFFSET_SIZE * len(self.sprites)
        for sprite in self.sprites:
            if not sprite.used:
                directory.extend((0).to_bytes(self.OFFSET_SIZE, byteorder='little'))
                continue
            directory.extend((records_start + len(records)).to_bytes(self.OFFSET_SIZE, byteorder='little'))
            records.extend(struct.pack("<i", len(sprite.quads)))
            for quad in sprite.quads:
                records.extend(quad.to_bytes())
        return bytes(struct.pack("<I", len(self.sprites)) + directory + records)

    def add_sprite(self):
        """Append a new used sprite id at the end of the directory and return it."""
        sprite = Sp2Sprite(len(self.sprites), quads=[Sp2Quad()])
        self.sprites.append(sprite)
        return sprite

    def used_sprites(self):
        return [sprite for sprite in self.sprites if sprite.used]

    def unused_ids(self):
        return [sprite.sprite_id for sprite in self.sprites if not sprite.used]

    def __str__(self):
        return f"Sp2File({len(self.sprites)} sprite ids, {len(self.unused_ids())} unused)"


class JokerManager:
    """SP2 sprite-table editor logic.

    Two sources share the same Sp2File model:
      - a standalone .sp2 file (face.sp2, cardanm.sp2): load_file / save_file
      - the magazine/Chocobo World pictures stored as mngrp.bin Pos 4 (raw mngrphd entry 7):
        load_mngrp / save_mngrp rewrite that section in place, the other sections untouched.
    """

    # Valid-section index of the SP2 sprite table inside mngrp.bin (raw mngrphd.bin entry 7)
    MNGRP_SP2_SECTION_POS = 4

    def __init__(self, game_data: GameData):
        self.game_data = game_data
        self.sp2 = None
        self.file_path = ""
        self.mngrp_path = ""
        self.mngrphd_path = ""
        self._mngrp_data = bytearray()
        self._mngrphd_data = bytearray()

    @property
    def is_mngrp_mode(self):
        return bool(self.mngrp_path)

    def load_file(self, file_path):
        """Load a standalone .sp2 file."""
        with open(file_path, "rb") as in_file:
            self.sp2 = Sp2File.from_bytes(in_file.read())
        self.file_path = file_path
        self.mngrp_path = ""
        self.mngrphd_path = ""

    def save_file(self, file_path=""):
        if not self.sp2:
            raise ValueError("No file loaded")
        if not file_path:
            file_path = self.file_path
        with open(file_path, "wb") as out_file:
            out_file.write(self.sp2.to_bytes())

    def load_mngrp(self, mngrp_path, mngrphd_path=""):
        """Load the SP2 table of mngrp.bin Pos 4, mngrphd.bin is searched next to it if not given."""
        if not mngrphd_path:
            mngrphd_path = os.path.join(os.path.dirname(mngrp_path), "mngrphd.bin")
        if not os.path.exists(mngrphd_path):
            raise FileNotFoundError(f"mngrphd.bin is needed to locate the sections of mngrp.bin, "
                                    f"not found at: {mngrphd_path}")
        with open(mngrp_path, "rb") as in_file:
            self._mngrp_data = bytearray(in_file.read())
        with open(mngrphd_path, "rb") as in_file:
            self._mngrphd_data = bytearray(in_file.read())

        mngrphd = Mngrphd(game_data=self.game_data, data_hex=bytearray(self._mngrphd_data))
        mngrp = Mngrp(game_data=self.game_data, data_hex=bytearray(self._mngrp_data),
                      header_entry_list=mngrphd.get_valid_entry_list())
        section_data = mngrp.get_section_by_id(self.MNGRP_SP2_SECTION_POS).get_data_hex()
        self.sp2 = Sp2File.from_bytes(bytes(section_data))
        self.mngrp_path = mngrp_path
        self.mngrphd_path = mngrphd_path
        self.file_path = ""

    def save_mngrp(self, mngrp_path="", mngrphd_path=""):
        """Write the SP2 table back inside the loaded mngrp.bin/mngrphd.bin (in place by default).
        The other mngrp sections are untouched; if the table grew, the following sections are
        shifted and the mngrphd offsets updated."""
        if not self.sp2 or not self.mngrp_path:
            raise ValueError("No mngrp.bin loaded")
        if not mngrp_path:
            mngrp_path = self.mngrp_path
        if not mngrphd_path:
            mngrphd_path = self.mngrphd_path

        # The full entry list (invalid included) is used so the rebuilt mngrphd keeps all its entries
        mngrphd = Mngrphd(game_data=self.game_data, data_hex=bytearray(self._mngrphd_data))
        mngrp = Mngrp(game_data=self.game_data, data_hex=bytearray(self._mngrp_data),
                      header_entry_list=mngrphd.get_entry_list())
        mngrp.set_section_by_id_and_bytearray(self.MNGRP_SP2_SECTION_POS, bytearray(self.sp2.to_bytes()))
        mngrp.update_data_hex()
        mngrphd.update_from_section_list(mngrp.get_section_list())
        mngrphd.update_data_hex()

        with open(mngrp_path, "wb") as out_file:
            out_file.write(mngrp.get_data_hex())
        with open(mngrphd_path, "wb") as out_file:
            out_file.write(mngrphd.get_data_hex())
