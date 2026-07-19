"""Empty placeholder battle .dat (0 bytes) - e.g. Squall's unused weapon slot d0w007.dat, the
only 0-byte file in the whole battle model set. Instead of being skipped, it opens as a BLANK
model of the kind its filename implies (a weapon here): all the tabs that kind normally shows,
but every section empty - an empty 3D view, an empty sequence list - so the slot can be filled
in and saved. See MonsterAnalyser.create_blank / IfritManager.create_blank_enemy.

Monsters are deliberately NOT blank-able (they'd need parse-shaped info_stat + AI defaults that
can't be synthesized from nothing), and no empty monster/character file exists anyway.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QSettings
_APP = QApplication.instance() or QApplication([])

from Ifrit.ifritmanager import IfritManager
from FF8GameData.monsterdata import EntityType

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME_DATA = os.path.join(REPO, "FF8GameData")
EMPTY_WEAPON = os.path.join(REPO, "extracted_files", "battle", "d0w007.dat")

pytestmark = pytest.mark.skipif(
    not (os.path.isfile(EMPTY_WEAPON) and os.path.getsize(EMPTY_WEAPON) == 0),
    reason="d0w007.dat (0-byte placeholder) not available")


def test_entity_type_from_filename():
    assert IfritManager.entity_type_from_filename("d0w007.dat") == EntityType.WEAPON
    assert IfritManager.entity_type_from_filename("d3c016.dat") == EntityType.CHARACTER
    assert IfritManager.entity_type_from_filename("c0m042.dat") == EntityType.MONSTER
    assert IfritManager.entity_type_from_filename("b0wave.dat") is None


def test_blank_weapon_is_created_for_empty_file():
    mgr = IfritManager(GAME_DATA)
    enemy = mgr.create_blank_enemy(EMPTY_WEAPON)
    assert enemy is not None
    assert enemy.entity_type == EntityType.WEAPON
    assert enemy.header_data['nb_section'] == 9
    # Every model section is empty.
    assert not enemy.geometry_data.object_data
    assert enemy.animation_data.nb_animations == 0


def test_monster_placeholder_is_refused():
    # A monster can't be blanked (no info_stat/AI defaults to synthesize) -> None so the caller
    # falls back to skipping it.
    mgr = IfritManager(GAME_DATA)
    assert mgr.create_blank_enemy("c0m199.dat") is None


def test_blank_weapon_round_trips_through_save_reload(tmp_path):
    mgr = IfritManager(GAME_DATA)
    enemy = mgr.create_blank_enemy(EMPTY_WEAPON)
    mgr.set_active_enemy(enemy, EMPTY_WEAPON, textures=([], True))
    out = str(tmp_path / "d0w007.dat")
    mgr.save_file(out)
    assert os.path.getsize(out) > 0

    reloaded = IfritManager(GAME_DATA)
    reloaded.init_from_file(out)
    # The synthesized header classifies back to a weapon with the same section count.
    assert reloaded.enemy.entity_type == EntityType.WEAPON
    assert reloaded.enemy.header_data['nb_section'] == 9


def test_empty_placeholder_opens_in_the_gui_as_an_empty_weapon():
    """The concrete goal: the 0-byte file must OPEN (not be skipped), showing a weapon's tabs
    (3D + Sequence) with an empty 3D view - previously Ifrit3DWidget.load_file() raised
    ValueError on zero-vertex geometry (numpy .min() on an empty array)."""
    from Ifrit.ifritmonsterwidget import IfritMonsterWidget

    widget = IfritMonsterWidget(settings=QSettings("test", "blank_placeholder"),
                                icon_path="Resources", game_data_folder=GAME_DATA)
    widget._ask_ram_budget = lambda *a: True   # don't pop the modal RAM dialog in a headless run
    widget.load_file(EMPTY_WEAPON)             # must not raise, must not skip

    assert len(widget._files) == 1, "placeholder was skipped instead of opened"
    pane = widget._files[0]['pane']
    tabs = pane._tabs
    assert tabs.isTabVisible(tabs.indexOf(pane._3d_widget))
    assert tabs.isTabVisible(tabs.indexOf(pane._seq_widget))
    assert not tabs.isTabVisible(tabs.indexOf(pane._stat_container))
    # 3D built with no geometry, no crash.
    gl = pane._3d_widget.gl_widget
    assert len(gl.triangles) == 0 and len(gl.quads) == 0
