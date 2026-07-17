"""
Shiva CLI Tool.

Headless mngrp.bin editing (same data as the Shiva GUI). mngrp.bin holds many kinds of
sections; mngrphd.bin holds the section table and is rewritten together with it.

Refine formulas (the m000-m004 sub-files):
  • export-refine-csv  (mngrp.bin → CSV: one row per refine formula entry)
  • import-refine-csv  (base mngrp.bin + CSV → new mngrp.bin + mngrphd.bin)

SeeD written tests (the string sections 95-126, one answer byte before each text):
  • show-seed          (print the questions, choices and expected answer of one test)
  • export-seed-csv    (mngrp.bin → CSV: one row per string, answer + text)
  • import-seed-csv    (base mngrp.bin + CSV → new mngrp.bin + mngrphd.bin)
  • set-seed-answer    (change the expected answer of one question)

Tutorial demos (the demo input scripts and mock save data, raw slots 168-179 and 205):
  • tutorial-list            (show the demo scripts and mock save sections)
  • export-tutorial-script   (one demo script → editable op-list text file)
  • import-tutorial-script   (op-list text file → demo script raw slot)
  • export-tutorial-json     (scripts + mock characters + mock GFs → JSON)
  • import-tutorial-json     (apply a JSON produced by export-tutorial-json)

Like the GUI, this reads and writes the whole file through one MngrpManager, keeping the
sections it does not edit byte for byte instead of rebuilding them from an older copy.
"""

import argparse
import os
import sys

from .base import BaseCliTool
from .common import load_game_data, read_csv, write_csv

REFINE_CSV_HEADER = ["Bin", "Section", "Entry", "Text",
                     "Input ID", "Amount required", "Output ID", "Amount received", "Unknown"]


def _load_manager(mngrp_path: str, mngrphd_path: str = ""):
    from FF8GameData.menu.mngrp.mngrpmanager import MngrpManager
    if not mngrphd_path:
        mngrphd_path = os.path.join(os.path.dirname(mngrp_path), "mngrphd.bin")
    if not os.path.exists(mngrphd_path):
        raise FileNotFoundError(f"mngrphd.bin is needed to locate the sections of mngrp.bin, "
                                f"not found at: {mngrphd_path}")
    manager = MngrpManager(load_game_data())
    manager.load_file(mngrphd_path, mngrp_path)
    return manager, mngrphd_path


def _cmd_export_refine_csv(args) -> int:
    from Shiva.ShivaRefine.refineview import build_refine_views
    manager, _ = _load_manager(args.input, args.mngrphd)
    rows = []
    for refine_view in build_refine_views(manager):
        for entry_index, entry in enumerate(refine_view.entries):
            rows.append([refine_view.bin_name, refine_view.name, entry_index,
                         refine_view.texts[entry_index].get_str(),
                         entry.element_in_id, entry.amount_required,
                         entry.element_out_id, entry.amount_received, entry.unk])
    write_csv(args.output, REFINE_CSV_HEADER, rows)
    print(f"[ok] {len(rows)} refine entries exported to {args.output}")
    return 0


def _cmd_import_refine_csv(args) -> int:
    from Shiva.ShivaRefine.refineview import build_refine_views
    manager, mngrphd_path = _load_manager(args.input, args.mngrphd)
    refine_views = {(view.bin_name, view.name): view for view in build_refine_views(manager)}
    applied = 0
    for row in read_csv(args.csv):
        if not row or not str(row[0]).strip():
            continue
        key = (row[0], row[1])
        if key not in refine_views:
            raise ValueError(f"Unknown refine section {key[0]}/{key[1]}")
        refine_view = refine_views[key]
        entry_index = int(row[2])
        entry = refine_view.entries[entry_index]
        refine_view.texts[entry_index].set_str(row[3])
        entry.element_in_id = int(row[4])
        entry.amount_required = int(row[5])
        entry.element_out_id = int(row[6])
        entry.amount_received = int(row[7])
        entry.unk = int(row[8])
        applied += 1
    manager.save_file(args.output or args.input, args.output_mngrphd or mngrphd_path)
    out_name = args.output or args.input
    print(f"[ok] {applied} refine entries applied, written to {out_name} (+ mngrphd)")
    return 0


def _load_seed_tests(mngrp_path: str, mngrphd_path: str = ""):
    from Shiva.ShivaSeedTest.seedtest import SeedTestSet
    manager, resolved_mngrphd = _load_manager(mngrp_path, mngrphd_path)
    return manager, SeedTestSet.from_mngrp(manager.game_data, manager.mngrp), resolved_mngrphd


