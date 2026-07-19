"""ShumiTranslator's FF8 exe pane: each of the 4 text sections (Draw text, Card misc text, Card
name, Scan text) gets a "+ Add entry" button that appends a new, empty text entry (data_read
starts blank, data_modified is ready to type).

Note on the exe's format: each section is backed by a FIXED-SIZE offset table read straight from
the .exe. Draw text and Card misc text have spare (currently-unused) offset slots; Card name and
Scan text are already fully packed. A naive append (what this button does) does not activate a
new offset slot, so on a fully-packed section the appended entry has no offset addressing it and
is not actually reachable in-game - it is written as inert trailing data. This is intentional
(user decision, 2026-07-19: add the button uniformly on every section, no special-casing or
warning - modders are expected to understand the format's constraints). This test only checks the
UI-level append and that saving never crashes, not that every section's new entry is addressable.
"""
import pathlib
import sys

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QFrame

project_root = pathlib.Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from FF8GameData.gamedata import GameData, FileType

EXE_REL = "extracted_files/FF8_EN.exe"
EXE = project_root / EXE_REL


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture(scope="module")
def game_data():
    gd = GameData(str(project_root / "FF8GameData"))
    for loader in ("kernel", "mngrp", "item", "magic", "card", "stat", "ai", "monster",
                  "status", "gforce", "attack_animation", "enemy_abilities"):
        getattr(gd, f"load_{loader}_data")()
    return gd


@pytest.mark.ff8data(EXE_REL)
def test_exe_sections_all_offer_an_add_entry_button(qapp, game_data):
    from ShumiTranslator.shumifilepane import ShumiFilePane
    pane = ShumiFilePane(game_data, FileType.EXE, str(EXE))
    from PyQt6.QtWidgets import QPushButton
    assert len(pane.section_widget_list) == 4  # draw_text, card_misc_text, card_name, scan_text
    for section_widget in pane.section_widget_list:
        buttons = [b for b in section_widget.findChildren(QPushButton) if b.text() == "+ Add entry"]
        assert len(buttons) == 1


@pytest.mark.ff8data(EXE_REL)
def test_add_entry_button_sits_at_the_end_left_aligned(qapp, game_data):
    """The button is the last row of entries (below every existing one), left-aligned - not in the
    section's header. New entries are inserted above it, so it stays the last row before the
    trailing separator no matter how many entries get added."""
    from ShumiTranslator.shumifilepane import ShumiFilePane
    pane = ShumiFilePane(game_data, FileType.EXE, str(EXE))
    section_widget = pane.section_widget_list[0]  # Draw text
    layout = section_widget.layout()
    button = section_widget._SectionWidget__add_button
    assert button is not None

    # Right before the trailing separator, and left-aligned (not stretched across the row).
    assert isinstance(layout.itemAt(layout.count() - 1).widget(), QFrame)
    button_item = layout.itemAt(layout.count() - 2)
    assert button_item.widget() is button
    assert button_item.alignment() & Qt.AlignmentFlag.AlignLeft

    before_widgets = len(section_widget.translation_widget_list)
    before_texts = len(section_widget.section.get_text_list())
    before_layout_count = layout.count()

    new_widget = section_widget.add_entry()

    assert len(section_widget.translation_widget_list) == before_widgets + 1
    assert len(section_widget.section.get_text_list()) == before_texts + 1
    assert section_widget.translation_widget_list[-1] is new_widget
    assert new_widget.translation.get_str() == ""            # data_read starts empty
    # The new row lands right above the button, which stays the last row before the separator.
    assert layout.count() == before_layout_count + 1
    assert isinstance(layout.itemAt(layout.count() - 1).widget(), QFrame)
    assert layout.itemAt(layout.count() - 2).widget() is button
    assert layout.itemAt(layout.count() - 3).widget() is new_widget

    # Adding a second entry: it lands above the first new one, button still stays last.
    second_widget = section_widget.add_entry()
    assert layout.itemAt(layout.count() - 2).widget() is button
    assert layout.itemAt(layout.count() - 3).widget() is second_widget
    assert layout.itemAt(layout.count() - 4).widget() is new_widget


@pytest.mark.ff8data(EXE_REL)
def test_add_entry_on_every_section_and_save_does_not_crash(qapp, game_data, tmp_path):
    """Card name and Scan text have zero spare offset slots (fully packed), so their appended
    entry is inert - but saving must still complete without raising."""
    from ShumiTranslator.shumifilepane import ShumiFilePane
    pane = ShumiFilePane(game_data, FileType.EXE, str(EXE))
    for section_widget in pane.section_widget_list:
        section_widget.add_entry()

    pane.manager.save_file(str(tmp_path))
    produced = sorted(p.name for p in tmp_path.iterdir())
    assert produced == ["battle_scans.msd", "card_names.msd", "card_texts.msd", "draw_point.msd"]
