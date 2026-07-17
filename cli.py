"""
Main CLI entry point for FF8 Ultimate Editor tools.

This module serves as the central dispatcher for all CLI tools,
allowing users to run different tools through a unified interface.

Usage:
    python cli.py [tool-name] [tool-command] [arguments...]

Examples:
    python cli.py shumi-translator export-csv --input kernel.bin --output kernel.csv
    python cli.py shumi-translator import-csv --input kernel.bin --csv kernel.csv
"""

import argparse
import sys
from typing import Dict, Type

from Cli.base import BaseCliTool
from Cli.registry import get_registry, register_tool
from Cli.shumi_translator import ShumiTranslatorCliTool
from Cli.ifrit_ai import IfritAiCliTool
from Cli.ifrit_model import IfritModelCliTool
from Cli.tonberry_shop import TonberryShopCliTool
from Cli.siren import SirenCliTool
from Cli.junkshop import JunkshopCliTool
from Cli.quezacotl import QuezacotlCliTool
from Cli.minimog import MinimogCliTool
from Cli.shiva import ShivaCliTool
from Cli.ccgroup import CCGroupCliTool
from Cli.cid import CidCliTool
from Cli.julia import JuliaCliTool
from Cli.solomon_ring import SolomonRingCliTool
from Cli.alexander import AlexanderCliTool
from Cli.seed import SeedCliTool
from Cli.odine import OdineCliTool
from Cli.kadowaki import KadowakiCliTool
from Cli.zone import ZoneCliTool
from Cli.moomba import MoombaCliTool
from Cli.joker import JokerCliTool
from Cli.piet import PietCliTool
from Cli.watts import WattsCliTool


def _register_all_tools():
    """Register all available CLI tools."""
    registry = get_registry()
    registry.register(ShumiTranslatorCliTool)
    registry.register(IfritAiCliTool)
    registry.register(IfritModelCliTool)
    registry.register(TonberryShopCliTool)
    registry.register(SirenCliTool)
    registry.register(JunkshopCliTool)
    registry.register(QuezacotlCliTool)
    registry.register(MinimogCliTool)
    registry.register(ShivaCliTool)
    registry.register(CCGroupCliTool)
    registry.register(CidCliTool)
    registry.register(JuliaCliTool)
    registry.register(SolomonRingCliTool)
    registry.register(AlexanderCliTool)
    registry.register(SeedCliTool)
    registry.register(OdineCliTool)
    registry.register(KadowakiCliTool)
    registry.register(ZoneCliTool)
    registry.register(MoombaCliTool)
    registry.register(JokerCliTool)
    registry.register(PietCliTool)
    registry.register(WattsCliTool)


def build_main_parser() -> argparse.ArgumentParser:
    """Build the main CLI argument parser."""
    registry = get_registry()
    tools_info = registry.list_tools()

    # Create main parser
    parser = argparse.ArgumentParser(
        prog="ff8-cli",
        description="FF8 Ultimate Editor — Unified CLI for text editing and data manipulation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Available tools:
{chr(10).join(f'  {name}: {desc}' for name, desc in sorted(tools_info.items()))}

Examples:
  ff8-cli shumi-translator export-csv --input kernel.bin --output kernel.csv
  ff8-cli solomon-ring set --input kernel.bin --section 2 --entry 1 --field atk_power --value 30
  ff8-cli siren set-price --input price.bin --item-id 24 --buy-price 3000
  ff8-cli ifrit export-gltf --input c0m071.dat --output c0m071.glb
  ff8-cli alexander export-glb --input a0stg001.x --output stage.glb
  ff8-cli ccgroup list --folder extracted_files/field/mapdata
        """,
    )

    # Main subparsers for tool selection
    subparsers = parser.add_subparsers(dest="tool", required=True, help="Tool to use")

    # Register each tool's subparser
    for name, tool_class in registry.get_all().items():
        tool = tool_class()
        tool_parser = tool.build_parser()

        # Create a wrapper subparser that will handle the tool
        tool_subparsers = subparsers.add_parser(
            name,
            help=tool.description,
            add_help=False,  # Don't add automatic help to avoid conflicts
        )

        # Copy the tool's subparsers to the main parser
        # This is a bit tricky, so we'll store a reference to the tool and its parser
        tool_subparsers._tool_instance = tool
        tool_subparsers._tool_parser = tool_parser

    return parser


def main():
    """Main CLI entry point."""
    # Register all tools first
    _register_all_tools()

    # Build and parse arguments
    parser = build_main_parser()

    # Custom argument parsing to handle nested subparsers
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        parser.print_help()
        sys.exit(0)

    tool_name = sys.argv[1]
    registry = get_registry()
    tool_class = registry.get(tool_name)

    if tool_class is None:
        print(f"[error] Unknown tool '{tool_name}'", file=sys.stderr)
        print(f"\nAvailable tools:", file=sys.stderr)
        for name, desc in sorted(registry.list_tools().items()):
            print(f"  {name}: {desc}", file=sys.stderr)
        sys.exit(1)

    # Instantiate tool and build its parser
    tool = tool_class()
    tool_parser = tool.build_parser()

    # Parse remaining arguments with the tool's parser
    try:
        tool_args = tool_parser.parse_args(sys.argv[2:])
        exit_code = tool.execute(tool_args)
        sys.exit(exit_code if exit_code is not None else 0)
    except SystemExit as e:
        # argparse calls sys.exit on error
        sys.exit(e.code)
    except Exception as e:
        print(f"[error] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()


