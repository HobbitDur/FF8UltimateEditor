"""
End-to-end glTF round-trip for the Ifrit3D export/import subtool:
    load monster .dat  ->  export .glb  ->  import the .glb back  ->  check the
    rebuilt mesh is valid and stable across a second export, and that saving the
    result back to disk rewrites the geometry section and nothing else.

This needs a real monster .dat (copyright, gitignored under extracted_files/),
so the whole module skips when that file is not present — matching the project's
"no committed game data" convention (see the top-level conftest.py).
"""
import pathlib
import sys

import pytest
from PyQt6.QtWidgets import QApplication

from FF8GameData.gamedata import GameData
from FF8GameData.dat.monsteranalyser import MonsterAnalyser
from Ifrit.IfritAI.AICompiler.AIDecompiler import AIDecompiler
from Ifrit.Ifrit3D.gltfexporter import GltfExporter
from Ifrit.Ifrit3D.gltfimporter import GltfImporter

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
BATTLE_DIR = PROJECT_ROOT / "extracted_files" / "battle"
DAT_FILE = BATTLE_DIR / "c0m003.dat"

HEADER_SECTION = MonsterAnalyser.DAT_FILE_SECTION_LIST.index("header")
GEOMETRY_SECTION = MonsterAnalyser.DAT_FILE_SECTION_LIST.index("model_geometry")

# A spread of monsters rather than c0m003 alone: different bone counts, object
# counts and primitive mixes exercise different paths through the importer.
ROUNDTRIP_IDS = ["001", "002", "003", "010", "020"]

pytestmark = pytest.mark.skipif(
    not DAT_FILE.exists(),
    reason="monster .dat not available (copyright, not committed): "
           "extracted_files/battle/c0m003.dat")


class _Holder:
    """Minimal stand-in for IfritManager so GltfExporter can read the model; an
    empty texture list makes the exporter fall back to a flat material, so no
    QImage/texture handling is needed."""

    def __init__(self, enemy):
        self.enemy = enemy
        self.texture_data = []


def _load(dat_path, game_data, decompiler):
    monster = MonsterAnalyser(game_data)
    monster.load_file_data(str(dat_path), game_data)
    monster.analyse_loaded_data(game_data, decompiler)
    return monster


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture(scope="module")
def game_data():
    gd = GameData(str(PROJECT_ROOT / "FF8GameData"))
    gd.load_all()
    return gd


@pytest.fixture(scope="module")
def decompiler(game_data):
    return AIDecompiler(game_data, [], None)


@pytest.fixture(scope="module")
def enemy(game_data, decompiler):
    return _load(DAT_FILE, game_data, decompiler)


def test_export_creates_glb(qapp, enemy, tmp_path):
    glb = tmp_path / "model.glb"
    GltfExporter(_Holder(enemy)).export(str(glb))
    assert glb.exists()
    assert glb.read_bytes()[:4] == b"glTF"


def test_import_rebuilds_nonempty_geometry(qapp, enemy, tmp_path):
    glb = tmp_path / "model.glb"
    GltfExporter(_Holder(enemy)).export(str(glb))

    importer = GltfImporter()
    geometry = importer.import_geometry(str(glb), original_end=enemy.geometry_data.end)

    assert geometry.nb_object == 1
    assert importer.stats["vertices"] > 0
    assert importer.stats["triangles"] > 0
    # geometry must re-serialize to bytes without error
    assert isinstance(geometry.get_byte(), (bytes, bytearray))


def test_roundtrip_is_stable_on_second_pass(qapp, enemy, tmp_path):
    """Export -> import -> re-export -> import should converge to the same
    vertex/triangle counts (the lossy quad->tri split happens only once)."""
    exporter = GltfExporter(_Holder(enemy))
    glb1 = tmp_path / "pass1.glb"
    exporter.export(str(glb1))
    first = GltfImporter()
    geo1 = first.import_geometry(str(glb1), original_end=enemy.geometry_data.end)

    # Feed the rebuilt geometry back into the model and export again.
    enemy.geometry_data = geo1
    if len(enemy.section_raw_data) > 2:
        enemy.section_raw_data[2] = geo1.get_byte()

    glb2 = tmp_path / "pass2.glb"
    GltfExporter(_Holder(enemy)).export(str(glb2))
    second = GltfImporter()
    second.import_geometry(str(glb2), original_end=geo1.end)

    assert second.stats["vertices"] == first.stats["vertices"]
    assert second.stats["triangles"] == first.stats["triangles"]


@pytest.mark.parametrize("monster_id", ROUNDTRIP_IDS)
def test_glb_import_touches_only_the_geometry_section(qapp, game_data, decompiler,
                                                      monster_id, tmp_path):
    """The whole round-trip, through a real save: load -> export .glb -> import
    back -> write_data_to_file -> reload and diff the rebuilt file section by
    section.

    Only the mesh is rebuilt from the .glb, so the geometry section is expected
    to change (quads split to triangles, per-corner vertices merged, CLUT bits
    dropped) and the header follows it, since a resized section 2 shifts every
    offset after it. Everything else — skeleton, animations, stats, AI, sounds —
    must come through the save untouched.

    The diff is against a plain no-glb load+save of the same file, not against
    the original bytes: a no-edit save already rewrites the alignment padding at
    the tail of each animation's bit-stream, which is expected and covered by
    test_realfile_monster.py. Using it as the baseline keeps this test about what
    the glTF import itself perturbs.
    """
    dat_path = BATTLE_DIR / f"c0m{monster_id}.dat"
    if not dat_path.exists():
        pytest.skip(f"monster .dat not available (copyright, not committed): {dat_path.name}")

    baseline_path = tmp_path / f"c0m{monster_id}_baseline.dat"
    _load(dat_path, game_data, decompiler).write_data_to_file(game_data, str(baseline_path))

    glb_path = tmp_path / f"c0m{monster_id}.glb"
    rebuilt_path = tmp_path / f"c0m{monster_id}_rebuilt.dat"
    GltfExporter(_Holder(_load(dat_path, game_data, decompiler))).export(str(glb_path))

    # Import into a freshly loaded original so every other section is untouched.
    rebuilt = _load(dat_path, game_data, decompiler)
    stats = GltfImporter().import_into_enemy(str(glb_path), rebuilt)
    assert stats["vertices"] > 0 and stats["triangles"] > 0
    rebuilt.write_data_to_file(game_data, str(rebuilt_path))

    # Reload both files so each is sliced by its own header: a size change in one
    # section must not smear into the ones after it.
    baseline_sections = _load(baseline_path, game_data, decompiler).section_raw_data
    rebuilt_sections = _load(rebuilt_path, game_data, decompiler).section_raw_data
    assert len(rebuilt_sections) == len(baseline_sections)

    changed = [index for index, (before, after)
               in enumerate(zip(baseline_sections, rebuilt_sections))
               if bytes(before) != bytes(after)]
    unexpected = [f"{index} ({MonsterAnalyser.DAT_FILE_SECTION_LIST[index]})"
                  for index in changed if index not in (HEADER_SECTION, GEOMETRY_SECTION)]
    assert not unexpected, f"c0m{monster_id}: sections changed by a mesh-only import: " \
                           f"{', '.join(unexpected)}"
