"""MAG family coverage, bounded editing and shared-file UI integration."""
import json
import pathlib
import random
import struct

import pytest

from FF8GameData.magcine.magfile import MagFile, MagField
from Laguna.lagunamanager import LagunaManager

ROOT = pathlib.Path(__file__).resolve().parents[2]
MAGIC = ROOT / "extracted_files/magic"


def _packed(script=b"\0\0", camera=b""):
    data = bytearray(48+len(script)+len(camera))
    for offset in (8, 20, 24, 28):
        struct.pack_into("<I", data, offset, 48)
    struct.pack_into("<I", data, 4, 48)
    if camera:
        struct.pack_into("<I", data, 32, 48+len(script))
    data[48:] = script+camera
    return bytes(data)


def _tim():
    return struct.pack("<II", 16, 2)+struct.pack("<I4H", 16, 320, 240, 2, 1)+b"\0\0\xff\x7f"


def _assert_partition(document):
    spans = document.sections
    if not document.data:
        assert not spans
        return
    assert spans[0].start == 0 and spans[-1].end == len(document.data)
    assert all(a.end == b.start for a, b in zip(spans, spans[1:]))
    for section in spans:
        assert 0 <= section.start < section.end <= len(document.data)
        assert all(section.start <= f.offset and f.offset+f.size <= section.end
                   for f in document.fields_for(section))


def test_contents_decide_format_not_extension():
    assert MagFile(_tim(), "MAG999_B.00").format == "PlayStation TIM"
    assert MagFile(_packed(), "anything.dat").format == "Packed MAG"
    assert MagFile(struct.pack("<I", 161), "mag324_h.00").format == "Four-byte reference"
    assert MagFile(b"\0"*128, "MAG200_B.00").format == "Raw / undecoded"
    assert MagFile(b"\0"*4+b"SCOT"+b"\0"*30).format == "SCOT sound"
    assert MagFile(b"AKAO"+b"\0"*30).format == "AKAO audio"


def test_truncated_and_random_data_never_escape_bounds():
    rng = random.Random(31)
    files = [b"", b"\x10\0\0\0", _tim()[:-1], _packed()[:47], _packed()[:-1]]
    files += [rng.randbytes(rng.randrange(0, 600)) for _ in range(200)]
    # A plausible header with an untrusted count/offset must not allocate or read it.
    bad = bytearray(_packed(b"\0"*12))
    struct.pack_into("<I", bad, 12, 48)
    struct.pack_into("<I", bad, 48, 0xFFFFFFFF)
    files.append(bytes(bad))
    for data in files:
        _assert_partition(MagFile(data))


def test_script_does_not_decode_following_camera_as_cinematic_code():
    # A fall-through wait followed by a camera; the cinematic decoder must stop at the boundary.
    collection = struct.pack("<3H8hH", 1, 6, 24, *([8]*8), 0xFFFF)
    camera = struct.pack("<4H", 2, 8, 10, 10+len(collection))+b"\x02\0"+collection
    manager = LagunaManager()
    manager.load_bytes(_packed(b"\x09\x02", camera))
    assert manager.script_end == 50
    assert all(i.offset < 50 for i in manager.program.instructions.values())
    assert next(s for s in manager.document.sections if s.kind == "camera").start == 50


def test_fixed_size_edits_are_atomic_and_reversible(tmp_path):
    manager = LagunaManager()
    original = _tim()
    manager.load_bytes(original)
    section = manager.document.sections[-1]
    with pytest.raises(ValueError, match="exact byte size"):
        manager.replace_section(section.start, b"x")
    with pytest.raises(ValueError, match="outside"):
        manager.patch_bytes(len(original), b"x")
    with pytest.raises(ValueError, match="fit"):
        manager.set_field(MagField("test", section.start, "B"), 256)
    assert not manager.modified and not manager.undo()
    assert manager.replace_section(section.start, b"\x01\x02\x03\x04")
    assert bytes(manager.data[:section.start]) == original[:section.start]
    assert len(manager.data) == len(original)
    edited = bytes(manager.data)
    assert manager.undo() and bytes(manager.data) == original
    assert manager.redo() and bytes(manager.data) == edited
    path = tmp_path / "changed.00"
    manager.save_file(str(path))
    assert path.read_bytes() == edited and not manager.modified
    # Undo after save compares against the saved image, rather than losing the history.
    assert manager.undo() and manager.modified


