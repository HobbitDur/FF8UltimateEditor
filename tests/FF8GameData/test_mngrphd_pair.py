"""mngrp.bin is only readable through the mngrphd.bin saved with it: every save moves the
sections after one that grew, so an older mngrphd.bin points at the wrong data from there on.
That pair is refused on load with a message saying so, instead of being read (and saved) wrong."""
import pathlib
import shutil
import struct

import pytest

from FF8GameData.FF8HexReader.mngrphd import Mngrphd, MngrpPairError

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MENU = PROJECT_ROOT / "extracted_files" / "menu"


def _header(*entries):
    """mngrphd.bin bytes from (data offset, size) pairs; None is an unused slot."""
    data = bytearray()
    for entry in entries:
        seek, size = (0xFFFFFFFF, 0) if entry is None else (entry[0] + 1, entry[1])  # bit 0 = stored raw
        data += struct.pack("<II", seek, size)
    return data


def test_a_header_matches_the_file_its_sections_fill():
    header = Mngrphd(None, _header((0, 2048), None, (2048, 4096)))
    header.check_matches(6144)


@pytest.mark.parametrize("size", [6144 + 2048, 6144 - 2048])
def test_a_header_of_another_save_is_refused(size):
    header = Mngrphd(None, _header((0, 2048), None, (2048, 4096)))
    with pytest.raises(MngrpPairError, match="does not match"):
        header.check_matches(size, "mod/menu/mngrp.bin")


@pytest.mark.ff8data("extracted_files/menu/mngrp.bin", "extracted_files/menu/mngrphd.bin")
def test_a_mngrp_saved_without_its_mngrphd_is_refused(tmp_path):
    from FF8GameData.gamedata import GameData
    from FF8GameData.menu.mngrp.mngrpmanager import MngrpManager
    game_data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    game_data.load_all()
    shutil.copy(MENU / "mngrp.bin", tmp_path / "mngrp.bin")
    shutil.copy(MENU / "mngrphd.bin", tmp_path / "mngrphd.bin")
    MngrpManager(game_data).load_file(str(tmp_path / "mngrphd.bin"), str(tmp_path / "mngrp.bin"))

    # A save rewrites both; keeping only the new mngrp.bin with the original mngrphd.bin is the
    # mistake this guards against.
    saved = MngrpManager(game_data)
    saved.load_file(str(tmp_path / "mngrphd.bin"), str(tmp_path / "mngrp.bin"))
    saved.save_file(str(tmp_path / "mngrp.bin"), str(tmp_path / "mngrphd_new.bin"))
    if (tmp_path / "mngrp.bin").stat().st_size == (MENU / "mngrp.bin").stat().st_size:
        pytest.skip("this mngrp.bin keeps its size on save: nothing moved")
    with pytest.raises(MngrpPairError):
        MngrpManager(game_data).load_file(str(tmp_path / "mngrphd.bin"), str(tmp_path / "mngrp.bin"))
    MngrpManager(game_data).load_file(str(tmp_path / "mngrphd_new.bin"), str(tmp_path / "mngrp.bin"))
