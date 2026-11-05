"""A new effect's own data edited (Choreography's Data tab, Fujin/effectdataview.py): its sprite
sequences (FF8GameData.psxgpu.spritesequence encode_sequence), its sound, its tables, its file name
and its tables of layouts - and what it draws and plays changing with them."""
import dataclasses
import struct
import subprocess
from pathlib import Path

import pytest

from FF8GameData.psxgpu.primlayout import encode_layout, parse_layout
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


@pytest.mark.ff8data("extracted_files/FF8_EN.exe")
def test_layouts_encode_back():
    """Hypnotize's 17 prim-model layouts: parsed and encoded again, byte for byte."""
    exe = EXE.read_bytes()
    entries = {key: entry for key, entry in load_description(133)["exe_data"].items()
               if isinstance(entry, dict) and entry.get("kind") == "layout"}
    assert len(entries) == 17
    for entry in entries.values():
        start = int(entry["address"], 16) - 0x400000
        data = exe[start:start + entry["size"]]
        layout = parse_layout(data)
        assert encode_layout(layout) == data and layout.objects and layout.frames > 0


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
    # a layout: its animation's keys and tracks
    view.select("main_layout")
    editor = view.layout_editor
    assert view.pages.currentWidget() is editor and editor.objects.count() == 2 and editor.frames_spin.value() == 30
    assert [editor.tracks.item(row).text() for row in range(editor.tracks.count())][:2] == [
        "Position value (1 key)", "Position velocity (1 key)"]
    before = parse_layout(bytes.fromhex(fujin.descriptions[225]["data"]["main_layout"]["hex"]))
    scale = next(i for i, track in enumerate(before.objects[0].tracks) if track.channel == "scale")
    frame, values = before.objects[0].tracks[scale].keys[0]
    editor.set_key(0, scale, 0, values=[v // 2 for v in values])
    editor.add_track_box.setCurrentIndex(editor.add_track_box.findText("Rotation value"))
    editor.add_track()
    editor.add_key()
    editor.frames_spin.setValue(40)
    assert view.apply()
    after = parse_layout(bytes.fromhex(fujin.descriptions[225]["data"]["main_layout"]["hex"]))
    assert after.frames == 40 and after.models == before.models
    assert after.objects[0].tracks[scale + 1].keys[0] == (frame, tuple(v // 2 for v in values))   # rotation value now first
    rotation = next(track for track in after.objects[0].tracks if (track.channel, track.slot) == ("rotation", "value"))
    assert [key[0] for key in rotation.keys] == [0, 1]


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


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/magic/mag132.tim", "extracted_files/battle/d0c000.dat",
                     "extracted_files/battle/d0w000.dat", "extracted_files/battle/c0m033.dat")
def test_an_edited_layout_changes_what_the_effect_draws(tmp_path):
    """Hypnotize's copy with its target layouts spinning twice as fast: drawn otherwise, as long."""
    from Fujin.effectparts import effect_schema
    from Fujin.recorderbuild import RECORDER
    if effect_schema(1) is None:
        pytest.skip("the recorder is not built with FFNx's effect sources")
    new = new_effect(load_description(133), 225, "New hypnosis", EXE.read_bytes())

    def record(tag):
        program = write_program(new, tmp_path / f"{tag}.fxprog")
        out = tmp_path / f"{tag}.txt"
        run = subprocess.run([str(RECORDER), "225", f"exe={EXE}", f"magic={MAGIC}", f"battle={BATTLE}", f"out={out}",
                              f"slot0={BATTLE / 'd0c000.dat'}", f"weapon0={BATTLE / 'd0w000.dat'}",
                              f"slot3={BATTLE / 'c0m033.dat'}", "caster=3", "target=0", f"program={program}"],
                             cwd=str(RECORDER.parent), capture_output=True, text=True, timeout=120)
        assert run.returncode == 0 and "faulted" not in run.stdout, run.stdout[-500:]
        return [line for line in out.read_text().splitlines() if line.startswith(("P ", "R "))]

    drawn = record("new")
    for k in range(8):
        entry = new["data"][f"target_layout.{k}"]
        layout = parse_layout(bytes.fromhex(entry["hex"]))
        track = next(track for track in layout.objects[0].tracks if (track.channel, track.slot) == ("rotation", "velocity"))
        track.keys[:] = [(frame, tuple(2 * v for v in values)) for frame, values in track.keys]
        entry["hex"] = encode_layout(layout).hex()
    redrawn = record("faster")
    assert redrawn != drawn and sum(line.startswith("R ") for line in redrawn) == sum(line.startswith("R ") for line in drawn)


def _port_layouts():
    """(effect, key, entry) of every port effect's layout parameter (its exe data has a capacity)."""
    from Fujin.effectprogram import described_effects
    for effect in described_effects():
        description = load_description(effect)
        for key, entry in description.get("exe_data", {}).items():
            if isinstance(entry, dict) and entry.get("kind") == "layout" and "capacity" in entry:
                yield effect, key, entry


@pytest.mark.ff8data("extracted_files/FF8_EN.exe")
def test_every_port_layout_fits_the_block_its_port_decodes_it_into():
    """Each port effect's layout parameter: a layout in the exe, of its size, whose player state is the
    block its port decodes it into (FFNx fx_params.h layout(): a layout needing more keeps the game's)."""
    from FF8GameData.psxgpu.primlayout import state_size
    exe = EXE.read_bytes()
    found = list(_port_layouts())
    assert len(found) >= 139 and len({effect for effect, _key, _entry in found}) >= 50
    for effect, key, entry in found:
        at = int(entry["address"], 16) - 0x400000
        layout = parse_layout(exe[at:at + entry["size"]])
        assert encode_layout(layout) == exe[at:at + entry["size"]], (effect, key)
        assert state_size(layout) <= entry["capacity"], (effect, key)
        assert any(param["key"] == key and param["type"] == "layout" and param["default"] == f"@{key}"
                   for param in load_description(effect)["params"]), (effect, key)


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/magic/mag127.tim", "extracted_files/battle/d0c000.dat",
                     "extracted_files/battle/d0w000.dat", "extracted_files/battle/c0m033.dat")
def test_a_port_effects_copy_plays_its_own_layout_and_flipbooks(tmp_path):
    """Gastric Juice's copy (a port effect: FFNx's code runs it) with its own data draws as the exe's; with its
    layout spinning twice as fast it draws otherwise (a spin that turns more of it off screen draws a few primitives
    less or more), with its flipbooks dimmed too otherwise again, as many primitives."""
    from Fujin.effectparts import effect_schema
    from Fujin.recorderbuild import RECORDER
    if effect_schema(128) is None or not any(f["type"] == "layout" for f in effect_schema(128)["fields"]):
        pytest.skip("the recorder is not built with FFNx's effect sources that read layouts as parameters")
    new = new_effect(load_description(128), 224, "New juice", EXE.read_bytes())

    def record(effect, tag, *extra):
        out = tmp_path / f"{tag}.txt"
        run = subprocess.run([str(RECORDER), str(effect), f"exe={EXE}", f"magic={MAGIC}", f"battle={BATTLE}", f"out={out}",
                              f"slot0={BATTLE / 'd0c000.dat'}", f"weapon0={BATTLE / 'd0w000.dat'}",
                              f"slot3={BATTLE / 'c0m033.dat'}", "caster=3", "target=0", *extra],
                             cwd=str(RECORDER.parent), capture_output=True, text=True, timeout=120)
        assert run.returncode == 0 and "faulted" not in run.stdout, run.stdout[-500:]
        return [line.split(" ", 2)[2] if line.startswith("P ") else line for line in out.read_text().splitlines()
                if line.startswith(("P ", "R "))]

    original = record(128, "original")
    assert record(224, "own", f"program={write_program(new, tmp_path / 'own.fxprog')}") == original
    data = new["data"]
    layout = parse_layout(bytes.fromhex(data["layout"]["hex"]))
    for obj in layout.objects:
        for track in obj.tracks:
            if (track.channel, track.slot) == ("rotation", "velocity"):
                track.keys[:] = [(frame, tuple(2 * v for v in values)) for frame, values in track.keys]
    data["layout"]["hex"] = encode_layout(layout).hex()
    spun = record(224, "spun", f"program={write_program(new, tmp_path / 'spun.fxprog')}")
    assert spun != original
    for key in ("seqs.spray", "seqs.drip", "seqs.splash"):
        sequence = parse_sequence(bytes.fromhex(data[key]["hex"]), 0, 0)
        for frame in sequence.frames:
            frame.pieces[:] = [dataclasses.replace(piece, intensity=0x10) for piece in frame.pieces]
        data[key]["hex"] = encode_sequence(sequence).hex()
    dimmed = record(224, "dimmed", f"program={write_program(new, tmp_path / 'dimmed.fxprog')}")
    assert dimmed != spun and len(dimmed) == len(spun)


@pytest.mark.ff8data("extracted_files/FF8_EN.exe")
def test_every_port_flipbook_is_a_sequence_its_code_plays_whole():
    """Each port effect's flipbook parameter: a sprite sequence in the exe, of its size, with the frames its code
    plays (FFNx fx_params.h sequence(): one with fewer frames keeps the game's); a copy keeps that minimum."""
    from Fujin.effectprogram import described_effects, own_data
    exe = EXE.read_bytes()
    found = [(effect, key, entry) for effect in described_effects()
             for key, entry in load_description(effect).get("exe_data", {}).items()
             if isinstance(entry, dict) and entry.get("kind") == "seq" and "frames" in entry]
    assert len(found) >= 140 and len({effect for effect, _key, _entry in found}) >= 56
    for effect, key, entry in found:
        address = int(entry["address"], 16)
        sequence = parse_sequence(exe, address - 0x400000, address)
        assert sequence is not None and sequence.size == entry["size"], (effect, key)
        assert len(sequence.frames) == entry["frames"], (effect, key)
        assert any(param["key"] == key and param["type"] == "seq" and param["default"] == f"@{key}"
                   for param in load_description(effect)["params"]), (effect, key)
    assert own_data(load_description(found[0][0]), exe)[found[0][1]]["frames"] == found[0][2]["frames"]
