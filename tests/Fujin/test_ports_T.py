"""Described ports of agent T's batch (2026-11-12): Energy Bomber (217), Ultimecia's first death (227), Evil-Eye (282) and
Magic Summon (283). Each is a port director - the port's file loader, setup and root run on the program's memory (its
module's) - with its parameters the port's: from its description it records what the exe's code records; with
parameters, what FFNx's port records with them; as effect 225 (a free slot, no exe function), itself again."""
import copy
import re

import pytest

from Fujin.effectprogram import compile_program, load_description, new_effect, write_program
from test_effect_program import BATTLE, record, untag

# effect: (texture, its parameter count, parameter values (decimal), (caster slot, target slot, slot 3's monster),
#          port line, module line, part keys, exe data kinds)
PORTS_T = {
    217: ("mag216.tim", 29, "sound 22311280\ntiming.damage 60\nball.height 3000\nsparks.per_tick 8\nburst.tick 60\n",
          (3, 0, "c0m112.dat"), "port 0x694E60 0x694E70 0x694F30", "module 217 0x25087F0 0x80",
          ["director", "ball", "trail", "burst", "sparks"],
          {"sound": 1, "layout": 2, "model": 1, "seq": 1, "name": 1, "camera": 1}),
    227: ("mag226.tim", 53, "sounds.fall 22311280\nrise.lift 600\nsparks.size 1024\nfeathers.spin_y 64\nground.z 2000\n",
          (3, 3, "c0m121.dat"), "port 0x693790 0x6937A0 0x693840", "module 227 0x2508700 0x6C",
          ["director", "rise", "burst", "ground", "sparks", "feathers"],
          {"sound": 3, "table": 4, "name": 1, "camera": 1, "layout": 3, "seq": 1, "model": 1}),
    282: ("mag281.tim", 25, "sound 22311280\neye.ticks 12\nhits.count 3\nsparks.rise 30\ntiming.end 60\n",
          (3, 0, "c0m094.dat"), "port 0x67D400 0x67D410 0x67D4C0", "module 282 0x2507E90 0x98",
          ["director", "eye", "hits", "sparks"], {"sound": 1, "name": 1, "camera": 1, "table": 1, "layout": 2, "seq": 1}),
    283: ("mag282.tim", 17, "sound 22311280\nflash.level 1024\ncircle.scroll 16\nsummon.tick 20\ntiming.end 70\n",
          (3, 0, "c0m012.dat"), "port 0x67C400 0x67C410 0x67C4B0", "module 283 0x2507E20 0x70",
          ["director", "circle", "warp", "summon"], {"sound": 1, "table": 1, "name": 1, "camera": 1, "layout": 2}),
}


def at_any_address(lines):
    """A record without the addresses of the sounds played and the flipbooks drawn (an own copy's are its own blocks)."""
    return [re.sub(r"^(S \S+|Q \S+ \S+) \S+", r"\1 -", line) for line in lines]


def files(effect):
    return ("extracted_files/FF8_EN.exe", "extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat",
            f"extracted_files/magic/{PORTS_T[effect][0]}", f"extracted_files/battle/{PORTS_T[effect][3][2]}")


@pytest.mark.parametrize("effect", list(PORTS_T))
def test_t_port_description_compiles(effect):
    """A port director: the port's file loader, setup and root run on the program's memory (its module's), no task of
    its own; its parts and exe data as its port's."""
    _texture, count, _values, _cast, port_line, module_line, parts, kinds = PORTS_T[effect]
    d = load_description(effect)
    lines = compile_program(d).splitlines()
    for line in ("director port -1", port_line, module_line):
        assert line in lines, line
    assert not any(line.startswith(("task ", "pool ")) for line in lines)
    assert len(d["params"]) == count
    assert [p["key"] for p in d["parts"]] == parts
    found = {}
    for key, entry in d["exe_data"].items():
        if key != "doc":
            found[entry["kind"]] = found.get(entry["kind"], 0) + 1
    assert found == kinds
    for p in d["params"]:     # every data parameter names its exe data
        if p["type"] in ("sound", "seq", "layout", "model", "data", "camera", "name"):
            assert p["default"] == "@" + p["key"] and p["key"] in d["exe_data"], p["key"]


