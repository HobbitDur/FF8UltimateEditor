r"""Build FF8GameData/Resources/json/effect_camera.json from the FF8 exes (no IDA needed).

Every spell/attack effect that moves the battle camera through a static camera track calls
Battle_PlayCameraAnimation (EN 0x5099A0) with ``push <track address>`` just before the call.
This script finds those calls in the English 2013 Steam exe, reads the pushed address,
checks it points at a camera track (8-byte header, script at +8), and gives the call to the
effect whose init function is the closest one before it in MagicList_Logic (EN 0xC81770,
4 bytes per effect id, entry 0 unused).

The other languages store the same tracks a little further in the exe. For each track the
script finds the identical bytes in the FR/DE/IT/ES exe and checks that this exe's code pushes
exactly that address once. The json then keeps the English address plus one offset per
language, like exe.json does for the other exe tables (the offset is not the same for every
track in DE and ES, so it is stored per track).

Calls whose argument is not a static track (the GF cinematic VM, the victory pose, the
battle intro) read their camera from a loaded file; they are listed by effect id only.

Usage:
    python dump_effect_cameras.py FF8_EN.exe [FF8_FR.exe FF8_DE.exe FF8_IT.exe FF8_ES.exe]
        [--names attack_animation.json] [--out effect_camera.json]
The language of each extra exe is read from its file name (_FR, _DE, _IT, _ES).
"""
import argparse
import json
import os
import re
import struct

PLAY_CAMERA_EN = 0x5099A0
EFFECT_TABLE_EN = 0xC81770
EFFECT_COUNT = 346
IMAGE_BASE = 0x400000
PUSH_SEARCH_WINDOW = 256
LANGUAGES = ("fr", "de", "it", "es")


class Exe:
    def __init__(self, path):
        with open(path, "rb") as file:
            self.data = file.read()
        pe = struct.unpack_from("<I", self.data, 0x3C)[0]
        count = struct.unpack_from("<H", self.data, pe + 6)[0]
        optional = struct.unpack_from("<H", self.data, pe + 20)[0]
        self.sections = []
        for index in range(count):
            header = pe + 24 + optional + 40 * index
            name = self.data[header:header + 8].rstrip(b"\0").decode()
            virtual_size, rva, raw_size, raw_offset = struct.unpack_from("<IIII", self.data, header + 8)
            self.sections.append((name, IMAGE_BASE + rva, virtual_size, raw_offset, raw_size))

    def section(self, name):
        return next(section for section in self.sections if section[0] == name)

    def offset(self, address):
        for _name, start, virtual_size, raw_offset, raw_size in self.sections:
            if start <= address < start + virtual_size and address - start < raw_size:
                return raw_offset + address - start
        return None

    def address(self, offset):
        for _name, start, _virtual_size, raw_offset, raw_size in self.sections:
            if raw_offset <= offset < raw_offset + raw_size:
                return start + offset - raw_offset
        return None

    def u32(self, address):
        offset = self.offset(address)
        return None if offset is None else struct.unpack_from("<I", self.data, offset)[0]

    def track_header(self, address):
        """(count, script offset, keyframe offset, size) if a camera track starts here."""
        offset = self.offset(address)
        if offset is None or offset + 8 > len(self.data):
            return None
        count, script, keyframes, size = struct.unpack_from("<4H", self.data, offset)
        if 1 <= count < 16 and script == 8 and script < keyframes < size:
            return count, script, keyframes, size
        return None

    def text(self):
        _name, start, _virtual_size, raw_offset, raw_size = self.section(".text")
        return start, self.data[raw_offset:raw_offset + raw_size]


def find_camera_calls(exe):
    """[(call address, pushed track address or None)] for every call to Battle_PlayCameraAnimation."""
    start, code = exe.text()
    calls = []
    index = code.find(b"\xE8")
    while index >= 0:
        if index + 5 <= len(code):
            target = start + index + 5 + struct.unpack_from("<i", code, index + 1)[0]
            if target == PLAY_CAMERA_EN:
                calls.append((start + index, pushed_track(exe, code, index)))
        index = code.find(b"\xE8", index + 1)
    return calls


def pushed_track(exe, code, call_index):
    """The closest `push imm32` before the call whose value is a camera track."""
    low = max(0, call_index - PUSH_SEARCH_WINDOW)
    for push in range(call_index - 5, low - 1, -1):
        if code[push] == 0x68:
            value = struct.unpack_from("<I", code, push + 1)[0]
            if exe.track_header(value):
                return value
    return None


def effect_inits(exe):
    return sorted((exe.u32(EFFECT_TABLE_EN + 4 * effect_id), effect_id)
                  for effect_id in range(1, EFFECT_COUNT) if exe.u32(EFFECT_TABLE_EN + 4 * effect_id))


