"""New effects and the game's host (docs/fujin-effect-description.md, step 6): Fujin edits an
effect's description (Choreography's Description tab), copies one into a free slot of the effect
table as a new effect, and Save writes their programs (direct/exe/effect_NNN.fxprog, with the edited
parameters) beside FujinEffects.dll, which runs them in the game - checked here inside the recorder,
which loads the DLL as the game does (host=)."""
import json
import re
import subprocess
from pathlib import Path

import pytest

from Fujin.effectprogram import (FREE_EFFECTS, compile_program, description_schema, load_description, new_effect,
                                 program_file_name, write_program)

ROOT = Path(__file__).resolve().parents[2]
EXE = ROOT / "extracted_files/FF8_EN.exe"
MAGIC, BATTLE = ROOT / "extracted_files/magic", ROOT / "extracted_files/battle"
FILES = ("extracted_files/FF8_EN.exe", "extracted_files/magic/mag000-049.tim", "extracted_files/magic/mag132.tim",
         "extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat", "extracted_files/battle/c0m009.dat",
         "extracted_files/battle/c0m033.dat")


def untag(lines):
    return [re.sub(r"^(P|Q \d+) \d+ ", r"\1 0 ", line) for line in lines if not line.startswith("M ")]


def test_a_new_effect_is_a_copy_in_a_free_slot():
    assert FREE_EFFECTS[:2] == (224, 225) and FREE_EFFECTS[2] == 346 and FREE_EFFECTS[-1] == 400
    cure = load_description(1)
    new = new_effect(cure, 224, "New heal")
    assert (new["effect"], new["name"], new["base"]) == (224, "New heal", 1)
    assert "functions" not in new["copy"] and not any("function" in task for task in new["tasks"])
    assert new["copy"]["memory"] == cure["copy"]["memory"] and "functions" in cure["copy"]     # the source untouched
    program = compile_program(new, {"ring.radius.num": 4})
    assert "program 224 New_heal" in program and "function " not in program
    assert "param ring.radius.num i16 4 2" in program
    assert new_effect(new, 225, "Again")["base"] == 1
    schema = description_schema(new)
    assert [field["key"] for field in schema["fields"]] == [param["key"] for param in new["params"]]
    assert {field["key"]: field["default"] for field in schema["fields"]}["emitter.sound"] == 0x16417C4


