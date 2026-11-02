"""Effects run from their descriptions (docs/fujin-effect-description.md): Fujin compiles a description
(FF8GameData/Resources/json/effects/effect_NNN.json) into a program (Fujin/effectprogram.py) the
recorder runs (program=<file>, Tools/fxhost/fxprogram.h) - Cure, Potion, Hypnotize and Antidote exactly as the
exe's code, with their parameters, in a free slot of their own, and changed by changing their
description."""
import copy
import re
import subprocess
from pathlib import Path

import pytest

from Fujin.effectprogram import DescriptionError, compile_program, load_description, write_program

ROOT = Path(__file__).resolve().parents[2]
EXE = ROOT / "extracted_files/FF8_EN.exe"
MAGIC, BATTLE = ROOT / "extracted_files/magic", ROOT / "extracted_files/battle"
FILES = ("extracted_files/FF8_EN.exe", "extracted_files/magic/mag000-049.tim", "extracted_files/magic/mag001.tim",
         "extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat", "extracted_files/battle/c0m009.dat")


def lab_recorder():
    from Fujin.effectparts import effect_schema
    from Fujin.recorderbuild import RECORDER
    if effect_schema(1) is None:
        pytest.skip("the effect recorder is not built with FFNx's effect sources (the updater's FFNxEffects)")
    return RECORDER


