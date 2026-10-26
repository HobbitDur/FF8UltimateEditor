"""ShumiTranslator's Ctrl+F: only the lines the searched text appears in stay shown."""
import pathlib
import struct
import sys

import pytest
from PyQt6.QtWidgets import QApplication

from FF8GameData.gamedata import FileType, GameData
from FF8GameData.menu.mngrp.string.sectionstring import SectionString
from ShumiTranslator.view.sectionwidget import SectionWidget
from ShumiTranslator.view.textsearchbar import TextSearchBar

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MENU = PROJECT_ROOT / "extracted_files" / "menu"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture(scope="module")
def game_data():
    game_data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    game_data.load_all()
    return game_data


def _section_widget(game_data, texts, first_line):
    offset = 2 + 2 * len(texts)
    offsets, data = [], bytearray()
    for text in texts:
        encoded = bytearray(game_data.translate_str_to_hex(text)) + b"\x00"
        offsets.append(offset)
        data += encoded
        offset += len(encoded)
    section = SectionString(game_data=game_data,
                            data_hex=bytearray(struct.pack(f"<H{len(texts)}H", len(texts), *offsets)) + data)
    return SectionWidget(section.get_text_section(), first_line)


@pytest.fixture
def bar(qapp, game_data):
    sections = [_section_widget(game_data, ["Potion", "Hi-Potion", "Phoenix Down"], 2),
                _section_widget(game_data, ["Elixir", "Remedy"], 5)]
    return TextSearchBar(sections)


def _shown(bar):
    return [[line.translation.get_str() for line in section.translation_widget_list if not line.isHidden()]
            for section in bar._section_widgets]


def _search(bar, text):
    bar.search_field.setText(text)
    bar.search()  # what the typing pause triggers


def test_only_the_matching_lines_stay_shown(bar):
    _search(bar, "POTION")
    assert _shown(bar) == [["Potion", "Hi-Potion"], []]
    assert bar.result_label.text() == "2/5"


def test_a_section_without_any_match_is_hidden(bar):
    _search(bar, "potion")
    assert not bar._section_widgets[0].isHidden()
    assert bar._section_widgets[1].isHidden()


def test_the_modified_text_is_searched_too(bar):
    bar._section_widgets[1].translation_widget_list[1].translation.set_str("Mega Potion")
    _search(bar, "mega")
    assert _shown(bar) == [[], ["Mega Potion"]]
    _search(bar, "remedy")  # the text as read still finds it
    assert _shown(bar) == [[], ["Mega Potion"]]


def test_a_number_also_finds_its_line(bar):
    _search(bar, "6")  # the CSV line numbers: 2, 3, 4 then 5, 6
    assert _shown(bar) == [[], ["Remedy"]]


def test_escape_shows_everything_again(bar):
    _search(bar, "potion")
    bar.clear_search()
    assert _shown(bar) == [["Potion", "Hi-Potion", "Phoenix Down"], ["Elixir", "Remedy"]]
    assert not any(section.isHidden() for section in bar._section_widgets)
    assert bar.result_label.text() == ""


def test_typing_waits_for_a_pause(bar):
    bar.search_field.setText("elixir")
    assert _shown(bar)[1] == ["Elixir", "Remedy"]  # not filtered yet
    assert bar._timer.isActive()


@pytest.mark.ff8data("extracted_files/menu/mngrp.bin", "extracted_files/menu/mngrphd.bin")
def test_mngrp_tabs_count_their_matches(qapp, game_data):
    from ShumiTranslator.shumifilepane import ShumiFilePane
    pane = ShumiFilePane(game_data, FileType.MNGRP, str(MENU / "mngrp.bin"), str(MENU / "mngrphd.bin"))
    tabs = pane.search_bar._tab_holder
    titles = [tabs.tabText(index) for index in range(tabs.count())]
    tabs.setCurrentIndex(titles.index("GF Refining"))

    _search(pane.search_bar, "Written Test")
    counts = [tabs.tabText(index) for index in range(tabs.count())]
    assert all(text.startswith(title + " (") for text, title in zip(counts, titles))
    assert "(0)" in tabs.tabText(titles.index("GF Refining"))
    assert not tabs.tabText(tabs.currentIndex()).endswith("(0)")  # moved to a tab with matches
    shown, total = map(int, pane.search_bar.result_label.text().split("/"))
    assert 0 < shown < total > 2500

    pane.search_bar.clear_search()
    assert [tabs.tabText(index) for index in range(tabs.count())] == titles
