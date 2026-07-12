"""
Parser for FF8 field character models: .mch files (main_chr.fs) and chara.one
containers (one per field). Produces the same data structures as the battle
.dat analyser (monsterdata), so the Ifrit3D viewer works on them unchanged.

Format references:
- FF8ModdingWiki: Field File Format/FileFormat_MCH.md and FileFormat_ONE.md
- ff8_mch Blender add-on by Shunsq/julianxhokaxhiu (GPLv3), used as reference
  implementation for the binary layouts.

Layout summary:
- d0xx.mch (main characters): TIM offset list (u32s until 0xFFFFFFFF), u32
  model data offset, then TIMs and model data. Field animations for main
  characters are NOT in the mch: each field's chara.one stores them.
- chara.one: u32 model count, then per-model headers (data offset/size, TIM
  offsets, model data offset, name). NPC models are stored inline as
  header-less MCH model data; main characters are stored as a name reference
  plus their animations for that field.
"""
from typing import List, Optional

from PIL import Image

from FF8GameData.monsterdata import (
    BoneSection, Bone, GeometrySection, ObjectData, VerticesData, Vertex,
    GeometryTriangle, GeometryQuad, UV, AnimationSection, Animation,
    AnimationFrame, RotationType, PositionType, Matrix4x4,
)

MCH_TRIANGLE_OPCODE = 0x25010607
MCH_QUAD_OPCODE = 0x2d010709
MCH_BONE_SIZE = 64
MCH_FACE_SIZE = 64
MCH_VERTEX_SIZE = 8
MCH_SKIN_SIZE = 8
# chara.one main-character entries store the model scale in the 0xd0 flag
# dword; NPC entries have no scale field and use the default.
DEFAULT_MODEL_SCALE = 256.0
# Viewer position scale: mch animation offsets are in 1/256 world units and
# vertices are normalized to 1/256 units too, so /2048 matches Vertex.SCALE.
POSITION_VIEWER_SCALE = 1.0 / 2048.0


def _u32(data, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 4], byteorder='little')


def _u16(data, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 2], byteorder='little')


def _s16(data, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 2], byteorder='little', signed=True)


def _signed12(value: int) -> int:
    """12-bit two's complement (full circle is 4096)."""
    return value - 0x1000 if value >= 0x800 else value


class TimImage:
    """A decoded TIM texture (PIL RGBA image plus VRAM placement info)."""

    def __init__(self, image: Image.Image, bpp: int, image_x: int, image_y: int):
        self.image = image
        self.bpp = bpp
        self.image_x = image_x
        self.image_y = image_y

    def __repr__(self):
        return f"TimImage({self.image.width}x{self.image.height}, bpp:{self.bpp}, vram:({self.image_x},{self.image_y}))"


