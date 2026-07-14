"""
Ifrit CLI Tool (monster .dat — non-AI parts; AI has its own 'ifrit-ai' tool).

Headless monster editing, same operations as the Ifrit GUI tabs:
  • export-xlsx    (c0m .dat file(s) → one Excel workbook, Stat/StatExcel tab data)
  • import-xlsx    (Excel workbook → the matching c0m .dat files, in place)
  • export-gltf    (c0m .dat → .glb: mesh, skeleton, every animation; no textures)
  • import-gltf    (.glb mesh → back into a c0m .dat; other sections preserved)
  • export-seq-xml (section 5 animation sequences → XML)
  • import-seq-xml (XML → section 5 of a c0m .dat)
"""

import argparse
import pathlib
import re
import sys

from .base import BaseCliTool
from .common import PROJECT_ROOT


class _Holder:
    """Minimal stand-in for IfritManager so GltfExporter can read the model
    without Qt textures (same trick as roundtrip_gltf.py)."""

    def __init__(self, enemy):
        self.enemy = enemy
        self.texture_data = []  # exporter falls back to a flat material


def _load_enemy(dat_path: str):
    """Headless monster load (no QApplication, no textures)."""
    from FF8GameData.gamedata import GameData
    from FF8GameData.dat.monsteranalyser import MonsterAnalyser
    from Ifrit.IfritAI.AICompiler.AIDecompiler import AIDecompiler

    game_data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    game_data.load_all()
    decompiler = AIDecompiler(game_data, [], None)
    enemy = MonsterAnalyser(game_data)
    enemy.load_file_data(dat_path, game_data)
    enemy.analyse_loaded_data(game_data, decompiler)
    return game_data, enemy


def _collect_dat_files(inputs) -> list:
    """Expand --input values: each may be a c0mNNN.dat file or a folder of them.

    Folder scans keep only canonical c0mNNN.dat names: the xlsx manager derives
    the monster id from the filename and chokes on anything else."""
    files = []
    for value in inputs:
        path = pathlib.Path(value)
        if path.is_dir():
            files.extend(sorted(str(p) for p in path.glob("c0m*.dat")
                                if re.fullmatch(r"c0m\d{3}\.dat", p.name)))
        else:
            files.append(str(path))
    if not files:
        raise ValueError("No .dat file found in the given input(s)")
    return files


def _ifrit_manager():
    from Ifrit.ifritmanager import IfritManager
    return IfritManager(game_data_folder=str(PROJECT_ROOT / "FF8GameData"))


def _cmd_export_xlsx(args) -> int:
    manager = _ifrit_manager()
    files = _collect_dat_files(args.input)
    manager.create_xlsx_file(args.output)
    manager.dat_to_xlsx(files, analyse_ai=args.ai)
    print(f"[ok] {len(files)} .dat file(s) exported to {args.output} "
          "(garbage ids 0/127/>143 skipped)")
    return 0


def _cmd_import_xlsx(args) -> int:
    from Ifrit.IfritXlsx import xlsxmanager
    manager = _ifrit_manager()
    files = _collect_dat_files([args.dat_dir])
    manager.load_xlsx_file(args.xlsx)
    if args.monster_ids:
        monster_ids = tuple(args.monster_ids)
    else:
        monster_ids = tuple(
            int(re.search(r"\d+", sheet.title).group())
            for sheet in manager._xlsx_to_dat_manager.workbook
            if sheet.title != xlsxmanager.REF_DATA_SHEET_TITLE)
    manager.xlsx_to_dat(files, monster_ids)
    manager.close_xlsx_file()
    print(f"[ok] Monsters {sorted(monster_ids)} imported from {args.xlsx} into {args.dat_dir} (in place)")
    return 0


def _cmd_export_gltf(args) -> int:
    from Ifrit.Ifrit3D.gltfexporter import GltfExporter
    _, enemy = _load_enemy(args.input)
    GltfExporter(_Holder(enemy)).export(args.output)
    print(f"[ok] {args.input} exported to {args.output} (mesh + skeleton + animations, no textures)")
    return 0


def _cmd_import_gltf(args) -> int:
    from Ifrit.Ifrit3D.gltfimporter import GltfImporter
    game_data, enemy = _load_enemy(args.input)
    stats = GltfImporter().import_into_enemy(args.glb, enemy)
    enemy.write_data_to_file(game_data, args.output)
    print(f"[ok] Mesh imported ({stats['vertices']} vertices, {stats['triangles']} triangles, "
          f"{stats['bones_used']} bones), written to {args.output}")
    return 0


