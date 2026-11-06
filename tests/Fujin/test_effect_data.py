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
    # the camera: its keyframes and script in the shared track editor, given back as they are
    view.select("camera")
    page = view.camera_page
    assert view.pages.currentWidget() is page and page.track is not None and page.editor.track is page.track
    assert view.edited_entry() == view.entry()
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
    assert len(found) >= 373 and len({effect for effect, _key, _entry in found}) >= 137
    for effect, key, entry in found:
        address = int(entry["address"], 16)
        sequence = parse_sequence(exe, address - 0x400000, address)
        assert sequence is not None and sequence.size == entry["size"], (effect, key)
        assert len(sequence.frames) == entry["frames"], (effect, key)
        assert any(param["key"] == key and param["type"] == "seq" and param["default"] == f"@{key}"
                   for param in load_description(effect)["params"]), (effect, key)
    assert own_data(load_description(found[0][0]), exe)[found[0][1]]["frames"] == found[0][2]["frames"]


def _models():
    """(effect, key, entry) of every prim model of the descriptions' exe data."""
    from Fujin.effectprogram import described_effects
    for effect in described_effects():
        for key, entry in load_description(effect).get("exe_data", {}).items():
            if isinstance(entry, dict) and entry.get("kind") == "model":
                yield effect, key, entry


@pytest.mark.ff8data("extracted_files/FF8_EN.exe")
def test_models_encode_back():
    """Every prim model of the descriptions (Effect_RenderPrimModel's meshes) parsed and encoded again, byte for byte,
    with the vertices its entry says its code reads; an entry may hold more after it (Double's morph pair)."""
    from FF8GameData.psxgpu.primmodel import encode_model, parse_model
    exe = EXE.read_bytes()
    found = list(_models())
    assert len(found) >= 400
    for effect, key, entry in found:
        address = int(entry["address"], 16)
        at = address - 0x400000
        model = parse_model(exe, at, address)
        assert model is not None and model.size <= entry["size"], (effect, key)
        assert encode_model(model) == exe[at:at + model.size], (effect, key)
        assert len(model.vertices) == entry["vertices"], (effect, key)


@pytest.mark.ff8data("extracted_files/FF8_EN.exe")
def test_every_port_model_is_a_parameter_that_keeps_its_vertices():
    """Each port effect's prim model (its exe data has the vertex count its code reads): a model parameter on it, and a
    copy keeps that count (FFNx fx_params.h model(): one with another count keeps the game's)."""
    from Fujin.effectprogram import own_data
    ports = [(effect, key, entry) for effect, key, entry in _models()
             if any(param["key"] == key for param in load_description(effect)["params"])]
    assert len(ports) >= 426 and len({effect for effect, _key, _entry in ports}) >= 114
    for effect, key, _entry in ports:
        assert any(param["key"] == key and param["type"] == "model" and param["default"] == f"@{key}"
                   for param in load_description(effect)["params"]), (effect, key)
    effect, key, entry = ports[0]
    assert own_data(load_description(effect), EXE.read_bytes())[key]["vertices"] == entry["vertices"]


@pytest.mark.ff8data("extracted_files/FF8_EN.exe")
def test_the_model_editor_scales_recolours_and_keeps_what_follows(qapp):
    """The Data tab's model page: Double's big rune scaled to half, a primitive recoloured; its vertices (its code
    reads them by number) are neither added nor removed; its morph pair's second model is kept."""
    from FF8GameData.psxgpu.primmodel import parse_model
    from Fujin.effectdataview import EffectDataView
    new = new_effect(load_description(4), 300, "New double", EXE.read_bytes())
    view = EffectDataView()
    view.show_data(new)
    view.select("big.model")
    editor = view.model_editor
    before = parse_model(bytes.fromhex(new["data"]["big.model"]["hex"]), 0, 0)
    editor.scale.setValue(0.5)
    editor.transform()
    editor.primitives.item(0, 2).setText("FF0000")
    edited = parse_model(bytes.fromhex(view.edited_entry()["hex"]), 0, 0)
    assert edited.vertices[0][:3] == [round(v * 0.5) for v in before.vertices[0][:3]]
    assert edited.primitives[0].colours == [(255, 0, 0)] and view.apply_button.isEnabled()
    editor.remove_vertex()
    assert len(editor.model.vertices) == 76 and "76" in editor.error.text()
    editor.add_vertex()
    assert len(editor.model.vertices) == 76
    view.select("morph.model")
    data = bytes.fromhex(new["data"]["morph.model"]["hex"])
    view.model_editor.scale.setValue(2)
    view.model_editor.transform()
    out = bytes.fromhex(view.edited_entry()["hex"])
    assert len(out) == len(data) and out[2268:] == data[2268:] and out[:2268] != data[:2268]


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/magic/mag000-049.tim", "extracted_files/battle/d0c000.dat",
                     "extracted_files/battle/d0w000.dat", "extracted_files/battle/c0m009.dat")
