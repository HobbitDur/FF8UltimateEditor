import json
import math
import os
from dataclasses import dataclass
from enum import Enum
from typing import List, Literal, Tuple, Optional

from PIL import Image


class LangType(Enum):
    ENGLISH = 0
    SPANISH = 1
    FRENCH = 2
    ITALIAN = 3
    GERMAN = 4


class MsdType(Enum):
    CARD_NAME = 0
    SCAN_TEXT = 1
    CARD_TEXT = 2
    DRAW_POINT = 3


class RemasterCardType(Enum):
    CARD_NAME = 0
    CARD_NAME2 = 1


class FileType(Enum):
    NONE = 0
    KERNEL = 1
    NAMEDIC = 2
    TKMNMES = 3
    MNGRP = 4
    EXE = 5
    DAT = 6
    REMASTER_DAT = 7
    FIELD_FS = 8
    WORLD_FS = 9


class SectionType(Enum):
    DATA = 1
    FF8_TEXT = 2
    KERNEL_HEADER = 3
    TKMNMES = 4
    MNGRP_STRING = 5
    MNGRP_MAP_COMPLEX_STRING = 6
    MNGRP_TEXTBOX = 7
    MNGRP_M00BIN = 8
    MNGRP_M00MSG = 9
    OFFSET_AND_TEXT = 10
    SIZE_AND_OFFSET_AND_TEXT = 11


# Section 1
class BoneSection:
    SECTION_BONE_HEADER_NB = {'offset': 0x00, 'size': 2, 'byteorder': 'little', 'name': 'nb_bone', 'pretty_name': 'Number bones', 'default_value': 0}
    SECTION_BONE_HEADER_UNKNOWN00 = {'offset': 0x02, 'size': 2, 'byteorder': 'little', 'name': 'unknown00', 'pretty_name': 'Unknown00', 'default_value': 0}
    SECTION_BONE_HEADER_UNKNOWN01 = {'offset': 0x04, 'size': 2, 'byteorder': 'little', 'name': 'unknown01', 'pretty_name': 'Unknown01', 'default_value': 0}
    SECTION_BONE_HEADER_UNKNOWN02 = {'offset': 0x06, 'size': 2, 'byteorder': 'little', 'name': 'unknown02', 'pretty_name': 'Unknown01', 'default_value': 0}
    SECTION_BONE_HEADER_SCALE_X = {'offset': 0x08, 'size': 2, 'byteorder': 'little', 'name': 'scaleX', 'pretty_name': 'Scale X', 'default_value': 0, 'signed':True}
    SECTION_BONE_HEADER_SCALE_Y = {'offset': 0x0A, 'size': 2, 'byteorder': 'little', 'name': 'scaleY', 'pretty_name': 'Scale Z', 'default_value': 0, 'signed':True}
    SECTION_BONE_HEADER_SCALE_Z = {'offset': 0x0C, 'size': 2, 'byteorder': 'little', 'name': 'scaleZ', 'pretty_name': 'Scale Y', 'default_value': 0, 'signed':True}
    SECTION_BONE_HEADER_UNKNOWN2 = {'offset': 0x0E, 'size': 2, 'byteorder': 'little', 'name': 'unknown2', 'pretty_name': 'Unknown2', 'default_value': 0}
    def __init__(self):
        self.nb_bone = 0
        self.unknown00 = 0
        self.unknown01 = 0
        self.unknown02 = 0
        self._scale_x = 0
        self._scale_y = 0
        self._scale_z = 0
        self.unknown2 = 0
        self.bones:List[Bone]= []
    def __str__(self):
        return f"Bones(count:{self.nb_bone}, unknown00:{self.unknown00}, unknown01:{self.unknown01}, unknown02:{self.unknown02}, scaleX:{self.get_scale_list()[0]}, scaleY:{self.get_scale_list()[1]}, scaleZ:{self.get_scale_list()[2]}, unknown2:{self.unknown2}, {self.bones})"
    def __repr__(self):
        return self.__str__()
    def analyze(self, data:bytes):
        self.nb_bone = int.from_bytes(data[self.SECTION_BONE_HEADER_NB['offset']:self.SECTION_BONE_HEADER_NB['offset'] + self.SECTION_BONE_HEADER_NB['size']],
                                        byteorder=self.SECTION_BONE_HEADER_NB['byteorder'])
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
        return self._scale_x, self._scale_y, self._scale_z


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
        self.parent_id = 0
        self.size = 0
        self._rotX = 0
        self._rotY = 0
        self._rotZ = 0
        self._local_rotation = (0, 0, 0)  # Will be filled from animation
        self._world_matrix = None
        self._world_position = (0, 0, 0)
        self._world_end = (0, 0, 0)
    def __str__(self):
        return f"Bone(Parent:{self.parent_id}, length:{self.size}, rot:{self._rotX},{self._rotY},{self._rotZ})"
    def __repr__(self):
        return self.__str__()
    def analyze(self, data:bytes):
        self.parent_id = int.from_bytes(data[self.SECTION_BONE_DATA_PARENT['offset']:self.SECTION_BONE_DATA_PARENT['offset']+self.SECTION_BONE_DATA_PARENT['size']], byteorder=self.SECTION_BONE_DATA_PARENT['byteorder'])
        self.size = int.from_bytes(data[self.SECTION_BONE_DATA_SIZE['offset']:self.SECTION_BONE_DATA_SIZE['offset']+self.SECTION_BONE_DATA_SIZE['size']], byteorder=self.SECTION_BONE_DATA_SIZE['byteorder'], signed=True) / 2048
        self._rotX = int.from_bytes(data[self.SECTION_BONE_DATA_ROTX['offset']:self.SECTION_BONE_DATA_ROTX['offset']+self.SECTION_BONE_DATA_ROTX['size']], byteorder=self.SECTION_BONE_DATA_ROTX['byteorder'], signed=True)
        self._rotY = int.from_bytes(data[self.SECTION_BONE_DATA_ROTY['offset']:self.SECTION_BONE_DATA_ROTY['offset']+self.SECTION_BONE_DATA_ROTY['size']], byteorder=self.SECTION_BONE_DATA_ROTY['byteorder'], signed=True)
        self._rotZ = int.from_bytes(data[self.SECTION_BONE_DATA_ROTZ['offset']:self.SECTION_BONE_DATA_ROTZ['offset']+self.SECTION_BONE_DATA_ROTZ['size']], byteorder=self.SECTION_BONE_DATA_ROTZ['byteorder'], signed=True)
    def get_rotation_deg(self):
        """Get rotation in degrees for animation (matches C# order)"""
        return (
            self._rotX * 360.0 / 4096.0,
            self._rotY * 360.0 / 4096.0,
            self._rotZ * 360.0 / 4096.0
        )
    def set_rotation_deg(self, rx: float, ry: float, rz: float):
        """Set rotation in degrees and update raw values"""
        self._rotX = int(rx * 4096.0 / 360.0)
        self._rotY = int(ry * 4096.0 / 360.0)
        self._rotZ = int(rz * 4096.0 / 360.0)
    def get_byte(self) -> bytearray:
        """Convert bone back to binary format"""
        data = bytearray()
        data.extend(self.parent_id.to_bytes(2, byteorder='little', signed=False))
        data.extend(int(self.size * 2048).to_bytes(2, byteorder='little', signed=True))
        data.extend(self._rotX.to_bytes(2, byteorder='little', signed=True))
        data.extend(self._rotY.to_bytes(2, byteorder='little', signed=True))
        data.extend(self._rotZ.to_bytes(2, byteorder='little', signed=True))

        # Add all the unknown fields (currently just zeros)
        # The bone data is 48 bytes total, we've written 10 bytes so far
        data.extend(bytearray(38))  # Fill remaining with zeros
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

    def analyze(self, data:bytes):
        self.vertex_indexes[0] = int.from_bytes(data[0:2], byteorder=self.SECTION_GEOMETRY_TRIANGLE_VERTEX_INDEXES['byteorder'])& 0xFFF
        self.vertex_indexes[1] = int.from_bytes(data[2:4], byteorder=self.SECTION_GEOMETRY_TRIANGLE_VERTEX_INDEXES['byteorder'])& 0xFFF
        self.vertex_indexes[2] = int.from_bytes(data[4:6], byteorder=self.SECTION_GEOMETRY_TRIANGLE_VERTEX_INDEXES['byteorder'])& 0xFFF
        self.vta.analyze(data[6:8])
        self.vtb.analyze(data[8:10])
        self.tex_id_1 = int.from_bytes(data[10:12], byteorder=self.SECTION_GEOMETRY_TRIANGLE_TEX_ID_1['byteorder'])
        self.vtc.analyze(data[12:14])
        self.tex_id_2 = int.from_bytes(data[14:16], byteorder=self.SECTION_GEOMETRY_TRIANGLE_TEX_ID_2['byteorder'])

    def __str__(self):
        return f"Triangle(VertexIndex{self.vertex_indexes}, UVData:{self.vta}{self.vtb}{self.vtc}, TexId({self.tex_id_1, self.tex_id_2}))"
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

    def analyze(self, data:bytes):
        self.vertex_indexes[0] = int.from_bytes(data[0:2], byteorder=self.SECTION_GEOMETRY_QUAD_VERTEX_INDEXES['byteorder']) & 0xFFF
        self.vertex_indexes[1] = int.from_bytes(data[2:4], byteorder=self.SECTION_GEOMETRY_QUAD_VERTEX_INDEXES['byteorder'])& 0xFFF
        self.vertex_indexes[2] = int.from_bytes(data[4:6], byteorder=self.SECTION_GEOMETRY_QUAD_VERTEX_INDEXES['byteorder'])& 0xFFF
        self.vertex_indexes[3] = int.from_bytes(data[6:8], byteorder=self.SECTION_GEOMETRY_QUAD_VERTEX_INDEXES['byteorder'])& 0xFFF
        self.vta.analyze(data[8:10])
        self.tex_id_1 = int.from_bytes(data[10:12], byteorder=self.SECTION_GEOMETRY_QUAD_TEX_ID_1['byteorder'])
        self.vtb.analyze(data[12:14])
        self.tex_id_2 = int.from_bytes(data[14:16], byteorder=self.SECTION_GEOMETRY_QUAD_TEX_ID_2['byteorder'])
        self.vtc.analyze(data[16:18])
        self.vtd.analyze(data[18:20])
    def __str__(self):
        return f"Quad(VertexIndex{self.vertex_indexes}, UVData{self.vta}{self.vtb}{self.vtc}{self.vtd}, TexId({self.tex_id_1, self.tex_id_2}))"
    def __repr__(self):
        return self.__str__()


