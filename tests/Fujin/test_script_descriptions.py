"""Every cinematic effect whose description has a "script" (its MAG script's values part by part, Fujin/scriptparts.py):
the game's file holds each value where the description says, and each value is written there and nowhere else."""
import json
from pathlib import Path

import pytest

from FF8GameData.magcine.cinescript import CineOpcodeTable, CineProgram
from Fujin.effectprogram import DESCRIPTIONS
from Fujin.scriptparts import apply_script_values, edits, read_value, script_matches, script_values

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = {}
for _path in sorted(DESCRIPTIONS.glob("effect_*.json")):
    _script = json.loads(_path.read_text(encoding="utf-8")).get("script")
    if _script:
        SCRIPTS[int(_path.stem.split("_")[1])] = _script
CASES = [pytest.param(effect, marks=pytest.mark.ff8data(f"extracted_files/magic/{script['file'].upper()}"), id=f"effect{effect}")
         for effect, script in SCRIPTS.items()]


def _file(script):
    return (ROOT / "extracted_files" / "magic" / script["file"].upper()).read_bytes()


@pytest.mark.parametrize("effect", CASES)
def test_every_value_is_the_one_the_game_has(effect):
    script = SCRIPTS[effect]
    data = _file(script)
    assert script_matches(script, data)
    assert script_values(script, data) == {field["key"]: field["default"] for field in script["fields"]}
    assert {field["part"] for field in script["fields"]} <= {part["key"] for part in script["parts"]}
    assert len({field["key"] for field in script["fields"]}) == len(script["fields"])
    assert len({part["key"] for part in script["parts"]}) == len(script["parts"])
    assert {group["key"] for group in script.get("groups", [])} <= {field["key"].rsplit(".", 1)[0] for field in script["fields"]}


@pytest.mark.parametrize("effect", CASES)
def test_a_value_is_written_where_it_is_read_and_nowhere_else(effect):
    script = SCRIPTS[effect]
    data = _file(script)
    for field in script["fields"]:
        for value in {field["min"], field["max"], field["default"]}:
            edited = apply_script_values(script, data, {field["key"]: value})
            assert read_value(field, edited) == value, field["key"]
            assert len(edited) == len(data) and script_matches(script, edited), field["key"]
            changed = {at for at in range(len(data)) if edited[at] != data[at]}
            allowed = {at + index for at, raw in edits(field, value, data) for index in range(len(raw))}
            assert changed <= allowed, field["key"]


@pytest.mark.parametrize("effect", CASES)
def test_a_part_drawn_by_several_bones_names_bones_its_script_starts(effect):
    """A part several bones draw ("ids": the Brothers' 37 slab pieces, Eden's 12 picture screens) lists its own id first,
    each bone once, each a bone program the script spawns."""
    script = SCRIPTS[effect]
    data = _file(script)
    program = CineProgram(data, int.from_bytes(data[4:8], "little"), CineOpcodeTable.for_effect(effect))
    bones = {target for target, refs in program.xrefs.items() if any(kind == "spawn" for _source, kind in refs)}
    for part in script["parts"]:
        if "ids" in part:
            assert part["ids"][0] == part["id"] and len(set(part["ids"])) == len(part["ids"]) > 1, part["key"]
            assert set(part["ids"]) <= bones, part["key"]
