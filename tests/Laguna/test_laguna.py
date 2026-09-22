"""Laguna - GF cinematic script (MAGxxx_B.00) decoding, simulation, in-place edits and the tool."""
import pathlib
import struct
import subprocess
import sys

import pytest

from FF8GameData.magcine.cinescript import (CineOpcodeTable, CineProgram, decode_instruction,
                                            format_instruction)
from FF8GameData.magcine.cinesim import CineSimulation, root_program_offset
from FF8GameData.magcine.magcontainer import MagContainer
from Laguna.lagunamanager import LagunaManager, CINEMATIC_GFS, gf_from_file_name

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MAGIC = PROJECT_ROOT / "extracted_files" / "magic"
GF_FILES = [(gf, MAGIC / file_name) for gf, (_effect, file_name) in CINEMATIC_GFS.items()]
needs_files = pytest.mark.skipif(not (MAGIC / "MAG200_B.00").exists(), reason="extracted_files/magic missing")


# --------------------------------------------------------------------- synthetic
def _words(*values):
    return b"".join(struct.pack("<H", v & 0xFFFF) for v in values)


def _file(script: bytes) -> bytes:
    """Minimal mag file: header with the root program right after it (0x30)."""
    header = bytearray(0x30)
    struct.pack_into("<I", header, 4, 0x30)
    struct.pack_into("<I", header, 0x10, 0x30 + len(script))
    return bytes(header) + script


def test_opcode_table_is_complete():
    table = CineOpcodeTable.default()
    assert len(table.opcodes) == 236
    assert table.get(0x09).name == "Wait"
    # the dozen GF-specific opcodes carry their GF list
    assert table.get(0xDA).gfs == ["Brothers"]
    assert table.get(0x93).gfs == ["Ifrit", "Leviathan"]


def test_generic_write_length_follows_the_component_mask():
    # SetVel (0x0B) with PosX|PosY|PosZ (bits 12..10) = 3 operand words
    instruction = decode_instruction(_words(0x0B | 0x1C00, 1, 2, 3, 0x0000), 0)
    assert instruction.length == 8 and instruction.words == [1, 2, 3]
    assert format_instruction(instruction) == "SetVel PosX=1 PosY=2 PosZ=3"


def test_walk_follows_jumps_spawns_and_calls():
    script = _words(0x0032, 14,     # 30 SpawnBone -> 0x3E
                    0x0003, 12,     # 34 Call -> 0x40
                    0x0209,         # 38 Wait 1
                    0x0001, 0,      # 3A LoopSequenceOrFinish
                    0x0000,         # 3E EndChannel (the spawned bone's program)
                    0x0004)         # 40 Return (the subroutine)
    program = CineProgram(_file(script), 0x30)
    assert not program.errors
    assert "spawn" in program.entry_kinds[0x3E]
    assert program.instructions[0x40].code == 0x04
    assert len(program.instructions) == 6


def test_simulation_waits_spawns_and_kills():
    # root: spawn a bone, wait 3 ticks, finish. bone: wait 1, die.
    script = _words(0x0032, 12, 0x0609, 0x0001, 0, 0x0000, 0x0209, 0x0000)
    simulation = CineSimulation(_file(script), 0x30)
    assert simulation.finished_tick == 3
    bone = simulation.bones[1]
    assert bone.spawn_tick == 0 and bone.death_tick == 1


# --------------------------------------------------------------------- real files
@needs_files
@pytest.mark.parametrize("gf,path", GF_FILES)
def test_every_gf_script_decodes_and_simulates(gf, path):
    data = path.read_bytes()
    program = CineProgram(data, root_program_offset(data))
    assert not program.errors, program.errors[:3]
    assert len(program.instructions) > 900
    simulation = CineSimulation(data, root_program_offset(data))
    assert simulation.finished_tick > 0 and not simulation.warnings


