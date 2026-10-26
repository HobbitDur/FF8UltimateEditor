"""Fujin Sound tab (MAG sound blocks -> audio.dat entries, controller vibration) and Models tab
(3D object view, unverified playback of non-GF cinematic scripts)."""
import pathlib
import struct
import sys

import pytest
from PyQt6.QtWidgets import QApplication

from FF8GameData.magcine.magfile import MagFile
from FF8GameData.magcine.magsound import (sound_entries, vibration_patterns, SOUND_TABLE, MUSIC_TABLE,
                                          STREAM, AKAO)

ROOT = pathlib.Path(__file__).resolve().parents[2]
MAGIC = ROOT / "extracted_files/magic"
BATTLE = ROOT / "extracted_files/battle"
AUDIO_FMT = "extracted_files/Sound/audio.fmt"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def _sound_mag():
    """A packed MAG with a two-entry sound table, one music-table block and a vibration bank."""
    data = bytearray(0x100)
    header = [0, 0, 0x30, 0, 0x40, 0x30, 0x30, 0x34, 0, 0xA0, 0, 0]
    struct.pack_into("<12I", data, 0, *header)
    struct.pack_into("<I", data, 0x30, 0x80 - 0x30)                   # music entry -> 0x80
    struct.pack_into("<II", data, 0x40, 8, 0x14)                       # sound table: 2 entries
    data[0x48:0x50] = struct.pack("<I", 400168) + b"SCOT"
    data[0x54:0x5C] = struct.pack("<I", 240018) + b"SCOT"
    data[0x80:0x88] = struct.pack("<I", 108) + b"SCOT"
    struct.pack_into("<II", data, 0xA0, 0, 8)                          # bank: slot 1 at +8
    left, right = bytes([10, 2, 40, 1, 20, 0xFF]), bytes([200, 0, 200, 0xFF])
    data[0xA8:0xAC] = struct.pack("<HH", len(left), len(right))
    data[0xAC:0xAC + len(left) + len(right)] = left + right
    return bytes(data)


def test_sound_table_entries_resolve_world_ids_to_audio_entries():
    entries = sound_entries(_sound_mag())
    assert [(e.table, e.index, e.offset, e.sound_id, e.archive_id, e.verified) for e in entries] == [
        (SOUND_TABLE, 0, 0x48, 400168, 1230 + 168, True),    # GetSoundID_ForWorld: category 40
        (SOUND_TABLE, 1, 0x54, 240018, 370 + 18, True),      # category 24
        (MUSIC_TABLE, 0, 0x80, 108, 108, False)]             # consumer not traced: unverified


def test_block_without_scot_signature_is_not_playable():
    data = bytearray(_sound_mag())
    data[0x4C:0x50] = b"XXXX"
    entry = sound_entries(bytes(data))[0]
    assert entry.archive_id is None and "SCOT" in entry.note


def test_vibration_envelope_steps_like_the_engine():
    """BdVibration_StepEnvelope: counter -1 after the claim, 0 after each segment, level x2 (max 255)."""
    (pattern,) = vibration_patterns(_sound_mag())
    assert pattern.index == 1 and pattern.offset == 0xA8
    assert pattern.left == [20, 40, 60, 80, 60, 40]
    assert pattern.right == [255, 255]
    assert pattern.ticks == 6


def test_section_map_names_the_vibration_bank():
    kinds = {section.name: section.kind for section in MagFile(_sound_mag()).sections}
    assert kinds["Controller vibration"] == "vibration" and kinds["Sound effects"] == "sound"


def test_streamed_scot_and_akao_files():
    (stream,) = sound_entries(struct.pack("<I", 109) + b"SCOT" + bytes(8))
    assert (stream.table, stream.archive_id, stream.verified) == (STREAM, 109, False)
    (bank,) = sound_entries(b"AKAO" + bytes(28))
    assert bank.table == AKAO and bank.archive_id is None


def test_sound_panel_lists_blocks_and_says_why_play_is_off(qapp):
    from Common.fileregistry import FileRegistry
    from Fujin.soundpanel import SoundPanel
    panel = SoundPanel(FileRegistry())
    panel.set_data(_sound_mag())
    assert panel.table.rowCount() == 3
    assert [panel.table.item(0, column).text() for column in (0, 3, 4)] == ["Sound effect", "400168", "#1398"]
    assert panel.table.item(2, 6).text().startswith("UNVERIFIED")
    assert not panel.play_button.isEnabled() and "Import the sound archive" in panel.play_button.toolTip()
    assert "header's Import" in panel.archive_label.text()
    assert panel.vibration_table.rowCount() == 1 and panel.curve.pattern.left[0] == 20
    panel.set_manager(None)
    assert panel.table.rowCount() == 0 and "FF8_EN.exe" in panel.status.text()


