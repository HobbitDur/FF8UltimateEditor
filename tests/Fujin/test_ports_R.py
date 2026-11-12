"""Described ports of agent R's batch (2026-11-11): 1000 Needles (177) and 10,000 Needles (178) (one parameter layout),
Snipe Laser (302, Funguar laser 277's layout) and Megiddo Flame (166, 312: the shared fx_megiddo.h, one layout). Each
runs from its description as the exe's code does, with parameters as FFNx's port does, and as a free slot; its
description compiles to the port director."""
import copy

import pytest

from Fujin.effectprogram import compile_program, load_description, write_program
from test_effect_program import BATTLE, record, untag

# effect: (texture, its parameter count, parameter values (decimal), (caster slot, target slot, slot 3's monster))
PORTS_R = {
    177: ("mag176.tim", 19, "sound 22311280\ndirector.damage 40\nneedles.per_tick 10\nneedles.scale_min 2048\n", (3, 0, "c0m055.dat")),
    178: ("mag176.tim", 19, "sound 22311280\ndirector.spawn 10\nneedles.spread 800\nsparks.life 3\n", (3, 0, "c0m084.dat")),
    302: ("Mag276-301.tim", 11, "sound 22311280\n", (3, 0, "c0m008.dat")),
    166: ("mag311.tim", 40, "sounds.start 22311280\nflames.count 4\nglow.size 8192\nbolts.count 2\n", (3, 0, "c0m114.dat")),
    312: ("mag311.tim", 40, "sounds.blast 22311280\ndirector.pillar 60\nrings.size 1600\npoint.bone 0\n", (3, 0, "c0m105.dat")),
}
# the port lines each description compiles to: setup, file loader, root; the module (from, size)
PORT_LINES = {
    177: ("port 0x5CF760 0x5CF740 0x5D0090", "module 177 0x2341948 0x26C38"),
    178: ("port 0x5CEDD0 0x5CEDB0 0x5CF700", "module 178 0x231AD10 0x26C38"),
    302: ("port 0x66CA50 0x66CA60 0x66CB00", "module 302 0x2507660 0x78"),
    166: ("port 0x5E4E90 0x5E4E70 0x5E93A0", "module 166 0x23BF038 0x4240"),
    312: ("port 0x59CB90 0x59CB70 0x5A10A0", "module 312 0x223CCA0 0x4240"),
}


def files(effect):
    return ("extracted_files/FF8_EN.exe", "extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat",
            f"extracted_files/magic/{PORTS_R[effect][0]}", f"extracted_files/battle/{PORTS_R[effect][3][2]}")


@pytest.mark.parametrize("effect", [pytest.param(effect, marks=pytest.mark.ff8data(*files(effect))) for effect in PORTS_R])
def test_r_port_runs_from_its_description(tmp_path, effect):
    """Cast by its monster on the party: what the exe's code records; with parameters, what FFNx's port records with them;
    as effect 225 (a free slot, no exe function), itself again."""
    _texture, count, values, (caster, target, monster) = PORTS_R[effect]
    cast = [f"caster={caster}", f"target={target}", f"slot3={BATTLE / monster}"]
    description = load_description(effect)
    program = write_program(description, tmp_path / "effect.fxprog")
    original, _log = record(tmp_path, effect, "original", *cast)
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


@pytest.mark.parametrize("effect", list(PORTS_R))
def test_r_port_description_compiles(effect):
    """A port director: the port's file loader, setup and root run on the program's memory (its module's)."""
    description = load_description(effect)
    lines = compile_program(description).splitlines()
    for line in ("director port -1", *PORT_LINES[effect]):
        assert line in lines, line
    assert len(description["params"]) == PORTS_R[effect][1]


def test_needles_share_one_layout():
    """1000 and 10,000 Needles read the same parameters (keys, labels, parts): only the game values and addresses differ;
    the director's part, the needles (their mesh as two tables), the sparks (the flipbook, its lift table)."""
    a, b = load_description(177), load_description(178)
    assert [(p["key"], p["label"], p["part"], p["type"]) for p in a["params"]] == \
        [(p["key"], p["label"], p["part"], p["type"]) for p in b["params"]]
    assert [p["key"] for p in a["parts"]] == ["director", "needles", "sparks"]
    kinds = sorted(e["kind"] for k, e in a["exe_data"].items() if k != "doc")
    assert kinds == ["camera", "name", "seq", "sound", "table", "table", "table"]
    defaults = {p["key"]: p["default"] for p in b["params"]}
    assert defaults["director.spawn"] == 0x24 and defaults["director.damage"] == 0x55 and defaults["needles.scale_min"] == 0x480


def test_snipe_laser_reads_as_funguar_laser():
    """Snipe Laser (302) has Funguar laser's (277) parameters - the same keys, labels and kinds - and its two beams'
    points on the caster."""
    snipe, funguar = load_description(302), load_description(277)
    keys = [(p["key"], p["label"], p["type"]) for p in snipe["params"]]
    assert keys[:-1] == [(p["key"], p["label"], p["type"]) for p in funguar["params"]]
    assert keys[-1] == ("tables.beam_points", "Beam points", "data")
    assert snipe["exe_data"]["tables.beam_points"]["labels"] == ["x", "y", "z", "bone"]


def test_megiddo_flames_share_one_layout():
    """Both Megiddo Flames (fx_megiddo.h) read one parameter layout; each one's data is its own module's (312's moved by
    -0x989F0, its camera track its own), its effect point's bone its own (166: 0x25, 312: 0xA)."""
    a, b = load_description(166), load_description(312)
    assert [(p["key"], p["label"], p["part"]) for p in a["params"]] == [(p["key"], p["label"], p["part"]) for p in b["params"]]
    for key, entry in a["exe_data"].items():
        if key in ("doc", "res.camera"):
            continue
        assert int(b["exe_data"][key]["address"], 16) == int(entry["address"], 16) - 0x989F0, key
    bones = [next(p["default"] for p in d["params"] if p["key"] == "point.bone") for d in (a, b)]
    assert bones == [0x25, 0xA]
    kinds = [e["kind"] for k, e in a["exe_data"].items() if k != "doc"]
    assert kinds.count("model") == 12 and kinds.count("seq") == 1 and kinds.count("table") == 2
