"""Real-file round-trip tests for the Seed tool (field model viewer/editor).

The Seed tool parses FF8 field character models into the same data structures the
Ifrit3D battle viewer uses. Two on-disk shapes are covered here with the original
game files from extracted_files/ (skipped in CI, ff8data marker):

- chara.one: a per-field container of NPC models + main-character animation blocks.
  Two file layouts exist. The PC "headered" layout (field/mapdata/**) supports
  saving: SeedManager re-serialises every loaded model's animations and, with no
  edits, must reproduce the container byte-for-byte (write_packed_animation_section
  is the exact inverse of the parser). The "headerless" PS-style layout
  (world/esk/chara.one) is read-only in the tool; saving deliberately raises.

- d0xx.mch: a standalone main-character model (main_chr.fs). Seed is a viewer for
  these (no .mch writer), so the invariant is a successful parse into meaningful
  geometry (bones / vertices / faces / textures).

Why the headered round-trip is byte-exact rather than just idempotent: loading an
entry only parses the packed animation section; unless the user edits a pose/bone,
_build_entry_block reproduces the original bytes and _rebuild leaves the entry in
place, so save is a true no-op on unmodified models. This is empirically verified
below (load every entry, then save) and is a stronger guarantee than idempotency.
"""
import pathlib

import pytest
from PyQt6.QtWidgets import QApplication

from Seed.seedmanager import SeedManager

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent

# Headerless PS-layout container (NPCs only, read-only in the tool).
ESK_CHARA_ONE_REL = "extracted_files/world/esk/chara.one"
ESK_CHARA_ONE = PROJECT_ROOT / ESK_CHARA_ONE_REL

# Headered PC-layout container: one main-character reference (d000, resolved from
# field/model/main_chr/d000.mch) + one NPC (o054). Exercises the save round-trip
# and the main_chr .mch resolution path.
HEADERED_CHARA_ONE_REL = "extracted_files/field/mapdata/bg/bgmd2_5/chara.one"
HEADERED_CHARA_ONE = PROJECT_ROOT / HEADERED_CHARA_ONE_REL

# Standalone main-character model (also referenced by the headered container above).
D000_MCH_REL = "extracted_files/field/model/main_chr/d000.mch"
D000_MCH = PROJECT_ROOT / D000_MCH_REL


@pytest.fixture(scope="module")
def qapp():
    # SeedManager builds QPixmap textures on load, which needs a QApplication.
    app = QApplication.instance() or QApplication([])
    yield app


def _geometry_counts(manager):
    object_data = manager.enemy.geometry_data.object_data[0]
    vertices = sum(vd.nb_vertices for vd in object_data.vertices_data)
    return len(manager.enemy.bone_data.bones), vertices, object_data.nb_triangle, object_data.nb_quad


# --------------------------------------------------------------- headerless chara.one

@pytest.mark.ff8data(ESK_CHARA_ONE_REL)
def test_real_esk_headerless_chara_one_loads_and_reloads(qapp, tmp_path):
    """The read-only PS-layout container parses its NPC entries, builds a
    meaningful model for one, and its entry list survives a reload. Saving is
    unsupported for this layout and must raise (documented, not a bug)."""
    manager = SeedManager()
    entries = manager.load_chara_one(str(ESK_CHARA_ONE))
    assert manager.chara_one.headerless, "esk/chara.one is expected to be the headerless PS layout"
    assert entries, "no entries parsed from the real chara.one"
    assert all(not entry.is_main for entry in entries), "headerless container should hold only NPC models"

    manager.load_entry(entries[0].index)
    bones, vertices, triangles, quads = _geometry_counts(manager)
    assert bones > 0 and vertices > 0
    assert triangles + quads > 0, "model has no faces"
    assert manager.enemy.animation_data.nb_animations > 0, "NPC model has no animations"
    assert manager.texture_data, "no textures built for the model"

    # Entry list is stable on reload (idempotent parse of the same bytes).
    reloaded = SeedManager()
    reloaded_entries = reloaded.load_chara_one(str(ESK_CHARA_ONE))
    assert [entry.name for entry in reloaded_entries] == [entry.name for entry in entries]

    # Saving a headerless container is deliberately not supported.
    with pytest.raises(ValueError):
        manager.save_chara_one(str(tmp_path / "nope.one"))


# ----------------------------------------------------------------- headered chara.one

@pytest.mark.ff8data(HEADERED_CHARA_ONE_REL, D000_MCH_REL)
def test_real_headered_chara_one_roundtrip_is_byte_exact(qapp, tmp_path):
    """Load every entry (main d000 via main_chr/d000.mch + NPC o054), then save
    with no edits: the container must be reproduced byte-for-byte."""
    manager = SeedManager()
    entries = manager.load_chara_one(str(HEADERED_CHARA_ONE))
    assert not manager.chara_one.headerless
    assert entries, "no entries parsed from the headered chara.one"
    assert any(entry.is_main for entry in entries), "expected a main-character reference entry"
    assert manager.main_chr_folder is not None, "main_chr folder was not auto-resolved"

    for entry in entries:
        manager.load_entry(entry.index)  # parses each model's animation section
    assert len(manager.models) == len(entries)

    out = tmp_path / "chara.one"
    modified = manager.save_chara_one(str(out))
    assert modified == [], "no edits were made, yet models were reported as modified"
    assert out.read_bytes() == HEADERED_CHARA_ONE.read_bytes(), \
        "no-edit save of the headered container is not byte-exact"


@pytest.mark.ff8data(HEADERED_CHARA_ONE_REL, D000_MCH_REL)
def test_real_headered_chara_one_reload_preserves_entries(qapp, tmp_path):
    """A saved container reloads to the same entry list (names + main/npc kind)."""
    manager = SeedManager()
    entries = manager.load_chara_one(str(HEADERED_CHARA_ONE))
    for entry in entries:
        manager.load_entry(entry.index)
    out = tmp_path / "chara.one"
    manager.save_chara_one(str(out))

    reloaded = SeedManager()
    reloaded_entries = reloaded.load_chara_one(str(out))
    assert [(e.name, e.is_main) for e in reloaded_entries] == [(e.name, e.is_main) for e in entries]


# ---------------------------------------------------------------------- standalone mch

@pytest.mark.ff8data(D000_MCH_REL)
def test_real_d000_mch_parses_meaningful_geometry(qapp):
    """load_mch on a real main-character model yields non-empty geometry and a
    decoded texture (Seed is a pure viewer for .mch: parse-only invariant)."""
    manager = SeedManager()
    manager.load_mch(str(D000_MCH))

    assert manager.enemy.name == "d000"
    assert manager.current_entry_index is None, "standalone mch should not set a chara.one entry index"
    bones, vertices, triangles, quads = _geometry_counts(manager)
    assert bones > 0, "no bones parsed"
    assert vertices > 0, "no vertices parsed"
    assert triangles > 0 and quads > 0, "expected both triangles and quads in the model"
    assert manager.enemy.tim_images, "no TIM textures listed"
    assert any(tim is not None for tim in manager.enemy.tim_images), "no TIM decoded"
    assert manager.texture_data, "no viewer textures built"
