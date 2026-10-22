"""Fujin's Models tab edits through Blender: Export .glb, then Import .glb moves the vertices in
place (the MAG keeps its size). Meshes, morph targets and embedded battle models."""
import shutil
import struct
import sys
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from FF8GameData.gltf.glbbuilder import read_glb, write_glb
from FF8GameData.magcine.magcontainer import MagContainer
from Fujin.magdocument import MagDocument

ROOT = Path(__file__).resolve().parents[2]
MESHES = "extracted_files/magic/MAG230_B.00"
MODEL = "extracted_files/magic/MAG005_B.01"      # Shiva's .01: one embedded battle model


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def _shift_positions(path, dx):
    """The .glb with every POSITION moved by dx along X (what a Blender edit does to it)."""
    gltf, binary = read_glb(path)
    binary = bytearray(binary)
    for mesh in gltf["meshes"]:
        for primitive in mesh["primitives"]:
            accessor = gltf["accessors"][primitive["attributes"]["POSITION"]]
            view = gltf["bufferViews"][accessor["bufferView"]]
            base = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
            for k in range(accessor["count"]):
                x = struct.unpack_from("<f", binary, base + 12 * k)[0]
                struct.pack_into("<f", binary, base + 12 * k, x + dx)
            accessor.pop("min", None)
            accessor.pop("max", None)
    write_glb(path, gltf, binary)


def _view(tmp_path, name):
    from Fujin.objectview import MagObjectView
    path = tmp_path / Path(name).name
    shutil.copyfile(ROOT / name, path)
    manager = MagDocument()
    manager.load_file(str(path))
    view = MagObjectView()
    view.set_manager(manager)
    return view, manager


@pytest.mark.ff8data(MESHES)
def test_mesh_glb_round_trip_and_vertex_move(qapp, tmp_path):
    view, manager = _view(tmp_path, MESHES)
    item = next(view.tree.topLevelItem(i) for i in range(view.tree.topLevelItemCount())
                if view.tree.topLevelItem(i).text(1) == "mesh")
    view.tree.setCurrentItem(item)
    glb = str(tmp_path / "mesh.glb")
    assert view.export_glb(glb) and view.import_glb(glb)       # unchanged file: nothing moves
    assert not manager.modified
    _shift_positions(glb, 0.05)                                # 50 engine units along X
    size = len(manager.data)
    changes = []
    view.data_changed.connect(lambda: changes.append(1))
    assert view.import_glb(glb) and changes and manager.modified and len(manager.data) == size
    kind, payload = view._selected_object()
    original = MagContainer(manager.original)
    before = next(o for o in original.objects if o.index == payload.index).mesh.vertices
    assert [v[0] - b[0] for v, b in zip(payload.mesh.vertices, before)] == [50] * len(before)
    assert [v[1:] for v in payload.mesh.vertices] == [b[1:] for b in before]
    manager.undo()
    assert not manager.modified


@pytest.mark.ff8data(MODEL)
def test_battle_model_glb_vertex_move(qapp, tmp_path):
    view, manager = _view(tmp_path, MODEL)
    item = next(view.tree.topLevelItem(i) for i in range(view.tree.topLevelItemCount())
                if view.tree.topLevelItem(i).text(1) == "model")
    view.tree.setCurrentItem(item)
    glb = str(tmp_path / "model.glb")
    assert view.export_glb(glb) and view.import_glb(glb) and not manager.modified
    _shift_positions(glb, 0.1)
    size = len(manager.data)
    assert view.import_glb(glb) and manager.modified and len(manager.data) == size
    changed = [i for i in range(size) if manager.data[i] != manager.original[i]]
    _kind, (container, object_id) = view._selected_object()
    obj = next(o for o in container.objects if o.index == object_id)
    skeleton, geometry, animation = obj.info["sections"]
    assert geometry <= min(changed) and max(changed) < animation        # only the geometry's vertices
    manager.undo()
    assert not manager.modified


@pytest.mark.ff8data(MESHES)
def test_glb_with_other_faces_is_refused(qapp, tmp_path, monkeypatch):
    from FF8GameData.magcine import magmeshgltf
    view, manager = _view(tmp_path, MESHES)
    item = next(view.tree.topLevelItem(i) for i in range(view.tree.topLevelItemCount())
                if view.tree.topLevelItem(i).text(1) == "mesh")
    view.tree.setCurrentItem(item)
    _kind, payload = view._selected_object()
    glb = str(tmp_path / "mesh.glb")
    magmeshgltf.export_mesh(payload.mesh, glb)
    gltf, binary = read_glb(glb)
    gltf["accessors"][gltf["meshes"][0]["primitives"][0]["indices"]]["count"] -= 3   # one face fewer
    write_glb(glb, gltf, binary)
    with pytest.raises(ValueError, match="only moving vertices"):
        magmeshgltf.import_positions(payload.mesh, glb)
    warnings = []
    monkeypatch.setattr("Fujin.objectview.QMessageBox.warning", lambda *args: warnings.append(args[2]))
    assert not view.import_glb(glb) and warnings and not manager.modified