@needs_files
def test_ifrit_simulated_length_matches_the_game():
    # measured in game (30 fps FFNx branch log): Ifrit's summon runs 324 real ticks
    data = (MAGIC / "MAG200_B.00").read_bytes()
    assert CineSimulation(data, root_program_offset(data)).finished_tick == 322


@needs_files
@pytest.mark.parametrize("gf,path", GF_FILES)
def test_mag_resources_parse(gf, path):
    for name in (path, path.with_suffix(".01")):
        container = MagContainer(name.read_bytes())
        assert container.packed
        assert not [o for o in container.objects if o.error]


@needs_files
def test_unmodified_save_is_byte_exact(tmp_path):
    manager = LagunaManager()
    manager.load_file(str(MAGIC / "MAG205_B.00"))
    assert manager.gf == "Eden"
    out = tmp_path / "MAG205_B.00"
    manager.save_file(str(out))
    assert out.read_bytes() == (MAGIC / "MAG205_B.00").read_bytes()


@needs_files
def test_in_place_edit_keeps_length_and_undoes():
    manager = LagunaManager()
    manager.load_file(str(MAGIC / "MAG200_B.00"))
    wait = next(i for i in manager.program.sorted_instructions() if i.code == 0x09)
    manager.replace_instruction(wait.offset, 0x09 | (5 << 9), [])
    assert manager.instruction_at(wait.offset).modifier == 5 and manager.modified
    spawn = next(i for i in manager.program.sorted_instructions() if i.code == 0x0A)
    with pytest.raises(ValueError):   # one more component = one more word: refused
        manager.replace_instruction(spawn.offset, spawn.op | 0xFC00, spawn.words)
    assert manager.undo() and not manager.modified


def test_gf_from_file_name():
    assert gf_from_file_name(r"C:\x\mag205_b.00") == "Eden"
    assert gf_from_file_name("MAG200_B.01") == ""


@needs_files
def test_cli_info_and_disasm():
    for command in (["info"], ["disasm", "-x"]):
        result = subprocess.run([sys.executable, "cli.py", "laguna", command[0], "-i",
                                 str(MAGIC / "MAG200_B.00")] + command[1:],
                                cwd=PROJECT_ROOT, capture_output=True, text=True, encoding="utf-8")
        assert result.returncode == 0, result.stderr
    assert "0 decode errors" in subprocess.run(
        [sys.executable, "cli.py", "laguna", "info", "-i", str(MAGIC / "MAG200_B.00")],
        cwd=PROJECT_ROOT, capture_output=True, text=True, encoding="utf-8").stdout


# --------------------------------------------------------------------- widget
@needs_files
def test_widget_loads_edits_and_simulates():
    from Common.fileregistry import FileRegistry
    from Laguna.lagunawidget import LagunaWidget
    registry = FileRegistry()
    widget = LagunaWidget(file_registry=registry)
    registry.open_file("MAG200_B.00", str(MAGIC / "MAG200_B.00"))
    registry.open_file("MAG200_B.01", str(MAGIC / "MAG200_B.01"))
    assert widget.current_gf == "Ifrit"
    assert widget.listing.rowCount() > 1000
    assert widget._simulation is not None and widget._simulation.finished_tick == 322
    assert widget.resource_tree.topLevelItemCount() == 2
    wait = next(i for i in widget.manager.program.sorted_instructions() if i.code == 0x09)
    widget._select_offset(wait.offset)
    widget.modifier_spin.setValue(3)
    widget._apply_instruction()
    assert widget.manager.instruction_at(wait.offset).modifier == 3
    widget.undo()
    assert not widget.manager.modified
    widget.deleteLater()


