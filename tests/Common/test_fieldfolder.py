"""The field folder check (Common/fieldfolder.py): the folder holding mapdata is accepted, any other
pick is refused with a message naming the folder to pick instead."""
import os

from Common.fieldfolder import NEEDS_MODELS, VANILLA_MIN_MAPS, check_field_folder


def make_field(root, maps=("bg/bghall_1", "bc/bccent12"), chara=True, main_chr=True):
    field = root / "field"
    for area_map in maps:
        folder = field / "mapdata" / area_map
        folder.mkdir(parents=True)
        (folder / f"{folder.name}.jsm").write_bytes(b"")
        if chara:
            (folder / "chara.one").write_bytes(b"")
    if main_chr:
        (field / "model" / "main_chr").mkdir(parents=True)
        (field / "model" / "main_chr" / "d000.mch").write_bytes(b"")
    return field


def test_the_field_folder_is_accepted(tmp_path):
    field = make_field(tmp_path)
    check = check_field_folder(str(field))
    assert check.ok and check.root == os.path.normpath(str(field))
    assert (check.maps, check.models) == (2, 2)
    assert check.main_chr == os.path.join(check.root, "model", "main_chr")


def test_a_folder_inside_the_field_folder_names_the_field_folder(tmp_path):
    field = make_field(tmp_path)
    for picked in (field / "mapdata", field / "mapdata" / "bg", field / "mapdata" / "bg" / "bghall_1"):
        check = check_field_folder(str(picked))
        assert not check.ok and check.root == ""
        assert "Pick the field folder" in check.error and os.path.normpath(str(field)) in check.error


def test_a_mod_root_holding_field_names_it(tmp_path):
    field = make_field(tmp_path)
    check = check_field_folder(str(tmp_path))
    assert not check.ok and "holds a 'field' folder" in check.error and str(field) in check.error


def test_an_unrelated_folder_shows_the_expected_layout(tmp_path):
    (tmp_path / "notes").mkdir()
    check = check_field_folder(str(tmp_path / "notes"))
    assert not check.ok and "No 'mapdata' folder" in check.error and "mapdata\\<area>\\<map>" in check.error
    assert "does not exist" in check_field_folder(str(tmp_path / "missing")).error


def test_misplaced_scripts_are_refused(tmp_path):
    """Every .jsm found is read as a map: one in another map's folder (as Cronos FieldRework's
    bghall2a.jsm inside bghall_2) or outside mapdata\\<area>\\<map> must be fixed first."""
    field = make_field(tmp_path)
    (field / "mapdata" / "bg" / "bghall_1" / "bghall2a.jsm").write_bytes(b"")
    (field / "mapdata" / "stray.jsm").write_bytes(b"")
    check = check_field_folder(str(field))
    assert not check.ok and check.maps == 2 and len(check.misplaced) == 2
    assert os.path.join("mapdata", "bg", "bghall_1", "bghall2a.jsm") in check.error
    assert check_field_folder(str(field), NEEDS_MODELS).ok  # Seed only reads the chara.one files


def test_an_empty_mapdata_has_no_map(tmp_path):
    (tmp_path / "field" / "mapdata").mkdir(parents=True)
    check = check_field_folder(str(tmp_path / "field"))
    assert not check.ok and "No map script" in check.error
    check = check_field_folder(str(make_field(tmp_path / "x", chara=False)), NEEDS_MODELS)
    assert not check.ok and "chara.one" in check.error


def test_the_vanilla_reference_must_be_the_whole_game(tmp_path):
    check = check_field_folder(str(make_field(tmp_path)), complete=True)
    assert not check.ok and "looks like a mod's field folder" in check.error
    many = [f"bg/map{index:03d}" for index in range(VANILLA_MIN_MAPS)]
    assert check_field_folder(str(make_field(tmp_path / "full", maps=many, chara=False)), complete=True).ok
