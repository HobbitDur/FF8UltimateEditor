"""Real-file round-trip test for Quezacotl (main/init.out new-game defaults editor).

Loads the original game init.out from extracted_files/. The vanilla file only reserves
4 item slots, so the manager grows the buffer to the full editable size on load; the
original bytes must be preserved as a prefix (only zero padding is appended), and a
second round-trip must be byte-identical.

Needs the real file, skipped otherwise (ff8data marker).
"""
import pathlib

import pytest

from FF8GameData.gamedata import GameData
from Quezacotl.quezacotlmanager import QuezacotlManager

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
INIT_OUT = PROJECT_ROOT / "extracted_files" / "main" / "init.out"


@pytest.fixture(scope="module")
def game_data():
    return GameData(str(PROJECT_ROOT / "FF8GameData"))


@pytest.mark.ff8data("extracted_files/main/init.out")
def test_real_init_out_preserves_original_bytes(game_data, tmp_path):
    """Load + save keeps every original byte (the manager only appends zero padding)."""
    manager = QuezacotlManager(game_data)
    manager.load_file(str(INIT_OUT))
    assert manager.gf_entries and manager.character_entries and manager.item_entries

    out = tmp_path / "init.out"
    manager.save_file(str(out))

    original = INIT_OUT.read_bytes()
    saved = out.read_bytes()
    assert saved[:len(original)] == original
    assert set(saved[len(original):]) <= {0}, "non-zero bytes were appended"


@pytest.mark.ff8data("extracted_files/main/init.out")
def test_real_init_out_roundtrip_is_idempotent(game_data, tmp_path):
    """Once normalised to full size, a further load + save is byte-identical."""
    manager = QuezacotlManager(game_data)
    manager.load_file(str(INIT_OUT))
    out1 = tmp_path / "init1.out"
    manager.save_file(str(out1))

    manager2 = QuezacotlManager(game_data)
    manager2.load_file(str(out1))
    out2 = tmp_path / "init2.out"
    manager2.save_file(str(out2))

    assert out1.read_bytes() == out2.read_bytes()
