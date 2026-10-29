"""Readable names for the bones of the battle models (.dat), with the user's own renames on top.

FF8 bones have no name, only an index. Two JSON files give them one:
- the shipped file (FF8GameData/Resources/json/bone_names.json) names every bone of every vanilla
  battle model, keyed by file name: {"c0m012.dat": ["Root", "Upper body", ...]}. It is built by
  Tools/generate_bone_names.py (automatic names, see boneautonames) and can be hand-edited.
- the user file holds ONLY the bones the user renamed: {"c0m012.dat": {"5": "Left wing"}}. It is
  created the first time a bone is renamed. It is not part of the release, so a self update (which
  only copies the new release over the old one) keeps it.

The shipped file is read first, then the user file: a user name wins. A bone named in neither
(a file that is not vanilla, a bone added in the editor) is "Bone N".
"""
import json
import os
import pathlib

from FF8GameData.packagepath import RESOURCES_JSON_FOLDER

SHIPPED_PATH = RESOURCES_JSON_FOLDER / "bone_names.json"

SOURCE_USER = "user"
SOURCE_SHIPPED = "shipped"
SOURCE_DEFAULT = "default"


def default_bone_name(bone_id: int) -> str:
    return f"Bone {bone_id}"


def model_key(file_name: str) -> str:
    """The key of a model in both files: its file name, without folder, lower case."""
    return os.path.basename(str(file_name or "")).lower()


class BoneNames:
    def __init__(self, shipped_path=SHIPPED_PATH, user_path=None):
        self.shipped_path = pathlib.Path(shipped_path)
        self.user_path = pathlib.Path(user_path) if user_path else None
        self._shipped = self._load_shipped()
        # A user file that exists but cannot be read is never overwritten (it would lose every
        # rename it holds): renaming is refused until the user fixes or removes it.
        self.user_load_error = ""
        self._user = self._load_user()

    def _load_shipped(self) -> dict:
        try:
            with open(self.shipped_path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return {}
        return {model_key(k): [str(n) for n in v] for k, v in data.items() if isinstance(v, list)}

    def _load_user(self) -> dict:
        if self.user_path is None or not self.user_path.exists():
            return {}
        try:
            with open(self.user_path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("the file is not a JSON object")
            return {model_key(k): {int(b): str(n) for b, n in v.items()} for k, v in data.items()}
        except (OSError, ValueError, AttributeError) as e:
            self.user_load_error = f"{self.user_path}: {e}"
            return {}

    def has_model(self, file_name) -> bool:
        key = model_key(file_name)
        return key in self._shipped or key in self._user

    def shipped_name(self, file_name, bone_id: int) -> str:
        names = self._shipped.get(model_key(file_name), [])
        if 0 <= bone_id < len(names) and names[bone_id]:
            return names[bone_id]
        return default_bone_name(bone_id)

    def name(self, file_name, bone_id: int) -> str:
        user_name = self._user.get(model_key(file_name), {}).get(bone_id)
        return user_name if user_name else self.shipped_name(file_name, bone_id)

    def names(self, file_name, nb_bones: int) -> list:
        return [self.name(file_name, bone_id) for bone_id in range(nb_bones)]

    def source(self, file_name, bone_id: int) -> str:
        """Where name() comes from: SOURCE_USER, SOURCE_SHIPPED or SOURCE_DEFAULT."""
        key = model_key(file_name)
        if bone_id in self._user.get(key, {}):
            return SOURCE_USER
        names = self._shipped.get(key, [])
        if 0 <= bone_id < len(names) and names[bone_id]:
            return SOURCE_SHIPPED
        return SOURCE_DEFAULT

    def rename(self, file_name, bone_id: int, new_name: str):
        """Give a bone the user's name and save the user file. An empty name, or the shipped name
        itself, removes the rename (the bone goes back to its shipped name). Raises OSError when the
        user file cannot be written, RuntimeError when it exists but could not be read."""
        if self.user_path is None:
            raise RuntimeError("No user bone-name file is set.")
        if self.user_load_error:
            raise RuntimeError(f"The user bone-name file could not be read, so it is not "
                               f"overwritten:\n{self.user_load_error}")
        key = model_key(file_name)
        new_name = (new_name or "").strip()
        renames = dict(self._user.get(key, {}))
        if not new_name or new_name == self.shipped_name(file_name, bone_id):
            renames.pop(bone_id, None)
        else:
            renames[bone_id] = new_name
        user = dict(self._user)
        if renames:
            user[key] = renames
        else:
            user.pop(key, None)
        self._write_user(user)
        self._user = user

    def _write_user(self, user: dict):
        data = {key: {str(b): user[key][b] for b in sorted(user[key])} for key in sorted(user)}
        self.user_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.user_path.with_name(self.user_path.name + ".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
            f.write("\n")
        os.replace(temp_path, self.user_path)   # never leaves a half-written user file


def write_shipped_file(path, names_by_model: dict):
    """Write the shipped file with one model per line (readable diffs when names are curated)."""
    lines = [f" {json.dumps(model_key(k))}: {json.dumps(v, ensure_ascii=False)}"
             for k, v in sorted(names_by_model.items(), key=lambda kv: model_key(kv[0]))]
    with open(path, "w", encoding="utf-8") as f:
        f.write("{\n" + ",\n".join(lines) + "\n}\n")