def _cmd_export_seq_xml(args) -> int:
    from Ifrit.IfritSeq.ifritseqwidget import IfritSeqWidget
    _, enemy = _load_enemy(args.input)
    IfritSeqWidget.create_anim_seq_xml(enemy.seq_animation_data['seq_animation_data'], args.output)
    nb = len(enemy.seq_animation_data['seq_animation_data'])
    print(f"[ok] {nb} animation sequences exported to {args.output}")
    return 0


def _cmd_import_seq_xml(args) -> int:
    from Ifrit.IfritSeq.ifritseqwidget import IfritSeqWidget
    game_data, enemy = _load_enemy(args.input)
    seq_data = IfritSeqWidget.create_anim_seq_data_from_xml(args.xml)
    if not seq_data:
        print(f"[error] No animation sequences found in {args.xml}", file=sys.stderr)
        return 1
    enemy.seq_animation_data['seq_animation_data'] = seq_data
    enemy.write_data_to_file(game_data, args.output)
    print(f"[ok] {len(seq_data)} animation sequences imported, written to {args.output}")
    return 0


class IfritModelCliTool(BaseCliTool):
    """CLI tool for monster .dat model/stat/seq editing (AI lives in 'ifrit-ai')."""

    @property
    def name(self) -> str:
        return "ifrit"

    @property
    def description(self) -> str:
        return "Monster editor: xlsx stats export/import, glTF mesh export/import, seq XML"

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="ff8-cli ifrit",
            description="Headless monster .dat editor (same operations as the Ifrit GUI tabs; "
                        "AI editing is in the separate 'ifrit-ai' tool)",
        )
        sub = parser.add_subparsers(dest="command", required=True)

        p_xlsx_out = sub.add_parser("export-xlsx", help="Export monster stats to an Excel workbook")
        p_xlsx_out.add_argument("--input", "-i", nargs="+", required=True,
                                help="c0mNNN.dat file(s) and/or a folder containing them")
        p_xlsx_out.add_argument("--output", "-o", required=True, help="Output .xlsx path")
        p_xlsx_out.add_argument("--ai", action="store_true", help="Also dump the AI code in each sheet")
        p_xlsx_out.set_defaults(func=_cmd_export_xlsx)

        p_xlsx_in = sub.add_parser("import-xlsx", help="Apply an Excel workbook onto the c0m .dat files (in place)")
        p_xlsx_in.add_argument("--xlsx", "-x", required=True, help="Workbook produced by export-xlsx")
        p_xlsx_in.add_argument("--dat-dir", "-d", required=True, help="Folder containing the c0mNNN.dat files")
        p_xlsx_in.add_argument("--monster-ids", type=int, nargs="+",
                               help="Only these monster ids (default: every sheet in the workbook)")
        p_xlsx_in.set_defaults(func=_cmd_import_xlsx)

        p_gltf_out = sub.add_parser("export-gltf", help="Export a monster to .glb (mesh/skeleton/animations)")
        p_gltf_out.add_argument("--input", "-i", required=True, help="Path to the c0mNNN.dat")
        p_gltf_out.add_argument("--output", "-o", required=True, help="Output .glb path")
        p_gltf_out.set_defaults(func=_cmd_export_gltf)

        p_gltf_in = sub.add_parser("import-gltf", help="Import a .glb mesh back into a c0m .dat")
        p_gltf_in.add_argument("--input", "-i", required=True, help="Path to the base c0mNNN.dat")
        p_gltf_in.add_argument("--glb", "-g", required=True, help=".glb previously exported (mesh may be edited)")
        p_gltf_in.add_argument("--output", "-o", required=True, help="Path of the .dat to write (can equal --input)")
        p_gltf_in.set_defaults(func=_cmd_import_gltf)

        p_seq_out = sub.add_parser("export-seq-xml", help="Export the section-5 animation sequences to XML")
        p_seq_out.add_argument("--input", "-i", required=True, help="Path to the c0mNNN.dat")
        p_seq_out.add_argument("--output", "-o", required=True, help="Output .xml path")
        p_seq_out.set_defaults(func=_cmd_export_seq_xml)

        p_seq_in = sub.add_parser("import-seq-xml", help="Import an animation-sequence XML into a c0m .dat")
        p_seq_in.add_argument("--input", "-i", required=True, help="Path to the base c0mNNN.dat")
        p_seq_in.add_argument("--xml", "-x", required=True, help="XML produced by export-seq-xml")
        p_seq_in.add_argument("--output", "-o", required=True, help="Path of the .dat to write (can equal --input)")
        p_seq_in.set_defaults(func=_cmd_import_seq_xml)

        return parser

    def execute(self, args: argparse.Namespace) -> int:
        try:
            return args.func(args)
        except Exception as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1
