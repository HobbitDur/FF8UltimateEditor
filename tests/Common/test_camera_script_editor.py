"""The camera script's user-friendly view (camera_script.json): scripts read into steps and write back
byte for byte, jumps stay on their command through edits, numbers and jumps get their byte size, and
the Script tab's rows, Code view, Apply and info button work together."""
import re
import sys

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

from FF8GameData.dat.camerascriptsteps import (CameraScriptInfo, ScriptStep, new_step, reachable_steps,
                                               read_steps, script_bytes)

STAGE = "extracted_files/battle/a0stg006.x"
# The script every vanilla stage has (see FF8GameData.dat.camerascript)
STAGE_SCRIPT = bytes.fromhex("0500c310e57fc100cb7fea06e607e60201e6f1030200 00".replace(" ", ""))


@pytest.fixture(scope="module")
def vm():
    from FF8GameData.gamedata import GameData
    from FF8GameData.dat.sequencevm import camera_sequence_vm
    game_data = GameData("FF8GameData")
    game_data.load_camera_sequence_data()
    return camera_sequence_vm(game_data)


@pytest.fixture(scope="module")
def info(vm):
    return CameraScriptInfo(vm.script_json)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def test_every_op_code_has_a_command(vm, info):
    assert set(info.command_of_op_code) == {entry["op_code"] for entry in vm.data_json["op_code_info"]}
    # every read value the VM knows is named, and the stage context says what variable 0 holds there
    assert {entry["param_id"] for entry in vm.data_json["special_change_current_value_params"]
            if entry["param_id"] < 0x80} <= set(info.read_variables)
    assert "scene.out" in info.variable_help(0, "stage") and "opening shot" in info.variable_help(0, "spell")
    assert "BS_CameraInit" in info.info_html("stage") and "BS_CameraInit" not in info.info_html("spell")


def test_the_stage_script_reads_as_steps(vm, info):
    steps = read_steps(vm, info, STAGE_SCRIPT)
    assert [step.command_id for step in steps] == ["play_var", "value", "store", "value", "value", "jump", "jump",
                                                  "jump", "wait", "jump", "capture_return", "end", "play"]
    assert steps[5].condition == "ne" and steps[5].target is steps[8]       # shot playing: wait
    assert steps[9].target is steps[1]                                      # next frame: test again
    assert steps[1].operation == "set" and steps[1].operand == "variable" and steps[1].value == 0x10
    runs = reachable_steps(steps)
    assert id(steps[7]) not in runs and id(steps[12]) not in runs          # dead jump, filler after the end
    assert script_bytes(info, steps) == STAGE_SCRIPT


@pytest.mark.ff8data("extracted_files/FF8_EN.exe")
def test_every_vanilla_script_writes_back_unchanged(vm, info):
    import glob
    from FF8GameData.battlestage.stagecamera import stage_camera_track
    from FF8GameData.gamedata import GameData
    from Fujin.cameraeffectmanager import CameraEffectManager
    scripts = []
    for path in sorted(glob.glob("extracted_files/battle/a0stg*.x")):
        stage_id = int(re.search(r"a0stg(\d+)", path).group(1))
        scripts.append(stage_camera_track(open(path, "rb").read(), stage_id, vm).script)
    manager = CameraEffectManager(GameData("FF8GameData"))
    manager.load_exe("extracted_files/FF8_EN.exe")
    scripts += [track.script for track in manager.tracks.values()]
    assert len(scripts) > 300
    for script in scripts:
        assert script_bytes(info, read_steps(vm, info, script)) == bytes(script)


def test_jumps_follow_their_command(vm, info):
    steps = read_steps(vm, info, STAGE_SCRIPT)
    wait = steps[8]
    steps.insert(6, new_step(info, "capture_return"))           # one byte more before the wait
    steps.insert(0, ScriptStep("play", 0x00, value=0x12))       # and two at the start
    data = script_bytes(info, steps)
    again = read_steps(vm, info, data)
    assert again[6].target is again[steps.index(wait)]           # "if not 0" still lands on the wait
    assert again[11].target is again[2]                          # the loop still tests the shot flag


