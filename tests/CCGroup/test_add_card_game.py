"""Giving a card game to an NPC that has none (jsmnpc.add_card_game) and the .msd texts, on the
real bghall_1 (has a cardgamemaster) and bggate_2 (none) fields, copied to tmp_path."""
import pathlib
import shutil
import struct

import pytest

from CCGroup import jsmnpc
from CCGroup.jsmcardgame import (CardGameFolderManager, PARAM_GAME_RULES, PARAM_TRADE_RULES,
                                 OPCODE_PSHM_B)
from FF8GameData.field.msdfile import MsdFile

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
FIELD = PROJECT_ROOT / "extracted_files" / "field" / "mapdata" / "bg"
MAPS = ("bghall_1", "bggate_2")
EXTENSIONS = ("jsm", "sym", "msd")

pytestmark = pytest.mark.ff8data(*[f"extracted_files/field/mapdata/bg/{name}/{name}.{extension}"
                                   for name in MAPS for extension in EXTENSIONS],
                                 *[f"extracted_files/field/mapdata/bg/{name}/chara.one" for name in MAPS])


@pytest.fixture(scope="module")
def game_data():
    from FF8GameData.gamedata import GameData
    return GameData(str(PROJECT_ROOT / "FF8GameData"))


@pytest.fixture
def folders(tmp_path):
    vanilla = tmp_path / "vanilla" / "field"
    for name in MAPS:
        folder = vanilla / "mapdata" / "bg" / name
        folder.mkdir(parents=True)
        for extension in EXTENSIONS:
            shutil.copy(FIELD / name / f"{name}.{extension}", folder / f"{name}.{extension}")
        shutil.copy(FIELD / name / "chara.one", folder / "chara.one")
    modified = tmp_path / "modified" / "field"
    modified.mkdir(parents=True)
    return vanilla, modified


@pytest.fixture
def manager(folders, game_data):
    vanilla, modified = folders
    manager = CardGameFolderManager(game_data)
    manager.load_folder(str(vanilla), str(modified))
    return manager


def map_file(manager, name):
    return next(jsm_file for jsm_file in manager.all_files if jsm_file.map_name == name)


def npc(manager, map_name, entity_name):
    return next(entity for entity in manager.npcs(map_file(manager, map_name)) if entity.entity_name == entity_name)


def test_npcs_leave_main_characters_out(manager):
    names = {entity.entity_name: entity.plays_cards() for entity in manager.npcs(map_file(manager, "bghall_1"))}
    assert names["seito6"] and not names["seito5"]
    assert not {"squall", "zell", "selphie"} & set(names)


def test_msd_round_trip_and_append(game_data):
    data = (FIELD / "bghall_1" / "bghall_1.msd").read_bytes()
    msd_file = MsdFile(data, game_data)
    assert msd_file.to_bytes() == data and not msd_file.is_modified()
    assert msd_file.text(85) == "You need 5 or more\ncards to play."
    index = msd_file.add_text("Hello\nworld")
    assert index == len(msd_file) - 1 and msd_file.text(index) == "Hello\nworld"
    assert MsdFile(msd_file.to_bytes(), game_data).text(85) == msd_file.text(85)  # older indexes unchanged


