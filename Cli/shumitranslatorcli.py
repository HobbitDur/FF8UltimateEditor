"""
shumi_cli.py — Command-line interface for ShumiTranslator.

Mirrors every action available in the GUI:
  • load + save binary
  • export CSV  (load → csv)
  • import CSV  (csv → save binary)
  • compress / uncompress  (kernel only)

Usage examples
--------------
# Export kernel to CSV
python shumi_cli.py export-csv --type kernel --input kernel.bin --output kernel.csv

# Import CSV back and save
python shumi_cli.py import-csv --type kernel --input kernel.bin --csv kernel.csv --output kernel_modified.bin

# Save a dat file after importing CSV
python shumi_cli.py import-csv --type dat --input c0m001.dat c0m002.dat --csv monsters.csv --output-dir ./out

# Compress kernel strings then save
python shumi_cli.py compress --input kernel.bin --output kernel_compressed.bin

# Uncompress kernel strings
python shumi_cli.py uncompress --input kernel.bin --output kernel_uncompressed.bin

# Export field.fs text to CSV
python shumi_cli.py export-csv --type field --input field.fs --output field_text.csv

# Import CSV into field.fs and write msd files to a folder
python shumi_cli.py import-csv --type field --input field.fs --csv field_text.csv --output-dir ./field_out

# Export all text for all languages
python shumi_cli.py export-all-field --input-dir Temp --output-dir Temp/result
python shumi_cli.py export-all-battle --input-dir Temp --output-dir Temp/result
python shumi_cli.py export-all-kernel --input-dir Temp --output-dir Temp/result
python shumi_cli.py export-all-mngrp --input-dir Temp --output-dir Temp/result --mngrphd mngrphd.bin
python shumi_cli.py export-all-namedic --input-dir Temp --output-dir Temp/result
python shumi_cli.py export-all-exe --input-dir Temp --output-dir Temp/result
python shumi_cli.py export-all-world --input-dir Temp --output-dir Temp/result
"""

import argparse
import csv
import os
import pathlib
import sys

# ---------------------------------------------------------------------------
# Lazy Qt import guard — the managers need no Qt at all; only the main GUI
# widget does.  If Qt is unavailable (e.g. headless CI without PyQt6 wheels)
# the CLI still works for non-Qt paths.
# ---------------------------------------------------------------------------

# Resolve project root so "FF8GameData" is always found regardless of cwd
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
_GAME_DATA_FOLDER = str(_PROJECT_ROOT / "FF8GameData")

# Default CSV delimiter
DEFAULT_DELIMITER = "|"

