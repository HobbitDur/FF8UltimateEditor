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
    59: ("mag057-058.tim", 11, "emitter.sound_tick 4\nmaster.wait 20\nfade.step_in 128\nactors.length 35\n"),
    58: ("mag057-058.tim", 10, "master.wait 30\nfade.step_in 128\nemitter.release 15\nactors.length 35\n"),
    57: ("mag056.tim", 9, "actors.length 30\nmaster.wait 30\nwobble.step 64\nemitter.release 25\n"),
    56: ("mag038-055.tim", 12, "emitter.flash_b 12\nmaster.wait 20\nwobble.step_in 128\nactors.length 30\nemitter.release 25\n"),
    55: ("mag054-071.tim", 13, "orb.hold 25\ndarken.level 1024\nsplash.until 24\ndirector.damage 40\nrain.from 16\n"),
    54: ("mag053.tim", 10, "master.wait 25\nwobble.step_in 128\nemitter.release 25\nactors.length 35\n"),
    53: ("mag052.tim", 10, "master.wait 20\nfade.step_in 128\nemitter.release 15\nactors.length 35\n"),
    52: ("mag027-051.tim", 7, "emitter.flash 10\nemitter.result 40\nactors.length 35\nemitter.release 25\n"),
    51: ("mag024-050.tim", 9, "emitter.heal 40\naura.third 2048\nglow.sparks 12\nsparkles.spread 1024\n"),
    49: ("mag048.tim", 10, "warp.step_in 512\nwarp.hold 40\ndirector.sound_tick 20\nprims.place 10\n"),
    48: ("mag047.tim", 11, "emitter.flash 8\nmaster.wait 20\nlight.step_in 128\nactors.length 30\nemitter.result 45\n"),
    47: ("mag046.tim", 10, "director.damage 40\nprims.middle 20\ndarken.level 1024\ndarken.step_out 128\n"),
    46: ("mag045.tim", 13, "sigh.fade 30\nsigh.show 6\nmaster.wait 12\nwobble.step_in 128\nemitter.release 45\n"),
    45: ("mag044.tim", 7, "darken.level 1024\ndarken.hold 30\ndirector.damage 25\neyes.forward 128\n"),
    44: ("mag043.tim", 8, "items.every 2\nitems.big 55\nfall.gravity 80\ncontrol.amp 512\n"),
    43: ("mag042.tim", 9, "reach.scale 20\nreach.max 4000\nemitter.release 50\nactors.length 35\n"),
    41: ("mag040.tim", 14, "ball.morph 256\nball.gravity 64\nball.lift 800\nemitter.sound 25\nactors.length 30\n"),
    40: ("mag039-067.tim", 9, "camera.approach 400\ncamera.view 1000\nbrackets.follow 20\nbars.step 16\nbars.level 200\n"),
    39: ("mag038-055.tim", 12, "emitter.flash_b 12\nmaster.wait 20\nwobble.step_in 128\nactors.length 30\nemitter.release 25\n"),
    38: ("mag036.tim", 14, "fallback.sound 40\nfallback.shake 5\nsequence.fade_out 256\nquake.length 30\n"),
    37: ("mag036.tim", 18, "ribbons.twist 600\nemitter.release 20\nstreaks.accel 80\norb.scale 8000\norb.hold 10\n"),
    36: ("mag035.tim", 8, "emitter.shake 12\nactors.length 30\nemitter.release 25\nemitter.chain 10\n"),
    35: ("mag004-034.tim", 9, "grow.radius 200\nspread.until 25\nemitter.result 40\ngrow.until 6\n"),
    34: ("mag033.tim", 3, "emitter.release 30\nemitter.result 30\n"),
    33: ("mag032.tim", 9, "actors.length 30\nmaster.wait 20\nfade.step 64\nemitter.release 25\n"),
    32: ("mag031.tim", 9, "emitter.flash 10\nmaster.wait 15\nwobble.step 64\nparticles.from 22\n"),
    30: ("mag029.tim", 13, "laser.grow 512\nlaser.hold 20\nmaster.wait 30\nlight.step 64\n"),
    29: ("mag028.tim", 6, "actors.start 4\nactors.length 30\nemitter.result 30\nemitter.release 30\n"),
    28: ("mag027-051.tim", 10, "emitter.flash 10\nmaster.wait 20\nfade.step 64\nactors.length 30\n"),
    27: ("mag026.tim", 9, "actors.length 30\nmaster.wait 20\nfade.step 64\nemitter.release 25\n"),
    26: ("mag025.tim", 12, "bursts.sparks 4\nknock.gravity 64\nemitter.dust 2\nbursts.radius 512\n"),
    25: ("mag024-050.tim", 9, "glow.sparks 4\naura.second 1024\nemitter.heal 40\nsparkles.spread 1024\n"),
    24: ("mag023-066.tim", 9, "actors.length 30\nmaster.wait 30\nwobble.step 64\nemitter.release 25\n"),
    22: ("mag021.tim", 9, "emitter.blob 40\nblob.cycles 3\nemitter.pools_every 3\nblob.spin -100\n"),
    21: ("mag020.tim", 11, "runes.every 5\nrunes.spin 300\nmotes.until 3\nemitter.release 40\n"),
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
    """Silence, Float, Slow, Haste, Dispel, Aura, Aero, Blind, both Petrify Stares, Zombie, Flare, Reflect, Berserk, Fire, Thunder, Double, Phoenix Down, Mega Phoenix, Doom, Ray-Bomb, Storm Breath, Blade Shot, Dark Mist, Death, Draw, Recover, Elvoret's entrance, Triple, Bio, Esuna, Cura, Clash, Full-life, Curaga, Wind Blast, Counter Laser-Eye, Protect, Shell, Pain, Life, Confuse, Drink Magic, Quake, Drain, Scan, Dribble, Melting Bubble, Junk, Stare, Sigh, Curse, Magma Breath, Resonance, Hi-Potion, X-Potion, Mega-Potion, Everyone's Grudge, Aqua Breath, Absorb, Treatment, Elixir and Megalixir from their descriptions: what the exe's code records; with parameters, what
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
    params.write_text("files.file00 elv18.00\n")
    native, _log = record_elvoret(tmp_path, 18, "native", "native=1", f"params={params}", f"overrides={files}")
    described, log = record_elvoret(tmp_path, 18, "described_params", f"program={program}", f"params={params}",
                                    f"overrides={files}")
    assert "1 set" in log and described == native and native != original
    description = copy.deepcopy(load_description(18))
    description["effect"], description["name"] = 225, "New death"
    del description["copy"]["functions"]
    new, log = record_elvoret(tmp_path, 225, "new", f"program={write_program(description, tmp_path / 'new.fxprog')}")
    assert "program: New_death" in log and untag(new) == original


def test_raldo_throw_description_compiles():
    """Raldo Throw: Doom's kind - the per-action director, the module, the emitter's and the director's state tables."""
    lines = compile_program(load_description(19)).splitlines()
    for line in ['module 19 0x2726900 0x9B98', 'module_pointer 2 0x1629FA8', 'arena_size 16384', 'code 0x8A3760']:
        assert line in lines, line
    assert "release_file" not in lines


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/magic/mag018.tim", "extracted_files/battle/d0c000.dat",
                     "extracted_files/battle/d0w000.dat", "extracted_files/battle/c0m095.dat", "extracted_files/battle/c0m096.dat")
