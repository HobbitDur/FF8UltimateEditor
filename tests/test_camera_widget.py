"""Ifrit's Camera tab (Ifrit/IfritCameraSeq) on the shared keyframe grid (Common/cameracollectionwidget,
the one Fujin and Alexander use): an edit writes into the monster's section 6 at once and tells
the host, a structural edit rebuilds the grid, and the mode/block settings are the shared lists."""
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication, QSpinBox

from FF8GameData.dat.cameracollection import parse_camera_collection

ROOT = Path(__file__).resolve().parents[1]
SOLDIER = "extracted_files/battle/c0m071.dat"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication(sys.argv)


def _camera_tab(path):
    from Ifrit.ifritmanager import IfritManager
    from Ifrit.IfritCameraSeq.ifritcameraseqwidget import IfritCameraSeqWidget
    manager = IfritManager(str(ROOT / "FF8GameData"))
    manager.init_from_file(str(ROOT / path))
    tab = IfritCameraSeqWidget(manager)
    tab.load_file()
    return manager, tab


@pytest.mark.ff8data(SOLDIER)
def test_ifrit_camera_tab_uses_the_shared_grid(app):
    from Common.cameracollectionwidget import CameraCollectionWidget
    from Common.cameramodecombo import CameraModeCombo
    manager, tab = _camera_tab(SOLDIER)
    edits = []
    tab.data_edited.connect(lambda: edits.append(1))
    grid = tab._collection_widget
    assert isinstance(grid, CameraCollectionWidget) and grid._structure_edits
    assert grid.expanded_set_indices() == [0]                      # the monster's one set, open
    assert "set(s)" in tab.summary_label.text()

    # A value edit patches the section bytes the file writer saves, and tells the host
    spin = next(s for s in grid.findChildren(QSpinBox) if s.maximum() == 32767)
    spin.setValue(spin.value() + 7)
    assert edits and manager.enemy.section_raw_data[6] == tab._collection.get_bytes()
    assert grid.findChildren(CameraModeCombo)                         # modes are the named lists

    # A structural edit (a keyframe duplicated) rebuilds the grid on the new bytes
    animation = next(a for a in tab._collection.sets[0].animations if not a.empty)
    before = sum(len(block.frames) for block in animation.blocks)
    from FF8GameData.dat.cameracollection import insert_keyframe
    grid._rebuild(insert_keyframe, 0, animation.slot, 0, 0)
    assert tab._collection_widget is not grid and len(edits) == 2
    rebuilt = parse_camera_collection(manager.enemy.section_raw_data[6])
    again = rebuilt.sets[0].animations[animation.slot]
    assert sum(len(block.frames) for block in again.blocks) == before + 1

    # The raw bytes view follows the edits
    tab.hex_checkbox.setChecked(True)
    tab.show()
    assert tab.hex_view.toPlainText() == bytes(tab._collection.get_bytes()).hex(" ")
    tab.close()
