"""Seed's Open-folder button: picking the 'field' folder lists every chara.one as a field and finds
main_chr inside it (it used to take the picked folder AS main_chr, breaking main characters)."""
import os
import pathlib

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from Seed.seedmanager import SeedManager

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
FIELD = PROJECT_ROOT / "extracted_files" / "field"
MAIN_CHR = FIELD / "model" / "main_chr"

needs_field = pytest.mark.skipif(not MAIN_CHR.is_dir(), reason="extracted field folder not available")


def _make_fake_field(tmp_path):
    for room in ("bccent12", "bgroad_6"):
        (tmp_path / "field" / "mapdata" / room[:2] / room).mkdir(parents=True)
        (tmp_path / "field" / "mapdata" / room[:2] / room / "chara.one").write_bytes(b"")
    main_chr = tmp_path / "field" / "model" / "main_chr"
    main_chr.mkdir(parents=True)
    (main_chr / "d000.mch").write_bytes(b"")
    return tmp_path / "field", main_chr


def test_find_chara_ones_and_main_chr(tmp_path):
    field, main_chr = _make_fake_field(tmp_path)
    assert [p.parent.name for p in SeedManager.find_chara_ones(field)] == ["bccent12", "bgroad_6"]
    # The field folder, its parent, the main_chr folder itself and a room folder all find main_chr.
    for picked in (field, tmp_path, main_chr, field / "mapdata" / "bc" / "bccent12"):
        assert SeedManager.find_main_chr_folder_in(picked) == main_chr
    assert not SeedManager.is_main_chr_folder(field)


def test_stale_main_chr_setting_is_redetected(tmp_path):
    """A main_chr folder without .mch (e.g. the 'field' folder picked before) must not stick."""
    field, main_chr = _make_fake_field(tmp_path)
    manager = SeedManager()
    manager.main_chr_folder = field
    manager.chara_one_path = field / "mapdata" / "bc" / "bccent12" / "chara.one"
    assert manager._find_main_chr_folder() == main_chr


@needs_field
def test_nameless_main_entries_use_the_flag_mch_id():
    """bgmast_6 main entries carry no 4-char name: the engine loads d<flag & 0xFFFF>.mch."""
    from FF8GameData.mch.mchanalyser import CharaOne
    path = next(FIELD.rglob("bgmast_6/chara.one"))
    entries = CharaOne(path.read_bytes()).entries
    assert [(e.name, e.mch_file_name) for e in entries if e.is_main] == \
        [("d002", "d002.mch"), ("d000", "d000.mch")]
    assert all((MAIN_CHR / e.mch_file_name).is_file() for e in entries if e.is_main)


@needs_field
def test_headerless_index_at_end_of_file():
    """Headerless chara.one keep their model index at the end, backwards: bg2f_1a = 9 main
    characters (animation blocks only) + 3 NPCs, matching the field script's SETMODEL 0-11."""
    from FF8GameData.mch.mchanalyser import CharaOne
    path = next(FIELD.rglob("bg2f_1a/chara.one"))
    one = CharaOne(path.read_bytes())
    assert one.headerless
    assert [e.name for e in one.entries] == ["d000", "d002", "d009", "d011", "d027", "d029", "d018",
                                             "d024", "d016", "model9", "model10", "model11"]
    first = one.entries[0]
    model = one.build_main_model(first, (MAIN_CHR / first.mch_file_name).read_bytes())
    assert [len(a.frames) for a in model.animation_data.animations] == [1, 28, 20]


@needs_field
def test_widget_open_field_folder_lists_all_fields():
    from PyQt6.QtWidgets import QApplication
    from Seed.seedwidget import SeedWidget
    _app = QApplication.instance() or QApplication([])
    widget = SeedWidget()
    widget.viewer_3d.load_file = lambda: None  # no GL headless
    widget.load_folder(str(FIELD))
    assert widget.field_list.count() >= 800
    assert widget.seed_manager.main_chr_folder == MAIN_CHR
    assert widget.seed_manager.chara_one is not None  # first field opened
    row = next(r for r in range(widget.field_list.count())
               if widget.field_list.item(r).text() == "bgroad_6")
    widget.field_list.setCurrentRow(row)
    assert widget.seed_manager.chara_one_path.parent.name == "bgroad_6"
    assert widget.model_list.count() > 0
