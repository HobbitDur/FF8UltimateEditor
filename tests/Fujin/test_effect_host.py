"""New effects and the game's host (docs/fujin-effect-description.md, step 6): Fujin edits an
effect's description (Choreography's Description tab), copies one into a free slot of the effect
table as a new effect, and Save writes their programs (FujinEffects/effect_NNN.fxprog, with the edited
parameters) beside FujinEffects.dll, which runs them in the game - checked here inside the recorder,
which loads the DLL as the game does (host=). A new effect works in memory of its own and, made with
the exe at hand, reads its own data (copied into its program): no exe address is left in it."""
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


def drawing(lines):
    """What a recording draws and plays, wherever its data lies: a sprite's sequence address and a
    sound's block address left out (a sound keeps the world sound id it plays)."""
    lines = [re.sub(r"^(Q \d+ \d+) [0-9A-F]+ ", r"\1 - ", line) for line in untag(lines)]
    return [re.sub(r"^(S \d+) [0-9A-F]+ ", r"\1 - ", line) for line in lines]


EXE_ADDRESS = re.compile(r"(?<![0-9A-Za-z$@])(0x[0-9A-F]{6,7}|1[0-9]{7}|[2-4][0-9]{7})(?![0-9])")


@pytest.mark.ff8data("extracted_files/FF8_EN.exe")
def test_a_new_effect_made_with_the_exe_has_its_own_data():
    exe = EXE.read_bytes()
    for effect, keys in ((1, 8), (133, 24), (122, 4), (115, 6), (123, 5), (125, 5), (109, 6), (111, 7), (118, 6), (121, 4), (120, 5), (127, 5), (114, 5), (124, 8), (106, 7), (108, 12), (2, 6), (3, 12), (4, 13), (5, 7), (7, 3), (8, 4), (10, 3), (11, 2), (12, 3), (13, 2), (14, 4), (15, 2), (16, 3), (17, 2), (18, 0), (19, 3), (20, 3), (21, 2), (22, 2), (23, 3), (24, 3), (25, 3), (26, 2), (27, 3), (28, 3), (29, 3), (30, 3), (31, 3), (32, 3), (33, 3), (34, 3), (35, 3), (36, 3), (37, 3), (38, 2), (39, 3), (40, 2), (41, 4), (42, 4), (292, 3), (293, 3), (294, 3), (295, 3), (296, 3)):
        source = load_description(effect)
        new = new_effect(source, 300 + effect % 100, "New", exe)
        assert "exe_data" not in new and "exe_data" in source
        data = {key: entry for key, entry in new["data"].items() if isinstance(entry, dict)}
        assert len(data) == keys
        for key, entry in source["exe_data"].items():
            if not isinstance(entry, dict):
                continue
            assert data[key]["from"] == entry["address"]
            if entry["kind"] == "pointers":
                assert data[key]["pointers"] == entry["items"]
            elif entry["kind"] == "actors":   # the actor data whole: from its body to its header's end
                start, end = int(entry["body"], 16) - 0x400000, int(entry["address"], 16) + entry["size"] - 0x400000
                assert bytes.fromhex(data[key]["hex"]) == exe[start:end]
            else:
                start = int(entry["address"], 16) - 0x400000
                assert bytes.fromhex(data[key]["hex"]) == exe[start:start + entry["size"]]
        program = compile_program(new)
        code = "\n".join(line for line in program.splitlines() if not line.startswith(("data ", "data_actors ", "#"))
                         # (a port module's copy: its code's identities and its memory moved into its block)
                         and not ("module" in source and line.startswith(("module", "memory ", "pool ", "code ", "tick call ",
                                                                          "phase_tick call ", "port ", "native "))))
        assert not EXE_ADDRESS.findall(code), EXE_ADDRESS.findall(code)[:5]
        # its part tabs show the exe's copy of its sequences and sounds
        defaults = {field["key"]: field["default"] for field in description_schema(new)["fields"]}
        assert defaults == {field["key"]: field["default"] for field in description_schema(source)["fields"]}
    cure = new_effect(load_description(1), 224, "New heal", exe)
    assert "data emitter.sound " in compile_program(cure) and "param emitter.sound sound @emitter.sound @emitter.sound" in compile_program(cure)
    # a sound picked in the part tab (an exe address) plays that one; the game value stays its own
    assert "param emitter.sound sound 23336900 @emitter.sound" in compile_program(cure, {"emitter.sound": 0x16417C4})


def test_a_new_effect_is_a_copy_in_a_free_slot():
    assert FREE_EFFECTS[:2] == (224, 225) and FREE_EFFECTS[2] == 346 and FREE_EFFECTS[-1] == 400
    cure = load_description(1)
    new = new_effect(cure, 224, "New heal")
    assert (new["effect"], new["name"], new["base"]) == (224, "New heal", 1)
    assert "copy" not in new and not any("function" in task for task in new["tasks"])
    assert "functions" in cure["copy"] and "own_memory" not in cure                            # the source untouched
    # memory of its own: each name its exe copy had, sized; its pools allocated too
    assert new["own_memory"].keys() == cure["copy"]["memory"].keys()
    assert (new["own_memory"]["overlay_ctx"], new["own_memory"]["root_pool"], new["own_memory"]["packet_cursor"]) == (0xF8, 0xC8, 4)
    assert all(pool["own"] and "queue" not in pool and "storage" not in pool for pool in new["pools"])
    program = compile_program(new, {"ring.radius.num": 4})
    assert "program 224 New_heal" in program and "function " not in program and "\nmemory " not in program
    assert "own overlay_verts 25600" in program and "pool own own 108 300 -1 0" in program
    hypnosis = new_effect(load_description(133), 225, "New hypnosis")
    assert hypnosis["own_memory"]["root_pool"] == 0x14
    assert "pool own 0xD40 196 1 -1 1" in compile_program(hypnosis)                              # storage: the magic buffer
    assert "param ring.radius.num i16 4 2" in program
    assert new_effect(new, 225, "Again")["base"] == 1
    schema = description_schema(new)
    assert [field["key"] for field in schema["fields"]] == [param["key"] for param in new["params"]]
    assert {field["key"]: field["default"] for field in schema["fields"]}["emitter.sound"] == 0x16417C4


