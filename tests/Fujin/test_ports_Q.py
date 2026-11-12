"""The boss Renzokuken family (334 Bahamut, 335 NORG, 336 Ultima Weapon, 337 the Sorceress, 339 Adel, 340 Ultimecia,
341 Jumbo Cactuar, 342 Ultimecia and Griever, 343 Griever) from their descriptions: one port each (FFNx
mag33N_renzokuken_*.cpp with the family's renzo_boss.inc, one RenzoBossParams layout), its file loader, setup and master
run on the program's memory. Squall casts it on his boss (slot 3; Adel's Rinoa in slot 4), the battle's sequences run
(sequences=1: the hits are his sequence's). What the exe's code records; with parameters, what FFNx's port records with
them; as effect 225 (a free slot, no exe function), itself again; as a copy with its own data (224), the same draws."""
import copy
import re

import pytest

from test_effect_program import BATTLE, EXE, record, untag
from Fujin.effectprogram import compile_program, load_description, new_effect, write_program

# effect: (the boss in slot 3, more monsters by slot, setup, file loader, root, module from, module size, own data entries)
BOSSES = {
    334: ("c0m067.dat", {}, "0x587790", "0x587770", "0x589940", "0x21F7250", "0x2E78"),
    335: ("c0m077.dat", {}, "0x5856B0", "0x585690", "0x587500", "0x21F4418", "0x2E34"),
    336: ("c0m090.dat", {}, "0x583040", "0x583020", "0x585420", "0x21F15E0", "0x2E34"),
    337: ("c0m117.dat", {}, "0x580990", "0x580970", "0x582DB0", "0x21EE748", "0x2E78"),
    339: ("c0m112.dat", {4: "c0m113.dat"}, "0x57E5D0", "0x57E5B0", "0x580700", "0x21EB8B0", "0x2E78"),
    340: ("c0m126.dat", {}, "0x57BC00", "0x57BBE0", "0x57E340", "0x21E8A78", "0x2E34"),
    341: ("c0m084.dat", {}, "0x579A80", "0x579A60", "0x57B970", "0x21E5BE0", "0x2E78"),
    342: ("c0m124.dat", {}, "0x5776D0", "0x5776B0", "0x5797F0", "0x21E2DA8", "0x2E34"),
    343: ("c0m122.dat", {}, "0x575650", "0x575630", "0x577440", "0x21DFEF0", "0x2E98"),
}
# the module's own models and whether its hit offsets are exe data (the others: a zero table in the module)
OWN = {334: (["ring", "turned", "caster"], False), 335: (["ring"], True), 336: (["caster_a", "caster_b", "ground"], True),
       337: (["caster", "ring", "ground"], False), 339: (["ring_a", "ring_b"], False),
       340: (["ring_a", "ring_b", "caster", "turned"], True), 341: (["ring"], False), 342: (["facing"], True),
       343: (["final"], False)}


def files(effect):
    boss, more = BOSSES[effect][:2]
    return ("extracted_files/FF8_EN.exe", "extracted_files/magic/mag333.tim", "extracted_files/battle/d0c000.dat",
            "extracted_files/battle/d0w000.dat", f"extracted_files/battle/{boss}",
            *[f"extracted_files/battle/{name}" for name in more.values()])


def cast(effect):
    boss, more = BOSSES[effect][:2]
    return ["caster=0", "target=3", f"slot3={BATTLE / boss}", *[f"slot{k}={BATTLE / name}" for k, name in more.items()],
            "sequences=1"]


