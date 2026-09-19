"""Section files (FF8GameData/dat/sectionfiles): one file per .dat section, one folder per .dat.

The contract pinned here is the one a mod relies on: applying a section folder onto a *fresh*
.dat rebuilds the modded one.

- Every section file is lossless: export every section of monster N, apply them onto a
  different monster's vanilla file, and every section comes out byte-for-byte equal to monster
  N's - except the AI, which goes through the AI compiler. The compiler normalises the byte code
  once (padding stop() count, unused operand bytes), so for the AI the contract is that the md is
  stable: md -> dat -> md gives the same md, and the same bytes.
- A section without a file is kept.
- The stats are a section file of their own format: info_stat.xlsx, one monster in the workbook
  format of Ifrit's Stat > Excel tab. It carries the battle texts too.
- A mistake in a file is reported against that file (SectionFileError), never silently written.

Needs the real (copyright, gitignored) monster files under extracted_files/battle/.
"""
import contextlib
import io
import pathlib
import shutil

import pytest

from FF8GameData.gamedata import GameData
from FF8GameData.dat.cameracollection import parse_camera_collection
from FF8GameData.dat.monsteranalyser import MonsterAnalyser
from FF8GameData.dat.sectionfiles import (SectionTools, SectionFileError, SECTION_FILE_NAMES,
                                          export_sections, apply_sections, folder_name_for)

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
BATTLE_DIR = PROJECT_ROOT / "extracted_files" / "battle"

# Every real monster: 127 is a 460-byte stub, 144-199 are placeholder copies. 0 is the dummy
# monster: every section but the AI round-trips (its AI uses a battle text it does not have).
MONSTER_IDS = [i for i in range(1, 144) if i != 127]


def _battle_file(monster_id: int) -> str:
    return f"extracted_files/battle/c0m{monster_id:03d}.dat"


@pytest.fixture(scope="module")
def tools():
    game_data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    game_data.load_all()
    return SectionTools(game_data)


def _load(tools, monster_id: int) -> MonsterAnalyser:
    monster = MonsterAnalyser(tools.game_data)
    with contextlib.redirect_stdout(io.StringIO()):  # The analysers print a lot
        monster.load_file_data(str(BATTLE_DIR / f"c0m{monster_id:03d}.dat"), tools.game_data)
        monster.analyse_loaded_data(tools.game_data, tools.decompiler)
    return monster


def _quiet(function, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return function(*args, **kwargs)


def _sections(monster: MonsterAnalyser, tools) -> list:
    monster.get_bytes(tools.game_data)
    return [bytes(section) for section in monster.section_raw_data]


# ---------------------------------------------------------------------------------------------
# Round trip on every vanilla monster
# ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("monster_id", [
    pytest.param(i, marks=pytest.mark.ff8data(_battle_file(i), _battle_file(MONSTER_IDS[(n + 1) % len(MONSTER_IDS)])))
    for n, i in enumerate(MONSTER_IDS)])
def test_section_folder_rebuilds_the_monster_on_another_file(tools, tmp_path, monster_id):
    other_id = MONSTER_IDS[(MONSTER_IDS.index(monster_id) + 1) % len(MONSTER_IDS)]
    source = _load(tools, monster_id)
    expected = _sections(source, tools)
    first_folder = tmp_path / "first" / f"c0m{monster_id:03d}"
    _quiet(export_sections, source, first_folder, tools)

    rebuilt = _load(tools, other_id)
    _quiet(apply_sections, rebuilt, first_folder, tools)
    rebuilt_sections = _sections(rebuilt, tools)
    layout = MonsterAnalyser.SECTION_INDEX_BY_ENTITY[source.entity_type]
    # The AI is compared through its md below (the battle texts share its section, and they are
    # compared on their own just after); every other section is byte-exact, stats included.
    not_compared = {layout['battle_script']}
    for index in range(1, len(expected)):
        if index not in not_compared:
            assert rebuilt_sections[index] == expected[index], f"section {index} differs"
    assert ([bytes(text.get_data_hex()) for text in rebuilt.battle_script_data['battle_text']] ==
            [bytes(text.get_data_hex()) for text in source.battle_script_data['battle_text']])

    # The AI: once compiled, md -> dat -> md is stable, in text and in bytes.
    second_folder = tmp_path / "second"
    _quiet(export_sections, rebuilt, second_folder, tools)
    again = _load(tools, other_id)
    _quiet(apply_sections, again, second_folder, tools)
    third_folder = tmp_path / "third"
    _quiet(export_sections, again, third_folder, tools)
    assert (third_folder / "ai.md").read_text(encoding="utf-8") == (second_folder / "ai.md").read_text(encoding="utf-8")
    def compared(sections):
        return [section for index, section in enumerate(sections) if index and index not in not_compared]
    assert compared(_sections(again, tools)) == compared(rebuilt_sections)