def decode_tim(data, offset: int) -> Optional[TimImage]:
    """Decode a TIM texture into a PIL RGBA image (first palette row)."""
    if offset + 8 > len(data) or _u32(data, offset) != 0x10:
        return None
    flags = _u32(data, offset + 4)
    bpp = flags & 0x3  # 0: 4bpp, 1: 8bpp, 2: 16bpp
    has_clut = bool(flags & 0x8)
    pos = offset + 8

    palette = None
    if has_clut:
        clut_size = _u32(data, pos)
        nb_colors = _u16(data, pos + 8)
        palette = []
        color_pos = pos + 12
        for i in range(nb_colors):
            color = _u16(data, color_pos + i * 2)
            red = (color & 0x1F) << 3
            green = ((color >> 5) & 0x1F) << 3
            blue = ((color >> 10) & 0x1F) << 3
            alpha = 0 if color == 0 else 255
            palette.append((red, green, blue, alpha))
        pos += clut_size

    image_x = _u16(data, pos + 4)
    image_y = _u16(data, pos + 6)
    width_16bit = _u16(data, pos + 8)
    height = _u16(data, pos + 10)
    pixel_pos = pos + 12

    if bpp == 0:
        width = width_16bit * 4
    elif bpp == 1:
        width = width_16bit * 2
    else:
        width = width_16bit
    if width <= 0 or height <= 0 or width > 1024 or height > 1024:
        return None

    rgba = bytearray(width * height * 4)
    if bpp == 0 and palette:
        for i in range(width * height // 2):
            byte = data[pixel_pos + i]
            for half, index in enumerate((byte & 0x0F, byte >> 4)):
                red, green, blue, alpha = palette[index]
                out = (i * 2 + half) * 4
                rgba[out:out + 4] = bytes((red, green, blue, alpha))
    elif bpp == 1 and palette:
        for i in range(width * height):
            red, green, blue, alpha = palette[data[pixel_pos + i] % len(palette)]
            out = i * 4
            rgba[out:out + 4] = bytes((red, green, blue, alpha))
    elif bpp == 2:
        for i in range(width * height):
            color = _u16(data, pixel_pos + i * 2)
            out = i * 4
            rgba[out] = (color & 0x1F) << 3
            rgba[out + 1] = ((color >> 5) & 0x1F) << 3
            rgba[out + 2] = ((color >> 10) & 0x1F) << 3
            rgba[out + 3] = 0 if color == 0 else 255
    else:
        return None

    image = Image.frombytes('RGBA', (width, height), bytes(rgba))
    return TimImage(image, bpp, image_x, image_y)


class FieldModel:
    """A parsed field model, exposing the monsterdata sections the 3D viewer uses."""

    def __init__(self):
        self.name = ""
        self.bone_data = BoneSection()
        self.geometry_data = GeometrySection()
        self.animation_data = AnimationSection()
        self.tim_images: List[TimImage] = []
        self.nb_unknown_faces = 0
        # Model data header offsets (relative to model data start)
        self.anim_offset = 0
        self.tex_anim_offset = 0
        self.tex_anim_size = 0


def parse_model_data(data, base: int, vertex_scale_factor: float = 1.0) -> FieldModel:
    """Parse header-less MCH model data starting at `base`.

    vertex_scale_factor normalizes vertices so that bone lengths (1/256 world
    units) and vertices share the same unit: raw * 256 / character_scale.
    """
    model = FieldModel()

    nb_bones = _u32(data, base)
    nb_vertices = _u32(data, base + 0x04)
    model.tex_anim_size = _u32(data, base + 0x08)
    nb_faces = _u32(data, base + 0x0C)
    nb_skins = _u32(data, base + 0x14)
    bone_offset = _u32(data, base + 0x20)
    vertex_offset = _u32(data, base + 0x24)
    model.tex_anim_offset = _u32(data, base + 0x28)
    face_offset = _u32(data, base + 0x2C)
    skin_offset = _u32(data, base + 0x34)
    model.anim_offset = _u32(data, base + 0x38)

    if nb_bones > 512 or nb_vertices > 100000 or nb_faces > 100000:
        raise ValueError(f"Model data at {hex(base)} looks invalid "
                         f"(bones:{nb_bones}, vertices:{nb_vertices}, faces:{nb_faces})")

    # --- Bones (64 bytes each: parent u16 1-based, +8: length s16) ---
    model.bone_data.nb_bone = nb_bones
    for i in range(nb_bones):
        bone_pos = base + bone_offset + i * MCH_BONE_SIZE
        bone = Bone()
        raw_parent = _u16(data, bone_pos)
        bone.parent_id = 0xFFFF if raw_parent == 0 else raw_parent - 1
        bone.set_size_raw(_s16(data, bone_pos + 8))
        model.bone_data.bones.append(bone)

    # --- Vertices (8 bytes: x, y, z s16 + 2 unknown) ---
    vertices = []
    for i in range(nb_vertices):
        vertex_pos = base + vertex_offset + i * MCH_VERTEX_SIZE
        vertex = Vertex()
        # Same slot convention as the .dat analyser: _x=file x, _z=file y, _y=file z
        vertex._x = round(_s16(data, vertex_pos) * vertex_scale_factor)
        vertex._z = round(_s16(data, vertex_pos + 2) * vertex_scale_factor)
        vertex._y = round(_s16(data, vertex_pos + 4) * vertex_scale_factor)
        vertices.append(vertex)

    # --- Skin objects (8 bytes: first vertex u16, count u16, bone u16 1-based) ---
    skins = []
    for i in range(nb_skins):
        skin_pos = base + skin_offset + i * MCH_SKIN_SIZE
        first = _u16(data, skin_pos)
        count = _u16(data, skin_pos + 2)
        raw_bone = _u16(data, skin_pos + 4)
        bone_id = 0 if raw_bone == 0 else raw_bone - 1
        skins.append((first, count, bone_id))
    skins.sort(key=lambda skin: skin[0])

    object_data = ObjectData()
    covered = 0
    for first, count, bone_id in skins:
        if first > covered:  # gap: bind unclaimed vertices to the root bone
            object_data.vertices_data.append(_make_vertices_data(0, vertices[covered:first]))
        vertices_data = _make_vertices_data(bone_id, vertices[first:first + count])
        object_data.vertices_data.append(vertices_data)
        covered = max(covered, first + count)
    if covered < nb_vertices:
        object_data.vertices_data.append(_make_vertices_data(0, vertices[covered:]))
    object_data.nb_vertices_data = len(object_data.vertices_data)

    # --- Faces (64 bytes each) ---
    for i in range(nb_faces):
        face_pos = base + face_offset + i * MCH_FACE_SIZE
        opcode = _u32(data, face_pos)
        indexes = [_u16(data, face_pos + 0x0C + 2 * j) for j in range(4)]
        uvs = []
        for j in range(4):
            uv = UV()
            uv._u = data[face_pos + 0x2C + 2 * j]
            uv._v = data[face_pos + 0x2C + 2 * j + 1]
            uvs.append(uv)
        tex_group = _u16(data, face_pos + 0x36)

        if opcode == MCH_TRIANGLE_OPCODE:
            triangle = GeometryTriangle()
            triangle.vertex_indexes = indexes[:3]
            # get_triangles_with_uv pairs vta with index[2], vtb with [0], vtc with [1]
            triangle.vta = uvs[2]
            triangle.vtb = uvs[0]
            triangle.vtc = uvs[1]
            triangle.tex_id_1 = tex_group
            triangle.tex_id_2 = tex_group
            object_data.triangles.append(triangle)
        elif opcode == MCH_QUAD_OPCODE:
            quad = GeometryQuad()
            quad.vertex_indexes = indexes
            quad.vta, quad.vtb, quad.vtc, quad.vtd = uvs
            quad.tex_id_1 = tex_group
            quad.tex_id_2 = tex_group
            object_data.quads.append(quad)
        else:
            model.nb_unknown_faces += 1
    object_data.nb_triangle = len(object_data.triangles)
    object_data.nb_quad = len(object_data.quads)

    model.geometry_data.nb_object = 1
    model.geometry_data.object_data = [object_data]
    model.geometry_data.end = nb_vertices
    return model


def _make_vertices_data(bone_id: int, vertices: List[Vertex]) -> VerticesData:
    vertices_data = VerticesData()
    vertices_data.bone_id = bone_id
    vertices_data.nb_vertices = len(vertices)
    vertices_data.vertices = vertices
    return vertices_data


def _make_position(raw_group) -> List[PositionType]:
    """Map a file (a, b, c) translation to viewer axes.

    File order is (depth, x, up) — like the vertex axes but with the first two
    swapped. Viewer mapping mirrors Vertex.get_list(): (-x, up, -depth).
    """
    file_a, file_b, file_c = raw_group
    position = []
    for raw, sign in ((file_b, -1.0), (file_c, 1.0), (file_a, -1.0)):
        position_type = PositionType(0, raw)
        position_type.scale = sign * POSITION_VIEWER_SCALE
        position.append(position_type)
    return position


def parse_packed_animation_section(data, offset: int, nb_model_bones: int,
                                   end: Optional[int] = None) -> AnimationSection:
    """Parse a field animation section (chara.one format, Vehek's layout):
    u16 animation count, then per animation: u16 frame count, u16 bone count,
    frames of 3 s16 offsets + bone count * 4 packed bytes (12-bit rotations).
    """
    section = AnimationSection()
    if end is None:
        end = len(data)
    if offset + 2 > end:
        return section
    nb_animations = _u16(data, offset)
    pos = offset + 2
    for _ in range(nb_animations):
        if pos + 4 > end:
            break
        nb_frames = _u16(data, pos)
        nb_anim_bones = _u16(data, pos + 2)
        pos += 4
        frame_size = 6 + 4 * nb_anim_bones
        if nb_frames > 1000 or nb_anim_bones > 512 or pos + nb_frames * frame_size > end:
            break
        animation = Animation()
        for _ in range(nb_frames):
            frame = AnimationFrame(nb_model_bones)
            frame.position = _make_position((_s16(data, pos), _s16(data, pos + 2), _s16(data, pos + 4)))
            pos += 6
            for bone_index in range(nb_anim_bones):
                byte_1, byte_2, byte_3, byte_4 = data[pos:pos + 4]
                pos += 4
                rot_z = _signed12((byte_1 | ((byte_4 & 0x03) << 8)) << 2)
                rot_x = _signed12((byte_2 | ((byte_4 & 0x0C) << 6)) << 2)
                rot_y = _signed12((byte_3 | ((byte_4 & 0x30) << 4)) << 2)
                if bone_index < nb_model_bones:
                    frame.rotation_vector_data[bone_index] = [
                        RotationType(True, 0, rot_x),
                        RotationType(True, 0, rot_y),
                        RotationType(True, 0, rot_z),
                    ]
            for bone_index in range(nb_anim_bones, nb_model_bones):
                frame.rotation_vector_data[bone_index] = [
                    RotationType(True, 0, 0),
                    RotationType(True, 0, 0),
                    RotationType(True, 0, 0),
                ]
            animation.frames.append(frame)
        section.animations.append(animation)
    section.nb_animations = len(section.animations)
    return section


def parse_uncompressed_animation_section(data, offset: int, nb_model_bones: int,
                                         end: Optional[int] = None) -> AnimationSection:
    """Parse the animation section embedded in main_chr .mch files:
    u16 animation count, then per animation: u16 frame count, u16 bone count,
    frames of 3 s16 offsets + bone count * 3 u16 rotations (4096 = full circle).
    Usually a single rest-pose animation.
    """
    section = AnimationSection()
    if end is None:
        end = len(data)
    if offset + 2 > end:
        return section
    nb_animations = _u16(data, offset)
    pos = offset + 2
    for _ in range(nb_animations):
        if pos + 4 > end:
            break
        nb_frames = _u16(data, pos)
        nb_anim_bones = _u16(data, pos + 2)
        pos += 4
        frame_size = 6 + 6 * nb_anim_bones
        if nb_frames > 1000 or nb_anim_bones > 512 or pos + nb_frames * frame_size > end:
            break
        animation = Animation()
        for _ in range(nb_frames):
            frame = AnimationFrame(nb_model_bones)
            frame.position = _make_position((_s16(data, pos), _s16(data, pos + 2), _s16(data, pos + 4)))
            pos += 6
            for bone_index in range(nb_anim_bones):
                rot_x = _s16(data, pos)
                rot_y = _s16(data, pos + 2)
                rot_z = _s16(data, pos + 4)
                pos += 6
                if bone_index < nb_model_bones:
                    frame.rotation_vector_data[bone_index] = [
                        RotationType(True, 0, rot_x),
                        RotationType(True, 0, rot_y),
                        RotationType(True, 0, rot_z),
                    ]
            for bone_index in range(nb_anim_bones, nb_model_bones):
                frame.rotation_vector_data[bone_index] = [
                    RotationType(True, 0, 0),
                    RotationType(True, 0, 0),
                    RotationType(True, 0, 0),
                ]
            animation.frames.append(frame)
        section.animations.append(animation)
    section.nb_animations = len(section.animations)
    return section


def flip_root_matrix(matrix):
    """180-degree rotation around X: field models are stored upside down
    compared to the battle .dat convention the viewer uses. Negating the
    matrix rows for Y and Z flips the root; children inherit it since they
    are composed from their parent's world matrix."""
    matrix.M21, matrix.M22, matrix.M23, matrix.M42 = -matrix.M21, -matrix.M22, -matrix.M23, -matrix.M42
    matrix.M31, matrix.M32, matrix.M33, matrix.M43 = -matrix.M31, -matrix.M32, -matrix.M33, -matrix.M43


def _field_local_matrix(rotations) -> Matrix4x4:
    """Field skeletons compose bone rotations as Y * (Z * X) (verified against
    in-game poses), while battle .dat models use Z * (Y * X)."""
    x_rot = Matrix4x4.CreateRotationX(-rotations[0].get_rotate_deg())
    y_rot = Matrix4x4.CreateRotationY(-rotations[1].get_rotate_deg())
    z_rot = Matrix4x4.CreateRotationZ(-rotations[2].get_rotate_deg())
    local = Matrix4x4.MultiplyColumnMajor(z_rot, x_rot)
    return Matrix4x4.MultiplyColumnMajor(y_rot, local)


def set_field_bone_matrix(frame: AnimationFrame, bones: List[Bone], bone_id: int):
    """Field-model version of AnimationFrame.set_bone_matrix (different euler
    order plus the root flip). Parents must be computed before children."""
    local = _field_local_matrix(frame.rotation_vector_data[bone_id])
    parent_id = bones[bone_id].parent_id
    if parent_id != 0xFFFF:
        parent_mat = frame.bone_matrices[parent_id]
        world = Matrix4x4.MultiplyRowMajor(parent_mat, local)
        parent_size = bones[parent_id].get_size()
        world.M41 = parent_mat.M13 * parent_size + parent_mat.M41
        world.M42 = parent_mat.M23 * parent_size + parent_mat.M42
        world.M43 = parent_mat.M33 * parent_size + parent_mat.M43
        frame.bone_matrices[bone_id] = world
    else:
        local.M41 = local.M42 = local.M43 = 0.0
        frame.bone_matrices[bone_id] = local
        flip_root_matrix(frame.bone_matrices[bone_id])


def compute_frame_matrices(frame: AnimationFrame, bones: List[Bone]):
    """Build world-space bone matrices for one frame."""
    for bone_id in range(len(bones)):
        set_field_bone_matrix(frame, bones, bone_id)


def compute_animation_matrices(animation_section: AnimationSection, bone_section: BoneSection):
    """Build world-space bone matrices for every frame (what the viewer consumes)."""
    for animation in animation_section.animations:
        for frame in animation.frames:
            compute_frame_matrices(frame, bone_section.bones)


class MchFile:
    """A main_chr d0xx.mch file: TIM offset list, model data offset, then content."""

    def __init__(self, data):
        self.data = data
        self.tim_offsets: List[int] = []
        pos = 0
        while pos + 4 <= len(data):
            value = _u32(data, pos)
            pos += 4
            if value == 0xFFFFFFFF:
                break
            self.tim_offsets.append(value)
        else:
            raise ValueError("Not a valid MCH file (no TIM offset terminator)")
        self.model_address = _u32(data, pos)
        if self.model_address + 0x40 > len(data):
            raise ValueError("Not a valid MCH file (model data offset out of range)")

    def build_model(self, character_scale: float = DEFAULT_MODEL_SCALE) -> FieldModel:
        factor = DEFAULT_MODEL_SCALE / character_scale if character_scale else 1.0
        model = parse_model_data(self.data, self.model_address, factor)
        model.tim_images = [tim for tim in
                            (decode_tim(self.data, offset) for offset in self.tim_offsets)
                            if tim is not None]
        model.animation_data = parse_uncompressed_animation_section(
            self.data, self.model_address + model.anim_offset, model.bone_data.nb_bone)
        compute_animation_matrices(model.animation_data, model.bone_data)
        return model


class CharaOneEntry:
    def __init__(self):
        self.index = 0
        self.name = ""
        self.data_offset = 0  # absolute offset of the model textures + data block
        self.size = 0
        self.is_main = False  # main character: model comes from main_chr d0xx.mch
        self.scale_raw = 0  # raw scale (main characters only); world scale = raw / 16
        self.tim_offsets: List[int] = []  # absolute offsets
        self.model_offset = 0  # absolute offset of the model data (NPC only)

    def get_scale(self) -> float:
        if self.is_main and self.scale_raw:
            return self.scale_raw / 16.0
        return DEFAULT_MODEL_SCALE

    def __repr__(self):
        kind = "main" if self.is_main else "npc"
        return (f"CharaOneEntry({self.index}:{self.name} [{kind}] data:{hex(self.data_offset)} "
                f"size:{hex(self.size)} tims:{len(self.tim_offsets)})")


def _is_model_name(raw: bytes) -> bool:
    """4-char model names like d000, p065, n002, o028."""
    return len(raw) == 4 and all(0x30 <= b <= 0x7A and b != 0x3F for b in raw)


class CharaOne:
    """A field chara.one container.

    Two layouts exist in the PC files:
    - headered: u32 model count then per-model headers (most fields). Optional
      fields vary per file: duplicated size, model name, 0xEEEEEEEE marker.
    - headerless: u32 EOF then raw TIM and model-data chunks back to back
      (PS-style layout kept for some fields). Parsed by signature scanning.
    """

    def __init__(self, data):
        self.data = data
        self.entries: List[CharaOneEntry] = []
        first_dword = _u32(data, 0)
        if first_dword == len(data):
            self._parse_headerless()
        elif first_dword <= 64:
            self._parse_headered(first_dword)
        else:
            raise ValueError(f"Not a valid chara.one file (first dword: {hex(first_dword)})")

    def _parse_headered(self, nb_models: int):
        data = self.data
        pos = 4
        for i in range(nb_models):
            entry = CharaOneEntry()
            entry.index = i
            # PC version: data offsets are relative to just after the model count
            entry.data_offset = _u32(data, pos) + 4
            entry.size = _u32(data, pos + 4)
            pos += 8
            if _u32(data, pos) == entry.size:  # optional duplicated size field
                pos += 4
            flag = _u32(data, pos)
            if flag >> 24 == 0xd0:
                entry.is_main = True
                entry.scale_raw = (flag >> 8) & 0xFFFF
                pos += 4
                pos += 4  # model data offset field (always 0 for main models)
            else:
                while _u32(data, pos) != 0xFFFFFFFF:
                    entry.tim_offsets.append(_u32(data, pos) + entry.data_offset)
                    pos += 4
                    if pos + 4 > len(data):
                        raise ValueError("Not a valid chara.one file (unterminated TIM list)")
                pos += 4
                entry.model_offset = _u32(data, pos) + entry.data_offset
                pos += 4
            # Optional: 4-char model name + 4 unknown bytes
            if _is_model_name(bytes(data[pos:pos + 4])):
                entry.name = bytes(data[pos:pos + 4]).decode('ascii')
                pos += 8
            else:
                entry.name = f"model{i}"
            if _u32(data, pos) == 0xEEEEEEEE:  # optional end marker
                pos += 4
            self.entries.append(entry)

    def _parse_headerless(self):
        """Scan raw TIM / model-data chunks (PS-style layout, uncompressed on PC)."""
        data = self.data
        end = len(data)
        pos = 4
        pending_tims = []
        while pos + 8 <= end:
            if _u32(data, pos) == 0x10 and _u32(data, pos + 4) in (0x02, 0x03, 0x08, 0x09):
                pending_tims.append(pos)
                pos = self._tim_end(pos)
                continue
            chunk_end = self._next_signature(pos + 4)
            entry = CharaOneEntry()
            entry.index = len(self.entries)
            entry.name = f"model{entry.index}"
            entry.data_offset = pos
            entry.size = chunk_end - pos
            entry.tim_offsets = pending_tims
            entry.model_offset = pos
            pending_tims = []
            self.entries.append(entry)
            pos = chunk_end

    def _tim_end(self, offset: int) -> int:
        pos = offset + 8
        if _u32(self.data, offset + 4) & 0x8:  # CLUT block
            pos += _u32(self.data, pos)
        pos += _u32(self.data, pos)  # image block (size includes its header)
        return pos

    def _next_signature(self, offset: int) -> int:
        """Find the next TIM signature (4-aligned) or end of file."""
        data = self.data
        pos = (offset + 3) & ~3
        while pos + 8 <= len(data):
            if _u32(data, pos) == 0x10 and _u32(data, pos + 4) in (0x02, 0x03, 0x08, 0x09):
                return pos
            pos += 4
        return len(data)

    def build_npc_model(self, entry: CharaOneEntry) -> FieldModel:
        if entry.is_main:
            raise ValueError(f"{entry.name} is a main character reference, use build_main_model")
        model = parse_model_data(self.data, entry.model_offset, 1.0)
        model.name = entry.name
        model.tim_images = [tim for tim in
                            (decode_tim(self.data, offset) for offset in entry.tim_offsets)
                            if tim is not None]
        end = entry.data_offset + entry.size
        model.animation_data = parse_packed_animation_section(
            self.data, entry.model_offset + model.anim_offset, model.bone_data.nb_bone, end)
        compute_animation_matrices(model.animation_data, model.bone_data)
        return model

    def build_main_model(self, entry: CharaOneEntry, mch_data) -> FieldModel:
        """Combine a main_chr .mch (geometry/textures) with this field's animations."""
        mch_file = MchFile(mch_data)
        model = parse_model_data(mch_file.data, mch_file.model_address,
                                 DEFAULT_MODEL_SCALE / entry.get_scale())
        model.name = entry.name
        model.tim_images = [tim for tim in
                            (decode_tim(mch_file.data, offset) for offset in mch_file.tim_offsets)
                            if tim is not None]
        end = entry.data_offset + entry.size
        model.animation_data = parse_packed_animation_section(
            self.data, entry.data_offset, model.bone_data.nb_bone, end)
        compute_animation_matrices(model.animation_data, model.bone_data)
        return model
