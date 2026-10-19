"""Fujin's Camera effect editor 3D preview: caster/target models, the script inputs, the slot
▶ Preview buttons and live keyframe edits, all wired to the shared battle camera preview."""
import sys
from pathlib import Path

import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[2]
EXE = "extracted_files/FF8_EN.exe"
SQUALL = "extracted_files/battle/d0c000.dat"
SOLDIER = "extracted_files/battle/c0m071.dat"
CURE, PHOENIX_DOWN = 1, 5


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def fujin(qapp):
    from Fujin.fujinwidget import FujinWidget
    return FujinWidget()


def test_preview_hooks_without_models(fujin):
    from Fujin.cameraeffectpreview import MODEL_SELECTION_KEY
    preview = fujin.camera_editor.preview
    assert preview.panel is None and "Import" in preview.placeholder.text()
    assert [label for label, _callback in fujin.complementary_entries()][0].startswith("Camera preview")
    sources = fujin.auto_import_sources()
    assert any(source.selection_key == MODEL_SELECTION_KEY and source.selection_only for source in sources)
    preview.add_models(["d0w000.dat", "notamodel.dat"])  # weapons and other files are not offered
    assert preview.model_paths() == [] and preview.panel is None


@pytest.mark.ff8data(EXE, SQUALL, SOLDIER)
def test_effect_camera_plays_around_caster_and_target(fujin):
    from FF8GameData.dat.camerascript import camera_animation_at
    editor = fujin.camera_editor
    preview = editor.preview
    files = {path: (ROOT / path).read_bytes() for path in (EXE, SQUALL, SOLDIER)}
    editor.exe_binding.open_path(EXE)
    editor.select_effect(CURE)
    track = editor.manager.track(CURE)
    assert preview.track is track and "animation <b>23</b>" in preview.result_label.text()

    # Caster = the character, target = the monster, whatever the import order
    preview.add_models([str(ROOT / SOLDIER), str(ROOT / SQUALL)])
    panel = preview.panel
    panel._timer.stop()
    assert Path(preview.caster_path()).name == "d0c000.dat"
    assert Path(preview.target_path()).name == "c0m071.dat"
    setup = panel._battle_setup
    assert setup.opponent is preview.model(preview.target_path()) and setup.role.currentIndex() == 0
    assert (preview.attacker_spin.value(), preview.target_slot_spin.value()) == (0, 3)
    assert (setup.caster_slot.value(), setup.target_slot.value()) == (0, 3)
    assert preview.previewed is camera_animation_at(track.collection, 23)
    assert panel._animation is preview.previewed and len(panel._poses) > 1
    assert panel._gl._preview_actor is not None             # the target is drawn

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


@pytest.mark.ff8data(EXE, SOLDIER)
def test_monster_caster_defaults(fujin):
    editor = fujin.camera_editor
    preview = editor.preview
    editor.exe_binding.open_path(EXE)
    editor.select_effect(CURE)
    preview.add_models([str(ROOT / SOLDIER)])
    preview.panel._timer.stop()
    assert preview.target_path() is None                    # no second model: a marker
    assert (preview.opening_spin.value(), preview.attacker_spin.value(),
            preview.target_slot_spin.value()) == (8, 3, 0)
    assert preview.last_run.chosen is not None and preview.panel._animation is preview.previewed
