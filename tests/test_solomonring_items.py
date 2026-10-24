"""SolomonRing and the shared item names with FFNx's AddMoreItems extension (FF8GameData/itemids.py).

A modded kernel.bin carries items 199-255: up to 57 more Item Names rows (section 9) and up to 56
more battle records (section 8, record 33 = item 199). These pin that SolomonRing keeps them on
save (it used to read exactly the vanilla 33 / 166 rows and rebuild the sections from those, which
silently deleted every added item), labels them by item id, adds and removes them the way the
game's id-based data allows, and that the names reach the other tools at the right ids.
"""
import pathlib
import struct

import pytest
from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication, QMessageBox

from FF8GameData import itemids, kernelnames
from FF8GameData.gamedata import GameData
from ShumiTranslator.model.kernel.kernelmanager import KernelManager
from SolomonRing.solomonringwidget import SolomonRingWidget
from tests.addmoreitems_fixture import POTION_NAME, extended_kernel

PROJECT_ROOT = pathlib.Path(__file__).parent.parent
KERNEL = PROJECT_ROOT / "extracted_files" / "main" / "kernel.bin"
GAME_DATA_FOLDER = str(PROJECT_ROOT / "FF8GameData")


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _close_solomonring_windows():
    yield
    for widget in QApplication.topLevelWidgets():
        if isinstance(widget, SolomonRingWidget):
            widget.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    QApplication.processEvents()


@pytest.fixture(scope="module")
def game_data():
    gd = GameData(GAME_DATA_FOLDER)
    gd.load_all()
    return gd


def _item_sections(path):
    """(battle record count, item name row count, every item text offset is valid) as FFNx's
    loader checks them (0-based sections 7, 8 and their texts 38, 39)."""
    data = pathlib.Path(path).read_bytes()
    count = struct.unpack_from("<I", data)[0]
    offsets = list(struct.unpack_from(f"<{count}I", data, 4)) + [len(data)]
    section = lambda i: data[offsets[i]:offsets[i + 1]]
    battle, names = section(7), section(8)

    def valid(text, offset):
        return offset == 0xFFFF or (offset < len(text) and b"\0" in text[offset:])
    offsets_ok = all(valid(section(38), struct.unpack_from("<H", battle, i + j)[0])
                     for i in range(0, len(battle), 24) for j in (0, 2))
    offsets_ok &= all(valid(section(39), struct.unpack_from("<H", names, i + j)[0])
                      for i in range(0, len(names), 4) for j in (0, 2))
    return len(battle) // 24, len(names) // 4, offsets_ok


def _item_contents(path):
    """Every battle record's data and every item entry's (name, description) bytes."""
    data = pathlib.Path(path).read_bytes()
    count = struct.unpack_from("<I", data)[0]
    offsets = list(struct.unpack_from(f"<{count}I", data, 4)) + [len(data)]
    section = lambda i: data[offsets[i]:offsets[i + 1]]

    def string(text, offset):
        return None if offset == 0xFFFF else text[offset:text.index(b"\0", offset)]

    def entries(records, size, text):
        return [(records[i + 4:i + size], string(text, struct.unpack_from("<H", records, i)[0]),
                 string(text, struct.unpack_from("<H", records, i + 2)[0]))
                for i in range(0, len(records), size)]
    return entries(section(7), 24, section(38)), entries(section(8), 4, section(39))


def _widget(path):
    widget = SolomonRingWidget(icon_path="Resources", game_data_folder=GAME_DATA_FOLDER)
    widget.load_file(str(path))
    return widget


def test_item_id_mapping():
    assert itemids.battle_row_to_item_id(32) == 32
    assert itemids.battle_row_to_item_id(33) == 199
    assert itemids.battle_row_to_item_id(88) == 254
    assert itemids.item_id_to_battle_row(199) == 33
    assert itemids.item_id_to_battle_row(255) is None
    assert itemids.item_id_to_battle_row(100) is None
    assert itemids.non_battle_row_to_item_id(222) == 255
    assert itemids.item_problems(33, 166) == []
    assert itemids.item_problems(89, 223) == []
    assert any("no Item Names row" in p for p in itemids.item_problems(34, 166))
    assert any("at most 89" in p for p in itemids.item_problems(90, 223))


