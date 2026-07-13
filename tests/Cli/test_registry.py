"""
Tests for the CLI tool registry and BaseCliTool contract.

These exercise the tool-registration/discovery layer with small in-test tool
classes so they don't depend on any concrete tool's runtime behaviour.
"""
import argparse

import pytest

from Cli.base import BaseCliTool
from Cli.registry import CliToolRegistry
from Cli.template_tool import TemplateCliTool


class DummyTool(BaseCliTool):
    """Minimal concrete tool used to exercise the registry."""

    TOOL_NAME = "dummy-tool"

    @property
    def name(self) -> str:
        return self.TOOL_NAME

    @property
    def description(self) -> str:
        return "A dummy tool for tests"

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(prog=self.name)
        sub = parser.add_subparsers(dest="command", required=True)
        p = sub.add_parser("run")
        p.add_argument("--value", type=int, default=0)
        p.set_defaults(func=lambda args: args.value)
        return parser

    def execute(self, args: argparse.Namespace) -> int:
        return args.func(args)


class OtherDummyTool(DummyTool):
    TOOL_NAME = "other-dummy"

    @property
    def description(self) -> str:
        return "Another dummy tool"


@pytest.fixture
def registry():
    return CliToolRegistry()


class TestRegistry:
    def test_register_and_get(self, registry):
        registry.register(DummyTool)
        assert registry.get("dummy-tool") is DummyTool

    def test_get_unknown_returns_none(self, registry):
        assert registry.get("does-not-exist") is None

    def test_register_duplicate_raises(self, registry):
        registry.register(DummyTool)
        with pytest.raises(ValueError):
            registry.register(DummyTool)

    def test_list_tools_maps_name_to_description(self, registry):
        registry.register(DummyTool)
        registry.register(OtherDummyTool)
        listing = registry.list_tools()
        assert listing == {
            "dummy-tool": "A dummy tool for tests",
            "other-dummy": "Another dummy tool",
        }

    def test_get_all_returns_copy(self, registry):
        registry.register(DummyTool)
        all_tools = registry.get_all()
        assert all_tools == {"dummy-tool": DummyTool}
        # mutating the returned dict must not affect the registry
        all_tools.clear()
        assert registry.get("dummy-tool") is DummyTool

    def test_instance_is_singleton(self):
        assert CliToolRegistry.instance() is CliToolRegistry.instance()


class TestBaseCliToolContract:
    def test_cannot_instantiate_abstract_base(self):
        with pytest.raises(TypeError):
            BaseCliTool()

    def test_concrete_tool_executes_through_parser(self):
        tool = DummyTool()
        args = tool.build_parser().parse_args(["run", "--value", "7"])
        assert tool.execute(args) == 7


class TestTemplateTool:
    """The shipped template tool is a real BaseCliTool subclass and should stay valid."""

    def test_metadata(self):
        tool = TemplateCliTool()
        assert tool.name == "template-tool"
        assert tool.description

    def test_parser_requires_a_subcommand(self):
        tool = TemplateCliTool()
        parser = tool.build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_example_command_parses(self):
        tool = TemplateCliTool()
        parser = tool.build_parser()
        args = parser.parse_args(["example-command", "--input", "file.txt"])
        assert args.input == "file.txt"
        assert hasattr(args, "func")

    def test_execute_runs_selected_command(self):
        tool = TemplateCliTool()
        parser = tool.build_parser()
        args = parser.parse_args(["another-command", "--verbose"])
        assert tool.execute(args) == 0

    def test_is_registrable(self):
        registry = CliToolRegistry()
        registry.register(TemplateCliTool)
        assert registry.get("template-tool") is TemplateCliTool
