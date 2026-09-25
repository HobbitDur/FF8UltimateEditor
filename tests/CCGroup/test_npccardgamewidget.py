"""NPC card players tab: Deck ID picker, rare card panel and deck preview on the real bghall_1
field script (Balamb Garden hall, 4 card players)."""
import pathlib
import shutil
import sys

import pytest
from PyQt6.QtWidgets import QApplication

from CCGroup.jsmcardgame import PARAM_DECK_ID, PARAM_LEVEL_MASK

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
BGHALL_DIR = PROJECT_ROOT / "extracted_files" / "field" / "mapdata" / "bg" / "bghall_1"

pytestmark = pytest.mark.ff8data("extracted_files/field/mapdata/bg/bghall_1/bghall_1.jsm",
                                 "extracted_files/field/mapdata/bg/bghall_1/bghall_1.sym")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def npc_tab(qapp, tmp_path):
    from PyQt6.QtCore import QSettings
    from CCGroup.npccardgamewidget import NpcCardGameWidget
    shutil.copy(BGHALL_DIR / "bghall_1.jsm", tmp_path / "bghall_1.jsm")
    shutil.copy(BGHALL_DIR / "bghall_1.sym", tmp_path / "bghall_1.sym")
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    widget = NpcCardGameWidget(settings=settings)
    widget.load_folder(str(tmp_path))
    yield widget
    widget.close_folder()
    widget.deleteLater()


def players_by_name(widget):
    return {player.entity_name: player for player in widget.manager.jsm_files[0].players}


def current_editor(widget):
    from CCGroup.npccardgamewidget import CardPlayerWidget
    return widget.findChild(CardPlayerWidget)


def test_deck_id_picker_follows_the_value_and_updates_the_tree(npc_tab):
    seito6 = players_by_name(npc_tab)["seito6"]
    npc_tab.select_player(seito6)
    deck_row = current_editor(npc_tab).rows[0]
    assert deck_row.spinbox.value() == 31
    assert "no rare card" in deck_row.picker.currentText()

    deck_row.spinbox.setValue(213)
    assert seito6.params[PARAM_DECK_ID].value == 213
    assert deck_row.picker.currentText().startswith("213 - Leviathan")
    assert npc_tab.player_label(seito6).endswith("Leviathan")


def test_shared_deck_id_links_select_the_other_player(npc_tab):
    players = players_by_name(npc_tab)
    npc_tab.select_player(players["seito8"])  # seito8 and seito10 share Deck ID 131
    rare_group = current_editor(npc_tab).rare_cards_group
    assert [other.entity_name for _, other in rare_group.shared_players] == ["seito10"]
    rare_group._RareCardsGroup__link_activated("0")
    assert current_editor(npc_tab).player is players["seito10"]


def test_preview_of_a_script_rolled_level_mask(npc_tab):
    seito8 = players_by_name(npc_tab)["seito8"]
    assert seito8.params[PARAM_LEVEL_MASK].is_variable()
    npc_tab.select_player(seito8)
    preview = current_editor(npc_tab).deck_preview_group
    assert [option.always_bits for option in preview.level_options] == [7, 11, 13, 14, 15]
    # 'Any' + the 5 masks; every dealt card comes from Lv1-4
    assert preview.level_option_combobox.count() == 6
    for _ in range(20):
        preview.deal()
        assert len(preview.hand) == 5 and all(card_id < 44 for card_id in preview.hand)


def test_deck_id_picker_has_no_duplicate_entry(npc_tab):
    seito6 = players_by_name(npc_tab)["seito6"]
    npc_tab.select_player(seito6)
    deck_row = current_editor(npc_tab).rows[0]
    deck_row.spinbox.setValue(0)
    texts = [deck_row.picker.itemText(index) for index in range(deck_row.picker.count())]
    assert deck_row.picker.currentText() == "0 - No rare cards"
    assert sum(text.lower().startswith("0 - no rare") for text in texts) == 1