class UV:
    def __init__(self):
        self.u: float=0
        self.v: float=0
    def analyze(self, data:bytes):
        self.u = int.from_bytes(data[0:1], byteorder='little')/128.0
        self.v = int.from_bytes(data[1:2], byteorder='little')/128.0
    def __str__(self):
        return f"UV({self.u},{self.v})"
    def __repr__(self):
        return self.__str__()

class ObjectData:
    SECTION_GEOMETRY_OBJECT_DATA_NB_VERTICES_DATA = {'offset': 0x00, 'size': 2, 'byteorder': 'little', 'name': 'nb_vertices_data', 'pretty_name': 'Mesh position', 'default_value':0}
    SECTION_GEOMETRY_OBJECT_DATA_PADDING = {'offset': 0x00, 'size': 0, 'byteorder': 'little', 'name': 'object_data_padding', 'pretty_name': 'Mesh position', 'default_value':0}
    SECTION_GEOMETRY_OBJECT_DATA_NB_TRIANGLE = {'offset': 0x00, 'size': 2, 'byteorder': 'little', 'name': 'nb_triangle', 'pretty_name': 'Mesh position', 'default_value':0}
    SECTION_GEOMETRY_OBJECT_DATA_NB_QUAD = {'offset': 0x02, 'size': 2, 'byteorder': 'little', 'name': 'nb_quad', 'pretty_name': 'Mesh position', 'default_value':0}
    SECTION_GEOMETRY_OBJECT_DATA_UNKNOWN = {'offset': 0x04, 'size': 8, 'byteorder': 'little', 'name': 'object_unknown', 'pretty_name': 'Mesh position', 'default_value':0}
    SECTION_GEOMETRY_OBJECT_DATA_TRIANGLE = {'offset': 0x0, 'size': 16, 'byteorder': 'little', 'name': 'triangle', 'pretty_name': 'Mesh position', 'default_value':[]}
    SECTION_GEOMETRY_OBJECT_DATA_QUAD = {'offset': 0x0, 'size': 20, 'byteorder': 'little', 'name': 'quad', 'pretty_name': 'Mesh position', 'default_value':[]}

    def __init__(self):
        self.nb_vertices_data = 0
        self.vertices_data:List[VerticesData]= []
        self._nb_padding = 0
        self.nb_triangle = 0
        self.nb_quad = 0
        self.unknown = 0
        self.triangles:List[GeometryTriangle] = []
        self.quads:List[GeometryQuad] = []


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
        unknown_byte = bytearray([0]*self.SECTION_GEOMETRY_OBJECT_DATA_UNKNOWN['size'])
        triangle_byte = bytearray()
        for triangle in self.triangles:
            triangle_byte.extend(triangle.get_byte())
        quad_byte = bytearray()
        for quad in self.quads:
            quad_byte.extend(quad.get_byte())

        return bytearray(nb_vertices_data_byte + vertices_data_byte + nb_padding_byte + nb_triangle_byte+nb_quad_byte+unknown_byte+triangle_byte+quad_byte)
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
        self.unknown = int.from_bytes(data[next_index+4:next_index+12], byteorder=self.SECTION_GEOMETRY_OBJECT_DATA_UNKNOWN['byteorder'])
        current_index = next_index+12
        next_index = current_index+ 16
        for i in range(self.nb_triangle):
            self.triangles.append(GeometryTriangle())
            self.triangles[-1].analyze(data[current_index: next_index])
            current_index = next_index
            next_index = next_index + 16
        next_index = current_index + 20
        for i in range(self.nb_quad):
            self.quads.append(GeometryQuad())
            self.quads[-1].analyze(data[current_index: next_index])
            current_index = next_index
            next_index = next_index + 20

    def __str__(self):
        return f"ObjectData(NbVerticesData:{self.nb_vertices_data}, padding:{self._nb_padding}, NbTriangle:{self.nb_triangle}, NbQuad:{self.nb_quad}, {self.vertices_data}, {self.triangles}, {self.quads})"
    def __repr__(self):
        return self.__str__()

    def get_triangles(self):
        triangle_list = []
        for triangle in self.triangles:
            triangle_list.append(triangle.vertex_indexes)
        return triangle_list
    def get_quads(self):
        quad_list = []
        for quad in self.quads:
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
        bone_id_byte = self.bone_id.to_bytes(length=self.SECTION_GEOMETRY_VERTICES_DATA_BONE_ID['size'], byteorder=self.SECTION_GEOMETRY_VERTICES_DATA_BONE_ID['byteorder'], signed=True)
        nb_vertices_byte = self.nb_vertices.to_bytes(length=self.SECTION_GEOMETRY_VERTICES_DATA_NUMBER_VERTEX['size'], byteorder=self.SECTION_GEOMETRY_VERTICES_DATA_NUMBER_VERTEX['byteorder'], signed=True)
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
        x_byte = self.x.to_bytes(length=self.SECTION_GEOMETRY_VERTICES_DATA_VERTEX_X['size'], byteorder=self.SECTION_GEOMETRY_VERTICES_DATA_VERTEX_X['byteorder'])
        y_byte = self.y.to_bytes(length=self.SECTION_GEOMETRY_VERTICES_DATA_VERTEX_Y['size'], byteorder=self.SECTION_GEOMETRY_VERTICES_DATA_VERTEX_Y['byteorder'])
        z_byte = self.z.to_bytes(length=self.SECTION_GEOMETRY_VERTICES_DATA_VERTEX_Z['size'], byteorder=self.SECTION_GEOMETRY_VERTICES_DATA_VERTEX_Z['byteorder'])
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

    def get_triangles(self):
        all_tri = []
        offset = 0
        for obj in self.object_data:
            obj_vert_count = sum(vd.nb_vertices for vd in obj.vertices_data)
            for tri in obj.triangles:
                all_tri.append((
                    tri.vertex_indexes[0] + offset,
                    tri.vertex_indexes[1] + offset,
                    tri.vertex_indexes[2] + offset
                ))
            offset += obj_vert_count
        return all_tri
    def get_quads(self):
        all_quads = []
        offset = 0
        for obj in self.object_data:
            obj_vert_count = sum(vd.nb_vertices for vd in obj.vertices_data)
            for quad in obj.quads:
                all_quads.append((
                    quad.vertex_indexes[0] + offset,
                    quad.vertex_indexes[1] + offset,
                    quad.vertex_indexes[2] + offset,
                    quad.vertex_indexes[3] + offset
                ))
            offset += obj_vert_count
        return all_quads

