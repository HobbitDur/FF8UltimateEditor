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

COMPLEMENTARY_NAMES = ("mngrp.bin", "kernel.bin", "mwepon.bin", "icon.sp1", "mitem.bin")


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
    zone._update_tooltips()
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


def test_the_two_dialogs_split_the_edited_file_from_the_rest():
    """The open button is mmag.bin only; everything else is a complementary file."""
    from Zone.zonewidget import (COMPLEMENTARY_FILES, COMPLEMENTARY_FILTER, MAIN_FILE,
                                 MAIN_FILTER)
    assert MAIN_FILE == "mmag.bin" and MAIN_FILE in MAIN_FILTER
    assert set(COMPLEMENTARY_FILES) == {"mngrp.bin", "kernel.bin", "mwepon.bin",
                                        "icon.sp1", "mitem.bin"}
    assert MAIN_FILE not in COMPLEMENTARY_FILES
    for name in COMPLEMENTARY_FILES:  # the dialog is filtered to the exact names
        assert name in COMPLEMENTARY_FILTER


def test_complementary_files_load_several_at_once(qapp, monkeypatch):
    """One trip through the dialog can bring in any number of them."""
    from Zone.zonewidget import ZoneWidget
    zone = ZoneWidget()
    zone._load_mmag(str(MENU_DIR / "mmag.bin"))

    # Deliberately not the declared order: mngrp.bin, which builds the renderer,
    # is picked in the middle.
    picked = [str(MENU_DIR / "mitem.bin"), str(MENU_DIR / "icon.sp1"),
              str(MENU_DIR / "mngrp.bin"), str(MENU_DIR / "mwepon.bin"),
              str(PROJECT_ROOT / "extracted_files" / "main" / "kernel.bin")]
    monkeypatch.setattr(zone.file_dialog, "getOpenFileNames",
                        lambda *a, **k: (picked, ""))
    zone.load_complementary_files()

    assert zone.manager.mngrp_loaded and zone.manager.kernel_loaded
    assert zone.manager.mwepon_loaded and zone.manager.icons_loaded
    assert zone.manager.mitem_loaded
    assert zone.renderer is not None
    QTest.qWait(DEBOUNCE_WAIT)
    assert zone.preview_label.pixmap() is not None


def test_the_pick_order_of_complementary_files_does_not_matter(qapp, monkeypatch):
    """Nothing here is sequenced: each file only fills in its own part of the
    manager, which the renderer reads as it draws. So no batching is needed."""
    from Zone.zonewidget import ZoneWidget
    kernel = str(PROJECT_ROOT / "extracted_files" / "main" / "kernel.bin")
    orders = [
        [str(MENU_DIR / "mngrp.bin"), kernel, str(MENU_DIR / "mwepon.bin"),
         str(MENU_DIR / "icon.sp1"), str(MENU_DIR / "mitem.bin")],
        # mngrp.bin dead last, everything else loaded before the renderer exists
        [str(MENU_DIR / "mitem.bin"), str(MENU_DIR / "icon.sp1"),
         str(MENU_DIR / "mwepon.bin"), kernel, str(MENU_DIR / "mngrp.bin")],
    ]
    renders = []
    for picked in orders:
        zone = ZoneWidget()
        zone._load_mmag(str(MENU_DIR / "mmag.bin"))
        monkeypatch.setattr(zone.file_dialog, "getOpenFileNames", lambda *a, **k: (picked, ""))
        zone.load_complementary_files()
        zone.entry_list.setCurrentRow(28)  # Combat King: uses kernel + icons
        QTest.qWait(DEBOUNCE_WAIT)
        renders.append(zone.preview_label.pixmap().toImage())
    assert renders[0] == renders[1]


def test_complementary_files_can_be_added_over_several_trips(qapp, monkeypatch):
    from Zone.zonewidget import ZoneWidget
    zone = ZoneWidget()
    zone._load_mmag(str(MENU_DIR / "mmag.bin"))

    monkeypatch.setattr(zone.file_dialog, "getOpenFileNames",
                        lambda *a, **k: ([str(MENU_DIR / "mngrp.bin")], ""))
    zone.load_complementary_files()
    assert zone.manager.mngrp_loaded and not zone.manager.kernel_loaded

    # Coming back later must add to what is there, not replace it
    monkeypatch.setattr(zone.file_dialog, "getOpenFileNames", lambda *a, **k: (
        [str(PROJECT_ROOT / "extracted_files" / "main" / "kernel.bin")], ""))
    zone.load_complementary_files()
    assert zone.manager.mngrp_loaded and zone.manager.kernel_loaded


def test_complementary_button_is_greyed_until_mmag_is_open(qapp):
    """The one order that is forced is shown, not enforced with a popup."""
    from Zone.zonewidget import ZoneWidget
    zone = ZoneWidget()
    assert zone.complementary_button.isEnabled() is False
    # Greyed, but Qt still shows its tooltip, so the reason stays readable
    assert "Greyed out until mmag.bin is open" in zone.complementary_button.toolTip()

    zone._load_mmag(str(MENU_DIR / "mmag.bin"))
    zone._update_tooltips()
    assert zone.complementary_button.isEnabled() is True
    assert "Greyed out until" not in zone.complementary_button.toolTip()


def test_hovering_the_buttons_explains_them(qapp):
    from Zone.zonewidget import ZoneWidget
    zone = ZoneWidget()
    main_tip = zone.load_button.toolTip()
    assert "mmag.bin" in main_tip and "Nothing open yet" in main_tip

    tooltip = zone.complementary_button.toolTip()
    assert "as many as you like at once" in tooltip, "multi-select must be explained"
    assert "come back to this button" in tooltip, "reopening must be explained"
    for name in COMPLEMENTARY_NAMES:
        assert name in tooltip, f"{name} should be described on hover"
    assert "✔" not in tooltip, "nothing is loaded yet"
    assert "Still missing" in tooltip

    zone._load_mmag(str(MENU_DIR / "mmag.bin"))
    zone._load_kernel(str(PROJECT_ROOT / "extracted_files" / "main" / "kernel.bin"))
    zone._update_tooltips()
    assert "mmag.bin</b>" in zone.load_button.toolTip()
    tooltip = zone.complementary_button.toolTip()
    assert "✔ <b>kernel.bin</b>" in tooltip
    assert "– <b>mngrp.bin</b>" in tooltip, "mngrp.bin is not loaded yet"


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
