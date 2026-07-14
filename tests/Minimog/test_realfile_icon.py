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