def test_unverified_playback_keeps_the_default_guard():
    from Fujin.magdocument import MagDocument
    manager = MagDocument()
    manager.load_bytes(_sound_mag(), name="MAG230_B.00")
    assert not manager.playback_verified
    manager.load_bytes(_sound_mag(), name="MAG200_B.00")
    assert manager.playback_verified


def test_fujin_offers_the_sound_archive_through_the_header(qapp):
    from Fujin.fujinwidget import FujinWidget
    fujin = FujinWidget()
    labels = [label for label, _callback in fujin.complementary_entries()]
    assert any("audio.fmt" in label for label in labels)
    assert fujin.sound_panel.audio_binding in fujin.file_bindings()
    assert fujin.sound_panel.audio_binding.read_only
    assert any(source.exact_name == "audio.fmt" for source in fujin.auto_import_sources())
    assert fujin.models.display.tabText(0) == "3D view" and fujin.sound.display.tabText(0) == "Sounds and vibration"


# ---------------------------------------------------------------- game data
@pytest.mark.ff8data("extracted_files/magic/MAG200_B.00", "extracted_files/magic/MAG230_B.00")
def test_vanilla_sound_tables():
    ifrit = sound_entries((MAGIC / "MAG200_B.00").read_bytes())
    assert [e.archive_id for e in ifrit if e.table == SOUND_TABLE] == [388, 391, 394, 397]
    (disease_breath,) = sound_entries((MAGIC / "MAG230_B.00").read_bytes())
    assert (disease_breath.sound_id, disease_breath.archive_id) == (400168, 1398)
    (pattern,) = vibration_patterns((MAGIC / "MAG200_B.00").read_bytes())
    assert pattern.ticks == 313 and max(pattern.left) == 208


@pytest.mark.ff8data("extracted_files/battle/mag005_b.08", "extracted_files/battle/mag186_g.dat")
def test_vanilla_streamed_parts():
    (stream,) = sound_entries((BATTLE / "mag005_b.08").read_bytes())
    assert (stream.table, stream.archive_id) == (STREAM, 109)
    (bank,) = sound_entries((BATTLE / "mag186_g.dat").read_bytes())
    assert bank.table == AKAO and bank.archive_id is None


@pytest.mark.ff8data("extracted_files/magic/MAG230_B.00", AUDIO_FMT)
def test_sound_panel_plays_with_the_shared_archive(qapp):
    from Common.fileregistry import FileRegistry
    from Fujin.soundpanel import SoundPanel
    registry = FileRegistry()
    panel = SoundPanel(registry)
    panel.audio_binding.open_path(str(ROOT / AUDIO_FMT))       # what the header's Import does
    panel.set_data((MAGIC / "MAG230_B.00").read_bytes())
    assert panel.julia is not None and panel.table.item(0, 5).text().endswith(" s")
    assert panel.play_button.isEnabled()
    other = SoundPanel(registry)                                 # an archive opened elsewhere is reused
    assert other.julia is not None


@pytest.mark.ff8data("extracted_files/magic/MAG230_B.00")
def test_non_gf_script_replays_as_unverified_approximation(qapp):
    from FF8GameData.magcine.cinescene import unrendered_draw_handlers
    from Fujin.magdocument import MagDocument
    from Fujin.magdocumentwidget import MagDocumentWidget
    manager = MagDocument()
    manager.load_file(str(MAGIC / "MAG230_B.00"))
    with pytest.raises(ValueError, match="Playback is verified only"):
        manager.simulate()
    simulation = manager.simulate(allow_unverified=True)
    assert simulation.finished_tick == 105
    assert unrendered_draw_handlers(simulation) == {6: 3}    # three particle emitters
    widget = MagDocumentWidget()
    widget.load_file(str(MAGIC / "MAG230_B.00"))
    assert widget.tabs.isTabEnabled(2)
    assert "UNVERIFIED" in widget.sim_label.text() and "particle emitter" in widget.sim_label.text()
    assert widget.scene_view.scene is not None


