"""Skeleton and animation editing of the battle models inside MAG files (Fujin.modeledit): every
vanilla model gives its bytes back untouched, bone and frame edits land in place, the other
animations keep their exact bytes, and an edit that would grow the MAG is refused."""
import glob
import shutil
import sys
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from Fujin.magdocument import MagDocument

ROOT = Path(__file__).resolve().parents[2]
SHIVA = "extracted_files/magic/MAG005_B.01"          # embedded model, 39 bones, 4 animations
EDEN_PART = "extracted_files/battle/mag186_b.dat"     # indexed container, 7 animations
TIGHT = "extracted_files/magic/MAG203_B.01"           # no slack at all in its animation section


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def models(path):
    from Fujin.modeledit import EmbeddedModel
    from Fujin.objectview import model_sources
    document = MagDocument()
    document.load_file(str(path))
    result = []
    for _label, kind, payload in model_sources(document.data, document.document):
        if kind == "model":
            container, object_id = payload
            obj = next(o for o in container.objects if o.index == object_id)
            result.append(EmbeddedModel(document.data, obj.info["sections"], obj.offset + obj.info["size"]))
    return document, result


@pytest.mark.ff8data(SHIVA, EDEN_PART)
def test_every_vanilla_model_round_trips(qapp):
    files = sorted(glob.glob(str(ROOT / "extracted_files/magic/*")) + glob.glob(str(ROOT / "extracted_files/battle/mag*")))
    count = 0
    for path in files:
        try:
            document, found = models(path)
        except Exception:      # noqa: BLE001 - files that are not MAG documents
            continue
        data = bytes(document.data)
        for model in found:
            count += 1
            for index in range(len(model.bones)):
                offset, raw = model.set_bone(index)
                assert data[offset:offset + len(raw)] == raw, (path, index)
            offset, raw = model.animation_patch()
            assert data[offset:offset + len(raw)] == raw, path
            cores = model._cores(model._animation_slices())
            for animation, core in zip(model.animations, cores):       # re-encoded: same length
                tail, animation.original_tail = animation.original_tail, b""
                assert len(animation.to_binary()) == len(core), path
                animation.original_tail = tail
    assert count >= 28


@pytest.mark.ff8data(SHIVA)
def test_bone_edit_in_place(qapp):
    document, (model,) = models(ROOT / SHIVA)
    bone = model.bones[3]
    length, rotation = bone.get_size_raw() + 100, (bone._rotX + 50, bone._rotY, bone._rotZ - 20)
    offset, raw = model.set_bone(3, length, rotation)
    assert offset == model.skeleton + 16 + 48 * 3 and len(raw) == 48
    document.patch_bytes(offset, raw)
    _again, (edited,) = models_from_bytes(document)
    assert edited.bones[3].get_size_raw() == length and (edited.bones[3]._rotX, edited.bones[3]._rotZ) == (rotation[0], rotation[2])
    with pytest.raises(ValueError, match="16-bit"):
        model.set_bone(3, 40000)


def models_from_bytes(document):
    from Fujin.modeledit import EmbeddedModel
    from Fujin.objectview import model_sources
    result = []
    for _label, kind, payload in model_sources(document.data, document.document):
        if kind == "model":
            container, object_id = payload
            obj = next(o for o in container.objects if o.index == object_id)
            result.append(EmbeddedModel(document.data, obj.info["sections"], obj.offset + obj.info["size"]))
    return document, result


@pytest.mark.ff8data(EDEN_PART)
def test_frame_edit_keeps_the_other_animations(qapp):
    document, (model,) = models(ROOT / EDEN_PART)
    before = model._animation_slices()
    frame = model.animations[2].frames[1]
    raw = int(frame.rotation_vector_data[4][1].get_rotate_raw())
    model.set_frame(2, 1, rotations={4: (int(frame.rotation_vector_data[4][0].get_rotate_raw()), raw + 1,
                                         int(frame.rotation_vector_data[4][2].get_rotate_raw()))})
    offset, data = model.animation_patch()
    document.patch_bytes(offset, data)
    _again, (edited,) = models_from_bytes(document)
    assert int(edited.animations[2].frames[1].rotation_vector_data[4][1].get_rotate_raw()) == raw + 1
    after = edited._animation_slices()
    for index in range(len(before)):
        if index != 2:
            assert edited._cores(after)[index] == model._cores(before)[index]     # byte for byte
    assert len(document.data) == len(document.original)


@pytest.mark.ff8data(TIGHT)
def test_an_edit_that_would_grow_the_mag_is_refused(qapp):
    _document, (model,) = models(ROOT / TIGHT)
    assert model.free_bytes() == 0
    animation = max(range(len(model.animations)), key=lambda a: len(model.animations[a].frames))
    middle = len(model.animations[animation].frames) // 2
    model.set_frame(animation, middle, rotations={bone: (1000, -1000, 1000) for bone in range(len(model.bones))})
    with pytest.raises(ValueError, match="more bytes than its section has"):
        model.animation_patch()


@pytest.mark.ff8data(SHIVA)
def test_models_tab_skeleton_and_pose_tables(qapp, tmp_path, monkeypatch):
    from Fujin.objectview import MagObjectView
    warnings = []
    monkeypatch.setattr("Fujin.objectview.QMessageBox.warning", lambda *args: warnings.append(args[2]))
    path = tmp_path / Path(SHIVA).name
    shutil.copyfile(ROOT / SHIVA, path)
    document = MagDocument()
    document.load_file(str(path))
    view = MagObjectView()
    view.set_manager(document)
    item = next(view.tree.topLevelItem(i) for i in range(view.tree.topLevelItemCount())
                if view.tree.topLevelItem(i).text(1) == "model")
    view.tree.setCurrentItem(item)
    assert view.model_edit.isVisibleTo(view) and view.skeleton_table.rowCount() == 39
    changes = []
    view.data_changed.connect(lambda: changes.append(1))
    view.skeleton_table.cellWidget(5, 2).setValue(view.skeleton_table.cellWidget(5, 2).value() + 64)
    assert document.modified and changes and len(document.data) == len(document.original)
    document.undo()
    assert not document.modified
    view.set_manager(document)
    view.tree.setCurrentItem(next(view.tree.topLevelItem(i) for i in range(view.tree.topLevelItemCount())
                                  if view.tree.topLevelItem(i).text(1) == "model"))
    view.model_edit.setCurrentIndex(1)
    view._fill_pose()
    assert view.pose_table.rowCount() == 40 and "Room left" in view.pose_label.text()
    spin = view.pose_table.cellWidget(3, 2)
    spin.setValue(spin.value() + 360 / 4096)                  # one raw unit on bone 2
    assert document.modified and not warnings and len(document.data) == len(document.original)
    assert view.model_edit.currentIndex() == 1 and view.pose_table.rowCount() == 40   # still on the pose