@pytest.mark.ff8data(*FILES)
def test_the_host_dll_plays_the_saved_programs(tmp_path):
    """FujinEffects.dll, in the recorder as in the game, reads the programs of a game folder: a new
    effect (Cure's copy as 224) records Cure; Cure with its parameters edited records FFNx's port
    with them; Hypnotize records itself."""
    from Fujin.effectparts import effect_schema
    from Fujin.recorderbuild import HOST_DLL, RECORDER
    if effect_schema(1) is None or not HOST_DLL.is_file():
        pytest.skip("the recorder and FujinEffects.dll are not built with FFNx's effect sources")
    folder = tmp_path / "game/direct/exe"
    folder.mkdir(parents=True)
    values = {"ring.radius.num": 4, "ring.radius.max": 2048, "sparkle.colour.r": 255}
    write_program(new_effect(load_description(1), 224, "New heal"), folder / program_file_name(224))
    write_program(load_description(1), folder / program_file_name(1), values)
    write_program(load_description(133), folder / program_file_name(133))

    def record(effect, tag, monster, caster, target, *extra):
        out = tmp_path / f"{tag}.txt"
        run = subprocess.run([str(RECORDER), str(effect), f"exe={EXE}", f"magic={MAGIC}", f"battle={BATTLE}", f"out={out}",
                              f"slot0={BATTLE / 'd0c000.dat'}", f"weapon0={BATTLE / 'd0w000.dat'}",
                              f"slot3={BATTLE / monster}", f"caster={caster}", f"target={target}", *extra],
                             cwd=str(RECORDER.parent), capture_output=True, text=True, timeout=120)
        assert run.returncode == 0 and "faulted" not in run.stdout, run.stdout[-500:]
        return untag(out.read_text().splitlines()), run.stdout

    host = (f"host={HOST_DLL}", f"hostdir={tmp_path / 'game'}")
    cure, _log = record(1, "cure", "c0m009.dat", 0, 3)
    new, log = record(224, "new", "c0m009.dat", 0, 3, *host)
    assert "host: 3 programs installed" in log and new == cure and len(cure) > 10000
    params = tmp_path / "params.txt"
    params.write_text("".join(f"{key} {value}\n" for key, value in values.items()))
    native, _log = record(1, "native", "c0m009.dat", 0, 3, "native=1", f"params={params}")
    hosted, _log = record(1, "hosted", "c0m009.dat", 0, 3, *host)
    assert hosted == native and hosted != cure
    hypnotize, _log = record(133, "hypnotize", "c0m033.dat", 3, 0)
    hosted, _log = record(133, "hosted133", "c0m033.dat", 3, 0, *host)
    assert hosted == hypnotize


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_description_tab_new_effect_save_and_import(qapp, tmp_path):
    from Fujin.fujinwidget import FujinWidget
    from Fujin.recorderbuild import HOST_DLL
    fujin = FujinWidget()
    fujin.select_effect(1)
    view = fujin.description_view
    assert json.loads(view.text.toPlainText()) == load_description(1) and not view.reset_button.isVisibleTo(view)
    assert fujin.effect_program(1) is None                     # Fujin's own description: FFNx's port previews it
    view.text.setPlainText("{ not json")
    assert not view.apply() and "Not applied" in view.error.text() and 1 not in fujin.descriptions
    edited = load_description(1)
    next(task for task in edited["tasks"] if task["key"] == "ring")["step_spawns"] = []
    edited["tasks"][1]["motion"] = ["helix", "$ring.steps.nothing", 1]
    view.text.setPlainText(json.dumps(edited))
    assert not view.apply() and "no parameter ring.steps.nothing" in view.error.text()
    edited["tasks"][1]["motion"] = ["helix", "$ring.steps.per_tick", "$ring.steps.angle"]
    view.text.setPlainText(json.dumps(edited))
    assert view.apply() and fujin.descriptions[1] == edited
    assert "program 1 Cure" in fujin.effect_program(1) and fujin.can_save_folder()
    # a new effect from the edited Cure, its parameters with it
    fujin.effect_params[1] = {"ring.radius.num": 4}
    assert fujin.new_effect_dialog(224, "New heal") == 224
    assert fujin.current_effect == 224 and fujin.effect_list.currentItem().text().startswith("* 224 — New heal (new effect)")
    assert fujin.descriptions[224]["base"] == 1 and fujin.effect_params[224] == {"ring.radius.num": 4}
    assert [tab.part["key"] for tab in fujin.part_tabs] == [part["key"] for part in edited["parts"]]
    assert "program 224 New_heal" in fujin.effect_program(224) and "param ring.radius.num i16 4 2" in fujin.effect_program(224)
    assert fujin.native_preview.program(224) == fujin.lab.program(224) == fujin.effect_program(224)
    with pytest.raises(ValueError):
        fujin.new_effect_dialog(224, "Twice")
    assert fujin.save_files(str(tmp_path))
    programs = tmp_path / "direct/exe"
    assert sorted(path.name for path in programs.iterdir()) == ["effect_001.fxprog", "effect_224.fxprog"]
    assert (programs / "effect_224.fxprog").read_text(encoding="ascii") == fujin.effect_program(224)
    assert json.loads((tmp_path / "effect_224.fxdesc").read_text(encoding="utf-8")) == fujin.descriptions[224]
    assert (tmp_path / HOST_DLL.name).is_file() == HOST_DLL.is_file()
    assert not fujin.can_save_folder()
    # imported again in a fresh Fujin
    other = FujinWidget()
    assert sorted(other.import_descriptions([str(tmp_path / "effect_001.fxdesc"), str(tmp_path / "effect_224.fxdesc")])) == [1, 224]
    assert other.descriptions == fujin.descriptions and other.effect_name(224) == "New heal"
    # back to Fujin's description; the new effect deleted
    other.select_effect(1)
    other._description_reset()
    assert 1 not in other.descriptions and other.effect_program(1) is None
    other.select_effect(224)
    assert other.description_view.reset_button.text() == "Delete this new effect"
    other._description_reset()
    assert 224 not in other.descriptions and other.effect_name(224) == other.catalog.name(224)


def test_the_preview_records_a_program(qapp, tmp_path):
    """An effect with a description held here records from its program (program=), the part tabs'
    variants still through params=; its cache key changes with the program."""
    from Common.fileregistry import FileRegistry
    from Fujin.nativepreview import BattleCast, NativePreviewView
    view = NativePreviewView(FileRegistry(), exe_path=lambda: str(tmp_path / "FF8_EN.exe"), effect_files=lambda: {})
    view.effect_id = 224
    cast = BattleCast({}, 0, 3, program="program 224 New_heal\n", params=(("ring.radius.num", 4),))
    args, _output, _lines = view._recorder_args(cast, str(tmp_path))
    program = next(arg for arg in args if arg.startswith("program="))[8:]
    assert Path(program).read_text(encoding="ascii") == "program 224 New_heal\n" and "native=1" not in args
    params = next(arg for arg in args if arg.startswith("params="))[7:]
    assert Path(params).read_text(encoding="ascii") == "ring.radius.num 4\n"
    assert cast.key() != BattleCast({}, 0, 3, program="program 224 Other\n", params=cast.params).key()
