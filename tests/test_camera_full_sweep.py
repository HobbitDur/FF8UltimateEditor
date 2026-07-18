"""Exhaustive Camera-tab coverage: every real monster (c0m*.dat) and character body
(d*c*.dat) file that has a camera section, not just the handful of samples the other camera
test files use. This is the "does it correctly edit every file that has it" guard - a bug that
only shows up on one specific monster's camera collection would slip past a small sample.

Reuses the real _CAMERA_SECTION_BY_ENTITY map from the Camera tab itself (not a re-derived
copy), so this sweep automatically tracks whatever the widget actually does.

Performance: each MonsterAnalyser.init_from_file() re-parses the whole .dat (AI decompile,
sequences, textures...), not just the camera section - unavoidable cost of testing through the
real load path rather than a synthetic shortcut. ~200 monsters + 17 character files takes a few
minutes; one shared IfritManager is reused throughout (see test_monster_analyser_roundtrip.py's
perf note) to avoid re-paying its ~0.5-0.8s constructor cost per file.
"""
import glob
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication([])

from Ifrit.ifritmanager import IfritManager
from Ifrit.IfritCameraSeq.ifritcameraseqwidget import _CAMERA_SECTION_BY_ENTITY
from FF8GameData.dat.monsteranalyser import GarbageFileError
from FF8GameData.dat.cameracollection import parse_camera_collection, CameraParseError

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BATTLE_DIR = os.path.join(REPO, "extracted_files", "battle")

pytestmark = pytest.mark.skipif(not os.path.isdir(BATTLE_DIR),
                                 reason="extracted battle files not available")

MONSTER_FILES = sorted(glob.glob(os.path.join(BATTLE_DIR, "c0m*.dat")))
CHARACTER_FILES = sorted(glob.glob(os.path.join(BATTLE_DIR, "d*c*.dat")))
ALL_CAMERA_CANDIDATE_FILES = MONSTER_FILES + CHARACTER_FILES

pytestmark = [pytestmark, pytest.mark.skipif(
    not ALL_CAMERA_CANDIDATE_FILES, reason="no monster/character battle files found")]


@pytest.fixture(scope="module")
def manager():
    return IfritManager(os.path.join(REPO, "FF8GameData"))


def _first_editable_field(collection):
    """A pos_x field of the first real keyframe in the collection, or None if it has none
    (a monster/character with an entirely empty camera section)."""
    for camera_set in collection.sets:
        for animation in camera_set.animations:
            if animation.empty:
                continue
            for block in animation.blocks:
                if block.frames:
                    return block.frames[0].pos_x
    return None


def test_at_least_one_file_of_each_kind_is_covered():
    # Guards the sweep itself: a broken glob would otherwise make every test below vacuously
    # pass on zero files instead of failing loudly.
    assert len(MONSTER_FILES) >= 50
    assert len(CHARACTER_FILES) >= 5


