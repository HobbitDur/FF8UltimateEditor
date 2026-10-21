"""FileRegistry.batch(): many files open at once, the views that list them refresh once at the end."""
import sys

import pytest
from PyQt6.QtWidgets import QApplication

from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from Common.openedfilespanel import OpenedFilesPanel


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def test_bindings_load_at_once_views_refresh_after(qapp, tmp_path, monkeypatch):
    registry = FileRegistry()
    loaded = []
    bindings = []
    for index in range(5):
        path = tmp_path / f"file{index}.bin"
        path.write_bytes(b"x")
        binding = FileBinding(path.name, registry, load_callback=loaded.append)
        bindings.append((binding, str(path)))
    panel = OpenedFilesPanel(registry)
    refreshes = []
    monkeypatch.setattr(panel, "_refresh", lambda *_args: refreshes.append(len(registry.paths)))
    registry.batch_finished.connect(panel._refresh)   # the patched method, as the panel connects it
    finished = []
    registry.batch_finished.connect(lambda: finished.append(True))
    with registry.batch():
        with registry.batch():                         # nested batches end once
            for binding, path in bindings:
                binding.open_path(path)
                assert registry.batching
        assert loaded == [path for _binding, path in bindings]   # every file loaded as it opened
        assert finished == []
    assert not registry.batching and finished == [True]
    assert refreshes and refreshes[-1] == 5
    registry.open_file("file0.bin", bindings[0][1])     # outside a batch: refreshed at once
    assert not registry.batching
