"""A battle camera track: a camera script and the keyframe collection it plays, in one block.

Spell/attack effects (stored in the exe, Fujin), battle stages (the camera section of a0stgXXX.x,
Alexander) and r0win.dat carry the same layout::

    +0  u16  count            2 (not read by the engine)
    +2  u16  script offset    always 8
    +4  u16  keyframe offset  start of the camera animation collection
    +6  u16  size             whole track
    +8       camera script    byte-code (camera_sequence_info.json) choosing which keyframe
                              animation plays (FF8GameData.dat.camerascript)
             padding          0 or 1 zero byte so the keyframes start on an even offset
    +keyframe offset          camera animation collection (FF8GameData.dat.cameracollection)

Both offsets are relative to the track and the script jumps are relative, so a track works
wherever it is stored. CameraTrack splits one into its parts and lays them out again
(to_bytes); CameraScriptTools edits the script as code with the camera VM.
"""
import struct
from dataclasses import dataclass

from FF8GameData.dat.cameracollection import parse_camera_collection
from FF8GameData.dat.sequenceanalyser import SequenceAnalyser
from FF8GameData.dat.sequencecodec import code_to_sequence, sequence_to_code
from FF8GameData.dat.sequencecommand import is_jump, is_jump_int16, read_sequence

HEADER = struct.Struct("<4H")
SCRIPT_OFFSET = 8
CAM_POINTER_COUNT = 2           # every track: script + keyframe collection
CAM_MAX_SIZE = 0xFFFF           # the header size field is a u16


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


def read_track_parts(vm, data: bytes, what="camera track"):
    """(header, script, padding, collection) of a whole track. ValueError when it is not one."""
    if len(data) < SCRIPT_OFFSET:
        raise ValueError(f"{what}: {len(data)} bytes, shorter than a track header")
    _count, script_offset, keyframe_offset, size = HEADER.unpack_from(data)
    if script_offset != SCRIPT_OFFSET or not script_offset < keyframe_offset < size or size != len(data):
        raise ValueError(f"{what}: not a camera track (script {script_offset}, keyframes {keyframe_offset}, "
                         f"size {size} for {len(data)} bytes)")
    script, padding = split_script(vm, bytes(data[SCRIPT_OFFSET:keyframe_offset]))
    collection = parse_camera_collection(bytearray(data[keyframe_offset:]))
    if bytes(collection.get_bytes()) != bytes(data[keyframe_offset:]):
        raise ValueError(f"{what}: the keyframes do not fill the track exactly")
    return bytes(data[:SCRIPT_OFFSET]), script, padding, collection


@dataclass(kw_only=True)
class CameraTrack:
    """One camera track, as read and as edited."""
    original: bytes = b""      # the bytes it was read from
    header: bytes = b""
    script: bytes = b""        # camera script commands, without the alignment padding
    padding: bytes = b""
    collection: object = None  # CameraCollection over the keyframe part (edited in place)
    exe_script_size: int = 0   # the script's length as read: the room a shorter script is filled up to

    @classmethod
    def from_bytes(cls, vm, data: bytes, **values):
        track = cls(original=bytes(data), **values)
        track._set_parts(data, vm)
        return track

    def _set_parts(self, data: bytes, vm):
        """All or nothing: on an error the track keeps its current parts."""
        self.header, self.script, self.padding, self.collection = read_track_parts(vm, data)
        if not self.exe_script_size:
            self.exe_script_size = len(self.script)

    @property
    def size(self) -> int:
        """The track's size where it was read: the room it has there."""
        return len(self.original)

    @property
    def current_size(self) -> int:
        return len(self.to_bytes())

    @property
    def script_room(self) -> int:
        """Bytes the script may use without growing the track: its length as read."""
        return self.exe_script_size

    def to_bytes(self) -> bytes:
        """The track as it is now. The header is rebuilt from the parts: the keyframes start on
        an even offset (one zero byte after an odd script), the size field is the whole track."""
        # the stored padding while it still aligns the keyframes (a .bcam read back keeps its bytes)
        padding = (self.padding if len(self.script) == self.exe_script_size
                   or (len(self.script) + len(self.padding)) % 2 == 0 else b"\0" * (len(self.script) % 2))
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


class CameraScriptTools:
    """The camera script of a track as code, with the camera VM (self.vm, camera_sequence_vm)."""
    vm = None

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
        """Replace the script from code. A shorter script is filled up to its length as read after
        its last command (an end() for an odd byte, then nop(0)s), which never runs since the script
        stops before, so the track keeps its size. A longer one makes the track grow. Returns the
        filler size."""
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
