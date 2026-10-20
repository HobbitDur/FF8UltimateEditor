"""Audit all extracted MAG/MA8 files without distributing game assets.

python -m Laguna.ResearchScript.sweep_mag_files extracted_files --out docs/mag-file-census.json
Reports content classification, section coverage, script decode errors and embedded cameras.
This is a structural/round-trip audit, not an in-game playback certification.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from FF8GameData.gamedata import GameData
from Fujin.cameraeffectmanager import CameraEffectManager, CameraTrack
from Laguna.lagunamanager import LagunaManager


def sweep(root):
    root = Path(root)
    counts = Counter()
    files = []
    failures = []
    vm = CameraEffectManager(GameData("FF8GameData")).vm
    archives = [root/name for name in ("magic", "battle") if (root/name).is_dir()]
    paths = [p for folder in archives or [root] for p in folder.rglob("*")]
    for path in sorted(paths, key=lambda p: str(p).lower()):
        if not path.is_file() or not path.name.lower().startswith(("mag", "ma8")):
            continue
        manager = LagunaManager()
        manager.load_file(str(path))
        doc = manager.document
        spans = doc.sections
        original = path.read_bytes()
        covered = (not original and not spans) or (spans and spans[0].start == 0 and spans[-1].end == len(original)
                   and all(a.end == b.start for a, b in zip(spans, spans[1:])))
        if not covered or bytes(manager.data) != original:
            failures.append(f"{path.name}: section coverage / byte preservation failed")
        counts[doc.format] += 1
        entry = dict(file=path.relative_to(root).as_posix(), size=len(original), format=doc.format,
                     sections=len(spans), sha256=hashlib.sha256(original).hexdigest())
        if doc.warnings:
            entry["warnings"] = doc.warnings
        if manager.program:
            entry["cinematic"] = dict(effect_id=manager.effect_id, root=manager.root,
                                      end=manager.script_end, instructions=len(manager.program.instructions),
                                      errors=manager.program.errors)
            if manager.program.errors:
                failures.append(f"{path.name}: cinematic decode errors")
        cameras = []
        for section in spans:
            if section.kind != "camera":
                continue
            try:
                track = CameraTrack.from_bytes(vm, original[section.start:section.end], effect_id=0,
                                               name=path.name, label="embedded", address=section.start, push_operand=0)
                if track.to_bytes() != original[section.start:section.end]:
                    raise ValueError("camera round trip changed bytes")
                cameras.append(dict(offset=section.start, size=section.size, keyframes=track.keyframe_count()))
            except (ValueError, IndexError) as error:
                failures.append(f"{path.name}: camera: {error}")
        if cameras:
            entry["cameras"] = cameras
        files.append(entry)
    return dict(scope="Extracted PC magic/ and battle/ MAG/MA8 files; content-based structural audit, not game playback.",
                total=len(files), formats=dict(sorted(counts.items())),
                cinematic_files=sum("cinematic" in f for f in files),
                camera_tracks=sum(len(f.get("cameras", [])) for f in files), failures=failures, files=files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", help="Root containing extracted magic/ and battle/ archives")
    parser.add_argument("--out")
    args = parser.parse_args()
    result = sweep(args.root)
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=1)+"\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "files"}, indent=1))
    return bool(result["failures"])


if __name__ == "__main__":
    raise SystemExit(main())
