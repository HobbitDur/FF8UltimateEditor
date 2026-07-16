"""Tests for the Zone page renderer (Zone/zonerender.py).

Rendering needs the real page art and book text out of mngrp.bin, so every test
here is ff8data. They assert the things that are meant to be *exact* - that the
art lands where the entry says, that the mat takes its colour from the tint
bytes - rather than pixel-comparing against a reference image.
"""
import pathlib

import pytest

from FF8GameData.gamedata import GameData
from Zone.zonemanager import ZoneManager
from Zone.zonerender import BACKGROUND_COLOR, CANVAS_HEIGHT, CANVAS_WIDTH, PageRenderer

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MENU_DIR = PROJECT_ROOT / "extracted_files" / "menu"

pytestmark = pytest.mark.ff8data("extracted_files/menu/mmag.bin",
                                 "extracted_files/menu/mngrp.bin",
                                 "extracted_files/menu/mngrphd.bin",
                                 "extracted_files/menu/mwepon.bin",
                                 "extracted_files/menu/mitem.bin",
                                 "extracted_files/menu/icon.sp1",
                                 "extracted_files/menu/icon.TEX",
                                 "extracted_files/main/kernel.bin",
                                 "extracted_files/menu/sysfnt.TEX",
                                 "extracted_files/menu/sysfnt.tdw")


@pytest.fixture(scope="module")
def manager():
    game_data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    game_data.load_all()
    zone = ZoneManager(game_data)
    zone.load_file(str(MENU_DIR / "mmag.bin"))
    zone.load_mngrp(str(MENU_DIR / "mngrp.bin"))
    zone.load_kernel(str(PROJECT_ROOT / "extracted_files" / "main" / "kernel.bin"))
    zone.load_mwepon(str(MENU_DIR / "mwepon.bin"))
    zone.load_icons(str(MENU_DIR / "icon.sp1"))
    zone.load_mitem(str(MENU_DIR / "mitem.bin"))
    return zone


@pytest.fixture(scope="module")
def renderer(manager):
    return PageRenderer(manager, menu_folder=str(MENU_DIR))


def test_font_and_textures_are_available(renderer, manager):
    assert renderer.has_font is True
    assert renderer.metrics.exact is True
    # Weapons Monthly 1st issue -> raw 28, a 256x192 8bpp TIM
    tim = renderer.page_texture(manager.entries[0])
    assert tim is not None and tim.image.size == (256, 192)


def test_sp2_table_is_the_one_the_overlays_index(manager):
    sprites = manager.get_sp2_sprites()
    assert sprites is not None and len(sprites) == 79
    # Entry 0's picture overlay is sprite 0, whose quad samples the page TIM:
    # texpage 0x00AE = VRAM (896, 0) 8bpp, the page picture slot.
    quad = sprites[0].quads[0]
    assert quad.texpage & 0xF == 14  # texpage X * 64 = 896
    assert (quad.texpage >> 7) & 3 == 1  # colour mode 1 = 8bpp


def test_render_size_and_background(renderer, manager):
    image = renderer.render(manager.entries[0])
    assert image.size == (CANVAS_WIDTH, CANVAS_HEIGHT)
    entry = manager.entries[0]
    # Inside the window but away from art/text: the flat background stand-in
    assert image.getpixel((entry.window_x + 2, entry.window_y + entry.window_height - 2)) \
        == BACKGROUND_COLOR


def test_mat_takes_its_colour_from_the_tint_bytes(renderer, manager):
    """Entry 0's mat is the sepia (115, 35, 0) rect behind the Lion Heart."""
    entry = manager.entries[0]
    assert (entry.picture_tint_r, entry.picture_tint_g, entry.picture_tint_b) == (115, 35, 0)
    image = renderer.render(manager.entries[0], draw_pictures=False, draw_text=False)
    # A pixel inside the mat rect: reddish-brown, and clearly not the blue background
    pixel = image.getpixel((entry.window_x + entry.picture_x + 4,
                            entry.window_y + entry.picture_y + entry.picture_height - 4))
    assert pixel[0] > pixel[1] > pixel[2], f"mat should be sepia, got {pixel}"
    assert pixel != BACKGROUND_COLOR