def test_indexed_directory_aliases_and_trailing_data():
    for data in (struct.pack("<5I", 3, 20, 24, 24, 28)+b"abcdefghTAIL",
                 struct.pack("<4I", 2, 24, 16, 20)+b"abcdefghTAIL"):
        doc = MagFile(data)
        assert doc.format == "Indexed MAG container"
        _assert_partition(doc)
        assert doc.sections[-1].name == "Trailing data"
    doc = MagFile(struct.pack("<3I", 2, 12, 16)+b"abcdefgh")
    assert doc.format == "Indexed MAG container"
    assert [(s.start, s.end) for s in doc.sections] == [(0, 12), (12, 16), (16, 20)]
    _assert_partition(doc)


def test_widget_edits_tim_fields_and_bytes_and_keeps_other_files(tmp_path):
    from Common.dirtytracking import install_dirty_tracking
    from Common.fileregistry import FileRegistry
    from Laguna.lagunawidget import LagunaWidget
    from Laguna.magsectionwidget import MagSectionEditor
    from PyQt6.QtWidgets import QApplication
    first, second = tmp_path/"MAG900_B.00", tmp_path/"MAG901_B.01"
    first.write_bytes(_tim())
    second.write_bytes(b"raw streamed bytes")
    registry = FileRegistry()
    widget = LagunaWidget(file_registry=registry)
    install_dirty_tracking(widget)
    widget.load_folder(str(tmp_path))
    QApplication.processEvents()
    assert len(widget.managers) == 2
    assert widget.manager.document.format == "PlayStation TIM"
    assert not widget.tabs.isTabEnabled(1)  # not a cinematic script
    widget.section_tabs.setCurrentIndex(1)  # image header
    page = widget.section_tabs.currentWidget()
    editor = page.findChild(MagSectionEditor)
    editor.field_table.item(1, 3).setText("321")  # VRAM X
    QApplication.processEvents()
    assert struct.unpack_from("<H", widget.manager.data, 12)[0] == 321
    assert widget.can_save_folder() and widget.dirty_state.dirty
    widget._show_gf(second.name)
    QApplication.processEvents()
    assert widget.dirty_state.dirty  # changing files preserves the first file's edits
    widget.section_tabs.currentWidget().findChild(MagSectionEditor).byte_table.item(0, 1).setText("41")
    QApplication.processEvents()
    assert widget.manager.data[0] == 0x41
    widget.undo()
    assert bytes(widget.manager.data) == second.read_bytes() and widget.can_save_folder()
    widget._show_gf(first.name)
    widget.undo()
    assert not widget.can_save_folder() and not widget.dirty_state.dirty
    registry.close_file(first.name)
    QApplication.processEvents()
    assert widget.current_gf == second.name
    widget.deleteLater()


