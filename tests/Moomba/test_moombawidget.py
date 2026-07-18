"""Tests for the Moomba widget's live page preview.

Editing a value or switching page must redraw the preview on its own, and a
burst of changes must coalesce into a single render. Needs the real art/text out
of mngrp.bin, so everything here is ff8data.
"""
import pathlib
import sys

import pytest
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MENU_DIR = PROJECT_ROOT / "extracted_files" / "menu"

pytestmark = pytest.mark.ff8data("extracted_files/menu/mmag2.bin",
                                 "extracted_files/menu/mngrp.bin",
                                 "extracted_files/menu/mngrphd.bin",
                                 "extracted_files/menu/sysfnt.TEX",
                                 "extracted_files/menu/sysfnt.tdw")

DEBOUNCE_WAIT = 150  # Comfortably longer than the widget's 40 ms debounce


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def widget(qapp):
    """A MoombaWidget with mmag2.bin + mngrp.bin loaded, showing page 0."""
    from Moomba.moombawidget import MoombaWidget
    moomba = MoombaWidget()
    moomba.manager.load_file(str(MENU_DIR / "mmag2.bin"))
    moomba.manager.load_mngrp(str(MENU_DIR / "mngrp.bin"))
    moomba._build_renderer(str(MENU_DIR / "mngrp.bin"))
    moomba.editor_container.setEnabled(True)
    moomba.page_list.clear()
    for entry in moomba.manager.entries:
        moomba.page_list.addItem(moomba.manager.get_entry_name(entry.entry_id))
    moomba.page_list.setCurrentRow(0)
    QTest.qWait(DEBOUNCE_WAIT)
    return moomba


def _snapshot(widget):
    return widget.preview_label.pixmap().toImage().copy()


def test_the_page_renders_once_mngrp_is_loaded(widget):
    pixmap = widget.preview_label.pixmap()
    assert pixmap is not None and not pixmap.isNull()


def test_editing_a_value_redraws_the_preview(widget):
    before = _snapshot(widget)
    widget.picture_overlay_x[0].setValue(120)  # move the art
    QTest.qWait(DEBOUNCE_WAIT)
    assert _snapshot(widget) != before
    assert widget.manager.entries[0].picture_overlays[0].x == 120  # reached the entry


def test_switching_page_redraws(widget):
    before = _snapshot(widget)
    widget.page_list.setCurrentRow(4)  # a manual page, different art + text
    QTest.qWait(DEBOUNCE_WAIT)
    assert _snapshot(widget) != before


def test_a_burst_of_changes_coalesces_into_one_render(widget):
    calls = []
    real = widget.renderer.render
    widget.renderer.render = lambda *a, **k: (calls.append(1), real(*a, **k))[1]
    for value in range(30, 90):
        widget.text_overlay_x[0].setValue(value)
    QTest.qWait(DEBOUNCE_WAIT)
    assert len(calls) == 1, f"the debounce should coalesce the burst, got {len(calls)}"
    assert widget.manager.entries[0].text_overlays[0].x == 89


def test_no_edit_reselect_keeps_bytes_exact(widget):
    original = (MENU_DIR / "mmag2.bin").read_bytes()
    widget.page_list.setCurrentRow(3)
    QTest.qWait(20)
    widget.page_list.setCurrentRow(0)
    rebuilt = b"".join(bytes(entry.to_bytes()) for entry in widget.manager.entries)
    assert rebuilt == original


def test_bindings_split_mmag2_from_the_read_only_mngrp(qapp):
    """mmag2.bin is the edited main binding; mngrp.bin is a read-only companion."""
    from Moomba.moombawidget import MoombaWidget
    moomba = MoombaWidget()
    assert moomba.mmag2_binding.file_name == "mmag2.bin" and not moomba.mmag2_binding.read_only
    assert moomba.mngrp_binding.file_name == "mngrp.bin" and moomba.mngrp_binding.read_only
    bindings = moomba.file_bindings()
    assert [b.file_name for b in bindings if not b.read_only] == ["mmag2.bin"]
    assert [b.file_name for b in bindings if b.read_only] == ["mngrp.bin"]


