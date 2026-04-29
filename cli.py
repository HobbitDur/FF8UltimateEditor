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


def _register_all_tools():
    """Register all available CLI tools."""
    registry = get_registry()
    registry.register(ShumiTranslatorCliTool)


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
  ff8-cli shumi-translator import-csv --input kernel.bin --csv kernel.csv
  ff8-cli shumi-translator compress --input kernel.bin --output kernel_compressed.bin
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


