"""The shared battle preview setup (Fujin, Ifrit Camera / Seq, SolomonRing, Watts): without an
encounter, two allies stand side by side in the battle formation facing the same way, not face to
face; an enemy still faces the party."""
import math
import sys
from pathlib import Path

import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[2]
BODY = "extracted_files/battle/d0c000.dat"


@pytest.fixture(scope="module")
def setup():
    QApplication.instance() or QApplication(sys.argv)
    from Ifrit.ifritmanager import IfritManager
    from Ifrit.IfritCameraSeq.battlepreview import BattlePreviewSetup
    manager = IfritManager(str(ROOT / "FF8GameData"))
    manager.init_from_file(str(ROOT / BODY))
    return BattlePreviewSetup(manager)


@pytest.mark.ff8data(BODY)
def test_party_caster_and_party_target_side_by_side(setup):
    from Ifrit.IfritCameraSeq.battlepreview import PARTY_FORMATIONS
    setup.role.setCurrentIndex(0)
    setup.party_size.setValue(3)
    setup.caster_slot.setValue(0)
    setup.target_slot.setValue(1)
    context = setup.build()
    formation = PARTY_FORMATIONS[3]
    expected = np.subtract(formation[1], formation[0])
    np.testing.assert_allclose(context.target.position, expected)
    assert context.target.yaw == context.caster.yaw == 0.          # both face the enemies
    assert "side by side" in setup.status.text()
    setup.party_size.setValue(2)                                    # the formation follows the size
    context = setup.build()
    np.testing.assert_allclose(context.target.position, np.subtract(PARTY_FORMATIONS[2][1], PARTY_FORMATIONS[2][0]))


@pytest.mark.ff8data(BODY)
def test_enemy_target_still_faces_the_party(setup):
    setup.role.setCurrentIndex(0)
    setup.caster_slot.setValue(0)
    setup.target_slot.setValue(3)
    context = setup.build()
    assert context.target.yaw == pytest.approx(math.pi) and context.caster.yaw == 0.
    assert context.target.position == tuple(spin.value() for spin in setup.position)
    setup.target_slot.setValue(0)                                   # casting on itself
    context = setup.build()
    assert context.target is context.caster
