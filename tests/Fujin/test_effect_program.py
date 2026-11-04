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
    given = {arg.split("=")[0] for arg in extra}   # (a cast of its own replaces the default one: target= adds up)
    cast = [arg for arg in (f"slot3={BATTLE / 'c0m009.dat'}", "caster=0", "target=3") if arg.split("=")[0] not in given]
    run = subprocess.run([str(recorder), str(effect), f"exe={EXE}", f"magic={MAGIC}", f"battle={BATTLE}", f"out={out}",
                          f"slot0={BATTLE / 'd0c000.dat'}", f"weapon0={BATTLE / 'd0w000.dat'}", *cast, *extra],
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
    338: ("", 2, "voice 22311280\nsound 22311276\n"),
    333: ("mag140-158-159-258-331-332.tim", 1, "sound 22311280\n"),
    332: ("mag140-158-159-258-331-332.tim", 1, "sound 22311280\n"),
    327: ("mag326-329.tim", 3, "sounds.start 22311280\nsounds.horse 22311276\n"),
    326: ("mag186.tim", 6, "sounds.start 22311280\nsounds.slash 22311276\ntimeline.damage 380\n"),
    325: ("mag324.tim", 8, "sounds.start 22311280\nsounds.burst 22311276\ntimeline.damage 480\n"),
    317: ("mag127.tim", 1, "sound 22311280\n"),
    315: ("mag314.tim", 3, "sounds.start 22311280\nsounds.hit 22311276\n"),
    311: ("mag213-310.tim", 1, "sound 22311280\n"),
    310: ("mag308.tim", 1, "sound 22311280\n"),
    309: ("mag308.tim", 1, "sound 22311280\n"),
    307: ("mag009.tim", 2, "sounds.muzzle 22311280\nsounds.blast 22311276\n"),
    306: ("mag173.tim", 1, "sound 22311280\n"),
    305: ("mag149.tim", 2, "sound 22311280\nmaster.damage 25\n"),
    304: ("mag303.tim", 1, "sound 22311280\n"),
    300: ("mag130-299.tim", 1, "sound 22311280\n"),
    299: ("mag283-298.tim", 1, "sound 22311280\n"),
    297: ("mag296.tim", 1, "sound 22311280\n"),
    291: ("mag290.tim", 6, "sounds.start 22311280\nsounds.drop 22311276\n"),
    289: ("mag288.tim", 1, "sound 22311280\n"),
    288: ("mag287.tim", 1, "sound 22311280\n"),
    281: ("mag280.tim", 1, "sound 22311280\n"),
    280: ("mag279.tim", 1, "sound 22311280\n"),
    278: ("mag277.tim", 6, "sounds.start 22311280\nsounds.wall 22311276\nruby.damage 40\n"),
    277: ("mag276-301.tim", 1, "sound 22311280\n"),
    276: ("mag275.tim", 2, "sound_start 22311280\nsound_voice 22311280\n"),
    275: ("mag125.tim", 1, "sound 22311280\n"),
    274: ("mag273.tim", 6, "sound_punch 22311280\nsound_booya 22311280\nsound_heel 22311280\nsound_kick 22311280\nsound_dolphin 22311280\nsound_meteor 22311280\n"),
    273: ("mag272.tim", 1, "sound 22311280\n"),
    272: ("mag271.tim", 1, "sound 22311280\n"),
    271: ("mag270.tim", 1, "sound 22311280\n"),
    260: ("mag069-259.tim", 4, "sounds.start 22311280\nsounds.burst 22311276\nmaster.damage 230\n"),
    259: ("mag140-158-159-258-331-332.tim", 1, "sound 22311280\n"),
    226: ("mag296.tim", 1, "sound 22311280\n"),
    216: ("mag215.tim", 1, "sound 22311280\n"),
    215: ("mag214.tim", 3, "sounds.start 22311280\nsounds.jump 22311276\ndirector.damage 250\n"),
    212: ("mag211.tim", 3, "sounds.start 22311280\nsounds.burn 22311276\ndirector.damage 160\n"),
    200: ("mag199.tim", 3, "sounds.start 22311280\nsounds.swing 22311276\ndirector.damage 120\n"),
    199: ("mag198.tim", 3, "sounds.start 22311280\nsounds.flash 22311276\n"),
    198: ("mag197.tim", 1, "sound 22311280\n"),
    197: ("mag196.tim", 1, "sound 22311280\n"),
    196: ("mag195.tim", 1, "sound 22311280\n"),
    195: ("mag194.tim", 1, "sound 22311280\n"),
    194: ("mag193.tim", 1, "sound 22311280\n"),
    193: ("mag192.tim", 1, "sound 22311280\n"),
    192: ("mag191.tim", 1, "sound 22311280\n"),
    191: ("mag190.tim", 7, "sounds.start 22311280\nsounds.end 22311276\ntimeline.damage 400\n"),
    190: ("mag149.tim", 2, "sound 22311280\nmaster.damage 25\n"),
    189: ("mag188.tim", 2, "sound 22311280\nmain.result 50\n"),
    188: ("mag187.tim", 1, "sound 22311280\n"),
    187: ("mag186.tim", 5, "sounds.start 22311280\nsounds.slash 22311276\ntimeline.damage 270\n"),
    185: ("mag184.tim", 6, "sounds.start 22311280\nsounds.blast 22311276\ntimeline.damage 250\n"),
    184: ("mag153.tim", 2, "sound 22311280\ncontroller.damage 30\n"),
    183: ("mag182.tim", 2, "sound 22311280\ndirector.result 20\n"),
    182: ("mag181.tim", 4, "sounds.short_ 22311280\nsounds.card 22311276\ndirector.result_short 30\ndirector.result_card 50\n"),
    180: ("mag179.tim", 2, "sound 22311280\ndirector.damage 30\n"),
    179: ("mag178.tim", 2, "sound 22311280\ndirector.damage 30\n"),
    176: ("mag175.tim", 2, "sounds.wind 22311280\nsounds.land 22311276\n"),
    175: ("mag174.tim", 2, "sound 22311280\ndirector.damage 90\n"),
    169: ("mag168.tim", 2, "sound 22311280\ndirector.damage 30\n"),
    168: ("mag167.tim", 2, "sound 22311280\ndirector.damage 50\n"),
    165: ("mag164.tim", 4, "sounds.a 22311280\nsounds.d 22311276\n"),
    164: ("mag163.tim", 3, "sounds.raise 22311280\nsounds.blast 22311276\ndirector.damage 280\n"),
    163: ("mag162.tim", 2, "sound 22311280\ndirector.damage 50\n"),
    162: ("mag161.tim", 3, "sounds.start 22311280\nsounds.circle 22311276\ndirector.damage 140\n"),
    161: ("mag160.tim", 1, "sound 22311280\n"),
    160: ("mag140-158-159-258-331-332.tim", 1, "sound 22311280\n"),
    159: ("mag140-158-159-258-331-332.tim", 1, "sound 22311280\n"),
    155: ("mag154.tim", 2, "sound 22311280\ndirector.damage 40\n"),
    154: ("mag153.tim", 2, "sound 22311280\ncontroller.damage 30\n"),
    153: ("mag152.tim", 2, "sound 22311280\nmaster.damage 40\n"),
    152: ("mag151.tim", 2, "sound 22311280\ncontroller.damage 30\n"),
    149: ("mag148.tim", 4, "sounds.start 22311280\nsounds.blast 22311276\ndirector.damage 150\n"),
    148: ("mag147.tim", 2, "sound 22311280\ndirector.damage 60\n"),
    147: ("mag146.tim", 2, "sound 22311280\ndirector.status 20\n"),
    146: ("mag145.tim", 3, "sounds.wind 22311280\ndirector.damage 70\n"),
    145: ("mag144.tim", 2, "sound 22311280\ndirector.status 25\n"),
    144: ("mag143.tim", 2, "sound 22311280\ndirector.damage 30\n"),
    143: ("mag142.tim", 2, "sound 22311280\ndirector.damage 40\n"),
    142: ("mag141.tim", 2, "sound 22311280\ndirector.damage 10\n"),
    141: ("mag140-158-159-258-331-332.tim", 1, "sound 22311280\n"),
    140: ("mag139.tim", 5, "sounds.rise 22311280\ncreature.damage 200\n"),
    139: ("mag138.tim", 1, "sound 22311280\n"),
    138: ("mag137.tim", 2, "sound 22311280\nmain.damage 32\n"),
    137: ("mag136.tim", 2, "sound 22311280\nblast.damage 40\n"),
    136: ("mag135.tim", 2, "sound 22311280\nshot.damage 50\n"),
    135: ("mag134.tim", 2, "sound 22311280\nreflect.damage 20\n"),
    134: ("mag133.tim", 2, "sound 22311280\nbeam.damage 20\n"),
    132: ("mag131.tim", 2, "sound 22311280\ntarget.damage 40\n"),
    131: ("mag130-299.tim", 2, "sound 22311280\ntarget.damage 30\n"),
    130: ("mag129.tim", 2, "sound 22311280\nimpact.damage 5\n"),
    129: ("mag128.tim", 2, "sound 22311280\ntarget.damage 12\n"),
    128: ("mag127.tim", 2, "sound 22311280\ntarget.damage 40\n"),
    126: ("mag125.tim", 2, "sound 22311280\nmain.damage 60\n"),
    119: ("mag118.tim", 2, "sound 22311280\ntarget.status 50\n"),
    117: ("mag116.tim", 2, "sound 22311280\ntarget.status 70\n"),
    116: ("mag115.tim", 6, "sounds.rise 22311280\ncreature.damage 300\n"),
    113: ("mag112.tim", 2, "sound 22311280\ntarget.damage 20\n"),
    112: ("mag111.tim", 2, "sounds.start 22311280\nsounds.hit 22311276\n"),
    110: ("mag010.tim", 1, "sound 22311280\n"),
    107: ("mag106.tim", 2, "sound 22311280\ntarget.status 80\n"),
    105: ("mag104.tim", 2, "sound 22311280\nbolt.damage 56\n"),
    104: ("mag103.tim", 2, "sound 22311280\nfreeze.damage 60\n"),
    103: ("mag102.tim", 2, "sound 22311280\nblock.damage 50\n"),
    102: ("mag101.tim", 2, "sound 22311280\nbolt.damage 20\n"),
    101: ("mag100.tim", 2, "sound 22311280\nflash 1500\n"),
    100: ("mag096-097-098-099.tim", 4, "sounds.call 22311280\nsounds.second 22311276\n"),
    99: ("mag096-097-098-099.tim", 4, "sounds.call 22311280\nsounds.second 22311276\n"),
    98: ("mag096-097-098-099.tim", 3, "sounds.call 22311280\nsounds.attack 22311276\n"),
    97: ("mag096-097-098-099.tim", 3, "sounds.call 22311280\nsounds.attack 22311276\n"),
    96: ("mag095.tim", 2, "sounds.moogle 22311280\n"),
    95: ("mag094.tim", 4, "sounds.arrive 22311280\nsounds.song 22311276\n"),
    94: ("mag093.tim", 4, "sounds.revive 22311280\ndirector.damage 90\n"),
    93: ("mag092.tim", 4, "sounds.heal 22311280\ndirector.damage 90\n"),
    92: ("mag091.tim", 4, "sounds.walk 22311280\ndirector.damage 120\n"),
    91: ("mag090.tim", 1, "sound 22311280\n"),
    90: ("mag089_0.tim", 2, "sounds.walk 22311276\n"),
    89: (None, 3, "sounds.sky 21569528\n"),
    88: ("mag087.tim", 3, "director.damage 50\n"),
    87: ("mag086.tim", 3, "director.damage 90\n"),
    86: ("mag085.tim", 3, "director.damage 70\n"),
    85: ("mag084.tim", 3, "director.damage 20\n"),
    83: ("mag082.tim", 3, "director.damage 90\ndirector.actors 30\n"),
    82: ("mag081.tim", 3, "director.damage 50\ndirector.actors 30\n"),
    81: ("mag080.tim", 3, "director.damage 40\ndirector.actors 30\n"),
    80: ("mag079.tim", 4, "master.lift 1000\nmaster.damage 120\n"),
    79: ("mag078.tim", 5, "director.damage 100\ndirector.actors 30\n"),
    78: ("mag072-077.tim", 13, "emitter.result 50\nscale.times 5\ndarken.step 128\n"),
    76: ("mag075.tim", 9, "master.sink 40\nhalo.step 4096\nring.size 2000\n"),
    74: ("mag013-073-344.tim", 12, "reaper.fade_in 512\nstrike.length 30\nreaper.vanish_frame 14\naura.length 40\nreaper.wait 20\n"),
    73: ("mag072-077.tim", 10, "emitter.result 50\nmaster.wait 40\ndarken.step 128\n"),
    72: ("mag054-071.tim", 14, "orb.hold 25\ndarken.level 1024\nsplash.until 24\ndirector.damage 40\nrain.from 16\ndirector.wait 8\n"),
    71: ("mag070.tim", 15, "caster.lasers 22\nlaser.grow 512\nemitter.result 30\nlight.step 128\n"),
    70: ("mag069-259.tim", 7, "master.damage 200\nmaster.voice_release 240\n"),
    69: (None, 10, "sparks.count 2\nsink.depth 2800\nshatter.speed 14000\nsparks.life 9\n"),
    68: ("mag039-067.tim", 7, "camera.approach 400\ncamera.view 1000\nbrackets.follow 20\nbrackets.grow 1536\n"),
    67: ("mag023-066.tim", 9, "actors.length 30\nmaster.wait 30\nwobble.step 64\nemitter.release 25\n"),
    66: ("mag065.tim", 6, "melt.push 2500\nmaster.damage 40\nflash.flash_in 16\n"),
    65: ("mag064.tim", 9, "master.sink 200\nmaster.damage 500\nmaster.away 5000\n"),
    64: ("mag063.tim", 7, "flashes.b 30\nmaster.sound_tick 20\nmaster.end 180\n"),
    63: ("mag062.tim", 5, "impact.push 800\nimpact.flash 1024\nmaster.damage 60\nmaster.end 80\n"),
    62: ("mag061.tim", 13, "picture.scroll 8\ndarken.step 256\nmusic.step 16\nemitter.sound 30\n"),
    61: ("mag060.tim", 9, "stage.level 1024\nactors.length 30\ndirector.result 30\n"),
    60: ("mag059.tim", 15, "strike.push_by 800\ndarken.level 1024\ndebris.until 50\nactors.length 30\ndirector.damage 30\n"),
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


# the battle stage an effect draws (Griever shatters Ultimecia's stage models, Tornado redraws its ground): the recorder loads it
CYCLE_STAGES = {69: 142, 146: 0}

# more monsters an effect needs (Biggs and Wedge's first death sweeps its two targets; White Wind (Quistis) records
# too little on one): slot -> file, every target
CYCLE_MONSTERS = {110: {4: "c0m073.dat"}, 297: {4: "c0m009.dat"}}
# a cast of its own (a monster's attack on the party: Geezard's Bad Breath, Cockatrice's Electric Discharge, Gayla's Gastric Juice, Grendel's Breath, Malboro's): caster slot, target slot, slot 3's monster
CYCLE_CASTS = {113: (3, 0, "c0m004.dat"), 126: (3, 0, "c0m016.dat"), 128: (3, 0, "c0m033.dat"), 129: (3, 0, "c0m053.dat"), 130: (3, 0, "c0m048.dat"), 131: (3, 0, "c0m048.dat"), 132: (3, 0, "c0m048.dat"), 134: (3, 0, "c0m026.dat"), 135: (3, 0, "c0m026.dat"), 136: (3, 0, "c0m099.dat"), 137: (3, 0, "c0m099.dat"), 138: (3, 0, "c0m044.dat"), 139: (3, 0, "c0m099.dat"), 152: (3, 0, "c0m018.dat"), 153: (3, 0, "c0m017.dat"), 154: (3, 0, "c0m017.dat"), 155: (3, 0, "c0m020.dat"), 159: (0, 3, "c0m092.dat"), 161: (0, 3, "c0m091.dat"), 168: (3, 0, "c0m015.dat"), 169: (3, 0, "c0m015.dat"), 176: (3, 0, "c0m046.dat"), 179: (3, 0, "c0m043.dat"), 180: (3, 0, "c0m043.dat"), 190: (3, 0, "c0m008.dat"), 226: (3, 3, "c0m046.dat"), 276: (3, 0, "c0m092.dat"), 277: (3, 0, "c0m058.dat"), 281: (3, 0, "c0m078.dat"), 289: (3, 0, "c0m034.dat"), 304: (3, 0, "c0m079.dat"), 311: (3, 0, "c0m066.dat"), 315: (3, 0, "c0m075.dat")}
# what the battle's AnimSeq VM (not run by the recorder) would have written: Renzokuken's stage durations (opcode AB)
CYCLE_POKES = {141: ["poke=0x1D98214:4,10,9,10,9,14"], 159: ["poke=0x1D98214:4,10,9,10,9,14"], 160: ["poke=0x1D98214:4,10,9,10,9,14"], 161: ["poke=0x1D98214:4,10,9,10,9,14"], 259: ["poke=0x1D98214:5,10,9,10,9,10,14"], 332: ["poke=0x1D98214:6,10,9,10,9,10,9,14"], 333: ["poke=0x1D98214:7,10,9,10,9,10,9,10,14"]}
# what the battle's Shot window does for each trigger press: the setup called again with the sequence mode (2 a shot,
# 1 the closing action); Duel's actions: 2..7 a move, 8 the end
CYCLE_RECALLS = {188: ["recall=10:2,20:2,30:2,45:1"], 192: ["recall=10:2,20:2,30:2,45:1"], 193: ["recall=10:2,20:2,30:2,45:1"], 194: ["recall=10:2,20:2,30:2,45:1"], 195: ["recall=10:2,20:2,30:2,45:1"], 196: ["recall=10:2,20:2,30:2,45:1"], 197: ["recall=10:2,20:2,30:2,45:1"], 198: ["recall=10:2,20:2,30:2,45:1"], 274: ["recall=5:2,60:3,115:4,170:5,225:6,285:7,375:8"]}
# the caster's own model and weapon in slot 0 (Duel's Punch Rush reads Zell's bones)
CYCLE_MODELS = {274: ("d1c003.dat", "d1w008.dat")}
# a monster in a slot of its own that the effect reads, not a target (Gerogero rises out of the Fake President's
# puddle: the next slot)
CYCLE_SLOTS = {315: {4: "c0m034.dat"}}

# frames an exe quirk draws differently in a copy, left out of the comparisons (R numbers [from, to)): Siren's
# splash task picks surface vertices past its table 0x258EC70, in the load-script pool's nodes (their pointers);
# Quezacotl's ribbons read a joint direction the exe never initialises (a stack local: its port carries what the
# game's stack held, the recorder's in place holds another) - one quad in each of three frames
CYCLE_QUIRK_FRAMES = {95: [(289, 301)], 116: [(111, 112), (145, 146), (284, 285)]}


def quirk(effect, lines):
    if effect not in CYCLE_QUIRK_FRAMES:
        return lines
    out, skip = [], False
    for line in lines:
        if line.startswith("R "):
            skip = any(lo <= int(line.split()[1]) < hi for lo, hi in CYCLE_QUIRK_FRAMES[effect])
        if not skip:
            out.append(line)
    return out


def cycle_files(effect):
    return ("extracted_files/FF8_EN.exe", "extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat",
            "extracted_files/battle/c0m009.dat",
            *([f"extracted_files/magic/{CYCLES[effect][0]}"] if CYCLES[effect][0] else []),
            *([f"extracted_files/battle/a0stg{CYCLE_STAGES[effect]:03d}.x"] if effect in CYCLE_STAGES else []),
            *[f"extracted_files/battle/{name}" for name in CYCLE_MONSTERS.get(effect, {}).values()],
            *([f"extracted_files/battle/{CYCLE_CASTS[effect][2]}"] if effect in CYCLE_CASTS else []))


def test_float_description_compiles():
    """Float: the cycle director places two layouts; both drawn in frames turned with the target,
    scaled by its size, the second from a tick on, its depth from a point of its frame (exe data)."""
    program = compile_program(load_description(115))
    assert "director cycle 0 $0 action_target 0 " in program and "field layout_b 764 620" in program
    assert "tick anchor_at_position" in program and "draw 2 0 at_least $10 layout_turned 1 $9 0 0 " in program


@pytest.mark.parametrize("effect", [pytest.param(effect, marks=pytest.mark.ff8data(*cycle_files(effect)))
                                    for effect in CYCLES])
def test_cycle_effect_runs_from_its_description(tmp_path, effect):
    """Silence, Float, Slow, Haste, Dispel, Aura, Aero, Blind, both Petrify Stares, Zombie, Flare, Reflect, Berserk, Fire, Thunder, Double, Phoenix Down, Mega Phoenix, Doom, Ray-Bomb, Storm Breath, Blade Shot, Dark Mist, Death, Draw, Recover, Elvoret's entrance, Triple, Bio, Esuna, Cura, Clash, Full-life, Curaga, Wind Blast, Counter Laser-Eye, Protect, Shell, Pain, Life, Confuse, Drink Magic, Quake, Drain, Scan, Dribble, Melting Bubble, Junk, Stare, Sigh, Curse, Magma Breath, Resonance, Hi-Potion, X-Potion, Mega-Potion, Everyone's Grudge, Aqua Breath, Absorb, Treatment, Elixir, Megalixir, Raijin's strike, Revive, Devour, Helix's beam, Model breaking apart, Great Attractor, Griever's death, Remedy, Scan (enemy), Griever, Shockwave Pulsar, Laser Eye (Quistis), Aqua Breath (Quistis), Mighty Guard (Quistis), LV?Death (Quistis), Ultimecia's final form appears, Mighty Guard, Ultimecia's final form dies, Ultimecia junctions to Griever, Ultimecia's attack, Ultimecia's attack (82), Ultimecia absorbs into time, The End, Angelo Cannon, Angelo Strike, Invincible Moon, Wishing Star, Tonberry, Angelo Rush, Angelo Search, Angelo Recover, Angelo Reverse, Siren, MiniMog, ChocoFire, ChocoFlare, ChocoMeteor, ChocoBocle, Trauma's grab, Thundara, Blizzara, Blizzaga, Thundaga, Demi, Biggs, Wedge's first death, Meteor Barret, Bad Breath, Quezacotl, Break, Stop, Electric Discharge, Gastric Juice, Breath, Eerie Sound Wave, Bad Breath (Malboro), Dissolving Acid, Beam Laser, Reflect Beam, Oil Shot, Oil Blast, Saliva, Sonic Wave, Phoenix, Renzokuken (5 hits), Fira, Firaga, Blizzard, Sleep, Tornado, Regen, Meltdown, Ultima, Ultrasonic Waves, Sticky Web, Ultra Waves, Sand Storm, Renzokuken (vs X-ATM092), Renzokuken, Renzokuken (vs Elvoret), Fated Circle, Rough Divide, Blasting Zone, Lion Heart, Sleeping Gas, Gastric Juice (Grat), Holy, Sand Storm (Adamantoise), Bomb glow, Suicide, Card, Defend, Ultra Waves (Quistis), Shiva, Odin, Normal Shot, Wall, Chain Gun, Doomtrain, Scatter Shot, Dark Shot, Flame Shot, Canister Shot, Quick Shot, Armor Shot, Hyper Shot, Cactuar, No Mercy, Burning Rave, My Final Heaven, Different Beat, White Wind (enemy), Renzokuken (6 hits), Shockwave Pulsar (Quistis), LV Up, LV Down, Mad Rush, Duel, Electrocute, X-ATM092 death, Funguar laser, Carbuncle, Full-cure, Shotgun, Rapture, Brrawghh, Pandemona, White Wind (Quistis), Micro Missiles (Quistis), Bad Breath (Quistis), Boomerang Sword, Gatling Gun (Quistis), Degenerator (Quistis), Ray-Bomb (Quistis), Hero, Holy War, Gravija, Fake President death, Acid (Quistis), Diablos, Odin reverse, Gilgamesh, Renzokuken (7 hits) and Renzokuken (8 hits) and Moomba from their descriptions: what the exe's code records; with parameters, what
    FFNx's port records with them; as effect 225 (a free slot, no exe function), itself again."""
    _texture, count, values = CYCLES[effect]
    stage = [f"stage={CYCLE_STAGES[effect]}"] if effect in CYCLE_STAGES else []
    if effect in CYCLE_MONSTERS:
        stage += [f"slot{k}={BATTLE / name}" for k, name in CYCLE_MONSTERS[effect].items()]
        stage += [f"targets={1 + len(CYCLE_MONSTERS[effect])}"]
    if effect in CYCLE_CASTS:
        caster, target, monster = CYCLE_CASTS[effect]
        stage += [f"caster={caster}", f"target={target}", f"slot3={BATTLE / monster}"]
    stage += CYCLE_POKES.get(effect, [])
    stage += CYCLE_RECALLS.get(effect, [])
    stage += [f"slot{k}={BATTLE / name}" for k, name in CYCLE_SLOTS.get(effect, {}).items()]
    if effect in CYCLE_MODELS:
        stage += [f"slot0={BATTLE / CYCLE_MODELS[effect][0]}", f"weapon0={BATTLE / CYCLE_MODELS[effect][1]}"]
    program = write_program(load_description(effect), tmp_path / "effect.fxprog")
    original, _log = record(tmp_path, effect, "original", *stage)
    described, log = record(tmp_path, effect, "described", f"program={program}", *stage)
    tasks = len(load_description(effect)["tasks"])
    assert f"{tasks} tasks, {count} params" in log and quirk(effect, untag(described)) == quirk(effect, original)
    assert len(original) > 10000
    # (Ray-Bomb hurts the party only: on the monster the recorder casts on, no number; Elvoret's entrance and
    # Ultimecia's model breaking apart and Griever hurt nobody; Wishing Star's waves need eight target records a target; Trauma's grab and Biggs and Wedge's first death hurt nobody; Renzokuken's hits are Squall's sequence's; Draw's sounds are sound ids, BdPlaySy's, which the
    # recorder does not log)
    assert effect in (10, 17, 64, 69, 89, 101, 110, 141, 159, 160, 161, 259, 276, 332, 333) or any(line.startswith("N ") for line in original)
    assert effect == 15 or any(line.startswith("S ") for line in original)
    params = tmp_path / "params.txt"
    params.write_text(values)
    native, _log = record(tmp_path, effect, "native", "native=1", f"params={params}", *stage)
    described, log = record(tmp_path, effect, "described_params", f"program={program}", f"params={params}", *stage)
    assert f"{values.count(chr(10))} set" in log and quirk(effect, described) == quirk(effect, native) and native != original
    description = copy.deepcopy(load_description(effect))
    description["effect"], description["name"] = 225, "New cycle"
    del description["copy"]["functions"]
    for task in description["tasks"]:
        task.pop("function", None)   # (Berserk's sparks: a task of their own, no exe function)
    program = write_program(description, tmp_path / "new.fxprog")
    new, log = record(tmp_path, 225, "new", f"program={program}", *stage)
    assert "program: New_cycle" in log and quirk(effect, untag(new)) == quirk(effect, original)


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


def test_hells_judgement_description_compiles():
    """Hell's Judgement: Elvoret's death's kind - a port director calling the cinematic clone's own setup (the
    engine's shared state block), its root re-pointed; its two script files the parameters."""
    lines = compile_program(load_description(75)).splitlines()
    for line in ['director port -1', 'port 0xB3E8E0 0xB3E8B0 0xB3EF50 exe', 'module 75 0x2796E00 0x1E40']:
        assert line in lines, line


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/magic/MAG074_B.00", "extracted_files/magic/MAG074_B.01",
                     "extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat",
                     "extracted_files/battle/c0m009.dat")
