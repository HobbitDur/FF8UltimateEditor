"""
Tests for Julia (FF8 sound editor, audio.fmt / audio.dat).
A small synthetic audio.fmt/audio.dat pair is built with known entries so the tests
don't need the original game files.
"""
import io
import pathlib
import struct
import wave

import pytest

from FF8GameData.gamedata import GameData
from Julia.juliamanager import (JuliaManager, FF8Sound, FORMAT_STRUCT, WAVEFMT_STRUCT,
                                 WAVE_FORMAT_PCM, WAVE_FORMAT_ADPCM)


def _wave_format(tag, channels, rate, bits, cb_size):
    block_align = channels * bits // 8 or 1
    avg = block_align * rate
    return (tag, channels, rate, avg, block_align, bits, cb_size)


def _build_archive(folder, entries):
    """entries: list of (data_bytes, wave_format_tuple, extra_bytes, buffer_flags)."""
    dat = bytearray()
    offsets = []
    for data, _fmt, _extra, _flags in entries:
        offsets.append(len(dat))
        dat += data
    fmt = bytearray()
    fmt += struct.pack("<H", len(entries) - 1)  # header stores count-1
    for (data, wave_format, extra, flags), offset in zip(entries, offsets):
        fmt += FORMAT_STRUCT.pack(len(data), offset, flags, 0, 0)
        fmt += WAVEFMT_STRUCT.pack(*wave_format)
        fmt += extra
    fmt_path = folder / "audio.fmt"
    dat_path = folder / "audio.dat"
    fmt_path.write_bytes(bytes(fmt))
    dat_path.write_bytes(bytes(dat))
    return str(fmt_path), str(dat_path)


@pytest.fixture
def archive(tmp_path):
    entries = [
        (b"\x11\x22\x33\x44\x55\x66\x77\x88", _wave_format(WAVE_FORMAT_PCM, 1, 11025, 16, 0), b"", 0),
        (b"\xAA\xBB\xCC\xDD\xEE\xFF\x00\x10\x20", _wave_format(WAVE_FORMAT_ADPCM, 2, 22050, 4, 4),
         b"\x01\x02\x03\x04", 1),
    ]
    fmt_path, _dat_path = _build_archive(tmp_path, entries)
    return fmt_path, entries


@pytest.fixture(scope="module")
def game_data():
    project_root = pathlib.Path(__file__).parent.parent.parent
    gd = GameData(str(project_root / "FF8GameData"))
    gd.load_monster_data()
    return gd


def test_parse(archive):
    fmt_path, entries = archive
    manager = JuliaManager()
    manager.load(fmt_path)

    assert len(manager.sounds) == len(entries)
    pcm, adpcm = manager.sounds
    assert pcm.format_tag == WAVE_FORMAT_PCM and pcm.channels == 1 and pcm.sample_rate == 11025
    assert not pcm.is_looping and pcm.format_label() == "PCM"
    assert adpcm.is_adpcm and adpcm.is_looping and adpcm.cb_size == 4 and adpcm.extra == b"\x01\x02\x03\x04"
    assert manager.get_raw(0) == entries[0][0]
    assert manager.get_raw(1) == entries[1][0]


def test_to_wav_is_valid_pcm(archive):
    fmt_path, entries = archive
    manager = JuliaManager()
    manager.load(fmt_path)

    reader = wave.open(io.BytesIO(manager.get_wav(0)), "rb")
    assert reader.getnchannels() == 1
    assert reader.getframerate() == 11025
    assert reader.getsampwidth() == 2
    assert reader.readframes(reader.getnframes()) == entries[0][0]


def test_wav_import_roundtrip(archive):
    """A WAV exported by Julia parses back to the same format + extra + data."""
    fmt_path, entries = archive
    manager = JuliaManager()
    manager.load(fmt_path)

    wav_path = pathlib.Path(fmt_path).parent / "s1.wav"
    manager.export_wav(1, str(wav_path))
    wave_format, extra, data = JuliaManager._parse_wav(str(wav_path))
    assert data == entries[1][0]
    assert extra == entries[1][2]
    assert wave_format[0] == WAVE_FORMAT_ADPCM
    assert wave_format[6] == 4


def test_replace_save_reload(archive, tmp_path):
    fmt_path, entries = archive
    manager = JuliaManager()
    manager.load(fmt_path)

    new_data = b"\x01" * 20
    new_sound = FF8Sound()
    new_sound.wave_format = _wave_format(WAVE_FORMAT_PCM, 1, 8000, 8, 0)
    new_wav = tmp_path / "new.wav"
    new_wav.write_bytes(new_sound.to_wav(new_data))

    manager.replace_from_wav(0, str(new_wav))
    manager.save()

    reloaded = JuliaManager()
    reloaded.load(fmt_path)
    assert reloaded.get_raw(0) == new_data
    assert reloaded.get_raw(1) == entries[1][0]  # untouched sound survives the rebuild
    assert reloaded.sounds[0].sample_rate == 8000
    assert reloaded.sounds[1].is_looping and reloaded.sounds[1].extra == entries[1][2]
    # data packed contiguously with reassigned offsets
    assert reloaded.sounds[0].data_offset == 0
    assert reloaded.sounds[1].data_offset == len(new_data)


def test_cross_reference(game_data):
    manager = JuliaManager(game_data)
    assert "GIM52A" in manager.actor_names_for(217)   # com_id 0x11 -> entity_id 17
    assert manager.actor_names_for(158) == ["Squall"]  # party actor
    assert manager.actor_names_for(999999) == []       # out of range -> blank
