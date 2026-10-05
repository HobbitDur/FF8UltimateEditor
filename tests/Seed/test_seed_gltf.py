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


def test_model_writer_round_trip_keeps_everything_the_engine_reads():
    """write_model_data on an unmodified model re-parses to the same mesh, face attributes
    (+0x08 flag, +0x1D command byte, TIM index), bones, texture animation and animation."""
    from FF8GameData.mch.mchanalyser import CharaOne, parse_model_data, write_model_data
    one = CharaOne(next(FIELD.rglob("bgroad_6/chara.one")).read_bytes())
    for entry in one.entries:
        if entry.is_main:
            continue
        model = parse_model_data(one.data, entry.model_offset)
        animation = bytes(one.data[entry.model_offset + model.anim_offset:entry.data_offset + entry.size])
        rebuilt = parse_model_data(write_model_data(model, animation), 0)

        def faces(m):
            vertices = [(group.bone_id, v._x, v._y, v._z) for obj in m.geometry_data.object_data
                        for group in obj.vertices_data for v in group.vertices]
            return sorted((tuple(vertices[i] for i in face.vertex_indexes[:3 if face in obj.triangles else 4]),
                           face.tex_id_1) for obj in m.geometry_data.object_data
                          for face in obj.triangles + obj.quads)
        assert faces(rebuilt) == faces(model)
        assert rebuilt.raw_bones == model.raw_bones and rebuilt.raw_tex_anim == model.raw_tex_anim


def test_imported_mesh_is_saved_for_npc_and_main_character(tmp_path):
    """export -> import -> save -> reload: an NPC mesh goes into chara.one, a main character's
    into its main_chr .mch; both pose exactly like before, other models untouched."""
    import shutil
    room = tmp_path / "field" / "mapdata" / "bg" / "bgroad_6"
    room.mkdir(parents=True)
    shutil.copy(next(FIELD.rglob("bgroad_6/chara.one")), room / "chara.one")
    main_chr = tmp_path / "field" / "model" / "main_chr"
    main_chr.mkdir(parents=True)
    shutil.copy(FIELD / "model" / "main_chr" / "d049.mch", main_chr / "d049.mch")

    manager = SeedManager()
    manager.load_chara_one(room / "chara.one")
    before = {}
    for index in (0, 2):  # d049 main character, p050 NPC
        manager.load_entry(index)
        before[index] = manager.get_animated_vertices(1, 5)
        glb = tmp_path / f"{index}.glb"
        GltfExporter(manager).export(str(glb))
        GltfImporter(manager.vertex_axis_signs).import_into_enemy(str(glb), manager.enemy)
        manager.on_mesh_imported()
    assert manager.modified_entry_names() == ["d049", "p050"]
    assert [path.name for _, path in manager.main_mesh_changes()] == ["d049.mch"]
    manager.save_chara_one(room / "chara.one")

    reloaded = SeedManager()
    reloaded.load_chara_one(room / "chara.one")
    for index in (0, 2):
        reloaded.load_entry(index)
        assert not any(quad for obj in reloaded.enemy.geometry_data.object_data for quad in obj.quads)
        after = reloaded.get_animated_vertices(1, 5)
        assert max(min(math.dist(a, b) for b in before[index]) for a in after) < 1e-9
    original = SeedManager()
    original.load_chara_one(next(FIELD.rglob("bgroad_6/chara.one")))
    for index in (3, 4):  # NPCs p041, p042
        original.load_entry(index)
        reloaded.load_entry(index)
        assert original.get_animated_vertices(0, 0) == reloaded.get_animated_vertices(0, 0)


def test_export_all_fields(tmp_path):
    """Batch export: <out>/<field>/<index>_<name>.glb for every model, the open field's models
    taken from the live manager (unsaved edits included), cancel stops before the next field."""
    from Seed.seedbatchexport import export_fields_to_gltf
    paths = [next(FIELD.rglob(f"{name}/chara.one")) for name in ("bgroad_6", "bgmast_6", "bg2f_1a")]
    live = _manager("bgroad_6", 2)
    live.enemy.animation_data.animations[1].frames = live.enemy.animation_data.animations[1].frames[:3]
    written, failures = export_fields_to_gltf(paths, tmp_path, FIELD / "model" / "main_chr", live)
    assert failures == []
    assert len(written) == 7 + 3 + 12
    assert (tmp_path / "bgroad_6" / "02_p050.glb") in written
    assert (tmp_path / "bg2f_1a" / "00_d000.glb") in written
    gltf, _ = read_glb(str(tmp_path / "bgroad_6" / "02_p050.glb"))
    assert "anim_1_3f" in [anim["name"] for anim in gltf["animations"]]  # the live, edited model

    seen = []
    written, _ = export_fields_to_gltf(paths, tmp_path / "cancel", FIELD / "model" / "main_chr",
                                       progress=lambda index, field: seen.append(field) or index < 1)
    assert seen == ["bgroad_6", "bgmast_6"] and len(written) == 7


def test_export_all_menu_entry():
    from Seed.seedwidget import SeedWidget
    widget = SeedWidget()
    texts = [action.text() for action in widget.viewer_3d._files_menu.actions()]
    assert "Export all opened fields to glTF…" in texts


def test_export_import_round_trip_is_exact(tmp_path):
    manager = _manager("bgroad_6", 2)
    before = manager.get_animated_vertices(1, 5)
    glb = tmp_path / "model.glb"
    GltfExporter(manager).export(str(glb))
    GltfImporter(manager.vertex_axis_signs).import_into_enemy(str(glb), manager.enemy)
    after = manager.get_animated_vertices(1, 5)
    assert len(after) == len(before)
    assert max(min(math.dist(a, b) for b in before) for a in after) < 1e-9