def test_hells_judgement_runs_from_its_description(tmp_path):
    """Hell's Judgement from its description: what the exe's code records; a script file of its own (an edited
    .00 copy) read by the port's file loader and the program's alike; as effect 225, itself again."""
    program = write_program(load_description(75), tmp_path / "effect.fxprog")
    original, _log = record(tmp_path, 75, "original")
    described, log = record(tmp_path, 75, "described", f"program={program}")
    assert "0 tasks, 2 params" in log and untag(described) == original and len(original) > 10000
    files = tmp_path / "files"
    files.mkdir()
    script = bytearray((MAGIC / "MAG074_B.00").read_bytes())
    for k in range(0x8000, 0x8040, 2):
        script[k] = (script[k] + 3) & 0xFF
    (files / "hj75.00").write_bytes(script)
    params = tmp_path / "params.txt"
    params.write_text("files.file00 hj75.00\n")
    native, _log = record(tmp_path, 75, "native", "native=1", f"params={params}", f"overrides={files}")
    described, log = record(tmp_path, 75, "described_params", f"program={program}", f"params={params}",
                            f"overrides={files}")
    assert "1 set" in log and described == native and native != original
    description = copy.deepcopy(load_description(75))
    description["effect"], description["name"] = 225, "New judgement"
    del description["copy"]["functions"]
    new, log = record(tmp_path, 225, "new", f"program={write_program(description, tmp_path / 'new.fxprog')}")
    assert "program: New_judgement" in log and untag(new) == original


