"""glTF round-trip harness for FF8 monster .dat files.

Full round: load original .dat  ->  export .glb  ->  import the .glb back into
the same model  ->  save .dat  ->  compare against the original, per section.

Only the mesh (section 2) is rebuilt from the glb; skeleton, animations and
every other section are preserved from the loaded original (see
Ifrit/Ifrit3D/gltfimporter.py for why bones/anim are not glb-invertible). The
per-section diff therefore shows section 2 changing (quads split to triangles,
per-corner vertices merged, CLUT bits dropped) while the rest stays byte-stable.

Usage (from the repo root, with the project venv):
    python roundtrip_gltf.py 001 002 003        # specific monster ids
    python roundtrip_gltf.py --all              # every c0mNNN.dat in battle/
    python roundtrip_gltf.py 001 --keep         # keep the .glb / rebuilt .dat
"""

import sys
import pathlib

ROOT = pathlib.Path(__file__).parent.resolve()
sys.path.insert(0, str(ROOT))

from FF8GameData.gamedata import GameData
from FF8GameData.dat.monsteranalyser import MonsterAnalyser
from Ifrit.IfritAI.AICompiler.AIDecompiler import AIDecompiler
from Ifrit.Ifrit3D.gltfexporter import GltfExporter
from Ifrit.Ifrit3D.gltfimporter import GltfImporter

BATTLE = ROOT / "extracted_files" / "battle"
OUT_DIR = ROOT / "roundtrip_out"


class _Holder:
    """Minimal stand-in for IfritManager so GltfExporter can read the model."""
    def __init__(self, enemy):
        self.enemy = enemy
        self.texture_data = []          # exporter falls back to a flat material


def _section_bounds(enemy):
    pos = enemy.header_data['section_pos']
    n = enemy.header_data['nb_section']
    fs = enemy.header_data['file_size']
    return [(pos[i], pos[i + 1] if i + 1 < n else fs) for i in range(n)]


def _load(dat_path, game_data, decompiler):
    enemy = MonsterAnalyser(game_data)
    enemy.load_file_data(str(dat_path), game_data)
    enemy.analyse_loaded_data(game_data, decompiler)
    return enemy


def _section_slices(enemy):
    """Raw bytes of each section, sliced by *this* file's own header."""
    return [bytes(s) for s in enemy.section_raw_data]


def _diff_report(orig_enemy, rebuilt_enemy):
    """Compare the two models section by section (each sliced by its own header),
    so a size change in one section does not smear into the following ones."""
    names = MonsterAnalyser.DAT_FILE_SECTION_LIST
    a = _section_slices(orig_enemy)
    b = _section_slices(rebuilt_enemy)
    changed = []
    lines = []
    for i in range(max(len(a), len(b))):
        sa = a[i] if i < len(a) else b""
        sb = b[i] if i < len(b) else b""
        if sa == sb:
            continue
        changed.append(i)
        nm = names[i] if i < len(names) else "?"
        m = min(len(sa), len(sb))
        ndiff = sum(1 for k in range(m) if sa[k] != sb[k]) + abs(len(sa) - len(sb))
        size = f"{len(sa)}->{len(sb)}" if len(sa) != len(sb) else f"{len(sa)}"
        lines.append(f"      sec {i:2d} {nm:16s} size {size:>13s}  {ndiff} bytes differ")
    return changed, lines


def run_one(monster_id: str, game_data, decompiler, keep=False):
    dat_path = BATTLE / f"c0m{monster_id}.dat"
    if not dat_path.exists():
        print(f"c0m{monster_id}.dat: not found")
        return None
    OUT_DIR.mkdir(exist_ok=True)
    glb_path = OUT_DIR / f"c0m{monster_id}.glb"
    rebuilt_dat = OUT_DIR / f"c0m{monster_id}_rebuilt.dat"

    original_bytes = dat_path.read_bytes()

    # 1) load + 2) export glb
    enemy = _load(dat_path, game_data, decompiler)
    GltfExporter(_Holder(enemy)).export(str(glb_path))

    # 3) import glb back into a freshly-loaded original (keeps all other sections)
    enemy = _load(dat_path, game_data, decompiler)
    stats = GltfImporter().import_into_enemy(str(glb_path), enemy)

    # 4) save
    enemy.write_data_to_file(game_data, str(rebuilt_dat))
    rebuilt_bytes = rebuilt_dat.read_bytes()

    # 5) compare per section, each file sliced by its own header
    orig_enemy = _load(dat_path, game_data, decompiler)
    rebuilt_enemy = _load(rebuilt_dat, game_data, decompiler)
    changed, lines = _diff_report(orig_enemy, rebuilt_enemy)

    size_note = "" if len(original_bytes) == len(rebuilt_bytes) \
        else f"  file {len(original_bytes)}->{len(rebuilt_bytes)}"
    changed_str = ", ".join(f"sec{k}" for k in changed) or "none"
    print(f"c0m{monster_id}: verts={stats['vertices']} tris={stats['triangles']} "
          f"bones={stats['bones_used']} tex={stats['textures']} | changed: {changed_str}{size_note}")
    for line in lines:
        print(line)

    if not keep:
        glb_path.unlink(missing_ok=True)
        rebuilt_dat.unlink(missing_ok=True)
    return changed


def main(argv):
    keep = "--keep" in argv
    argv = [a for a in argv if a != "--keep"]
    if "--all" in argv:
        ids = sorted(p.stem[3:] for p in BATTLE.glob("c0m*.dat"))
        # skip known garbage files (id 0, 127, >143) as the tools do elsewhere
        ids = [i for i in ids if 0 < int(i) < 144 and int(i) != 127]
    else:
        ids = argv or ["001", "002", "003", "010", "020"]

    game_data = GameData(str(ROOT / "FF8GameData"))
    game_data.load_all()
    decompiler = AIDecompiler(game_data, [], None)

    for monster_id in ids:
        try:
            run_one(monster_id, game_data, decompiler, keep=keep)
        except Exception as exc:
            import traceback
            print(f"c0m{monster_id}: ERROR {type(exc).__name__}: {exc}")
            traceback.print_exc()


if __name__ == "__main__":
    main(sys.argv[1:])
