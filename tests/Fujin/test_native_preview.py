"""Overview > Effect preview: an effect drawn from the game's own code, in the Camera tab preview's battle. FF8UltimateEditor's
effect recorder (Tools/fxrecorder) records the PlayStation GPU packets and VRAM uploads of each tick,
through the effect's own camera; FF8GameData.psxgpu draws them (decoder + software rasteriser), Fujin
plays them."""
import os
import struct
import sys
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from FF8GameData.psxgpu.fxdump import load_recording, parse_recording
from FF8GameData.psxgpu.gpu import Gpu, Vram

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = Path(__file__).parent / "data" / "cure_native_sample.txt.gz"   # Cure, ticks 0, 1, 15, 16
EXE = ROOT / "extracted_files/FF8_EN.exe"
MAGIC, BATTLE = ROOT / "extracted_files/magic", ROOT / "extracted_files/battle"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def xy(x, y):
    return (y & 0xFFFF) << 16 | (x & 0xFFFF)


def test_flat_and_gouraud_polygons():
    gpu = Gpu(background=(0, 0, 0))
    gpu.draw_packet([0x200000FF, xy(10, 10), xy(60, 10), xy(10, 60)])     # F3 red
    assert tuple(gpu.image()[15, 15]) == (255, 0, 0) and tuple(gpu.image()[55, 55]) == (0, 0, 0)
    gpu.draw_packet([0x38000000 | 0x00FF00, xy(100, 10), 0x00FF00, xy(150, 10), 0x00FF00, xy(100, 60),
                     0x00FF00, xy(150, 60)])                                         # G4 green quad
    assert tuple(gpu.image()[50, 140]) == (0, 255, 0) and gpu.counts["polygons"] == 2
    gpu.draw_packet([0x220000FF, xy(10, 10), xy(60, 10), xy(10, 60)])    # semi F3: mode 0 = average
    assert tuple(gpu.image()[15, 15]) == (255, 0, 0)       # 255/2 + 255/2 on red, 0 + 0 elsewhere


def test_textured_sprite_through_a_clut():
    vram = Vram()
    vram.upload(0, 480, 2, 1, [0x0000, 0x801F])             # CLUT: 0 transparent, 1 red with STP
    vram.upload(64, 0, 2, 2, [0x0101, 0x0101, 0x0100, 0x0101])   # 8-bit texels (two per word)
    gpu = Gpu(vram, background=(0, 0, 50))
    clut = (480 << 6) | 0
    gpu.draw_packet([0xE1000000 | 0x0081, 0x65808080, xy(20, 20), clut << 16, (4 << 16) | 4])
    image = gpu.image()
    assert tuple(image[20, 20]) == (255, 0, 0) and tuple(image[22, 20]) == (0, 0, 50)  # texel 0: transparent
    gpu.draw_packet([0xE1000000 | 0x00A1, 0x67808080, xy(20, 20), clut << 16, (4 << 16) | 4])  # semi, mode 1
    assert tuple(gpu.image()[20, 20]) == (255, 0, 0)       # additive: red + red, clamped
    assert not gpu.missing_pages
    gpu.draw_packet([0xE1000000 | 0x0089, 0x65808080, xy(40, 40), clut << 16, (4 << 16) | 4])  # page 9: empty
    assert 0x89 in gpu.missing_pages


def test_recording_lines_and_held_frames_skipped():
    lines = ["V 0 0 0 1 1 7FFF", "R 0 1", "P 0 0 0 0 0 0 0 45C7A0 100 4 20FFFFFF 0 A A0000",
             "C 0 10 20 30 1 2 3", "H 0 1", "P 0 0 0 0 0 0 0 45C7A0 100 4 20FF0000 0 A A0000",
             "R 1 0", "B 1 0 0 1 1 5 5"]
    recording = parse_recording(lines, 9)
    assert len(recording.ticks) == 2 and len(recording.ticks[0].packets) == 1        # the held frame is not a tick
    assert recording.ticks[0].camera == ((10, 20, 30), (1, 2, 3))
    assert recording.pre_uploads[0][:5] == ("V", 0, 0, 1, 1) and recording.ticks[1].uploads[0][0] == "B"
    assert recording.vram_at(1).words[5, 5] == 0x7FFF                                 # the copy applied


