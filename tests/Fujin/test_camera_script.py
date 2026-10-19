"""The camera script runner: which keyframe animation an effect's camera script plays."""
import pytest

from FF8GameData.dat.camerascript import (CameraScriptInputs, animation_index_parts, camera_animation_at,
                                          camera_category_value, run_camera_script)

EXE = "extracted_files/FF8_EN.exe"
CURE = 1


@pytest.fixture(scope="module")
def vm():
    from FF8GameData.gamedata import GameData
    from FF8GameData.dat.sequencevm import camera_sequence_vm
    game_data = GameData("FF8GameData")
    game_data.load_camera_sequence_data()
    return camera_sequence_vm(game_data)


def script(vm, code):
    from FF8GameData.dat.sequencecodec import code_to_sequence
    return bytes(code_to_sequence(vm, code))


def test_play_and_play_var_and_end(vm):
    run = run_camera_script(vm, script(vm, "play(3)\nend_clear()\nplay(5)"))
    assert run.played == [3] and run.chosen == 3 and run.stop_reason.startswith("end_clear")
    # A computed index through a camera variable: set 2 slot 1
    run = run_camera_script(vm, script(vm, "set_i8(33)\nstore_var(0x01)\nplay_var(1)\nend()"))
    assert run.chosen == 33 and animation_index_parts(33) == (2, 1)


def test_branches_on_the_inputs(vm):
    # "if target slot >= 3 (a monster) play 1 else play 2", the way effect scripts compare
    code = script(vm, "set_var(0x19)\nstore_var(0x7F)\nset_i8(3)\nsub_var(0x7F)\njump_le(5)\nplay(2)\n"
                      "end_clear()\nplay(1)\nend_clear()")
    assert run_camera_script(vm, code, CameraScriptInputs(target_slot=4)).chosen == 1
    assert run_camera_script(vm, code, CameraScriptInputs(target_slot=0)).chosen == 2
    run = run_camera_script(vm, code, CameraScriptInputs(target_slot=4))
    assert (0x19, 4) in run.reads


def test_opening_shot_none_is_negative_and_random_is_modulo(vm):
    # Camera variable 0 = -1 (no opening shot) must compare below 0, like the game's word read
    code = script(vm, "set_var(0x00)\njump_lt(5)\nplay(0)\nend_clear()\nend_clear()")
    assert run_camera_script(vm, code, CameraScriptInputs(opening=-1)).chosen is None
    assert run_camera_script(vm, code, CameraScriptInputs(opening=0)).chosen == 0
    code = script(vm, "play_var(0x22)\nend_clear()")  # C3 22 = random modulo 8
    assert [run_camera_script(vm, code, CameraScriptInputs(random=value)).chosen
            for value in (0, 7, 8, 13)] == [0, 7, 0, 5]


def test_endless_loop_and_unknown_op_code_stop(vm):
    assert "endless" in run_camera_script(vm, script(vm, "jump(0)")).stop_reason
    assert "past the end" in run_camera_script(vm, script(vm, "play(1)")).stop_reason


def test_camera_category_value():
    assert [camera_category_value(category) for category in (0, 1, 2, 3, 4, 8)] == [3, 2, 1, 0, 4, 5]


@pytest.mark.ff8data(EXE)
def test_every_effect_track_plays_an_animation_of_its_own(vm):
    from FF8GameData.gamedata import GameData
    from Fujin.cameraeffectmanager import CameraEffectManager
    manager = CameraEffectManager(GameData("FF8GameData"))
    manager.load_exe(EXE)
    for inputs in (CameraScriptInputs(), CameraScriptInputs(opening=8, attacker_slot=3, target_slot=0)):
        for track in manager.tracks.values():
            run = run_camera_script(manager.vm, track.script, inputs)
            assert run.stop_reason.startswith("end_clear"), (track.effect_id, run.stop_reason)
            assert camera_animation_at(track.collection, run.chosen) is not None, track.effect_id
    cure = manager.track(CURE)
    # A character's Cure on a monster: random modulo 8 picks the close-up variant
    assert run_camera_script(manager.vm, cure.script, CameraScriptInputs(random=0)).chosen == 23
    assert run_camera_script(manager.vm, cure.script, CameraScriptInputs(random=1)).chosen == 0
    assert run_camera_script(manager.vm, cure.script, CameraScriptInputs(opening=-1)).chosen is None
