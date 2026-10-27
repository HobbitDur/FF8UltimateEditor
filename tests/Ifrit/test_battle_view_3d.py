"""Ifrit3D's "Battle view": the loaded model in a scene.out encounter, the free camera on the field.

The model stands on its encounter slot, turned the way the game turns a monster, with the engine's
root offset; the encounter's other enemies are drawn only from the models opened in the session
(else a post marks their slot). Unchecked, the model is alone at the origin again."""
import math
import struct
import sys
from pathlib import Path

import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[2]
SOLDIER = "extracted_files/battle/c0m071.dat"
BODY = "extracted_files/battle/d0c000.dat"
POSITIONS = ((-1100, 0, -2900), (1300, 0, -4200))


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def _scene(tmp_path):
    """scene.out with one encounter of two G-Soldiers (c0m071)."""
    raw = bytearray(128)
    raw[7] = 0xC0
    raw[0x38:0x3A] = bytes((71 + 16, 71 + 16))
    for index, position in enumerate(POSITIONS):
        struct.pack_into('<3h', raw, 8 + 6 * index, *position)
    scene = tmp_path / "scene.out"
    scene.write_bytes(raw)
    return scene


def _pane(tmp_path, path, scene=None):
    """Ifrit with `path` opened (and scene.out, through the session's files like the header's
    Import complementary), its 3D tab loaded."""
    from PyQt6.QtCore import QSettings
    from Ifrit.ifritmonsterwidget import IfritMonsterWidget
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    widget = IfritMonsterWidget(settings=settings, icon_path="Resources", game_data_folder="FF8GameData")
    widget._ask_ram_budget = lambda *a: True
    if scene is not None:
        widget.file_registry.open_file("scene.out", str(scene))
    widget.load_file(str(ROOT / path))
    return widget, _view(widget, 0)


def _view(widget, index):
    pane = widget._files[index]['pane']
    pane._load_tab(pane._3d_widget)
    return pane._3d_widget


@pytest.mark.ff8data(SOLDIER)
def test_monster_stands_on_its_slot_and_comes_back_alone(qapp, tmp_path):
    from Ifrit.IfritCameraSeq.battlepreview import model_root
    widget, view = _pane(tmp_path, SOLDIER, _scene(tmp_path))
    gl = view.gl_widget
    assert view._battle_view_cb is not None and not view.battle_view_active()

    view._battle_view_cb.setChecked(True)
    picker = view._battle_view.setup.encounters
    picker.encounter.setCurrentIndex(1)                 # the encounter, on its first soldier
    assert picker.selected_slot.slot_index == 0
    setup = view._battle_view.setup

    position, yaw = gl._preview_model_transform
    assert np.allclose(position, setup.to_viewer(POSITIONS[0]))
    assert yaw == pytest.approx(math.degrees(-math.pi))  # a monster faces the party
    assert np.allclose(gl.model_translation, model_root(view.ifrit_manager, view.current_anim_id, view.current_frame))

    # The other soldier is the model's own file, drawn; the 3 party slots are posts
    assert gl._preview_actor is not None
    markers = gl._preview_slots[0]
    assert len(markers) == 3
    assert all(abs(point[1]) < 1e-6 for point in markers)   # on the ground
    assert gl._preview_slots[2] is not None                 # and the ground grid

    # The camera orbits the field, not the model
    assert not np.allclose(gl.reference_position, (0., 0., 0.))

    # A frame step keeps the model on its slot, with the root of that frame
    view.set_frame(min(3, view.get_max_frames() - 1))
    assert np.allclose(gl._preview_model_transform[0], setup.to_viewer(POSITIONS[0]))
    assert np.allclose(gl.model_translation, model_root(view.ifrit_manager, view.current_anim_id, view.current_frame))

    view._battle_view_cb.setChecked(False)
    assert gl._preview_model_transform == ((0., 0., 0.), 0.)
    assert gl._preview_actor is None and gl._preview_slots[0] == ()   # no posts; the ground is its own
    widget.close()


