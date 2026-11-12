"""Four ported effects described (docs/fujin-effect-description.md): Gatling Gun 150 (Quistis' Gatling Gun 305's code)
and Degenerator 174 (Quistis' Degenerator 306's), described like their twins, and the Hexadragon's Breath 157 and
Melt-Eye 158, each with its parts and the numbers of its timeline. Each is a port director - the port's file loader,
setup and root run on the program's memory (its module's) - with its parameters the port's: from its description it
records what the exe's code records; with parameters, what FFNx's port records with them; as effect 225 (a free slot,
no exe function), itself again."""
import copy

import pytest

from test_effect_program import BATTLE, compile_program, load_description, record, untag, write_program

# effect: (texture, params count, params text, cast (caster, target, monster), port line, module line,
#          part keys, exe data kinds)
PORTS = {
    150: ("mag149.tim", 10, "sound 22311280\nmaster.damage 25\n",
          (3, 0, "c0m007.dat"), "port 0x60E340 0x60E320 0x60F630", "module 150 0x244FD60 0x12124",
          ["master"], {"sound": 1, "seq": 3, "model": 3, "name": 1, "camera": 1}),
    157: ("mag156.tim", 84, "sounds.start 22311280\ndirector.cloud2 36\nbreath.per_tick 5\nsplatter.spread 2000\n",
          (3, 0, "c0m024.dat"), "port 0x603E90 0x603E70 0x605460", "module 157 0x23EB5C0 0x1880",
          ["director", "swirl", "breath", "cloud", "burst", "puff", "clouds", "rings", "splatter"],
          {"sound": 2, "seq": 4, "model": 5, "name": 1, "camera": 1}),
    158: ("mag157.tim", 54, "sound 22311280\ndirector.beams 8\nbeam.end_x 3000\ndrops.per_tick 4\n",
          (3, 0, "c0m024.dat"), "port 0x602ED0 0x602EB0 0x603E30", "module 158 0x23D7B08 0x13AB8",
          ["director", "beams", "ring", "trail", "splash", "drops"],
          {"sound": 1, "seq": 3, "model": 2, "table": 1, "name": 1, "camera": 1}),
    174: ("mag173.tim", 13, "sound 22311280\n",
          (3, 0, "c0m022.dat"), "port 0x5D45A0 0x5D4580 0x5D7440", "module 174 0x2394208 0x306C",
          ["controller"], {"sound": 1, "seq": 3, "model": 5, "table": 2, "name": 1, "camera": 1}),
}


def files(effect):
    return ("extracted_files/FF8_EN.exe", "extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat",
            f"extracted_files/magic/{PORTS[effect][0]}", f"extracted_files/battle/{PORTS[effect][3][2]}")


@pytest.mark.parametrize("effect", list(PORTS))
def test_port_description_compiles(effect):
    """A port director: the port's file loader, setup and root run on the program's memory (its module's), no task of
    its own; its parts and exe data."""
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
def test_port_runs_from_its_description(tmp_path, effect):
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
    description["effect"], description["name"] = 225, "New port"
    del description["copy"]["functions"]
    new, log = record(tmp_path, 225, "new", f"program={write_program(description, tmp_path / 'new.fxprog')}", *cast)
    assert "program: New_port" in log and untag(new) == original
