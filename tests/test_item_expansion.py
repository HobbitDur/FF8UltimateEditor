"""Item creation is coordinated across the kernel, field metadata and prices."""
import gc
from pathlib import Path
import struct

import pytest
from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication

from Common.fileregistry import FileRegistry
from Common.itemfiles import ItemFiles
from FF8GameData.gamedata import GameData, SectionType
from FF8GameData.itemdefinitions import ItemDefinitions, battle_item_id, battle_item_row
from FF8GameData.kernelnames import read_names
from Kadowaki.kadowakiwidget import KadowakiWidget
from ShumiTranslator.model.kernel.kernelmanager import KernelManager
from Siren.sirenwidget import SirenWidget
from SolomonRing.solomonringwidget import SolomonRingWidget
from TonberryShop.tonberryshop import TonberryShop

ROOT = Path(__file__).resolve().parents[1]
GAME_DATA = str(ROOT / "FF8GameData")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def files(tmp_path):
    """A complete synthetic vanilla-layout kernel; no copyrighted fixtures needed."""
    gd = GameData(GAME_DATA)
    gd.load_all()
    configs = gd.kernel_data_json["sections"]
    sections = {}
    for cfg in configs:
        if cfg["type"] != SectionType.DATA:
            continue
        count = cfg["number_sub_section"]
        size = cfg["sub_section_size"]
        per = cfg["sub_section_nb_text_offset"]
        data = bytearray(count * size)
        for row in range(count):
            for i in range(per):
                struct.pack_into("<H", data, row * size + i * 2, row * per + i)
        sections[cfg["id"]] = data
        text_id = cfg["section_id_text_linked"]
        if text_id:
            sections[text_id] = bytes(max(1, count * per))
    result = bytearray(4 + 4 * len(configs))
    struct.pack_into("<I", result, 0, len(configs))
    for cfg in configs:
        struct.pack_into("<I", result, cfg["id"] * 4, len(result))
        result.extend(sections.get(cfg["id"], b"\0"))
    kernel = tmp_path / "kernel.bin"
    kernel.write_bytes(result)
    mitem = tmp_path / "mitem.bin"
    price = tmp_path / "price.bin"
    mdata = bytearray(bytes([10, 0, 0, 0]) * 199)
    mdata[4:8] = bytes([0, 3, 4, 0])
    pdata = bytearray(4 * 199)
    pdata[4:8] = bytes([50, 0, 10, 0])
    mitem.write_bytes(mdata)
    price.write_bytes(pdata)
    km = KernelManager(gd)
    km.load_file(str(kernel))
    defs = ItemDefinitions(km)
    for item_id in range(199):
        text, row = defs.text_source(item_id)
        text.get_text_list()[row * 2].set_str(f"Original {item_id}")
    defs.section(8).get_subsection_list()[1].get_data_list()[-1].get_data_hex()[3] = 4
    km.save_file(str(kernel))
    return kernel, mitem, price


@pytest.fixture
def project(qapp, files):
    registry = FileRegistry()
    source = ItemFiles.for_registry(registry, GAME_DATA)
    for key, path in zip(("kernel.bin", "mitem.bin", "price.bin"), files):
        registry.open_file(key, str(path))
    return registry, source


@pytest.fixture
def editor(qapp, project):
    registry, source = project
    widget = SolomonRingWidget(game_data_folder=GAME_DATA, file_registry=registry)
    yield widget, source
    widget.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    QApplication.processEvents()
    gc.collect()


def test_stable_id_mapping():
    assert [battle_item_id(x) for x in (0, 32, 33, 88)] == [0, 32, 199, 254]
    assert [battle_item_row(x) for x in (1, 32, 33, 198, 199, 254, 255)] == [1, 32, None, None, 33, 88, None]


def test_add_roundtrip_preserves_original_ids_and_side_bytes(editor, files):
    widget, source = editor
    kernel, mitem, price = files
    original_mitem, original_price = mitem.read_bytes(), price.read_bytes()
    assert widget.add_item("Super Potion", "Restore more HP", 1, True) == 199
    assert source.mitem.menu_items[199].to_bytes() == bytes([0, 3, 4, 0])
    assert source.price.price_entries[199].to_bytes() == bytes([50, 0, 10, 0])
    assert widget._section_tabs[8].list_widget.item(33).text().startswith("199: Super Potion")
    assert widget._section_tabs[9].list_widget.item(166).text().startswith("199: Super Potion")
    assert widget.save_files()
    assert mitem.read_bytes()[:len(original_mitem)] == original_mitem
    assert price.read_bytes()[:len(original_price)] == original_price
    names = read_names(widget.game_data, kernel, keep_unnamed=True)["item"]
    assert names[33] == "Original 33" and names[198] == "Original 198"
    assert names[199] == "Super Potion"
    reloaded = KernelManager(widget.game_data)
    reloaded.load_file(str(kernel))
    assert len(reloaded.section_list[8].get_subsection_list()) == 34
    assert ItemDefinitions(reloaded).text(199, 1) == "Restore more HP"


