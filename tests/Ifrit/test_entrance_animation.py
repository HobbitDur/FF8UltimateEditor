"""The battle-entrance animation (character body section 7, weapon section 8, Edea section 10)
listed and played in Ifrit's 3D tab, read-only, without touching the saved bytes."""
import os
import sys

import pytest

BATTLE = "extracted_files/battle"


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


def _manager(name):
    path = os.path.join(BATTLE, f"{name}.dat")
    if not os.path.isfile(path):
        pytest.skip("needs the game's battle files in extracted_files/battle")
    from Ifrit.ifritmanager import IfritManager
    manager = IfritManager("FF8GameData")
    manager.init_from_file(os.path.abspath(path))
    manager._ensure_matrices()
    return manager


def _saved_bytes(manager):
    return bytes(manager.enemy.get_bytes(manager.game_data))


def _untouched_save(name):
    """What saving the file gives when the entrance was never shown (section 3 re-encodes
    with zeroed alignment slack, so this is the reference, not the file itself)."""
    return _saved_bytes(_manager(name))


@pytest.mark.parametrize("name, section", [("d0c000", 7), ("d0w000", 8), ("d1c003", 7),
                                           ("d7c016", 10)])
def test_entrance_view_holds_the_extra_block(qapp, name, section):
    from FF8GameData.monsterdata import AnimationSection
    manager = _manager(name)
    assert manager.entrance_section_index() == section
    raw = bytes(manager.enemy.section_raw_data[section])
    view = manager.make_entrance_view()
    assert view is not None and view is not manager and view.enemy is not manager.enemy

    entrance = view.enemy.animation_data
    expected = AnimationSection()
    expected.analyze(raw, manager.enemy.bone_data)
    assert entrance.nb_animations == expected.nb_animations >= 1
    assert [a.get_nb_frame() for a in entrance.animations] == \
           [a.get_nb_frame() for a in expected.animations]
    assert entrance.animations[0].get_nb_frame() > 1
    # Same model: only the animation list differs.
    assert view.enemy.bone_data is manager.enemy.bone_data
    assert view.enemy.geometry_data is manager.enemy.geometry_data
    assert manager.enemy.animation_data is not entrance
    # The block re-encodes byte-exact, and is posable on the file's skeleton.
    assert bytes(expected.to_binary()) == raw
    verts = view.get_animated_vertices(anim_id=0, frame_id=0)
    assert len(verts) == len(manager.get_animated_vertices(anim_id=0, frame_id=0))
    # Showing it changes nothing in the saved file; the block's raw bytes are written as read.
    saved = _saved_bytes(manager)
    assert saved == _untouched_save(name)
    assert raw in saved


def test_reduced_weapon_has_no_entrance(qapp):
    manager = _manager("d1w008")      # Zell's gloves: posed by the body's bones
    assert manager.entrance_section_index() is None
    assert manager.make_entrance_view() is None


def test_3d_tab_lists_and_plays_the_entrance_with_the_weapon(qapp):
    from Ifrit.Ifrit3D.ifrit3dwidget import Ifrit3DWidget
    body, weapon = _manager("d0c000"), _manager("d0w000")
    widget = Ifrit3DWidget(body, show_controls=True)
    widget.load_file()
    widget.set_weapon_options([("None", None), ("d0w000", weapon)], default_index=1)
    nb = len(body.enemy.animation_data.animations)
    selector = widget.anim_selector
    assert selector.maximum() == nb                      # the extra entry after the animations
    assert selector.textFromValue(nb) == "Entrance (section 7)"
    assert selector.textFromValue(nb - 1) == str(nb - 1)

    selector.setValue(nb)
    entrance_frames = body.make_entrance_view().enemy.animation_data.animations[0].get_nb_frame()
    assert widget.ifrit_manager is not body and widget.current_anim_id == 0
    assert widget.get_max_frames() == entrance_frames
    # The weapon plays its own section 8 entrance in lockstep.
    shown_weapon = widget._weapon_manager
    assert shown_weapon is not weapon and shown_weapon.enemy.section_raw_data is weapon.enemy.section_raw_data
    assert shown_weapon.enemy.animation_data.nb_animations >= 1
    widget.set_frame(entrance_frames // 2)
    widget.update_animated_mesh()
    assert len(widget._current_weapon_verts()) == len(weapon.enemy.geometry_data.get_vertices())
    assert not widget.anim_tools_btn.isEnabled()        # read-only view

    # Switching weapon keeps the entrance on the new one too.
    widget.weapon_selector.setCurrentIndex(0)
    assert widget._weapon_manager is None
    widget.weapon_selector.setCurrentIndex(1)
    assert widget._weapon_manager is not weapon

    # Back to a section 3 animation: the real managers are back.
    selector.setValue(3)
    assert widget.ifrit_manager is body and widget._weapon_manager is weapon
    assert widget.current_anim_id == 3 and widget.anim_tools_btn.isEnabled()
    assert widget.get_max_frames() == body.enemy.animation_data.animations[3].get_nb_frame()

    # A reload while the entrance is shown goes back to the real file first.
    selector.setValue(nb)
    widget.load_file(keep_view=True)
    assert widget.ifrit_manager is body
    assert _saved_bytes(body) == _untouched_save("d0c000")
    widget.deleteLater()
