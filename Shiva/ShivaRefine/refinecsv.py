"""Refine entries <-> CSV, shared by the Shiva Refine tab and the `shiva` CLI.

No Qt here, so the GUI and the CLI write and read exactly the same file. Export uses the "|"
delimiter like every other Shiva/CLI CSV; import auto-detects it (Excel may save ";" or ",").
Columns are matched by header name, not position.

A row is one entry of a refine table: Bin (m000-m004) and Entry, its index in the table - the same
with or without a kernel.bin, which only says which ability offers which entries. Ability names
them on export (empty without a kernel.bin) and is not read back, except for a new recipe: a row
with an empty Entry is added at the end of the kernel.bin ability it names, the ranges of the
table moving with it. Rows are never taken as a removal - a CSV may list only the rows it changes.
"""
import csv
import pathlib

from FF8GameData.gamedata import GameData

COLUMN_BIN = "Bin"
COLUMN_ENTRY = "Entry"
COLUMN_ABILITY = "Ability"
COLUMN_TEXT = "Text"
COLUMN_INPUT_ID = "Input ID"
COLUMN_AMOUNT_REQUIRED = "Amount required"
COLUMN_OUTPUT_ID = "Output ID"
COLUMN_AMOUNT_RECEIVED = "Amount received"
COLUMN_GF_LEVEL = "Required GF level"

REFINE_CSV_HEADER = [COLUMN_BIN, COLUMN_ENTRY, COLUMN_ABILITY, COLUMN_TEXT, COLUMN_INPUT_ID,
                     COLUMN_AMOUNT_REQUIRED, COLUMN_OUTPUT_ID, COLUMN_AMOUNT_RECEIVED, COLUMN_GF_LEVEL]
REQUIRED_COLUMNS = [name for name in REFINE_CSV_HEADER if name != COLUMN_ABILITY]
DELIMITER = "|"


def export_rows(layout):
    """One row per refine entry of a RefineLayout, in REFINE_CSV_HEADER order."""
    rows = []
    for table, (bin_section, msg_section) in enumerate(layout.tables()):
        texts = msg_section.get_text_list()
        for index, entry in enumerate(bin_section.entries):
            abilities = " / ".join(ability.name for ability in layout.abilities_offering(table, index))
            rows.append([bin_section.m00bin.name, index, abilities, texts[index].get_str(), entry.element_in_id,
                         entry.amount_required, entry.element_out_id, entry.amount_received,
                         entry.required_gf_level])
    return rows


def write_refine_csv(path, layout):
    rows = export_rows(layout)
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file, delimiter=DELIMITER, quotechar='"', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(REFINE_CSV_HEADER)
        writer.writerows(rows)
    return len(rows)


def read_refine_csv(path, layout):
    """Apply a refine CSV (current format, or an old one through the temporary layer below) onto
    the entries and texts of a RefineLayout. Returns the number of entries applied."""
    delimiter = GameData.find_delimiter_from_csv_file(path)
    with open(path, newline="", encoding="utf-8") as csv_file:
        lines = list(csv.reader(csv_file, delimiter=delimiter, quotechar='"'))
    if not lines:
        return 0
    header = [name.strip() for name in lines[0]]
    rows = [dict(zip(header, line)) for line in lines[1:] if line and str(line[0]).strip()]
    if _legacy_is_old_format(header):
        rows = _legacy_convert_rows(header, rows)
    else:
        missing = [name for name in REQUIRED_COLUMNS if name not in header]
        if missing:
            raise ValueError(f"Refine CSV: missing column(s) {', '.join(missing)}")
    return apply_rows(layout, rows)


