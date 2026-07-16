"""Render a mmag.bin page the way the menu draws it, into a PIL image.

The two viewers fill a PSX ordering table, so the primitives they add last are
the ones drawn first. Back to front a page is:

    paper background -> menu window -> paper mat -> picture overlays
    -> unlock block -> text -> footer

Which viewer draws it depends on the entry: the tutorial books (43-67) go
through Menu_Magazine_Draw (0x4C9330), the item-menu magazines (0-42) through
Menu_ItemMagazine_DrawPage (0x4FD6E0). They agree on everything above except
the unlock block, which only the item reader draws (and drawing it is what
unlocks the weapon/move in the savemap, every frame the page is up).

What is exact and what is not:

* **Picture overlays** are exact. Their SP2 quads (mngrp Pos 4) carry texpage
  0x00AE = VRAM (896, 0) in 8bpp, which is exactly where the page picture TIM
  declares itself, and CLUT 0x36A0 = VRAM (512, 218), the TIM's own CLUT row.
  So a quad is a straight crop of the decoded TIM.
* **The paper mat rect** is exact: a semi-transparent flat rectangle whose
  colour is the entry's tint bytes (see FF8GameData.menu.magpage).
* **Text** uses the real sysfnt.TEX glyphs at the engine's own pen positions.
  Inline {Icon} codes only reserve their advance: the icons are icon.sp1
  sprites, which belong to another file (and the Minimog editor).
* **The unlock block** is laid out exactly (positions and counts come from
  kernel.bin / mwepon.bin), the weapon remodel item names and quantities are
  real text, and both icon kinds are the real icon.sp1 sprites when it is loaded
  (the item's type icon also needs mitem.bin, which says which type it is).
  Anything not loaded falls back to a box of the right size in the right place.

  The Duel button glyphs come with a caveat the engine forces on us: it looks up
  icon.sp1 ids 128-139 through the player's **key config**, so what a player sees
  depends on their bindings. icon.sp1 holds the PlayStation pad set, which is the
  default and what this draws - `button_icon_style` lets the caller ask for plain
  boxes instead rather than imply a certainty that is not there.
* **The background is one flat rectangle at the window's real place and size.**
  Two things stack up there in game and neither is reconstructible from
  mmag.bin: the menu window gradient (BattleUI_DrawWindowBackground, shared
  with the rest of the menu) and, behind it, the paper tile - whose texture
  window resolves to a 32x32 tile at VRAM (896, 192), below the 256x192 page
  TIM, so no file the entry references carries it. They are drawn as one solid
  colour rather than pretending to more fidelity than there is.
"""
from PIL import Image, ImageDraw

from FF8GameData.font.atlas import FontAtlas
from FF8GameData.font.textlayout import FontMetrics, MENU_TEXT_LINE_HEIGHT, layout_text
from FF8GameData.menu.magpage import UNUSED_ID, MagPageEntry
from FF8GameData.tim.timfile import decode_tim

# The menu draws in a 384x240-ish space; the window sits at (24, 8) in every retail entry.
CANVAS_WIDTH = 384
CANVAS_HEIGHT = 240

BACKDROP_COLOR = (16, 16, 24, 255)
# Stand-in for the menu window + paper tile (see the module docstring).
BACKGROUND_COLOR = (24, 36, 88, 255)

FOOTER_Y = 200  # Menu_Magazine_Draw draws the footer line at y=200
ZOOM_NEUTRAL = 128  # PSX colour blending is texel * colour / 128, so 128 = unchanged

# Unlock block metrics, from Menu_ItemMagazine_DrawPage (0x4FD6E0).
DUEL_BUTTON_STEP = 40  # The pen advances 40 px per button of the combo
DUEL_SEPARATOR_DX = -16  # The separator icon sits 16 px left of its button
DUEL_SEPARATOR_ICON = 55  # The icon.sp1 id the exe draws between two buttons
# Fallback sizes, used when the icon they stand for is unavailable (no icon.sp1,
# no mitem.bin) or when the caller asked for boxes.
BUTTON_BOX = (22, 16)
SEPARATOR_BOX = (8, 8)
ITEM_ICON_BOX = (12, 12)
ITEM_NAME_DX = 14  # The exe draws the item name at icon x + 14
ITEM_ICON_DY = -2  # ... and the icon 2 px above the text

