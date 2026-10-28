"""The battle-entrance animation (character body section 7, weapon section 8, Edea section 10):
its own "N - Entrance" tab in Ifrit, edited like section 3 and saved with the file."""
import os
import sys

import pytest

BATTLE = "extracted_files/battle"


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


def _path(name):
    path = os.path.join(BATTLE, f"{name}.dat")
    if not os.path.isfile(path):
        pytest.skip("needs the game's battle files in extracted_files/battle")
    return os.path.abspath(path)


def _manager(name):
    from Ifrit.ifritmanager import IfritManager
    manager = IfritManager("FF8GameData")
    manager.init_from_file(_path(name))
    manager._ensure_matrices()
    return manager


def _saved_bytes(manager):
    return bytes(manager.enemy.get_bytes(manager.game_data))


def _untouched_save(name):
    """What saving gives when the entrance was never parsed (section 3 re-encodes with zeroed
    alignment slack, so this is the reference, not the file itself)."""
    return _saved_bytes(_manager(name))


@pytest.mark.parametrize("name, section", [("d0c000", 7), ("d0w000", 8), ("d1c003", 7),
                                           ("d7c016", 10)])
def test_entrance_view_is_the_extra_block_and_saves_byte_exact(qapp, name, section):
    from FF8GameData.monsterdata import AnimationSection
    manager = _manager(name)
    assert manager.entrance_section_index() == section
    raw = bytes(manager.enemy.section_raw_data[section])
    view = manager.entrance_view()

    entrance = view.enemy.animation_data
    expected = AnimationSection()
    expected.analyze(raw, manager.enemy.bone_data)
    assert entrance is manager.enemy.entrance_animation_data
    assert entrance.nb_animations == expected.nb_animations == 1
    assert entrance.animations[0].get_nb_frame() == expected.animations[0].get_nb_frame() > 1
    # Same file: everything but the animation list is the manager's own.
    assert view.enemy.bone_data is manager.enemy.bone_data
    assert view.enemy.geometry_data is manager.enemy.geometry_data
    assert view.game_data is manager.game_data
    assert manager.enemy.animation_data is not entrance
    verts = view.get_animated_vertices(anim_id=0, frame_id=0)
    assert len(verts) == len(manager.get_animated_vertices(anim_id=0, frame_id=0))
    # Parsed and re-encoded on save: unchanged bytes.
    saved = _saved_bytes(manager)
    assert saved == _untouched_save(name)
    assert raw in saved


def test_reduced_weapon_has_no_entrance(qapp):
    manager = _manager("d1w008")      # Zell's gloves: posed by the body's bones
    assert manager.entrance_section_index() is None
    assert manager.entrance_view().enemy.animation_data.nb_animations == 0


def test_entrance_edit_is_saved_and_undoable(qapp, tmp_path):
    from FF8GameData.dat.monsteranalyser import MonsterAnalyser
    manager = _manager("d0c000")
    before = _saved_bytes(manager)
    view = manager.entrance_view()
    rotation = view.enemy.animation_data.animations[0].frames[10].rotation_vector_data[3]
    original = [axis.get_rotate_deg() for axis in rotation]
    view.set_animation_frame_bone_rotation(0, 10, 3, original[0] + 30.0, original[1], original[2])
    # main animations untouched, the entrance changed
    path = tmp_path / "d0c000.dat"
    manager.save_file(str(path))
    saved = MonsterAnalyser(manager.game_data)
    saved.load_file_data(str(path), manager.game_data)
    saved.analyse_loaded_data(manager.game_data)
    assert saved.section_raw_data[3] == manager.enemy.section_raw_data[3]
    reread = saved.ensure_entrance_animation().animations[0].frames[10].rotation_vector_data[3]
    assert abs(reread[0].get_rotate_deg() - (original[0] + 30.0)) % 360 < 0.1
    # Undo (section-targeted restore) puts the old block back into the SAME object.
    entrance = manager.enemy.entrance_animation_data
    manager.enemy.restore_sections_from_snapshot(before, [7], manager.game_data)
    assert manager.enemy.entrance_animation_data is entrance
    back = entrance.animations[0].frames[10].rotation_vector_data[3]
    assert [axis.get_rotate_deg() for axis in back] == pytest.approx(original)
    assert _saved_bytes(manager) == before


def test_new_bone_reshapes_both_blocks(qapp):
    manager = _manager("d0c000")
    entrance = manager.entrance_view().enemy.animation_data
    nb_bones = len(manager.enemy.bone_data.bones)
    manager.add_bone(parent_id=0)
    assert len(entrance.animations[0].frames[0].rotation_vector_data) == nb_bones + 1
    assert len(manager.enemy.animation_data.animations[0].frames[0].rotation_vector_data) == nb_bones + 1


def test_dat30_conversion_converts_the_parsed_block(qapp):
    from FF8GameData.dat.dat30 import convert_extra_animation_block
    manager = _manager("d0c000")
    entrance = manager.entrance_view().enemy.animation_data
    nb_frame = entrance.animations[0].get_nb_frame()
    assert convert_extra_animation_block(manager.enemy) == 1
    assert manager.enemy.entrance_animation_data is entrance
    assert entrance.animations[0].get_nb_frame() == 2 * nb_frame
    assert manager.enemy.ensure_entrance_animation().animations[0].get_nb_frame() == 2 * nb_frame
    saved = _saved_bytes(manager)
    assert bytes(entrance.to_binary()) in saved


