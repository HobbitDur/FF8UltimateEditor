"""Real-file round-trip test for Minimog (menu/icon.sp1 editor).

Unlike test_minimogmanager.py (which builds a small synthetic icon.sp1), this test
loads the *original* game icon.sp1 from extracted_files/ and checks that loading
then saving it is byte-for-byte lossless. It needs the real file and is skipped
otherwise (see the ff8data marker in the project-root conftest.py).
"""
import pathlib

import pytest

from Minimog.minimogmanager import MinimogManager

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
ICON_SP1 = PROJECT_ROOT / "extracted_files" / "menu" / "icon.sp1"
ICON_TEX = PROJECT_ROOT / "extracted_files" / "menu" / "icon.TEX"


@pytest.mark.ff8data("extracted_files/menu/icon.sp1")
def test_real_icon_sp1_roundtrip_is_lossless(tmp_path):
    """Load the real icon.sp1, save it, and expect identical bytes."""
    manager = MinimogManager()
    manager.load_file(str(ICON_SP1))
    assert len(manager.icons) == 329
    assert all(icon.quads for icon in manager.icons), "vanilla icons all have quads"

    out = tmp_path / "icon.sp1"
    manager.save_file(str(out))

    assert out.read_bytes() == ICON_SP1.read_bytes()


@pytest.mark.ff8data("extracted_files/menu/icon.sp1")
def test_real_icon_sp1_edit_persists(tmp_path):
    """A single quad edit survives save + reload, other icons untouched."""
    manager = MinimogManager()
    manager.load_file(str(ICON_SP1))
    original = [[quad.to_bytes() for quad in icon.quads] for icon in manager.icons]

    manager.icons[1].quads[0].u = 42
    manager.icons[1].quads[0].dy = -5
    manager.add_quad(200)
    out = tmp_path / "icon.sp1"
    manager.save_file(str(out))

    reloaded = MinimogManager()
    reloaded.load_file(str(out))
    assert reloaded.icons[1].quads[0].u == 42
    assert reloaded.icons[1].quads[0].dy == -5
    assert len(reloaded.icons[200].quads) == len(original[200]) + 1
    for icon_id, quads in enumerate(original):
        if icon_id in (1, 200):
            continue
        assert [quad.to_bytes() for quad in reloaded.icons[icon_id].quads] == quads


@pytest.mark.ff8data("extracted_files/menu/icon.sp1", "extracted_files/menu/icon.TEX")
def test_real_icon_render_from_tex():
    """The preview crops real pixels: vanilla icon 1 is a 24x16 opaque sprite."""
    from FF8GameData.tex.texfile import TexFile

    manager = MinimogManager()
    manager.load_file(str(ICON_SP1))
    tex_file = TexFile.read(str(ICON_TEX))

    image = manager.render_icon(1, tex_file)
    assert image is not None
    assert (image.width, image.height) == (24, 16)
    alpha_bytes = image.tobytes()[3::4]
    assert any(alpha_bytes), "icon should not be fully transparent"


@pytest.mark.ff8data("extracted_files/menu/icon.sp1", "extracted_files/menu/icon.TEX")
def test_render_icon_hides_single_quad_offset(tmp_path):
    """render_icon() crops tightly to the quad, so a single-quad icon's dx/dy
    offset has no visible effect: the crop just re-centers on the quad. Icon
    20 (dx=4, dy=0) is a real vanilla example - same output size as if dx
    were 0, since only width/height (not dx/dy) drive the crop size."""
    from FF8GameData.tex.texfile import TexFile

    manager = MinimogManager()
    manager.load_file(str(ICON_SP1))
    tex_file = TexFile.read(str(ICON_TEX))
    quad = manager.icons[20].quads[0]
    assert (quad.dx, quad.dy) == (4, 0)  # a real offset, not a degenerate 0,0 case

    with_offset = manager.render_icon(20, tex_file)
    quad.dx = 0
    without_offset = manager.render_icon(20, tex_file)
    assert with_offset.size == without_offset.size == (quad.width, quad.height)
    assert with_offset.tobytes() == without_offset.tobytes()