def test_final_form_death_description_compiles():
    """Ultimecia's final form death: Elvoret's death's kind - a port director calling the cinematic clone's own setup
    (the engine's shared state block), its root re-pointed; its two script files the parameters."""
    lines = compile_program(load_description(77)).splitlines()
    for line in ['director port -1', 'port 0xB302F0 0xB302C0 0xB30990 exe', 'module 77 0x2796E00 0x1E40']:
        assert line in lines, line


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/magic/MAG076_B.00", "extracted_files/magic/MAG076_B.01",
                     "extracted_files/battle/mag076_b.02", "extracted_files/battle/d0c000.dat",
                     "extracted_files/battle/d0w000.dat", "extracted_files/battle/c0m009.dat")
def test_final_form_death_runs_from_its_description(tmp_path):
    """Ultimecia's final form death from its description: what the exe's code records; a script file of its own (an
    edited .00 copy) read by the port's file loader and the program's alike; as effect 225, itself again."""
    program = write_program(load_description(77), tmp_path / "effect.fxprog")
    original, _log = record(tmp_path, 77, "original")
    described, log = record(tmp_path, 77, "described", f"program={program}")
    assert "0 tasks, 2 params" in log and untag(described) == original and len(original) > 10000
    files = tmp_path / "files"
    files.mkdir()
    script = bytearray((MAGIC / "MAG076_B.00").read_bytes())
    for k in range(0x8000, 0x8040, 2):
        script[k] = (script[k] + 3) & 0xFF
    (files / "ffd77.00").write_bytes(script)
    params = tmp_path / "params.txt"
    params.write_text("files.file00 ffd77.00\n")
    native, _log = record(tmp_path, 77, "native", "native=1", f"params={params}", f"overrides={files}")
    described, log = record(tmp_path, 77, "described_params", f"program={program}", f"params={params}",
                            f"overrides={files}")
    assert "1 set" in log and described == native and native != original
    description = copy.deepcopy(load_description(77))
    description["effect"], description["name"] = 225, "New final death"
    del description["copy"]["functions"]
    new, log = record(tmp_path, 225, "new", f"program={write_program(description, tmp_path / 'new.fxprog')}")
    assert "program: New_final_death" in log and untag(new) == original


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


def test_raijin_strike_description_compiles():
    """Raijin's strike: Doom's kind - the per-action director, the director block's exe word, the emitter's and the director's state tables, its file released at the end."""
    lines = compile_program(load_description(60)).splitlines()
    for line in ['module 60 0x2604078 0x2FE4', 'module_pointer 2 0x1597358', 'release_file', 'code 0x7EB580']:
        assert line in lines, line


def test_revive_ability_description_compiles():
    """Revive: Recover's kind (its code Recover's at its own addresses) - the director block's exe word, the emitter's and the director's state tables."""
    lines = compile_program(load_description(61)).splitlines()
    for line in ['module 61 0x2601920 0x2750', 'module_pointer 2 0x1596AD4', 'act_pool actor_pool 67200', 'code 0x7E5D80']:
        assert line in lines, line


def test_devour_description_compiles():
    """Devour: Doom's kind with Pain's master (no actor pools, no stage tasks), its own emitter, its four pictures loaded by the program's file loader before its texture."""
    lines = compile_program(load_description(62)).splitlines()
    for line in ['module 62 0x2601318 0x608', 'load_file tim_title 22637192 first', 'load_file tim_pic3 22637240 first', 'native 0x7E4D90']:
        assert line in lines, line


def test_helix_beam_description_compiles():
    """Helix's beam: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools in the magic buffer)."""
    lines = compile_program(load_description(63)).splitlines()
    for line in ['director port -1', 'port 0x6E6BE0 0x6E6BF0 0x6E6CB0', 'module 63 0x25450A0 0x60']:
        assert line in lines, line


def test_model_breaking_apart_description_compiles():
    """Model breaking apart: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools in the magic buffer)."""
    lines = compile_program(load_description(64)).splitlines()
    for line in ['director port -1', 'port 0x6E5180 0x6E5190 0x6E5260', 'module 64 0x2545018 0x84']:
        assert line in lines, line


def test_great_attractor_description_compiles():
    """Great Attractor: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools and particle tables in the magic buffer)."""
    lines = compile_program(load_description(65)).splitlines()
    for line in ['director port -1', 'port 0x6E0350 0x6E0360 0x6E03F0', 'module 65 0x2544F60 0xB4']:
        assert line in lines, line


def test_griever_death_description_compiles():
    """Griever's death: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory."""
    lines = compile_program(load_description(66)).splitlines()
    for line in ['director port -1', 'port 0x622610 0x6225F0 0x627DF0', 'module 66 0x24C66B0 0x2B20']:
        assert line in lines, line


def test_remedy_description_compiles():
    """Remedy: Esuna's kind (its module a relocated copy of Esuna's) - its actor pools, the stage wobble in and out (native tasks) after its wait."""
    lines = compile_program(load_description(67)).splitlines()
    for line in ['module 67 0x26005D0 0xD48', 'act_stage 1 2 $3', 'act_pool actor_pool 67200', 'native 0x7DEE60']:
        assert line in lines, line


def test_enemy_scan_description_compiles():
    """Scan (enemy): the spell Scan's library reduced to its short sequence, a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its camera state through its exe pointer)."""
    lines = compile_program(load_description(68)).splitlines()
    for line in ['director port -1', 'port 0x7DC1A0 0x7DC180 0x7DC280', 'module 68 0x25FCDD8 0x37DC']:
        assert line in lines, line


def test_griever_description_compiles():
    """Griever: a port director on the module's own setup (shared memory: its helpers run at their exe addresses), recorded on Ultimecia's stage (142): its two stage models shattered."""
    lines = compile_program(load_description(69)).splitlines()
    for line in ['director port -1', 'port 0x6FE050 0x0 0x6FE0D0 exe', 'module 69 0x2556628 0x970']:
        assert line in lines, line


def test_shockwave_pulsar_description_compiles():
    """Shockwave Pulsar: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools in the magic buffer)."""
    lines = compile_program(load_description(70)).splitlines()
    for line in ['director port -1', 'port 0x6DD8D0 0x6DD8E0 0x6DD970', 'module 70 0x2544E78 0xE4']:
        assert line in lines, line


def test_laser_eye_quistis_description_compiles():
    """Laser Eye (Quistis): Counter Laser-Eye's library relocated (Doom's kind with Drain's master) - its actor pools, the stage light up and down (native tasks) after its wait, its emitter the port's."""
    lines = compile_program(load_description(71)).splitlines()
    for line in ['module 71 0x25FA408 0x29D0', 'act_stage 1 2 $2', 'act_pool actor_pool 33600', 'native 0x7D65D0']:
        assert line in lines, line


def test_aqua_breath_quistis_description_compiles():
    """Aqua Breath (Quistis): Aqua Breath's library relocated (Doom's kind without actor pools) - the director block's exe word, the emitter's and the director's state tables."""
    lines = compile_program(load_description(72)).splitlines()
    for line in ['module 72 0x25F4F68 0x5498', 'module_pointer 2 0x1589C28', 'arena_size 49152', 'code 0x7D2430']:
        assert line in lines, line


def test_mighty_guard_quistis_description_compiles():
    """Mighty Guard (Quistis): Doom's kind with Drain's master - its actor pools, the stage darkening in and out (native tasks) after its wait; after the darkening in, its two act calls (the caster's animation set bound, her cast animation queued)."""
    lines = compile_program(load_description(73)).splitlines()
    for line in ['module 73 0x25F3F60 0x1008', 'act_stage 1 2 $4', 'act_pool actor_pool 67200', 'native 0x7CC220', 'act_call 0x5022C0 @caster @bind_block 0x1587F4C', 'act_call 0x505C00 @caster 0x1']:
        assert line in lines, line


def test_lvdeath_quistis_description_compiles():
    """LV?Death (Quistis): Death's library relocated (Doom's kind) - the director for each target, the module, the emitter's and the director's state tables."""
    lines = compile_program(load_description(74)).splitlines()
    for line in ['module 74 0x25EC518 0x7A40', 'module_pointer 2 0x1582068', 'per_target', 'release_file', 'arena_size 57344', 'code 0x7C49D0']:
        assert line in lines, line


def test_ultimecia_final_form_spawn_description_compiles():
    """Ultimecia's final form appears: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory."""
    lines = compile_program(load_description(76)).splitlines()
    for line in ['director port -1', 'port 0x61F9A0 0x61F980 0x6225A0', 'module 76 0x24C3270 0x343C']:
        assert line in lines, line


def test_mighty_guard_description_compiles():
    """Mighty Guard: Doom's kind with Drain's master - its actor pools, the stage darkening in and out (native tasks) after its wait."""
    lines = compile_program(load_description(78)).splitlines()
    for line in ['module 78 0x25EB530 0xFE4', 'act_stage 1 2 $4', 'act_pool actor_pool 67200', 'native 0x7BE710']:
        assert line in lines, line


def test_ultimecia_final_death_description_compiles():
    """Ultimecia's final form dies: Doom's kind - the per-action director, the module, the emitter's and the director's state tables, the master's own tail states after the last action."""
    lines = compile_program(load_description(79)).splitlines()
    for line in ['module 79 0x25DF338 0xC1F8', 'module_pointer 2 0x1580B20', 'arena_size 32768', 'code 0x7B55B0', 'act_tail 0x7BE1A0 0x7BE1F0 0x7BE220 0x7BE240 0x7BE270 0x7BE280 0x7BE2A0']:
        assert line in lines, line


def test_ultimecia_junction_description_compiles():
    """Ultimecia junctions to Griever: Doom's kind - the per-action director, the module, the emitter's and the director's state tables, the master's own state 1 (the caster put above its target)."""
    lines = compile_program(load_description(80)).splitlines()
    for line in ['module 80 0x25D4938 0xAA00', 'module_pointer 2 0x157B2E0', 'arena_size 32768', 'code 0x7ABAF0', 'act_state 1 0x7AB890']:
        assert line in lines, line


def test_ultimecia_attack_81_description_compiles():
    """Ultimecia's attack (81): Doom's kind - the per-action director, the module, the emitter's and the director's state tables, no file release."""
    lines = compile_program(load_description(81)).splitlines()
    for line in ['module 81 0x25D21E0 0x2758', 'module_pointer 2 0x157B104', 'arena_size 32768', 'code 0x7A5670']:
        assert line in lines, line


def test_ultimecia_attack_82_description_compiles():
    """Ultimecia's attack (82): Doom's kind - the per-action director, the module, the emitter's and the director's state tables, no file release."""
    lines = compile_program(load_description(82)).splitlines()
    for line in ['module 82 0x25CFA88 0x2758', 'module_pointer 2 0x157AEEC', 'arena_size 32768', 'code 0x79F2F0']:
        assert line in lines, line


def test_ultimecia_absorb_description_compiles():
    """Ultimecia absorbs into time: Doom's kind - the per-action director, the module, the emitter's and the director's state tables, Boko's pool sizes, the file released."""
    lines = compile_program(load_description(83)).splitlines()
    for line in ['module 83 0x25C9F70 0x5B18', 'module_pointer 2 0x157843C', 'release_file', 'arena_size 32768', 'code 0x797BF0', 'act_pool particle_pool 4320']:
        assert line in lines, line


def test_the_end_description_compiles():
    """The End: Doom's kind - the per-action director, the module, the emitter's (the cut machinery) and the director's state tables, the file released."""
    lines = compile_program(load_description(85)).splitlines()
    for line in ['module 85 0x25BC390 0x5FBC', 'module_pointer 2 0x156C7F0', 'release_file', 'arena_size 32768', 'code 0x784E30']:
        assert line in lines, line


def test_angelo_cannon_description_compiles():
    """Angelo Cannon: Doom's kind without actor pools - the per-action director, the module, the emitter's and the director's state tables, the file released."""
    lines = compile_program(load_description(86)).splitlines()
    for line in ['module 86 0x25B4CC8 0x76C8', 'module_pointer 2 0x1561770', 'release_file', 'arena_size 57344', 'code 0x77FBF0']:
        assert line in lines, line


def test_angelo_strike_description_compiles():
    """Angelo Strike: Doom's kind - the per-action director, the module (two exe words: the director block's and the camera block's), the emitter's and the director's state tables, the file released."""
    lines = compile_program(load_description(87)).splitlines()
    for line in ['module 87 0x25ACEB0 0x7E18', 'module_pointer 2 0x1557D28', 'module_pointer 3 0x155B1E0', 'release_file', 'arena_size 40960', 'code 0x774240']:
        assert line in lines, line


def test_invincible_moon_description_compiles():
    """Invincible Moon: Doom's kind - the per-action director, the module (the director block's and the camera block's exe words), the emitter's and the director's state tables, the file released."""
    lines = compile_program(load_description(88)).splitlines()
    for line in ['module 88 0x25A4D98 0x8118', 'module_pointer 2 0x154ECE0', 'module_pointer 3 0x154F918', 'release_file', 'arena_size 40960', 'code 0x768ED0']:
        assert line in lines, line


def test_wishing_star_description_compiles():
    """Wishing Star: a port director (Ray-Bomb's kind) - its setup the port's (no file loader: its TIMs are exe data), run on the program's memory."""
    lines = compile_program(load_description(89)).splitlines()
    for line in ['director port -1', 'port 0x6F9CF0 0x0 0x6F9D80', 'module 89 0x2556584 0xA0']:
        assert line in lines, line


def test_tonberry_description_compiles():
    """Tonberry: Doom's kind without actor pools - the per-action director, the module, the emitter's and the director's state tables; its loader's two more TIMs, uploaded by the setup."""
    lines = compile_program(load_description(90)).splitlines()
    for line in ['module 90 0x259EEA8 0x5F58', 'module_pointer 2 0x1547168', 'release_file', 'arena_size 24576', 'code 0x762C60', 'load_file tim_1 22342848 upload', 'load_file tim_2 22342864 upload']:
        assert line in lines, line


def test_angelo_rush_description_compiles():
    """Angelo Rush: Doom's kind - the per-action director, the module with its actor pools, the emitter's and the director's state tables; the dash's sound."""
    lines = compile_program(load_description(91)).splitlines()
    for line in ['module 91 0x2598F28 0x5F80', 'release_file', 'arena_size 32768', 'code 0x7598C0']:
        assert line in lines, line


def test_angelo_search_description_compiles():
    """Angelo Search: Doom's kind without actor pools - the per-action director, the module, the emitter's and the director's state tables; the three sounds and the found item's frame."""
    lines = compile_program(load_description(92)).splitlines()
    for line in ['module 92 0x2594D98 0x4188', 'release_file', 'arena_size 32768', 'code 0x7555B0']:
        assert line in lines, line


def test_angelo_recover_description_compiles():
    """Angelo Recover: Doom's kind - the per-action director, the module with its actor pools, the emitter's and the director's state tables; the two sounds and the director's frames."""
    lines = compile_program(load_description(93)).splitlines()
    for line in ['module 93 0x2592548 0x2850', 'release_file', 'arena_size 32768', 'code 0x74E8B0']:
        assert line in lines, line


