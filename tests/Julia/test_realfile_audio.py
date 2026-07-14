"""Real-file round-trip test for Julia (FF8 sound editor, audio.fmt / audio.dat).

Unlike test_juliamanager.py (which builds a tiny synthetic archive), this test loads
the *original* game audio.fmt + audio.dat from extracted_files/ and checks the save.

Empirically observed invariant (invariant #2 in the task brief):

* audio.dat *is* byte-for-byte lossless: save() repacks sample bytes contiguously in
  entry order and the original file is already laid out that way, so the rebuilt .dat
  matches the original exactly.
* audio.fmt is *not* byte-identical, even though its length is unchanged. The only
  differences are the ``dataOffset`` field of the zero-length ("invalid") sound slots:
  the original stores 0 for them, while save() writes the running data cursor. Since
  those slots have data_length == 0 their offset is never dereferenced, so the change
  is harmless. What must therefore hold is idempotency (a second round-trip is byte
  stable) and that all parsed content survives a save + reload.

Needs the real files, skipped otherwise (ff8data marker in the project-root conftest).
"""
import io
import pathlib
import shutil
import wave

import pytest

from Julia.juliamanager import JuliaManager

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
SOUND_DIR = PROJECT_ROOT / "extracted_files" / "Sound"
AUDIO_FMT = SOUND_DIR / "audio.fmt"
AUDIO_DAT = SOUND_DIR / "audio.dat"


def _copy_archive(tmp_path):
    """save() overwrites the loaded paths in place, so work on a copy in tmp_path."""
    work_fmt = tmp_path / "audio.fmt"
    work_dat = tmp_path / "audio.dat"
    shutil.copy(AUDIO_FMT, work_fmt)
    shutil.copy(AUDIO_DAT, work_dat)
    return work_fmt, work_dat


def _snapshot(manager):
    """Per-sound metadata that must survive a save + reload."""
    return [(s.data_length, s.buffer_flags, s.wave_format, s.extra) for s in manager.sounds]


@pytest.mark.ff8data("extracted_files/Sound/audio.fmt", "extracted_files/Sound/audio.dat")
def test_real_audio_dat_roundtrip_is_byte_exact(tmp_path):
    """The sample bank (audio.dat) is rebuilt byte-for-byte identical to the original."""
    work_fmt, work_dat = _copy_archive(tmp_path)
    original_dat = AUDIO_DAT.read_bytes()

    manager = JuliaManager()
    manager.load(str(work_fmt), str(work_dat))
    assert len(manager.sounds) > 0, "no sounds parsed from the real file"
    assert sum(1 for s in manager.sounds if s.is_valid) > 0, "no valid sounds parsed"

    manager.save()
    assert work_dat.read_bytes() == original_dat


@pytest.mark.ff8data("extracted_files/Sound/audio.fmt", "extracted_files/Sound/audio.dat")
def test_real_audio_content_survives_reload(tmp_path):
    """All parsed sound metadata + raw sample bytes survive a save + reload."""
    work_fmt, work_dat = _copy_archive(tmp_path)

    manager = JuliaManager()
    manager.load(str(work_fmt), str(work_dat))
    before = _snapshot(manager)
    # raw bytes of a handful of valid sounds, sampled across the archive
    valid_indices = [i for i, s in enumerate(manager.sounds) if s.is_valid]
    sample_indices = valid_indices[:: max(1, len(valid_indices) // 20)]
    before_raw = {i: manager.get_raw(i) for i in sample_indices}

    manager.save()

    reloaded = JuliaManager()
    reloaded.load(str(work_fmt), str(work_dat))
    assert _snapshot(reloaded) == before
    for i, raw in before_raw.items():
        assert reloaded.get_raw(i) == raw


@pytest.mark.ff8data("extracted_files/Sound/audio.fmt", "extracted_files/Sound/audio.dat")
def test_real_audio_roundtrip_is_idempotent(tmp_path):
    """audio.fmt is not byte-exact vs the original, but a second round-trip is stable."""
    work_fmt, work_dat = _copy_archive(tmp_path)

    m1 = JuliaManager()
    m1.load(str(work_fmt), str(work_dat))
    m1.save()  # normalise
    after_first = work_fmt.read_bytes(), work_dat.read_bytes()

    m2 = JuliaManager()
    m2.load(str(work_fmt), str(work_dat))
    m2.save()
    after_second = work_fmt.read_bytes(), work_dat.read_bytes()

    assert after_first == after_second


@pytest.mark.ff8data("extracted_files/Sound/audio.fmt", "extracted_files/Sound/audio.dat")
def test_real_audio_export_wav_is_valid(tmp_path):
    """Exporting one real sound yields a non-empty, parseable RIFF/WAVE file."""
    work_fmt, work_dat = _copy_archive(tmp_path)

    manager = JuliaManager()
    manager.load(str(work_fmt), str(work_dat))
    # Python's wave module only decodes plain PCM, so pick a valid PCM sound.
    index = next(i for i, s in enumerate(manager.sounds) if s.is_valid and not s.is_adpcm)

    out = tmp_path / "sound.wav"
    manager.export_wav(index, str(out))

    payload = out.read_bytes()
    assert len(payload) > 44, "exported WAV is empty / header-only"
    assert payload[:4] == b"RIFF" and payload[8:12] == b"WAVE"

    reader = wave.open(io.BytesIO(payload), "rb")
    assert reader.getnchannels() == manager.sounds[index].channels
    assert reader.getframerate() == manager.sounds[index].sample_rate
    assert reader.getnframes() > 0
