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
    ("d0c000", ["1/2/3 - 3D", "4 - Dynamic Texture", "5 - Camera", "6 - Static Texture", "7 - Entrance",
                "Exe - Limit anim."]),
    ("d0w000", ["1/2/3 - 3D", "4 - Sequence", "7 - Static Texture", "8 - Entrance", "Exe - Limit anim."]),
    ("d1w008", ["1 - 3D", "2 - Sequence", "5 - Static Texture"]),
    ("d7c016", ["1/2/3 - 3D", "4 - Dynamic Texture", "5 - Camera", "6 - Sequence", "9 - Static Texture",
                "10 - Entrance", "Exe - Limit anim."]),
])
def test_tabs_show_their_real_section_in_section_order(qapp, name, labels):
    """A character body / weapon with exe anim sets also shows the "Exe - Limit anim." tab, greyed
    while no FF8 exe / .animset is open (Zell's reduced gloves never have it)."""
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


def test_squall_eye_blink_entry(qapp):
    """Section 4 entry = a destination the polygons sample + the sprites copied onto it
    (QueueTextureAnimation 0x50C780): Squall's right painted eye, open eye 0, closed eye 1."""
    manager = _manager("d0c000")
    entry = manager.enemy.dynamic_texture_data.dynamic_texture_data[0]
    assert entry.table_index == 0 and entry.texture_num == 1
    assert (entry.destination.get_u_pixel(), entry.destination.get_v_pixel()) == (64, 29)
    assert (entry.sprite_width, entry.sprite_height) == (12, 6)
    assert [(sprite.get_u_pixel(), sprite.get_v_pixel()) for sprite in entry.sprites] == [(44, 90), (58, 90)]
    assert entry.anim_speed == 0


def test_an_edit_keeps_the_entry_ids_the_sequences_use(qapp):
    """c0m056 has no entry 0 (offset table [0, 4]): its only entry is entry 1, and stays entry 1
    when an edit rebuilds the section (the engine reads offset[n] positionally)."""
    from FF8GameData.monsterdata import DynamicTextureSection
    raw = bytes(_manager("c0m056").enemy.section_raw_data[4])
    section = DynamicTextureSection()
    section.analyze(raw)
    assert [entry.table_index for entry in section.dynamic_texture_data] == [1]
    section.dynamic_texture_data[0].destination.set_v_pixel(7)
    rebuilt = bytes(section.to_binary())
    assert rebuilt != raw and int.from_bytes(rebuilt[0:2], "little") == 0
    again = DynamicTextureSection()
    again.analyze(rebuilt)
    assert [entry.table_index for entry in again.dynamic_texture_data] == [1]
    assert again.dynamic_texture_data[0].destination.get_v_pixel() == 7


def test_play_paints_each_sprite_onto_the_destination(qapp):
    manager = _manager("d0c000")
    pane = _pane(manager, "d0c000")
    dynamic = pane._dynamic_texture_widget.dynamic_texture_widget
    entry = dynamic._get_entries_for_current_texture()[0]
    image = dynamic._current_texture_image().toImage()
    dynamic._show_sprite_on_destination(1)                  # the closed eye copied onto the eye
    shown = dynamic.texture_preview.original_pixmap.toImage()
    dx, dy = entry.destination.get_u_pixel(), entry.destination.get_v_pixel()
    sx, sy = entry.sprites[1].get_u_pixel(), entry.sprites[1].get_v_pixel()
    for x in range(entry.sprite_width):
        for y in range(entry.sprite_height):
            assert shown.pixel(dx + x, dy + y) == image.pixel(sx + x, sy + y)
    assert shown.pixel(0, 0) == image.pixel(0, 0)          # the rest untouched
    dynamic._show_sprite_on_destination(-1)                 # stopped: as in the file
    assert dynamic.texture_preview.original_pixmap.toImage() == image
    pane.deleteLater()
