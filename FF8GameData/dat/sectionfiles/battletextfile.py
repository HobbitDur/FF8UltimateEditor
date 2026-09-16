"""Battle texts as a text file: one battle text per line, in index order (line 1 is text 0).

A line break inside a text is written as \\n, so each text stays on one line. The other FF8
text tags ({Squall}, {Var0}...) are written the way every other FF8UltimateEditor tool writes
them.
"""
import pathlib

from FF8GameData.GenericSection.ff8text import FF8Text
from .common import SectionFileError


def export_section(enemy, file_path: pathlib.Path, tools):
    lines = [text.get_str().replace("\n", "\\n") for text in enemy.battle_script_data['battle_text']]
    file_path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")


def apply_section(enemy, file_path: pathlib.Path, tools):
    battle_text_list = []
    for line_number, line in enumerate(file_path.read_text(encoding="utf-8").splitlines(), start=1):
        text = FF8Text(game_data=tools.game_data, own_offset=0, data_hex=bytearray(), id=0)
        try:
            text.set_str(line.replace("\\n", "\n"))
        except ValueError as error:
            raise SectionFileError(f"{file_path}: line {line_number} has a character FF8 cannot write: {error}")
        battle_text_list.append(text)
    enemy.battle_script_data['battle_text'] = battle_text_list
