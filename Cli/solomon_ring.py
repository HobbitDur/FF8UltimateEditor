"""
SolomonRing CLI Tool.

Headless kernel.bin editing (same data-driven model as the SolomonRing GUI:
kernel_section_fields.json defines every editable field of the 31 sections):
  • list-sections  (print the editable kernel sections)
  • list-fields    (print the fields + text labels of one section)
  • get            (print one entry's fields, or a single field/text)
  • set            (set one field or text of one entry, save the kernel)
  • export-csv     (one section → CSV: one row per entry, texts + all fields)
  • import-csv     (CSV → kernel.bin, applied onto a base kernel)

Fields are addressed exactly like the GUI: section id → entry index → field name.
"""

import argparse
import json
import sys

from .base import BaseCliTool
from .common import PROJECT_ROOT, load_game_data, read_csv, write_csv


def _load_section_configs() -> dict:
    path = PROJECT_ROOT / "FF8GameData" / "Resources" / "json" / "kernel_section_fields.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class _KernelFile:
    """A loaded kernel.bin exposed as KernelEntry lists per section (GUI model, headless)."""

    def __init__(self, kernel_path: str):
        from ShumiTranslator.model.kernel.kernelmanager import KernelManager
        self.game_data = load_game_data()
        self.manager = KernelManager(self.game_data)
        self.manager.load_file(kernel_path)
        self.section_configs = _load_section_configs()
        # Read the raw json like the GUI does: KernelManager.load_file mutates
        # game_data.kernel_data_json, losing the section_id_text_linked values.
        kernel_json_path = PROJECT_ROOT / "FF8GameData" / "Resources" / "json" / "kernel_bin_data.json"
        with open(kernel_json_path, encoding="utf-8") as f:
            kernel_json = json.load(f)
        self.text_link = {s["id"]: s["section_id_text_linked"]
                          for s in kernel_json["sections"] if s["type"] == "data"}
        self._by_id = {s.id: s for s in self.manager.section_list if s}

    def config(self, section_id: int) -> dict:
        config = self.section_configs.get(str(section_id))
        if config is None:
            raise ValueError(f"Section {section_id} has no field definition "
                             f"(known: {', '.join(sorted(self.section_configs, key=int))})")
        return config

    def entries(self, section_id: int) -> list:
        """Same construction as KernelSectionTab.load_section."""
        from SolomonRing.kernelentry import KernelEntry
        config = self.config(section_id)
        section = self._by_id[section_id]
        text_id = self.text_link.get(section_id, 0)
        text_section = self._by_id.get(text_id) if text_id else None
        fields = config["fields"]
        nb_text = len(config.get("text_labels", []))
        return [KernelEntry(subsection, text_section, nb_text, i, fields, self.game_data)
                for i, subsection in enumerate(section.get_subsection_list())]

    def save(self, output_path: str):
        self.manager.save_file(output_path)


def _cmd_list_sections(args) -> int:
    configs = _load_section_configs()
    for section_id in sorted(configs, key=int):
        config = configs[section_id]
        name = config.get("name", f"Section {section_id}")
        nb_fields = len(config.get("fields", []))
        labels = ", ".join(config.get("text_labels", []))
        print(f"{int(section_id):3d}: {name} ({nb_fields} fields" + (f", texts: {labels})" if labels else ")"))
    return 0


def _cmd_list_fields(args) -> int:
    config = _load_section_configs().get(str(args.section))
    if config is None:
        print(f"[error] Section {args.section} has no field definition", file=sys.stderr)
        return 1
    for index, label in enumerate(config.get("text_labels", [])):
        print(f"text {index}: {label}")
    for field in config.get("fields", []):
        extra = []
        if field.get("mask") is not None:
            extra.append(f"mask 0x{field['mask']:X}")
        if field.get("lookup"):
            extra.append(f"lookup {field['lookup']}")
        if field.get("readonly"):
            extra.append("readonly")
        details = f" ({', '.join(extra)})" if extra else ""
        print(f"{field['name']}: offset 0x{field['offset']:X}, size {field['size']}{details}")
    return 0


def _cmd_get(args) -> int:
    kernel = _KernelFile(args.input)
    entries = kernel.entries(args.section)
    entry = entries[args.entry]
    config = kernel.config(args.section)
    if args.field:
        print(entry.get(args.field))
        return 0
    if args.text_index is not None:
        print(entry.get_text(args.text_index))
        return 0
    for index, label in enumerate(config.get("text_labels", [])):
        print(f"text {index} ({label}): {entry.get_text(index)}")
    for field in config.get("fields", []):
        print(f"{field['name']}: {entry.get(field['name'])}")
    return 0


def _cmd_set(args) -> int:
    if args.field is None and args.text_index is None:
        print("[error] Nothing to set: give --field/--value or --text-index/--text", file=sys.stderr)
        return 1
    kernel = _KernelFile(args.input)
    entry = kernel.entries(args.section)[args.entry]
    if args.field is not None:
        if args.value is None:
            print("[error] --field needs --value", file=sys.stderr)
            return 1
        entry.set(args.field, int(args.value, 0))
    if args.text_index is not None:
        if args.text is None:
            print("[error] --text-index needs --text", file=sys.stderr)
            return 1
        entry.set_text(args.text_index, args.text)
    kernel.save(args.output or args.input)
    print(f"[ok] Section {args.section} entry {args.entry} updated, written to {args.output or args.input}")
    return 0


