"""Real-file load/save round-trip for the Ifrit monster editor.

Ifrit edits battle ``c0mNNN.dat`` monster files (3D model / stats / AI /
animation-sequence / texture).  This test drives the *same* high-level API the
IfritMonsterWidget uses:

    IfritManager.init_from_file(path)   # load a monster .dat
    IfritManager.save_file(path)        # re-serialise it back to disk

which under the hood is ``MonsterAnalyser.load_file_data`` +
``analyse_loaded_data`` (load) and ``write_data_to_file`` (save).

A no-edit load -> save round-trip reproduces every section byte-for-byte,
with one deliberate exception: the animation section (section 3,
``model_animation``) is re-encoded from its parsed bit-packed representation
via ``AnimationSection.to_binary`` / ``BitWriter``. Each animation's
bit-stream rarely ends on a byte boundary; the leftover high bits of that
final byte are never read by the game (``Battle_ReadAnimation`` reads exactly
the frames' bits) and Square's original encoder left garbage there. This
round trip zero-fills those bits instead of trying to reproduce the original
garbage, so that one padding byte per animation is allowed to differ from the
source file. ``_section3_care_mask`` / ``_assert_bytes_equal_modulo_padding``
below compute exactly which bits that is and mask them out of the
comparisons -- everything else (every other section, and every real bit of
frame data within section 3) is still required to be byte/bit-exact.

The invariants asserted here therefore are:
  1. byte-exactness modulo animation alignment padding - a no-edit load +
     save reproduces the original file, except for the never-read alignment
     bits at the tail of each animation's bit-stream;
  2. edit persistence - a stat edit (HP) survives save + reload.

Needs the real (copyright, gitignored) monster files under extracted_files/battle/,
so it is marked ``ff8data`` and skipped in CI / when those files are absent.
"""
import copy
import pathlib
import shutil
import sys

import pytest
from PyQt6.QtWidgets import QApplication

from FF8GameData.monsterdata import BitWriter
from Ifrit.ifritmanager import IfritManager

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
BATTLE_DIR = PROJECT_ROOT / "extracted_files" / "battle"

# Every real monster file. Indices 127 (a 460-byte stub) and 144-199 (200
# files total, but 144-199 are all byte-identical to each other) are
# placeholder/garbage entries rather than real monsters and are excluded.
MONSTERS = [f"c0m{i:03d}.dat" for i in range(144) if i != 127]
MONSTER_MARK = [
    pytest.param(name, marks=pytest.mark.ff8data(f"extracted_files/battle/{name}"))
    for name in MONSTERS
]


@pytest.fixture(scope="module")
def qapp():
    # IfritManager pulls in Qt (QPixmap textures); a QApplication must exist.
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture(scope="module")
def manager(qapp):
    # Constructing the manager loads all of FF8GameData once; init_from_file
    # fully re-initialises the parsed monster on every call, so it is safe to
    # reuse this instance across tests.
    return IfritManager(str(PROJECT_ROOT / "FF8GameData"))


def _load(manager, monster_name, tmp_path, out_name="work.dat"):
    """Copy the real .dat into tmp_path and load it (never touch extracted_files)."""
    work = tmp_path / out_name
    shutil.copy(BATTLE_DIR / monster_name, work)
    manager.init_from_file(str(work))
    return work


def _section3_care_mask(enemy) -> bytearray:
    """Byte mask (relative to the section-3 raw bytes) that is 0xFF everywhere
    except the one alignment byte at the end of each animation's bit-stream,
    where only the low bits holding real frame data are kept. Those high bits
    are never read by the game and are zero-filled on save -- an original
    file with non-zero garbage there is expected to differ, not a bug."""
    section = enemy.animation_data
    length = len(bytes(enemy.section_raw_data[3]))
    mask = bytearray([0xFF]) * length

    for anim, anim_start in zip(section.animations, section.offsets):
        writer = BitWriter()
        prev_frame = None
        for frame in anim.frames:
            frame.write_to_writer(writer, prev_frame)
            prev_frame = frame
        if writer._bits_in_buffer > 0:
            partial_byte_offset = anim_start + 1 + len(writer._data)
            mask[partial_byte_offset] = (1 << writer._bits_in_buffer) - 1

    return mask


