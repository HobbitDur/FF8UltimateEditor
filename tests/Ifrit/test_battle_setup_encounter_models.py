"""The shared battle preview setup (Fujin, Ifrit Camera tab) draws an encounter's enemies and the
default player only from the models the host's user opened one by one: a c0mNNN.dat lying beside
scene.out or the loaded model is never read. An enemy that is not opened stays a marker at its
scene.out place and its file is named in the status."""
import shutil
import struct
import sys
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[2]
BODY = "extracted_files/battle/d0c000.dat"
SOLDIER = "extracted_files/battle/c0m071.dat"
POSITIONS = ((-1100, 77, -2900), (1300, 0, -4200))


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def _manager(path):
    from Ifrit.ifritmanager import IfritManager
    manager = IfritManager(str(ROOT / "FF8GameData"))
    manager.init_from_file(str(ROOT / path))
    return manager


def _battle_folder(tmp_path):
    """scene.out with one encounter of two G-Soldiers (c0m071), the soldier and Squall copied
    beside it: files the setup must not pick up."""
    raw = bytearray(128)
    raw[7] = 0xC0
    raw[0x38:0x3A] = bytes((71 + 16, 71 + 16))
    for index, position in enumerate(POSITIONS):
        struct.pack_into('<3h', raw, 8 + 6 * index, *position)
    scene = tmp_path / "scene.out"
    scene.write_bytes(raw)
    for name in (SOLDIER, BODY):
        shutil.copy(ROOT / name, tmp_path / Path(name).name)
    return scene


def _pick_encounter(setup, scene):
    picker = setup.encounters
    assert picker.load(scene)
    picker.encounter.setCurrentIndex(1)
    assert picker.selected is not None and picker.selected_slot is not None
    return picker


@pytest.mark.ff8data(BODY, SOLDIER)
def test_enemy_not_imported_is_a_named_marker(qapp, tmp_path):
    from Ifrit.IfritCameraSeq.battlepreview import BattlePreviewSetup
    squall = _manager(BODY)
    setup = BattlePreviewSetup(squall)
    picker = _pick_encounter(setup, _battle_folder(tmp_path))
    context = setup.build()
    # Both soldiers stand where scene.out puts them, as markers: no model read from the folder
    assert [context.slots[3 + i].position for i in range(2)] == list(POSITIONS)
    assert setup._scene_mesh_actors == [] and setup.opponent_mesh() is None
    assert "c0m071.dat: not imported" in picker.status.text()
    assert "markers" in setup.status.text()

    # The host's opened model (its model list) draws them
    asked = []
    setup.model_source = lambda name: asked.append(name) or (str(ROOT / SOLDIER) if name == "c0m071.dat" else None)
    context = setup.build()
    assert "c0m071.dat" in asked
    drawn = [actor for _manager, actor in setup._scene_mesh_actors]
    assert drawn == [context.slots[3], context.slots[4]]
    assert [actor.position for actor in drawn] == list(POSITIONS)
    assert "not imported" not in picker.status.text()
    setup.close()


@pytest.mark.ff8data(BODY, SOLDIER)
def test_monster_preview_player_only_from_imported_models(qapp, tmp_path):
    """Filming a monster: the party's player is the loaded opponent or an opened d0c000.dat, never
    the Squall beside scene.out."""
    from Ifrit.IfritCameraSeq.battlepreview import BattlePreviewSetup
    soldier = _manager(SOLDIER)
    setup = BattlePreviewSetup(soldier)
    picker = _pick_encounter(setup, _battle_folder(tmp_path))
    setup.build()
    assert "d0c000.dat not imported" in picker.status.text()
    # the other soldier is the loaded model's own file: drawn without a lookup
    assert [manager for manager, _actor in setup._scene_mesh_actors] == [soldier]

    squall = _manager(BODY)
    setup.models = {"d0c000.dat": squall}               # imported by the host
    context = setup.build()
    assert "not imported" not in picker.status.text()
    assert (squall, context.slots[setup.party_slot.value()]) in setup._scene_mesh_actors
    setup.close()


@pytest.mark.ff8data(BODY, SOLDIER)
def test_ifrit_camera_tab_uses_the_session_models(qapp, tmp_path):
    """Ifrit's Camera tab preview: the encounter models are the files opened in the session's
    list, nothing else - not even a file beside the opened one."""
    from PyQt6.QtCore import QSettings
    from Ifrit.ifritmonsterwidget import IfritMonsterWidget
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    widget = IfritMonsterWidget(settings=settings, icon_path="Resources", game_data_folder="FF8GameData")
    widget._ask_ram_budget = lambda *a: True
    widget.load_file(str(ROOT / SOLDIER))
    setup = widget._files[0]['pane']._camera_widget._preview_panel._battle_setup
    assert setup.model_source("c0m071.dat") == str(ROOT / SOLDIER)
    assert setup.model_source("d0c000.dat") is None            # beside it on disk, not opened
    widget._append_to_session([str(ROOT / BODY)])
    assert setup.model_source("d0c000.dat") == str(ROOT / BODY)
    widget.close()
