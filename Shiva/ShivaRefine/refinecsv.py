"""Refine entries <-> CSV, shared by the Shiva Refine tab and the `shiva` CLI.

No Qt here, so the GUI and the CLI write and read exactly the same file. Export uses the "|"
delimiter like every other Shiva/CLI CSV; import auto-detects it (Excel may save ";" or ",").
Columns are matched by header name, not position.
"""
import csv
import pathlib

from FF8GameData.gamedata import GameData

COLUMN_BIN = "Bin"
COLUMN_SECTION = "Section"
COLUMN_ENTRY = "Entry"
COLUMN_TEXT = "Text"
COLUMN_INPUT_ID = "Input ID"
COLUMN_AMOUNT_REQUIRED = "Amount required"
COLUMN_OUTPUT_ID = "Output ID"
COLUMN_AMOUNT_RECEIVED = "Amount received"
COLUMN_GF_LEVEL = "Required GF level"

REFINE_CSV_HEADER = [COLUMN_BIN, COLUMN_SECTION, COLUMN_ENTRY, COLUMN_TEXT, COLUMN_INPUT_ID,
                     COLUMN_AMOUNT_REQUIRED, COLUMN_OUTPUT_ID, COLUMN_AMOUNT_RECEIVED, COLUMN_GF_LEVEL]
DELIMITER = "|"


def export_rows(refine_views):
    """One row per refine entry, in REFINE_CSV_HEADER order."""
    rows = []
    for refine_view in refine_views:
        for entry_index, entry in enumerate(refine_view.entries):
            rows.append([refine_view.bin_name, refine_view.name, entry_index,
                         refine_view.texts[entry_index].get_str(), entry.element_in_id,
                         entry.amount_required, entry.element_out_id, entry.amount_received,
                         entry.required_gf_level])
    return rows


def write_refine_csv(path, refine_views):
    rows = export_rows(refine_views)
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file, delimiter=DELIMITER, quotechar='"', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(REFINE_CSV_HEADER)
        writer.writerows(rows)
    return len(rows)


def read_refine_csv(path, refine_views):
    """Apply a refine CSV (current format, or the old one through the temporary layer below) onto
    the entries and texts of refine_views. Returns the number of entries applied."""
    delimiter = GameData.find_delimiter_from_csv_file(path)
    with open(path, newline="", encoding="utf-8") as csv_file:
        lines = list(csv.reader(csv_file, delimiter=delimiter, quotechar='"'))
    if not lines:
        return 0
    header = [name.strip() for name in lines[0]]
    rows = [dict(zip(header, line)) for line in lines[1:] if line and str(line[0]).strip()]
    if _legacy_is_old_format(header):
        rows = [_legacy_convert_row(row) for row in rows]
    else:
        missing = [name for name in REFINE_CSV_HEADER if name not in header]
        if missing:
            raise ValueError(f"Refine CSV: missing column(s) {', '.join(missing)}")
    return apply_rows(refine_views, rows)


def apply_rows(refine_views, rows):
    """rows: dicts keyed by the REFINE_CSV_HEADER names."""
    views = {(view.bin_name, view.name): view for view in refine_views}
    applied = 0
    for row in rows:
        key = (row[COLUMN_BIN], row[COLUMN_SECTION])
        if key not in views:
            raise ValueError(f"Unknown refine section {key[0]}/{key[1]}")
        view = views[key]
        entry_index = int(row[COLUMN_ENTRY])
        entry = view.entries[entry_index]
        view.texts[entry_index].set_str(row[COLUMN_TEXT])
        entry.element_in_id = int(row[COLUMN_INPUT_ID])
        entry.amount_required = int(row[COLUMN_AMOUNT_REQUIRED])
        entry.element_out_id = int(row[COLUMN_OUTPUT_ID])
        entry.amount_received = int(row[COLUMN_AMOUNT_RECEIVED])
        entry.required_gf_level = int(row[COLUMN_GF_LEVEL])
        applied += 1
    return applied


# --------------------------------------------------------------------------------------------------
# TEMPORARY - old CSV format compatibility. Remove this block (and its call in read_refine_csv) once
# no CSV exported before 2026-10-23 is in use.
# The old export had "Amount received" = only byte 0x02, and a last column "Unknown" = bytes
# 0x03-0x04 read as a little-endian u16. Byte 0x03 is the high byte of the amount received and
# byte 0x04 the required GF level.
LEGACY_COLUMN_UNKNOWN = "Unknown"


def _legacy_is_old_format(header):
    return LEGACY_COLUMN_UNKNOWN in header and COLUMN_GF_LEVEL not in header


def _legacy_convert_row(row):
    unknown = int(row[LEGACY_COLUMN_UNKNOWN])
    row = dict(row)
    row[COLUMN_AMOUNT_RECEIVED] = str(int(row[COLUMN_AMOUNT_RECEIVED]) | ((unknown & 0xFF) << 8))
    row[COLUMN_GF_LEVEL] = str(unknown >> 8)
    return row
# --------------------------------------------------------------------------------------------------
