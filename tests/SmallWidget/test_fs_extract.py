"""Header's Extract .fs button: without deling-cli it says to update the Deling tool instead of
opening the file pickers, and a failed extraction reports itself without taking the editor down."""
import sys
from types import SimpleNamespace

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

import SmallWidget.fsextractwidget as fsextract


def _button(tmp_path):
    QApplication.instance() or QApplication(sys.argv)
    return fsextract.FsExtractWidget("Resources", str(tmp_path))    # no fs/DelingCli in there


def test_missing_deling_cli_asks_to_update_deling(tmp_path, monkeypatch):
    shown = []
    monkeypatch.setattr(fsextract.QMessageBox, "warning", lambda _parent, title, text: shown.append((title, text)))
    monkeypatch.setattr(fsextract.QFileDialog, "getOpenFileName",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no file picker without deling-cli")))
    button = _button(tmp_path)
    button.click()
    assert len(shown) == 1 and "Tool update" in shown[0][1] and "Deling" in shown[0][1]
    assert button.isEnabled()


def test_failed_extraction_reports_and_frees_the_thread(tmp_path, monkeypatch):
    fs_path, dest = tmp_path / "field.fs", tmp_path / "out"
    fs_path.write_bytes(b"")
    errors = []
    monkeypatch.setattr(fsextract.QMessageBox, "critical", lambda _parent, title, text: errors.append(text))
    monkeypatch.setattr(fsextract.QFileDialog, "getOpenFileName", lambda *a, **k: (str(fs_path), ""))
    monkeypatch.setattr(fsextract.QFileDialog, "getExistingDirectory", lambda *a, **k: str(dest))
    button = _button(tmp_path)

    def unpack(*_args, **_kwargs):
        raise FileNotFoundError("deling-cli.exe vanished")
    button._deling_manager = SimpleNamespace(is_installed=lambda: True, unpack=unpack)
    button.click()
    worker = button._worker
    loop = QEventLoop()
    worker.finished.connect(loop.quit)
    QTimer.singleShot(5000, loop.quit)
    if not worker.isFinished():
        loop.exec()
    QApplication.processEvents()
    assert errors and "vanished" in errors[0]
    assert button.isEnabled() and button._worker is None