# --------------------------------------------------------------------- 3D scene
@needs_files
def test_scene_places_the_creature_and_the_camera():
    from FF8GameData.magcine.cinescene import CineScene
    from Laguna.creature import CreatureLoader
    data00 = (MAGIC / "MAG200_B.00").read_bytes()
    containers = [MagContainer(data00), MagContainer((MAGIC / "MAG200_B.01").read_bytes())]
    simulation = CineSimulation(data00, root_program_offset(data00))
    scene = CineScene(simulation, containers, CreatureLoader(containers))
    items = scene.items(120)
    creature = [item for item in items if item.kind == "creature"]
    assert len(creature) == 1 and len(creature[0].mesh.faces) > 500
    # the creature is at full size (outAngle 256 x 16 = 4096 = 1.0): scale 1 on every axis
    import numpy as np
    assert abs(np.linalg.norm(creature[0].matrix[:3, 0]) - 1.0) < 1e-6
    eye, target = scene.camera(120)
    assert eye.shape == (3,) and not (eye == target).all()


@needs_files
def test_widget_playback_follows_edits():
    from Common.fileregistry import FileRegistry
    from Laguna.lagunawidget import LagunaWidget
    registry = FileRegistry()
    widget = LagunaWidget(file_registry=registry)
    registry.open_file("MAG200_B.00", str(MAGIC / "MAG200_B.00"))
    widget._on_timeline_picked(17, 120)
    assert widget.tick_slider.value() == 120 and widget.scene_view.selected_bone == 17
    before = widget._simulation.finished_tick
    wait = next(i for i in widget.manager.program.sorted_instructions() if i.code == 0x09 and i.modifier == 1)
    widget._select_offset(wait.offset)
    widget.modifier_spin.setValue(20)
    widget._apply_instruction()          # the simulation re-runs by itself after an edit
    assert widget._simulation.finished_tick != before
    widget.deleteLater()


@needs_files
def test_open_folder_brings_every_gf_file():
    """The shared Open-folder scan finds the .00, .01 and every streamed part, and the scene uses them."""
    from Common.fileregistry import FileRegistry
    from Common.filetoolbarwidget import FileToolbarWidget
    from Laguna.lagunawidget import LagunaWidget
    registry = FileRegistry()
    widget = LagunaWidget(file_registry=registry)
    folder = PROJECT_ROOT / "extracted_files"
    found = FileToolbarWidget.scan_folder(str(folder), {b.file_name for b in widget.file_bindings()})
    assert len(found) == 169  # 7 x (.00 + .01) + 155 streamed parts
    for name in ("MAG200_B.00", "MAG200_B.01") + tuple(n for n in found if n.startswith("mag200_b.")):
        registry.open_file(name, found[name])
    from PyQt6.QtWidgets import QApplication
    QApplication.processEvents()
    assert widget.current_gf == "Ifrit" and widget._missing_files() == []
    assert widget.parts["Ifrit"]  # the packed parts (the raw ones are VRAM pages)
    meshes = [item for tick in range(0, widget.scene_view.scene.tick_count, 10)
              for item in widget.scene_view.scene.items(tick, False) if item.kind == "mesh"]
    assert meshes
    widget.deleteLater()


@needs_files
def test_import_is_one_folder_pick(monkeypatch):
    """Import offers no file menu for Laguna: one folder dialog, every GF file inside is loaded."""
    from PyQt6.QtWidgets import QFileDialog, QStackedWidget, QApplication
    from Common.fileregistry import FileRegistry
    from Common.filetoolbarwidget import FileToolbarWidget
    from Laguna.lagunawidget import LagunaWidget
    registry = FileRegistry()
    widget = LagunaWidget(file_registry=registry)
    stack = QStackedWidget()
    stack.addWidget(widget)
    toolbar = FileToolbarWidget(stack, registry)
    entries = toolbar._import_entries()
    assert len(entries) == 1                                   # no list of files to choose from
    assert not toolbar.import_complementary_button.isEnabled()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        staticmethod(lambda *args, **kwargs: str(PROJECT_ROOT / "extracted_files")))
    entries[0][1]()
    QApplication.processEvents()
    assert widget.gf_selector.count() == 7 and widget._missing_files() == []
    toolbar.deleteLater()
    stack.deleteLater()
