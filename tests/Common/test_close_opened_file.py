"""Removing a file from the Opened files panel: every tool stops using it (no save, no reload,
no pick-up later), and the tools with a multi-file session drop that session."""
import pathlib
import sys

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from Common.openedfilespanel import OpenedFilesPanel

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def test_close_file_detaches_the_binding(qapp):
    registry = FileRegistry()
    loads, saves, closes = [], [], []
    binding = FileBinding("kernel.bin", registry, load_callback=loads.append,
                          save_callback=lambda: saves.append(1))
    binding.file_closed.connect(closes.append)
    registry.open_file("kernel.bin", "C:/a/kernel.bin")
    assert binding.is_loaded and loads == ["C:/a/kernel.bin"]

    registry.close_file("kernel.bin")
    assert "kernel.bin" not in registry.paths
    assert closes == ["C:/a/kernel.bin"]
    assert not binding.is_loaded and binding.current_path == ""
    binding.save()
    assert saves == []                      # a removed file is never written
    binding.reload_from_disk()
    assert loads == ["C:/a/kernel.bin"]     # ...nor reloaded

    # A tool created afterwards doesn't pick it up either.
    late = []
    FileBinding("kernel.bin", registry, load_callback=late.append).load_opened_file()
    assert late == []

    # Opening the same path again is a fresh load, and Save works again.
    registry.open_file("kernel.bin", "C:/a/kernel.bin")
    assert loads == ["C:/a/kernel.bin", "C:/a/kernel.bin"]
    binding.save()
    assert saves == [1]


def test_close_unknown_file_is_a_no_op(qapp):
    registry = FileRegistry()
    closed = []
    registry.file_closed.connect(lambda *args: closed.append(args))
    registry.close_file("nothing.bin")
    assert closed == []


def test_panel_close_button_asks_then_removes(qapp, monkeypatch):
    registry = FileRegistry()
    registry.open_file("kernel.bin", "C:/a/kernel.bin")
    registry.open_file("price.bin", "C:/a/price.bin")
    panel = OpenedFilesPanel(registry)
    assert panel.file_list.count() == 2
    assert panel.file_list.itemWidget(panel.file_list.item(0)) is not None  # the ✕ row overlay

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    panel.close_file("kernel.bin")
    assert "kernel.bin" in registry.paths   # declined: nothing removed

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    panel.close_file("kernel.bin")
    assert list(registry.paths) == ["price.bin"]
    assert panel.file_list.count() == 1 and "price.bin" in panel.file_list.item(0).text()
    assert "(1)" in panel.header_button.text()


@pytest.mark.ff8data("extracted_files/field")
def test_ccgroup_npc_scripts_close(qapp):
    from CCGroup.ccgroup import CCGroupWidget
    registry = FileRegistry()
    cc = CCGroupWidget(file_registry=registry)
    cc.tab_widget.setCurrentIndex(1)
    cc.load_folder(str(PROJECT_ROOT / "extracted_files" / "field"))
    assert cc.npc_card_game_widget.manager.nb_players() > 0
    registry.close_file(cc.NPC_REGISTRY_NAME)
    assert cc.npc_card_game_widget.manager.nb_players() == 0
    assert cc.npc_card_game_widget.folder_loaded == ""
    assert not cc.can_save_folder()


@pytest.mark.ff8data("extracted_files/battle/a0stg000.x")
def test_alexander_stages_close(qapp, monkeypatch):
    from Alexander.alexanderwidget import AlexanderWidget
    from PyQt6.QtWidgets import QFileDialog
    registry = FileRegistry()
    alexander = AlexanderWidget(file_registry=registry)
    monkeypatch.setattr(alexander.viewer_3d, "load_file", lambda: None)
    monkeypatch.setattr(alexander, "_frame_stage", lambda: None)
    paths = [str(PROJECT_ROOT / "extracted_files" / "battle" / "a0stg000.x")]
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: (paths, ""))
    alexander.open_files()
    alexander.stage_list.setCurrentRow(0)
    assert alexander.manager.is_loaded and alexander.can_save_folder()
    registry.close_file(alexander.REGISTRY_NAME)
    assert alexander.stage_list.count() == 0
    assert not alexander.manager.is_loaded and not alexander.can_save_folder()
    assert alexander.viewer_3d.isHidden()


