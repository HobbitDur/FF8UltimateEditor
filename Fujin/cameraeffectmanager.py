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

An effect that starts no camera at all (5 Phoenix Down, 7 Mega Phoenix, Scan, Defend...) can be
given one: FFNx starts an effect_NNN.bcam right after such an effect starts (FFNx #1047, "Add").
Fujin creates it from another effect's track or from a minimal one; it has no exe address, so it
lives only as a .bcam. Only the item/command effects known to be camera-less are offered: many
effects with no track move the camera with their own code (GF summons, Shot, Duel, Zell's
finishers, Angelo, Gilgamesh...), and a camera added there would fight it.
A .bcam file read back (load_bcam) becomes that effect's track: an override of its exe track, or a
created camera.
"""
import json
import os
import re
import struct
from dataclasses import dataclass, field

from FF8GameData.dat.cameracollection import build_default_animation, parse_camera_collection, NB_SLOT_PER_SET
from FF8GameData.dat.cameratrack import (CAM_MAX_SIZE, CAM_POINTER_COUNT, HEADER, SCRIPT_OFFSET,  # noqa: F401
                                         CameraScriptTools, split_script, CameraTrack as _CameraTrack)
from FF8GameData.dat.sequencevm import camera_sequence_vm
from FF8GameData.packagepath import RESOURCES_JSON_FOLDER

DATA_FILE = "effect_camera.json"
IMAGE_BASE = 0x400000
HEXT_BYTES_PER_LINE = 16
CAM_FFNX_FOLDER = "direct/exe"  # where FFNx reads them, in the game folder
CAM_EXTENSION = ".bcam"  # not .cam: that is already the FF8 movie camera format

# Effects that start no camera and do not move it with their own code: a camera can be created for
# them (items and commands). 5/7 cast like Life (35), whose camera is the natural start.
CREATABLE_CAMERA_EFFECTS = (5, 7, 40, 53, 58, 59, 183, 292, 293, 294, 295, 296)
DEFAULT_CAMERA_SOURCE = {5: 35, 7: 35}
MINIMAL_SCRIPT = b"\x00\x00\x02"     # play(0), end_clear(): the shortest vanilla scripts (85 The End)
CAM_FILE_PATTERN = re.compile(r"effect_(\d{3})\.bcam", re.IGNORECASE)

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


@dataclass
class CameraTrack(_CameraTrack):
    """One effect's camera track, as read from the exe and as edited (its parts: FF8GameData.dat.cameratrack)."""
    effect_id: int
    name: str
    label: str                 # its name in the IDA database (MAG001_CURE_cameraAnim)
    address: int               # in the opened exe (its language)
    push_operand: int          # where the effect's code stores the track address
    same_as: list = field(default_factory=list)  # other effects whose track has the same bytes

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
    def created(self) -> bool:
        """A camera made for an effect that has none in the exe (no address): .bcam only."""
        return not self.address

    def replace_bytes(self, data: bytes, vm):
        """Take a whole track (a .bcam file) as this track's content - its header may differ from the
        exe's. All or nothing: ValueError, and the track unchanged, when FFNx would refuse it."""
        error = cam_track_error(bytes(data))
        if error is not None:
            raise ValueError(f"effect {self.effect_id}: {error}")
        _count, _script_offset, keyframe_offset, _size = HEADER.unpack_from(data)
        script, padding = split_script(vm, bytes(data[SCRIPT_OFFSET:keyframe_offset]))
        collection = parse_camera_collection(bytearray(data[keyframe_offset:]))
        if bytes(collection.get_bytes()) != bytes(data[keyframe_offset:]):
            raise ValueError(f"effect {self.effect_id}: the keyframes do not fill the track exactly")
        self.header, self.script, self.padding, self.collection = bytes(data[:SCRIPT_OFFSET]), script, padding, collection

    @property
    def fits_exe(self) -> bool:
        """Still the exe's size and layout: it can go into the exe (.hext). Otherwise only a .bcam can use it."""
        return self.current_size == self.size

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


class CameraEffectManager(CameraScriptTools):
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
        """The exe's tracks are read (created cameras alone do not count)."""
        return any(not track.created for track in self.tracks.values())

    def created_tracks(self) -> dict:
        return {effect_id: track for effect_id, track in self.tracks.items() if track.created}

    @property
    def language_name(self) -> str:
        return LANGUAGE_NAMES[self.language]

    def effect_ids(self) -> list:
        """Every effect id with a name (1-345), with or without a camera track."""
        return sorted(effect_id for effect_id in self.effect_names if effect_id > 0)

    def camera_kind(self, effect_id: int) -> str:
        track = self.tracks.get(effect_id)
        if track is not None and track.created:
            return "created"
        if track is not None or any(entry["effect_id"] == effect_id for entry in self.data["tracks"]):
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
        self.tracks = {**self.created_tracks(), **tracks}    # created cameras do not depend on the exe

    def close(self):
        self.tracks = self.created_tracks()
        self.language = None
        self.exe_path = ""

    # ------------------------------------------------------------------ created cameras
    def can_create(self, effect_id: int) -> bool:
        return effect_id in CREATABLE_CAMERA_EFFECTS and effect_id not in self.tracks

    @staticmethod
    def minimal_track_bytes() -> bytes:
        """A ready-to-edit track: play(0) then end_clear(), one set whose slot 0 is a 2-keyframe
        camera (the default animation of the track editor)."""
        from FF8GameData.dat.cameracollection import _serialize
        collection = bytes(_serialize([[(object(), build_default_animation())]
                                       + [(None, None)] * (NB_SLOT_PER_SET - 1)]))
        script = MINIMAL_SCRIPT + b"\0" * (len(MINIMAL_SCRIPT) % 2)
        keyframe_offset = SCRIPT_OFFSET + len(script)
        return HEADER.pack(CAM_POINTER_COUNT, SCRIPT_OFFSET, keyframe_offset,
                           keyframe_offset + len(collection)) + script + collection

    def _created_track(self, effect_id: int, data: bytes) -> CameraTrack:
        track = CameraTrack(effect_id=effect_id, name=self.effect_names.get(effect_id, ""),
                            label="created camera (.bcam only)", address=0, push_operand=0, original=b"")
        track.replace_bytes(data, self.vm)
        return track

    def create_track(self, effect_id: int, source_effect: int = None) -> CameraTrack:
        """Give a camera-less effect a camera: a copy of `source_effect`'s track as it is now (edits
        included), or the minimal track. It is .bcam only (no exe address)."""
        if not self.can_create(effect_id):
            raise ValueError(f"effect {effect_id} cannot get a created camera")
        if source_effect is None:
            data = self.minimal_track_bytes()
        else:
            source = self.tracks.get(source_effect)
            if source is None:
                raise ValueError(f"effect {source_effect} has no camera track to copy (open the exe)")
            data = source.to_bytes()
        track = self._created_track(effect_id, data)
        self.tracks[effect_id] = track
        return track

    def remove_track(self, effect_id: int):
        """Drop a created camera (an exe track is only reset)."""
        track = self.tracks.get(effect_id)
        if track is not None and track.created:
            del self.tracks[effect_id]

    # ------------------------------------------------------------------ .bcam import
    def load_bcam(self, effect_id: int, data: bytes) -> CameraTrack:
        """A .bcam file as `effect_id`'s camera: it overrides the exe track (still a .hext edit
        when it keeps the exe's size and layout, else .bcam only), or becomes a created camera.
        ValueError with the reason, nothing changed, when FFNx would refuse the file."""
        if effect_id not in self.effect_names or effect_id <= 0:
            raise ValueError(f"no effect {effect_id}")
        track = self.tracks.get(effect_id)
        if track is None:
            track = self._created_track(effect_id, data)
            self.tracks[effect_id] = track
        else:
            track.replace_bytes(data, self.vm)
        return track

    def load_bcam_files(self, paths):
        """Read effect_NNN.bcam files, each opened by the user (never the files of a folder).
        Returns ([loaded effect ids], [(path, reason)])."""
        loaded, refused = [], []
        for path in paths:
            match = CAM_FILE_PATTERN.fullmatch(os.path.basename(path))
            if match is None:
                refused.append((path, "not named effect_NNN.bcam (NNN = the effect id), so no effect to load it on"))
                continue
            try:
                with open(path, "rb") as file:
                    data = file.read()
                self.load_bcam(int(match.group(1)), data)
            except (OSError, ValueError, struct.error) as error:
                refused.append((path, str(error)))
                continue
            loaded.append(int(match.group(1)))
        return loaded, refused

    # ------------------------------------------------------------------ editing
    def track(self, effect_id: int):
        return self.tracks.get(effect_id)

    def modified_tracks(self) -> list:
        return [track for _effect_id, track in sorted(self.tracks.items()) if track.modified]

    def reset_track(self, effect_id: int):
        track = self.tracks[effect_id]
        if track.created:
            self.remove_track(effect_id)
            return
        track._set_parts(track.original, self.vm)

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

    def all_cam_files(self, tracks=None) -> list:
        """[(effect_NNN.bcam, bytes)] of `tracks` (default: every modified track), every one checked
        before the caller writes any. ValueError naming the first FFNx would refuse."""
        tracks = self.modified_tracks() if tracks is None else tracks
        return [(cam_file_name(track.effect_id), self.cam_bytes(track)) for track in tracks]

    # ------------------------------------------------------------------ 30 fps (FFNx)
    def convert_tracks_to_real30(self, effect_ids=None, factor: int = 2) -> list:
        """Convert every loaded camera track (the exe's, the created ones, the .bcam read back) or
        `effect_ids` for FFNx True30FPS, which plays every battle camera at 30 Hz with no marker:
        keyframe durations x factor, script waits (FF8GameData/dat/camera30.py). Each track all or
        nothing. Vanilla tracks keep their size, so they still go into the .hext as well as .bcam.
        Returns [(effect id, CameraConversionReport or None, message)]."""
        from FF8GameData.dat import camera30
        result = []
        for effect_id in sorted(self.tracks if effect_ids is None else effect_ids):
            track = self.tracks.get(effect_id)
            if track is None:
                result.append((effect_id, None, "no camera track"))
                continue
            message = ("looks already converted (every keyframe duration is even): converted again"
                       if camera30.track_looks_converted(track, factor) else "")
            report = camera30.CameraConversionReport()
            try:
                camera30.convert_track(self.vm, track, factor, report)
            except ValueError as error:
                result.append((effect_id, None, f"not converted: {error}"))
                continue
            if not track.created and not track.fits_exe:
                message = (message + "; " if message else "") + "grew: .bcam only"
            result.append((effect_id, report, message))
        return result

    # ------------------------------------------------------------------ hext
    def hext_text(self) -> str:
        """The .hext of every edited track that still fits the exe (FFNx applies it to the running
        game). A resized track cannot go into the exe: it is only listed, for its .bcam file."""
        lines = [f"#Fujin camera effect patch for the {self.language_name} FF8 exe - "
                 "addresses differ in the other languages, do not use it with them.",
                 f"+{IMAGE_BASE:X}", ""]
        for track in self.resized_tracks():
            if track.created:
                lines.append(f"#Effect {track.effect_id} {track.name}: created camera (no exe track), not in "
                             f"this patch - use its effect_{track.effect_id:03d}.bcam")
                continue
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
