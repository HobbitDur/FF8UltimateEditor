"""Magazine page pictures: the slots the PC game shows, and a picture written into both copies."""
import pathlib
import shutil
import struct

import pytest
from PIL import Image

from FF8GameData.menu.magpicture import (PC_PICTURE_FILES, encode_picture_tex, encode_picture_tim,
                                         pc_picture_file_name, quantize_picture, tex_to_image)
from FF8GameData.tex.texfile import HEADER_SIZE, TexFile
from FF8GameData.tim.timfile import PalettedTim, decode_tim

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MENU = PROJECT_ROOT / "extracted_files" / "menu"


def _test_image():
    image = Image.new("RGBA", (256, 192))
    image.putdata([(x, y, (x * y) % 256, 255) for y in range(192) for x in range(256)])
    for x in range(20):
        for y in range(20):
            image.putpixel((x, y), (0, 0, 0, 0))        # transparent corner
            image.putpixel((x + 40, y), (0, 0, 0, 255))  # opaque black square
    return image


def _template_tim():
    return PalettedTim(1, 512, 218, [[0] * 256], 896, 0, 256, 192, bytes(256 * 192)).to_bytes()


def _template_tex():
    header = bytearray(HEADER_SIZE)
    for offset, value in ((0x00, 2), (0x08, 1), (0x30, 1), (0x34, 256), (0x38, 8), (0x3C, 256), (0x40, 256)):
        struct.pack_into("<I", header, offset, value)
    palette = bytearray((0, 0, 0, 0)) + bytearray((1, 2, 3, 255)) * 255
    return TexFile(header, palette, bytearray(256 * 256), 1, 256, 8, 256, 256)


def test_the_slots_the_pc_game_shows():
    assert pc_picture_file_name(28) == "mag00.TEX"
    assert pc_picture_file_name(24) == "mag07.TEX"
    assert pc_picture_file_name(184) == "mag19.TEX"
    assert pc_picture_file_name(100) is None  # a slot the switches do not have is never uploaded
    assert pc_picture_file_name(206) == "mag206.TEX"  # past them: FFNx's AddMorePictures
    assert len(PC_PICTURE_FILES) == 30


def test_quantize_keeps_index_0_for_transparent_pixels_only():
    palette, indices = quantize_picture(_test_image())
    assert len(palette) == 256 and len(indices) == 256 * 192
    assert indices[0] == 0                       # transparent corner
    black = indices[40]
    assert black != 0 and palette[black] != (0, 0, 0)  # opaque black is not the transparent colour
    assert all(index != 0 for index in indices[256 * 100: 256 * 101])


def test_a_256x256_export_is_cropped_and_other_sizes_refused():
    big = Image.new("RGBA", (256, 256), (10, 20, 30, 255))
    assert len(quantize_picture(big)[1]) == 256 * 192
    with pytest.raises(ValueError):
        quantize_picture(Image.new("RGBA", (320, 240)))


def test_tim_keeps_the_template_vram_placement():
    palette, indices = quantize_picture(_test_image())
    data = encode_picture_tim(palette, indices, _template_tim())
    tim = PalettedTim.parse(data)
    assert (tim.clut_x, tim.clut_y, tim.image_x, tim.image_y) == (512, 218, 896, 0)
    assert tim.indices == indices
    assert len(data) == 49696  # the vanilla page TIM size
    decoded = decode_tim(data).image
    assert decoded.getpixel((0, 0))[3] == 0
    assert decoded.getpixel((100, 100))[3] == 255


def test_tex_has_the_picture_on_top_and_index_0_below():
    palette, indices = quantize_picture(_test_image())
    tex = encode_picture_tex(palette, indices, _template_tex())
    reread = TexFile.from_bytes(tex.to_bytes())
    assert bytes(reread.pixels[:256 * 192]) == indices
    assert set(reread.pixels[256 * 192:]) == {0}
    assert reread.palette(0)[0] == (0, 0, 0, 0)
    image = tex_to_image(reread)
    assert image.size == (256, 192)
    r, g, b, a = image.getpixel((200, 150))
    assert a == 255 and abs(r - 200) < 24 and abs(g - 150) < 24


@pytest.mark.ff8data("extracted_files/menu/mag00.TEX")
def test_vanilla_tex_reads_as_a_page_picture():
    image = tex_to_image(TexFile.read(str(MENU / "mag00.TEX")))
    assert image.size == (256, 192)
    assert len(image.getcolors(65536)) > 16  # all 8 bits of the index are used, not the low nibble


@pytest.mark.ff8data("extracted_files/menu/mag00.TEX")
def test_vanilla_tex_round_trips_through_the_encoder(tmp_path):
    vanilla = TexFile.read(str(MENU / "mag00.TEX"))
    palette = [(r, g, b) for r, g, b, _a in vanilla.palette(0)]
    tex = encode_picture_tex(palette, bytes(vanilla.pixels[:256 * 192]), vanilla)
    assert tex.to_bytes() == vanilla.to_bytes()


def test_added_slots_name_their_texture():
    from FF8GameData.menu.magpicture import is_added_slot
    assert pc_picture_file_name(185) == "mag185.TEX" and pc_picture_file_name(255) == "mag255.TEX"
    assert not is_added_slot(184) and not is_added_slot(256)


def test_a_tex_is_written_without_any_template(tmp_path):
    from FF8GameData.menu.magpicture import write_picture_tex
    palette, indices = quantize_picture(_test_image())
    assert write_picture_tex(str(tmp_path), 206, palette, indices)
    tex = TexFile.read(str(tmp_path / "mag206.TEX"))
    assert (tex.width, tex.height, tex.palette_entries) == (256, 256, 256)
    assert bytes(tex.pixels[:256 * 192]) == indices


@pytest.mark.ff8data("extracted_files/menu/mag00.TEX")
def test_default_header_is_the_vanilla_one():
    from FF8GameData.menu.magpicture import DEFAULT_TEX_HEADER
    vanilla = bytearray((MENU / "mag00.TEX").read_bytes()[:240])
    vanilla[0x60:0x64] = bytes(4)  # runtime pointers the original tool left in the header
    vanilla[0xD8:0xDC] = bytes(4)
    assert DEFAULT_TEX_HEADER == bytes(vanilla)