def test_angelo_reverse_description_compiles():
    """Angelo Reverse: Doom's kind - the per-action director, the module with its actor pools, the emitter's and the director's state tables; the two sounds and the director's frames."""
    lines = compile_program(load_description(94)).splitlines()
    for line in ['module 94 0x258FCF8 0x2850', 'release_file', 'arena_size 32768', 'code 0x747B10']:
        assert line in lines, line


def test_siren_description_compiles():
    """Siren: the act engine's own module - the per-action director with its cut script, the module with its actor pools, the emitter's and the director's state tables; the four sounds."""
    lines = compile_program(load_description(95)).splitlines()
    for line in ['module 95 0x257F8A0 0x10458', 'release_file', 'arena_size 3072', 'code 0x73A7B0']:
        assert line in lines, line


def test_minimog_description_compiles():
    """MiniMog: Doom's kind with the module's own director (the port's task, its draw-mode packet after its states) - the per-action emitter's state table, the module with its actor pools and two exe words; the two sounds."""
    lines = compile_program(load_description(96)).splitlines()
    for line in ['module 96 0x257B740 0x4160', 'module_pointer 2 0x152BB90', 'module_pointer 3 0x152BC00', 'release_file', 'arena_size 4096', 'code 0x7327B0', 'native 0x7327B0']:
        assert line in lines, line


def test_chocofire_description_compiles():
    """ChocoFire: Doom's kind on the shared Boko port - the per-action director, the module with its actor pools and two exe words; its sounds."""
    lines = compile_program(load_description(97)).splitlines()
    for line in ['module 97 0x2575268 0x64D8', 'module_pointer 2 0x152B5B8', 'module_pointer 3 0x152BA30', 'release_file', 'arena_size 4096', 'code 0x72A410']:
        assert line in lines, line


def test_chocoflare_description_compiles():
    """ChocoFlare: Doom's kind on the shared Boko port - the per-action director, the module with its actor pools and two exe words; its sounds."""
    lines = compile_program(load_description(98)).splitlines()
    for line in ['module 98 0x256E358 0x6F10', 'module_pointer 2 0x152AF30', 'module_pointer 3 0x152B3C8', 'release_file', 'arena_size 4096', 'code 0x722210']:
        assert line in lines, line


def test_chocometeor_description_compiles():
    """ChocoMeteor: Doom's kind on the shared Boko port - the per-action director, the module with its actor pools and two exe words; its sounds."""
    lines = compile_program(load_description(99)).splitlines()
    for line in ['module 99 0x2565A30 0x8928', 'module_pointer 2 0x1529FA0', 'module_pointer 3 0x152AC40', 'release_file', 'arena_size 4096', 'code 0x718750']:
        assert line in lines, line


def test_chocobocle_description_compiles():
    """ChocoBocle: Doom's kind on the shared Boko port - the per-action director, the module with its actor pools and two exe words; its sounds."""
    lines = compile_program(load_description(100)).splitlines()
    for line in ['module 100 0x255EAC8 0x6F68', 'module_pointer 2 0x15297F0', 'module_pointer 3 0x1529CD0', 'release_file', 'arena_size 4096', 'code 0x70F370']:
        assert line in lines, line


def test_trauma_grab_description_compiles():
    """Trauma's grab: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its grab pool in the magic buffer)."""
    lines = compile_program(load_description(101)).splitlines()
    for line in ['director port -1', 'port 0x6DD0C0 0x6DD0D0 0x6DD1A0', 'module 101 0x2544E10 0x68']:
        assert line in lines, line


def test_thundara_description_compiles():
    """Thundara: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory."""
    lines = compile_program(load_description(102)).splitlines()
    for line in ['director port -1', 'port 0x6DC2D0 0x6DC2B0 0x6DC390', 'module 102 0x2543F18 0xEF8']:
        assert line in lines, line


def test_blizzara_description_compiles():
    """Blizzara: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools and model copies in the magic buffer)."""
    lines = compile_program(load_description(103)).splitlines()
    for line in ['director port -1', 'port 0x6DA300 0x6DA2E0 0x6DA3A0', 'module 103 0x2543E90 0x88']:
        assert line in lines, line


def test_blizzaga_description_compiles():
    """Blizzaga: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools and model copies in the magic buffer)."""
    lines = compile_program(load_description(104)).splitlines()
    for line in ['director port -1', 'port 0x6D6310 0x6D62F0 0x6D6400', 'module 104 0x2543DF0 0xA0']:
        assert line in lines, line


def test_thundaga_description_compiles():
    """Thundaga: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools and debris in the magic buffer)."""
    lines = compile_program(load_description(105)).splitlines()
    for line in ['director port -1', 'port 0x6D3DB0 0x6D3DC0 0x6D3E50', 'module 105 0x2543CF0 0x100']:
        assert line in lines, line


def test_demi_description_compiles():
    """Demi: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools in the magic buffer)."""
    lines = compile_program(load_description(107)).splitlines()
    for line in ['director port -1', 'port 0x6D1310 0x6D1320 0x6D13B0', 'module 107 0x2521B30 0x88']:
        assert line in lines, line


def test_biggs_wedge_death_description_compiles():
    """Biggs and Wedge's first death: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools and vertex table in the magic buffer)."""
    lines = compile_program(load_description(110)).splitlines()
    for line in ['director port -1', 'port 0x6CE210 0x6CE220 0x6CE2A0', 'module 110 0x25219C8 0x9C']:
        assert line in lines, line


def test_meteor_barret_description_compiles():
    """Meteor Barret: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools in the magic buffer)."""
    lines = compile_program(load_description(112)).splitlines()
    for line in ['director port -1', 'port 0x6CBBE0 0x6CBBF0 0x6CBCF0', 'module 112 0x25218E0 0x90']:
        assert line in lines, line


def test_bad_breath_description_compiles():
    """Bad Breath: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools in the magic buffer)."""
    lines = compile_program(load_description(113)).splitlines()
    for line in ['director port -1', 'port 0x6CAC20 0x6CAC30 0x6CACD0', 'module 113 0x2521870 0x70']:
        assert line in lines, line


def test_quezacotl_description_compiles():
    """Quezacotl: a port director (Ray-Bomb's kind) on a shared module - its setup, file loader and stream callback the port's, the exe's own helpers reading the module's words."""
    lines = compile_program(load_description(116)).splitlines()
    for line in ['director port -1', 'port 0x6C3550 0x6C3560 0x6C3760', 'module 116 0x25216D8 0xF8']:
        assert line in lines, line


def test_break_description_compiles():
    """Break: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools and dither table in the magic buffer)."""
    lines = compile_program(load_description(117)).splitlines()
    for line in ['director port -1', 'port 0x6C16A0 0x6C16B0 0x6C1740', 'module 117 0x2521650 0x88']:
        assert line in lines, line


def test_stop_description_compiles():
    """Stop: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pool and shard buffer in the magic buffer)."""
    lines = compile_program(load_description(119)).splitlines()
    for line in ['director port -1', 'port 0x6BEFD0 0x6BEFE0 0x6BF070', 'module 119 0x2521590 0x48']:
        assert line in lines, line


def test_electric_discharge_description_compiles():
    """Electric Discharge: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools in the magic buffer)."""
    lines = compile_program(load_description(126)).splitlines()
    for line in ['director port -1', 'port 0x6B9A10 0x6B9A20 0x6B9AF0', 'module 126 0x25212C0 0xA8']:
        assert line in lines, line


def test_gastric_juice_description_compiles():
    """Gastric Juice: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools in the magic buffer)."""
    lines = compile_program(load_description(128)).splitlines()
    for line in ['director port -1', 'port 0x6B7D00 0x6B7D10 0x6B7DB0', 'module 128 0x25211E0 0x90']:
        assert line in lines, line


def test_breath_description_compiles():
    """Breath: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools in the magic buffer)."""
    lines = compile_program(load_description(129)).splitlines()
    for line in ['director port -1', 'port 0x6B4C00 0x6B4C10 0x6B4CB0', 'module 129 0x2521110 0xD0']:
        assert line in lines, line


def test_eerie_sound_wave_description_compiles():
    """Eerie Sound Wave: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools in the magic buffer)."""
    lines = compile_program(load_description(130)).splitlines()
    for line in ['director port -1', 'port 0x6B4240 0x6B4250 0x6B42F0', 'module 130 0x25210A8 0x68']:
        assert line in lines, line


def test_bad_breath_malboro_description_compiles():
    """Malboro's Bad Breath: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools in the magic buffer)."""
    lines = compile_program(load_description(131)).splitlines()
    for line in ['director port -1', 'port 0x6B2BD0 0x6B2BE0 0x6B2C80', 'module 131 0x2520FF0 0xB8']:
        assert line in lines, line


def test_dissolving_acid_description_compiles():
    """Dissolving Acid: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools in the magic buffer)."""
    lines = compile_program(load_description(132)).splitlines()
    for line in ['director port -1', 'port 0x6B19F0 0x6B1A00 0x6B1AA0', 'module 132 0x2520F60 0x90']:
        assert line in lines, line


def test_beam_laser_description_compiles():
    """Beam Laser: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools in the magic buffer)."""
    lines = compile_program(load_description(134)).splitlines()
    for line in ['director port -1', 'port 0x6B0070 0x6B0080 0x6B0130', 'module 134 0x2520E68 0x80']:
        assert line in lines, line


def test_reflect_beam_description_compiles():
    """Reflect Beam: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools in the magic buffer)."""
    lines = compile_program(load_description(135)).splitlines()
    for line in ['director port -1', 'port 0x6AEEA0 0x6AEEB0 0x6AEF50', 'module 135 0x2520DD0 0x98']:
        assert line in lines, line


def test_oil_shot_description_compiles():
    """Oil Shot: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools in the magic buffer)."""
    lines = compile_program(load_description(136)).splitlines()
    for line in ['director port -1', 'port 0x6AD1A0 0x6AD1B0 0x6AD250', 'module 136 0x2520D28 0xA8']:
        assert line in lines, line


def test_oil_blast_description_compiles():
    """Oil Blast: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools in the magic buffer)."""
    lines = compile_program(load_description(137)).splitlines()
    for line in ['director port -1', 'port 0x6AB850 0x6AB860 0x6AB900', 'module 137 0x2520CC0 0x68']:
        assert line in lines, line


def test_saliva_description_compiles():
    """Saliva: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools in the magic buffer)."""
    lines = compile_program(load_description(138)).splitlines()
    for line in ['director port -1', 'port 0x6A9F10 0x6A9F20 0x6A9FC0', 'module 138 0x2520C48 0x78']:
        assert line in lines, line


def test_sonic_wave_description_compiles():
    """Sonic Wave: a port director (Ray-Bomb's kind) - its setup (the module's data copy) and file loader the port's, run on the program's memory."""
    lines = compile_program(load_description(139)).splitlines()
    for line in ['director port -1', 'port 0x6A8830 0x6A8840 0x6A88F0', 'module 139 0x2517B50 0x90F8']:
        assert line in lines, line


def test_phoenix_description_compiles():
    """Phoenix: a port director (Ray-Bomb's kind) - its setup, file loader and stream callback the port's, run on the program's memory."""
    lines = compile_program(load_description(140)).splitlines()
    for line in ['director port -1', 'port 0x6A6300 0x6A6310 0x6A6530', 'module 140 0x2517AA0 0xB0']:
        assert line in lines, line


def test_renzokuken_5_description_compiles():
    """Renzokuken (5 hits): a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory; the recorder pokes the stage durations the AnimSeq VM would compute."""
    lines = compile_program(load_description(141)).splitlines()
    for line in ['director port -1', 'port 0x61DE70 0x61DE50 0x61F710', 'module 141 0x24C10B8 0x21B8']:
        assert line in lines, line


def test_fira_description_compiles():
    """Fira: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory."""
    lines = compile_program(load_description(142)).splitlines()
    for line in ['director port -1', 'port 0x61CE10 0x61CDF0 0x61DD90', 'module 142 0x24BFB48 0x1570']:
        assert line in lines, line


def test_firaga_description_compiles():
    """Firaga: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory."""
    lines = compile_program(load_description(143)).splitlines()
    for line in ['director port -1', 'port 0x61BFE0 0x61BFC0 0x61CDA0', 'module 143 0x24BECC8 0xE78']:
        assert line in lines, line


def test_blizzard_description_compiles():
    """Blizzard: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory."""
    lines = compile_program(load_description(144)).splitlines()
    for line in ['director port -1', 'port 0x61ABA0 0x61AB80 0x61BF70', 'module 144 0x24BB960 0x3368']:
        assert line in lines, line


def test_sleep_description_compiles():
    """Sleep: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its packet arenas in the module)."""
    lines = compile_program(load_description(145)).splitlines()
    for line in ['director port -1', 'port 0x6185D0 0x6185B0 0x61AA80', 'module 145 0x24AA630 0x11330']:
        assert line in lines, line


def test_tornado_description_compiles():
    """Tornado: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools and packet arenas in the module); a battle stage loaded (its ground redrawn)."""
    lines = compile_program(load_description(146)).splitlines()
    for line in ['director port -1', 'port 0x614D70 0x614D50 0x618560', 'module 146 0x2491BC0 0x18A70']:
        assert line in lines, line


def test_regen_description_compiles():
    """Regen: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools and packet arenas in the module)."""
    lines = compile_program(load_description(147)).splitlines()
    for line in ['director port -1', 'port 0x614290 0x614270 0x614D10', 'module 147 0x2476660 0x1B55C']:
        assert line in lines, line


def test_meltdown_description_compiles():
    """Meltdown: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools and packet arenas in the module)."""
    lines = compile_program(load_description(148)).splitlines()
    for line in ['director port -1', 'port 0x6120D0 0x6120B0 0x614230', 'module 148 0x2464BA8 0x11AB8']:
        assert line in lines, line


def test_ultima_description_compiles():
    """Ultima: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools and particle arrays in the module, its packets in the magic buffer)."""
    lines = compile_program(load_description(149)).splitlines()
    for line in ['director port -1', 'port 0x60F690 0x60F670 0x612000', 'module 149 0x2461E88 0x2D20']:
        assert line in lines, line


def test_ultrasonic_waves_description_compiles():
    """Ultrasonic Waves: a port controller (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools in the module, its packets in the magic buffer); cast by Red Bat."""
    lines = compile_program(load_description(152)).splitlines()
    for line in ['director port -1', 'port 0x60AFB0 0x60AF90 0x60C8F0', 'module 152 0x244BE70 0x1800']:
        assert line in lines, line


def test_sticky_web_description_compiles():
    """Sticky Web: a port master (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools and packet arenas in the module); cast by Caterchipillar."""
    lines = compile_program(load_description(153)).splitlines()
    for line in ['director port -1', 'port 0x609640 0x609620 0x60AF50', 'module 153 0x243A4D8 0x11998']:
        assert line in lines, line


