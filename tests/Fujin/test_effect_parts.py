"""Choreography's part tabs: an effect FFNx has a C++ port with parameters for (Cure), part by part.
The effect recorder runs the port (built in from FFNx's effect sources, ExternalTools/FFNx/fx) with
the edited parameters and tags each primitive with its part; Fujin edits the parameters, shows each
part alone, saves them as effect_NNN.fxparams."""
import json
import os
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import pytest
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton

ROOT = Path(__file__).resolve().parents[2]
EXE = ROOT / "extracted_files/FF8_EN.exe"
MAGIC, BATTLE = ROOT / "extracted_files/magic", ROOT / "extracted_files/battle"
CURE_FILES = ("extracted_files/FF8_EN.exe", "extracted_files/magic/mag000-049.tim", "extracted_files/battle/a8def.tim",
              "extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat", "extracted_files/battle/c0m009.dat")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def cure_schema():
    from Fujin.effectparts import effect_schema
    schema = effect_schema(1)
    if schema is None:
        pytest.skip("the effect recorder is not built with FFNx's effect sources (the updater's FFNxEffects)")
    return schema


def test_recording_lines_carry_their_part():
    from FF8GameData.psxgpu.fxdump import parse_recording
    lines = ["R 0 3 ordered",
             "P 1 0 0 0 0 0 0 0 10 4 60808080 00100010 00200020 00300030",
             "P 4 0 0 0 0 0 0 0 10 4 60404040 00500050 00600060 00700070",
             "P 0 0 0 0 0 0 0 0 10 4 60202020 00800080 00900090 00A000A0"]
    recording = parse_recording(lines)
    tick = recording.ticks[0]
    assert tick.parts == [1, 4, 0] and tick.part_ids == {0, 1, 4}
    assert [words[0] for _b, _o, words in tick.part_packets({4})] == [0x60404040]
    assert len(tick.part_packets(None)) == 3


def test_cure_parameter_table():
    schema = cure_schema()
    assert [part["key"] for part in schema["parts"]] == ["emitter", "ring", "glow", "overlay", "sparkles", "motes", "glints"]
    fields = {field["key"]: field for field in schema["fields"]}
    assert fields["ring.substeps"]["default"] == 4 and fields["ring.angle_step"]["default"] == 0x80
    assert fields["emitter.heal_tick"]["default"] == 15 and fields["glow.grey"]["default"] == 0x3C
    assert fields["mote.count.count[1]"]["part"] == "motes" and fields["sparkle.window.last"]["default"] == 16
    assert all(field["min"] <= field["default"] <= field["max"] for field in schema["fields"])