@pytest.mark.ff8data("extracted_files/magic/MAG230_B.00")
def test_disease_breath_camera_script_and_keyframes_save_in_the_mag(tmp_path):
    from Common.fileregistry import FileRegistry
    from Laguna.lagunawidget import LagunaWidget
    from Laguna.magsectionwidget import MagSectionEditor
    from PyQt6.QtWidgets import QApplication
    path = tmp_path/"MAG230_B.00"
    original = (MAGIC/path.name).read_bytes()
    path.write_bytes(original)
    widget = LagunaWidget(file_registry=FileRegistry())
    widget.load_file(str(path))
    assert widget.manager.root == 0x58 and widget.manager.script_end == 0x870
    index = next(i for i in range(widget.section_tabs.count()) if widget.section_tabs.tabText(i) == "Camera")
    widget.section_tabs.setCurrentIndex(index)
    editor = widget.section_tabs.currentWidget().findChild(MagSectionEditor)
    assert editor.camera_track.keyframe_count() == 5
    editor.camera_script.setPlainText("end_clear()")
    editor._apply_camera_script()
    QApplication.processEvents()
    edited = bytes(widget.manager.data)
    assert edited[:0x870] == original[:0x870] and edited[0x930:] == original[0x930:]
    widget.undo()
    widget.section_tabs.setCurrentIndex(index)
    editor = widget.section_tabs.currentWidget().findChild(MagSectionEditor)
    frame = editor.camera_track.collection.sets[0].animations[0].blocks[0].frames[0]
    frame.pos_x.set(frame.pos_x.get()+10)
    editor._apply_camera()
    QApplication.processEvents()
    assert widget.manager.modified
    widget.save_files()
    saved = path.read_bytes()
    assert saved != original and len(saved) == len(original)
    assert saved[:0x870] == original[:0x870] and saved[0x930:] == original[0x930:]
    reopened = LagunaManager()
    reopened.load_file(str(path))
    assert bytes(reopened.data) == saved
    widget.deleteLater()


@pytest.mark.ff8data("extracted_files/magic/MAG200_B.00", "extracted_files/battle/mag205_b.56")
def test_entire_mag_corpus_opens_partitions_saves_and_undoes(tmp_path):
    catalog = json.loads((ROOT/"FF8GameData/Resources/json/mag_file_catalog.json").read_text())
    files = [p for root in (MAGIC, ROOT/"extracted_files/battle") for p in root.iterdir()
             if p.is_file() and p.name.lower().startswith(("mag", "ma8"))]
    assert {p.name for p in files} == set(catalog["files"])
    assert len(files) == 790
    for p in files:
        m = LagunaManager()
        m.load_file(str(p))
        _assert_partition(m.document)
        if m.program:
            assert not m.program.errors, (p.name, m.program.errors)
        original = p.read_bytes()
        output = tmp_path / p.name
        m.save_file(str(output))
        assert output.read_bytes() == original, p.name
        last = m.document.sections[-1]
        patch = bytes([original[last.end-1] ^ 1])
        m.patch_bytes(last.end-1, patch)
        assert bytes(m.data[:-1]) == original[:-1], p.name
        assert m.undo() and bytes(m.data) == original, p.name


@pytest.mark.ff8data("extracted_files/magic/MAG230_B.00")
def test_all_embedded_cameras_are_byte_exact():
    from FF8GameData.gamedata import GameData
    from Fujin.cameraeffectmanager import CameraEffectManager, CameraTrack
    vm = CameraEffectManager(GameData("FF8GameData")).vm
    count = 0
    for p in MAGIC.iterdir():
        data = p.read_bytes()
        for s in MagFile(data).sections:
            if s.kind == "camera":
                track = CameraTrack.from_bytes(vm, data[s.start:s.end], effect_id=0, name=p.name,
                                               label="embedded", address=s.start, push_operand=0)
                assert track.to_bytes() == data[s.start:s.end], p.name
                count += 1
    assert count == 46


def test_effect_profiles_separate_real_handlers_from_ifrit_stubs():
    from FF8GameData.magcine.cinescript import CineOpcodeTable, decode_instruction
    base = CineOpcodeTable.default()
    meteor = CineOpcodeTable.for_effect(223)
    assert not base.get(0xBB).valid
    assert meteor.get(0xBB).valid and meteor.get(0xBB).length(0xBB, [0, 0]) == 6
    entity_list = decode_instruction(struct.pack("<4H", 0x309A, 1, 2, 3), 0, CineOpcodeTable.for_effect(248))
    assert not entity_list.error and entity_list.length == 8
    assert CineOpcodeTable.for_effect(211).get(0xAF).length(0xAF, [0]) == 80
    assert base.get(0xBB).name == "Unused"  # profiles never mutate the shared default
    invalid = decode_instruction(struct.pack("<2H", 0xAF, 1), 0, CineOpcodeTable.for_effect(211))
    assert "does not advance" in invalid.error


