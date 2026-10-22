"""Fujin's Camera effect editor 3D preview: Fujin feeds the shared battle camera preview (models,
party and weapons, scene.out encounter, caster/target slots); the script inputs, the slot
▶ Preview buttons and live keyframe edits drive what it plays."""
import struct
import sys
from pathlib import Path

import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[2]
EXE = "extracted_files/FF8_EN.exe"
SQUALL = "extracted_files/battle/d0c000.dat"
GUNBLADE = "extracted_files/battle/d0w000.dat"
ZELL = "extracted_files/battle/d1c003.dat"
GLOVES = "extracted_files/battle/d1w008.dat"   # a reduced weapon: no skeleton, posed by Zell's bones
SOLDIER = "extracted_files/battle/c0m071.dat"
CURE, PHOENIX_DOWN = 1, 5


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def fujin(qapp):
    from Fujin.fujinwidget import FujinWidget
    return FujinWidget()


def paths(*names):
    return [str(ROOT / name) for name in names]


def test_preview_hooks_without_models(fujin):
    from Fujin.cameraeffectpreview import MODEL_SELECTION_KEY
    preview = fujin.camera_editor.preview
    assert preview.panel is None and "Import" in preview.placeholder.text()
    labels = [label for label, _callback in fujin.complementary_entries()]
    assert labels[0].startswith("Camera preview models") and "scene.out" in labels[1]
    sources = fujin.auto_import_sources()
    assert any(source.selection_key == MODEL_SELECTION_KEY and source.selection_only
               and "d?w*.dat" in source.patterns for source in sources)
    assert any(source.exact_name == "scene.out" for source in sources)
    assert preview.sceneout_binding in fujin.file_bindings()
    preview.add_models(["notamodel.dat", "d0w000.dat"])  # a lone weapon has no one to hold it
    assert preview.model_paths() == ["d0w000.dat"] and preview.panel is None
    assert preview.caster_key() is None


def test_settings_fold_and_are_remembered(qapp):
    """The pickers and inputs fold away to give the 3D view the room, and stay folded next time."""
    from PyQt6.QtCore import QSettings
    from Common.fileregistry import FileRegistry
    from Fujin.cameraeffectpreview import SETTINGS_STATE_KEY
    from Fujin.fujinwidget import FujinWidget
    settings = QSettings("HobbitDur", "FF8UltimateEditor")   # isolated by the root conftest
    settings.remove(SETTINGS_STATE_KEY)
    registry = FileRegistry(settings=settings)
    fujin = FujinWidget(file_registry=registry)
    preview = fujin.camera_editor.preview
    section = preview.settings_section
    assert section.is_expanded() and section.isAncestorOf(preview.caster_combo)
    assert section.isAncestorOf(preview.party_combos[0]) and section.isAncestorOf(preview.inputs_section)
    assert not section.isAncestorOf(preview.result_label)   # what the script chose stays in sight
    section._toggle.click()
    assert not section.is_expanded() and settings.value(SETTINGS_STATE_KEY, type=bool) is False
    again = FujinWidget(file_registry=registry)
    assert not again.camera_editor.preview.settings_section.is_expanded()
    settings.remove(SETTINGS_STATE_KEY)


