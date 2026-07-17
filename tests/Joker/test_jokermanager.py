"""Tests for Joker (SP2 quad-list sprite table editor).

Synthetic tests exercise the Sp2File model alone (build/parse, unused ids, directory
rebuild after adding quads/sprites) and run everywhere. The real-file tests load the
three known SP2 sources (face.sp2, cardanm.sp2, mngrp.bin Pos 4) and assert the
round-trip is byte-exact; they need the original game files (ff8data marker).
"""
import pathlib
import shutil
import struct

import pytest

from Joker.jokermanager import JokerManager, Sp2File, Sp2Quad, Sp2Sprite

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MENU_DIR = PROJECT_ROOT / "extracted_files" / "menu"
FACE = MENU_DIR / "face.sp2"
CARDANM = MENU_DIR / "cardanm.sp2"
MNGRP = MENU_DIR / "mngrp.bin"
MNGRPHD = MENU_DIR / "mngrphd.bin"


@pytest.fixture(scope="module")
def game_data():
    from FF8GameData.gamedata import GameData
    return GameData(str(PROJECT_ROOT / "FF8GameData"))


def _snapshot(sp2):
    return [(sprite.used,
             [(q.u, q.v, q.clut, q.width, q.height, q.dx, q.dy, q.texpage) for q in sprite.quads]
             if sprite.used else [])
            for sprite in sp2.sprites]


def _build_synthetic():
    return Sp2File([
        Sp2Sprite(0, quads=[Sp2Quad(u=0, v=0, clut=0x3620, width=32, height=48, dx=0, dy=0, texpage=0x8E)]),
        Sp2Sprite(1, used=False),
        Sp2Sprite(2, quads=[Sp2Quad(u=128, v=96, clut=0xB620, width=64, height=64, dx=-4, dy=7, texpage=0xAE),
                            Sp2Quad(u=1, v=2, clut=3, width=4, height=5, dx=-6, dy=-7, texpage=8)]),
    ])


# --- Synthetic tests (no game files needed) ---

def test_synthetic_build_parse_roundtrip():
    sp2 = _build_synthetic()
    rebuilt = Sp2File.from_bytes(sp2.to_bytes())
    assert _snapshot(rebuilt) == _snapshot(sp2)
    assert rebuilt.unused_ids() == [1]
    assert len(rebuilt.used_sprites()) == 2


def test_synthetic_directory_layout():
    data = _build_synthetic().to_bytes()
    count = struct.unpack_from("<I", data, 0)[0]
    offsets = struct.unpack_from("<3I", data, 4)
    assert count == 3
    assert offsets[0] == 4 + 4 * 3  # first record right after the directory
    assert offsets[1] == 0  # unused id
    assert offsets[2] == offsets[0] + 4 + Sp2Quad.SIZE  # after sprite 0 (1 quad)
    # sprite 2 record: 2 quads
    assert struct.unpack_from("<i", data, offsets[2])[0] == 2
    assert len(data) == offsets[2] + 4 + 2 * Sp2Quad.SIZE


def test_synthetic_add_quad_rebuilds_offsets():
    sp2 = _build_synthetic()
    sp2.sprites[0].quads.append(Sp2Quad(u=9, v=9, width=1, height=1))
    data = sp2.to_bytes()
    offsets = struct.unpack_from("<3I", data, 4)
    # sprite 2 shifted by one quad size
    assert offsets[2] == 4 + 4 * 3 + 4 + 2 * Sp2Quad.SIZE
    rebuilt = Sp2File.from_bytes(data)
    assert len(rebuilt.sprites[0].quads) == 2
    assert rebuilt.sprites[0].quads[1].u == 9


def test_synthetic_add_sprite_extends_directory():
    sp2 = _build_synthetic()
    new_sprite = sp2.add_sprite()
    assert new_sprite.sprite_id == 3
    rebuilt = Sp2File.from_bytes(sp2.to_bytes())
    assert len(rebuilt.sprites) == 4
    assert rebuilt.sprites[3].used
    assert len(rebuilt.sprites[3].quads) == 1


def test_synthetic_flag_unused_then_restore():
    sp2 = _build_synthetic()
    sp2.sprites[2].used = False
    rebuilt = Sp2File.from_bytes(sp2.to_bytes())
    assert rebuilt.unused_ids() == [1, 2]
    # quads of an unused id are not written
    assert rebuilt.sprites[2].quads == []


