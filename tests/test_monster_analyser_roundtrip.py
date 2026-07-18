"""Regression guards for two MonsterAnalyser bugs found while auditing which .dat sections
the tool manages per entity type, both only visible on EntityType.WEAPON_NO_ANIM (the reduced
5-section weapon format used by Zell's and Kiros's unarmed files, e.g. d1w008.dat):

1. write_data_to_file() had no branch for WEAPON_NO_ANIM at all. Its shared "common" preamble
   (section 1 = skeleton, section 3 = animation) doesn't even apply to this format - section 1
   is geometry and there is no separate animation section - so every save silently dropped
   almost the whole file (33260 bytes -> 1740 bytes observed on d1w008.dat).
2. analyse_loaded_data() sliced the LAST section's end boundary from header_data['file_size'],
   a field read from a fixed byte offset assumed to hold a real trailing size field. For every
   other entity type that offset happens to land past the real file end, so Python's slice
   clamping (seq[start:huge_number] -> seq[start:len(seq)]) silently masked the bug. For
   WEAPON_NO_ANIM that offset instead lands inside section 1's own payload, decoding to a tiny
   garbage integer (1, on d1w008.dat) that truncated the real last section (Textures, 4652
   bytes) down to nothing.

Fixing only bug 1 still left files corrupted (33260 -> 28608 bytes) until bug 2 was fixed too -
this file pins both, plus the general boundary fix for every other entity type in case a
similarly-shaped format is added later.

Performance note: IfritManager's constructor reloads FF8GameData's JSON (~0.5-0.8s), while
init_from_file() on an already-built manager is cheap (~0.1s) - init_from_file() fully replaces
self.enemy with a fresh MonsterAnalyser each call, so it's safe to reuse one manager across many
files. Tests here always do that instead of constructing a new IfritManager per file.
"""
import glob
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
# Built at import time (not inside a fixture): the reduced-weapon file list below is
# discovered at collection time so it can feed @pytest.mark.parametrize, which needs its
# values before any fixture runs.
_APP = QApplication.instance() or QApplication([])

from Ifrit.ifritmanager import IfritManager
from FF8GameData.monsterdata import EntityType

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BATTLE_DIR = os.path.join(REPO, "extracted_files", "battle")

pytestmark = pytest.mark.skipif(not os.path.isdir(BATTLE_DIR),
                                 reason="extracted battle files not available")


def _discovery_manager():
    return IfritManager(os.path.join(REPO, "FF8GameData"))


def _reduced_weapon_files():
    """Every dXwYYY.dat that the header actually classifies as WEAPON_NO_ANIM (5 real
    sections) - found by loading rather than hardcoded, since the reduced format isn't
    tied to a fixed filename pattern. Reuses one manager across the whole scan."""
    if not os.path.isdir(BATTLE_DIR):
        return []
    mgr = _discovery_manager()
    found = []
    for path in sorted(glob.glob(os.path.join(BATTLE_DIR, "d*w*.dat"))):
        try:
            mgr.init_from_file(path)
        except Exception:
            continue
        if mgr.enemy.entity_type == EntityType.WEAPON_NO_ANIM:
            found.append(path)
    return found


REDUCED_WEAPON_FILES = _reduced_weapon_files()

# A small, deliberately mixed sample (not every file - that would take minutes) used by
# test_every_loaded_entity_type_keeps_its_last_section_full_length to check the general
# boundary fix across entity types, not just WEAPON_NO_ANIM.
_MIXED_TYPE_SAMPLE = sorted(set(
    glob.glob(os.path.join(BATTLE_DIR, "c0m00*.dat"))
    + glob.glob(os.path.join(BATTLE_DIR, "d0c*.dat"))
    + glob.glob(os.path.join(BATTLE_DIR, "d7c016.dat"))
    + glob.glob(os.path.join(BATTLE_DIR, "d0w00*.dat"))
    + REDUCED_WEAPON_FILES
)) if os.path.isdir(BATTLE_DIR) else []


@pytest.fixture(scope="module")
def manager():
    """One IfritManager, reused via init_from_file() across every test in this module."""
    return IfritManager(os.path.join(REPO, "FF8GameData"))


def test_at_least_one_reduced_weapon_file_is_covered():
    # Guards the test itself: if discovery ever finds zero files (e.g. extracted_files
    # layout changes), every parametrized test below silently collects as empty instead of
    # failing - this makes that loud instead of quiet.
    assert len(REDUCED_WEAPON_FILES) >= 1


@pytest.mark.parametrize("path", REDUCED_WEAPON_FILES)
def test_reduced_weapon_no_op_save_is_byte_identical(manager, tmp_path, path):
    manager.init_from_file(path)
    out = str(tmp_path / os.path.basename(path))
    manager.save_file(out)

    with open(path, "rb") as f:
        original = f.read()
    with open(out, "rb") as f:
        saved = f.read()

    assert len(saved) == len(original), (
        f"{os.path.basename(path)}: save changed the file size "
        f"({len(original)} -> {len(saved)} bytes) - the writer is dropping or padding data")
    assert saved == original, f"{os.path.basename(path)}: a no-op save must not change any byte"


@pytest.mark.parametrize("path", REDUCED_WEAPON_FILES)
def test_reduced_weapon_last_section_is_not_truncated(manager, path):
    """Directly pins bug 2: the last section (Textures) must be sliced to the file's real end,
    not to the bogus header_data['file_size'] value."""
    manager.init_from_file(path)
    h = manager.enemy.header_data
    last_index = h['nb_section'] - 1
    expected_len = os.path.getsize(path) - h['section_pos'][last_index]
    assert len(manager.enemy.section_raw_data[last_index]) == expected_len


def test_every_loaded_entity_type_keeps_its_last_section_full_length(manager):
    """General regression for the root cause, across a mix of entity types - not just
    WEAPON_NO_ANIM. Confirms the len(file_raw_data) boundary fix didn't just move the bug to
    only "happen to work" for the other types."""
    assert len(_MIXED_TYPE_SAMPLE) >= 4, "sample setup produced too few files to be meaningful"
    seen_types = set()
    for path in _MIXED_TYPE_SAMPLE:
        try:
            manager.init_from_file(path)
        except Exception:
            # A handful of com-id/weapon slots are genuinely empty placeholder files (e.g.
            # d0w007.dat is 0 bytes - Squall only has 7 real weapons); not this test's concern.
            continue
        h = manager.enemy.header_data
        last_index = h['nb_section'] - 1
        expected_len = os.path.getsize(path) - h['section_pos'][last_index]
        actual_len = len(manager.enemy.section_raw_data[last_index])
        assert actual_len == expected_len, f"{os.path.basename(path)}: last section truncated"
        seen_types.add(manager.enemy.entity_type)
    # Sanity: this sample should actually have exercised more than one entity type.
    assert len(seen_types) >= 2
