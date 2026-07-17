"""Convert Shiva's summon model (mag184) texture references to the battle-monster convention.

The geometry copied from mag184_e.dat references the texture the way the summon
uploads it to VRAM: mag184_d.dat's image lives at tpage 13 (VRAM x 832, y 256)
with CLUTs at (320,224) and (320,225).  A c0mXXX monster instead uploads its
section-11 TIMs at VRAM (640,0)/(640,128) with CLUTs at (0,224)/(0,225).

This script:
  1. cuts the 128x256 strip the model actually uses out of mag184_d.dat and
     rebuilds it as two 128x128 8bpp TIMs with monster VRAM coordinates;
  2. patches every triangle/quad tex id in section 2:
        tex_id_1 (CLUT id) : 0x3814 -> 0x3800, 0x3854 -> 0x3840
        tex_id_2 (tpage id): 0x00bd -> 0x00aa
  3. writes both TIMs into section 11 (same 16928-byte size, so the patch is
     fully in-place and no header offset changes).

Run from the repo root:  python shiva_convert.py
"""
import shutil
import struct
import sys
from pathlib import Path

BASE = Path(__file__).parent
SHIVA_DAT = BASE / "Shiva.dat"
MAG_D = BASE / "extracted_files" / "battle" / "mag184_d.dat"

# CLUT id = vram_x/16 + vram_y*64 ; tpage id = x/64 | (y>=256)<<4 | blend<<5 | 8bpp<<7
CLUT_MAP = {0x3814: 0x3800, 0x3854: 0x3840}
TPAGE_MAP = {0x00BD: 0x00AA}

# The model reads tpage 13 = VRAM halfwords 832..895.  mag184_d's image starts
# at halfword 704, so that is pixel columns (832-704)*2 = 256..383 of the image.
SRC_PIXEL_X = 256
STRIP_W = 128


def read_mag_d_strip():
    data = MAG_D.read_bytes()
    if data[:4] != b"\x10\x00\x00\x00":
        sys.exit(f"{MAG_D} is not a TIM file")
    clut_len, _cx, _cy, cw, ch = struct.unpack_from("<IHHHH", data, 8)
    clut_rows = [data[20 + r * cw * 2: 20 + (r + 1) * cw * 2] for r in range(ch)]
    p = 8 + clut_len
    _img_len, _ix, _iy, iw, ih = struct.unpack_from("<IHHHH", data, p)
    w = iw * 2  # 8bpp: 2 texels per VRAM halfword
    pixels = data[p + 12: p + 12 + w * ih]
    strip = bytearray()
    for y in range(ih):
        strip.extend(pixels[y * w + SRC_PIXEL_X: y * w + SRC_PIXEL_X + STRIP_W])
    return clut_rows, strip  # strip is 128x256, rows top to bottom


def build_tim_8bpp(clut_raw, clut_x, clut_y, pixels, img_x, img_y, w, h):
    tim = bytearray()
    tim += b"\x10\x00\x00\x00"                      # magic
    tim += struct.pack("<I", 0x09)                   # 8bpp + CLUT
    tim += struct.pack("<IHHHH", 12 + len(clut_raw), clut_x, clut_y, len(clut_raw) // 2, 1)
    tim += clut_raw
    tim += struct.pack("<IHHHH", 12 + len(pixels), img_x, img_y, w // 2, h)
    tim += pixels
    return tim


def patch_geometry(sec: bytearray):
    """Remap tex ids in-place; returns (nb_patched, counters per value)."""
    nb_obj = struct.unpack_from("<I", sec, 0)[0]
    offsets = [struct.unpack_from("<I", sec, 4 + i * 4)[0] for i in range(nb_obj)]
    patched = 0
    for off in offsets:
        p = off
        nb_vd = struct.unpack_from("<H", sec, p)[0]
        p += 2
        for _ in range(nb_vd):
            _bone, nbv = struct.unpack_from("<HH", sec, p)
            p += 4 + nbv * 6
        p += (4 - (p - off) % 4) % 4
        nb_tri, nb_quad = struct.unpack_from("<HH", sec, p)
        p += 12
        for count, stride in ((nb_tri, 16), (nb_quad, 20)):
            for _ in range(count):
                for field_off, mapping in ((10, CLUT_MAP), (14, TPAGE_MAP)):
                    old = struct.unpack_from("<H", sec, p + field_off)[0]
                    if old not in mapping:
                        sys.exit(f"Unexpected tex id 0x{old:04x} at section offset {p + field_off} "
                                 f"(already converted, or not the mag184_e geometry?)")
                    struct.pack_into("<H", sec, p + field_off, mapping[old])
                p += stride
                patched += 1
    return patched


def main():
    raw = bytearray(SHIVA_DAT.read_bytes())
    nb_section = struct.unpack_from("<I", raw, 0)[0]
    if nb_section != 11:
        sys.exit(f"Expected 11 sections in {SHIVA_DAT}, found {nb_section}")
    pos = [struct.unpack_from("<I", raw, 4 + i * 4)[0] for i in range(nb_section)]
    file_size = struct.unpack_from("<I", raw, 4 + nb_section * 4)[0]
    sec2_start, sec2_end = pos[1], pos[2]
    sec11_start, sec11_end = pos[10], file_size

    # 1. Build the two monster TIMs from mag184_d
    clut_rows, strip = read_mag_d_strip()
    tim_top = build_tim_8bpp(clut_rows[0], 0, 224, strip[:128 * 128], 640, 0, 128, 128)
    tim_bottom = build_tim_8bpp(clut_rows[1], 0, 225, strip[128 * 128:], 640, 128, 128, 128)

    # 2. Rebuild section 11 and check it fits exactly in place
    sec11 = bytearray()
    sec11 += struct.pack("<I", 2)                              # nb_texture
    sec11 += struct.pack("<II", 16, 16 + len(tim_top))         # TIM offsets
    sec11 += struct.pack("<I", 16 + len(tim_top) + len(tim_bottom))  # eof
    sec11 += tim_top + tim_bottom
    if len(sec11) != sec11_end - sec11_start:
        sys.exit(f"Section 11 size mismatch: built {len(sec11)}, "
                 f"existing {sec11_end - sec11_start} — aborting, nothing written")

    # 3. Patch geometry tex ids
    sec2 = raw[sec2_start:sec2_end]
    patched = patch_geometry(sec2)

    backup = SHIVA_DAT.with_suffix(".dat.bak")
    if not backup.exists():
        shutil.copy2(SHIVA_DAT, backup)
        print(f"Backup written to {backup.name}")

    raw[sec2_start:sec2_end] = sec2
    raw[sec11_start:sec11_end] = sec11
    SHIVA_DAT.write_bytes(raw)
    print(f"Patched {patched} faces (tex ids remapped to monster convention)")
    print(f"Wrote 2 TIMs: image VRAM (640,0)+(640,128), CLUTs (0,224)+(0,225)")
    print(f"{SHIVA_DAT.name} updated ({len(raw)} bytes, size unchanged)")


if __name__ == "__main__":
    main()