def test_raldo_throw_runs_from_its_description(tmp_path):
    """Raldo Throw as Granaldo (c0m095, slot 3) casts it on Squall, its Raldo (c0m096, com id 0x70) standing at it in
    slot 4: what the exe's code records; with parameters, what FFNx's port records with them; as effect 225, itself
    again."""
    def record_raldo(effect, tag, *extra):
        recorder = lab_recorder()
        out = tmp_path / f"{tag}.txt"
        run = subprocess.run([str(recorder), str(effect), f"exe={EXE}", f"magic={MAGIC}", f"battle={BATTLE}", f"out={out}",
                              f"slot0={BATTLE / 'd0c000.dat'}", f"weapon0={BATTLE / 'd0w000.dat'}",
                              f"slot3={BATTLE / 'c0m095.dat'}", f"slot4={BATTLE / 'c0m096.dat'}", "pos4=0,0,-3000",
                              "caster=3", "target=0", *extra],
                             cwd=str(recorder.parent), capture_output=True, text=True, timeout=120)
        assert run.returncode == 0 and "faulted" not in run.stdout, run.stdout[-500:]
        return out.read_text().splitlines(), run.stdout

    program = write_program(load_description(19), tmp_path / "effect.fxprog")
    original, _log = record_raldo(19, "original")
    described, log = record_raldo(19, "described", f"program={program}")
    assert "2 tasks, 18 params" in log and untag(described) == original and len(original) > 50000
    assert any(line.startswith("N ") for line in original) and any(line.startswith("S ") for line in original)
    params = tmp_path / "params.txt"
    params.write_text("toss.speed 300" + chr(10) + "raldo.radius 600" + chr(10) + "debris.take 5" + chr(10) + "ball.start 20" + chr(10))
    native, _log = record_raldo(19, "native", "native=1", f"params={params}")
    described, log = record_raldo(19, "described_params", f"program={program}", f"params={params}")
    assert "4 set" in log and described == native and native != original
    description = copy.deepcopy(load_description(19))
    description["effect"], description["name"] = 225, "New throw"
    del description["copy"]["functions"]
    for task in description["tasks"]:
        task.pop("function", None)
    new, log = record_raldo(225, "new", f"program={write_program(description, tmp_path / 'new.fxprog')}")
    assert "program: New_throw" in log and untag(new) == original


