"""
Nida CLI Tool.

Headless SeeD written test editing (same data as the Nida GUI). The tests live
in the mngrp.bin string sections at raw header entries 95-126 (mngrphd.bin
holds the section table and is rewritten together with it): entry 95 is the
shared exam UI text, entries 96-125 the tests 1-30 (10 questions each), entry
126 an unused "test 31". Every string starts with the expected-answer byte
(0-based cursor-stop index) before the FF8 text:
  • show        (print the questions, choices and expected answer of one test)
  • export-csv  (mngrp.bin → CSV: one row per string, answer + text)
  • import-csv  (base mngrp.bin + CSV → new mngrp.bin + mngrphd.bin)
  • set-answer  (change the expected answer of one question)
"""

import argparse
import sys

from .base import BaseCliTool
from .common import load_game_data, read_csv, write_csv

def _load_manager(mngrp_path: str, mngrphd_path: str = ""):
    from Nida.nidamanager import NidaManager
    manager = NidaManager(load_game_data())
    manager.load_file(mngrp_path, mngrphd_path or "")
    return manager


def _cmd_show(args) -> int:
    manager = _load_manager(args.input, args.mngrphd)
    test = manager.get_test_by_csv_id(args.test)
    print(f"{test.name}: {len(test.strings)} strings")
    for index, seed_string in enumerate(test.strings):
        choices = seed_string.get_choices()
        print(f"\n[{index}] expected answer: {seed_string.answer}")
        print(f"    text: {seed_string.get_text()}")
        for choice_index, (stop, snippet) in enumerate(choices):
            marker = " <== expected" if choice_index == seed_string.answer else ""
            print(f"    choice {choice_index} (stop 0x{stop:02x}): {snippet}{marker}")
    return 0


def _cmd_export_csv(args) -> int:
    manager = _load_manager(args.input, args.mngrphd)
    rows = manager.to_csv_rows()
    write_csv(args.output, manager.CSV_HEADER, rows)
    print(f"[ok] {len(rows)} SeeD test strings exported to {args.output}")
    return 0


def _cmd_import_csv(args) -> int:
    manager = _load_manager(args.input, args.mngrphd)
    applied = manager.apply_csv_rows(read_csv(args.csv))
    manager.save_file(args.output or "", args.output_mngrphd or "")
    out_name = args.output or args.input
    print(f"[ok] {applied} SeeD test strings applied, written to {out_name} (+ mngrphd)")
    return 0


def _cmd_set_answer(args) -> int:
    manager = _load_manager(args.input, args.mngrphd)
    test = manager.get_test_by_csv_id(args.test)
    if not 0 <= args.question - 1 < len(test.strings):
        raise ValueError(f"{test.name} has {len(test.strings)} questions, got question {args.question}")
    seed_string = test.strings[args.question - 1]
    nb_choices = len(seed_string.get_cursor_stops())
    if args.answer >= nb_choices:
        raise ValueError(f"{test.name} question {args.question} has {nb_choices} choices, "
                         f"answer {args.answer} is out of range")
    seed_string.answer = args.answer
    manager.save_file(args.output or "", args.output_mngrphd or "")
    out_name = args.output or args.input
    print(f"[ok] {test.name} question {args.question} expected answer set to {args.answer}, "
          f"written to {out_name} (+ mngrphd)")
    return 0


class NidaCliTool(BaseCliTool):
    """CLI tool for the SeeD written tests (string sections inside mngrp.bin)."""

    @property
    def name(self) -> str:
        return "nida"

    @property
    def description(self) -> str:
        return "SeeD test editor: show/export/import the exam questions and answers (mngrp.bin sections 95-126)"

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="ff8-cli nida",
            description="Headless SeeD written test editor (same data as the Nida GUI). "
                        "mngrphd.bin is auto-detected next to mngrp.bin when not given. "
                        "Tests are 1-30 (31 = unused duplicate), questions 1-10, answers are "
                        "0-based cursor-stop indexes (0 = YES, 1 = NO on the standard questions).",
        )
        sub = parser.add_subparsers(dest="command", required=True)

        def add_common(sub_parser, with_outputs=True):
            sub_parser.add_argument("--input", "-i", required=True, help="Path to mngrp.bin")
            sub_parser.add_argument("--mngrphd", help="Path to mngrphd.bin (default: next to mngrp.bin)")
            if with_outputs:
                sub_parser.add_argument("--output", "-o", help="Output mngrp.bin (overwrites input if omitted)")
                sub_parser.add_argument("--output-mngrphd",
                                        help="Output mngrphd.bin (overwrites the loaded one if omitted)")

        p_show = sub.add_parser("show", help="Print the questions, choices and expected answers of one test")
        add_common(p_show, with_outputs=False)
        p_show.add_argument("--test", "-t", required=True,
                            help="Test number (1-31) or 'general' for the shared exam UI text")
        p_show.set_defaults(func=_cmd_show)

        p_export = sub.add_parser("export-csv", help="Export all the SeeD test strings to CSV")
        add_common(p_export, with_outputs=False)
        p_export.add_argument("--output", "-o", required=True, help="Output CSV path")
        p_export.set_defaults(func=_cmd_export_csv)

        p_import = sub.add_parser("import-csv", help="Apply a CSV onto mngrp.bin")
        add_common(p_import)
        p_import.add_argument("--csv", "-c", required=True, help="CSV produced by export-csv")
        p_import.set_defaults(func=_cmd_import_csv)

        p_set = sub.add_parser("set-answer", help="Change the expected answer of one question")
        add_common(p_set)
        p_set.add_argument("--test", "-t", required=True,
                           help="Test number (1-31) or 'general'")
        p_set.add_argument("--question", "-q", required=True, type=int, help="Question number (1-10)")
        p_set.add_argument("--answer", "-a", required=True, type=int,
                           help="Expected answer as a 0-based choice index (0 = YES, 1 = NO)")
        p_set.set_defaults(func=_cmd_set_answer)

        return parser

    def execute(self, args: argparse.Namespace) -> int:
        try:
            return args.func(args)
        except Exception as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1
