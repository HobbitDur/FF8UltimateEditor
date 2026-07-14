"""Real-file round-trip test for ShumiTranslator's text ("all text editor") containers.

ShumiTranslator edits FF8 text in many container types. kernel.bin (FF8_TEXT) is already
covered by tests/test_solomonring_kernel.py via KernelManager, so this test targets a
DIFFERENT container: the menu text packed inside mngrp.bin, loaded through ShumiTranslator's
own MngrpManager. That file holds the .msg text containers (SectionType.MNGRP_M00MSG -- the
same blobs dumped as extracted_files/menu/m00x.msg / mwepon.msg, which are pure text with
their offsets stored in a separate m00bin section, so they cannot be parsed standalone),
plus TKMNMES, MNGRP_STRING and MNGRP_TEXTBOX text.

Invariant: saving repacks every text section and recomputes all offsets, so the first save
is NOT byte-identical to the original. What must hold is:
  * every decoded string survives a save + reload unchanged (semantic losslessness), and
  * a second round-trip is byte-stable (idempotent).
This mirrors the reasoning in tests/Pandemona/test_realfile_mngrp.py.

Needs the real files, skipped otherwise (ff8data marker). Note the load/save argument order:
MngrpManager.load_file(mngrphd, mngrp) but save_file(mngrp, mngrphd).
"""
import pathlib
import shutil

import pytest

from FF8GameData.gamedata import GameData, SectionType
from ShumiTranslator.model.mngrp.mngrpmanager import MngrpManager

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MENU_DIR = PROJECT_ROOT / "extracted_files" / "menu"
MNGRP = MENU_DIR / "mngrp.bin"
MNGRPHD = MENU_DIR / "mngrphd.bin"

MNGRP_REL = "extracted_files/menu/mngrp.bin"
MNGRPHD_REL = "extracted_files/menu/mngrphd.bin"


@pytest.fixture(scope="module")
def game_data():
    gd = GameData(str(PROJECT_ROOT / "FF8GameData"))
    gd.load_all()
    return gd


def _copy_work(tmp_path):
    work_mngrp = tmp_path / "mngrp.bin"
    work_mngrphd = tmp_path / "mngrphd.bin"
    shutil.copy(MNGRP, work_mngrp)
    shutil.copy(MNGRPHD, work_mngrphd)
    return work_mngrp, work_mngrphd


def _text_snapshot(manager):
    """Decoded string list of every editable text section, keyed by section id + type."""
    snap = {}
    for section in manager.mngrp.get_section_list():
        if section is None:
            continue
        section_type = getattr(section, "type", None)
        if section_type == SectionType.MNGRP_STRING:
            texts = [t.get_str() for t in section.get_text_section().get_text_list()]
        elif section_type in (SectionType.FF8_TEXT, SectionType.MNGRP_M00MSG,
                              SectionType.MNGRP_TEXTBOX, SectionType.TKMNMES):
            texts = [t.get_str() for t in section.get_text_list()]
        else:
            continue
        snap[(section.id, str(section_type))] = texts
    return snap


def _m00msg_ids(manager):
    return [s.id for s in manager.mngrp.get_section_list()
            if s is not None and getattr(s, "type", None) == SectionType.MNGRP_M00MSG]


@pytest.mark.ff8data(MNGRP_REL, MNGRPHD_REL)
def test_real_mngrp_text_survives_reload(game_data, tmp_path):
    """Load real mngrp.bin, save, reload: every decoded string is preserved."""
    work_mngrp, work_mngrphd = _copy_work(tmp_path)

    manager = MngrpManager(game_data)
    manager.load_file(str(work_mngrphd), str(work_mngrp))
    before = _text_snapshot(manager)

    # Sanity: the real file must actually contain the .msg (M00MSG) text container.
    m00msg_ids = _m00msg_ids(manager)
    assert m00msg_ids, "no MNGRP_M00MSG (.msg) text section parsed from the real mngrp.bin"
    assert any(before[key] for key in before if key[0] in m00msg_ids), \
        "M00MSG text container parsed empty"

    manager.save_file(str(work_mngrp), str(work_mngrphd))

    reloaded = MngrpManager(game_data)
    reloaded.load_file(str(work_mngrphd), str(work_mngrp))
    assert _text_snapshot(reloaded) == before


@pytest.mark.ff8data(MNGRP_REL, MNGRPHD_REL)
def test_real_mngrp_roundtrip_is_idempotent(game_data, tmp_path):
    """First save normalises offsets; a second round-trip must be byte-stable."""
    work_mngrp, work_mngrphd = _copy_work(tmp_path)

    manager = MngrpManager(game_data)
    manager.load_file(str(work_mngrphd), str(work_mngrp))
    manager.save_file(str(work_mngrp), str(work_mngrphd))  # normalise
    after_first = work_mngrp.read_bytes(), work_mngrphd.read_bytes()

    manager2 = MngrpManager(game_data)
    manager2.load_file(str(work_mngrphd), str(work_mngrp))
    manager2.save_file(str(work_mngrp), str(work_mngrphd))
    after_second = work_mngrp.read_bytes(), work_mngrphd.read_bytes()

    assert after_first == after_second


@pytest.mark.ff8data(MNGRP_REL, MNGRPHD_REL)
def test_real_mngrp_m00msg_edit_persists(game_data, tmp_path):
    """Editing one .msg (M00MSG) string survives save + reload; a sibling stays unchanged."""
    work_mngrp, work_mngrphd = _copy_work(tmp_path)

    manager = MngrpManager(game_data)
    manager.load_file(str(work_mngrphd), str(work_mngrp))

    msg_id = _m00msg_ids(manager)[0]
    section = next(s for s in manager.mngrp.get_section_list()
                   if s is not None and s.id == msg_id)
    text_list = section.get_text_list()
    assert len(text_list) >= 2, "need at least two strings to check a sibling is untouched"

    new_text = "ShumiTranslator test string"
    sibling_before = text_list[1].get_str()
    text_list[0].set_str(new_text)

    manager.save_file(str(work_mngrp), str(work_mngrphd))

    reloaded = MngrpManager(game_data)
    reloaded.load_file(str(work_mngrphd), str(work_mngrp))
    reloaded_section = next(s for s in reloaded.mngrp.get_section_list()
                            if s is not None and s.id == msg_id)
    reloaded_texts = reloaded_section.get_text_list()
    assert reloaded_texts[0].get_str() == new_text
    assert reloaded_texts[1].get_str() == sibling_before
