"""A new effect's own data edited (Choreography's Data tab, Fujin/effectdataview.py): its sprite
sequences (FF8GameData.psxgpu.spritesequence encode_sequence), its sound, its tables, its file name
and its tables of layouts - and what it draws and plays changing with them."""
import dataclasses
import struct
import subprocess
from pathlib import Path

import pytest

from FF8GameData.psxgpu.spritesequence import encode_sequence, find_sequences, parse_sequence
from Fujin.effectprogram import load_description, new_effect, write_program

ROOT = Path(__file__).resolve().parents[2]
EXE = ROOT / "extracted_files/FF8_EN.exe"
MAGIC, BATTLE = ROOT / "extracted_files/magic", ROOT / "extracted_files/battle"
FILES = ("extracted_files/FF8_EN.exe", "extracted_files/magic/mag000-049.tim", "extracted_files/battle/d0c000.dat",
         "extracted_files/battle/d0w000.dat", "extracted_files/battle/c0m009.dat")


@pytest.mark.ff8data("extracted_files/FF8_EN.exe")
def test_sequences_encode_back():
    exe = EXE.read_bytes()
    sequences = find_sequences(exe)
    exact = 0
    for address, sequence in sequences.items():
        data = encode_sequence(sequence)
        again = parse_sequence(data, 0, address)
        assert again.frames == sequence.frames and again.parameters == sequence.parameters
        exact += data == exe[address - 0x400000:address - 0x400000 + sequence.size]
    assert len(sequences) > 300 and exact > 290              # but for a few laid out with gaps or shared frames


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.mark.ff8data("extracted_files/FF8_EN.exe")
def test_the_data_tab_edits_a_new_effects_data(qapp):
    from Fujin.fujinwidget import FujinWidget
    exe = EXE.read_bytes()
    fujin = FujinWidget()
    fujin.select_effect(1)
    assert not fujin.data_view.list.isEnabled()                 # Fujin's Cure reads the exe's data
    fujin.descriptions[224] = new_effect(load_description(1), 224, "New heal", exe)
    fujin.descriptions[225] = new_effect(load_description(133), 225, "New hypnosis", exe)
    fujin._update_effect_rows(refresh=False)
    fujin.select_effect(224)
    view = fujin.data_view
    assert view.list.count() == 8 and view.list.isEnabled()
    # a sequence: a piece's intensity
    view.select("ring.seq")
    assert view.pages.currentWidget() is view.sequence and view.sequence.frames.count() == 2
    before = fujin.descriptions[224]["data"]["ring.seq"]["hex"]
    view.sequence.set_piece(0, 0, intensity=0x20)
    assert view.apply_button.isEnabled() and view.apply()
    after = fujin.descriptions[224]["data"]["ring.seq"]["hex"]
    assert after != before and parse_sequence(bytes.fromhex(after), 0, 0).frames[0].pieces[0].intensity == 0x20
    assert f"data ring.seq {after}" in fujin.effect_program(224) and fujin.can_save_folder()
    # frames added and removed
    view.sequence.add_frame()
    assert view.sequence.frames.count() == 3
    view.sequence.remove_frame()
    view.sequence.add_piece()
    assert len(view.sequence.sequence.frames[0].pieces) == 2
    # the sound: another world sound id
    view.select("emitter.sound")
    view.sound.setValue(860001)
    assert view.apply()
    assert struct.unpack("<I", bytes.fromhex(fujin.descriptions[224]["data"]["emitter.sound"]["hex"]))[0] == 860001
    # the texture's file name
    view.select("texture_name")
    view.name.setText("mag001.tim")
    view._edited()
    assert view.apply() and bytes.fromhex(fujin.descriptions[224]["data"]["texture_name"]["hex"]) == b"mag001.tim\0\0"
    # the camera: read-only here
    view.select("camera")
    assert view.pages.currentWidget() is view.summary and "Camera tab" in view.summary.text()
    # Hypnotize's copy: its ring points (a table) and its tables of layouts
    fujin.select_effect(225)
    view.select("ring_points")
    assert view.table.rowCount() == 8 and view.table.columnCount() == 4
    view.table.item(0, 0).setText("100")
    assert view.apply()
    assert struct.unpack_from("<h", bytes.fromhex(fujin.descriptions[225]["data"]["ring_points"]["hex"]))[0] == 100
    view.select("ring_layouts")
    combo = view.pointers.itemAt(0, view.pointers.ItemRole.FieldRole).widget()
    combo.setCurrentText("ring_layout.7")
    assert view.apply() and fujin.descriptions[225]["data"]["ring_layouts"]["pointers"][0] == "ring_layout.7"
    assert "data_pointers ring_layouts ring_layout.7 ring_layout.1" in fujin.effect_program(225)
    view.select("main_layout")
    assert "2 object(s), 30 frames" in view.summary.text()


@pytest.mark.ff8data(*FILES)
def test_edited_data_changes_what_the_effect_draws_and_plays(tmp_path):
    from Fujin.effectparts import effect_schema
    from Fujin.recorderbuild import RECORDER
    if effect_schema(1) is None:
        pytest.skip("the recorder is not built with FFNx's effect sources")
    exe = EXE.read_bytes()

    def record(description, tag):
        program = write_program(description, tmp_path / f"{tag}.fxprog")
        out = tmp_path / f"{tag}.txt"
        run = subprocess.run([str(RECORDER), "224", f"exe={EXE}", f"magic={MAGIC}", f"battle={BATTLE}", f"out={out}",
                              f"slot0={BATTLE / 'd0c000.dat'}", f"weapon0={BATTLE / 'd0w000.dat'}",
                              f"slot3={BATTLE / 'c0m009.dat'}", "caster=0", "target=3", f"program={program}"],
                             cwd=str(RECORDER.parent), capture_output=True, text=True, timeout=120)
        assert run.returncode == 0 and "faulted" not in run.stdout, run.stdout[-500:]
        lines = out.read_text().splitlines()
        return [line for line in lines if line.startswith("P ")], [line.split()[3] for line in lines if line.startswith("S ")]

    new = new_effect(load_description(1), 224, "New heal", exe)
    data = new["data"]
    word = struct.unpack("<I", bytes.fromhex(data["emitter.sound"]["hex"]))[0]
    drawn, sounds = record(new, "new")
    assert sounds == [f"{word:X}"]
    sequence = parse_sequence(bytes.fromhex(data["sparkle.seq"]["hex"]), 0, 0)
    for frame in sequence.frames:
        frame.pieces[:] = [dataclasses.replace(piece, intensity=0x10) for piece in frame.pieces]
    data["sparkle.seq"]["hex"] = encode_sequence(sequence).hex()
    data["emitter.sound"]["hex"] = struct.pack("<I", 860001).hex()
    redrawn, resounded = record(new, "edited")
    assert redrawn != drawn and len(redrawn) == len(drawn) and resounded == [f"{860001:X}"]
