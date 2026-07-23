"""EntityType.MONSTER_NO_MODEL: c0m127.dat (com_id 127 = "Ultimecia (No Model, has
Apocalypse)"), the only known file of this kind. It has 3 header sections (header + 2 real
sections: info_stat, then AI/battle_script) instead of a normal monster's 12 (header + 11) -
no skeleton/geometry/animation/dynamic-texture/camera/seq_anim/sound/texture sections at all.

Before this was recognized, the header's nb_section=3 didn't match any known entity type, so
the file was force-classified as MONSTER and then raised GarbageFileError trying to parse a
model that isn't there. See EntityType.MONSTER_NO_MODEL for how the two real sections were
identified: info_stat (380 bytes, same size as every other monster's section 7, decodes to
monster_name "Ultimecia") and AI/battle_script (decompiles to coherent code - untargetable()
on init, untargetable();vanish() on death).
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication([])

from Ifrit.ifritmanager import IfritManager
from FF8GameData.monsterdata import EntityType

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NO_MODEL_FILE = os.path.join(REPO, "extracted_files", "battle", "c0m127.dat")

pytestmark = pytest.mark.skipif(not os.path.isfile(NO_MODEL_FILE),
                                 reason="c0m127.dat not available")


@pytest.fixture(scope="module")
def manager():
    mgr = IfritManager(os.path.join(REPO, "FF8GameData"))
    mgr.init_from_file(NO_MODEL_FILE)
    return mgr


def test_classifies_as_monster_no_model(manager):
    assert manager.enemy.entity_type == EntityType.MONSTER_NO_MODEL
    assert manager.enemy.header_data['nb_section'] == 3


def test_info_stat_section_decodes_correctly(manager):
    assert manager.enemy.info_stat_data['monster_name'].get_str().strip('\x00') == 'Ultimecia'
    # Hidden HP is exactly what you'd expect for an invisible, untargetable trigger entity -
    # a sanity check that this is really info_stat data, not a coincidental name match.
    assert manager.enemy.info_stat_data['byte_flag_1']['Hidden HP'] == 1


def test_ai_section_decodes_to_coherent_code(manager):
    ai_data = manager.enemy.battle_script_data['ai_data']
    assert len(ai_data) >= 4
    init_code = ai_data[0]['code']
    death_code = ai_data[3]['code']
    assert 'untargetable' in init_code
    assert 'untargetable' in death_code
    assert 'vanish' in death_code


def test_no_op_save_is_byte_identical(manager, tmp_path):
    out = str(tmp_path / "c0m127.dat")
    manager.save_file(out)
    with open(NO_MODEL_FILE, "rb") as f:
        original = f.read()
    with open(out, "rb") as f:
        saved = f.read()
    assert len(saved) == len(original)
    assert saved == original


def test_editing_a_stat_persists_through_save_reload(tmp_path):
    mgr = IfritManager(os.path.join(REPO, "FF8GameData"))
    mgr.init_from_file(NO_MODEL_FILE)
    original_hp = list(mgr.enemy.info_stat_data['hp'])
    new_hp = [b ^ 0xFF for b in original_hp]  # flip every bit, guaranteed different
    mgr.enemy.info_stat_data['hp'] = new_hp

    out = str(tmp_path / "c0m127_edited.dat")
    mgr.save_file(out)

    reloaded = IfritManager(os.path.join(REPO, "FF8GameData"))
    reloaded.init_from_file(out)
    assert list(reloaded.enemy.info_stat_data['hp']) == new_hp
    assert reloaded.enemy.info_stat_data['monster_name'].get_str().strip('\x00') == 'Ultimecia'


def test_gui_loads_without_crashing_and_shows_only_stat_and_ai():
    """The concrete bug this used to hit: opening the file built the 3D tab unconditionally,
    whose Ifrit3DWidget.load_file() raised ValueError on this file's zero-vertex geometry
    (numpy .min() on an empty array) - the file couldn't be opened in the real app at all.
    Confirms it opens and shows only the Stat and AI tabs. The editor now lives in a per-file
    IfritFilePane (IfritMonsterWidget is the multi-file shell)."""
    from PyQt6.QtCore import QSettings
    from Ifrit.ifritmonsterwidget import IfritMonsterWidget

    widget = IfritMonsterWidget(settings=QSettings("test", "monster_no_model"),
                                 icon_path="Resources", game_data_folder="FF8GameData")
    widget.load_file(NO_MODEL_FILE)  # builds this file's pane; must not raise

    pane = widget._files[0]['pane']
    tabs = pane._tabs
    # Visibility is applied by the pane itself (IfritFilePane._apply_visibility) from the parsed
    # entity type - MONSTER_NO_MODEL has only info_stat + AI.
    assert tabs.isTabVisible(tabs.indexOf(pane._stat_container))
    assert tabs.isTabVisible(tabs.indexOf(pane._ai_container))
    assert not tabs.isTabVisible(tabs.indexOf(pane._3d_widget))
    assert not tabs.isTabVisible(tabs.indexOf(pane._seq_widget))
    assert not tabs.isTabVisible(tabs.indexOf(pane._camera_widget))
    assert not tabs.isTabVisible(tabs.indexOf(pane._dynamic_texture_widget))
    assert not tabs.isTabVisible(tabs.indexOf(pane._texture_widget))

    pane._ensure_tab_loaded(pane._stat_container)   # load the Stat tab's data on demand
    assert pane._stat_widget.name_widget._name_edit.text() == 'Ultimecia'