def test_norg_pod_opening_description_compiles():
    """NORG Pod opening: Doom's kind with Drain's master - the stage light ramps as the act director's stage in and
    out after its wait, no actor pools; the module's own emitter and ramps (native tasks)."""
    lines = compile_program(load_description(20)).splitlines()
    for line in ['module 20 0x2721590 0x5370', 'arena_size 40960', 'act_stage 1 2 $3', 'native 0x89FFB0',
                 'native 0x89FE90', 'native 0x8A3150']:
        assert line in lines, line
    assert not any(line.startswith(("act_pool ", "module_pointer ")) for line in lines)


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/magic/mag019.tim", "extracted_files/battle/d0c000.dat",
                     "extracted_files/battle/d0w000.dat", "extracted_files/battle/c0m068.dat")
def test_norg_pod_opening_runs_from_its_description(tmp_path):
    """NORG Pod opening as the NORG Pod (c0m068, slot 3) casts it on Squall: what the exe's code records; with
    parameters, what FFNx's port records with them; as effect 225 (its ramps' state tables found through their code),
    itself again."""
    def record_pod(effect, tag, *extra):
        recorder = lab_recorder()
        out = tmp_path / f"{tag}.txt"
        run = subprocess.run([str(recorder), str(effect), f"exe={EXE}", f"magic={MAGIC}", f"battle={BATTLE}", f"out={out}",
                              f"slot0={BATTLE / 'd0c000.dat'}", f"weapon0={BATTLE / 'd0w000.dat'}",
                              f"slot3={BATTLE / 'c0m068.dat'}", "caster=3", "target=0", *extra],
                             cwd=str(recorder.parent), capture_output=True, text=True, timeout=120)
        assert run.returncode == 0 and "faulted" not in run.stdout, run.stdout[-500:]
        return out.read_text().splitlines(), run.stdout

    program = write_program(load_description(20), tmp_path / "effect.fxprog")
    original, _log = record_pod(20, "original")
    described, log = record_pod(20, "described", f"program={program}")
    assert "3 tasks, 16 params" in log and untag(described) == original and len(original) > 30000
    assert any(line.startswith("N ") for line in original) and any(line.startswith("S ") for line in original)
    params = tmp_path / "params.txt"
    params.write_text(chr(10).join(["lid.gravity 60", "light.level 2048", "master.wait 25", "debris.frames 10",
                                    "emitter.release 40"]) + chr(10))
    native, _log = record_pod(20, "native", "native=1", f"params={params}")
    described, log = record_pod(20, "described_params", f"program={program}", f"params={params}")
    assert "5 set" in log and described == native and native != original
    description = copy.deepcopy(load_description(20))
    description["effect"], description["name"] = 225, "New pod"
    del description["copy"]["functions"]
    for task in description["tasks"]:
        task.pop("function", None)
    new, log = record_pod(225, "new", f"program={write_program(description, tmp_path / 'new.fxprog')}")
    assert "program: New_pod" in log and untag(new) == original


def test_triple_description_compiles():
    """Triple: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory."""
    lines = compile_program(load_description(21)).splitlines()
    for line in ['director port -1', 'port 0x89DEF0 0x89DED0 0x89DFF0', 'module 21 0x2714F28 0xC658']:
        assert line in lines, line


def test_bio_description_compiles():
    """Bio: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory."""
    lines = compile_program(load_description(22)).splitlines()
    for line in ['director port -1', 'port 0x89A6B0 0x89A690 0x89A7B0', 'module 22 0x27044E0 0x10A48']:
        assert line in lines, line