@pytest.mark.skipif(not SAMPLE.exists(), reason="sample recording missing")
def test_cure_sample_draws_its_sparkles():
    recording = load_recording(SAMPLE, 1)
    assert len(recording.ticks) == 4 and recording.has_vram
    vram = recording.vram_at(0)
    assert vram.written[256:512, 384:640].all() and vram.written[240:242, 320:576].all()   # mag000-049.tim
    view = recording.fit_view()
    image, gpu = recording.frame(3, view=view, scale=0.5)
    lit = image.astype(int).sum(axis=2) > 200
    assert lit.mean() > 0.02 and image[..., 2].mean() > image[..., 0].mean()             # blue light, plenty
    assert gpu.counts["polygons"] > 100 and gpu.missing_pages                              # the target model: grey
    game, _gpu = recording.frame(3, scale=0.125)            # the game window: 2560 x 1792 units
    assert game.shape == (224, 320, 3)


@pytest.mark.skipif(not SAMPLE.exists(), reason="sample recording missing")
def test_fujin_native_preview_view(qapp):
    from Fujin.fujinwidget import FujinWidget
    fujin = FujinWidget()
    view = fujin.native_preview
    assert fujin.tabs.widget(0) is fujin.overview_splitter and fujin.overview_splitter.widget(1) is view
    assert "Native preview" not in [fujin.choreography.tabText(i) for i in range(fujin.choreography.count())]
    assert any("a8def.tim" in label for label, _cb in fujin.complementary_entries())
    assert view.textures_binding in fujin.file_bindings()
    fujin.select_effect(1)
    view.load_recording_file(str(SAMPLE))
    assert view.slider.maximum() == 3 and "Effect 1" in view.status.text()
    view.slider.setValue(3)
    assert view.picture.pixmap() is not None and view.frame(3)[0].width() == 640   # the game window
    view.view_mode.setCurrentIndex(1)
    assert view.frame(3)[0].width() == 560                            # fit the effect
    assert "Flat grey" in view.status.text()


@pytest.mark.skipif(not EXE.exists(), reason="FF8_EN.exe not extracted")
def test_effect_camera_lines():
    from FF8GameData.gamedata import GameData
    from Fujin.cameraeffectmanager import CameraEffectManager
    from Fujin.nativepreview import BattleCast, camera_lines
    cameras = CameraEffectManager(GameData(str(ROOT / "FF8GameData")))
    cameras.load_exe(str(EXE))
    dummy = str(BATTLE / "c0m000.dat")
    lines = camera_lines(cameras, cameras.track(1), BattleCast({0: (dummy, None), 3: (dummy, None)}, 0, 3))
    assert len(lines) > 10 and all(len(line.split()) == 9 for line in lines)
    first = [int(value) for value in lines[0].split()]
    assert first[0] == 0 and first[4:7] == [0, 0, -3000]               # Cure's camera looks at the target



@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/magic/mag000-049.tim",
                     "extracted_files/battle/a8def.tim", "extracted_files/battle/d0c000.dat",
                     "extracted_files/battle/d0w000.dat", "extracted_files/battle/c0m009.dat")
