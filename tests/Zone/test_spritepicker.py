"""The sprite picker: the page's picture with the sprites' rectangles, picked by clicking."""
import pathlib
import sys

import pytest
from PyQt6.QtWidgets import QApplication

from Joker.jokermanager import Sp2Quad, Sp2Sprite

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MENU_DIR = PROJECT_ROOT / "extracted_files" / "menu"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def _sprite(sprite_id, *rects, used=True):
    quads = [Sp2Quad(u=u, v=v, clut=0, width=w, height=h, dx=0, dy=0, texpage=0) for u, v, w, h in rects]
    return Sp2Sprite(sprite_id=sprite_id, quads=quads, used=used)


def test_the_smallest_sprite_under_the_click_wins():
    from Zone.spritepicker import sprite_at
    big = _sprite(1, (0, 0, 128, 96))
    small = _sprite(2, (10, 10, 20, 20))
    assert sprite_at([big, small], 15, 15) is small
    assert sprite_at([big, small], 100, 50) is big
    assert sprite_at([big, small], 200, 150) is None


def test_the_dialog_lists_usable_sprites_and_keeps_the_choice(qapp):
    from Zone.spritepicker import SpritePickerDialog
    sprites = [_sprite(0, (0, 0, 64, 64)), _sprite(1, (64, 0, 64, 64), used=False), _sprite(2, (0, 64, 32, 32))]
    dialog = SpritePickerDialog(None, sprites, current_id=2)
    assert dialog.sprite_list.count() == 3  # "none" + sprites 0 and 2 (1 is unused)
    assert dialog.selected_id() == 2
    dialog.select(0)
    assert dialog.selected_id() == 0 and dialog.sprite_list.currentRow() == 1


@pytest.mark.ff8data("extracted_files/menu/mmag.bin", "extracted_files/menu/mngrp.bin",
                     "extracted_files/menu/mngrphd.bin")
def test_zone_opens_the_picker_on_the_page_picture(qapp, monkeypatch):
    from Zone import zonewidget
    from Zone.zonewidget import ZoneWidget
    zone = ZoneWidget()
    zone._load_mmag(str(MENU_DIR / "mmag.bin"))
    zone._apply_mngrp(str(MENU_DIR / "mngrp.bin"))
    zone.select_entry(8)
    seen = {}

    class FakeDialog:
        def __init__(self, picture, sprites, current_id, parent=None):
            seen["picture"], seen["current"] = picture, current_id

        def exec(self):
            return True

        def selected_id(self):
            return 3

    monkeypatch.setattr(zonewidget, "SpritePickerDialog", FakeDialog)
    zone._pick_sprite(0)
    assert seen["picture"] is not None and seen["picture"].size == (256, 192)
    assert zone.pic_overlay_spins[0][2].value() == 3


@pytest.mark.ff8data("extracted_files/menu/mmag.bin", "extracted_files/menu/mngrp.bin",
                     "extracted_files/menu/mngrphd.bin")
def test_a_sprite_picked_with_the_button_redraws_the_preview_and_marks_the_page_edited(qapp, monkeypatch):
    """The picker sets the slot's id from code: the preview must still redraw (it once only heard
    the combo's own index changes) and the page count as edited."""
    from Zone import zonewidget
    from Zone.zonewidget import ZoneWidget
    zone = ZoneWidget()
    zone._load_mmag(str(MENU_DIR / "mmag.bin"))
    zone._apply_mngrp(str(MENU_DIR / "mngrp.bin"))
    zone.select_entry(8)
    marks = []
    monkeypatch.setattr(zone, "_mark_edited", lambda: marks.append(1))
    redraws = []
    zone._preview_timer.timeout.disconnect()
    zone._preview_timer.timeout.connect(lambda: redraws.append(1))

    class FakeDialog:
        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return True

        def selected_id(self):
            return 3

    monkeypatch.setattr(zonewidget, "SpritePickerDialog", FakeDialog)
    zone._pick_sprite(0)
    assert zone._preview_timer.isActive() or redraws  # the redraw is scheduled
    assert marks