def test_psycho_blast_description_compiles():
    """Psycho Blast: Doom's kind - the per-action director, the module with its director block, the emitter's and the
    director's state tables, its file released at the end."""
    lines = compile_program(load_description(23)).splitlines()
    for line in ['module 23 0x27011B8 0x3328', 'module_pointer 2 0x1614284', 'release_file', 'arena_size 32768',
                 'code 0x893500']:
        assert line in lines, line


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/magic/mag022.tim", "extracted_files/battle/d0c000.dat",
                     "extracted_files/battle/d0w000.dat", "extracted_files/battle/c0m077.dat")
def test_psycho_blast_runs_from_its_description(tmp_path):
    """Psycho Blast as NORG (c0m077, slot 3) casts it on Squall: what the exe's code records; with parameters, what
    FFNx's port records with them; as effect 225, itself again."""
    def record_norg(effect, tag, *extra):
        recorder = lab_recorder()
        out = tmp_path / f"{tag}.txt"
        run = subprocess.run([str(recorder), str(effect), f"exe={EXE}", f"magic={MAGIC}", f"battle={BATTLE}", f"out={out}",
                              f"slot0={BATTLE / 'd0c000.dat'}", f"weapon0={BATTLE / 'd0w000.dat'}",
                              f"slot3={BATTLE / 'c0m077.dat'}", "caster=3", "target=0", *extra],
                             cwd=str(recorder.parent), capture_output=True, text=True, timeout=120)
        assert run.returncode == 0 and "faulted" not in run.stdout, run.stdout[-500:]
        return out.read_text().splitlines(), run.stdout

    program = write_program(load_description(23), tmp_path / "effect.fxprog")
    original, _log = record_norg(23, "original")
    described, log = record_norg(23, "described", f"program={program}")
    assert "2 tasks, 12 params" in log and untag(described) == original and len(original) > 30000
    assert any(line.startswith("N ") for line in original) and any(line.startswith("S ") for line in original)
    params = tmp_path / "params.txt"
    params.write_text(chr(10).join(["orb.speed 800", "orb.appear 30", "debris.first 4", "actors.length 30"]) + chr(10))
    native, _log = record_norg(23, "native", "native=1", f"params={params}")
    described, log = record_norg(23, "described_params", f"program={program}", f"params={params}")
    assert "4 set" in log and described == native and native != original
    description = copy.deepcopy(load_description(23))
    description["effect"], description["name"] = 225, "New blast"
    del description["copy"]["functions"]
    for task in description["tasks"]:
        task.pop("function", None)
    new, log = record_norg(225, "new", f"program={write_program(description, tmp_path / 'new.fxprog')}")
    assert "program: New_blast" in log and untag(new) == original


def test_esuna_description_compiles():
    """Esuna: Doom's kind with Drain's master - its actor pools, the stage wobble in and out (native tasks) after its wait."""
    lines = compile_program(load_description(24)).splitlines()
    for line in ['module 24 0x2700470 0xD48', 'act_stage 1 2 $3', 'act_pool actor_pool 67200', 'native 0x88D3B0']:
        assert line in lines, line


def test_cura_description_compiles():
    """Cura: Doom's kind with Double's short root - the module, its arenas in the magic buffer, its own emitter."""
    lines = compile_program(load_description(25)).splitlines()
    for line in ['module 25 0x26E5908 0x1AB68', 'magic_buffer 0x0 0x12000 0x0', 'director per_action 0 short', 'native 0x889F40']:
        assert line in lines, line


def test_clash_description_compiles():
    """Clash: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory."""
    lines = compile_program(load_description(26)).splitlines()
    for line in ['director port -1', 'port 0x8885D0 0x8885B0 0x8886C0', 'module 26 0x26D9050 0xC8A0']:
        assert line in lines, line


def test_full_life_description_compiles():
    """Full-life: Doom's kind with Drain's master - its actor pools, the stage fade in and out (native tasks) after its wait."""
    lines = compile_program(load_description(27)).splitlines()
    for line in ['module 27 0x26D8308 0xD48', 'act_stage 1 2 $3', 'act_pool actor_pool 94080', 'native 0x883550']:
        assert line in lines, line


