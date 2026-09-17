"""Refresh the spells, items and enemy attacks a monster xlsx offers, in place.

The workbook writes every one of them as "<id>:<name>" (43:Death, 144:Arctic Wind...) and reads
back only the id, so a name is what a modder sees, never what a value means. When a mod renames
things in its kernel.bin, the workbook it edits keeps showing the old names until they are
refreshed here.

The file is patched rather than re-written: a monster workbook holds a stat chart per monster and
a drop-down per name column, and a spreadsheet library that reads and saves it loses them. An xlsx
is a zip of xml files, and those texts all live in one of them (xl/sharedStrings.xml), so that
single entry is rewritten and every other one is copied across untouched.

A text is only renamed when "<id>:<name>" says one thing: the same id exists in each list, so
"43:Death" is a spell only because no item and no enemy attack with id 43 is called Death either.
The rest is reported, never guessed.

A mod can also ADD spells to its kernel.bin, and then the workbook offers fewer than there are:
grow_list_in_workbook writes the missing ones where they are picked from and stretches the
drop-downs to reach them.
"""
import pathlib
import re
import shutil
import zipfile
from xml.sax.saxutils import escape, unescape

from FF8GameData.monsterdata import AIData
from Ifrit.IfritXlsx.xlsxmanager import (COL_MISC, REF_DATA_SHEET_TITLE, REF_DATA_COL_ABILITIES,
                                         REF_DATA_COL_ITEM, REF_DATA_COL_MAGIC, ROW_BYTE_FLAG)

TEXT_PATTERN = re.compile(r"(<t[^>]*>)([^<]*)(</t>)")
SHARED_STRINGS = "xl/sharedStrings.xml"

# Where a list of names is offered in the ref_data sheet, which is what every drop-down points at.
REF_DATA_COLUMN = {
    "magic": REF_DATA_COL_MAGIC,
    "item": REF_DATA_COL_ITEM,
    "enemy_ability": REF_DATA_COL_ABILITIES,
}


def _replace_workbook(xlsx_file, entries, files):
    """Write the patched workbook over the old one, through a file next to it: a failure half way
    then leaves the original where it was. A workbook open in Excel cannot be replaced, and saying
    so is more use than the error Windows gives."""
    temporary_file = str(xlsx_file) + ".patching"
    with zipfile.ZipFile(temporary_file, "w", zipfile.ZIP_DEFLATED) as new_workbook:
        for info, _ in entries:
            new_workbook.writestr(info, files[info.filename], compress_type=info.compress_type)
    try:
        shutil.move(temporary_file, xlsx_file)
    except PermissionError as error:
        pathlib.Path(temporary_file).unlink(missing_ok=True)
        raise PermissionError(f"{xlsx_file} cannot be written to - it is open in Excel or "
                              f"LibreOffice. Close it and run this again.") from error


def name_renames(old_names: dict, new_names: dict) -> dict:
    """The {shown text: new shown text} the workbook needs, from two {list: {id: name}} maps.

    A text several lists could have written is left out: it is returned on its own by
    ambiguous_renames() so the caller can say what it skipped."""
    renames = {}
    for text, targets in _by_text(old_names, new_names).items():
        if len(set(targets.values())) == 1:
            renames[text] = next(iter(targets.values()))
    return renames


def ambiguous_renames(old_names: dict, new_names: dict) -> dict:
    """The texts two lists write the same way and rename differently, as {text: {list: new text}}."""
    return {text: targets for text, targets in _by_text(old_names, new_names).items()
            if len(set(targets.values())) > 1}


def _by_text(old_names: dict, new_names: dict) -> dict:
    """{shown text: {list name: new shown text}} for every id whose name changed."""
    by_text = {}
    for list_name, names in new_names.items():
        for id_, new_name in names.items():
            old_name = old_names.get(list_name, {}).get(id_)
            if old_name is None or old_name == new_name:
                continue
            by_text.setdefault(f"{id_}:{old_name}", {})[list_name] = f"{id_}:{new_name}"
    return by_text


def rename_in_workbook(xlsx_file, renames: dict) -> dict:
    """Apply {shown text: new shown text} to a workbook, in place. Returns what it replaced, as
    {shown text: how many times}. The file is left untouched when nothing matches."""
    if not renames:
        return {}
    with zipfile.ZipFile(xlsx_file) as workbook:
        if SHARED_STRINGS not in workbook.namelist():
            return {}
        entries = [(info, workbook.read(info.filename)) for info in workbook.infolist()]

    replaced = {}

    def rename(match):
        text = unescape(match.group(2))
        if text not in renames:
            return match.group(0)
        replaced[text] = replaced.get(text, 0) + 1
        return match.group(1) + escape(renames[text]) + match.group(3)

    patched = []
    for info, content in entries:
        if info.filename == SHARED_STRINGS:
            content = TEXT_PATTERN.sub(rename, content.decode("utf8")).encode("utf8")
        patched.append((info, content))
    if not replaced:
        return {}

    _replace_workbook(xlsx_file, patched, {info.filename: content for info, content in patched})
    return replaced


