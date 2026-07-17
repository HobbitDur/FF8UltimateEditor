"""Game-view semantic round-trip test for mngrp.bin / mngrphd.bin.

The other mngrp tests (test_realfile_text.py, tests/Shiva/test_shiva_roundtrip.py)
prove that MngrpManager can reload its own output. That is necessary but not
sufficient: a save bug that moves a string to a different offset SLOT, drops a
zero offset, or shifts a tkmnmes padding would round-trip fine through the tool
while breaking in game, because FF8_EN.exe addresses everything positionally:

  * mngrphd.bin entries are read by RAW slot index (entry = header + 8*index);
    invalid entries (seek 0/0xFFFFFFFF or size 0) are placeholders that keep the
    raw indices stable and must survive a save byte-exactly.
  * getMenuString (0x4BD630) resolves text as base[2*section+2] then
    subtable[2*(2*index+variant)+2] -- a 0 offset means "no string", so zero
    offsets must stay zero AT THE SAME SLOT, and every non-zero slot must keep
    resolving to the same decoded string.
  * The TextBox map (raw slot 127) is a list of {entry_offset, section 0-5}
    consumed by the info browser (sub_4D5F10); each entry carries parent/left/
    right link ids used for navigation.
  * The refine menu (Menu_Prog19_RefineMenu_Init) reads m00X.bin 8-byte records
    {text_offset, received, unk, input, required, output} and resolves
    text_offset inside the paired m00X.msg.

This test therefore re-reads BOTH the original files and MngrpManager's saved
output with a small independent, game-accurate reader (plain struct offsets,
no MngrpManager section objects) and asserts the two views are semantically
identical. Byte identity is NOT expected (the save normalises text encoding and
padding); decoded-string identity at every game-addressable slot is.

Needs the real files, skipped otherwise (ff8data marker).
"""
import json
import pathlib
import shutil
import struct

import pytest

from FF8GameData.gamedata import GameData
from FF8GameData.GenericSection.ff8text import FF8Text
from FF8GameData.menu.mngrp.mngrpmanager import MngrpManager

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MENU_DIR = PROJECT_ROOT / "extracted_files" / "menu"
MNGRP = MENU_DIR / "mngrp.bin"
MNGRPHD = MENU_DIR / "mngrphd.bin"

MNGRP_REL = "extracted_files/menu/mngrp.bin"
MNGRPHD_REL = "extracted_files/menu/mngrphd.bin"

HEADER_ENTRY_COUNT = 256
TEXTBOX_MAP_TYPE = "mngrp_map_complex_string"
TEXTBOX_TYPE = "mngrp_complex_string"


@pytest.fixture(scope="module")
def game_data():
    gd = GameData(str(PROJECT_ROOT / "FF8GameData"))
    gd.load_all()
    return gd


@pytest.fixture(scope="module")
def section_meta(game_data):
    """data_type/section_name per compacted position, from mngrp_bin_data.json."""
    json_path = PROJECT_ROOT / "FF8GameData" / "Resources" / "json" / "mngrp_bin_data.json"
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)["sections"]


# ---------------------------------------------------------------------------
# Independent game-accurate readers
# ---------------------------------------------------------------------------

def read_header(hd: bytes):
    """raw slot -> (offset, size) for valid entries, exactly like the exe:
    valid = size != 0 and seek not in {0, 0xFFFFFFFF}; real offset = seek & ~1
    (bit 0 of seek is the 'stored uncompressed' flag, always set on PC)."""
    entries = {}
    for raw in range(HEADER_ENTRY_COUNT):
        seek, size = struct.unpack_from("<II", hd, raw * 8)
        if size == 0 or seek in (0, 0xFFFFFFFF):
            continue
        assert seek & 1, f"raw slot {raw}: seek bit0 (uncompressed flag) not set"
        entries[raw] = (seek - 1, size)
    return entries


def decode(game_data, data: bytes, cursor_location_size=2, first_hex_literal=False):
    """Decoded, normalised string as the tool's codec sees it."""
    return FF8Text(game_data=game_data, own_offset=0, data_hex=bytearray(data),
                   id=0, cursor_location_size=cursor_location_size,
                   first_hex_literal=first_hex_literal).get_str()


