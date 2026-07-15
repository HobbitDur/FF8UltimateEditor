"""Full round-trip verification for every text container ShumiTranslator handles.

For each container type this test loads the real game file(s), **forces a re-encode of
every decoded string** (``t.set_str(t.get_str())`` on all text objects, which runs the
string through ``translate_str_to_hex``), saves, reloads, and asserts that every decoded
string is byte-for-byte identical to what came out originally.

Why force a re-encode?  When a string is not edited, the containers keep its original raw
bytes on save, so a plain load/save/reload would never exercise the text codec.  Forcing a
re-encode makes the round-trip go through encode+decode for *every* string, which is exactly
where the ``{xNN}`` control-code handling lives.  This guarantees that all control codes --
including the raw ``{x..}`` codes that are not given a friendly name (menu ``0x0a`` context
values, ``MNGRP_STRING`` literal ``0x00``/``0x01`` padding, unmapped icons/locations, ...) --
survive the export/import cycle without any data loss.

Coverage: kernel.bin, namedic.bin, mngrp.bin (+mngrphd), the four EXE text sections and the
battle c0m*.dat set.  field.fs / world.fs / remaster card .dat are handled by ShumiTranslator
too but are not part of this extraction, so they are intentionally not covered here.

These need the original game files and are skipped automatically when absent (ff8data marker).
"""
import os
import re
import shutil
import sys
import pathlib

import pytest

from FF8GameData.gamedata import GameData, SectionType
from FF8GameData.GenericSection.ff8text import FF8Text

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
EF = PROJECT_ROOT / "extracted_files"

KERNEL = "extracted_files/main/kernel.bin"
NAMEDIC = "extracted_files/main/namedic.bin"
MNGRP = "extracted_files/menu/mngrp.bin"
MNGRPHD = "extracted_files/menu/mngrphd.bin"
EXE = "extracted_files/FF8_EN.exe"
BATTLE_ONE = "extracted_files/battle/c0m001.dat"

RAW_CODE_RE = re.compile(r"\{x[0-9a-f]{2,4}\}")
# 0x0a slots that FF8GameData now gives a friendly name (SpecialValues).  None of these
# must ever appear in export as a raw {x0aNN} token, otherwise the naming did not apply.
NAMED_0A_SLOTS = {"0a20", "0a22", "0a23", "0a26"}


@pytest.fixture(scope="module")
def game_data():
    gd = GameData(str(PROJECT_ROOT / "FF8GameData"))
    gd.load_all()
    return gd


# --------------------------------------------------------------------------- helpers

def _snapshot(text_sections):
    """List-of-lists of decoded strings for the given text sections."""
    return [[t.get_str() for t in sec.get_text_list()] for sec in text_sections]


def _force_reencode(text_sections):
    """Round-trip every string through the codec in place (set_str re-encodes)."""
    for sec in text_sections:
        for t in sec.get_text_list():
            t.set_str(t.get_str())


def _assert_lossless(before, after, label):
    assert len(before) == len(after), f"[{label}] section count changed: {len(before)} -> {len(after)}"
    for si, (a, b) in enumerate(zip(before, after)):
        assert a == b, (
            f"[{label}] section {si} text changed across round-trip.\n"
            f"  first diff: {next((x, y) for x, y in zip(a, b) if x != y)}"
        )


def _kernel_sections(mgr):
    return [s for s in mgr.section_list if s.type == SectionType.FF8_TEXT]


def _mngrp_sections(mgr):
    out = []
    for s in mgr.mngrp.get_section_list():
        if s is None:
            continue
        st = getattr(s, "type", None)
        if st == SectionType.MNGRP_STRING:
            out.append(s.get_text_section())
        elif st in (SectionType.FF8_TEXT, SectionType.MNGRP_M00MSG, SectionType.MNGRP_TEXTBOX):
            out.append(s)
        elif st == SectionType.TKMNMES:
            out.extend(s.get_text_section_by_id(i) for i in range(s.get_nb_text_section()))
    return out