# ---------------------------------------------------------------------------------------------
# Offering MORE names than the workbook was written with
# ---------------------------------------------------------------------------------------------
#
# A mod can add spells to its kernel.bin, and a workbook written before that offers the list as it
# was. The names are chosen from a column of the ref_data sheet, so making more of them available
# is: write the missing ones in that column, and stretch the drop-down of every monster sheet to
# the rows they landed on.

COLUMN_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
CELL_PATTERN = re.compile(r"<c r=\"([A-Z]+)(\d+)\"(?:\s[^>]*)?(?:/>|>.*?</c>)", re.S)
ROW_PATTERN = re.compile(r"<row r=\"(\d+)\"[^>]*(?:/>|>.*?</row>)", re.S)


def column_letter(column_index: int) -> str:
    return COLUMN_LETTERS[column_index]   # The ref_data sheet is seven columns wide


def list_length_in_workbook(xlsx_file, list_name: str) -> int:
    """How many names that list offers in this workbook today."""
    with zipfile.ZipFile(xlsx_file) as workbook:
        sheet_path = _ref_data_path(workbook)
        if sheet_path is None:
            return 0
        sheet = workbook.read(sheet_path).decode("utf8")
    letter = column_letter(REF_DATA_COLUMN[list_name])
    rows = {int(row) for column, row in
            ((match.group(1), match.group(2)) for match in CELL_PATTERN.finditer(sheet)) if column == letter}
    length = 0
    while length + 2 in rows:   # Row 1 is the title, the names run from row 2 without a gap
        length += 1
    return length


def grow_list_in_workbook(xlsx_file, list_name: str, texts: list) -> int:
    """Offer `texts` (the whole list, as "<id>:<name>") where the workbook offers fewer of them.

    Returns how many were added. The ones already there are left alone - they are renamed by
    rename_in_workbook, which is a different question from how long the list is."""
    letter = column_letter(REF_DATA_COLUMN[list_name])
    with zipfile.ZipFile(xlsx_file) as workbook:
        sheet_path = _ref_data_path(workbook)
        if sheet_path is None:
            return 0
        entries = [(info, workbook.read(info.filename)) for info in workbook.infolist()]
    files = {info.filename: content for info, content in entries}

    already = list_length_in_workbook(xlsx_file, list_name)
    missing = texts[already:]
    if not missing:
        return 0

    shared, indexes = _shared_strings(files[SHARED_STRINGS].decode("utf8"), missing)
    files[SHARED_STRINGS] = shared.encode("utf8")
    files[sheet_path] = _write_column(files[sheet_path].decode("utf8"), letter,
                                      already + 2, indexes).encode("utf8")

    # The drop-downs name the rows they read: every one of them now reaches the last of them
    last_row = already + 1 + len(missing)
    range_pattern = re.compile(rf"({re.escape(REF_DATA_SHEET_TITLE)}!\${letter}\d*:\${letter}\$)(\d+)")
    for name in list(files):
        if name.startswith("xl/worksheets/sheet") and name != sheet_path:
            text = files[name].decode("utf8")
            grown = range_pattern.sub(lambda match: match.group(1) + str(last_row)
                                      if int(match.group(2)) == already + 1 else match.group(0), text)
            if grown != text:
                files[name] = grown.encode("utf8")

    _replace_workbook(xlsx_file, entries, files)
    return len(missing)


def _ref_data_path(workbook) -> str:
    """The zip entry holding the ref_data sheet: the workbook names its sheets and points at them
    through its relationships, and neither order matches the file names."""
    book = workbook.read("xl/workbook.xml").decode("utf8")
    match = re.search(rf"<sheet name=\"{REF_DATA_SHEET_TITLE}\"[^>]*r:id=\"(rId\d+)\"", book)
    if not match:
        return None
    relationships = workbook.read("xl/_rels/workbook.xml.rels").decode("utf8")
    target = re.search(rf"Id=\"{match.group(1)}\"[^>]*Target=\"([^\"]+)\"", relationships)
    return "xl/" + target.group(1) if target else None


