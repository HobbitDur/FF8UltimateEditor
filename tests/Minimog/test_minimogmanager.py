"""
Tests for Minimog (icon.sp1 menu icon UV table editor).

icon.sp1 is {u32 icon count, u32 directory[count] = {u16 offset from file
start, u16 quad count}, 8-byte quads}. A small synthetic file is built with
known quads so the tests don't need the original game files.
"""
import struct

import pytest

from Minimog.minimogmanager import MinimogManager, Sp1Icon, Sp1Quad, CLUT_BASE


def pack_quad(u, v, clut, abe, unknown_bits, tpage, width, dx, height, dy):
    dword0 = (u | (v << 8) | (clut << 16) | (abe << 27)
              | (unknown_bits << 28) | (tpage << 30))
    return struct.pack("<I", dword0) + struct.pack("<BbBb", width, dx, height, dy)


def build_sp1(icon_quads):
    """Build an sp1 file from a list of per-icon quad-bytes lists."""
    directory_end = 4 + 4 * len(icon_quads)
    directory = bytearray()
    quad_block = bytearray()
    for quads in icon_quads:
        directory += struct.pack("<HH", directory_end + len(quad_block), len(quads))
        for quad in quads:
            quad_block += quad
    return struct.pack("<I", len(icon_quads)) + bytes(directory) + bytes(quad_block)


@pytest.fixture
def sp1_file(tmp_path):
    """icon.sp1 with 3 icons: 1 quad, 2 quads, 1 quad with every flag set."""
    icon_quads = [
        [pack_quad(u=208, v=0, clut=160, abe=0, unknown_bits=0, tpage=3,
                   width=24, dx=0, height=16, dy=0)],
        [pack_quad(u=0, v=32, clut=32, abe=0, unknown_bits=0, tpage=0,
                   width=16, dx=-4, height=8, dy=2),
         pack_quad(u=16, v=32, clut=32, abe=0, unknown_bits=0, tpage=0,
                   width=16, dx=12, height=8, dy=2)],
        [pack_quad(u=255, v=255, clut=0x7FF, abe=1, unknown_bits=3, tpage=2,
                   width=255, dx=-128, height=255, dy=127)],
    ]
    data = build_sp1(icon_quads)
    file_path = tmp_path / "icon.sp1"
    file_path.write_bytes(data)
    return file_path, icon_quads


class TestSp1Quad:
    def test_dword0_field_decode(self):
        quad = Sp1Quad.from_bytes(pack_quad(u=208, v=7, clut=160, abe=0, unknown_bits=0,
                                            tpage=3, width=24, dx=0, height=16, dy=0))
        assert quad.u == 208
        assert quad.v == 7
        assert quad.clut == 160
        assert quad.primitive_clut == CLUT_BASE + 160
        assert quad.palette_index == 2  # 160 >> 6
        assert quad.semi_transparent is False
        assert quad.texture_page == 3

    def test_dword1_signed_offsets(self):
        quad = Sp1Quad.from_bytes(pack_quad(u=0, v=0, clut=0, abe=0, unknown_bits=0,
                                            tpage=0, width=200, dx=-16, height=100, dy=-1))
        assert quad.width == 200
        assert quad.dx == -16
        assert quad.height == 100
        assert quad.dy == -1

    def test_all_bits_roundtrip(self):
        raw = pack_quad(u=255, v=255, clut=0x7FF, abe=1, unknown_bits=3, tpage=2,
                        width=255, dx=-128, height=255, dy=127)
        quad = Sp1Quad.from_bytes(raw)
        assert quad.semi_transparent is True
        assert quad.unknown_bits == 3  # bits 28-29 preserved even though unused
        assert quad.to_bytes() == raw

    def test_to_bytes_known_value(self):
        quad = Sp1Quad(u=0x12, v=0x34, clut=0x56, semi_transparent=False, texture_page=1,
                       width=8, dx=1, height=9, dy=-2)
        dword0 = 0x12 | (0x34 << 8) | (0x56 << 16) | (1 << 30)
        assert quad.to_bytes() == struct.pack("<I", dword0) + struct.pack("<BbBb", 8, 1, 9, -2)