def _cmd_show_seed(args) -> int:
    _, seed_tests, _ = _load_seed_tests(args.input, args.mngrphd)
    test = seed_tests.get_test_by_csv_id(args.test)
    print(f"{test.name}: {len(test.strings)} strings")
    for index, seed_string in enumerate(test.strings):
        choices = seed_string.get_choices()
        print(f"\n[{index}] expected answer: {seed_string.answer}")
        print(f"    text: {seed_string.get_text()}")
        for choice_index, (stop, snippet) in enumerate(choices):
            marker = " <== expected" if choice_index == seed_string.answer else ""
            print(f"    choice {choice_index} (stop 0x{stop:02x}): {snippet}{marker}")
    return 0


def _cmd_export_seed_csv(args) -> int:
    _, seed_tests, _ = _load_seed_tests(args.input, args.mngrphd)
    rows = seed_tests.to_csv_rows()
    write_csv(args.output, seed_tests.CSV_HEADER, rows)
    print(f"[ok] {len(rows)} SeeD test strings exported to {args.output}")
    return 0


def _cmd_import_seed_csv(args) -> int:
    manager, seed_tests, mngrphd_path = _load_seed_tests(args.input, args.mngrphd)
    applied = seed_tests.apply_csv_rows(read_csv(args.csv))
    seed_tests.save_to_mngrp(manager.mngrp)
    manager.save_file(args.output or args.input, args.output_mngrphd or mngrphd_path)
    out_name = args.output or args.input
    print(f"[ok] {applied} SeeD test strings applied, written to {out_name} (+ mngrphd)")
    return 0


def _cmd_set_seed_answer(args) -> int:
    manager, seed_tests, mngrphd_path = _load_seed_tests(args.input, args.mngrphd)
    test = seed_tests.get_test_by_csv_id(args.test)
    if not 0 <= args.question - 1 < len(test.strings):
        raise ValueError(f"{test.name} has {len(test.strings)} questions, got question {args.question}")
    seed_string = test.strings[args.question - 1]
    nb_choices = len(seed_string.get_cursor_stops())
    if args.answer >= nb_choices:
        raise ValueError(f"{test.name} question {args.question} has {nb_choices} choices, "
                         f"answer {args.answer} is out of range")
    seed_string.answer = args.answer
    seed_tests.save_to_mngrp(manager.mngrp)
    manager.save_file(args.output or args.input, args.output_mngrphd or mngrphd_path)
    out_name = args.output or args.input
    print(f"[ok] {test.name} question {args.question} expected answer set to {args.answer}, "
          f"written to {out_name} (+ mngrphd)")
    return 0


def _load_tutorial(mngrp_path: str, mngrphd_path: str = ""):
    from Shiva.ShivaTutorial.tutorialmanager import TutorialManager
    manager, resolved_mngrphd = _load_manager(mngrp_path, mngrphd_path)
    return manager, TutorialManager.from_mngrp(manager.game_data, manager.mngrp), resolved_mngrphd


def _save_tutorial(manager, tutorial, mngrphd_path, args):
    """Write the tutorial slots back, keeping every other section byte for byte."""
    from Shiva.mngrpsave import keep_unowned_sections_raw
    keep_unowned_sections_raw(manager.game_data, manager.mngrp, tutorial.owned_section_ids())
    tutorial.save_to_mngrp(manager.mngrp)
    manager.save_file(args.output or args.input, args.output_mngrphd or mngrphd_path)
    return args.output or args.input


def _cmd_tutorial_list(args) -> int:
    _, tutorial, _ = _load_tutorial(args.input, args.mngrphd)
    print("Demo scripts:")
    for slot, script in tutorial.scripts.items():
        print(f"  raw {slot}: {script.name} ({len(script.ops)} ops)")
    for slot, mock_file in tutorial.mock_char_files.items():
        existing = sum(1 for record in mock_file.records if record.exists)
        print(f"Mock characters raw {slot}: {len(mock_file.records)} records ({existing} exist)")
    for slot, mock_file in tutorial.mock_gf_files.items():
        existing = sum(1 for record in mock_file.records if record.exists)
        print(f"Mock GFs raw {slot}: {len(mock_file.records)} records ({existing} exist)")
    return 0


def _cmd_export_tutorial_script(args) -> int:
    _, tutorial, _ = _load_tutorial(args.input, args.mngrphd)
    if args.slot not in tutorial.scripts:
        raise ValueError(f"raw slot {args.slot} is not a demo script (valid: {sorted(tutorial.scripts)})")
    script = tutorial.scripts[args.slot]
    with open(args.output, "w", encoding="utf8") as out_file:
        out_file.write(script.to_text(tutorial.get_captions(args.slot)))
    print(f"[ok] {script.name} ({len(script.ops)} ops) exported to {args.output}")
    return 0