def test_ultra_waves_description_compiles():
    """Ultra Waves: a port controller (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools, grid and packet arenas in the module); cast by Caterchipillar."""
    lines = compile_program(load_description(154)).splitlines()
    for line in ['director port -1', 'port 0x607C10 0x607BF0 0x609590', 'module 154 0x2404238 0x362A0']:
        assert line in lines, line


def test_sand_storm_description_compiles():
    """Sand Storm: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools, funnel vertices and packet arenas in the module); cast by Fastitocalon."""
    lines = compile_program(load_description(155)).splitlines()
    for line in ['director port -1', 'port 0x606CF0 0x606CD0 0x607BB0', 'module 155 0x23F07F0 0x13A48']:
        assert line in lines, line


def test_renzokuken_xatm_description_compiles():
    """Renzokuken vs X-ATM092: a port controller (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory; Squall on X-ATM092 (its animation set bound too)."""
    lines = compile_program(load_description(159)).splitlines()
    for line in ['director port -1', 'port 0x600BC0 0x600BA0 0x602C40', 'module 159 0x23D5648 0x24BC']:
        assert line in lines, line


def test_renzokuken_generic_description_compiles():
    """Renzokuken (the generic version): a port controller (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory."""
    lines = compile_program(load_description(160)).splitlines()
    for line in ['director port -1', 'port 0x5FF080 0x5FF060 0x600930', 'module 160 0x23D34A8 0x219C']:
        assert line in lines, line


def test_renzokuken_elvoret_description_compiles():
    """Renzokuken vs Elvoret: a port controller (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory; Squall on Elvoret (its animation set bound too)."""
    lines = compile_program(load_description(161)).splitlines()
    for line in ['director port -1', 'port 0x5FD100 0x5FD0E0 0x5FEC10', 'module 161 0x23D0D90 0x2714']:
        assert line in lines, line


def test_fated_circle_description_compiles():
    """Fated Circle: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory."""
    lines = compile_program(load_description(162)).splitlines()
    for line in ['director port -1', 'port 0x5F90F0 0x5F90D0 0x5FD090', 'module 162 0x23CE588 0x2804']:
        assert line in lines, line


def test_rough_divide_description_compiles():
    """Rough Divide: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory."""
    lines = compile_program(load_description(163)).splitlines()
    for line in ['director port -1', 'port 0x5F5B80 0x5F5B60 0x5F9020', 'module 163 0x23CA120 0x4468']:
        assert line in lines, line


def test_blasting_zone_description_compiles():
    """Blasting Zone: a port director (Ray-Bomb's kind) - its setup (Squall turned to the targets) and file loader the port's, run on the program's memory."""
    lines = compile_program(load_description(164)).splitlines()
    for line in ['director port -1', 'port 0x5F0260 0x5F0240 0x5F5B10', 'module 164 0x23C6950 0x37CC']:
        assert line in lines, line


def test_lion_heart_description_compiles():
    """Lion Heart: a port director (Ray-Bomb's kind) - its setup (Squall turned to the targets) and file loader the port's, run on the program's memory."""
    lines = compile_program(load_description(165)).splitlines()
    for line in ['director port -1', 'port 0x5E9470 0x5E9450 0x5F01F0', 'module 165 0x23C3278 0x36D8']:
        assert line in lines, line


def test_sleeping_gas_description_compiles():
    """Sleeping Gas: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools and cloud buffers in the module, its packets in the magic buffer); cast by Grat."""
    lines = compile_program(load_description(168)).splitlines()
    for line in ['director port -1', 'port 0x5E1750 0x5E1730 0x5E29A0', 'module 168 0x23B3C10 0x9740']:
        assert line in lines, line


def test_gastric_juice_grat_description_compiles():
    """Gastric Juice (Grat): a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools and mesh buffers in the module, its packets in the magic buffer); cast by Grat."""
    lines = compile_program(load_description(169)).splitlines()
    for line in ['director port -1', 'port 0x5DEE60 0x5DEE40 0x5E16E0', 'module 169 0x23B1370 0x28A0']:
        assert line in lines, line


def test_holy_description_compiles():
    """Holy: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools, grid and triangles in the module, its packets in the magic buffer)."""
    lines = compile_program(load_description(175)).splitlines()
    for line in ['director port -1', 'port 0x5D1AD0 0x5D1AB0 0x5D44C0', 'module 175 0x2374578 0x1FC90']:
        assert line in lines, line


def test_sand_storm_adamantoise_description_compiles():
    """Sand Storm (Adamantoise): a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools, funnel packets and rings in the module); cast by Adamantoise."""
    lines = compile_program(load_description(176)).splitlines()
    for line in ['director port -1', 'port 0x5D00F0 0x5D00D0 0x5D1A60', 'module 176 0x2368580 0xBFF4']:
        assert line in lines, line


def test_bomb_glow_description_compiles():
    """Bomb glow: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools and packet arenas in the module); cast by the Bomb."""
    lines = compile_program(load_description(179)).splitlines()
    for line in ['director port -1', 'port 0x5CDF40 0x5CDF20 0x5CED70', 'module 179 0x2309558 0x117B8']:
        assert line in lines, line


def test_suicide_description_compiles():
    """Suicide: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools in the module, its packets in the magic buffer); cast by the Bomb."""
    lines = compile_program(load_description(180)).splitlines()
    for line in ['director port -1', 'port 0x5CC840 0x5CC820 0x5CDED0', 'module 180 0x2307D98 0x17BC']:
        assert line in lines, line


def test_card_description_compiles():
    """Card: a port director (Ray-Bomb's kind) - its setup (the director by the target record's bit) and file loader the port's, run on the program's memory (its pools in the module, its packets in the magic buffer)."""
    lines = compile_program(load_description(182)).splitlines()
    for line in ['director port -1', 'port 0x5C9FE0 0x5C9FC0 0x5CB4E0', 'module 182 0x2304220 0x23B4']:
        assert line in lines, line


def test_defend_description_compiles():
    """Defend: a port director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools and packet arenas in the module)."""
    lines = compile_program(load_description(183)).splitlines()
    for line in ['director port -1', 'port 0x5C9A50 0x5C9A30 0x5C9F80', 'module 183 0x22F33C8 0x10E58']:
        assert line in lines, line


def test_ultra_waves_quistis_description_compiles():
    """Ultra Waves (Quistis): a port controller (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools, grid and packet arenas in the module)."""
    lines = compile_program(load_description(184)).splitlines()
    for line in ['director port -1', 'port 0x5C7FC0 0x5C7FA0 0x5C99A0', 'module 184 0x22BD108 0x362C0']:
        assert line in lines, line


def test_shiva_description_compiles():
    """Shiva: a port timeline (Ray-Bomb's kind) on a shared module - its setup and file loader the port's, the exe's own renderers reading the module's words."""
    lines = compile_program(load_description(185)).splitlines()
    for line in ['director port -1', 'port 0x5C0D50 0x5C0D30 0x5C7F50', 'module 185 0x22BC128 0xFD8']:
        assert line in lines, line


def test_odin_description_compiles():
    """Odin: a port timeline (Ray-Bomb's kind) on a shared module - its setup the port's (the file loader is the engine's nullsub, the texture exe data), the exe's own renderers reading and writing the module's words."""
    lines = compile_program(load_description(187)).splitlines()
    for line in ['director port -1', 'port 0x6472E0 0x0 0x64DD50', 'module 187 0x24FD458 0x14A8']:
        assert line in lines, line


def test_normal_shot_description_compiles():
    """Normal Shot: a port root (Ray-Bomb's kind) - its setup (by the cast's sequence mode: the opening, a shot, the closing action) and file loader the port's, run on the program's memory; three shots and the closing action recalled like the battle's Shot window."""
    lines = compile_program(load_description(188)).splitlines()
    for line in ['director port -1', 'port 0x5BE340 0x5BE320 0x5BF650', 'module 188 0x22B2A38 0x4BBC']:
        assert line in lines, line


def test_wall_description_compiles():
    """Wall: a port main task (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools, capture packets and packet arenas in the module)."""
    lines = compile_program(load_description(189)).splitlines()
    for line in ['director port -1', 'port 0x5BC960 0x5BC940 0x5BE290', 'module 189 0x2293F4C 0x1EAE8']:
        assert line in lines, line


def test_chain_gun_description_compiles():
    """Chain Gun: a port master (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools and packet arenas in the module); cast by GIM47N."""
    lines = compile_program(load_description(190)).splitlines()
    for line in ['director port -1', 'port 0x5BB2C0 0x5BB2A0 0x5BC900', 'module 190 0x2281B18 0x1242C']:
        assert line in lines, line


def test_doomtrain_description_compiles():
    """Doomtrain: a port timeline (Ray-Bomb's kind) on a shared module - its setup the port's (the file loader is the engine's nullsub, the texture exe data), run on the module's memory (the camera-script interpreter's state lives in it)."""
    lines = compile_program(load_description(191)).splitlines()
    for line in ['director port -1', 'port 0x63E730 0x0 0x6472C0', 'module 191 0x24FBD68 0x16D0']:
        assert line in lines, line


def test_scatter_shot_description_compiles():
    """Scatter Shot: a port root (Ray-Bomb's kind) - its setup (by the cast's sequence mode: the opening, a shot, the closing action) and file loader the port's, run on the program's memory; three shots and the closing action recalled like the battle's Shot window."""
    lines = compile_program(load_description(192)).splitlines()
    for line in ['director port -1', 'port 0x5B96F0 0x5B96D0 0x5BB1B0', 'module 192 0x227B338 0x67DC']:
        assert line in lines, line


def test_dark_shot_description_compiles():
    """Dark Shot: a port root (Ray-Bomb's kind) - its setup (by the cast's sequence mode: the opening, a shot, the closing action) and file loader the port's, run on the program's memory; three shots and the closing action recalled like the battle's Shot window."""
    lines = compile_program(load_description(193)).splitlines()
    for line in ['director port -1', 'port 0x5B7190 0x5B7170 0x5B95E0', 'module 193 0x2276778 0x4BBC']:
        assert line in lines, line


def test_flame_shot_description_compiles():
    """Flame Shot: a port root (Ray-Bomb's kind) - its setup (by the cast's sequence mode: the opening, a shot, the closing action) and file loader the port's, run on the program's memory; three shots and the closing action recalled like the battle's Shot window."""
    lines = compile_program(load_description(194)).splitlines()
    for line in ['director port -1', 'port 0x5B4C60 0x5B4C40 0x5B7080', 'module 194 0x2271470 0x5308']:
        assert line in lines, line


def test_canister_shot_description_compiles():
    """Canister Shot: a port root (Ray-Bomb's kind) - its setup (by the cast's sequence mode: the opening, a shot, the closing action) and file loader the port's, run on the program's memory; three shots and the closing action recalled like the battle's Shot window."""
    lines = compile_program(load_description(195)).splitlines()
    for line in ['director port -1', 'port 0x5B2A40 0x5B2A20 0x5B4BC0', 'module 195 0x226A970 0x6AFC']:
        assert line in lines, line


def test_quick_shot_description_compiles():
    """Quick Shot: a port root (Ray-Bomb's kind) - its setup (by the cast's sequence mode: the opening, a shot, the closing action) and file loader the port's, run on the program's memory; three shots and the closing action recalled like the battle's Shot window."""
    lines = compile_program(load_description(196)).splitlines()
    for line in ['director port -1', 'port 0x5B1900 0x5B18E0 0x5B29A0', 'module 196 0x2265DB0 0x4BBC']:
        assert line in lines, line


def test_armor_shot_description_compiles():
    """Armor Shot: a port root (Ray-Bomb's kind) - its setup (by the cast's sequence mode: the opening, a shot, the closing action) and file loader the port's, run on the program's memory; three shots and the closing action recalled like the battle's Shot window."""
    lines = compile_program(load_description(197)).splitlines()
    for line in ['director port -1', 'port 0x5AED30 0x5AED10 0x5B17F0', 'module 197 0x2260468 0x5948']:
        assert line in lines, line


def test_hyper_shot_description_compiles():
    """Hyper Shot: a port root (Ray-Bomb's kind) - its setup (by the cast's sequence mode: the opening, a shot, the closing action) and file loader the port's, run on the program's memory; three shots and the closing action recalled like the battle's Shot window."""
    lines = compile_program(load_description(198)).splitlines()
    for line in ['director port -1', 'port 0x5AA3E0 0x5AA3C0 0x5AEC90', 'module 198 0x225A908 0x5B5C']:
        assert line in lines, line


def test_cactuar_description_compiles():
    """Cactuar: a port timeline (Ray-Bomb's kind) - its setup (the model container copied into the magic buffer, the effect frame) and file loader the port's, run on the program's memory."""
    lines = compile_program(load_description(199)).splitlines()
    for line in ['director port -1', 'port 0x5A8750 0x5A8730 0x5AA3A0', 'module 199 0x2259950 0xF94']:
        assert line in lines, line


def test_no_mercy_description_compiles():
    """No Mercy: a port director (Ray-Bomb's kind) - its setup (Seifer turned to the targets) the port's (the file loader is the engine's nullsub, the texture exe data), run on the program's memory."""
    lines = compile_program(load_description(200)).splitlines()
    for line in ['director port -1', 'port 0x6391D0 0x0 0x63E680', 'module 200 0x24F7A68 0x4300']:
        assert line in lines, line


def test_burning_rave_description_compiles():
    """Burning Rave: a port root and director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its queues' pools in the magic buffer)."""
    lines = compile_program(load_description(212)).splitlines()
    for line in ['director port -1', 'port 0x6A0D20 0x6A0D30 0x6A0DC0', 'module 212 0x25101F8 0xCC']:
        assert line in lines, line


def test_my_final_heaven_description_compiles():
    """My Final Heaven: a port root and director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its queues' pools in the magic buffer)."""
    lines = compile_program(load_description(215)).splitlines()
    for line in ['director port -1', 'port 0x69AB60 0x69AB70 0x69AC00', 'module 215 0x2508938 0x74']:
        assert line in lines, line


def test_different_beat_description_compiles():
    """Different Beat: a port root and director (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its queues' pools in the magic buffer)."""
    lines = compile_program(load_description(216)).splitlines()
    for line in ['director port -1', 'port 0x6959E0 0x6959F0 0x695AB0', 'module 216 0x2508870 0xC4']:
        assert line in lines, line


def test_water_description_compiles():
    """Water: Elvoret's death's kind - a port director calling the cinematic clone's own setup (the engine's shared
    state block), its root re-pointed; its two script files the parameters."""
    lines = compile_program(load_description(222)).splitlines()
    for line in ['director port -1', 'port 0xA9B200 0xA9B1D0 0xA9B870 exe', 'module 222 0x2796E00 0x1E40']:
        assert line in lines, line


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/magic/MAG221_B.00", "extracted_files/magic/MAG221_B.01",
                     "extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat",
                     "extracted_files/battle/c0m009.dat")
