"""Choreography > Native preview: a native effect drawn from the game's own code. The FFNx effect
harness records the PlayStation GPU packets and VRAM uploads of each tick; FF8GameData.psxgpu
draws them (decoder + software rasteriser), Fujin plays them."""
import os
import struct
import sys
from pathlib import Path

import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication

from FF8GameData.psxgpu.fxdump import load_recording, parse_recording
from FF8GameData.psxgpu.gpu import Gpu, Vram

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = Path(__file__).parent / "data" / "cure_native_sample.txt.gz"   # Cure, ticks 0, 1, 15, 16
HARNESS = Path("D:/FFNxMenu30fps/harness/fxaudit/fxaudit_held.exe")


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
    game, _gpu = recording.frame(3)
    assert game.shape == (224, 320, 3)


@pytest.mark.skipif(not SAMPLE.exists(), reason="sample recording missing")
def test_fujin_native_preview_view(qapp):
    from Fujin.fujinwidget import FujinWidget
    fujin = FujinWidget()
    view = fujin.native_preview
    assert fujin.choreography.tabText(2) == "Native preview"
    assert any("fxaudit_held.exe" in label for label, _cb in fujin.complementary_entries())
    assert view.harness_binding in fujin.file_bindings()
    fujin.select_effect(1)
    view.load_recording_file(str(SAMPLE))
    assert view.slider.maximum() == 3 and "Effect 1" in view.status.text()
    view.slider.setValue(3)
    assert view.picture.pixmap() is not None and view.frame(3)[0].width() == 560
    view.view_mode.setCurrentIndex(1)
    assert view.frame(3)[0].width() == 640                            # the game window, x2
    assert "Flat grey" in view.status.text()


@pytest.mark.skipif(not HARNESS.exists() or not (ROOT / "extracted_files/FF8_EN.exe").exists(),
                    reason="FFNx effect harness not on this PC")
def test_record_cure_with_the_harness(qapp):
    from Common.fileregistry import FileRegistry
    from Fujin.nativepreview import NativePreviewView, recording_path
    registry = FileRegistry()
    view = NativePreviewView(registry)
    view.harness_binding.open_path(str(HARNESS))
    view.set_effect(1, "Cure")
    if os.path.exists(recording_path(1)):
        os.remove(recording_path(1))
    view.set_effect(None)
    view.set_effect(1, "Cure")
    assert view.record()
    assert view._process.waitForFinished(120000)
    QApplication.processEvents()
    assert view.recording is not None and len(view.recording.ticks) == 51 and view.recording.has_vram