# Section 3 data:

class BitReader:
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

        # Sign-extend if count < 16 and the highest bit is set
        if count < 16 and (temp & (1 << (count - 1))):
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
            vector_axis = self.read_bits(self.ROTATION_READ_HELPER[count_index])
        count_index = self.read_bits(2) & 3
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
    def rotate_deg(self, deg):
        self._vector_axis_deg = deg
        self._vector_axis = deg * 4096.0 / 360.0
    def rotate_raw(self, raw):
        self._vector_axis = raw
        self._vector_axis_deg = raw * 360.0 / 4096.0

    def __str__(self):
        return f"RotType(Available:{self.is_rotation_type_available}, Bits:{self.rotation_type_bits}, Value:{self._vector_axis})"
    def __repr__(self):
        return self.__str__()

class RotationVectorDataSupp:
    def __init__(self):
        self.unk1: int = 0
        self.unk2: int = 0
        self.unk3: int = 0
        self.unk_flag1: bool = False
        self.unk_flag2: bool = False
        self.unk_flag3: bool = False

class PositionType:
    def __init__(self, position_type_bits:int = 0, vector_axis: float = 0):
        self.position_type_bits:int = position_type_bits
        self.vector_axis: float = vector_axis

class AnimationFrame:
    def __init__(self, nb_bones: int):
        self.position: List[PositionType] = []

        self.rotation_vector_data: List[List[RotationType]] = []
        #self.bone_rot_raw: List[Vector3D] = [Vector3D() for _ in range(nb_bones)]
        #self.bone_rot_deg: List[Tuple[float, float, float]] = [(0.0, 0.0, 0.0) for _ in range(nb_bones)]
        self.bone_matrices: List[Matrix4x4] = [Matrix4x4() for _ in range(nb_bones)]  # Initialize with identity matrices
        self.rotation_vector_data_supp: List[RotationVectorDataSupp] = [RotationVectorDataSupp() for _ in range(nb_bones)]
        self.mode_bit:int = 0


    def __str__(self):
        return f"AnimationFrame(pos:{self.position}, bones_rot:{self.rotation_vector_data})"

    def __repr__(self):
        return self.__str__()

    def rotate_bone_deg(self, deg:Vector3D, bone_id:int):
        if bone_id > len(self.rotation_vector_data):
            print(f"Bone id for rotation too high. BoneID:{bone_id}, max:{len(self.rotation_vector_data)}")
        self.rotation_vector_data[bone_id][0].rotate_deg(deg.x)
        self.rotation_vector_data[bone_id][1].rotate_deg(deg.y)
        self.rotation_vector_data[bone_id][2].rotate_deg(deg.z)

    def rotate_bone_raw(self, raw:Vector3D, bone_id:int):
        if bone_id > len(self.rotation_vector_data):
            print(f"Bone id for rotation too high. BoneID:{bone_id}, max:{len(self.rotation_vector_data)}")
        self.rotation_vector_data[bone_id][0].rotate_deg(raw.x)
        self.rotation_vector_data[bone_id][1].rotate_deg(raw.y)
        self.rotation_vector_data[bone_id][2].rotate_deg(raw.z)

    def set_bone_matrix(self, parent_id:int, parent_bone_size: int, bone_id:int):
        xRot = Matrix4x4.CreateRotationX(-self.rotation_vector_data[bone_id][0])
        yRot = Matrix4x4.CreateRotationY(-self.rotation_vector_data[bone_id][1])
        zRot = Matrix4x4.CreateRotationZ(-self.rotation_vector_data[bone_id][2])

        # Combine in the same order as C#: Y*X then Z*(Y*X)
        local = Matrix4x4.MultiplyColumnMajor(yRot, xRot)
        local = Matrix4x4.MultiplyColumnMajor(zRot, local)
        if parent_id != 0xFFFF:
            parent_mat = self.bone_matrices[parent_id]
            # World rotation = parent * local (row-major)
            world = Matrix4x4.MultiplyRowMajor(parent_mat, local)

            # Now manually set translation: parent_pos + parent_rot * (0,0,parent_length)

            world.M41 = parent_mat.M13 * parent_bone_size + parent_mat.M41
            world.M42 = parent_mat.M23 * parent_bone_size + parent_mat.M42
            world.M43 = parent_mat.M33 * parent_bone_size + parent_mat.M43
            self.bone_matrices[bone_id] = world
        else:
            local.M41 = 0.0
            local.M42 = 0.0
            local.M43 = 0.0
            self.bone_matrices[bone_id] = local

    def to_binary(self, prev_frame: 'AnimationFrame' = None) -> bytearray:
        """
        Convert frame back to binary delta-encoded format.
        This is complex because we need to re-encode the deltas.
        """
        data = bytearray()

        # Encode position deltas
        if prev_frame is None:
            px, py, pz = self.position
            px_raw = int(-px / 0.10)
            py_raw = int(-py / 0.10)
            pz_raw = int(-pz / 0.10)
        else:
            prev_px, prev_py, prev_pz = prev_frame.position
            px_raw = int(-(self.position[0] - prev_px) / 0.10)
            py_raw = int(-(self.position[1] - prev_py) / 0.10)
            pz_raw = int(-(self.position[2] - prev_pz) / 0.10)

        # Write position (simplified - you may need more sophisticated encoding)
        data.extend(self._encode_position_type(px_raw))
        data.extend(self._encode_position_type(py_raw))
        data.extend(self._encode_position_type(pz_raw))

        # Write mode bit (simplified - assume mode 0)
        data.extend(self._encode_bits(0, 1))

        # Encode bone rotations
        for bone_idx in range(len(self.bone_rot_raw)):
            raw = self.bone_rot_raw[bone_idx]
            prev_raw = prev_frame.bone_rot_raw[bone_idx] if prev_frame else Vector3D(0, 0, 0)

            rx_delta = int(raw.x - prev_raw.x)
            ry_delta = int(raw.y - prev_raw.y)
            rz_delta = int(raw.z - prev_raw.z)

            data.extend(self._encode_rotation_type(rx_delta))
            data.extend(self._encode_rotation_type(ry_delta))
            data.extend(self._encode_rotation_type(rz_delta))

        return data

    def _encode_position_type(self, value: int) -> bytearray:
        """Encode a position delta value"""
        # Simplified - you'd need to implement proper encoding based on the bit reader logic
        abs_val = abs(value)
        if abs_val < (1 << 3):
            bits_needed = 3
            type_idx = 0
        elif abs_val < (1 << 6):
            bits_needed = 6
            type_idx = 1
        elif abs_val < (1 << 9):
            bits_needed = 9
            type_idx = 2
        else:
            bits_needed = 16
            type_idx = 3

        # Write 2-bit type and then the value
        result = type_idx & 0x3
        result = (result << bits_needed) | (value & ((1 << bits_needed) - 1))

        # Convert to bytes (simplified)
        total_bits = 2 + bits_needed
        byte_count = (total_bits + 7) // 8
        return result.to_bytes(byte_count, byteorder='little')

    def _encode_rotation_type(self, value: int) -> bytearray:
        """Encode a rotation delta value"""
        if value == 0:
            return self._encode_bits(0, 1)

        abs_val = abs(value)
        if abs_val < (1 << 3):
            bits_needed = 3
            type_idx = 0
        elif abs_val < (1 << 6):
            bits_needed = 6
            type_idx = 1
        elif abs_val < (1 << 8):
            bits_needed = 8
            type_idx = 2
        else:
            bits_needed = 12
            type_idx = 3

        # Write 1-bit flag (1), 2-bit type, and the value
        result = 1  # Flag indicating there is rotation
        result = (result << 2) | type_idx
        result = (result << bits_needed) | (value & ((1 << bits_needed) - 1))

        total_bits = 3 + bits_needed
        byte_count = (total_bits + 7) // 8
        return result.to_bytes(byte_count, byteorder='little')

    def _encode_bits(self, value: int, num_bits: int) -> bytearray:
        """Encode a value with specific number of bits"""
        byte_count = (num_bits + 7) // 8
        return value.to_bytes(byte_count, byteorder='little')

    def set_all_bones_matrix(self, bones:List[Bone]):
        # --- Build bone matrices ---
        # Direct port of C# ReadSection3 matrix loop
        for bone_index in range(len(self.bone_matrices)):
            parent_id = bones[bone_index].parent_id
            if parent_id != 0xFFFF:
                bone_parent_size = bones[parent_id].size
            else:
                bone_parent_size = None
            self.set_bone_matrix(parent_id, bone_parent_size, bone_index)

    def move(self, br:BitReader, prev_frame:'AnimationFrame'):
        # --- Root position ---
        # C#: float x = -bitReader.ReadPositionType() * 0.10f  (delta)
        # Frame 0 is absolute, subsequent frames accumulate
        self.position = []
        px_raw = br.read_position_type()
        py_raw = br.read_position_type()
        pz_raw = br.read_position_type()
        self.position.append(PositionType(position_type_bits=px_raw[0], vector_axis=-px_raw[1]*0.10))
        self.position.append(PositionType(position_type_bits=py_raw[0], vector_axis=-py_raw[1]*0.10))
        self.position.append(PositionType(position_type_bits=pz_raw[0], vector_axis=-pz_raw[1]*0.10))

        if prev_frame:
            prev_pos = prev_frame.position
            self.position[0].vector_axis = self.position[0].vector_axis + prev_pos[0].vector_axis
            self.position[1].vector_axis = self.position[1].vector_axis + prev_pos[1].vector_axis
            self.position[2].vector_axis = self.position[2].vector_axis + prev_pos[2].vector_axis

    def rotate_all_bones(self, br:BitReader,prev_frame:'AnimationFrame'):
        self.mode_bit = br.read_bit()

        for bone_index in range(len(self.rotation_vector_data)):
            if prev_frame:
                prev_frame_raw = prev_frame.rotation_vector_data[bone_index],
            else:
                prev_frame_raw = [0, 0, 0]

            rx = br.read_rotation_type()
            ry = br.read_rotation_type()
            rz = br.read_rotation_type()
            self.rotation_vector_data[bone_index].append(RotationType(is_rotation_type_available=rx[0], rotation_type_bits=rx[1], vector_axis=rx[2]+prev_frame_raw[0]))
            self.rotation_vector_data[bone_index].append(RotationType(is_rotation_type_available=rx[0], rotation_type_bits=rx[1], vector_axis=rx[2]+prev_frame_raw[1]))
            self.rotation_vector_data[bone_index].append(RotationType(is_rotation_type_available=rx[0], rotation_type_bits=rx[1], vector_axis=rx[2]+prev_frame_raw[2]))

            if self.mode_bit == 1:
                self.rotation_vector_data_supp.unk_flag1 = br.read_bit()
                if self.rotation_vector_data_supp.unk_flag1:
                    self.rotation_vector_data_supp.unk1 = br.read_bits(16)
                self.rotation_vector_data_supp.unk_flag2 = br.read_bit()
                if self.rotation_vector_data_supp.unk_flag2:
                    self.rotation_vector_data_supp.unk2 = br.read_bits(16)
                self.rotation_vector_data_supp.unk_flag3 = br.read_bit()
                if self.rotation_vector_data_supp.unk_flag2:
                    self.rotation_vector_data_supp.unk3 = br.read_bits(16)

            if prev_frame_raw:
                self.rotation_vector_data[bone_index]
                raw = Vector3D(
                    prev_frame_raw.x + rx,
                    prev_frame_raw.y + ry,
                    prev_frame_raw.z + rz,
                )
            self.rotate_bone_raw(raw, bone_index)


