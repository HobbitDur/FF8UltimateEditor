r"""Data side of Fujin's Camera effect editor: the spell/attack camera tracks inside the FF8 exe.

An effect moves the battle camera by calling Battle_PlayCameraAnimation (EN 0x5099A0) with a
camera track, a block of static data in the exe's .data section. 221 effects have one, each at
its own address (FF8GameData/Resources/json/effect_camera.json, made by
Fujin/ResearchScript/dump_effect_cameras.py; the other languages store the same bytes a little
further, by the per-track offsets of that json). A track is::

    +0  u16  count            (not used by the engine for these tracks)
    +2  u16  script offset    always 8
    +4  u16  keyframe offset  start of the camera animation collection
    +6  u16  size             whole track
    +8       camera script    byte-code (camera_sequence_info.json) choosing which keyframe
                              animation plays, from the attacker, target, random values...
             padding          0 or 1 zero byte so the keyframes start on an even address
    +keyframe offset          camera animation collection (FF8GameData.dat.cameracollection)

Both offsets are relative to the track, the script jumps are relative and the engine only reads
the track (the VM writes its variables elsewhere), so a track works wherever it is stored.

Edits keep every track at its exe size (a script no longer than the exe's, filled up when shorter;
the same keyframes and header): the exe has no free room after a track. They are saved as a .hext that FFNx applies to the running game; the
.hext only fits the language of the exe it was made from, so it says which one it is for.

One effect's track can also be exported as a .cam file: the track bytes as the exe stores them,
which FFNx loads from <direct_mode_path>/battle/effect_camera/effect_NNN.cam instead of the exe's
(julianxhokaxhiu/FFNx#1047, docs/ff8/mods/effect_camera.md). Tracks are the same in every
language, so a .cam works with every exe.
"""
import json
import re
import struct
from dataclasses import dataclass, field

from FF8GameData.dat.cameracollection import parse_camera_collection
from FF8GameData.dat.sequencecodec import code_to_sequence, sequence_to_code
from FF8GameData.dat.sequencecommand import read_sequence
from FF8GameData.dat.sequenceanalyser import SequenceAnalyser
from FF8GameData.dat.sequencevm import camera_sequence_vm
from FF8GameData.packagepath import RESOURCES_JSON_FOLDER

DATA_FILE = "effect_camera.json"
IMAGE_BASE = 0x400000
HEADER = struct.Struct("<4H")
SCRIPT_OFFSET = 8
HEXT_BYTES_PER_LINE = 16
CAM_POINTER_COUNT = 2           # every track: script + keyframe collection
CAM_MAX_SIZE = 0xFFFF           # the header size field is a u16
CAM_FFNX_FOLDER = "direct/battle/effect_camera"  # where FFNx reads them, in the game folder

# exe.json "lang" value keys -> offset key prefix (None = English), like the other exe readers
_EXE_LANGUAGES = {"english_value": None, "french_value": "fr", "italian_value": "it",
                  "german_value": "de", "spanish_value": "es"}
LANGUAGE_NAMES = {None: "EN", "fr": "FR", "it": "IT", "de": "DE", "es": "ES"}


def exe_language_prefix(exe: bytes, exe_data_json: dict):
    lang = exe_data_json["lang"]
    value = exe[lang["offset"]] if len(exe) > lang["offset"] else None
    for key, prefix in _EXE_LANGUAGES.items():
        if value == lang[key]:
            return prefix
    raise ValueError("unknown FF8 exe language (EN, FR, DE, IT and ES exes are supported)")


def load_effect_camera_data() -> dict:
    with open(RESOURCES_JSON_FOLDER / DATA_FILE, encoding="utf-8") as file:
        data = json.load(file)
    for entry in data["tracks"]:
        for key, value in entry.items():
            if isinstance(value, str) and value.startswith("0x"):
                entry[key] = int(value, 16)
    return data


def load_effect_names() -> dict:
    with open(RESOURCES_JSON_FOLDER / "attack_animation.json", encoding="utf-8") as file:
        return {entry["id"]: entry["name"] for entry in json.load(file)["attack_animation"]}


def split_script(vm, script: bytes):
    """(commands, padding): the alignment byte after the last command is not code."""
    sizes = {info["op_code"]: info["size"] for info in vm.data_json["op_code_info"]}
    end = 0
    for command in read_sequence(vm, script):
        parameters = bytes(command.parameters or b"")
        if command.is_unknown() or len(parameters) < sizes.get(command.op_code, 0):
            break
        end += 1 + len(parameters)
    return script[:end], script[end:]