def _cmd_export_csv(args) -> int:
    kernel = _KernelFile(args.input)
    config = kernel.config(args.section)
    text_labels = config.get("text_labels", [])
    field_names = [field["name"] for field in config.get("fields", [])]
    header = ["Entry"] + [f"text:{label}" for label in text_labels] + field_names
    rows = []
    for index, entry in enumerate(kernel.entries(args.section)):
        row = [index]
        row.extend(entry.get_text(text_index) for text_index in range(len(text_labels)))
        row.extend(entry.get(name) for name in field_names)
        rows.append(row)
    write_csv(args.output, header, rows)
    print(f"[ok] Section {args.section}: {len(rows)} entries exported to {args.output}")
    return 0


def _cmd_import_csv(args) -> int:
    kernel = _KernelFile(args.input)
    config = kernel.config(args.section)
    text_labels = config.get("text_labels", [])
    field_names = [field["name"] for field in config.get("fields", [])]
    entries = kernel.entries(args.section)
    applied = 0
    for row in read_csv(args.csv):
        if not row or not str(row[0]).strip():
            continue
        entry = entries[int(row[0])]
        for text_index in range(len(text_labels)):
            # Only touch changed strings: rewriting an identical text would
            # re-encode it (vanilla kernel text is compressed) for nothing.
            if row[1 + text_index] != entry.get_text(text_index):
                entry.set_text(text_index, row[1 + text_index])
        for field_index, name in enumerate(field_names):
            cell = row[1 + len(text_labels) + field_index]
            if str(cell).strip() and int(cell) != entry.get(name):
                entry.set(name, int(cell))
        applied += 1
    kernel.save(args.output or args.input)
    print(f"[ok] Section {args.section}: {applied} entries applied, written to {args.output or args.input}")
    return 0


class SolomonRingCliTool(BaseCliTool):
    """CLI tool for kernel.bin field-level editing."""

    @property
    def name(self) -> str:
        return "solomon-ring"

    @property
    def description(self) -> str:
        return "kernel.bin editor: list/get/set fields and export/import sections as CSV"

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="ff8-cli solomon-ring",
            description="Headless kernel.bin editor (same data-driven model as the SolomonRing GUI)",
        )
        sub = parser.add_subparsers(dest="command", required=True)

        p_sections = sub.add_parser("list-sections", help="List the editable kernel sections")
        p_sections.set_defaults(func=_cmd_list_sections)

        p_fields = sub.add_parser("list-fields", help="List the fields of a section")
        p_fields.add_argument("--section", "-s", type=int, required=True, help="Section id (1-31)")
        p_fields.set_defaults(func=_cmd_list_fields)

        p_get = sub.add_parser("get", help="Print an entry (all fields, or one field/text)")
        p_get.add_argument("--input", "-i", required=True, help="Path to kernel.bin")
        p_get.add_argument("--section", "-s", type=int, required=True, help="Section id (1-31)")
        p_get.add_argument("--entry", "-e", type=int, required=True, help="Entry index in the section")
        p_get.add_argument("--field", help="Print only this field")
        p_get.add_argument("--text-index", type=int, help="Print only this text (0=Name, 1=Description)")
        p_get.set_defaults(func=_cmd_get)

        p_set = sub.add_parser("set", help="Set one field and/or text of an entry")
        p_set.add_argument("--input", "-i", required=True, help="Path to kernel.bin")
        p_set.add_argument("--section", "-s", type=int, required=True, help="Section id (1-31)")
        p_set.add_argument("--entry", "-e", type=int, required=True, help="Entry index in the section")
        p_set.add_argument("--field", help="Field name (see list-fields)")
        p_set.add_argument("--value", help="Field value (decimal or 0x hex)")
        p_set.add_argument("--text-index", type=int, help="Text index (0=Name, 1=Description)")
        p_set.add_argument("--text", help="New text value")
        p_set.add_argument("--output", "-o", help="Output kernel.bin (overwrites input if omitted)")
        p_set.set_defaults(func=_cmd_set)

        p_export = sub.add_parser("export-csv", help="Export one section to CSV")
        p_export.add_argument("--input", "-i", required=True, help="Path to kernel.bin")
        p_export.add_argument("--section", "-s", type=int, required=True, help="Section id (1-31)")
        p_export.add_argument("--output", "-o", required=True, help="Output CSV path")
        p_export.set_defaults(func=_cmd_export_csv)

        p_import = sub.add_parser("import-csv", help="Apply a section CSV onto a kernel.bin")
        p_import.add_argument("--input", "-i", required=True, help="Path to the base kernel.bin")
        p_import.add_argument("--section", "-s", type=int, required=True, help="Section id (1-31)")
        p_import.add_argument("--csv", "-c", required=True, help="CSV produced by export-csv")
        p_import.add_argument("--output", "-o", help="Output kernel.bin (overwrites input if omitted)")
        p_import.set_defaults(func=_cmd_import_csv)

        return parser

    def execute(self, args: argparse.Namespace) -> int:
        try:
            return args.func(args)
        except Exception as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1
