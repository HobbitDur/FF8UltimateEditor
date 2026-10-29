"""Build FF8GameData/Resources/json/bone_names.json: an automatic name for every bone of every
battle model (.dat) of a battle folder, guessed from its rest pose (see boneautonames).

    .venv/Scripts/python.exe Tools/generate_bone_names.py extracted_files/battle

Models already in the file keep their names (they may have been curated by hand); pass --overwrite
to rebuild them too.
"""
import argparse
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from FF8GameData.dat.boneautonames import auto_bone_names
from FF8GameData.dat.bonenames import SHIPPED_PATH, model_key, write_shipped_file
from Ifrit.ifritmanager import IfritManager


def rest_pose(manager: IfritManager):
    """(parents, joints, vertices_by_bone) of the manager's model in animation 0, frame 0."""
    enemy = manager.enemy
    bones = enemy.bone_data.bones
    manager._ensure_matrices()
    matrices = enemy.animation_data.animations[0].frames[0].bone_matrices
    joints = [(m.M41, m.M42, m.M43) for m in matrices]
    vertices_by_bone = [[] for _ in bones]
    positions = manager.get_animated_vertices(0, 0)
    bone_ids = [vertices_data.bone_id for obj in enemy.geometry_data.object_data
                for vertices_data in obj.vertices_data for _ in vertices_data.vertices]
    for position, bone_id in zip(positions, bone_ids):
        if 0 <= bone_id < len(bones):
            vertices_by_bone[bone_id].append(position)
    return [bone.parent_id for bone in bones], joints, vertices_by_bone


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("battle_folder")
    parser.add_argument("--output", default=str(SHIPPED_PATH))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    app = QApplication([])   # IfritManager builds Qt objects
    output = pathlib.Path(args.output)
    names_by_model = {}
    if output.exists():
        with open(output, encoding="utf-8") as f:
            names_by_model = json.load(f)
    manager = IfritManager()
    done = skipped = 0
    for path in sorted(pathlib.Path(args.battle_folder).glob("*.dat")):
        key = model_key(path.name)
        if not IfritManager.is_battle_model_file(str(path)) or key.startswith("mag"):
            continue
        if key in names_by_model and not args.overwrite:
            continue
        try:
            manager.enemy = manager.parse_file(str(path))
            if not (manager.enemy.bone_data and manager.enemy.bone_data.bones
                    and manager.enemy.animation_data.animations):
                skipped += 1
                continue
            names_by_model[key] = auto_bone_names(*rest_pose(manager), lengths=[
                bone.get_size() for bone in manager.enemy.bone_data.bones])
            done += 1
        except Exception as e:      # one broken file must not stop the whole build
            print(f"{key}: skipped ({e})")
            skipped += 1
    write_shipped_file(output, names_by_model)
    print(f"{done} models named, {skipped} skipped, {len(names_by_model)} in {output}")
    del app


if __name__ == "__main__":
    main()
