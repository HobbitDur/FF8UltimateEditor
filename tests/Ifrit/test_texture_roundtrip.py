"""Export -> reimport -> save round trip for the Ifrit static texture editor.

The texture widget (Ifrit.IfritTexture.ifrittexturewidget.IfritTextureWidget)
edits battle ``c0mNNN.dat`` section 11 (the monster's TIM textures). Monster
TIMs are read and written natively (IfritManager._analyze_native /
_build_tims_native): each TIM becomes a texture PNG + a palette PNG (one pixel
row per CLUT row) + a meta file, and saving rebuilds the TIM from them while
keeping every CLUT word whose color did not change and every texel's palette
index where it still shows what the source TIM rendered there. So:

    IfritManager.init_from_file(path)        # load a monster .dat
    IfritTextureWidget(manager).save_file()  # export pixmaps -> rebuild TIMs
    IfritManager.save_file(path)             # re-serialise the .dat to disk

A no-edit round trip is byte-exact, and a palette-only edit moves no texel to
another slot (palette swaps recolor by slot; the old VincentTim re-quantizing
path moved thousands of texels between duplicate/near colors).

Needs the real (copyright, gitignored) monster files under extracted_files/battle/,
so it is marked ``ff8data`` and skipped in CI / when those files are absent.
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
        assert before == after, f"{label}: TIM bytes changed after a no-edit round trip"

    out = tmp_path / "out.dat"
    manager.save_file(str(out))
    assert len(out.read_bytes()) == original_size, f"{monster_name}: file size changed on save"


@pytest.mark.ff8data("extracted_files/battle/c0m071.dat")
def test_palette_only_edit_keeps_every_texel_index(manager, tmp_path):
    """Replacing only the palette (here: red and blue swapped) rewrites the CLUT and leaves
    every texel on its slot, even though the texture view still shows the old colors."""
    from PyQt6.QtGui import QImage, QPixmap
    from FF8GameData.tim.timfile import PalettedTim

    _load(manager, "c0m071.dat", tmp_path)
    before = PalettedTim.parse(bytes(manager.enemy.texture_data["texture_data"][0]["data"]))
    widget = IfritTextureWidget(manager)
    palette_widget = widget._texture_widgets[0]._palette_image_widget
    swapped = palette_widget.get_image().toImage().rgbSwapped()
    palette_widget.set_image(QPixmap.fromImage(QImage(swapped)))
    widget.save_file()

    after = PalettedTim.parse(bytes(manager.enemy.texture_data["texture_data"][0]["data"]))
    assert after.indices == before.indices
    for old, new in zip(before.clut_rows[0], after.clut_rows[0]):
        # red and blue fields swapped, green and the STP bit kept
        swapped_word = (old & 0x83E0) | ((old & 0x1F) << 10) | ((old >> 10) & 0x1F)
        assert new == (swapped_word or 0x8000 if old else 0)