def record(tmp_path, tag, *extra):
    from Fujin.recorderbuild import RECORDER
    out = tmp_path / f"{tag}.txt"
    run = subprocess.run([str(RECORDER), "1", f"exe={EXE}", f"magic={MAGIC}", f"battle={BATTLE}", f"out={out}",
                          f"slot0={BATTLE / 'd0c000.dat'}", f"weapon0={BATTLE / 'd0w000.dat'}",
                          f"slot3={BATTLE / 'c0m009.dat'}", "caster=0", "target=3", *extra],
                         cwd=str(RECORDER.parent), capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stdout[-500:]
    return out.read_text().splitlines(), run.stdout


@pytest.mark.ff8data(*CURE_FILES)
def test_cure_port_is_the_original_and_its_parameters_change_it(tmp_path):
    """The port with the game's values draws exactly what the original code draws (part tags aside);
    a parameter changes it."""
    cure_schema()
    original, _log = record(tmp_path, "original")
    native, log = record(tmp_path, "native", "native=1")
    assert "ported task functions for effect 1" in log
    untagged = [re.sub(r"^P \d+ ", "P 0 ", line) for line in native]
    assert untagged == original and len(original) > 10000
    parts = {int(line.split()[1]) for line in native if line.startswith("P ")}
    assert parts == {0, 1, 2, 3, 4, 5, 6}                         # the actors (0) and Cure's six parts
    params = tmp_path / "params.txt"
    params.write_text("ring.radius.num 4\nring.radius_max 2048\n")
    wide, log = record(tmp_path, "wide", "native=1", f"params={params}")
    assert "params: 2 values set" in log and wide != native
    from FF8GameData.psxgpu.fxdump import parse_recording
    sparkles = lambda lines: parse_recording(lines, 1).fit_view(parts={4})[2]
    assert sparkles(wide) > sparkles(native) * 1.4                # the ring, so its sparkles, twice as wide


@pytest.mark.ff8data(*CURE_FILES)
def test_cure_part_tabs_edit_preview_and_save(qapp, tmp_path):
    from Fujin.fujinwidget import FujinWidget
    cure_schema()
    fujin = FujinWidget()
    fujin.import_paths([str(MAGIC / "mag000-049.tim")])
    fujin.camera_editor.exe_binding.open_path(str(EXE))
    fujin.native_preview.textures_binding.open_path(str(BATTLE / "a8def.tim"))
    fujin.camera_editor.preview.add_models([str(BATTLE / name) for name in ("d0c000.dat", "d0w000.dat", "c0m009.dat")])
    fujin.select_effect(1)
    titles = [fujin.choreography.tabText(i) for i in range(fujin.choreography.count())]
    assert titles[-7:] == ["Emitter", "Ring", "Ground glow", "Overlay", "Sparkles", "Motes", "Glints"]
    ring = next(tab for tab in fujin.part_tabs if tab.part["key"] == "ring")
    fujin.tabs.setCurrentIndex(2)
    fujin.choreography.setCurrentWidget(ring)                    # shown: the lab records
    wait(qapp, fujin.lab)
    recording = fujin.lab.recording
    assert recording is not None and not fujin.lab.cast().actors and fujin.lab.cast().native
    assert set().union(*(set(tick.parts) for tick in recording.ticks)) == {0, 1, 2, 3, 4, 5, 6}   # 0: its target
    assert ring.preview.picture.pixmap() is not None and not ring.preview.picture.pixmap().isNull()
    # the Target box: the monster as a reference, the same in every tab
    ring.preview._show(5)
    alone = ring.preview.picture.pixmap().toImage()
    assert ring.preview.reference.isEnabled() and "c0m009.dat" in ring.preview.reference.text()
    ring.preview.reference.setChecked(True)
    assert all(tab.preview.reference.isChecked() for tab in fujin.part_tabs)
    assert ring.preview.shown_parts() == {0, 1} and ring.preview.picture.pixmap().toImage() != alone
    ring.preview.reference.setChecked(False)
    # the emitter draws nothing: its tab shows the whole effect, the sound and heal ticks marked
    emitter = next(tab for tab in fujin.part_tabs if tab.part["key"] == "emitter")
    assert emitter.preview.part_ids == {1, 2, 3, 4, 5, 6}
    emitter.preview.slider.setValue(15)
    assert emitter.preview.frame_label.text().endswith("- Heal")
    assert fujin.choreography.currentWidget() is ring
    ring.spins["ring.radius.num"].setValue(4)
    assert fujin.effect_params == {1: {"ring.radius.num": 4}} and fujin.can_save_folder()
    QTest.qWait(400)
    wait(qapp, fujin.lab)
    assert fujin.choreography.currentWidget() is ring              # an edit keeps the tab shown
    assert fujin.lab.recording is not recording and fujin.lab.cast().params == (("ring.radius.num", 4),)
    ring.spins["ring.radius.num"].setValue(2)                    # back to the game's: nothing kept
    assert fujin.effect_params == {1: {}}
    ring.spins["ring.substeps"].setValue(6)
    assert fujin.save_files(str(tmp_path))
    saved = json.loads((tmp_path / "effect_001.fxparams").read_text(encoding="utf-8"))
    assert saved == {"effect": 1, "name": fujin.catalog.name(1), "params": {"ring.substeps": 6}}
    assert not fujin.can_save_folder()
    fujin.effect_params.clear()
    assert fujin.import_parameters([str(tmp_path / "effect_001.fxparams")]) == [1]
    ring = next(tab for tab in fujin.part_tabs if tab.part["key"] == "ring")
    assert fujin.effect_params == {1: {"ring.substeps": 6}} and ring.spins["ring.substeps"].value() == 6


@pytest.mark.ff8data(*CURE_FILES)
def test_cure_part_tabs_show_the_images_their_pieces_come_from(qapp, tmp_path):
    from Fujin.fujinwidget import FujinWidget
    from FF8GameData.psxgpu.texuse import texture_sheets
    cure_schema()
    fujin = FujinWidget()
    fujin.import_paths([str(MAGIC / "mag000-049.tim")])
    fujin.camera_editor.exe_binding.open_path(str(EXE))
    fujin.native_preview.textures_binding.open_path(str(BATTLE / "a8def.tim"))
    fujin.camera_editor.preview.add_models([str(BATTLE / name) for name in ("d0c000.dat", "d0w000.dat", "c0m009.dat")])
    fujin.select_effect(1)
    tabs = {tab.part["key"]: tab for tab in fujin.part_tabs}
    fujin.tabs.setCurrentIndex(2)
    fujin.choreography.setCurrentWidget(tabs["sparkles"])
    wait(qapp, fujin.lab)
    # the sparkles: 3 flipbook frames of the effect's TIM (mag000-049.tim: VRAM 384,256, 8-bit, palette row 0)
    sparkles = tabs["sparkles"].images
    assert [(v.sheet.x, v.sheet.y, v.sheet.depth, v.sheet.clut_xy) for v in sparkles.views] == [(384, 256, 1, (320, 240))]
    assert sparkles.views[0].pieces == [(32, 96, 48, 112), (32, 112, 48, 128), (48, 96, 64, 112)]
    assert sparkles.views[0].image.size().width() == 512 and sparkles.views[0].image.size().height() == 256
    # following the preview's tick: the pieces drawn then
    tabs["sparkles"].preview.slider.setValue(6)
    assert sparkles.views[0].tick == 6 and sparkles.views[0].sheet.pieces[6]
    # the overlay: the target's own texture, and the image its values name (the light it projects)
    overlay = tabs["overlay"].images
    titles = [label.text() for label in overlay.findChildren(QLabel)]
    assert any("the target's own texture" in title for title in titles)
    named = [view for view in overlay.views if view.named]
    assert len(named) == 1 and named[0].named == (256, 128, 384, 256) and named[0].sheet.clut_xy == (320, 241)
    # the glints draw plain colours; the emitter (draws nothing) shows the whole effect's images
    assert not tabs["glints"].images.views and "no textured" in tabs["glints"].images.note.text()
    every = texture_sheets(fujin.lab.recording, {1, 2, 3, 4, 5, 6})
    assert len(tabs["emitter"].images.views) == len(every) == 3
    # the link: from the TIM, shown in the Textures tab with the pieces outlined
    buttons = [b for b in sparkles.findChildren(QPushButton) if b.text() == "Show in Textures"]
    assert len(buttons) == 1 and any("From mag000-049.tim" in l.text() for l in sparkles.findChildren(QLabel))
    buttons[0].click()
    assert fujin.tabs.currentWidget() is fujin.textures
    card = fujin.textures.panel.cards[0]
    assert card.outline == ("Sparkles", [(32, 96, 48, 112), (32, 112, 48, 128), (48, 96, 64, 112)])
    assert card.row == 0 and "outlined: the pieces Sparkles takes" in card.info.text()


def wait(qapp, view):
    deadline = time.monotonic() + 60
    QTest.qWait(50)
    while view._process is not None or view._edit_refresh.isActive():
        assert time.monotonic() < deadline, view.status.text()
        if view._process is not None:
            view._process.waitForFinished(500)
        QTest.qWait(20)
        qapp.processEvents()


def test_updater_takes_one_source_folder(tmp_path, monkeypatch):
    """FFNxEffects: a folder of a GitHub source archive (a branch's, or a release's), nothing else."""
    from ToolUpdate import toolupdate
    archive = tmp_path / "FFNxEffects.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("FFNx-branch/src/ff8/battle/fx/fx_params.h", "// params")
        zipped.writestr("FFNx-branch/src/ff8/battle/fx/mag001_cure.cpp", "// cure")
        zipped.writestr("FFNx-branch/src/ff8/other.cpp", "// not taken")
        zipped.comment = b"0123456789abcdef"
    downloader = toolupdate.ToolDownloader.__new__(toolupdate.ToolDownloader)
    target = tmp_path / "ExternalTools" / "FFNx" / "fx"
    downloader.json_data = {"ExternalTools": {"FFNxEffects": {
        "link": "https://github.com/HobbitDur/FFNx", "install_path": str(target),
        "source": {"stable": "branch:Work", "canary": "branch:Work"}, "source_folder": "src/ff8/battle/fx"}}}
    monkeypatch.setattr(toolupdate.ToolDownloader, "FOLDER_DOWNLOAD", str(tmp_path / "download"))
    links = []

    def download(self, link, func=None, headers={}, write_file=False, file_name=None, dest_path=None):
        links.append(link)
        (tmp_path / "download").mkdir(exist_ok=True)
        (tmp_path / "download" / file_name).write_bytes(archive.read_bytes())
        return None, file_name

    monkeypatch.setattr(toolupdate.ToolDownloader, "_ToolDownloader__download_file", download)
    (target).mkdir(parents=True)
    (target / "stale.cpp").write_text("old")
    downloader.update_one_tool("FFNxEffects")
    assert links == ["https://github.com/HobbitDur/FFNx/archive/refs/heads/Work.zip"]
    assert sorted(os.listdir(target)) == ["SOURCE.txt", "fx_params.h", "mag001_cure.cpp"]
    assert (target / "SOURCE.txt").read_text().split("\n")[1:3] == ["Work", "0123456789abcdef"]


def test_recorder_rebuilt_when_ffnx_effect_sources_change(tmp_path, monkeypatch):
    from Fujin import recorderbuild
    source, script, exe, fx = (tmp_path / "fxrecorder.cpp", tmp_path / "build.bat", tmp_path / "fxrecorder.exe",
                               tmp_path / "fx")
    for path in (source, script, exe):
        path.write_text("x")
    fx.mkdir()
    (fx / "mag001_cure.cpp").write_text("x")
    for path, when in ((source, 1000), (script, 1000), (fx / "mag001_cure.cpp", 1000), (exe, 2000)):
        os.utime(path, (when, when))
    monkeypatch.setattr(recorderbuild, "RECORDER", exe)
    monkeypatch.setattr(recorderbuild, "SOURCES", (source, script))
    monkeypatch.setattr(recorderbuild, "FFNX_EFFECTS", fx)
    monkeypatch.setattr(sys, "platform", "win32")
    assert not recorderbuild.needs_build()
    os.utime(fx / "mag001_cure.cpp", (3000, 3000))                 # the updater brought newer sources
    assert recorderbuild.needs_build()


def test_choreography_says_how_to_get_the_part_tabs(qapp, monkeypatch):
    """A recorder built without FFNx's effect sources (a fresh clone: they come from the updater)
    gives no part tabs; Choreography says how to get them."""
    from Fujin import fujinwidget
    monkeypatch.setattr(fujinwidget, "effect_schema", lambda _effect: None)
    monkeypatch.setattr(fujinwidget, "recorder_has_ports", lambda: False)
    fujin = fujinwidget.FujinWidget()
    fujin.select_effect(1)
    assert fujin.part_tabs == [] and not fujin.parts_note.isHidden()
    assert "FFNx button" in fujin.parts_note.text() and "Update" in fujin.parts_note.text()
    monkeypatch.setattr(fujinwidget, "recorder_has_ports", lambda: True)    # built with them: no part for it
    fujin.select_effect(2)
    assert fujin.parts_note.isHidden()


def test_part_tabs_come_when_the_recorder_build_ends(qapp, monkeypatch):
    """The updater brought FFNx's effect sources and the recorder is built again: Fujin shows the
    part tabs without a restart (and says it is building meanwhile)."""
    from Fujin import fujinwidget, recorderbuild
    build = recorderbuild.RecorderBuild()
    monkeypatch.setattr(recorderbuild, "_build", build)
    monkeypatch.setattr(fujinwidget, "effect_schema", lambda _effect: None)
    monkeypatch.setattr(fujinwidget, "recorder_has_ports", lambda: False)
    fujin = fujinwidget.FujinWidget()
    fujin.select_effect(1)
    assert fujin.part_tabs == [] and "FFNx button" in fujin.parts_note.text()
    build.building = True
    build.changed.emit()
    assert "being built" in fujin.parts_note.text()
    schema = {"parts": [{"id": 1, "key": "ring", "title": "Ring", "doc": ""}],
              "fields": [{"part": "ring", "key": "ring.substeps", "label": "Sub-steps", "doc": "", "default": 4,
                          "min": 1, "max": 16}]}
    monkeypatch.setattr(fujinwidget, "effect_schema", lambda _effect: schema)
    monkeypatch.setattr(fujinwidget, "recorder_has_ports", lambda: True)
    build._end(0, "")
    assert [tab.part["key"] for tab in fujin.part_tabs] == ["ring"] and fujin.parts_note.isHidden()
    tabs = list(fujin.part_tabs)
    build.changed.emit()                                         # the same table: the tabs stay as they are
    assert fujin.part_tabs == tabs


HYPNOTIZE_FILES = ("extracted_files/FF8_EN.exe", "extracted_files/magic/mag132.tim",
                   "extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat",
                   "extracted_files/battle/c0m033.dat")


@pytest.mark.ff8data(*HYPNOTIZE_FILES)
def test_hypnotize_port_and_its_pc_screen_units(tmp_path):
    """Hypnotize (Gayla on Squall): the port is the original; its main layout never draws on PC (its
    frame takes the PC's eighths of a pixel for PSX pixels), main.pixels = 1 brings it back."""
    from FF8GameData.psxgpu.fxdump import parse_recording
    from Fujin.effectparts import effect_schema
    from Fujin.recorderbuild import RECORDER
    schema = effect_schema(133)
    if schema is None:
        pytest.skip("the effect recorder is not built with FFNx's effect sources (the updater's FFNxEffects)")
    assert [part["key"] for part in schema["parts"]] == ["timing", "main", "rings", "targets", "sprites"]
    assert {field["key"]: field["default"] for field in schema["fields"]}["main.pixels"] == 0

    def hypnotize(tag, *extra):
        out = tmp_path / f"{tag}.txt"
        run = subprocess.run([str(RECORDER), "133", f"exe={EXE}", f"magic={MAGIC}", f"battle={BATTLE}", f"out={out}",
                              f"slot0={BATTLE / 'd0c000.dat'}", f"weapon0={BATTLE / 'd0w000.dat'}",
                              f"slot3={BATTLE / 'c0m033.dat'}", "caster=3", "target=0", *extra],
                             cwd=str(RECORDER.parent), capture_output=True, text=True, timeout=120)
        assert run.returncode == 0, run.stdout[-500:]
        return out.read_text().splitlines()

    original, native = hypnotize("original"), hypnotize("native", "native=1")
    assert [re.sub(r"^P \d+ ", "P 0 ", line) for line in native] == original
    parts = lambda lines: set().union(*(set(tick.parts) for tick in parse_recording(lines, 133).ticks))
    assert parts(native) == {0, 2, 3, 4}                          # no main layout on PC
    params = tmp_path / "params.txt"
    params.write_text("main.pixels 1\n")
    assert 1 in parts(hypnotize("pixels", "native=1", f"params={params}"))


@pytest.mark.ff8data(*CURE_FILES)
def test_potion_shares_cures_parameters_but_keeps_its_own(tmp_path):
    """Potion (effect 50) runs a relocated copy of Cure's code: the same parts and fields (FFNx
    mag_heal_ring.h, each module with its own live values), and its port is the original."""
    from Fujin.effectparts import effect_schema
    cure = cure_schema()
    potion = effect_schema(50)
    assert potion is not None and potion["name"] == "Potion"
    assert potion["parts"] == cure["parts"] and potion["fields"] == cure["fields"]

    def effect(effect_id, tag, *extra):
        from Fujin.recorderbuild import RECORDER
        out = tmp_path / f"{tag}.txt"
        run = subprocess.run([str(RECORDER), str(effect_id), f"exe={EXE}", f"magic={MAGIC}", f"battle={BATTLE}",
                              f"out={out}", f"slot0={BATTLE / 'd0c000.dat'}", f"weapon0={BATTLE / 'd0w000.dat'}",
                              f"slot3={BATTLE / 'c0m009.dat'}", "caster=0", "target=3", *extra],
                             cwd=str(RECORDER.parent), capture_output=True, text=True, timeout=120)
        assert run.returncode == 0, run.stdout[-500:]
        return out.read_text().splitlines()

    potion_original, potion_native = effect(50, "original"), effect(50, "native", "native=1")
    assert [re.sub(r"^P \d+ ", "P 0 ", line) for line in potion_native] == potion_original
    params = tmp_path / "params.txt"
    params.write_text("ring.radius.num 4\nring.radius_max 2048\n")
    assert effect(50, "wide", "native=1", f"params={params}") != potion_native
