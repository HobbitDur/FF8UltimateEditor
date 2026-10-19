"""battle_scan_cameras.bin reader/writer: how the Scan screen frames each target.

The game keeps this table inside FF8_EN.exe (g_Scan_CameraRows), one 16-byte row per
target. FFNx dumps it to ``direct/exe/battle_scan_cameras.bin`` (``save_exe_data``) and
reads it back from there, so modders can change it. The file has no header and holds
exactly ROW_COUNT rows::

    0x0  int16  distance        camera distance, negative = in front of the target
    0x2  int16  offset_x        side offset of the camera aim
    0x4  int16  offset_y        height offset of the camera aim (negative = up)
    0x6  int16  model_offset_y  height of the point the model turns around
    0x8  int16  aim_at_model    0 = aim at the target position, otherwise at its model
    0xA  int16  view_offset_y   height offset used while the player moves a target
                                aimed at its position
    0xC  uint8  can_pitch       1 = the player can tilt the model
    0xD  uint8  can_yaw         1 = the model turns, and the player can turn it
    0xE  uint8  unknown         1 in every vanilla row
    0xF  uint8  padding

Rows 0-159 follow the com_id (characters 0-15, then a monster's row is its c0m number
plus 16). Rows 160-165 are alternate forms the game picks for a few vanilla monsters in a
given state. The monsters FFNx unlocks (c0m144 and up) come after them, at c0m + 22.
"""
import json
import struct
from dataclasses import dataclass, fields

from FF8GameData.packagepath import RESOURCES_JSON_FOLDER

FILE_NAME = "battle_scan_cameras.bin"
ROW_SIZE = 0x10
VANILLA_ROW_COUNT = 166
FIRST_NEW_COM_ID = 160
ROW_COUNT = VANILLA_ROW_COUNT + 0x100 - FIRST_NEW_COM_ID  # one row per com_id byte value: 262
FILE_SIZE = ROW_COUNT * ROW_SIZE

FIRST_MONSTER_ROW = 16          # c0m000
LAST_VANILLA_C0M = 143
FIRST_NEW_C0M = 144
LAST_C0M_FILE = 199             # FFNx loads c0m files up to c0m199
NEW_MONSTER_ROW_SHIFT = 22      # c0m144 -> row 166
DEFAULT_ROW = 87                # G-Soldier, the framing most human-sized monsters use

# Rows the game returns instead of the monster's own one when it is in a given state
# (MAG_040_SCAN_GetCameraRowIndex): row -> (c0m, state).
ALTERNATE_ROWS = {
    160: (20, "Fastitocalon / Fastitocalon-F alternate form"),
    161: (27, "Armadodo, not in its idle sequence"),
    162: (103, "Abadon, not in its idle sequence"),
    163: (43, "Bomb at 1.5x size"),
    164: (43, "Bomb at 2x size"),
    165: (59, "Imp, not in its idle sequence"),
}
CHARACTER_NAMES = ["Squall", "Zell", "Irvine", "Quistis", "Rinoa", "Selphie", "Seifer", "Edea",
                   "Laguna", "Kiros", "Ward"]

_ROW_STRUCT = struct.Struct("<hhhhhhBBBB")


@dataclass
class ScanCameraRow:
    distance: int = -0x1200
    offset_x: int = 0x200
    offset_y: int = -0x280
    model_offset_y: int = 0x280
    aim_at_model: int = 1
    view_offset_y: int = 0
    can_pitch: int = 1
    can_yaw: int = 1
    unknown: int = 1
    padding: int = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> "ScanCameraRow":
        return cls(*_ROW_STRUCT.unpack(data))

    def to_bytes(self) -> bytes:
        return _ROW_STRUCT.pack(*self.values())

    def values(self) -> tuple:
        return tuple(getattr(self, field.name) for field in fields(self))

    def copy(self) -> "ScanCameraRow":
        return ScanCameraRow(*self.values())


ROW_FIELDS = tuple(field.name for field in fields(ScanCameraRow))
SIGNED_FIELDS = ROW_FIELDS[:6]   # int16
BYTE_FIELDS = ROW_FIELDS[6:]     # uint8


def row_for_c0m(c0m: int) -> int:
    """The row the game reads for a monster in its normal state."""
    if 0 <= c0m <= LAST_VANILLA_C0M:
        return c0m + FIRST_MONSTER_ROW
    if FIRST_NEW_C0M <= c0m <= 0xFF - FIRST_MONSTER_ROW:
        return c0m + NEW_MONSTER_ROW_SHIFT
    raise ValueError(f"c0m{c0m:03d} has no scan camera row")


