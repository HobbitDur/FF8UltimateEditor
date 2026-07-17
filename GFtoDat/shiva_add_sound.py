"""Splice the sound sections (9 and 10) of a donor monster into the Shiva .dat.

An empty section 9 is abnormal: every valid vanilla monster has one (the engine
reads the AKAO sound table unconditionally), so a 0-byte section is a likely
in-game crash. The donor is the vanilla owner of the tested slot, c0m071
(G-Soldier), whose sounds fit the encounters that reference this slot.

Run from the repo root:  python shiva_add_sound.py
"""
import shutil
import struct
import sys
from pathlib import Path

BASE = Path(__file__).parent
TARGET = BASE / "c0m071.dat"
DONOR = BASE / "extracted_files" / "battle" / "c0m071.dat"

NB_SECTION = 11
HEADER_SIZE = 4 + NB_SECTION * 4 + 4  # 52


def read_sections(path: Path):
    data = path.read_bytes()
    nb = struct.unpack_from("<I", data, 0)[0]
    if nb != NB_SECTION:
        sys.exit(f"{path.name}: expected {NB_SECTION} sections, found {nb}")
    pos = [struct.unpack_from("<I", data, 4 + i * 4)[0] for i in range(nb)]
    fsize = struct.unpack_from("<I", data, 4 + nb * 4)[0]
    bounds = pos + [fsize]
    return [data[bounds[i]:bounds[i + 1]] for i in range(nb)]  # sections 1..11


def main():
    target_sections = read_sections(TARGET)
    donor_sections = read_sections(DONOR)

    if len(target_sections[8]) or len(target_sections[9]):
        sys.exit(f"{TARGET.name} already has sound data "
                 f"(s9={len(target_sections[8])}, s10={len(donor_sections[9])} bytes) — aborting.")

    target_sections[8] = donor_sections[8]   # section 9: sound (AKAO table)
    target_sections[9] = donor_sections[9]   # section 10: sound related
    print(f"Donor {DONOR.name}: section 9 = {len(donor_sections[8])} bytes, "
          f"section 10 = {len(donor_sections[9])} bytes")

    out = bytearray()
    out += struct.pack("<I", NB_SECTION)
    position = HEADER_SIZE
    for sec in target_sections:
        out += struct.pack("<I", position)
        position += len(sec)
    out += struct.pack("<I", position)  # file size
    for sec in target_sections:
        out += sec

    backup = TARGET.with_suffix(".dat.before_sound.bak")
    if not backup.exists():
        shutil.copy2(TARGET, backup)
        print(f"Backup written to {backup.name}")
    TARGET.write_bytes(bytes(out))
    print(f"{TARGET.name} written ({len(out)} bytes)")


if __name__ == "__main__":
    main()
