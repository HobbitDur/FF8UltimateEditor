"""Julia - FF8 battle sound editor (audio.fmt / audio.dat).

Reads the FF8 PC sound archive (``audio.fmt`` describing entries + ``audio.dat``
holding the raw sample data), lets the caller export/replace sounds, and rebuilds
both files. Also resolves which battle actor (character / monster) uses each sound,
using the ``battle_actor_sound.json`` resource extracted from ``stru_B8A418`` in
FF8_EN.exe.

Format (little-endian), from myst6re's ff8-sound-remixed:
    audio.fmt: uint16 soundCount, then (soundCount + 1) entries of
        Format (20 bytes): uint32 dataLength, uint32 dataOffset, uint8 bufferFlags,
                           uint8 x3 padding, uint32 bufferReadCursor, uint32 bufferWriteCursor
        WaveFormatEx (18 bytes): uint16 wFormatTag, uint16 nChannels, uint32 nSamplesPerSec,
                           uint32 nAvgBytesPerSec, uint16 nBlockAlign, uint16 wBitsPerSample, uint16 cbSize
        if cbSize > 0: cbSize extra bytes (MS-ADPCM coefficient block)
    audio.dat: sound i occupies [dataOffset, dataOffset + dataLength).
"""
import json
import os
import struct

# Format struct: dataLength, dataOffset, bufferFlags, (3 padding), readCursor, writeCursor
FORMAT_STRUCT = struct.Struct("<IIB3xII")  # 20 bytes
WAVEFMT_STRUCT = struct.Struct("<HHIIHHH")  # 18 bytes

WAVE_FORMAT_PCM = 1
WAVE_FORMAT_ADPCM = 2

FORMAT_LABELS = {WAVE_FORMAT_PCM: "PCM", WAVE_FORMAT_ADPCM: "ADPCM"}

# com_id 0..10 in stru_B8A418 are the playable characters, in this order.
CHARACTER_NAMES = ["Squall", "Zell", "Irvine", "Quistis", "Rinoa", "Selphie",
                   "Seifer", "Edea", "Laguna", "Kiros", "Ward"]


class FF8Sound:
    """One entry of audio.fmt (+ a handle on its data in audio.dat)."""

    def __init__(self):
        self.data_offset = 0
        self.data_length = 0
        self.buffer_flags = 0
        self.read_cursor = 0
        self.write_cursor = 0
        # WaveFormatEx fields: (tag, channels, samples_per_sec, avg_bytes_per_sec, block_align, bits, cb_size)
        self.wave_format = (WAVE_FORMAT_PCM, 0, 0, 0, 0, 0, 0)
        self.extra = b""      # ADPCM coefficient block (cb_size bytes)
        self.data = None      # replaced/imported bytes; None means "read from source audio.dat"

    # --- WaveFormatEx accessors ---
    @property
    def format_tag(self):
        return self.wave_format[0]

    @property
    def channels(self):
        return self.wave_format[1]

    @property
    def sample_rate(self):
        return self.wave_format[2]

    @property
    def bits_per_sample(self):
        return self.wave_format[5]

    @property
    def cb_size(self):
        return self.wave_format[6]

    @property
    def is_looping(self):
        return self.buffer_flags == 1

    @property
    def is_adpcm(self):
        return self.format_tag == WAVE_FORMAT_ADPCM

    @property
    def is_valid(self):
        return self.data_length != 0

    def format_label(self):
        return FORMAT_LABELS.get(self.format_tag, f"fmt{self.format_tag}")

    def to_wav(self, raw):
        """Build a standalone RIFF/WAVE for this sound. ``raw`` = its sample bytes.

        Mirrors ff8-sound-remixed's Sound::toWav (credited to Qhimm / FF8SND).
        """
        out = bytearray()
        out += b"RIFF"
        # RIFF payload = "WAVE"(4) + fmt chunk(8 + 18 + extra) + data chunk(8 + raw) = 38 + extra + raw.
        # (ff8-sound-remixed uses 36, which assumes a 16-byte fmt chunk; we always emit the full
        #  18-byte WaveFormatEx, so 38 is the correct size and keeps strict WAV parsers happy.)
        out += struct.pack("<I", len(raw) + 38 + len(self.extra))
        out += b"WAVEfmt "
        out += struct.pack("<I", 18 + len(self.extra))
        out += WAVEFMT_STRUCT.pack(*self.wave_format)
        out += self.extra
        out += b"data"
        out += struct.pack("<I", len(raw))
        out += raw
        return bytes(out)