def string_section_view(game_data, sec: bytes, first_hex_literal=False):
    """Per-slot decoded strings of a string section (count word, u16 offsets,
    FF8 text). A 0 offset stays None -- the game shows no string there."""
    count = struct.unpack_from("<H", sec, 0)[0]
    offsets = list(struct.unpack_from("<%dH" % count, sec, 2)) if count else []
    view = []
    for i, off in enumerate(offsets):
        if off == 0:
            view.append(None)
            continue
        end = len(sec)
        for later in offsets[i + 1:]:
            if later:
                end = later
                break
        view.append(decode(game_data, sec[off:end], first_hex_literal=first_hex_literal))
    return count, view


def tkmnmes_view(game_data, sec: bytes):
    """Per-padding-slot view of a tkmnmes section: None for empty slots,
    otherwise the string-section view of the sub-section at that padding."""
    count_word = struct.unpack_from("<H", sec, 0)[0]
    nb_pad = count_word + 1
    paddings = struct.unpack_from("<%dH" % nb_pad, sec, 2)
    non_zero = sorted(p for p in paddings if p)
    view = []
    for pad in paddings:
        if pad == 0:
            view.append(None)
            continue
        end = len(sec)
        for later in non_zero:
            if later > pad:
                end = later
                break
        view.append(string_section_view(game_data, sec[pad:end]))
    return count_word, view


def textbox_map_view(mapsec: bytes):
    """[(entry_offset, section_number), ...] from the TextBox map section."""
    count = struct.unpack_from("<I", mapsec, 0)[0]
    return [struct.unpack_from("<HH", mapsec, 4 + 4 * i) for i in range(count)]


def textbox_entry_view(game_data, sec: bytes, entry_off: int):
    """(link0, link1, link2, title, body) of a TextBox entry, resolved like the
    info browser (sub_4D5F10): three u16 link ids, a u16 length (= exact entry
    size, unused by the game), then the title up to its 0x00 terminator and the
    body after it (pre_strcpy / strlen+1 in the exe). Entries start on 4-byte
    boundaries; the stored length must cover the content exactly."""
    assert entry_off % 4 == 0, f"TextBox entry at 0x{entry_off:X} not 4-byte aligned"
    link0, link1, link2, length = struct.unpack_from("<4H", sec, entry_off)
    content = sec[entry_off + 8: entry_off + length]
    title_end = content.index(b"\x00")
    body_end = content.index(b"\x00", title_end + 1)
    assert body_end == len(content) - 1, \
        f"TextBox entry at 0x{entry_off:X}: stored length {length} does not end at the body terminator"
    title = decode(game_data, content[:title_end], cursor_location_size=3)
    body = decode(game_data, content[title_end + 1:body_end], cursor_location_size=3)
    return link0, link1, link2, title, body