def record(tmp_path, effect, tag, *extra):
    recorder = lab_recorder()
    out = tmp_path / f"{tag}.txt"
    run = subprocess.run([str(recorder), str(effect), f"exe={EXE}", f"magic={MAGIC}", f"battle={BATTLE}", f"out={out}",
                          f"slot0={BATTLE / 'd0c000.dat'}", f"weapon0={BATTLE / 'd0w000.dat'}",
                          f"slot3={BATTLE / 'c0m009.dat'}", "caster=0", "target=3", *extra],
                         cwd=str(recorder.parent), capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stdout[-500:]
    return out.read_text().splitlines(), run.stdout


def untag(lines):
    """Without part tags nor the port's notes (M lines): what the original code draws."""
    return [re.sub(r"^(P|Q \d+) \d+ ", r"\1 0 ", line) for line in lines if not line.startswith("M ")]


def test_cure_and_potion_descriptions_compile():
    for effect in (1, 50):
        description = load_description(effect)
        program = compile_program(description)
        assert program.startswith("# effect program") and f"program {effect} {description['name']}" in program
        assert program.count("\ntask ") == 4 and "director per_action 0" in program
    broken = copy.deepcopy(load_description(1))
    broken["tasks"][1]["motion"] = ["helix", "$ring.steps.nothing", 1]
    with pytest.raises(DescriptionError, match="no parameter ring.steps.nothing"):
        compile_program(broken)
    broken["tasks"][1]["motion"] = ["spiral", 1, 2]
    with pytest.raises(DescriptionError, match="unknown operation spiral"):
        compile_program(broken)


@pytest.mark.ff8data(*FILES)
def test_cure_and_potion_run_from_their_descriptions(tmp_path):
    for effect in (1, 50):
        program = write_program(load_description(effect), tmp_path / f"effect_{effect}.fxprog")
        original, _log = record(tmp_path, effect, f"original{effect}")
        described, log = record(tmp_path, effect, f"described{effect}", f"program={program}")
        assert "4 tasks, 102 params" in log
        assert untag(described) == original and len(original) > 10000


@pytest.mark.ff8data(*FILES)
def test_a_program_takes_the_parameters_as_the_port_does(tmp_path):
    params = tmp_path / "params.txt"
    params.write_text("ring.radius.num 4\nring.radius.max 2048\nsparkle.colour.r 255\nfiles.texture mag001.tim\n")
    program = write_program(load_description(1), tmp_path / "cure.fxprog")
    native, _log = record(tmp_path, 1, "native", "native=1", f"params={params}")
    described, log = record(tmp_path, 1, "described", f"program={program}", f"params={params}")
    assert "4 set" in log and described == native


@pytest.mark.ff8data(*FILES)
def test_a_description_runs_in_a_free_slot(tmp_path):
    """Cure's description without the exe functions it stands in for, as effect 224 (a free slot of
    the dispatch tables): the program's own setup and tasks run it, as Cure."""
    description = copy.deepcopy(load_description(1))
    description["effect"], description["name"] = 224, "New heal"
    del description["copy"]["functions"]
    for task in description["tasks"]:
        task.pop("function")
    program = write_program(description, tmp_path / "new.fxprog")
    cure, _log = record(tmp_path, 1, "cure")
    new, log = record(tmp_path, 224, "new", f"program={program}")
    assert "program: New_heal" in log and untag(new) == cure


@pytest.mark.ff8data(*FILES)
def test_changing_the_description_changes_the_effect(tmp_path):
    """The ring without its per-step sparkles: nothing of part 4 drawn; motes the sparkles' way
    (a random velocity on each axis) instead of rising straight."""
    parts = lambda lines: {int(line.split()[1]) for line in lines if line.startswith("P ")}
    description = copy.deepcopy(load_description(1))
    ring = next(task for task in description["tasks"] if task["key"] == "ring")
    ring["step_spawns"] = []
    program = write_program(description, tmp_path / "no_sparkles.fxprog")
    without, _log = record(tmp_path, 1, "without", f"program={program}")
    assert 4 not in parts(without) and {1, 2, 3, 5, 6} <= parts(without)
    mote = next(task for task in description["tasks"] if task["key"] == "mote")
    mote["phases"][0]["do"][1] = ["velocity_roll", -32, 31, -16, 15, -32, 31]
    program = write_program(description, tmp_path / "scattered.fxprog")
    scattered, _log = record(tmp_path, 1, "scattered", f"program={program}")
    assert scattered != without


HYPNOTIZE_FILES = ("extracted_files/FF8_EN.exe", "extracted_files/magic/mag132.tim", "extracted_files/battle/d0c000.dat",
                   "extracted_files/battle/d0w000.dat", "extracted_files/battle/c0m033.dat")


def record_hypnotize(tmp_path, effect, tag, *extra):
    """Hypnotize as Gayla (c0m033, slot 3) casts it on Squall."""
    recorder = lab_recorder()
    out = tmp_path / f"{tag}.txt"
    run = subprocess.run([str(recorder), str(effect), f"exe={EXE}", f"magic={MAGIC}", f"battle={BATTLE}", f"out={out}",
                          f"slot0={BATTLE / 'd0c000.dat'}", f"weapon0={BATTLE / 'd0w000.dat'}",
                          f"slot3={BATTLE / 'c0m033.dat'}", "caster=3", "target=0", *extra],
                         cwd=str(recorder.parent), capture_output=True, text=True, timeout=120)
    assert run.returncode == 0 and "faulted" not in run.stdout, run.stdout[-500:]
    return out.read_text().splitlines(), run.stdout


def test_hypnotize_description_compiles():
    """Hypnotize's parts are not the heal ring's: plain nodes with their fields, a master director,
    spawns every n ticks, prim layouts."""
    program = compile_program(load_description(133))
    assert "director master 0 1 action_targets" in program and program.count("\ntask ") == 4
    assert program.count("node plain") == 4 and "field layout 28 168" in program and "spawn_every 1 " in program
    broken = copy.deepcopy(load_description(133))
    broken["tasks"][0]["node"].append(["layout", 8])
    with pytest.raises(DescriptionError, match="its fields take 0xcc bytes, the node 0xc4"):
        compile_program(broken)
    broken = copy.deepcopy(load_description(133))
    broken["tasks"][1]["phases"] = [{}]
    with pytest.raises(DescriptionError, match="a plain node has no phases"):
        compile_program(broken)


@pytest.mark.ff8data(*HYPNOTIZE_FILES)
def test_hypnotize_runs_from_its_description(tmp_path):
    """Hypnotize from its description: what the exe's code records; with parameters, what FFNx's
    port records with them; as effect 225 (a free slot, no exe function), Hypnotize again."""
    program = write_program(load_description(133), tmp_path / "hypnotize.fxprog")
    original, _log = record_hypnotize(tmp_path, 133, "original")
    described, log = record_hypnotize(tmp_path, 133, "described", f"program={program}")
    assert "4 tasks, 32 params" in log and untag(described) == original and len(original) > 10000
    params = tmp_path / "params.txt"
    params.write_text("main.pixels 1\nrings.every 3\ntargets.scale.min 1000\nsprites.frames 12\n"
                      "sprites.spread.y.min -900\ntiming.damage_tick 20\n")
    native, _log = record_hypnotize(tmp_path, 133, "native", "native=1", f"params={params}")
    described, log = record_hypnotize(tmp_path, 133, "described_params", f"program={program}", f"params={params}")
    assert "6 set" in log and described == native and native != original
    description = copy.deepcopy(load_description(133))
    description["effect"], description["name"] = 225, "New hypnosis"
    del description["copy"]["functions"]
    for task in description["tasks"]:
        task.pop("function")
    program = write_program(description, tmp_path / "new.fxprog")
    new, log = record_hypnotize(tmp_path, 225, "new", f"program={program}")
    assert "program: New_hypnosis" in log and untag(new) == original


# the status-cure items (one source built with different options): effect, its texture, its record flags
STATUS_ITEMS = {292: ("mag291.tim", 0x48200), 293: ("mag292.tim", 0x40300), 294: ("mag293.tim", 0x48000),
                295: ("mag294.tim", 0x9500), 296: ("mag295.tim", 0x40200)}


def item_files(effect):
    return ("extracted_files/FF8_EN.exe", f"extracted_files/magic/{STATUS_ITEMS[effect][0]}",
            "extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat", "extracted_files/battle/c0m009.dat")


@pytest.mark.parametrize("effect", list(STATUS_ITEMS))
def test_status_item_description_compiles(effect):
    """Antidote and the other status-cure items: the master starts one plain node at an anchor on
    target 0 (its effect position, between two shares of its height, or a bone's point), plays the
    sound on its own clock (Holy Water: before its queue); Echo Screen keeps a camera matrix of its
    own; the layout drawn at the anchor, target 0's result when it ends; no camera track."""
    program = compile_program(load_description(effect))
    sound = "director_event_first" if effect == 296 else "director_event"
    assert "director master 0 1 target_anchor $4 $5 $6 $7 $8 $9 " in program and f"{sound} sound_at $1 $0 $2" in program
    assert ("camera_matrix" in program) == (effect == 295)
    assert "field anchor 12 8" in program and "at_end heal_first_target" in program and "camera 0" in program
    assert f"layout_at_anchor $3 {STATUS_ITEMS[effect][1]}" in program
    broken = copy.deepcopy(load_description(effect))
    broken["director"]["events"] = [["heal_all_at", 3]]
    with pytest.raises(DescriptionError, match="unknown operation heal_all_at"):
        compile_program(broken)


@pytest.mark.parametrize("effect", [pytest.param(effect, marks=pytest.mark.ff8data(*item_files(effect)))
                                    for effect in STATUS_ITEMS])
def test_status_item_runs_from_its_description(tmp_path, effect):
    """A status-cure item from its description: what the exe's code records; with parameters, what
    FFNx's port records with them; as effect 225 (a free slot, no exe function), itself again."""
    program = write_program(load_description(effect), tmp_path / "item.fxprog")
    original, _log = record(tmp_path, effect, "original")
    described, log = record(tmp_path, effect, "described", f"program={program}")
    assert "1 tasks, 10 params" in log and untag(described) == original and len(original) > 5000
    assert any(line.startswith("N ") for line in original) and any(line.startswith("S 1 ") for line in original)
    params = tmp_path / "params.txt"
    params.write_text("layout.depth -300\nlayout.anchor 1\nlayout.height_a.times 2\nlayout.height_a.share 3\n"
                      "timing.sound_tick 5\ntiming.sound_pan 40\n")
    native, _log = record(tmp_path, effect, "native", "native=1", f"params={params}")
    described, log = record(tmp_path, effect, "described_params", f"program={program}", f"params={params}")
    assert "6 set" in log and described == native and native != original
    description = copy.deepcopy(load_description(effect))
    description["effect"], description["name"] = 225, "New item"
    del description["copy"]["functions"]
    for task in description["tasks"]:
        task.pop("function")
    program = write_program(description, tmp_path / "new.fxprog")
    new, log = record(tmp_path, 225, "new", f"program={program}")
    assert "program: New_item" in log and untag(new) == original


SILENCE_FILES = ("extracted_files/FF8_EN.exe", "extracted_files/magic/mag121.tim", "extracted_files/battle/d0c000.dat",
                 "extracted_files/battle/d0w000.dat", "extracted_files/battle/c0m009.dat")


def test_silence_description_compiles():
    """Silence: a cycle director (one target task per action, every n ticks, the target marked); the
    task's anchor at a bone every tick, its 3D sound, its layout at a depth from the target's size,
    the action's result, its end past a tick, the mark cleared."""
    program = compile_program(load_description(122))
    assert "director cycle 0 $0 action_target 8192 " in program and program.split("action_target 8192 ")[1].split("\n")[0].endswith(" 0")
    assert "field action 14 2" in program and "field entity 16 4" in program and "end tick_above $5" in program
    assert "tick anchor_at_bone $6" in program and "tick sound_3d_at $2 $1 $3" in program
    assert "draw 1 0 - - layout_on_target $7 $8 768 $9 $10" in program and "at_end unmark_target 8192" in program
    broken = copy.deepcopy(load_description(122))
    broken["director"]["kind"] = "loop"
    with pytest.raises(DescriptionError, match="per_action, master or cycle"):
        compile_program(broken)


# the effects whose director starts one task per action every n ticks: texture, parameters set, values
CYCLES = {
    122: ("mag121.tim", 11, "timing.every 7\ntiming.sound_tick 3\ntiming.damage_tick 30\ntiming.end_tick 45\n"
                            "layout.depth.base -1000\nlayout.nearer.object 2\nlayout.bone 241\n"),
    115: ("mag114.tim", 11, "timing.every 6\ntiming.sound_tick 4\ntiming.damage_tick 40\ntiming.end_tick 50\n"
                            "scale.base 1500\nscale.shift 1\nglyph.bone 240\nupper.from_tick 3\n"),
    123: ("mag122.tim", 9, "timing.every 6\ntiming.sound_tick 3\ntiming.fade_tick 20\nscale.base 1500\nscale.shift 1\n"
                           "blink.from 5\nblink.ticks 30\n"),
    125: ("mag124.tim", 9, "timing.every 6\ntiming.sound_tick 3\ntiming.fade_tick 20\nscale.base 1500\nscale.shift 1\n"
                           "blink.from 5\nblink.ticks 30\n"),
    109: ("mag108.tim", 29, "timing.every 6\ntiming.busy_tick 10\ntiming.fade_tick 10\nflash.level 1000\n"
                            "ring.size_times 2\nsparkles.lift -100\ncircle.turns 4\ncircle.window.last 33\nsparkles.every 3\n"),
}


def cycle_files(effect):
    return ("extracted_files/FF8_EN.exe", f"extracted_files/magic/{CYCLES[effect][0]}", "extracted_files/battle/d0c000.dat",
            "extracted_files/battle/d0w000.dat", "extracted_files/battle/c0m009.dat")


def test_float_description_compiles():
    """Float: the cycle director places two layouts; both drawn in frames turned with the target,
    scaled by its size, the second from a tick on, its depth from a point of its frame (exe data)."""
    program = compile_program(load_description(115))
    assert "director cycle 0 $0 action_target 0 " in program and "field layout_b 764 620" in program
    assert "tick anchor_at_position" in program and "draw 2 0 at_least $10 layout_turned 1 $9 0 0 " in program


@pytest.mark.parametrize("effect", [pytest.param(effect, marks=pytest.mark.ff8data(*cycle_files(effect)))
                                    for effect in CYCLES])
def test_cycle_effect_runs_from_its_description(tmp_path, effect):
    """Silence, Float, Slow, Haste and Dispel from their descriptions: what the exe's code records; with parameters, what
    FFNx's port records with them; as effect 225 (a free slot, no exe function), itself again."""
    _texture, count, values = CYCLES[effect]
    program = write_program(load_description(effect), tmp_path / "effect.fxprog")
    original, _log = record(tmp_path, effect, "original")
    described, log = record(tmp_path, effect, "described", f"program={program}")
    tasks = len(load_description(effect)["tasks"])
    assert f"{tasks} tasks, {count} params" in log and untag(described) == original and len(original) > 10000
    assert any(line.startswith("N ") for line in original) and any(line.startswith("S ") for line in original)
    params = tmp_path / "params.txt"
    params.write_text(values)
    native, _log = record(tmp_path, effect, "native", "native=1", f"params={params}")
    described, log = record(tmp_path, effect, "described_params", f"program={program}", f"params={params}")
    assert f"{values.count(chr(10))} set" in log and described == native and native != original
    description = copy.deepcopy(load_description(effect))
    description["effect"], description["name"] = 225, "New cycle"
    del description["copy"]["functions"]
    for task in description["tasks"]:
        task.pop("function")
    program = write_program(description, tmp_path / "new.fxprog")
    new, log = record(tmp_path, 225, "new", f"program={program}")
    assert "program: New_cycle" in log and untag(new) == original


def test_clock_spell_descriptions_compile():
    """Haste and Slow: the cycle director keeps the effect camera matrix every tick and places both
    layouts with the target's effect position and its effect point 0xF0; both layouts in frames of
    the target from those (the lower one lowered by its size), through every record flag and the
    engine's renderer; Slow's "scaled" word is the camera matrix's m[1][0]; the end when both
    layouts have finished."""
    for effect, scaled in ((123, -1), (125, 1)):
        program = compile_program(load_description(effect))
        assert "camera_matrix" in program.splitlines() and "field spawn 28 8" in program
        assert f"layout_turned 0 -1 1 0 0 $5 $6 62208 {scaled} 1" in program and "layout_turned 1 -1 2 " in program
        assert "end layout_end" in program and ("at_end unmark_target 8" in program) == (effect == 123)


def test_dispel_description_compiles():
    """Dispel: the cycle director waits while a young target task runs on that target and gives the
    anchor a size word; the target task's screen flash, its particles (a second task), its ring, its
    sound and result after the ring, the flash off at its end."""
    program = compile_program(load_description(109))
    assert "director cycle 0 $0 action_target 0 " in program and program.count("\ntask ") == 2
    assert "field entity 20 4" in program and "tick screen_flash_curve " in program and "at_end screen_flash_off" in program
    assert "random_around " in program and "rising_circle " in program and "after sound_3d_at " in program
    assert "end tick_at_node_end" in program and "node_sequence_sprite -2048" in program