def test_add_in_a_map_with_a_card_master(manager):
    jsm_file = map_file(manager, "bghall_1")
    before = bytes(jsm_file.data)
    calls = jsmnpc.card_master_calls(jsm_file)
    player = manager.add_card_game(jsm_file, npc(manager, "bghall_1", "seito5"), "Cards?\nYes\nNo", "Need 5 cards.")
    assert (player.entity_name, player.script_name) == ("seito5", "talk")
    # Rules from the card master (vars 292/293), its two calls copied from seito6's script
    assert player.params[PARAM_GAME_RULES].opcode == OPCODE_PSHM_B and player.params[PARAM_GAME_RULES].value == 292
    assert player.params[PARAM_TRADE_RULES].value == 293
    assert calls["maeshori"] in bytes(jsm_file.data)[len(before):] and calls["shori"] in bytes(jsm_file.data)[len(before):]
    # Append-only: only the talk entry and the end-of-script entry changed in the original part
    offset_section1 = struct.unpack_from("<H", before, 4)[0]
    changed = {index // 2 * 2 for index in range(len(before)) if jsm_file.data[index] != before[index]}
    talk_entry = offset_section1 + npc(manager, "bghall_1", "seito5").talk_script * 2
    assert changed == {talk_entry, offset_section1 + jsmnpc.end_entry_index(jsm_file) * 2}
    messages = jsmnpc.player_messages(jsm_file, player)
    msd_file = manager.msd(jsm_file)
    assert [(use.role, msd_file.text(use.message_id)) for use in messages] == [
        (jsmnpc.ROLE_QUESTION, "Cards?\nYes\nNo"), (jsmnpc.ROLE_NOT_ENOUGH, "Need 5 cards.")]


def test_add_in_a_map_without_card_master_uses_the_region_rules(manager):
    jsm_file = map_file(manager, "bggate_2")
    assert not jsmnpc.has_card_master(jsm_file)
    s1 = npc(manager, "bggate_2", "s1")
    original_talk_start = jsm_file.script_positions[s1.talk_script] // 4
    player = manager.add_card_game(jsm_file, s1, "Q\nYes\nNo", "N", region=4, on_no=jsmnpc.ON_NO_ORIGINAL)
    assert player.params[PARAM_GAME_RULES].value == 272 + 4  # Dollet rules
    assert player.params[PARAM_TRADE_RULES].value == 280 + 4
    # "No" goes on with the original talk script, right after its LBL
    instructions = jsm_file.instructions()
    last = len(instructions) - 1
    assert instructions[last][0] == jsmnpc.OPCODE_JMP
    assert instructions[original_talk_start][0] == jsmnpc.OPCODE_LBL
    assert last + instructions[last][1] == original_talk_start + 1
    with pytest.raises(ValueError):
        jsmnpc.add_card_game(jsm_file, npc(manager, "bggate_2", "s1"), 0, 0)  # already plays cards


def test_saved_into_the_modified_folder_and_reloaded(manager, folders, game_data):
    vanilla, modified = folders
    manager.add_card_game(map_file(manager, "bggate_2"), npc(manager, "bggate_2", "s1"), "Play?\nYes\nNo", "5 cards!")
    msd_file = manager.msd(map_file(manager, "bghall_1"))
    msd_file.set_text(59, "Cards?\nYes\nNo")  # a vanilla card player's question, edited
    report = manager.save_all_report()
    assert [jsm_file.map_name for jsm_file in report.written] == ["bggate_2"]
    assert sorted(pathlib.Path(path).name for path in report.written_texts) == ["bggate_2.msd", "bghall_1.msd"]
    assert (vanilla / "mapdata" / "bg" / "bghall_1" / "bghall_1.msd").read_bytes() == \
        (FIELD / "bghall_1" / "bghall_1.msd").read_bytes()  # vanilla untouched

    reloaded = CardGameFolderManager(game_data)
    reloaded.load_folder(str(vanilla), str(modified))
    gate = map_file(reloaded, "bggate_2")
    assert [(player.entity_name, player.script_name) for player in gate.players] == [("s1", "talk")]
    texts = [reloaded.msd(gate).text(use.message_id) for use in jsmnpc.player_messages(gate, gate.players[0])]
    assert texts == ["Play?\nYes\nNo", "5 cards!"]
    assert reloaded.msd(map_file(reloaded, "bghall_1")).text(59) == "Cards?\nYes\nNo"
    assert not reloaded.has_modifications()


def test_added_npcs_get_their_own_deck_id(manager):
    from CCGroup import cardlocation
    from CCGroup.jsmcardgame import PARAM_DECK_ID
    gate = map_file(manager, "bggate_2")
    first = manager.add_card_game(gate, npc(manager, "bggate_2", "s1"), "Q\nYes\nNo", "N")
    second = manager.add_card_game(gate, npc(manager, "bggate_2", "s2"), "Q\nYes\nNo", "N")
    deck_ids = [first.params[PARAM_DECK_ID].value, second.params[PARAM_DECK_ID].value]
    assert deck_ids[0] != deck_ids[1]
    for deck_id in deck_ids:
        assert not cardlocation.is_reserved_location(deck_id)
        assert len(manager.deck_id_users(deck_id)) == 1  # only the NPC itself
    chosen = manager.add_card_game(map_file(manager, "bghall_1"), npc(manager, "bghall_1", "seito5"), "Q", "N",
                                   deck_id=31)
    assert chosen.params[PARAM_DECK_ID].value == 31  # an explicit Deck ID is kept (shared with seito6)
