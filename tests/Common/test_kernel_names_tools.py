"""Weapon and ability names come only from a kernel.bin, opened as a complementary file.

Junkshop, Zone, Kadowaki, Quezacotl and Hyne have no built-in list of them any more: without a
kernel.bin each shows the ids alone, greyed out, with a notice saying to open one; opening one
(in any tool - it is shared) names them, and removing it takes the names away again. The data
itself is never changed by any of it.

Needs the real (copyright, gitignored) files under extracted_files/.
"""
import pathlib
import sys

import pytest
from PyQt6.QtWidgets import QApplication

from Common.fileregistry import FileRegistry

ROOT = pathlib.Path(__file__).parent.parent.parent
DATA = ROOT / "extracted_files"
KERNEL = str(DATA / "main" / "kernel.bin")
GAME_DATA = str(ROOT / "FF8GameData")
pytestmark = pytest.mark.ff8data("extracted_files/main/kernel.bin")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.mark.ff8data("extracted_files/menu/mwepon.bin")
def test_junkshop_weapon_list(qapp):
    from Junkshop.junkshopwidget import JunkshopWidget
    registry = FileRegistry()
    tool = JunkshopWidget(game_data_folder=GAME_DATA, file_registry=registry)
    assert tool.kernel_names.binding in tool.file_bindings()
    registry.open_file("mwepon.bin", str(DATA / "menu" / "mwepon.bin"))
    assert tool.weapon_list.item(0).text() == "Weapon 0"
    assert not tool.weapon_notice.isHidden()

    registry.open_file("kernel.bin", KERNEL)
    assert tool.weapon_list.item(0).text() == "Revolver"
    assert tool.weapon_notice.isHidden()

    registry.close_file("kernel.bin")
    assert tool.weapon_list.item(0).text() == "Weapon 0"


@pytest.mark.ff8data("extracted_files/menu/mmag.bin")
def test_zone_weapon_combo(qapp):
    from Zone.zonewidget import ZoneWidget
    registry = FileRegistry()
    tool = ZoneWidget(game_data_folder=GAME_DATA, file_registry=registry)
    registry.open_file("mmag.bin", str(DATA / "menu" / "mmag.bin"))
    tool.entry_list.setCurrentRow(0)                 # Weapons Monthly: weapon 6 (Lion Heart)
    combo = tool.weapon_combo
    assert combo.currentData() == 6 and not combo.isEnabled()
    assert "Lion Heart" not in combo.currentText() and not tool.weapon_notice.isHidden()

    registry.open_file("kernel.bin", KERNEL)
    assert combo.isEnabled() and combo.currentData() == 6 and combo.currentText() == "6: Lion Heart"
    assert tool.weapon_notice.isHidden()

    registry.close_file("kernel.bin")
    assert combo.currentData() == 6 and not combo.isEnabled()


@pytest.mark.ff8data("extracted_files/menu/mitem.bin")
def test_kadowaki_gf_ability_param(qapp):
    from Kadowaki.kadowakiwidget import KadowakiWidget
    registry = FileRegistry()
    tool = KadowakiWidget(game_data_folder=GAME_DATA, file_registry=registry)
    registry.open_file("mitem.bin", str(DATA / "menu" / "mitem.bin"))
    tool.item_list.setCurrentRow(tool.manager.menu_items.index(
        next(m for m in tool.manager.menu_items if m.name == "HP-J Scroll")))
    param = next(w for w in (tool.param1_widget, tool.param2_widget) if w._kernel_only_empty)
    assert param._kernel_only_empty and not param._list_combo.isEnabled()
    value = param.get_value()
    assert value == 1                                # HP-J

    registry.open_file("kernel.bin", KERNEL)
    assert param._list_combo.isEnabled() and param.get_value() == 1
    assert param._list_combo.currentText() == "HP-J"

    registry.close_file("kernel.bin")
    assert not param._list_combo.isEnabled() and param.get_value() == 1


def _own_enabled(widget):
    """Enabled by its own setting - Hyne keeps its whole tab area disabled until a save is open,
    which says nothing about the names."""
    from PyQt6.QtCore import Qt
    return not widget.testAttribute(Qt.WidgetAttribute.WA_ForceDisabled)


@pytest.mark.parametrize("tool_name", ["Quezacotl", "Hyne"])
@pytest.mark.ff8data("extracted_files/main/init.out")
def test_quezacotl_and_hyne_abilities_and_weapons(qapp, tool_name):
    if tool_name == "Quezacotl":
        from Quezacotl.quezacotlwidget import QuezacotlWidget as Tool
    else:
        from Hyne.hynewidget import HyneWidget as Tool
    registry = FileRegistry()
    tool = Tool(game_data_folder=GAME_DATA, file_registry=registry)
    assert tool.kernel_names.binding in tool.file_bindings()
    if tool_name == "Quezacotl":
        registry.open_file("init.out", str(DATA / "main" / "init.out"))
    check_hp_j = tool.gf_ability_checks[1]
    weapon_check = tool.misc_weapon_checks[0][1]
    assert check_hp_j.text() == "Ability 1" and not _own_enabled(check_hp_j)
    assert weapon_check.text() == "Weapon 0" and not _own_enabled(weapon_check)
    assert not tool.kernel_notice.isHidden()
    learning = tool.gf_learning_ability_combo.currentData()

    registry.open_file("kernel.bin", KERNEL)
    assert check_hp_j.text() == "HP-J" and _own_enabled(check_hp_j)
    assert weapon_check.text().startswith("Revolver") and _own_enabled(weapon_check)
    assert _own_enabled(tool.gf_learning_ability_combo)
    assert tool.gf_learning_ability_combo.currentData() == learning   # the value never moves
    assert tool.kernel_notice.isHidden()

    registry.close_file("kernel.bin")
    assert check_hp_j.text() == "Ability 1" and not _own_enabled(check_hp_j)
    assert tool.gf_learning_ability_combo.currentData() == learning
