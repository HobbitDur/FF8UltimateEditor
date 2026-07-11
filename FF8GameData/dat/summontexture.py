"""Import a summon/magic (magXXX_x.dat) TIM texture into a monster .dat.

Summon model files (e.g. mag184_e.dat for Shiva) reference their texture at the
VRAM location where the summon uploads it during the cinematic: the geometry's
tex_id_1 is a PSX CLUT id (vram_x/16 + vram_y*64) and tex_id_2 a texture page id
(bits 0-3: x/64, bit 4: y>=256, bits 5-6: semi-transparency, bit 7+: color depth)
pointing somewhere inside the raw TIM file that ships next to the model
(e.g. mag184_d.dat).

A battle monster instead embeds its textures as 128x128 8bpp TIMs in section 11,
uploaded at VRAM (640,0), (640,128), (704,0), ... with one CLUT row per TIM at
(0,224), (0,225), ...

This module bridges the two: it reads which (CLUT, texture page, top/bottom half)
combinations the loaded geometry actually uses, extracts those 128x128 blocks and
palette rows from the raw summon TIM, rebuilds them as monster-convention TIMs in
section 11, and remaps every triangle/quad tex id accordingly (UVs are unchanged).
"""
import struct
from typing import Dict, List, Tuple

MONSTER_IMAGE_VRAM_X = 640   # first texture page column, in VRAM halfwords
MONSTER_CLUT_VRAM_Y = 224    # first CLUT row
PAGE_WIDTH_HW = 64           # a texture page is 64 halfwords = 128 pixels in 8bpp
PAGE_HEIGHT = 256
TIM_HEIGHT = 128             # monster TIMs stack two 128px halves per page column


class SummonTextureError(Exception):
    pass


def clut_id_to_vram(clut_id: int) -> Tuple[int, int]:
    return (clut_id & 0x3F) * 16, clut_id >> 6


