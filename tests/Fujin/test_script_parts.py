"""A cinematic effect's script edited part by part (Fujin/scriptparts.py, a description's "script"): Disease Breath's
parts and their values, written to its file, and what the game's code then draws."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from FF8GameData.psxgpu.fxdump import parse_recording
from Fujin.effectprogram import load_description
from Fujin.scriptparts import apply_script_values, edits, read_value, script_matches, script_values, with_script_parts

ROOT = Path(__file__).resolve().parents[2]
EXE = ROOT / "extracted_files/FF8_EN.exe"
MAGIC, BATTLE = ROOT / "extracted_files/magic", ROOT / "extracted_files/battle"
SCRIPT = ("extracted_files/magic/MAG230_B.00",)
FILES = ("extracted_files/FF8_EN.exe", "extracted_files/magic/MAG230_B.00", "extracted_files/magic/MAG230_B.01",
         "extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat", "extracted_files/battle/c0m009.dat")
SPARKS, CLOUD, RINGS, SWIRL_1, SWIRL_2 = 0x3F8, 0x14A, 0x212, 0x2D4, 0x350


@pytest.fixture
def script():
    return load_description(231)["script"]


def _file():
    return (MAGIC / "MAG230_B.00").read_bytes()


@pytest.mark.ff8data(*SCRIPT)
def test_every_value_is_the_one_the_game_has(script):
    data = _file()
    assert script_matches(script, data)
    assert script_values(script, data) == {field["key"]: field["default"] for field in script["fields"]}
    parts = {part["key"] for part in script["parts"]}
    assert {field["part"] for field in script["fields"]} == parts
    assert len({field["key"] for field in script["fields"]}) == len(script["fields"])


@pytest.mark.ff8data(*SCRIPT)
def test_a_value_is_written_where_it_is_read_and_nowhere_else(script):
    data = _file()
    for field in script["fields"]:
        value = field["max"] if field["default"] != field["max"] else field["min"]
        edited = apply_script_values(script, data, {field["key"]: value})
        assert read_value(field, edited) == value, field["key"]
        assert len(edited) == len(data)
        changed = {at for at in range(len(data)) if edited[at] != data[at]}
        allowed = {at + index for at, raw in edits(field, value, data) for index in range(len(raw))}
        assert changed <= allowed, field["key"]
    # the modifier of an instruction keeps its opcode
    wait = next(field for field in script["fields"] if field["key"] == "script.timing.start")
    assert apply_script_values(script, data, {wait["key"]: 5})[0x8C:0x8E] == bytes.fromhex("090a")


@pytest.mark.ff8data(*SCRIPT)
def test_a_file_laid_out_otherwise_is_not_edited(script):
    data = bytearray(_file())
    assert not script_matches(script, bytes(data[:-1]))
    data[0x8C] = 0x0A                                   # another instruction where a Wait is expected
    assert not script_matches(script, bytes(data))


def test_a_description_without_a_script_keeps_its_parts():
    schema = {"parts": [{"id": 0}], "fields": [], "groups": []}
    assert with_script_parts(schema, {"parts": []}) is schema
    assert with_script_parts(None, load_description(231)) is None
    both = with_script_parts(schema, {"script": {"parts": [{"id": 1}], "fields": [{"key": "script.a"}], "groups": []}})
    assert [part["id"] for part in both["parts"]] == [0, 1] and both["fields"] == [{"key": "script.a"}]


def test_the_script_parts_stay_out_of_the_effects_program():
    assert all(param["key"].startswith("files.") for param in load_description(231)["params"])


def _record(folder, tmp_path, tag, *extra):
    from Fujin.recorderbuild import RECORDER
    if not RECORDER.is_file():
        pytest.skip("the effect recorder is not built")
    from FF8GameData.psxgpu.fxdump import load_recording
    out = tmp_path / f"{tag}.txt"
    run = subprocess.run([str(RECORDER), "231", f"exe={EXE}", f"magic={folder}", f"battle={tmp_path}", f"out={out}", "native=1", "actors=2",
                          f"slot0={BATTLE / 'd0c000.dat'}", f"weapon0={BATTLE / 'd0w000.dat'}", f"slot3={BATTLE / 'c0m009.dat'}", "caster=0", "target=3",
                          "sequences=1", *extra], cwd=str(RECORDER.parent), capture_output=True, text=True, timeout=120)
    assert "faulted" not in run.stdout, run.stdout[-300:]
    return load_recording(str(out))


def _middle(box):
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


@pytest.mark.ff8data(*FILES)
def test_each_part_is_recorded_under_its_own_id(tmp_path, script):
    folder = tmp_path / "effect"
    folder.mkdir()
    shutil.copy(MAGIC / "MAG230_B.00", folder)
    shutil.copy(MAGIC / "MAG230_B.01", folder)
    recording = _record(folder, tmp_path, "parts")
    drawn = {part for tick in recording.ticks for part in tick.parts}
    assert {part["id"] for part in script["parts"] if part["id"]} <= drawn
    # the sparks gather before the rest
    first = lambda part: next(index for index, tick in enumerate(recording.ticks) if part in tick.parts)
    assert first(SPARKS) < first(CLOUD) == first(RINGS) < first(SWIRL_1) == first(SWIRL_2)


@pytest.mark.ff8data(*FILES)
def test_the_purple_lines_follow_what_moves(tmp_path, script):
    folder = tmp_path / "effect"
    folder.mkdir()
    shutil.copy(MAGIC / "MAG230_B.00", folder)
    shutil.copy(MAGIC / "MAG230_B.01", folder)
    game = _record(folder, tmp_path, "game")
    moves = lambda path: len({(x, y) for _tick, x, y in path}) > 1
    # each ring stays where it is released, the rising puffs rise, the trail's don't
    assert game.sprite_paths({RINGS}) and not any(moves(path) for path in game.sprite_paths({RINGS}))
    puffs = game.sprite_paths({CLOUD})
    assert any(moves(path) for path in puffs) and not all(moves(path) for path in puffs)
    # the Path tab draws the cloud's own way, and a value edited moves it
    parts = {part["key"]: part for part in script["parts"]}
    way = lambda recording: recording.sprite_paths(set(parts["path"]["paths"]))[0]
    assert parts["timing"]["paths"] == [] and moves(way(game))
    (folder / "MAG230_B.00").write_bytes(apply_script_values(script, _file(), {"script.path.speed": 2048}))
    slow = _record(folder, tmp_path, "slow")
    assert way(slow)[0] == way(game)[0] and way(slow)[-1] != way(game)[-1]
    (folder / "MAG230_B.00").write_bytes(apply_script_values(script, _file(), {"script.path.start": 1}))
    assert way(_record(folder, tmp_path, "target"))[0] != way(game)[0]


def test_a_purple_line_is_seen_by_the_camera_of_the_tick_shown():
    """A point at (0, 0, 1000) in the battle; the camera then moves it 100 to the right and to 2000 away, then behind it."""
    camera = lambda x, z: f"4096 0 0 0 4096 0 0 0 4096 {x} 0 {z} 640 160 112"
    recording = parse_recording([
        f"W 0 {camera(0, 0)}", "P 0 7 1 1280 896 0 0 1000",
        f"W 1 {camera(100, 1000)}", "P 1 7 1 1536 896 100 0 2000",
        f"W 2 {camera(0, -5000)}", "P 2 7 1 1280 896 0 0 -4000",
        "P 3 8 1 10 20"])
    seen = lambda tick: [[(index, round(x), round(y)) for index, x, y in path] for path in recording.sprite_paths({7}, camera_tick=tick)]
    assert seen(0) == [[(0, 1280, 896), (1, 1280, 896), (2, 1280, 896)]]    # it never moved in the battle
    assert seen(1) == [[(0, 1536, 896), (1, 1536, 896), (2, 1536, 896)]]    # 8 * 100 * 640 / 2000 + 8 * 160
    assert seen(2) == []                                                    # behind the camera
    # at their own tick: where the game drew them; a recording without a position stays as drawn
    assert recording.sprite_paths({7}) == [[(0, 1280, 896), (1, 1536, 896), (2, 1280, 896)]]
    assert recording.sprite_paths({8}, camera_tick=0) == [[(3, 10, 20)]]
    # a tick without a camera yet (all zeros): its point has no place in the battle, the others do, seen by the closest camera
    recording = parse_recording(["W 0 0 0 0 0 0 0 0 0 0 0 0 0 352 160 112", "P 0 7 1 1280 896 0 0 0",
                                 f"W 1 {camera(0, 0)}", "P 1 7 1 1280 896 0 0 1000"])
    assert recording.ticks[0].view is None
    assert recording.sprite_paths({7}, camera_tick=0) == [[(1, 1280.0, 896.0)]]


@pytest.mark.ff8data(*FILES)
def test_the_purple_lines_land_where_the_game_draws(tmp_path, script):
    folder = tmp_path / "effect"
    folder.mkdir()
    shutil.copy(MAGIC / "MAG230_B.00", folder)
    shutil.copy(MAGIC / "MAG230_B.01", folder)
    recording = _record(folder, tmp_path, "camera", "gamecamera=1", "camvar=0")
    assert len({(tuple(tick.view[0]), tuple(tick.view[1])) for tick in recording.ticks if tick.view}) > 1   # it moves
    way = set(next(part for part in script["parts"] if part["key"] == "path")["paths"])
    drawn = recording.sprite_paths(way)[0]
    compared = 0
    for index, x, y in drawn:
        seen = [point for path in recording.sprite_paths(way, camera_tick=index) for point in path if point[0] == index]
        if seen:                                                    # (not while it passes behind that camera)
            compared += 1
            assert abs(seen[0][1] - x) <= 16 and abs(seen[0][2] - y) <= 16, index
    assert compared > len(drawn) * 3 // 4


@pytest.mark.ff8data(*FILES)
def test_the_game_camera_holds_the_view_until_its_shot_moves(tmp_path):
    """Disease Breath's shot holds the current view for 10 ticks (keyframe modes 0xF3, 0xF4), then leaves it towards the target: not from the world's origin."""
    folder = tmp_path / "effect"
    folder.mkdir()
    shutil.copy(MAGIC / "MAG230_B.00", folder)
    shutil.copy(MAGIC / "MAG230_B.01", folder)
    recording = _record(folder, tmp_path, "camera", "gamecamera=1", "camvar=0", "castcam=0,-1500,6000,0,-500,-1000")
    start = ((0, -1500, 6000), (0, -500, -1000))
    assert all(recording.ticks[index].camera == start for index in range(13))
    assert recording.ticks[20].camera != start and abs(recording.ticks[20].camera[0][2] - 6000) < 1000
    assert all(tick.view for tick in recording.ticks)


@pytest.mark.ff8data(*FILES)
def test_the_tight_rings_go_on_when_the_wide_ones_start(tmp_path, script):
    """StartChannel 0 takes the first free channel: unlike the puffs (channel 2, replaced), both kinds of rings run together."""
    folder = tmp_path / "effect"
    folder.mkdir()
    shutil.copy(MAGIC / "MAG230_B.00", folder)
    shutil.copy(MAGIC / "MAG230_B.01", folder)
    recording = _record(folder, tmp_path, "rings")
    first = next(index for index, tick in enumerate(recording.ticks) if RINGS in tick.parts)
    count = lambda after, part: len(recording.ticks[first + after].part_packets({part}))
    assert count(8, RINGS) == 16 and count(32, RINGS) == 32     # 2 a tick, then 4 a tick, for 8 ticks each
    assert count(16, CLOUD) == count(32, CLOUD) == 16           # 1 a tick throughout


@pytest.mark.ff8data(*FILES)
@pytest.mark.parametrize("place", [(), ("pos3=1500,0,-2500",)], ids=["where it stands", "moved"])
def test_from_the_target_the_cloud_never_leaves_it(tmp_path, script, place):
    """The bone is spawned before it gets its position in the game's order: its first puff goes to the world's origin, on the
    way from the caster it goes unnoticed. From the target the position comes first."""
    folder = tmp_path / "effect"
    folder.mkdir()
    shutil.copy(MAGIC / "MAG230_B.01", folder)
    start = next(field for field in script["fields"] if field["key"] == "script.path.start")
    (folder / "MAG230_B.00").write_bytes(apply_script_values(script, _file(), {start["key"]: 1}))
    recording = _record(folder, tmp_path, "target", *place)
    target = recording.part_box(0, {0})
    wide = (target[2] - target[0]) * 1.5
    for index, tick in enumerate(recording.ticks):
        if CLOUD in tick.parts:
            box = recording.part_box(index, {CLOUD})
            assert abs(_middle(box)[0] - _middle(target)[0]) < wide + (box[2] - box[0]) / 2, index
    (folder / "MAG230_B.00").write_bytes(_file())
    game = _record(folder, tmp_path, "game", *place)
    first = next(index for index, tick in enumerate(game.ticks) if CLOUD in tick.parts)
    assert game.part_box(first, {CLOUD}) != recording.part_box(first, {CLOUD})


@pytest.mark.ff8data(*FILES)
def test_a_size_edited_draws_bigger(tmp_path, script):
    folder = tmp_path / "effect"
    folder.mkdir()
    shutil.copy(MAGIC / "MAG230_B.00", folder)
    shutil.copy(MAGIC / "MAG230_B.01", folder)
    game = _record(folder, tmp_path, "game")
    (folder / "MAG230_B.00").write_bytes(apply_script_values(script, _file(), {"script.rings.first.size": 800}))
    bigger = _record(folder, tmp_path, "bigger")
    tick = next(index for index, tick in enumerate(game.ticks) if RINGS in tick.parts) + 4
    width = lambda recording: recording.part_box(tick, {RINGS})[2] - recording.part_box(tick, {RINGS})[0]
    assert width(bigger) > width(game)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.mark.ff8data(*FILES)
def test_the_tabs_edit_the_effects_file_with_one_undo_a_change(qapp, tmp_path, script):
    from Fujin import nativepreview
    from Fujin.fujinwidget import FujinWidget
    if not nativepreview.RECORDER.is_file():
        pytest.skip("the effect recorder is not built")
    for name in ("MAG230_B.00", "MAG230_B.01"):
        shutil.copy(MAGIC / name, tmp_path / name)
    fujin = FujinWidget()
    fujin.select_effect(231)
    tabs = {tab.part["key"]: tab for tab in fujin.part_tabs}
    assert {"timing", "path", "sparks", "cloud", "rings", "swirl_a", "swirl_b"} <= set(tabs)
    start = tabs["path"].spins["script.path.start"]
    assert not start.isEnabled() and "Import" in tabs["path"].doc.text()
    fujin.import_paths([str(tmp_path / "MAG230_B.00"), str(tmp_path / "MAG230_B.01")])
    assert start.isEnabled() and start.value() == 0
    speed = tabs["path"].spins["script.path.speed"]
    assert speed.value() == 4096
    manager = next(m for m in fujin.mag_editor.managers.values() if m.file_path.endswith("MAG230_B.00"))
    start.setValue(1)
    assert bytes(manager.data[0xDE:0xE6]).hex() == "6000f10032002a00" and manager.modified
    assert fujin.can_save_folder()
    fujin._refresh()
    assert speed.value() == 0                           # what the choice also sets
    manager.undo()                                      # a single step: the file is as the game's again
    assert bytes(manager.data) == _file()
    fujin._refresh()
    assert start.value() == 0 and speed.value() == 4096
    # an effect made from it edits the file its Files tab names
    assert fujin.new_effect_dialog(349, "Bio", 231) == 349
    other = tmp_path / "mag348_b.00"
    other.write_bytes(_file())
    fujin.import_paths([str(other)])
    fujin.effect_params.setdefault(349, {})["files.file00"] = "mag348_b.00"
    fujin._build_part_tabs()
    tabs = {tab.part["key"]: tab for tab in fujin.part_tabs}
    tabs["timing"].spins["script.timing.camera"].setValue(1)
    own = next(m for m in fujin.mag_editor.managers.values() if m.file_path.endswith("mag348_b.00"))
    assert bytes(own.data[0x5A:0x5C]).hex() == "3930" and bytes(manager.data) == _file()


def test_a_missing_shared_texture_is_sent_to_import_complementary():
    from Fujin.nativepreview import recording_notes
    notes = recording_notes("missing battle file a8def.tim (for a load)\nmissing battle file MAG200_B.02 (for a load)")
    assert "a8def.tim not imported (Import complementary)" in notes and "NOT IMPORTED, asked for by the effect: MAG200_B.02" in notes
    assert "NOT IMPORTED" not in recording_notes("missing battle file a8def.tim (for a load)")
