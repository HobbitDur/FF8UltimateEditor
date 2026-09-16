"""Monster AI as markdown: one title + one ``` code block per AI sub-section, in this order:

    # Init code
    # Enemy turn
    # Counter-attack
    # Death
    # Before dying or taking a hit

The code is the IfritAI language (the one the IfritAI tab edits). Only the code blocks are read
back, by position: the titles and any text outside the blocks are free.
"""
import pathlib
import re

from lark.exceptions import UnexpectedInput

from FF8GameData.dat.daterrors import AICodeError
from .common import SectionFileError

AI_SECTION_TITLES = ["# Init code", "# Enemy turn", "# Counter-attack", "# Death", "# Before dying or taking a hit"]


def ai_data_to_md(ai_data, decompiler) -> str:
    from bs4 import BeautifulSoup

    code_text = ""
    for index_section, section in enumerate(ai_data):
        if index_section == len(ai_data) - 1:  # The last section is just an empty end marker
            break
        code_text += AI_SECTION_TITLES[index_section] + "\n```\n"
        code_text += decompiler.decompile_from_command_list(section['command'])
        code_text += "```\n\n"
    # The decompiler writes html line breaks (it also feeds the rich text AI editor)
    soup = BeautifulSoup(code_text, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    return soup.get_text().replace("\xa0", " ")


def md_to_code_blocks(md_text: str) -> list:
    return re.findall(r'```.*?\n(.*?)\n```', md_text, re.DOTALL)


def compile_code(code: str, compiler, decompiler) -> dict:
    """One AI sub-section's source code -> the ai_data entry the .dat writer uses."""
    bytecode = compiler.compile(code)
    command_list = decompiler.decompile_bytecode_to_command_list(bytecode)
    return {"bytecode": bytecode, "code": code, "command": command_list}


def export_section(enemy, file_path: pathlib.Path, tools):
    tools.decompiler.set_battle_text_info_stat(enemy.battle_script_data['battle_text'], enemy.info_stat_data)
    md_text = ai_data_to_md(enemy.battle_script_data['ai_data'], tools.decompiler)
    file_path.write_text(md_text, encoding="utf-8")


def apply_section(enemy, file_path: pathlib.Path, tools):
    code_blocks = md_to_code_blocks(file_path.read_text(encoding="utf-8"))
    if len(code_blocks) != len(AI_SECTION_TITLES):
        raise SectionFileError(f"{file_path}: expected {len(AI_SECTION_TITLES)} ``` code blocks "
                               f"({', '.join(title[2:] for title in AI_SECTION_TITLES)}), found {len(code_blocks)}")
    # The AI refers to the battle texts and to the abilities by index, so compile against this
    # enemy's (possibly just applied) texts and stats.
    tools.compiler.set_battle_text_info_stat(enemy.battle_script_data['battle_text'], enemy.info_stat_data)
    tools.decompiler.set_battle_text_info_stat(enemy.battle_script_data['battle_text'], enemy.info_stat_data)
    AICodeError.clear_errors()
    new_ai_data = []
    try:
        for index, code in enumerate(code_blocks):
            new_ai_data.append(compile_code(code, tools.compiler, tools.decompiler))
    except AICodeError:
        pass  # Collected below with every other error
    except UnexpectedInput as error:  # A syntax error, reported by the parser
        raise SectionFileError(f"{file_path}: the AI code does not compile, syntax error in "
                               f"\"{AI_SECTION_TITLES[index][2:]}\":\n{error}")
    if AICodeError.has_errors():
        messages = [f"{error['title']} - {error['message']}" for error in AICodeError.get_errors()]
        AICodeError.clear_errors()
        raise SectionFileError(f"{file_path}: the AI code does not compile:\n" + "\n".join(messages))
    for index, ai_section in enumerate(new_ai_data):
        enemy.battle_script_data['ai_data'][index] = ai_section
