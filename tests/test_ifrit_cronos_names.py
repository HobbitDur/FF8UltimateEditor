"""The Cronos checkbox of the Ifrit monster editor and the names it shows.

Cronos renames a few spells and items in its own kernel.bin (Death -> Reaper, Arctic Wind ->
Stone Skin...). Ticking the checkbox is what asks for those names - everywhere they are shown: the
xlsx it exports, the drops and draws, the AI parameters. Unticked, the editor shows the names the
game ships, whatever a mod calls them: nothing a mod renames leaks into a vanilla file.
"""
import os
import pathlib

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication

PROJECT_ROOT = pathlib.Path(__file__).parent.parent


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def editor(app):
    from PyQt6.QtCore import QSettings
    from Ifrit.ifritmonsterwidget import IfritMonsterWidget

    return IfritMonsterWidget(QSettings("FF8UltimateEditorTest", "CronosNames"),
                              game_data_folder=str(PROJECT_ROOT / "FF8GameData"))


def _name(editor, list_field, key, id_):
    return next(entry["name"] for entry in getattr(editor._game_data, list_field)[key] if entry["id"] == id_)


def test_unticked_the_editor_shows_the_names_the_game_ships(editor):
    editor._cronos_checkbox.setChecked(False)
    editor._apply_cronos_data(False)
    assert _name(editor, "magic_data_json", "magic", 43) == "Death"
    assert _name(editor, "item_data_json", "items", 144) == "Arctic Wind"
    assert _name(editor, "enemy_abilities_data_json", "abilities", 16) == "Arm Slash"


def test_ticked_it_shows_the_names_cronos_gives_them(editor):
    editor._apply_cronos_data(True)
    assert _name(editor, "magic_data_json", "magic", 43) == "Reaper"
    assert _name(editor, "item_data_json", "items", 144) == "Stone Skin"
    assert _name(editor, "enemy_abilities_data_json", "abilities", 16) == "Arm Machine Gun"
    assert editor._game_data.ai_json_file_name == "ai_cronos.json"

    # And unticking puts every one of them back - a checkbox, not a one way door
    editor._apply_cronos_data(False)
    assert _name(editor, "magic_data_json", "magic", 43) == "Death"
    assert editor._game_data.ai_json_file_name == "ai_vanilla.json"
