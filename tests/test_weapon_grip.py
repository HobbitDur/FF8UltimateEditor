"""30 fps: a character's weapon keeps its grip in the hand on the new in-between frames
(FF8GameData/dat/weapongrip.py). Selphie's nunchaku left her hand by up to 5.8 vertex units on
one in-between frame of a fast swing, back in it the next: a shiver at 30 Hz.

Needs the vanilla d5c011 / d5w028-031 (Selphie) in extracted_files/battle, or in the folder named
by FF8_BATTLE_FOLDER.
"""
import os
import pathlib
import shutil

import numpy as np
import pytest

from FF8GameData.dat import weapongrip
from FF8GameData.dat.monsteranalyser import MonsterAnalyser
from Ifrit.ifritmanager import IfritManager

PROJECT_ROOT = pathlib.Path(__file__).parent.parent
BATTLE_PATH = pathlib.Path(os.environ.get("FF8_BATTLE_FOLDER", PROJECT_ROOT / "extracted_files" / "battle"))
FAMILY = ["d5c011.dat", "d5w028.dat", "d5w029.dat", "d5w030.dat", "d5w031.dat"]
pytestmark = pytest.mark.skipif(not all((BATTLE_PATH / name).exists() for name in FAMILY),
                                reason="Selphie's vanilla battle files not available")


@pytest.fixture(scope="module")
def manager():
    return IfritManager(str(PROJECT_ROOT / "FF8GameData"))


def _load(manager, path):
    model = MonsterAnalyser(manager.game_data)
    model.load_file_data(str(path), manager.game_data)
    model.analyse_loaded_data(manager.game_data)
    return model


@pytest.fixture(scope="module")
def converted(manager, tmp_path_factory):
    folder = tmp_path_factory.mktemp("selphie30")
    for name in FAMILY:
        shutil.copy(BATTLE_PATH / name, folder / name)
    report_list = manager.convert_file_list_to_fps([str(folder / name) for name in FAMILY], 30)
    assert not any(report['error'] or report['skipped_list'] for report in report_list)
    return folder, {report['file']: report for report in report_list}


def test_the_grip_is_the_handle_in_the_hand(manager):
    """On the vanilla frames, the nunchaku handle (weapon bone 2) stays on her hand (body bone 24),
    for every nunchaku, though only the Flail has a vertex on that pivot."""
    body = _load(manager, BATTLE_PATH / "d5c011.dat")
    for name in FAMILY[1:]:
        weapon = _load(manager, BATTLE_PATH / name)
        # find_grip reads the even frames of a converted file: each vanilla frame twice
        pairs = [(anim_id, [frame for frame in body_frames for _ in (0, 1)],
                  [frame for frame in weapon_frames for _ in (0, 1)])
                 for anim_id, body_frames, weapon_frames in weapongrip._pairs(body, weapon)]
        grip = weapongrip.find_grip(body, weapon, pairs)
        assert (grip.weapon_bone, grip.body_bone) == (2, 24), name
        assert grip.spread < 0.05, name


def test_every_in_between_keeps_the_grip_in_the_hand(manager, converted):
    folder, report_by_name = converted
    body = _load(manager, folder / "d5c011.dat")
    for name in FAMILY[1:]:
        grip_report = report_by_name[name]['grip_report']
        assert grip_report['nb_pinned'] > 200, name
        assert grip_report['worst_before'] > 5, name         # the 5.8 in-between of anim 30
        weapon = _load(manager, folder / name)                # as saved, then read back
        grip = grip_report['grip']
        for anim_id, body_frames, weapon_frames in weapongrip._pairs(body, weapon):
            for index in range(len(weapon_frames)):
                distance = np.linalg.norm(grip.offset(body, weapon, body_frames[index], weapon_frames[index]))
                assert distance < 0.25, (name, anim_id, index, distance)


@pytest.mark.skipif(not all((BATTLE_PATH / name).exists() for name in ("dac021.dat", "daw039.dat")),
                    reason="Ward's vanilla battle files not available")
def test_a_weapon_without_a_steady_grip_is_left_as_blended(manager, tmp_path, monkeypatch):
    """No point of Ward's harpoon stays in his hand (it leaves it by up to 18 units): nothing to
    pin, the weapon is the plain conversion."""
    family = ["dac021.dat", "daw039.dat"]
    for folder in ("pinned", "plain"):
        (tmp_path / folder).mkdir()
        for name in family:
            shutil.copy(BATTLE_PATH / name, tmp_path / folder / name)
    report_list = manager.convert_file_list_to_fps([str(tmp_path / "pinned" / name) for name in family], 30)
    grip_report = {report['file']: report for report in report_list}["daw039.dat"]['grip_report']
    assert not grip_report['steady'] and grip_report['nb_pinned'] == 0
    monkeypatch.setattr(weapongrip, "pin_family_grips", lambda model_by_name: {})
    manager.convert_file_list_to_fps([str(tmp_path / "plain" / name) for name in family], 30)
    assert (tmp_path / "pinned" / "daw039.dat").read_bytes() == (tmp_path / "plain" / "daw039.dat").read_bytes()


def test_the_original_frames_and_the_body_are_untouched(manager, converted, monkeypatch):
    """Only the weapon roots of in-between frames move: the original frames keep their vanilla
    root, the body is the family's conversion without the pinning, and a weapon differs from
    it in its in-between roots only."""
    folder, _report_by_name = converted
    for name in FAMILY[1:]:
        vanilla = _load(manager, BATTLE_PATH / name)
        weapon = _load(manager, folder / name)
        for vanilla_anim, anim in zip(vanilla.animation_data.animations, weapon.animation_data.animations):
            for index, frame in enumerate(vanilla_anim.frames):
                assert ([p.get_pos_raw() for p in anim.frames[2 * index].position]
                        == [p.get_pos_raw() for p in frame.position]), (name, index)
    plain = folder / "plain"
    plain.mkdir()
    for name in FAMILY:
        shutil.copy(BATTLE_PATH / name, plain / name)
    monkeypatch.setattr(weapongrip, "pin_family_grips", lambda model_by_name: {})
    manager.convert_file_list_to_fps([str(plain / name) for name in FAMILY], 30)
    assert (plain / "d5c011.dat").read_bytes() == (folder / "d5c011.dat").read_bytes()
    for name in FAMILY[1:]:
        unpinned, pinned = _load(manager, plain / name), _load(manager, folder / name)
        for unpinned_anim, pinned_anim in zip(unpinned.animation_data.animations,
                                              pinned.animation_data.animations):
            for frame_a, frame_b in zip(unpinned_anim.frames, pinned_anim.frames):
                assert all(a.get_rotate_raw() == b.get_rotate_raw()
                           for bone_a, bone_b in zip(frame_a.rotation_vector_data, frame_b.rotation_vector_data)
                           for a, b in zip(bone_a, bone_b)), name