def _exe_sections(mgr):
    es = mgr.get_exe_section()
    return [
        es.get_section_draw_text().get_text_section(),
        es.get_section_card_misc_text().get_text_section(),
        es.get_section_card_name().get_text_section(),
        es.get_section_scan_text().get_text_section(),
    ]


def _battle_files_filtered():
    files = []
    for p in sorted((EF / "battle").glob("c0m*.dat")):
        try:
            idx = int(p.stem.split("m")[1])
        except (IndexError, ValueError):
            files.append(p)
            continue
        if idx != 127 and idx <= 143:
            files.append(p)
    return files


# --------------------------------------------------------------------------- round-trip tests

@pytest.mark.ff8data(KERNEL)
def test_roundtrip_kernel(game_data, tmp_path):
    from ShumiTranslator.model.kernel.kernelmanager import KernelManager
    work = tmp_path / "kernel.bin"
    shutil.copy(EF / "main/kernel.bin", work)

    mgr = KernelManager(game_data)
    mgr.load_file(str(work))
    before = _snapshot(_kernel_sections(mgr))
    _force_reencode(_kernel_sections(mgr))
    mgr.save_file(str(work))

    reloaded = KernelManager(game_data)
    reloaded.load_file(str(work))
    _assert_lossless(before, _snapshot(_kernel_sections(reloaded)), "kernel")


@pytest.mark.ff8data(NAMEDIC)
def test_roundtrip_namedic(game_data, tmp_path):
    from ShumiTranslator.model.mngrp.string.sectionstring import SectionString
    work = tmp_path / "namedic.bin"
    shutil.copy(EF / "main/namedic.bin", work)

    mgr = SectionString(game_data)
    mgr.load_file(str(work))
    before = _snapshot([mgr])
    _force_reencode([mgr])
    mgr.save_file(str(work))

    reloaded = SectionString(game_data)
    reloaded.load_file(str(work))
    _assert_lossless(before, _snapshot([reloaded]), "namedic")


@pytest.mark.ff8data(MNGRP, MNGRPHD)
def test_roundtrip_mngrp(game_data, tmp_path):
    from ShumiTranslator.model.mngrp.mngrpmanager import MngrpManager
    work = tmp_path / "mngrp.bin"
    work_hd = tmp_path / "mngrphd.bin"
    shutil.copy(EF / "menu/mngrp.bin", work)
    shutil.copy(EF / "menu/mngrphd.bin", work_hd)

    mgr = MngrpManager(game_data)
    mgr.load_file(str(work_hd), str(work))
    before = _snapshot(_mngrp_sections(mgr))
    _force_reencode(_mngrp_sections(mgr))
    mgr.save_file(str(work), str(work_hd))

    reloaded = MngrpManager(game_data)
    reloaded.load_file(str(work_hd), str(work))
    _assert_lossless(before, _snapshot(_mngrp_sections(reloaded)), "mngrp")


@pytest.mark.ff8data(EXE)
def test_roundtrip_exe_codec(game_data):
    """The EXE importer emits .msd side files rather than rewriting the exe, so the codec is
    verified directly: re-encode each string and rebuild a fresh FF8Text from the bytes."""
    from ShumiTranslator.model.exe.exemanager import ExeManager
    mgr = ExeManager(game_data)
    mgr.load_file(str(EF / "FF8_EN.exe"))

    total = 0
    for sec in _exe_sections(mgr):
        for t in sec.get_text_list():
            total += 1
            original = t.get_str()
            encoded = game_data.translate_str_to_hex(original)
            cls = getattr(t, "_cursor_location_size", 2)
            rebuilt = FF8Text(game_data=game_data, own_offset=0,
                              data_hex=bytearray(encoded), id=0, cursor_location_size=cls)
            assert rebuilt.get_str() == original, f"[exe] codec lost data: {original!r} -> {rebuilt.get_str()!r}"
    assert total > 0, "no EXE text parsed"