@dataclass
class CameraTrack:
    """One effect's camera track, as read from the exe and as edited."""
    effect_id: int
    name: str
    label: str                 # its name in the IDA database (MAG001_CURE_cameraAnim)
    address: int               # in the opened exe (its language)
    push_operand: int          # where the effect's code stores the track address
    original: bytes            # the exe's bytes
    header: bytes = b""
    script: bytes = b""        # camera script commands, without the alignment padding
    padding: bytes = b""
    collection: object = None  # CameraCollection over the keyframe part (edited in place)
    same_as: list = field(default_factory=list)  # other effects whose track has the same bytes

    @classmethod
    def from_bytes(cls, vm, data: bytes, **values):
        track = cls(original=bytes(data), **values)
        track._set_parts(data, vm)
        return track

    def _set_parts(self, data: bytes, vm):
        """Split `data` into header / script / padding / keyframes. All or nothing: on an error the
        track keeps its current parts."""
        if self.original and data[:SCRIPT_OFFSET] != self.original[:SCRIPT_OFFSET]:
            raise ValueError(f"effect {self.effect_id}: the track header (size, script and keyframe "
                             "offsets) cannot change - a track keeps its exe size and layout")
        _count, script_offset, keyframe_offset, size = HEADER.unpack_from(data)
        if script_offset != SCRIPT_OFFSET or not script_offset < keyframe_offset < size or size != len(data):
            raise ValueError(f"effect {self.effect_id}: not a camera track at 0x{self.address:X}")
        script, padding = split_script(vm, bytes(data[SCRIPT_OFFSET:keyframe_offset]))
        collection = parse_camera_collection(bytearray(data[keyframe_offset:]))
        if bytes(collection.get_bytes()) != bytes(data[keyframe_offset:]):
            raise ValueError(f"effect {self.effect_id}: the keyframes do not fill the track exactly")
        self.header, self.script, self.padding, self.collection = bytes(data[:SCRIPT_OFFSET]), script, padding, collection

    @property
    def size(self) -> int:
        return len(self.original)

    @property
    def script_room(self) -> int:
        """Bytes the script may use: its exe length (the padding byte stays apart)."""
        return len(self.script)

    def to_bytes(self) -> bytes:
        data = self.header + self.script + self.padding + bytes(self.collection.get_bytes())
        if len(data) != self.size:  # nothing should get here: every edit keeps the size
            raise ValueError(f"effect {self.effect_id}: the track is {len(data)} bytes, "
                             f"the exe has room for exactly {self.size}")
        return data

    @property
    def modified(self) -> bool:
        return self.to_bytes() != self.original

    def keyframe_count(self) -> int:
        return sum(len(block.frames) for camera_set in self.collection.sets
                   for animation in camera_set.animations for block in animation.blocks)

    def changed_runs(self):
        """[(address, bytes)] of the bytes that differ from the exe, in address order."""
        current, runs, start = self.to_bytes(), [], None
        for index in range(len(current) + 1):
            differs = index < len(current) and current[index] != self.original[index]
            if differs and start is None:
                start = index
            elif not differs and start is not None:
                runs.append((self.address + start, current[start:index]))
                start = None
        return runs


def cam_file_name(effect_id: int) -> str:
    """The name FFNx looks for: effect_NNN.cam, NNN = the effect id (1 = Cure)."""
    return f"effect_{effect_id:03d}.cam"


def cam_track_error(data: bytes):
    """Why FFNx would ignore this .cam file, or None when it loads it. The same checks as
    ff8_effect_camera_is_valid (FFNx src/ff8/battle/effect_camera.cpp)."""
    if not 0 < len(data) <= CAM_MAX_SIZE:
        return "file too big" if data else "file too small"
    if len(data) < HEADER.size:
        return "file too small"
    count, script_offset, keyframe_offset, size = HEADER.unpack_from(data)
    if count != CAM_POINTER_COUNT or script_offset != SCRIPT_OFFSET:
        return "bad header"
    if size != len(data):
        return "header size does not match the file size"
    if keyframe_offset <= script_offset or keyframe_offset + 2 > size:
        return "keyframe offset out of range"
    collection_size = size - keyframe_offset
    set_count = struct.unpack_from("<H", data, keyframe_offset)[0]
    table_size = 2 + 2 * set_count + 2
    if set_count == 0 or table_size > collection_size:
        return "bad keyframe set count"
    if struct.unpack_from("<H", data, keyframe_offset + table_size - 2)[0] != collection_size:
        return "keyframe collection size does not match the file size"
    for index in range(set_count):
        set_offset = struct.unpack_from("<H", data, keyframe_offset + 2 + 2 * index)[0]
        if not table_size <= set_offset < collection_size:
            return "keyframe set offset out of range"
    return None


