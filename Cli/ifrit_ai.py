"""
IfritAI CLI Tool.

Headless command-line interface for monster AI editing:
  • export-md   (c0mXXX.dat → md file with the 5 AI sections)
  • compile-md  (base c0mXXX.dat + md file → new c0mXXX.dat)

Mirrors the exact load/compile sequence of the IfritAI GUI widget
(IfritManager + IfritAiWidget) without any Qt dependency.
"""

import argparse
import pathlib
import sys

from .base import BaseCliTool


def _load_game_data():
    from FF8GameData.gamedata import GameData
    gd = GameData(str(pathlib.Path(__file__).resolve().parent.parent / "FF8GameData"))
    gd.load_all()
    return gd


def _load_enemy(dat_path: str):
    """Replicate IfritManager's init sequence headlessly.

    Returns (enemy, compiler, decompiler) with the file loaded and analysed.
    """
    from FF8GameData.dat.monsteranalyser import MonsterAnalyser
    from Ifrit.IfritAI.AICompiler.AICompiler import AICompiler
    from Ifrit.IfritAI.AICompiler.AIDecompiler import AIDecompiler

    game_data = _load_game_data()
    dummy = MonsterAnalyser(game_data)
    compiler = AICompiler(game_data, dummy.battle_script_data['battle_text'], dummy.info_stat_data)
    decompiler = AIDecompiler(game_data, dummy.battle_script_data['battle_text'], dummy.info_stat_data)

    enemy = MonsterAnalyser(game_data)
    enemy.load_file_data(dat_path, game_data)
    enemy.analyse_loaded_data(game_data, decompiler)
    compiler.set_battle_text_info_stat(enemy.battle_script_data['battle_text'], enemy.info_stat_data)
    return game_data, enemy, compiler, decompiler


def _ai_data_to_md(game_data, ai_data, decompiler) -> str:
    """Same output as IfritAiWidget.create_md_from_ai_data."""
    from FF8GameData.dat.sectionfiles import aifile
    return aifile.ai_data_to_md(ai_data, decompiler)


def _md_to_ai_data(md_file: str, enemy, compiler, decompiler):
    """Same behaviour as IfritAiWidget.create_ai_data_from_md."""
    from FF8GameData.dat.sectionfiles import aifile
    content = pathlib.Path(md_file).read_text(encoding='utf-8')
    code_blocks = aifile.md_to_code_blocks(content)
    if not code_blocks:
        print(f"[error] No ``` code blocks found in {md_file}", file=sys.stderr)
        sys.exit(1)
    for index_code, code in enumerate(code_blocks):
        enemy.battle_script_data['ai_data'][index_code] = aifile.compile_code(code, compiler, decompiler)


class IfritAiCliTool(BaseCliTool):
    """CLI tool for monster AI md export / compile."""

    @property
    def name(self) -> str:
        return "ifrit-ai"

    @property
    def description(self) -> str:
        return "Monster AI: export .dat AI to md, or compile md back into a .dat"

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="ff8-cli ifrit-ai",
            description="Headless monster AI md export / compile (same engine as the IfritAI GUI)",
        )
        sub = parser.add_subparsers(dest="command", required=True)

        p_export = sub.add_parser("export-md", help="Export the AI sections of a c0mXXX.dat to a md file")
        p_export.add_argument("--input", required=True, help="Path to the monster .dat file")
        p_export.add_argument("--output", help="Output md path (default: <input>.md next to the dat)")

        p_compile = sub.add_parser("compile-md", help="Compile a md file into a copy of a base c0mXXX.dat")
        p_compile.add_argument("--input", required=True, help="Path to the base monster .dat file")
        p_compile.add_argument("--md", required=True, help="Path to the md file with the AI code blocks")
        p_compile.add_argument("--output", required=True, help="Path of the .dat to write (can equal --input)")

        return parser

    def execute(self, args: argparse.Namespace) -> int:
        if args.command == "export-md":
            return self._export_md(args)
        if args.command == "compile-md":
            return self._compile_md(args)
        print(f"[error] Unknown command {args.command}", file=sys.stderr)
        return 1

    @staticmethod
    def _export_md(args) -> int:
        game_data, enemy, compiler, decompiler = _load_enemy(args.input)
        output = args.output or str(pathlib.Path(args.input).with_suffix(".md"))
        md_text = _ai_data_to_md(game_data, enemy.battle_script_data['ai_data'], decompiler)
        pathlib.Path(output).write_text(md_text, encoding='utf-8')
        print(f"[ok] AI exported to {output}")
        return 0

    @staticmethod
    def _compile_md(args) -> int:
        from FF8GameData.dat.daterrors import AICodeError

        game_data, enemy, compiler, decompiler = _load_enemy(args.input)
        try:
            _md_to_ai_data(args.md, enemy, compiler, decompiler)
            if AICodeError.has_errors():
                print(AICodeError.format_errors_for_display(), file=sys.stderr)
                AICodeError.clear_errors()
                return 1
        except AICodeError:
            print(AICodeError.format_errors_for_display(), file=sys.stderr)
            AICodeError.clear_errors()
            return 1
        enemy.write_data_to_file(game_data, args.output)
        print(f"[ok] Compiled {args.md} into {args.output}")
        return 0