def _cmd_import_tutorial_script(args) -> int:
    manager, tutorial, mngrphd_path = _load_tutorial(args.input, args.mngrphd)
    if args.slot not in tutorial.scripts:
        raise ValueError(f"raw slot {args.slot} is not a demo script (valid: {sorted(tutorial.scripts)})")
    with open(args.script, encoding="utf8") as in_file:
        tutorial.scripts[args.slot].set_ops_from_text(in_file.read())
    output = _save_tutorial(manager, tutorial, mngrphd_path, args)
    print(f"[ok] {len(tutorial.scripts[args.slot].ops)} ops applied to raw {args.slot}, written to {output}")
    return 0


def _cmd_export_tutorial_json(args) -> int:
    import json
    _, tutorial, _ = _load_tutorial(args.input, args.mngrphd)
    with open(args.output, "w", encoding="utf8") as out_file:
        json.dump(tutorial.to_dict(), out_file, indent=1, ensure_ascii=False)
    print(f"[ok] tutorial demo data exported to {args.output}")
    return 0


def _cmd_import_tutorial_json(args) -> int:
    import json
    manager, tutorial, mngrphd_path = _load_tutorial(args.input, args.mngrphd)
    with open(args.json, encoding="utf8") as in_file:
        tutorial.from_dict(json.load(in_file))
    output = _save_tutorial(manager, tutorial, mngrphd_path, args)
    print(f"[ok] tutorial demo data applied, written to {output}")
    return 0


