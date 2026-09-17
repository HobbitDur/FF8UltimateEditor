"""Tests for resolving a WARP_TO_FIELD to the field it actually goes to.

Both files are optional and read-only, so most of this is about degrading tidily when one or
both are missing - a modder who only opened the wmset must still get a usable line.
"""
import pathlib
import struct

import pytest

from Chocoboy.fieldentrances import (FieldEntranceTable, FieldNameList, describe_entrance,
                                     entrance_field_name)

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
WM2FIELD_REL = "extracted_files/main/wm2field.tbl"
MAPLIST_REL = "extracted_files/field/mapdata/maplist"
WM2FIELD = PROJECT_ROOT / WM2FIELD_REL
MAPLIST = PROJECT_ROOT / MAPLIST_REL


def build_entrance(x, y, triangle, field_id, facing):
    return struct.pack("<hhhh", x, y, triangle, field_id) + bytes([facing]) + bytes(15)


def test_a_record_is_read_the_way_the_module_handler_reads_it():
    table = FieldEntranceTable(build_entrance(-9, -360, 29, 827, 3))
    assert len(table) == 1
    assert table.get(0) == {"x": -9, "y": -360, "triangle": 29, "field_id": 827, "facing": 3}
    assert table.get(1) is None


def test_a_field_id_is_its_line_number_in_the_maplist():
    names = FieldNameList("wm00\nwm01\nbccent_1\n")
    assert names.get(0) == "wm00"
    assert names.get(2) == "bccent_1"
    assert names.get(3) is None


def test_with_both_files_an_entrance_reads_as_a_place():
    table = FieldEntranceTable(build_entrance(-9, -360, 29, 2, 3))
    names = FieldNameList("a\nb\nrgcock2\n")
    assert describe_entrance(0, table, names) == \
           "rgcock2, at x -9, y -360, triangle 29, facing 3"
    assert entrance_field_name(0, table, names) == "rgcock2"


def test_without_the_maplist_the_field_is_still_numbered():
    table = FieldEntranceTable(build_entrance(-9, -360, 29, 827, 3))
    assert describe_entrance(0, table, None).startswith("field 827, at x -9")
    assert entrance_field_name(0, table, None) == "field 827"


def test_without_wm2field_it_says_which_file_would_answer():
    assert "wm2field.tbl" in describe_entrance(44, None, None)
    assert entrance_field_name(44, None, None) == ""


def test_an_entrance_the_table_does_not_have_says_so():
    table = FieldEntranceTable(build_entrance(0, 0, 0, 1, 0))
    assert "does not have" in describe_entrance(99, table, None)


# --- the real game files ---------------------------------------------------------------------

@pytest.mark.ff8data(WM2FIELD_REL, MAPLIST_REL)
def test_the_real_tables_name_the_two_vehicle_interiors():
    """The entrances that decide what vehicle codes 48 and 50 are: 66 is the Ragnarok cockpit
    and 64 is inside Balamb Garden, which is how the scripts checking each one settle it."""
    table = FieldEntranceTable.from_file(str(WM2FIELD))
    names = FieldNameList.from_file(str(MAPLIST))
    assert len(table) == 72
    assert entrance_field_name(66, table, names) == "rgcock4"
    assert entrance_field_name(44, table, names) == "rgcock2"
    assert entrance_field_name(64, table, names) == "bgsido_4"


@pytest.mark.ff8data(WM2FIELD_REL, MAPLIST_REL)
def test_every_real_entrance_names_a_real_field():
    table = FieldEntranceTable.from_file(str(WM2FIELD))
    names = FieldNameList.from_file(str(MAPLIST))
    for entrance in range(len(table)):
        assert names.get(table.get(entrance)["field_id"]), f"entrance {entrance}"
