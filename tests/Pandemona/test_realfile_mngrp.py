"""Real-file round-trip test for Pandemona (refine editor, m00x data inside menu/mngrp.bin).

Loads the original mngrp.bin/mngrphd.bin pair from extracted_files/. Saving repacks the
refine + text sections and recomputes text offsets, so the first save is not guaranteed
byte-identical to the original; what must hold is that the parsed refine data survives a
save + reload and that a second round-trip is byte-stable (idempotent).

Needs the real files, skipped otherwise (ff8data marker).
"""
import pathlib
import shutil

import pytest

from FF8GameData.gamedata import GameData
from Pandemona.pandemonamanager import PandemonaManager

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MENU_DIR = PROJECT_ROOT / "extracted_files" / "menu"
MNGRP = MENU_DIR / "mngrp.bin"
MNGRPHD = MENU_DIR / "mngrphd.bin"


@pytest.fixture(scope="module")
def game_data():
    return GameData(str(PROJECT_ROOT / "FF8GameData"))


def _refine_snapshot(manager):
    return [[(e.text, e.element_in_id, e.amount_required, e.element_out_id, e.amount_received, e.unk)
             for e in section.entries]
            for section in manager.refine_sections]


@pytest.mark.ff8data("extracted_files/menu/mngrp.bin", "extracted_files/menu/mngrphd.bin")
def test_real_mngrp_refine_survives_reload(game_data, tmp_path):
    work_mngrp = tmp_path / "mngrp.bin"
    work_mngrphd = tmp_path / "mngrphd.bin"
    shutil.copy(MNGRP, work_mngrp)
    shutil.copy(MNGRPHD, work_mngrphd)

    manager = PandemonaManager(game_data)
    manager.load_file(str(work_mngrp), str(work_mngrphd))
    assert manager.refine_sections, "no refine sections parsed from the real file"
    before = _refine_snapshot(manager)

    manager.save_file()

    reloaded = PandemonaManager(game_data)
    reloaded.load_file(str(work_mngrp), str(work_mngrphd))
    assert _refine_snapshot(reloaded) == before


@pytest.mark.ff8data("extracted_files/menu/mngrp.bin", "extracted_files/menu/mngrphd.bin")
def test_real_mngrp_roundtrip_is_idempotent(game_data, tmp_path):
    work_mngrp = tmp_path / "mngrp.bin"
    work_mngrphd = tmp_path / "mngrphd.bin"
    shutil.copy(MNGRP, work_mngrp)
    shutil.copy(MNGRPHD, work_mngrphd)

    manager = PandemonaManager(game_data)
    manager.load_file(str(work_mngrp), str(work_mngrphd))
    manager.save_file()  # normalise
    after_first = work_mngrp.read_bytes(), work_mngrphd.read_bytes()

    manager2 = PandemonaManager(game_data)
    manager2.load_file(str(work_mngrp), str(work_mngrphd))
    manager2.save_file()
    after_second = work_mngrp.read_bytes(), work_mngrphd.read_bytes()

    assert after_first == after_second


@pytest.mark.ff8data("extracted_files/menu/mngrp.bin", "extracted_files/menu/mngrphd.bin")
def test_real_mngrp_edit_persists(game_data, tmp_path):
    work_mngrp = tmp_path / "mngrp.bin"
    work_mngrphd = tmp_path / "mngrphd.bin"
    shutil.copy(MNGRP, work_mngrp)
    shutil.copy(MNGRPHD, work_mngrphd)

    manager = PandemonaManager(game_data)
    manager.load_file(str(work_mngrp), str(work_mngrphd))
    manager.refine_sections[0].entries[0].amount_received = 7
    manager.save_file()

    reloaded = PandemonaManager(game_data)
    reloaded.load_file(str(work_mngrp), str(work_mngrphd))
    assert reloaded.refine_sections[0].entries[0].amount_received == 7