@pytest.mark.ff8data(EXE, SQUALL, GUNBLADE, SOLDIER)
def test_effect_camera_plays_around_caster_and_target(fujin):
    from FF8GameData.dat.camerascript import camera_animation_at
    editor = fujin.camera_editor
    preview = editor.preview
    files = {path: (ROOT / path).read_bytes() for path in (EXE, SQUALL, GUNBLADE, SOLDIER)}
    editor.exe_binding.open_path(EXE)
    editor.select_effect(CURE)
    track = editor.manager.track(CURE)
    assert preview.track is track and "animation <b>23</b>" in preview.result_label.text()

    # The character joins the party with its weapon and casts; the monster is the target
    preview.add_models(paths(SOLDIER, SQUALL, GUNBLADE))
    panel = preview.panel
    panel._timer.stop()
    setup = panel._battle_setup
    assert preview.party_members() == {0: (str(ROOT / SQUALL), str(ROOT / GUNBLADE))}
    assert preview.caster_key() == ("party", 0)
    assert preview.target_key() == ("monster", str(ROOT / SOLDIER))
    assert setup.opponent is preview.model(str(ROOT / SOLDIER)) and setup.role.currentIndex() == 0
    assert panel._weapon_manager is preview.model(str(ROOT / GUNBLADE))   # in the caster's hands
    assert preview.battle_slots() == (0, 3) == (setup.caster_slot.value(), setup.target_slot.value())
    assert setup.context.target.position == (0, 0, -5000)                   # the setup's own placement
    assert preview.previewed is camera_animation_at(track.collection, 23)
    assert panel._animation is preview.previewed and len(panel._poses) > 1
    assert panel._gl._preview_actor is not None                             # the target is drawn
    # Black bars and a frame line outside the game's 4:3 screen, not the scene's background
    assert panel._gl.letterbox_color == (0., 0., 0., 1.) and panel._gl.letterbox_outline_color is not None

    # Script inputs choose another animation
    preview.random_spin.setValue(1)
    panel._timer.stop()
    assert preview.last_run.chosen == 0 and panel._animation is track.collection.sets[0].animations[0]
    preview.opening_spin.setValue(-1)                       # no opening shot: no effect camera
    panel._timer.stop()
    assert preview.last_run.chosen is None and panel._empty_camera
    assert "no camera animation" in preview.result_label.text()
    preview.opening_spin.setValue(0)
    panel._timer.stop()

    # A slot's ▶ Preview plays it as is
    widget = editor._collection_widget
    slot = track.collection.sets[1].animations[7]
    widget.preview_requested.emit(slot)
    panel._timer.stop()
    assert panel._animation is slot and "Slot preview: set 1, slot 7" in preview.result_label.text()

    # Editing a keyframe of the shown animation replays it at once
    before = [pose.eye for pose in panel._poses]
    frame = slot.blocks[0].frames[0]
    widget._on_field_changed(frame.pos_x, frame.pos_x.get() + 2000)
    panel._timer.stop()
    assert panel._animation is slot
    assert not np.allclose(np.array(before[0]), np.array(panel._poses[0].eye))
    assert editor.has_changes()

    # An effect without a camera track empties the preview
    editor.select_effect(PHOENIX_DOWN)
    assert preview.track is None and panel._animation is None

    # Only the .hext is ever written: the exe and the models stay untouched
    assert all((ROOT / path).read_bytes() == data for path, data in files.items())


def _scene_out(tmp_path):
    """One encounter: two G-Soldiers (c0m071) at distinct positions."""
    raw = bytearray(128)
    raw[7] = 0xC0
    raw[0x38:0x3A] = bytes((71 + 16, 71 + 16))
    struct.pack_into('<3h', raw, 8, -1100, 77, -2900)
    struct.pack_into('<3h', raw, 14, 1300, 0, -4200)
    scene = tmp_path / "scene.out"
    scene.write_bytes(raw)
    return scene


@pytest.mark.ff8data(EXE, SQUALL, GUNBLADE, ZELL, GLOVES, SOLDIER)
def test_scene_out_places_party_and_enemies(fujin, tmp_path):
    from Ifrit.IfritCameraSeq.battlepreview import PARTY_FORMATIONS
    editor = fujin.camera_editor
    preview = editor.preview
    editor.exe_binding.open_path(EXE)
    editor.select_effect(CURE)
    preview.add_models(paths(SQUALL, GUNBLADE, ZELL, GLOVES, SOLDIER))
    preview.panel._timer.stop()
    assert set(preview.party_members()) == {0, 1}
    scene = _scene_out(tmp_path)
    fujin.file_registry.open_file("scene.out", str(scene))  # shared: the setup's picker loads it
    setup = preview.panel._battle_setup
    picker = setup.encounters
    picker.encounter.setCurrentIndex(1)
    preview.panel._timer.stop()
    # Fujin's party and Caster/Target place the actors, and the header toolbar opens the files:
    # the shared setup's own file buttons and slot controls are hidden here
    assert picker.open_button.isHidden() and all(button.isHidden() for button in setup.opponent_buttons)
    assert setup.role.isHidden() and setup.caster_slot.isHidden() and setup.party_size.isHidden()
    assert picker.enemy_slot.isHidden() and not picker.encounter.isHidden()

    # Enemies stand at their scene.out slots, the party in the game's formation
    labels = [preview.caster_combo.itemText(row) for row in range(preview.caster_combo.count())]
    assert labels[:2] == ["Party 0: d0c000.dat", "Party 1: d1c003.dat"]
    assert any(label.startswith("Enemy 4:") for label in labels)
    assert preview.caster_key() == ("party", 0) and preview.target_key() == ("enemy", 0)
    formation = PARTY_FORMATIONS[2]
    assert setup.context.caster.position == formation[0]
    assert setup.context.target.position == (-1100, 77, -2900)
    assert setup.context.slots[1].position == formation[1]
    assert setup.context.slots[4].position == (1300, 0, -4200)
    # Zell (party 1) is drawn with his gloves; Squall's gunblade is the main model's
    assert [weapon for weapon, _actor, _body in setup._scene_weapons] == [preview.model(str(ROOT / GLOVES))]
    mesh = setup.opponent_mesh(2, True)
    assert np.isfinite(mesh.vertices).all()

    # The other soldier as target: picked in Fujin, or with the picker's enemy slot
    preview.target_combo.setCurrentIndex(labels.index(next(l for l in labels if l.startswith("Enemy 4:"))) + 1)
    preview.panel._timer.stop()
    assert preview.battle_slots() == (0, 4) and setup.context.target.position == (1300, 0, -4200)

    # An enemy casts: the monster is filmed at its own slot, a party member is the target
    preview.caster_combo.setCurrentIndex(labels.index(next(l for l in labels if l.startswith("Enemy 4:"))))
    preview.panel._timer.stop()
    assert preview.caster_key() == ("enemy", 1) and preview.target_key()[0] == "party"
    assert setup.main_position == (1300, 0, -4200) and picker.selected_slot.slot_index == 1
    assert setup.context.caster.position == (1300, 0, -4200)
    assert preview.battle_slots()[0] == 4 and preview.opening_spin.value() == 8
    assert len(setup._scene_weapons) == 2                  # both party members hold their weapons
    assert preview.last_run is not None and preview.panel._animation is preview.previewed
    assert scene.read_bytes()[:8] == bytes(7) + b"\xC0"     # read-only