@pytest.mark.parametrize("effect", [pytest.param(effect, marks=pytest.mark.ff8data(*files(effect))) for effect in PORTS_T])
def test_t_port_runs_from_its_description(tmp_path, effect):
    """Cast by its monster on Squall: what the exe's code records; with parameters, what FFNx's port records with them
    (and not the game's); as effect 225 (a free slot, no exe function), itself again; as an own copy (224, its data its
    own), itself again (its sounds and flipbooks read from its own blocks)."""
    _texture, count, values, (caster, target, monster), *_rest = PORTS_T[effect]
    cast = [f"caster={caster}", f"target={target}", f"slot3={BATTLE / monster}"]
    description = load_description(effect)
    program = write_program(description, tmp_path / "effect.fxprog")
    original, _log = record(tmp_path, effect, "original", *cast)
    described, log = record(tmp_path, effect, "described", f"program={program}", *cast)
    assert f"0 tasks, {count} params" in log and untag(described) == original
    assert len(original) > 10000 and any(line.startswith("S ") for line in original)
    params = tmp_path / "params.txt"
    params.write_text(values)
    native, _log = record(tmp_path, effect, "native", "native=1", f"params={params}", *cast)
    described, log = record(tmp_path, effect, "described_params", f"program={program}", f"params={params}", *cast)
    assert f"{values.count(chr(10))} set" in log and described == native and native != original
    free = copy.deepcopy(description)
    free["effect"], free["name"] = 225, "New T"
    del free["copy"]["functions"]
    new, log = record(tmp_path, 225, "new", f"program={write_program(free, tmp_path / 'new.fxprog')}", *cast)
    assert "program: New_T" in log and untag(new) == original
    exe = (BATTLE.parent / "FF8_EN.exe").read_bytes()
    own = new_effect(description, 224, "Own T", exe)
    copied, log = record(tmp_path, 224, "own", f"program={write_program(own, tmp_path / 'own.fxprog')}", *cast)
    assert at_any_address(untag(copied)) == at_any_address(original)


def test_energy_bomber_reads_its_ball_and_sparks():
    """Energy Bomber's ball (its bone, lift, throw and hop ticks, the hop's height and spread) and its sparks are
    parameters with the game's values; the trail's fade is not one (its draw mode never reads it)."""
    d = load_description(217)
    defaults = {p["key"]: p["default"] for p in d["params"]}
    assert (defaults["ball.bone"], defaults["ball.throw_tick"], defaults["ball.hop_tick"]) == (0x27, 0x2F, 0x37)
    assert (defaults["timing.damage"], defaults["timing.end"]) == (0x4E, 0x56)
    assert (defaults["sparks.per_tick"], defaults["sparks.life"]) == (16, 12)
    assert not any(k.startswith("trail.") for k in defaults)
    assert d["exe_data"]["seqs.spark"]["frames"] == 12
    assert d["exe_data"]["layouts.ball"]["capacity"] == 0x398


def test_ultimecia_reads_her_lines_and_points():
    """Ultimecia's first death: her four lines' ticks, the three layouts' ticks, and her model's points as tables of
    (x, y, z, bone) - the spark tables keep their lengths (96, 96, 119 points)."""
    d = load_description(227)
    defaults = {p["key"]: p["default"] for p in d["params"]}
    assert [defaults[f"lines.{k}"] for k in ("first", "second", "third", "fourth")] == [0x26, 0x55, 0x73, 0xA5]
    assert (defaults["rise.tick"], defaults["burst.tick"], defaults["ground.tick"], defaults["timing.end"]) == \
        (0xD4, 0x104, 0x10C, 0x11C)
    sizes = {k: e["size"] for k, e in d["exe_data"].items() if k != "doc" and e["kind"] == "table"}
    assert sizes == {"tables.caster_point": 8, "tables.points_a": 0x300, "tables.points_b": 0x300, "tables.points_c": 0x3B8}
    assert all(d["exe_data"][k]["labels"] == ["x", "y", "z", "bone"] for k in sizes)


def test_evil_eye_reads_its_eye_point_and_hits():
    """Evil-Eye's eye point on the caster is a table (x, y, z, bone: bone 13); its hits spawn a spark every 4 frames
    under 28 left; its loader reads mag281.tim."""
    d = load_description(282)
    defaults = {p["key"]: p["default"] for p in d["params"]}
    assert (defaults["hits.until"], defaults["hits.every"], defaults["hits.count"]) == (0x1C, 4, 1)
    assert (defaults["eye.tick"], defaults["eye.ticks"], defaults["timing.end"]) == (2, 0x1A, 0x31)
    assert d["exe_data"]["tables.eye"]["size"] == 8 and d["exe_data"]["tables.eye"]["labels"] == ["x", "y", "z", "bone"]
    assert d["exe_data"]["layouts.eye"]["capacity"] == 0x548 and d["exe_data"]["layouts.hit"]["capacity"] == 0x180


def test_magic_summon_reads_its_flash_colours_and_lists_its_warp_tables():
    """Magic Summon's flash colours are a table (8 x red, green, blue, -); the warp's weight and distance tables stay
    code: listed as not editable."""
    d = load_description(283)
    colours = d["exe_data"]["tables.flash_colours"]
    assert (colours["size"], colours["format"], colours["columns"]) == (32, "B", 4)
    defaults = {p["key"]: p["default"] for p in d["params"]}
    assert (defaults["summon.tick"], defaults["summon.ticks"], defaults["timing.end"]) == (0x18, 0x24, 0x3C)
    assert [row["address"] for row in d["not_editable"]] == ["0x10996AC", "0x109AAAC"]
