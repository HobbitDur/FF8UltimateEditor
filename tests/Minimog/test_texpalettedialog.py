"""Tests for TexPalettePickerDialog: the live-preview palette picker used by
Minimog's "Export by palette" button. Needs the real icon.TEX so its
16 real palettes are available to pick between; everything here is ff8data.
"""
import pathlib
import sys

import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QDialog

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
ICON_TEX = PROJECT_ROOT / "extracted_files" / "menu" / "icon.TEX"

pytestmark = pytest.mark.ff8data("extracted_files/menu/icon.TEX")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture(scope="module")
def tex_file():
    from FF8GameData.tex.texfile import TexFile
    return TexFile.read(str(ICON_TEX))


def test_spinbox_range_matches_the_texture_s_palette_count(qapp, tex_file):
    from Minimog.texpalettedialog import TexPalettePickerDialog
    dialog = TexPalettePickerDialog(None, tex_file)
    assert dialog.palette_spinbox.minimum() == 0
    assert dialog.palette_spinbox.maximum() == tex_file.num_palettes - 1 == 15


def test_default_palette_is_preselected(qapp, tex_file):
    from Minimog.texpalettedialog import TexPalettePickerDialog
    dialog = TexPalettePickerDialog(None, tex_file, default_palette=7)
    assert dialog.palette_index == 7
    assert dialog.palette_spinbox.value() == 7


def test_out_of_range_default_is_clamped(qapp, tex_file):
    from Minimog.texpalettedialog import TexPalettePickerDialog
    dialog = TexPalettePickerDialog(None, tex_file, default_palette=99)
    assert dialog.palette_index == tex_file.num_palettes - 1


def test_changing_the_palette_updates_the_live_preview(qapp, tex_file):
    from Minimog.texpalettedialog import TexPalettePickerDialog
    dialog = TexPalettePickerDialog(None, tex_file, default_palette=0)
    before = dialog.preview_label.pixmap().toImage().copy()

    dialog.palette_spinbox.setValue(2)

    after = dialog.preview_label.pixmap().toImage().copy()
    assert after != before, "palette 0 and palette 2 must not preview identically"


def test_preview_pixmap_matches_the_scaled_texture_render(qapp, tex_file):
    from Minimog.texpalettedialog import TexPalettePickerDialog, PREVIEW_SCALE
    dialog = TexPalettePickerDialog(None, tex_file, default_palette=3)
    pixmap = dialog.preview_label.pixmap()
    assert pixmap.width() == tex_file.width * PREVIEW_SCALE
    assert pixmap.height() == tex_file.height * PREVIEW_SCALE


def test_get_palette_returns_selected_value_on_accept(qapp, tex_file):
    from Minimog.texpalettedialog import TexPalettePickerDialog

    def accept_with_palette_9():
        dialog = QApplication.activeModalWidget()
        dialog.palette_spinbox.setValue(9)
        dialog.accept()

    QTimer.singleShot(0, accept_with_palette_9)
    palette, accepted = TexPalettePickerDialog.get_palette(None, tex_file, default_palette=0)

    assert accepted is True
    assert palette == 9


def test_get_palette_reports_cancellation(qapp, tex_file):
    from Minimog.texpalettedialog import TexPalettePickerDialog

    QTimer.singleShot(0, lambda: QApplication.activeModalWidget().reject())
    palette, accepted = TexPalettePickerDialog.get_palette(None, tex_file, default_palette=4)

    assert accepted is False
