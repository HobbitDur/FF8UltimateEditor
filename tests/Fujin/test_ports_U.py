"""Described ports of agent U's batch (2026-11-12): Mega Spark (279), Thunder Summon (285), Mini Pulse Cannon (286), Mega
Pulse Cannon (287: Mega Spark's arcs and Mini Pulse Cannon's charge sparks in one module, their keys shared) and Final
Battle Music (344: Griever's cue script, it draws nothing). Each runs from its description as the exe's code does, with
parameters as FFNx's port does, and as a free slot; its description compiles to the port director."""
import copy

import pytest

from Fujin.effectprogram import compile_program, load_description, write_program
from test_effect_program import BATTLE, record, untag

# effect: (its file in the magic folder (None: no file), its parameter count, parameter values (decimal), (caster slot,
# target slot, slot 3's monster))
PORTS_U = {
    279: ("mag278.tim", 102, "sound 22311280\ndirector.damage 50\nbolts.count 8\narcs.every 2\n", (3, 0, "c0m030.dat")),
    285: ("mag284.tim", 89, "sounds.start 22311280\ndirector.damage 100\nsparks.burst 2\nbolt.depth -64\n", (3, 0, "c0m133.dat")),
    286: ("mag285.tim", 38, "sound 22311280\ndirector.damage 40\ncharge.count 4\nbeam.depth -64\n", (3, 0, "c0m110.dat")),
    287: (None, 84, "sound 22311280\ndirector.damage 50\nrocks.every 4\ncharge.count 2\n", (3, 0, "c0m109.dat")),
}
# the port lines each description compiles to: setup, file loader (0x0: none), root; the module (from, size)
PORT_LINES = {
    279: ("port 0x67EFD0 0x67EFE0 0x67F090", "module 279 0x2508070 0xA0"),
    285: ("port 0x67A860 0x67A870 0x67A900", "module 285 0x2507D08 0xA4"),
    286: ("port 0x679E10 0x679E20 0x679EC0", "module 286 0x2507CA8 0x5C"),
    287: ("port 0x6F2E80 0x0 0x6F2F20", "module 287 0x25562F8 0x8C"),
    344: ("port 0x62A650 0x0 0x62A7A0", "module 344 0x24DFD70 0x10E5C"),
}
GRIEVER = (3, 0, "c0m122.dat")
# Thunder Summon moves the battle camera words itself: its bolt is in view only with the game's camera (as Fujin plays it)
EXTRA = {285: ["gamecamera=1"]}
# Mega Spark: the exe's own run is no reference in the recorder (its bolt ribbons read never-written stack words - the
# executor's residues the port models - and it faults at tick 45): FFNx's port with the game's values is


def files(effect):
    texture, monster = PORTS_U[effect][0], PORTS_U[effect][3][2]
    return ("extracted_files/FF8_EN.exe", "extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat",
            f"extracted_files/battle/{monster}") + ((f"extracted_files/magic/{texture}",) if texture else ())


def cast_of(caster, target, monster):
    return [f"caster={caster}", f"target={target}", f"slot3={BATTLE / monster}"]


@pytest.mark.parametrize("effect", [pytest.param(effect, marks=pytest.mark.ff8data(*files(effect))) for effect in PORTS_U])
def test_u_port_runs_from_its_description(tmp_path, effect):
    """Cast by its monster on the party: what the exe's code records; with parameters, what FFNx's port records with them;
    as effect 225 (a free slot, no exe function), itself again."""
    _texture, count, values, who = PORTS_U[effect]
    cast = cast_of(*who) + EXTRA.get(effect, [])
    description = load_description(effect)
    program = write_program(description, tmp_path / "effect.fxprog")
    original, _log = record(tmp_path, effect, "original", *cast, *(["native=1"] if effect == 279 else []))
    if effect == 279:
        original = untag(original)
    described, log = record(tmp_path, effect, "described", f"program={program}", *cast)
    assert f"0 tasks, {count} params" in log and untag(described) == original
    assert len(original) > 10000 and any(line.startswith("N ") for line in original)
    assert any(line.startswith("S ") for line in original)
    params = tmp_path / "params.txt"
    params.write_text(values)
    native, _log = record(tmp_path, effect, "native", "native=1", f"params={params}", *cast)
    described, log = record(tmp_path, effect, "described_params", f"program={program}", f"params={params}", *cast)
    assert f"{values.count(chr(10))} set" in log and described == native and native != original
    free = copy.deepcopy(description)
    free["effect"], free["name"] = 225, "New cycle"
    del free["copy"]["functions"]
    program = write_program(free, tmp_path / "new.fxprog")
    new, log = record(tmp_path, 225, "new", f"program={program}", *cast)
    assert "program: New_cycle" in log and untag(new) == original


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat",
                     "extracted_files/battle/c0m122.dat")