class Animation:
    def __init__(self):
        self._frames: List[AnimationFrame] = []

    def __str__(self):
        return f"Animation(nb_frames:{len(self._frames)}, {self._frames})"

    def __repr__(self):
        return self.__str__()

    def add_frame(self, br:BitReader, bones:List[Bone]):
        frame = AnimationFrame(len(bones))
        if len(self._frames) != 0:
            prev_frame = self._frames[-1]
        else:
            prev_frame = None

        frame.move(br, prev_frame)
        frame.rotate_all_bones(br, prev_frame)
        frame.set_all_bones_matrix(bones)

        self._frames.append(frame)

    def get_nb_frame(self):
        return len(self._frames)


    def to_binary(self) -> bytearray:
        """Convert entire animation back to binary format"""
        data = bytearray()

        # Write frame count
        data.append(len(self._frames))

        # Write each frame with delta encoding
        for i, frame in enumerate(self._frames):
            prev_frame = self._frames[i - 1] if i > 0 else None
            data.extend(frame.to_binary(prev_frame))

        return data

class AnimationSection:
    def __init__(self):
        self.nb_animations: int = 0
        self.offsets: List[int] = []
        self.animations: List[Animation] = []

    def analyze(self, data: bytes, bone_section: BoneSection):
        bones = bone_section.bones

        # Read animation section header
        self.nb_animations = int.from_bytes(data[0:4], byteorder='little')

        for i in range(self.nb_animations):
            off = int.from_bytes(data[4 + i * 4: 8 + i * 4], byteorder='little')
            self.offsets.append(off)

        for anim_idx in range(self.nb_animations):
            anim_start = self.offsets[anim_idx]
            anim = Animation()
            anim._nb_frames = data[anim_start]
            anim._frames = []

            # BitReader starts at byte AFTER the frame count byte
            br = BitReader(data, start_byte=anim_start + 1)

            for frame_index in range(anim._nb_frames):
                anim.add_frame(br, bones)

            self.animations.append(anim)

    def __str__(self):
        return f"AnimationSection(nb:{self.nb_animations}, {self.animations})"

    def __repr__(self):
        return self.__str__()


    def to_binary(self) -> bytearray:
        """Convert entire animation section back to binary"""
        data = bytearray()

        # Write header
        data.extend(self.nb_animations.to_bytes(4, byteorder='little'))

        # Calculate and write offsets
        offset_pos = 4 + self.nb_animations * 4
        offsets = []
        anim_data = bytearray()

        for anim in self.animations:
            offsets.append(offset_pos)
            anim_binary = anim.to_binary()
            anim_data.extend(anim_binary)
            offset_pos += len(anim_binary)

        # Write offsets
        for offset in offsets:
            data.extend(offset.to_bytes(4, byteorder='little'))

        # Write animation data
        data.extend(anim_data)

        return data
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


