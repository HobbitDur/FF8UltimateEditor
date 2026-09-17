"""Rename the spells, items and enemy attacks shown in a monster xlsx, in place.

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
"""
import re
import shutil
import zipfile
from xml.sax.saxutils import escape, unescape

TEXT_PATTERN = re.compile(r"(<t[^>]*>)([^<]*)(</t>)")
SHARED_STRINGS = "xl/sharedStrings.xml"


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

    # Written next to the workbook first, so a failure half way leaves the original in place
    temporary_file = str(xlsx_file) + ".renaming"
    with zipfile.ZipFile(temporary_file, "w", zipfile.ZIP_DEFLATED) as new_workbook:
        for info, content in patched:
            new_workbook.writestr(info, content, compress_type=info.compress_type)
    shutil.move(temporary_file, xlsx_file)
    return replaced
