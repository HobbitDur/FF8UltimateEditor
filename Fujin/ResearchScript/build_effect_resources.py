"""Validate IDA resource symbols against the audited English PE and emit editable spans.

Usage: python Fujin/ResearchScript/build_effect_resources.py extracted_files/FF8_EN.exe
No game bytes or decompiled source are included in the generated manifest.
"""
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDITED_SHA256 = "064d466b5fe2ba901fd44abf19f37c0fd6a2db40aabd95c9e5959195b6589570"


def build(exe, symbols):
    if hashlib.sha256(exe).hexdigest() != AUDITED_SHA256:
        raise ValueError("Use the audited English 2013 Steam executable to generate addresses")
    resources = []
    for symbol in symbols:
        name, address = symbol["name"], int(symbol["address"], 16)
        offset = address - 0x400000
        effect = int(re.search(r"(?:MAG|GF)(\d{3})", name)[1])
        if name.endswith("ModelContainer"):
            count, *directory = struct.unpack_from("<6I", exe, offset)
            if count != 4 or directory[0] != 24 or directory != sorted(directory):
                raise ValueError(f"Invalid model directory: {name}")
            size, kind = directory[-1], "model"
        else:
            magic, flags = struct.unpack_from("<II", exe, offset)
            if magic != 16 or flags & ~11:
                raise ValueError(f"Invalid TIM: {name}")
            end = offset + 8
            for _ in range(2 if flags & 8 else 1):
                length, _x, _y, width, height = struct.unpack_from("<I4H", exe, end)
                if length != 12 + width * height * 2:
                    raise ValueError(f"Invalid TIM dimensions: {name}")
                end += length
            size, kind = end - offset, "texture"
        raw = exe[offset:offset + size]
        if len(raw) != size:
            raise ValueError(f"Truncated native resource: {name}")
        resources.append(dict(id=name, effect_ids=[effect], kind=kind,
                              address=f"0x{address:X}", file_offset=offset, size=size,
                              sha256=hashlib.sha256(raw).hexdigest()))
    parameters = json.loads(Path(__file__).with_name("effect_camera_parameters.json").read_text(encoding="utf-8"))["parameters"]
    for parameter in parameters:
        entry = dict(parameter)
        offset = int(entry["address"], 16) - 0x400000
        size = struct.calcsize("<" + entry["fmt"])
        guard_offset = int(entry["instruction_address"], 16) - 0x400000
        guard = bytes.fromhex(entry["instruction_hex"])
        if exe[guard_offset:guard_offset+len(guard)] != guard or not guard_offset <= offset < offset+size <= guard_offset+len(guard):
            raise ValueError(f"Native camera operand does not match: {entry['id']}")
        entry.update(kind="camera_parameter", file_offset=offset, size=size,
                     sha256=hashlib.sha256(exe[offset:offset+size]).hexdigest())
        resources.append(entry)
    return dict(schema_version=1, exe_sha256=AUDITED_SHA256, language="EN",
                provenance="Named IDA model/TIM symbols, validated directories and TIM dimensions; "
                           "addresses map to file offset VA - 0x400000 in this PE.",
                resources=sorted(resources, key=lambda r: r["file_offset"]))


if __name__ == "__main__":
    symbols = json.loads(Path(__file__).with_name("effect_resource_symbols.json").read_text(encoding="utf-8"))["symbols"]
    manifest = build(Path(sys.argv[1]).read_bytes(), symbols)
    target = ROOT / "FF8GameData/Resources/json/effect_resources.json"
    target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Validated {len(manifest['resources'])} native resources -> {target}")