def test_effect_preview_records_the_camera_preview_battle(qapp):
    """The cast is the Camera tab preview's: Squall (with his gunblade) in party slot 0, an imported
    monster in enemy slot 3; picking the caster here picks it there; the recording draws both."""
    from Fujin import nativepreview
    from Fujin.fujinwidget import FujinWidget
    if not nativepreview.RECORDER.is_file():
        pytest.skip("the effect recorder is not built")
    fujin = FujinWidget()
    fujin.import_paths([str(MAGIC / "mag000-049.tim")])
    fujin.camera_editor.exe_binding.open_path(str(EXE))
    view = fujin.native_preview
    view.textures_binding.open_path(str(BATTLE / "a8def.tim"))
    squall, gunblade, monster = (str(BATTLE / name) for name in ("d0c000.dat", "d0w000.dat", "c0m009.dat"))
    preview = fujin.camera_editor.preview
    preview.add_models([squall, gunblade, monster])
    view.refresh_cast()
    assert [view.caster_combo.itemText(i) for i in range(view.caster_combo.count())] ==         [preview.caster_combo.itemText(i) for i in range(preview.caster_combo.count())]
    assert view.cast().slots == {0: (squall, gunblade), 3: (monster, None)}
    assert (view.cast().caster, view.cast().target) == (0, 3)
    view.caster_combo.setCurrentIndex(next(i for i in range(view.caster_combo.count())
                                           if view.caster_combo.itemData(i) == ("monster", monster)))
    view.caster_combo.activated.emit(view.caster_combo.currentIndex())          # the monster casts, on Squall
    assert preview.caster_key() == ("monster", monster) and preview.target_key() == ("party", 0)
    assert (view.cast().caster, view.cast().target) == (3, 0)
    fujin.select_effect(1)
    if os.path.exists(nativepreview.recording_path(1, view.cast().key())):
        os.remove(nativepreview.recording_path(1, view.cast().key()))
    assert view.record()
    wait_for_preview(qapp, view)
    # the monster's cast (its sequence 11, seen wide), then Cure's 51 ticks
    cast_ticks = len(view.recording.ticks) - 51
    assert view.recording is not None and cast_ticks > 0 and view.camera_used
    image, gpu = view.recording.frame(0, scale=0.125)
    assert not gpu.missing_pages and gpu.counts["polygons"] > 150              # Squall drawn, textured
    image, gpu = view.recording.frame(cast_ticks + 16, scale=0.125)
    assert not gpu.missing_pages and gpu.counts["polygons"] > 100              # the effect, all textured
    # Cure's rays (untextured semi-transparent polygons) take their mode from the draw-mode packet
    # inserted after them, which the console runs first: B + F, light added, not a darkening B/2 + F/2
    ordered = [words for tick in view.recording.ticks for _bucket, _order, words in tick.packets]
    rays = [index for index, words in enumerate(ordered) if words and words[0] >> 24 in (0x32, 0x3A)]
    assert rays and all(ordered[index - 1][0] >> 24 == 0xE1 and (ordered[index - 1][0] >> 5) & 3 == 1
                        for index in rays)
    assert (image.astype(int).sum(axis=2) > 200).mean() > 0.01                 # in the game window


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/magic/mag000-049.tim",
                     "extracted_files/battle/a8def.tim", "extracted_files/battle/scene.out",
                     "extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat",
                     "extracted_files/battle/c0m014.dat")
def test_effect_preview_plays_a_scene_out_encounter(qapp):
    """Only files opened one by one: without models Play is off, a8def.tim is an optional side
    file; the Battle picker is the Camera tab setup's encounter list, its enemies placed where
    scene.out has them - an enemy not imported is named and left out (no target: no Record); Play
    records first."""
    from Fujin import nativepreview
    from Fujin.fujinwidget import FujinWidget
    if not nativepreview.RECORDER.is_file():
        pytest.skip("the effect recorder is not built")
    fujin = FujinWidget()
    fujin.import_paths([str(MAGIC / "mag000-049.tim")])
    fujin.camera_editor.exe_binding.open_path(str(EXE))
    fujin.select_effect(1)
    view = fujin.native_preview
    assert not view.play_button.isEnabled() and any("caster model" in need for need in view.missing())
    assert any("a8def.tim" in label for label, _cb in fujin.complementary_entries())   # a side file
    view.textures_binding.open_path(str(BATTLE / "a8def.tim"))
    preview = fujin.camera_editor.preview
    preview.sceneout_binding.open_path(str(BATTLE / "scene.out"))
    preview.add_models([str(BATTLE / "d0c000.dat"), str(BATTLE / "d0w000.dat")])
    view._load_battle()
    index = next(i for i in range(view.encounter_combo.count())
                 if view.encounter_combo.itemText(i).startswith("Encounter 20 "))
    view.encounter_combo.setCurrentIndex(index)
    view.encounter_combo.activated.emit(index)
    assert preview.encounter_combo().currentIndex() == index                    # the Camera tab's pick too
    assert view.cast().not_imported == ["c0m014.dat"] and 3 not in view.cast().slots   # never read from a folder
    assert any("target model" in need and "c0m014.dat" in need for need in view.missing())
    assert not view.play_button.isEnabled()
    preview.add_models([str(BATTLE / "c0m014.dat")])
    view.refresh_cast()
    assert view.play_button.isEnabled()
    cast = view.cast(placed=True)
    assert cast.slots[3] == (str(BATTLE / "c0m014.dat"), None) and (cast.caster, cast.target) == (0, 3)
    assert cast.positions[3] == (-500.0, 0.0, -2500.0)                          # scene.out's place
    cached = nativepreview.recording_path(1, cast.key())
    if os.path.exists(cached):
        os.remove(cached)
    view.set_effect(None)
    view.set_effect(1, "Cure")
    view.play_button.setChecked(True)                                           # records, then plays
    wait_for_preview(qapp, view)
    assert view.recording is not None and len(view.recording.ticks) > 51 and view.timer.isActive()   # cast + Cure
    view.play_button.setChecked(False)