def test_curaga_description_compiles():
    """Curaga: Doom's kind with Drain's master - its actor pools, the stage wobble in and out (native tasks) after its wait."""
    lines = compile_program(load_description(28)).splitlines()
    for line in ['module 28 0x26D74F8 0xE10', 'act_stage 1 2 $4', 'act_pool actor_pool 94080', 'native 0x87DF70']:
        assert line in lines, line


def test_wind_blast_description_compiles():
    """Wind Blast: Doom's kind with Drain's master - its actor pools, no stage tasks, its own emitter."""
    lines = compile_program(load_description(29)).splitlines()
    for line in ['module 29 0x26D6A40 0xAB8', 'act_stage -1 -1 0', 'act_pool actor_pool 53760', 'native 0x8797C0']:
        assert line in lines, line


def test_counter_laser_eye_description_compiles():
    """Counter Laser-Eye: Doom's kind with Drain's master - its actor pools, the light ramps (native tasks) after its wait."""
    lines = compile_program(load_description(30)).splitlines()
    for line in ['module 30 0x26D40B8 0x2988', 'act_stage 1 2 $3', 'act_pool actor_pool 33600', 'native 0x873A70']:
        assert line in lines, line


def test_heartbreak_description_compiles():
    """Heartbreak: Doom's kind with Drain's master - its actor pools, the light ramps (native tasks) after its wait."""
    lines = compile_program(load_description(31)).splitlines()
    for line in ['module 31 0x26CDCC8 0x63F0', 'act_stage 1 2 $5', 'act_pool actor_pool 33600', 'native 0x86CE90']:
        assert line in lines, line


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/magic/mag030.tim", "extracted_files/battle/d0c000.dat",
                     "extracted_files/battle/d0w000.dat", "extracted_files/battle/c0m023.dat")
def test_heartbreak_runs_from_its_description(tmp_path):
    """Heartbreak as Creeps (c0m023, slot 3) casts it on Squall: what the exe's code records; with parameters, what
    FFNx's port records with them; as effect 225, itself again. (Its matrices read stack words earlier code left,
    among them its own memory's addresses: a copy with memory of its own draws some sparks differently.)"""
    def record_creeps(effect, tag, *extra):
        recorder = lab_recorder()
        out = tmp_path / f"{tag}.txt"
        run = subprocess.run([str(recorder), str(effect), f"exe={EXE}", f"magic={MAGIC}", f"battle={BATTLE}", f"out={out}",
                              f"slot0={BATTLE / 'd0c000.dat'}", f"weapon0={BATTLE / 'd0w000.dat'}",
                              f"slot3={BATTLE / 'c0m023.dat'}", "caster=3", "target=0", *extra],
                             cwd=str(recorder.parent), capture_output=True, text=True, timeout=120)
        assert run.returncode == 0 and "faulted" not in run.stdout, run.stdout[-500:]
        return out.read_text().splitlines(), run.stdout

    program = write_program(load_description(31), tmp_path / "effect.fxprog")
    original, _log = record_creeps(31, "original")
    described, log = record_creeps(31, "described", f"program={program}")
    assert "3 tasks, 11 params" in log and untag(described) == original and len(original) > 30000
    assert any(line.startswith("N ") for line in original) and any(line.startswith("S ") for line in original)
    again, _log = record_creeps(31, "again")
    assert again == original   # (the recorder's buffers at fixed addresses: the stack words it reads are the same)
    params = tmp_path / "params.txt"
    params.write_text(chr(10).join(["emitter.flash_a 8", "master.wait 20", "light.step 64", "actors.length 30"]) + chr(10))
    native, _log = record_creeps(31, "native", "native=1", f"params={params}")
    described, log = record_creeps(31, "described_params", f"program={program}", f"params={params}")
    assert "4 set" in log and described == native and native != original
    description = copy.deepcopy(load_description(31))
    description["effect"], description["name"] = 225, "New heartbreak"
    del description["copy"]["functions"]
    for task in description["tasks"]:
        task.pop("function", None)
    new, log = record_creeps(225, "new", f"program={write_program(description, tmp_path / 'new.fxprog')}")
    assert "program: New_heartbreak" in log and untag(new) == original


def test_protect_description_compiles():
    """Protect: Doom's kind with Drain's master without actor pools - the stage wobble in and out (native tasks) after its wait."""
    lines = compile_program(load_description(32)).splitlines()
    for line in ['module 32 0x26C3890 0xA438', 'act_stage 1 2 $4', 'native 0x86BDC0']:
        assert line in lines, line


