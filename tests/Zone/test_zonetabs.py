"""The magazine editor is one tabbed tool: mmag.bin + mmag2.bin, sharing a registry."""
import sys

import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def test_two_tabs_for_the_two_page_files(qapp):
    from Moomba.moombawidget import MoombaWidget
    from Zone.zonetabswidget import ZoneTabsWidget
    from Zone.zonewidget import ZoneWidget
    tabs = ZoneTabsWidget()
    assert tabs.tabs.count() == 2
    assert "mmag.bin" in tabs.tabs.tabText(0)
    assert "mmag2.bin" in tabs.tabs.tabText(1)
    assert isinstance(tabs.mmag_widget, ZoneWidget)
    assert isinstance(tabs.mmag2_widget, MoombaWidget)


def test_both_tabs_share_one_file_registry(qapp):
    """A mngrp.bin (or the mmag files) opened in one tab is seen by the other."""
    from Common.fileregistry import FileRegistry
    from Zone.zonetabswidget import ZoneTabsWidget
    registry = FileRegistry()
    tabs = ZoneTabsWidget(file_registry=registry)
    assert tabs.mmag_widget.mmag_binding.registry is registry
    assert tabs.mmag2_widget.mmag2_binding.registry is registry


def test_file_bindings_follow_the_active_tab(qapp):
    """The shared toolbar drives the active tab's files: mmag.bin on tab 1, mmag2.bin on tab 2."""
    from Zone.zonetabswidget import ZoneTabsWidget
    tabs = ZoneTabsWidget()

    tabs.tabs.setCurrentIndex(0)
    main = [b for b in tabs.file_bindings() if not b.read_only]
    assert [b.file_name for b in main] == ["mmag.bin"]
    # its five complementary files are offered read-only
    assert {b.file_name for b in tabs.file_bindings() if b.read_only} == {
        "mngrp.bin", "kernel.bin", "mwepon.bin", "icon.sp1", "mitem.bin"}

    tabs.tabs.setCurrentIndex(1)
    main = [b for b in tabs.file_bindings() if not b.read_only]
    assert [b.file_name for b in main] == ["mmag2.bin"]
    assert {b.file_name for b in tabs.file_bindings() if b.read_only} == {"mngrp.bin"}