@pytest.mark.ff8data(_battle_file(0), _battle_file(1))
def test_dummy_monster_round_trips_every_section_but_its_ai(tools, tmp_path):
    source = _load(tools, 0)
    expected = _sections(source, tools)
    folder = tmp_path / "c0m000"
    # c0m000 is the game's "Dummy": every monster file gets a stats sheet now (a mod can put a
    # real monster in any slot), this one included
    _quiet(export_sections, source, folder, tools, ["info_stat"])
    assert any(folder.glob("*.xlsx"))
    _quiet(export_sections, source, folder, tools,
           [name for name in SECTION_FILE_NAMES if name != "info_stat"])
    rebuilt = _load(tools, 1)
    names = ["skeleton", "geometry", "animation", "dynamic_texture", "camera", "sound",
             "sound_bank", "texture", "anim_seq"]
    _quiet(apply_sections, rebuilt, folder, tools, names)
    rebuilt_sections = _sections(rebuilt, tools)
    for index in range(1, 7):   # 7, the stats, is not in `names`: the xlsx has no sheet for c0m000
        assert rebuilt_sections[index] == expected[index], f"section {index} differs"
    assert rebuilt_sections[9:] == expected[9:]
    with pytest.raises(SectionFileError, match="does not compile"):
        _quiet(apply_sections, rebuilt, folder, tools, ["ai"])


# ---------------------------------------------------------------------------------------------
# Behaviour, on one monster
# ---------------------------------------------------------------------------------------------

G_SOLDIER = 71        # Has battle texts, no dynamic texture
DYNAMIC_TEXTURE = 34  # Has a dynamic texture section


def _export(tools, tmp_path, monster_id, names=None) -> pathlib.Path:
    folder = tmp_path / f"c0m{monster_id:03d}"
    _quiet(export_sections, _load(tools, monster_id), folder, tools, names)
    return folder


@pytest.mark.ff8data(_battle_file(G_SOLDIER), _battle_file(1))
def test_a_section_without_a_file_is_kept(tools, tmp_path):
    folder = _export(tools, tmp_path, G_SOLDIER, ["camera"])
    target = _load(tools, 1)
    vanilla = _sections(target, tools)
    applied = _quiet(apply_sections, target, folder, tools)
    assert applied == ["camera"]
    result = _sections(target, tools)
    camera = MonsterAnalyser.SECTION_INDEX_BY_ENTITY[target.entity_type]['camera']
    assert result[camera] == _sections(_load(tools, G_SOLDIER), tools)[camera]
    for index in range(1, len(result)):
        if index != camera:
            assert result[index] == vanilla[index]


@pytest.mark.ff8data(_battle_file(G_SOLDIER), _battle_file(1))
def test_info_stat_xlsx_carries_the_stats_and_the_battle_texts(tools, tmp_path):
    """One monster in the workbook format of the Stat > Excel tab: the stats and the texts."""
    folder = _export(tools, tmp_path, G_SOLDIER, ["info_stat"])
    assert [path.name for path in folder.iterdir()] == ["info_stat.xlsx"]
    source = _load(tools, G_SOLDIER)
    target = _load(tools, 1)
    assert _quiet(apply_sections, target, folder, tools) == ["info_stat"]
    stats = MonsterAnalyser.SECTION_INDEX_BY_ENTITY[target.entity_type]['info_stat']
    assert _sections(target, tools)[stats] == _sections(source, tools)[stats]
    assert ([text.get_str() for text in target.battle_script_data['battle_text']] ==
            [text.get_str() for text in source.battle_script_data['battle_text']])