class TestMinimogManager:
    def test_load_file(self, sp1_file):
        file_path, icon_quads = sp1_file
        manager = MinimogManager()
        manager.load_file(str(file_path))
        assert len(manager.icons) == 3
        assert [len(icon.quads) for icon in manager.icons] == [1, 2, 1]
        assert manager.icons[1].quads[0].dx == -4
        assert manager.icons[1].quads[1].dx == 12

    def test_save_without_modification_is_identical(self, sp1_file, tmp_path):
        file_path, _ = sp1_file
        manager = MinimogManager()
        manager.load_file(str(file_path))
        saved = tmp_path / "saved_icon.sp1"
        manager.save_file(str(saved))
        assert saved.read_bytes() == file_path.read_bytes()

    def test_modify_and_save(self, sp1_file, tmp_path):
        file_path, _ = sp1_file
        manager = MinimogManager()
        manager.load_file(str(file_path))
        manager.icons[0].quads[0].u = 100
        manager.icons[0].quads[0].dy = -8
        saved = tmp_path / "saved_icon.sp1"
        manager.save_file(str(saved))

        reloaded = MinimogManager()
        reloaded.load_file(str(saved))
        assert reloaded.icons[0].quads[0].u == 100
        assert reloaded.icons[0].quads[0].dy == -8
        # untouched neighbours survive byte-perfect
        assert reloaded.icons[2].quads[0].to_bytes() == manager.icons[2].quads[0].to_bytes()

    def test_add_quad_rebuilds_directory(self, sp1_file, tmp_path):
        file_path, _ = sp1_file
        manager = MinimogManager()
        manager.load_file(str(file_path))
        manager.add_quad(0, Sp1Quad(u=1, v=2, clut=32, width=10, height=11, dx=3, dy=4))
        saved = tmp_path / "saved_icon.sp1"
        manager.save_file(str(saved))

        data = saved.read_bytes()
        directory_end = 4 + 4 * 3
        # icon 0 now holds 2 quads, later icons are pushed 8 bytes further
        offsets = [struct.unpack_from("<HH", data, 4 + 4 * i) for i in range(3)]
        assert offsets[0] == (directory_end, 2)
        assert offsets[1] == (directory_end + 2 * 8, 2)
        assert offsets[2] == (directory_end + 4 * 8, 1)

        reloaded = MinimogManager()
        reloaded.load_file(str(saved))
        assert len(reloaded.icons[0].quads) == 2
        assert reloaded.icons[0].quads[1].width == 10
        assert reloaded.icons[1].quads[0].u == 0  # neighbours unchanged

    def test_remove_quad(self, sp1_file, tmp_path):
        file_path, _ = sp1_file
        manager = MinimogManager()
        manager.load_file(str(file_path))
        removed = manager.remove_quad(1, 0)
        assert removed.dx == -4
        saved = tmp_path / "saved_icon.sp1"
        manager.save_file(str(saved))

        reloaded = MinimogManager()
        reloaded.load_file(str(saved))
        assert len(reloaded.icons[1].quads) == 1
        assert reloaded.icons[1].quads[0].dx == 12

    def test_offset_overflow_rejected(self):
        manager = MinimogManager()
        # 8192 single-quad icons push quad offsets past the u16 directory limit
        manager.icons = [Sp1Icon(i, [Sp1Quad(width=1, height=1)]) for i in range(8192)]
        with pytest.raises(ValueError, match="UInt16"):
            manager.to_bytes()

    def test_truncated_file_rejected(self, tmp_path):
        file_path = tmp_path / "bad.sp1"
        file_path.write_bytes(struct.pack("<I", 50) + b"\x00" * 8)
        manager = MinimogManager()
        with pytest.raises(ValueError, match="too small"):
            manager.load_file(str(file_path))

    def test_button_icons_flagged(self):
        assert Sp1Icon(128).is_button_icon
        assert Sp1Icon(139).is_button_icon
        assert "L2" in Sp1Icon(128).name
        assert "Start" in Sp1Icon(139).name
        assert not Sp1Icon(127).is_button_icon
        assert not Sp1Icon(140).is_button_icon

    def test_bounding_box(self):
        icon = Sp1Icon(0, [Sp1Quad(width=16, height=8, dx=-4, dy=2),
                           Sp1Quad(width=16, height=8, dx=12, dy=2)])
        assert icon.bounding_box() == (-4, 2, 28, 10)

    def test_anchored_bounding_box_includes_origin_with_zero_pad(self):
        # pad=0 collapses to "just widen bounding_box() to cover (0, 0)"
        icon = Sp1Icon(0, [Sp1Quad(width=8, height=8, dx=10, dy=10)])
        assert icon.bounding_box() == (10, 10, 18, 18)
        assert icon.anchored_bounding_box(pad=0) == (0, 0, 18, 18)

    def test_anchored_bounding_box_starts_icon_sized_at_zero_offset(self):
        # the main ask: no offset should mean no extra room beyond the pad
        icon = Sp1Icon(0, [Sp1Quad(width=8, height=8, dx=0, dy=0)])
        assert icon.anchored_bounding_box(pad=4) == (-4, -4, 12, 12)

    def test_anchored_bounding_box_left_edge_is_stable_for_positive_dx(self):
        # as dx grows (staying on the same side of 0), the near edge - and so
        # the crosshair's pixel position - must not move, only the far edge
        # grows to fit the quad further from the origin
        small_offset = Sp1Icon(0, [Sp1Quad(width=8, height=8, dx=4, dy=0)])
        large_offset = Sp1Icon(0, [Sp1Quad(width=8, height=8, dx=20, dy=0)])
        left_a, top_a, right_a, bottom_a = small_offset.anchored_bounding_box()
        left_b, top_b, right_b, bottom_b = large_offset.anchored_bounding_box()
        assert left_a == left_b == -4   # pinned at -pad, unaffected by dx growing
        assert top_a == top_b == -4     # unaffected by an X-only change
        assert right_b > right_a        # only the far edge grows with dx

    def test_anchored_bounding_box_extends_left_for_negative_dx(self):
        # crossing to the other side of the origin does need to grow the near
        # edge too - there's no pre-reserved slack to avoid it - but it's
        # still never clipped
        icon = Sp1Icon(0, [Sp1Quad(width=8, height=8, dx=-52, dy=0)])
        left, top, right, bottom = icon.anchored_bounding_box()
        assert left == -56  # bounding_box()'s min_x (-52) - the default pad (4)

    def test_anchored_bounding_box_noop_when_already_covers_origin(self):
        icon = Sp1Icon(0, [Sp1Quad(width=8, height=8, dx=-2, dy=-2)])
        assert icon.anchored_bounding_box(pad=0) == icon.bounding_box() == (-2, -2, 6, 6)


