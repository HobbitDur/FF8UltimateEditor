"""Ifrit takes kernel.bin as a complementary file: when one is open (in Ifrit or any tool sharing
it), the spell, item and enemy-attack names it holds are the ones Ifrit shows - the Draw / Mug /
Drop lists of the Stat tab first of all. Opening or removing it refreshes the shown file without
re-reading it from disk, so unsaved edits stay.

Needs the real (copyright, gitignored) files under extracted_files/.
"""
import os
import pathlib

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication, QMessageBox

PROJECT_ROOT = pathlib.Path(__file__).parent.parent
KERNEL = PROJECT_ROOT / "extracted_files" / "main" / "kernel.bin"
MODEL = PROJECT_ROOT / "extracted_files" / "battle" / "c0m071.dat"
pytestmark = pytest.mark.ff8data("extracted_files/main/kernel.bin", "extracted_files/battle/c0m071.dat")


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def renamed_kernel(tmp_path):
    """A copy of kernel.bin where spell 1 (Fire) is called Blaze."""
    from FF8GameData import kernelnames
    from FF8GameData.gamedata import GameData
    from ShumiTranslator.model.kernel.kernelmanager import KernelManager
    game_data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    game_data.load_kernel_data()
    manager = KernelManager(game_data)
    manager.load_file(str(KERNEL))
    sections = {section.id: section for section in manager.section_list if section}
    texts = sections[kernelnames._text_section_id(game_data, 2)].get_text_list()
    texts[1 * kernelnames._texts_per_entry(game_data, 2)].set_str("Blaze")
    path = tmp_path / "kernel.bin"
    manager.save_file(str(path))
    return str(path)


def _draw_combo_text(pane, spell_id):
    combo = pane._stat_widget._loot_widgets['low_lvl_mag'][0][0]
    return combo.itemText(combo.findData(spell_id))


def test_kernel_bin_names_the_draws_and_goes_away_with_it(app, renamed_kernel, monkeypatch):
    from PyQt6.QtCore import QSettings
    from Common.fileregistry import FileRegistry
    from Ifrit.ifritmonsterwidget import IfritMonsterWidget
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    registry = FileRegistry()
    ifrit = IfritMonsterWidget(QSettings("FF8UltimateEditorTest", "KernelNames"),
                               game_data_folder=str(PROJECT_ROOT / "FF8GameData"),
                               file_registry=registry)
    ifrit._cronos_checkbox.setChecked(False)
    assert ifrit.kernel_binding.read_only and ifrit.file_bindings() == [ifrit.kernel_binding]
    ifrit.load_file(str(MODEL))
    pane = ifrit._files[0]['pane']
    stats = pane._stat_widget
    stats.load_data()
    assert _draw_combo_text(pane, 1) == "1: Fire"

    # An unsaved edit made before the kernel.bin opens must survive the refresh.
    stats._data['low_lvl_mag'][0]['ID'] = 1
    registry.open_file("kernel.bin", renamed_kernel)   # e.g. opened in SolomonRing
    assert stats._data['low_lvl_mag'][0]['ID'] == 1
    stats.load_data()
    assert _draw_combo_text(pane, 1) == "1: Blaze"
    assert pane._stat_widget._loot_widgets['low_lvl_mag'][0][0].currentData() == 1

    registry.close_file("kernel.bin")                  # removed: back to the built-in names
    stats.load_data()
    assert _draw_combo_text(pane, 1) == "1: Fire"
    ifrit.deleteLater()
