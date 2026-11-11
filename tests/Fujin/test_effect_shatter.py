"""Effect 359, Reflect breaks (Cronos's OneShotReflect): the shatter director (Tools/fxhost/fxshatter.h). The game's
bounce-flash model shown whole on a fighter, then an icy burst and icy pieces flying apart, drawn by the flash's own
draw task (0x570650) from the exe's battle models - no file, no texture upload, no magic buffer, no camera, so it can
play while a spell's effect runs. Two ways in: a cast (its slot, as any new effect) and FujinEffects_PlayOnEntity,
which Cronos calls mid-spell when Reflect breaks (the battle's hit-effect queue) - recorded here with the recorder's
playon= inside a Fire cast."""
import subprocess

import pytest

from Fujin.effectprogram import compile_program, load_description, write_program
from test_effect_program import BATTLE, EXE, MAGIC, lab_recorder

FILES = ("extracted_files/FF8_EN.exe", "extracted_files/magic/mag000-049.tim", "extracted_files/battle/d0c000.dat",
         "extracted_files/battle/d0w000.dat", "extracted_files/battle/c0m009.dat")


def run(tmp_path, effect, tag, *extra):
    recorder = lab_recorder()
    out = tmp_path / f"{tag}.txt"
    done = subprocess.run([str(recorder), str(effect), f"exe={EXE}", f"magic={MAGIC}", f"battle={BATTLE}", f"out={out}",
                           f"slot0={BATTLE / 'd0c000.dat'}", f"weapon0={BATTLE / 'd0w000.dat'}",
                           f"slot3={BATTLE / 'c0m009.dat'}", "caster=0", "target=3", *extra],
                          cwd=str(recorder.parent), capture_output=True, text=True, timeout=120)
    assert done.returncode == 0 and "faulted" not in done.stdout, done.stdout[-500:]
    return out.read_text().splitlines(), done.stdout


def prims(lines):
    return [line for line in lines if line.startswith("P ")]


def test_the_shatter_compiles_to_its_director_and_its_parameters():
    lines = compile_program(load_description(359)).splitlines()
    assert "director shatter -1" in lines and "texture 0 -1" in lines and "camera 0" in lines
    for line in ("param whole.model i16 8 8", "param timing.sound i32 114 114", "param pieces.life i16 14 14",
                 "param burst.ticks i16 0 0"):
        assert line in lines, line


def tick_prims(lines):
    """Each tick's primitives (a tick's lines end with its C line)."""
    out, now = [], []
    for line in lines:
        if line.startswith("P "):
            now.append(line)
        elif line.startswith("C "):
            out.append(now)
            now = []
    return out


@pytest.mark.ff8data(*FILES)
def test_the_shatter_cast_breaks_the_whole_dome_into_its_polygons(tmp_path):
    program = write_program(load_description(359), tmp_path / "effect_359.fxprog")
    lines, log = run(tmp_path, 359, "cast", f"program={program}")
    assert "done: effect 359, 18 ticks recorded" in log   # 3 whole + 14 of shards + the last
    ticks = tick_prims(lines)
    assert len(ticks) == 18 and all(ticks[k] for k in range(17))
    # the dome's 48 polygons, whole then as shards flying apart (the fighters drawn too: about as many, other places)
    assert abs(len(ticks[2]) - len(ticks[8])) < 48 and ticks[2] != ticks[8]
    # shorter-lived shards, a burst with them
    params = tmp_path / "params.txt"
    params.write_text("pieces.life 4\nburst.ticks 2\n")
    short, log = run(tmp_path, 359, "short", f"program={program}", f"params={params}")
    assert "done: effect 359, 8 ticks recorded" in log
    assert len(tick_prims(short)[3]) > len(ticks[3])   # the burst's model with the shards


@pytest.mark.ff8data(*FILES)
def test_play_on_entity_adds_the_shatter_to_a_running_spell(tmp_path):
    host = lab_recorder().parent.parent / "fxhost" / "FujinEffects.dll"
    folder = tmp_path / "game"
    (folder / "FujinEffects").mkdir(parents=True)
    write_program(load_description(359), folder / "FujinEffects" / "effect_359.fxprog")
    fire, _log = run(tmp_path, 2, "fire", "sequences=1")
    both, log = run(tmp_path, 2, "both", "sequences=1", f"host={host}", f"hostdir={folder}", "playon=359:3:4")
    assert "tick 4: playon 359 on slot 3: 1" in log
    assert len(prims(both)) > len(prims(fire)) + 500
    # before it (ticks 0-3, each closed by its C line): Fire alone
    first = [k for k, line in enumerate(both) if line.startswith("C ")][3] + 1
    assert both[:first] == fire[:first] and both[first:] != fire[first:]
    # no program for that id, or not a shatter: 0 (the caller plays the game's flash), Fire as it is
    none, log = run(tmp_path, 2, "none", "sequences=1", f"host={host}", f"hostdir={folder}", "playon=360:3:4")
    assert "tick 4: playon 360 on slot 3: 0" in log and none == fire
