"""Stats and battle texts as an xlsx holding this one monster: info_stat.xlsx.

The stats are edited in a spreadsheet, not in a text file - that is what the Stat > Excel tab and
the ifrit export-xlsx / import-xlsx commands do, and a mod keeps its stats in one workbook covering
every monster. So the section file for them is the same format, restricted to a single monster: one
sheet, the same columns, openable in Excel and re-importable anywhere the big workbook is.

It carries what that sheet carries: the stats (section 7) and the battle texts (the texts of
section 8), which is why there is no separate battle-text section file.

Applying takes the sheet of the monster being written onto when the workbook has one, and the only
sheet when it holds a single monster - so the file extracted from one monster can be applied to
another, like every other section file. A workbook covering the whole game (the mod's own xlsx)
therefore works too: the monster's own sheet is the one read.
"""
import pathlib
import re

from .common import SectionFileError


def _sheet_monster_id(sheet) -> int:
    """The monster id a sheet is about: its title starts with the number (e.g. '71 - G-Soldier')."""
    match = re.search(r'\d+', sheet.title)
    return int(match.group()) if match else -1


def export_section(enemy, file_path: pathlib.Path, tools):
    from Ifrit.IfritXlsx.xlsxmanager import DatToXlsx

    file_name = enemy.origin_file_name or f"c0m{enemy.id:03}.dat"
    writer = DatToXlsx()
    writer.create_file(str(file_path))
    try:
        # analyse_ai=False: the AI has its own section file, and analysing it here is pure waiting
        writer.export_to_xlsx(enemy, file_name, tools.game_data, analyse_ai=False)
        if not writer.workbook.worksheets():
            # export_to_xlsx skips the files the game does not use (000, 127, above 143)
            raise SectionFileError(f"{file_name}: the xlsx export skips this file, it holds no monster")
        writer.create_ref_data(tools.game_data)  # The sheet of values the drop-down columns point at
    finally:
        writer.close_file()


def apply_section(enemy, file_path: pathlib.Path, tools):
    from Ifrit.IfritXlsx import xlsxmanager

    reader = xlsxmanager.XlsxToDat()
    reader.load_file(str(file_path))
    try:
        sheets = [sheet for sheet in reader.workbook if sheet.title != xlsxmanager.REF_DATA_SHEET_TITLE]
        if not sheets:
            raise SectionFileError(f"{file_path}: the workbook has no monster sheet")
        chosen = next((sheet for sheet in sheets if _sheet_monster_id(sheet) == enemy.id), None)
        if chosen is None:
            if len(sheets) > 1:
                raise SectionFileError(
                    f"{file_path}: no sheet for monster {enemy.id} and the workbook holds several "
                    f"({', '.join(sheet.title for sheet in sheets)}) - which one should be applied?")
            chosen = sheets[0]  # A single monster: that is the one, whatever its id
        enemy.info_stat_data = reader.get_stat_info(chosen, tools.game_data)
        enemy.battle_script_data['battle_text'] = reader.get_battle_text(chosen, tools.game_data)
    finally:
        reader.close_file()