@pytest.mark.ff8data(SOLDIER, BODY)
def test_party_member_drawn_when_opened(qapp, tmp_path):
    """Opening Squall shows him (the file list switches to him); back on the soldier, the battle
    view is still on, on the same encounter, and Squall stands in the party's player slot."""
    widget, view = _pane(tmp_path, SOLDIER, _scene(tmp_path))
    view._battle_view_cb.setChecked(True)
    view._battle_view.setup.encounters.encounter.setCurrentIndex(1)
    assert len(view.gl_widget._preview_slots[0]) == 3

    widget._append_to_session([str(ROOT / BODY)])             # Squall opened in the session
    widget._activate_index(0)                                  # back to the soldier: a new pane
    view = _view(widget, 0)
    assert view.battle_view_active()
    assert view._battle_view.setup.encounters.selected.index == 0
    assert len(view.gl_widget._preview_slots[0]) == 0         # the party is Squall alone, drawn
    assert view._battle_view.setup.cast.party_members()[0][0] == str(ROOT / BODY)
    widget.close()


@pytest.mark.ff8data(SOLDIER)
def test_manual_placement_without_scene_out(qapp, tmp_path):
    widget, view = _pane(tmp_path, SOLDIER)
    view._battle_view_cb.setChecked(True)
    position, yaw = view.gl_widget._preview_model_transform
    assert np.allclose(position, (0., 0., 0.)) and yaw == pytest.approx(math.degrees(-math.pi))
    widget.close()


@pytest.mark.ff8data("extracted_files/battle/d0w000.dat")
def test_weapons_have_no_battle_view(qapp, tmp_path):
    widget, view = _pane(tmp_path, "extracted_files/battle/d0w000.dat")
    assert view._battle_view_cb is None
    widget.close()


@pytest.mark.ff8data(SOLDIER)
def test_ground_toggle_in_both_views(qapp, tmp_path):
    """The model alone stands on the engine's ground (its feet at frame 0); "Ground" off hides it,
    in the model view and in the battle view."""
    widget, view = _pane(tmp_path, SOLDIER, _scene(tmp_path))
    gl = view.gl_widget
    view.cb_ground.setChecked(True)
    view.set_frame(0)
    assert gl._preview_slots[2] is not None
    feet = np.asarray(view.ifrit_manager.get_animated_vertices(view.current_anim_id, 0))[:, 1].min()
    assert feet + gl.model_translation[1] == pytest.approx(gl._preview_ground_y, abs=0.05)

    view.cb_ground.setChecked(False)
    assert gl._preview_slots[2] is None

    view._battle_view_cb.setChecked(True)
    view._battle_view.setup.encounters.encounter.setCurrentIndex(1)
    assert gl._preview_slots[2] is None and len(gl._preview_slots[0]) == 3   # the posts stay
    view.cb_ground.setChecked(True)
    assert gl._preview_slots[2] is not None and gl._preview_ground_y == 0.
    widget.close()


@pytest.mark.ff8data(SOLDIER)
def test_ground_keeps_its_size_while_the_animation_plays(qapp, tmp_path):
    """The grid is sized once on the loaded model: the canvas' MODEL_SIZE follows each posed frame's
    bounds, and a grid sized on it stretched while the animation played."""
    widget, view = _pane(tmp_path, SOLDIER)
    gl = view.gl_widget
    view.cb_ground.setChecked(True)
    grids, sizes = set(), set()
    for frame in range(view.get_max_frames()):
        view.set_frame(frame)
        view.update_animated_mesh()
        grids.add((gl._preview_slots[2], gl._preview_slots[3], gl._preview_ground_y))
        sizes.add(round(float(gl.MODEL_SIZE), 4))
    assert len(sizes) > 1          # the pose's bounds do change...
    assert len(grids) == 1         # ...the ground does not
    widget.close()