def test_picture_overlay_lands_where_the_entry_says(renderer, manager):
    """Turning the art off must change pixels only under the sprite's rect."""
    entry = manager.entries[0]
    slot = entry.picture_overlays[0]
    assert not slot.unused
    quad = manager.get_sp2_sprites()[slot.id].quads[0]

    with_art = renderer.render(entry, draw_text=False, draw_unlock=False)
    without_art = renderer.render(entry, draw_pictures=True, draw_text=False, draw_unlock=False)
    assert with_art.tobytes() == without_art.tobytes()  # same flags -> deterministic

    bare = renderer.render(entry, draw_pictures=False, draw_text=False, draw_unlock=False)
    changed = [(x, y) for x in range(CANVAS_WIDTH) for y in range(CANVAS_HEIGHT)
               if with_art.getpixel((x, y)) != bare.getpixel((x, y))]
    assert changed, "the picture overlay must draw something"
    left = entry.window_x + slot.x + quad.dx
    top = entry.window_y + slot.y + quad.dy
    for x, y in changed:
        assert left <= x < left + quad.width, f"pixel {x},{y} outside the sprite rect"
        assert top <= y < top + quad.height, f"pixel {x},{y} outside the sprite rect"


def test_text_overlays_draw_and_are_toggleable(renderer, manager):
    entry = manager.entries[0]
    with_text = renderer.render(entry)
    without_text = renderer.render(entry, draw_text=False, draw_footer=False)
    assert with_text.tobytes() != without_text.tobytes()


def test_footer_only_on_the_multi_page_books(renderer, manager):
    """The footer is the scroll hint, so the one-page magazines do not set it."""
    assert manager.get_footer_text().endswith("to go to Tutorial")
    assert manager.entries[0].footer_flag == 1  # Weapons Monthly: 4 pages
    assert manager.entries[28].footer_flag == 0  # Combat King 001: 1 page
    assert manager.entries[43].footer_flag == 1  # Battle tutorial: 8 pages

    entry = manager.entries[0]
    with_footer = renderer.render(entry, draw_text=False)
    without_footer = renderer.render(entry, draw_text=False, draw_footer=False)
    assert with_footer.tobytes() != without_footer.tobytes()


def test_every_entry_renders(renderer, manager):
    """Including entry 68, the empty terminator, and the tutorial books."""
    for entry in manager.entries:
        image = renderer.render(entry)
        assert image.size == (CANVAS_WIDTH, CANVAS_HEIGHT)


def test_combat_king_has_no_page_art_only_the_duel_combo(renderer, manager):
    """The Combat King pages have no picture overlay at all, so nothing samples
    their page texture (raw 20 is even a byte-identical copy of the Weapons
    Monthly one). What fills their banner is the Duel combo."""
    entry = manager.entries[28]
    assert all(slot.unused for slot in entry.picture_overlays)
    assert renderer.render(entry, draw_pictures=True, draw_text=False, draw_unlock=False).tobytes() \
        == renderer.render(entry, draw_pictures=False, draw_text=False, draw_unlock=False).tobytes()

    with_combo = renderer.render(entry, draw_text=False)
    without = renderer.render(entry, draw_text=False, draw_unlock=False)
    assert with_combo.tobytes() != without.tobytes(), "the Duel combo must draw"


def test_duel_combo_is_laid_out_the_way_the_exe_walks_it(renderer, manager):
    """One button per code, 40 px apart, starting at the entry's combo position."""
    from Zone.zonerender import BUTTON_BOX, DUEL_BUTTON_STEP
    entry = manager.entries[32]  # My Final Heaven: the 5-button combo
    sequence = manager.duel_sequence(entry.duel_move_id)
    assert len(sequence) == 5

    with_combo = renderer.render(entry, draw_text=False)
    without = renderer.render(entry, draw_text=False, draw_unlock=False)
    changed = [(x, y) for x in range(CANVAS_WIDTH) for y in range(CANVAS_HEIGHT)
               if with_combo.getpixel((x, y)) != without.getpixel((x, y))]
    assert changed
    left = entry.window_x + entry.duel_combo_x
    top = entry.window_y + entry.duel_combo_y
    last_button_right = left + DUEL_BUTTON_STEP * (len(sequence) - 1) + BUTTON_BOX[0]
    for x, y in changed:
        assert left - 16 <= x < last_button_right, f"combo pixel {x},{y} outside the run"
        assert top <= y < top + BUTTON_BOX[1] + 4
    # The run stays on screen, inside the window
    assert last_button_right <= entry.window_x + entry.window_width


