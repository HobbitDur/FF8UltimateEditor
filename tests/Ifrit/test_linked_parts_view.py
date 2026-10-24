"""Linked monster parts in the 3D view: Seifer's Gunblade monster must land in his hands.

The Gunblade (c0m082) is the character weapon d6w033 rebuilt as a monster at skeleton scale 195
(Seifer's body is 188, its root track divided by the same ratio). Posed on monster Seifer
(c0m086) it must sit exactly where d6w033 sits on character Seifer (d6c014, same body mesh)."""
import os
import sys

import numpy as np
import pytest

BATTLE = "extracted_files/battle"


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


def _manager(name):
    path = os.path.join(BATTLE, f"{name}.dat")
    if not os.path.isfile(path):
        pytest.skip("needs the game's battle files in extracted_files/battle")
    from Ifrit.ifritmanager import IfritManager
    manager = IfritManager("FF8GameData")
    manager.init_from_file(os.path.abspath(path))
    manager._ensure_matrices()
    return manager


def test_gunblade_monster_sits_where_the_character_weapon_does(qapp):
    from Ifrit.Ifrit3D.ifrit3dwidget import Ifrit3DWidget
    character = Ifrit3DWidget(_manager("d6c014"), show_controls=False)
    character.load_file()
    weapon = np.array(character._current_attached_verts(_manager("d6w033"), None))

    monster = Ifrit3DWidget(_manager("c0m086"), show_controls=False)
    monster.load_file()
    gunblade = _manager("c0m082")
    monster.set_linked_parts([(gunblade, {0: 0})])
    assert monster._attached_models()[0][1] == 0          # body anim 0 -> part anim 0
    part = np.array(monster._current_attached_verts(gunblade, 0))

    # same blade (same vertex order), same place: 0.006 apart on an 8-unit blade. Without each
    # model's own skeleton scale the Gunblade drifts by 0.4.
    assert part.shape == weapon.shape
    assert np.abs(part - weapon).max() < 0.02
    character.deleteLater()
    monster.deleteLater()
