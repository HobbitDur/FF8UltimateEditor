"""Export -> reimport -> save round trip for the Ifrit static texture editor.

The texture widget (Ifrit.IfritTexture.ifrittexturewidget.IfritTextureWidget)
edits battle ``c0mNNN.dat`` section 11 (the monster's TIM textures) through an
external native tool, VincentTim's ``tim.exe``: on load, each TIM is decoded
to a PNG + palette PNG + meta file; on save, those are re-encoded back into a
TIM by the same tool. This test drives that exact pipeline with no edits:

    IfritManager.init_from_file(path)   # load a monster .dat (auto-runs tim.exe)
    IfritTextureWidget(manager).save_file()  # export pixmaps -> tim.exe -> rebuild TIMs
    IfritManager.save_file(path)        # re-serialise the .dat to disk

Unlike the geometry/animation round trip in test_realfile_monster.py, the raw
TIM bytes are *not* required to match byte-for-byte here. Some monster CLUTs
contain duplicate palette entries (two indices sharing the exact same 15-bit
color), and tim.exe's PNG -> TIM encoder is free to pick either index when it
re-quantizes -- same rendered image, different raw index byte. That was
confirmed by hand on c0m001.dat: after fixing FF8GameData/tim/timfile.py's
5-bit -> 8-bit color expansion to match tim.exe's own rounding formula
(round(v * 255/31), from VincentTim's PsColor.cpp), the only remaining raw
byte differences trace back to palette slots holding identical colors.

So the invariant asserted here is pixel-exactness after decoding through the
palette (which is what actually reaches the screen / the game), not raw byte
equality: every texture's decoded RGBA image must be identical before and
after the round trip, and the overall file size must be unchanged.

Needs the real (copyright, gitignored) monster files under extracted_files/battle/
and the external tim.exe under ExternalTools/VincentTim/, so it is marked
``ff8data`` and skipped in CI / when those files are absent.
"""
import pathlib
import shutil
import sys

import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication

from FF8GameData.tim.timfile import decode_tim
from Ifrit.ifritmanager import IfritManager
from Ifrit.IfritTexture.ifrittexturewidget import IfritTextureWidget

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
BATTLE_DIR = PROJECT_ROOT / "extracted_files" / "battle"

# Same monster set as test_realfile_monster.py: every real monster file.
# Index 127 is a 460-byte stub and 144-199 are placeholder duplicates.
MONSTERS = [f"c0m{i:03d}.dat" for i in range(144) if i != 127]
MONSTER_MARK = [
    pytest.param(name, marks=pytest.mark.ff8data(f"extracted_files/battle/{name}"))
    for name in MONSTERS
]


@pytest.fixture(scope="module")
def qapp():
    # IfritManager/IfritTextureWidget pull in Qt (QPixmap textures); a
    # QApplication must exist.
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture(scope="module")
def manager(qapp):
    # Constructing the manager loads all of FF8GameData once; init_from_file
    # fully re-initialises the parsed monster (and its textures) on every
    # call, so it is safe to reuse this instance across tests.
    return IfritManager(str(PROJECT_ROOT / "FF8GameData"))


@pytest.fixture(autouse=True)
def _clean_vincent_tim_temp(manager):
    """IfritManager.temp_path (Ifrit/temp_vincent_tim) is a single fixed
    directory shared by every IfritManager instance/run, not a per-test tmp
    dir -- and analyze() never cleans up its own leftovers (only the widget's
    _import() does). Any stale PNG/meta files left behind by a previous run
    (crashed, interrupted, or just a different monster) would otherwise get
    silently swept into this test's texture count on export/inject. Clear it
    before and after every test so each case is self-contained."""
    def _clear():
        if manager.temp_path.exists():
            shutil.rmtree(manager.temp_path)
    _clear()
    yield
    _clear()


def _load(manager, monster_name, tmp_path, out_name="work.dat"):
    """Copy the real .dat into tmp_path and load it (never touch extracted_files)."""
    work = tmp_path / out_name
    shutil.copy(BATTLE_DIR / monster_name, work)
    manager.init_from_file(str(work))
    return work


def _decoded_rgba(tim_bytes: bytes) -> np.ndarray:
    """Decode a TIM's pixel data through its palette (row 0 -- every real
    monster TIM has exactly one CLUT row) into an (H, W, 4) uint8 array."""
    decoded = decode_tim(tim_bytes, 0, palette_index=0)
    assert decoded is not None, "not a valid TIM"
    return np.array(decoded.image.convert("RGBA"))


@pytest.mark.parametrize("monster_name", MONSTER_MARK)
def test_texture_roundtrip_no_edit_is_pixel_exact(manager, monster_name, tmp_path):
    """A no-edit export -> reimport -> save reproduces every texture
    pixel-for-pixel (after decoding through the palette) and leaves the
    overall file size unchanged."""
    work = _load(manager, monster_name, tmp_path)
    original_size = len(work.read_bytes())
    enemy = manager.enemy

    original_tims = [bytes(t["data"]) for t in enemy.texture_data["texture_data"]]
    assert original_tims, f"{monster_name}: no textures found"

    widget = IfritTextureWidget(manager)
    widget.save_file()

    new_tims = [bytes(t["data"]) for t in enemy.texture_data["texture_data"]]
    assert len(new_tims) == len(original_tims), (
        f"{monster_name}: texture count changed ({len(original_tims)} -> {len(new_tims)})"
    )

    for index, (before, after) in enumerate(zip(original_tims, new_tims)):
        label = f"{monster_name} texture {index}"
        img_before = _decoded_rgba(before)
        img_after = _decoded_rgba(after)
        assert img_before.shape == img_after.shape, f"{label}: dimensions changed"
        assert np.array_equal(img_before, img_after), (
            f"{label}: decoded RGBA pixels differ after a no-edit round trip "
            f"(max abs diff: {np.abs(img_before.astype(int) - img_after.astype(int)).max()})"
        )

    out = tmp_path / "out.dat"
    manager.save_file(str(out))
    assert len(out.read_bytes()) == original_size, f"{monster_name}: file size changed on save"
