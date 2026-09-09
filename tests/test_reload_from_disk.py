"""The shared-toolbar Reload button (Common/filetoolbarwidget.py) re-reads the files the ACTIVE
tool is using, and only those: its own FileBindings (writable and read-only alike) plus, for a
tool whose files have no fixed FF8 name and so no binding, its reload_files() hook. Files another
tool has open are deliberately left untouched, so reloading in one tool cannot discard edits
sitting in another.

Ifrit is the hook case: an Alexander-pattern tool with no per-file FileBinding, it implements
reload_files() / can_reload_files(). These tests lock in that it reloads all of its own files and
keeps the single-live-GL-context guarantee, and that the toolbar scopes Reload to one tool.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QStackedWidget, QWidget
from PyQt6.QtCore import QSettings
_APP = QApplication.instance() or QApplication([])

from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from Common.filetoolbarwidget import FileToolbarWidget
from Ifrit.ifritmanager import IfritManager
from Ifrit.ifritmonsterwidget import IfritMonsterWidget

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BATTLE = os.path.join(REPO, "extracted_files", "battle")
MONSTER_FILES = [os.path.join(BATTLE, f"c0m{i:03d}.dat") for i in range(4)]


# ---------------------------------------------------------------- toolbar scoping

class _ToolWithFile(QWidget):
    """Minimal tool: one binding, counting how often its file is (re)loaded."""

    def __init__(self, file_name, registry):
        QWidget.__init__(self)
        self.loads = 0
        self.binding = FileBinding(file_name, registry, load_callback=self._load)

    def _load(self, _path):
        self.loads += 1

    def file_bindings(self):
        return [self.binding]


def _toolbar_with_two_tools(tmp_path):
    registry = FileRegistry()
    stack = QStackedWidget()
    tool_a = _ToolWithFile("a.bin", registry)
    tool_b = _ToolWithFile("b.bin", registry)
    stack.addWidget(tool_a)
    stack.addWidget(tool_b)
    toolbar = FileToolbarWidget(stack, registry, icon_path=os.path.join(REPO, "Resources"))
    for name, tool in (("a.bin", tool_a), ("b.bin", tool_b)):
        path = tmp_path / name
        path.write_bytes(b"\x00")
        registry.open_file(name, str(path))
    tool_a.loads = tool_b.loads = 0        # ignore the initial load
    return toolbar, stack, tool_a, tool_b


def test_reload_only_touches_the_active_tools_files(tmp_path):
    toolbar, stack, tool_a, tool_b = _toolbar_with_two_tools(tmp_path)
    stack.setCurrentWidget(tool_a)

    toolbar._reload()                                  # what the toolbar button does

    assert tool_a.loads == 1                           # the active tool re-read its file
    assert tool_b.loads == 0                           # the other tool was left alone


def test_reload_follows_the_active_tool(tmp_path):
    toolbar, stack, tool_a, tool_b = _toolbar_with_two_tools(tmp_path)
    stack.setCurrentWidget(tool_b)

    toolbar._reload()

    assert tool_b.loads == 1
    assert tool_a.loads == 0


def test_reload_button_greys_out_when_the_active_tool_has_no_file(tmp_path):
    registry = FileRegistry()
    stack = QStackedWidget()
    loaded = _ToolWithFile("a.bin", registry)
    empty = _ToolWithFile("b.bin", registry)
    stack.addWidget(loaded)
    stack.addWidget(empty)
    toolbar = FileToolbarWidget(stack, registry, icon_path=os.path.join(REPO, "Resources"))
    path = tmp_path / "a.bin"
    path.write_bytes(b"\x00")
    registry.open_file("a.bin", str(path))             # only the first tool's file is open

    stack.setCurrentWidget(loaded)
    toolbar._refresh()
    assert toolbar.reload_button.isEnabled()

    stack.setCurrentWidget(empty)                      # a file IS open in the registry, but not
    toolbar._refresh()                                 # one this tool uses
    assert not toolbar.reload_button.isEnabled()


# ---------------------------------------------------------------- Ifrit's hook

ifrit_only = pytest.mark.skipif(
    not all(os.path.isfile(p) for p in MONSTER_FILES),
    reason="c0m000-c0m003.dat not available")


def _make_widget(name, registry):
    settings = QSettings("test", name)
    settings.setValue("ifrit/ram_budget_gb", 6)     # preload all 4
    base = IfritManager("FF8GameData")
    w = IfritMonsterWidget(settings=settings, icon_path="Resources",
                           game_data_folder="FF8GameData", file_registry=registry)
    w._game_data = base.game_data
    w.show()
    return w


def _live_gl(w):
    return [i for i, f in enumerate(w._files)
            if f['pane'] is not None and f['pane']._3d_widget.gl_widget is not None]


@ifrit_only
def test_ifrit_exposes_the_reload_hooks():
    w = _make_widget("reload_sub", FileRegistry())
    assert callable(getattr(w, "reload_files", None))       # the toolbar calls this
    assert callable(getattr(w, "can_reload_files", None))   # ...and this to grey the button
    assert w.can_reload_files() is False                    # nothing loaded yet


@ifrit_only
def test_reload_reparses_every_file_and_keeps_one_context():
    w = _make_widget("reload_all", FileRegistry())
    w._build_session(MONSTER_FILES)
    w._activate_index(2)
    panes_before = [id(f['pane']) for f in w._files if f['pane'] is not None]
    assert w.can_reload_files() is True

    w.reload_files()                                  # what the toolbar button does

    # every pane got rebuilt from the fresh parse (identities changed)
    panes_after = [id(f['pane']) for f in w._files if f['pane'] is not None]
    assert not (set(panes_before) & set(panes_after))
    # the previously-active file is shown again, with the only live GL context
    assert w._active_index == 2
    assert _live_gl(w) == [2]
    assert all(f['name'] for f in w._files)           # names re-resolved after reparse


@ifrit_only
def test_reload_with_nothing_loaded_is_a_noop():
    w = _make_widget("reload_empty", FileRegistry())
    w.reload_files()                                  # must not raise with no files open
    assert w._files == []
