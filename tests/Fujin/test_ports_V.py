"""Described act-engine ports of agent V's batch (2026-11-12): Doom Activation (9: Stare's kind with Angelo Search's
master), Angel Wing (84: MiniMog's kind, Rinoa's limit break) and LV5 Death (345: LV?Death's library relocated, Death's
director). Each is the act family's per-action director (Doom's kind: the engine's emitter and the module's director as
state tables, the port's tasks spawned as thunks) run on the program's memory; from its description it records what the
exe's code records; with parameters, what FFNx's port records with them; as effect 225 (a free slot, no exe function),
itself again."""
import copy

import pytest

from Fujin.effectprogram import compile_program, load_description, write_program
from test_effect_program import BATTLE, record, untag

# effect: (texture, its parameter count, parameter values (decimal), the cast's recorder arguments (file names in
#          the battle folder), the files it needs)
PORTS_V = {
    9: ("mag008.tim", 22, "director.sound 22311280\nsink.speed 60\nparticles.radius 300\ndarken.level 1024\n",
        ("caster=3", "target=3", "slot3=c0m009.dat"), ("c0m009.dat",)),
    84: ("mag083.tim", 39, "angel.sound 22311280\nangel.reveal_step 64\nwings.y -2048\nglow_a.depth -1024\n",
         ("caster=0", "target=0", "slot0=d4c009.dat", "weapon0=d4w023.dat"), ("d4c009.dat", "d4w023.dat")),
    345: ("mag013-073-344.tim", 15, "reaper.fade_in 512\nstrike.length 30\nreaper.vanish_frame 14\naura.length 40\n",
          ("caster=3", "target=0", "slot3=c0m057.dat"), ("c0m057.dat",)),
}
# the lines each description compiles to: its module and exe words, its director's kind, its director task's code
LINES_V = {
    9: ["module 9 0x274EFE8 0x9510", "module_pointer 2 0x1634B7C", "release_file", "arena_size 65536", "code 0x8C0800"],
    84: ["module 84 0x25C2350 0x7C20", "module_pointer 2 0x15720A8", "module_pointer 3 0x1572BAC", "release_file",
         "arena_size 49152", "code 0x78DCE0", "act_pool particle_pool 432", "act_pool actor_pool 26880"],
    345: ["module 345 0x25570A0 0x7A20", "module_pointer 2 0x1524658", "per_target", "release_file", "arena_size 57344",
          "code 0x705FF0", "act_pool actor_pool 40320"],
}
# its parts and its exe data's kinds
PARTS_V = {
    9: (["director", "stage", "doom", "sink", "particles"],
        {"name": 1, "camera": 1, "sound": 1, "layout": 2, "seq": 1, "table": 1}),
    84: (["director", "angel", "plays", "feathers", "glows"],
         {"name": 1, "sound": 1, "tim": 1, "anim_set": 1, "layout": 3, "model": 2, "table": 1}),
    345: (["reaper", "actors"], {"name": 1, "camera": 1, "sound": 2, "tim": 2, "table": 1, "model": 1}),
}


def files(effect):
    return ("extracted_files/FF8_EN.exe", "extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat",
            f"extracted_files/magic/{PORTS_V[effect][0]}", *[f"extracted_files/battle/{name}" for name in PORTS_V[effect][4]])


def cast_of(effect):
    return [f"{arg.split('=')[0]}={BATTLE / arg.split('=')[1]}" if arg.endswith(".dat") else arg for arg in PORTS_V[effect][3]]


@pytest.mark.parametrize("effect", list(PORTS_V))
def test_v_act_description_compiles(effect):
    """The act family's per-action director (Doom's kind): the module (its memory, the exe words pointing into it), the
    engine's emitter and the module's director as state tables; its parts and exe data."""
    d = load_description(effect)
    lines = compile_program(d).splitlines()
    for line in LINES_V[effect]:
        assert line in lines, line
    parts, kinds = PARTS_V[effect]
    assert [p["key"] for p in d["parts"]] == parts
    found = {}
    for key, entry in d["exe_data"].items():
        if key != "doc":
            found[entry["kind"]] = found.get(entry["kind"], 0) + 1
    assert found == kinds
    assert len(d["params"]) == PORTS_V[effect][1]


@pytest.mark.parametrize("effect", [pytest.param(effect, marks=pytest.mark.ff8data(*files(effect))) for effect in PORTS_V])
def test_v_act_port_runs_from_its_description(tmp_path, effect):
    """From its description: what the exe's code records; with parameters, what FFNx's port records with them (and not
    the game's); as effect 225 (a free slot, no exe function), itself again."""
    _texture, count, values, _cast, _files = PORTS_V[effect]
    cast = cast_of(effect)
    description = load_description(effect)
    tasks = len(description["tasks"])
    program = write_program(description, tmp_path / "effect.fxprog")
    original, _log = record(tmp_path, effect, "original", *cast)
    described, log = record(tmp_path, effect, "described", f"program={program}", *cast)
    assert f"{tasks} tasks, {count} params" in log and untag(described) == original
    assert len(original) > 10000 and any(line.startswith("N ") for line in original)
    assert any(line.startswith("S ") for line in original)
    params = tmp_path / "params.txt"
    params.write_text(values)
    native, _log = record(tmp_path, effect, "native", "native=1", f"params={params}", *cast)
    described, log = record(tmp_path, effect, "described_params", f"program={program}", f"params={params}", *cast)
    assert f"{values.count(chr(10))} set" in log and described == native and native != original
    free = copy.deepcopy(description)
    free["effect"], free["name"] = 225, "New act"
    del free["copy"]["functions"]
    for task in free["tasks"]:
        task.pop("function", None)
    program = write_program(free, tmp_path / "new.fxprog")
    new, log = record(tmp_path, 225, "new", f"program={program}", *cast)
    assert "program: New_act" in log and untag(new) == original