# Language mapping: folder name -> 2-letter code
LANGUAGES = {
    "eng": "EN",
    "ger": "DE",
    "spa": "ES",
    "fre": "FR",
    "ita": "IT",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_game_data():
    from FF8GameData.gamedata import GameData
    gd = GameData(_GAME_DATA_FOLDER)
    gd.load_kernel_data()
    gd.load_mngrp_data()
    gd.load_item_data()
    gd.load_magic_data()
    gd.load_card_data()
    gd.load_stat_data()
    gd.load_ai_data()
    gd.load_monster_data()
    gd.load_status_data()
    gd.load_gforce_data()
    gd.load_special_action_data()
    gd.load_enemy_abilities_data()
    return gd


def _detect_type(input_files: list[str]) -> str:
    """Guess file type from the first input filename when --type is omitted."""
    name = pathlib.Path(input_files[0]).name.lower()
    if "kernel" in name and name.endswith(".bin"):
        return "kernel"
    if "namedic" in name and name.endswith(".bin"):
        return "namedic"
    if "mngrp" in name and name.endswith(".bin"):
        return "mngrp"
    if name.endswith(".exe"):
        return "exe"
    if "c0m" in name and name.endswith(".dat"):
        return "dat"
    if "off_cards_names" in name and name.endswith(".dat"):
        return "remaster"
    if "field" in name and name.endswith(".fs"):
        return "field"
    if "world" in name and name.endswith(".fs"):
        return "world"
    print(f"[error] Cannot auto-detect file type from '{input_files[0]}'. Use --type.", file=sys.stderr)
    sys.exit(1)


def _filter_dat_files(paths: list[str]) -> list[str]:
    """Mirror the GUI filter: skip c0m000, c0m127 and indices > 143."""
    result = []
    for p in paths:
        stem = pathlib.Path(p).stem
        try:
            index = int(stem.split("m")[1])
        except (IndexError, ValueError):
            result.append(p)
            continue
        if index != 0 and index != 127 and index <= 143:
            result.append(p)
    return result


def _iter_sections(gd, file_type: str, manager):
    """
    Yield section objects that carry text, matching what the GUI shows.
    Returns (section_widget_id, section) pairs so CSV row numbers stay
    consistent with what the GUI exports.
    """
    from FF8GameData.gamedata import SectionType

    idx = 0
    if file_type == "kernel":
        for section in manager.section_list:
            if section.type == SectionType.FF8_TEXT:
                yield idx, section
                idx += 1

    elif file_type == "namedic":
        yield 0, manager.get_text_section()

    elif file_type == "mngrp":
        for section in manager.mngrp.get_section_list():
            if section.type == SectionType.MNGRP_STRING:
                yield idx, section.get_text_section()
                idx += 1
            elif section.type in (SectionType.FF8_TEXT, SectionType.MNGRP_M00MSG, SectionType.MNGRP_TEXTBOX):
                yield idx, section
                idx += 1
            elif section.type == SectionType.TKMNMES:
                for i in range(section.get_nb_text_section()):
                    yield idx, section.get_text_section_by_id(i)
                    idx += 1

    elif file_type == "exe":
        exe_section = manager.get_exe_section()
        yield 0, exe_section.get_section_draw_text().get_text_section()
        yield 1, exe_section.get_section_card_misc_text().get_text_section()
        yield 2, exe_section.get_section_card_name().get_text_section()
        yield 3, exe_section.get_section_scan_text().get_text_section()

    elif file_type == "dat":
        for section in manager.get_section_list():
            yield idx, section
            idx += 1

    elif file_type == "remaster":
        yield 0, manager.get_section().get_text_section()


# ---------------------------------------------------------------------------
# Core Export Functions
# ---------------------------------------------------------------------------

def _write_csv(output: pathlib.Path, delimiter: str, file_type: str, gd, manager):
    """Write sections to CSV file."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=delimiter, quotechar='"', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(["Section data name", "Section Widget id", "Text Sub id", "Text"])
        for widget_id, section in _iter_sections(gd, file_type, manager):
            for text_id, ff8_text in enumerate(section.get_text_list()):
                writer.writerow([
                    section.name,
                    widget_id,
                    text_id,
                    ff8_text.get_str().replace("\n", "\\n"),
                ])


def _export_kernel_csv(gd, input_file: str, output_file: str):
    """Export kernel.bin to CSV."""
    from ShumiTranslator.model.kernel.kernelmanager import KernelManager
    mgr = KernelManager(game_data=gd)
    mgr.load_file(input_file)
    _write_csv(pathlib.Path(output_file), DEFAULT_DELIMITER, "kernel", gd, mgr)


def _export_namedic_csv(gd, input_file: str, output_file: str):
    """Export namedic.bin to CSV."""
    from ShumiTranslator.model.mngrp.string.sectionstring import SectionString
    mgr = SectionString(game_data=gd)
    mgr.load_file(input_file)
    _write_csv(pathlib.Path(output_file), DEFAULT_DELIMITER, "namedic", gd, mgr)


def _export_mngrp_csv(gd, input_file: str, mngrphd_file: str, output_file: str):
    """Export mngrp.bin to CSV."""
    from ShumiTranslator.model.mngrp.mngrpmanager import MngrpManager
    mgr = MngrpManager(game_data=gd)
    mgr.load_file(mngrphd_file, input_file)
    _write_csv(pathlib.Path(output_file), DEFAULT_DELIMITER, "mngrp", gd, mgr)


def _export_exe_csv(gd, input_file: str, output_file: str):
    """Export EXE to CSV."""
    from ShumiTranslator.model.exe.exemanager import ExeManager
    mgr = ExeManager(game_data=gd)
    mgr.load_file(input_file)
    _write_csv(pathlib.Path(output_file), DEFAULT_DELIMITER, "exe", gd, mgr)


def _export_battle_csv(gd, input_files: list[str], output_file: str):
    """Export battle c0m files to CSV."""
    from ShumiTranslator.model.battle.battlemanager import BattleManager
    mgr = BattleManager(game_data=gd)
    mgr.reset()
    for f in _filter_dat_files(input_files):
        mgr.add_file(f)
    _write_csv(pathlib.Path(output_file), DEFAULT_DELIMITER, "dat", gd, mgr)


def _export_remaster_csv(gd, input_file: str, output_file: str):
    """Export remaster card names to CSV."""
    from ShumiTranslator.model.exe.remasterdatmanager import RemasterDatManager
    from FF8GameData.gamedata import RemasterCardType
    name = pathlib.Path(input_file).name
    rtype = RemasterCardType.CARD_NAME2 if "2" in name else RemasterCardType.CARD_NAME
    mgr = RemasterDatManager(game_data=gd)
    mgr.load_file(input_file, rtype)
    _write_csv(pathlib.Path(output_file), DEFAULT_DELIMITER, "remaster", gd, mgr)


def _export_field_csv(gd, input_file: str, output_file: str):
    """Export field.fs to CSV."""
    from ShumiTranslator.model.field.fieldfsmanager import FieldFsManager
    mgr = FieldFsManager(game_data=gd, game_data_folder=os.path.join("..", "FF8GameData"))
    mgr.load_file(input_file)
    mgr.save_csv(output_file)


def _export_world_csv(gd, input_file: str, output_file: str):
    """Export world.fs to CSV."""
    from ShumiTranslator.model.world.worldfsmanager import WorldFsManager
    mgr = WorldFsManager(game_data=gd, game_data_folder=os.path.join("..", "FF8GameData"))
    mgr.load_file(input_file)
    mgr.save_csv(output_file)


# ---------------------------------------------------------------------------
# Core Import Functions
# ---------------------------------------------------------------------------

def _get_csv_delimiter(csv_path: str) -> str:
    """Detect delimiter from existing CSV file."""
    from FF8GameData.gamedata import GameData
    return GameData.find_delimiter_from_csv_file(csv_path)


def _apply_csv_to_sections(csv_path: str, delimiter: str, sections: list):
    """Read CSV and push text values back into section objects."""
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=delimiter, quotechar='"')
        for row_idx, row in enumerate(reader):
            if row_idx == 0:
                continue
            widget_id = int(row[1])
            text_sub_id = int(row[2])
            text = row[3].replace("`", "'")
            if not text:
                continue
            _, section = sections[widget_id]
            section.set_text_from_id(text_sub_id, text)


def _import_kernel_csv(gd, input_file: str, csv_file: str, output_file: str = None):
    """Import CSV into kernel.bin."""
    from ShumiTranslator.model.kernel.kernelmanager import KernelManager
    mgr = KernelManager(game_data=gd)
    mgr.load_file(input_file)
    sections = list(_iter_sections(gd, "kernel", mgr))
    delimiter = _get_csv_delimiter(csv_file)
    _apply_csv_to_sections(csv_file, delimiter, sections)
    out = output_file or input_file
    mgr.save_file(out)
    return out


def _import_namedic_csv(gd, input_file: str, csv_file: str, output_file: str = None):
    """Import CSV into namedic.bin."""
    from ShumiTranslator.model.mngrp.string.sectionstring import SectionString
    mgr = SectionString(game_data=gd)
    mgr.load_file(input_file)
    sections = list(_iter_sections(gd, "namedic", mgr))
    delimiter = _get_csv_delimiter(csv_file)
    _apply_csv_to_sections(csv_file, delimiter, sections)
    out = output_file or input_file
    mgr.save_file(out)
    return out


def _import_mngrp_csv(gd, input_file: str, mngrphd_file: str, csv_file: str, output_file: str = None):
    """Import CSV into mngrp.bin."""
    from ShumiTranslator.model.mngrp.mngrpmanager import MngrpManager
    mgr = MngrpManager(game_data=gd)
    mgr.load_file(mngrphd_file, input_file)
    sections = list(_iter_sections(gd, "mngrp", mgr))
    delimiter = _get_csv_delimiter(csv_file)
    _apply_csv_to_sections(csv_file, delimiter, sections)
    out = output_file or input_file
    mgr.save_file(out, mngrphd_file)
    return out


def _import_exe_csv(gd, input_file: str, csv_file: str, output_dir: str):
    """Import CSV into EXE and save msd files."""
    from ShumiTranslator.model.exe.exemanager import ExeManager
    mgr = ExeManager(game_data=gd)
    mgr.load_file(input_file)
    sections = list(_iter_sections(gd, "exe", mgr))
    delimiter = _get_csv_delimiter(csv_file)
    _apply_csv_to_sections(csv_file, delimiter, sections)
    out_dir = output_dir or str(pathlib.Path(input_file).parent)
    mgr.save_file(out_dir)
    return out_dir


def _import_battle_csv(gd, input_files: list[str], csv_file: str):
    """Import CSV into battle c0m files."""
    from ShumiTranslator.model.battle.battlemanager import BattleManager
    mgr = BattleManager(game_data=gd)
    mgr.reset()
    filtered = _filter_dat_files(input_files)
    for f in filtered:
        mgr.add_file(f)
    sections = list(_iter_sections(gd, "dat", mgr))
    delimiter = _get_csv_delimiter(csv_file)
    _apply_csv_to_sections(csv_file, delimiter, sections)
    mgr.save_all_file()
    return "in place"


def _import_remaster_csv(gd, input_file: str, csv_file: str, output_file: str = None):
    """Import CSV into remaster card names."""
    from ShumiTranslator.model.exe.remasterdatmanager import RemasterDatManager
    from FF8GameData.gamedata import RemasterCardType
    name = pathlib.Path(input_file).name
    rtype = RemasterCardType.CARD_NAME2 if "2" in name else RemasterCardType.CARD_NAME
    mgr = RemasterDatManager(game_data=gd)
    mgr.load_file(input_file, rtype)
    sections = list(_iter_sections(gd, "remaster", mgr))
    delimiter = _get_csv_delimiter(csv_file)
    _apply_csv_to_sections(csv_file, delimiter, sections)
    out = output_file or input_file
    mgr.save_file(out)
    return out


def _import_field_csv(gd, input_file: str, csv_file: str, output_dir: str):
    """Import CSV into field.fs."""
    from ShumiTranslator.model.field.fieldfsmanager import FieldFsManager
    mgr = FieldFsManager(game_data=gd)
    mgr.load_file(input_file)
    mgr.load_csv(csv_to_load=csv_file)
    out_dir = pathlib.Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    mgr.save_file(str(out_dir))
    return str(out_dir)


def _import_world_csv(gd, input_file: str, csv_file: str, output_dir: str):
    """Import CSV into world.fs."""
    from ShumiTranslator.model.world.worldfsmanager import WorldFsManager
    mgr = WorldFsManager(game_data=gd)
    mgr.load_file(input_file)
    mgr.load_csv(csv_to_load=csv_file)
    out_dir = pathlib.Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    mgr.save_file(str(out_dir))
    return str(out_dir)


# ---------------------------------------------------------------------------
# Command Handlers
# ---------------------------------------------------------------------------

def cmd_export_csv(args):
    """Export a binary file to CSV."""
    gd = _load_game_data()
    file_type = args.type or _detect_type(args.input)
    output_file = args.output

    print(f"[export-csv] type={file_type}  input={args.input}  output={output_file}")

    if file_type == "kernel":
        _export_kernel_csv(gd, args.input[0], output_file)
    elif file_type == "namedic":
        _export_namedic_csv(gd, args.input[0], output_file)
    elif file_type == "mngrp":
        if not args.mngrphd:
            print("[error] --mngrphd is required for mngrp files.", file=sys.stderr)
            sys.exit(1)
        _export_mngrp_csv(gd, args.input[0], args.mngrphd, output_file)
    elif file_type == "exe":
        _export_exe_csv(gd, args.input[0], output_file)
    elif file_type == "dat":
        _export_battle_csv(gd, args.input, output_file)
    elif file_type == "remaster":
        _export_remaster_csv(gd, args.input[0], output_file)
    elif file_type == "field":
        _export_field_csv(gd, args.input[0], output_file)
    elif file_type == "world":
        _export_world_csv(gd, args.input[0], output_file)

    print(f"[export-csv] Done → {output_file}")


def cmd_import_csv(args):
    """Import CSV into a binary file."""
    gd = _load_game_data()
    file_type = args.type or _detect_type(args.input)
    csv_file = args.csv

    print(f"[import-csv] type={file_type}  input={args.input}  csv={csv_file}")

    if file_type == "kernel":
        out = _import_kernel_csv(gd, args.input[0], csv_file, args.output)
        print(f"[import-csv] Saved → {out}")
    elif file_type == "namedic":
        out = _import_namedic_csv(gd, args.input[0], csv_file, args.output)
        print(f"[import-csv] Saved → {out}")
    elif file_type == "mngrp":
        if not args.mngrphd:
            print("[error] --mngrphd is required for mngrp files.", file=sys.stderr)
            sys.exit(1)
        out = _import_mngrp_csv(gd, args.input[0], args.mngrphd, csv_file, args.output)
        print(f"[import-csv] Saved → {out}")
    elif file_type == "exe":
        out_dir = args.output_dir or pathlib.Path(args.input[0]).parent
        _import_exe_csv(gd, args.input[0], csv_file, str(out_dir))
        print(f"[import-csv] Msd files saved → {out_dir}")
    elif file_type == "dat":
        result = _import_battle_csv(gd, args.input, csv_file)
        print(f"[import-csv] Dat files saved {result}")
    elif file_type == "remaster":
        out = _import_remaster_csv(gd, args.input[0], csv_file, args.output)
        print(f"[import-csv] Saved → {out}")
    elif file_type == "field":
        out_dir = args.output_dir or pathlib.Path(args.input[0]).parent
        _import_field_csv(gd, args.input[0], csv_file, str(out_dir))
        print(f"[import-csv] Files saved → {out_dir}")
    elif file_type == "world":
        out_dir = args.output_dir or pathlib.Path(args.input[0]).parent
        _import_world_csv(gd, args.input[0], csv_file, str(out_dir))
        print(f"[import-csv] Files saved → {out_dir}")


def cmd_export_all_field(args):
    """Export all field.fs text from all languages."""
    gd = _load_game_data()
    input_dir = pathlib.Path(args.input_dir)
    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for folder, lang_code in LANGUAGES.items():
        fs_file = input_dir / folder / "fs_files" / "field.fs"

        if not fs_file.exists():
            print(f"[warning] File not found: {fs_file}")
            continue

        output_file = output_dir / f"Default_all_text_{lang_code}.csv"
        print(f"[export-all-field] Exporting {folder} ({lang_code}) -> {output_file}")

        _export_field_csv(gd, str(fs_file), str(output_file))

    print(f"[export-all-field] Done! CSV files saved to {output_dir}")


def cmd_export_all_battle(args):
    """Export all battle text from all languages."""
    gd = _load_game_data()
    input_dir = pathlib.Path(args.input_dir)
    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for folder, lang_code in LANGUAGES.items():
        battle_dir = input_dir / folder / "extracted_files" / "battle"

        if not battle_dir.exists():
            print(f"[warning] Directory not found: {battle_dir}")
            continue

        c0m_files = sorted(battle_dir.glob("c0m*.dat"))
        if not c0m_files:
            print(f"[warning] No c0m*.dat files found in {battle_dir}")
            continue

        output_file = output_dir / f"Default_all_battle_text_{lang_code}.csv"
        print(f"[export-all-battle] Exporting {folder} ({lang_code}) -> {output_file}")

        _export_battle_csv(gd, [str(f) for f in c0m_files], str(output_file))

    print(f"[export-all-battle] Done! CSV files saved to {output_dir}")


def cmd_export_all_kernel(args):
    """Export all kernel.bin text from all languages."""
    gd = _load_game_data()
    input_dir = pathlib.Path(args.input_dir)
    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for folder, lang_code in LANGUAGES.items():
        kernel_file = input_dir / folder/ "extracted_files" / "main" / "kernel.bin"

        if not kernel_file.exists():
            print(f"[warning] File not found: {kernel_file}")
            continue

        output_file = output_dir / f"Default_all_kernel_text_{lang_code}.csv"
        print(f"[export-all-kernel] Exporting {folder} ({lang_code}) -> {output_file}")

        _export_kernel_csv(gd, str(kernel_file), str(output_file))

    print(f"[export-all-kernel] Done! CSV files saved to {output_dir}")


def cmd_export_all_namedic(args):
    """Export all namedic.bin text from all languages."""
    gd = _load_game_data()
    input_dir = pathlib.Path(args.input_dir)
    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for folder, lang_code in LANGUAGES.items():
        namedic_file = input_dir / folder/ "extracted_files" / "main" / "namedic.bin"

        if not namedic_file.exists():
            print(f"[warning] File not found: {namedic_file}")
            continue

        output_file = output_dir / f"Default_all_namedic_text_{lang_code}.csv"
        print(f"[export-all-namedic] Exporting {folder} ({lang_code}) -> {output_file}")

        _export_namedic_csv(gd, str(namedic_file), str(output_file))

    print(f"[export-all-namedic] Done! CSV files saved to {output_dir}")


def cmd_export_all_mngrp(args):
    """Export all mngrp.bin text from all languages."""
    gd = _load_game_data()
    input_dir = pathlib.Path(args.input_dir)
    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for folder, lang_code in LANGUAGES.items():
        mngrp_file = input_dir / folder/ "extracted_files" / "menu" / "mngrp.bin"
        mngrphd_file = input_dir / folder / "extracted_files"/ "menu" / "mngrphd.bin"

        if not mngrp_file.exists():
            print(f"[warning] File not found: {mngrp_file}")
            continue

        if not mngrphd_file.exists():
            print(f"[warning] mngrphd.bin not found: {mngrphd_file}")
            continue

        output_file = output_dir / f"Default_all_mngrp_text_{lang_code}.csv"
        print(f"[export-all-mngrp] Exporting {folder} ({lang_code}) -> {output_file}")

        _export_mngrp_csv(gd, str(mngrp_file), str(mngrphd_file), str(output_file))

    print(f"[export-all-mngrp] Done! CSV files saved to {output_dir}")

def cmd_export_all_exe(args):
    """Export all FF8_XX.exe text from all languages."""
    gd = _load_game_data()
    input_dir = pathlib.Path(args.input_dir)
    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Map language folders to exe filenames
    exe_files = {
        "eng": "FF8_EN.exe",
        "ger": "FF8_DE.exe",
        "spa": "FF8_ES.exe",
        "fre": "FF8_FR.exe",
        "ita": "FF8_IT.exe",
    }

    for folder, lang_code in LANGUAGES.items():
        exe_path = input_dir / folder / exe_files[folder]

        if not exe_path.exists():
            print(f"[warning] EXE not found: {exe_path}")
            continue

        output_file = output_dir / f"Default_all_exe_text_{lang_code}.csv"
        print(f"[export-all-exe] Exporting {folder} ({lang_code}) -> {output_file}")

        _export_exe_csv(gd, str(exe_path), str(output_file))

    print(f"[export-all-exe] Done! CSV files saved to {output_dir}")


def cmd_export_all_world(args):
    """Export all world.fs text from all languages."""
    gd = _load_game_data()
    input_dir = pathlib.Path(args.input_dir)
    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for folder, lang_code in LANGUAGES.items():
        world_file = input_dir / folder / "fs_files" / "world.fs"

        if not world_file.exists():
            print(f"[warning] File not found: {world_file}")
            continue

        output_file = output_dir / f"Default_all_world_text_{lang_code}.csv"
        print(f"[export-all-world] Exporting {folder} ({lang_code}) -> {output_file}")

        _export_world_csv(gd, str(world_file), str(output_file))

    print(f"[export-all-world] Done! CSV files saved to {output_dir}")


def cmd_compress(args):
    """Compress kernel.bin text strings."""
    gd = _load_game_data()
    from ShumiTranslator.model.kernel.kernelmanager import KernelManager
    from FF8GameData.gamedata import SectionType

    mgr = KernelManager(game_data=gd)
    mgr.load_file(args.input)
    print(f"[compress] Compressing {args.input} …")

    for section in mgr.section_list:
        if section.type == SectionType.FF8_TEXT:
            compressibility = [
                x["compressibility_factor"]
                for x in gd.kernel_data_json["sections"]
                if x["id"] == section.id
            ][0]
            section.compress_str(compressibility)

    out = args.output or args.input
    mgr.save_file(out)
    print(f"[compress] Done → {out}")


def cmd_uncompress(args):
    """Uncompress kernel.bin text strings."""
    gd = _load_game_data()
    from ShumiTranslator.model.kernel.kernelmanager import KernelManager
    from FF8GameData.gamedata import SectionType

    mgr = KernelManager(game_data=gd)
    mgr.load_file(args.input)
    print(f"[uncompress] Uncompressing {args.input} …")

    for section in mgr.section_list:
        if section.type == SectionType.FF8_TEXT:
            section.uncompress_str()

    out = args.output or args.input
    mgr.save_file(out)
    print(f"[uncompress] Done → {out}")


# ---------------------------------------------------------------------------
# Argument Parser
# ---------------------------------------------------------------------------
def cmd_export_all(args):
    """Export all text from all languages for all file types."""
    input_dir = args.input_dir
    output_dir = args.output_dir

    print(f"[export-all] Starting export of all text types from {input_dir} to {output_dir}")
    print("=" * 60)

    # Export all field files
    print("\n[1/7] Exporting field files...")
    cmd_export_all_field(args)

    # Export all battle files
    print("\n[2/7] Exporting battle files...")
    cmd_export_all_battle(args)

    # Export all kernel files
    print("\n[3/7] Exporting kernel files...")
    cmd_export_all_kernel(args)

    # Export all namedic files
    print("\n[4/7] Exporting namedic files...")
    cmd_export_all_namedic(args)

    # Export all mngrp files (mngrphd.bin expected in same folder)
    print("\n[5/7] Exporting mngrp files...")
    cmd_export_all_mngrp(args)

    # Export all exe files
    print("\n[6/7] Exporting exe files...")
    cmd_export_all_exe(args)

    # Export all world files
    print("\n[7/7] Exporting world files...")
    cmd_export_all_world(args)

    print("\n" + "=" * 60)
    print(f"[export-all] Complete! All CSV files saved to {output_dir}")

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shumi_cli",
        description="ShumiTranslator — command-line interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # export-csv
    p_export = sub.add_parser("export-csv", help="Load a binary file and export its text to CSV")
    p_export.add_argument("--input", "-i", nargs="+", required=True, help="Input file(s).")
    p_export.add_argument("--output", "-o", required=True, help="Output CSV file path.")
    p_export.add_argument("--type", "-t", choices=["kernel", "namedic", "mngrp", "exe", "dat", "remaster", "field", "world"],
                          help="File type. Auto-detected from filename if omitted.")
    p_export.add_argument("--mngrphd", help="Path to mngrphd.bin (required when --type=mngrp).")
    p_export.set_defaults(func=cmd_export_csv)

    # import-csv
    p_import = sub.add_parser("import-csv", help="Apply a CSV to a binary file and save")
    p_import.add_argument("--input", "-i", nargs="+", required=True, help="Input file(s) to patch.")
    p_import.add_argument("--csv", "-c", required=True, help="CSV file previously produced by export-csv.")
    p_import.add_argument("--output", "-o", help="Output file path (overwrites input if omitted).")
    p_import.add_argument("--output-dir", help="Output directory (exe, field, world, dat).")
    p_import.add_argument("--type", "-t", choices=["kernel", "namedic", "mngrp", "exe", "dat", "remaster", "field", "world"],
                          help="File type. Auto-detected if omitted.")
    p_import.add_argument("--mngrphd", help="Path to mngrphd.bin (required when --type=mngrp).")
    p_import.set_defaults(func=cmd_import_csv)

    # export-all-field
    p_export_field = sub.add_parser("export-all-field", help="Export all field.fs text from all languages")
    p_export_field.add_argument("--input-dir", "-i", required=True, help="Root directory containing lang subfolders (eng/, ger/, spa/, fre/, ita/).")
    p_export_field.add_argument("--output-dir", "-o", required=True, help="Directory where CSV files will be saved.")
    p_export_field.set_defaults(func=cmd_export_all_field)

    # export-all-battle
    p_export_battle = sub.add_parser("export-all-battle", help="Export all battle text from all languages")
    p_export_battle.add_argument("--input-dir", "-i", required=True, help="Root directory containing lang subfolders (eng/, ger/, spa/, fre/, ita/).")
    p_export_battle.add_argument("--output-dir", "-o", required=True, help="Directory where CSV files will be saved.")
    p_export_battle.set_defaults(func=cmd_export_all_battle)

    # export-all-kernel
    p_export_kernel = sub.add_parser("export-all-kernel", help="Export all kernel.bin text from all languages")
    p_export_kernel.add_argument("--input-dir", "-i", required=True, help="Root directory containing lang subfolders (eng/, ger/, spa/, fre/, ita/).")
    p_export_kernel.add_argument("--output-dir", "-o", required=True, help="Directory where CSV files will be saved.")
    p_export_kernel.set_defaults(func=cmd_export_all_kernel)

    # export-all-namedic
    p_export_namedic = sub.add_parser("export-all-namedic", help="Export all namedic.bin text from all languages")
    p_export_namedic.add_argument("--input-dir", "-i", required=True, help="Root directory containing lang subfolders (eng/, ger/, spa/, fre/, ita/).")
    p_export_namedic.add_argument("--output-dir", "-o", required=True, help="Directory where CSV files will be saved.")
    p_export_namedic.set_defaults(func=cmd_export_all_namedic)

    # export-all-mngrp
    p_export_mngrp = sub.add_parser("export-all-mngrp", help="Export all mngrp.bin text from all languages")
    p_export_mngrp.add_argument("--input-dir", "-i", required=True, help="Root directory containing lang subfolders (eng/, ger/, spa/, fre/, ita/).")
    p_export_mngrp.add_argument("--output-dir", "-o", required=True, help="Directory where CSV files will be saved.")
    p_export_mngrp.add_argument("--mngrphd", required=True, help="Path to mngrphd.bin (required for mngrp files).")
    p_export_mngrp.set_defaults(func=cmd_export_all_mngrp)

    # export-all-exe
    p_export_exe = sub.add_parser("export-all-exe", help="Export all FF8_XX.exe text from all languages")
    p_export_exe.add_argument("--input-dir", "-i", required=True, help="Root directory containing lang subfolders (eng/, ger/, spa/, fre/, ita/).")
    p_export_exe.add_argument("--output-dir", "-o", required=True, help="Directory where CSV files will be saved.")
    p_export_exe.set_defaults(func=cmd_export_all_exe)

    # export-all-world
    p_export_world = sub.add_parser("export-all-world", help="Export all world.fs text from all languages")
    p_export_world.add_argument("--input-dir", "-i", required=True, help="Root directory containing lang subfolders (eng/, ger/, spa/, fre/, ita/).")
    p_export_world.add_argument("--output-dir", "-o", required=True, help="Directory where CSV files will be saved.")
    p_export_world.set_defaults(func=cmd_export_all_world)

    # compress
    p_compress = sub.add_parser("compress", help="Compress kernel.bin text strings (kernel only)")
    p_compress.add_argument("--input", "-i", required=True, help="kernel.bin path.")
    p_compress.add_argument("--output", "-o", help="Output path (overwrites input if omitted).")
    p_compress.set_defaults(func=cmd_compress)

    # uncompress
    p_uncompress = sub.add_parser("uncompress", help="Uncompress kernel.bin text strings (kernel only)")
    p_uncompress.add_argument("--input", "-i", required=True, help="kernel.bin path.")
    p_uncompress.add_argument("--output", "-o", help="Output path (overwrites input if omitted).")
    p_uncompress.set_defaults(func=cmd_uncompress)
    # export-all
    p_export_all = sub.add_parser("export-all", help="Export all text from all languages for all file types")
    p_export_all.add_argument("--input-dir", "-i", required=True, help="Root directory containing lang subfolders (eng/, ger/, spa/, fre/, ita/).")
    p_export_all.add_argument("--output-dir", "-o", required=True, help="Directory where CSV files will be saved.")
    p_export_all.set_defaults(func=cmd_export_all)

    return parser


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()