def _shared_strings(shared: str, texts: list) -> tuple:
    """Add `texts` to the workbook's table of texts (the ones already in it are reused), and give
    back their places in it - a cell holds the place, not the text."""
    places = {unescape(match.group(2)): index
              for index, match in enumerate(TEXT_PATTERN.finditer(shared))}
    added = [text for text in texts if text not in places]
    count = len(places)
    new_entries = ""
    for text in added:
        places[text] = count
        new_entries += f"<si><t>{escape(text)}</t></si>"
        count += 1
    if added:
        shared = shared.replace("</sst>", new_entries + "</sst>")
        shared = re.sub(r"count=\"\d+\" uniqueCount=\"\d+\"",
                        lambda match: f"count=\"{count}\" uniqueCount=\"{count}\"", shared, count=1)
    return shared, [places[text] for text in texts]


def _write_column(sheet: str, letter: str, first_row: int, indexes: list) -> str:
    """Put one text per row in `letter`, from `first_row` down, keeping the cells of a row in
    column order (a spreadsheet reads them as they come)."""
    style = _column_style(sheet, letter)
    column = COLUMN_LETTERS.index(letter)

    def write_row(match):
        row_xml = match.group(0)
        row_number = int(match.group(1))
        place = row_number - first_row
        if not 0 <= place < len(indexes):
            return row_xml
        cell = f"<c r=\"{letter}{row_number}\"{style} t=\"s\"><v>{indexes[place]}</v></c>"
        following = [name for name, _ in CELL_PATTERN.findall(row_xml) if COLUMN_LETTERS.index(name) > column]
        if following:
            return row_xml.replace(f"<c r=\"{following[0]}{row_number}\"", cell + f"<c r=\"{following[0]}{row_number}\"", 1)
        return row_xml.replace("</row>", cell + "</row>")

    grown = ROW_PATTERN.sub(write_row, sheet)
    written = grown.count(f"<c r=\"{letter}") - sheet.count(f"<c r=\"{letter}")
    if written != len(indexes):
        raise ValueError(f"The ref_data sheet has no room for {len(indexes) - written} more names "
                         f"in column {letter}: it stops at row {_last_row(sheet)}")
    return grown


def _column_style(sheet: str, letter: str) -> str:
    """The style the column's names already use, so a new one looks like the others - row 1 is the
    column's title and wears a different one."""
    for row, style in re.findall(rf"<c r=\"{letter}(\d+)\"(\s+s=\"\d+\")", sheet):
        if int(row) > 1:
            return style
    return ""


def _last_row(sheet: str) -> int:
    rows = [int(match.group(1)) for match in ROW_PATTERN.finditer(sheet)]
    return max(rows) if rows else 0


# ---------------------------------------------------------------------------------------------
# Relabelling the bit flags
# ---------------------------------------------------------------------------------------------

def refresh_byte_flag_labels(xlsx_file) -> dict:
    """Label the bit flags of every monster sheet with what the tools call them today.

    A bit IS its position in the byte; its name is only what the tools call it, and those are
    still being found - byte 2's first five were "byte2_zz1", "byte2_unused_3"... until someone
    worked out what they do. A workbook keeps whatever it was written with, so the labels are
    rewritten in place, by position, leaving the values beside them exactly where they are.

    Returns {old label: new label} for the ones that changed."""
    labels = [label for flag in AIData.BYTE_FLAG_LIST for label in AIData.BYTE_FLAG_VALUES[flag]]
    letter = column_letter(COL_MISC)
    first_row = ROW_BYTE_FLAG + 1     # The writer counts its rows from 0, a sheet from 1

    with zipfile.ZipFile(xlsx_file) as workbook:
        entries = [(info, workbook.read(info.filename)) for info in workbook.infolist()]
        reference = _ref_data_path(workbook)
    files = {info.filename: content for info, content in entries}

    shared, indexes = _shared_strings(files[SHARED_STRINGS].decode("utf8"), labels)
    texts = re.findall(r"<t[^>]*>([^<]*)</t>", shared)
    changed = {}
    for name in files:
        if not name.startswith("xl/worksheets/sheet") or name == reference:
            continue
        sheet = files[name].decode("utf8")
        for place, (label, index) in enumerate(zip(labels, indexes)):
            pattern = re.compile(rf"(<c r=\"{letter}{first_row + place}\"[^>]*t=\"s\"[^>]*><v>)(\d+)(</v>)")
            match = pattern.search(sheet)
            if not match or int(match.group(2)) == index:
                continue
            was = unescape(texts[int(match.group(2))])
            if was != label:
                changed[was] = label
            sheet = pattern.sub(match.group(1) + str(index) + match.group(3), sheet, count=1)
        files[name] = sheet.encode("utf8")
    if not changed:
        return {}
    files[SHARED_STRINGS] = shared.encode("utf8")

    _replace_workbook(xlsx_file, entries, files)
    return changed
