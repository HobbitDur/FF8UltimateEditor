"""The exe's Scan text counts its offsets from the first text, which therefore sits at offset 0:
rebuilding the section must give the exe's bytes back (it once read that 0 as "no text", shifted
every text by one slot and printed "The size of the text list (160) is different than ... (159)")."""
import pytest

from FF8GameData.GenericSection.offsetandtext import SectionOffsetAndText
from FF8GameData.gamedata import GameData

EXE = "extracted_files/FF8_EN.exe"


@pytest.mark.ff8data(EXE)
def test_scan_text_rebuilds_byte_identical(capsys):
    game_data = GameData("FF8GameData")
    game_data.load_exe_data()
    exe = bytearray(open(EXE, "rb").read())
    config = game_data.exe_data_json["scan_data_offset"]
    start, count = config["eng_section_start"], config["nb_offset"]
    section = SectionOffsetAndText(game_data, exe[start:], id=7, own_offset=start, name="Scan text",
                                   offset_size=config["offset_size"], nb_offset=count,
                                   ignore_empty_offset=False, nb_byte_shift=0, text_offset_start_0=True)
    assert len(section.get_text_list()) == count
    data = bytes(section.update_data_hex())
    assert data[:2 * count] == bytes(exe[start:start + 2 * count])      # the offset table
    assert data == bytes(exe[start:start + len(data)])                   # and the texts
    assert "different than the nb" not in capsys.readouterr().out