def test_a_port_effects_copy_draws_its_own_models(tmp_path):
    """Triple's copy (a port effect) with its own models draws as the exe; with every model's vertices halved it draws
    otherwise, as long (a smaller mesh may leave a few primitives on or off screen)."""
    from FF8GameData.psxgpu.primmodel import encode_model, parse_model
    from Fujin.effectparts import effect_schema
    from Fujin.recorderbuild import RECORDER
    if effect_schema(21) is None or not any(f["type"] == "model" for f in effect_schema(21)["fields"]):
        pytest.skip("the recorder is not built with FFNx's effect sources that read models as parameters")
    new = new_effect(load_description(21), 224, "New triple", EXE.read_bytes())

    def record(effect, tag, *extra):
        out = tmp_path / f"{tag}.txt"
        run = subprocess.run([str(RECORDER), str(effect), f"exe={EXE}", f"magic={MAGIC}", f"battle={BATTLE}", f"out={out}",
                              f"slot0={BATTLE / 'd0c000.dat'}", f"weapon0={BATTLE / 'd0w000.dat'}",
                              f"slot3={BATTLE / 'c0m009.dat'}", "caster=0", "target=3", *extra],
                             cwd=str(RECORDER.parent), capture_output=True, text=True, timeout=120)
        assert run.returncode == 0 and "faulted" not in run.stdout, run.stdout[-500:]
        return [line.split(" ", 2)[2] if line.startswith("P ") else line for line in out.read_text().splitlines()
                if line.startswith(("P ", "R "))]

    original = record(21, "original")
    assert record(224, "own", f"program={write_program(new, tmp_path / 'own.fxprog')}") == original
    for key, entry in new["data"].items():
        if isinstance(entry, dict) and entry.get("kind") == "model":
            model = parse_model(bytes.fromhex(entry["hex"]), 0, 0)
            for vertex in model.vertices:
                vertex[:3] = [v // 2 for v in vertex[:3]]
            entry["hex"] = encode_model(model).hex()
    smaller = record(224, "smaller", f"program={write_program(new, tmp_path / 'smaller.fxprog')}")
    frames = lambda lines: sum(line.startswith("R ") for line in lines)
    assert smaller != original and frames(smaller) == frames(original)


def _port_entries(kinds):
    """(effect, key, entry) of the port effects' exe data parameters of these kinds."""
    from Fujin.effectprogram import described_effects
    for effect in described_effects():
        description = load_description(effect)
        params = {param["key"] for param in description.get("params", [])}
        for key, entry in description.get("exe_data", {}).items():
            if isinstance(entry, dict) and entry.get("kind") in kinds and key in params:
                yield effect, key, entry


@pytest.mark.ff8data("extracted_files/FF8_EN.exe")
def test_port_resources_are_parameters_of_their_kind():
    """The B ports' texture file names, camera tracks, TIMs and animation sets (fx_params.h name / camera / tim /
    anim_set): each a parameter of its kind on its exe data, the exe's bytes reading as one; an animation set keeps
    the bytes after it the game may read (its tail)."""
    from FF8GameData.dat.cameratrack import HEADER
    from Fujin.effectdataview import anim_set_sections
    exe = EXE.read_bytes()
    found = {}
    for effect, key, entry in _port_entries(("name", "camera", "tim", "anim_set")):
        found.setdefault(entry["kind"], set()).add(effect)
        param = next(p for p in load_description(effect)["params"] if p["key"] == key)
        assert param["type"] == entry["kind"] and param["default"] == f"@{key}", (effect, key)
        start = int(entry["address"], 16) - 0x400000
        data = exe[start:start + entry["size"]]
        if entry["kind"] == "name":
            assert data.split(b"\0")[0].isascii() and b"\0" in data, (effect, key)
        elif entry["kind"] == "camera":
            _count, script, keyframes, size = HEADER.unpack_from(data)
            assert script == 8 and 8 < keyframes < size == len(data), (effect, key)
        elif entry["kind"] == "tim":
            assert struct.unpack_from("<I", data)[0] == 0x10, (effect, key)
        else:
            assert entry["tail"] == 4096 and len(anim_set_sections(data[:-entry["tail"]])) == entry["count"], (effect, key)
    assert len(found["name"]) >= 100 and len(found["camera"]) >= 80 and len(found["tim"]) >= 8
    assert len(found["anim_set"]) >= 40


@pytest.mark.ff8data("extracted_files/FF8_EN.exe")
def test_port_tables_and_morph_sets_read_in_their_format():
    """The B ports' small tables (colours, fades, counts, offsets) and morphs' vertex sets (fx_params.h data /
    vertices): whole rows of their format; a vertex set's {size, count} header matches its length."""
    exe = EXE.read_bytes()
    tables = list(_port_entries(("table",)))
    assert len(tables) >= 90 and len({effect for effect, _key, _entry in tables}) >= 50
    for effect, key, entry in tables:
        size = struct.calcsize(entry.get("format", "h"))
        assert (entry["size"] - entry.get("skip", 0)) % (size * entry["columns"]) == 0, (effect, key)
        if entry.get("skip") == 8:
            start = int(entry["address"], 16) - 0x400000
            length, count = struct.unpack_from("<2I", exe, start)
            assert length == entry["size"] == 8 + 8 * count and count == entry["count"], (effect, key)


@pytest.mark.ff8data("extracted_files/FF8_EN.exe")
def test_the_data_tab_edits_a_ports_resources_and_tables(qapp, tmp_path, monkeypatch):
    """A port's copy in the Data tab: its TIM in Fujin's TIM card (a .tim of the game's kind imported, one without
    the game's palette refused), its animation set (a set of another count refused, the bytes after it kept), its
    colour table (bytes), its morph's vertex set (its size and count kept) and its camera track in the shared
    track editor."""
    from PyQt6.QtWidgets import QFileDialog
    from Fujin.cameraeffectmanager import CameraEffectManager
    from Fujin.effectdataview import EffectDataView
    from FF8GameData.gamedata import GameData
    exe = EXE.read_bytes()
    view = EffectDataView(camera_tools=CameraEffectManager(GameData(str(ROOT / "FF8GameData"))))
    new = new_effect(load_description(89), 300, "New wishing star", exe)
    view.show_data(new)
    view.select("res.tim_a")
    tim = bytes.fromhex(new["data"]["res.tim_a"]["hex"])
    assert view.pages.currentWidget() is view.tim_page and view.tim_page.card is not None
    other = bytearray(tim)
    other[-1] ^= 0xFF
    (tmp_path / "a.tim").write_bytes(bytes(other))
    flipped = bytearray(tim)
    flipped[4] ^= 8                                     # (the palette flag: not the game's kind)
    (tmp_path / "b.tim").write_bytes(bytes(flipped))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_a, **_k: (str(tmp_path / "b.tim"), ""))
    view.tim_page.import_tim()
    assert "palette" in view.tim_page.error.text() and view.edited_entry()["hex"] == tim.hex()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_a, **_k: (str(tmp_path / "a.tim"), ""))
    view.tim_page.import_tim()
    assert view.edited_entry()["hex"] == bytes(other).hex() and view.apply()
    view.select("res.anim")
    data = bytes.fromhex(new["data"]["res.anim"]["hex"])
    (tmp_path / "two.anim").write_bytes(struct.pack("<4I", 2, 16, 16, 16))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_a, **_k: (str(tmp_path / "two.anim"), ""))
    view.anim_page.import_set()
    assert "Not imported" in view.anim_page.info.text() and view.anim_page.data() == data
    tail = new["data"]["res.anim"]["tail"]
    (tmp_path / "three.anim").write_bytes(data[:-tail])
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_a, **_k: (str(tmp_path / "three.anim"), ""))
    view.anim_page.import_set()
    assert view.anim_page.data() == data                # the same set: its tail kept
    new = new_effect(load_description(66), 301, "New griever death", exe)
    view.show_data(new)
    view.select("tables.spark_colours")
    assert view.table.format == "B" and view.table.columnCount() == 4 and view.table.rowCount() == 18
    view.table.item(0, 0).setText("255")
    assert bytes.fromhex(view.edited_entry()["hex"])[0] == 255
    view.table.item(0, 1).setText("256")                # (a byte: refused)
    assert bytes.fromhex(view.edited_entry()["hex"])[1] == bytes.fromhex(new["data"]["tables.spark_colours"]["hex"])[1]
    new = new_effect(load_description(21), 302, "New triple", exe)
    view.show_data(new)
    view.select("morphs.from")
    head = bytes.fromhex(new["data"]["morphs.from"]["hex"])[:8]
    assert view.table.rowCount() == 80
    view.table.item(0, 0).setText("7")
    edited = bytes.fromhex(view.edited_entry()["hex"])
    assert edited[:8] == head and struct.unpack_from("<h", edited, 8)[0] == 7 and len(edited) == 648
    view.select("res.camera")
    assert view.camera_page.track is not None and view.edited_entry()["hex"] == new["data"]["res.camera"]["hex"]


