"""Composite character rendering: a character body (dXcYYY) can show its weapon (dXwYYY) in the
SAME 3D viewer, both played on the same animation index. See the CompositeCharacterWeaponAnimation
wiki. The two models are merged into one mesh pushed to the GL widget (weapon vertex indices
offset past the body's, weapon texture ids offset above the body's), reusing the single-model
render path. These tests cover the data merge + the selector wiring (the GL paint itself needs a
real context and is verified visually).
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QSettings
_APP = QApplication.instance() or QApplication([])

from FF8GameData.monsterdata import EntityType
from Ifrit.ifritmanager import IfritManager
from Ifrit.ifritmonsterwidget import IfritMonsterWidget

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BATTLE = os.path.join(REPO, "extracted_files", "battle")
BODY = os.path.join(BATTLE, "d0c000.dat")   # Squall body
WEAPON = os.path.join(BATTLE, "d0w000.dat")  # Squall's Revolver gunblade

pytestmark = pytest.mark.skipif(
    not (os.path.isfile(BODY) and os.path.isfile(WEAPON) and os.path.getsize(WEAPON) > 0),
    reason="d0c000.dat / d0w000.dat not available")


def test_character_slot_correspondence():
    assert IfritManager.character_slot_of("d0c000.dat") == "0"
    assert IfritManager.character_slot_of("d0w000.dat") == "0"
    assert IfritManager.character_slot_of("d1c003.dat") == "1"      # Zell
    assert IfritManager.character_slot_of("c0m000.dat") is None      # monster
    # a body and weapon correspond iff their slot digit matches
    assert IfritManager.character_slot_of("d0c000.dat") == IfritManager.character_slot_of("d0w006.dat")
    assert IfritManager.character_slot_of("d0c000.dat") != IfritManager.character_slot_of("d1w008.dat")


@pytest.fixture(scope="module")
def session():
    base = IfritManager("FF8GameData")
    w = IfritMonsterWidget(settings=QSettings("test", "weapon_overlay"),
                           icon_path="Resources", game_data_folder="FF8GameData")
    w._game_data = base.game_data
    w._ask_ram_budget = lambda *a: True
    w._build_session([BODY, WEAPON])
    names = [os.path.basename(f['path']) for f in w._files]
    w._activate_index(names.index("d0c000.dat"))
    pane = w._files[names.index("d0c000.dat")]['pane']
    return w, pane


def test_weapon_auto_paired_and_listed(session):
    _, pane = session
    sel = pane._3d_widget.weapon_selector
    labels = [sel.itemText(i) for i in range(sel.count())]
    assert labels[0].startswith("None")
    assert "d0w000.dat" in labels
    # auto-defaults to the character's first weapon, not None
    assert sel.currentText() == "d0w000.dat"
    assert pane._3d_widget._weapon_manager is not None
    assert pane._3d_widget._weapon_manager.enemy.entity_type == EntityType.WEAPON


def test_merged_mesh_is_body_plus_weapon(session):
    _, pane = session
    w3d = pane._3d_widget
    gl = w3d.gl_widget
    nb_body_v = len(pane.ifrit_manager.enemy.geometry_data.get_vertices())
    nb_weap_v = len(w3d._weapon_manager.enemy.geometry_data.get_vertices())
    assert len(gl.vertices) == nb_body_v + nb_weap_v
    # the weapon's faces reference vertices past the body's block
    max_idx = max(i for tri in gl.triangles for i in tri)
    assert max_idx >= nb_body_v
    # texture atlas covers both models with no out-of-range index
    assert gl._tex_id_to_index
    assert max(gl._tex_id_to_index.values()) < len(gl._pending_qpixmaps)


def test_selector_toggles_body_only_and_back(session):
    _, pane = session
    w3d = pane._3d_widget
    gl = w3d.gl_widget
    nb_body_v = len(pane.ifrit_manager.enemy.geometry_data.get_vertices())

    w3d.weapon_selector.setCurrentIndex(0)               # None (body only)
    assert w3d._weapon_manager is None
    assert len(gl.vertices) == nb_body_v

    w3d.weapon_selector.setCurrentIndex(1)               # back to the weapon
    assert w3d._weapon_manager is not None
    assert len(gl.vertices) > nb_body_v


def test_monster_has_no_weapon_selector():
    """A monster/weapon body must not get the composite selector (character bodies only)."""
    monster = os.path.join(BATTLE, "c0m000.dat")
    if not os.path.isfile(monster):
        pytest.skip("c0m000.dat not available")
    base = IfritManager("FF8GameData")
    w = IfritMonsterWidget(settings=QSettings("test", "weapon_overlay_monster"),
                           icon_path="Resources", game_data_folder="FF8GameData")
    w._game_data = base.game_data
    w._ask_ram_budget = lambda *a: True
    w._build_session([monster])
    pane = w._files[0]['pane']
    # no options populated -> single-model viewer, weapon manager stays None
    assert pane._3d_widget._weapon_manager is None
