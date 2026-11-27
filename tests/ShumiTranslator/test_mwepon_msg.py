"""mwepon.msg, the Junk Shop text per upgrade: the model (FF8GameData.menu.mweponmsg), its
ShumiTranslator tab, and Junkshop showing it read-only beside the offsets.

Synthetic files (built here) run everywhere; the retail round trip needs the game's files (ff8data).
"""
import pathlib
import shutil
import sys

import pytest
from PyQt6.QtWidgets import QApplication

from FF8GameData.gamedata import FileType, GameData
from FF8GameData.menu.mweponmsg import MweponMsg, read_offsets, text_at

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MENU = PROJECT_ROOT / "extracted_files" / "menu"


@pytest.fixture(scope="module")
def game_data():
    data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    data.load_all()
    return data


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def _record(offset, price=10, item=1, quantity=2):
    return bytes([offset & 0xFF, offset >> 8, 0, price, item, quantity, 0, 0, 0, 0, 0, 0])


def _files(folder, game_data, texts, shared=None):
    """mwepon.msg with those texts in order and a mwepon.bin with one upgrade per text (plus, with
    shared=(upgrade, text), an extra upgrade showing an existing text)."""
    msg = bytearray()
    offsets = []
    for text in texts:
        offsets.append(len(msg))
        msg += bytes(game_data.translate_str_to_hex(text)) + b"\x00"
    if shared is not None:
        offsets.append(offsets[shared])
    (folder / "mwepon.msg").write_bytes(bytes(msg))
    (folder / "mwepon.bin").write_bytes(b"".join(_record(offset, price=index + 1) for index, offset in enumerate(offsets)))
    return folder / "mwepon.msg", folder / "mwepon.bin"


def test_a_longer_text_moves_the_offsets_after_it_and_nothing_else(tmp_path, game_data):
    msg_path, bin_path = _files(tmp_path, game_data, [" ", " ", " "])
    before = bin_path.read_bytes()
    model = MweponMsg.from_files(game_data, msg_path, bin_path)
    model.get_text_list()[0].set_str("Revolver: Str +11")
    model.save(msg_path, bin_path)

    after = bin_path.read_bytes()
    offsets = read_offsets(after)
    assert offsets[0] == 0 and offsets[1] == len("Revolver: Str +11") + 1 and offsets[2] == offsets[1] + 2
    for index in range(3):  # only bytes 0-1 of each record moved
        assert after[12 * index + 2:12 * index + 12] == before[12 * index + 2:12 * index + 12]
    msg = msg_path.read_bytes()
    assert text_at(game_data, msg, offsets[0]) == "Revolver: Str +11"
    assert text_at(game_data, msg, offsets[2]) == " "


def test_upgrades_sharing_a_text_keep_sharing_it(tmp_path, game_data):
    msg_path, bin_path = _files(tmp_path, game_data, ["A", "B"], shared=0)
    model = MweponMsg.from_files(game_data, msg_path, bin_path)
    assert len(model.get_text_list()) == 2 and model.upgrades_of(0) == [0, 2]
    model.get_text_list()[0].set_str("Shared")
    model.save(msg_path, bin_path)
    offsets = read_offsets(bin_path.read_bytes())
    assert offsets[0] == offsets[2] and text_at(game_data, msg_path.read_bytes(), offsets[2]) == "Shared"


def test_an_offset_past_the_end_is_refused(tmp_path, game_data):
    msg_path, bin_path = _files(tmp_path, game_data, ["A"])
    bin_path.write_bytes(_record(40))
    with pytest.raises(ValueError, match="past the end"):
        MweponMsg.from_files(game_data, msg_path, bin_path)


@pytest.mark.ff8data("extracted_files/menu/mwepon.msg", "extracted_files/menu/mwepon.bin")
def test_the_retail_file_saves_unchanged(tmp_path, game_data):
    for name in ("mwepon.msg", "mwepon.bin"):
        shutil.copy(MENU / name, tmp_path / name)
    model = MweponMsg.from_files(game_data, tmp_path / "mwepon.msg", tmp_path / "mwepon.bin")
    assert len(model.get_text_list()) == 33  # one blank text per upgrade
    model.save(tmp_path / "mwepon.msg", tmp_path / "mwepon.bin")
    assert (tmp_path / "mwepon.msg").read_bytes() == (MENU / "mwepon.msg").read_bytes()
    assert (tmp_path / "mwepon.bin").read_bytes() == (MENU / "mwepon.bin").read_bytes()


def test_shumitranslator_opens_edits_and_saves_mwepon_msg(tmp_path, game_data, qapp):
    from ShumiTranslator.shumitranslator import ShumiTranslator
    msg_path, bin_path = _files(tmp_path, game_data, [" ", " "])
    shumi = ShumiTranslator(game_data_folder=str(PROJECT_ROOT / "FF8GameData"))
    assert shumi.mwepon_msg_binding in shumi.file_bindings()
    shumi.mwepon_msg_binding.open_path(str(msg_path))
    pane = shumi.tab_widget.currentWidget()
    assert pane.file_type == FileType.MWEPON_MSG and pane.display_name == "mwepon.msg"
    assert len(pane.section_widget_list) == 1

    pane.section_widget_list[0].set_text_from_id(1, "Shear Trigger: Str +14")
    assert "mwepon.bin" in pane.save(shumi)
    offsets = read_offsets(bin_path.read_bytes())
    assert text_at(game_data, msg_path.read_bytes(), offsets[1]) == "Shear Trigger: Str +14"


def test_junkshop_shows_the_text_and_keeps_the_offsets_on_disk(tmp_path, game_data, qapp):
    from Junkshop.junkshopwidget import JunkshopWidget
    msg_path, bin_path = _files(tmp_path, game_data, ["First", "Second"])
    junkshop = JunkshopWidget(game_data_folder=str(PROJECT_ROOT / "FF8GameData"))
    assert junkshop.msg_binding in junkshop.file_bindings() and junkshop.msg_binding.read_only
    junkshop.mwepon_binding.open_path(str(bin_path))
    assert junkshop.msg_binding.current_path == str(msg_path)  # opened beside mwepon.bin
    junkshop.weapon_list.setCurrentRow(1)
    assert junkshop.msg_text_label.text() == "\"Second\""

    # ShumiTranslator moves the offsets meanwhile; a Junkshop save keeps the moved ones
    model = MweponMsg.from_files(game_data, msg_path, bin_path)
    model.get_text_list()[0].set_str("A much longer first text")
    model.save(msg_path, bin_path)
    moved = read_offsets(bin_path.read_bytes())
    junkshop.price_spinbox.setValue(500)
    junkshop.save_file()
    saved = bin_path.read_bytes()
    assert read_offsets(saved) == moved and saved[12 + 3] == 50
