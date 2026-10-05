"""glTF export/import of field models (Seed): the shared Ifrit3D exporter/importer must use the
field conventions (plain v' = R*v + t vertices, 30 fps, real texture alpha)."""
import math
import os
import pathlib

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from FF8GameData.gltf.glbbuilder import read_glb, read_accessor
from Ifrit.Ifrit3D.gltfexporter import GltfExporter
from Ifrit.Ifrit3D.gltfimporter import GltfImporter
from Seed.seedmanager import SeedManager

FIELD = pathlib.Path(__file__).parent.parent.parent / "extracted_files" / "field"

pytestmark = pytest.mark.skipif(not (FIELD / "model" / "main_chr").is_dir(),
                                reason="extracted field folder not available")
_APP = QApplication.instance() or QApplication([])


def _manager(field, entry):
    manager = SeedManager()
    manager.load_chara_one(next(FIELD.rglob(f"{field}/chara.one")))
    manager.load_entry(entry)
    return manager


@pytest.mark.parametrize("field, entry", [("bgroad_6", 0), ("bgroad_6", 2), ("bg2f_1a", 1)])
def test_export_bind_pose_matches_viewer(tmp_path, field, entry):
    manager = _manager(field, entry)
    glb = tmp_path / "model.glb"
    GltfExporter(manager).export(str(glb))
    gltf, binary = read_glb(str(glb))

    frame = next(anim for anim in manager.enemy.animation_data.animations if anim.frames).frames[0]
    offset = [frame.position[axis].get_pos_world() for axis in range(3)]
    viewer = [tuple(c + offset[axis] for axis, c in enumerate(vertex))
              for vertex in manager.get_animated_vertices(0, 0)]
    exported = [position[:3] for primitive in gltf["meshes"][0]["primitives"]
                for position in read_accessor(gltf, binary, primitive["attributes"]["POSITION"])]
    worst = max(min(math.dist(point, vertex) for vertex in viewer) for point in exported[::5])
    assert worst < 1e-5
    # field animations play at 30 fps
    anim = next(anim for anim in gltf["animations"] if not anim["name"].endswith("_1f"))
    times = read_accessor(gltf, binary, anim["samplers"][0]["input"])
    assert times[1][0] == pytest.approx(1 / 30)


def test_export_import_round_trip_is_exact(tmp_path):
    manager = _manager("bgroad_6", 2)
    before = manager.get_animated_vertices(1, 5)
    glb = tmp_path / "model.glb"
    GltfExporter(manager).export(str(glb))
    GltfImporter(manager.vertex_axis_signs).import_into_enemy(str(glb), manager.enemy)
    after = manager.get_animated_vertices(1, 5)
    assert len(after) == len(before)
    assert max(min(math.dist(a, b) for b in before) for a in after) < 1e-9
