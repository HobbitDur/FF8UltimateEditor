"""
Shared helpers for the CLI tools.

Every tool needs the same three things: the project root (to find FF8GameData
resources when the CLI is run from anywhere), a loaded GameData instance, and
consistent CSV reading/writing ("|" delimiter on export, auto-detection on
import so files edited in Excel with ";" or "," still work).
"""

import csv
import pathlib

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_DELIMITER = "|"

_game_data = None


def load_game_data():
    """Build the GameData engine the same way the GUI widgets do (cached: every
    command needs it at most once, and the test suite runs many commands)."""
    global _game_data
    if _game_data is None:
        from FF8GameData.gamedata import GameData
        _game_data = GameData(str(PROJECT_ROOT / "FF8GameData"))
        _game_data.load_all()
    return _game_data


def write_csv(output_path: str, header: list, rows: list, delimiter: str = DEFAULT_DELIMITER):
    """Write a CSV with the shared delimiter and utf-8 encoding."""
    output = pathlib.Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=delimiter, quotechar='"', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(header)
        writer.writerows(rows)


def read_csv(csv_path: str) -> list:
    """Read a CSV (delimiter auto-detected) and return its data rows (header skipped)."""
    from FF8GameData.gamedata import GameData
    delimiter = GameData.find_delimiter_from_csv_file(csv_path)
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=delimiter, quotechar='"')
        rows = list(reader)
    return rows[1:]  # skip header


def parse_bool(value: str) -> bool:
    """Accept the usual spellings of a boolean CSV cell."""
    return str(value).strip().lower() in ("1", "true", "yes", "x", "rare", "on")