@pytest.mark.ff8data("extracted_files/FF8_EN.exe")
def test_native_effect_profiles_are_reproducible():
    from Laguna.ResearchScript.dump_mag_profiles import build
    expected = json.loads((ROOT/"FF8GameData/Resources/json/mag_cinematic_profiles.json").read_text())
    assert build(str(ROOT/"extracted_files/FF8_EN.exe")) == expected


@pytest.mark.ff8data("extracted_files/magic/MAG230_B.00")
def test_unverified_effect_playback_is_explicit():
    manager = LagunaManager()
    manager.load_file(str(MAGIC/"MAG230_B.00"))
    with pytest.raises(ValueError, match="Playback is verified only"):
        manager.simulate()


def test_new_mod_binding_reopens_a_closed_tool(tmp_path):
    from Common.closedfileview import install_closed_file_view
    from Common.fileregistry import FileRegistry
    from Laguna.lagunawidget import LagunaWidget
    from PyQt6.QtWidgets import QApplication
    registry = FileRegistry()
    widget = LagunaWidget(file_registry=registry)
    view = install_closed_file_view(widget)
    first = tmp_path/"MAG900_B.00"
    first.write_bytes(_tim())
    widget.load_folder(str(tmp_path))
    registry.close_file(first.name)
    QApplication.processEvents()
    assert view.is_blank
    second = tmp_path/"MAG901_B.custom"
    second.write_bytes(b"mod-added resource")
    binding = widget._add_generic_binding(second.name)
    binding.open_path(str(second))
    QApplication.processEvents()
    assert not view.is_blank and widget.manager.data == second.read_bytes()
    registry.close_file(second.name)
    assert view.is_blank
    widget.deleteLater()


def test_failed_save_keeps_unsaved_bytes_and_dirty_marker(tmp_path, monkeypatch):
    from Common.dirtytracking import install_dirty_tracking
    from Common.filetoolbarwidget import FileToolbarWidget
    from Common.fileregistry import FileRegistry
    from Laguna.lagunawidget import LagunaWidget
    from PyQt6.QtWidgets import QStackedWidget, QMessageBox, QApplication
    registry = FileRegistry()
    widget = LagunaWidget(file_registry=registry)
    install_dirty_tracking(widget)
    path = tmp_path/"MAG900_B.00"
    path.write_bytes(_tim())
    widget.load_folder(str(tmp_path))
    widget.manager.patch_bytes(len(widget.manager.data)-1, b"\x01")
    widget._mark_dirty()
    stack = QStackedWidget()
    stack.addWidget(widget)
    toolbar = FileToolbarWidget(stack, registry)
    def fail(*_args):
        raise OSError("test write failure")
    monkeypatch.setattr(widget.manager, "save_file", fail)
    messages = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *_args: messages.append(_args))
    toolbar._save()
    QApplication.processEvents()
    assert messages and widget.manager.modified and widget.dirty_state.dirty
    assert path.read_bytes() == _tim()
    toolbar.deleteLater()
    stack.deleteLater()


def test_companion_opens_edits_and_saves_without_its_root_file(tmp_path):
    from Common.fileregistry import FileRegistry
    from Laguna.lagunawidget import LagunaWidget
    path = tmp_path/"MAG200_B.01"
    original = bytearray(_packed(b"resource bytes"))
    struct.pack_into("<I", original, 4, 0)  # a resource-only part, with no cinematic root
    path.write_bytes(original)
    registry = FileRegistry()
    widget = LagunaWidget(file_registry=registry)
    widget.companion_bindings["Ifrit"].open_path(str(path))
    assert widget.manager is not None and widget.manager.program is None
    assert widget.current_gf == path.name
    assert not widget.companion_bindings["Ifrit"].read_only
    widget.manager.patch_bytes(len(original)-1, b"!")
    widget._section_edited()
    assert widget.companions["Ifrit"].data[-1:] == b"!"
    assert widget.save_files()
    assert path.read_bytes() == bytes(original[:-1])+b"!"
    assert not widget.can_save_folder()
    registry.close_file(path.name)
    assert widget.manager is None and "Ifrit" not in widget.companions
    widget.deleteLater()
