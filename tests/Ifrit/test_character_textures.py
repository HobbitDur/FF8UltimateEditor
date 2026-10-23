"""Character / weapon files in Ifrit: their texture section (character 6, weapon 7, Edea 9, reduced
weapon 5) and a character's eye-blink dynamic texture (section 4) parsed, shown in their own tabs,
edited and saved like a monster's; every tab labelled with its real section and in section order."""
import os
import sys

import pytest

BATTLE = "extracted_files/battle"


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


def _path(name):
    path = os.path.join(BATTLE, f"{name}.dat")
    if not os.path.isfile(path):
        pytest.skip("needs the game's battle files in extracted_files/battle")
    return os.path.abspath(path)


def _manager(name):
    from Ifrit.ifritmanager import IfritManager
    manager = IfritManager("FF8GameData")
    manager.init_from_file(_path(name))
    return manager


def _pane(manager, name):
    from PyQt6.QtCore import QSettings
    from Ifrit.ifritmonsterwidget import IfritFilePane
    return IfritFilePane(manager, _path(name), QSettings("FF8UltimateEditorTest", "character_textures"))


@pytest.mark.parametrize("name, texture, nb_texture, eye", [("d0c000", 6, 2, 4), ("d0w000", 7, 1, None),
                                                           ("d1w008", 5, 1, None), ("d7c016", 9, 2, 4)])
def test_texture_and_eye_blink_are_parsed_and_saved_byte_exact(qapp, name, texture, nb_texture, eye):
    manager = _manager(name)
    enemy = manager.enemy
    original = [bytes(section) for section in enemy.section_raw_data]
    assert len(enemy.texture_data['texture_data']) == nb_texture
    assert len(enemy.dynamic_texture_data.dynamic_texture_data) == (1 if eye else 0)
    enemy.get_bytes(manager.game_data)
    assert bytes(enemy.section_raw_data[texture]) == original[texture]
    if eye:
        assert bytes(enemy.section_raw_data[eye]) == original[eye]
    # read natively (no VincentTim): each TIM on its 128 x 128 canvas at its place in the page
    assert len(manager.texture_data) == nb_texture
    for data in manager.texture_data:
        assert data.source_tim is not None
        assert (data.texture_image.width(), data.texture_image.height()) == (128, 128)


def test_texture_edit_is_cropped_back_to_its_tim(qapp):
    """The weapon's TIM is 128 x 32 drawn at y 96 of its canvas: an edited texel lands in it."""
    from PyQt6.QtGui import QColor, QPixmap
    from FF8GameData.tim.timfile import PalettedTim
    manager = _manager("d0w000")
    pane = _pane(manager, "d0w000")
    before = bytes(manager.enemy.get_bytes(manager.game_data))
    pane._texture_widget.save_file()                                    # unedited: same bytes
    assert bytes(manager.enemy.get_bytes(manager.game_data)) == before
    source = manager.texture_data[0].source_tim
    image = manager.texture_data[0].texture_image.toImage()
    image.setPixelColor(5, 96 + 7, QColor(255, 0, 255))
    manager.texture_data[0].texture_image = QPixmap.fromImage(image)
    pane._texture_widget.show_current()
    pane._texture_widget.save_file()
    tim = PalettedTim.parse(bytes(manager.enemy.texture_data['texture_data'][0]['data']))
    assert (tim.width, tim.height) == (source.width, source.height) == (128, 32)
    changed = [index for index, (a, b) in enumerate(zip(tim.indices, source.indices)) if a != b]
    assert changed == [7 * 128 + 5]
    pane.deleteLater()


@pytest.mark.parametrize("name, labels", [
    ("c0m001", ["1/2/3 - 3D", "4 - Dynamic Texture", "5 - Sequence", "6 - Camera", "7 - Stat", "8 - AI",
                "11 - Static Texture"]),
    ("c0m127", ["1 - Stat", "2 - AI"]),
    ("d0c000", ["1/2/3 - 3D", "4 - Dynamic Texture", "5 - Camera", "6 - Static Texture", "7 - Entrance"]),
    ("d0w000", ["1/2/3 - 3D", "4 - Sequence", "7 - Static Texture", "8 - Entrance"]),
    ("d1w008", ["1 - 3D", "2 - Sequence", "5 - Static Texture"]),
    ("d7c016", ["1/2/3 - 3D", "4 - Dynamic Texture", "5 - Camera", "6 - Sequence", "9 - Static Texture",
                "10 - Entrance"]),
])
def test_tabs_show_their_real_section_in_section_order(qapp, name, labels):
    manager = _manager(name)
    pane = _pane(manager, name)
    tabs = pane._tabs
    assert [tabs.tabText(i) for i in range(tabs.count()) if tabs.isTabVisible(i)] == labels
    pane.deleteLater()


def test_eye_blink_tab_opens_on_the_texture_it_animates(qapp):
    manager = _manager("d0c000")
    pane = _pane(manager, "d0c000")
    dynamic = pane._dynamic_texture_widget.dynamic_texture_widget
    entry = manager.enemy.dynamic_texture_data.dynamic_texture_data[0]
    assert entry.texture_num == 1                       # Squall's eyes are on his second texture
    assert dynamic.texture_combo.count() == 2
    assert dynamic.current_texture_index == 1 and dynamic._get_entries_for_current_texture() == [entry]
    pane.deleteLater()
