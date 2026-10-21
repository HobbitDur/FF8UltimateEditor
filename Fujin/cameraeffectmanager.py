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

An edited track that keeps its exe size (a script no longer than the exe's, filled up when
shorter; the same keyframe layout) goes into the exe as a .hext that FFNx applies to the running
game; the .hext only fits the language of the exe it was made from, so it says which one it is for.
The exe has no free room after a track, so a track that grew (a longer script, keyframes or
animations added) - or shrank - no longer fits it: the header is rebuilt from the parts, and the
track can only be used as a .bcam file.

One effect's track exported as a .bcam file is the track bytes as the exe stores them: FFNx loads
<direct_mode_path>/exe/effect_NNN.bcam instead of the exe's track, with no size
limit (FFNx docs/ff8/mods/effect_camera.md). Tracks are the same in every language, so a .bcam
works with every exe.
"""
import json
import re
import struct
from dataclasses import dataclass, field

from FF8GameData.dat.cameracollection import parse_camera_collection
from FF8GameData.dat.sequencecodec import code_to_sequence, sequence_to_code
from FF8GameData.dat.sequencecommand import is_jump, is_jump_int16, read_sequence
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
CAM_FFNX_FOLDER = "direct/exe"  # where FFNx reads them, in the game folder
CAM_EXTENSION = ".bcam"  # not .cam: that is already the FF8 movie camera format

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
    exe_script_size: int = 0   # the script's length in the exe
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
        if not self.exe_script_size:
            self.exe_script_size = len(script)

    @property
    def size(self) -> int:
        """The track's size in the exe: the room it has there."""
        return len(self.original)

    @property
    def current_size(self) -> int:
        return len(self.to_bytes())

    @property
    def fits_exe(self) -> bool:
        """Still the exe's size and layout: it can go into the exe (.hext). Otherwise only a .bcam can use it."""
        return self.current_size == self.size

    @property
    def script_room(self) -> int:
        """Bytes the script may use in the exe: its exe length (the padding byte stays apart)."""
        return self.exe_script_size

    def to_bytes(self) -> bytes:
        """The track as it is now. The header is rebuilt from the parts: the keyframes start on
        an even offset (one zero byte after an odd script), the size field is the whole track."""
        padding = self.padding if len(self.script) == self.exe_script_size else b"\0" * (len(self.script) % 2)
        keyframe_offset = SCRIPT_OFFSET + len(self.script) + len(padding)
        collection = bytes(self.collection.get_bytes())
        count = struct.unpack_from("<H", self.header)[0]
        return (HEADER.pack(count, SCRIPT_OFFSET, keyframe_offset, keyframe_offset + len(collection))
                + self.script + padding + collection)

    def set_collection(self, data):
        """Replace the keyframe collection (a structural edit: its size may change)."""
        self.collection = parse_camera_collection(bytearray(data))

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
    """The name FFNx looks for: effect_NNN.bcam, NNN = the effect id (1 = Cure)."""
    return f"effect_{effect_id:03d}{CAM_EXTENSION}"


