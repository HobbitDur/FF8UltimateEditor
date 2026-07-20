"""The 3D viewer's per-frame backface cull used to run a Python loop calling _should_cull_backface
(a numpy cross-product + dot) on EVERY face, plus rebuild a frozenset-keyed face_count dict, on
EVERY repaint. At ~2600 faces that was 35-45 ms/frame of pure CPU before any GL draw - the real
cause of the "3D viewer lags with heavy models" report (per active model, not per loaded file,
which is why capping panes did nothing). It is now one vectorized numpy pass per paint
(_recompute_cull_masks) over topology cached on set_*_with_uv. These tests pin that the vectorized
mask makes the SAME cull decision as the old per-face code, so the optimization can't silently
change what's drawn.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication([])

import numpy as np

from Ifrit.ifritmanager import IfritManager
from Ifrit.Ifrit3D.ff8openwidget import FF8OpenGLWidget

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BATTLE = os.path.join(REPO, "extracted_files", "battle")


def _loaded_gl(fname):
    mgr = IfritManager("FF8GameData")
    mgr.init_from_file(os.path.join(BATTLE, fname))
    mgr._ensure_matrices()
    en = mgr.enemy
    gl = FF8OpenGLWidget()
    verts = (mgr.get_animated_vertices(0, 0) if en.animation_data.nb_animations
             else en.geometry_data.get_vertices())
    gl.set_vertices(verts)
    gl.set_triangles_with_uv(en.geometry_data.get_triangles_with_uv())
    gl.set_quads_with_uv(en.geometry_data.get_quads_with_uv())
    gl._eye_model = np.array([12.0, 25.0, 130.0])   # an off-axis camera, like an orbit view
    return gl


def _old_decisions(gl, face_list):
    """Reproduce the pre-optimization per-face path exactly."""
    view_dir = gl._view_direction_model()
    out = []
    fc = {}
    for entry in face_list:
        k = frozenset(entry[0]); fc[k] = fc.get(k, 0) + 1
    for entry in face_list:
        verts = [gl.vertices_array[i] for i in entry[0]]
        out.append(bool(gl._should_cull_backface(verts, fc[frozenset(entry[0])], view_dir)))
    return out


@pytest.mark.parametrize("fname", [
    f for f in ("c0m000.dat", "c0m030.dat", "c0m070.dat")
    if os.path.isfile(os.path.join(BATTLE, f))
])
@pytest.mark.parametrize("mode", ["all", "duplicates", "off"])
def test_vectorized_cull_matches_per_face(fname, mode):
    gl = _loaded_gl(fname)
    gl.backface_cull = mode
    gl._recompute_cull_masks()

    for face_list, mask in ((gl.triangles_uv, gl._tri_cull_mask),
                            (gl.quads_uv, gl._quad_cull_mask)):
        if not face_list:
            continue
        old = _old_decisions(gl, face_list)
        new = [bool(x) for x in mask]
        assert new == old, f"{fname} {mode}: {sum(a != b for a, b in zip(old, new))} faces differ"


def test_topology_rebuilt_when_geometry_changes():
    """Merging in a weapon (or reloading) changes the face count; the cached topology must track
    it so the cull mask stays the right length."""
    gl = _loaded_gl("c0m000.dat")
    n0 = len(gl.triangles_uv)
    gl._recompute_cull_masks()
    assert gl._tri_cull_mask is None or len(gl._tri_cull_mask) == n0
    # replace with a different model's geometry
    gl2mgr = IfritManager("FF8GameData"); gl2mgr.init_from_file(os.path.join(BATTLE, "c0m030.dat"))
    gl2mgr._ensure_matrices()
    gl.set_vertices(gl2mgr.get_animated_vertices(0, 0))
    gl.set_triangles_with_uv(gl2mgr.enemy.geometry_data.get_triangles_with_uv())
    gl._eye_model = np.array([0.0, 0.0, 100.0])
    gl._recompute_cull_masks()
    assert len(gl._tri_cull_mask) == len(gl.triangles_uv)
