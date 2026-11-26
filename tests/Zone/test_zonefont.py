"""The page previews' font is two side files (sysfnt.TEX, sysfnt.tdw), opened like the others:
never taken from mngrp.bin's folder, removable, and the preview says which one is missing."""
import pathlib
import shutil
import sys

import pytest
from PyQt6.QtWidgets import QApplication

from Common.fileregistry import FileRegistry

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MENU_DIR = PROJECT_ROOT / "extracted_files" / "menu"

pytestmark = pytest.mark.ff8data("extracted_files/menu/mmag.bin",
                                 "extracted_files/menu/mmag2.bin",
                                 "extracted_files/menu/mngrp.bin",
                                 "extracted_files/menu/mngrphd.bin",
                                 "extracted_files/menu/sysfnt.TEX",
                                 "extracted_files/menu/sysfnt.tdw")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def test_mngrp_folder_font_is_not_picked_up(qapp):
    """mngrp.bin opened alone: its folder has sysfnt.*, but they are not opened, so no font."""
    from Zone.zonewidget import ZoneWidget
    zone = ZoneWidget(file_registry=FileRegistry())
    zone.companion_bindings["mngrp.bin"].open_path(str(MENU_DIR / "mngrp.bin"))
    assert zone.renderer is not None and zone.renderer.atlas is None
    assert "sysfnt.TEX and sysfnt.tdw" in zone.font_notice.text()


def test_opening_and_removing_the_font_side_files(qapp):
    from Zone.zonewidget import ZoneWidget
    registry = FileRegistry()
    zone = ZoneWidget(file_registry=registry)
    zone.companion_bindings["mngrp.bin"].open_path(str(MENU_DIR / "mngrp.bin"))
    registry.open_file("sysfnt.TEX", str(MENU_DIR / "sysfnt.TEX"))
    assert zone.renderer.atlas is not None
    assert "sysfnt.tdw" in zone.font_notice.text()  # glyphs, but no widths yet
    registry.open_file("sysfnt.tdw", str(MENU_DIR / "sysfnt.tdw"))
    assert zone.renderer.metrics.exact
    assert zone.font_notice.text() == "" and zone.font_notice.isHidden()
    registry.close_file("sysfnt.TEX")
    assert zone.renderer.atlas is None
    assert "sysfnt.TEX" in zone.font_notice.text()


def test_font_opened_before_mngrp_is_used(qapp):
    """Opened first (or in the other tab), the font goes into the renderer built later."""
    from Zone.zonewidget import ZoneWidget
    registry = FileRegistry()
    registry.open_file("sysfnt.TEX", str(MENU_DIR / "sysfnt.TEX"))
    registry.open_file("sysfnt.tdw", str(MENU_DIR / "sysfnt.tdw"))
    zone = ZoneWidget(file_registry=registry)
    zone.companion_bindings["mngrp.bin"].open_path(str(MENU_DIR / "mngrp.bin"))
    assert zone.renderer.atlas is not None and zone.renderer.metrics.exact


def test_mmag_opens_the_font_beside_it(qapp, tmp_path):
    """Like every side file, the font beside the opened mmag.bin is opened with it (Zone and
    Moomba share it through the registry)."""
    from Zone.zonetabswidget import ZoneTabsWidget
    for name in ("mmag.bin", "mngrp.bin", "mngrphd.bin", "sysfnt.TEX", "sysfnt.tdw"):
        shutil.copy(MENU_DIR / name, tmp_path / name)
    registry = FileRegistry()
    tabs = ZoneTabsWidget(file_registry=registry)
    tabs.mmag_widget.mmag_binding.open_path(str(tmp_path / "mmag.bin"))
    assert registry.get_path("sysfnt.TEX") == str(tmp_path / "sysfnt.TEX")
    assert tabs.mmag_widget.renderer.atlas is not None
    assert tabs.mmag2_widget.font_source.atlas is not None  # the other tab has it too
