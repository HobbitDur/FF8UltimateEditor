"""Effects run from their descriptions (docs/fujin-effect-description.md): Fujin compiles a description
(FF8GameData/Resources/json/effects/effect_NNN.json) into a program (Fujin/effectprogram.py) the
recorder runs (program=<file>, Tools/fxhost/fxprogram.h) - Cure, Potion and Hypnotize exactly as the
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
