"""Real-file load/save round-trip for the Ifrit monster editor.

Ifrit edits battle ``c0mNNN.dat`` monster files (3D model / stats / AI /
animation-sequence / texture).  This test drives the *same* high-level API the
IfritMonsterWidget uses:

    IfritManager.init_from_file(path)   # load a monster .dat
    IfritManager.save_file(path)        # re-serialise it back to disk

which under the hood is ``MonsterAnalyser.load_file_data`` +
``analyse_loaded_data`` (load) and ``write_data_to_file`` (save).

A no-edit load -> save round-trip is byte-for-byte identical to the original
file.  Most sections are kept as their raw bytes; the animation section
(section 3, ``model_animation``) is re-encoded from its parsed bit-packed
representation via ``AnimationSection.to_binary`` / ``BitWriter``, which
reproduces the original bytes exactly: each animation records the original
byte-alignment slack bits of its bit-stream (garbage the game never reads --
``Battle_ReadAnimation`` reads exactly the frames' bits) and re-emits them on
save instead of zero-filling.

The invariants asserted here therefore are:
  1. byte-exactness - a no-edit load + save reproduces the original file
     byte-for-byte (every section, including the re-encoded animation one);
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

from Ifrit.ifritmanager import IfritManager

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
BATTLE_DIR = PROJECT_ROOT / "extracted_files" / "battle"

# A few genuine monsters (index 0/127 and >143 are garbage/placeholder files).
MONSTERS = ["c0m001.dat", "c0m002.dat", "c0m003.dat"]
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


@pytest.mark.parametrize("monster_name", MONSTER_MARK)
def test_real_monster_roundtrip_is_byte_exact(manager, monster_name, tmp_path):
    """A no-edit load -> save reproduces the original file byte-for-byte,
    including the re-encoded bit-packed animation section."""
    work = _load(manager, monster_name, tmp_path)

    out = tmp_path / "out.dat"
    manager.save_file(str(out))

    assert out.read_bytes() == work.read_bytes()


@pytest.mark.parametrize("monster_name", MONSTER_MARK)
def test_real_monster_roundtrip_preserves_sections(manager, monster_name, tmp_path):
    """Every section, including the re-encoded animation section (index 3),
    is byte-identical to the original after a no-edit save."""
    _load(manager, monster_name, tmp_path)
    enemy = manager.enemy

    # Snapshot the original section slices parsed from the untouched file.
    original_sections = [bytes(s) for s in enemy.section_raw_data]
    original_size = sum(len(s) for s in original_sections)

    out = tmp_path / "out.dat"
    manager.save_file(str(out))
    saved_sections = [bytes(s) for s in enemy.section_raw_data]

    assert len(out.read_bytes()) == original_size, "file size changed on save"
    assert len(saved_sections) == len(original_sections)

    for index, (before, after) in enumerate(zip(original_sections, saved_sections)):
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