def c0m_for_row(row: int):
    """The monster whose model a row frames (alternate rows give their monster), or None."""
    if FIRST_MONSTER_ROW <= row < FIRST_NEW_COM_ID:
        return row - FIRST_MONSTER_ROW
    if row in ALTERNATE_ROWS:
        return ALTERNATE_ROWS[row][0]
    if VANILLA_ROW_COUNT <= row < ROW_COUNT:
        return row - NEW_MONSTER_ROW_SHIFT
    return None


def com_id_for_row(row: int):
    """The engine com_id that reads this row in its normal state (None for alternate rows)."""
    if row < FIRST_NEW_COM_ID:
        return row
    if row in ALTERNATE_ROWS:
        return None
    return row - VANILLA_ROW_COUNT + FIRST_NEW_COM_ID


def load_vanilla_rows() -> list:
    """The 166 rows of the vanilla exe, plus G-Soldier copies for every new monster."""
    with open(RESOURCES_JSON_FOLDER / "scan_camera_vanilla.json", encoding="utf-8") as file:
        hex_rows = json.load(file)["rows"]
    rows = [ScanCameraRow.from_bytes(bytes.fromhex(hex_row)) for hex_row in hex_rows]
    if len(rows) != VANILLA_ROW_COUNT:
        raise ValueError(f"scan_camera_vanilla.json must hold {VANILLA_ROW_COUNT} rows")
    rows += [rows[DEFAULT_ROW].copy() for _ in range(ROW_COUNT - VANILLA_ROW_COUNT)]
    return rows


def load_monster_names() -> dict:
    """c0m number -> monster name, from the editor's monster.json."""
    with open(RESOURCES_JSON_FOLDER / "monster.json", encoding="utf-8") as file:
        monsters = json.load(file)["monster"]
    return {monster["com_id"]: monster["name"] for monster in monsters}


class XuManager:
    """The scan camera table: ROW_COUNT ScanCameraRow, loaded from / saved to the .bin."""

    def __init__(self):
        self.rows = load_vanilla_rows()
        self._vanilla = [row.copy() for row in self.rows]
        self.monster_names = load_monster_names()
        self.file_path = ""

    # ------------------------------------------------------------------ file
    def load_file(self, path: str):
        with open(path, "rb") as file:
            self.load_bytes(file.read())
        self.file_path = path

    def load_bytes(self, data: bytes):
        if len(data) != FILE_SIZE:
            raise ValueError(f"{FILE_NAME} must contain exactly {FILE_SIZE} bytes "
                             f"({ROW_COUNT} rows of {ROW_SIZE}), got {len(data)}")
        self.rows = [ScanCameraRow.from_bytes(data[i * ROW_SIZE:(i + 1) * ROW_SIZE])
                     for i in range(ROW_COUNT)]

    def to_bytes(self) -> bytes:
        return b"".join(row.to_bytes() for row in self.rows)

    def save_file(self, path: str = ""):
        path = path or self.file_path
        if not path:
            raise ValueError("no path to save to")
        with open(path, "wb") as file:
            file.write(self.to_bytes())
        self.file_path = path

    def reset_to_vanilla(self):
        self.rows = [row.copy() for row in self._vanilla]

    # ------------------------------------------------------------------ rows
    def vanilla_row(self, row: int) -> ScanCameraRow:
        return self._vanilla[row].copy()

    def is_vanilla(self, row: int) -> bool:
        return self.rows[row] == self._vanilla[row]

    def set_field(self, row: int, field: str, value: int):
        if field not in ROW_FIELDS:
            raise ValueError(f"unknown field {field!r} (one of {', '.join(ROW_FIELDS)})")
        low, high = (-0x8000, 0x7FFF) if field in SIGNED_FIELDS else (0, 0xFF)
        if not low <= value <= high:
            raise ValueError(f"{field} must be in {low}..{high}")
        setattr(self.rows[row], field, value)

    def copy_row(self, source: int, target: int):
        self.rows[target] = self.rows[source].copy()

    def monster_name(self, c0m: int) -> str:
        return self.monster_names.get(c0m, f"c0m{c0m:03d}")

    def row_label(self, row: int) -> str:
        """Who reads the row, e.g. "087  c0m071 G-Soldier"."""
        if row in ALTERNATE_ROWS:
            c0m, state = ALTERNATE_ROWS[row]
            return f"{row:03d}  {state}"
        if row < FIRST_MONSTER_ROW:
            name = CHARACTER_NAMES[row] if row < len(CHARACTER_NAMES) else "character"
            return f"{row:03d}  {name} (not scannable)"
        c0m = c0m_for_row(row)
        if c0m > LAST_C0M_FILE:
            return f"{row:03d}  com_id {com_id_for_row(row)} (no c0m file)"
        return f"{row:03d}  c0m{c0m:03d} {self.monster_name(c0m)}"