@pytest.mark.ff8data(*FILES)
def test_a_port_effects_copy_plays_its_own_camera_and_morph(tmp_path):
    """Triple's copy (a port effect) starts its own camera track (the recorder's K line: its size and checksum) and
    blends its own morph's vertex sets: as the exe's, it records as the exe; with Cure's camera track and its morph
    sets halved, otherwise."""
    from Fujin.effectparts import effect_schema
    from Fujin.recorderbuild import RECORDER
    schema = effect_schema(21)
    if schema is None or not any(f["type"] == "camera" for f in schema["fields"]):
        pytest.skip("the recorder is not built with FFNx's effect sources that read cameras as parameters")
    exe = EXE.read_bytes()
    new = new_effect(load_description(21), 224, "New triple", exe)

    def record(effect, tag, *extra):
        out = tmp_path / f"{tag}.txt"
        run = subprocess.run([str(RECORDER), str(effect), f"exe={EXE}", f"magic={MAGIC}", f"battle={BATTLE}", f"out={out}",
                              f"slot0={BATTLE / 'd0c000.dat'}", f"weapon0={BATTLE / 'd0w000.dat'}",
                              f"slot3={BATTLE / 'c0m009.dat'}", "caster=0", "target=3", *extra],
                             cwd=str(RECORDER.parent), capture_output=True, text=True, timeout=120)
        assert run.returncode == 0 and "faulted" not in run.stdout, run.stdout[-500:]
        return [line.split(" ", 2)[2] if line.startswith("P ") else line for line in out.read_text().splitlines()
                if line.startswith(("P ", "R ", "K "))]

    original = record(21, "original")
    assert any(line.startswith("K ") for line in original)
    assert record(224, "own", f"program={write_program(new, tmp_path / 'own.fxprog')}") == original
    cure = load_description(1)["exe_data"]["camera"]
    start = int(cure["address"], 16) - 0x400000
    new["data"]["res.camera"]["hex"] = exe[start:start + cure["size"]].hex()
    for key in ("morphs.from", "morphs.to"):
        data = bytes.fromhex(new["data"][key]["hex"])
        values = struct.unpack_from(f"<{(len(data) - 8) // 2}h", data, 8)
        new["data"][key]["hex"] = (data[:8] + struct.pack(f"<{len(values)}h", *(v // 2 for v in values))).hex()
    edited = record(224, "edited", f"program={write_program(new, tmp_path / 'edited.fxprog')}")
    cameras = lambda lines: [line for line in lines if line.startswith("K ")]
    others = lambda lines: [line for line in lines if not line.startswith("K ")]
    assert cameras(edited) != cameras(original) and others(edited) != others(original)


def _described():
    from Fujin.effectprogram import described_effects
    return [(effect, load_description(effect)) for effect in described_effects()]


@pytest.mark.ff8data("extracted_files/FF8_EN.exe")
def test_what_code_reads_at_a_fixed_place_is_listed_as_not_editable():
    """Each description's "not_editable" rows: data in the exe its parameters don't hold, not part of its program."""
    from Fujin.effectprogram import compile_program
    exe_size = EXE.stat().st_size
    rows = 0
    for effect, description in _described():
        held = [(int(entry["address"], 16), entry["size"]) for entry in description.get("exe_data", {}).values()
                if isinstance(entry, dict) and "address" in entry and "size" in entry]
        keys = [entry["key"] for entry in description.get("not_editable", [])]
        assert len(keys) == len(set(keys)), effect
        for entry in description.get("not_editable", []):
            rows += 1
            address = int(entry["address"], 16)
            assert entry["label"] and entry["doc"] and 0 < entry["size"] <= 4096, (effect, entry["key"])
            assert 0xC00000 <= address and address - 0x400000 + entry["size"] <= exe_size, (effect, entry["key"])
            assert not any(start <= address < start + size for start, size in held), (effect, entry["key"])
    assert rows >= 800
    doom = load_description(8)
    assert compile_program(doom) == compile_program({key: value for key, value in doom.items() if key != "not_editable"})


@pytest.mark.ff8data("extracted_files/FF8_EN.exe")
def test_the_data_tab_shows_not_editable_rows(qapp):
    """A shipped effect's and a new effect's not editable rows in the Data tab: greyed after its own data, their
    bytes from the exe, nothing to apply."""
    from Fujin.effectdataview import NO_DATA, EffectDataView, entries, hex_dump
    exe = EXE.read_bytes()
    view = EffectDataView(exe=lambda: exe)
    doom = load_description(8)
    view.show_data(doom)
    assert view.list.isEnabled() and view.note.text().startswith(NO_DATA) and "not editable" in view.note.text()
    assert view.list.count() == len(doom["not_editable"])
    row = doom["not_editable"][0]
    view.select(row["key"])
    address = int(row["address"], 16)
    assert "not editable" in view.title.text() and row["address"] in view.title.text()
    assert view.fixed_bytes.isReadOnly()
    assert view.fixed_bytes.toPlainText() == hex_dump(address, exe[address - 0x400000:address - 0x400000 + row["size"]])
    assert not view.apply_button.isEnabled() and view.entry() is None and not view.apply()
    new = new_effect(doom, 300, "New doom", exe)
    view.show_data(new)
    own = list(entries(new))
    assert view.list.count() == len(own) + len(doom["not_editable"])
    assert view.list.item(len(own)).text() == f"{row['label']} (not editable)"
    view.select(row["key"])
    assert view.pages.currentIndex() == view.pages_by_kind["not_editable"]
    blind = EffectDataView()
    blind.show_data(doom)
    blind.select(row["key"])
    assert "FF8_EN.exe" in blind.fixed_bytes.toPlainText()


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/magic/mag140-158-159-258-331-332.tim", "extracted_files/battle/d0c000.dat",
                     "extracted_files/battle/d0w000.dat", "extracted_files/battle/c0m092.dat")
def test_renzokuken_plays_its_own_sequence(tmp_path):
    """Renzokuken vs X-ATM092: its length is what Squall's sequence computes (opcode AB): the game's sequence code run by the
    recorder (sequences=1) plays it whole, the models still drawn, where without it the effect ends at once."""
    from Fujin.effectprogram import binds_its_animations
    from Fujin.recorderbuild import RECORDER
    assert binds_its_animations(159) and binds_its_animations(188) and not binds_its_animations(1)
    assert binds_its_animations(300, "param res.anim_sets anim_set 1 1") and not binds_its_animations(300, "param a i16 1 1")

    def record(tag, *extra):
        out = tmp_path / f"{tag}.txt"
        run = subprocess.run([str(RECORDER), "159", f"exe={EXE}", f"magic={MAGIC}", f"battle={BATTLE}", f"out={out}",
                              f"slot0={BATTLE / 'd0c000.dat'}", f"weapon0={BATTLE / 'd0w000.dat'}",
                              f"slot3={BATTLE / 'c0m092.dat'}", "caster=0", "target=3", *extra],
                             cwd=str(RECORDER.parent), capture_output=True, text=True, timeout=120)
        assert run.returncode == 0 and "faulted" not in run.stdout, run.stdout[-500:]
        ticks = []
        for line in out.read_text().splitlines():
            if line.startswith("R "):
                ticks.append(0)
            elif line.startswith("P "):
                ticks[-1] += 1
        return ticks

    assert len(record("plain")) == 3
    ticks = record("sequences", "sequences=1")
    assert len(ticks) > 100 and min(ticks) > 200


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/magic/mag140-158-159-258-331-332.tim", "extracted_files/battle/d0c000.dat",
                     "extracted_files/battle/d0w000.dat", "extracted_files/battle/c0m092.dat")
def test_an_animset_file_plays_in_the_recording(tmp_path):
    """effect_159.animset instead of the exe's set, as FFNx in the game (animset=address:file): the same bytes record the same; a
    Renzokuken stage counting one more animation (its AB list) makes the effect longer. A file FFNx would refuse is refused."""
    from FF8GameData.dat.exeanimset import anim_set_info, locate_anim_sets
    from Fujin.animsetfiles import AnimSetFiles, file_error
    from Fujin.recorderbuild import RECORDER
    exe = EXE.read_bytes()
    info = anim_set_info(159, 0)
    start = locate_anim_sets(exe)[info]
    data = exe[start:start + info.size]
    same = tmp_path / "same" / "effect_159.animset"
    same.parent.mkdir()
    same.write_bytes(data)
    longer = tmp_path / "effect_159.animset"
    stages, counted_again = bytes((0xAB, 1, 0, 1, 0xA0, 2)), bytes((0xAB, 1, 0, 1, 1, 0xA0))
    assert data.count(stages) == 2                                       # (its two sequences' AB lists: animations 0, 1 | 2 | ...)
    longer.write_bytes(data.replace(stages, counted_again))              # (0, 1, 1 | nothing | ...)
    (tmp_path / "effect_999.animset").write_bytes(data)
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "effect_159.animset").write_bytes(data[:40])
    assert "no animation set" in file_error(str(tmp_path / "effect_999.animset"))
    assert file_error(str(tmp_path / "bad" / "effect_159.animset")) and file_error(str(same)) is None
    files = AnimSetFiles()
    assert files.load([str(same), str(tmp_path / "effect_999.animset")])[0] == [159]
    assert files.bindings(159, str(EXE)) == ((start + 0x400000, str(same)),) and files.bindings(160, str(EXE)) == ()

    def record(tag, *extra):
        out = tmp_path / f"{tag}.txt"
        run = subprocess.run([str(RECORDER), "159", f"exe={EXE}", f"magic={MAGIC}", f"battle={BATTLE}", f"out={out}",
                              f"slot0={BATTLE / 'd0c000.dat'}", f"weapon0={BATTLE / 'd0w000.dat'}", f"slot3={BATTLE / 'c0m092.dat'}",
                              "caster=0", "target=3", "sequences=1", *extra], cwd=str(RECORDER.parent), capture_output=True, text=True, timeout=120)
        assert run.returncode == 0 and "faulted" not in run.stdout, run.stdout[-500:]
        return [line for line in out.read_text().splitlines() if line.startswith(("P ", "R "))]

    original = record("exe")
    address = f"0x{start + 0x400000:X}"
    assert record("same", f"animset={address}:{same}") == original
    edited = record("longer", f"animset={address}:{longer}")
    ticks = lambda lines: sum(line.startswith("R ") for line in lines)
    assert ticks(edited) != ticks(original)