def test_shell_description_compiles():
    """Shell: Doom's kind with Drain's master - its actor pools, the stage darkening in and out (native tasks) after its wait."""
    lines = compile_program(load_description(33)).splitlines()
    for line in ['module 33 0x26C0380 0x3510', 'act_stage 1 2 $3', 'act_pool actor_pool 33600', 'native 0x866470']:
        assert line in lines, line


def test_pain_description_compiles():
    """Pain: Doom's kind with Drain's master without actor pools or stage tasks, its own emitter."""
    lines = compile_program(load_description(34)).splitlines()
    for line in ['module 34 0x26BA9E0 0x59A0', 'act_stage -1 -1 0', 'native 0x8658A0']:
        assert line in lines, line


def test_life_description_compiles():
    """Life: Doom's kind with Double's short root - the module, its arenas in the magic buffer, its own emitter."""
    lines = compile_program(load_description(35)).splitlines()
    for line in ['module 35 0x26AC780 0xE260', 'magic_buffer 0x0 0x2000 0x0', 'director per_action 0 short', 'native 0x864BC0']:
        assert line in lines, line


def test_confuse_description_compiles():
    """Confuse: Doom's kind with Drain's master - its actor pools, no stage tasks, its own emitter."""
    lines = compile_program(load_description(36)).splitlines()
    for line in ['module 36 0x26A8DB8 0xE0C', 'act_stage -1 -1 0', 'act_pool actor_pool 33600', 'native 0x85F840']:
        assert line in lines, line


def test_drink_magic_description_compiles():
    """Drink Magic: Doom's kind (Draw's), its emitter the module's own (a native task: the port's task function)."""
    lines = compile_program(load_description(37)).splitlines()
    for line in ['module 37 0x26A05C8 0x87F0', 'arena_size 36864', 'act_pool particle_pool 1080', 'native 0x856D70']:
        assert line in lines, line


def test_quake_description_compiles():
    """Quake: a port director (Ray-Bomb's kind) - its setup the port's, its file loader the engine's nullsub, run on the program's memory."""
    lines = compile_program(load_description(38)).splitlines()
    for line in ['director port -1', 'port 0x8D8510 0x0 0x8D8610', 'module 38 0x278C8E0 0x6580']:
        assert line in lines, line


def test_drain_description_compiles():
    """Drain: Doom's kind with its own master (the one Esuna's copies) - its actor pools, the stage wobble in and out (native tasks) after its wait."""
    lines = compile_program(load_description(39)).splitlines()
    for line in ['module 39 0x269D958 0xE0C', 'act_stage 1 2 $5', 'act_pool actor_pool 94080', 'native 0x851830']:
        assert line in lines, line


def test_scan_description_compiles():
    """Scan: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its camera state through its exe pointer)."""
    lines = compile_program(load_description(40)).splitlines()
    for line in ['director port -1', 'port 0x84D030 0x84D010 0x84D110', 'module 40 0x269A160 0x37DC']:
        assert line in lines, line


def test_dribble_description_compiles():
    """Dribble: Doom's kind (Draw's), its emitter the module's own (a native task: the port's task function)."""
    lines = compile_program(load_description(41)).splitlines()
    for line in ['module 41 0x267B858 0x1D260', 'arena_size 20480', 'act_pool actor_pool 33600', 'native 0x846900']:
        assert line in lines, line


def test_shoot_description_compiles():
    """Shoot: Doom's kind (Draw's), its emitter the module's own (a native task); its pools run in the master's order (the ball tasks before the prim models)."""
    lines = compile_program(load_description(42)).splitlines()
    for line in ['module 42 0x2659108 0x21F1C', 'arena_size 24576', 'act_pool actor_pool 20160', 'native 0x83F020']:
        assert line in lines, line


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/magic/mag041.tim", "extracted_files/battle/d0c000.dat",
                     "extracted_files/battle/d0w000.dat", "extracted_files/battle/d1c003.dat",
                     "extracted_files/battle/d1w008.dat", "extracted_files/battle/d2c006.dat",
                     "extracted_files/battle/d2w013.dat", "extracted_files/battle/c0m032.dat")
