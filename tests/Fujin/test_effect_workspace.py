"""Source ownership, native operand verification, cross-view editing and save round trips."""
import hashlib
import shutil
import struct
from pathlib import Path

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from Fujin.effectcatalog import EffectCatalog, filename_effect
from Fujin.nativeresources import NativeResourceStore, apply_effect_hext
from FF8GameData.magcine.magfile import MagFile

ROOT = Path(__file__).resolve().parents[2]
EXE = "extracted_files/FF8_EN.exe"
BREATH = "extracted_files/magic/MAG230_B.00"


@pytest.fixture
def workspace():
    from Fujin.fujinwidget import FujinWidget
    return FujinWidget()


def test_catalog_distinguishes_verified_sources_from_filename_hints():
    catalog = EffectCatalog()
    assert catalog.name(231) == "Disease Breath"
    assert catalog.runtime(231) == "MAG cinematic interpreter"
    assert len(catalog.effect_ids()) == 400
    resources = catalog.resources(231, ["MAG230_mod.09"])
    assert next(r for r in resources if r.key == "mag230_b.00").evidence == "Loader reference"
    assert next(r for r in resources if r.key == "mag230_mod.09").evidence == "Filename family only"
    assert filename_effect("mag326_g.dat") == 327
    assert filename_effect("ma8def_0.tim") is None
    shared = {r.key for r in catalog.resources(328)}
    assert "mag326_g.dat" in shared
    assert "c0m122.dat" in catalog.notes(69)
    assert not any(r.name == "V" for r in catalog.resources(140))


@pytest.mark.ff8data(EXE)
def test_native_resources_match_fingerprints_and_have_model_sections():
    catalog = EffectCatalog()
    store = NativeResourceStore(catalog.native)
    exe = (ROOT / EXE).read_bytes()
    store.load(exe, "EN")
    assert len(store.managers) == 56 and not store.unavailable
    assert len([e for e in store.entries.values() if e["kind"] == "model"]) == 24
    for key, entry in store.entries.items():
        manager = store.managers[key]
        assert hashlib.sha256(manager.data).hexdigest() == entry["sha256"]
        if entry["kind"] == "model":
            assert {"skeleton", "geometry", "animation"} <= {s.kind for s in manager.document.sections}
    store.load(exe, "FR")
    assert not store.managers and len(store.unavailable) == 56
    corrupted = bytearray(exe)
    entry = catalog.native["resources"][0]
    corrupted[entry["file_offset"]] ^= 1
    store.load(corrupted, "EN")
    assert entry["id"] not in store.managers and entry["id"] in store.unavailable


def test_concatenated_tim_images_are_independently_mapped():
    def tim(color):
        return struct.pack("<II", 16, 2)+struct.pack("<I4H", 14, 320, 240, 1, 1)+struct.pack("<H", color)
    first, second = tim(0x001F), tim(0x7C00)
    document = MagFile(first+second)
    headers = [s for s in document.sections if s.kind == "header"]
    assert [s.start for s in headers] == [0, len(first)]
    assert headers[1].meta["tim_offset"] == len(first)
    assert document.sections[-1].end == len(first+second)


@pytest.mark.ff8data(BREATH)
def test_disease_camera_and_section_views_share_one_document(workspace, tmp_path):
    path = tmp_path / "MAG230_B.00"
    shutil.copyfile(ROOT / BREATH, path)
    original = path.read_bytes()
    workspace.import_paths([str(path)])
    workspace.select_effect(231)
    assert workspace.mag_editor.manager.program is not None
    assert workspace.mag_camera.sources.count() == 1
    workspace.mag_camera.activate()
    manager = workspace.mag_camera.sections.manager
    page = workspace.mag_camera.sections.currentWidget()
    from Fujin.magsectionwidget import MagSectionEditor
    editor = page.findChild(MagSectionEditor)
    assert editor.camera_track.keyframe_count() == 5
    assert workspace.camera_editor.preview.track is editor.camera_track
    camera = next(s for s in manager.document.sections if s.kind == "camera")
    assert camera.start == 0x870
    frame = editor.camera_track.collection.sets[0].animations[0].blocks[0].frames[0]
    frame.pos_x.set(frame.pos_x.get()+20)
    editor._apply_camera()
    QApplication.processEvents()
    workspace.files.activate()
    index = next(i for i in range(workspace.files.sources.count())
                 if workspace.files.sources.itemData(i).key == "mag230_b.00")
    workspace.files.sources.setCurrentIndex(index)
    workspace.files.activate()
    assert workspace.files.sections.manager is manager
    assert workspace.can_save_folder()
    assert workspace.save_files()
    assert path.read_bytes() == bytes(manager.data) != original
    assert not workspace.can_save_folder()
    workspace.select_effect(1)
    assert workspace.mag_camera.sources.count() == 0
    workspace.select_effect(231)
    assert workspace.resolve(next(r for r in workspace.resources if r.key == "mag230_b.00")) is manager