class JuliaManager:
    """Read/write of the FF8 sound archive (audio.fmt + audio.dat)."""

    def __init__(self, game_data=None):
        self.game_data = game_data
        self.sounds = []
        self.fmt_path = None
        self.dat_path = None
        self._audio_id_to_com = {}   # audio_id -> [com_id, ...]
        self._monster_by_entity = {}  # entity_id -> name
        self._load_cross_reference()

    # ------------------------------------------------------------------ loading
    def load(self, fmt_path, dat_path=None):
        """Parse audio.fmt. audio.dat is taken from the same folder if not given."""
        if dat_path is None:
            dat_path = os.path.join(os.path.dirname(fmt_path), "audio.dat")
        if not os.path.isfile(dat_path):
            raise FileNotFoundError(f"audio.dat not found next to audio.fmt: {dat_path}")

        with open(fmt_path, "rb") as f:
            buf = f.read()

        pos = 0
        (sound_count,) = struct.unpack_from("<H", buf, pos)
        pos += 2

        sounds = []
        for _ in range(sound_count + 1):
            sound = FF8Sound()
            (sound.data_length, sound.data_offset, sound.buffer_flags,
             sound.read_cursor, sound.write_cursor) = FORMAT_STRUCT.unpack_from(buf, pos)
            pos += FORMAT_STRUCT.size
            sound.wave_format = WAVEFMT_STRUCT.unpack_from(buf, pos)
            pos += WAVEFMT_STRUCT.size
            cb_size = sound.wave_format[6]
            if cb_size > 0:
                sound.extra = buf[pos:pos + cb_size]
                pos += cb_size
            sounds.append(sound)

        self.sounds = sounds
        self.fmt_path = fmt_path
        self.dat_path = dat_path
        return sounds

    def get_raw(self, index):
        """Return the sample bytes for a sound (imported data, or read from source dat)."""
        sound = self.sounds[index]
        if sound.data is not None:
            return sound.data
        if not sound.is_valid:
            return b""
        with open(self.dat_path, "rb") as f:
            f.seek(sound.data_offset)
            return f.read(sound.data_length)

    # ------------------------------------------------------------------ export
    def get_wav(self, index):
        return self.sounds[index].to_wav(self.get_raw(index))

    def export_wav(self, index, path):
        with open(path, "wb") as f:
            f.write(self.get_wav(index))

    def export_all(self, folder):
        count = 0
        for i, sound in enumerate(self.sounds):
            if sound.is_valid:
                self.export_wav(i, os.path.join(folder, f"sound_{i:04d}.wav"))
                count += 1
        return count

    # ------------------------------------------------------------------ import
    def replace_from_wav(self, index, wav_path):
        """Replace a sound with the contents of a RIFF/WAVE file (PCM or MS-ADPCM)."""
        wave_format, extra, data = self._parse_wav(wav_path)
        sound = self.sounds[index]
        sound.wave_format = wave_format
        sound.extra = extra
        sound.data = data
        sound.data_length = len(data)

    @staticmethod
    def _parse_wav(path):
        with open(path, "rb") as f:
            buf = f.read()
        if buf[:4] != b"RIFF" or buf[8:12] != b"WAVE":
            raise ValueError("Not a RIFF/WAVE file")

        pos = 12
        wave_format = None
        extra = b""
        data = None
        while pos + 8 <= len(buf):
            chunk_id = buf[pos:pos + 4]
            (chunk_size,) = struct.unpack_from("<I", buf, pos + 4)
            body = buf[pos + 8:pos + 8 + chunk_size]
            if chunk_id == b"fmt ":
                tag, channels, rate, avg, align, bits = struct.unpack_from("<HHIIHH", body, 0)
                cb_size = 0
                if len(body) >= 18:
                    (cb_size,) = struct.unpack_from("<H", body, 16)
                    extra = body[18:18 + cb_size]
                wave_format = (tag, channels, rate, avg, align, bits, len(extra))
            elif chunk_id == b"data":
                data = body
            pos += 8 + chunk_size + (chunk_size & 1)  # chunks are word-aligned

        if wave_format is None or data is None:
            raise ValueError("WAV missing 'fmt ' or 'data' chunk")
        return wave_format, extra, data

    # ------------------------------------------------------------------ save
    def save(self, fmt_path=None, dat_path=None):
        """Rebuild audio.fmt + audio.dat. Packs data contiguously and reassigns offsets."""
        fmt_path = fmt_path or self.fmt_path
        dat_path = dat_path or self.dat_path
        if not fmt_path or not dat_path:
            raise ValueError("No target paths (load a file first)")

        # Collect all sample bytes BEFORE writing (some come from the source audio.dat we are about to overwrite).
        raws = [self.get_raw(i) for i in range(len(self.sounds))]

        dat = bytearray()
        for sound, raw in zip(self.sounds, raws):
            sound.data_offset = len(dat)
            sound.data_length = len(raw)
            dat += raw

        fmt = bytearray()
        fmt += struct.pack("<H", len(self.sounds) - 1)  # header stores count-1 (reader loops count+1)
        for sound in self.sounds:
            fmt += FORMAT_STRUCT.pack(sound.data_length, sound.data_offset, sound.buffer_flags,
                                      sound.read_cursor, sound.write_cursor)
            fmt += WAVEFMT_STRUCT.pack(*sound.wave_format)
            fmt += sound.extra

        self._atomic_write(dat_path, bytes(dat))
        self._atomic_write(fmt_path, bytes(fmt))

        # The source now matches our new offsets; drop imported buffers so future reads use the file.
        for sound in self.sounds:
            sound.data = None
        self.fmt_path = fmt_path
        self.dat_path = dat_path

    @staticmethod
    def _atomic_write(path, payload):
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(payload)
        os.replace(tmp, path)

    # ------------------------------------------------------------ cross-reference
    def _load_cross_reference(self):
        if self.game_data is None:
            return
        # audio_id -> [com_id, ...] from the extracted stru_B8A418 table
        try:
            path = os.path.join(self.game_data.resource_folder_json, "battle_actor_sound.json")
            with open(path, encoding="utf-8") as f:
                actor_sounds = json.load(f)["actor_sounds"]
            for com_id_str, audio_ids in actor_sounds.items():
                com_id = int(com_id_str)
                for audio_id in audio_ids:
                    self._audio_id_to_com.setdefault(audio_id, []).append(com_id)
        except (OSError, KeyError, ValueError):
            self._audio_id_to_com = {}

        # entity_id -> monster name (entity_id == exe com_id for monsters)
        monsters = getattr(self.game_data, "monster_data_json", None) or {}
        for monster in monsters.get("monster", []):
            self._monster_by_entity[monster["entity_id"]] = monster["name"]

    def actor_names_for(self, index):
        """Names of the battle actors that use the sound whose audio id == ``index``."""
        names = []
        seen = set()
        for com_id in self._audio_id_to_com.get(index, []):
            name = self._name_for_com(com_id)
            if name and name not in seen:
                seen.add(name)
                names.append(name)
        return names

    def _name_for_com(self, com_id):
        if 0 <= com_id < len(CHARACTER_NAMES):
            return CHARACTER_NAMES[com_id]
        if com_id in self._monster_by_entity:
            return self._monster_by_entity[com_id]
        return f"com {com_id:#x}"