def m00_view(game_data, binsec: bytes, msgsec: bytes):
    """Game view of an m00X.bin + m00X.msg pair: one tuple per 8-byte record
    {received, unk, input, required, output, decoded text}; all-zero trailing
    records (padding) are skipped."""
    view = []
    for i in range(len(binsec) // 8):
        rec = binsec[8 * i: 8 * i + 8]
        if rec == b"\x00" * 8:
            continue
        text_offset = struct.unpack_from("<H", rec, 0)[0]
        received = rec[2]
        unk = struct.unpack_from("<H", rec, 3)[0]
        input_id, required, output_id = rec[5], rec[6], rec[7]
        text = decode(game_data, msgsec[text_offset:])
        view.append((i, received, unk, input_id, required, output_id, text))
    return view


def full_semantic_view(game_data, section_meta, hd: bytes, grp: bytes):
    """One comparable object for the whole archive, keyed by raw slot."""
    entries = read_header(hd)
    raw_slots = sorted(entries)
    sections = {raw: grp[off:off + size] for raw, (off, size) in entries.items()}
    view = {}
    textbox_secs = {}
    m00_bins, m00_msgs = [], []

    for pos, raw in enumerate(raw_slots):
        meta = section_meta[pos]
        data_type = meta["data_type"]
        sec = sections[raw]
        if data_type == "tkmnmes":
            view[raw] = ("tkmnmes", tkmnmes_view(game_data, sec))
        elif data_type == "mngrp_string":
            literal = "Test seed" in meta["section_name"]
            view[raw] = ("string", string_section_view(game_data, sec, first_hex_literal=literal))
        elif data_type == TEXTBOX_MAP_TYPE:
            view[raw] = ("textbox_map_placeholder", None)  # resolved below
        elif data_type == TEXTBOX_TYPE:
            textbox_secs[len(textbox_secs)] = sec
            view[raw] = ("textbox_section_placeholder", None)  # resolved below
        elif data_type == "m00bin":
            m00_bins.append(sec)
            view[raw] = ("m00bin_placeholder", None)  # resolved below
        elif data_type == "m00msg":
            m00_msgs.append(sec)
            view[raw] = ("m00msg", None)  # covered by the paired bin
        else:
            # Pure data (TIM textures, unknown blobs): the save must not touch
            # the content; only trailing zero-padding may differ.
            view[raw] = ("data", sec.rstrip(b"\x00"))

    # TextBox entries, resolved through the map like the game does.
    map_pos = next(i for i, m in enumerate(section_meta) if m["data_type"] == TEXTBOX_MAP_TYPE)
    map_sec = sections[raw_slots[map_pos]]
    resolved = []
    for entry_off, section_number in textbox_map_view(map_sec):
        resolved.append((section_number,) + textbox_entry_view(
            game_data, textbox_secs[section_number], entry_off))
    view["textbox_entries"] = resolved

    # m00X recipes resolved against their msg text.
    for idx, (binsec, msgsec) in enumerate(zip(m00_bins, m00_msgs)):
        view[f"m00{idx}"] = m00_view(game_data, binsec, msgsec)

    return entries, view


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def _save_roundtrip(game_data, tmp_path):
    work_mngrp = tmp_path / "mngrp.bin"
    work_mngrphd = tmp_path / "mngrphd.bin"
    shutil.copy(MNGRP, work_mngrp)
    shutil.copy(MNGRPHD, work_mngrphd)
    manager = MngrpManager(game_data)
    manager.load_file(str(work_mngrphd), str(work_mngrp))
    manager.save_file(str(work_mngrp), str(work_mngrphd))
    return work_mngrp.read_bytes(), work_mngrphd.read_bytes()


@pytest.mark.ff8data(MNGRP_REL, MNGRPHD_REL)
def test_saved_header_keeps_game_structure(game_data, tmp_path):
    """Raw slot layout survives: same valid slots, invalid entries byte-exact,
    bit0 flags set, sizes 0x800-aligned, sections contiguous and in-bounds."""
    new_grp, new_hd = _save_roundtrip(game_data, tmp_path)
    orig_hd = MNGRPHD.read_bytes()

    orig_entries = read_header(orig_hd)
    new_entries = read_header(new_hd)
    assert sorted(orig_entries) == sorted(new_entries), \
        "valid raw header slots changed -- exe hardcodes these indices"

    # Invalid placeholder entries must be preserved byte-exactly.
    for raw in range(HEADER_ENTRY_COUNT):
        if raw in orig_entries:
            continue
        assert new_hd[raw * 8: raw * 8 + 8] == orig_hd[raw * 8: raw * 8 + 8], \
            f"invalid header entry at raw slot {raw} was rewritten"

    # Saved sections: 0x800-aligned, contiguous, matching the file size.
    expected_offset = 0
    for raw in sorted(new_entries):
        off, size = new_entries[raw]
        assert off == expected_offset, f"raw slot {raw}: gap or overlap at 0x{off:X}"
        assert size % 0x800 == 0, f"raw slot {raw}: size 0x{size:X} not 0x800-aligned"
        expected_offset = off + size
    assert expected_offset == len(new_grp)


@pytest.mark.ff8data(MNGRP_REL, MNGRPHD_REL)
def test_saved_mngrp_is_game_semantically_identical(game_data, section_meta, tmp_path):
    """Every game-addressable datum (string slot, tkmnmes padding slot, TextBox
    map entry, m00X record) resolves identically in the original and the save."""
    new_grp, new_hd = _save_roundtrip(game_data, tmp_path)

    orig_entries, orig_view = full_semantic_view(
        game_data, section_meta, MNGRPHD.read_bytes(), MNGRP.read_bytes())
    _, new_view = full_semantic_view(game_data, section_meta, new_hd, new_grp)

    raw_slots = sorted(orig_entries)
    for pos, raw in enumerate(raw_slots):
        name = section_meta[pos]["section_name"] or section_meta[pos]["data_type"]
        assert new_view[raw] == orig_view[raw], \
            f"raw slot {raw} (pos {pos}, {name}) changed semantically"

    assert new_view["textbox_entries"] == orig_view["textbox_entries"], \
        "TextBox map/entries resolve differently"
    for idx in range(5):
        assert new_view[f"m00{idx}"] == orig_view[f"m00{idx}"], \
            f"m00{idx} refine records or their text changed"