@pytest.mark.ff8data(EXE, SQUALL, SOLDIER)
def test_encounter_enemy_not_imported_is_a_named_marker(fujin, tmp_path):
    """Only Squall imported: the soldiers of the encounter are markers at their scene.out places,
    named in the status - the c0m071.dat beside scene.out (and Squall) is never read."""
    import shutil
    editor = fujin.camera_editor
    preview = editor.preview
    editor.exe_binding.open_path(EXE)
    editor.select_effect(CURE)
    preview.add_models(paths(SQUALL))
    preview.panel._timer.stop()
    scene = _scene_out(tmp_path)
    shutil.copy(ROOT / SOLDIER, tmp_path / "c0m071.dat")
    fujin.file_registry.open_file("scene.out", str(scene))
    setup = preview.panel._battle_setup
    picker = setup.encounters
    picker.encounter.setCurrentIndex(1)
    preview.panel._timer.stop()
    assert preview.caster_key() == ("party", 0) and preview.target_key() == ("enemy", 0)
    assert setup.context.target.position == (-1100, 77, -2900)
    assert setup.context.slots[4].position == (1300, 0, -4200)
    assert [manager for manager, _actor in setup._scene_mesh_actors] == []      # markers only
    assert "c0m071.dat: not imported" in picker.status.text()
    assert all("c0m071" not in path for path in preview._models)


@pytest.mark.ff8data(EXE, SOLDIER)
def test_monster_caster_defaults(fujin):
    editor = fujin.camera_editor
    preview = editor.preview
    editor.exe_binding.open_path(EXE)
    editor.select_effect(CURE)
    preview.add_models(paths(SOLDIER))
    preview.panel._timer.stop()
    assert preview.target_key() is None                     # no second model: a marker
    assert preview.opening_spin.value() == 8 and preview.battle_slots() == (3, 0)
    assert preview.last_run.chosen is not None and preview.panel._animation is preview.previewed


def test_party_member_casting_on_another_stands_beside_it(fujin):
    """Caster party 0, target party 1, no encounter: side by side in the battle formation (both
    facing the enemies), as in the game - not face to face."""
    from Ifrit.IfritCameraSeq.battlepreview import PARTY_FORMATIONS
    editor = fujin.camera_editor
    preview = editor.preview
    editor.exe_binding.open_path(EXE)
    editor.select_effect(CURE)
    preview.add_models(paths(SQUALL, GUNBLADE, ZELL, GLOVES))
    preview.panel._timer.stop()
    assert set(preview.party_members()) == {0, 1}
    target = next(row for row in range(preview.target_combo.count())
                  if preview.target_combo.itemData(row) == ("party", 1))
    preview.target_combo.setCurrentIndex(target)
    preview.panel._timer.stop()
    setup = preview.panel._battle_setup
    assert preview.battle_slots() == (0, 1) and setup.party_size.value() == 2
    context = setup.context
    np.testing.assert_allclose(context.target.position, np.subtract(PARTY_FORMATIONS[2][1], PARTY_FORMATIONS[2][0]))
    assert context.caster.yaw == context.target.yaw == 0.