def test_opening_mmag2_auto_loads_the_mngrp_beside_it(qapp):
    """Opening mmag2.bin picks up (and shares) the mngrp.bin sitting next to it."""
    from Moomba.moombawidget import MoombaWidget
    moomba = MoombaWidget()
    moomba.load_file(str(MENU_DIR / "mmag2.bin"))  # mngrp.bin sits next to it
    assert moomba.manager.mngrp_loaded, "mngrp next to mmag2.bin should auto-load"
    assert moomba.renderer is not None


def test_the_mngrp_binding_opens_mngrp(qapp):
    from Moomba.moombawidget import MoombaWidget
    moomba = MoombaWidget()
    # Load mmag2 from a folder with no mngrp beside it, so nothing auto-loads
    import shutil
    tmp = MENU_DIR.parent / "_moomba_tmp"
    tmp.mkdir(exist_ok=True)
    shutil.copy(MENU_DIR / "mmag2.bin", tmp / "mmag2.bin")
    try:
        moomba.load_file(str(tmp / "mmag2.bin"))
        assert not moomba.manager.mngrp_loaded  # none beside it
        moomba.mngrp_binding.open_path(str(MENU_DIR / "mngrp.bin"))
        assert moomba.manager.mngrp_loaded and moomba.renderer is not None
    finally:
        shutil.rmtree(tmp)


@pytest.mark.ff8data("extracted_files/menu/mmag.bin")
def test_mngrp_is_shared_across_tabs_through_the_registry(qapp):
    """Opening mmag.bin in Zone auto-loads its mngrp and shares it; a Moomba tab on the
    same registry renders from that same mngrp without opening it again."""
    from Common.fileregistry import FileRegistry
    from Moomba.moombawidget import MoombaWidget
    from Zone.zonewidget import ZoneWidget

    registry = FileRegistry()
    zone = ZoneWidget(file_registry=registry)
    moomba = MoombaWidget(file_registry=registry)

    zone.load_file(str(MENU_DIR / "mmag.bin"))  # auto-loads + publishes mngrp beside it
    assert zone.manager.mngrp_loaded
    # Moomba picked up the shared mngrp and can render, without its own mmag2 even open
    assert moomba.manager.mngrp_loaded and moomba.renderer is not None
    assert registry.get_path("mngrp.bin")

    # A tab created after the file is shared picks it up on construction
    latecomer = MoombaWidget(file_registry=registry)
    assert latecomer.manager.mngrp_loaded and latecomer.renderer is not None


@pytest.mark.ff8data("extracted_files/menu/mmag.bin", "extracted_files/menu/mwepon.bin",
                     "extracted_files/menu/icon.sp1", "extracted_files/menu/icon.TEX",
                     "extracted_files/menu/mitem.bin")
def test_zone_auto_loads_the_files_next_to_mmag(qapp):
    """The unlock-block files that sit next to mmag.bin load on open, no button needed."""
    from Zone.zonewidget import ZoneWidget
    zone = ZoneWidget()
    zone.load_file(str(MENU_DIR / "mmag.bin"))
    assert zone.manager.mngrp_loaded    # menu/mngrp.bin
    assert zone.manager.mwepon_loaded   # menu/mwepon.bin
    assert zone.manager.icons_loaded    # menu/icon.sp1
    assert zone.manager.mitem_loaded    # menu/mitem.bin
    # kernel.bin lives in main/, not next to mmag.bin, so it waits for the button
    assert not zone.manager.kernel_loaded


def test_preview_is_inert_before_mngrp(qapp):
    """Without mngrp.bin there is no renderer, so editing must not blow up."""
    from Moomba.moombawidget import MoombaWidget
    moomba = MoombaWidget()
    moomba.manager.load_file(str(MENU_DIR / "mmag2.bin"))
    moomba.page_list.addItem("0")
    moomba.page_list.setCurrentRow(0)
    assert moomba.renderer is None
    moomba.picture_overlay_x[0].setValue(50)
    QTest.qWait(DEBOUNCE_WAIT)
    assert moomba.preview_label.pixmap() is None or moomba.preview_label.pixmap().isNull()
