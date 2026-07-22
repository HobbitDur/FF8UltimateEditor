
import copy
import math
import os
from enum import Enum
from typing import List, Optional, Tuple
from urllib.parse import to_bytes


class EntityType(Enum):
    MONSTER = 1
    WEAPON = 2
    CHARACTER = 3
    WEAPON_NO_ANIM = 4
    # A character having no weapon file (Edea, d7c016): the sections a weapon usually
    # carries for the pair (animation sequences, sounds) are inside the body file.
    CHARACTER_NO_WEAPON = 5
    # A "monster" with no visual model at all - just info_stat + AI, 3 header sections
    # (header + 2 real sections). Only known instance: c0m127.dat, com_id 127 =
    # "Ultimecia (No Model, has Apocalypse)" - an invisible, untargetable trigger entity
    # used purely to cast the Apocalypse attack in the final battle. Confirmed by decoding
    # section 1 as a normal info_stat block (monster_name = "Ultimecia", same 380-byte size
    # as every other monster's section 7) and section 2 as a normal AI/battle_script block
    # (decompiles to coherent code: untargetable() on init, untargetable();vanish() on
    # death) - both via the existing, unmodified info_stat/AI parsers. The exact EXE loader
    # for this specific case hasn't been pinned down in IDA (battle_monster_dat_loader
    # handles the standard 11-section layout only); the section contents themselves are
    # unambiguous regardless of which loader function reads them.
    MONSTER_NO_MODEL = 6
# Section 1
class BoneSection:
    SECTION_BONE_HEADER_NB = {'offset': 0x00, 'size': 1, 'byteorder': 'little', 'name': 'nb_bone', 'pretty_name': 'Number bones', 'default_value': 0}
    SECTION_BONE_HEADER_EXTRA_DATA = {'offset': 0x01, 'size': 1, 'byteorder': 'little', 'name': 'bone_extra_data', 'pretty_name': 'Bone extra data', 'default_value': 0}
    SECTION_BONE_HEADER_UNKNOWN00 = {'offset': 0x02, 'size': 2, 'byteorder': 'little', 'name': 'unknown00', 'pretty_name': 'Unknown00', 'default_value': 0}
    SECTION_BONE_HEADER_UNKNOWN01 = {'offset': 0x04, 'size': 2, 'byteorder': 'little', 'name': 'unknown01', 'pretty_name': 'Unknown01', 'default_value': 0}
    SECTION_BONE_HEADER_UNKNOWN02 = {'offset': 0x06, 'size': 2, 'byteorder': 'little', 'name': 'unknown02', 'pretty_name': 'Unknown01', 'default_value': 0}
    SECTION_BONE_HEADER_SCALE_X = {'offset': 0x08, 'size': 2, 'byteorder': 'little', 'name': 'scaleX', 'pretty_name': 'Scale X', 'default_value': 0, 'signed':True}
    SECTION_BONE_HEADER_SCALE_Y = {'offset': 0x0A, 'size': 2, 'byteorder': 'little', 'name': 'scaleY', 'pretty_name': 'Scale Z', 'default_value': 0, 'signed':True}
    SECTION_BONE_HEADER_SCALE_Z = {'offset': 0x0C, 'size': 2, 'byteorder': 'little', 'name': 'scaleZ', 'pretty_name': 'Scale Y', 'default_value': 0, 'signed':True}
    SECTION_BONE_HEADER_UNKNOWN2 = {'offset': 0x0E, 'size': 2, 'byteorder': 'little', 'name': 'unknown2', 'pretty_name': 'Unknown2', 'default_value': 0}
    def __init__(self):
        self.nb_bone = 0
        self.extra_data:bool = False
        self.unknown00 = 0
        self.unknown01 = 0
        self.unknown02 = 0
        self._scale_x = 0
        self._scale_y = 0
        self._scale_z = 0
        self.unknown2 = 0
        self.bones:List[Bone]= []
    def __str__(self):
        return f"Bones(count:{self.nb_bone}, unknown00:{self.unknown00}, unknown01:{self.unknown01}, unknown02:{self.unknown02}, scaleX:{self._scale_x}, scaleY:{self._scale_y}, scaleZ:{self._scale_z}, unknown2:{self.unknown2}, {self.bones})"
    def __repr__(self):
        return self.__str__()
    def analyze(self, data:bytes):
        self.nb_bone = int.from_bytes(data[self.SECTION_BONE_HEADER_NB['offset']:self.SECTION_BONE_HEADER_NB['offset'] + self.SECTION_BONE_HEADER_NB['size']],
                                        byteorder=self.SECTION_BONE_HEADER_NB['byteorder'])
        self.extra_data = bool(int.from_bytes(data[self.SECTION_BONE_HEADER_EXTRA_DATA['offset']:self.SECTION_BONE_HEADER_EXTRA_DATA['offset'] + self.SECTION_BONE_HEADER_EXTRA_DATA['size']],
                                        byteorder=self.SECTION_BONE_HEADER_EXTRA_DATA['byteorder']))
        self.unknown00 = int.from_bytes(data[self.SECTION_BONE_HEADER_UNKNOWN00['offset']:self.SECTION_BONE_HEADER_UNKNOWN00['offset'] + self.SECTION_BONE_HEADER_UNKNOWN00['size']],
                                        byteorder=self.SECTION_BONE_HEADER_UNKNOWN00['byteorder'])
        self.unknown01 = int.from_bytes(data[self.SECTION_BONE_HEADER_UNKNOWN01['offset']:self.SECTION_BONE_HEADER_UNKNOWN01['offset'] + self.SECTION_BONE_HEADER_UNKNOWN01['size']],
                                        byteorder=self.SECTION_BONE_HEADER_UNKNOWN01['byteorder'])
        self.unknown02 = int.from_bytes(data[self.SECTION_BONE_HEADER_UNKNOWN02['offset']:self.SECTION_BONE_HEADER_UNKNOWN02['offset'] + self.SECTION_BONE_HEADER_UNKNOWN02['size']],
                                        byteorder=self.SECTION_BONE_HEADER_UNKNOWN02['byteorder'])
        self._scale_x = int.from_bytes(data[self.SECTION_BONE_HEADER_SCALE_X['offset']:self.SECTION_BONE_HEADER_SCALE_X['offset'] + self.SECTION_BONE_HEADER_SCALE_X['size']],
                                        byteorder=self.SECTION_BONE_HEADER_SCALE_X['byteorder'], signed=True)
        self._scale_y = int.from_bytes(data[self.SECTION_BONE_HEADER_SCALE_Y['offset']:self.SECTION_BONE_HEADER_SCALE_Y['offset'] + self.SECTION_BONE_HEADER_SCALE_Y['size']],
                                        byteorder=self.SECTION_BONE_HEADER_SCALE_Y['byteorder'], signed=True)
        self._scale_z = int.from_bytes(data[self.SECTION_BONE_HEADER_SCALE_Z['offset']:self.SECTION_BONE_HEADER_SCALE_Z['offset'] + self.SECTION_BONE_HEADER_SCALE_Z['size']],
                                        byteorder=self.SECTION_BONE_HEADER_SCALE_Z['byteorder'], signed=True)
        self.unknown2 = int.from_bytes(
            data[self.SECTION_BONE_HEADER_UNKNOWN2['offset']:self.SECTION_BONE_HEADER_UNKNOWN2['offset'] + self.SECTION_BONE_HEADER_UNKNOWN2['size']],
            byteorder=self.SECTION_BONE_HEADER_UNKNOWN2['byteorder'])
        current_index = self.SECTION_BONE_HEADER_UNKNOWN2['offset'] + self.SECTION_BONE_HEADER_UNKNOWN2['size']
        next_index = current_index + 48
        for i in range(self.nb_bone):
            self.bones.append(Bone())
            self.bones[-1].analyze(data[current_index:next_index])
            current_index = next_index
            next_index = next_index + 48
    def get_scale_list(self):
        return -self._scale_x/2048, -self._scale_y/2048, -self._scale_z/2048


    def to_binary(self) -> bytearray:
        """Convert entire bone section back to binary"""
        data = bytearray()
        # Write header
        data.extend(self.nb_bone.to_bytes(2, byteorder='little'))
        data.extend(self.unknown00.to_bytes(2, byteorder='little'))
        data.extend(self.unknown01.to_bytes(2, byteorder='little'))
        data.extend(self.unknown02.to_bytes(2, byteorder='little'))
        data.extend(self._scale_x.to_bytes(2, byteorder='little', signed=True))
        data.extend(self._scale_y.to_bytes(2, byteorder='little', signed=True))
        data.extend(self._scale_z.to_bytes(2, byteorder='little', signed=True))
        data.extend(self.unknown2.to_bytes(2, byteorder='little'))

        # Write all bones
        for bone in self.bones:
            data.extend(bone.get_byte())

        return data