def owner_effect(inits, call):
    owner = None
    for init, effect_id in inits:
        if init > call:
            break
        owner = effect_id
    return owner


# Effects attack_animation.json calls "Unknown" but whose IDA init function is named.
LABEL_HINTS = {60: "RAIJIN_STRIKE", 101: "TRAUMA_GRAB"}


def slug(name):
    variants = name.split("/")
    if len(variants) == 2 and variants[1] == variants[0] + "+":   # "Potion/Potion+" -> POTION
        name = variants[0]
    return re.sub(r"[^A-Za-z0-9]+", "_", name.replace('"', "").replace("'", "")).strip("_").upper()


def push_operand(exe, value):
    """Address of the single `push value` operand in this exe's code, or None."""
    start, code = exe.text()
    needle = b"\x68" + struct.pack("<I", value)
    first = code.find(needle)
    if first < 0 or code.find(needle, first + 1) >= 0:
        return None
    return start + first + 1


def build(en_path, language_paths, names):
    exe = Exe(en_path)
    inits = effect_inits(exe)
    tracks = []
    file_camera_effects = set()
    for call, track in find_camera_calls(exe):
        effect_id = owner_effect(inits, call)
        if track is None:
            if effect_id is not None:
                file_camera_effects.add(effect_id)
            continue
        size = exe.track_header(track)[3]
        name = names.get(effect_id, "")
        label_name = LABEL_HINTS.get(effect_id) or ("" if name in ("", "Unknown") else slug(name))
        tracks.append({
            "effect_id": effect_id,
            "name": name or "Unknown",
            "label": f"MAG{effect_id:03d}_{label_name}_cameraAnim" if label_name else f"MAG{effect_id:03d}_cameraAnim",
            "eng_address": track,
            "size": size,
            "eng_push_operand": push_operand(exe, track),
        })
    tracks.sort(key=lambda entry: entry["effect_id"])

    for language, path in language_paths.items():
        other = Exe(path)
        for entry in tracks:
            blob = exe.data[exe.offset(entry["eng_address"]):][:entry["size"]]
            candidates = []
            position = other.data.find(blob)
            while position >= 0:
                address = other.address(position)
                operand = push_operand(other, address) if address is not None else None
                if operand is not None:
                    candidates.append((address, operand))
                position = other.data.find(blob, position + 1)
            if not candidates:
                raise ValueError(f"{language}: {entry['label']} not found with a single push")
            # Byte-identical tracks (Potion = Cure, ...) match each other's copy too: the
            # language only shifts data by a few hundred bytes, so take the nearest copy.
            address, operand = min(candidates, key=lambda candidate: abs(candidate[0] - entry["eng_address"]))
            entry[f"{language}_offset"] = address - entry["eng_address"]
            entry[f"{language}_push_offset"] = operand - entry["eng_push_operand"]

    def hex_fields(entry):
        return {key: (f"0x{value:X}" if isinstance(value, int) and key != "effect_id" else value)
                for key, value in entry.items()}

    return {
        "comment": "Static battle camera tracks of the spell/attack effects, located in FF8_EN.exe "
                   "(2013 Steam). eng_address = track start (VA), size = the header's size field, "
                   "eng_push_operand = the imm32 of the effect's `push` before its "
                   "Battle_PlayCameraAnimation call. <lang>_offset / <lang>_push_offset = what to add "
                   "for that language's exe. Generated by Fujin/ResearchScript/dump_effect_cameras.py.",
        "battle_play_camera_animation": f"0x{PLAY_CAMERA_EN:X}",
        "effect_table": f"0x{EFFECT_TABLE_EN:X}",
        "file_camera_effects": sorted(file_camera_effects),
        "tracks": [hex_fields(entry) for entry in tracks],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("en_exe")
    parser.add_argument("other_exes", nargs="*")
    parser.add_argument("--names", default=os.path.join(os.path.dirname(__file__), "..", "..", "FF8GameData",
                                                        "Resources", "json", "attack_animation.json"))
    parser.add_argument("--out", default="effect_camera.json")
    args = parser.parse_args()
    with open(args.names, encoding="utf-8") as file:
        names = {entry["id"]: entry["name"] for entry in json.load(file)["attack_animation"]}
    language_paths = {}
    for path in args.other_exes:
        match = re.search(r"_(FR|DE|IT|ES)\.exe$", path, re.IGNORECASE)
        if not match:
            raise SystemExit(f"cannot tell the language of {path} (expected FF8_FR.exe, ...)")
        language_paths[match.group(1).lower()] = path
    result = build(args.en_exe, language_paths, names)
    with open(args.out, "w", encoding="utf-8") as file:
        json.dump(result, file, indent=1)
        file.write("\n")
    print(f"{len(result['tracks'])} tracks, {len(result['file_camera_effects'])} file-camera effects -> {args.out}")


if __name__ == "__main__":
    main()