def _assert_bytes_equal_modulo_mask(original: bytes, saved: bytes, mask: bytes, label: str):
    assert len(original) == len(saved), f"{label}: size changed on save"
    for i in range(len(original)):
        assert (original[i] & mask[i]) == (saved[i] & mask[i]), (
            f"{label}: byte {i} differs beyond known alignment padding "
            f"(original=0x{original[i]:02x} saved=0x{saved[i]:02x} mask=0x{mask[i]:02x})"
        )


@pytest.mark.parametrize("monster_name", MONSTER_MARK)
def test_real_monster_roundtrip_is_byte_exact(manager, monster_name, tmp_path):
    """A no-edit load -> save reproduces the original file byte-for-byte,
    except for the never-read alignment bits at the tail of each animation's
    bit-stream (zero-filled on save instead of reproducing the original
    encoder's garbage there)."""
    work = _load(manager, monster_name, tmp_path)
    enemy = manager.enemy

    original = work.read_bytes()
    section3_offset = sum(len(bytes(s)) for s in enemy.section_raw_data[:3])
    section3_mask = _section3_care_mask(enemy)
    mask = bytearray([0xFF]) * len(original)
    mask[section3_offset:section3_offset + len(section3_mask)] = section3_mask

    out = tmp_path / "out.dat"
    manager.save_file(str(out))
    saved = out.read_bytes()

    _assert_bytes_equal_modulo_mask(original, saved, mask, monster_name)


@pytest.mark.parametrize("monster_name", MONSTER_MARK)
def test_real_monster_roundtrip_preserves_sections(manager, monster_name, tmp_path):
    """Every section is byte-identical to the original after a no-edit save,
    except section 3 (animation), which is allowed to differ only in the
    never-read alignment padding at the end of each animation's bit-stream."""
    _load(manager, monster_name, tmp_path)
    enemy = manager.enemy

    # Snapshot the original section slices parsed from the untouched file.
    original_sections = [bytes(s) for s in enemy.section_raw_data]
    original_size = sum(len(s) for s in original_sections)
    section3_mask = _section3_care_mask(enemy)

    out = tmp_path / "out.dat"
    manager.save_file(str(out))
    saved_sections = [bytes(s) for s in enemy.section_raw_data]

    assert len(out.read_bytes()) == original_size, "file size changed on save"
    assert len(saved_sections) == len(original_sections)

    for index, (before, after) in enumerate(zip(original_sections, saved_sections)):
        if index == 3:
            _assert_bytes_equal_modulo_mask(before, after, section3_mask, f"section {index}")
        else:
            assert after == before, f"section {index} changed on save (expected byte-exact)"


@pytest.mark.parametrize("monster_name", MONSTER_MARK)
def test_real_monster_stat_edit_persists(manager, monster_name, tmp_path):
    """A single stat edit (HP base curve byte) survives save + reload, and the
    monster name is left untouched."""
    _load(manager, monster_name, tmp_path)
    enemy = manager.enemy

    original_hp = copy.deepcopy(enemy.info_stat_data['hp'])
    original_name = enemy.info_stat_data['monster_name'].get_str()

    new_hp0 = (original_hp[0] + 7) % 256
    enemy.info_stat_data['hp'][0] = new_hp0

    out = tmp_path / "edited.dat"
    manager.save_file(str(out))

    manager.init_from_file(str(out))
    reloaded = manager.enemy
    assert reloaded.info_stat_data['hp'][0] == new_hp0
    assert reloaded.info_stat_data['hp'][1:] == original_hp[1:]
    assert reloaded.info_stat_data['monster_name'].get_str() == original_name