def test_weapon_remodel_list_draws_real_item_names(renderer, manager):
    """Weapons Monthly 1st issue page 1 lists the real Lion Heart recipe."""
    entry = manager.entries[0]
    items = manager.weapon_items(entry.weapon_index)
    assert [(manager.get_item_name(i), q) for i, q in items] == \
        [("Adamantine", 1), ("Dragon Fang", 4), ("Pulse Ammo", 12)]

    with_list = renderer.render(entry, draw_text=False)
    without = renderer.render(entry, draw_text=False, draw_unlock=False)
    assert with_list.tobytes() != without.tobytes()


def test_unlock_block_is_a_no_op_for_the_tutorial_books(renderer, manager):
    """Entries 43-67 leave 0x18-0x22 at 0xFF; the tutorial viewer never reads them."""
    for index in range(43, 68):
        entry = manager.entries[index]
        assert renderer.render(entry, draw_unlock=True).tobytes() \
            == renderer.render(entry, draw_unlock=False).tobytes()


def test_button_icons_resolve_the_way_the_exe_picks_them(manager):
    """icon = 128 + lowest set bit of (code & 0xF0FF): 128-135 are the shoulder and
    face buttons, 140-143 the d-pad directions."""
    # Dolphin Blow alternates the two shoulder buttons
    assert [manager.button_icon_id(c) for c in manager.duel_sequence(4)] == [130, 131, 130, 131]
    # My Final Heaven rotates the d-pad, then a face button
    assert [manager.button_icon_id(c) for c in manager.duel_sequence(9)] == [140, 141, 142, 143, 132]
    # Bits 8-11 (Select/L3/R3/Start) are masked out rather than drawn
    assert manager.button_icon_id(0x4100) == 128 + 14  # bit 8 dropped, bit 14 kept


def test_item_type_icons_come_from_mitem_and_the_exe_table(manager):
    """byte_B88024[item type] + 223, so every remodel item resolves to icon 223-229."""
    items = manager.weapon_items(manager.entries[0].weapon_index)
    icon_ids = [manager.item_icon_id(item_id) for item_id, _q in items]
    assert icon_ids == [224, 229, 227]
    assert all(223 <= icon_id <= 229 for icon_id in icon_ids)


def test_button_style_is_the_callers_choice(manager):
    """The engine picks the glyph via the key config, so both are legitimate."""
    from Zone.zonerender import BUTTON_STYLE_BOXES, BUTTON_STYLE_ICONS
    entry = manager.entries[32]
    icons = PageRenderer(manager, menu_folder=str(MENU_DIR),
                         button_icon_style=BUTTON_STYLE_ICONS).render(entry, draw_text=False)
    boxes = PageRenderer(manager, menu_folder=str(MENU_DIR),
                         button_icon_style=BUTTON_STYLE_BOXES).render(entry, draw_text=False)
    assert icons.tobytes() != boxes.tobytes()


def test_icons_fall_back_to_boxes_when_icon_sp1_is_absent(manager, tmp_path):
    """A renderer is still usable without icon.sp1 - the boxes keep the layout."""
    bare = ZoneManager(manager.game_data)
    bare.load_file(str(MENU_DIR / "mmag.bin"))
    bare.load_mngrp(str(MENU_DIR / "mngrp.bin"))
    bare.load_kernel(str(PROJECT_ROOT / "extracted_files" / "main" / "kernel.bin"))
    assert bare.icons_loaded is False and bare.mitem_loaded is False
    assert bare.icon_image(130) is None and bare.item_icon_id(1) is None
    renderer = PageRenderer(bare, menu_folder=str(MENU_DIR))
    entry = bare.entries[32]
    with_combo = renderer.render(entry, draw_text=False)
    without = renderer.render(entry, draw_text=False, draw_unlock=False)
    assert with_combo.tobytes() != without.tobytes()


def test_render_without_a_font_falls_back_to_boxes(manager):
    """No sysfnt.* : text still lays out, drawn as boxes of the right width."""
    renderer = PageRenderer(manager, menu_folder="")
    assert renderer.has_font is False
    entry = manager.entries[0]
    with_text = renderer.render(entry)
    without_text = renderer.render(entry, draw_text=False, draw_footer=False)
    assert with_text.tobytes() != without_text.tobytes()