def wait_for_preview(qapp, view):
    """Wait for both the debounced edit and its recorder, including an edit queued mid-record."""
    deadline = time.monotonic() + 30
    while view._process is not None or view._edit_refresh.isActive():
        assert time.monotonic() < deadline, view.status.text()
        if view._process is not None:
            view._process.waitForFinished(1000)
        QTest.qWait(20)
        qapp.processEvents()


@pytest.mark.ff8data("extracted_files/magic/mag000-049.tim", "extracted_files/FF8_EN.exe",
                     "extracted_files/battle/a8def.tim", "extracted_files/battle/c0m000.dat",
                     "extracted_files/battle/d0c000.dat")
def test_cure_previews_unsaved_png_and_undo(qapp, tmp_path, monkeypatch):
    from Fujin import nativepreview
    from Fujin.fujinwidget import FujinWidget
    if not nativepreview.RECORDER.is_file():
        pytest.skip("the effect recorder is not built")
    # Isolate the disk cache too: unsaved previews must not replace a clean recording.
    cached = tmp_path / "clean_recording.txt"
    monkeypatch.setattr(nativepreview, "recording_path", lambda *_args: str(cached))
    path = tmp_path / "mag000-049.tim"
    original = (MAGIC / path.name).read_bytes()
    path.write_bytes(original)
    fujin = FujinWidget()
    fujin.import_paths([str(path)])
    fujin.camera_editor.exe_binding.open_path(str(EXE))
    fujin.select_effect(1)
    view = fujin.native_preview
    view.textures_binding.open_path(str(BATTLE / "a8def.tim"))
    fujin.camera_editor.preview.add_models([str(BATTLE / "d0c000.dat"), str(BATTLE / "c0m000.dat")])
    view.refresh_cast()
    assert view.record()
    wait_for_preview(qapp, view)
    assert len(view.recording.ticks) == 51
    baseline, _gpu = view.recording.frame(16, scale=0.125)
    clean_cache = cached.read_bytes()
    view.slider.setValue(16)

    fujin.tabs.setCurrentIndex(4)
    fujin.textures.activate()
    card = fujin.textures.panel.cards[0]
    picture = card.texture.picture().copy()
    picture[64:128, :64] = 0                         # remove Cure's little sparkles
    yy, xx = np.mgrid[:64, :64]
    picture[:64, :64] = 0
    picture[:64, :64][np.abs(xx-32)+np.abs(yy-32) < 20] = (0, 255, 255, 128)
    png = tmp_path / "diamonds.png"
    Image.fromarray(picture).save(png)
    assert card.import_picture(str(png))              # the real UI signal schedules the refresh
    assert view._edit_refresh.isActive()
    wait_for_preview(qapp, view)
    changed, gpu = view.recording.frame(16, scale=0.125)
    assert not np.array_equal(changed, baseline) and not gpu.missing_pages
    assert view.slider.value() == 16 and "unsaved" in view.status.text()
    assert card.texture.manager.modified and path.read_bytes() == original
    assert cached.read_bytes() == clean_cache and view._scratch is None

    fujin.show()                                     # Undo routes to the visible resource editor
    qapp.processEvents()
    assert fujin.undo()                              # no Save, Undo also refreshes the preview
    wait_for_preview(qapp, view)
    restored, _gpu = view.recording.frame(16, scale=0.125)
    assert np.array_equal(restored, baseline)
    assert view.slider.value() == 16 and not view._recorded_edits
    assert not card.texture.manager.modified and path.read_bytes() == original
    assert fujin.redo()
    wait_for_preview(qapp, view)
    redone, _gpu = view.recording.frame(16, scale=0.125)
    assert np.array_equal(redone, changed) and view.slider.value() == 16
    assert card.texture.manager.modified and path.read_bytes() == original