@pytest.mark.ff8data("extracted_files/main/kernel.bin")
def test_an_extended_kernel_survives_a_plain_save(game_data, tmp_path):
    work = tmp_path / "kernel.bin"
    work.write_bytes(extended_kernel(KERNEL.read_bytes()))
    assert _item_sections(work) == (89, 223, True)
    km = KernelManager(game_data)
    km.load_file(str(work))
    out = tmp_path / "saved.bin"
    km.save_file(str(out))
    assert _item_sections(out) == (89, 223, True)
    # The editor repacks the text (the vanilla file is not byte-exact either), so the item data
    # and the strings each entry points at are what must come back.
    assert _item_contents(out) == _item_contents(work)


@pytest.mark.ff8data("extracted_files/main/kernel.bin")
def test_solomonring_shows_and_keeps_the_added_items(qapp, tmp_path):
    work = tmp_path / "kernel.bin"
    work.write_bytes(extended_kernel(KERNEL.read_bytes()))
    widget = _widget(work)
    battle, names = widget._section_tabs[8], widget._section_tabs[9]
    assert len(battle._entries) == 89 and len(names._entries) == 223
    assert names.list_widget.item(0).text().startswith("33: ")
    assert names.list_widget.item(222).text() == f"255: {POTION_NAME}"
    assert battle.list_widget.item(32).text().startswith("32: ")
    # The added battle records show their item's name, from the Item Names row.
    assert battle.list_widget.item(33).text() == f"199: {POTION_NAME}"
    assert battle.list_widget.item(88).text() == f"254: {POTION_NAME}"
    assert widget.item_problems() == []
    item_lookup = {e["value"]: e["name"] for e in widget.registry.resolve("item")["entries"]}
    assert item_lookup[255] == POTION_NAME and item_lookup[1] == "Potion"

    names.list_widget.setCurrentRow(222)
    names._text_widgets[0].setText("Hero Drink")
    widget._save_kernel()
    assert _item_sections(work) == (89, 223, True)
    reloaded = _widget(work)
    assert reloaded._section_tabs[9].list_widget.item(222).text() == "255: Hero Drink"


def _yes(monkeypatch, answers):
    """QMessageBox.question answering from `answers` (Yes / No), and recording what it asked."""
    asked = []

    def question(*args, **kwargs):
        asked.append(args[2])
        return QMessageBox.StandardButton.Yes if answers.pop(0) else QMessageBox.StandardButton.No
    monkeypatch.setattr(QMessageBox, "question", question)
    return asked


@pytest.mark.ff8data("extracted_files/main/kernel.bin")
def test_a_new_item_is_on_both_tabs_and_greyed_until_usable_in_battle(qapp, tmp_path):
    """"+ Add entry" on either tab adds the next item to both: its name, and its Battle Items
    record greyed (a placeholder: no battle use, nothing to edit) until "Usable in battle" is on.
    Records are tied to ids by position, so any added item can be a battle item."""
    work = tmp_path / "kernel.bin"
    work.write_bytes(KERNEL.read_bytes())
    widget = _widget(work)
    battle, names = widget._section_tabs[8], widget._section_tabs[9]
    button = widget.battle_use_button
    battle.list_widget.setCurrentRow(1)
    assert not button.isEnabled()                        # the game's own battle items
    battle._add_btn.click()                              # item 199, from Battle Items
    names._add_btn.click()                               # item 200, from Item Names
    assert len(names._entries) == 168 and len(battle._entries) == 35
    assert battle.list_widget.item(33).text() == "199: Item 199 (field item)"
    assert battle.entry_disabled(33) and battle.entry_disabled(34)
    assert names.current_entry_index() == 167
    battle.list_widget.setCurrentRow(34)                 # item 200
    assert button.isEnabled() and not button.isChecked()
    assert not battle._form_host.isEnabled()

    button.click()                                       # usable in battle: the Potion's data
    assert widget.item_has_battle_use(200) and not widget.item_has_battle_use(199)
    assert bytes(battle._entries[34]._payload) == bytes(battle._entries[1]._payload)
    assert battle.list_widget.item(34).text() == "200: Item 200" and battle._form_host.isEnabled()
    names.list_widget.setCurrentRow(167)
    names._text_widgets[0].setText("Mega Tonic")
    widget._commit_item_tabs()
    assert battle.list_widget.item(34).text() == "200: Mega Tonic"
    assert widget.item_problems() == []
    widget._save_kernel()
    assert _item_sections(work) == (35, 168, True)

    reloaded = _widget(work)
    assert [reloaded.item_has_battle_use(i) for i in (199, 200)] == [False, True]
    assert reloaded._section_tabs[8].list_widget.count() == 35