def test_shoot_runs_from_its_description(tmp_path):
    """Shoot as Wendigo (c0m032, slot 3) casts it on a party of three (the ball is slot 1, passed between slots 0 and
    2): what the exe's code records; with parameters, what FFNx's port records with them; as effect 225, itself
    again."""
    def record_wendigo(effect, tag, *extra):
        recorder = lab_recorder()
        out = tmp_path / f"{tag}.txt"
        run = subprocess.run([str(recorder), str(effect), f"exe={EXE}", f"magic={MAGIC}", f"battle={BATTLE}", f"out={out}",
                              f"slot0={BATTLE / 'd0c000.dat'}", f"weapon0={BATTLE / 'd0w000.dat'}",
                              f"slot1={BATTLE / 'd1c003.dat'}", f"weapon1={BATTLE / 'd1w008.dat'}",
                              f"slot2={BATTLE / 'd2c006.dat'}", f"weapon2={BATTLE / 'd2w013.dat'}",
                              f"slot3={BATTLE / 'c0m032.dat'}", "caster=3", "target=0", *extra],
                             cwd=str(recorder.parent), capture_output=True, text=True, timeout=120)
        assert run.returncode == 0 and "faulted" not in run.stdout, run.stdout[-500:]
        return out.read_text().splitlines(), run.stdout

    program = write_program(load_description(42), tmp_path / "effect.fxprog")
    original, _log = record_wendigo(42, "original")
    described, log = record_wendigo(42, "described", f"program={program}")
    assert "1 tasks, 15 params" in log and untag(described) == original and len(original) > 100000
    assert sum(line.startswith("S ") for line in original) == 2
    params = tmp_path / "params.txt"
    params.write_text(chr(10).join(["ball.morph 256", "ball.gravity 64", "ball.shot 2000", "emitter.sound 25",
                                    "ball.passes 45"]) + chr(10))
    native, _log = record_wendigo(42, "native", "native=1", f"params={params}")
    described, log = record_wendigo(42, "described_params", f"program={program}", f"params={params}")
    assert "5 set" in log and described == native and native != original
    description = copy.deepcopy(load_description(42))
    description["effect"], description["name"] = 225, "New shoot"
    del description["copy"]["functions"]
    for task in description["tasks"]:
        task.pop("function", None)
    new, log = record_wendigo(225, "new", f"program={write_program(description, tmp_path / 'new.fxprog')}")
    assert "program: New_shoot" in log and untag(new) == original


def test_melting_bubble_description_compiles():
    """Melting Bubble: Doom's kind with Drain's master (Wind Blast's) - its actor pools, no stage tasks, its own emitter."""
    lines = compile_program(load_description(43)).splitlines()
    for line in ['module 43 0x2655778 0xAB4', 'act_stage -1 -1 0', 'act_pool actor_pool 67200', 'native 0x839C60']:
        assert line in lines, line


def test_junk_description_compiles():
    """Junk: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools in the magic buffer)."""
    lines = compile_program(load_description(44)).splitlines()
    for line in ['director port -1', 'port 0x6E7AE0 0x6E7AF0 0x6E7B90', 'module 44 0x2545100 0x84']:
        assert line in lines, line


def test_stare_vysage_description_compiles():
    """Stare: Doom's kind without actor pools - the per-action director, the director block's exe word, the master's view-axis call before the prim-model queue."""
    lines = compile_program(load_description(45)).splitlines()
    for line in ['module 45 0x26543B0 0x13C8', 'module_pointer 2 0x15C357C', 'pool_before 0x836840 0x1D97778 @view_matrix', 'code 0x836AC0']:
        assert line in lines, line


def test_sigh_description_compiles():
    """Sigh: Doom's kind with Drain's master - its actor pools, the stage wobble in and out (native tasks) after its wait."""
    lines = compile_program(load_description(46)).splitlines()
    for line in ['module 46 0x264EC60 0x3B54', 'act_stage 1 2 $3', 'act_pool actor_pool 67200', 'native 0x831FE0']:
        assert line in lines, line


def test_curse_description_compiles():
    """Curse: Doom's kind - the per-action director, the phase data's exe word, the emitter's and the director's state tables, its file released at the end."""
    lines = compile_program(load_description(47)).splitlines()
    for line in ['module 47 0x264B3C8 0x3898', 'module_pointer 2 0x15B8028', 'release_file', 'code 0x82B170']:
        assert line in lines, line