def test_unsaved_side_edits_survive_new_tool_and_creation(qapp, project):
    registry, source = project
    field = KadowakiWidget(game_data_folder=GAME_DATA, file_registry=registry)
    price = SirenWidget(game_data_folder=GAME_DATA, file_registry=registry)
    field.item_list.setCurrentRow(1)
    field.param1_widget.set_value(9)
    field._on_data_changed()
    price.item_list.setCurrentRow(1)
    price.buy_spinbox.setValue(1230)
    widget = SolomonRingWidget(game_data_folder=GAME_DATA, file_registry=registry)
    assert widget.item_files.mitem is field.manager
    assert widget.item_files.price is price.manager
    widget.add_item("Copy", template_id=1)
    assert field.manager.menu_items[199].param1 == 9
    assert price.manager.price_entries[199].buy_price == 1230
    assert field.item_list.item(199).text() == "Copy"
    assert price.item_list.item(199).text() == "Copy"
    assert not field.mitem_binding.complementary
    assert not price.price_binding.complementary
    assert widget.file_bindings()[1].complementary
    for tool in (field, price, widget):
        tool.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    QApplication.processEvents()
    gc.collect()


def test_field_only_gap_is_disabled_when_later_item_gets_battle_settings(project, files):
    registry, source = project
    manager = KernelManager(source.game_data)
    manager.load_file(str(files[0]))
    items = ItemDefinitions(manager)
    assert source.create(items, "Field only", battle=False) == 199
    assert len(items.section(8).get_subsection_list()) == 33
    assert source.create(items, "Battle item", battle=True) == 200
    records = items.section(8).get_subsection_list()
    assert len(records) == 35
    assert records[33].get_data_list()[-1].get_data_hex()[6] == 0x20
    assert records[34].get_data_list()[-1].get_data_hex()[3] == 4
    assert items.text(199) == "Field only"


def test_final_id_and_capacity_leave_files_unchanged_on_rejection(project, files):
    registry, source = project
    manager = KernelManager(source.game_data)
    manager.load_file(str(files[0]))
    items = ItemDefinitions(manager)
    # Exercise the data operation without constructing 57 full forms.
    for item_id in range(199, 255):
        assert source.create(items, f"Added {item_id}", template_id=1, battle=True) == item_id
    assert source.create(items, "Final", template_id=1, battle=False) == 255
    before = (len(source.mitem.menu_items), len(source.price.price_entries), items.count)
    with pytest.raises(ValueError):
        source.create(items, "Overflow", template_id=1, battle=False)
    with pytest.raises(ValueError):
        items.ensure_battle(255)
    assert before == (len(source.mitem.menu_items), len(source.price.price_entries), items.count)
    assert len(items.section(8).get_subsection_list()) == 89
    assert len(items.section(9).get_subsection_list()) == 223


def test_name_edit_is_canonical_in_both_forms(editor):
    widget, source = editor
    widget.add_item("Before", battle=True)
    names = widget._section_tabs[9]
    battle = widget._section_tabs[8]
    names._text_widgets[0].setText("After")
    names.commit()
    battle.list_widget.setCurrentRow(33)
    assert battle._text_widgets[0].text() == "After"
    battle._text_widgets[0].setText("After battle edit")
    battle.commit()
    assert names._text_widgets[0].text() == "After battle edit"
    assert source.names[199] == "After battle edit"
    assert widget.items.text(33) == "Original 33"


def test_missing_file_and_invalid_template_do_not_partially_add(editor):
    widget, source = editor
    original = widget.items.count
    with pytest.raises(ValueError):
        source.create(widget.items, "Bad", template_id=999)
    assert widget.items.count == original
    source.price_binding.registry.close_file("price.bin")
    with pytest.raises(ValueError):
        widget.add_item("Needs price")
    assert widget.items.count == original
    assert not widget._item_actions[9][0].isEnabled()


def test_shop_duplicate_names_keep_the_selected_id(qapp, project, tmp_path):
    registry, source = project
    shop_file = tmp_path / "shop.bin"
    data = bytearray(bytes([0, 255]) * 320)
    data[0] = 199
    data[2] = 200
    shop_file.write_bytes(data)
    source.set_names({199: "Same name", 200: "Same name"})
    shop = TonberryShop(resource_folder=str(ROOT / "Resources"), file_registry=registry, game_data_folder=GAME_DATA)
    registry.open_file("shop.bin", str(shop_file))
    assert shop.item_combo[0].currentData() == 199
    assert shop.item_combo[1].currentData() == 200
    source.set_names({199: "Renamed", 200: "Renamed"})
    shop.save_file()
    assert shop_file.read_bytes() == data
    shop.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    QApplication.processEvents()
    gc.collect()

def test_add_item_button_drives_creation(editor, monkeypatch):
    from PyQt6.QtWidgets import QDialog
    from SolomonRing.itemdialog import ItemCreationDialog
    widget, source = editor
    widget._show_item_tab(9)

    def accept(dialog):
        dialog.template.setCurrentIndex(dialog.template.findData(1))
        dialog.name.setText("Created by button")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(ItemCreationDialog, "exec", accept)
    widget._item_actions[9][0].click()
    assert widget.items.text(199) == "Created by button"
    assert source.mitem.menu_items[199].param1 == 4


def test_world_item_rewards_follow_live_names(qapp, project):
    from Chocoboy.chocoboywidget import ChocoboyWidget
    registry, source = project
    world = ChocoboyWidget(game_data_folder=GAME_DATA, file_registry=registry)
    source.set_names({199: "World reward"})
    assert world._item_name(199) == "World reward"
    registry.close_file("kernel.bin")
    assert world._item_name(199) == "item 199"
    world.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    QApplication.processEvents()


def test_closing_kernel_disables_creation_and_project_save(editor):
    widget, source = editor
    source.kernel_binding.registry.close_file("kernel.bin")
    assert not widget._item_actions[9][0].isEnabled()
    assert widget.save_files() is False
    with pytest.raises(ValueError):
        widget.add_item("Stale action")
