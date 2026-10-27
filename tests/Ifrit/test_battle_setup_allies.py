"""The shared battle setup (every battle preview): without an encounter, two allies stand side by side
in the battle formation facing the same way, not face to face; an enemy still faces the party. Who
stands where is picked in the setup's panel, among the loaded files."""
import math
import sys
from pathlib import Path

import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[2]
BODY = "extracted_files/battle/d0c000.dat"
ZELL = "extracted_files/battle/d1c003.dat"
IRVINE = "extracted_files/battle/d2c006.dat"
SOLDIER = "extracted_files/battle/c0m071.dat"


@pytest.fixture
def setup():
    QApplication.instance() or QApplication(sys.argv)
    from Ifrit.ifritmanager import IfritManager
    from Ifrit.IfritCameraSeq.battlepreview import BattlePreviewSetup
    manager = IfritManager(str(ROOT / "FF8GameData"))
    manager.init_from_file(str(ROOT / BODY))
    setup = BattlePreviewSetup(manager)
    yield setup
    setup.close()


def _pick(combo, key):
    from Ifrit.IfritCameraSeq.battlecast import index_of
    index = index_of(combo, key)
    assert index >= 0, f"{key} not offered"
    combo.setCurrentIndex(index)


@pytest.mark.ff8data(BODY, ZELL, IRVINE)
def test_party_caster_and_party_target_side_by_side(setup):
    from Ifrit.IfritCameraSeq.battlepreview import PARTY_FORMATIONS
    setup.set_model_paths(lambda: [str(ROOT / BODY), str(ROOT / ZELL)])
    cast = setup.cast
    assert cast.party_members()[0][0] == str(ROOT / BODY)            # the model itself, in the party
    assert cast.party_members()[1][0] == str(ROOT / ZELL)            # a loaded character fills the next slot
    cast.role_combo.setCurrentIndex(0)
    _pick(cast.target_combo, ("party", 1))
    context = setup.build()
    formation = PARTY_FORMATIONS[2]                                  # a party of the two loaded characters
    np.testing.assert_allclose(context.target.position, np.subtract(formation[1], formation[0]))
    assert context.target.yaw == context.caster.yaw == 0.            # both face the enemies
    assert "side by side" in setup.status.text()

    setup.set_model_paths(lambda: [str(ROOT / BODY), str(ROOT / ZELL), str(ROOT / IRVINE)])
    context = setup.build()                                          # the formation follows the party
    np.testing.assert_allclose(context.target.position, np.subtract(PARTY_FORMATIONS[3][1], PARTY_FORMATIONS[3][0]))


@pytest.mark.ff8data(BODY, SOLDIER)
def test_enemy_target_still_faces_the_party(setup):
    setup.set_model_paths(lambda: [str(ROOT / BODY), str(ROOT / SOLDIER)])
    cast = setup.cast
    cast.role_combo.setCurrentIndex(0)
    _pick(cast.target_combo, ("monster", str(ROOT / SOLDIER)))
    context = setup.build()
    assert context.target.yaw == pytest.approx(math.pi) and context.caster.yaw == 0.
    assert context.target.position == tuple(spin.value() for spin in setup.position)
    assert setup.opponent is not None                               # the soldier's model stands there


@pytest.mark.ff8data(BODY)
def test_no_character_loaded_says_so(setup):
    setup.cast.main_manager = None                                   # a host with no character of its own
    setup.set_model_paths(lambda: [])
    assert not setup.cast.message.isHidden()
    assert "open character .dat files" in setup.cast.message.text()
