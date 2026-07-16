"""Tests for the Zone widget's live page preview.

Editing any form value must redraw the preview on its own (no button), and a
burst of changes must coalesce into a single render rather than one per step.

Needs the real art/text out of mngrp.bin, so everything here is ff8data.
"""
import pathlib
import sys

import pytest
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MENU_DIR = PROJECT_ROOT / "extracted_files" / "menu"

pytestmark = pytest.mark.ff8data("extracted_files/menu/mmag.bin",
                                 "extracted_files/menu/mngrp.bin",
                                 "extracted_files/menu/mngrphd.bin",
                                 "extracted_files/menu/mwepon.bin",
                                 "extracted_files/menu/mitem.bin",
                                 "extracted_files/menu/icon.sp1",
                                 "extracted_files/menu/icon.TEX",
                                 "extracted_files/main/kernel.bin",
                                 "extracted_files/menu/sysfnt.TEX",
                                 "extracted_files/menu/sysfnt.tdw")

# Comfortably longer than the widget's 40 ms debounce.
DEBOUNCE_WAIT = 150


@pytest.fixture(scope="module")
def qapp():
    # ZoneWidget builds real Qt widgets, so a QApplication must exist.
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def widget(qapp):
    """A ZoneWidget with every file loaded, showing entry 0.

    Loaded through the same per-file methods the open dialog dispatches to.
    Function-scoped: the tests edit the loaded entries in place.
    """
    from Zone.zonewidget import ZoneWidget
    zone = ZoneWidget()
    zone._load_mmag(str(MENU_DIR / "mmag.bin"))
    zone._load_mngrp(str(MENU_DIR / "mngrp.bin"))
    zone._load_kernel(str(PROJECT_ROOT / "extracted_files" / "main" / "kernel.bin"))
    zone._load_mwepon(str(MENU_DIR / "mwepon.bin"))
    zone._load_icons(str(MENU_DIR / "icon.sp1"))
    zone._load_mitem(str(MENU_DIR / "mitem.bin"))
    zone._update_load_tooltip()
    zone._refresh_preview()
    return zone


def _snapshot(widget):
    return widget.preview_label.pixmap().toImage().copy()


def _count_renders(widget, calls):
    real = widget.renderer.render

    def counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    widget.renderer.render = counting
    return real


def test_editing_a_value_redraws_the_preview(widget):
    before = _snapshot(widget)
    widget.pic_tint_r.setValue(255)
    QTest.qWait(DEBOUNCE_WAIT)
    assert _snapshot(widget) != before
    # The edit also reached the entry, so a save would keep it
    assert widget.manager.entries[0].picture_tint_r == 255


def test_overlay_spin_boxes_are_wired_too(widget):
    before = _snapshot(widget)
    widget.text_overlay_spins[0][1].setValue(90)  # move the title's Y
    QTest.qWait(DEBOUNCE_WAIT)
    assert _snapshot(widget) != before


def test_combo_boxes_and_check_boxes_are_wired_too(widget):
    before = _snapshot(widget)
    widget.footer_flag.setChecked(not widget.footer_flag.isChecked())
    QTest.qWait(DEBOUNCE_WAIT)
    assert _snapshot(widget) != before
    assert widget.manager.entries[0].footer_flag == 0


def test_a_burst_of_changes_coalesces_into_one_render(widget):
    calls = []
    _count_renders(widget, calls)
    for value in range(60, 120):
        widget.pic_tint_g.setValue(value)
    QTest.qWait(DEBOUNCE_WAIT)
    assert len(calls) == 1, f"the debounce should coalesce the burst, got {len(calls)} renders"
    # The last value of the burst is the one on screen
    assert widget.manager.entries[0].picture_tint_g == 119


def test_switching_entry_renders_once_not_once_per_field(widget):
    calls = []
    _count_renders(widget, calls)
    widget.entry_list.setCurrentRow(33)
    QTest.qWait(DEBOUNCE_WAIT)
    assert len(calls) == 1, f"repopulating the form must not redraw per field, got {len(calls)}"


def test_preview_is_inert_until_mngrp_is_loaded(qapp):
    """Without mngrp.bin there is no art to draw, so editing must not blow up."""
    from Zone.zonewidget import ZoneWidget
    zone = ZoneWidget()
    zone._load_mmag(str(MENU_DIR / "mmag.bin"))
    assert zone.renderer is None
    zone.pic_tint_r.setValue(200)
    QTest.qWait(DEBOUNCE_WAIT)
    assert zone.preview_label.pixmap() is None or zone.preview_label.pixmap().isNull()


def test_the_open_dialog_lists_every_file_by_exact_name():
    """One dialog, filtered to the exact names, so they are all visible at once."""
    from Zone.zonewidget import LOADABLE_FILES, LOADABLE_FILTER
    assert set(LOADABLE_FILES) == {"mmag.bin", "mngrp.bin", "kernel.bin", "mwepon.bin",
                                   "icon.sp1", "mitem.bin"}
    for name in LOADABLE_FILES:
        assert name in LOADABLE_FILTER
    # Only mmag.bin can be opened first: it holds the entries the rest decorates
    assert LOADABLE_FILES["mmag.bin"][2] is False
    assert all(needs for _m, _w, needs in
               (v for k, v in LOADABLE_FILES.items() if k != "mmag.bin"))


def test_hovering_the_open_button_says_what_is_loaded(qapp):
    from Zone.zonewidget import ZoneWidget
    zone = ZoneWidget()
    tooltip = zone.load_button.toolTip()
    for name in ("mmag.bin", "mngrp.bin", "kernel.bin", "mwepon.bin"):
        assert name in tooltip, f"{name} should be described on hover"
    assert "✔" not in tooltip, "nothing is loaded yet"

    zone._load_mmag(str(MENU_DIR / "mmag.bin"))
    zone._update_load_tooltip()
    tooltip = zone.load_button.toolTip()
    assert "✔ <b>mmag.bin</b>" in tooltip
    assert "– <b>kernel.bin</b>" in tooltip, "kernel.bin is not loaded yet"


def test_the_file_name_label_is_gone(widget):
    assert not hasattr(widget, "file_label")


def test_the_user_picks_the_duel_button_glyph(widget):
    """The engine resolves these through the key config, so the choice is offered."""
    from Zone.zonerender import BUTTON_STYLE_BOXES, BUTTON_STYLE_ICONS
    assert [widget.button_icon_combo.itemData(i) for i in range(widget.button_icon_combo.count())] \
        == [BUTTON_STYLE_ICONS, BUTTON_STYLE_BOXES]
    assert widget.renderer.button_icon_style == BUTTON_STYLE_ICONS

    widget.entry_list.setCurrentRow(32)  # Combat King 005, a 5-button combo
    QTest.qWait(DEBOUNCE_WAIT)
    with_icons = _snapshot(widget)

    widget.button_icon_combo.setCurrentIndex(1)  # -> boxes
    QTest.qWait(DEBOUNCE_WAIT)
    assert widget.renderer.button_icon_style == BUTTON_STYLE_BOXES
    assert _snapshot(widget) != with_icons


def test_hovering_the_glyph_choice_explains_it_is_a_game_setup(widget):
    tooltip = widget.button_icon_combo.toolTip()
    assert "key config" in tooltip
    assert "icon.sp1" in tooltip