def make_solid_tex(color=(200, 50, 50, 254), size=64):
    """A synthetic TexFile: one palette, every pixel index 1 = `color` (r, g, b, a)."""
    from FF8GameData.tex.texfile import TexFile

    r, g, b, a = color
    palette_entries = 16
    raw_palette = bytearray(palette_entries * 4)
    raw_palette[4:8] = bytes((b, g, r, a))  # on-disk order is B,G,R,A - index 1
    pixels = bytearray([1]) * (size * size)
    return TexFile(raw_header=bytes(240), raw_palette=bytes(raw_palette), pixels=pixels,
                   num_palettes=1, palette_entries=palette_entries, bpp=4,
                   width=size, height=size)


class TestRenderSheet:
    def test_places_icon_at_its_grid_cell(self):
        manager = MinimogManager()
        manager.icons = [Sp1Icon(0, []), Sp1Icon(1, [Sp1Quad(u=0, v=0, clut=64, width=8, height=8)])]
        tex_file = make_solid_tex()

        sheet = manager.render_sheet(tex_file, scale=1, columns=20, cell=40)
        assert sheet.size == (20 * 40, 40)  # 2 icons still round up to a single row
        assert sheet.getpixel((5, 5))[:3] == (30, 30, 30)  # icon 0's cell: empty
        assert sheet.getpixel((45, 5))[:3] == (200, 50, 50)  # icon 1's cell (40..80): the quad

    def test_oversized_quad_is_clipped_to_its_own_cell(self):
        # a quad wider than `cell` must not bleed into the next icon's cell
        manager = MinimogManager()
        manager.icons = [Sp1Icon(0, [Sp1Quad(u=0, v=0, clut=64, width=50, height=10)])]
        tex_file = make_solid_tex()

        sheet = manager.render_sheet(tex_file, scale=1, columns=20, cell=40)
        assert sheet.getpixel((35, 5))[:3] == (200, 50, 50)  # inside icon 0's cell
        assert sheet.getpixel((45, 5))[:3] == (30, 30, 30), \
            "the quad's extra 10px must be clipped, not spill into the next cell"


