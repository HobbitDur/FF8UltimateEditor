"""Described GF summons (2026-11-17): Leviathan (6), Ifrit (201), Bahamut (202), Cerberus (203), Alexander (204), the
Brothers (205) and Eden (206) - the GF cinematic engine's own, Elvoret's death's description kind. Each is a port director
calling the GF's own setup (the engine's shared state block), its root re-pointed at the program's director; its two
script files the parameters (the parts it streams from the battle folder stay the game's). Squall summons it on a
monster: from its description it records what the exe's code records; an edited .00 copy is read by the port's file
loader and the program's alike; as effect 225 (a free slot, no exe function), itself again."""
import copy

import pytest

from Fujin.effectprogram import compile_program, load_description, write_program
from test_effect_program import BATTLE, MAGIC, record, untag

# effect: (name, its script files, port line, an .00 byte window (model vertices) that changes the drawing)
GFS = {
    6: ("Leviathan", "MAG005_B", "port 0xB58080 0xB58050 0xB586F0 exe", (0x2E68, 0x2EA8)),
    201: ("Ifrit", "MAG200_B", "port 0xB25780 0xB25750 0xB25DF0 exe", (0x2EF8, 0x2F38)),
    202: ("Bahamut", "MAG201_B", "port 0xB189A0 0xB18970 0xB19010 exe", (0x44DC, 0x451C)),
    203: ("Cerberus", "MAG202_B", "port 0xB0C1A0 0xB0C170 0xB0C820 exe", (0x3328, 0x3368)),
    204: ("Alexander", "MAG203_B", "port 0xAFFCA0 0xAFFC70 0xB00310 exe", (0x5420, 0x5460)),
    205: ("Brothers", "MAG204_B", "port 0xAF4520 0xAF44F0 0xAF4B90 exe", (0xD208, 0xD248)),
    206: ("Eden", "MAG205_B", "port 0xAE2DD0 0xAE2DA0 0xAE3470 exe", (0x6360, 0x63A0)),
}
MONSTER = "c0m092"
CAST = [f"slot3={BATTLE / (MONSTER + '.dat')}", "caster=0", "target=3"]
# Eden's port draws its pixel dots in PC screen units (FFNx PR 1088, Draw 53): its description records as the port with
# the game's files, not as the exe's code
SCREEN_UNITS = {206}


def files(effect):
    name = GFS[effect][1]
    return ("extracted_files/FF8_EN.exe", f"extracted_files/magic/{name}.00", f"extracted_files/magic/{name}.01",
            "extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat", f"extracted_files/battle/{MONSTER}.dat")


def summon(tmp_path, effect, tag, *extra):
    lines, log = record(tmp_path, effect, tag, *CAST, *extra)
    assert "faulted" not in log, log[-500:]
    return lines, log


@pytest.mark.parametrize("effect", list(GFS))
def test_gf_description_compiles(effect):
    """A port director calling the GF's own setup on the engine's shared state block, its root re-pointed; its two
    script files the parameters, nothing else."""
    _name, _files, port_line, _window = GFS[effect]
    d = load_description(effect)
    lines = compile_program(d).splitlines()
    for line in ("director port -1", port_line, f"module {effect} 0x2796E00 0x1E40"):
        assert line in lines, line
    assert [p["key"] for p in d["params"]] == ["files.file00", "files.file01"]


@pytest.mark.parametrize("effect", [pytest.param(effect, marks=pytest.mark.ff8data(*files(effect))) for effect in GFS])
def test_gf_runs_from_its_description(tmp_path, effect):
    """Squall summons it on a monster: from its description, what the exe's code records; a script file of its own (an
    edited .00 copy: vertices of a mesh moved) read by the port's file loader and the program's alike; as effect 225,
    itself again."""
    name, script_files, _port_line, (lo, hi) = GFS[effect]
    program = write_program(load_description(effect), tmp_path / "effect.fxprog")
    if effect in SCREEN_UNITS:
        lines, _log = summon(tmp_path, effect, "original", "native=1")
        original = untag(lines)
    else:
        original, _log = summon(tmp_path, effect, "original")
    described, log = summon(tmp_path, effect, "described", f"program={program}")
    assert "0 tasks, 2 params" in log and untag(described) == original and len(original) > 10000
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    script = bytearray((MAGIC / f"{script_files}.00").read_bytes())
    for k in range(lo, hi, 2):
        script[k] = (script[k] + 3) & 0xFF
    (files_dir / f"c{effect}.00").write_bytes(script)
    params = tmp_path / "params.txt"
    params.write_text(f"files.file00 c{effect}.00\n")
    native, _log = summon(tmp_path, effect, "native", "native=1", f"params={params}", f"overrides={files_dir}")
    described, log = summon(tmp_path, effect, "described_params", f"program={program}", f"params={params}",
                            f"overrides={files_dir}")
    assert "1 set" in log and described == native and untag(native) != original
    description = copy.deepcopy(load_description(effect))
    description["effect"], description["name"] = 225, f"New {name}"
    del description["copy"]["functions"]
    new, log = summon(tmp_path, effect, "new", f"program={write_program(description, tmp_path / 'new.fxprog')}")
    assert f"program: New_{name}" in log and untag(new) == original