def cam_track_error(data: bytes):
    """Why FFNx would ignore this .bcam file, or None when it loads it. The same checks as
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
        """Replace the script from code. A shorter script is filled up to its exe length after its
        last command (an end() for an odd byte, then nop(0)s), which never runs since the script
        stops before, so the track still fits the exe. A longer one makes the track grow: it no
        longer fits the exe, only a .bcam file can use it. Returns the filler size."""
        script = bytes(code_to_sequence(self.vm, code))
        filler = max(0, track.script_room - len(script))
        track.script = script + b"\x01" * (filler % 2) + b"\x09\x00" * (filler // 2)
        return filler

    def script_without_filler(self, script: bytes) -> bytes:
        """`script` without the trailing nop(0)s that fill it up (set_script_code, fit_track_to_size):
        room the keyframes can use in a fixed-size track. Nops a jump lands on are kept."""
        commands, address = [], 0
        for command in read_sequence(self.vm, script):
            parameters = bytes(command.parameters or b"")
            commands.append((address, command.op_code, parameters))
            address += 1 + len(parameters)
        if address != len(script):
            return bytes(script)  # not plain commands to the end: leave it as it is
        cut = len(script)
        for start, op_code, parameters in reversed(commands):
            if (op_code, parameters) != (0x09, b"\x00"):
                break
            cut = start
        for start, op_code, parameters in commands:
            if is_jump(op_code):
                offset = struct.unpack("<h" if is_jump_int16(op_code) else "<b", parameters)[0]
                if start + offset >= cut:
                    cut = max(cut, start + offset + 2)
        return bytes(script[:min(cut, len(script))])

    @staticmethod
    def fixed_script_room(track: CameraTrack, size: int) -> int:
        """Bytes left for the script when the track must be `size` bytes with its current keyframes."""
        return size - SCRIPT_OFFSET - len(track.collection.get_bytes())

    def fit_track_to_size(self, track: CameraTrack, script: bytes, size: int) -> int:
        """Lay `script` and the track's current keyframes out in exactly `size` bytes, for a track
        stored in a fixed room (a MAG section). The script is filled up after its last command like
        set_script_code. ValueError, the track unchanged, when they need more than `size`. Returns
        the filler size. An odd filler starts with the zero alignment byte before the keyframes,
        as the game files store it, so an unchanged script lays out as it was read."""
        room = self.fixed_script_room(track, size)
        if len(script) > room:
            raise ValueError(f"the script and the keyframes need {len(script) - room} more bytes "
                             f"than the camera's {size}")
        if (SCRIPT_OFFSET + room) % 2:
            raise ValueError("the keyframes would not start on an even offset")
        filler = room - len(script)
        track.script = bytes(script) + b"\x09\x00" * (filler // 2)
        track.padding = b"\0" * (filler % 2)
        track.exe_script_size = len(track.script)
        return filler

    def resized_tracks(self) -> list:
        """The edited tracks whose size changed: they no longer fit the exe (.bcam only)."""
        return [track for track in self.modified_tracks() if not track.fits_exe]

    # ------------------------------------------------------------------ .bcam (FFNx)
    @staticmethod
    def cam_bytes(track: CameraTrack) -> bytes:
        """The track as it is now (edits included), as an FFNx effect_NNN.bcam file."""
        data = track.to_bytes()
        error = cam_track_error(data)
        if error is not None:
            raise ValueError(f"effect {track.effect_id}: FFNx would ignore this track ({error})")
        return data

    # ------------------------------------------------------------------ hext
    def hext_text(self) -> str:
        """The .hext of every edited track that still fits the exe (FFNx applies it to the running
        game). A resized track cannot go into the exe: it is only listed, for its .bcam file."""
        lines = [f"#Fujin camera effect patch for the {self.language_name} FF8 exe - "
                 "addresses differ in the other languages, do not use it with them.",
                 f"+{IMAGE_BASE:X}", ""]
        for track in self.resized_tracks():
            lines.append(f"#Effect {track.effect_id} {track.name}: resized to {track.current_size} bytes "
                         f"(exe room {track.size}), not in this patch - use its effect_{track.effect_id:03d}.bcam")
        if self.resized_tracks():
            lines.append("")
        for track in self.modified_tracks():
            if not track.fits_exe:
                continue
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
        images = {effect_id: bytearray(track.to_bytes()) for effect_id, track in self.tracks.items()
                  if track.fits_exe}
        touched = set()
        for address, data in writes:
            track = next((track for track in self.tracks.values()
                          if track.address <= address and address + len(data) <= track.address + track.size), None)
            if track is None:
                raise ValueError(f"0x{address:X} is not inside a camera track of this {self.language_name} exe "
                                 "(a .hext made for another language, or not a camera patch)")
            if track.effect_id not in images:
                raise ValueError(f"effect {track.effect_id} was resized: it no longer fits the exe, reset it "
                                 "before applying a .hext over it")
            offset = address - track.address
            images[track.effect_id][offset:offset + len(data)] = data
            touched.add(track.effect_id)
        # Check every touched track before changing any, so a refused .hext leaves the tracks as they were.
        checked = {}
        for effect_id in touched:
            track = self.tracks[effect_id]
            check = CameraTrack(effect_id=effect_id, name=track.name, label=track.label, address=track.address,
                                push_operand=track.push_operand, original=track.original,
                                exe_script_size=track.exe_script_size)
            check._set_parts(bytes(images[effect_id]), self.vm)
            checked[effect_id] = check
        for effect_id, check in checked.items():
            track = self.tracks[effect_id]
            track.header, track.script, track.padding, track.collection = (
                check.header, check.script, check.padding, check.collection)
        return len(touched)
