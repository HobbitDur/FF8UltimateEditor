import json

from FF8GameData.packagepath import RESOURCES_JSON_FOLDER
from FF8GameData.sceneout import ENCOUNTER_SIZE, ENEMY_ID_BASE, NB_SLOT, EncounterRecord

FILE_NAME = "scene.out"
NAMES_FILE = RESOURCES_JSON_FOLDER / "scene_out_names.json"


def load_names(path=NAMES_FILE):
    """(battle stage names, enemy names) by id, from Jumbo Cactuar's lists."""
    with open(path, encoding="utf-8") as file:
        names = json.load(file)
    return names["battle_stage"], names["enemy"]


class JumboCactuarManager:
    """scene.out, the encounter list: every record editable, with a per-encounter revert and an
    undo history. Qt-free, shared by the JumboCactuar GUI and its CLI.

    A file of another size than 1024 x 128 bytes is read as it is: whole records are edited and
    any trailing bytes are written back unchanged."""

    def __init__(self):
        self.stage_names, self.enemy_names = load_names()
        self.file_path = ""
        self.records = []      # EncounterRecord per encounter id
        self._original = []    # bytes per encounter, as last read or saved
        self._trailing = b""
        self._undo = []        # (encounter id, record bytes before the edit, edit key)
        self._redo = []

    @property
    def loaded(self):
        return bool(self.records)

    def load_file(self, path):
        with open(path, "rb") as file:
            self.load_bytes(file.read())
        self.file_path = path

    def load_bytes(self, data):
        count = len(data) // ENCOUNTER_SIZE
        self.records = [EncounterRecord(data[index * ENCOUNTER_SIZE:(index + 1) * ENCOUNTER_SIZE])
                        for index in range(count)]
        self._trailing = bytes(data[count * ENCOUNTER_SIZE:])
        self._original = [record.to_bytes() for record in self.records]
        self._undo.clear()
        self._redo.clear()

    def to_bytes(self) -> bytes:
        return b"".join(record.to_bytes() for record in self.records) + self._trailing

    def save_file(self, path=None):
        path = path or self.file_path
        data = self.to_bytes()
        with open(path, "wb") as file:
            file.write(data)
        self.file_path = path
        self._original = [record.to_bytes() for record in self.records]

    # --- Changes ---

    def is_modified(self, index):
        return self.records[index].to_bytes() != self._original[index]

    def modified_indices(self):
        return [index for index in range(len(self.records)) if self.is_modified(index)]

    def before_edit(self, index, key=None):
        """Call before changing encounter `index`: records its state for undo. Successive edits of
        the same field (same non-None key, same encounter) make one undo step, so typing a number
        digit by digit is undone at once."""
        if self._undo and key is not None and self._undo[-1][0] == index and self._undo[-1][2] == key:
            return
        self._undo.append((index, self.records[index].to_bytes(), key))
        self._redo.clear()

    def end_edit_group(self):
        """The next edit starts a new undo step, even of the field edited last."""
        if self._undo:
            index, before, _key = self._undo[-1]
            self._undo[-1] = (index, before, None)

    def set_record(self, index, data):
        self.before_edit(index)
        self.records[index] = EncounterRecord(data)

    def revert(self, index):
        """Back to the encounter as last read or saved."""
        self.set_record(index, self._original[index])

    def can_undo(self):
        return bool(self._undo)

    def can_redo(self):
        return bool(self._redo)

    def undo(self):
        """Undo the last edit; returns the encounter id it changed (None when nothing to undo)."""
        return self._step(self._undo, self._redo)

    def redo(self):
        return self._step(self._redo, self._undo)

    def _step(self, source, target):
        if not source:
            return None
        index, data, _key = source.pop()
        target.append((index, self.records[index].to_bytes(), None))
        self.records[index] = EncounterRecord(data)
        return index

    # --- Names ---

    def stage_label(self, stage_id):
        name = self.stage_names[stage_id] if stage_id < len(self.stage_names) else "Unknown stage"
        return f"{stage_id:3d} - {name}"

    def enemy_name(self, enemy_byte):
        if enemy_byte < ENEMY_ID_BASE:
            return f"0x{enemy_byte:02X} (no c0m file)"
        com_id = enemy_byte - ENEMY_ID_BASE
        return self.enemy_names[com_id] if com_id < len(self.enemy_names) else f"c0m{com_id:03d}"

    def enemy_label(self, enemy_byte):
        if enemy_byte < ENEMY_ID_BASE:
            return self.enemy_name(enemy_byte)
        return f"{enemy_byte - ENEMY_ID_BASE:3d} - {self.enemy_name(enemy_byte)}"

    def summary(self, index):
        """One line for the encounter list: its stage and its enabled enemies."""
        record = self.records[index]
        enemies = [self.enemy_name(record.enemy_byte(slot)) for slot in range(NB_SLOT)
                   if record.slot_flag("enabled", slot)]
        stage = self.stage_names[record.stage_id] if record.stage_id < len(self.stage_names) else "?"
        return f"{index:04d} {stage}: {', '.join(enemies) if enemies else '(no enemy)'}"
