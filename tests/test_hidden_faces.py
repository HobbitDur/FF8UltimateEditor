"""Some battle model faces carry a per-face "hide" bit (TPage word & 0xFE00) that the real
renderer also skips - see GeometryTriangle/GeometryQuad.is_hidden(). Most files never set it, but
d0w006.dat (Lion Heart, Squall's ultimate weapon) uses it on 65% of its triangles and 22% of its
quads - unlike every other Squall gunblade (d0w000-d0w005, all 0%) - so the visible-only mesh
looks broken (chunks missing) in the static viewer, which has no way to simulate whatever
dynamically reveals those faces in-game. Ifrit3D can show them anyway via a "Show hidden faces"
toggle (Ifrit3D/ifrit3dwidget.py), on by default so a file opens looking whole.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication([])

from Ifrit.ifritmanager import IfritManager
from Ifrit.Ifrit3D.ifrit3dwidget import Ifrit3DWidget

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BATTLE = os.path.join(REPO, "extracted_files", "battle")
LION_HEART = os.path.join(BATTLE, "d0w006.dat")     # 65%/22% hidden
REVOLVER = os.path.join(BATTLE, "d0w000.dat")        # 0% hidden, sanity control

pytestmark = pytest.mark.skipif(
    not (os.path.isfile(LION_HEART) and os.path.isfile(REVOLVER)),
    reason="d0w006.dat / d0w000.dat not available")


def test_geometry_getters_include_hidden_on_request():
    mgr = IfritManager("FF8GameData")
    mgr.init_from_file(LION_HEART)
    geo = mgr.enemy.geometry_data
    assert len(geo.get_triangles(include_hidden=False)) == 24
    assert len(geo.get_triangles(include_hidden=True)) == 68
    assert len(geo.get_quads(include_hidden=False)) == 76
    assert len(geo.get_quads(include_hidden=True)) == 97
    # default (no argument) stays the old, conservative behavior - other callers
    # (gltf export, Watts composite model) are unaffected by this toggle.
    assert len(geo.get_triangles()) == 24
    assert len(geo.get_quads()) == 76


def test_viewer_shows_hidden_faces_by_default():
    mgr = IfritManager("FF8GameData")
    mgr.init_from_file(LION_HEART)
    w3d = Ifrit3DWidget(mgr, show_controls=True)
    assert w3d._show_hidden_faces is True
    assert w3d.cb_hidden_faces.isChecked() is True
    w3d.load_file()
    assert len(w3d.gl_widget.triangles) == 68
    assert len(w3d.gl_widget.quads) == 97


def test_toggle_off_shrinks_the_mesh_and_back_on_restores_it():
    mgr = IfritManager("FF8GameData")
    mgr.init_from_file(LION_HEART)
    w3d = Ifrit3DWidget(mgr, show_controls=True)
    w3d.load_file()

    w3d.cb_hidden_faces.setChecked(False)
    assert len(w3d.gl_widget.triangles) == 24
    assert len(w3d.gl_widget.quads) == 76

    w3d.cb_hidden_faces.setChecked(True)
    assert len(w3d.gl_widget.triangles) == 68
    assert len(w3d.gl_widget.quads) == 97


def test_files_with_no_hidden_faces_are_unaffected_by_the_toggle():
    mgr = IfritManager("FF8GameData")
    mgr.init_from_file(REVOLVER)
    w3d = Ifrit3DWidget(mgr, show_controls=True)
    w3d.load_file()
    on = (len(w3d.gl_widget.triangles), len(w3d.gl_widget.quads))
    w3d.cb_hidden_faces.setChecked(False)
    off = (len(w3d.gl_widget.triangles), len(w3d.gl_widget.quads))
    assert on == off
