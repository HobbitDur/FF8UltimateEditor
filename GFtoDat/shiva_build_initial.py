"""Build the initial Shiva.dat monster container from the GF summon model.

Recreates the first step of the mag184 -> c0m conversion pipeline (the original
script was lost): take mag184_e.dat's model sections and lay them out as an
11-section c0mXXX monster file.

  monster sec 1 (skeleton)  = mag184_e sec 1 (3328 B, 69 bones)
  monster sec 2 (geometry)  = mag184_e sec 2 (42760 B) - tex ids still summon-style
  monster sec 3 (animation) = mag184_e sec 3 (11120 B, 3 anims: 1/86/6 frames)
  monster sec 4..10         = empty (no dyn-texture/seq/camera/stat/AI/sound yet)
  monster sec 11 (textures) = zero placeholder sized for the 2 monster TIMs
                              (4 + 2*4 + 4 + 2*16928 = 33872 B) that
                              shiva_convert.py rebuilds in place right after.

mag184_e's 24-byte trailer section is dropped (summon-only texture-swap data).

Run from the repo root:  python shiva_build_initial.py
"""
import struct
import sys
from pathlib import Path

BASE = Path(__file__).parent
OUT = BASE / "GFtoDat" / "Shiva.dat" if (BASE / "GFtoDat").is_dir() else BASE / "Shiva.dat"
MAG_E = BASE / "extracted_files" / "battle" / "mag184_e.dat"

NB_SECTION = 11
TIM_SIZE = 4 + 4 + 12 + 512 + 12 + 128 * 128       # 8bpp 128x128 TIM with 1 CLUT row
SEC11_PLACEHOLDER = 4 + 2 * 4 + 4 + 2 * TIM_SIZE   # 33872


def main():
    data = MAG_E.read_bytes()
    nb = struct.unpack_from("<I", data, 0)[0]
    if nb != 4:
        sys.exit(f"{MAG_E.name}: expected 4 sections, found {nb}")
    pos = [struct.unpack_from("<I", data, 4 + i * 4)[0] for i in range(nb)]
    fsize = struct.unpack_from("<I", data, 4 + nb * 4)[0]
    bounds = pos + [fsize]
    mag_sections = [data[bounds[i]:bounds[i + 1]] for i in range(nb)]

    frame_check = struct.unpack_from("<H", mag_sections[0], 0)[0]
    if frame_check != 69:
        sys.exit(f"{MAG_E.name}: expected 69 bones, found {frame_check}")

    sections = [
        mag_sections[0],                  # 1 skeleton
        mag_sections[1],                  # 2 geometry
        mag_sections[2],                  # 3 animation
        b"",                              # 4 dynamic textures
        b"",                              # 5 animation sequences
        b"",                              # 6 camera
        b"",                              # 7 info/stat
        b"",                              # 8 AI
        b"",                              # 9 sound (AKAO)
        b"",                              # 10 sound related
        bytes(SEC11_PLACEHOLDER),         # 11 textures (placeholder)
    ]
    for i, sec in enumerate(sections):
        if len(sec) % 4:
            sys.exit(f"Section {i + 1} length {len(sec)} not 4-byte aligned")

    out = bytearray()
    out += struct.pack("<I", NB_SECTION)
    position = 4 + NB_SECTION * 4 + 4
    for sec in sections:
        out += struct.pack("<I", position)
        position += len(sec)
    out += struct.pack("<I", position)
    for sec in sections:
        out += sec

    OUT.write_bytes(bytes(out))
    print(f"{OUT} written ({len(out)} bytes)")
    print(f"Sections: " + ", ".join(str(len(s)) for s in sections))


if __name__ == "__main__":
    main()
