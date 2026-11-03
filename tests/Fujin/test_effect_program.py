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

from Fujin.effectprogram import DescriptionError, compile_program, load_description, new_effect, write_program

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
        task.pop("function", None)
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
        task.pop("function", None)
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
        task.pop("function", None)
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
    with pytest.raises(DescriptionError, match="per_action, master, cycle or chain"):
        compile_program(broken)


# the effects whose director starts one task per action every n ticks (and Fire's, one director per
# action, each starting the next one's): texture, parameters set, values
CYCLES = {
    17: ("mag010.tim", 7, "caster.descent 80\nburst.ticks 10\nend 110\n"),
    16: ("mag015.tim", 9, "stage.level 1024\nactors.length 30\ndirector.result 30\n"),
    15: ("mag014.tim", 8, "ribbons.twist 600\nemitter.release 20\nemitter.length 25\nsounds.b 100\n"),
    14: ("mag013-073-344.tim", 11, "reaper.fade_in 512\nstrike.length 30\nreaper.vanish_frame 14\naura.length 40\n"),
    13: ("mag012.tim", 10, "emitter.damage 60\ncontrol.puffs_until 8\ncontrol.spawner_d 25\n"),
    12: ("mag011.tim", 13, "blade.spin 600\nsparks.ticks 5\nfans.scale 4096\nblade.trails_until 40\n"),
    11: ("mag010.tim", 30, "stream.ticks 40\nhits.scale 2048\nrings.every 3\ntiming.end 70\n"),
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
    111: ("mag110.tim", 32, "timing.every 6\nflames.count 2\nflames.window.last 25\nflames.radius.base 500\n"
                            "flames.fade.from 4\nglow.from 10\nglow.rot_b 300\naura.size_shift 10\n"),
    118: ("mag117.tim", 16, "timing.every 6\nwind.from_tick 5\nwind.scale.base 1500\nleaves.window.last 9\n"
                            "leaves.speed 100\nleaves.climb 20\ntiming.sound_tick 2\n"),
    121: ("mag120.tim", 22, "flash.up 900\nlayout.additive.b -1\nflash.fade_at.second 15\nlayout.follow 10\n"
                            "timing.sound_tick 6\nlayout.ot_shift 2\n"),
    120: ("mag119.tim", 20, "stare.ahead 3\nstone.from 10\nstare.follow 5\ntiming.fade_tick 6\n"
                            "stone.depth.base -1000\ntiming.end_tick 45\n"),
    127: ("mag126.tim", 20, "stare.ahead 3\nstone.from 10\nstone.ticks 20\n"),
    114: ("mag113.tim", 20, "overlay.amp.base 800\nmist.additive.b -1\noverlay.window.from 20\ntiming.mark_from 25\n"
                            "mist.depth.shift 4\n"),
    124: ("mag123.tim", 34, "tint.ticks 16\ntint.shift 8\nsparks.count 4\nsilhouette.from 30\nflash.level 1500\n"
                            "burst.depth.shift 4\n"),
    106: ("mag105.tim", 32, "hexagons.count 5\nwall.grow 15\nrings.every 4\nbeams.count 6\ntiming.size_shift 3\n"),
    108: ("mag107.tim", 51, "rays.count 5\nembers.count 2\nswirls.per_tick 3\nglow.ticks 12\nsparks.every 3\n"
                            "rays.width 200\n"),
    10: ("mag009.tim", 39, "beam.width 4096\ndust.count 3\npuffs.first 55\nring.tick 75\ncharge.count 4\n"),
    8: ("mag007.tim", 36, "dust.radius 400\nsmoke.ticks 25\nreaper.rise 100\nscythe.y -1200\nwobble.level 1024\n"
                          "aura.length 30\n"),
    7: ("mag006.tim", 392, "actor5.speed.max 140\nactor2.frames 18\nactor0.depth -300\nactor1.offset.y -400\n"
                           "emitter.release 4\nfade_in.step 128\nwait 20\n"),
    5: ("mag004-034.tim", 65, "rising.count 2\nring.spin 200\nfall.speed.base 30\nglints.rate[2].count 1\n"
                               "emitter.grow.radius 150\nrevive.every 3\n"),
    4: ("mag003.tim", 79, "runes.spin 200\ncolumns.peak 8000\nmotes.spin 50\nglows.level 40\nbig.fade_out 600\nsprites.count 3\n"
                          "morph.step 300\nflash.jump -100\nemitter.release_tick 25\n"),
    3: ("mag003.tim", 32, "strike.lift 400\nground.tilt 200\ntiming.sound_tick 2\nsmoke.window.frames 10\nflash.window.frames 3\n"),
    2: ("mag001.tim", 57, "flames.count 6\nsparks.count 3\nembers.rise.base -40\nflames.glow.base 96\ntiming.sound_tick 3\n"),
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
    """Silence, Float, Slow, Haste, Dispel, Aura, Aero, Blind, both Petrify Stares, Zombie, Flare, Reflect, Berserk, Fire, Thunder, Double, Phoenix Down, Mega Phoenix, Doom, Ray-Bomb, Storm Breath, Blade Shot, Dark Mist, Death, Draw, Recover and Elvoret's entrance from their descriptions: what the exe's code records; with parameters, what
    FFNx's port records with them; as effect 225 (a free slot, no exe function), itself again."""
    _texture, count, values = CYCLES[effect]
    program = write_program(load_description(effect), tmp_path / "effect.fxprog")
    original, _log = record(tmp_path, effect, "original")
    described, log = record(tmp_path, effect, "described", f"program={program}")
    tasks = len(load_description(effect)["tasks"])
    assert f"{tasks} tasks, {count} params" in log and untag(described) == original and len(original) > 10000
    # (Ray-Bomb hurts the party only: on the monster the recorder casts on, no number; Elvoret's entrance hurts
    # nobody; Draw's sounds are sound ids, BdPlaySy's, which the recorder does not log)
    assert effect in (10, 17) or any(line.startswith("N ") for line in original)
    assert effect == 15 or any(line.startswith("S ") for line in original)
    params = tmp_path / "params.txt"
    params.write_text(values)
    native, _log = record(tmp_path, effect, "native", "native=1", f"params={params}")
    described, log = record(tmp_path, effect, "described_params", f"program={program}", f"params={params}")
    assert f"{values.count(chr(10))} set" in log and described == native and native != original
    description = copy.deepcopy(load_description(effect))
    description["effect"], description["name"] = 225, "New cycle"
    del description["copy"]["functions"]
    for task in description["tasks"]:
        task.pop("function", None)   # (Berserk's sparks: a task of their own, no exe function)
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


def test_aura_description_compiles():
    """Aura: its layout through the table callback (a word per object), its flames spawned a few at a
    time with one turn and speed (a second task: spinning models fading in and out), its glow at the
    target's feet, the screen fade's own values."""
    program = compile_program(load_description(111))
    assert "draw 1 0 - - layout_table " in program and "draw 3 0 - - sequence_at_feet " in program
    assert " spinning_ring " in program and "spinning_model " in program and "event spin" in program
    assert "event screen_fade_at $27 0 1 0 128" in program and program.count("\ntask ") == 2


def test_aero_description_compiles():
    """Aero: its two layouts through the scaled anchor callback (the effect camera matrix, the 16-bit
    row scale), its leaves a second task (a whirl leaf each: its own physics, gone once shrunk)."""
    program = compile_program(load_description(118))
    assert program.count("layout_scaled_on_target ") == 2 and "camera_matrix" in program.splitlines()
    assert "whirl_leaf " in program and "tick whirl_leaf_move " in program and "end leaf_gone" in program
    assert "field leaf 12 48" in program and "tumbling_model " in program


def test_blind_description_compiles():
    """Blind: the cycle director clears the flash level before its tasks and sets the screen flash to
    it after them; each target task raises it, follows the target's effect point for a while, draws
    its layout by the engine's renderer (objects 0 and 3 additive quads), then its sound, three fades
    and the result; it ends with its layout."""
    program = compile_program(load_description(121))
    lines = program.splitlines()
    assert "director_event_first flash_level_clear" in lines and "director_event screen_flash_level" in lines
    assert "tick flash_level_raise " in program and "tick follow_bone " in program
    assert "layout_engine_at_anchor 2816 " in program   # record flags 0x800 | 0x200 | 0x100
    assert program.count("after screen_fade_at ") == 3 and "after sound_3d_at_position " in program
    assert "end layout_end" in program


def test_petrify_stare_descriptions_compile():
    """Both Petrify Stares: the cycle director set up as the master is (the caster kept), one
    target node; the stare at the caster's effect point ahead of its facing, the stone at the
    target's position from a later tick (a draw within a window); their own rotation flag."""
    for effect, flags in ((120, "1536"), (127, "262656")):   # 0x200 | 0x400, 0x200 | 0x40000
        program = compile_program(load_description(effect))
        lines = program.splitlines()
        assert "master_setup" in lines and "memory caster" in program
        assert "tick follow_bone $11 $12 1" in lines and "tick point_at_position $16" in lines
        assert any(line.startswith("draw 2 0 within $16 $17 layout_on_point 1 1 0 -1 ") and line.endswith(flags)
                   for line in lines)
        assert "after sound_3d_at_position $2 $1 $3 1" in lines and "end tick_above $5" in lines


def test_zombie_description_compiles():
    """Zombie: the cycle director waits while any target task is young (on any target); the mist
    scaled by the target's size with two objects as gouraud additive quads; the target redrawn
    swayed by its wave table; the target's entities marked from a tick, unmarked at the end."""
    program = compile_program(load_description(114))
    lines = program.splitlines()
    director = next(line for line in lines if line.startswith("director cycle"))
    assert director.endswith(" 1") and "tick mark_ring_from $7 8" in lines and "at_end unmark_ring 8" in lines
    assert any(line.startswith("draw 1 0 - - layout_scaled_on_target 0 1 ") and line.endswith(" $12 $13 -1 -1") for line in lines)
    assert any(line.startswith("draw 2 0 - - sway_overlay $14 $15 ") for line in lines)


def test_flare_description_compiles():
    """Flare: the director hands an older task's saved colour over; the target task raises the
    flash (risen, held, fallen), sets it once, tints its target, draws the burst at its anchor and
    the ring at its feet (objects 2 and 3 at a quarter depth), the ripple silhouette from its one
    block of tables, and spawns collapsing sparks, a second task."""
    program = compile_program(load_description(124))
    lines = program.splitlines()
    assert "field colour 36 4" in lines and "field ripple 40 4" in lines and "field spark 12 32" in lines
    assert "tick flash_level_hold $6 $7 $8 $9 $10 $11" in lines and "tick flash_level_set $13 $14" in lines
    assert any(line.startswith("tick tint_target ") for line in lines) and "tick mark_target 2048" in lines
    assert sum(line.startswith("draw ") and "layout_scaled_on_target" in line and line.endswith(" -1 -1 2 3")
               for line in lines) == 2
    assert any(" ripple_silhouette $25 $26 " in line for line in lines) and "end spark_gone" in lines
    assert any(" collapse_sparks $28 " in line for line in lines)


def test_reflect_description_compiles():
    """Reflect: the cycle director starts its barrier at counter 0, the setup seeds the shared LCG,
    its packet arenas are its own memory (no magic buffer); the barrier spawns its hexagons at its
    first tick and its rings over the wall's steps, draws the wall, and its dead beams draw shared
    rands from the beam pool."""
    program = compile_program(load_description(106))
    lines = program.splitlines()
    assert "seed_shared_rand" in lines and "cycle_spawn_tick 0" in lines and "memory packet_arena_a 0x2523C98" in lines
    assert not any(line.startswith("magic_buffer") for line in lines) and "field barrier 20 72" in lines
    assert any(line.startswith("spawn_every ") and " orbit_spawn " in line for line in lines)
    assert any(line.startswith("spawn_every ") and " growth_spawn " in line for line in lines)
    assert "event dead_beams $13 $31 3" in lines and any(" barrier_wall " in line for line in lines)


def test_berserk_description_compiles():
    """Berserk: the main task's spawn point on the target's feet, its swirls, embers and sparks (the
    embers and sparks two tasks of one pool), its rays spawned after them and drawn last; it ends once
    no ray was drawn."""
    program = compile_program(load_description(108))
    lines = program.splitlines()
    assert "tick spawn_to_feet 0" in lines and "end rays_done $6" in lines
    assert [line.split()[5] for line in lines if line.startswith("spawn_every ")] == ["ribbon_start", "ember_ring", "spark_near"]
    assert any(line.startswith("event ray_spawn ") for line in lines)
    ops = ("sequence_at_anchor", "pulse_model", "layout_table_at_spawn", "light_rays")
    draws = [next(op for op in ops if f" {op}" in line) for line in lines if line.startswith("draw ") and any(f" {op}" in line for op in ops)]
    assert draws == list(ops)
    assert "end ribbon_done $16" in lines and lines.count("draw 5 0 - - mote_sprite") == 1


def test_fire_description_compiles():
    """Fire: the chain director (several targets' director, the lone target's); each director starts
    the next action's on its chain counter, does nothing while the battle only draws; the lone
    target's waits for its target and frees it at its end; the flames wait their delay, draw first,
    then spawn their embers and sparks."""
    lines = compile_program(load_description(2)).splitlines()
    assert "director chain 0 1" in lines and lines.count("draw_only skip") == 2 and lines.count("draw_only after_draws") == 3
    assert "hold claim_target" in lines and "at_end release_target" in lines and lines.count("tick chain_next $0") == 2
    assert [line.split()[5] for line in lines if line.startswith("spawn_every ")] == ["flames_on_targets", "flames_on_targets",
                                                                                      "flame_embers", "flame_sparks"]
    assert "field delay 14 2" in lines and "end life_out" in lines


def test_thunder_description_compiles():
    """Thunder: the cycle director at the target's effect point 0xF1; its texture a TIM of its data
    uploaded as it is (no file); the bolt's camera offset from the target's size at its first tick,
    its sound at its spawn point, the screen quad, eight layers over their windows (one on a plane
    at the target's feet)."""
    lines = compile_program(load_description(3)).splitlines()
    assert "texture 0 -1" in lines and any(line.startswith("texture_data ") for line in lines)
    assert "tick spawn_size_word 0 $3 $4" in lines and "tick sound_3d_at_spawn $6 $5 $7" in lines
    draws = [line.split()[6] for line in lines if line.startswith("draw ")]
    assert draws == ["screen_quad"] + ["point_layer"] * 6 + ["ground_layer", "point_layer"]


def test_double_description_compiles():
    """Double: the heal ring's director in its short form; node variables as tokens (base << 20 |
    type << 16 | offset: the rune's fade an i16 at 0x50, the column's emitter's signal at 0x58); a
    negated parameter; the spawns' child actions, the runes' motion after their phase, the
    column's flash model drawn while its flash is on."""
    from Fujin.effectprogram import DescriptionError
    description = load_description(4)
    lines = compile_program(description).splitlines()
    assert "director per_action 0 short" in lines
    fade, signal = (1 << 16) | 0x50, (1 << 20) | (1 << 16) | 0x58
    assert any(line == f"phase_tick add {fade} -$13" for line in lines)
    assert any(line.startswith(f"wait equals {signal} 2") for line in lines)
    assert sum(line.startswith("spawn_init ") for line in lines) > 30 and any(line.startswith("move circle_place ") for line in lines)
    assert any(line.startswith("draw_when equals ") for line in lines)
    broken = copy.deepcopy(description)
    broken["tasks"][2]["after_phase"][0][1] = "nowhere"
    with pytest.raises(DescriptionError, match="names no nowhere"):
        compile_program(broken)


def test_phoenix_down_description_compiles():
    """Phoenix Down: the short director whose setup uploads the texture even when the cast repeats (no
    camera); the emitter's phases on its tick (above), its spawns of the revive sparkles gated by its
    spawning flag (an every-n-ticks spawn's gate on its own line), the glints by a four-rate schedule."""
    lines = compile_program(load_description(5)).splitlines()
    assert "director per_action 0 short upload_always" in lines and "camera 0" in lines
    assert sum(line.startswith("wait above ") for line in lines) == 3 and lines.count("spawn_gate 2") == 4
    places = [line.split()[-7 if line.startswith("spawn_every") else 0] for line in lines if line.startswith("spawn")]
    assert any("revive_rising" in line for line in lines) and any(line.startswith("spawn -1 2 ") and " glint " in line for line in lines)


@pytest.mark.ff8data("extracted_files/FF8_EN.exe")
def test_mega_phoenix_description_compiles():
    """Mega Phoenix: the per-action director in the act family's form (its task per target, arenas of
    0xA000, the actor pools carved at state 2, the fades, the counters cleared every tick, the parts of
    its actors' draws); the emitter spawning the actor system with its actor data; every field of its five
    definitions a patch of that data; an own copy carries the actor data whole."""
    description = load_description(7)
    lines = compile_program(description).splitlines()
    for line in ("director per_action 0", "per_target", "arena_size 40960", "act_stage 2 3 $7", "act_pool particle_pool 2700",
                 "act_pool actor_pool 53760", "act_clear count_a", "act_parts 1 2", "camera 0"):
        assert line in lines, line
    assert sum(line.startswith("patch 23323032 ") for line in lines) == 5 * 76
    assert "phase_tick actor_step" in lines and "wait actor_done" in lines and "phase_tick stage_fade 65564 $8 $9" in lines
    own = compile_program(new_effect(description, 224, "Own", EXE.read_bytes())).splitlines()
    actors = next(line for line in own if line.startswith("data_actors actors "))
    assert actors.split()[2:4] == [str(0x163E198 - 0x163ACD4), str(0x163ACD4)] and len(actors.split()[4]) == 2 * (0x163E29C - 0x163ACD4)
    assert sum(line.startswith("patch @actors ") for line in own) == 5 * 76


@pytest.mark.ff8data("extracted_files/FF8_EN.exe")
def test_doom_description_compiles():
    """Doom: a port module's pieces - the per-action director in the act family's form (arenas of
    0x8000, its actor pools, its file released at its end), the module whose code runs and the data
    word pointing into its memory, the engine's emitter and the phase director as their state tables
    (each phase calls the port's state function); an own copy moves the module's memory into a block of
    its own."""
    description = load_description(7 + 1)
    lines = compile_program(description).splitlines()
    for line in ("module 8 0x2758500 0x7680", "module_pointer 2 0x1634F20", "release_file", "arena_size 32768",
                 "act_pool actor_pool 26880", "code 0x8C5350", "tick call 9196560"):
        assert line in lines, line
    assert sum(line.startswith("phase_tick call ") for line in lines) == 5 + 15
    own = compile_program(new_effect(description, 224, "Own", EXE.read_bytes())).splitlines()
    assert "module 8 0x2758500 0x7680 own" in own and "memory root_queue 0x2758958" in own
    assert not any(line.startswith("function ") for line in own)


def test_ray_bomb_description_compiles():
    """Ray-Bomb: a port director - the port's file loader, setup and root run on the program's memory
    (its module's), no task of its own; its parameters the port's."""
    lines = compile_program(load_description(10)).splitlines()
    assert "director port -1" in lines and "port 0x627E60 0x627E40 0x629730" in lines and "module 10 0x24C91D8 0x1638" in lines
    assert not any(line.startswith(("task ", "pool ")) for line in lines)


def test_storm_breath_description_compiles():
    """Storm Breath: a port director - the port's file loader, setup and root run on the program's
    memory (its module's), no task of its own; its parameters the port's."""
    lines = compile_program(load_description(11)).splitlines()
    assert "director port -1" in lines and "port 0x6EA500 0x6EA510 0x6EA5B0" in lines and "module 11 0x2556140 0x88" in lines
    assert not any(line.startswith(("task ", "pool ")) for line in lines)


def test_blade_shot_description_compiles():
    """Blade Shot: a port director - the port's file loader, setup and root run on the program's
    memory (its module's), no task of its own; its parameters the port's."""
    lines = compile_program(load_description(12)).splitlines()
    assert "director port -1" in lines and "port 0x6E8AE0 0x6E8AC0 0x6E8C90" in lines and "module 12 0x2545188 0x10FB8" in lines
    assert not any(line.startswith(("task ", "pool ")) for line in lines)


def test_dark_mist_description_compiles():
    """Dark Mist: a port director - the port's file loader, setup and root run on the program's
    memory (its module's), no task of its own; its parameters the port's."""
    lines = compile_program(load_description(13)).splitlines()
    assert "director port -1" in lines and "port 0x8BE1F0 0x8BE1D0 0x8BE2D0" in lines and "module 13 0x27428A8 0xC73C" in lines
    assert not any(line.startswith(("task ", "pool ")) for line in lines)


def test_death_description_compiles():
    """Death: Doom's kind - the per-action director, the module, the emitter's and the director's state tables."""
    lines = compile_program(load_description(14)).splitlines()
    for line in ['module 14 0x273AE80 0x7A20', 'module_pointer 2 0x162B860', 'release_file', 'arena_size 57344', 'code 0x8B6E30']:
        assert line in lines, line


def test_draw_description_compiles():
    """Draw: Doom's kind, its emitter the module's own (a native task: the port's task function)."""
    lines = compile_program(load_description(15)).splitlines()
    for line in ['module 15 0x2732BF8 0x8284', 'native 0x8B0C70', 'arena_size 36864', 'act_pool particle_pool 1080']:
        assert line in lines, line


def test_recover_description_compiles():
    """Recover: Doom's kind - the per-action director, the module, the emitter's and the director's state tables."""
    lines = compile_program(load_description(16)).splitlines()
    for line in ['module 16 0x27304A0 0x2750', 'module_pointer 2 0x162A484', 'arena_size 32768', 'code 0x8AB600']:
        assert line in lines, line


def test_elvoret_entrance_description_compiles():
    """Elvoret's entrance: a port director with no file loader of its own (its TIM is exe data)."""
    lines = compile_program(load_description(17)).splitlines()
    for line in ['director port -1', 'port 0x7003C0 0x0 0x700460', 'module 17 0x2556FA0 0x60', 'texture 0 -1']:
        assert line in lines, line


def test_elvoret_death_description_compiles():
    """Elvoret's death: a port director calling the cinematic clone's own setup (its memory the engine's shared
    state block), its root re-pointed; its two script files the parameters."""
    lines = compile_program(load_description(18)).splitlines()
    for line in ['director port -1', 'port 0xB4A530 0xB4A500 0xB4ABA0 exe', 'module 18 0x2796E00 0x1E40']:
        assert line in lines, line


def record_elvoret(tmp_path, effect, tag, *extra):
    """Elvoret's death as Elvoret (c0m091, slot 3) casts it on itself."""
    recorder = lab_recorder()
    out = tmp_path / f"{tag}.txt"
    run = subprocess.run([str(recorder), str(effect), f"exe={EXE}", f"magic={MAGIC}", f"battle={BATTLE}", f"out={out}",
                          f"slot0={BATTLE / 'd0c000.dat'}", f"weapon0={BATTLE / 'd0w000.dat'}",
                          f"slot3={BATTLE / 'c0m091.dat'}", "caster=3", "target=3", *extra],
                         cwd=str(recorder.parent), capture_output=True, text=True, timeout=120)
    assert run.returncode == 0 and "faulted" not in run.stdout, run.stdout[-500:]
    return out.read_text().splitlines(), run.stdout


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/magic/MAG017_B.00", "extracted_files/magic/MAG017_B.01",
                     "extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat",
                     "extracted_files/battle/c0m091.dat")