def test_water_runs_from_its_description(tmp_path):
    """Water from its description: what the exe's code records; a script file of its own (an edited .00 copy)
    read by the port's file loader and the program's alike; as effect 225, itself again."""
    program = write_program(load_description(222), tmp_path / "effect.fxprog")
    original, _log = record(tmp_path, 222, "original")
    described, log = record(tmp_path, 222, "described", f"program={program}")
    assert "0 tasks, 2 params" in log and untag(described) == original and len(original) > 10000
    files = tmp_path / "files"
    files.mkdir()
    script = bytearray((MAGIC / "MAG221_B.00").read_bytes())
    for k in range(0x8000, 0x8040, 2):
        script[k] = (script[k] + 3) & 0xFF
    (files / "w222.00").write_bytes(script)
    params = tmp_path / "params.txt"
    params.write_text("files.file00 w222.00\n")
    native, _log = record(tmp_path, 222, "native", "native=1", f"params={params}", f"overrides={files}")
    described, log = record(tmp_path, 222, "described_params", f"program={program}", f"params={params}",
                            f"overrides={files}")
    assert "1 set" in log and described == native and native != original
    description = copy.deepcopy(load_description(222))
    description["effect"], description["name"] = 225, "New water"
    del description["copy"]["functions"]
    new, log = record(tmp_path, 225, "new", f"program={write_program(description, tmp_path / 'new.fxprog')}")
    assert "program: New_water" in log and untag(new) == original


def test_meteor_description_compiles():
    """Meteor: Elvoret's death's kind - a port director calling the cinematic clone's own setup (the engine's shared
    state block), its root re-pointed; its two script files the parameters."""
    lines = compile_program(load_description(223)).splitlines()
    for line in ['director port -1', 'port 0xA8F890 0xA8F860 0xA8FF00 exe', 'module 223 0x2796E00 0x1E40']:
        assert line in lines, line


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/magic/MAG222_B.00", "extracted_files/magic/MAG222_B.01",
                     "extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat",
                     "extracted_files/battle/c0m009.dat")
def test_meteor_runs_from_its_description(tmp_path):
    """Meteor from its description: what the exe's code records; a script file of its own (an edited .00 copy)
    read by the port's file loader and the program's alike; as effect 225, itself again."""
    program = write_program(load_description(223), tmp_path / "effect.fxprog")
    original, _log = record(tmp_path, 223, "original")
    described, log = record(tmp_path, 223, "described", f"program={program}")
    assert "0 tasks, 2 params" in log and untag(described) == original and len(original) > 10000
    files = tmp_path / "files"
    files.mkdir()
    script = bytearray((MAGIC / "MAG222_B.00").read_bytes())
    for k in range(0x4000, 0x4040, 2):
        script[k] = (script[k] + 3) & 0xFF
    (files / "m223.00").write_bytes(script)
    params = tmp_path / "params.txt"
    params.write_text("files.file00 m223.00\n")
    native, _log = record(tmp_path, 223, "native", "native=1", f"params={params}", f"overrides={files}")
    described, log = record(tmp_path, 223, "described_params", f"program={program}", f"params={params}",
                            f"overrides={files}")
    assert "1 set" in log and described == native and native != original
    description = copy.deepcopy(load_description(223))
    description["effect"], description["name"] = 225, "New meteor"
    del description["copy"]["functions"]
    new, log = record(tmp_path, 225, "new", f"program={write_program(description, tmp_path / 'new.fxprog')}")
    assert "program: New_meteor" in log and untag(new) == original



def test_white_wind_enemy_description_compiles():
    """White Wind (enemy): a port root and scene task (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools in the magic buffer); Adamantoise healing itself."""
    lines = compile_program(load_description(226)).splitlines()
    for line in ['director port -1', 'port 0x694520 0x694530 0x6945D0', 'module 226 0x2508770 0x84']:
        assert line in lines, line


def test_homing_laser_quistis_description_compiles():
    """Homing Laser (Quistis): Elvoret's death's kind - a port director calling the cinematic clone's own setup (the engine's shared
    state block), its root re-pointed; its two script files the parameters."""
    lines = compile_program(load_description(229)).splitlines()
    for line in ['director port -1', 'port 0xA7AA20 0xA7A9F0 0xA7B090 exe', 'module 229 0x2796E00 0x1E40']:
        assert line in lines, line


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/magic/MAG228_B.00", "extracted_files/magic/MAG228_B.01",
                     "extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat",
                     "extracted_files/battle/c0m009.dat")
def test_homing_laser_quistis_runs_from_its_description(tmp_path):
    """Homing Laser (Quistis) from its description: what the exe's code records; a script file of its own (an edited .00 copy)
    read by the port's file loader and the program's alike; as effect 225, itself again."""
    program = write_program(load_description(229), tmp_path / "effect.fxprog")
    original, _log = record(tmp_path, 229, "original")
    described, log = record(tmp_path, 229, "described", f"program={program}")
    assert "0 tasks, 2 params" in log and untag(described) == original and len(original) > 10000
    files = tmp_path / "files"
    files.mkdir()
    script = bytearray((MAGIC / "MAG228_B.00").read_bytes())
    for k in range(0x13B2, 0x13F2, 2):
        script[k] = (script[k] + 3) & 0xFF
    (files / "c229.00").write_bytes(script)
    params = tmp_path / "params.txt"
    params.write_text("files.file00 c229.00\n")
    native, _log = record(tmp_path, 229, "native", "native=1", f"params={params}", f"overrides={files}")
    described, log = record(tmp_path, 229, "described_params", f"program={program}", f"params={params}",
                            f"overrides={files}")
    assert "1 set" in log and described == native and native != original
    description = copy.deepcopy(load_description(229))
    description["effect"], description["name"] = 225, "New homing_laser_quistis"
    del description["copy"]["functions"]
    new, log = record(tmp_path, 225, "new", f"program={write_program(description, tmp_path / 'new.fxprog')}")
    assert "program: New_homing_laser_quistis" in log and untag(new) == original


def test_fire_breath_quistis_description_compiles():
    """Fire Breath (Quistis): Elvoret's death's kind - a port director calling the cinematic clone's own setup (the engine's shared
    state block), its root re-pointed; its two script files the parameters."""
    lines = compile_program(load_description(230)).splitlines()
    for line in ['director port -1', 'port 0xA70B70 0xA70B40 0xA711E0 exe', 'module 230 0x2796E00 0x1E40']:
        assert line in lines, line


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/magic/MAG229_B.00", "extracted_files/magic/MAG229_B.01",
                     "extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat",
                     "extracted_files/battle/c0m009.dat")
def test_fire_breath_quistis_runs_from_its_description(tmp_path):
    """Fire Breath (Quistis) from its description: what the exe's code records; a script file of its own (an edited .00 copy)
    read by the port's file loader and the program's alike; as effect 225, itself again."""
    program = write_program(load_description(230), tmp_path / "effect.fxprog")
    original, _log = record(tmp_path, 230, "original")
    described, log = record(tmp_path, 230, "described", f"program={program}")
    assert "0 tasks, 2 params" in log and untag(described) == original and len(original) > 10000
    files = tmp_path / "files"
    files.mkdir()
    script = bytearray((MAGIC / "MAG229_B.00").read_bytes())
    for k in range(0x2E78, 0x2EB8, 2):
        script[k] = (script[k] + 3) & 0xFF
    (files / "c230.00").write_bytes(script)
    params = tmp_path / "params.txt"
    params.write_text("files.file00 c230.00\n")
    native, _log = record(tmp_path, 230, "native", "native=1", f"params={params}", f"overrides={files}")
    described, log = record(tmp_path, 230, "described_params", f"program={program}", f"params={params}",
                            f"overrides={files}")
    assert "1 set" in log and described == native and native != original
    description = copy.deepcopy(load_description(230))
    description["effect"], description["name"] = 225, "New fire_breath_quistis"
    del description["copy"]["functions"]
    new, log = record(tmp_path, 225, "new", f"program={write_program(description, tmp_path / 'new.fxprog')}")
    assert "program: New_fire_breath_quistis" in log and untag(new) == original


def test_disease_breath_description_compiles():
    """Disease Breath: Elvoret's death's kind - a port director calling the cinematic clone's own setup (the engine's shared
    state block), its root re-pointed; its two script files the parameters."""
    lines = compile_program(load_description(231)).splitlines()
    for line in ['director port -1', 'port 0xA664A0 0xA66470 0xA66B10 exe', 'module 231 0x2796E00 0x1E40']:
        assert line in lines, line


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/magic/MAG230_B.00", "extracted_files/magic/MAG230_B.01",
                     "extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat",
                     "extracted_files/battle/c0m009.dat")
def test_disease_breath_runs_from_its_description(tmp_path):
    """Disease Breath from its description: what the exe's code records; a script file of its own (an edited .00 copy)
    read by the port's file loader and the program's alike; as effect 225, itself again."""
    program = write_program(load_description(231), tmp_path / "effect.fxprog")
    original, _log = record(tmp_path, 231, "original")
    described, log = record(tmp_path, 231, "described", f"program={program}")
    assert "0 tasks, 2 params" in log and untag(described) == original and len(original) > 10000
    files = tmp_path / "files"
    files.mkdir()
    script = bytearray((MAGIC / "MAG230_B.00").read_bytes())
    for k in range(0x121A, 0x125A, 2):
        script[k] = (script[k] + 3) & 0xFF
    (files / "c231.00").write_bytes(script)
    params = tmp_path / "params.txt"
    params.write_text("files.file00 c231.00\n")
    native, _log = record(tmp_path, 231, "native", "native=1", f"params={params}", f"overrides={files}")
    described, log = record(tmp_path, 231, "described_params", f"program={program}", f"params={params}",
                            f"overrides={files}")
    assert "1 set" in log and described == native and native != original
    description = copy.deepcopy(load_description(231))
    description["effect"], description["name"] = 225, "New disease_breath"
    del description["copy"]["functions"]
    new, log = record(tmp_path, 225, "new", f"program={write_program(description, tmp_path / 'new.fxprog')}")
    assert "program: New_disease_breath" in log and untag(new) == original


def test_breath_of_death_description_compiles():
    """Breath of Death: Elvoret's death's kind - a port director calling the cinematic clone's own setup (the engine's shared
    state block), its root re-pointed; its two script files the parameters."""
    lines = compile_program(load_description(232)).splitlines()
    for line in ['director port -1', 'port 0xA5C2E0 0xA5C2B0 0xA5C950 exe', 'module 232 0x2796E00 0x1E40']:
        assert line in lines, line


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/magic/MAG231_B.00", "extracted_files/magic/MAG231_B.01",
                     "extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat",
                     "extracted_files/battle/c0m009.dat")
def test_breath_of_death_runs_from_its_description(tmp_path):
    """Breath of Death from its description: what the exe's code records; a script file of its own (an edited .00 copy)
    read by the port's file loader and the program's alike; as effect 225, itself again."""
    program = write_program(load_description(232), tmp_path / "effect.fxprog")
    original, _log = record(tmp_path, 232, "original")
    described, log = record(tmp_path, 232, "described", f"program={program}")
    assert "0 tasks, 2 params" in log and untag(described) == original and len(original) > 10000
    files = tmp_path / "files"
    files.mkdir()
    script = bytearray((MAGIC / "MAG231_B.00").read_bytes())
    for k in range(0x20D8, 0x2118, 2):
        script[k] = (script[k] + 3) & 0xFF
    (files / "c232.00").write_bytes(script)
    params = tmp_path / "params.txt"
    params.write_text("files.file00 c232.00\n")
    native, _log = record(tmp_path, 232, "native", "native=1", f"params={params}", f"overrides={files}")
    described, log = record(tmp_path, 232, "described_params", f"program={program}", f"params={params}",
                            f"overrides={files}")
    assert "1 set" in log and described == native and native != original
    description = copy.deepcopy(load_description(232))
    description["effect"], description["name"] = 225, "New breath_of_death"
    del description["copy"]["functions"]
    new, log = record(tmp_path, 225, "new", f"program={write_program(description, tmp_path / 'new.fxprog')}")
    assert "program: New_breath_of_death" in log and untag(new) == original


def test_earthquake_armadodo_description_compiles():
    """Earthquake: Elvoret's death's kind - a port director calling the cinematic clone's own setup (the engine's shared
    state block), its root re-pointed; its two script files the parameters."""
    lines = compile_program(load_description(233)).splitlines()
    for line in ['director port -1', 'port 0xA51F40 0xA51F10 0xA525B0 exe', 'module 233 0x2796E00 0x1E40']:
        assert line in lines, line


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/magic/MAG232_B.00", "extracted_files/magic/MAG232_B.01",
                     "extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat",
                     "extracted_files/battle/c0m009.dat")
def test_earthquake_armadodo_runs_from_its_description(tmp_path):
    """Earthquake from its description: what the exe's code records; a script file of its own (an edited .00 copy)
    read by the port's file loader and the program's alike; as effect 225, itself again."""
    program = write_program(load_description(233), tmp_path / "effect.fxprog")
    original, _log = record(tmp_path, 233, "original")
    described, log = record(tmp_path, 233, "described", f"program={program}")
    assert "0 tasks, 2 params" in log and untag(described) == original and len(original) > 10000
    files = tmp_path / "files"
    files.mkdir()
    script = bytearray((MAGIC / "MAG232_B.00").read_bytes())
    for k in range(0x1000, 0x1040, 2):
        script[k] = (script[k] + 3) & 0xFF
    (files / "c233.00").write_bytes(script)
    params = tmp_path / "params.txt"
    params.write_text("files.file00 c233.00\n")
    native, _log = record(tmp_path, 233, "native", "native=1", f"params={params}", f"overrides={files}")
    described, log = record(tmp_path, 233, "described_params", f"program={program}", f"params={params}",
                            f"overrides={files}")
    assert "1 set" in log and described == native and native != original
    description = copy.deepcopy(load_description(233))
    description["effect"], description["name"] = 225, "New earthquake_armadodo"
    del description["copy"]["functions"]
    new, log = record(tmp_path, 225, "new", f"program={write_program(description, tmp_path / 'new.fxprog')}")
    assert "program: New_earthquake_armadodo" in log and untag(new) == original


def test_fart_description_compiles():
    """Fart: Elvoret's death's kind - a port director calling the cinematic clone's own setup (the engine's shared
    state block), its root re-pointed; its two script files the parameters."""
    lines = compile_program(load_description(234)).splitlines()
    for line in ['director port -1', 'port 0xA488F0 0xA488C0 0xA48F60 exe', 'module 234 0x2796E00 0x1E40']:
        assert line in lines, line


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/magic/MAG233_B.00", "extracted_files/magic/MAG233_B.01",
                     "extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat",
                     "extracted_files/battle/c0m009.dat")
