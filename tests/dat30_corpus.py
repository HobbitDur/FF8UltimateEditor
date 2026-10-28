"""Corpus run of every 30 fps conversion over extracted_files (not a pytest file: run it by hand).

    py -3.14 tests/dat30_corpus.py [--out report.txt] [--work folder]

Converts COPIES (in --work, a temp folder by default) of:
- every battle model c0m / dXc / dXw (Ifrit's conversion: animations, sequences, camera; a character
  body with all its weapons as one family),
- r0win.dat (Watts), every a0stgNNN.x camera (Alexander), the 221 exe effect camera tracks and the
  MAGxxx_B.00 cameras (Fujin),
and reports per file: converted / refused (why) / over a vanilla memory cap (FF8GameData/dat/
battlememory.py), plus the monster arena of every scene.out encounter once its monsters are
converted (stage up to its TIM + every distinct enabled monster's [section 1, section 10) + the
vertex workspace, cap 204,800 bytes).
"""
import argparse
import collections
import pathlib
import shutil
import struct
import sys
import tempfile
import time

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

EXTRACTED = PROJECT_ROOT / "extracted_files"
BATTLE = EXTRACTED / "battle"


def _log(lines, text=""):
    print(text, flush=True)
    lines.append(text)


def run_models(work, lines):
    from Ifrit.ifritmanager import IfritManager
    manager = IfritManager(str(PROJECT_ROOT / "FF8GameData"))
    names = sorted(p.name for p in BATTLE.iterdir() if IfritManager.is_battle_model_file(p.name))
    for name in names:
        shutil.copyfile(BATTLE / name, work / name)
    # one call per family (a character body + its weapons), one per monster: the families stay whole
    groups = collections.OrderedDict()
    for name in names:
        slot = IfritManager.character_slot_of(name)
        groups.setdefault(("d", slot) if slot is not None else ("m", name), []).append(str(work / name))
    status = collections.Counter()
    _log(lines, f"=== Battle models: {len(names)} files ===")
    for group in groups.values():
        for report in manager.convert_file_list_to_fps(group, 30):
            name = report['file']
            if report['error'] or report['skipped_list']:
                why = report['error'] or "; ".join(f"{a}: {r}" for a, r in report['skipped_list'])
                state = "not a model" if "not a monster" in why or "no animation" in why else "REFUSED"
                status[state] += 1
                _log(lines, f"  {state:11} {name}: {why}")
                continue
            sequence = report.get('sequence_report')
            count = sequence.count() if sequence is not None else {}
            manual = count.get('manual', 0) + count.get('refused', 0)
            camera = report.get('camera_report')
            over = [w for w in report['warning_list'] if "over the" in w]
            status["converted"] += 1
            status["over cap"] += bool(over)
            _log(lines, f"  converted   {name}: {report['nb_converted']} anims"
                        + (f", split {[(a, n, p) for a, n, p, _ids in report['split_list']]}" if report['split_list'] else "")
                        + (f", seq {count.get('rewritten', 0)}/{count.get('unchanged', 0)}"
                           + (f"/fallback {count['fallback']}" if count.get('fallback') else "")
                           + (f" MANUAL {manual}" if manual else "") if sequence is not None else "")
                        + (f", camera {camera.nb_keyframe} kf max {camera.max_block_ticks} ticks" if camera else ""))
            for warning in report['warning_list']:
                _log(lines, f"      warning: {warning}")
    _log(lines, f"  -> {dict(status)}")
    return status


