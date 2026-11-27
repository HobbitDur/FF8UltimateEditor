"""Ifrit's battle previews draw the encounter's battle stage, as Alexander, JumboCactuar and Fujin do:
the stage comes from Ifrit's Import complementary (a0stgNNN.x, BattleSideFiles) and replaces the
ground grid. And the encounter list of a monster comes from its c0mNNN file name: a file named
otherwise is not taken for c0m000 (the Dummy, in 202 encounters from 764 up)."""
import struct
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[2]
SOLDIER = "extracted_files/battle/c0m071.dat"
STAGE = "extracted_files/battle/a0stg004.x"
STAGE_ID = 4


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def _scene(tmp_path, records):
    """scene.out with one encounter per (stage id, [com ids]) record, every slot present."""
    raw = bytearray()
    for stage_id, com_ids in records:
        record = bytearray(128)
        record[0x00] = stage_id
        record[7] = (0xFF00 >> len(com_ids)) & 0xFF   # slot i present = bit 7 - i
        for index, com_id in enumerate(com_ids):
            record[0x38 + index] = com_id + 16
            struct.pack_into('<3h', record, 8 + 6 * index, 1000 * index, 0, -3000)
        raw += record
    path = tmp_path / "scene.out"
    path.write_bytes(raw)
    return path


def test_monster_named_without_c0m_number_lists_no_encounter(qapp, tmp_path):
    from Ifrit.IfritCameraSeq.encounterpreview import EncounterPicker
    scene = _scene(tmp_path, [(160, [0]), (29, [0, 0]), (4, [71])])
    enemy = SimpleNamespace(entity_type=SimpleNamespace(name='MONSTER'), id=0,
                            origin_file_name='my monster.dat', origin_path=str(tmp_path / 'my monster.dat'))
    picker = EncounterPicker(SimpleNamespace(enemy=enemy))
    assert picker.load(scene)
    assert picker.com_id is None and picker.encounter.count() == 1   # Manual placement only
    assert "c0mNNN" in picker.status.text()
    # the real Dummy does list its encounters
    enemy.origin_file_name, enemy.origin_path = 'c0m000.dat', str(tmp_path / 'c0m000.dat')
    picker.refresh_model()
    assert [picker.encounter.itemData(i).index for i in range(1, picker.encounter.count())] == [0, 1]
    # a renamed copy keeps its number: c0m071 - copy.dat is the G-Soldier
    enemy.origin_file_name, enemy.origin_path = 'c0m071 - copy.dat', str(tmp_path / 'c0m071 - copy.dat')
    picker.refresh_model()
    assert [picker.encounter.itemData(i).index for i in range(1, picker.encounter.count())] == [2]
    picker.close()


def _soldier_setup(tmp_path):
    from Ifrit.ifritmanager import IfritManager
    from Ifrit.IfritCameraSeq.battlepreview import BattlePreviewSetup
    manager = IfritManager(str(ROOT / "FF8GameData"))
    manager.init_from_file(str(ROOT / SOLDIER))
    setup = BattlePreviewSetup(manager, model_view=True)
    picker = setup.encounters
    assert picker.load(_scene(tmp_path, [(STAGE_ID, [71])]))
    picker.refresh_model(force=True)
    picker.encounter.setCurrentIndex(1)
    assert picker.selected is not None and picker.selected_slot is not None
    return setup


@pytest.mark.ff8data(SOLDIER, STAGE)
def test_setup_draws_the_encounter_stage_once_opened(qapp, tmp_path):
    setup = _soldier_setup(tmp_path)
    setup.build()
    assert setup.stage is None and setup.opponent_mesh() is None   # no stage source: nothing more

    opened = {}
    setup.set_stage_source(lambda name: opened.get(name))
    setup.build()
    assert setup.stage is None and "a0stg004.x not imported" in setup.encounters.status.text()

    opened["a0stg004.x"] = str(ROOT / STAGE)
    setup.set_stage_source(lambda name: opened.get(name))
    setup.build()
    assert setup.stage is not None and setup.stage_note == ''
    mesh = setup.opponent_mesh()
    count = len(setup.stage.vertices)
    from FF8GameData.battlestage.battlestageanalyser import VERTEX_SCALE
    # the stage, rescaled from BattleScenePreview's viewer space to this scene's unit
    assert np.allclose(mesh.vertices[:count], setup.stage.vertices * (setup.unit / VERTEX_SCALE), atol=1e-4)
    assert len(mesh.batches) == len(setup.stage.batches)
    assert setup.opponent_mesh(3, True) is mesh            # a later tick keeps the stage
    assert np.allclose(mesh.vertices[:count], setup.stage.vertices * (setup.unit / VERTEX_SCALE), atol=1e-4)

    setup.encounters.encounter.setCurrentIndex(0)           # manual placement: no stage
    setup.build()
    assert setup.stage is None
    setup.close()


@pytest.mark.ff8data(SOLDIER, STAGE)
def test_battle_view_hides_the_grid_under_a_stage(qapp, tmp_path):
    from Ifrit.Ifrit3D.battleview import BattleView
    setup = _soldier_setup(tmp_path)
    view = BattleView.__new__(BattleView)
    view.setup, view.ifrit_manager, view._dirty = setup, setup.manager, False
    calls = []
    gl = SimpleNamespace(set_model_translation=lambda *a: None, set_preview_model_transform=lambda *a: None,
                         set_preview_actor=lambda mesh: calls.append(('actor', mesh)),
                         set_preview_slot_markers=lambda points, height, grid, step: calls.append(('grid', grid)))
    setup.build(0, animate=True)
    view.apply(gl, 0, 0)
    assert calls[-1][0] == 'grid' and calls[-1][1] is not None        # no stage: the grid
    setup.set_stage_source(lambda name: str(ROOT / STAGE) if name == "a0stg004.x" else None)
    setup.build(0, animate=True)
    view.apply(gl, 0, 0)
    assert calls[-1] == ('grid', None) and calls[-2][1] is not None   # the stage, no grid
    setup.close()


@pytest.mark.ff8data(SOLDIER, STAGE)
def test_ifrit_imports_stages_as_complementary_files(qapp, tmp_path):
    from PyQt6.QtCore import QSettings
    from Ifrit.ifritmonsterwidget import IfritMonsterWidget, STAGE_FILES_KEY
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    widget = IfritMonsterWidget(settings=settings, icon_path="Resources", game_data_folder="FF8GameData")
    widget._ask_ram_budget = lambda *a: True
    labels = [label for label, _opener in widget.complementary_entries()]
    assert any(label.startswith("Battle stages: a0stg") for label in labels)
    assert all(binding.file_name in labels for binding in widget.file_bindings())   # the others stay offered
    assert any(source.key == STAGE_FILES_KEY for source in widget.auto_import_sources())

    widget.load_file(str(ROOT / SOLDIER))
    pane = widget._files[0]['pane']
    setup = pane._camera_widget._preview_panel._battle_setup
    assert setup.stage_source("a0stg004.x") is None
    widget.stage_files.add([str(ROOT / STAGE)])
    assert setup.stage_source("a0stg004.x") == str(ROOT / STAGE)
    assert widget.file_registry.get_path(STAGE_FILES_KEY)
    widget.file_registry.close_file(STAGE_FILES_KEY)          # closed in the Opened files panel
    assert setup.stage_source("a0stg004.x") is None
    widget.close()