class Bone:
    SECTION_BONE_DATA_PARENT = {'offset': 0x00, 'size': 2, 'byteorder': 'little', 'name': 'parent', 'pretty_name': 'Parent ID', 'default_value':0}
    SECTION_BONE_DATA_SIZE = {'offset': 0x02, 'size': 2, 'byteorder': 'little', 'name': 'size', 'pretty_name': 'Size', 'default_value':0}
    SECTION_BONE_DATA_ROTX = {'offset': 0x04, 'size': 2, 'byteorder': 'little', 'name': 'rotX', 'pretty_name': 'Rotation X', 'default_value':0}
    SECTION_BONE_DATA_ROTY = {'offset': 0x06, 'size': 2, 'byteorder': 'little', 'name': 'rotY', 'pretty_name': 'Rotation Z', 'default_value':0}
    SECTION_BONE_DATA_ROTZ = {'offset': 0x08, 'size': 2, 'byteorder': 'little', 'name': 'rotZ', 'pretty_name': 'Rotation Y', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN3 = {'offset': 0x0A, 'size': 2, 'byteorder': 'little', 'name': 'unknown3', 'pretty_name': 'Unknown 3', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN4 = {'offset': 0x0C, 'size': 2, 'byteorder': 'little', 'name': 'unknown4', 'pretty_name': 'Unknown 4', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN5 = {'offset': 0x0E, 'size': 2, 'byteorder': 'little', 'name': 'unknown5', 'pretty_name': 'Unknown 5', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN6 = {'offset': 0x10, 'size': 2, 'byteorder': 'little', 'name': 'unknown6', 'pretty_name': 'Unknown 6', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN7 = {'offset': 0x12, 'size': 2, 'byteorder': 'little', 'name': 'unknown7', 'pretty_name': 'Unknown 7', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN8 = {'offset': 0x14, 'size': 2, 'byteorder': 'little', 'name': 'unknown8', 'pretty_name': 'Unknown 8', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN9 = {'offset': 0x16, 'size': 2, 'byteorder': 'little', 'name': 'unknown9', 'pretty_name': 'Unknown 9', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN10 = {'offset': 0x18, 'size': 2, 'byteorder': 'little', 'name': 'unknown10', 'pretty_name': 'Unknown 10', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN11 = {'offset': 0x1A, 'size': 2, 'byteorder': 'little', 'name': 'unknown11', 'pretty_name': 'Unknown 11', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN12 = {'offset': 0x1C, 'size': 2, 'byteorder': 'little', 'name': 'unknown12', 'pretty_name': 'Unknown 12', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN13 = {'offset': 0x1E, 'size': 2, 'byteorder': 'little', 'name': 'unknown13', 'pretty_name': 'Unknown 13', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN14 = {'offset': 0x20, 'size': 2, 'byteorder': 'little', 'name': 'unknown14', 'pretty_name': 'Unknown 14', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN15 = {'offset': 0x22, 'size': 2, 'byteorder': 'little', 'name': 'unknown15', 'pretty_name': 'Unknown 15', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN16 = {'offset': 0x24, 'size': 2, 'byteorder': 'little', 'name': 'unknown16', 'pretty_name': 'Unknown 16', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN17 = {'offset': 0x26, 'size': 2, 'byteorder': 'little', 'name': 'unknown17', 'pretty_name': 'Unknown 17', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN18 = {'offset': 0x28, 'size': 2, 'byteorder': 'little', 'name': 'unknown18', 'pretty_name': 'Unknown 18', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN19 = {'offset': 0x2A, 'size': 2, 'byteorder': 'little', 'name': 'unknown19', 'pretty_name': 'Unknown 19', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN20 = {'offset': 0x2C, 'size': 2, 'byteorder': 'little', 'name': 'unknown20', 'pretty_name': 'Unknown 20', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN21 = {'offset': 0x2E, 'size': 2, 'byteorder': 'little', 'name': 'unknown21', 'pretty_name': 'Unknown 21', 'default_value':0}
    def __init__(self):
        self.parent_id: int = 0
        self._size: int = 0
        self._rotX = 0
        self._rotY = 0
        self._rotZ = 0
        self._local_rotation = (0, 0, 0)  # Will be filled from animation
        self._world_matrix = None
        self._world_position = (0, 0, 0)
        self._world_end = (0, 0, 0)
        # Bytes 0x0A-0x2F of the 48-byte bone entry: not yet reverse-engineered
        # (a guessed scaleX/scaleY/scaleZ/matrix/unk7 layout exists in the IDA
        # database but has zero confirmed xrefs from real bone-parsing code),
        # and real game files do have non-zero data here for some monsters. Kept
        # verbatim and re-emitted on save instead of zero-filling, since there is
        # no editor for these fields and no reason to believe the game ignores
        # them (that guess previously silently corrupted monster skeletons with
        # non-zero data in this range on any load->save round trip).
        self._original_unknown_tail: bytes = bytes(38)
    def __str__(self):
        return f"Bone(Parent:{self.parent_id}, length:{self.get_size()}, rot:{self._rotX},{self._rotY},{self._rotZ})"
    def __repr__(self):
        return self.__str__()
    def analyze(self, data:bytes):
        self.parent_id = int.from_bytes(data[self.SECTION_BONE_DATA_PARENT['offset']:self.SECTION_BONE_DATA_PARENT['offset']+self.SECTION_BONE_DATA_PARENT['size']], byteorder=self.SECTION_BONE_DATA_PARENT['byteorder'])
        self._size = int.from_bytes(data[self.SECTION_BONE_DATA_SIZE['offset']:self.SECTION_BONE_DATA_SIZE['offset']+self.SECTION_BONE_DATA_SIZE['size']], byteorder=self.SECTION_BONE_DATA_SIZE['byteorder'], signed=True)
        self._rotX = int.from_bytes(data[self.SECTION_BONE_DATA_ROTX['offset']:self.SECTION_BONE_DATA_ROTX['offset']+self.SECTION_BONE_DATA_ROTX['size']], byteorder=self.SECTION_BONE_DATA_ROTX['byteorder'], signed=True)
        self._rotY = int.from_bytes(data[self.SECTION_BONE_DATA_ROTY['offset']:self.SECTION_BONE_DATA_ROTY['offset']+self.SECTION_BONE_DATA_ROTY['size']], byteorder=self.SECTION_BONE_DATA_ROTY['byteorder'], signed=True)
        self._rotZ = int.from_bytes(data[self.SECTION_BONE_DATA_ROTZ['offset']:self.SECTION_BONE_DATA_ROTZ['offset']+self.SECTION_BONE_DATA_ROTZ['size']], byteorder=self.SECTION_BONE_DATA_ROTZ['byteorder'], signed=True)
        self._original_unknown_tail = bytes(data[0x0A:0x30])

    def get_size_raw(self) -> int:
        return self._size
    def get_size(self) -> float:
        return self._size / 2048
    def set_size(self, size: float):
        self._size = round(size * 2048)
    def set_size_raw(self, size: int):
        self._size = size

    def get_rotation_deg(self):
        """Get rotation in degrees for animation (matches C# order)"""
        return (
            self._rotX * 360.0 / 4096.0,
            self._rotY * 360.0 / 4096.0,
            self._rotZ * 360.0 / 4096.0
        )
    def set_rotation_deg(self, rx: float, ry: float, rz: float):
        """Set rotation in degrees and update raw values.

        round() (not int() truncation) so a degree value maps to the NEAREST raw unit and the
        raw<->deg round-trip is lossless - matches the frame-rotation path (RotationType.rotate_deg)
        and the position/scale setters. int() truncation drifted values down by up to one raw unit
        (1 raw = 360/4096 = 0.088 deg)."""
        self._rotX = round(rx * 4096.0 / 360.0)
        self._rotY = round(ry * 4096.0 / 360.0)
        self._rotZ = round(rz * 4096.0 / 360.0)
    def get_byte(self) -> bytearray:
        """Convert bone back to binary format"""
        data = bytearray()
        data.extend(self.parent_id.to_bytes(2, byteorder='little', signed=False))
        data.extend(self._size.to_bytes(2, byteorder='little', signed=True))
        data.extend(self._rotX.to_bytes(2, byteorder='little', signed=True))
        data.extend(self._rotY.to_bytes(2, byteorder='little', signed=True))
        data.extend(self._rotZ.to_bytes(2, byteorder='little', signed=True))

        # Bytes 0x0A-0x2F: unparsed, preserved verbatim (see __init__).
        data.extend(self._original_unknown_tail)
        return data

# Section 2 data
class GeometryTriangle:
    SECTION_GEOMETRY_TRIANGLE_VERTEX_INDEXES = {'offset': 0x00, 'size': 6, 'byteorder': 'little', 'name': 'nb_vertices_data', 'pretty_name': 'Mesh position'}
    SECTION_GEOMETRY_TRIANGLE_TEX_COORD_1 = {'offset': 0x06, 'size': 2, 'byteorder': 'little', 'name': 'nb_vertices_data', 'pretty_name': 'Mesh position'}
    SECTION_GEOMETRY_TRIANGLE_TEX_COORD_2 = {'offset': 0x8, 'size': 2, 'byteorder': 'little', 'name': 'nb_vertices_data', 'pretty_name': 'Mesh position'}
    SECTION_GEOMETRY_TRIANGLE_TEX_ID_1 = {'offset': 0x0A, 'size': 2, 'byteorder': 'little', 'name': 'nb_vertices_data', 'pretty_name': 'Mesh position'}
    SECTION_GEOMETRY_TRIANGLE_TEX_COORD_3 = {'offset': 0x0C, 'size': 2, 'byteorder': 'little', 'name': 'nb_vertices_data', 'pretty_name': 'Mesh position'}
    SECTION_GEOMETRY_TRIANGLE_TEX_ID_2 = {'offset': 0x0E, 'size': 2, 'byteorder': 'little', 'name': 'nb_vertices_data', 'pretty_name': 'Mesh position'}

    def __init__(self):
        self.vertex_indexes = [0]*3
        self.vta: UV = UV()
        self.vtb: UV = UV()
        self.tex_id_1 = 0
        self.vtc: UV = UV()
        self.tex_id_2 = 0
        self.depth_bias = 0  # top nibble of first index: (nibble - 8), 0 = neutral

    def analyze(self, data:bytes):
        first_index = int.from_bytes(data[0:2], byteorder=self.SECTION_GEOMETRY_TRIANGLE_VERTEX_INDEXES['byteorder'])
        self.depth_bias = (first_index >> 12) - 8
        self.vertex_indexes[0] = first_index & 0xFFF
        self.vertex_indexes[1] = int.from_bytes(data[2:4], byteorder=self.SECTION_GEOMETRY_TRIANGLE_VERTEX_INDEXES['byteorder'])& 0xFFF
        self.vertex_indexes[2] = int.from_bytes(data[4:6], byteorder=self.SECTION_GEOMETRY_TRIANGLE_VERTEX_INDEXES['byteorder'])& 0xFFF
        self.vta.analyze(data[6:8])
        self.vtb.analyze(data[8:10])
        self.tex_id_1 = int.from_bytes(data[10:12], byteorder=self.SECTION_GEOMETRY_TRIANGLE_TEX_ID_1['byteorder'])
        self.vtc.analyze(data[12:14])
        self.tex_id_2 = int.from_bytes(data[14:16], byteorder=self.SECTION_GEOMETRY_TRIANGLE_TEX_ID_2['byteorder'])
    def get_uv_str(self):
        return f"{self.vta}{self.vtb}{self.vtc}"

    def is_hidden(self):
        """Faces whose TPage word has any 0xFE00 bits set are skipped by the renderer."""
        return (self.tex_id_2 & 0xFE00) != 0

    def get_byte(self) -> bytearray:
        data = bytearray()
        first_index = (((self.depth_bias + 8) & 0xF) << 12) | (self.vertex_indexes[0] & 0xFFF)
        data.extend(first_index.to_bytes(2, 'little'))
        data.extend(self.vertex_indexes[1].to_bytes(2, 'little'))
        data.extend(self.vertex_indexes[2].to_bytes(2, 'little'))
        data.extend(self.vta.to_binary())
        data.extend(self.vtb.to_binary())
        data.extend(self.tex_id_1.to_bytes(2, 'little'))
        data.extend(self.vtc.to_binary())
        data.extend(self.tex_id_2.to_bytes(2, 'little'))
        return data  # 16 bytes
    def __str__(self):
        return f"Triangle(VertexIndex{self.vertex_indexes}, DepthBias:{self.depth_bias}, UVData:{self.vta}{self.vtb}{self.vtc}, TexId({self.tex_id_1, self.tex_id_2}))"
    def __repr__(self):
        return self.__str__()

class GeometryQuad:
    SECTION_GEOMETRY_QUAD_VERTEX_INDEXES = {'offset': 0x00, 'size': 8, 'byteorder': 'little', 'name': 'nb_vertices_data', 'pretty_name': 'Mesh position'}
    SECTION_GEOMETRY_QUAD_TEX_COORD_1 = {'offset': 0x08, 'size': 2, 'byteorder': 'little', 'name': 'nb_vertices_data', 'pretty_name': 'Mesh position'}
    SECTION_GEOMETRY_QUAD_TEX_ID_1 = {'offset': 0x0A, 'size': 2, 'byteorder': 'little', 'name': 'nb_vertices_data', 'pretty_name': 'Mesh position'}
    SECTION_GEOMETRY_QUAD_TEX_COORD_2 = {'offset': 0xC, 'size': 2, 'byteorder': 'little', 'name': 'nb_vertices_data', 'pretty_name': 'Mesh position'}
    SECTION_GEOMETRY_QUAD_TEX_ID_2 = {'offset': 0x0E, 'size': 2, 'byteorder': 'little', 'name': 'nb_vertices_data', 'pretty_name': 'Mesh position'}
    SECTION_GEOMETRY_QUAD_TEX_COORD_3 = {'offset': 0x10, 'size': 2, 'byteorder': 'little', 'name': 'nb_vertices_data', 'pretty_name': 'Mesh position'}
    SECTION_GEOMETRY_QUAD_TEX_COORD_4 = {'offset': 0x12, 'size': 2, 'byteorder': 'little', 'name': 'nb_vertices_data', 'pretty_name': 'Mesh position'}
    def __init__(self):
        self.vertex_indexes = [0]*4
        self.vta: UV = UV()
        self.tex_id_1 = 0
        self.vtb: UV = UV()
        self.tex_id_2 = 0
        self.vtc: UV = UV()
        self.vtd: UV = UV()
        self.depth_bias = 0  # top nibble of first index: (nibble - 8), 0 = neutral

    def analyze(self, data:bytes):
        first_index = int.from_bytes(data[0:2], byteorder=self.SECTION_GEOMETRY_QUAD_VERTEX_INDEXES['byteorder'])
        self.depth_bias = (first_index >> 12) - 8
        self.vertex_indexes[0] = first_index & 0xFFF
        self.vertex_indexes[1] = int.from_bytes(data[2:4], byteorder=self.SECTION_GEOMETRY_QUAD_VERTEX_INDEXES['byteorder'])& 0xFFF
        self.vertex_indexes[2] = int.from_bytes(data[4:6], byteorder=self.SECTION_GEOMETRY_QUAD_VERTEX_INDEXES['byteorder'])& 0xFFF
        self.vertex_indexes[3] = int.from_bytes(data[6:8], byteorder=self.SECTION_GEOMETRY_QUAD_VERTEX_INDEXES['byteorder'])& 0xFFF
        self.vta.analyze(data[8:10])
        self.tex_id_1 = int.from_bytes(data[10:12], byteorder=self.SECTION_GEOMETRY_QUAD_TEX_ID_1['byteorder'])
        self.vtb.analyze(data[12:14])
        self.tex_id_2 = int.from_bytes(data[14:16], byteorder=self.SECTION_GEOMETRY_QUAD_TEX_ID_2['byteorder'])
        self.vtc.analyze(data[16:18])
        self.vtd.analyze(data[18:20])

    def get_uv_str(self):
        return f"{self.vta}{self.vtb}{self.vtc}{self.vtd}"

    def is_hidden(self):
        """Faces whose TPage word has any 0xFE00 bits set are skipped by the renderer."""
        return (self.tex_id_2 & 0xFE00) != 0

    def get_byte(self) -> bytearray:
        data = bytearray()
        first_index = (((self.depth_bias + 8) & 0xF) << 12) | (self.vertex_indexes[0] & 0xFFF)
        data.extend(first_index.to_bytes(2, 'little'))
        data.extend(self.vertex_indexes[1].to_bytes(2, 'little'))
        data.extend(self.vertex_indexes[2].to_bytes(2, 'little'))
        data.extend(self.vertex_indexes[3].to_bytes(2, 'little'))
        data.extend(self.vta.to_binary())
        data.extend(self.tex_id_1.to_bytes(2, 'little'))
        data.extend(self.vtb.to_binary())
        data.extend(self.tex_id_2.to_bytes(2, 'little'))
        data.extend(self.vtc.to_binary())
        data.extend(self.vtd.to_binary())
        return data  # 20 bytes
    def __str__(self):
        return f"Quad(VertexIndex{self.vertex_indexes}, DepthBias:{self.depth_bias}, UVData{self.vta}{self.vtb}{self.vtc}{self.vtd}, TexId({self.tex_id_1, self.tex_id_2}))"
    def __repr__(self):
        return self.__str__()


class GeometryColoredTriangle(GeometryTriangle):
    """Colored triangle (20 bytes): textured triangle + raw GPU color command dword
    {red, green, blue, code}. Unused by vanilla monsters; used by battle stages and
    magic-effect models."""
    def __init__(self):
        super().__init__()
        self.color_command = 0

    def analyze(self, data:bytes):
        super().analyze(data[0:16])
        self.color_command = int.from_bytes(data[16:20], byteorder='little')

    def get_rgb_norm(self):
        return ((self.color_command & 0xFF) / 255.0,
                ((self.color_command >> 8) & 0xFF) / 255.0,
                ((self.color_command >> 16) & 0xFF) / 255.0)

    def get_byte(self) -> bytearray:
        data = super().get_byte()
        data.extend(self.color_command.to_bytes(4, 'little'))
        return data  # 20 bytes
    def __str__(self):
        return f"Colored{super().__str__()[:-1]}, Color:{self.color_command:08X})"


class GeometryColoredQuad(GeometryQuad):
    """Colored quad (24 bytes): textured quad + raw GPU color command dword
    {red, green, blue, code}. Unused by vanilla monsters; used by battle stages and
    magic-effect models."""
    def __init__(self):
        super().__init__()
        self.color_command = 0

    def analyze(self, data:bytes):
        super().analyze(data[0:20])
        self.color_command = int.from_bytes(data[20:24], byteorder='little')

    def get_rgb_norm(self):
        return ((self.color_command & 0xFF) / 255.0,
                ((self.color_command >> 8) & 0xFF) / 255.0,
                ((self.color_command >> 16) & 0xFF) / 255.0)

    def get_byte(self) -> bytearray:
        data = super().get_byte()
        data.extend(self.color_command.to_bytes(4, 'little'))
        return data  # 24 bytes
    def __str__(self):
        return f"Colored{super().__str__()[:-1]}, Color:{self.color_command:08X})"


class UV:
    def __init__(self, member_size:int=1, vram_size:bool=False):
        self._u: int=0
        self._v: int=0
        self.member_size = member_size
        self.vram_size:bool = vram_size
    def analyze(self, data:bytes):
        self._u = int.from_bytes(data[0:self.member_size], byteorder='little')
        self._v = int.from_bytes(data[self.member_size:self.member_size*2], byteorder='little')

    def get_u_norm(self):
        return (self._u & 0xFF) / 128.0
    def get_v_norm(self):
        return (self._v & 0xFF) / 128.0
    def get_u_raw(self):
        return self._u
    def get_v_raw(self):
        return self._v
    def get_u_pixel(self):
        if self.vram_size:
            return self._u * 2
        else:
            return self._u
    def get_v_pixel(self):
        return self._v

    def set_u_pixel(self, value:int):
        if self.vram_size:
            self._u = math.floor(value / 2)
        else:  # In VRAM, you have for X 2 bytes data per texel
            self._u = value
    def set_v_pixel(self, value:int):
        self._v = value
    def to_binary(self):
        data = bytearray()
        data.extend(self._u.to_bytes(length=self.member_size, byteorder="little"))
        data.extend(self._v.to_bytes(length=self.member_size, byteorder="little"))
        return data
    def __str__(self):
        return f"UV({self.get_u_raw()},{self.get_v_raw()})"
    def __repr__(self):
        return self.__str__()

class ObjectData:
    SECTION_GEOMETRY_OBJECT_DATA_NB_VERTICES_DATA = {'offset': 0x00, 'size': 2, 'byteorder': 'little', 'name': 'nb_vertices_data', 'pretty_name': 'Mesh position', 'default_value':0}
    SECTION_GEOMETRY_OBJECT_DATA_PADDING = {'offset': 0x00, 'size': 0, 'byteorder': 'little', 'name': 'object_data_padding', 'pretty_name': 'Mesh position', 'default_value':0}
    SECTION_GEOMETRY_OBJECT_DATA_NB_TRIANGLE = {'offset': 0x00, 'size': 2, 'byteorder': 'little', 'name': 'nb_triangle', 'pretty_name': 'Mesh position', 'default_value':0}
    SECTION_GEOMETRY_OBJECT_DATA_NB_QUAD = {'offset': 0x02, 'size': 2, 'byteorder': 'little', 'name': 'nb_quad', 'pretty_name': 'Mesh position', 'default_value':0}
    SECTION_GEOMETRY_OBJECT_DATA_NB_COLORED_TRIANGLE = {'offset': 0x04, 'size': 2, 'byteorder': 'little', 'name': 'nb_colored_triangle', 'pretty_name': 'Nb colored triangles', 'default_value':0}
    SECTION_GEOMETRY_OBJECT_DATA_NB_COLORED_QUAD = {'offset': 0x06, 'size': 2, 'byteorder': 'little', 'name': 'nb_colored_quad', 'pretty_name': 'Nb colored quads', 'default_value':0}
    SECTION_GEOMETRY_OBJECT_DATA_UNUSED = {'offset': 0x08, 'size': 4, 'byteorder': 'little', 'name': 'object_unused', 'pretty_name': 'Unused (skipped by the renderer)', 'default_value':0}
    SECTION_GEOMETRY_OBJECT_DATA_TRIANGLE = {'offset': 0x0, 'size': 16, 'byteorder': 'little', 'name': 'triangle', 'pretty_name': 'Mesh position', 'default_value':[]}
    SECTION_GEOMETRY_OBJECT_DATA_QUAD = {'offset': 0x0, 'size': 20, 'byteorder': 'little', 'name': 'quad', 'pretty_name': 'Mesh position', 'default_value':[]}
    SECTION_GEOMETRY_OBJECT_DATA_COLORED_TRIANGLE = {'offset': 0x0, 'size': 20, 'byteorder': 'little', 'name': 'colored_triangle', 'pretty_name': 'Colored triangle', 'default_value':[]}
    SECTION_GEOMETRY_OBJECT_DATA_COLORED_QUAD = {'offset': 0x0, 'size': 24, 'byteorder': 'little', 'name': 'colored_quad', 'pretty_name': 'Colored quad', 'default_value':[]}

    def __init__(self):
        self.nb_vertices_data = 0
        self.vertices_data:List[VerticesData]= []
        self._nb_padding = 0
        self.nb_triangle = 0
        self.nb_quad = 0
        self.nb_colored_triangle = 0
        self.nb_colored_quad = 0
        self.unused = 0
        self.triangles:List[GeometryTriangle] = []
        self.quads:List[GeometryQuad] = []
        self.colored_triangles:List[GeometryColoredTriangle] = []
        self.colored_quads:List[GeometryColoredQuad] = []

    def get_uv_str(self):
        uv_str = "Triangle:\n"
        for triangle in self.triangles:
            uv_str+= triangle.get_uv_str()
        uv_str += "\nQuad:\n"
        for quad in self.quads:
            uv_str+= quad.get_uv_str()
        return uv_str

    def get_byte(self):
        nb_vertices_data_byte = self.nb_vertices_data.to_bytes(length=self.SECTION_GEOMETRY_OBJECT_DATA_NB_VERTICES_DATA['size'], byteorder=self.SECTION_GEOMETRY_OBJECT_DATA_NB_VERTICES_DATA['byteorder'])
        vertices_data_byte = bytearray()
        for vertices_data in self.vertices_data:
            vertices_data_byte.extend(vertices_data.get_byte())
        size_section_till_now = len(nb_vertices_data_byte) + len(vertices_data_byte)
        self._nb_padding = (4 - (size_section_till_now % 4)) % 4
        nb_padding_byte = bytearray()
        for i in range(self._nb_padding):
            nb_padding_byte.extend([0])
        nb_triangle_byte = self.nb_triangle.to_bytes(length=self.SECTION_GEOMETRY_OBJECT_DATA_NB_TRIANGLE['size'], byteorder=self.SECTION_GEOMETRY_OBJECT_DATA_NB_TRIANGLE['byteorder'])
        nb_quad_byte = self.nb_quad.to_bytes(length=self.SECTION_GEOMETRY_OBJECT_DATA_NB_QUAD['size'], byteorder=self.SECTION_GEOMETRY_OBJECT_DATA_NB_QUAD['byteorder'])
        nb_colored_triangle_byte = self.nb_colored_triangle.to_bytes(length=self.SECTION_GEOMETRY_OBJECT_DATA_NB_COLORED_TRIANGLE['size'], byteorder=self.SECTION_GEOMETRY_OBJECT_DATA_NB_COLORED_TRIANGLE['byteorder'])
        nb_colored_quad_byte = self.nb_colored_quad.to_bytes(length=self.SECTION_GEOMETRY_OBJECT_DATA_NB_COLORED_QUAD['size'], byteorder=self.SECTION_GEOMETRY_OBJECT_DATA_NB_COLORED_QUAD['byteorder'])
        unused_byte = self.unused.to_bytes(length=self.SECTION_GEOMETRY_OBJECT_DATA_UNUSED['size'], byteorder=self.SECTION_GEOMETRY_OBJECT_DATA_UNUSED['byteorder'])
        triangle_byte = bytearray()
        for triangle in self.triangles:
            triangle_byte.extend(triangle.get_byte())
        quad_byte = bytearray()
        for quad in self.quads:
            quad_byte.extend(quad.get_byte())
        colored_triangle_byte = bytearray()
        for colored_triangle in self.colored_triangles:
            colored_triangle_byte.extend(colored_triangle.get_byte())
        colored_quad_byte = bytearray()
        for colored_quad in self.colored_quads:
            colored_quad_byte.extend(colored_quad.get_byte())

        return bytearray(nb_vertices_data_byte + vertices_data_byte + nb_padding_byte + nb_triangle_byte + nb_quad_byte
                         + nb_colored_triangle_byte + nb_colored_quad_byte + unused_byte
                         + triangle_byte + quad_byte + colored_triangle_byte + colored_quad_byte)
    def analyze(self, data:bytes):
        self.nb_vertices_data = int.from_bytes(data[0:2], byteorder=self.SECTION_GEOMETRY_OBJECT_DATA_NB_VERTICES_DATA['byteorder'])
        current_index = 2
        next_index = current_index + VerticesData.get_size(data[2:6])
        for i in range(self.nb_vertices_data):
            self.vertices_data.append(VerticesData())
            self.vertices_data[-1].analyze(data[current_index:next_index])
            if i < self.nb_vertices_data - 1:
                current_index = next_index
                next_index = next_index + VerticesData.get_size(data[current_index:current_index+4])
        self._nb_padding = (4 - (next_index % 4)) % 4
        next_index +=   self._nb_padding
        self.nb_triangle = int.from_bytes(data[next_index:next_index+2], byteorder=self.SECTION_GEOMETRY_OBJECT_DATA_NB_TRIANGLE['byteorder'])
        self.nb_quad = int.from_bytes(data[next_index+2:next_index+4], byteorder=self.SECTION_GEOMETRY_OBJECT_DATA_NB_QUAD['byteorder'])
        self.nb_colored_triangle = int.from_bytes(data[next_index+4:next_index+6], byteorder=self.SECTION_GEOMETRY_OBJECT_DATA_NB_COLORED_TRIANGLE['byteorder'])
        self.nb_colored_quad = int.from_bytes(data[next_index+6:next_index+8], byteorder=self.SECTION_GEOMETRY_OBJECT_DATA_NB_COLORED_QUAD['byteorder'])
        self.unused = int.from_bytes(data[next_index+8:next_index+12], byteorder=self.SECTION_GEOMETRY_OBJECT_DATA_UNUSED['byteorder'])
        current_index = next_index+12
        for i in range(self.nb_triangle):
            self.triangles.append(GeometryTriangle())
            self.triangles[-1].analyze(data[current_index: current_index + 16])
            current_index += 16
        for i in range(self.nb_quad):
            self.quads.append(GeometryQuad())
            self.quads[-1].analyze(data[current_index: current_index + 20])
            current_index += 20
        for i in range(self.nb_colored_triangle):
            self.colored_triangles.append(GeometryColoredTriangle())
            self.colored_triangles[-1].analyze(data[current_index: current_index + 20])
            current_index += 20
        for i in range(self.nb_colored_quad):
            self.colored_quads.append(GeometryColoredQuad())
            self.colored_quads[-1].analyze(data[current_index: current_index + 24])
            current_index += 24

    def __str__(self):
        return (f"ObjectData(NbVerticesData:{self.nb_vertices_data}, padding:{self._nb_padding}, NbTriangle:{self.nb_triangle}, NbQuad:{self.nb_quad}, "
                f"NbColoredTriangle:{self.nb_colored_triangle}, NbColoredQuad:{self.nb_colored_quad}, "
                f"{self.vertices_data}, {self.triangles}, {self.quads}, {self.colored_triangles}, {self.colored_quads})")
    def __repr__(self):
        return self.__str__()

    def get_triangles(self):
        triangle_list = []
        for triangle in self.triangles + self.colored_triangles:
            triangle_list.append(triangle.vertex_indexes)
        return triangle_list
    def get_quads(self):
        quad_list = []
        for quad in self.quads + self.colored_quads:
            quad_list.append(quad.vertex_indexes)
        return quad_list
    def get_vertices(self):
        vertices =  []
        for verticesData in self.vertices_data:
            for vertex in verticesData.vertices:
                vertices.append(vertex.get_list())
        return vertices

class VerticesData:
    SECTION_GEOMETRY_VERTICES_DATA_BONE_ID = {'offset': 0x00, 'size': 2, 'byteorder': 'little', 'name': 'vertices_bone_id', 'pretty_name': 'Vertices bone ID', 'default_value': 0}
    SECTION_GEOMETRY_VERTICES_DATA_NUMBER_VERTEX = {'offset': 0x02, 'size': 2, 'byteorder': 'little', 'name': 'nb_vertex', 'pretty_name': 'Number vertex', 'default_value': []}

    def __init__(self):
        self.bone_id = 0
        self.nb_vertices = 0
        self.vertices:List[Vertex]= []
    def get_byte(self):
        bone_id_byte = self.bone_id.to_bytes(2, byteorder='little')
        nb_vertices_byte = self.nb_vertices.to_bytes(2, byteorder='little')
        value_return = bytearray(bone_id_byte+nb_vertices_byte)
        for vertex in self.vertices:
            value_return.extend(vertex.get_byte())
        return value_return
    def analyze(self, data:bytes):
        self.bone_id = int.from_bytes(data[0:2], byteorder=self.SECTION_GEOMETRY_VERTICES_DATA_BONE_ID['byteorder'])
        self.nb_vertices = int.from_bytes(data[2:4], byteorder=self.SECTION_GEOMETRY_VERTICES_DATA_NUMBER_VERTEX['byteorder'])
        current_index = 4
        next_index = current_index + 6
        for i in range(self.nb_vertices):
            self.vertices.append(Vertex())
            self.vertices[-1].analyze(data[current_index:next_index])
            current_index = next_index
            next_index = next_index + 6
    def __str__(self):
        return f"VerticesData(BoneID:{self.bone_id}, NbVertices:{self.nb_vertices}, {self.vertices})"
    def __repr__(self):
        return self.__str__()
    @staticmethod
    def get_size(data:bytes):
        return int.from_bytes(data[2:4], byteorder=VerticesData.SECTION_GEOMETRY_VERTICES_DATA_NUMBER_VERTEX['byteorder'])*6+4



class Vertex:
    SECTION_GEOMETRY_VERTICES_DATA_VERTEX_X = {'offset': 0x00, 'size': 2, 'byteorder': 'little', 'name': 'vertexX', 'pretty_name': 'Vertex X', 'default_value':0}
    SECTION_GEOMETRY_VERTICES_DATA_VERTEX_Y = {'offset': 0x02, 'size': 2, 'byteorder': 'little', 'name': 'vertexY', 'pretty_name': 'Vertex Z', 'default_value':0}
    SECTION_GEOMETRY_VERTICES_DATA_VERTEX_Z = {'offset': 0x04, 'size': 2, 'byteorder': 'little', 'name': 'vertexZ', 'pretty_name': 'Vertex Y', 'default_value':0}
    SCALE = 1.0 / 2048.0
    def __init__(self):
        self._x = 0
        self._y = 0
        self._z = 0
    def get_byte(self):
        x_byte = self._x.to_bytes(length=self.SECTION_GEOMETRY_VERTICES_DATA_VERTEX_X['size'], byteorder=self.SECTION_GEOMETRY_VERTICES_DATA_VERTEX_X['byteorder'], signed=True)
        y_byte = self._y.to_bytes(length=self.SECTION_GEOMETRY_VERTICES_DATA_VERTEX_Y['size'], byteorder=self.SECTION_GEOMETRY_VERTICES_DATA_VERTEX_Y['byteorder'], signed=True)
        z_byte = self._z.to_bytes(length=self.SECTION_GEOMETRY_VERTICES_DATA_VERTEX_Z['size'], byteorder=self.SECTION_GEOMETRY_VERTICES_DATA_VERTEX_Z['byteorder'], signed=True)
        return bytearray(x_byte + z_byte + y_byte)
    def analyze(self, data:bytes):
        self._x = int.from_bytes(data[0:2], byteorder=self.SECTION_GEOMETRY_VERTICES_DATA_VERTEX_X['byteorder'], signed=True)
        self._y  = int.from_bytes(data[4:6], byteorder=self.SECTION_GEOMETRY_VERTICES_DATA_VERTEX_Y['byteorder'], signed=True)
        self._z  = int.from_bytes(data[2:4], byteorder=self.SECTION_GEOMETRY_VERTICES_DATA_VERTEX_Z['byteorder'], signed=True)

    def get_list(self):
        return -self._x*self.SCALE, self._z*self.SCALE, -self._y*self.SCALE
    def __str__(self):
        return f"Vertex{self.get_list()}"
    def __repr__(self):
        return self.__str__()


class GeometrySection:
    SECTION_GEOMETRY_HEADER_NB_OBJECT = {'offset': 0x00, 'size': 4, 'byteorder': 'little', 'name': 'nb_object', 'pretty_name': 'Nb object', 'default_value':0}
    SECTION_GEOMETRY_HEADER_OBJECT_OFFSET = {'offset': 0x02, 'size': 4, 'byteorder': 'little', 'name': 'offset', 'pretty_name': 'Mesh position', 'default_value':[]}
    SECTION_GEOMETRY_END = {'offset': 0x00, 'size': 4, 'byteorder': 'little', 'name': 'vertices_count', 'pretty_name': 'Total count of vertices', 'default_value':0}
    def __init__(self):
        self.nb_object = 0
        self.offset:List[int] = []
        self.object_data:List[ObjectData] = []
        self.end = 0

    def get_uv_str(self):
        uv_str = "ObjectData:\n"
        for object_data in self.object_data:
            uv_str += object_data.get_uv_str()
        return uv_str

    def get_byte(self):
        nb_object_byte = self.nb_object.to_bytes(length=self.SECTION_GEOMETRY_HEADER_NB_OBJECT['size'], byteorder=self.SECTION_GEOMETRY_HEADER_NB_OBJECT['byteorder'])
        nb_offset_byte = bytearray()
        for offset in self.offset:
            nb_offset_byte.extend(offset.to_bytes(length=self.SECTION_GEOMETRY_HEADER_OBJECT_OFFSET['size'], byteorder=self.SECTION_GEOMETRY_HEADER_OBJECT_OFFSET['byteorder']))
        object_data_byte = bytearray()
        for object_data in self.object_data:
            object_data_byte.extend(object_data.get_byte())
        end_byte = self.end.to_bytes(length=self.SECTION_GEOMETRY_END['size'], byteorder=self.SECTION_GEOMETRY_END['byteorder'])

        return bytearray(nb_object_byte+nb_offset_byte+object_data_byte+end_byte)

    def analyze(self, data:bytes):
        current_index = 0
        next_index = self.SECTION_GEOMETRY_HEADER_NB_OBJECT['size']
        self.nb_object = int.from_bytes(data[current_index:next_index], byteorder=self.SECTION_GEOMETRY_HEADER_NB_OBJECT['byteorder'])
        current_index = next_index
        next_index = current_index + self.SECTION_GEOMETRY_HEADER_OBJECT_OFFSET['size']
        for i in range(self.nb_object):
            self.offset.append(int.from_bytes(data[current_index:next_index], byteorder=self.SECTION_GEOMETRY_HEADER_OBJECT_OFFSET['byteorder']))
            current_index = next_index
            next_index = current_index + self.SECTION_GEOMETRY_HEADER_OBJECT_OFFSET['size']
        for i in range(self.nb_object):
            current_index = self.offset[i]
            if i == self.nb_object - 1:
                next_index = len(data)-4
            else:
                next_index = self.offset[i+1]
            self.object_data.append(ObjectData())
            self.object_data[-1].analyze(data[current_index: next_index])
        self.end = int.from_bytes(data[-4:], byteorder=self.SECTION_GEOMETRY_END['byteorder'])

    def __str__(self):
        return f"Nb object:{self.nb_object}, offset:{self.offset}, {self.object_data}, end: {self.end}"
    def __repr__(self):
        return self.__str__()
    def get_vertices(self):
        vertices_list = []
        for object in self.object_data:
            vertices_list.extend(object.get_vertices())
        return vertices_list

    def get_triangles(self, include_hidden=False):
        all_tri = []
        offset = 0
        for obj in self.object_data:
            obj_vert_count = sum(vd.nb_vertices for vd in obj.vertices_data)
            for tri in obj.triangles + obj.colored_triangles:
                if tri.is_hidden() and not include_hidden:
                    continue
                all_tri.append((
                    tri.vertex_indexes[0] + offset,
                    tri.vertex_indexes[1] + offset,
                    tri.vertex_indexes[2] + offset
                ))
            offset += obj_vert_count
        return all_tri
    def get_quads(self, include_hidden=False):
        all_quads = []
        offset = 0
        for obj in self.object_data:
            obj_vert_count = sum(vd.nb_vertices for vd in obj.vertices_data)
            for quad in obj.quads + obj.colored_quads:
                if quad.is_hidden() and not include_hidden:
                    continue
                all_quads.append((
                    quad.vertex_indexes[0] + offset,
                    quad.vertex_indexes[1] + offset,
                    quad.vertex_indexes[2] + offset,
                    quad.vertex_indexes[3] + offset
                ))
            offset += obj_vert_count
        return all_quads

    def get_triangles_with_uv(self, include_hidden=False):
        """Returns list of (vertex_indices_tuple, uvs_tuple, tex_id, depth_bias) for every triangle.
        include_hidden also returns faces whose TPage word sets the 0xFE00 "hide" bits (a real
        engine mechanic the runtime renderer itself skips - see GeometryTriangle.is_hidden)."""
        result = []
        offset = 0
        for obj in self.object_data:
            obj_vert_count = sum(vd.nb_vertices for vd in obj.vertices_data)
            for tri in obj.triangles:
                if tri.is_hidden() and not include_hidden:
                    continue
                indices = (
                    tri.vertex_indexes[2] + offset,  # C
                    tri.vertex_indexes[0] + offset,  # A
                    tri.vertex_indexes[1] + offset,  # B
                )
                uvs = (
                    (tri.vta.get_u_norm(), tri.vta.get_v_norm()),  # for C
                    (tri.vtb.get_u_norm(), tri.vtb.get_v_norm()),  # for A
                    (tri.vtc.get_u_norm(), tri.vtc.get_v_norm()),  # for B
                )
                # tex_id_1 upper 6 bits encode CLUT/page info; low bits = texture index
                tex_id = tri.tex_id_1 & 0xFF
                result.append((indices, uvs, tex_id, tri.depth_bias))
            offset += obj_vert_count
        return result

    def get_quads_with_uv(self, include_hidden=False):
        """Returns list of (vertex_indices_tuple, uvs_tuple, tex_id, depth_bias) for every quad."""
        result = []
        offset = 0
        for obj in self.object_data:
            obj_vert_count = sum(vd.nb_vertices for vd in obj.vertices_data)
            for quad in obj.quads:
                if quad.is_hidden() and not include_hidden:
                    continue
                indices = (
                    quad.vertex_indexes[0] + offset,  # A
                    quad.vertex_indexes[1] + offset,  # B
                    quad.vertex_indexes[2] + offset,  # C
                    quad.vertex_indexes[3] + offset,  # D
                )
                uvs = (
                    (quad.vta.get_u_norm(), quad.vta.get_v_norm()),
                    (quad.vtb.get_u_norm(), quad.vtb.get_v_norm()),
                    (quad.vtc.get_u_norm(), quad.vtc.get_v_norm()),
                    (quad.vtd.get_u_norm(), quad.vtd.get_v_norm()),
                )
                tex_id = quad.tex_id_1 & 0xFF
                result.append((indices, uvs, tex_id, quad.depth_bias))
            offset += obj_vert_count
        return result

    def get_triangles_hidden_mask(self, include_hidden=False):
        """Bool per entry, aligned 1:1 with get_triangles_with_uv(include_hidden): True where the
        face is hidden (TPage 0xFE00, never drawn by the engine). Lets a caller count only the
        drawn faces for the packet-buffer budget independently of whether the viewer is currently
        displaying hidden faces."""
        return [tri.is_hidden() for obj in self.object_data for tri in obj.triangles
                if include_hidden or not tri.is_hidden()]

    def get_quads_hidden_mask(self, include_hidden=False):
        """Bool per entry, aligned 1:1 with get_quads_with_uv(include_hidden). See
        get_triangles_hidden_mask."""
        return [quad.is_hidden() for obj in self.object_data for quad in obj.quads
                if include_hidden or not quad.is_hidden()]

    def get_colored_triangles_with_color(self, include_hidden=False):
        """Returns list of (vertex_indices_tuple, rgb_norm_tuple, depth_bias) for every colored triangle."""
        result = []
        offset = 0
        for obj in self.object_data:
            obj_vert_count = sum(vd.nb_vertices for vd in obj.vertices_data)
            for tri in obj.colored_triangles:
                if tri.is_hidden() and not include_hidden:
                    continue
                indices = (
                    tri.vertex_indexes[0] + offset,
                    tri.vertex_indexes[1] + offset,
                    tri.vertex_indexes[2] + offset,
                )
                result.append((indices, tri.get_rgb_norm(), tri.depth_bias))
            offset += obj_vert_count
        return result

    def get_colored_quads_with_color(self, include_hidden=False):
        """Returns list of (vertex_indices_tuple, rgb_norm_tuple, depth_bias) for every colored quad."""
        result = []
        offset = 0
        for obj in self.object_data:
            obj_vert_count = sum(vd.nb_vertices for vd in obj.vertices_data)
            for quad in obj.colored_quads:
                if quad.is_hidden() and not include_hidden:
                    continue
                indices = (
                    quad.vertex_indexes[0] + offset,
                    quad.vertex_indexes[1] + offset,
                    quad.vertex_indexes[2] + offset,
                    quad.vertex_indexes[3] + offset,
                )
                result.append((indices, quad.get_rgb_norm(), quad.depth_bias))
            offset += obj_vert_count
        return result

# Section 3 data:
class BitWriter:
    """Helper class to write bit-packed data - LSB first order"""

    def __init__(self):
        self._data = bytearray()
        self._buffer = 0
        self._bits_in_buffer = 0

    def write_bits(self, value: int, count: int):
        """Write 'count' bits of value (supports up to 16 bits)"""
        if count <= 0:
            return
        if count > 16:
            raise ValueError("count must be <= 16")

        # Mask to required bits
        value &= (1 << count) - 1

        # Add bits to buffer (LSB first)
        self._buffer |= (value << self._bits_in_buffer)
        self._bits_in_buffer += count

        # Write full bytes
        while self._bits_in_buffer >= 8:
            self._data.append(self._buffer & 0xFF)
            self._buffer >>= 8
            self._bits_in_buffer -= 8

    def write_bit(self, value: bool):
        self.write_bits(1 if value else 0, 1)

    def flush(self):
        if self._bits_in_buffer > 0:
            self._data.append(self._buffer & 0xFF)
            self._buffer = 0
            self._bits_in_buffer = 0

    def get_data(self, flush=True) -> bytearray:
        if flush:
            self.flush()
        return self._data

    def align_to_byte(self):
        """Pad the current bits to reach a byte boundary"""
        if self._bits_in_buffer > 0:
            # Pad with zeros to reach byte boundary
            remaining = 8 - self._bits_in_buffer
            self.write_bits(0, remaining)

    def write_byte(self, value: int):
        """Write a full byte, aligned to byte boundary"""
        self.write_bits(value & 0xFF, 8)
    def get_size_including_buffer(self) -> int:
        """Get the total size in bytes including pending bits in buffer"""
        return len(self._data) + (1 if self._bits_in_buffer > 0 else 0)
class  BitReader:
    """
    Port of ExtapathyExtended.BitReader.
    Reads from a bytes buffer with a sub-byte bit cursor.
    ReadBits(n) reads n bits, sign-extends to short (16-bit signed).
    """
    POSITION_READ_HELPER = [3, 6, 9, 16]
    ROTATION_READ_HELPER = [3, 6, 8, 12]

    def __init__(self, data: bytes, start_byte: int = 0):
        self._data = data
        self._byte_pos = start_byte
        self._bit_pos = 0  # sub-byte bit offset (0–7)

    def read_bit(self) -> bool:
        return (self.read_bits(1) & 1) != 0

    def read_bits(self, count: int) -> int:
        if count > 16:
            raise ValueError("count must be <= 16")

        pos = self._byte_pos
        b0 = self._data[pos] if pos < len(self._data) else 0
        b1 = self._data[pos + 1] if pos + 1 < len(self._data) else 0
        b2 = self._data[pos + 2] if pos + 2 < len(self._data) else 0

        temp = b0 | (b1 << 8) | (b2 << 16)

        # Shift to align the bits
        temp = (temp >> self._bit_pos) & ((1 << count) - 1)

        # Sign-extend for signed values (always treat as signed 16-bit)
        if count <= 16:
            # Check if the highest bit is set
            if temp & (1 << (count - 1)):
                temp -= (1 << count)

        # Advance stream
        self._byte_pos = pos + (count + self._bit_pos) // 8
        self._bit_pos = (count + self._bit_pos) % 8

        return temp

    def read_position_type(self) -> Tuple[int, int]:
        """2-bit index → lookup in [3,6,9,16] → read that many bits signed."""
        count_index = self.read_bits(2) & 3
        return count_index, self.read_bits(self.POSITION_READ_HELPER[count_index])

    def read_rotation_type(self) -> Tuple[bool, int, int]:
        """
        1-bit flag: if 0 → return 0 (no rotation).
        If 1 → 2-bit index → lookup in [3,6,8,12] → read that many bits signed.
        """
        should_read = (self.read_bits(1) & 1) != 0
        count_index = 0
        if not should_read:
            vector_axis = 0
        else:
            count_index = self.read_bits(2) & 3
            vector_axis = self.read_bits(self.ROTATION_READ_HELPER[count_index])
        return should_read, count_index, vector_axis


class Matrix4x4:
    """Direct port of XNA Matrix (4x4 row-major, translation in row 3)"""

    def __init__(self):
        # Identity matrix
        self.M11 = 1.0
        self.M12 = 0.0
        self.M13 = 0.0
        self.M14 = 0.0
        self.M21 = 0.0
        self.M22 = 1.0
        self.M23 = 0.0
        self.M24 = 0.0
        self.M31 = 0.0
        self.M32 = 0.0
        self.M33 = 1.0
        self.M34 = 0.0
        self.M41 = 0.0
        self.M42 = 0.0
        self.M43 = 0.0
        self.M44 = 1.0

    @staticmethod
    def CreateRotationX(angle_deg):
        """Matches MakiExtended.GetRotationMatrixX"""
        r = math.radians(angle_deg)
        c = math.cos(r)
        s = math.sin(r)
        mat = Matrix4x4()
        mat.M22 = c
        mat.M23 = -s
        mat.M32 = s
        mat.M33 = c
        return mat

    @staticmethod
    def CreateRotationY(angle_deg):
        """Matches MakiExtended.GetRotationMatrixY"""
        r = math.radians(angle_deg)
        c = math.cos(r)
        s = math.sin(r)
        mat = Matrix4x4()
        mat.M11 = c
        mat.M13 = s
        mat.M31 = -s
        mat.M33 = c
        return mat

    @staticmethod
    def CreateRotationZ(angle_deg):
        """Matches MakiExtended.GetRotationMatrixZ"""
        r = math.radians(angle_deg)
        c = math.cos(r)
        s = math.sin(r)
        mat = Matrix4x4()
        mat.M11 = c
        mat.M12 = -s
        mat.M21 = s
        mat.M22 = c
        return mat
    @staticmethod
    def MultiplyColumnMajor(a, b):
        """
        Column-major multiplication: result = b * a.
        Mimics MakiExtended.MatrixMultiply in C#.
        """
        result = Matrix4x4()
        result.M11 = b.M11 * a.M11 + b.M21 * a.M12 + b.M31 * a.M13
        result.M12 = b.M11 * a.M21 + b.M21 * a.M22 + b.M31 * a.M23
        result.M13 = b.M11 * a.M31 + b.M21 * a.M32 + b.M31 * a.M33
        result.M14 = 0

        result.M21 = b.M12 * a.M11 + b.M22 * a.M12 + b.M32 * a.M13
        result.M22 = b.M12 * a.M21 + b.M22 * a.M22 + b.M32 * a.M23
        result.M23 = b.M12 * a.M31 + b.M22 * a.M32 + b.M32 * a.M33
        result.M24 = 0

        result.M31 = b.M13 * a.M11 + b.M23 * a.M12 + b.M33 * a.M13
        result.M32 = b.M13 * a.M21 + b.M23 * a.M22 + b.M33 * a.M23
        result.M33 = b.M13 * a.M31 + b.M23 * a.M32 + b.M33 * a.M33
        result.M34 = 0

        result.M41 = 0
        result.M42 = 0
        result.M43 = 0
        result.M44 = 0
        return result

    @staticmethod
    def MultiplyRowMajor(a, b):
        """
        Row-major multiplication: result = a * b.
        Mimics XNA Matrix.Multiply.
        """
        result = Matrix4x4()
        result.M11 = a.M11*b.M11 + a.M12*b.M21 + a.M13*b.M31 + a.M14*b.M41
        result.M12 = a.M11*b.M12 + a.M12*b.M22 + a.M13*b.M32 + a.M14*b.M42
        result.M13 = a.M11*b.M13 + a.M12*b.M23 + a.M13*b.M33 + a.M14*b.M43
        result.M14 = a.M11*b.M14 + a.M12*b.M24 + a.M13*b.M34 + a.M14*b.M44

        result.M21 = a.M21*b.M11 + a.M22*b.M21 + a.M23*b.M31 + a.M24*b.M41
        result.M22 = a.M21*b.M12 + a.M22*b.M22 + a.M23*b.M32 + a.M24*b.M42
        result.M23 = a.M21*b.M13 + a.M22*b.M23 + a.M23*b.M33 + a.M24*b.M43
        result.M24 = a.M21*b.M14 + a.M22*b.M24 + a.M23*b.M34 + a.M24*b.M44

        result.M31 = a.M31*b.M11 + a.M32*b.M21 + a.M33*b.M31 + a.M34*b.M41
        result.M32 = a.M31*b.M12 + a.M32*b.M22 + a.M33*b.M32 + a.M34*b.M42
        result.M33 = a.M31*b.M13 + a.M32*b.M23 + a.M33*b.M33 + a.M34*b.M43
        result.M34 = a.M31*b.M14 + a.M32*b.M24 + a.M33*b.M34 + a.M34*b.M44

        result.M41 = a.M41*b.M11 + a.M42*b.M21 + a.M43*b.M31 + a.M44*b.M41
        result.M42 = a.M41*b.M12 + a.M42*b.M22 + a.M43*b.M32 + a.M44*b.M42
        result.M43 = a.M41*b.M13 + a.M42*b.M23 + a.M43*b.M33 + a.M44*b.M43
        result.M44 = a.M41*b.M14 + a.M42*b.M24 + a.M43*b.M34 + a.M44*b.M44
        return result

class Vector3D:
    def __init__(self, x: float = 0, y: float = 0, z: float = 0):
        self.x = x
        self.y = y
        self.z = z

class RotationType:
    def __init__(self, is_rotation_type_available:bool = False, rotation_type_bits:int = 0, vector_axis: int = 0):
        self.is_rotation_type_available:bool = is_rotation_type_available
        self.rotation_type_bits:int = rotation_type_bits
        self._vector_axis: int = vector_axis
        self._vector_axis_deg: float = 0
        self.rotate_raw(self._vector_axis)
    def rotate_deg(self, deg):
        self._vector_axis_deg = deg
        self._vector_axis = round(deg * 4096.0 / 360.0)
    def rotate_raw(self, raw):
        self._vector_axis = raw
        self._vector_axis_deg = raw * 360.0 / 4096.0
    def get_rotate_deg(self):
        return self._vector_axis_deg
    def get_rotate_raw(self):
        return self._vector_axis

    def __str__(self):
        return f"RotType(Available:{self.is_rotation_type_available}, Bits:{self.rotation_type_bits}, Value:{self._vector_axis})"
    def __repr__(self):
        return self.__str__()

class RotationVectorDataSupp:
    """Per-bone scale channels (squash-and-stretch), one per axis (X, Y, Z).

    Engine semantics (FF8_EN.exe Battle__ReadBoneScale): each channel is 1 flag bit;
    when the flag is clear the scale is exactly 1024 raw (= 1.0, neutral), when set a
    16-bit signed payload follows and the raw scale is payload + 1024.
    Scales are ABSOLUTE per frame (not accumulated like rotations) and hierarchical
    at transform time (child effective scale = parent scale * value / 1024).
    Only consumed on frames whose mode bit is 1.
    unk1/unk2/unk3 keep the historical names for the bitstream writer: they store the
    raw 16-bit payloads for the X, Y and Z channels respectively."""
    SCALE_NEUTRAL_RAW = 1024

    def __init__(self):
        self.unk1: int = 0
        self.unk2: int = 0
        self.unk3: int = 0
        self.unk_flag1: bool = False
        self.unk_flag2: bool = False
        self.unk_flag3: bool = False

    def get_scale_raw(self, axis: int) -> int:
        """Raw scale of axis 0/1/2 (X/Y/Z); 1024 = 1.0 neutral."""
        flag = (self.unk_flag1, self.unk_flag2, self.unk_flag3)[axis]
        if not flag:
            return self.SCALE_NEUTRAL_RAW
        payload = (self.unk1, self.unk2, self.unk3)[axis]
        return payload + self.SCALE_NEUTRAL_RAW

    def get_scale_factor(self, axis: int) -> float:
        """Scale of axis 0/1/2 (X/Y/Z) as a float factor, 1.0 = neutral."""
        return self.get_scale_raw(axis) / self.SCALE_NEUTRAL_RAW

    def get_scale_factors(self):
        return (self.get_scale_factor(0), self.get_scale_factor(1), self.get_scale_factor(2))

    def set_scale_raw(self, axis: int, raw: int):
        payload = raw - self.SCALE_NEUTRAL_RAW
        if payload == 0:
            # Neutral scale is stored as "no payload" (single 0 bit), like vanilla data
            payload = 0
            flag = False
        else:
            flag = True
        if axis == 0:
            self.unk1, self.unk_flag1 = payload, flag
        elif axis == 1:
            self.unk2, self.unk_flag2 = payload, flag
        else:
            self.unk3, self.unk_flag3 = payload, flag

    def set_scale_factor(self, axis: int, factor: float):
        self.set_scale_raw(axis, round(factor * self.SCALE_NEUTRAL_RAW))

    def is_neutral(self) -> bool:
        return not (self.unk_flag1 or self.unk_flag2 or self.unk_flag3)


class PositionType:
    SCALE = -1.0 /204.8  # Negative scale to match vertex coordinate system


    def __init__(self, position_type_bits: int = 0, vector_axis: int = 0, bone_scale:float= 20480):
        self.position_type_bits: int = position_type_bits
        self._vector_axis: int = vector_axis
        self.scale:float = self.SCALE
        #self.scale:float = bone_scale

    def get_pos_raw(self):
        return self._vector_axis

    def get_pos_world(self):
        """Return scaled world position to match vertex coordinate system"""
        return self._vector_axis * self.scale

    def move_world(self, move_value: float):
        self._vector_axis += round(move_value / self.scale)

    def move_raw(self, move_value: int):
        self._vector_axis += move_value

    def set_pos_raw(self, pos_raw: int):
        self._vector_axis = pos_raw

    def set_pos_world(self, pos_world: float):
        self._vector_axis = round(pos_world / self.scale)

    def __str__(self):
        return f"typeBit: {self.position_type_bits}, Val:{self.get_pos_world()}"

    def __repr__(self):
        return f"PositionType({self.__str__()})"

class AnimationFrame:
    def __init__(self, nb_bones: int):
        self.position: List[PositionType] = []
        self.rotation_vector_data: List[List[RotationType]] =  [[] for _ in range(nb_bones)]
        #self.bone_rot_raw: List[Vector3D] = [Vector3D() for _ in range(nb_bones)]
        #self.bone_rot_deg: List[Tuple[float, float, float]] = [(0.0, 0.0, 0.0) for _ in range(nb_bones)]
        # bone_matrices / bone_chain_matrices / bone_acc_scale are DERIVED render data
        # (recomputable from the rotations via set_all_bones_matrix). They are ~60% of a
        # monster's animation RAM, so a parsed file that isn't being shown in 3D drops them
        # (AnimationSection.free_bone_matrices) and rebuilds on demand. _reset_matrix_lists
        # re-allocates them; free_matrices() drops them to None.
        self._reset_matrix_lists(nb_bones)
        self.rotation_vector_data_supp: List[RotationVectorDataSupp] = [RotationVectorDataSupp() for _ in range(nb_bones)]
        self.mode_bit:int = 0

    def _reset_matrix_lists(self, nb_bones: int):
        self.bone_matrices: List[Matrix4x4] = [Matrix4x4() for _ in range(nb_bones)]  # identity (scaled, used for skinning)
        # Unscaled rotation chain (parent * local), kept separate so a parent's
        # non-uniform scale doesn't contaminate the children's rotations —
        # mirrors the engine, which chains rotations and applies the
        # accumulated scale only on the stored per-bone matrix.
        self.bone_chain_matrices: List[Matrix4x4] = [Matrix4x4() for _ in range(nb_bones)]
        # Accumulated per-axis scale down the hierarchy (1.0 = neutral)
        self.bone_acc_scale: List[Tuple[float, float, float]] = [(1.0, 1.0, 1.0) for _ in range(nb_bones)]

    def free_matrices(self):
        """Drop this frame's derived render matrices (recomputable from the rotations)."""
        self.bone_matrices = None
        self.bone_chain_matrices = None
        self.bone_acc_scale = None

    def get_bone_scale_factors(self, bone_id: int) -> Tuple[float, float, float]:
        """Per-bone scale of this frame (1.0 neutral). Only meaningful when mode_bit is 1."""
        if self.mode_bit == 1 and bone_id < len(self.rotation_vector_data_supp):
            return self.rotation_vector_data_supp[bone_id].get_scale_factors()
        return (1.0, 1.0, 1.0)


    def __str__(self):
        return f"AnimationFrame(pos:{self.position}, bones_rot:{self.rotation_vector_data}, mode:{self.mode_bit})"

    def __repr__(self):
        return self.__str__()

    def write_to_writer(self, writer: BitWriter, prev_frame: 'AnimationFrame' = None):
        """Write frame data to an existing BitWriter (no flushing)"""
        # Positions
        for axis in range(3):
            if prev_frame is None:
                raw_value = self.position[axis].get_pos_raw()
            else:
                raw_value = self.position[axis].get_pos_raw() - prev_frame.position[axis].get_pos_raw()

            raw_value = raw_value & 0xFFFF
            ti = self.position[axis].position_type_bits
            n = BitReader.POSITION_READ_HELPER[ti]
            writer.write_bits(ti, 2)
            writer.write_bits(raw_value & ((1 << n) - 1), n)

        writer.write_bit(self.mode_bit == 1)

        # Rotations
        for bone_idx in range(len(self.rotation_vector_data)):
            for axis in range(3):
                rot = self.rotation_vector_data[bone_idx][axis]

                if prev_frame and bone_idx < len(prev_frame.rotation_vector_data):
                    prev_raw = int(prev_frame.rotation_vector_data[bone_idx][axis].get_rotate_raw())
                else:
                    prev_raw = 0

                current_raw = int(rot.get_rotate_raw())
                delta = current_raw - prev_raw

                avail = rot.is_rotation_type_available
                writer.write_bit(avail)
                if avail:
                    ti = rot.rotation_type_bits
                    n = BitReader.ROTATION_READ_HELPER[ti]
                    writer.write_bits(ti, 2)
                    v = delta if delta >= 0 else (1 << n) + delta
                    writer.write_bits(v & ((1 << n) - 1), n)

            # Supplementary data
            if self.mode_bit == 1 and bone_idx < len(self.rotation_vector_data_supp):
                supp = self.rotation_vector_data_supp[bone_idx]
                writer.write_bit(supp.unk_flag1)
                if supp.unk_flag1:
                    writer.write_bits(supp.unk1 & 0xFFFF, 16)
                writer.write_bit(supp.unk_flag2)
                if supp.unk_flag2:
                    writer.write_bits(supp.unk2 & 0xFFFF, 16)
                writer.write_bit(supp.unk_flag3)
                if supp.unk_flag3:
                    writer.write_bits(supp.unk3 & 0xFFFF, 16)

    def rotate_bone_deg(self, deg:Vector3D, bone_id:int):
        if bone_id > len(self.rotation_vector_data):
            print(f"Bone id for rotation too high. BoneID:{bone_id}, max:{len(self.rotation_vector_data)}")
        self.rotation_vector_data[bone_id][0].rotate_deg(deg.x)
        self.rotation_vector_data[bone_id][1].rotate_deg(deg.y)
        self.rotation_vector_data[bone_id][2].rotate_deg(deg.z)

    def rotate_bone_raw(self, raw:Vector3D, bone_id:int):
        if bone_id > len(self.rotation_vector_data):
            print(f"Bone id for rotation too high. BoneID:{bone_id}, max:{len(self.rotation_vector_data)}")
        self.rotation_vector_data[bone_id][0].rotate_raw(raw.x)
        self.rotation_vector_data[bone_id][1].rotate_raw(raw.y)
        self.rotation_vector_data[bone_id][2].rotate_raw(raw.z)

    def set_bone_matrix(self, parent_id:int, parent_bone_size: float, bone_id:int):
        xRot = Matrix4x4.CreateRotationX(-self.rotation_vector_data[bone_id][0].get_rotate_deg())
        yRot = Matrix4x4.CreateRotationY(-self.rotation_vector_data[bone_id][1].get_rotate_deg())
        zRot = Matrix4x4.CreateRotationZ(-self.rotation_vector_data[bone_id][2].get_rotate_deg())

        # Combine in the same order as C#: Y*X then Z*(Y*X)
        local = Matrix4x4.MultiplyColumnMajor(yRot, xRot)
        local = Matrix4x4.MultiplyColumnMajor(zRot, local)

        # Per-bone squash-and-stretch scale (mode-bit frames only), hierarchical:
        # accumulated scale = parent accumulated scale * this bone's scale
        bone_scale = self.get_bone_scale_factors(bone_id)

        if parent_id != 0xFFFF:
            # Rotation chain stays unscaled (like the engine's chained matrices)
            chain = Matrix4x4.MultiplyRowMajor(self.bone_chain_matrices[parent_id], local)

            parent_acc = self.bone_acc_scale[parent_id]
            acc = (parent_acc[0] * bone_scale[0],
                   parent_acc[1] * bone_scale[1],
                   parent_acc[2] * bone_scale[2])

            # Translation: parent_pos + parent SCALED matrix * (0,0,parent_length)
            # (using the scaled parent shortens/stretches the limb with the parent's scale,
            #  exactly like the engine)
            parent_mat = self.bone_matrices[parent_id]
            trans_x = parent_mat.M13 * parent_bone_size + parent_mat.M41
            trans_y = parent_mat.M23 * parent_bone_size + parent_mat.M42
            trans_z = parent_mat.M33 * parent_bone_size + parent_mat.M43
        else:
            chain = local
            acc = bone_scale
            trans_x = trans_y = trans_z = 0.0

        self.bone_chain_matrices[bone_id] = chain
        self.bone_acc_scale[bone_id] = acc

        # Stored (skinning) matrix = chain with each local axis column scaled
        world = Matrix4x4()
        world.M11, world.M21, world.M31 = chain.M11 * acc[0], chain.M21 * acc[0], chain.M31 * acc[0]
        world.M12, world.M22, world.M32 = chain.M12 * acc[1], chain.M22 * acc[1], chain.M32 * acc[1]
        world.M13, world.M23, world.M33 = chain.M13 * acc[2], chain.M23 * acc[2], chain.M33 * acc[2]
        world.M41 = trans_x
        world.M42 = trans_y
        world.M43 = trans_z
        self.bone_matrices[bone_id] = world

    def set_all_bones_matrix(self, bones:List[Bone]):
        for bone_index in range(len(self.bone_matrices)):
            parent_id = bones[bone_index].parent_id
            if parent_id != 0xFFFF:
                bone_parent_size = bones[parent_id].get_size()
            else:
                bone_parent_size = None
            self.set_bone_matrix(parent_id, bone_parent_size, bone_index)

    def analyze_pos(self, br: BitReader, prev_frame: 'AnimationFrame', bone_section:BoneSection):
        self.position = []

        # Read position deltas
        px_bits, px_val = br.read_position_type()
        py_bits, py_val = br.read_position_type()
        pz_bits, pz_val = br.read_position_type()

        # Accumulate if there's a previous frame
        if prev_frame and prev_frame.position:
            px_val += prev_frame.position[0].get_pos_raw()
            py_val += prev_frame.position[1].get_pos_raw()
            pz_val += prev_frame.position[2].get_pos_raw()

        self.position = [
            PositionType(px_bits, px_val, bone_section.get_scale_list()[0]),
            PositionType(py_bits, py_val, bone_section.get_scale_list()[1]),
            PositionType(pz_bits, pz_val, bone_section.get_scale_list()[2])
        ]

    def rotate_all_bones(self, br: BitReader, prev_frame: 'AnimationFrame', bones: List[Bone]):
        self.mode_bit = br.read_bit()

        for bone_index in range(len(bones)):
            # Read rotation deltas
            rx_available, rx_bits, rx_val = br.read_rotation_type()
            ry_available, ry_bits, ry_val = br.read_rotation_type()
            rz_available, rz_bits, rz_val = br.read_rotation_type()

            # Get previous frame values
            if prev_frame and prev_frame.rotation_vector_data:
                prev_rx = prev_frame.rotation_vector_data[bone_index][0].get_rotate_raw()
                prev_ry = prev_frame.rotation_vector_data[bone_index][1].get_rotate_raw()
                prev_rz = prev_frame.rotation_vector_data[bone_index][2].get_rotate_raw()
            else:
                prev_rx = prev_ry = prev_rz = 0

            # Accumulate deltas (only add if rotation data was present)
            final_rx = prev_rx + (rx_val if rx_available else 0)
            final_ry = prev_ry + (ry_val if ry_available else 0)
            final_rz = prev_rz + (rz_val if rz_available else 0)

            # Store rotation data
            self.rotation_vector_data[bone_index] = [
                RotationType(rx_available, rx_bits, final_rx),
                RotationType(ry_available, ry_bits, final_ry),
                RotationType(rz_available, rz_bits, final_rz)
            ]

            if self.mode_bit == 1:
                if bone_index >= len(self.rotation_vector_data_supp):
                    self.rotation_vector_data_supp.extend([RotationVectorDataSupp() for _ in range(bone_index - len(self.rotation_vector_data_supp) + 1)])

                self.rotation_vector_data_supp[bone_index].unk_flag1 = br.read_bit()
                if self.rotation_vector_data_supp[bone_index].unk_flag1:
                    self.rotation_vector_data_supp[bone_index].unk1 = br.read_bits(16)

                self.rotation_vector_data_supp[bone_index].unk_flag2 = br.read_bit()
                if self.rotation_vector_data_supp[bone_index].unk_flag2:
                    self.rotation_vector_data_supp[bone_index].unk2 = br.read_bits(16)

                self.rotation_vector_data_supp[bone_index].unk_flag3 = br.read_bit()
                if self.rotation_vector_data_supp[bone_index].unk_flag3:
                    self.rotation_vector_data_supp[bone_index].unk3 = br.read_bits(16)

class Animation:
    def __init__(self):
        self.frames: List[AnimationFrame] = []
        # Original bytes between the end of the bit-stream and the next
        # animation offset (or the section end for the last animation).
        self.original_tail: bytes = b""

    def __str__(self):
        return f"Animation(nb_frames:{len(self.frames)}, {self.frames})"

    def __repr__(self):
        return self.__str__()

    def write_to_writer(self, writer: BitWriter):
        """Write animation to an existing BitWriter without flushing"""
        # Write frame count as bits (8 bits) at current position
        writer.write_bits(len(self.frames), 8)

        prev_frame = None
        for frame in self.frames:
            frame.write_to_writer(writer, prev_frame)
            prev_frame = frame

    def add_frame(self, br: BitReader, bone_section: BoneSection):
        bones = bone_section.bones
        frame = AnimationFrame(len(bones))

        if len(self.frames) != 0:
            prev_frame = self.frames[-1]
        else:
            prev_frame = None

        frame.analyze_pos(br, prev_frame, bone_section)
        frame.rotate_all_bones(br, prev_frame, bones)
        frame.set_all_bones_matrix(bones)

        self.frames.append(frame)

    def get_nb_frame(self):
        return len(self.frames)

    def create_interpolated_frames(self, bones: List[Bone], factor: int = 4, smooth_loop: bool = False,
                                   wrap_frame: 'AnimationFrame' = None):
        """
        Insert (factor - 1) interpolated frames between each pair of consecutive frames.
        With factor = 4, an animation made for 15 fps becomes a 60 fps animation.
        If smooth_loop is True, frames are also inserted between the last and the first
        frame (nice for looping animations like the idle stance, wrong for one-shot
        animations like a death animation).
        wrap_frame is the frame the loop goes back to, when it is not this animation's own
        first frame: a looping animation split in several parts wraps back to the first
        frame of its FIRST part (see FF8GameData/dat/animsplitter.py).
        """
        if len(self.frames) < 2:
            return

        new_frames = []
        for frame_index, frame in enumerate(self.frames):
            new_frames.append(frame)

            is_last_frame = (frame_index == len(self.frames) - 1)
            if is_last_frame and not smooth_loop:
                continue

            if is_last_frame:
                next_frame = wrap_frame if wrap_frame is not None else self.frames[0]
            else:
                next_frame = self.frames[frame_index + 1]
            for step_index in range(1, factor):
                step = step_index / factor
                new_frames.append(self._create_frame_between(frame, next_frame, step, bones))

        self.frames = new_frames
        self._recompute_frame_storage_types()
        # The bit-stream is fully re-encoded: the original tail no longer
        # applies (zero-fill for byte-alignment is fine, the game never reads it).
        self.original_tail = b""

    @staticmethod
    def _create_frame_between(frame_a: 'AnimationFrame', frame_b: 'AnimationFrame', step: float,
                              bones: List[Bone]) -> 'AnimationFrame':
        """Create a new frame interpolated between frame_a (step=0.0) and frame_b (step=1.0)."""
        nb_bones = len(bones)
        new_frame = AnimationFrame(nb_bones)
        new_frame.mode_bit = frame_a.mode_bit
        new_frame.rotation_vector_data_supp = copy.deepcopy(frame_a.rotation_vector_data_supp)

        # Skeleton position: simple linear interpolation of the raw values
        for axis in range(3):
            raw_a = frame_a.position[axis].get_pos_raw()
            raw_b = frame_b.position[axis].get_pos_raw()
            raw_value = round(raw_a + (raw_b - raw_a) * step)
            new_frame.position.append(PositionType(0, raw_value))

        # Bone rotations: interpolate each axis taking the shortest way around
        # the circle (a full circle is 4096 in raw units)
        for bone_index in range(nb_bones):
            new_rotations = []
            for axis in range(3):
                raw_a = int(frame_a.rotation_vector_data[bone_index][axis].get_rotate_raw())
                raw_b = int(frame_b.rotation_vector_data[bone_index][axis].get_rotate_raw())
                shortest_delta = ((raw_b - raw_a + 2048) % 4096) - 2048
                raw_value = round(raw_a + shortest_delta * step)
                new_rotations.append(RotationType(True, 0, raw_value))
            new_frame.rotation_vector_data[bone_index] = new_rotations

        # Bone scales (squash-and-stretch): interpolate the raw values linearly.
        # A frame without the mode bit is entirely neutral (1024 raw).
        if frame_a.mode_bit == 1 or frame_b.mode_bit == 1:
            new_frame.mode_bit = 1
            for bone_index in range(nb_bones):
                if bone_index >= len(new_frame.rotation_vector_data_supp):
                    new_frame.rotation_vector_data_supp.append(RotationVectorDataSupp())
                supp = new_frame.rotation_vector_data_supp[bone_index]
                for axis in range(3):
                    if frame_a.mode_bit == 1 and bone_index < len(frame_a.rotation_vector_data_supp):
                        raw_a = frame_a.rotation_vector_data_supp[bone_index].get_scale_raw(axis)
                    else:
                        raw_a = RotationVectorDataSupp.SCALE_NEUTRAL_RAW
                    if frame_b.mode_bit == 1 and bone_index < len(frame_b.rotation_vector_data_supp):
                        raw_b = frame_b.rotation_vector_data_supp[bone_index].get_scale_raw(axis)
                    else:
                        raw_b = RotationVectorDataSupp.SCALE_NEUTRAL_RAW
                    supp.set_scale_raw(axis, round(raw_a + (raw_b - raw_a) * step))

        new_frame.set_all_bones_matrix(bones)
        return new_frame

    def _recompute_frame_storage_types(self):
        """
        The file format stores each frame as a delta from the previous frame, with a
        per-value storage size (the "type bits"). After inserting new frames all the
        deltas changed, so recompute the smallest storage size able to hold each delta.
        """
        prev_frame = None
        for frame in self.frames:
            for axis in range(3):
                prev_raw = prev_frame.position[axis].get_pos_raw() if prev_frame else 0
                delta = frame.position[axis].get_pos_raw() - prev_raw
                frame.position[axis].position_type_bits = self._smallest_type_index(delta, BitReader.POSITION_READ_HELPER)

            for bone_index in range(len(frame.rotation_vector_data)):
                for axis in range(3):
                    rotation = frame.rotation_vector_data[bone_index][axis]
                    if prev_frame:
                        prev_raw = int(prev_frame.rotation_vector_data[bone_index][axis].get_rotate_raw())
                    else:
                        prev_raw = 0
                    delta = int(rotation.get_rotate_raw()) - prev_raw
                    rotation.is_rotation_type_available = (delta != 0)
                    rotation.rotation_type_bits = self._smallest_type_index(delta, BitReader.ROTATION_READ_HELPER)
            prev_frame = frame

    @staticmethod
    def _smallest_type_index(delta: int, bit_sizes: List[int]) -> int:
        """Return the index of the smallest bit size able to hold delta as a signed value."""
        for type_index, nb_bits in enumerate(bit_sizes):
            if -(1 << (nb_bits - 1)) <= delta < (1 << (nb_bits - 1)):
                return type_index
        return len(bit_sizes) - 1

    def to_binary(self) -> bytearray:
        data = bytearray()
        data.extend(len(self.frames).to_bytes(1, byteorder='little'))

        writer = BitWriter()
        prev_frame = None

        for frame in self.frames:
            frame.write_to_writer(writer, prev_frame)
            prev_frame = frame

        # FLUSH at the end of each animation - this makes the buffer bits
        # part of this animation's data
        data.extend(writer.get_data(flush=True))
        data.extend(self.original_tail)

        return data

class AnimationSection:
    def __init__(self):
        self.nb_animations: int = 0
        self.offsets: List[int] = []
        self.animations: List[Animation] = []
        # Whether every frame currently holds its derived render matrices. Parsing builds them;
        # free_bone_matrices() drops them (huge RAM saving for files not shown in 3D) and sets
        # this False; build_bone_matrices() recomputes them.
        self.matrices_built: bool = True

    def free_bone_matrices(self):
        """Drop every frame's derived render matrices (bone_matrices / bone_chain_matrices /
        bone_acc_scale) - ~60% of a monster's animation RAM. They are recomputable from the
        rotations (build_bone_matrices) and are only needed to render the model in 3D, so a
        parsed file that isn't being shown shouldn't carry them. Save/round-trip is unaffected:
        it re-encodes each frame from its rotations, never the matrices."""
        for anim in self.animations:
            for frame in anim.frames:
                frame.free_matrices()
        self.matrices_built = False

    def build_bone_matrices(self, bones):
        """(Re)compute every frame's derived render matrices from its rotations."""
        for anim in self.animations:
            for frame in anim.frames:
                if getattr(frame, 'bone_matrices', None) is None:
                    frame._reset_matrix_lists(len(bones))
                frame.set_all_bones_matrix(bones)
        self.matrices_built = True

    def free_animations(self):
        """Drop the EXPANDED per-frame animation objects entirely (source rotations + derived
        matrices). The section is re-expandable from its tiny raw bytes via analyze(), so a file
        loaded but not shown in 3D doesn't carry the ~30 MB expansion. offsets is cleared too so
        a later re-analyze() doesn't append duplicates; nb_animations is kept for reference."""
        self.animations = []
        self.offsets = []
        self.matrices_built = False

    def analyze(self, data: bytes, bone_section: BoneSection):
        # Read animation section header
        self.nb_animations = int.from_bytes(data[0:4], byteorder='little')
        for i in range(self.nb_animations):
            off = int.from_bytes(data[4 + i * 4: 8 + i * 4], byteorder='little')
            self.offsets.append(off)
        for anim_idx in range(self.nb_animations):
            anim_start = self.offsets[anim_idx]
            anim: Animation = Animation()
            anim.frames = []

            # BitReader starts at byte AFTER the frame count byte
            br = BitReader(data, start_byte=anim_start + 1)

            for frame_index in range(data[anim_start]):
                anim.add_frame(br, bone_section)

            # The bit-stream rarely ends on a byte boundary: the leftover high
            # bits of the final byte are never read by the game
            # (Battle_ReadAnimation reads exactly the frames' bits) and are
            # zero-filled on save instead of preserving Square's original
            # garbage there.
            if br._bit_pos > 0:
                anim_end = br._byte_pos + 1
            else:
                anim_end = br._byte_pos
            next_start = self.offsets[anim_idx + 1] if anim_idx + 1 < self.nb_animations else len(data)
            if anim_end < next_start:
                anim.original_tail = bytes(data[anim_end:next_start])

            self.animations.append(anim)


    def __str__(self):
        return f"AnimationSection(nb:{self.nb_animations}, {self.animations})"

    def __repr__(self):
        return self.__str__()

    def to_binary(self) -> bytearray:
        data = bytearray()
        data.extend(self.nb_animations.to_bytes(4, byteorder='little'))

        # Collect all animation data first to calculate offsets
        animations_data = []
        current_offset = 4 + self.nb_animations * 4

        for anim in self.animations:
            animations_data.append(anim.to_binary())
            current_offset += len(animations_data[-1])

        # Write offsets
        current_offset = 4 + self.nb_animations * 4
        for anim_data in animations_data:
            data.extend(current_offset.to_bytes(4, byteorder='little'))
            current_offset += len(anim_data)

        # Write all animation data
        for anim_data in animations_data:
            data.extend(anim_data)

        # Pad to multiple of 4
        padding_needed = (4 - (len(data) % 4)) % 4
        if padding_needed > 0:
            data.extend(b'\x00' * padding_needed)

        return data


# Section 4: Texture animation

class DynamicTextureData:
    """One VRAM texture-animation entry: a fixed on-model `anchor_uv` position
    (what the monster's polygons actually sample) whose content is replaced by
    each `frames` entry in turn, cycling over time. Confirmed by inspecting
    real monster data (e.g. PuPu, com_id 60): the frame-position sequences show
    smooth sweeping paths with consecutive *duplicate* positions used to hold a
    frame for longer (no separate speed/counter field exists, unlike the
    structurally similar but unrelated stage texture-animator
    BS_Effect_DeformCompression @0x50cb20), and the sequence frequently starts
    or ends back at `anchor_uv`. This entire feature is vestigial in the
    retail PC build though (see DynamicTextureSection docstring) -- section 4's
    pointer is computed at load time but sits outside the address range of the
    struct any renderer actually receives, so nothing here is ever displayed
    in-game; this naming is the best-supported reading of the file format, not
    an observed runtime behavior.
    """
    def __init__(self, data:bytes=bytes()):
        self.texture_num:int = 0
        self.clut_info:int= 0
        self.anchor_uv = UV(member_size=1, vram_size=True)
        self.sprite_width = 0
        self.sprite_height=0
        self.number_frames = 0
        self.unk1=0
        self.unk2=0
        self.frames: List[UV] = []
        if data:
            self.analyze(data)
    def analyze(self, data:bytes):
        self.texture_num = int.from_bytes(data[0: 2], byteorder='little') & 0x3F
        self.clut_info = int.from_bytes(data[0: 2], byteorder='little') & 0xFFC0
        self.unk1 = int.from_bytes(data[2: 3], byteorder='little')
        self.sprite_width = int.from_bytes(data[3: 4], byteorder='little')*2 # The size is in VRAM-X ref, and a texel is on 2 bytes.
        self.sprite_height = int.from_bytes(data[4: 5], byteorder='little')
        self.number_frames = int.from_bytes(data[5: 6], byteorder='little')
        self.unk2 = int.from_bytes(data[6: 8], byteorder='little')
        self.anchor_uv.analyze(data[8: 10])
        for i in range(self.number_frames):
            uv = UV(member_size=1, vram_size=True)
            uv.analyze(data[10+i*2: 10+(i+1)*2])
            self.frames.append(uv)
    def to_binary(self):
        data = bytearray()
        data.extend(((self.clut_info & 0xFFC0) | (self.texture_num & 0x3F)).to_bytes(2, byteorder='little'))
        data.extend(self.unk1.to_bytes(1, byteorder='little'))
        data.extend(int(self.sprite_width/2).to_bytes(1, byteorder='little'))
        data.extend(self.sprite_height.to_bytes(1, byteorder='little'))
        data.extend(self.number_frames.to_bytes(1, byteorder='little'))
        data.extend(self.unk2.to_bytes(2, byteorder='little'))
        data.extend(self.anchor_uv.to_binary())
        for i in range(self.number_frames):
            data.extend(self.frames[i].to_binary())
        return data


    def __str__(self):
       return f"TextureAnimData(ID:{self.texture_num}, anchorUV:{self.anchor_uv}, SpriteSize:({ self.sprite_width},{ self.sprite_height}), NbFrames:{self.number_frames}), unk1:{self.unk1}, unk2:{self.unk2}, frames:{self.frames}"
    def __repr__(self):
        return self.__str__()

class DynamicTextureSection:
    def __init__(self):
        self.offset:List[int] = []
        self.dynamic_texture_data: List[DynamicTextureData] = []
        # Exact original section bytes, and a to_binary() snapshot of each
        # parsed entry, captured right after analyze(). A header slot whose
        # offset is 0 is a legitimate, position-significant "no animation for
        # this slot" marker rather than end-of-table padding -- confirmed
        # against the game's identical stage texture-animation reader
        # (BS_Effect_DeformCompression @0x50cb20), which indexes its own
        # u16 entryOffset[n] table positionally and treats 0 that way -- but no
        # monster-file consumer of this vestigial section exists to confirm
        # how many header slots there are meant to be, so reconstructing the
        # header from scratch can't reliably tell a real zero slot apart from
        # a coincidental zero word inside entry data. Rather than guess, an
        # unedited section (no entry's fields changed, none added/removed) is
        # written back byte-for-byte; only an actual edit falls back to a
        # freshly generated (dense, no zero slots) header.
        self._original_bytes: bytes = b""
        self._original_entry_snapshot: List[bytes] = []

    def analyze(self, data:bytes):
        for i in range(0, len(data)):
            offset = int.from_bytes(data[2*i: 2*(i+1)], byteorder='little')
            if offset < len(data) - 1:
                if not self.offset or self.offset[-1] < offset:
                    self.offset.append(offset)
            else:
                break
        for i in range(len(self.offset)):
            if self.offset[i] == 0:
                continue
            if i == len(self.offset)-1:
                self.dynamic_texture_data.append(DynamicTextureData(data[self.offset[i]:]))
            else:
                self.dynamic_texture_data.append(DynamicTextureData(data[self.offset[i]:self.offset[i + 1]]))
        self._original_bytes = bytes(data)
        self._original_entry_snapshot = [bytes(entry.to_binary()) for entry in self.dynamic_texture_data]

    def to_binary(self):
        current_snapshot = [bytes(entry.to_binary()) for entry in self.dynamic_texture_data]
        if self._original_bytes and current_snapshot == self._original_entry_snapshot:
            return bytearray(self._original_bytes)

        data = bytearray()
        # Write header
        offset_computed = []
        data_computed = []
        current_offset = len(self.dynamic_texture_data)*2
        for i in range(0, len(self.dynamic_texture_data)):
            current_data = self.dynamic_texture_data[i].to_binary()
            data_computed.append(current_data)
            offset_computed.append(current_offset)
            current_offset += len(current_data)
        for offset in offset_computed:
            data.extend(offset.to_bytes(2, byteorder='little'))
        for data_el in data_computed:
            data.extend(data_el)
        # Rainbow bug
        padding = (4 - len(data) % 4) % 4  # Calculate how many zeros needed
        data.extend([0] * padding)
        return data

    def __str__(self):
        return f"TextureAnimSection(offset:{self.offset}, data:{self.dynamic_texture_data})"
    def __repr__(self):
        return self.__str__()


class AIData:
    SECTION_HEADER_NB_SECTION = {'offset': 0, 'size': 4, 'byteorder': 'little', 'name': 'nb_section', 'pretty_name': 'Number section'}
    SECTION_HEADER_SECTION_POSITION = {'offset': 0x04, 'size': 4, 'byteorder': 'little', 'name': 'section_pos',
                                       'pretty_name': 'Section position'}  # size: nbSections * 4 bytes
    SECTION_HEADER_FILE_SIZE = {'offset': 0x30, 'size': 4, 'byteorder': 'little', 'name': 'file_size', 'pretty_name': 'File size'}  # offset: 4 + nbSections * 4
    SECTION_HEADER_DICT = {'nb_section': 0, 'section_pos': [], 'file_size': 0}

    # Section 1: Bone section
    SECTION_BONE_HEADER_NB = {'offset': 0x00, 'size': 2, 'byteorder': 'little', 'name': 'nb_bone', 'pretty_name': 'Number bones', 'default_value': 0}
    SECTION_BONE_HEADER_UNKNOWN00 = {'offset': 0x02, 'size': 2, 'byteorder': 'little', 'name': 'unknown00', 'pretty_name': 'Unknown00', 'default_value': 0}
    SECTION_BONE_HEADER_UNKNOWN01 = {'offset': 0x04, 'size': 2, 'byteorder': 'little', 'name': 'unknown01', 'pretty_name': 'Unknown01', 'default_value': 0}
    SECTION_BONE_HEADER_UNKNOWN02 = {'offset': 0x06, 'size': 2, 'byteorder': 'little', 'name': 'unknown02', 'pretty_name': 'Unknown01', 'default_value': 0}
    SECTION_BONE_HEADER_SCALE_X = {'offset': 0x08, 'size': 2, 'byteorder': 'little', 'name': 'scaleX', 'pretty_name': 'Scale X', 'default_value': 0, 'signed':True}
    SECTION_BONE_HEADER_SCALE_Z = {'offset': 0x0A, 'size': 2, 'byteorder': 'little', 'name': 'scaleZ', 'pretty_name': 'Scale Z', 'default_value': 0, 'signed':True}
    SECTION_BONE_HEADER_SCALE_Y = {'offset': 0x0C, 'size': 2, 'byteorder': 'little', 'name': 'scaleY', 'pretty_name': 'Scale Y', 'default_value': 0, 'signed':True}
    SECTION_BONE_HEADER_UNKNOWN2 = {'offset': 0x0E, 'size': 2, 'byteorder': 'little', 'name': 'unknown2', 'pretty_name': 'Unknown2', 'default_value': 0}

    SECTION_BONE_HEADER_LIST_DATA = [SECTION_BONE_HEADER_NB, SECTION_BONE_HEADER_UNKNOWN00, SECTION_BONE_HEADER_UNKNOWN01, SECTION_BONE_HEADER_UNKNOWN02, SECTION_BONE_HEADER_SCALE_X, SECTION_BONE_HEADER_SCALE_Z, SECTION_BONE_HEADER_SCALE_Y,
                                     SECTION_BONE_HEADER_UNKNOWN2]
    SECTION_BONE_HEADER_DICT = {item['name']: item['default_value'] for item in SECTION_BONE_HEADER_LIST_DATA}

    SECTION_BONE_DATA_PARENT = {'offset': 0x00, 'size': 2, 'byteorder': 'little', 'name': 'parent', 'pretty_name': 'Parent ID', 'default_value':0}
    SECTION_BONE_DATA_SIZE = {'offset': 0x02, 'size': 2, 'byteorder': 'little', 'name': 'size', 'pretty_name': 'Size', 'default_value':0}
    SECTION_BONE_DATA_ROTX = {'offset': 0x04, 'size': 2, 'byteorder': 'little', 'name': 'rotX', 'pretty_name': 'Rotation X', 'default_value':0}
    SECTION_BONE_DATA_ROTZ = {'offset': 0x06, 'size': 2, 'byteorder': 'little', 'name': 'rotZ', 'pretty_name': 'Rotation Z', 'default_value':0}
    SECTION_BONE_DATA_ROTY = {'offset': 0x08, 'size': 2, 'byteorder': 'little', 'name': 'rotY', 'pretty_name': 'Rotation Y', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN3 = {'offset': 0x0A, 'size': 2, 'byteorder': 'little', 'name': 'unknown3', 'pretty_name': 'Unknown 3', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN4 = {'offset': 0x0C, 'size': 2, 'byteorder': 'little', 'name': 'unknown4', 'pretty_name': 'Unknown 4', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN5 = {'offset': 0x0E, 'size': 2, 'byteorder': 'little', 'name': 'unknown5', 'pretty_name': 'Unknown 5', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN6 = {'offset': 0x10, 'size': 2, 'byteorder': 'little', 'name': 'unknown6', 'pretty_name': 'Unknown 6', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN7 = {'offset': 0x12, 'size': 2, 'byteorder': 'little', 'name': 'unknown7', 'pretty_name': 'Unknown 7', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN8 = {'offset': 0x14, 'size': 2, 'byteorder': 'little', 'name': 'unknown8', 'pretty_name': 'Unknown 8', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN9 = {'offset': 0x16, 'size': 2, 'byteorder': 'little', 'name': 'unknown9', 'pretty_name': 'Unknown 9', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN10 = {'offset': 0x18, 'size': 2, 'byteorder': 'little', 'name': 'unknown10', 'pretty_name': 'Unknown 10', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN11 = {'offset': 0x1A, 'size': 2, 'byteorder': 'little', 'name': 'unknown11', 'pretty_name': 'Unknown 11', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN12 = {'offset': 0x1C, 'size': 2, 'byteorder': 'little', 'name': 'unknown12', 'pretty_name': 'Unknown 12', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN13 = {'offset': 0x1E, 'size': 2, 'byteorder': 'little', 'name': 'unknown13', 'pretty_name': 'Unknown 13', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN14 = {'offset': 0x20, 'size': 2, 'byteorder': 'little', 'name': 'unknown14', 'pretty_name': 'Unknown 14', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN15 = {'offset': 0x22, 'size': 2, 'byteorder': 'little', 'name': 'unknown15', 'pretty_name': 'Unknown 15', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN16 = {'offset': 0x24, 'size': 2, 'byteorder': 'little', 'name': 'unknown16', 'pretty_name': 'Unknown 16', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN17 = {'offset': 0x26, 'size': 2, 'byteorder': 'little', 'name': 'unknown17', 'pretty_name': 'Unknown 17', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN18 = {'offset': 0x28, 'size': 2, 'byteorder': 'little', 'name': 'unknown18', 'pretty_name': 'Unknown 18', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN19 = {'offset': 0x2A, 'size': 2, 'byteorder': 'little', 'name': 'unknown19', 'pretty_name': 'Unknown 19', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN20 = {'offset': 0x2C, 'size': 2, 'byteorder': 'little', 'name': 'unknown20', 'pretty_name': 'Unknown 20', 'default_value':0}
    SECTION_BONE_DATA_UNKNOWN21 = {'offset': 0x2E, 'size': 2, 'byteorder': 'little', 'name': 'unknown21', 'pretty_name': 'Unknown 21', 'default_value':0}

    SECTION_BONE_DATA_LIST_DATA = [SECTION_BONE_DATA_PARENT, SECTION_BONE_DATA_SIZE, SECTION_BONE_DATA_ROTX, SECTION_BONE_DATA_ROTZ, SECTION_BONE_DATA_ROTY,
                                   SECTION_BONE_DATA_UNKNOWN3, SECTION_BONE_DATA_UNKNOWN4, SECTION_BONE_DATA_UNKNOWN5, SECTION_BONE_DATA_UNKNOWN6, SECTION_BONE_DATA_UNKNOWN7,
                                   SECTION_BONE_DATA_UNKNOWN8, SECTION_BONE_DATA_UNKNOWN9, SECTION_BONE_DATA_UNKNOWN10, SECTION_BONE_DATA_UNKNOWN11, SECTION_BONE_DATA_UNKNOWN12,
                                   SECTION_BONE_DATA_UNKNOWN13, SECTION_BONE_DATA_UNKNOWN14, SECTION_BONE_DATA_UNKNOWN15, SECTION_BONE_DATA_UNKNOWN16, SECTION_BONE_DATA_UNKNOWN17,
                                   SECTION_BONE_DATA_UNKNOWN18, SECTION_BONE_DATA_UNKNOWN19, SECTION_BONE_DATA_UNKNOWN20, SECTION_BONE_DATA_UNKNOWN21]

    SECTION_BONE_DATA_DICT = {item['name']: item['default_value'] for item in SECTION_BONE_DATA_LIST_DATA}

    SECTION_BONE_DICT = {'header': SECTION_BONE_HEADER_DICT, 'data': []}

    # Section 2: Geometry section
    SECTION_GEOMETRY_HEADER_NB_OBJECT = {'offset': 0x00, 'size': 4, 'byteorder': 'little', 'name': 'nb_object', 'pretty_name': 'Nb object', 'default_value':0}
    SECTION_GEOMETRY_HEADER_OBJECT_OFFSET = {'offset': 0x02, 'size': 4, 'byteorder': 'little', 'name': 'offset', 'pretty_name': 'Mesh position', 'default_value':[]}

    SECTION_GEOMETRY_OBJECT_DATA_NB_VERTICES = {'offset': 0x00, 'size': 2, 'byteorder': 'little', 'name': 'object_nb_vertices', 'pretty_name': 'Mesh position', 'default_value':0}

    SECTION_GEOMETRY_VERTICES_DATA_BONE_ID = {'offset': 0x00, 'size': 2, 'byteorder': 'little', 'name': 'vertices_bone_id', 'pretty_name': 'Vertices bone ID', 'default_value':0}
    SECTION_GEOMETRY_VERTICES_DATA_NUMBER_VERTEX = {'offset': 0x02, 'size': 2, 'byteorder': 'little', 'name': 'nb_vertex', 'pretty_name': 'Number vertex', 'default_value':[]}
    SECTION_GEOMETRY_VERTICES_DATA_VERTEX = {'offset': 0x04, 'size': 6, 'byteorder': 'little', 'name': 'vertex', 'pretty_name': 'Vertex', 'default_value':0}

    SECTION_GEOMETRY_VERTICES_DATA_VERTEX_X = {'offset': 0x00, 'size': 2, 'byteorder': 'little', 'name': 'vertexX', 'pretty_name': 'Vertex X', 'default_value':0}
    SECTION_GEOMETRY_VERTICES_DATA_VERTEX_Z = {'offset': 0x02, 'size': 2, 'byteorder': 'little', 'name': 'vertexZ', 'pretty_name': 'Vertex Z', 'default_value':0}
    SECTION_GEOMETRY_VERTICES_DATA_VERTEX_Y = {'offset': 0x04, 'size': 2, 'byteorder': 'little', 'name': 'vertexY', 'pretty_name': 'Vertex Y', 'default_value':0}

    SECTION_GEOMETRY_VERTEX_DATA_LIST_DATA = [SECTION_GEOMETRY_VERTICES_DATA_VERTEX_X, SECTION_GEOMETRY_VERTICES_DATA_VERTEX_Z, SECTION_GEOMETRY_VERTICES_DATA_VERTEX_Y]


    SECTION_GEOMETRY_OBJECT_DATA_PADDING = {'offset': 0x00, 'size': 0, 'byteorder': 'little', 'name': 'object_data_padding', 'pretty_name': 'Mesh position', 'default_value':0}
    SECTION_GEOMETRY_OBJECT_DATA_NB_TRIANGLE = {'offset': 0x00, 'size': 2, 'byteorder': 'little', 'name': 'nb_triangle', 'pretty_name': 'Mesh position', 'default_value':0}
    SECTION_GEOMETRY_OBJECT_DATA_NB_QUAD = {'offset': 0x02, 'size': 2, 'byteorder': 'little', 'name': 'nb_quad', 'pretty_name': 'Mesh position', 'default_value':0}
    SECTION_GEOMETRY_OBJECT_DATA_UNKNOWN = {'offset': 0x04, 'size': 8, 'byteorder': 'little', 'name': 'object_unknown', 'pretty_name': 'Mesh position', 'default_value':0}
    SECTION_GEOMETRY_OBJECT_DATA_TRIANGLE = {'offset': 0x0, 'size': 16, 'byteorder': 'little', 'name': 'triangle', 'pretty_name': 'Mesh position', 'default_value':[]}
    SECTION_GEOMETRY_OBJECT_DATA_QUAD = {'offset': 0x0, 'size': 20, 'byteorder': 'little', 'name': 'quad', 'pretty_name': 'Mesh position', 'default_value':[]}

    SECTION_GEOMETRY_END = {'offset': 0x00, 'size': 4, 'byteorder': 'little', 'name': 'vertices_count', 'pretty_name': 'Total count of vertices', 'default_value':0}

    SECTION_GEOMETRY_LIST_DATA = [SECTION_GEOMETRY_HEADER_NB_OBJECT, SECTION_GEOMETRY_HEADER_OBJECT_OFFSET]

    SECTION_GEOMETRY_VERTEX_DICT = {'vertices_bone_id': 0, 'nb_vertex':0, 'vertex_data':[]}
    SECTION_GEOMETRY_OBJECT_DICT = {'object_nb_vertices':0, 'vertices_section':SECTION_GEOMETRY_VERTEX_DICT, 'padding':[], 'nb_triangle':0, 'nb_quad':0, 'object_unknown':0, 'triangle':[], 'quad':[]}
    SECTION_GEOMETRY_DICT = {'nb_object': 0, 'offset':[], 'object':[]}
    # Section 3: Animation section
    SECTION_MODEL_ANIM_NB_MODEL = {'offset': 0x00, 'size': 4, 'byteorder': 'little', 'name': 'nb_anim', 'pretty_name': 'Number model animation'}
    SECTION_MODEL_ANIM_OFFSET = {'offset': 0x04, 'size': 4, 'byteorder': 'little', 'name': 'anim_offset', 'pretty_name': 'Animation offset'}
    SECTION_MODEL_ANIM_DICT = {'nb_animation': 0, 'animation_offset': []}
    SECTION_MODEL_ANIM_LIST_DATA = [SECTION_MODEL_ANIM_NB_MODEL, SECTION_MODEL_ANIM_OFFSET]
    # Section 5: Sequence Animation section
    SECTION_MODEL_SEQ_ANIM_NB_SEQ = {'offset': 0x00, 'size': 2, 'byteorder': 'little', 'name': 'nb_anim_seq', 'pretty_name': 'Number model animation'}
    SECTION_MODEL_SEQ_ANIM_OFFSET = {'offset': 0x02, 'size': 2, 'byteorder': 'little', 'name': 'seq_anim_offset', 'pretty_name': 'Sequence animation offset'}
    SECTION_MODEL_SEQ_ANIM_DICT = {'nb_anim_seq': 0, 'seq_anim_offset': [], 'seq_animation_data': []}
    SECTION_MODEL_SEQ_ANIM_LIST_DATA = [SECTION_MODEL_SEQ_ANIM_NB_SEQ, SECTION_MODEL_SEQ_ANIM_OFFSET]
    # Section 7: Info & stat section
    SECTION_INFO_STAT_NAME_DATA = {'offset': 0x00, 'size': 24, 'byteorder': 'big', 'name': 'monster_name', 'pretty_name': 'Monster name'}
    NAME_DATA = {'offset': 0x00, 'size': 24, 'byteorder': 'big', 'name': 'name', 'pretty_name': 'Name'}
    HP_DATA = {'offset': 0x18, 'size': 4, 'byteorder': 'big', 'name': 'hp', 'pretty_name': 'HP'}
    STR_DATA = {'offset': 0x1C, 'size': 4, 'byteorder': 'big', 'name': 'str', 'pretty_name': 'STR'}
    VIT_DATA = {'offset': 0x20, 'size': 4, 'byteorder': 'big', 'name': 'vit', 'pretty_name': 'VIT'}
    MAG_DATA = {'offset': 0x24, 'size': 4, 'byteorder': 'big', 'name': 'mag', 'pretty_name': 'MAG'}
    SPR_DATA = {'offset': 0x28, 'size': 4, 'byteorder': 'big', 'name': 'spr', 'pretty_name': 'SPR'}
    SPD_DATA = {'offset': 0x2C, 'size': 4, 'byteorder': 'big', 'name': 'spd', 'pretty_name': 'SPD'}
    EVA_DATA = {'offset': 0x30, 'size': 4, 'byteorder': 'big', 'name': 'eva', 'pretty_name': 'EVA'}
    MED_LVL_DATA = {'offset': 0xF4, 'size': 1, 'byteorder': 'big', 'name': 'med_lvl', 'pretty_name': 'Medium level'}
    HIGH_LVL_DATA = {'offset': 0xF5, 'size': 1, 'byteorder': 'big', 'name': 'high_lvl', 'pretty_name': 'High Level'}
    EXTRA_XP_DATA = {'offset': 0x100, 'size': 2, 'byteorder': 'little', 'name': 'extra_xp',
                     'pretty_name': 'Extra XP'}  # Seems the size was intended for 2 bytes, but in practice no monster has a value > 255
    XP_DATA = {'offset': 0x102, 'size': 2, 'byteorder': 'little', 'name': 'xp',
               'pretty_name': 'XP'}  # Seems the size was intended for 2 bytes, but in practice no monster has a value > 255
    LOW_LVL_MAG_DATA = {'offset': 0x104, 'size': 8, 'byteorder': 'big', 'name': 'low_lvl_mag', 'pretty_name': 'Low level Mag draw'}
    MED_LVL_MAG_DATA = {'offset': 0x10C, 'size': 8, 'byteorder': 'big', 'name': 'med_lvl_mag', 'pretty_name': 'Medium level Mag draw'}
    HIGH_LVL_MAG_DATA = {'offset': 0x114, 'size': 8, 'byteorder': 'big', 'name': 'high_lvl_mag', 'pretty_name': 'High level Mag draw'}
    LOW_LVL_MUG_DATA = {'offset': 0x11C, 'size': 8, 'byteorder': 'big', 'name': 'low_lvl_mug', 'pretty_name': 'Low level Mug draw'}
    MED_LVL_MUG_DATA = {'offset': 0x124, 'size': 8, 'byteorder': 'big', 'name': 'med_lvl_mug', 'pretty_name': 'Medium level Mug draw'}
    HIGH_LVL_MUG_DATA = {'offset': 0x12C, 'size': 8, 'byteorder': 'big', 'name': 'high_lvl_mug', 'pretty_name': 'High level Mug draw'}
    LOW_LVL_DROP_DATA = {'offset': 0x134, 'size': 8, 'byteorder': 'big', 'name': 'low_lvl_drop', 'pretty_name': 'Low level drop draw'}
    MED_LVL_DROP_DATA = {'offset': 0x13C, 'size': 8, 'byteorder': 'big', 'name': 'med_lvl_drop', 'pretty_name': 'Medium level drop draw'}
    HIGH_LVL_DROP_DATA = {'offset': 0x144, 'size': 8, 'byteorder': 'big', 'name': 'high_lvl_drop', 'pretty_name': 'High level drop draw'}
    MUG_RATE_DATA = {'offset': 0x14C, 'size': 1, 'byteorder': 'big', 'name': 'mug_rate', 'pretty_name': 'Mug rate %'}
    DROP_RATE_DATA = {'offset': 0x14D, 'size': 1, 'byteorder': 'big', 'name': 'drop_rate', 'pretty_name': 'Drop rate %'}
    PADDING_DATA = {'offset': 0x14E, 'size': 1, 'byteorder': 'big', 'name': 'padding', 'pretty_name': 'Empty padding'}
    AP_DATA = {'offset': 0x14F, 'size': 1, 'byteorder': 'big', 'name': 'ap', 'pretty_name': 'AP'}
    SECTION_INFO_STAT_RENZOKUKEN = {'offset': 0x150, 'size': 16, 'byteorder': 'little', 'name': 'renzokuken', 'pretty_name': 'Renzokuken'}
    ELEM_DEF_DATA = {'offset': 0x160, 'size': 8, 'byteorder': 'big', 'name': 'elem_def', 'pretty_name': 'Elemental def'}
    STATUS_DEF_DATA = {'offset': 0x168, 'size': 20, 'byteorder': 'big', 'name': 'status_def', 'pretty_name': 'Status def'}
    SECTION_INFO_STAT_BYTE_FLAG_0 = {'offset': 0xF6, 'size': 1, 'byteorder': 'little', 'name': 'byte_flag_0', 'pretty_name': 'Byte Flag 0'}
    SECTION_INFO_STAT_BYTE_FLAG_0_LIST_VALUE = ['byte0_zz1', 'byte0_zz2', 'byte0_zz3', 'byte0_unused4', 'byte0_unused5', 'byte0_unused6', 'byte0_unused7',
                                                'byte0_unused8']
    SECTION_INFO_STAT_BYTE_FLAG_1 = {'offset': 0xF7, 'size': 1, 'byteorder': 'little', 'name': 'byte_flag_1', 'pretty_name': 'Byte Flag 1'}
    SECTION_INFO_STAT_BYTE_FLAG_1_LIST_VALUE = ['Zombie', 'Fly', 'byte1_zz1', 'Immune NVPlus_Moins', 'Hidden HP', 'Auto-Reflect', 'Auto-Shell', 'Auto-Protect']
    CARD_DATA = {'offset': 0xF8, 'size': 3, 'byteorder': 'big', 'name': 'card', 'pretty_name': 'Card data'}
    DEVOUR_DATA = {'offset': 0xFB, 'size': 3, 'byteorder': 'big', 'name': 'devour', 'pretty_name': 'Devour'}
    SECTION_INFO_STAT_BYTE_FLAG_2 = {'offset': 0xFE, 'size': 1, 'byteorder': 'little', 'name': 'byte_flag_2', 'pretty_name': 'Byte Flag 2'}
    SECTION_INFO_STAT_BYTE_FLAG_2_LIST_VALUE = ['IncreaseSurpriseRNG', 'DecreaseSurpriseRNG', 'SurpriseAttackImmunity', 'IncreaseChanceEscape', 'DecreaseChanceEscape',
                                                'byte2_unused_6',
                                                'Diablos-missed', 'Always obtains card']
    SECTION_INFO_STAT_BYTE_FLAG_3 = {'offset': 0xFF, 'size': 1, 'byteorder': 'little', 'name': 'byte_flag_3', 'pretty_name': 'Byte Flag 3'}
    SECTION_INFO_STAT_BYTE_FLAG_3_LIST_VALUE = ['byte3_zz1', 'byte3_zz2', 'byte3_zz3', 'byte3_zz4', 'byte3_unused_5', 'byte3_unused_6', 'byte3_unused_7',
                                                'byte3_unused_8']
    ABILITIES_LOW_DATA = {'offset': 0x34, 'size': 64, 'byteorder': 'little', 'name': 'abilities_low', 'pretty_name': 'Abilities Low Level'}
    ABILITIES_MED_DATA = {'offset': 0x74, 'size': 64, 'byteorder': 'little', 'name': 'abilities_med', 'pretty_name': 'Abilities Medium Level'}
    ABILITIES_HIGH_DATA = {'offset': 0xB4, 'size': 64, 'byteorder': 'little', 'name': 'abilities_high', 'pretty_name': 'Abilities High Level'}
    SECTION_INFO_STAT_DICT = {'monster_name': "", 'hp': [], 'str': [], 'vit': [], 'mag': [], 'spr': [], 'spd': [], 'eva': [],
                              'abilities_low': [], 'abilities_med': [], 'abilities_high': [], 'med_lvl': 0, 'high_lvl': 0,
                              'byte_flag_0': {}, 'byte_flag_1': {}, 'card': [], 'devour': [], 'byte_flag_2': {}, 'byte_flag_3': {},
                              'extra_xp': 0, 'xp': 0, 'low_lvl_mag': [], 'med_lvl_mag': [], 'high_lvl_mag': [],
                              'low_lvl_mug': [], 'med_lvl_mug': [], 'high_lvl_mug': [],
                              'low_lvl_drop': [], 'med_lvl_drop': [], 'high_lvl_drop': [], 'mug_rate': 0, 'drop_rate': 0,
                              'padding': 0, 'ap': 0, 'renzokuken': [], 'elem_def': [], 'status_def': []}
    SECTION_INFO_STAT_LIST_DATA = [SECTION_INFO_STAT_NAME_DATA, HP_DATA, STR_DATA, VIT_DATA, MAG_DATA, SPR_DATA, SPD_DATA, EVA_DATA,
                                   ABILITIES_LOW_DATA, ABILITIES_MED_DATA, ABILITIES_HIGH_DATA, MED_LVL_DATA, HIGH_LVL_DATA,
                                   SECTION_INFO_STAT_BYTE_FLAG_0, SECTION_INFO_STAT_BYTE_FLAG_1, CARD_DATA, DEVOUR_DATA,
                                   SECTION_INFO_STAT_BYTE_FLAG_2, SECTION_INFO_STAT_BYTE_FLAG_3,
                                   EXTRA_XP_DATA, XP_DATA, LOW_LVL_MAG_DATA, MED_LVL_MAG_DATA, HIGH_LVL_MAG_DATA,
                                   LOW_LVL_MUG_DATA, MED_LVL_MUG_DATA, HIGH_LVL_MUG_DATA, LOW_LVL_DROP_DATA, MED_LVL_DROP_DATA, HIGH_LVL_DROP_DATA,
                                   MUG_RATE_DATA, DROP_RATE_DATA, PADDING_DATA, AP_DATA, SECTION_INFO_STAT_RENZOKUKEN, ELEM_DEF_DATA, STATUS_DEF_DATA]
    # Battle script section
    # Subsection header
    SECTION_BATTLE_SCRIPT_HEADER_NB_SUB = {'offset': 0x00, 'size': 4, 'byteorder': 'little', 'name': 'battle_nb_sub', 'pretty_name': 'Number sub-section'}
    SECTION_BATTLE_SCRIPT_HEADER_OFFSET_AI_SUB = {'offset': 0x04, 'size': 4, 'byteorder': 'little', 'name': 'offset_ai_sub',
                                                  'pretty_name': 'Offset AI sub-section'}
    SECTION_BATTLE_SCRIPT_HEADER_OFFSET_TEXT_OFFSET_SUB = {'offset': 0x08, 'size': 4, 'byteorder': 'little', 'name': 'offset_text_offset',
                                                           'pretty_name': 'Offset to text offset'}
    SECTION_BATTLE_SCRIPT_HEADER_OFFSET_TEXT_SUB = {'offset': 0x0C, 'size': 4, 'byteorder': 'little', 'name': 'offset_text_sub',
                                                    'pretty_name': 'Offset to text sub-section'}

    SECTION_BATTLE_SCRIPT_BATTLE_SCRIPT_HEADER_LIST_DATA = [SECTION_BATTLE_SCRIPT_HEADER_NB_SUB, SECTION_BATTLE_SCRIPT_HEADER_OFFSET_AI_SUB,
                                                            SECTION_BATTLE_SCRIPT_HEADER_OFFSET_TEXT_OFFSET_SUB, SECTION_BATTLE_SCRIPT_HEADER_OFFSET_TEXT_SUB]
    # Subsection AI
    SECTION_BATTLE_SCRIPT_AI_OFFSET_INIT_CODE = {'offset': 0x00, 'size': 4, 'byteorder': 'little', 'name': 'offset_init_code',
                                                 'pretty_name': 'Offset init code'}
    SECTION_BATTLE_SCRIPT_AI_OFFSET_ENNEMY_TURN = {'offset': 0x04, 'size': 4, 'byteorder': 'little', 'name': 'offset_ennemy_turn',
                                                   'pretty_name': 'Offset ennemy turn'}
    SECTION_BATTLE_SCRIPT_AI_OFFSET_COUNTERATTACK = {'offset': 0x08, 'size': 4, 'byteorder': 'little', 'name': 'offset_counterattack',
                                                     'pretty_name': 'Offset counterattack'}
    SECTION_BATTLE_SCRIPT_AI_OFFSET_DEATH = {'offset': 0x0C, 'size': 4, 'byteorder': 'little', 'name': 'offset_death', 'pretty_name': 'Offset death'}
    SECTION_BATTLE_SCRIPT_AI_OFFSET_BEFORE_DYING_OR_HIT = {'offset': 0x10, 'size': 4, 'byteorder': 'little', 'name': 'offset_before_dying_or_hit',
                                                           'pretty_name': 'Offset before dying or getting hit'}
    SECTION_BATTLE_SCRIPT_AI_OFFSET_LIST_DATA = [SECTION_BATTLE_SCRIPT_AI_OFFSET_INIT_CODE, SECTION_BATTLE_SCRIPT_AI_OFFSET_ENNEMY_TURN,
                                                 SECTION_BATTLE_SCRIPT_AI_OFFSET_COUNTERATTACK, SECTION_BATTLE_SCRIPT_AI_OFFSET_DEATH,
                                                 SECTION_BATTLE_SCRIPT_AI_OFFSET_BEFORE_DYING_OR_HIT]
    # Subsection Offset to text offset
    SECTION_BATTLE_SCRIPT_TEXT_OFFSET = {'offset': 0x00, 'size': 2, 'byteorder': 'little', 'name': 'text_offset', 'pretty_name': 'List of text offset'}
    # Subsection battle text
    SECTION_BATTLE_SCRIPT_BATTLE_TEXT = {'offset': 0x00, 'size': 0, 'byteorder': 'little', 'name': 'battle_text', 'pretty_name': 'Battle text'}
    SECTION_BATTLE_SCRIPT_DICT = {'battle_nb_sub': 0, 'offset_ai_sub': 0, 'offset_text_offset': 0, 'offset_text_sub': 0, 'text_offset': [], 'battle_text': [],
                                  'ai_data': []}
    SECTION_BATTLE_SCRIPT_LIST_DATA = [SECTION_BATTLE_SCRIPT_HEADER_NB_SUB, SECTION_BATTLE_SCRIPT_HEADER_OFFSET_AI_SUB,
                                       SECTION_BATTLE_SCRIPT_HEADER_OFFSET_TEXT_OFFSET_SUB, SECTION_BATTLE_SCRIPT_HEADER_OFFSET_TEXT_SUB,
                                       SECTION_BATTLE_SCRIPT_TEXT_OFFSET, SECTION_BATTLE_SCRIPT_BATTLE_TEXT, SECTION_BATTLE_SCRIPT_AI_OFFSET_INIT_CODE,
                                       SECTION_BATTLE_SCRIPT_AI_OFFSET_ENNEMY_TURN, SECTION_BATTLE_SCRIPT_AI_OFFSET_COUNTERATTACK,
                                       SECTION_BATTLE_SCRIPT_AI_OFFSET_DEATH, SECTION_BATTLE_SCRIPT_AI_OFFSET_BEFORE_DYING_OR_HIT]

    SECTION_TEXTURE_NB = {'offset': 0x00, 'size': 4, 'byteorder': 'little', 'name': 'nb_texture', 'pretty_name': 'Number texture'}
    SECTION_TEXTURE_OFFSET = {'offset': 0x04, 'size': 4, 'byteorder': 'little', 'name': 'tim_offset', 'pretty_name': 'TIM offset'}
    SECTION_TEXTURE_END_OF_FILE = {'offset': 0x00, 'size': 4, 'byteorder': 'little', 'name': 'eof_texture', 'pretty_name': 'End  of file texture'}
    SECTION_TEXTURE_DATA = {'offset': 0x00, 'size': 4, 'byteorder': 'little', 'name': 'texture_data', 'pretty_name': 'Texture data'}
    SECTION_TEXTURE_LIST_DATA = [SECTION_TEXTURE_NB, SECTION_TEXTURE_OFFSET, SECTION_TEXTURE_END_OF_FILE, SECTION_TEXTURE_DATA]
    SECTION_TEXTURE_DICT = {'nb_texture': 0, 'tim_offset': [], 'eof_texture': 0, 'texture_data': []}

    BYTE_FLAG_LIST = ['byte_flag_0', 'byte_flag_1', 'byte_flag_2', 'byte_flag_3']
    CARD_OBTAIN_ORDER = ['DROP', 'MOD', 'RARE_MOD']
    MISC_ORDER = ['med_lvl', 'high_lvl', 'extra_xp', 'xp', 'mug_rate', 'drop_rate', 'ap']
    ABILITIES_HIGHNESS_ORDER = ['abilities_low', 'abilities_med', 'abilities_high']
    RESOURCE_FOLDER = "Resources"
    CHARACTER_LIST = ["Squall", "Zell", "Irvine", "Quistis", "Rinoa", "Selphie", "Seifer", "Edea", "Laguna", "Kiros", "Ward", "Angelo",
                      "Griever", "Boko"]
    COLOR_LIST = ["Darkgrey", "Grey", "Yellow", "Red", "Green", "Blue", "Purple", "White",
                  "DarkgreyBlink", "GreyBlink", "YellowBlink", "RedBlink", "GreenBlink", "BlueBlink", "PurpleBlink", "WhiteBlink"]
    LOCATION_LIST = ["Galbadia", "Esthar", "Balamb", "Dollet", "Timber", "Trabia", "Centra", "Horizon"]
    AI_CODE_NAME_LIST = ["Initialization fight", "Enemy turn", "Counter-Attack", "Death", "Before dying or taking a hit", "End"]
    ELEM_DEF_MIN_VAL = -100
    ELEM_DEF_MAX_VAL = 400
    STATUS_DEF_MIN_VAL = 0
    STATUS_DEF_MAX_VAL = 155
    STAT_MIN_VAL = 0
    STAT_MAX_VAL = 255
    AI_DATA_PATH = os.path.join("Resources", "ai_vanilla.json")
    AI_SECTION_LIST = ['Init code', 'Enemy turn', 'Counter-attack', 'Death', 'Before dying or taking a hit']
    COLOR = "#0055ff"