def make_multi_palette_tex(colors=((200, 50, 50, 254), (50, 50, 200, 254)), size=64):
    """A synthetic TexFile with one palette per given (r, g, b, a) color, every
    pixel index 1 - lets a test point different UV rectangles at different
    palettes to check render_texture_true_colors()'s per-region resolution."""
    from FF8GameData.tex.texfile import TexFile

    palette_entries = 16
    raw_palette = bytearray(len(colors) * palette_entries * 4)
    for p, (r, g, b, a) in enumerate(colors):
        base = p * palette_entries * 4
        raw_palette[base + 4:base + 8] = bytes((b, g, r, a))  # on-disk B,G,R,A, index 1
    pixels = bytearray([1]) * (size * size)
    return TexFile(raw_header=bytes(240), raw_palette=bytes(raw_palette), pixels=pixels,
                   num_palettes=len(colors), palette_entries=palette_entries, bpp=4,
                   width=size, height=size)


class TestRenderTextureTrueColors:
    def test_matches_the_tex_file_s_native_size(self):
        manager = MinimogManager()
        manager.icons = [Sp1Icon(0, [Sp1Quad(u=0, v=0, clut=0, width=8, height=8)])]
        tex_file = make_multi_palette_tex()

        image = manager.render_texture_true_colors(tex_file)

        assert image.size == (tex_file.width, tex_file.height)

    def test_each_region_uses_its_own_icon_s_palette(self):
        manager = MinimogManager()
        manager.icons = [
            Sp1Icon(0, [Sp1Quad(u=0, v=0, clut=0, width=8, height=8)]),    # palette 0 = red
            Sp1Icon(1, [Sp1Quad(u=16, v=0, clut=64, width=8, height=8)]),  # palette 1 = blue
        ]
        tex_file = make_multi_palette_tex()

        image = manager.render_texture_true_colors(tex_file)

        assert image.getpixel((4, 4))[:3] == (200, 50, 50)
        assert image.getpixel((20, 4))[:3] == (50, 50, 200)

    def test_pixels_no_icon_claims_are_left_transparent(self):
        manager = MinimogManager()
        manager.icons = [Sp1Icon(0, [Sp1Quad(u=0, v=0, clut=0, width=8, height=8)])]
        tex_file = make_multi_palette_tex()

        image = manager.render_texture_true_colors(tex_file)

        assert image.getpixel((40, 40))[3] == 0, "far outside the only quad, nothing claims it"

    def test_a_rectangle_shared_by_two_icons_resolves_to_the_lower_icon_id(self):
        manager = MinimogManager()
        manager.icons = [
            Sp1Icon(0, [Sp1Quad(u=0, v=0, clut=0, width=8, height=8)]),   # red, claims (0,0)-(8,8) first
            Sp1Icon(5, [Sp1Quad(u=0, v=0, clut=64, width=8, height=8)]),  # blue, same rectangle, higher id
        ]
        tex_file = make_multi_palette_tex()

        image = manager.render_texture_true_colors(tex_file)

        assert image.getpixel((4, 4))[:3] == (200, 50, 50), \
            "the lower icon id must win a rectangle shared with a higher one"