def test_elvoret_death_runs_from_its_description(tmp_path):
    """Elvoret's death from its description: what the exe's code records; a script file of its own (an edited
    .00 copy) read by the port's file loader and the program's alike; as effect 225, itself again."""
    program = write_program(load_description(18), tmp_path / "effect.fxprog")
    original, _log = record_elvoret(tmp_path, 18, "original")
    described, log = record_elvoret(tmp_path, 18, "described", f"program={program}")
    assert "0 tasks, 2 params" in log and untag(described) == original and len(original) > 10000
    files = tmp_path / "files"
    files.mkdir()
    script = bytearray((MAGIC / "MAG017_B.00").read_bytes())
    for k in range(0x1B700, 0x1B740, 2):
        script[k] = (script[k] + 3) & 0xFF
    (files / "elv18.00").write_bytes(script)
    params = tmp_path / "params.txt"
    params.write_text("files.file00 elv18.00
")
    native, _log = record_elvoret(tmp_path, 18, "native", "native=1", f"params={params}", f"overrides={files}")
    described, log = record_elvoret(tmp_path, 18, "described_params", f"program={program}", f"params={params}",
                                    f"overrides={files}")
    assert "1 set" in log and described == native and native != original
    description = copy.deepcopy(load_description(18))
    description["effect"], description["name"] = 225, "New death"
    del description["copy"]["functions"]
    new, log = record_elvoret(tmp_path, 225, "new", f"program={write_program(description, tmp_path / 'new.fxprog')}")
    assert "program: New_death" in log and untag(new) == original
