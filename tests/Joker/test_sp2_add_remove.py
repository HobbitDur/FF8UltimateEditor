"""Add / remove sprite ids: only added ones can go, and no id after a removed one moves."""
import sys

import pytest
from PyQt6.QtWidgets import QApplication

from Joker.jokermanager import Sp2File, Sp2Quad, Sp2Sprite


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def _table(count):
    return Sp2File([Sp2Sprite(i, quads=[Sp2Quad(u=i)]) for i in range(count)])


def test_remove_keeps_the_ids_after_and_add_reuses_the_gap():
    sp2 = _table(3)
    assert sp2.add_sprite(reuse_from=3).sprite_id == 3
    assert sp2.add_sprite(reuse_from=3).sprite_id == 4
    sp2.remove_sprite(3, keep_count=3)            # before 4: only made unused
    assert len(sp2.sprites) == 5 and not sp2.sprites[3].used and sp2.sprites[4].used
    assert sp2.add_sprite(reuse_from=3).sprite_id == 3   # the gap is taken again
    sp2.remove_sprite(4, keep_count=3)            # the last one: gone
    sp2.remove_sprite(3, keep_count=3)
    assert len(sp2.sprites) == 3
    with pytest.raises(ValueError):
        sp2.remove_sprite(1, keep_count=3)        # the file's own


def test_the_editor_buttons(qapp):
    from Joker.sp2editorwidget import Sp2EditorWidget
    editor = Sp2EditorWidget()
    sp2 = _table(3)
    editor.set_sp2(sp2)
    assert not editor.remove_sprite_button.isEnabled()      # id 0, the file's
    editor.add_sprite_button.click()
    assert editor.sprite_list.currentRow() == 3 and editor.remove_sprite_button.isEnabled()
    editor.remove_sprite_button.click()
    assert len(sp2.sprites) == 3 and sp2.to_bytes() == _table(3).to_bytes()


def test_shiva_keeps_the_games_79_sprites(qapp):
    from Shiva.ShivaSprite.shivaspritewidget import ShivaSpriteWidget
    tab = ShivaSpriteWidget()
    tab.sp2 = _table(80)                     # a mod's mngrp: one sprite added after the game's 79
    tab.sp2_editor.set_sp2(tab.sp2, select_row=78)
    assert not tab.sp2_editor.remove_sprite_button.isEnabled()
    tab.sp2_editor.sprite_list.setCurrentRow(79)
    assert tab.sp2_editor.remove_sprite_button.isEnabled()


def test_a_new_shiva_sprite_uses_the_page_pictures_texture_page(qapp):
    from Shiva.ShivaSprite.shivaspritewidget import ShivaSpriteWidget
    tab = ShivaSpriteWidget()
    tab.sp2 = _table(79)
    tab.sp2_editor.set_sp2(tab.sp2)
    tab.sp2_editor.add_sprite_button.click()
    quad = tab.sp2.sprites[79].quads[0]
    assert (quad.clut, quad.texpage, quad.width, quad.height) == (0x36A0, 0x00AE, 128, 96)