class CameraEffectManager:
    def __init__(self, game_data):
        self.game_data = game_data
        if not game_data.exe_data_json:
            game_data.load_exe_data()
        if not getattr(game_data, "camera_sequence_data_json", None):
            game_data.load_camera_sequence_data()
        self.vm = camera_sequence_vm(game_data)
        self.data = load_effect_camera_data()
        self.effect_names = load_effect_names()
        self.file_camera_effects = set(self.data["file_camera_effects"])
        self.language = None
        self.tracks = {}            # effect_id -> CameraTrack
        self.exe_path = ""

    @property
    def loaded(self) -> bool:
        return bool(self.tracks)

    @property
    def language_name(self) -> str:
        return LANGUAGE_NAMES[self.language]

    def effect_ids(self) -> list:
        """Every effect id with a name (1-345), with or without a camera track."""
        return sorted(effect_id for effect_id in self.effect_names if effect_id > 0)

    def camera_kind(self, effect_id: int) -> str:
        if effect_id in self.tracks or any(entry["effect_id"] == effect_id for entry in self.data["tracks"]):
            return "track"
        if effect_id in self.file_camera_effects:
            return "file"
        return "none"

    # ------------------------------------------------------------------ loading
    def load_exe(self, path: str):
        with open(path, "rb") as file:
            self.load_exe_bytes(file.read())
        self.exe_path = path

    def load_exe_bytes(self, exe: bytes):
        language = exe_language_prefix(exe, self.game_data.exe_data_json)
        tracks = {}
        for entry in self.data["tracks"]:
            shift = entry.get(f"{language}_offset", 0) if language else 0
            push_shift = entry.get(f"{language}_push_offset", 0) if language else 0
            address = entry["eng_address"] + shift
            data = exe[address - IMAGE_BASE:address - IMAGE_BASE + entry["size"]]
            push_operand = entry["eng_push_operand"] + push_shift
            pushed = exe[push_operand - IMAGE_BASE:push_operand - IMAGE_BASE + 4]
            if len(data) != entry["size"] or pushed != struct.pack("<I", address):
                raise ValueError(f"the camera track of effect {entry['effect_id']} is not where it should be "
                                 f"in this exe (not a 2013 Steam FF8 exe, or already patched?)")
            tracks[entry["effect_id"]] = CameraTrack.from_bytes(
                self.vm, data, effect_id=entry["effect_id"], name=entry["name"], label=entry["label"],
                address=address, push_operand=push_operand)
        by_bytes = {}
        for track in tracks.values():
            by_bytes.setdefault(track.original, []).append(track.effect_id)
        for track in tracks.values():
            track.same_as = [other for other in by_bytes[track.original] if other != track.effect_id]
        self.language = language
        self.tracks = tracks

    def close(self):
        self.tracks = {}
        self.language = None
        self.exe_path = ""

    # ------------------------------------------------------------------ editing
    def track(self, effect_id: int):
        return self.tracks.get(effect_id)

    def modified_tracks(self) -> list:
        return [track for _effect_id, track in sorted(self.tracks.items()) if track.modified]

    def reset_track(self, effect_id: int):
        track = self.tracks[effect_id]
        track._set_parts(track.original, self.vm)

    def script_text(self, track: CameraTrack) -> str:
        """What the script does, one command per line (read-only description)."""
        return SequenceAnalyser(self.vm, None, bytearray(track.script)).get_text()

    def script_code(self, track: CameraTrack) -> str:
        """The script as editable code (sequencecodec syntax)."""
        return sequence_to_code(self.vm, track.script)

    def script_size(self, code: str) -> int:
        """Bytes `code` compiles to (ValueError when it does not compile)."""
        return len(code_to_sequence(self.vm, code))

    def set_script_code(self, track: CameraTrack, code: str) -> int:
        """Replace the script from code. The track cannot grow: a longer script is refused, a
        shorter one is filled up to its exe length after its last command (an end() for an odd
        byte, then nop(0)s), which never runs since the script stops before. Returns the filler size."""
        script = bytes(code_to_sequence(self.vm, code))
        filler = track.script_room - len(script)
        if filler < 0:
            raise ValueError(f"the script is {len(script)} bytes, the exe has room for "
                             f"{track.script_room}: remove {-filler} byte(s)")
        track.script = script + b"\x01" * (filler % 2) + b"\x09\x00" * (filler // 2)
        return filler

    # ------------------------------------------------------------------ .cam (FFNx)
    @staticmethod
    def cam_bytes(track: CameraTrack) -> bytes:
        """The track as it is now (edits included), as an FFNx effect_NNN.cam file."""
        data = track.to_bytes()
        error = cam_track_error(data)
        if error is not None:
            raise ValueError(f"effect {track.effect_id}: FFNx would ignore this track ({error})")
        return data

    # ------------------------------------------------------------------ hext
    def hext_text(self) -> str:
        """The .hext of every edited track (FFNx applies it to the running game)."""
        lines = [f"#Fujin camera effect patch for the {self.language_name} FF8 exe - "
                 "addresses differ in the other languages, do not use it with them.",
                 f"+{IMAGE_BASE:X}", ""]
        for track in self.modified_tracks():
            lines.append(f"#Effect {track.effect_id} {track.name}: camera track {track.label} "
                         f"at 0x{track.address:X}")
            for address, data in track.changed_runs():
                for start in range(0, len(data), HEXT_BYTES_PER_LINE):
                    chunk = data[start:start + HEXT_BYTES_PER_LINE]
                    lines.append(f"{address + start - IMAGE_BASE:X} = {chunk.hex(' ').upper()}")
            lines.append("")
        return "\n".join(lines)

    def apply_hext_text(self, text: str) -> int:
        """Re-apply a saved camera .hext over the opened exe's tracks. Returns how many tracks it
        changed. Lines that do not land inside a camera track are refused (wrong language/file)."""
        if not self.loaded:
            raise ValueError("open the FF8 exe first: the .hext is applied over its camera tracks")
        # Addresses of one language often fall inside another language's tracks too, so the
        # language written by hext_text() is what really tells them apart.
        made_for = re.search(r"for the (EN|FR|DE|IT|ES) FF8 exe", text)
        if made_for and made_for.group(1) != self.language_name:
            raise ValueError(f"this .hext was made for the {made_for.group(1)} exe, "
                             f"the opened exe is {self.language_name}")
        base, writes = 0, []
        for line_number, raw in enumerate(text.splitlines(), 1):
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            if line.startswith("+"):
                base = int(line[1:], 16)
                continue
            match = re.fullmatch(r"([0-9A-Fa-f]+)\s*=\s*((?:[0-9A-Fa-f]{2}\s*)+)", line)
            if not match:
                raise ValueError(f"line {line_number}: not an 'address = bytes' line: {raw}")
            writes.append((base + int(match.group(1), 16), bytes.fromhex(match.group(2))))
        images = {effect_id: bytearray(track.to_bytes()) for effect_id, track in self.tracks.items()}
        touched = set()
        for address, data in writes:
            track = next((track for track in self.tracks.values()
                          if track.address <= address and address + len(data) <= track.address + track.size), None)
            if track is None:
                raise ValueError(f"0x{address:X} is not inside a camera track of this {self.language_name} exe "
                                 "(a .hext made for another language, or not a camera patch)")
            offset = address - track.address
            images[track.effect_id][offset:offset + len(data)] = data
            touched.add(track.effect_id)
        # Check every touched track before changing any, so a refused .hext leaves the tracks as they were.
        checked = {}
        for effect_id in touched:
            track = self.tracks[effect_id]
            check = CameraTrack(effect_id=effect_id, name=track.name, label=track.label, address=track.address,
                                push_operand=track.push_operand, original=track.original)
            check._set_parts(bytes(images[effect_id]), self.vm)
            checked[effect_id] = check
        for effect_id, check in checked.items():
            track = self.tracks[effect_id]
            track.header, track.script, track.padding, track.collection = (
                check.header, check.script, check.padding, check.collection)
        return len(touched)
