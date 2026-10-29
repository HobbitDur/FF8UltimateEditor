"""Bone names: the shipped file, the user's renames on top, and the automatic names that built the
shipped file (FF8GameData.dat.bonenames / boneautonames)."""
import json

import pytest

from FF8GameData.dat.boneautonames import auto_bone_names
from FF8GameData.dat.bonenames import (BoneNames, SHIPPED_PATH, SOURCE_DEFAULT, SOURCE_SHIPPED,
                                       SOURCE_USER, write_shipped_file)


@pytest.fixture
def shipped(tmp_path):
    path = tmp_path / "bone_names.json"
    write_shipped_file(path, {"c0m012.dat": ["Root", "Body", "Head"]})
    return path


def test_shipped_names_then_default(shipped, tmp_path):
    names = BoneNames(shipped, tmp_path / "user.json")
    assert names.names("C0M012.DAT", 4) == ["Root", "Body", "Head", "Bone 3"]   # key ignores case
    assert names.source("c0m012.dat", 2) == SOURCE_SHIPPED
    assert names.source("c0m012.dat", 3) == SOURCE_DEFAULT
    assert names.name("c0m999.dat", 0) == "Bone 0"
    assert not (tmp_path / "user.json").exists()      # only created by a rename


def test_rename_saves_only_the_changes(shipped, tmp_path):
    user = tmp_path / "UserData" / "bone_names.json"
    names = BoneNames(shipped, user)
    names.rename("c0m012.dat", 2, "Lion head")
    names.rename("c0m012.dat", 5, "Tail tip")
    assert json.loads(user.read_text(encoding="utf-8")) == {
        "c0m012.dat": {"2": "Lion head", "5": "Tail tip"}}
    assert names.source("c0m012.dat", 2) == SOURCE_USER

    # Read back: shipped first, then the user's file on top
    reloaded = BoneNames(shipped, user)
    assert reloaded.names("c0m012.dat", 6) == ["Root", "Body", "Lion head", "Bone 3", "Bone 4", "Tail tip"]

    # An empty name, or the shipped name itself, drops the rename
    reloaded.rename("c0m012.dat", 2, "")
    reloaded.rename("c0m012.dat", 5, "Bone 5")
    assert json.loads(user.read_text(encoding="utf-8")) == {}
    assert reloaded.name("c0m012.dat", 2) == "Head"


def test_unreadable_user_file_is_never_overwritten(shipped, tmp_path):
    user = tmp_path / "bone_names.json"
    user.write_text("{ not json", encoding="utf-8")
    names = BoneNames(shipped, user)
    assert names.user_load_error
    with pytest.raises(RuntimeError):
        names.rename("c0m012.dat", 1, "Chest")
    assert user.read_text(encoding="utf-8") == "{ not json"


def test_shipped_file_names_the_party():
    """The shipped file covers the vanilla models; Squall is named like a humanoid."""
    with open(SHIPPED_PATH, encoding="utf-8") as f:
        shipped = json.load(f)
    assert len(shipped) > 200
    assert all(isinstance(v, list) and all(isinstance(n, str) and n for n in v) for v in shipped.values())
    squall = shipped["d0c000.dat"]
    assert len(squall) == 23
    assert squall[:3] == ["Root", "Upper body", "Lower body"]
    assert (squall[4], squall[9]) == ("Neck", "Head")
    assert (squall[3], squall[5], squall[6], squall[7]) == ("L arm 1", "R arm 1", "L leg 1", "R leg 1")


def _humanoid(left_x=-1.0, right_x=1.0, left_z=0.0, right_z=0.0):
    """A small humanoid in the viewer's space (+Y up, facing -Z, right = +X):
    0 root, 1 upper body, 2 lower body, 3 neck, 4 head, 5/6 left arm, 7/8 right arm,
    9/10 left leg, 11/12 right leg."""
    parents = [-1, 0, 0, 1, 3, 1, 5, 1, 7, 2, 9, 2, 11]
    joints = [(0, 0, 0), (0, 0, 0), (0, 0, 0), (0, 2, 0), (0, 2.5, 0),
              (left_x * 0.5, 2, left_z), (left_x, 1, left_z), (right_x * 0.5, 2, right_z), (right_x, 1, right_z),
              (left_x * 0.3, -1, left_z), (left_x * 0.3, -3, left_z),
              (right_x * 0.3, -1, right_z), (right_x * 0.3, -3, right_z)]
    vertices = [[] for _ in parents]
    vertices[1] = [(0, 1, 0)] * 4
    vertices[2] = [(0, -0.5, 0)] * 4
    vertices[4] = [(0, 3, 0)] * 20                       # the heavy head
    vertices[6] = [(left_x, 0, left_z)] * 3
    vertices[8] = [(right_x, 0, right_z)] * 3
    vertices[10] = [(left_x * 0.3, -4, left_z)] * 3      # feet on the ground
    vertices[12] = [(right_x * 0.3, -4, right_z)] * 3
    lengths = [0, 2, 1, 0.5, 0.5, 1, 1, 1, 1, 2, 2, 2, 2]
    return parents, joints, vertices, lengths


def test_auto_names_a_humanoid():
    parents, joints, vertices, lengths = _humanoid()
    assert auto_bone_names(parents, joints, vertices, lengths) == [
        "Root", "Upper body", "Lower body", "Neck", "Head",
        "L arm 1", "L arm 2", "R arm 1", "R arm 2", "L leg 1", "L leg 2", "R leg 1", "R leg 2"]


def test_auto_names_side_on_stance_uses_file_order():
    """Limbs spread front/back instead of left/right: mirrored chains take the file's order,
    left first."""
    parents, joints, vertices, lengths = _humanoid(left_x=0.0, right_x=0.0, left_z=1.0, right_z=-1.0)
    names = auto_bone_names(parents, joints, vertices, lengths)
    assert names[5:] == ["L arm 1", "L arm 2", "R arm 1", "R arm 2", "L leg 1", "L leg 2", "R leg 1", "R leg 2"]