@pytest.mark.ff8data(*FILES)
def test_the_host_dll_plays_the_saved_programs(tmp_path):
    """FujinEffects.dll, in the recorder as in the game, reads the programs of a game folder: new
    effects in memory of their own, with their own data (Cure's copy as 224, Hypnotize's as 225),
    draw and play what Cure and Hypnotize do; Cure with its parameters edited records FFNx's port
    with them; Hypnotize records itself."""
    from Fujin.effectparts import effect_schema
    from Fujin.recorderbuild import HOST_DLL, RECORDER
    if effect_schema(1) is None or not HOST_DLL.is_file():
        pytest.skip("the recorder and FujinEffects.dll are not built with FFNx's effect sources")
    folder = tmp_path / "game/FujinEffects"
    folder.mkdir(parents=True)
    values = {"ring.radius.num": 4, "ring.radius.max": 2048, "sparkle.colour.r": 255}
    exe = EXE.read_bytes()
    write_program(new_effect(load_description(1), 224, "New heal", exe), folder / program_file_name(224))
    write_program(load_description(1), folder / program_file_name(1), values)
    write_program(load_description(133), folder / program_file_name(133))
    write_program(new_effect(load_description(133), 225, "New hypnosis", exe), folder / program_file_name(225))

    def record(effect, tag, monster, caster, target, *extra):
        out = tmp_path / f"{tag}.txt"
        run = subprocess.run([str(RECORDER), str(effect), f"exe={EXE}", f"magic={MAGIC}", f"battle={BATTLE}", f"out={out}",
                              f"slot0={BATTLE / 'd0c000.dat'}", f"weapon0={BATTLE / 'd0w000.dat'}",
                              f"slot3={BATTLE / monster}", f"caster={caster}", f"target={target}", *extra],
                             cwd=str(RECORDER.parent), capture_output=True, text=True, timeout=120)
        assert run.returncode == 0 and "faulted" not in run.stdout, run.stdout[-500:]
        return out.read_text().splitlines(), run.stdout

    host = (f"host={HOST_DLL}", f"hostdir={tmp_path / 'game'}")
    cure, _log = record(1, "cure", "c0m009.dat", 0, 3)
    new, log = record(224, "new", "c0m009.dat", 0, 3, *host)
    assert "host: 4 programs installed" in log and drawing(new) == drawing(cure) and len(cure) > 10000
    assert any(line.startswith("S ") for line in new)
    params = tmp_path / "params.txt"
    params.write_text("".join(f"{key} {value}\n" for key, value in values.items()))
    native, _log = record(1, "native", "c0m009.dat", 0, 3, "native=1", f"params={params}")
    hosted, _log = record(1, "hosted", "c0m009.dat", 0, 3, *host)
    assert untag(hosted) == untag(native) and untag(hosted) != untag(cure)
    hypnotize, _log = record(133, "hypnotize", "c0m033.dat", 3, 0)
    hosted, _log = record(133, "hosted133", "c0m033.dat", 3, 0, *host)
    assert untag(hosted) == untag(hypnotize)
    new, _log = record(225, "new225", "c0m033.dat", 3, 0, *host)
    assert drawing(new) == drawing(hypnotize)


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
    programs = tmp_path / "FujinEffects"
    assert not (tmp_path / "direct/exe").exists()                # FFNx's folder: none of it is FFNx's
    assert sorted(path.name for path in programs.iterdir()) == ["effect_001.fxprog", "effect_224.fxprog"]
    # one file per effect: the program the DLL runs, then the line Fujin reopens it from
    text = (programs / "effect_224.fxprog").read_text(encoding="ascii")
    assert text.startswith(fujin.effect_program(224)) and text.count("\n#source ") == 1
    assert sorted(path.name for path in tmp_path.iterdir()) == sorted(["FujinEffects", "effects_EN.hext"]
                                                                      + [HOST_DLL.name] * HOST_DLL.is_file())
    assert not fujin.can_save_folder()
    # imported again in a fresh Fujin
    other = FujinWidget()
    assert sorted(other.import_effects([str(programs / "effect_001.fxprog"), str(programs / "effect_224.fxprog")])) == [1, 224]
    assert other.descriptions == fujin.descriptions and other.effect_name(224) == "New heal"
    assert other.effect_params == {1: {"ring.radius.num": 4}, 224: {"ring.radius.num": 4}}
    assert not other.can_save_folder()                            # what the files hold: nothing to save
    # back to Fujin's description; the new effect deleted
    other.select_effect(1)
    other._description_reset()
    assert 1 not in other.descriptions and other.effect_program(1) is None
    other.select_effect(224)
    assert other.description_view.reset_button.text() == "Delete this new effect"
    other._description_reset()
    assert 224 not in other.descriptions and other.effect_name(224) == other.catalog.name(224)
    # saved again: Cure's file keeps its parameters only, the deleted new effect's file goes
    other.effect_params.pop(224, None)
    assert other.save_files(str(tmp_path))
    assert sorted(path.name for path in programs.iterdir()) == ["effect_001.fxprog"]
    from Fujin.effectprogram import read_effect_file
    assert read_effect_file((programs / "effect_001.fxprog").read_text(encoding="ascii")) == (1, None, {"ring.radius.num": 4})


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