@pytest.mark.ff8data(EXE)
def test_native_camera_fields_edit_signed_values_and_undo(workspace):
    from Fujin.magsectionwidget import MagSectionEditor
    workspace.camera_editor.exe_binding.open_path(str(ROOT / EXE))
    workspace.select_effect(278)
    view = workspace.native_camera
    index = next(i for i in range(view.sources.count())
                 if view.sources.itemData(i).key == "Carbuncle_MiddleAngleStep")
    view.sources.setCurrentIndex(index)
    view.activate()
    view.parameter_table.item(index, 1).setText("-16")
    QApplication.processEvents()
    manager = workspace.native.managers["Carbuncle_MiddleAngleStep"]
    assert bytes(manager.data) == b"\xf0" and workspace.can_save_folder()
    view.activate()
    view.undo_button.click()
    QApplication.processEvents()
    assert bytes(manager.data) == b"\xe0" and not workspace.can_save_folder()


@pytest.mark.ff8data(EXE)
def test_native_cli_exports_parameters_and_rejects_out_of_range_values(tmp_path, capsys):
    from Cli.fujin import FujinCliTool
    tool = FujinCliTool()
    parser = tool.build_parser()
    output = tmp_path / "camera.hext"
    args = parser.parse_args(["native", "-i", str(ROOT / EXE), "--parameter",
        "Carbuncle_MiddleAngleStep", "--value", "-16", "-o", str(output)])
    assert tool.execute(args) == 0
    assert "281DE7 = F0" in output.read_text()
    args.value = 128
    assert tool.execute(args) == 1
    assert "281DE7 = F0" in output.read_text()
    assert "[error]" in capsys.readouterr().out


@pytest.mark.ff8data(EXE, BREATH)
def test_combined_save_and_atomic_patch_import(workspace, tmp_path):
    exe_bytes = (ROOT / EXE).read_bytes()
    workspace.camera_editor.exe_binding.open_path(str(ROOT / EXE))
    workspace.select_effect(278)
    assert workspace.native_camera.sources.count() == 6
    native = workspace.native.managers["Carbuncle_OpeningHeight"]
    assert struct.unpack("<i", native.data)[0] == 3000
    native.patch_bytes(0, struct.pack("<i", 3500))
    camera = workspace.camera_editor.manager.track(35)
    frame = camera.collection.sets[0].animations[0].blocks[0].frames[0]
    frame.pos_x.set(frame.pos_x.get()+10)
    path = tmp_path / "MAG230_B.00"
    shutil.copyfile(ROOT / BREATH, path)
    workspace.import_paths([str(path)])
    manager = workspace.resolve(next(r for r in workspace.catalog.resources(231) if r.key == "mag230_b.00"))
    manager.patch_bytes(len(manager.data)-1, b"\x01")
    assert workspace.save_files(tmp_path / "export")
    assert not workspace.can_save_folder()
    patch = (tmp_path / "export/effects_EN.hext").read_text()
    assert "MAG035_LIFE_cameraAnim" in patch and "Carbuncle_OpeningHeight" in patch
    assert (ROOT / EXE).read_bytes() == exe_bytes
    assert path.read_bytes() == bytes(manager.data)
    workspace.camera_editor.manager.reset_track(35)
    native.undo()
    assert workspace.can_save_folder()
    assert apply_effect_hext(patch, workspace.camera_editor.manager, workspace.native) == 2
    assert not workspace.can_save_folder()
    signature = workspace._native_signature()
    with pytest.raises(ValueError, match="outside loaded"):
        apply_effect_hext(patch+"\n0 = FF", workspace.camera_editor.manager, workspace.native)
    assert workspace._native_signature() == signature
    with pytest.raises(ValueError, match="targets the FR"):
        apply_effect_hext(patch.replace("for the EN FF8 exe", "for the FR FF8 exe"),
                          workspace.camera_editor.manager, workspace.native)
    assert workspace._native_signature() == signature


@pytest.mark.ff8data(EXE)
def test_resized_camera_export_and_revert_cleanup(workspace, tmp_path):
    workspace.camera_editor.exe_binding.open_path(str(ROOT / EXE))
    editor = workspace.camera_editor
    workspace.select_effect(35)
    track = editor.manager.track(35)
    editor.manager.set_script_code(track, editor.manager.script_code(track)+"\nend()")
    assert not track.fits_exe and workspace.can_save_folder()
    assert workspace.save_files(tmp_path)
    cam = tmp_path / "direct/exe/effect_035.bcam"
    assert cam.read_bytes() == track.to_bytes()
    assert not workspace.can_save_folder()
    editor.manager.reset_track(35)
    assert workspace.save_files(tmp_path)
    assert not cam.exists() and not workspace.can_save_folder()


@pytest.mark.ff8data(EXE)
def test_close_exe_clears_native_sources_and_free_slot_clears_preview(workspace):
    workspace.camera_editor.exe_binding.open_path(str(ROOT / EXE))
    workspace.select_effect(278)
    assert workspace.models.sources.count()
    workspace.select_effect(400)
    assert workspace.camera_editor.preview.track is None
    workspace.file_registry.close_file("FF8 exe")
    QApplication.processEvents()
    assert not workspace.native.managers and not workspace.can_save_folder()
