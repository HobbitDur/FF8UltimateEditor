"""Four ported effects described like their described twins (docs/fujin-effect-description.md): Storm Breath (Elnoyle)
213 (Storm Breath 11's code), Ray-Bomb (GIM52A) 313 (Ray-Bomb 10's), Micro Missiles 284 (Micro Missiles 299's) and
Kamikaze 181 (Suicide 180's). Each is a port director - the port's file loader, setup and root run on the program's
memory (its module's) - with its parameters the port's: from its description it records what the exe's code records;
with parameters, what FFNx's port records with them; as effect 225 (a free slot, no exe function), itself again."""
import copy

import pytest

from test_effect_program import BATTLE, compile_program, load_description, record, untag, write_program

# effect: (texture, params count, params text, cast (caster, target, monster), port line, module line,
#          part keys, exe data kinds)
PORTS = {
    213: ("mag212.tim", 43, "stream.ticks 40\nhits.scale 2048\nrings.every 3\ntiming.end 70\nstart.tick 3\n",
          (3, 0, "c0m131.dat"), "port 0x69EAC0 0x69EAD0 0x69EB70", "module 213 0x2510170 0x88",
          ["timing", "stream", "sparks", "mist"], {"sound": 2, "layout": 2, "seq": 4, "model": 3, "name": 1, "camera": 1}),
    313: ("mag312.tim", 57, "beam.turn 512\ndust.count 2\npuffs.first 101\nring.tick 125\ncharge.count 4\n",
          (3, 0, "c0m001.dat"), "port 0x59B0D0 0x59B0B0 0x59CA20", "module 313 0x223B668 0x1638",
          ["timing", "charge", "flash", "beam", "blast", "bounce"],
          {"sound": 1, "seq": 4, "model": 3, "name": 1, "camera": 1, "table": 6}),
    284: ("mag283-298.tim", 15, "sound 22311280\nlaunch.ticks 24\nlaunch.height 600\n",
          (3, 0, "c0m001.dat"), "port 0x67B7A0 0x67B7B0 0x67B850", "module 284 0x2507DB0 0x6C",
          ["master"], {"sound": 1, "layout": 3, "seq": 3, "name": 1, "camera": 1}),
    181: ("mag180.tim", 14, "sound 22311280\ndirector.damage 30\nflares.count 8\n",
          (0, 3, "c0m009.dat"), "port 0x5CB550 0x5CB530 0x5CC7D0", "module 181 0x23065D8 0x17BC",
          ["director"], {"sound": 1, "seq": 3, "model": 2, "name": 1, "camera": 1}),
}


def files(effect):
    return ("extracted_files/FF8_EN.exe", "extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat",
            f"extracted_files/magic/{PORTS[effect][0]}", f"extracted_files/battle/{PORTS[effect][3][2]}")


@pytest.mark.parametrize("effect", list(PORTS))
def test_twin_port_description_compiles(effect):
    """A port director: the port's file loader, setup and root run on the program's memory (its module's), no task of
    its own; its parts and exe data its twin's shape."""
    _texture, _count, _values, _cast, port_line, module_line, parts, kinds = PORTS[effect]
    d = load_description(effect)
    lines = compile_program(d).splitlines()
    for line in ("director port -1", port_line, module_line):
        assert line in lines, line
    assert not any(line.startswith(("task ", "pool ")) for line in lines)
    assert [p["key"] for p in d["parts"]] == parts
    found = {}
    for key, entry in d["exe_data"].items():
        if key != "doc":
            found[entry["kind"]] = found.get(entry["kind"], 0) + 1
    assert found == kinds


@pytest.mark.parametrize("effect", [pytest.param(effect, marks=pytest.mark.ff8data(*files(effect))) for effect in PORTS])
def test_twin_port_runs_from_its_description(tmp_path, effect):
    """From its description: what the exe's code records; with parameters, what FFNx's port records with them (and
    not the game's); as effect 225 (a free slot, no exe function), itself again."""
    _texture, count, values, (caster, target, monster), *_rest = PORTS[effect]
    cast = [f"caster={caster}", f"target={target}", f"slot3={BATTLE / monster}"]
    program = write_program(load_description(effect), tmp_path / "effect.fxprog")
    original, _log = record(tmp_path, effect, "original", *cast)
    described, log = record(tmp_path, effect, "described", f"program={program}", *cast)
    assert f"0 tasks, {count} params" in log and untag(described) == original
    assert len(original) > 10000 and any(line.startswith("S ") for line in original)
    params = tmp_path / "params.txt"
    params.write_text(values)
    native, _log = record(tmp_path, effect, "native", "native=1", f"params={params}", *cast)
    described, log = record(tmp_path, effect, "described_params", f"program={program}", f"params={params}", *cast)
    assert f"{values.count(chr(10))} set" in log and described == native and native != original
    description = copy.deepcopy(load_description(effect))
    description["effect"], description["name"] = 225, "New twin"
    del description["copy"]["functions"]
    new, log = record(tmp_path, 225, "new", f"program={write_program(description, tmp_path / 'new.fxprog')}", *cast)
    assert "program: New_twin" in log and untag(new) == original