def apply_rows(layout, rows):
    """rows: dicts keyed by the REFINE_CSV_HEADER names. The rows of existing entries are applied
    first, then the new recipes (empty Entry), which move the entries after them."""
    tables = {bin_section.m00bin.name: (bin_section, msg_section) for bin_section, msg_section in layout.tables()}
    applied = 0
    new_rows = []
    for row in rows:
        if row[COLUMN_BIN] not in tables:
            raise ValueError(f"Unknown refine table {row[COLUMN_BIN]}")
        if not str(row[COLUMN_ENTRY]).strip():
            new_rows.append(row)
            continue
        bin_section, msg_section = tables[row[COLUMN_BIN]]
        index = int(row[COLUMN_ENTRY])
        if not 0 <= index < len(bin_section.entries):
            raise ValueError(f"{row[COLUMN_BIN]} entry {index}: the table has {len(bin_section.entries)} entries "
                             f"(leave Entry empty to add a recipe to the ability named in {COLUMN_ABILITY})")
        _apply(row, bin_section.entries[index], msg_section.get_text_list()[index])
        applied += 1
    for row in new_rows:
        name = str(row.get(COLUMN_ABILITY, "")).strip()
        if not layout.from_kernel:
            raise ValueError(f"{row[COLUMN_BIN]}: adding the recipe '{row[COLUMN_TEXT]}' needs kernel.bin, "
                             f"which holds the range of each refine ability")
        matches = [view for view in layout.views if view.kind == "ability" and view.bin_name == row[COLUMN_BIN]
                   and view.name == name]
        if len(matches) != 1:
            raise ValueError(f"{row[COLUMN_BIN]}: no single refine ability named '{name}' for the new recipe "
                             f"'{row[COLUMN_TEXT]}'")
        view = matches[0]
        new_row = layout.insert_entry(view, len(view.entries) - 1)
        _apply(row, view.entries[new_row], view.texts[new_row])
        applied += 1
    return applied


def _apply(row, entry, text):
    text.set_str(row[COLUMN_TEXT])
    entry.element_in_id = int(row[COLUMN_INPUT_ID])
    entry.amount_required = int(row[COLUMN_AMOUNT_REQUIRED])
    entry.element_out_id = int(row[COLUMN_OUTPUT_ID])
    entry.amount_received = int(row[COLUMN_AMOUNT_RECEIVED])
    entry.required_gf_level = int(row[COLUMN_GF_LEVEL])


# --------------------------------------------------------------------------------------------------
# TEMPORARY - old CSV formats. Remove this block (and its call in read_refine_csv) once no CSV
# exported before 2026-10-27 is in use.
# Before 2026-10-27 a row was keyed by a "Section" (the block of a hardcoded vanilla layout) and its
# Entry in that block. Those exports always held every entry, in table order, so the entry's index
# in its table is its place among the rows of its Bin. Before 2026-10-23 there was also "Amount
# received" = only byte 0x02, and a last column "Unknown" = bytes 0x03-0x04 read as a little-endian
# u16: byte 0x03 is the high byte of the amount received and byte 0x04 the required GF level.
LEGACY_COLUMN_SECTION = "Section"
LEGACY_COLUMN_UNKNOWN = "Unknown"


def _legacy_is_old_format(header):
    return LEGACY_COLUMN_SECTION in header


def _legacy_convert_rows(header, rows):
    old_amounts = LEGACY_COLUMN_UNKNOWN in header and COLUMN_GF_LEVEL not in header
    converted = []
    next_index = {}
    previous = {}
    for row in rows:
        row = dict(row)
        table = row[COLUMN_BIN]
        place = (row[LEGACY_COLUMN_SECTION], int(row[COLUMN_ENTRY]))
        expected_entry = previous[table][1] + 1 if table in previous and previous[table][0] == place[0] else 0
        if place[1] != expected_entry:
            raise ValueError(f"Old refine CSV: {table}/{place[0]} entry {place[1]} is out of order. An old CSV "
                             f"must hold every entry in file order; export it again with this Shiva.")
        previous[table] = place
        row[COLUMN_ENTRY] = str(next_index.get(table, 0))
        next_index[table] = next_index.get(table, 0) + 1
        if old_amounts:
            unknown = int(row[LEGACY_COLUMN_UNKNOWN])
            row[COLUMN_AMOUNT_RECEIVED] = str(int(row[COLUMN_AMOUNT_RECEIVED]) | ((unknown & 0xFF) << 8))
            row[COLUMN_GF_LEVEL] = str(unknown >> 8)
        converted.append(row)
    return converted
# --------------------------------------------------------------------------------------------------