@pytest.mark.ff8data(BATTLE_ONE)
def test_roundtrip_battle(game_data, tmp_path):
    from ShumiTranslator.model.battle.battlemanager import BattleManager
    work_dir = tmp_path / "battle"
    work_dir.mkdir()
    for p in _battle_files_filtered():
        shutil.copy(p, work_dir / p.name)
    work_files = sorted(work_dir.glob("c0m*.dat"))

    def _load():
        m = BattleManager(game_data)
        m.reset()
        for f in work_files:
            m.add_file(str(f))
        return m

    mgr = _load()
    before = _snapshot(list(mgr.get_section_list()))
    _force_reencode(list(mgr.get_section_list()))
    mgr.save_all_file()
    _assert_lossless(before, _snapshot(list(_load().get_section_list())), "battle")


# --------------------------------------------------------------------------- residual raw-code report

@pytest.mark.ff8data(KERNEL, NAMEDIC, MNGRP, MNGRPHD, EXE, BATTLE_ONE)
def test_residual_raw_codes_are_consistent(game_data, capsys):
    """Enumerate every raw ``{xNN}`` control code still present after decoding all real text.

    These raw codes are legitimate FF8 data (context-specific menu 0x0a values, MNGRP_STRING
    literal padding, icons/locations past the named tables) -- the round-trip tests above prove
    they are never lost.  This test additionally guarantees that a code we *have* named never
    leaks back out as raw, and prints the full residual histogram as a report.
    """
    from ShumiTranslator.model.kernel.kernelmanager import KernelManager
    from ShumiTranslator.model.mngrp.string.sectionstring import SectionString
    from ShumiTranslator.model.mngrp.mngrpmanager import MngrpManager
    from ShumiTranslator.model.exe.exemanager import ExeManager
    from ShumiTranslator.model.battle.battlemanager import BattleManager
    import collections

    def all_strings():
        k = KernelManager(game_data); k.load_file(str(EF / "main/kernel.bin"))
        for sec in _kernel_sections(k):
            yield from (t.get_str() for t in sec.get_text_list())
        n = SectionString(game_data); n.load_file(str(EF / "main/namedic.bin"))
        yield from (t.get_str() for t in n.get_text_list())
        m = MngrpManager(game_data); m.load_file(str(EF / "menu/mngrphd.bin"), str(EF / "menu/mngrp.bin"))
        for sec in _mngrp_sections(m):
            yield from (t.get_str() for t in sec.get_text_list())
        e = ExeManager(game_data); e.load_file(str(EF / "FF8_EN.exe"))
        for sec in _exe_sections(e):
            yield from (t.get_str() for t in sec.get_text_list())
        b = BattleManager(game_data); b.reset()
        for f in _battle_files_filtered():
            b.add_file(str(f))
        for sec in b.get_section_list():
            yield from (t.get_str() for t in sec.get_text_list())

    hist = collections.Counter()
    for s in all_strings():
        for tok in RAW_CODE_RE.findall(s):
            hist[tok[2:-1]] += 1  # strip {x .. }

    leaked = NAMED_0A_SLOTS & set(hist)
    assert not leaked, f"named 0x0a slots leaked as raw codes (naming did not apply): {sorted(leaked)}"

    a0 = {k: v for k, v in hist.items() if k.startswith("0a")}
    report = ["", "==== residual raw {xNN} codes across all containers ====",
              f"distinct codes: {len(hist)}   total occurrences: {sum(hist.values())}",
              f"distinct 0x0a codes still raw: {len(a0)} (occurrences: {sum(a0.values())})"]
    for code, count in sorted(hist.items()):
        report.append(f"  {{x{code}}} : {count}")
    with capsys.disabled():
        print("\n".join(report))