def test_the_cast_sequence_is_the_one_the_game_picks():
    """A character's by the command that plays the effect (Magic 11, GF 14, item 15), a monster's from its ability slots; nothing for an
    actor with no sequence for it."""
    from Fujin.castsequence import cast_sequence, monster_abilities, shipped_users
    squall, weapon, monster = str(BATTLE / "d0c000.dat"), str(BATTLE / "d0w000.dat"), str(BATTLE / "c0m009.dat")
    users = shipped_users(1)
    assert ("Magic", 21) in users                                        # Cure
    assert cast_sequence(users, squall, weapon) == 11
    assert cast_sequence(users, squall) is None                          # no weapon file: no sequences
    assert cast_sequence([("Battle item", 3)], squall, weapon) == 15
    assert cast_sequence([("Enemy attack", 2)], squall, weapon) is None
    abilities = monster_abilities(monster)
    kind, sequence, entry = next(a for a in abilities if a[0] == 8)
    assert cast_sequence([("Enemy attack", entry)], monster) == sequence
    assert cast_sequence([("Enemy attack", 9999)], monster) is None


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/magic/mag001.tim", "extracted_files/battle/d0c000.dat",
                     "extracted_files/battle/d0w000.dat", "extracted_files/battle/c0m009.dat")
def _record_159(tmp_path, *extra):
    from Fujin.recorderbuild import RECORDER
    battle = ROOT / "extracted_files/battle"
    out = tmp_path / "recording.txt"
    run = subprocess.run([str(RECORDER), "159", f"exe={EXE}", f"magic={ROOT / 'extracted_files/magic'}", f"battle={battle}", f"out={out}",
                          f"slot0={battle / 'd0c000.dat'}", f"weapon0={battle / 'd0w000.dat'}", f"slot3={battle / 'c0m092.dat'}", "caster=0", "target=3",
                          "pos0=0,0,1800", "yaw0=0", "pos3=0,0,-3200", "yaw3=2048", "sequences=1", *extra],
                         cwd=str(RECORDER.parent), capture_output=True, text=True, timeout=300)
    return run.stdout, out


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/battle/c0m092.dat", "extracted_files/magic/mag140-158-159-258-331-332.tim")
def test_x_atm_faces_squall_in_renzokuken(tmp_path):
    """X-ATM092's sequence in effect 159 faces it by C3 0x1A, the angle the game's targeting setup works out before the effect (facing away: 0)."""
    log, _out = _record_159(tmp_path)
    assert "slot 3 faces 2048" in log and "slot 0 faces 0" in log, log[-400:]


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/battle/a0stg006.x", "extracted_files/battle/c0m092.dat",
                     "extracted_files/magic/mag140-158-159-258-331-332.tim")