def test_fart_runs_from_its_description(tmp_path):
    """Fart from its description: what the exe's code records; a script file of its own (an edited .00 copy)
    read by the port's file loader and the program's alike; as effect 225, itself again."""
    program = write_program(load_description(234), tmp_path / "effect.fxprog")
    original, _log = record(tmp_path, 234, "original")
    described, log = record(tmp_path, 234, "described", f"program={program}")
    assert "0 tasks, 2 params" in log and untag(described) == original and len(original) > 10000
    files = tmp_path / "files"
    files.mkdir()
    script = bytearray((MAGIC / "MAG233_B.00").read_bytes())
    for k in range(0x40, 0x80, 2):
        script[k] = (script[k] + 3) & 0xFF
    (files / "c234.00").write_bytes(script)
    params = tmp_path / "params.txt"
    params.write_text("files.file00 c234.00\n")
    native, _log = record(tmp_path, 234, "native", "native=1", f"params={params}", f"overrides={files}")
    described, log = record(tmp_path, 234, "described_params", f"program={program}", f"params={params}",
                            f"overrides={files}")
    assert "1 set" in log and described == native and native != original
    description = copy.deepcopy(load_description(234))
    description["effect"], description["name"] = 225, "New fart"
    del description["copy"]["functions"]
    new, log = record(tmp_path, 225, "new", f"program={write_program(description, tmp_path / 'new.fxprog')}")
    assert "program: New_fart" in log and untag(new) == original


def test_breath_blue_dragon_description_compiles():
    """Breath: Elvoret's death's kind - a port director calling the cinematic clone's own setup (the engine's shared
    state block), its root re-pointed; its two script files the parameters."""
    lines = compile_program(load_description(235)).splitlines()
    for line in ['director port -1', 'port 0xA3E370 0xA3E340 0xA3E9E0 exe', 'module 235 0x2796E00 0x1E40']:
        assert line in lines, line


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/magic/MAG234_B.00", "extracted_files/magic/MAG234_B.01",
                     "extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat",
                     "extracted_files/battle/c0m009.dat")
def test_breath_blue_dragon_runs_from_its_description(tmp_path):
    """Breath from its description: what the exe's code records; a script file of its own (an edited .00 copy)
    read by the port's file loader and the program's alike; as effect 225, itself again."""
    program = write_program(load_description(235), tmp_path / "effect.fxprog")
    original, _log = record(tmp_path, 235, "original")
    described, log = record(tmp_path, 235, "described", f"program={program}")
    assert "0 tasks, 2 params" in log and untag(described) == original and len(original) > 10000
    files = tmp_path / "files"
    files.mkdir()
    script = bytearray((MAGIC / "MAG234_B.00").read_bytes())
    for k in range(0x2560, 0x25A0, 2):
        script[k] = (script[k] + 3) & 0xFF
    (files / "c235.00").write_bytes(script)
    params = tmp_path / "params.txt"
    params.write_text("files.file00 c235.00\n")
    native, _log = record(tmp_path, 235, "native", "native=1", f"params={params}", f"overrides={files}")
    described, log = record(tmp_path, 235, "described_params", f"program={program}", f"params={params}",
                            f"overrides={files}")
    assert "1 set" in log and described == native and native != original
    description = copy.deepcopy(load_description(235))
    description["effect"], description["name"] = 225, "New breath_blue_dragon"
    del description["copy"]["functions"]
    new, log = record(tmp_path, 225, "new", f"program={write_program(description, tmp_path / 'new.fxprog')}")
    assert "program: New_breath_blue_dragon" in log and untag(new) == original


def test_ochu_dance_description_compiles():
    """Ochu Dance: Elvoret's death's kind - a port director calling the cinematic clone's own setup (the engine's shared
    state block), its root re-pointed; its two script files the parameters."""
    lines = compile_program(load_description(239)).splitlines()
    for line in ['director port -1', 'port 0xA15A30 0xA15A00 0xA160A0 exe', 'module 239 0x2796E00 0x1E40']:
        assert line in lines, line


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/magic/MAG238_B.00", "extracted_files/magic/MAG238_B.01",
                     "extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat",
                     "extracted_files/battle/c0m009.dat")
def test_ochu_dance_runs_from_its_description(tmp_path):
    """Ochu Dance from its description: what the exe's code records; a script file of its own (an edited .00 copy)
    read by the port's file loader and the program's alike; as effect 225, itself again."""
    program = write_program(load_description(239), tmp_path / "effect.fxprog")
    original, _log = record(tmp_path, 239, "original")
    described, log = record(tmp_path, 239, "described", f"program={program}")
    assert "0 tasks, 2 params" in log and untag(described) == original and len(original) > 10000
    files = tmp_path / "files"
    files.mkdir()
    script = bytearray((MAGIC / "MAG238_B.00").read_bytes())
    for k in range(0x2CE4, 0x2D24, 2):
        script[k] = (script[k] + 3) & 0xFF
    (files / "c239.00").write_bytes(script)
    params = tmp_path / "params.txt"
    params.write_text("files.file00 c239.00\n")
    native, _log = record(tmp_path, 239, "native", "native=1", f"params={params}", f"overrides={files}")
    described, log = record(tmp_path, 239, "described_params", f"program={program}", f"params={params}",
                            f"overrides={files}")
    assert "1 set" in log and described == native and native != original
    description = copy.deepcopy(load_description(239))
    description["effect"], description["name"] = 225, "New ochu_dance"
    del description["copy"]["functions"]
    new, log = record(tmp_path, 225, "new", f"program={write_program(description, tmp_path / 'new.fxprog')}")
    assert "program: New_ochu_dance" in log and untag(new) == original


def test_ochu_earthquake_description_compiles():
    """Ochu Earthquake: Elvoret's death's kind - a port director calling the cinematic clone's own setup (the engine's shared
    state block), its root re-pointed; its two script files the parameters."""
    lines = compile_program(load_description(240)).splitlines()
    for line in ['director port -1', 'port 0xA0B360 0xA0B330 0xA0B9D0 exe', 'module 240 0x2796E00 0x1E40']:
        assert line in lines, line


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/magic/MAG239_B.00", "extracted_files/magic/MAG239_B.01",
                     "extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat",
                     "extracted_files/battle/c0m009.dat")
def test_ochu_earthquake_runs_from_its_description(tmp_path):
    """Ochu Earthquake from its description: what the exe's code records; a script file of its own (an edited .00 copy)
    read by the port's file loader and the program's alike; as effect 225, itself again."""
    program = write_program(load_description(240), tmp_path / "effect.fxprog")
    original, _log = record(tmp_path, 240, "original")
    described, log = record(tmp_path, 240, "described", f"program={program}")
    assert "0 tasks, 2 params" in log and untag(described) == original and len(original) > 10000
    files = tmp_path / "files"
    files.mkdir()
    script = bytearray((MAGIC / "MAG239_B.00").read_bytes())
    for k in range(0x296A, 0x29AA, 2):
        script[k] = (script[k] + 3) & 0xFF
    (files / "c240.00").write_bytes(script)
    params = tmp_path / "params.txt"
    params.write_text("files.file00 c240.00\n")
    native, _log = record(tmp_path, 240, "native", "native=1", f"params={params}", f"overrides={files}")
    described, log = record(tmp_path, 240, "described_params", f"program={program}", f"params={params}",
                            f"overrides={files}")
    assert "1 set" in log and described == native and native != original
    description = copy.deepcopy(load_description(240))
    description["effect"], description["name"] = 225, "New ochu_earthquake"
    del description["copy"]["functions"]
    new, log = record(tmp_path, 225, "new", f"program={write_program(description, tmp_path / 'new.fxprog')}")
    assert "program: New_ochu_earthquake" in log and untag(new) == original


def test_sand_shake_description_compiles():
    """Sand Shake: Elvoret's death's kind - a port director calling the cinematic clone's own setup (the engine's shared
    state block), its root re-pointed; its two script files the parameters."""
    lines = compile_program(load_description(256)).splitlines()
    for line in ['director port -1', 'port 0x979400 0x9793D0 0x979A70 exe', 'module 256 0x2796E00 0x1E40']:
        assert line in lines, line


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/magic/MAG255_B.00", "extracted_files/magic/MAG255_B.01",
                     "extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat",
                     "extracted_files/battle/c0m009.dat")
def test_sand_shake_runs_from_its_description(tmp_path):
    """Sand Shake from its description: what the exe's code records; a script file of its own (an edited .00 copy)
    read by the port's file loader and the program's alike; as effect 225, itself again."""
    program = write_program(load_description(256), tmp_path / "effect.fxprog")
    original, _log = record(tmp_path, 256, "original")
    described, log = record(tmp_path, 256, "described", f"program={program}")
    assert "0 tasks, 2 params" in log and untag(described) == original and len(original) > 10000
    files = tmp_path / "files"
    files.mkdir()
    script = bytearray((MAGIC / "MAG255_B.00").read_bytes())
    for k in range(0x40, 0x80, 2):
        script[k] = (script[k] + 3) & 0xFF
    (files / "c256.00").write_bytes(script)
    params = tmp_path / "params.txt"
    params.write_text("files.file00 c256.00\n")
    native, _log = record(tmp_path, 256, "native", "native=1", f"params={params}", f"overrides={files}")
    described, log = record(tmp_path, 256, "described_params", f"program={program}", f"params={params}",
                            f"overrides={files}")
    assert "1 set" in log and described == native and native != original
    description = copy.deepcopy(load_description(256))
    description["effect"], description["name"] = 225, "New sand_shake"
    del description["copy"]["functions"]
    new, log = record(tmp_path, 225, "new", f"program={write_program(description, tmp_path / 'new.fxprog')}")
    assert "program: New_sand_shake" in log and untag(new) == original


def test_mad_cow_special_description_compiles():
    """Mad Cow Special: Elvoret's death's kind - a port director calling the cinematic clone's own setup (the engine's shared
    state block), its root re-pointed; its two script files the parameters."""
    lines = compile_program(load_description(258)).splitlines()
    for line in ['director port -1', 'port 0x964A00 0x9649D0 0x965070 exe', 'module 258 0x2796E00 0x1E40']:
        assert line in lines, line


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/magic/MAG257_B.00", "extracted_files/magic/MAG257_B.01",
                     "extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat",
                     "extracted_files/battle/c0m009.dat")
def test_mad_cow_special_runs_from_its_description(tmp_path):
    """Mad Cow Special from its description: what the exe's code records; a script file of its own (an edited .00 copy)
    read by the port's file loader and the program's alike; as effect 225, itself again."""
    program = write_program(load_description(258), tmp_path / "effect.fxprog")
    original, _log = record(tmp_path, 258, "original")
    described, log = record(tmp_path, 258, "described", f"program={program}")
    assert "0 tasks, 2 params" in log and untag(described) == original and len(original) > 10000
    files = tmp_path / "files"
    files.mkdir()
    script = bytearray((MAGIC / "MAG257_B.00").read_bytes())
    for k in range(0x40, 0x80, 2):
        script[k] = (script[k] + 3) & 0xFF
    (files / "c258.00").write_bytes(script)
    params = tmp_path / "params.txt"
    params.write_text("files.file00 c258.00\n")
    native, _log = record(tmp_path, 258, "native", "native=1", f"params={params}", f"overrides={files}")
    described, log = record(tmp_path, 258, "described_params", f"program={program}", f"params={params}",
                            f"overrides={files}")
    assert "1 set" in log and described == native and native != original
    description = copy.deepcopy(load_description(258))
    description["effect"], description["name"] = 225, "New mad_cow_special"
    del description["copy"]["functions"]
    new, log = record(tmp_path, 225, "new", f"program={write_program(description, tmp_path / 'new.fxprog')}")
    assert "program: New_mad_cow_special" in log and untag(new) == original


def test_desperado_description_compiles():
    """Desperado: Elvoret's death's kind - a port director calling the cinematic clone's own setup (the engine's shared
    state block), its root re-pointed; its two script files the parameters."""
    lines = compile_program(load_description(261)).splitlines()
    for line in ['director port -1', 'port 0x9598D0 0x9598A0 0x959F40 exe', 'module 261 0x2796E00 0x1E40']:
        assert line in lines, line


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/magic/MAG260_B.00", "extracted_files/magic/MAG260_B.01",
                     "extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat",
                     "extracted_files/battle/c0m009.dat")
def test_desperado_runs_from_its_description(tmp_path):
    """Desperado from its description: what the exe's code records; a script file of its own (an edited .00 copy)
    read by the port's file loader and the program's alike; as effect 225, itself again."""
    program = write_program(load_description(261), tmp_path / "effect.fxprog")
    original, _log = record(tmp_path, 261, "original")
    described, log = record(tmp_path, 261, "described", f"program={program}")
    assert "0 tasks, 2 params" in log and untag(described) == original and len(original) > 10000
    files = tmp_path / "files"
    files.mkdir()
    script = bytearray((MAGIC / "MAG260_B.00").read_bytes())
    for k in range(0x40, 0x80, 2):
        script[k] = (script[k] + 3) & 0xFF
    (files / "c261.00").write_bytes(script)
    params = tmp_path / "params.txt"
    params.write_text("files.file00 c261.00\n")
    native, _log = record(tmp_path, 261, "native", "native=1", f"params={params}", f"overrides={files}")
    described, log = record(tmp_path, 261, "described_params", f"program={program}", f"params={params}",
                            f"overrides={files}")
    assert "1 set" in log and described == native and native != original
    description = copy.deepcopy(load_description(261))
    description["effect"], description["name"] = 225, "New desperado"
    del description["copy"]["functions"]
    new, log = record(tmp_path, 225, "new", f"program={write_program(description, tmp_path / 'new.fxprog')}")
    assert "program: New_desperado" in log and untag(new) == original


def test_blood_pain_description_compiles():
    """Blood Pain: Elvoret's death's kind - a port director calling the cinematic clone's own setup (the engine's shared
    state block), its root re-pointed; its two script files the parameters."""
    lines = compile_program(load_description(262)).splitlines()
    for line in ['director port -1', 'port 0x94F9F0 0x94F9C0 0x950060 exe', 'module 262 0x2796E00 0x1E40']:
        assert line in lines, line


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/magic/MAG261_B.00", "extracted_files/magic/MAG261_B.01",
                     "extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat",
                     "extracted_files/battle/c0m009.dat")
