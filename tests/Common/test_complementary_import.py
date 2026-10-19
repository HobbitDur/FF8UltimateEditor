"""Complementary imports choose a file type before opening its own picker."""
import os

import pytest
from PyQt6.QtWidgets import QApplication, QFileDialog, QMenu, QStackedWidget, QWidget

from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from Common.filetoolbarwidget import FileToolbarWidget


@pytest.fixture
def toolbar():
    app = QApplication.instance() or QApplication([])
    registry = FileRegistry()
    tool = QWidget()
    tool.inputs = []
    tool.file_bindings = lambda: tool.inputs
    stack = QStackedWidget()
    stack.addWidget(tool)
    bar = FileToolbarWidget(stack, registry)
    yield bar, tool, registry
    bar.close()
    stack.close()
    bar.deleteLater()
    stack.deleteLater()
    app.processEvents()


@pytest.mark.parametrize('side_is_editable', [False, True])
def test_complementary_menu_opens_only_the_chosen_file_type(toolbar, monkeypatch, tmp_path, side_is_editable):
    bar, tool, registry = toolbar
    loaded = []
    tool.inputs = [
        FileBinding('FF8 exe', registry, load_callback=lambda path: loaded.append(('exe', path)), file_filter='*.exe'),
        FileBinding('kernel.bin', registry, load_callback=lambda path: loaded.append(('kernel', path)), read_only=True),
        FileBinding('wmx.obj', registry, load_callback=lambda path: loaded.append(('wmx', path)),
                    read_only=not side_is_editable, complementary=side_is_editable),
    ]
    previous_folder = str(tmp_path / 'previous-terrain')
    selected = str(tmp_path / 'other-folder' / 'wmx.obj')
    registry.remember_folder('wmx.obj', previous_folder)
    dialogs, menus = [], []

    def pick_file(**kwargs):
        dialogs.append(kwargs)
        return selected, ''

    def choose_terrain(menu, position):
        actions = menu.actions()
        menus.append([action.text() for action in actions])
        assert not dialogs  # choosing the type precedes opening a file dialog
        actions[1].trigger()

    monkeypatch.setattr(QFileDialog, 'getOpenFileName', pick_file)
    monkeypatch.setattr(QMenu, 'exec', choose_terrain)
    bar._refresh()
    bar.import_complementary_button.click()
    assert menus == [['kernel.bin', 'wmx.obj']]
    assert len(dialogs) == 1
    assert dialogs[0]['caption'] == 'Open wmx.obj'
    assert dialogs[0]['filter'] == 'wmx.obj'
    assert dialogs[0]['directory'] == previous_folder
    assert loaded == [('wmx', selected)]
    assert registry.get_path('wmx.obj') == selected
    assert not registry.get_path('kernel.bin') and not registry.get_path('FF8 exe')
    assert registry.last_folder('wmx.obj') == os.path.dirname(selected)


def test_one_complementary_file_opens_directly_and_cancel_preserves_state(toolbar, monkeypatch, tmp_path):
    bar, tool, registry = toolbar
    binding = FileBinding('kernel.bin', registry, read_only=True)
    tool.inputs = [binding]
    folder = str(tmp_path)
    registry.remember_folder('kernel.bin', folder)
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda **kwargs: ('', ''))
    bar._refresh()
    bar.import_complementary_button.click()
    assert not registry.get_path('kernel.bin')
    assert registry.last_folder('kernel.bin') == folder


def test_custom_complementary_choices_still_use_their_own_callbacks(toolbar, monkeypatch):
    bar, tool, registry = toolbar
    opened = []
    tool.complementary_entries = lambda: [('Model', lambda: opened.append('model')),
                                           ('Skeleton', lambda: opened.append('skeleton'))]

    def choose_skeleton(menu, position):
        assert [action.text() for action in menu.actions()] == ['Model', 'Skeleton']
        menu.actions()[1].trigger()

    monkeypatch.setattr(QMenu, 'exec', choose_skeleton)
    bar._refresh()
    bar.import_complementary_button.click()
    assert opened == ['skeleton'] and not registry.paths