@pytest.mark.ff8data("extracted_files/main/kernel.bin")
def test_switching_battle_use_off_asks_and_erases_the_data_on_save(qapp, tmp_path, monkeypatch):
    asked = _yes(monkeypatch, [False, True, True])
    work = tmp_path / "kernel.bin"
    work.write_bytes(extended_kernel(KERNEL.read_bytes(), added_names=1, added_battle=1))
    widget = _widget(work)
    battle, button = widget._section_tabs[8], widget.battle_use_button
    battle.list_widget.setCurrentRow(33)                 # item 199, a battle item
    assert button.isChecked()
    battle._field_widgets["attack_power"][2].setValue(77)   # typed in the form
    button.click()                                       # "No": still a battle item
    assert "lost when the file is saved" in asked[-1] and button.isChecked()
    assert widget.item_has_battle_use(199)
    button.click()                                       # "Yes": a field item
    assert not widget.item_has_battle_use(199) and not button.isChecked()
    button.click()                                       # back on before saving: its data is back
    assert widget.item_has_battle_use(199) and battle._entries[33].get("attack_power") == 77
    battle.list_widget.setCurrentRow(33)
    button.click()                                       # "Yes" again, then save
    widget._save_kernel()
    assert _item_contents(work)[0][33][0] == bytes(20)
    reloaded = _widget(work)
    reloaded._section_tabs[8].list_widget.setCurrentRow(33)
    reloaded.battle_use_button.click()                   # the old data is gone: the Potion's
    assert bytes(reloaded._section_tabs[8]._entries[33]._payload) == \
        bytes(reloaded._section_tabs[8]._entries[1]._payload)


@pytest.mark.ff8data("extracted_files/main/kernel.bin")
def test_only_the_last_item_can_be_removed(qapp, tmp_path, monkeypatch):
    """An id is a position: only the last item goes, from either tab, name and record together
    (asking first when it is a battle item)."""
    asked = _yes(monkeypatch, [True])
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: shown.append(args[2]))
    work = tmp_path / "kernel.bin"
    work.write_bytes(extended_kernel(KERNEL.read_bytes(), added_names=3, added_battle=2))
    widget = _widget(work)
    battle, names = widget._section_tabs[8], widget._section_tabs[9]
    assert len(battle._entries) == 36                    # 201 gets its (greyed) record on load
    for tab, row in ((battle, 32), (names, 165), (battle, 33), (names, 166)):
        tab.list_widget.setCurrentRow(row)
        assert not tab._remove_btn.isEnabled()
    battle.list_widget.setCurrentRow(35)                 # item 201, a field item: no question
    battle._remove_btn.click()
    assert len(names._entries) == 168 and len(battle._entries) == 35 and not asked
    names.list_widget.setCurrentRow(167)                 # item 200, a battle item: asked
    names._remove_btn.click()
    assert "usable in battle" in asked[-1]
    assert len(names._entries) == 167 and len(battle._entries) == 34


@pytest.mark.ff8data("extracted_files/main/kernel.bin")
def test_item_255_has_no_battle_record(qapp, tmp_path, monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: shown.append(args[2]))
    work = tmp_path / "kernel.bin"
    work.write_bytes(extended_kernel(KERNEL.read_bytes(), added_names=57, added_battle=0))
    widget = _widget(work)
    battle = widget._section_tabs[8]
    assert len(battle._entries) == 89 and not battle._add_btn.isEnabled()
    battle.list_widget.setCurrentRow(88)                 # item 254, while 255 is the last item
    battle._remove_btn.click()
    assert "Only the last item, 255" in shown[-1] and len(battle._entries) == 89


@pytest.mark.ff8data("extracted_files/main/kernel.bin")
def test_the_shared_item_names_follow_the_extension(game_data, tmp_path):
    """The battle records 33+ are items 199+, named by the Item Names rows: read as ids 33+, the
    Potion copies would rename the first non-battle items."""
    work = tmp_path / "kernel.bin"
    work.write_bytes(extended_kernel(KERNEL.read_bytes()))
    names = kernelnames.read_names(game_data, work)["item"]
    vanilla = kernelnames.read_names(game_data, KERNEL)["item"]
    assert {id_: names[id_] for id_ in vanilla} == vanilla
    assert all(names[id_] == POTION_NAME for id_ in range(199, 256))
    changes = kernelnames.name_changes(game_data, work, vanilla_kernel_file=KERNEL)
    assert set(changes["item"]) == set(range(199, 256))