def test_final_battle_music_runs_its_cues_from_its_description(tmp_path):
    """Final Battle Music (344) draws nothing: its cue task's damage, camera track and end as the exe's; a damage tick moved
    moves the damage; as effect 225 (a free slot) itself again."""
    cast = cast_of(*GRIEVER)
    description = load_description(344)
    program = write_program(description, tmp_path / "effect.fxprog")
    original, _log = record(tmp_path, 344, "original", *cast)
    described, log = record(tmp_path, 344, "described", f"program={program}", *cast)
    assert "0 tasks, 14 params" in log and untag(described) == original
    assert [line for line in original if line.startswith(("N ", "K "))] == ["K 32 520 99BB14E7", "N 34 0 0 0 0"]
    params = tmp_path / "params.txt"
    params.write_text("cues.damage 20\ncues.end 40\n")
    native, _log = record(tmp_path, 344, "native", "native=1", f"params={params}", *cast)
    described, log = record(tmp_path, 344, "described_params", f"program={program}", f"params={params}", *cast)
    assert "2 set" in log and described == native and "N 20 0 0 0 0" in native and "N 34 0 0 0 0" not in native
    free = copy.deepcopy(description)
    free["effect"], free["name"] = 225, "New cycle"
    del free["copy"]["functions"]
    program = write_program(free, tmp_path / "new.fxprog")
    new, log = record(tmp_path, 225, "new", f"program={program}", *cast)
    assert "program: New_cycle" in log and untag(new) == original


@pytest.mark.parametrize("effect", list(PORT_LINES))
def test_u_port_description_compiles(effect):
    """A port director: the port's file loader, setup and root run on the program's memory (its module's)."""
    description = load_description(effect)
    lines = compile_program(description).splitlines()
    for line in ("director port -1", *PORT_LINES[effect]):
        assert line in lines, line
    assert len(description["params"]) == (PORTS_U[effect][1] if effect in PORTS_U else 14)


def _rows(description, prefixes):
    return [(p["key"], p["label"], p["type"]) for p in description["params"] if p["key"].startswith(prefixes)]


def test_mega_pulse_cannon_arcs_read_as_mega_sparks():
    """Mega Pulse Cannon (287) draws Mega Spark's (279) arcs: their brightness, fade, width and ribbon texture read the same
    in both (their own timing aside), each with its own triangle rows on its caster."""
    spark, pulse = load_description(279), load_description(287)
    shared = ("arcs.bright", "arcs.fade", "arcs.width", "ribbon.", "tables.triangles")
    assert _rows(spark, shared) == _rows(pulse, shared) and len(_rows(spark, shared)) == 13
    assert spark["exe_data"]["tables.triangles"]["size"] == 24 * 24 and pulse["exe_data"]["tables.triangles"]["size"] == 13 * 24
    assert spark["exe_data"]["tables.triangles"]["labels"][3::4] == ["bone0", "bone1", "bone2"]
    clut = {d["effect"]: next(p["default"] for p in d["params"] if p["key"] == "ribbon.clut") for d in (spark, pulse)}
    assert clut == {279: 0x3D94, 287: 0x3E14}


def test_mega_pulse_cannon_charge_reads_as_mini_pulse_cannons():
    """Mini Pulse Cannon (286) and Mega Pulse Cannon (287) both draw charge sparks round their muzzle: one set of keys,
    labels and kinds; their counts, lives and spreads their own."""
    mini, mega = load_description(286), load_description(287)
    keys = ("charge.", "seqs.charge", "tables.muzzle")
    assert _rows(mini, keys) == _rows(mega, keys) and len(_rows(mini, keys)) == 15
    defaults = {d["effect"]: {p["key"]: p["default"] for p in d["params"]} for d in (mini, mega)}
    assert (defaults[286]["charge.count"], defaults[286]["charge.life"]) == (2, 10)
    assert (defaults[287]["charge.count"], defaults[287]["charge.life"]) == (4, 14)


def test_final_battle_music_keeps_its_music_block_not_editable():
    """Final Battle Music (344): its parameters are its cue ticks, the music commands' values, the caster's chain
    transformation and its camera track; the music block it hands the fanfare player is listed, not editable."""
    description = load_description(344)
    assert [p["part"] for p in description["params"]] == ["cues"] * 14
    assert [key for key in description["exe_data"] if key != "doc"] == ["res.camera"]
    row, = description["not_editable"]
    assert row["address"] == "0xDEE388" and row["key"] == "not_editable.final_battle_music"
    assert "file_loader" not in description["copy"]["functions"]