def vram_to_clut_id(x: int, y: int) -> int:
    return (x // 16) | (y << 6)


class RawTim:
    """Minimal parser for a standalone 8bpp TIM file (e.g. mag184_d.dat)."""

    def __init__(self, data: bytes):
        if data[:4] != b"\x10\x00\x00\x00":
            raise SummonTextureError("The selected file is not a TIM texture (bad magic).")
        flag = struct.unpack_from("<I", data, 4)[0]
        if (flag & 0x7) != 1 or not (flag & 0x8):
            raise SummonTextureError("Only 8bpp TIMs with a CLUT are supported "
                                     f"(flag=0x{flag:x}).")
        clut_len, self.clut_x, self.clut_y, clut_w, clut_h = struct.unpack_from("<IHHHH", data, 8)
        self.clut_rows = [data[20 + r * clut_w * 2: 20 + (r + 1) * clut_w * 2]
                          for r in range(clut_h)]
        p = 8 + clut_len
        _img_len, self.image_x, self.image_y, img_w_hw, self.image_h = struct.unpack_from("<IHHHH", data, p)
        self.image_w = img_w_hw * 2  # 8bpp: 2 texels per VRAM halfword
        self.pixels = data[p + 12: p + 12 + self.image_w * self.image_h]

    def pixel_block(self, vram_x_hw: int, vram_y: int, w_px: int, h: int) -> bytes:
        """Extract a pixel block addressed in VRAM coordinates."""
        col = (vram_x_hw - self.image_x) * 2
        row = vram_y - self.image_y
        if col < 0 or row < 0 or col + w_px > self.image_w or row + h > self.image_h:
            raise SummonTextureError(
                f"The geometry references VRAM ({vram_x_hw},{vram_y}) which is outside "
                f"this TIM (image at ({self.image_x},{self.image_y}) size "
                f"{self.image_w}x{self.image_h}). Wrong magXXX file for this model?")
        block = bytearray()
        for y in range(h):
            start = (row + y) * self.image_w + col
            block.extend(self.pixels[start:start + w_px])
        return bytes(block)

    def clut_row(self, clut_id: int) -> bytes:
        x, y = clut_id_to_vram(clut_id)
        row = y - self.clut_y
        if x != self.clut_x or row < 0 or row >= len(self.clut_rows):
            raise SummonTextureError(
                f"The geometry references CLUT id 0x{clut_id:04x} = VRAM ({x},{y}) but this "
                f"TIM holds its CLUTs at ({self.clut_x},{self.clut_y}) "
                f"({len(self.clut_rows)} rows). Wrong magXXX file for this model?")
        return self.clut_rows[row]


def build_tim_8bpp(clut_raw: bytes, clut_x: int, clut_y: int,
                   pixels: bytes, img_x: int, img_y: int, w: int, h: int) -> bytes:
    tim = bytearray()
    tim += b"\x10\x00\x00\x00"
    tim += struct.pack("<I", 0x09)  # 8bpp + CLUT
    tim += struct.pack("<IHHHH", 12 + len(clut_raw), clut_x, clut_y, len(clut_raw) // 2, 1)
    tim += clut_raw
    tim += struct.pack("<IHHHH", 12 + len(pixels), img_x, img_y, w // 2, h)
    tim += pixels
    return bytes(tim)


def _collect_texture_groups(geometry) -> Dict[Tuple[int, int], List[int]]:
    """Map every used (tpage_id, clut_id) pair to the raw V values that use it."""
    groups: Dict[Tuple[int, int], List[int]] = {}
    for obj in geometry.object_data:
        for face in list(obj.triangles) + list(obj.quads):
            uvs = [face.vta, face.vtb, face.vtc]
            if hasattr(face, "vtd"):
                uvs.append(face.vtd)
            key = (face.tex_id_2, face.tex_id_1)
            groups.setdefault(key, []).extend(uv.get_v_raw() & 0xFF for uv in uvs)
    return groups


def _build_conversion_plan(groups) -> List[dict]:
    """Decide which 128x128 block each (tpage, clut) pair becomes.

    Monster TIM i gets CLUT row (0, 224+i); its image goes to
    (640 + 128*column, 128*half) where faces with V < 128 use the top half and
    V >= 128 the bottom half of a source page.
    """
    plan = []
    for (tpage, clut), v_values in sorted(groups.items()):
        half = min(v_values) // TIM_HEIGHT
        if max(v_values) // TIM_HEIGHT != half:
            raise SummonTextureError(
                f"Faces using CLUT 0x{clut:04x} span both halves of texture page "
                f"{tpage & 0xF} — this layout cannot be expressed with one CLUT per "
                f"128x128 monster TIM.")
        plan.append({"tpage": tpage, "clut": clut, "half": half})

    used_pages = sorted({entry["tpage"] & 0x1F for entry in plan})
    for entry in plan:
        entry["col"] = used_pages.index(entry["tpage"] & 0x1F)

    seen = set()
    for entry in plan:
        slot = (entry["col"], entry["half"])
        if slot in seen:
            raise SummonTextureError(
                "Two different CLUTs are used on the same half of the same texture "
                "page — this cannot be expressed with one CLUT per monster TIM.")
        seen.add(slot)
    return plan


def _patch_geometry_tex_ids(enemy, id_mapping: Dict[Tuple[int, int], Tuple[int, int]]):
    """Rewrite tex ids in both the parsed geometry and the raw section-2 bytes."""
    sec = enemy.section_raw_data[2]
    nb_obj = struct.unpack_from("<I", sec, 0)[0]
    offsets = [struct.unpack_from("<I", sec, 4 + i * 4)[0] for i in range(nb_obj)]
    if nb_obj != len(enemy.geometry_data.object_data):
        raise SummonTextureError("Parsed geometry does not match the raw section 2 data.")

    for obj_index, off in enumerate(offsets):
        obj = enemy.geometry_data.object_data[obj_index]
        p = off + 2
        for vd in obj.vertices_data:
            p += 4 + vd.nb_vertices * 6
        p += (4 - (p - off) % 4) % 4
        p += 12  # nb_triangle, nb_quad, unknown
        for faces, stride in ((obj.triangles, 16), (obj.quads, 20)):
            for face in faces:
                new_clut, new_tpage = id_mapping[(face.tex_id_2, face.tex_id_1)]
                face.tex_id_1 = new_clut
                face.tex_id_2 = new_tpage
                struct.pack_into("<H", sec, p + 10, new_clut)
                struct.pack_into("<H", sec, p + 14, new_tpage)
                p += stride


def import_summon_tim(enemy, tim_bytes: bytes) -> int:
    """Convert a summon TIM into `enemy`'s section-11 textures and remap its
    geometry tex ids to the monster convention.  Returns the number of TIMs built.

    `enemy` is a loaded MonsterAnalyser (EntityType.MONSTER).  Its parsed geometry,
    raw section 2 and texture_data dict are updated in place; call
    write_data_to_file() afterwards to persist.
    """
    if not enemy.geometry_data.object_data:
        raise SummonTextureError("No model loaded: open a monster .dat first.")

    tim = RawTim(tim_bytes)
    groups = _collect_texture_groups(enemy.geometry_data)
    plan = _build_conversion_plan(groups)

    # Validate every reference against the TIM before touching anything
    tims = []
    id_mapping = {}
    for i, entry in enumerate(plan):
        tpage, clut, half, col = entry["tpage"], entry["clut"], entry["half"], entry["col"]
        page_x_hw = (tpage & 0xF) * PAGE_WIDTH_HW
        page_y = ((tpage >> 4) & 1) * PAGE_HEIGHT
        pixels = tim.pixel_block(page_x_hw, page_y + half * TIM_HEIGHT, TIM_HEIGHT, TIM_HEIGHT)
        clut_raw = tim.clut_row(clut)

        new_clut_id = vram_to_clut_id(0, MONSTER_CLUT_VRAM_Y + i)
        new_tpage = (tpage & 0xFFE0) | ((MONSTER_IMAGE_VRAM_X // PAGE_WIDTH_HW) + col)
        id_mapping[(tpage, clut)] = (new_clut_id, new_tpage)

        tims.append(build_tim_8bpp(
            clut_raw, 0, MONSTER_CLUT_VRAM_Y + i,
            pixels,
            MONSTER_IMAGE_VRAM_X + col * PAGE_WIDTH_HW, half * TIM_HEIGHT,
            TIM_HEIGHT, TIM_HEIGHT))

    _patch_geometry_tex_ids(enemy, id_mapping)

    # Fill section 11 (offsets are recomputed by prepare_texture on save)
    offset = 4 + len(tims) * 4 + 4
    tim_offsets = []
    for t in tims:
        tim_offsets.append(offset)
        offset += len(t)
    enemy.texture_data["nb_texture"] = len(tims)
    enemy.texture_data["tim_offset"] = tim_offsets
    enemy.texture_data["eof_texture"] = offset
    enemy.texture_data["texture_data"] = [{"id": i, "data": bytearray(t)}
                                          for i, t in enumerate(tims)]
    return len(tims)
