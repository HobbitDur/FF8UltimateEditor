"""
TEMPLATE: CLI Tool Implementation Example

This file serves as a template for creating new CLI tools.
Copy this file and modify it to create your own tool.

To add a new tool:
1. Copy this file to Cli/your_tool_name.py
2. Rename the class from TemplateCliTool to YourToolCliTool
3. Update the name, description, and implement the subcommands
4. Import and register the tool in cli.py
"""

import argparse
import sys

from .base import BaseCliTool


# ---------------------------------------------------------------------------
# Command Handlers
# ---------------------------------------------------------------------------

def _cmd_example_command(args):
    """Example command handler."""
    print(f"[example-command] Running with args: {args}")
    # Your implementation here


def _cmd_another_command(args):
    """Another example command handler."""
    print(f"[another-command] Running with args: {args}")
    # Your implementation here


# ---------------------------------------------------------------------------
# Tool Class
# ---------------------------------------------------------------------------

class TemplateCliTool(BaseCliTool):
    """
    Example CLI tool template.

    This class demonstrates how to structure a CLI tool.
    Copy and modify this template to create new tools.
    """

    @property
    def name(self) -> str:
        """Unique tool identifier (e.g., 'my-tool')."""
        return "template-tool"

    @property
    def description(self) -> str:
        """Human-readable description."""
        return "Template Tool - Use this as a starting point for new tools"

    def build_parser(self) -> argparse.ArgumentParser:
        """Build and configure argument parser with subcommands."""
        parser = argparse.ArgumentParser(
            prog="ff8-cli template-tool",
            description="Template Tool — Example CLI implementation",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  ff8-cli template-tool example-command --input file.txt
  ff8-cli template-tool another-command
            """,
        )

        # Create subcommands
        sub = parser.add_subparsers(dest="command", required=True)

        # Subcommand 1: example-command
        p_example = sub.add_parser(
            "example-command",
            help="Do something with a file"
        )
        p_example.add_argument(
            "--input", "-i",
            required=True,
            help="Input file path"
        )
        p_example.add_argument(
            "--output", "-o",
            help="Output file path (optional)"
        )
        p_example.set_defaults(func=_cmd_example_command)

        # Subcommand 2: another-command
        p_another = sub.add_parser(
            "another-command",
            help="Do something else"
        )
        p_another.add_argument(
            "--verbose", "-v",
            action="store_true",
            help="Enable verbose output"
        )
        p_another.set_defaults(func=_cmd_another_command)

        return parser

    def execute(self, args: argparse.Namespace) -> int:
        """Execute the selected command."""
        try:
            if not hasattr(args, 'func'):
                print(f"[error] No command specified", file=sys.stderr)
                return 1

            # Call the appropriate handler
            args.func(args)
            return 0

        except Exception as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1


# ---------------------------------------------------------------------------
# Integration Instructions
# ---------------------------------------------------------------------------
"""
To use this template:

1. Create a new file: Cli/my_tool.py
2. Copy this template and modify:
   - Change 'template-tool' to your tool name
   - Change 'TemplateCliTool' to your class name
   - Update command handlers with your logic
   - Add/remove subcommands as needed

3. Update cli.py:
   ```python
   from Cli.my_tool import MyToolCliTool
   
   def _register_all_tools():
       registry = get_registry()
       registry.register(ShumiTranslatorCliTool)
       registry.register(MyToolCliTool)  # Add this line
   ```

4. Test your tool:
   python cli.py my-tool example-command --help
   python cli.py my-tool example-command --input myfile.txt
"""

