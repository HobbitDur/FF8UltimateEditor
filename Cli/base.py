"""
Abstract base class for CLI tools.

Every CLI tool should inherit from BaseCliTool and implement the required methods.
"""

from abc import ABC, abstractmethod
import argparse


class BaseCliTool(ABC):
    """
    Abstract base class for all CLI tools.

    Each tool should:
    1. Define a unique `name` and `description`
    2. Implement `build_parser()` to configure subcommands
    3. Implement `execute()` to run the selected command
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool identifier (e.g., 'shumi-translator')."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of the tool."""
        pass

    @abstractmethod
    def build_parser(self) -> argparse.ArgumentParser:
        """
        Build and return ArgumentParser with tool-specific subcommands.

        Returns:
            ArgumentParser: Parser configured with this tool's subcommands.
        """
        pass

    @abstractmethod
    def execute(self, args: argparse.Namespace) -> int:
        """
        Execute the command with parsed arguments.

        Args:
            args: Parsed command-line arguments.

        Returns:
            int: Exit code (0 for success, non-zero for failure).
        """
        pass

