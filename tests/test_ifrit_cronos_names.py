"""The Cronos checkbox of the Ifrit monster editor switches the AI tables - and only them.

Cronos's spell, item and enemy-attack names are not the checkbox's business: they come from its
kernel.bin, opened as a complementary file like any other (see test_ifrit_kernel_names.py). So
ticking it never renames anything, and FF8UltimateEditor ships no Cronos names file.
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


def test_the_checkbox_switches_the_ai_tables_and_nothing_else(editor):
    editor._apply_cronos_data(True)
    assert editor._game_data.ai_json_file_name == "ai_cronos.json"
    assert _name(editor, "magic_data_json", "magic", 43) == "Death"      # no rename
    assert _name(editor, "item_data_json", "items", 144) != "Stone Skin"
    editor._apply_cronos_data(False)
    assert editor._game_data.ai_json_file_name == "ai_vanilla.json"


def test_no_cronos_names_file_is_shipped():
    assert not (PROJECT_ROOT / "FF8GameData" / "Resources" / "json" / "names_cronos.json").exists()