@pytest.mark.ff8data("extracted_files/magic/MAG260_B.00", "extracted_files/battle/mag186_b.dat")
def test_object_view_meshes_and_animated_models(qapp):
    from Fujin.magdocument import MagDocument
    from Fujin.objectview import MagObjectView, model_sources
    manager = MagDocument()
    manager.load_file(str(MAGIC / "MAG260_B.00"))
    kinds = [kind for _label, kind, _payload in model_sources(manager.data, manager.document)]
    assert kinds.count("mesh") == 9 and kinds.count("sprite") == 4 and kinds.count("model") == 1
    view = MagObjectView()
    view.set_manager(manager)
    assert view.tree.currentItem().text(1) == "mesh" and view.preview.mesh.faces
    model = next(view.tree.topLevelItem(i) for i in range(view.tree.topLevelItemCount())
                 if view.tree.topLevelItem(i).text(1) == "model")
    view.tree.setCurrentItem(model)
    assert view.animation_combo.count() == 1 and view.frame_slider.maximum() == 154
    view.frame_slider.setValue(10)
    assert view.frame_label.text() == "frame 11/155" and view.preview.bounds is not None
    sprite = view.tree.topLevelItem(0)
    view.tree.setCurrentItem(sprite)
    assert view.preview.mesh is None and "VRAM" in view.info.text()

    creature = MagDocument()                                    # indexed container: a standard battle model
    creature.load_file(str(BATTLE / "mag186_b.dat"))
    view.set_manager(creature)
    assert view.tree.topLevelItemCount() == 1 and not view.controls.isHidden()
    assert view.animation_combo.count() > 0


@pytest.mark.ff8data("extracted_files/magic/mag000-049.tim")
def test_object_view_explains_files_without_objects(qapp):
    from Fujin.magdocument import MagDocument
    from Fujin.objectview import MagObjectView
    manager = MagDocument()
    manager.load_file(str(MAGIC / "mag000-049.tim"))
    view = MagObjectView()
    view.set_manager(manager)
    assert view.tree.topLevelItemCount() == 0 and "Textures" in view.family.text()


def test_sound_and_vibration_edits_in_place(qapp):
    """High-level edits: a block plays another audio.dat entry; a vibration point takes a new
    strength / ramp. Same file size, undoable."""
    from Common.fileregistry import FileRegistry
    from Fujin.magdocument import MagDocument
    from Fujin.soundpanel import SoundPanel, level_for_percent
    from FF8GameData.magcine.magsound import world_id_for_archive
    manager = MagDocument()
    manager.load_bytes(_sound_mag(), name="MAG230_B.00")
    size = len(manager.data)
    panel = SoundPanel(FileRegistry())
    changes = []
    panel.data_changed.connect(lambda: changes.append(1))
    panel.set_manager(manager)
    panel.table.selectRow(0)
    assert panel.entry_spin.value() == 1398 and not panel.use_button.isEnabled()
    panel.entry_spin.setValue(1300)
    assert panel.use_button.isEnabled() and panel.use_entry()
    assert panel.entries[0].archive_id == 1300 and panel.entries[0].sound_id == 400070   # category 40 kept
    assert world_id_for_archive(100, 400168) == 100                                        # below it: category 0
    assert len(manager.data) == size and manager.modified and changes
    manager.undo()
    assert not manager.modified
    panel.set_manager(manager)
    pattern = panel.patterns[0]
    first = pattern.left_points[0]
    panel.point_tables["left"].cellWidget(0, 0).setValue(50)
    assert panel.patterns[0].left_points[0][0] == level_for_percent(50) and len(manager.data) == size
    if first[1] != 0xFF:
        panel.point_tables["left"].cellWidget(0, 1).setValue(10)
        assert panel.patterns[0].left_points[0][1] == 9
    manager.undo()
    manager.undo()
    assert not manager.modified


def test_an_edit_keeps_the_vibration_pattern_selected_with_ctrl_held(qapp):
    """The tables are rebuilt after each edit and the selection restored. QTableView.selectRow
    toggles under a held Ctrl, which deselected the pattern and emptied its point table."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    from Common.fileregistry import FileRegistry
    from Fujin.magdocument import MagDocument
    from Fujin.soundpanel import SoundPanel
    manager = MagDocument()
    manager.load_bytes(_sound_mag(), name="MAG230_B.00")
    panel = SoundPanel(FileRegistry())
    panel.set_manager(manager)
    QTest.keyPress(panel, Qt.Key.Key_Control, Qt.KeyboardModifier.ControlModifier)
    try:
        panel.point_tables["left"].cellWidget(0, 0).setValue(50)
        assert panel._selected_pattern() is not None
        assert panel.point_tables["left"].cellWidget(0, 1) is not None
    finally:
        QTest.keyRelease(panel, Qt.Key.Key_Control)