def test_a_far_jump_becomes_int16_and_numbers_get_their_size(vm, info):
    jump = new_step(info, "jump")
    steps = [jump] + [ScriptStep("value", 0xC1, value=1, operation="add", operand="sbyte") for _ in range(70)]
    steps.append(new_step(info, "end"))
    jump.target = steps[-1]                                      # 140 bytes away: past an 8-bit offset
    data = script_bytes(info, steps)
    assert data[0] == 0xED and int.from_bytes(data[1:3], "little") == 143
    value = ScriptStep("value", 0xC1, value=300, operation="set", operand="sbyte")
    assert script_bytes(info, [value]) == bytes([0xC0]) + (300).to_bytes(2, "little")
    value.value = 200                                            # an int16 that fits keeps its form
    assert script_bytes(info, [value]) == bytes([0xC0, 200, 0])
    assert script_bytes(info, [ScriptStep("value", 0xC1, value=200, operation="sub", operand="sbyte")]) == \
        bytes([0xCA, 200])                                       # 200 is too big for sbyte: ubyte


@pytest.mark.ff8data(STAGE)
def test_script_tab_rows_code_and_apply(qapp, vm, monkeypatch):
    from Alexander.alexandermanager import AlexanderManager
    from Common.cameratrackeditor import CameraTrackEditor, VIEW_CODE, VIEW_USER_FRIENDLY
    from FF8GameData.battlestage.stagecamera import stage_camera_track
    manager = AlexanderManager()
    track = stage_camera_track(open(STAGE, "rb").read(), 6, manager.vm)
    editor = CameraTrackEditor(manager, room_name="stage file", context="stage")
    editor.set_slot_notes({(0, 0): "intro of encounter 1 (main)"})
    editor.set_track(track)
    steps_widget = editor.script_steps
    assert steps_widget.rows == []          # built when the view shows (a spell script has ~150 rows)
    steps_widget.ensure_rows()
    assert editor.script_view_combo.currentIndex() == VIEW_USER_FRIENDLY
    assert len(steps_widget.rows) == 13 and "never runs" in steps_widget.rows[12].description_label.text()
    assert "intro of encounter 1" in steps_widget.rows[12].description_label.text()
    assert steps_widget.rows[8].source_label.text() == "◀ 6, 8"

    # Pick another animation for the first command: the code follows, Apply writes it
    row = steps_widget.rows[0]
    row.command_combo.setCurrentIndex(row.command_combo.findData("play"))
    set_combo, slot_combo = [steps_widget.rows[0].param_layout.itemAt(i).widget() for i in range(2)]
    slot_combo.setCurrentIndex(slot_combo.findData(1))
    assert editor.script_editor.toPlainText().splitlines()[0] == "play(1)"
    # A jump picks its command from the list: line 6 now waits at line 12 (capture_return)
    target_combo = steps_widget.rows[5].param_layout.itemAt(1).widget()
    target_combo.setCurrentIndex(target_combo.findData(10))
    assert steps_widget.steps[5].target is steps_widget.steps[10]
    assert "go to line 11" in steps_widget.rows[5].description_label.text()
    assert steps_widget.rows[10].source_label.text() == "◀ 6, 7"
    target_combo.setCurrentIndex(target_combo.findData(8))   # back to the wait
    assert editor.script_size_label.text() == "23 / 23 bytes"
    editor._apply_script()
    assert track.script[:2] == bytes([0x00, 0x01]) and track.script[2:] == STAGE_SCRIPT[2:]
    steps_widget.ensure_rows()

    # Removing a jump's target moves the jump to the next command
    steps_widget._on_action(steps_widget.rows[8], "remove")     # the wait
    assert steps_widget.steps[5].target is steps_widget.steps[8] and steps_widget.steps[8].command_id == "jump"

    # Code view: a hand edit shows in the rows when switching back; broken code keeps the Code view
    editor.script_view_combo.setCurrentIndex(VIEW_CODE)
    editor.script_editor.setPlainText("play(0x12)\nend_clear()")
    editor.script_view_combo.setCurrentIndex(VIEW_USER_FRIENDLY)
    assert [step.command_id for step in steps_widget.steps] == ["play", "end"]
    steps_widget.ensure_rows()
    assert "set 1 slot 2" in steps_widget.rows[0].description_label.text()
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    editor.script_view_combo.setCurrentIndex(VIEW_CODE)
    editor.script_editor.setPlainText("not_a_command(")
    editor.script_view_combo.setCurrentIndex(VIEW_USER_FRIENDLY)
    assert warnings and editor.script_view_combo.currentIndex() == VIEW_CODE

    shown = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: shown.append(self.text()))
    editor.script_info_button.click()
    assert shown and "Battle stage script" in shown[0]
