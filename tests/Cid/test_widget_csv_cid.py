"""Widget-level CSV round-trip tests for the Cid draw-point editor.

``CidWidget`` holds two independent kinds of data that map to two different files:
  * magic / high-yield / refill  -> one byte per draw ID in the EXE (``.hext`` export)
  * X / Y / Sub ID               -> world-map positions in wmset Section 34

Its CSV export/import (``CidWidget._save_csv`` / ``_open_csv``) is a *separate*
implementation from the CLI tool (``Cli/cid.py`` is covered in ``tests/Cli``), so it
needs its own coverage. These tests drive the real widget: they load the genuine
``FF8_EN.exe`` for the magic bytes, round-trip the model through a CSV on disk, and check
that the per-draw values survive and that the ``_exe_dirty`` / ``_wmset_dirty``
unsaved-change flags (which the single Save button relies on to decide what to write) end
up set correctly. Needs the real exe, skipped otherwise (ff8data marker).
"""
import pathlib
import sys

import pytest
from PyQt6.QtWidgets import QApplication

from Cid.cidwidget import CidWidget

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
EXE_REL = "extracted_files/FF8_EN.exe"
EXE = PROJECT_ROOT / EXE_REL

WORLD_ROW = 130  # 0-based index of a world draw point (Draw ID 131), which has a wmset position


@pytest.fixture(scope="module")
def qapp():
    # CidWidget builds real Qt widgets, so a QApplication must exist.
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def widget(qapp):
    # Function-scoped: each test corrupts the model, so it must start from a clean widget.
    return CidWidget(icon_path=str(PROJECT_ROOT / "Resources"),
                     game_data_folder=str(PROJECT_ROOT / "FF8GameData"))


def _load_exe(widget, monkeypatch):
    """Load the real exe through the widget's normal path, without the file dialog."""
    monkeypatch.setattr(widget._exe_dialog, "getOpenFileName",
                        lambda *args, **kwargs: (str(EXE), ""))
    widget._load_exe()


def _model_snapshot(widget):
    return [(draw.magic_index, draw.high_yield, draw.refill, draw.x, draw.y, draw.sub_id)
            for draw in widget._draw_list]


@pytest.mark.ff8data(EXE_REL)
def test_widget_csv_roundtrip_preserves_model(widget, monkeypatch, tmp_path):
    """Export the model to CSV, wipe it in memory, re-import -> every draw is restored."""
    _load_exe(widget, monkeypatch)
    assert widget.exe_loaded
    assert widget._exe_dirty is False, "loading the exe is not an edit"

    # Give a world draw point a distinctive position so the CSV carries real X/Y/Sub ID.
    world = widget._draw_list[WORLD_ROW]
    world.x, world.y, world.sub_id = 42, 7, 3

    before = _model_snapshot(widget)

    csv_path = tmp_path / "draws.csv"
    monkeypatch.setattr(widget.csv_dialog, "getSaveFileName",
                        lambda *args, **kwargs: (str(csv_path), ""))
    widget._save_csv()
    assert csv_path.exists()

    # Corrupt the in-memory model so a broken import cannot silently pass.
    for draw in widget._draw_list:
        draw.magic_index, draw.high_yield, draw.refill = 0, False, False
        draw.x = draw.y = draw.sub_id = 0

    monkeypatch.setattr(widget.csv_dialog, "getOpenFileName",
                        lambda *args, **kwargs: (str(csv_path), ""))
    widget._open_csv()

    assert _model_snapshot(widget) == before
    # A CSV import that carries position columns dirties both backing files.
    assert widget._exe_dirty is True
    assert widget._wmset_dirty is True


@pytest.mark.ff8data(EXE_REL)
def test_widget_csv_import_without_positions_leaves_wmset_clean(widget, monkeypatch, tmp_path):
    """A legacy 4-column CSV (no X/Y/Sub ID) updates magic only and never dirties wmset."""
    _load_exe(widget, monkeypatch)

    # A world draw point with a known position that the import must NOT touch.
    world = widget._draw_list[WORLD_ROW]
    world.x, world.y, world.sub_id = 99, 88, 5

    csv_path = tmp_path / "legacy.csv"
    csv_path.write_text(
        "Draw ID,Magic ID,High Yield,Refill\n"
        "1,5,1,0\n"
        "2,6,0,1\n",
        encoding="utf-8")

    monkeypatch.setattr(widget.csv_dialog, "getOpenFileName",
                        lambda *args, **kwargs: (str(csv_path), ""))
    widget._open_csv()

    # Magic data for the two listed draws was applied...
    first, second = widget._draw_list[0], widget._draw_list[1]
    assert (first.magic_index, first.high_yield, first.refill) == (5, True, False)
    assert (second.magic_index, second.high_yield, second.refill) == (6, False, True)
    # ...the world position was left alone, and only the EXE file is flagged dirty.
    assert (world.x, world.y, world.sub_id) == (99, 88, 5)
    assert widget._exe_dirty is True
    assert widget._wmset_dirty is False
