"""Tests for rendering mmag2.bin pages (the shared PageRenderer driven by MoombaManager).

The Chocobo World screen draws only the two overlay layers (Menu_ChocoboWorld_Draw,
0x4D1D30) — no window, paper, mat, unlock block or footer — so these assert that
those layers stay off and that the art + raw-90 text land where the entry says.
Needs the real art/text out of mngrp.bin, so everything here is ff8data.
"""
import pathlib

import pytest

from FF8GameData.gamedata import GameData
from FF8GameData.menu.pagerender import CANVAS_HEIGHT, CANVAS_WIDTH, PageRenderer
from Moomba.moombamanager import MoombaManager

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MENU_DIR = PROJECT_ROOT / "extracted_files" / "menu"

pytestmark = pytest.mark.ff8data("extracted_files/menu/mmag2.bin",
                                 "extracted_files/menu/mngrp.bin",
                                 "extracted_files/menu/mngrphd.bin",
                                 "extracted_files/menu/sysfnt.TEX",
                                 "extracted_files/menu/sysfnt.tdw")


@pytest.fixture(scope="module")
def manager():
    game_data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    game_data.load_all()
    moomba = MoombaManager(game_data)
    moomba.load_file(str(MENU_DIR / "mmag2.bin"))
    moomba.load_mngrp(str(MENU_DIR / "mngrp.bin"))
    return moomba


@pytest.fixture(scope="module")
def renderer(manager):
    return PageRenderer(manager, menu_folder=str(MENU_DIR))


def test_only_the_overlay_layers_are_drawn(manager):
    """The Chocobo World screen composites only the overlays onto its own chrome."""
    assert manager.DRAWS_PICTURES is True and manager.DRAWS_TEXT is True
    assert manager.DRAWS_BACKGROUND is False
    assert manager.DRAWS_MAT is False
    assert manager.DRAWS_UNLOCK is False
    assert manager.DRAWS_FOOTER is False


def test_render_size_and_no_window_or_mat(renderer, manager):
    entry = manager.entries[0]
    image = renderer.render(entry)
    assert image.size == (CANVAS_WIDTH, CANVAS_HEIGHT)
    # By default (manager flags) the background/mat layers are off, so a page with its
    # art and text turned off is nothing but the bare backdrop.
    from FF8GameData.menu.pagerender import BACKDROP_COLOR
    bare = renderer.render(entry, draw_pictures=False, draw_text=False)
    assert {pixel for _count, pixel in bare.getcolors(maxcolors=256)} == {BACKDROP_COLOR}


def test_page_texture_is_category_6(renderer, manager):
    # Story pages -> raw 180, manual pages -> raw 181
    assert manager.texture_raw_file(manager.entries[0]) == 180  # story slide
    assert manager.texture_raw_file(manager.entries[4]) == 181  # manual page
    tim = renderer.page_texture(manager.entries[0])
    assert tim is not None and tim.image.size == (256, 192)


def test_picture_overlay_lands_where_the_entry_says(renderer, manager):
    """Story slide 1's art is sprite 58; turning it off must change only its rect."""
    entry = manager.entries[0]
    slot = next(slot for slot in entry.picture_overlays if not slot.unused)
    quad = manager.get_sp2_sprites()[slot.id].quads[0]

    with_art = renderer.render(entry, draw_text=False)
    bare = renderer.render(entry, draw_pictures=False, draw_text=False)
    changed = [(x, y) for x in range(CANVAS_WIDTH) for y in range(CANVAS_HEIGHT)
               if with_art.getpixel((x, y)) != bare.getpixel((x, y))]
    assert changed, "the picture overlay must draw something"
    left = entry.window_x + slot.x + quad.dx
    top = entry.window_y + slot.y + quad.dy
    for x, y in changed:
        assert left <= x < left + quad.width, f"pixel {x},{y} outside the sprite rect"
        assert top <= y < top + quad.height, f"pixel {x},{y} outside the sprite rect"


def test_text_overlays_draw_the_raw90_strings(renderer, manager):
    entry = manager.entries[0]
    with_text = renderer.render(entry)
    without_text = renderer.render(entry, draw_text=False)
    assert with_text.tobytes() != without_text.tobytes()


def test_every_page_renders(renderer, manager):
    for entry in manager.entries:
        assert renderer.render(entry).size == (CANVAS_WIDTH, CANVAS_HEIGHT)


def test_forcing_the_magazine_layers_on_is_still_possible(renderer, manager):
    """The manager flags are only the defaults; a caller can override each one."""
    entry = manager.entries[0]
    default = renderer.render(entry)
    with_mat = renderer.render(entry, draw_mat=True, draw_background=True)
    # Entry 0's picture rect is 0x0, so the mat draws nothing, but the background does
    assert with_mat.tobytes() != default.tobytes()