def test_magma_breath_description_compiles():
    """Magma Breath: Doom's kind with Drain's master (Counter Laser-Eye's) - its actor pools, the stage light ramps (native tasks) after its wait."""
    lines = compile_program(load_description(48)).splitlines()
    for line in ['module 48 0x26480F0 0x14FC', 'act_stage 1 2 $4', 'act_pool actor_pool 67200', 'native 0x825170']:
        assert line in lines, line


def test_resonance_description_compiles():
    """Resonance: Doom's kind without actor pools - the director block's exe word, the emitter's and the director's state tables, its file released at the end."""
    lines = compile_program(load_description(49)).splitlines()
    for line in ['module 49 0x26464D8 0x1C18', 'module_pointer 2 0x15ADAF0', 'release_file', 'code 0x821970']:
        assert line in lines, line


def test_hipotion_description_compiles():
    """Hi-Potion: Cura's kind (its module a relocated copy of Cura's) - Double's short root, its arenas in the magic buffer, its own emitter."""
    lines = compile_program(load_description(51)).splitlines()
    for line in ['module 51 0x2619F50 0x1AB68', 'magic_buffer 0x0 0x12000 0x0', 'director per_action 0 short', 'native 0x81C9E0']:
        assert line in lines, line


def test_xpotion_description_compiles():
    """X-Potion: Doom's kind with Drain's master (Curaga's code, no stage tasks) - its actor pools, its own emitter."""
    lines = compile_program(load_description(52)).splitlines()
    for line in ['module 52 0x26193D0 0xB7C', 'act_stage -1 -1 0', 'act_pool actor_pool 94080', 'native 0x817750']:
        assert line in lines, line


def test_megapotion_description_compiles():
    """Mega-Potion: Doom's kind with Drain's master, one emitter per target - its actor pools, the stage fade in and out (native tasks) after its wait, no camera track."""
    lines = compile_program(load_description(53)).splitlines()
    for line in ['module 53 0x2617168 0xFE4', 'per_target', 'act_stage 1 2 $3', 'native 0x8123A0']:
        assert line in lines, line


def test_everyones_grudge_description_compiles():
    """Everyone's Grudge: Doom's kind with Drain's master (Esuna's) - its actor pools, the stage wobble in and out (native tasks) after its wait."""
    lines = compile_program(load_description(54)).splitlines()
    for line in ['module 54 0x2616420 0xD44', 'act_stage 1 2 $3', 'act_pool actor_pool 40320', 'native 0x80CEF0']:
        assert line in lines, line


def test_aqua_breath_description_compiles():
    """Aqua Breath: Doom's kind without actor pools - the director block's exe word, the emitter's and the director's state tables."""
    lines = compile_program(load_description(55)).splitlines()
    for line in ['module 55 0x2610FA8 0x5478', 'module_pointer 2 0x15A38D4', 'arena_size 49152', 'code 0x808DD0']:
        assert line in lines, line


def test_absorb_description_compiles():
    """Absorb: Drain's kind (its module a relocated copy of Drain's) - its actor pools, the stage wobble in and out (native tasks) after its wait."""
    lines = compile_program(load_description(56)).splitlines()
    for line in ['module 56 0x260E338 0xE0C', 'act_stage 1 2 $5', 'act_pool actor_pool 94080', 'native 0x803660']:
        assert line in lines, line


def test_treatment_description_compiles():
    """Treatment: Esuna's kind (its module a relocated copy of Esuna's) - its actor pools, the stage wobble in and out (native tasks) after its wait."""
    lines = compile_program(load_description(57)).splitlines()
    for line in ['module 57 0x260D5F0 0xD48', 'act_stage 1 2 $3', 'act_pool actor_pool 67200', 'native 0x7FD590']:
        assert line in lines, line


def test_elixir_description_compiles():
    """Elixir: Mega-Potion's kind (its code with other immediates), one emitter per target - its actor pools, the stage fade in and out (native tasks) after its wait, no camera track."""
    lines = compile_program(load_description(58)).splitlines()
    for line in ['module 58 0x260A328 0xFE4', 'per_target', 'act_stage 1 2 $3', 'native 0x7F80E0']:
        assert line in lines, line


def test_megalixir_description_compiles():
    """Megalixir: Mega-Potion's kind (its code with other immediates), one emitter per target - its actor pools, the stage fade in and out (native tasks) after its wait, no camera track."""
    lines = compile_program(load_description(59)).splitlines()
    for line in ['module 59 0x2607060 0xFE4', 'per_target', 'act_stage 1 2 $4', 'native 0x7F2C40']:
        assert line in lines, line