@pytest.mark.ff8data("extracted_files/battle/c0m071.dat")
def test_ifrit_session_close(qapp, monkeypatch):
    from PyQt6.QtCore import QSettings
    from Ifrit.ifritmonsterwidget import IfritMonsterWidget
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    registry = FileRegistry()
    ifrit = IfritMonsterWidget(QSettings("FF8UltimateEditorTest", "CloseOpenedFile"),
                               game_data_folder=str(PROJECT_ROOT / "FF8GameData"),
                               file_registry=registry)
    ifrit.load_file(str(PROJECT_ROOT / "extracted_files" / "battle" / "c0m071.dat"))
    assert ifrit.REGISTRY_NAME in registry.paths and len(ifrit._files) == 1
    registry.close_file(ifrit.REGISTRY_NAME)
    assert ifrit._files == [] and ifrit._active_index == -1
    assert ifrit._file_list.count() == 0
    assert ifrit._stack.currentWidget() is ifrit._placeholder
    assert not ifrit.can_save_folder()
    ifrit.deleteLater()


@pytest.mark.ff8data("extracted_files/main/kernel.bin")
def test_shumi_tab_closes_with_its_file(qapp):
    from ShumiTranslator.shumitranslator import ShumiTranslator
    registry = FileRegistry()
    shumi = ShumiTranslator(game_data_folder=str(PROJECT_ROOT / "FF8GameData"),
                            file_registry=registry)
    registry.open_file("kernel.bin", str(PROJECT_ROOT / "extracted_files" / "main" / "kernel.bin"))
    assert shumi.tab_widget.count() == 1
    registry.close_file("kernel.bin")
    assert shumi.tab_widget.count() == 0
    assert not shumi.can_save_folder()


@pytest.mark.ff8data("extracted_files/menu/price.bin")
def test_fixed_file_tool_view_clears_and_comes_back(qapp):
    from Common.closedfileview import install_closed_file_view
    from Siren.sirenwidget import SirenWidget
    registry = FileRegistry()
    siren = SirenWidget(game_data_folder=str(PROJECT_ROOT / "FF8GameData"), file_registry=registry)
    view = install_closed_file_view(siren)
    assert not view.is_blank                 # a fresh tool keeps its own look
    price = str(PROJECT_ROOT / "extracted_files" / "menu" / "price.bin")
    registry.open_file("price.bin", price)
    assert not view.is_blank
    registry.close_file("price.bin")
    assert view.is_blank                     # the removed file's data is off screen
    registry.open_file("price.bin", price)
    assert not view.is_blank                 # opening a file brings the editor back


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/world/dat/wmsetus.obj")
def test_cid_drops_only_the_removed_file(qapp):
    from Cid.cidwidget import CidWidget
    registry = FileRegistry()
    cid = CidWidget(game_data_folder=str(PROJECT_ROOT / "FF8GameData"), file_registry=registry)
    registry.open_file("FF8 exe", str(PROJECT_ROOT / "extracted_files" / "FF8_EN.exe"))
    registry.open_file("wmsetxx.obj",
                       str(PROJECT_ROOT / "extracted_files" / "world" / "dat" / "wmsetus.obj"))
    world = cid._draw_list[cid.WORLD_EXE_START_INDEX]
    exe_bytes = [draw.get_exe_byte() for draw in cid._draw_list]
    position = (world.x, world.y)
    assert any(exe_bytes) and position != (0, 0)

    registry.close_file("FF8 exe")           # the exe part goes, the world positions stay
    assert not cid.exe_loaded and not any(d.get_exe_byte() for d in cid._draw_list)
    assert (world.x, world.y) == position and cid._section.is_loaded()

    registry.close_file("wmsetxx.obj")
    assert (world.x, world.y) == (0, 0) and not cid.can_save_folder()