PLACEHOLDER_FILL = (210, 210, 225, 70)
PLACEHOLDER_EDGE = (225, 225, 240, 190)

# How to draw a Duel button. The engine's own choice depends on the player's key
# config, so this is the caller's to make (see the module docstring).
BUTTON_STYLE_ICONS = "icons"  # icon.sp1's PlayStation pad set, the game's default
BUTTON_STYLE_BOXES = "boxes"  # A plain box, claiming nothing
BUTTON_STYLES = (BUTTON_STYLE_ICONS, BUTTON_STYLE_BOXES)


class PageRenderer:
    """Draws mmag/mmag2 page entries. Needs a ZoneManager with mngrp loaded for
    the page textures and book text, and the menu folder for sysfnt.*"""

    def __init__(self, manager, menu_folder="", button_icon_style=BUTTON_STYLE_ICONS):
        self.manager = manager
        self.metrics = FontMetrics.from_folder(menu_folder)
        self.atlas = FontAtlas.from_folder(menu_folder) if menu_folder else None
        self.button_icon_style = button_icon_style
        self._tim_cache = {}

    @property
    def has_font(self):
        """True when real glyphs are available (else text falls back to boxes)."""
        return self.atlas is not None

    def page_texture(self, entry: MagPageEntry):
        """The decoded page picture TIM for an entry, or None."""
        raw_file = self.manager.texture_raw_file(entry)
        if raw_file not in self._tim_cache:
            data = self.manager.get_raw_file(raw_file)
            self._tim_cache[raw_file] = decode_tim(data) if data else None
        return self._tim_cache[raw_file]

    def render(self, entry: MagPageEntry, draw_background=True, draw_mat=True,
               draw_pictures=True, draw_unlock=True, draw_text=True, draw_footer=True):
        canvas = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), BACKDROP_COLOR)
        if draw_background:
            self._draw_background(canvas, entry)
        if draw_mat:
            self._draw_mat(canvas, entry)
        if draw_pictures:
            self._draw_picture_overlays(canvas, entry)
        if draw_unlock:
            self._draw_unlock(canvas, entry)
        if draw_text:
            self._draw_text_overlays(canvas, entry)
        if draw_footer and entry.footer_flag:
            self._draw_footer(canvas, entry)
        return canvas

    @staticmethod
    def _blend(canvas, box, color):
        """Alpha-composite a flat rectangle, clipped to the canvas."""
        x, y, width, height = box
        if width <= 0 or height <= 0:
            return
        canvas.alpha_composite(Image.new("RGBA", (width, height), color), (x, y))

    def _draw_background(self, canvas, entry):
        # Menu_Magazine_DrawPaperBackground tiles 64px strips across the window width,
        # under the menu window gradient; both cover exactly the window rect.
        self._blend(canvas, (entry.window_x, entry.window_y,
                             entry.window_width, entry.window_height), BACKGROUND_COLOR)

    def _draw_mat(self, canvas, entry):
        """The GP0(0x62) semi-transparent flat rect behind the page art."""
        if not entry.picture_width or not entry.picture_height:
            return
        color = (min(entry.picture_tint_r * 255 // ZOOM_NEUTRAL, 255),
                 min(entry.picture_tint_g * 255 // ZOOM_NEUTRAL, 255),
                 min(entry.picture_tint_b * 255 // ZOOM_NEUTRAL, 255),
                 ZOOM_NEUTRAL)  # PSX blend mode 0 = half back + half front
        self._blend(canvas, (entry.window_x + entry.picture_x,
                             entry.window_y + entry.picture_y,
                             entry.picture_width, entry.picture_height), color)

    def _draw_picture_overlays(self, canvas, entry):
        tim = self.page_texture(entry)
        if tim is None:
            return
        sprites = self.manager.get_sp2_sprites()
        for slot in entry.picture_overlays:
            if slot.unused:
                continue
            if sprites is None or slot.id >= len(sprites):
                continue
            for quad in sprites[slot.id].quads:
                source = tim.image.crop((quad.u, quad.v,
                                         quad.u + quad.width, quad.v + quad.height))
                canvas.alpha_composite(source, (entry.window_x + slot.x + quad.dx,
                                                entry.window_y + slot.y + quad.dy))

    def _placeholder(self, canvas, box):
        """An outlined box standing in for an icon this renderer cannot know."""
        x, y, width, height = box
        overlay = Image.new("RGBA", (width, height), PLACEHOLDER_FILL)
        ImageDraw.Draw(overlay).rectangle((0, 0, width - 1, height - 1), outline=PLACEHOLDER_EDGE)
        canvas.alpha_composite(overlay, (x, y))

    def _draw_unlock(self, canvas, entry):
        """The unlock block (entry 0x18-0x22), which only the item-menu reader draws.

        The tutorial books leave these at 0xFF, so this is a no-op for them."""
        self._draw_duel_combo(canvas, entry)
        self._draw_weapon_items(canvas, entry)

    def _draw_icon(self, canvas, icon_id, x, y, fallback_box):
        """A real icon.sp1 sprite at the engine's draw position, or a box."""
        icon = self.manager.icon_image(icon_id) if icon_id is not None else None
        if icon is None:
            self._placeholder(canvas, (x, y, *fallback_box))
            return
        image, offset_x, offset_y = icon
        canvas.alpha_composite(image, (x + offset_x, y + offset_y))

    def _draw_duel_combo(self, canvas, entry):
        """Zell's Duel button combo, drawn in the banner on the Combat King pages."""
        if entry.duel_move_id == UNUSED_ID:
            return
        x = entry.window_x + entry.duel_combo_x
        y = entry.window_y + entry.duel_combo_y
        for index, code in enumerate(self.manager.duel_sequence(entry.duel_move_id)):
            if index:  # A separator icon sits between consecutive buttons
                self._draw_icon(canvas, DUEL_SEPARATOR_ICON,
                                x + DUEL_SEPARATOR_DX, y + 4, SEPARATOR_BOX)
            if self.button_icon_style == BUTTON_STYLE_ICONS:
                self._draw_icon(canvas, self.manager.button_icon_id(code), x, y, BUTTON_BOX)
            else:
                self._placeholder(canvas, (x, y, *BUTTON_BOX))
            x += DUEL_BUTTON_STEP

    def _draw_weapon_items(self, canvas, entry):
        """The mwepon.bin remodel line: one row of icon + item name + quantity."""
        if entry.weapon_index == UNUSED_ID:
            return
        x = entry.window_x + entry.weapon_list_x
        y = entry.window_y + entry.weapon_list_y
        for item_id, quantity in self.manager.weapon_items(entry.weapon_index):
            self._draw_icon(canvas, self.manager.item_icon_id(item_id),
                            x, y + ITEM_ICON_DY, ITEM_ICON_BOX)
            self._draw_string(canvas, self.manager.get_item_name(item_id), x + ITEM_NAME_DX, y)
            # The engine ends the quantity on the column x (menu_draw_number_rightaligned)
            self._draw_string(canvas, str(quantity), x + entry.weapon_quantity_column_x, y,
                              right_align=True)
            y += entry.weapon_line_spacing

    def _draw_text_overlays(self, canvas, entry):
        for slot in entry.text_overlays:
            if slot.unused:
                continue
            text = self.manager.get_overlay_text(entry, slot)
            if not text:
                continue
            self._draw_string(canvas, text, entry.window_x + slot.x, entry.window_y + slot.y)

    def _draw_footer(self, canvas, entry):
        text = self.manager.get_footer_text()
        if not text:
            return
        layout = layout_text(text, self.manager.game_data, self.metrics,
                             line_height=MENU_TEXT_LINE_HEIGHT)
        # Menu_Magazine_Draw centres it: x = (336 - width) / 2 + 24
        self._draw_string(canvas, text, (336 - layout.max_width) // 2 + 24, FOOTER_Y)

    def _draw_string(self, canvas, text, x, y, right_align=False):
        layout = layout_text(text, self.manager.game_data, self.metrics,
                             line_height=MENU_TEXT_LINE_HEIGHT)
        if right_align:
            x -= layout.max_width
        if self.atlas is not None:
            self.atlas.draw_layout(canvas, layout, x, y)
            return
        # No sysfnt.TEX: show each glyph as a box of its true width so the text
        # blocks are still placed and sized correctly.
        for glyph in layout.glyphs:
            self._blend(canvas, (x + glyph.x, y + glyph.y,
                                 max(glyph.width - 1, 1), MENU_TEXT_LINE_HEIGHT - 3),
                        (210, 210, 210, 160))
