"""Tests for Minimog's two export flows.

icon.TEX only stores palette indices, not colors, so there are two different
things "export as PNG" can mean:
  - export_tex_png(): the raw atlas under ONE palette the user picks (for
    inspecting/editing the texture itself)
  - export_true_colors(): the SAME atlas layout/size, but each region
    resolved through whichever icon.sp1 quad actually claims it - the true
    in-game colors, with no palette to pick (e.g. why "Target" is red)

These tests drive both through the real widget (mocking only the modal
dialogs Qt would show); needs icon.sp1 + icon.TEX so everything here is
ff8data.
"""
import pathlib
import sys

import pytest
from PyQt6.QtWidgets import QApplication

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MENU_DIR = PROJECT_ROOT / "extracted_files" / "menu"

pytestmark = pytest.mark.ff8data("extracted_files/menu/icon.sp1", "extracted_files/menu/icon.TEX")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def widget(qapp):
    from Minimog.minimogwidget import MinimogWidget
    w = MinimogWidget()
    w.manager.load_file(str(MENU_DIR / "icon.sp1"))
    w._auto_load_tex(str(MENU_DIR))
    w.editor_container.setEnabled(True)
    w.icon_list.addItems([f"{icon.name} ({len(icon.quads)})" for icon in w.manager.icons])
    return w


def test_export_buttons_disabled_until_tex_is_loaded(qapp):
    from Minimog.minimogwidget import MinimogWidget
    w = MinimogWidget()
    assert not w.export_tex_button.isEnabled()
    assert not w.export_true_colors_button.isEnabled()
    w.manager.load_file(str(MENU_DIR / "icon.sp1"))
    assert not w.export_tex_button.isEnabled(), "loading the sp1 alone isn't enough, TEX is what's exported"
    assert not w.export_true_colors_button.isEnabled()
    w._auto_load_tex(str(MENU_DIR))
    assert w.export_tex_button.isEnabled()
    assert w.export_true_colors_button.isEnabled()


def test_export_writes_the_chosen_palette(widget, tmp_path, monkeypatch):
    from FF8GameData.tex.texfile import TexFile
    out_path = tmp_path / "exported"
    monkeypatch.setattr("Minimog.minimogwidget.TexPalettePickerDialog.get_palette",
                        staticmethod(lambda parent, tex_file, default_palette: (5, True)))
    monkeypatch.setattr(widget.file_dialog, "getSaveFileName", lambda **kw: (str(out_path), "*.png"))

    widget.export_tex_png()

    saved = out_path.with_suffix(".png")
    assert saved.exists(), "the .png extension must be appended when the dialog omits it"
    expected = widget.tex_file.to_image(5)
    actual = TexFile.read(str(MENU_DIR / "icon.TEX")).to_image(5)  # sanity: same source
    assert expected.tobytes() == actual.tobytes()
    from PIL import Image
    assert Image.open(saved).convert("RGBA").tobytes() == expected.tobytes()


def test_export_uses_a_different_palette_gives_different_pixels(widget, tmp_path, monkeypatch):
    from PIL import Image
    results = []
    for palette in (0, 2):
        out_path = tmp_path / f"p{palette}.png"
        monkeypatch.setattr(
            "Minimog.minimogwidget.TexPalettePickerDialog.get_palette",
            staticmethod(lambda parent, tex_file, default_palette, palette=palette: (palette, True)))
        monkeypatch.setattr(widget.file_dialog, "getSaveFileName", lambda **kw: (str(out_path), "*.png"))
        widget.export_tex_png()
        results.append(Image.open(out_path).tobytes())
    assert results[0] != results[1], "palette 0 and palette 2 must not render identically"


def test_cancelling_the_palette_prompt_writes_nothing(widget, tmp_path, monkeypatch):
    out_path = tmp_path / "should_not_exist.png"
    monkeypatch.setattr("Minimog.minimogwidget.TexPalettePickerDialog.get_palette",
                        staticmethod(lambda parent, tex_file, default_palette: (0, False)))
    monkeypatch.setattr(widget.file_dialog, "getSaveFileName", lambda **kw: (str(out_path), "*.png"))

    widget.export_tex_png()

    assert not out_path.exists()


def test_default_palette_comes_from_the_selected_quad(widget, monkeypatch):
    widget.icon_list.setCurrentRow(1)
    widget.quad_list.setCurrentRow(0)
    expected_default = widget.manager.icons[1].quads[0].palette_index

    seen = {}
    def fake_get_palette(parent, tex_file, default_palette):
        seen["value"] = default_palette
        return default_palette, False  # cancel, we only care what was passed in
    monkeypatch.setattr("Minimog.minimogwidget.TexPalettePickerDialog.get_palette",
                        staticmethod(fake_get_palette))

    widget.export_tex_png()

    assert seen["value"] == expected_default


def test_export_true_colors_matches_the_tex_png_layout(widget, tmp_path, monkeypatch):
    """The whole point: same canvas size/positions as export_tex_png(), not the
    grid-by-icon-id layout render_sheet() uses."""
    out_path = tmp_path / "true_colors"
    monkeypatch.setattr(widget.file_dialog, "getSaveFileName", lambda **kw: (str(out_path), "*.png"))

    widget.export_true_colors()

    saved = out_path.with_suffix(".png")
    assert saved.exists(), "the .png extension must be appended when the dialog omits it"
    from PIL import Image
    result = Image.open(saved)
    assert result.size == (widget.tex_file.width, widget.tex_file.height)


def test_export_true_colors_uses_each_icon_s_own_stored_clut(widget, tmp_path, monkeypatch):
    """Unlike export_tex_png() (one global palette), the pixels at icon 15's
    ("Target") own UV rectangle must come out red with no palette picked."""
    out_path = tmp_path / "true_colors.png"
    monkeypatch.setattr(widget.file_dialog, "getSaveFileName", lambda **kw: (str(out_path), "*.png"))

    widget.export_true_colors()

    from PIL import Image
    result = Image.open(out_path).convert("RGBA")
    quad = widget.manager.icons[15].quads[0]
    r, g, b, a = result.getpixel((quad.u + 8, quad.v + 4))
    assert a != 0 and r > 120 and r > g + 30, "Target's own UV rectangle should be red"


def test_export_true_colors_matches_manager_render_texture_true_colors(widget, tmp_path, monkeypatch):
    out_path = tmp_path / "true_colors.png"
    monkeypatch.setattr(widget.file_dialog, "getSaveFileName", lambda **kw: (str(out_path), "*.png"))

    widget.export_true_colors()

    from PIL import Image
    expected = widget.manager.render_texture_true_colors(widget.tex_file)
    assert Image.open(out_path).convert("RGBA").tobytes() == expected.tobytes()