def test_blood_pain_runs_from_its_description(tmp_path):
    """Blood Pain from its description: what the exe's code records; a script file of its own (an edited .00 copy)
    read by the port's file loader and the program's alike; as effect 225, itself again."""
    program = write_program(load_description(262), tmp_path / "effect.fxprog")
    original, _log = record(tmp_path, 262, "original")
    described, log = record(tmp_path, 262, "described", f"program={program}")
    assert "0 tasks, 2 params" in log and untag(described) == original and len(original) > 10000
    files = tmp_path / "files"
    files.mkdir()
    script = bytearray((MAGIC / "MAG261_B.00").read_bytes())
    for k in range(0x40, 0x80, 2):
        script[k] = (script[k] + 3) & 0xFF
    (files / "c262.00").write_bytes(script)
    params = tmp_path / "params.txt"
    params.write_text("files.file00 c262.00\n")
    native, _log = record(tmp_path, 262, "native", "native=1", f"params={params}", f"overrides={files}")
    described, log = record(tmp_path, 262, "described_params", f"program={program}", f"params={params}",
                            f"overrides={files}")
    assert "1 set" in log and described == native and native != original
    description = copy.deepcopy(load_description(262))
    description["effect"], description["name"] = 225, "New blood_pain"
    del description["copy"]["functions"]
    new, log = record(tmp_path, 225, "new", f"program={write_program(description, tmp_path / 'new.fxprog')}")
    assert "program: New_blood_pain" in log and untag(new) == original


def test_massive_anchor_description_compiles():
    """Massive Anchor: Elvoret's death's kind - a port director calling the cinematic clone's own setup (the engine's shared
    state block), its root re-pointed; its two script files the parameters."""
    lines = compile_program(load_description(263)).splitlines()
    for line in ['director port -1', 'port 0x945810 0x9457E0 0x945E80 exe', 'module 263 0x2796E00 0x1E40']:
        assert line in lines, line


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/magic/MAG262_B.00", "extracted_files/magic/MAG262_B.01",
                     "extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat",
                     "extracted_files/battle/c0m009.dat")
def test_massive_anchor_runs_from_its_description(tmp_path):
    """Massive Anchor from its description: what the exe's code records; a script file of its own (an edited .00 copy)
    read by the port's file loader and the program's alike; as effect 225, itself again."""
    program = write_program(load_description(263), tmp_path / "effect.fxprog")
    original, _log = record(tmp_path, 263, "original")
    described, log = record(tmp_path, 263, "described", f"program={program}")
    assert "0 tasks, 2 params" in log and untag(described) == original and len(original) > 10000
    files = tmp_path / "files"
    files.mkdir()
    script = bytearray((MAGIC / "MAG262_B.00").read_bytes())
    for k in range(0x40, 0x80, 2):
        script[k] = (script[k] + 3) & 0xFF
    (files / "c263.00").write_bytes(script)
    params = tmp_path / "params.txt"
    params.write_text("files.file00 c263.00\n")
    native, _log = record(tmp_path, 263, "native", "native=1", f"params={params}", f"overrides={files}")
    described, log = record(tmp_path, 263, "described_params", f"program={program}", f"params={params}",
                            f"overrides={files}")
    assert "1 set" in log and described == native and native != original
    description = copy.deepcopy(load_description(263))
    description["effect"], description["name"] = 225, "New massive_anchor"
    del description["copy"]["functions"]
    new, log = record(tmp_path, 225, "new", f"program={write_program(description, tmp_path / 'new.fxprog')}")
    assert "program: New_massive_anchor" in log and untag(new) == original



def test_renzokuken_6_description_compiles():
    """Renzokuken (6 hits): a port controller (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory."""
    lines = compile_program(load_description(259)).splitlines()
    for line in ['director port -1', 'port 0x5A6C20 0x5A6C00 0x5A84C0', 'module 259 0x2257798 0x21B4']:
        assert line in lines, line


def test_shockwave_pulsar_quistis_description_compiles():
    """Shockwave Pulsar (Quistis): a port root and master (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools in the magic buffer)."""
    lines = compile_program(load_description(260)).splitlines()
    for line in ['director port -1', 'port 0x690690 0x6906A0 0x690730', 'module 260 0x2508610 0xF0']:
        assert line in lines, line


def test_lv_up_description_compiles():
    """LV Up: a port root (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pool in the magic buffer)."""
    lines = compile_program(load_description(271)).splitlines()
    for line in ['director port -1', 'port 0x68F550 0x68F560 0x68F600', 'module 271 0x25085A8 0x68']:
        assert line in lines, line


def test_lv_down_description_compiles():
    """LV Down: a port root (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pool in the magic buffer)."""
    lines = compile_program(load_description(272)).splitlines()
    for line in ['director port -1', 'port 0x68DC70 0x68DC80 0x68DD20', 'module 272 0x2508540 0x68']:
        assert line in lines, line


def test_mad_rush_description_compiles():
    """Mad Rush: a port root (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools in the magic buffer)."""
    lines = compile_program(load_description(273)).splitlines()
    for line in ['director port -1', 'port 0x68D650 0x68D660 0x68D700', 'module 273 0x25084E8 0x58']:
        assert line in lines, line


def test_duel_description_compiles():
    """Duel: a port root (Ray-Bomb's kind) - its setup (by the cast's sequence mode: the cast, a move posted) and file loader the port's, run on the program's memory; Zell's model, the six moves and the end recalled like the battle's Duel actions."""
    lines = compile_program(load_description(274)).splitlines()
    for line in ['director port -1', 'port 0x6897E0 0x6897F0 0x689990', 'module 274 0x2508410 0xD8']:
        assert line in lines, line


def test_electrocute_description_compiles():
    """Electrocute: a port root (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools and points in the magic buffer)."""
    lines = compile_program(load_description(275)).splitlines()
    for line in ['director port -1', 'port 0x687B40 0x687B50 0x687C00', 'module 275 0x2508348 0xC8']:
        assert line in lines, line


def test_xatm092_death_description_compiles():
    """X-ATM092 death: a port root (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools and packet arenas in the magic buffer)."""
    lines = compile_program(load_description(276)).splitlines()
    for line in ['director port -1', 'port 0x684EE0 0x684EF0 0x684FA0', 'module 276 0x2508278 0xD0']:
        assert line in lines, line


def test_funguar_laser_description_compiles():
    """Funguar laser: a port root (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools and packet arenas in the magic buffer)."""
    lines = compile_program(load_description(277)).splitlines()
    for line in ['director port -1', 'port 0x683F10 0x683F20 0x683FC0', 'module 277 0x2508200 0x78']:
        assert line in lines, line


def test_carbuncle_description_compiles():
    """Carbuncle: a port timeline (Ray-Bomb's kind) on a shared module - its setup and file loader the port's, the exe's own helpers reading the module's words."""
    lines = compile_program(load_description(278)).splitlines()
    for line in ['director port -1', 'port 0x680C50 0x680C60 0x680DF0', 'module 278 0x2508110 0xF0']:
        assert line in lines, line


def test_full_cure_description_compiles():
    """Full-cure: a port root (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools and packet arenas in the magic buffer)."""
    lines = compile_program(load_description(280)).splitlines()
    for line in ['director port -1', 'port 0x67E730 0x67E740 0x67E7F0', 'module 280 0x2507FD8 0x98']:
        assert line in lines, line


def test_shotgun_description_compiles():
    """Shotgun: a port root (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools and packet arenas in the magic buffer)."""
    lines = compile_program(load_description(281)).splitlines()
    for line in ['director port -1', 'port 0x67DCE0 0x67DCF0 0x67DD90', 'module 281 0x2507F28 0xB0']:
        assert line in lines, line


def test_rapture_description_compiles():
    """Rapture: a port root (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools and packet arenas in the magic buffer)."""
    lines = compile_program(load_description(288)).splitlines()
    for line in ['director port -1', 'port 0x6791F0 0x679200 0x679290', 'module 288 0x2507C40 0x68']:
        assert line in lines, line


def test_brrawghh_description_compiles():
    """Brrawghh: a port root (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools and packet arenas in the magic buffer)."""
    lines = compile_program(load_description(289)).splitlines()
    for line in ['director port -1', 'port 0x6777E0 0x6777F0 0x677890', 'module 289 0x2507BD0 0x70']:
        assert line in lines, line


def test_pandemona_description_compiles():
    """Pandemona: a port timeline (Ray-Bomb's kind) on a shared module - its setup the port's (the file loader is the engine's nullsub), the exe's own helpers reading the module's words."""
    lines = compile_program(load_description(291)).splitlines()
    for line in ['director port -1', 'port 0x6ED250 0x0 0x6ED350', 'module 291 0x2556258 0xA0']:
        assert line in lines, line


def test_white_wind_quistis_description_compiles():
    """White Wind (Quistis): a port root (Ray-Bomb's kind) - its setup (her cast animation bound) and file loader the port's, run on the program's memory (its pools and packet arenas in the magic buffer)."""
    lines = compile_program(load_description(297)).splitlines()
    for line in ['director port -1', 'port 0x673000 0x673010 0x6730D0', 'module 297 0x2507908 0x80']:
        assert line in lines, line


def test_micro_missiles_quistis_description_compiles():
    """Micro Missiles (Quistis): a port root (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools and packet arenas in the magic buffer)."""
    lines = compile_program(load_description(299)).splitlines()
    for line in ['director port -1', 'port 0x66FCC0 0x66FCD0 0x66FD70', 'module 299 0x2507810 0x6C']:
        assert line in lines, line


def test_bad_breath_quistis_description_compiles():
    """Bad Breath (Quistis): a port root (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools and packet arenas in the magic buffer)."""
    lines = compile_program(load_description(300)).splitlines()
    for line in ['director port -1', 'port 0x66EF00 0x66EF10 0x66EFB0', 'module 300 0x2507758 0xB8']:
        assert line in lines, line


def test_boomerang_sword_description_compiles():
    """Boomerang Sword: a port root (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools and packet arenas in the magic buffer)."""
    lines = compile_program(load_description(304)).splitlines()
    for line in ['director port -1', 'port 0x669790 0x6697A0 0x669840', 'module 304 0x2507558 0x78']:
        assert line in lines, line


def test_gatling_gun_quistis_description_compiles():
    """Gatling Gun (Quistis): a port root (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools, particle arrays and packet arenas in the module)."""
    lines = compile_program(load_description(305)).splitlines()
    for line in ['director port -1', 'port 0x5A57D0 0x5A57B0 0x5A6BC0', 'module 305 0x2245650 0x12144']:
        assert line in lines, line


def test_degenerator_quistis_description_compiles():
    """Degenerator (Quistis): a port root (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools and particles in the module)."""
    lines = compile_program(load_description(306)).splitlines()
    for line in ['director port -1', 'port 0x5A2C90 0x5A2C70 0x5A5760', 'module 306 0x2242590 0x30BC']:
        assert line in lines, line


def test_ray_bomb_quistis_description_compiles():
    """Ray-Bomb (Quistis): a port root (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools and particles in the module)."""
    lines = compile_program(load_description(307)).splitlines()
    for line in ['director port -1', 'port 0x5A1170 0x5A1150 0x5A2B00', 'module 307 0x2240EE8 0x16A8']:
        assert line in lines, line


def test_hero_description_compiles():
    """Hero: a port root (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools and packet arenas in the magic buffer)."""
    lines = compile_program(load_description(309)).splitlines()
    for line in ['director port -1', 'port 0x666DD0 0x666DE0 0x666E70', 'module 309 0x2507480 0x4C']:
        assert line in lines, line


def test_holy_war_description_compiles():
    """Holy War: a port root (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools and packet arenas in the magic buffer)."""
    lines = compile_program(load_description(310)).splitlines()
    for line in ['director port -1', 'port 0x6664A0 0x6664B0 0x666540', 'module 310 0x2507430 0x4C']:
        assert line in lines, line


def test_gravija_description_compiles():
    """Gravija: a port root (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools and packet arenas in the magic buffer)."""
    lines = compile_program(load_description(311)).splitlines()
    for line in ['director port -1', 'port 0x6652C0 0x6652D0 0x665380', 'module 311 0x25055E0 0x1E48']:
        assert line in lines, line


def test_fake_president_death_description_compiles():
    """Fake President death: a port root (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools and particles in the module)."""
    lines = compile_program(load_description(315)).splitlines()
    for line in ['director port -1', 'port 0x598DB0 0x598D90 0x59B000', 'module 315 0x2239530 0x2130']:
        assert line in lines, line


def test_acid_quistis_description_compiles():
    """Acid (Quistis): a port root (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory (its pools and packet arenas in the magic buffer)."""
    lines = compile_program(load_description(317)).splitlines()
    for line in ['director port -1', 'port 0x65F840 0x65F850 0x65F8F0', 'module 317 0x2505490 0x90']:
        assert line in lines, line


def test_diablos_description_compiles():
    """Diablos: a port timeline (Ray-Bomb's kind) on a shared module - its setup and file loader the port's, the exe's own helpers reading the module's words."""
    lines = compile_program(load_description(325)).splitlines()
    for line in ['director port -1', 'port 0x6541E0 0x6541F0 0x654350', 'module 325 0x250517C 0xB4']:
        assert line in lines, line


def test_odin_reverse_description_compiles():
    """Odin reverse: a port timeline (Ray-Bomb's kind) on a shared module - its setup the port's (the file loader is the engine's nullsub), the exe's own helpers reading the module's words."""
    lines = compile_program(load_description(326)).splitlines()
    for line in ['director port -1', 'port 0x62A7E0 0x0 0x6326B0', 'module 326 0x24F0BD0 0x1738']:
        assert line in lines, line


def test_gilgamesh_description_compiles():
    """Gilgamesh: a port timeline (Ray-Bomb's kind) on a shared module - its setup and file loader the port's, the exe's own helpers reading the module's words."""
    lines = compile_program(load_description(327)).splitlines()
    for line in ['director port -1', 'port 0x58D760 0x58D6E0 0x596B70', 'module 327 0x21FF2A8 0x1DD8']:
        assert line in lines, line


def test_renzokuken_7_description_compiles():
    """Renzokuken (7 hits): a port controller (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory."""
    lines = compile_program(load_description(332)).splitlines()
    for line in ['director port -1', 'port 0x58B930 0x58B910 0x58D470', 'module 332 0x21FC2C0 0x2FE4']:
        assert line in lines, line


def test_renzokuken_8_description_compiles():
    """Renzokuken (8 hits): a port controller (Ray-Bomb's kind) - its setup and file loader the port's, run on the program's memory."""
    lines = compile_program(load_description(333)).splitlines()
    for line in ['director port -1', 'port 0x589BD0 0x589BB0 0x58B6A0', 'module 333 0x21FA0E8 0x21D4']:
        assert line in lines, line


def test_moomba_description_compiles():
    """Moomba: a port timeline (Ray-Bomb's kind) on a shared module - its setup the port's (the file loader is the engine's nullsub), the exe's own helpers reading the module's words."""
    lines = compile_program(load_description(338)).splitlines()
    for line in ['director port -1', 'port 0x6EBD50 0x0 0x6EBE20', 'module 338 0x25561C8 0x8C']:
        assert line in lines, line