@pytest.mark.parametrize("effect", list(BOSSES))
def test_boss_renzokuken_description_compiles(effect):
    """A port controller (Ray-Bomb's kind): its file loader, setup and master the port's, on its module's memory; one
    part (the controller); its data the shared layout's - the sound, the flash / debris / spark flipbooks (and the
    emitters' one), the sparkle / slash / streak meshes and the module's own, the texture, the camera track, the
    animation sets, the hit leads (and offsets when they are exe data), the finisher sparkles' fade and depth tables."""
    d = load_description(effect)
    _boss, _more, setup, loader, root, start, size = BOSSES[effect]
    lines = compile_program(d).splitlines()
    for line in ["director port -1", f"port {setup} {loader} {root}", f"module {effect} {start} {size}"]:
        assert line in lines, line
    assert [p["key"] for p in d["parts"]] == ["controller"]
    own, offs = OWN[effect]
    keys = [p["key"] for p in d["params"]]
    assert keys[:4] == ["sound", "seqs.flash", "seqs.debris", "seqs.spark"]
    assert [k for k in keys if k.startswith("models.")] == ["models.sparkle", "models.slash", "models.streak",
                                                            *[f"models.{k}" for k in own]]
    assert ("tables.hit_offs" in keys) == offs and ("seqs.emit" in keys) == (effect != 341)
    assert d["exe_data"]["res.anim_sets"]["count"] == (3 if effect == 339 else 2)
    assert all(p["default"] == "@" + p["key"] for p in d["params"])


@pytest.mark.parametrize("effect", [pytest.param(effect, marks=pytest.mark.ff8data(*files(effect))) for effect in BOSSES])
def test_boss_renzokuken_runs_from_its_description(tmp_path, effect):
    stage = cast(effect)
    description = load_description(effect)
    program = write_program(description, tmp_path / "effect.fxprog")
    original, _log = record(tmp_path, effect, "original", *stage)
    described, log = record(tmp_path, effect, "described", f"program={program}", *stage)
    assert f"0 tasks, {len(description['params'])} params" in log and untag(described) == untag(original)
    assert len(original) > 10000 and any(line.startswith("S ") for line in original)
    # with parameters: the program as the port (the sound and a flipbook of another effect's: drawn otherwise)
    params = tmp_path / "params.txt"
    params.write_text("sound 22311280\nseqs.flash 13342192\n")
    native, _log = record(tmp_path, effect, "native", "native=1", f"params={params}", *stage)
    described, log = record(tmp_path, effect, "described_params", f"program={program}", f"params={params}", *stage)
    assert "2 set" in log and described == native and native != original
    # a free slot, no exe function
    free = copy.deepcopy(description)
    free["effect"], free["name"] = 225, "New boss Renzokuken"
    del free["copy"]["functions"]
    new, log = record(tmp_path, 225, "new", f"program={write_program(free, tmp_path / 'new.fxprog')}", *stage)
    assert "program: New_boss_Renzokuken" in log and untag(new) == untag(original)


@pytest.mark.parametrize("effect", [pytest.param(effect, marks=pytest.mark.ff8data(*files(effect))) for effect in BOSSES])
def test_boss_renzokuken_own_copy_draws_as_the_exe(tmp_path, effect):
    """As a new effect with its own copy of the exe's data (224): every data parameter its own block, the same draws (the
    data's addresses aside). Adel's and Ultimecia's boss sequence starts before its set is bound (their controller's tick 1):
    a copy of the boss's set - its own block, or an .animset file bound by the recorder - plays otherwise from about tick
    40, so their animation sets stay the exe's here."""
    stage = cast(effect)
    description = load_description(effect)
    own = new_effect(description, 224, "Own", EXE.read_bytes())
    assert sum(isinstance(e, dict) for e in own["data"].values()) == len(description["params"])
    extra = []
    if effect in (339, 340):
        params = tmp_path / "params.txt"
        params.write_text(f"res.anim_sets {int(description['exe_data']['res.anim_sets']['address'], 16)}\n")
        extra.append(f"params={params}")
    original, _log = record(tmp_path, effect, "original", *stage)
    copied, _log = record(tmp_path, 224, "own", f"program={write_program(own, tmp_path / 'own.fxprog')}", *extra, *stage)
    nodata = lambda lines: [re.sub(r"^(S \d+|Q \d+ \d+) [0-9A-F]+ ", r"\1 - ", line) for line in untag(lines)]
    assert nodata(copied) == nodata(original)
