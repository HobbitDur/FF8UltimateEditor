"""The shared header: file-management buttons under the selector, a collapsible opened-files
panel (no pop-up), and Import/Save that follow the active tool and Zone's active tab."""
import os
import sys

import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture(scope="module")
def main_window(qapp):
    # Building the whole app is heavy (loads every tool), so build it once for the module.
    from ff8ultimateeditorwidget import FF8UltimateEditorWidget
    return FF8UltimateEditorWidget("Resources", "FF8GameData")


def test_left_column_stacks_selector_buttons_and_opened_files(main_window):
    col = main_window._program_option_layout
    assert col.count() == 3  # selector row, file-buttons row, opened-files panel
    btn_row = col.itemAt(1).layout()
    names = [type(btn_row.itemAt(i).widget()).__name__
             for i in range(btn_row.count()) if btn_row.itemAt(i).widget()]
    # Import/Save toolbar and the .fs extract button share the file-management row
    assert "FileToolbarWidget" in names and "FsExtractWidget" in names
    assert type(col.itemAt(2).widget()).__name__ == "OpenedFilesPanel"


def test_opened_files_panel_is_collapsible_and_live(main_window):
    panel = main_window._opened_files_panel
    # isHidden() reflects the collapse toggle regardless of whether the window is shown.
    assert panel.file_list.isHidden() is True            # collapsed by default
    before = len(main_window.file_registry.paths)
    # A name no tool binds to, so nothing tries to load it; the panel still lists it.
    main_window.file_registry.open_file("zzdummy.bin", "some/dir/zzdummy.bin")
    assert f"Opened files ({before + 1})" in panel.header_button.text()  # live count
    panel.header_button.setChecked(True)                 # expand to see them
    assert panel.file_list.isHidden() is False and panel.file_list.count() == before + 1


def test_complementary_button_present_but_disabled_without_companions(main_window):
    tb = main_window._file_toolbar
    main_window.tool_stack.setCurrentWidget(main_window._siren_widget)
    assert tb.import_button.isEnabled()
    assert tb.import_complementary_button.isEnabled() is False  # Siren has no companions


def test_import_and_save_follow_zones_active_tab(main_window):
    tb = main_window._file_toolbar
    zone = main_window._zone_widget
    main_window.tool_stack.setCurrentWidget(zone)

    zone.tabs.setCurrentIndex(0)  # mmag.bin
    assert [b.file_name for b in tb._main_bindings()] == ["mmag.bin"]
    assert sorted(b.file_name for b in tb._complementary_bindings()) == [
        "icon.sp1", "kernel.bin", "mitem.bin", "mngrp.bin", "mwepon.bin"]
    assert tb.import_button.isEnabled() and tb.import_complementary_button.isEnabled()

    zone.tabs.setCurrentIndex(1)  # mmag2.bin -> toolbar follows via file_bindings_changed
    assert [b.file_name for b in tb._main_bindings()] == ["mmag2.bin"]
    assert sorted(b.file_name for b in tb._complementary_bindings()) == ["mngrp.bin"]


def test_ifrit_open_save_are_on_the_shared_toolbar(main_window):
    ifrit = main_window._ifrit_widget
    # Ifrit dropped its own open/save/reload buttons for a binding on the shared toolbar.
    assert not hasattr(ifrit, "_open_btn") and not hasattr(ifrit, "_save_btn")
    tb = main_window._file_toolbar
    main_window.tool_stack.setCurrentWidget(ifrit)
    assert [b.file_name for b in tb._main_bindings()] == ["battle model (.dat)"]
    assert tb.import_button.isEnabled()


def test_reload_button_reloads_every_opened_file(main_window):
    from Common.filebinding import FileBinding
    tb = main_window._file_toolbar
    # The Reload button sits right after Save and acts on the whole registry.
    widgets = [tb.layout().itemAt(i).widget() for i in range(tb.layout().count())]
    assert widgets.index(tb.reload_button) == widgets.index(tb.save_button) + 1

    # A throwaway binding on a name no real tool uses, so no real loader runs on a fake path.
    # (Kept in a local so it is not garbage-collected mid-test, which would drop its signals.)
    reloaded = []
    probe = FileBinding("zzreload.bin", main_window.file_registry, load_callback=reloaded.append)
    assert probe.file_name == "zzreload.bin"

    tb.reload_button.click()                     # nothing of ours open yet -> no reload
    assert reloaded == []

    main_window.file_registry.open_file("zzreload.bin", "some/dir/zzreload.bin")  # first load
    assert reloaded == ["some/dir/zzreload.bin"]
    reloaded.clear()
    assert tb.reload_button.isEnabled()          # something is open now
    tb.reload_button.click()                     # reload -> re-read the same path from disk
    assert reloaded == ["some/dir/zzreload.bin"]


def test_accepted_file_names_are_the_concrete_ones(main_window):
    accepted = main_window.file_registry.accepted_file_names()
    # every tool's exact file name is offered to the Open-folder scan...
    assert {"price.bin", "mngrp.bin", "mmag.bin", "kernel.bin", "mitem.bin"} <= accepted
    # ...but wildcard bindings (Ifrit's *.dat) are not, since a scan can't pick one file.
    assert "battle model (.dat)" not in accepted


def test_scan_folder_finds_recognized_files_recursively(tmp_path):
    from Common.filetoolbarwidget import FileToolbarWidget
    (tmp_path / "price.bin").write_bytes(b"x")
    sub = tmp_path / "menu"
    sub.mkdir()
    (sub / "MITEM.BIN").write_bytes(b"x")        # matched case-insensitively
    (sub / "notes.txt").write_bytes(b"x")        # not a name any tool reads -> ignored
    found = FileToolbarWidget.scan_folder(str(tmp_path), {"price.bin", "mitem.bin"})
    assert set(found) == {"price.bin", "mitem.bin"}
    assert found["mitem.bin"].endswith(os.path.join("menu", "MITEM.BIN"))


def test_open_folder_loads_the_files_it_finds(main_window):
    """The end of the Open-folder flow: opening each scanned file loads its tool."""
    from Common.filetoolbarwidget import FileToolbarWidget
    reg = main_window.file_registry
    # Limit to two light tools so the test stays cheap (Siren/price.bin, Kadowaki/mitem.bin).
    found = FileToolbarWidget.scan_folder("extracted_files", {"price.bin", "mitem.bin"})
    assert set(found) == {"price.bin", "mitem.bin"}
    for file_name, path in found.items():
        reg.open_file(file_name, path)
    assert main_window._siren_widget.price_binding.is_loaded
    assert main_window._kadowaki_widget.mitem_binding.is_loaded
    assert main_window._siren_widget.editor_container.isEnabled()


def test_open_folder_hands_the_field_folder_to_the_npc_tab(main_window, monkeypatch):
    """A folder-based tool (CCGroup's NPC card players tab) loads the whole field folder via the
    shared Open-folder button (which calls its load_folder), not a per-file binding."""
    from PyQt6.QtWidgets import QFileDialog
    cc = main_window._ccgroup_widget
    main_window.tool_stack.setCurrentWidget(cc)
    cc.tab_widget.setCurrentIndex(1)  # NPC card players tab
    assert not hasattr(cc.npc_card_game_widget, "_NpcCardGameWidget__folder_button")

    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        lambda *args, **kwargs: "extracted_files/field")
    main_window._file_toolbar._open_folder()   # no named files there -> no summary dialog pops
    assert cc.npc_card_game_widget.manager.nb_players() > 0