class GameData:
    AIData = AIData()

    def __init__(self, game_data_submodule_path="FF8GameData", ai_file: str = "ai_vanilla.json"):
        self.resource_folder_json = os.path.join(game_data_submodule_path, "Resources", "json")
        self.resource_folder_image = os.path.join(game_data_submodule_path, "Resources", "image")
        self.resource_folder = os.path.join(game_data_submodule_path, "Resources")
        self.devour_data_json = {}
        self.magic_data_json = {}
        self.enemy_abilities_data_json = {}
        self.gforce_data_json = {}
        self.item_data_json = {}
        self.draw_data_json = {}
        self.special_action_data_json = {}
        self.field_data_json = {}
        self.stat_data_json = {}
        self.monster_data_json = {}
        self.status_data_json = {}
        self.field_data_json = {}
        self.sysfnt_data_json = {}
        self.kernel_data_json = {}
        self.mngrp_data_json = {}
        self.exe_data_json = {}
        self.ai_data_json = {}
        self.anim_sequence_data_json = {}
        self.ai_json_file_name = ai_file
        self.__init_hex_to_str_table()



    def __init_hex_to_str_table(self):
        self.load_sysfnt_data()
        with open(os.path.join(self.resource_folder, "sysfnt.txt"), "r", encoding="utf-8") as localize_file:
            self.translate_hex_to_str_table = localize_file.read()
            self.translate_hex_to_str_table = self.translate_hex_to_str_table.replace(',",",',
                                                                                      ',";;;",')  # Handling the unique case of a "," character (which is also a separator)
            self.translate_hex_to_str_table = self.translate_hex_to_str_table.replace('\n', '')
            self.translate_hex_to_str_table = self.translate_hex_to_str_table.split(',')
            for i in range(len(self.translate_hex_to_str_table)):
                self.translate_hex_to_str_table[i] = self.translate_hex_to_str_table[i].replace(';;;', ',')
                if self.translate_hex_to_str_table[i].count('"') == 2:
                    self.translate_hex_to_str_table[i] = self.translate_hex_to_str_table[i].replace('"', '')

    @staticmethod
    def find_delimiter_from_csv_file(csv_file):
        with open(csv_file, newline='', encoding="utf-8") as text_file:
            csv_text = text_file.read()
        number_comma = csv_text.count(',')
        number_semicolon = csv_text.count(';')
        number_pipe = csv_text.count('|')
        if number_pipe >= number_semicolon and number_pipe >= number_comma:
            delimiter = "|"
        elif number_semicolon >= number_pipe and number_semicolon >= number_comma:
            delimiter = ";"
        else:
            delimiter = ","
        return delimiter

    def load_ai_data(self, ai_json_name=None):
        if ai_json_name:
            self.ai_json_file_name = ai_json_name
        file_path = os.path.join(self.resource_folder_json, self.ai_json_file_name)
        with open(file_path, encoding="utf8") as f:
            self.ai_data_json = json.load(f)

    def load_gforce_data(self):
        file_path = os.path.join(self.resource_folder_json, "gforce.json")
        with open(file_path, encoding="utf8") as f:
            self.gforce_data_json = json.load(f)

    def load_stat_data(self):
        file_path = os.path.join(self.resource_folder_json, "stat.json")
        with open(file_path, encoding="utf8") as f:
            self.stat_data_json = json.load(f)

    def load_status_data(self):
        file_path = os.path.join(self.resource_folder_json, "status.json")
        with open(file_path, encoding="utf8") as f:
            self.status_data_json = json.load(f)

    def load_devour_data(self):
        file_path = os.path.join(self.resource_folder_json, "devour.json")
        with open(file_path, encoding="utf8") as f:
            self.devour_data_json = json.load(f)

    def load_field_data(self):
        file_path = os.path.join(self.resource_folder_json, "field.json")
        with open(file_path, encoding="utf8") as f:
            self.field_data_json = json.load(f)

    def load_enemy_abilities_data(self):
        file_path = os.path.join(self.resource_folder_json, "enemy_abilities.json")
        with open(file_path, encoding="utf8") as f:
            self.enemy_abilities_data_json = json.load(f)

    def load_magic_data(self):
        file_path = os.path.join(self.resource_folder_json, "magic.json")
        with open(file_path, encoding="utf8") as f:
            self.magic_data_json = json.load(f)

    def load_special_action_data(self):
        file_path = os.path.join(self.resource_folder_json, "special_action.json")
        with open(file_path, encoding="utf8") as f:
            self.special_action_data_json = json.load(f)

    def load_monster_data(self):
        file_path = os.path.join(self.resource_folder_json, "monster.json")
        with open(file_path, encoding="utf8") as f:
            self.monster_data_json = json.load(f)

    def load_sysfnt_data(self):
        file_path = os.path.join(self.resource_folder_json, "sysfnt_data.json")
        with open(file_path, encoding="utf8") as f:
            self.sysfnt_data_json = json.load(f)

    def load_item_data(self):
        file_path = os.path.join(self.resource_folder_json, "item.json")
        with open(file_path, encoding="utf8") as f:
            self.item_data_json = json.load(f)

    def load_draw_data(self):
        file_path = os.path.join(self.resource_folder_json, "draw.json")
        with open(file_path, encoding="utf8") as f:
            self.draw_data_json = json.load(f)

    def load_exe_data(self):
        file_path = os.path.join(self.resource_folder_json, "exe.json")
        with open(file_path, encoding="utf8") as f:
            self.exe_data_json = json.load(f)
        for key in self.exe_data_json["lang"]:
            if self.exe_data_json["lang"][key]:
                self.exe_data_json["lang"][key] = int(
                    self.exe_data_json["lang"][key], 16)
        for key in self.exe_data_json["card_data_offset"]:
            self.exe_data_json["card_data_offset"][key] = int(self.exe_data_json["card_data_offset"][key], 16)
        for key in self.exe_data_json["scan_data_offset"]:
            self.exe_data_json["scan_data_offset"][key] = int(self.exe_data_json["scan_data_offset"][key], 16)
        for key in self.exe_data_json["draw_text_offset"]:
            self.exe_data_json["draw_text_offset"][key] = int(self.exe_data_json["draw_text_offset"][key], 16)
        for key in self.exe_data_json["draw_data_offset"]:
            self.exe_data_json["draw_data_offset"][key] = int(self.exe_data_json["draw_data_offset"][key], 16)

    def load_anim_sequence_data(self):
        file_path = os.path.join(self.resource_folder_json, "anim_sequence_info.json")
        with open(file_path, encoding="utf8") as f:
            self.anim_sequence_data_json = json.load(f)
        for i, el in enumerate(self.anim_sequence_data_json["op_code_info"]):
            if el["op_code"]:
                self.anim_sequence_data_json["op_code_info"][i]["op_code"] = int(self.anim_sequence_data_json["op_code_info"][i]["op_code"], 16)
        for i, el in enumerate(self.anim_sequence_data_json["special_change_current_value_params"]):
            if el["param_id"]:
                self.anim_sequence_data_json["special_change_current_value_params"][i]["param_id"] = int(
                    self.anim_sequence_data_json["special_change_current_value_params"][i]["param_id"], 16)
        for i, el in enumerate(self.anim_sequence_data_json["e5_special_params"]):
            if el["param_id"]:
                self.anim_sequence_data_json["e5_special_params"][i]["param_id"] = int(self.anim_sequence_data_json["e5_special_params"][i]["param_id"], 16)
        for i, el in enumerate(self.anim_sequence_data_json["effect_id"]):
            if el["param_id"]:
                self.anim_sequence_data_json["effect_id"][i]["param_id"] = int(self.anim_sequence_data_json["effect_id"][i]["param_id"], 16)
        for i, el in enumerate(self.anim_sequence_data_json["fade_effect_id"]):
            if el["param_id"]:
                self.anim_sequence_data_json["fade_effect_id"][i]["param_id"] = int(self.anim_sequence_data_json["fade_effect_id"][i]["param_id"], 16)
        for i, el in enumerate(self.anim_sequence_data_json["sound_channel_flag"]):
            if el["param_id"]:
                self.anim_sequence_data_json["sound_channel_flag"][i]["param_id"] = int(self.anim_sequence_data_json["sound_channel_flag"][i]["param_id"], 16)
        for i, el in enumerate(self.anim_sequence_data_json["sound_id_from_category"]):
            if el["param_id"]:
                self.anim_sequence_data_json["sound_id_from_category"][i]["param_id"] = int(self.anim_sequence_data_json["sound_id_from_category"][i]["param_id"], 16)

    def load_mngrp_data(self):
        file_path = os.path.join(self.resource_folder_json, "mngrp_bin_data.json")
        with open(file_path, encoding="utf8") as f:
            self.mngrp_data_json = json.load(f)
        for i in range(len(self.mngrp_data_json["sections"])):
            if self.mngrp_data_json["sections"][i]["section_offset"]:
                self.mngrp_data_json["sections"][i]["section_offset"] = int(
                    self.mngrp_data_json["sections"][i]["section_offset"], 16)
            if self.mngrp_data_json["sections"][i]["size"]:
                self.mngrp_data_json["sections"][i]["size"] = int(
                    self.mngrp_data_json["sections"][i]["size"], 16)
            data_type_str = self.mngrp_data_json["sections"][i]["data_type"]
            if data_type_str == "tkmnmes":
                self.mngrp_data_json["sections"][i]["data_type"] = SectionType.TKMNMES
            elif data_type_str == "mngrp_string":
                self.mngrp_data_json["sections"][i]["data_type"] = SectionType.MNGRP_STRING
            elif data_type_str == "data":
                self.mngrp_data_json["sections"][i]["data_type"] = SectionType.DATA
            elif data_type_str == "text":
                self.mngrp_data_json["sections"][i]["data_type"] = SectionType.FF8_TEXT
            elif data_type_str == "mngrp_complex_string":
                self.mngrp_data_json["sections"][i]["data_type"] = SectionType.MNGRP_TEXTBOX
            elif data_type_str == "mngrp_map_complex_string":
                self.mngrp_data_json["sections"][i]["data_type"] = SectionType.MNGRP_MAP_COMPLEX_STRING
            elif data_type_str == "m00bin":
                self.mngrp_data_json["sections"][i]["data_type"] = SectionType.MNGRP_M00BIN
            elif data_type_str == "m00msg":
                self.mngrp_data_json["sections"][i]["data_type"] = SectionType.MNGRP_M00MSG

    def load_kernel_data(self):
        file_path = os.path.join(self.resource_folder_json, "kernel_bin_data.json")
        with open(file_path, encoding="utf8") as f:
            self.kernel_data_json = json.load(f)

        for i in range(len(self.kernel_data_json["sections"])):
            if self.kernel_data_json["sections"][i]["section_offset"]:
                self.kernel_data_json["sections"][i]["section_offset"] = int(
                    self.kernel_data_json["sections"][i]["section_offset"], 16)
            if self.kernel_data_json["sections"][i]["section_offset_text_linked"]:
                self.kernel_data_json["sections"][i]["section_offset_text_linked"] = int(
                    self.kernel_data_json["sections"][i]["section_offset_text_linked"], 16)
            if self.kernel_data_json["sections"][i]["section_offset_data_linked"]:
                self.kernel_data_json["sections"][i]["section_offset_data_linked"] = int(
                    self.kernel_data_json["sections"][i]["section_offset_data_linked"], 16)
            data_type_str = self.kernel_data_json["sections"][i]["type"]
            if data_type_str == "data":
                self.kernel_data_json["sections"][i]["type"] = SectionType.DATA
            elif data_type_str == "text":
                self.kernel_data_json["sections"][i]["type"] = SectionType.FF8_TEXT

    def load_card_data(self):
        file_path = os.path.join(self.resource_folder_json, "card.json")
        with open(file_path, encoding="utf8") as f:
            self.card_data_json = json.load(f)
        self.__load_cards()

    def __load_cards(self):
        # Thank you Maki !
        img = Image.open(os.path.join(self.resource_folder_image, "text_0.png"))
        TILES_WIDTH_EL = 128
        TILES_HEIGHT_EL = 128
        for i, list_el in enumerate(self.card_data_json["card_type"]):
            # Calculate the bounding box of the tile
            left = list_el["img_x"] * TILES_WIDTH_EL
            upper = list_el["img_y"] * TILES_HEIGHT_EL
            right = left + TILES_WIDTH_EL
            lower = upper + TILES_HEIGHT_EL
            # Extract the tile using cropping
            tile = img.crop((left, upper, right, lower))
            self.card_data_json["card_type"][i]["img"] = tile

        img = Image.open(os.path.join(self.resource_folder_image, "cards_00.png"))
        img_remaster = Image.open(os.path.join(self.resource_folder_image, "cards_00_remaster.png"))
        img_xylomod = Image.open(os.path.join(self.resource_folder_image, "cards_00_xylomod.png"))

        TILES_WIDTH = 64
        TILES_HEIGHT = 64
        for i, list_el in enumerate(self.card_data_json["card_info"]):
            # Calculate the bounding box of the tile
            left = list_el["img_x"] * TILES_WIDTH
            upper = list_el["img_y"] * TILES_HEIGHT
            right = left + TILES_WIDTH
            lower = upper + TILES_HEIGHT
            # Extract the tile using cropping
            tile = img.crop((left, upper, right, lower))
            self.card_data_json["card_info"][i]["img"] = tile

        TILES_WIDTH = 256
        TILES_HEIGHT = 256
        for i, list_el in enumerate(self.card_data_json["card_info"]):
            # Calculate the bounding box of the tile
            left = list_el["img_x"] * TILES_WIDTH
            upper = list_el["img_y"] * TILES_HEIGHT
            right = left + TILES_WIDTH
            lower = upper + TILES_HEIGHT
            # Extract the tile using cropping
            tile_remaster = img_remaster.crop((left, upper, right, lower))
            self.card_data_json["card_info"][i]["img_remaster"] = tile_remaster

        TILES_WIDTH = 256
        TILES_HEIGHT = 256
        for i, list_el in enumerate(self.card_data_json["card_info"]):
            # Calculate the bounding box of the tile
            left = list_el["img_x"] * TILES_WIDTH
            upper = list_el["img_y"] * TILES_HEIGHT
            right = left + TILES_WIDTH
            lower = upper + TILES_HEIGHT
            # Extract the tile using cropping
            tile_xylomod = img_xylomod.crop((left, upper, right, lower))
            self.card_data_json["card_info"][i]["img_xylomod"] = tile_xylomod

    def translate_str_to_hex(self, string):
        c = 0
        str_size = len(string)
        encode_list = []
        while c < str_size:
            char = string[c]
            if char == '\\':
                encode_list.append(0x02)
                c += 2
                continue
            if char == '\n':  # \n{NewPage}\n,\n
                if '{NewPage}' in string[c + 1:c + 10]:
                    encode_list.append(0x01)
                    c += 10
                else:
                    encode_list.append(0x02)
                    c += 1
                continue
            elif char == '{':
                rest = string[c + 1:]
                index_next_bracket = rest.find('}')
                if index_next_bracket != -1:
                    substring = rest[:index_next_bracket]
                    if substring in self.sysfnt_data_json['Characters']:  # {name}
                        index_list = self.sysfnt_data_json['Characters'].index(substring)
                        if index_list < 11:
                            encode_list.extend([0x03, 0x30 + index_list])
                        elif index_list == 11:
                            encode_list.extend([0x03, 0x40])
                        elif index_list == 12:
                            encode_list.extend([0x03, 0x50])
                        elif index_list == 13:
                            encode_list.extend([0x03, 0x60])
                    elif substring in self.sysfnt_data_json['Icons']:  # {Icons}
                        index_list = self.sysfnt_data_json['Icons'].index(substring)
                        encode_list.extend([0x05, 0x20 + index_list])
                    elif substring in self.sysfnt_data_json['Colors']:  # {Color}
                        index_list = self.sysfnt_data_json['Colors'].index(substring)
                        encode_list.extend([0x06, 0x20 + index_list])
                    elif substring in self.sysfnt_data_json['GuardianForce']:  # {GuardianForce}
                        index_list = self.sysfnt_data_json['GuardianForce'].index(substring)
                        encode_list.extend([0x0c, 0x60 + index_list])
                    elif substring in self.sysfnt_data_json['Locations']:  # {Location}
                        index_list = self.sysfnt_data_json['Locations'].index(substring)
                        encode_list.extend([0x0e, 0x20 + index_list])
                    elif 'Cursor_location_id:0x' in substring:
                        len_curs = len('Cursor_location_id:0x')
                        if len(substring) == len_curs + 4:
                            encode_list.extend([0x0b, int(substring[len_curs:len_curs + 2], 16), int(substring[len_curs + 2:len_curs + 4], 16)])
                        else:
                            encode_list.extend([0x0b, int(substring[len_curs:len_curs + 2], 16)])
                    elif 'Var' in substring:
                        if len(substring) == 5:
                            if 'b' in substring:  # {Varb0}
                                encode_list.extend([0x04, int(substring[-1]) + 0x40])
                            else:  # {Var00}
                                encode_list.extend([0x04, int(substring[-1]) + 0x30])
                        else:  # {Var0}
                            encode_list.extend([0x04, int(substring[-1]) + 0x20])
                    elif 'Wait' in substring:  # {Wait000}
                        encode_list.extend([0x09, int(substring[-1]) + 0x20])
                    elif 'Jp' in substring:  # {Jp000}
                        encode_list.extend([0x1c, int(substring[-1]) + 0x20])
                    elif '{' + substring + '}' in self.translate_hex_to_str_table:  # {} at end of sysfnt
                        encode_list.append(self.translate_hex_to_str_table.index('{' + substring + '}'))
                    elif 'x' in substring and len(substring) == 5:  # {xffff}
                        encode_list.extend([int(substring[1:3], 16), int(substring[3:5], 16)])
                    elif 'x' in substring and len(substring) == 3:  # {xff}
                        encode_list.append(int(substring[1:3], 16))
                    c += len(substring) + 2  # +2 for the {}
                    continue
            encode_list.append(self.translate_hex_to_str_table.index(char))
            c += 1
            # Jp ?
        return encode_list

    def translate_hex_to_str(self, hex_list, zero_as_slash_n=False, first_hex_literal=False, cursor_location_size=2):
        build_str = ""
        i = 0
        hex_size = len(hex_list)
        while i < hex_size:
            hex_val = hex_list[i]
            if i == 0 and first_hex_literal:
                build_str += "{{x{:02x}}}".format(hex_val)
            elif hex_val == 0x00 and zero_as_slash_n:
                build_str += "\n"
            elif hex_val == 0x00:
                pass
            elif hex_val in [0x01, 0x02]:
                build_str += self.translate_hex_to_str_table[hex_val]
            elif hex_val == 0x03:  # {Name}
                i += 1
                if i < hex_size:
                    hex_val = hex_list[i]
                    if hex_val >= 0x30 and hex_val <= 0x3a:
                        build_str += '{' + self.sysfnt_data_json['Characters'][hex_val - 0x30] + '}'
                    elif hex_val == 0x40:
                        build_str += '{' + self.sysfnt_data_json['Characters'][11] + '}'
                    elif hex_val == 0x50:
                        build_str += '{' + self.sysfnt_data_json['Characters'][12] + '}'
                    elif hex_val == 0x60:
                        build_str += '{' + self.sysfnt_data_json['Characters'][13] + '}'
                    else:
                        build_str += "{{x03{:02x}}}".format(hex_val)
                else:
                    build_str += "{x03}"
            elif hex_val == 0x04:  # {Var0}, {Var00} et {Varb0}
                i += 1
                if i < hex_size:
                    hex_val = hex_list[i]
                    if hex_val >= 0x20 and i <= 0x27:
                        build_str += "{{Var{:02x}}}".format(hex_val - 0x20)
                    elif hex_val >= 0x30 and i <= 0x37:
                        build_str += "{{Var0{:02x}}}".format(hex_val - 0x30)
                    elif hex_val >= 0x40 and i <= 0x47:
                        build_str += "{{Varb{:02x}}}".format(hex_val - 0x40)
                    else:
                        build_str += "{{x04{:02x}}}".format(hex_val)

                else:
                    build_str += "{x04}"
            elif hex_val == 0x05:  # {Icons}
                i += 1
                if i < hex_size:
                    hex_val = hex_list[i]
                    if hex_val >= 0x20 and hex_val <= 0x5d:
                        build_str += '{' + self.sysfnt_data_json['Icons'][hex_val - 0x20] + '}'
                    else:
                        build_str += "{{x05{:02x}}}".format(hex_val)
                else:
                    build_str += "{x05}"
            elif hex_val == 0x06:  # {Color}
                i += 1
                if i < hex_size:
                    hex_val = hex_list[i]
                    if hex_val >= 0x20 and hex_val <= 0x2f:
                        build_str += '{' + self.sysfnt_data_json['Colors'][hex_val - 0x20] + '}'
                    else:
                        build_str += "{{x06{:02x}}}".format(hex_val)
                else:
                    build_str += "{x06}"
            elif hex_val == 0x09:  # {Wait000}
                i += 1
                if i < hex_size:
                    hex_val = hex_list[i]
                    if hex_val >= 0x20:
                        build_str += "{{Wait{:03}}}".format(hex_val - 0x20)
                    else:
                        build_str += "{{x09{:02x}}}".format(hex_val)
                else:
                    build_str += "{x06}"
            elif hex_val == 0x0b:  # {cursor_location}
                i += 1
                if i < hex_size:
                    if cursor_location_size == 2:
                        hex_val = hex_list[i]
                        build_str += "{{Cursor_location_id:0x{:02x}}}".format(hex_val)
                    if cursor_location_size == 3:
                        hex_val1 = hex_list[i]
                        i += 1
                        hex_val2 = hex_list[i]
                        build_str += "{{Cursor_location_id:0x{:02x}{:02x}}}".format(hex_val1, hex_val2)
                else:
                    build_str += "{x0b}"
            elif hex_val == 0x0c:  # {GuardianForce}
                i += 1
                if i < hex_size:
                    hex_val = hex_list[i]
                    if hex_val >= 0x60 and hex_val <= 0x6f:
                        build_str += '{' + self.sysfnt_data_json['GuardianForce'][hex_val - 0x60] + '}'
                    else:
                        build_str += "{{x0c{:02x}}}".format(hex_val)
                else:
                    build_str += "{x0c}"
            elif hex_val == 0x0e:  # {Location}
                i += 1
                if i < hex_size:
                    hex_val = hex_list[i]
                    if hex_val >= 0x20 and hex_val <= 0x27:
                        build_str += '{' + self.sysfnt_data_json['Locations'][hex_val - 0x20] + '}'
                    else:
                        build_str += "{{x0e{:02x}}}".format(hex_val)
                else:
                    build_str += "{x0e}"
            elif hex_val >= 0x19 and hex_val <= 0x1b:  # jp19, jp1a, jp1b
                i += 1
                if i < hex_size:
                    old_hex_val = hex_val
                    hex_val = hex_list[i]
                    if hex_val >= 0x20:
                        character = None  # To be changed, caract(index, oldIndex-0x18);
                    else:
                        character = None
                    if not character:
                        character = "{{x{:02x}{:02x}}}".format(old_hex_val, hex_val)
                    build_str += character
                else:
                    build_str += "{{x{:02x}}}".format(hex_val)
            elif hex_val == 0x1c:  # addJp
                i += 1
                if i < hex_size:
                    hex_val = hex_list[i]
                    if hex_val >= 0x20:
                        build_str += "{{Jp{:03}}}".format(hex_val - 0x20)
                    else:
                        build_str += "{{x1c{:02x}}}".format(hex_val)
                else:
                    build_str += "{x1c}"
            elif hex_val >= 0x03 and hex_val <= 0x1f:
                i += 1
                if i < hex_size:
                    build_str += "{{x{:02x}{:02x}}}".format(hex_val, hex_list[i])
                else:
                    build_str += "{{x{:02x}}}".format(hex_val)
            else:
                character = self.translate_hex_to_str_table[hex_val]
                if not character:
                    character = "{{x{:02x}}}".format(hex_val)
                build_str += character
            i += 1

        return build_str

    def load_all(self):
        self.load_monster_data()
        self.load_sysfnt_data()
        self.load_item_data()
        self.load_devour_data()
        self.load_gforce_data()
        self.load_stat_data()
        self.load_status_data()
        self.load_kernel_data()
        self.load_card_data()
        self.load_mngrp_data()
        self.load_exe_data()
        self.load_ai_data()
        self.load_magic_data()
        self.load_enemy_abilities_data()
        self.load_special_action_data()
        self.load_anim_sequence_data()
        self.load_field_data()
        self.load_draw_data()