@pytest.mark.parametrize("name, label", [("d0c000", "7 - Entrance"), ("d1c003", "7 - Entrance"),
                                         ("d7c016", "10 - Entrance"), ("d0w000", "8 - Entrance")])
def test_pane_has_an_entrance_tab(qapp, name, label):
    from PyQt6.QtCore import QSettings
    from Ifrit.ifritmonsterwidget import IfritFilePane
    manager = _manager(name)
    pane = IfritFilePane(manager, _path(name), QSettings("FF8UltimateEditorTest", "entrance"))
    tabs = pane._tabs
    index = tabs.indexOf(pane._entrance_widget)
    assert tabs.isTabVisible(index) and tabs.tabText(index) == label
    widget = pane._entrance_widget
    assert widget.ifrit_manager.enemy.animation_data is manager.enemy.entrance_animation_data
    assert widget.get_max_frames() == manager.enemy.entrance_animation_data.animations[0].get_nb_frame()
    assert all(action.isVisible() for action in widget._animation_list_actions)   # every 3D option
    # Editing it is an edit of the 3D sections and of the entrance section.
    section = manager.entrance_section_index()
    assert set(pane._sections_for_tab(widget)) == {1, 2, 3, section}
    pane.deleteLater()


def test_monster_pane_hides_the_entrance_tab(qapp):
    from PyQt6.QtCore import QSettings
    from Ifrit.ifritmonsterwidget import IfritFilePane
    manager = _manager("c0m001")
    pane = IfritFilePane(manager, _path("c0m001"), QSettings("FF8UltimateEditorTest", "entrance"))
    assert not pane._tabs.isTabVisible(pane._tabs.indexOf(pane._entrance_widget))
    pane.deleteLater()


def test_entrance_tab_plays_the_weapon_entrance_in_lockstep(qapp):
    from Ifrit.Ifrit3D.entrance3dwidget import Entrance3DWidget
    body, weapon = _manager("d0c000"), _manager("d0w000")
    widget = Entrance3DWidget(body.entrance_view(), show_controls=True)
    widget.load_file()
    widget.set_weapon_options([("None", None), ("d0w000", weapon.entrance_view())], default_index=1)
    shown = widget._weapon_manager
    assert shown.enemy.animation_data is weapon.enemy.entrance_animation_data
    assert widget.get_max_frames() == body.enemy.entrance_animation_data.animations[0].get_nb_frame()
    widget.set_frame(widget.get_max_frames() // 2)
    assert len(widget._current_weapon_verts()) == len(weapon.enemy.geometry_data.get_vertices())
    widget.deleteLater()


def test_3d_and_entrance_tabs_share_their_view_toggles(qapp):
    from PyQt6.QtCore import QSettings
    from Ifrit.ifritmonsterwidget import IfritFilePane
    settings = QSettings("FF8UltimateEditor", "FF8UltimateEditor")
    keys = ("ifrit/3d/show_skeleton", "ifrit/3d/show_wireframe", "ifrit/3d/show_gizmo")
    saved = {key: settings.value(key) for key in keys}     # the user's own, put back after
    try:
        manager = _manager("d0c000")
        pane = IfritFilePane(manager, _path("d0c000"), QSettings("FF8UltimateEditorTest", "entrance"))
        main, entrance = pane._3d_widget, pane._entrance_widget
        for name in ("cb_skeleton", "cb_wire", "_gizmo_action"):
            first, second = getattr(main, name), getattr(entrance, name)
            assert first.isChecked() == second.isChecked()
            first.setChecked(not first.isChecked())
            assert second.isChecked() == first.isChecked()
            second.setChecked(not second.isChecked())                       # and the other way
            assert first.isChecked() == second.isChecked()
        assert entrance.gl_widget.show_skeleton == main.cb_skeleton.isChecked()
        main.fps_slider.setValue(30)
        assert entrance.fps_slider.value() == 30
        pane.deleteLater()
    finally:
        for key, value in saved.items():
            if value is None:
                settings.remove(key)
            else:
                settings.setValue(key, value)


def test_entrance_view_plays_its_animations_once_and_never_splits(qapp):
    from FF8GameData.dat.animloopdetector import ANIM_ONE_SHOT
    from Ifrit.Ifrit3D.entrance3dwidget import Entrance3DWidget
    body = _manager("d0c000")
    widget = Entrance3DWidget(body.entrance_view(), show_controls=True)
    widget.load_file()
    nb_animations = len(body.enemy.entrance_animation_data.animations)
    # Section 3's sequences say nothing of this block: it is played once, out of Slow's reach.
    assert widget._get_animation_kind_dict() == {anim_id: ANIM_ONE_SHOT for anim_id in range(nb_animations)}
    assert widget._get_max_animation_frames(0) == getattr(body, 'max_animation_frames', 255)
    report, reason = widget._split_animation_to_fit(0, 2, False, 255)
    assert report is None and reason
    widget.deleteLater()


def test_entrance_whole_file_30fps_goes_through_the_3d_tab(qapp):
    from PyQt6.QtCore import QSettings
    from Ifrit.ifritmonsterwidget import IfritFilePane
    manager = _manager("d0c000")
    pane = IfritFilePane(manager, _path("d0c000"), QSettings("FF8UltimateEditorTest", "entrance"))
    assert pane._entrance_widget.real30_handler == pane._3d_widget._convert_loaded_file_to_real30
    pane.deleteLater()
