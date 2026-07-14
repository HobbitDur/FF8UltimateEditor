"""Read-only decoder for menu.fs's Refine data tables (mngrp.bin/mngrphd.bin).

A Menu ability (kernel.bin section 18) only stores WHICH table (menu_index) and WHICH
slice of it (start_offset..end_offset) it uses - the actual source/destination items and
quantities live in menu.fs, not kernel.bin, so there's nothing here for SolomonRing to
*edit*. This module lets the editor show that data for reference, decoded live from the
extracted mngrp files, instead of leaving Start/End offset as two bare unexplained numbers.

Record format (confirmed via Menu_Prog19_RefineMenu_Init / sub_4D9600 / sub_4D9660,
FF8_EN.exe): each 8-byte record is
  offset 0-1  WORD  display text offset (unused here - names are resolved from GameData)
  offset 2-3  WORD  output quantity
  offset 4    BYTE  source quantity required
  offset 5    BYTE  source material id (item id for tables 0/1/3/4, magic id for table 2)
  offset 6    BYTE  (unconfirmed - constant 1 in every sample seen so far)
  offset 7    BYTE  destination material id (magic id for tables 0/2, item id for tables 1/3/4)
Tables (menu_index -> mngrp section id pair, first holds these records):
  0 = Magic Refine (188/196), 1 = Tool/Medicine Refine (189/197),
  2 = Mid/High Magic Refine (190/198), 3 = LV Up Refine (191/199).
  4 = Card Mod has no table - the game lists every card the player currently owns instead.
"""
from dataclasses import dataclass

RECORD_SIZE = 8
# menu_index -> mngrp section id holding that table's 8-byte records.
# 4 (Card Mod) uses the same record format in section 192, just with card ids as the
# source material (the menu itself only *lists* the cards you currently own, but the
# card->item recipe table it slices with start/end offset is this static section).
TABLE_SECTION_IDS = {0: 188, 1: 189, 2: 190, 3: 191, 4: 192}
CARD_MOD_INDEX = 4


@dataclass
class MngrphdEntry:
    seek: int
    size: int
    invalid_value: bool = False


def _read_mngrphd_entries(data: bytes):
    entries = []
    for i in range(0, len(data), 8):
        seek = int.from_bytes(data[i:i + 4], "little")
        size = int.from_bytes(data[i + 4:i + 8], "little")
        if seek == 0xFFFFFF or size == 0:
            entries.append(MngrphdEntry(seek=seek, size=size, invalid_value=True))
        else:
            entries.append(MngrphdEntry(seek=seek - 1, size=size, invalid_value=False))
    return entries


class MenuRefineReference:
    """Loads mngrphd.bin + mngrp.bin once and answers "what does this ability refine?"."""

    def __init__(self, mngrphd_path: str, mngrp_path: str):
        with open(mngrphd_path, "rb") as f:
            self._entries = _read_mngrphd_entries(f.read())
        with open(mngrp_path, "rb") as f:
            self._mngrp_data = f.read()

    def table_records(self, menu_index: int):
        """Every record in the table for this menu_index, as raw (out_qty, src_qty,
        src_id, dest_id) tuples. Returns [] if menu_index has no table (255/128/129/4)."""
        section_id = TABLE_SECTION_IDS.get(menu_index)
        if section_id is None or section_id >= len(self._entries):
            return []
        entry = self._entries[section_id]
        if entry.invalid_value:
            return []
        raw = self._mngrp_data[entry.seek: entry.seek + entry.size]
        records = []
        for i in range(0, len(raw) - RECORD_SIZE + 1, RECORD_SIZE):
            rec = raw[i:i + RECORD_SIZE]
            out_qty = int.from_bytes(rec[2:4], "little")
            src_qty = rec[4]
            src_id = rec[5]
            dest_id = rec[7]
            records.append((out_qty, src_qty, src_id, dest_id))
        return records

    def describe(self, menu_index: int, start_offset: int, end_offset: int,
                item_names: dict, magic_names: dict, card_names: dict = None):
        """Human-readable lines for this ability's [start_offset, end_offset] slice."""
        records = self.table_records(menu_index)
        if not records:
            return ["(this ability has no Refine table - shops / plain menu abilities)"]
        # Source is: cards for Card Mod, magic for the mid/high magic table, items otherwise.
        if menu_index == CARD_MOD_INDEX:
            src_names = card_names or {}
        elif menu_index == 2:
            src_names = magic_names
        else:
            src_names = item_names
        dest_is_magic = menu_index in (0, 2)
        dest_names = magic_names if dest_is_magic else item_names
        lines = []
        for i in range(start_offset, min(end_offset, len(records) - 1) + 1):
            if i < 0 or i >= len(records):
                continue
            out_qty, src_qty, src_id, dest_id = records[i]
            src = src_names.get(src_id, f"0x{src_id:X}")
            dest = dest_names.get(dest_id, f"0x{dest_id:X}")
            lines.append(f"{src_qty}x {src}  ->  {out_qty}x {dest}")
        return lines or ["(start/end offset out of range for this table)"]
