"""FF8 menu font atlas (sysfnt.TEX): turn FF8 code bytes into glyph images.

menu_draw_text (0x4BDE30) emits one 12x12 textured quad per printable code:

    cell = code - 0x20
    U    = 12 * (cell % 21)
    V    = 12 * (cell / 21)

(the exe packs both into one u16 as ``12 * ((cell % 21) | (cell / 21) << 8)``,
which is the same thing). The atlas is therefore 21 columns of 12x12 glyphs.

sysfnt.TEX carries 8 palettes, one per sysfnt colour index ({White} = 7 is the
engine default); the blink colours reuse their base palette.

Only the single-byte path is implemented: codes 0x19-0x1F are a 2-byte lead for
the extended (Japanese) tables, whose cells live past the end of the EN atlas.
"""
from PIL import Image

from FF8GameData.tex.texfile import TexFile

GLYPH_SIZE = 12  # Each atlas cell is 12x12 pixels
ATLAS_COLUMNS = 21  # menu_draw_text divides/modulos the cell index by 21
FIRST_CODE = 0x20  # Cell 0 is FF8 code 0x20
NB_PALETTE = 8  # sysfnt.TEX palettes = the 8 sysfnt base colours


class FontAtlas:
    """Glyph images from sysfnt.TEX, cached per (code, colour)."""

    def __init__(self, images_by_palette):
        self._images = images_by_palette  # [PIL.Image] indexed by palette
        self._cache = {}

    @classmethod
    def from_file(cls, tex_path):
        tex = TexFile.read(tex_path)
        images = [tex.to_image(palette) for palette in range(min(NB_PALETTE, tex.num_palettes))]
        return cls(images)

    @classmethod
    def from_folder(cls, folder):
        """Load sysfnt.TEX from a menu folder, or None when it is not there."""
        import os
        tex_path = os.path.join(folder, "sysfnt.TEX")
        if not os.path.exists(tex_path):
            return None
        return cls.from_file(tex_path)

    def glyph(self, code, color=7):
        """The 12x12 RGBA image of an FF8 code byte, or None if it has no cell."""
        key = (code, color)
        if key in self._cache:
            return self._cache[key]
        cell = code - FIRST_CODE
        if cell < 0 or not self._images:
            return None
        atlas = self._images[color % len(self._images)]
        u = GLYPH_SIZE * (cell % ATLAS_COLUMNS)
        v = GLYPH_SIZE * (cell // ATLAS_COLUMNS)
        if v + GLYPH_SIZE > atlas.height:  # Past the end of the atlas (extended tables)
            return None
        image = atlas.crop((u, v, u + GLYPH_SIZE, v + GLYPH_SIZE))
        self._cache[key] = image
        return image

    def draw_layout(self, target: Image.Image, layout, origin_x=0, origin_y=0):
        """Blit every glyph of a TextLayout onto target at its pen position.

        Returns the number of glyphs that had no atlas cell (drawn by the caller
        as a fallback if it wants one)."""
        missing = 0
        for glyph in layout.glyphs:
            image = self.glyph(glyph.code, glyph.color)
            if image is None:
                missing += 1
                continue
            target.alpha_composite(image, (origin_x + glyph.x, origin_y + glyph.y))
        return missing