def test_every_camera_bearing_file_round_trips_through_a_real_save(manager, tmp_path):
    """The core guarantee: for every file whose entity type the Camera tab claims to support,
    loading it, parsing its camera section, and running it through a real (no-op) save_file()
    must reproduce that section byte-for-byte - and must not change the overall file's length
    (the exact invariant that was silently broken for WEAPON_NO_ANIM)."""
    checked = 0
    empty_sections = 0
    skipped_unsupported_type = 0
    skipped_garbage_files = 0
    failures = []

    for path in ALL_CAMERA_CANDIDATE_FILES:
        name = os.path.basename(path)
        try:
            manager.init_from_file(path)
        except GarbageFileError:
            # A handful of com-id slots are non-standard stubs the game itself never loads
            # as a real monster/character (e.g. c0m127.dat: nb_section=3, matches no known
            # file layout) - MonsterAnalyser already flags these on its own; not a camera bug.
            skipped_garbage_files += 1
            continue
        except Exception as e:
            failures.append(f"{name}: failed to load ({e!r})")
            continue

        entity_type = manager.enemy.entity_type
        section_index = _CAMERA_SECTION_BY_ENTITY.get(entity_type)
        if section_index is None:
            # This file's header put it in a type the Camera tab doesn't claim to support
            # (e.g. a d*c*.dat that turned out to be a weapon-adjacent oddity) - not this
            # sweep's concern, the tab correctly hides itself for those.
            skipped_unsupported_type += 1
            continue

        original_section = bytes(manager.enemy.section_raw_data[section_index])
        original_file_size = os.path.getsize(path)

        if len(original_section) < 6:
            empty_sections += 1
            continue

        try:
            collection = parse_camera_collection(original_section)
        except CameraParseError as e:
            failures.append(f"{name} (S{section_index}): failed to parse ({e!r})")
            continue

        # Structural round-trip: the parsed model must serialize back to the exact same bytes
        # even before touching the file writer.
        if bytes(collection.get_bytes()) != original_section:
            failures.append(f"{name} (S{section_index}): model round-trip changed the bytes")
            continue

        # Full round-trip through the real file writer.
        out = str(tmp_path / name)
        try:
            manager.save_file(out)
        except Exception as e:
            failures.append(f"{name}: save_file() raised ({e!r})")
            continue

        if os.path.getsize(out) != original_file_size:
            failures.append(
                f"{name}: overall file size changed on a no-op save "
                f"({original_file_size} -> {os.path.getsize(out)} bytes)")

        try:
            manager.init_from_file(out)
        except Exception as e:
            failures.append(f"{name}: saved file failed to reload ({e!r})")
            continue

        reloaded_section = bytes(manager.enemy.section_raw_data[section_index])
        if reloaded_section != original_section:
            failures.append(f"{name} (S{section_index}): camera section changed after save+reload")
        else:
            checked += 1
        os.remove(out)

    assert not failures, "Camera round-trip failures:\n" + "\n".join(failures)
    # Sanity on the sweep's own coverage - if these drop to zero the assertions above are
    # vacuously true and this test would stop meaning anything.
    assert checked >= 50, f"only {checked} files were actually verified end-to-end"
    print(f"\ncamera sweep: {checked} verified, {empty_sections} empty (skipped), "
          f"{skipped_unsupported_type} unsupported entity type (skipped), "
          f"{skipped_garbage_files} garbage/stub files (skipped)")


def test_editing_a_keyframe_persists_through_save_reload(manager, tmp_path):
    """Not just preservation - an actual edit must survive save+reload, sampled across a
    spread of monster ids and every character file (full 217-file sweep would duplicate
    test_every_camera_bearing_file_round_trips_through_a_real_save's cost for no extra
    signal beyond what one edit-path check per family already gives)."""
    sample = MONSTER_FILES[::15] + CHARACTER_FILES
    edited_count = 0
    no_keyframe_count = 0

    for path in sample:
        name = os.path.basename(path)
        try:
            manager.init_from_file(path)
        except GarbageFileError:
            continue  # non-standard stub slot, e.g. c0m127.dat - see the other sweep test
        entity_type = manager.enemy.entity_type
        section_index = _CAMERA_SECTION_BY_ENTITY.get(entity_type)
        if section_index is None:
            continue

        original_section = bytes(manager.enemy.section_raw_data[section_index])
        if len(original_section) < 6:
            continue
        collection = parse_camera_collection(original_section)
        field = _first_editable_field(collection)
        if field is None:
            no_keyframe_count += 1
            continue

        new_value = 12345 if field.get() != 12345 else -12345
        field.set(new_value)
        edited_bytes = bytes(collection.get_bytes())
        assert len(edited_bytes) == len(original_section), f"{name}: edit resized the section"
        manager.enemy.section_raw_data[section_index] = bytearray(edited_bytes)

        out = str(tmp_path / name)
        manager.save_file(out)
        manager.init_from_file(out)
        reloaded = bytes(manager.enemy.section_raw_data[section_index])
        assert reloaded == edited_bytes, f"{name}: edited keyframe did not survive save+reload"
        os.remove(out)
        edited_count += 1

    assert edited_count >= 5, f"only {edited_count} files actually had an edit verified"
    print(f"\nedit sweep: {edited_count} edited+verified, {no_keyframe_count} had no keyframes")
