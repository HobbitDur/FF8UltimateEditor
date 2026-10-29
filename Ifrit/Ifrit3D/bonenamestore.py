"""The one bone-name store shared by every 3D view, so a rename shows in all of them.

Built-in names come from FF8GameData/Resources/json/bone_names.json, the user's renames from
UserData/bone_names.json next to the app (created on the first rename, never part of a release, so a
self update keeps it). See FF8GameData.dat.bonenames.
"""
from Common.apppaths import app_path
from FF8GameData.dat.bonenames import BoneNames

USER_BONE_NAMES_PATH = app_path("UserData", "bone_names.json")

_store = None


def shared_bone_names() -> BoneNames:
    global _store
    if _store is None:
        _store = BoneNames(user_path=USER_BONE_NAMES_PATH)
    return _store


def set_shared_bone_names(store):
    """Swap the store (tests point it at a temporary user file); None rebuilds it on next use."""
    global _store
    _store = store
