"""Integration test that drives the REAL 3D preview (not a stub).

Earlier bugs ('NoneType' has no attribute 'position', missing get_skeleton_lines) slipped
through because the unit tests stubbed Ifrit3DWidget. This builds the actual widget,
imports three characters, and previews a camera slot - which constructs a real
Ifrit3DWidget over the composite and runs its load_file(). It cannot check the rendered
pixels, but it exercises every CPU-side path that threw those AttributeErrors.

Needs PyQt + the real character files, so it is marked ff8data and runs offscreen.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pathlib

import pytest

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
BATTLE = PROJECT_ROOT / "extracted_files" / "battle"
PARTY = ["d0c000.dat", "d1c003.dat", "d2c006.dat"]  # Squall, Zell, Irvine


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PyQt6.QtWidgets")
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.mark.ff8data("extracted_files/battle/r0win.dat", *[f"extracted_files/battle/{f}" for f in PARTY])
def test_three_character_preview_renders(qapp, monkeypatch):
    from PyQt6.QtWidgets import QFileDialog, QMessageBox
    from Watts.wattswidget import WattsWidget

    widget = WattsWidget()
    widget.load_file(str(BATTLE / "r0win.dat"))

    files = [str(BATTLE / name) for name in PARTY]
    monkeypatch.setattr(QFileDialog, "getOpenFileNames",
                        staticmethod(lambda *a, **k: (files, "x")))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "critical",
                        staticmethod(lambda *a, **k: pytest.fail(f"import error: {a}")))
    widget._import_character_dat()
    assert len(widget._preview_models) == 3

    # Preview a slot: builds the REAL Ifrit3DWidget over the composite and runs load_file().
    widget._on_preview_requested(widget.manager.camera_collection.sets[0].animations[0])
    panel = widget._preview_panel
    assert panel._view is not None, "the 3D view was not built"
    assert panel._placeholder.isHidden(), \
        "preview fell back to the '3D preview unavailable' placeholder"
    # geometry of all three characters is present
    assert len(panel._gl.vertices) > 1000
    assert len(panel._gl.triangles) > 1000