def run_arena(work, lines):
    """Monster arena per scene.out encounter with the converted monsters."""
    from FF8GameData.battlestage.battlestageanalyser import stage_geometry_offset
    from FF8GameData.dat.battlememory import MONSTER_ARENA_CAP, monster_arena_bytes, section_offsets
    scene = (BATTLE / "scene.out").read_bytes()
    stage_cache, monster_cache = {}, {}

    def stage_part(stage_id):
        if stage_id not in stage_cache:
            path = BATTLE / f"a0stg{stage_id:03d}.x"
            data = path.read_bytes()
            geometry = stage_geometry_offset(data, stage_id)
            header = struct.unpack_from("<8I", data, geometry)
            workspace = 0
            for group in range(4):
                start, end = header[1 + group], header[2 + group]
                if start == end:
                    continue
                anim = struct.unpack_from("<I", data, geometry + start + 12)[0]
                workspace = max(workspace, struct.unpack_from("<I", data, geometry + start + anim - 4)[0])
            stage_cache[stage_id] = ((geometry + header[6] + 3) & ~3, workspace)
        return stage_cache[stage_id]

    def monster(com_id, folder):
        key = (com_id, folder)
        if key not in monster_cache:
            path = folder / f"c0m{com_id - 16:03d}.dat"
            if not path.exists():
                monster_cache[key] = None
            else:
                data = path.read_bytes()
                offsets = section_offsets(data)
                vertices = struct.unpack_from("<I", data, offsets[2] - 4)[0] if len(offsets) > 11 else 0
                monster_cache[key] = (monster_arena_bytes(data), vertices)
        return monster_cache[key]

    over_vanilla, over_converted, worst = 0, [], (0, None)
    nb = 0
    for encounter in range(len(scene) // 128):
        record = scene[encounter * 128:(encounter + 1) * 128]
        stage_id = record[0]
        if not (BATTLE / f"a0stg{stage_id:03d}.x").exists():
            continue
        nb += 1
        enabled = record[7]
        com_ids = sorted({com for slot, com in enumerate(record[56:64])
                          if (enabled >> (7 - slot)) & 1 and com >= 16})
        totals = []
        for folder in (BATTLE, work):
            geometry, workspace = stage_part(stage_id)
            infos = [info for info in (monster(com, folder) for com in com_ids) if info]
            totals.append(geometry + sum(i[0] for i in infos) + 8 * max([workspace] + [i[1] for i in infos]))
        over_vanilla += totals[0] > MONSTER_ARENA_CAP
        if totals[1] > MONSTER_ARENA_CAP:
            over_converted.append((encounter, stage_id, totals[1]))
        worst = max(worst, (totals[1], encounter))
    _log(lines, f"=== Monster arena ({nb} encounters, cap {MONSTER_ARENA_CAP}) ===")
    _log(lines, f"  vanilla over cap: {over_vanilla}; converted over cap: {len(over_converted)}; "
                f"worst converted {worst[0]} (encounter {worst[1]})")
    for encounter, stage_id, total in sorted(over_converted, key=lambda e: -e[2])[:20]:
        _log(lines, f"    encounter {encounter} (stage {stage_id}): {total} (+{total - MONSTER_ARENA_CAP})")
    return len(over_converted)


def run_r0win(lines):
    from FF8GameData.gamedata import GameData
    from Watts.wattsmanager import WattsManager
    manager = WattsManager(GameData(str(PROJECT_ROOT / "FF8GameData")))
    manager.load_file(str(BATTLE / "r0win.dat"))
    try:
        report = manager.convert_to_real30()
    except ValueError as error:
        _log(lines, f"=== r0win.dat: REFUSED: {error}")
        return
    _log(lines, f"=== r0win.dat: converted, {len(manager.to_bytes())} bytes; poses "
                + ", ".join(f"{n} {b}/{w}" for n, b, w, _s in report['poses'])
                + f"; camera {report['camera_report'].summary()}"
                + "".join(f"; warning: {w}" for w in report['warning_list']))


def run_cameras(lines):
    from FF8GameData.battlestage.stagecamera import STAGE_CAMERA_OFFSET, camera_section
    from FF8GameData.dat import camera30
    from FF8GameData.dat.sequencevm import camera_sequence_vm
    from FF8GameData.gamedata import GameData
    from Fujin.cameraeffectmanager import CameraEffectManager
    game_data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    game_data.load_camera_sequence_data()
    vm = camera_sequence_vm(game_data)

    def convert(kind, items):
        ok, refused, grown, worst = 0, [], [], 0
        for name, data in items:
            report = camera30.CameraConversionReport()
            try:
                new = convert_one(data, report)
            except ValueError as error:
                refused.append((name, str(error)))
                continue
            ok += 1
            worst = max(worst, report.max_block_ticks)
            if len(new) != len(data):
                grown.append(name)
        _log(lines, f"=== {kind}: {ok} converted, {len(refused)} refused, {len(grown)} grown, longest block "
                    f"{worst} ticks (cap {camera30.MAX_BLOCK_TICKS}) ===")
        for name, error in refused:
            _log(lines, f"  REFUSED {name}: {error}")

    def convert_one(data, report):
        return camera30.convert_track_bytes(vm, data, 2, report)
    convert("Stage cameras (a0stgNNN.x)",
            [(f"a0stg{s:03d}.x", camera_section((BATTLE / f"a0stg{s:03d}.x").read_bytes(), s))
             for s in sorted(STAGE_CAMERA_OFFSET)])
    effects = CameraEffectManager(game_data)
    effects.load_exe(str(EXTRACTED / "FF8_EN.exe"))
    convert("Exe effect camera tracks", [(f"effect {e}", t.original) for e, t in sorted(effects.tracks.items())])

    def convert_one(data, report):  # noqa: F811 - MAG files: the whole file, the camera in its room
        return camera30.convert_mag_camera(vm, data, 2, report)
    mags = [(p.name, p.read_bytes()) for p in sorted((EXTRACTED / "magic").glob("MAG*_B.00"))]
    mags = [(name, data) for name, data in mags if camera30.mag_camera_offset(data) is not None]
    convert("MAG cameras (MAGxxx_B.00)", mags)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", help="Also write the report there")
    parser.add_argument("--work", help="Folder for the converted copies (default: a temp folder)")
    args = parser.parse_args()
    lines = []
    start = time.time()
    work = pathlib.Path(args.work) if args.work else pathlib.Path(tempfile.mkdtemp(prefix="dat30_corpus_"))
    work.mkdir(parents=True, exist_ok=True)
    run_cameras(lines)
    run_r0win(lines)
    run_models(work, lines)
    run_arena(work, lines)
    _log(lines, f"({time.time() - start:.0f} s; converted copies in {work})")
    if args.out:
        pathlib.Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