@pytest.mark.ff8data("extracted_files/menu/icon.sp1", "extracted_files/menu/icon.TEX")
def test_render_icon_anchored_makes_single_quad_offset_visible():
    """render_icon_anchored() keeps the draw cursor (0,0) in frame, so icon
    20's real dx=4 offset now visibly shifts the sprite away from a fixed
    crosshair, and the canvas grows (to the right) to keep both in frame."""
    from FF8GameData.tex.texfile import TexFile

    manager = MinimogManager()
    manager.load_file(str(ICON_SP1))
    tex_file = TexFile.read(str(ICON_TEX))
    quad = manager.icons[20].quads[0]
    assert (quad.dx, quad.dy) == (4, 0)

    anchored = manager.render_icon_anchored(20, tex_file)
    assert anchored.size != (quad.width, quad.height), \
        "anchored render must differ in size from the tight crop to prove the offset is visible"

    origin_x, origin_y = 4, 4  # default pad; icon 20's dx/dy stay >= 0 so left/top pin at -pad
    assert anchored.getpixel((origin_x, origin_y))[:3] == (255, 48, 48)

    # the quad itself starts dx pixels right of the crosshair
    quad_pixel = anchored.getpixel((origin_x + quad.dx + 1, origin_y + quad.dy + 1))
    assert quad_pixel[3] != 0, "quad content should be opaque just inside its own rectangle"


@pytest.mark.ff8data("extracted_files/menu/icon.sp1", "extracted_files/menu/icon.TEX")
def test_render_icon_anchored_crosshair_is_stable_across_offset_edits():
    """As long as dx stays >= 0 (as it does here, 4 then 20), the frame's
    near edge is already pinned at -pad because it already covered the
    origin - so nudging dx must not move the crosshair pixel or shift
    anything already drawn, only grow the canvas on the right to fit the
    quad further away, matching how the real engine cursor doesn't move
    just because a glyph's offset changed."""
    from FF8GameData.tex.texfile import TexFile

    manager = MinimogManager()
    manager.load_file(str(ICON_SP1))
    tex_file = TexFile.read(str(ICON_TEX))
    quad = manager.icons[20].quads[0]
    origin_x, origin_y = 4, 4  # default pad; icon 20's dx/dy stay >= 0 so left/top pin at -pad
    crosshair_color = (255, 48, 48)

    quad.dx = 4
    small = manager.render_icon_anchored(20, tex_file)
    quad.dx = 20
    large = manager.render_icon_anchored(20, tex_file)

    assert small.getpixel((origin_x, origin_y))[:3] == crosshair_color
    assert large.getpixel((origin_x, origin_y))[:3] == crosshair_color
    assert small.height == large.height, "Y extent is untouched by an X-only edit"
    assert large.width > small.width, "canvas only grows to the right to fit the larger offset"

    # the icon actually moved: opaque at the small offset's landing spot only in `small`,
    # opaque at the large offset's landing spot only in `large`
    small_spot = (origin_x + 4 + 1, origin_y + 1)
    large_spot = (origin_x + 20 + 1, origin_y + 1)
    assert small.getpixel(small_spot)[3] != 0
    assert large.getpixel(small_spot)[3] == 0, "icon left its old spot, it doesn't leave a trail"
    assert large.getpixel(large_spot)[3] != 0


@pytest.mark.ff8data("extracted_files/menu/icon.sp1", "extracted_files/menu/icon.TEX")
def test_render_sheet_places_known_icon_in_its_cell():
    """The contact sheet lays out icon id N at grid cell (N % columns, N // columns)
    and covers all 329 icons. Icon 20 ("BULLET") should land inside its own cell."""
    from FF8GameData.tex.texfile import TexFile

    manager = MinimogManager()
    manager.load_file(str(ICON_SP1))
    tex_file = TexFile.read(str(ICON_TEX))

    sheet = manager.render_sheet(tex_file, scale=1, columns=20, cell=40)
    assert sheet.size == (20 * 40, ((329 + 19) // 20) * 40)

    cell_x, cell_y = (20 % 20) * 40, (20 // 20) * 40
    cell = sheet.crop((cell_x, cell_y, cell_x + 40, cell_y + 40))
    alpha_bytes = cell.tobytes()[3::4]
    assert any(alpha_bytes), "icon 20's cell should contain visible pixels"

