"""A battle model face picks its texture by its CLUT word (tex_id_1 = y << 6 | x / 16), one
palette row per texture. c0m121 (Ultimecia) uses rows 224-228: 0x3800 ... 0x3900. The viewer used
to key faces on the word's low byte only, and 0x3800 / 0x3900 both give 0x00, so the wings (row 228,
texture 4) were drawn with the body texture (row 224, texture 0). 14 vanilla monsters had this.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication([])

from Ifrit.ifritmanager import IfritManager
from Ifrit.Ifrit3D.ff8openwidget import FF8OpenGLWidget

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ULTIMECIA = os.path.join(REPO, "extracted_files", "battle", "c0m121.dat")

pytestmark = pytest.mark.skipif(not os.path.isfile(ULTIMECIA), reason="c0m121.dat not available")


def test_each_clut_row_gets_its_own_texture():
    mgr = IfritManager("FF8GameData")
    mgr.init_from_file(ULTIMECIA)
    geo = mgr.enemy.geometry_data
    tex_ids = ([tex for _i, _uv, tex, _bias in geo.get_triangles_with_uv()] +
               [tex for _i, _uv, tex, _bias in geo.get_quads_with_uv()])
    assert sorted(set(tex_ids)) == [0x3800, 0x3840, 0x3880, 0x38C0, 0x3900]

    # the viewer's id -> texture map: one texture each, row 228 on the last one
    tex_map = FF8OpenGLWidget._rank_texture_map(tex_ids, len(mgr.texture_data))
    assert tex_map == {0x3800: 0, 0x3840: 1, 0x3880: 2, 0x38C0: 3, 0x3900: 4}
