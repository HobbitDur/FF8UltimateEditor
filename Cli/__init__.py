"""
FF8 Ultimate Editor CLI Package.

This package provides a modular, extensible CLI architecture for multiple tools.
"""

from .base import BaseCliTool
from .registry import CliToolRegistry

__all__ = ["BaseCliTool", "CliToolRegistry"]