class ShivaCliTool(BaseCliTool):
    """CLI tool for mngrp.bin editing (refine formulas for now)."""

    @property
    def name(self) -> str:
        return "shiva"

    @property
    def description(self) -> str:
        return "mngrp.bin editor: export/import the refine formulas (m000-m004) as CSV"

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="ff8-cli shiva",
            description="Headless mngrp.bin editor (same data as the Shiva GUI). "
                        "mngrphd.bin is auto-detected next to mngrp.bin when not given.",
        )
        sub = parser.add_subparsers(dest="command", required=True)

        p_export = sub.add_parser("export-refine-csv", help="Export the refine formulas to CSV")
        p_export.add_argument("--input", "-i", required=True, help="Path to mngrp.bin")
        p_export.add_argument("--mngrphd", help="Path to mngrphd.bin (default: next to mngrp.bin)")
        p_export.add_argument("--output", "-o", required=True, help="Output CSV path")
        p_export.set_defaults(func=_cmd_export_refine_csv)

        p_import = sub.add_parser("import-refine-csv", help="Apply a refine CSV onto mngrp.bin")
        p_import.add_argument("--input", "-i", required=True, help="Path to the base mngrp.bin")
        p_import.add_argument("--mngrphd", help="Path to mngrphd.bin (default: next to mngrp.bin)")
        p_import.add_argument("--csv", "-c", required=True, help="CSV produced by export-refine-csv")
        p_import.add_argument("--output", "-o", help="Output mngrp.bin (overwrites input if omitted)")
        p_import.add_argument("--output-mngrphd", help="Output mngrphd.bin (overwrites the loaded one if omitted)")
        p_import.set_defaults(func=_cmd_import_refine_csv)

        # --- SeeD written tests (string sections 95-126) ---
        p_show = sub.add_parser("show-seed", help="Print the questions, choices and answers of one SeeD test")
        p_show.add_argument("--input", "-i", required=True, help="Path to mngrp.bin")
        p_show.add_argument("--mngrphd", help="Path to mngrphd.bin (default: next to mngrp.bin)")
        p_show.add_argument("--test", "-t", required=True,
                            help="Test number (1-31) or 'general' for the shared exam UI text")
        p_show.set_defaults(func=_cmd_show_seed)

        p_seed_export = sub.add_parser("export-seed-csv", help="Export the SeeD test strings to CSV")
        p_seed_export.add_argument("--input", "-i", required=True, help="Path to mngrp.bin")
        p_seed_export.add_argument("--mngrphd", help="Path to mngrphd.bin (default: next to mngrp.bin)")
        p_seed_export.add_argument("--output", "-o", required=True, help="Output CSV path")
        p_seed_export.set_defaults(func=_cmd_export_seed_csv)

        p_seed_import = sub.add_parser("import-seed-csv", help="Apply a SeeD test CSV onto mngrp.bin")
        p_seed_import.add_argument("--input", "-i", required=True, help="Path to the base mngrp.bin")
        p_seed_import.add_argument("--mngrphd", help="Path to mngrphd.bin (default: next to mngrp.bin)")
        p_seed_import.add_argument("--csv", "-c", required=True, help="CSV produced by export-seed-csv")
        p_seed_import.add_argument("--output", "-o", help="Output mngrp.bin (overwrites input if omitted)")
        p_seed_import.add_argument("--output-mngrphd", help="Output mngrphd.bin (overwrites the loaded one if omitted)")
        p_seed_import.set_defaults(func=_cmd_import_seed_csv)

        p_set = sub.add_parser("set-seed-answer", help="Change the expected answer of one SeeD question")
        p_set.add_argument("--input", "-i", required=True, help="Path to the base mngrp.bin")
        p_set.add_argument("--mngrphd", help="Path to mngrphd.bin (default: next to mngrp.bin)")
        p_set.add_argument("--test", "-t", required=True, help="Test number (1-31) or 'general'")
        p_set.add_argument("--question", "-q", required=True, type=int, help="Question number (1-10)")
        p_set.add_argument("--answer", "-a", required=True, type=int,
                           help="Expected answer as a 0-based choice index (0 = YES, 1 = NO)")
        p_set.add_argument("--output", "-o", help="Output mngrp.bin (overwrites input if omitted)")
        p_set.add_argument("--output-mngrphd", help="Output mngrphd.bin (overwrites the loaded one if omitted)")
        p_set.set_defaults(func=_cmd_set_seed_answer)

        # --- Tutorial demos (demo scripts + mock save data, raw slots 168-179, 205) ---
        def add_tutorial_output(sub_parser):
            sub_parser.add_argument("--output", "-o", help="Output mngrp.bin (overwrites input if omitted)")
            sub_parser.add_argument("--output-mngrphd",
                                    help="Output mngrphd.bin (overwrites the loaded one if omitted)")

        p_tut_list = sub.add_parser("tutorial-list", help="List the demo scripts and mock save sections")
        p_tut_list.add_argument("--input", "-i", required=True, help="Path to mngrp.bin")
        p_tut_list.add_argument("--mngrphd", help="Path to mngrphd.bin (default: next to mngrp.bin)")
        p_tut_list.set_defaults(func=_cmd_tutorial_list)

        p_tut_es = sub.add_parser("export-tutorial-script", help="Export one demo script as an op-list text file")
        p_tut_es.add_argument("--input", "-i", required=True, help="Path to mngrp.bin")
        p_tut_es.add_argument("--mngrphd", help="Path to mngrphd.bin (default: next to mngrp.bin)")
        p_tut_es.add_argument("--slot", "-s", type=int, required=True,
                              help="Raw mngrphd slot of the script (168-175 or 205)")
        p_tut_es.add_argument("--output", "-o", required=True, help="Output text file")
        p_tut_es.set_defaults(func=_cmd_export_tutorial_script)

        p_tut_is = sub.add_parser("import-tutorial-script", help="Apply an op-list text file onto a demo script")
        p_tut_is.add_argument("--input", "-i", required=True, help="Path to the base mngrp.bin")
        p_tut_is.add_argument("--mngrphd", help="Path to mngrphd.bin (default: next to mngrp.bin)")
        p_tut_is.add_argument("--slot", "-s", type=int, required=True,
                              help="Raw mngrphd slot of the script (168-175 or 205)")
        p_tut_is.add_argument("--script", "-t", required=True, help="Text file produced by export-tutorial-script")
        add_tutorial_output(p_tut_is)
        p_tut_is.set_defaults(func=_cmd_import_tutorial_script)

        p_tut_ej = sub.add_parser("export-tutorial-json", help="Export scripts + mock save data as JSON")
        p_tut_ej.add_argument("--input", "-i", required=True, help="Path to mngrp.bin")
        p_tut_ej.add_argument("--mngrphd", help="Path to mngrphd.bin (default: next to mngrp.bin)")
        p_tut_ej.add_argument("--output", "-o", required=True, help="Output JSON path")
        p_tut_ej.set_defaults(func=_cmd_export_tutorial_json)

        p_tut_ij = sub.add_parser("import-tutorial-json", help="Apply a JSON produced by export-tutorial-json")
        p_tut_ij.add_argument("--input", "-i", required=True, help="Path to the base mngrp.bin")
        p_tut_ij.add_argument("--mngrphd", help="Path to mngrphd.bin (default: next to mngrp.bin)")
        p_tut_ij.add_argument("--json", "-j", required=True, help="JSON produced by export-tutorial-json")
        add_tutorial_output(p_tut_ij)
        p_tut_ij.set_defaults(func=_cmd_import_tutorial_json)

        return parser

    def execute(self, args: argparse.Namespace) -> int:
        try:
            return args.func(args)
        except Exception as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1