def test_synthetic_empty_used_sprite_differs_from_unused():
    sp2 = Sp2File([Sp2Sprite(0, quads=[]), Sp2Sprite(1, used=False)])
    data = sp2.to_bytes()
    offsets = struct.unpack_from("<2I", data, 4)
    assert offsets[0] != 0 and offsets[1] == 0
    rebuilt = Sp2File.from_bytes(data)
    assert rebuilt.sprites[0].used and rebuilt.sprites[0].quads == []
    assert not rebuilt.sprites[1].used


def test_not_an_sp2_file_raises():
    with pytest.raises(ValueError):
        Sp2File.from_bytes(b"\xFF\xFF\xFF\xFF garbage")


# --- Real-file byte-exact round-trips (the three known SP2 sources) ---

@pytest.mark.ff8data("extracted_files/menu/face.sp2")
def test_real_face_sp2_byte_exact(game_data, tmp_path):
    original = FACE.read_bytes()
    sp2 = Sp2File.from_bytes(original)
    assert len(sp2.sprites) == 64
    assert not sp2.unused_ids()
    assert all(len(s.quads) == 1 for s in sp2.sprites)
    assert (sp2.sprites[0].quads[0].width, sp2.sprites[0].quads[0].height) == (32, 48)
    assert sp2.to_bytes() == original

    manager = JokerManager(game_data)
    manager.load_file(str(FACE))
    out = tmp_path / "face.sp2"
    manager.save_file(str(out))
    assert out.read_bytes() == original


@pytest.mark.ff8data("extracted_files/menu/cardanm.sp2")
def test_real_cardanm_sp2_byte_exact(game_data, tmp_path):
    original = CARDANM.read_bytes()
    sp2 = Sp2File.from_bytes(original)
    assert len(sp2.sprites) == 12
    assert (sp2.sprites[0].quads[0].width, sp2.sprites[0].quads[0].height) == (64, 64)
    assert sp2.to_bytes() == original

    manager = JokerManager(game_data)
    manager.load_file(str(CARDANM))
    out = tmp_path / "cardanm.sp2"
    manager.save_file(str(out))
    assert out.read_bytes() == original


@pytest.mark.ff8data("extracted_files/menu/mngrp.bin", "extracted_files/menu/mngrphd.bin")
def test_real_mngrp_pos4_byte_exact(game_data, tmp_path):
    work_mngrp = tmp_path / "mngrp.bin"
    work_mngrphd = tmp_path / "mngrphd.bin"
    shutil.copy(MNGRP, work_mngrp)
    shutil.copy(MNGRPHD, work_mngrphd)

    manager = JokerManager(game_data)
    manager.load_mngrp(str(work_mngrp), str(work_mngrphd))
    assert len(manager.sp2.sprites) == 79
    manager.save_mngrp()  # no edit: both files must stay byte-identical

    assert work_mngrp.read_bytes() == MNGRP.read_bytes()
    assert work_mngrphd.read_bytes() == MNGRPHD.read_bytes()


@pytest.mark.ff8data("extracted_files/menu/mngrp.bin", "extracted_files/menu/mngrphd.bin")
def test_real_mngrp_pos4_edit_persists(game_data, tmp_path):
    work_mngrp = tmp_path / "mngrp.bin"
    work_mngrphd = tmp_path / "mngrphd.bin"
    shutil.copy(MNGRP, work_mngrp)
    shutil.copy(MNGRPHD, work_mngrphd)

    manager = JokerManager(game_data)
    manager.load_mngrp(str(work_mngrp), str(work_mngrphd))
    manager.sp2.sprites[0].quads[0].width = 100
    manager.sp2.sprites[5].used = False
    new_sprite = manager.sp2.add_sprite()
    new_sprite.quads[0].u = 42
    manager.save_mngrp()

    reloaded = JokerManager(game_data)
    reloaded.load_mngrp(str(work_mngrp), str(work_mngrphd))
    assert len(reloaded.sp2.sprites) == 80
    assert reloaded.sp2.sprites[0].quads[0].width == 100
    assert reloaded.sp2.unused_ids() == [5]
    assert reloaded.sp2.sprites[79].quads[0].u == 42
    # the untouched neighbour sections must still parse: the refine data is a good canary
    from FF8GameData.menu.mngrp.mngrpmanager import MngrpManager
    from Shiva.ShivaRefine.refineview import build_refine_views
    game_data.load_item_data()  # the m00x sections name their entries from those
    game_data.load_magic_data()
    game_data.load_card_data()
    shared = MngrpManager(game_data)
    shared.load_file(str(work_mngrphd), str(work_mngrp))
    assert build_refine_views(shared)