@pytest.mark.parametrize("latest", [b"latest", None])
def test_edits_during_first_recording_request_a_fresh_snapshot(qapp, monkeypatch, latest):
    from Common.fileregistry import FileRegistry
    from Fujin.nativepreview import NativePreviewView
    edits = {"atlas.tim": b"first"}
    view = NativePreviewView(FileRegistry(), file_edits=lambda: edits)
    view.effect_id = 1
    view._preview_requested = True
    old_signature = view._edit_signature(edits)
    if latest is None:
        edits.clear()                               # Undo to clean before the first run finishes
    else:
        edits["atlas.tim"] = latest
    requests = []
    monkeypatch.setattr(view, "record", lambda keep_tick=False: requests.append(keep_tick))
    view._load_recorded(1, "discarded-recording.txt", 0, old_signature, 16, 0, "")
    QTest.qWait(300)
    assert requests == [True] and view.recording is None


def test_failed_recorder_releases_unsaved_snapshot(qapp, tmp_path, monkeypatch):
    from Common.fileregistry import FileRegistry
    from Fujin import nativepreview
    view = nativepreview.NativePreviewView(FileRegistry(), file_edits=lambda: {"atlas.tim": b"edit"})
    view.effect_id = 1
    monkeypatch.setattr(view, "missing", lambda: [])
    monkeypatch.setattr(nativepreview, "RECORDER", tmp_path / "missing-recorder.exe")
    snapshots = []
    temporary_directory = nativepreview.tempfile.TemporaryDirectory

    def snapshot_directory(**kwargs):
        scratch = temporary_directory(dir=tmp_path, **kwargs)
        snapshots.append(Path(scratch.name))
        return scratch

    monkeypatch.setattr(nativepreview.tempfile, "TemporaryDirectory", snapshot_directory)
    assert view.record()
    wait_for_preview(qapp, view)
    assert snapshots and not snapshots[0].exists() and view._scratch is None
    assert "Could not start" in view.status.text() and view.play_button.isEnabled()


def test_opengl_draws_the_same_picture_as_the_software_gpu():
    """The OpenGL renderer (what plays the preview at 15 frames per second) against the software
    Gpu on Cure's sample. OpenGL needs a real window platform: run apart (the tests' platform is
    offscreen); skipped without OpenGL 3.3."""
    import subprocess
    script = (
        "import sys, numpy as np\n"
        "from PyQt6.QtWidgets import QApplication\n"
        "app = QApplication([])\n"
        "from FF8GameData.psxgpu.fxdump import load_recording\n"
        "from FF8GameData.psxgpu.glrender import PsxGlRenderer\n"
        "renderer = PsxGlRenderer.create()\n"
        "if renderer is None:\n"
        "    print('NO-GL'); sys.exit(0)\n"
        "recording = load_recording(sys.argv[1], 1)\n"
        "for tick in range(len(recording.ticks)):\n"
        "    gl, gl_gpu = recording.frame(tick, scale=0.25, renderer=renderer)\n"
        "    soft, soft_gpu = recording.frame(tick, scale=0.25)\n"
        "    off = (np.abs(gl.astype(int) - soft.astype(int)).max(axis=2) > 24).mean()\n"
        "    assert gl.shape == soft.shape and gl_gpu.counts == soft_gpu.counts and off < 0.01, (tick, off)\n"
        "print('SAME')\n")
    environment = dict(os.environ, QT_QPA_PLATFORM="windows" if sys.platform == "win32" else "xcb")
    result = subprocess.run([sys.executable, "-c", script, str(SAMPLE)], cwd=str(ROOT), env=environment,
                            capture_output=True, text=True, timeout=300)
    if "NO-GL" in result.stdout or (result.returncode and "could not connect to display" in result.stderr):
        pytest.skip("no OpenGL 3.3 context here")
    assert "SAME" in result.stdout, result.stdout + result.stderr
