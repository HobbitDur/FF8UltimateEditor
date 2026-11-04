"""The battle effects' prim-model layouts: keyframed animations of models, played by the effect
library's prim player (Effect_PrimPlayer_Play 0x701970; FFNx's twin src/ff8/battle/fx/fx_primplayer.cpp),
each object drawn through the effect's callback every tick.

    layout data   +0 u32 model count, +4 int32 header offset, +8 int32 model offsets (from the data)
    models        before the header (their vertex frames and polygons: kept as bytes here)
    header        +0 object count, +4 total frames, +8 int32 object offsets (from the header)
    object        +0 u32 flags (low byte: its model), +4 u32 track flags, +8 int32 key-table offsets
                  (from the object), one per track flag set, in this order:
                    position value / velocity / acceleration   bits 0, 1, 2    keys {frame, 3 x int32 16.16}
                    rotation                                    bits 3, 4, 5    (same)
                    scale                                       bits 6, 7, 8    (same)
                    colour value / velocity / acceleration      bits 9, 10, 11  keys {frame, 3 x u16 (value >> 8 = byte), pad}
                    channel A (value, velocity, acceleration)   bit 12          keys {frame, 3 x int32}
                    channel B (frame a, frame b, value, velocity, acceleration)
                                                                bit 13          keys {frame, 2 x u16, 3 x int32}
    key table     keys in frame order, then -1 (4 bytes: the table's end)

On each tick a keyed slot takes its key of that frame (if any); velocity and acceleration integrate
between keys. Channel B blends the model's vertex frames a and b by its value (the callback).

No Qt here.
"""
import struct
from dataclasses import dataclass, field

# (track name, slot name, track-flag bit, key stride, payload format)
TRACKS = tuple((channel, slot, 3 * index + bit, 16, "<3i")
               for index, channel in enumerate(("position", "rotation", "scale"))
               for bit, slot in enumerate(("value", "velocity", "acceleration"))) + tuple(
    ("colour", slot, 9 + bit, 12, "<3HH") for bit, slot in enumerate(("value", "velocity", "acceleration"))) + (
    ("a", "keys", 12, 16, "<3i"), ("b", "keys", 13, 20, "<2H3i"))
TRACK_BITS = sum(1 << track[2] for track in TRACKS)


@dataclass
class Track:
    channel: str            # position, rotation, scale, colour, a, b
    slot: str               # value, velocity, acceleration (keys: channels A and B)
    keys: list = field(default_factory=list)     # [(frame, (values...))]

    @property
    def spec(self):
        return next(t for t in TRACKS if t[0] == self.channel and t[1] == self.slot)


@dataclass
class LayoutObject:
    flags: int                                   # low byte: its model
    tracks: list = field(default_factory=list)   # in track-flag order
    other_bits: int = 0                          # track-flag bits beyond the tracks (kept)

    @property
    def model(self):
        return self.flags & 0xFF

    @property
    def track_flags(self):
        return self.other_bits | sum(1 << track.spec[2] for track in self.tracks)


@dataclass
class PrimLayout:
    models: bytes            # the data before the header: model count, offsets, models
    frames: int
    objects: list = field(default_factory=list)
    model_count: int = 0


def _keys(data, at, stride, payload):
    keys = []
    while True:
        frame = struct.unpack_from("<i", data, at)[0]
        if frame == -1:
            return keys
        keys.append((frame, struct.unpack_from(payload, data, at + 4)))
        at += stride


def parse_layout(data):
    """The PrimLayout of a layout's bytes (ValueError when they are not one)."""
    try:
        model_count, header = struct.unpack_from("<Ii", data, 0)
        count, frames = struct.unpack_from("<ii", data, header)
        if not 0 <= count <= 256 or not 0 < header < len(data):
            raise ValueError("not a prim-model layout")
        layout = PrimLayout(bytes(data[:header]), frames, [], model_count)
        for index in range(count):
            at = header + struct.unpack_from("<i", data, header + 8 + 4 * index)[0]
            flags, tf = struct.unpack_from("<II", data, at)
            obj = LayoutObject(flags, [], tf & ~TRACK_BITS)
            offset = at + 8
            for channel, slot, bit, stride, payload in TRACKS:
                if tf >> bit & 1:
                    table = at + struct.unpack_from("<i", data, offset)[0]
                    offset += 4
                    obj.tracks.append(Track(channel, slot, _keys(data, table, stride, payload)))
            layout.objects.append(obj)
        return layout
    except struct.error:
        raise ValueError("not a prim-model layout (cut short)") from None


def state_size(layout):
    """The bytes of player state the layout needs (Effect_DecodeModelPrimLayout 0x7016B0's walk): the
    data pointer and the frame, then each object's integrator slots by its track flags. A port decodes a
    layout into a block of a fixed size (its description's "capacity"): a layout needing more is not
    played (FFNx's fx_params.h layout() keeps the game's)."""
    words = 2
    for obj in layout.objects:
        tf = obj.track_flags
        words += 9 if tf & 4 else 6 if tf & 2 else 3 if tf & 1 else 0                  # position
        words += 9 if tf & 0x20 else 6 if tf & 0x10 else 3 if tf & 8 else 0            # rotation
        words += 9 if tf & 0x100 else 6 if tf & 0x80 else 3 if tf & 0x40 else 0         # scale
        words += 6 if tf & 0x800 else 4 if tf & 0x400 else 2 if tf & 0x200 else 0      # colour
        words += (3 if tf & 0x1000 else 0) + (4 if tf & 0x2000 else 0)                  # channels A, B
    return 4 * words


def encode_layout(layout):
    """The bytes of a PrimLayout (parse_layout's inverse): its models as they are, then the
    header, each object followed by its key tables."""
    header = len(layout.models)
    out = bytearray(layout.models)
    struct.pack_into("<i", out, 4, header)
    body = bytearray(struct.pack("<ii", len(layout.objects), layout.frames)) + bytes(4 * len(layout.objects))
    for index, obj in enumerate(layout.objects):
        struct.pack_into("<i", body, 8 + 4 * index, len(body))
        start = len(body)
        tracks = sorted(obj.tracks, key=lambda track: track.spec[2])
        body += struct.pack("<II", obj.flags, obj.track_flags) + bytes(4 * len(tracks))
        for slot, track in enumerate(tracks):
            _channel, _slot, _bit, stride, payload = track.spec
            struct.pack_into("<i", body, start + 8 + 4 * slot, len(body) - start)
            # (by frame only: keys of one frame keep their order, the player takes the first - Full-cure has some)
            for frame, values in sorted(track.keys, key=lambda key: key[0]):
                body += struct.pack("<i", frame) + struct.pack(payload, *values)
            body += struct.pack("<i", -1)
    return bytes(out + body)
