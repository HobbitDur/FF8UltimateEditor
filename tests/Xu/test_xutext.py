"""Xu: battle_scans.msd (FFNx scan texts, entry = com_id) model and the Scan text layout."""
import struct

import pytest

from FF8GameData.gamedata import GameData
from Xu.xutext import XuTextManager

NL = chr(92) + "n"  # how FF8Text writes a line break


@pytest.fixture(scope="module")
def game_data():
    return GameData("FF8GameData")


def _msd(game_data, texts):
    blobs = [bytes(game_data.translate_str_to_hex(text)) + b"\x00" for text in texts]
    offsets, position = [], 4 * len(blobs)
    for blob in blobs:
        offsets.append(position)
        position += len(blob)
    return struct.pack(f"<{len(blobs)}I", *offsets) + b"".join(blobs)


def test_round_trip_and_growth(game_data, tmp_path):
    data = _msd(game_data, ["Dummy", "", "G-Soldier" + NL + "with a sword."])
    manager = XuTextManager(game_data)
    manager.load_bytes(data)
    assert manager.to_bytes() == data
    assert manager.get_str(2) == "G-Soldier" + NL + "with a sword."
    assert manager.get_str(1) == "" and manager.text(5) is None

    manager.set_str(162, "Medic")  # a c0m146 text: the file grows to reach com_id 162
    assert len(manager.texts) == 163 and manager.is_modified(162) and not manager.is_modified(2)
    path = tmp_path / "battle_scans.msd"
    manager.save_file(str(path))
    reread = XuTextManager(game_data)
    reread.load_file(str(path))
    assert reread.get_str(162) == "Medic" and reread.get_str(100) == ""
    # every entry has its own terminator: empty texts never share the next one's offset
    offsets = struct.unpack_from("<163I", path.read_bytes(), 0)
    assert len(set(offsets)) == 163


def test_bad_files(game_data):
    manager = XuTextManager(game_data)
    with pytest.raises(ValueError):
        manager.load_bytes(b"\x00")
    with pytest.raises(ValueError):
        manager.load_bytes(struct.pack("<I", 0x1000))


def test_scan_text_layout(game_data):
    from Xu.xuhud import ScanHud, lines_per_page
    hud = ScanHud(game_data)
    assert lines_per_page() == 7  # (128 - 12) / 16
    text = NL.join(f"line {i}" for i in range(9))
    assert hud.page_count(text) == 2
    assert hud.too_wide_lines("short" + NL + "W" * 40) == [2]
    image = hud.render("G-Soldier", text, page=1)
    assert image.size == (320, 240) and image.getbbox() is not None