@pytest.mark.ff8data(_battle_file(G_SOLDIER), _battle_file(1))
def test_info_stat_xlsx_of_several_monsters_uses_the_monsters_own_sheet(tools, tmp_path):
    """A workbook covering several monsters - the mod's own xlsx - works as a section file too:
    each monster reads its own sheet, and a monster with no sheet is an error, not a guess."""
    from Ifrit.IfritXlsx.xlsxmanager import DatToXlsx

    path = tmp_path / "info_stat.xlsx"
    writer = DatToXlsx()
    writer.create_file(str(path))
    for monster_id in (1, G_SOLDIER):
        _quiet(writer.export_to_xlsx, _load(tools, monster_id), f"c0m{monster_id:03d}.dat",
               tools.game_data, analyse_ai=False)
    writer.close_file()

    target = _load(tools, G_SOLDIER)
    target.info_stat_data['hp'] = [1, 2, 3, 4]
    _quiet(apply_sections, target, tmp_path, tools, ["info_stat"])
    assert target.info_stat_data['hp'] == _load(tools, G_SOLDIER).info_stat_data['hp']

    with pytest.raises(SectionFileError, match="no sheet for monster 2"):
        _quiet(apply_sections, _load(tools, 2), tmp_path, tools, ["info_stat"])


@pytest.mark.ff8data(_battle_file(G_SOLDIER))
def test_export_only_changed_sections(tools, tmp_path):
    modded = _load(tools, G_SOLDIER)
    modded.seq_animation_data['seq_animation_data'][0]['data'] = bytearray([0xA2])
    written = _quiet(export_sections, modded, tmp_path / "c0m071", tools, None, _load(tools, G_SOLDIER))
    assert written == ["anim_seq"]
    assert [path.name for path in (tmp_path / "c0m071").iterdir()] == ["anim_seq.xml"]


@pytest.mark.ff8data(_battle_file(G_SOLDIER))
def test_replacing_section_bytes_keeps_the_edits_of_other_sections(tools):
    monster = _load(tools, G_SOLDIER)
    monster.info_stat_data['hp'] = [1, 2, 3, 4]
    camera = MonsterAnalyser.SECTION_INDEX_BY_ENTITY[monster.entity_type]['camera']
    other_camera = _sections(_load(tools, 1), tools)[camera]
    _quiet(monster.replace_sections_bytes, {camera: other_camera}, tools.game_data, tools.decompiler)
    assert monster.info_stat_data['hp'] == [1, 2, 3, 4]
    assert _sections(monster, tools)[camera] == other_camera


@pytest.mark.ff8data(_battle_file(G_SOLDIER))
def test_anim_seq_ids_must_be_complete(tools, tmp_path):
    folder = tmp_path / "c0m071"
    folder.mkdir()
    (folder / "anim_seq.xml").write_text('<sequence_animations><animation id="1"><data>A2</data></animation>'
                                         '<animation id="3"><data>A2</data></animation></sequence_animations>')
    with pytest.raises(SectionFileError, match="ids must be 1 to 2"):
        _quiet(apply_sections, _load(tools, G_SOLDIER), folder, tools)


@pytest.mark.ff8data(_battle_file(G_SOLDIER))
def test_ai_md_needs_the_five_code_blocks(tools, tmp_path):
    folder = _export(tools, tmp_path, G_SOLDIER, ["ai"])
    md_text = (folder / "ai.md").read_text(encoding="utf-8")
    (folder / "ai.md").write_text(md_text[:md_text.index("# Death")], encoding="utf-8")
    with pytest.raises(SectionFileError, match="expected 5"):
        _quiet(apply_sections, _load(tools, G_SOLDIER), folder, tools)


