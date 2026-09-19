"""Adding monster sheets to an existing monster xlsx without rewriting it (Ifrit/IfritXlsx/xlsxappend).

A modder's workbook is patched at the zip level: every part already there must come out byte for
byte, the new sheets land in monster-id order before ref_data, and their values, drop-downs and
stat chart must be the ones the xlsx writer produced.

Needs the real (copyright, gitignored) monster files under extracted_files/battle/.
"""
import contextlib
import io
import pathlib
import zipfile

import openpyxl
import pytest
from PyQt6.QtWidgets import QApplication

ROOT = pathlib.Path(__file__).parent.parent.parent
BATTLE = ROOT / "extracted_files" / "battle"
pytestmark = pytest.mark.ff8data("extracted_files/battle/c0m000.dat", "extracted_files/battle/c0m001.dat",
                                 "extracted_files/battle/c0m002.dat", "extracted_files/battle/c0m127.dat",
                                 "extracted_files/battle/c0m144.dat")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _write(manager, path, ids):
    with contextlib.redirect_stdout(io.StringIO()):
        manager.create_xlsx_file(str(path))
        manager.dat_to_xlsx([str(BATTLE / f"c0m{i:03d}.dat") for i in ids])


def test_missing_monster_sheets_are_appended_in_place(qapp, tmp_path):
    from Ifrit.ifritmanager import IfritManager
    from Ifrit.IfritXlsx.xlsxappend import append_sheets
    manager = IfritManager(str(ROOT / "FF8GameData"))
    target, source = tmp_path / "target.xlsx", tmp_path / "source.xlsx"
    _write(manager, target, [1, 2])
    # c0m000, c0m127 (no model) and c0m144 (a free slot) used to be refused by the writer
    _write(manager, source, [0, 2, 127, 144])
    before = zipfile.ZipFile(target)
    before_parts = {name: before.read(name) for name in before.namelist()}
    before.close()

    added = append_sheets(target, source)
    assert added == ["0 - Dummy", "127 - Ultimecia", "144 - DefaultMonsterName"]   # 2 is already there
    assert append_sheets(target, source) == []                                     # idempotent

    after = zipfile.ZipFile(target)
    index_parts = {"xl/workbook.xml", "xl/_rels/workbook.xml.rels", "[Content_Types].xml",
                   "xl/sharedStrings.xml", "xl/styles.xml"}
    for name, content in before_parts.items():
        if name not in index_parts:
            assert after.read(name) == content, name   # every sheet, chart, drawing: byte for byte
    after.close()

    workbook = openpyxl.load_workbook(target)
    assert workbook.sheetnames[0] == "0 - Dummy"
    assert workbook.sheetnames[-1] == "ref_data"
    assert workbook.sheetnames.index("127 - Ultimecia") < workbook.sheetnames.index("144 - DefaultMonsterName")
    written = openpyxl.load_workbook(source)
    for name in added:
        got, expected = workbook[name], written[name]
        assert [list(row) for row in got.iter_rows(values_only=True)] == \
               [list(row) for row in expected.iter_rows(values_only=True)]
        assert len(got.data_validations.dataValidation) == len(expected.data_validations.dataValidation)
        assert len(got._charts) == 1
