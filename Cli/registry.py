"""
CLI Tool Registry.

Manages registration and discovery of available CLI tools.
"""

from typing import Dict, Type, Optional
from .base import BaseCliTool


class CliToolRegistry:
    """
    Registry for managing available CLI tools.

    Usage:
        registry = CliToolRegistry()
        registry.register(MyTool)
        tool = registry.get("my-tool")
    """

    _instance: Optional["CliToolRegistry"] = None

    def __init__(self):
        """Initialize the registry."""
        self._tools: Dict[str, Type[BaseCliTool]] = {}

    @classmethod
    def instance(cls) -> "CliToolRegistry":
        """Get or create singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, tool_class: Type[BaseCliTool]) -> None:
        """
        Register a CLI tool.

        Args:
            tool_class: Class inheriting from BaseCliTool.

        Raises:
            ValueError: If a tool with the same name is already registered.
        """
        # Instantiate to get metadata
        tool = tool_class()
        name = tool.name

        if name in self._tools:
            raise ValueError(f"Tool '{name}' is already registered.")

        self._tools[name] = tool_class

    def get(self, name: str) -> Optional[Type[BaseCliTool]]:
        """
        Get a tool class by name.

        Args:
            name: Tool name/identifier.

        Returns:
            Tool class if found, None otherwise.
        """
        return self._tools.get(name)

    def list_tools(self) -> Dict[str, str]:
        """
        Get all registered tools with their descriptions.

        Returns:
            Dict mapping tool names to descriptions.
        """
        result = {}
        for name, tool_class in self._tools.items():
            tool = tool_class()
            result[name] = tool.description
        return result

    def get_all(self) -> Dict[str, Type[BaseCliTool]]:
        """Get all registered tools."""
        return dict(self._tools)


# Global registry instance
_registry = CliToolRegistry.instance()


def register_tool(tool_class: Type[BaseCliTool]) -> None:
    """Register a tool globally."""
    _registry.register(tool_class)


def get_registry() -> CliToolRegistry:
    """Get the global registry instance."""
    return _registry

