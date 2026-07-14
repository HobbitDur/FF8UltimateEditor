"""Real-file round-trip test for Alexander (battle stage a0stgXXX.x viewer/editor).

Unlike test_stagefs.py (which builds a synthetic fs/fi/fl archive), this test loads
the *original* game battle stages from extracted_files/battle/ and checks the
manager's save path.

A directly-loaded, unedited stage keeps its parsed ``raw`` structure and
``AlexanderManager.save`` re-serialises that structure. The writer rebuilds the
geometry header and per-group offsets from the parsed layout, so the strongest
invariant we assert is that this reserialisation is byte-for-byte identical to the
original file (byte-exact lossless copy). This is checked across several stages.

These need the real files (extracted_files/battle/a0stgXXX.x) and are skipped
otherwise (see the ff8data marker in the project-root conftest.py).
"""
import pathlib

import pytest

from Alexander.alexandermanager import AlexanderManager

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
BATTLE_DIR = PROJECT_ROOT / "extracted_files" / "battle"

STAGE_IDS = [0, 1, 2, 3, 4, 5]


def _stage_path(stage_id):
    return BATTLE_DIR / f"a0stg{stage_id:03d}.x"


@pytest.mark.ff8data("extracted_files/battle/a0stg000.x")
def test_real_stage_load_produces_geometry():
    """Loading the real stage yields meaningful parsed model data (non-empty)."""
    manager = AlexanderManager()
    manager.load_stage_file(str(_stage_path(0)))

    assert manager.is_loaded
    assert manager.enemy.raw is not None
    # geometry: at least some objects distributed across the 4 groups
    assert manager._all_objects, "no geometry objects parsed from the real stage"
    assert len(manager._group_of_object) == len(manager._all_objects)
    # textures decoded for the visible geometry
    assert manager.visible_textures(), "no textures decoded from the real stage"


@pytest.mark.ff8data(
    "extracted_files/battle/a0stg000.x",
    "extracted_files/battle/a0stg001.x",
    "extracted_files/battle/a0stg002.x",
    "extracted_files/battle/a0stg003.x",
    "extracted_files/battle/a0stg004.x",
    "extracted_files/battle/a0stg005.x",
)
@pytest.mark.parametrize("stage_id", STAGE_IDS)
def test_real_stage_roundtrip_is_byte_exact(stage_id, tmp_path):
    """Load a real stage, re-save the unedited model, expect identical bytes.

    The writer rebuilds the geometry header/offsets from the parsed ``raw``
    structure rather than copying the whole file, so this also proves the parse
    is complete and lossless.
    """
    path = _stage_path(stage_id)
    if not path.exists():
        pytest.skip(f"{path.name} not available")

    manager = AlexanderManager()
    manager.load_stage_file(str(path))

    out = tmp_path / path.name
    note = manager.save(str(out))

    assert out.read_bytes() == path.read_bytes(), (
        f"{path.name} not byte-exact after round-trip (note: {note!r})")


@pytest.mark.ff8data("extracted_files/battle/a0stg000.x")
def test_real_stage_reload_matches(tmp_path):
    """A saved stage reloads into an equivalent model (object/group counts survive)."""
    path = _stage_path(0)
    manager = AlexanderManager()
    manager.load_stage_file(str(path))
    before = (len(manager._all_objects), list(manager._group_of_object))

    out = tmp_path / path.name
    manager.save(str(out))

    reloaded = AlexanderManager()
    reloaded.load_stage_file(str(out))
    after = (len(reloaded._all_objects), list(reloaded._group_of_object))
    assert after == before