def test_the_stage_draws_behind_the_actors(tmp_path):
    from FF8GameData.psxgpu.fxdump import load_recording
    camera = tmp_path / "camera.txt"
    camera.write_text("0 0 -1500 6000 0 -500 0 0 512\n")
    plain, plain_out = _record_159(tmp_path, f"camera={camera}")
    (tmp_path / "stage").mkdir()
    staged, staged_out = _record_159(tmp_path / "stage", f"camera={camera}", "stage=6",
                                     f"stagefile={ROOT / 'extracted_files/battle/a0stg006.x'}", "stagedraw=1")
    assert "faulted" not in staged, staged[-400:]
    bare, stage = load_recording(plain_out), load_recording(staged_out)
    assert len(stage.ticks) == len(bare.ticks)
    for tick in (0, len(stage.ticks) // 2):
        assert stage.frame(tick)[1].counts["polygons"] > bare.frame(tick)[1].counts["polygons"] + 100
    # tick 0 has it too (its task only starts drawing on its second run), and it fills the sky of the empty recording
    image = stage.frame(0, scale=0.5)[0]
    assert (image[:40].astype(int).sum(2) > 80).mean() > 0.5


def test_cure_cast_is_the_games_sequence(tmp_path):
    """Cure as the game plays it: Squall's sequence 11 starts the effect (it asks after its 45 ticks), the recording ends with the effect,
    and the cast's glow stands at his height (+0x24 as the game inits it: 0, not above his head)."""
    from Fujin.recorderbuild import RECORDER

    def record(tag, *extra):
        out = tmp_path / f"{tag}.txt"
        run = subprocess.run([str(RECORDER), "1", f"exe={EXE}", f"magic={MAGIC}", f"battle={BATTLE}", f"out={out}",
                              f"slot0={BATTLE / 'd0c000.dat'}", f"weapon0={BATTLE / 'd0w000.dat'}", f"slot3={BATTLE / 'c0m009.dat'}",
                              "caster=0", "target=3", "sequences=1", *extra], cwd=str(RECORDER.parent), capture_output=True, text=True, timeout=120)
        assert run.returncode == 0 and "faulted" not in run.stdout, run.stdout[-500:]
        return run.stdout, sum(line.startswith("R ") for line in out.read_text().splitlines())

    alone = record("alone")[1]
    log, ticks = record("cast", "castseq=11")
    assert "45 ticks before the effect" in log and ticks == alone + 45
