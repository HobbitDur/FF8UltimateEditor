"""Field and world texts through deling-cli with a character table other than Latin (Japanese, Vietnamese).

deling-cli exports and imports texts with the Latin table, so a Japanese game gives unreadable CSVs
(e.g. "{x19ba}" for every kanji), and a Vietnamese one shows the letters its font replaced ("Tàn cœng"
for "Tấn công"). The bytes are not lost: GameData's Latin encoder gives them back exactly. So the CSVs
are converted here, with the character table in use (GameData.set_character_table):

- export: Deling's Latin text -> bytes (Latin table) -> text in the table in use.
- import: text -> bytes (table in use) -> Latin text in Deling's own spelling: Latin table characters,
  line breaks as "\\n", new pages as "\\n{NewPage}\\n" and every other control code as a raw {xNNNN} tag.

The CSV layout stays Deling's: a header row, then "#name","count" rows starting each file, then one
"text","comment" row per text, all fields quoted, CRLF row ends.
"""
import csv
import os

from FF8GameData.gamedata import GameData


def needs_conversion(game_data: GameData) -> bool:
    """Whether the table in use is not the Latin one Deling writes with."""
    return game_data.jp_encoding or game_data.translate_hex_to_str_table != game_data.latin_table


def _deling_breaks(text: str) -> str:
    """GameData writes 0x02 as the two characters "\\n" and 0x01 as {NewPage}; Deling uses real line breaks."""
    return text.replace('\\n', '\n').replace('{NewPage}', '\n{NewPage}\n')


def from_deling(game_data: GameData, text: str) -> str:
    """Deling's Latin text -> text in the character table in use."""
    with game_data.using_latin_table():
        data = game_data.translate_str_to_hex(text)
    return _deling_breaks(game_data.translate_hex_to_str(data))


def to_deling(game_data: GameData, text: str) -> str:
    """Text in the character table in use -> Deling's Latin text."""
    data = game_data.translate_str_to_hex(text)
    table = game_data.latin_table
    out = []
    i = 0
    while i < len(data):
        value = data[i]
        if value == 0x00:
            pass
        elif value == 0x01:
            out.append('\n{NewPage}\n')
        elif value == 0x02:
            # Deling's import reads "\n{NewPage}\n\n" as a new page alone: a line break right after a new page
            # is written as a raw tag so it is kept.
            out.append('{x02}' if i > 0 and data[i - 1] == 0x01 else '\n')
        elif value < 0x20:  # control code and its parameter byte, in Deling's raw tag form
            if i + 1 < len(data):
                out.append('{{x{:02x}{:02x}}}'.format(value, data[i + 1]))
                i += 1
            else:
                out.append('{{x{:02x}}}'.format(value))
        else:
            out.append(table[value] if value < len(table) and table[value] else '{{x{:02x}}}'.format(value))
        i += 1
    return ''.join(out)


def latin_to_japanese(game_data: GameData, text: str) -> str:
    """from_deling with the Japanese table, whatever the table in use."""
    saved = game_data.jp_encoding
    try:
        game_data.jp_encoding = True
        return from_deling(game_data, text)
    finally:
        game_data.jp_encoding = saved


def japanese_to_latin(game_data: GameData, text: str) -> str:
    """to_deling with the Japanese table, whatever the table in use."""
    saved = game_data.jp_encoding
    try:
        game_data.jp_encoding = True
        return to_deling(game_data, text)
    finally:
        game_data.jp_encoding = saved


def _is_section_row(row) -> bool:
    return bool(row) and row[0].startswith('#') and len(row) > 1 and row[1].isdigit() and '\n' not in row[0]


def convert_csv(game_data: GameData, source_path: str, dest_path: str, from_deling_csv: bool):
    """Copy a Deling text CSV, converting every text cell (not the header or the "#file" rows): from
    Deling's Latin text to the table in use (from_deling_csv) or back."""
    convert = from_deling if from_deling_csv else to_deling
    with open(source_path, encoding='utf-8', newline='') as source:
        rows = list(csv.reader(source))
    for row in rows[1:]:
        if row and not _is_section_row(row):
            row[0] = convert(game_data, row[0])
    os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
    with open(dest_path, 'w', encoding='utf-8', newline='') as dest:
        csv.writer(dest, quoting=csv.QUOTE_ALL, lineterminator='\r\n').writerows(rows)