if __name__ == "__main__":
    # To be able to read a file and write back in a file
    file_to_load = "FF8_EN.exe"  # Fill with the file you want. use os.path.join if it is in folder
    file_export = "export.txt"  # The file to write the final string back
    print("Loading core data engine")
    game_data = GameData(".")
    # game_data.load_all() # This load all data if you want to test further, not just text translation

    print(f"Reading the file: {file_to_load}")
    current_file_data = bytearray()
    with open(file_to_load, "rb") as in_file:
        while el := in_file.read(1):
            current_file_data.extend(el)

    # Ignoring not wanted values (for example only alphabet)
    # EOL => 0x00
    # 0-> 9 => 0x21 -> 0x2a
    # A -> œ => 0x45 -> 0xa7
    # {in} -> {ag} => 0xe8 -> 0xff
    print("Limiting to specific characters")
    transformed_file = bytearray()
    for byte in current_file_data:
        if byte == 0 or 0x21 <= byte <= 0x2a or 0x45 <= byte <= 0xa7 or 0xe8 <= byte <= 0xff:
            transformed_file.append(byte)

    current_file_data = transformed_file
    zero_as_slash_n_param = True
    print(f"Transforming the byte data into ff8 string and considering byte 0 (end of string) as a \\n: {zero_as_slash_n_param}")
    ff8_string = game_data.translate_hex_to_str(current_file_data, zero_as_slash_n_param)
    print("File translated")
    # line_break = 200 # To define how often we return to line (for increase readability)
    # print(f"Now breaking the line every {line_break} characters")
    # ff8_string = '\n'.join(ff8_string[i:i + line_break] for i in range(0, len(ff8_string), line_break))
    # print("Now removing the multiple \\n")
    # Now removing the multiple following \n
    # new_string = ""
    # for index, char in enumerate(ff8_string):
    #     if index % 1000 == 0:
    #         print(index)
    #     if index < len(ff8_string) - 1:
    #         if char == '\n' and ff8_string[index + 1] == '\n':
    #             continue
    #     new_string += char
    # ff8_string = new_string

    print(f"Now writing in export file: {file_export}")
    with open(file_export, "w", encoding="utf-8") as in_file:
        in_file.write(ff8_string)

    print("Enjoy !")
