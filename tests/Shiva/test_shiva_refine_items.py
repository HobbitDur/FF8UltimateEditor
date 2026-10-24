"""The refine editor names its items by id, the ones FFNx's AddMoreItems adds (199-255) included.

It used to fill each combo with item.json's list and take the position as the item id. That list
goes on past the game's items (255 "Immune" sits right after 198), so a refine giving item 199
showed "Immune", and picking "Immune" wrote 199. The ids are each entry's data now, and an opened
kernel.bin offers its items.
"""
import pathlib
import shutil
import sys

import pytest
from PyQt6.QtWidgets import QApplication

from FF8GameData.m00x.dataclass import TypeId
from Shiva.shivawidget import ShivaWidget

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MENU = PROJECT_ROOT / "extracted_files" / "menu"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.mark.ff8data("extracted_files/menu/mngrp.bin", "extracted_files/menu/mngrphd.bin")
def test_refine_items_are_kept_and_named_by_id(qapp, tmp_path):
    for name in ("mngrp.bin", "mngrphd.bin"):
        shutil.copy(MENU / name, tmp_path / name)
    widget = ShivaWidget(game_data_folder=str(PROJECT_ROOT / "FF8GameData"))
    widget.load_file(str(tmp_path / "mngrp.bin"))
    refine = widget.refine_tab
    row = next(i for i, view in enumerate(refine.refine_views) if view.output_type == TypeId.ITEM)
    refine.section_list.setCurrentRow(row)
    entry = refine.refine_views[row].entries[0]
    entry.element_out_id = 199
    refine.reload_selected_section()
    combo = refine.entry_table.cellWidget(0, refine.COLUMN_OUTPUT)
    assert combo.currentText() == "Unknown (199)" and combo.currentData() == 199

    widget.kernel_names.items = {199: "Mega Tonic", 230: "Hero Drink"}
    widget.kernel_names.changed.emit()
    combo = refine.entry_table.cellWidget(0, refine.COLUMN_OUTPUT)
    assert combo.currentText() == "199: Mega Tonic"
    combo.activated.emit(combo.findData(230))
    assert entry.element_out_id == 230
    combo.activated.emit(combo.findData(3))
    assert entry.element_out_id == 3
