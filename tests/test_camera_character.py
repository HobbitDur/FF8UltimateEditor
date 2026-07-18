"""Character camera (section 5) round-trips through load -> edit -> save -> reload.

A character (dXc) file carries its camera collection in section 5 as the SAME bare-collection
format as a monster section 6, just with 2 sets (verified against FF8_EN.exe: the engine plays
the acting entity's own collection via cameraWhenDoingAction / command_queue->unk09). These
guards pin the Camera tab's flow for characters: the file loads as a 2-set collection, and an
edit written into section_raw_data[5] survives a real save_file()/reload byte-for-byte.
"""
import glob
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from FF8GameData.dat.cameracollection import parse_camera_collection
from FF8GameData.monsterdata import EntityType

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHAR_FILES = sorted(glob.glob(os.path.join(REPO, "extracted_files", "battle", "d*c*.dat")))

pytestmark = pytest.mark.skipif(not CHAR_FILES, reason="extracted battle files not available")


@pytest.fixture(scope="module")
def app():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _load(path):
    from Ifrit.ifritmanager import IfritManager
    mgr = IfritManager(os.path.join(REPO, "FF8GameData"))
    mgr.init_from_file(path)
    return mgr


def _first_frame_field(collection):
    """A pos_x field of the first real keyframe, or None if the file has no camera motion."""
    for camera_set in collection.sets:
        for animation in camera_set.animations:
            if animation.empty:
                continue
            for block in animation.blocks:
                if block.frames:
                    return block.frames[0].pos_x
    return None


def test_all_character_files_are_two_set_collections(app):
    for path in CHAR_FILES:
        mgr = _load(path)
        assert mgr.enemy.entity_type in (EntityType.CHARACTER, EntityType.CHARACTER_NO_WEAPON), \
            f"{os.path.basename(path)}: unexpected entity type {mgr.enemy.entity_type}"
        section5 = bytes(mgr.enemy.section_raw_data[5])
        collection = parse_camera_collection(section5)
        assert collection.nb_set == 2, f"{os.path.basename(path)}: expected 2 sets, got {collection.nb_set}"
        assert collection.eof == len(section5), f"{os.path.basename(path)}: eof != section length"


def test_no_op_save_keeps_section5_byte_identical(app, tmp_path):
    path = CHAR_FILES[0]
    mgr = _load(path)
    original = bytes(mgr.enemy.section_raw_data[5])
    out = str(tmp_path / "noop.dat")
    mgr.save_file(out)
    assert bytes(_load(out).enemy.section_raw_data[5]) == original


def test_character_camera_edit_round_trips(app, tmp_path):
    path = CHAR_FILES[0]
    mgr = _load(path)
    collection = parse_camera_collection(bytes(mgr.enemy.section_raw_data[5]))
    field = _first_frame_field(collection)
    assert field is not None, "the test file should have at least one keyframe"

    new_value = 1234 if field.get() != 1234 else 4321
    field.set(new_value)
    edited = bytes(collection.get_bytes())
    assert len(edited) == len(mgr.enemy.section_raw_data[5]), "a value edit must not resize the section"
    # This is exactly what IfritCameraSeqWidget.save_file() does before the file writer runs.
    mgr.enemy.section_raw_data[5] = bytearray(edited)

    out = str(tmp_path / "edited.dat")
    mgr.save_file(out)

    reloaded = bytes(_load(out).enemy.section_raw_data[5])
    assert reloaded == edited, "the section-5 edit must survive save + reload"
    assert parse_camera_collection(reloaded).nb_set == 2, "reloaded section 5 still parses as a 2-set collection"