@pytest.mark.ff8data(_battle_file(G_SOLDIER))
@pytest.mark.parametrize("bad_code", ["stop(;", "target(NOT_A_TARGET);"])
def test_ai_md_compile_errors_are_reported(tools, tmp_path, bad_code):
    folder = _export(tools, tmp_path, G_SOLDIER, ["ai"])
    md_text = (folder / "ai.md").read_text(encoding="utf-8")
    (folder / "ai.md").write_text(md_text.replace("stop();", bad_code, 1), encoding="utf-8")
    with pytest.raises(SectionFileError, match="does not compile"):
        _quiet(apply_sections, _load(tools, G_SOLDIER), folder, tools)


@pytest.mark.ff8data(_battle_file(G_SOLDIER))
def test_textures_are_numbered_tim_files_of_the_folder(tools, tmp_path):
    """One file per texture, in the section folder itself - not in a sub-folder, so selecting every
    file of a section folder takes the textures too."""
    folder = _export(tools, tmp_path, G_SOLDIER, ["texture"])
    tim_files = sorted(path.name for path in folder.iterdir())
    assert tim_files == [f"texture_{index:02d}.tim" for index in range(len(tim_files))]
    assert all((folder / name).read_bytes()[:4] == b"\x10\x00\x00\x00" for name in tim_files)  # TIM magic
    # A gap in the numbering is refused rather than silently dropping a texture
    (folder / tim_files[0]).rename(folder / f"texture_{len(tim_files) + 1:02d}.tim")
    with pytest.raises(SectionFileError, match="texture_00.tim is missing"):
        _quiet(apply_sections, _load(tools, G_SOLDIER), folder, tools)


@pytest.mark.ff8data(_battle_file(G_SOLDIER))
def test_camera_xml_value_edit_is_applied(tools, tmp_path):
    folder = _export(tools, tmp_path, G_SOLDIER, ["camera"])
    xml_text = (folder / "camera.xml").read_text(encoding="utf-8")
    start = xml_text.index('duration="') + len('duration="')
    end = xml_text.index('"', start)
    edited = xml_text[:start] + "77" + xml_text[end:]
    (folder / "camera.xml").write_text(edited, encoding="utf-8")
    monster = _load(tools, G_SOLDIER)
    _quiet(apply_sections, monster, folder, tools)
    camera = MonsterAnalyser.SECTION_INDEX_BY_ENTITY[monster.entity_type]['camera']
    first_frame = parse_camera_collection(bytearray(_sections(monster, tools)[camera])).sets[0]
    first_block = [animation for animation in first_frame.animations if not animation.empty][0].blocks[0]
    assert first_block.frames[0].duration.get() == 77


@pytest.mark.ff8data(_battle_file(DYNAMIC_TEXTURE))
def test_dynamic_texture_xml_frame_edit_is_applied(tools, tmp_path):
    folder = _export(tools, tmp_path, DYNAMIC_TEXTURE, ["dynamic_texture"])
    xml_text = (folder / "dynamic_texture.xml").read_text(encoding="utf-8")
    frame_start = xml_text.index("<frame ")
    frame_end = xml_text.index("/>", frame_start) + 2
    (folder / "dynamic_texture.xml").write_text(
        xml_text[:frame_start] + '<frame u="123" v="45" /><frame u="1" v="2" />' + xml_text[frame_end:], encoding="utf-8")
    monster = _load(tools, DYNAMIC_TEXTURE)
    frame_count = len(monster.dynamic_texture_data.dynamic_texture_data[0].frames)
    _quiet(apply_sections, monster, folder, tools)
    entry = monster.dynamic_texture_data.dynamic_texture_data[0]
    assert (entry.frames[0].get_u_raw(), entry.frames[0].get_v_raw()) == (123, 45)
    assert len(entry.frames) == frame_count + 1


def test_folder_name_is_the_dat_name():
    assert folder_name_for("some/path/c0m071.dat") == "c0m071"
