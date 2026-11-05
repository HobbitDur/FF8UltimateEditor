"""The card players file (CCGroup/cardplayersfile.py): export every card player, then apply the file
onto another field folder - values, texts and the card games given to an NPC - as unsaved edits.
Plus the NPC tab's marks (bold unsaved maps, blue mod maps, the 'no card master' note) and the
field view's missing-file messages."""
import json
import pathlib
import shutil
import sys

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

from CCGroup import cardplayersfile, jsmnpc
from CCGroup.jsmcardgame import PARAM_RARE_CHANCE

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
FIELD = PROJECT_ROOT / "extracted_files" / "field" / "mapdata" / "bg"
MAPS = ("bghall_1", "bggate_2")
EXTENSIONS = ("jsm", "sym", "msd")

pytestmark = pytest.mark.ff8data(*[f"extracted_files/field/mapdata/bg/{name}/{name}.{extension}"
                                   for name in MAPS for extension in EXTENSIONS],
                                 *[f"extracted_files/field/mapdata/bg/{name}/chara.one" for name in MAPS])


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture(scope="module")
def game_data():
    from FF8GameData.gamedata import GameData
    data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    data.load_card_data()
    return data


def make_vanilla(root, with_background=False):
    vanilla = root / "field"
    for name in MAPS:
        folder = vanilla / "mapdata" / "bg" / name
        folder.mkdir(parents=True)
        extensions = EXTENSIONS + (("mim", "map", "ca") if with_background else ())
        for extension in extensions:
            shutil.copy(FIELD / name / f"{name}.{extension}", folder / f"{name}.{extension}")
        shutil.copy(FIELD / name / "chara.one", folder / "chara.one")
    return str(vanilla)


@pytest.fixture
def npc_tab(qapp, game_data, monkeypatch):
    from CCGroup.npccardgamewidget import NpcCardGameWidget
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    widget = NpcCardGameWidget(game_data=game_data)
    yield widget
    widget.deleteLater()


def file_of(widget, map_name):
    return next(f for f in widget.manager.all_files if f.map_name == map_name)


def player(widget, map_name, entity):
    return next(p for p in file_of(widget, map_name).players if p.entity_name == entity)


def npc(widget, map_name, entity):
    return next(n for n in widget.manager.npcs(file_of(widget, map_name)) if n.entity_name == entity)


def test_export_then_apply_onto_another_folder(npc_tab, game_data, qapp, tmp_path, monkeypatch):
    # A mod on top of vanilla: one value changed, one NPC given a card game
    npc_tab.set_reference_folder(make_vanilla(tmp_path / "vanilla"))
    mod = tmp_path / "mod" / "field"
    mod.mkdir(parents=True)
    npc_tab.set_working_folder(str(mod))
    player(npc_tab, "bghall_1", "seito6").params[PARAM_RARE_CHANCE].set_literal(99)
    npc_tab.add_card_game(file_of(npc_tab, "bghall_1"), npc(npc_tab, "bghall_1", "seito5"),
                          "Cards, maybe?\nYes\nNo", "Come back with 5 cards.", on_no=jsmnpc.ON_NO_ORIGINAL)
    path = tmp_path / "setup.cardplayers.json"
    content = npc_tab.export_card_players(str(path))
    records = {(r["map"].split("/")[-1], r["entity"]): r for r in json.loads(path.read_text(encoding="utf-8"))["players"]}
    assert content["format"] == cardplayersfile.FORMAT_NAME
    seito6, seito5 = records[("bghall_1", "seito6")], records[("bghall_1", "seito5")]
    assert seito6["rare_chance"] == 99 and seito6["changed"] and "added" not in seito6
    assert seito5["added"]["on_no"] == jsmnpc.ON_NO_ORIGINAL
    assert [t["text"] for t in seito5["texts"] if t["role"] == jsmnpc.ROLE_QUESTION] == ["Cards, maybe?\nYes\nNo"]
    assert seito6["game_rules"] == {"var": 292, "push": "PSHM_B"}  # a variable push stays one
    assert not any(r["changed"] for key, r in records.items() if key[1] not in ("seito5", "seito6"))

    # Applied onto a fresh vanilla copy: the same setup, as unsaved edits
    from CCGroup.npccardgamewidget import NpcCardGameWidget
    other = NpcCardGameWidget(game_data=game_data)
    other.set_reference_folder(make_vanilla(tmp_path / "other"))
    report = other.apply_card_players(str(path))
    assert report.changed == ["bghall_1 seito6"] and report.added == ["bghall_1 seito5"]
    assert not report.not_found and not report.problems
    assert player(other, "bghall_1", "seito6").params[PARAM_RARE_CHANCE].value == 99
    added = player(other, "bghall_1", "seito5")
    msd = other.manager.msd(file_of(other, "bghall_1"))
    assert [msd.text(use.message_id) for use in jsmnpc.player_messages(file_of(other, "bghall_1"), added)] == \
        ["Cards, maybe?\nYes\nNo", "Come back with 5 cards."]
    assert other.manager.has_unsaved_changes(file_of(other, "bghall_1"))
    assert not other.manager.has_unsaved_changes(file_of(other, "bggate_2"))

    # Applying it again changes nothing and adds no second card game
    again = other.apply_card_players(str(path))
    assert not again.changed and not again.added and again.unchanged == len(records)
    other.deleteLater()


def test_a_map_or_npc_missing_is_reported(npc_tab, tmp_path):
    npc_tab.set_working_folder(make_vanilla(tmp_path / "vanilla"))
    content = {"format": cardplayersfile.FORMAT_NAME, "version": 1, "players": [
        {"map": "mapdata/zz/zzzz_1", "entity": "a", "script": "talk", "index": 0},
        {"map": "mapdata/bg/bghall_1", "entity": "nobody", "script": "talk", "index": 0},
        {"map": "mapdata/bg/bghall_1", "entity": "seito6", "script": "talk", "index": 0, "variant_literals": [1, 2]}]}
    report = cardplayersfile.apply_players(npc_tab.manager, content)
    assert len(report.not_found) == 2 and "no such map" in report.not_found[0]
    assert report.problems and "variant" in report.problems[0]


def test_not_a_card_players_file_is_refused(tmp_path):
    path = tmp_path / "other.json"
    path.write_text('{"something": 1}', encoding="utf-8")
    with pytest.raises(ValueError, match="Not a CCGroup card players file"):
        cardplayersfile.read_file(str(path))


def test_tree_marks_follow_the_open_folders(npc_tab, tmp_path):
    from PyQt6.QtWidgets import QLabel, QTreeWidget
    from CCGroup.npccardgamewidget import NO_CARD_MASTER_TEXT, MODIFIED_FOLDER_COLOR
    vanilla = make_vanilla(tmp_path / "vanilla")
    mod = tmp_path / "mod" / "field" / "mapdata" / "bg" / "bggate_2"
    mod.mkdir(parents=True)
    shutil.copy(FIELD / "bggate_2" / "bggate_2.jsm", mod / "bggate_2.jsm")
    tree = npc_tab.findChild(QTreeWidget)

    def map_item(name):
        return next(tree.topLevelItem(i) for i in range(tree.topLevelItemCount()) if name in tree.topLevelItem(i).text(0))

    npc_tab.set_working_folder(str(tmp_path / "mod" / "field"))   # alone: nothing is blue
    assert map_item("bggate_2").foreground(0).color() != MODIFIED_FOLDER_COLOR
    npc_tab.set_reference_folder(vanilla)                          # both: the mod's map is blue
    gate, hall = map_item("bggate_2"), map_item("bghall_1")
    assert "[mod]" in gate.text(0) and gate.foreground(0).color() == MODIFIED_FOLDER_COLOR
    assert hall.foreground(0).color() != MODIFIED_FOLDER_COLOR and hall.text(1) != NO_CARD_MASTER_TEXT
    legend = " ".join(label.text() for label in npc_tab.findChildren(QLabel))
    assert "Blue map" in legend and "Bold map" in legend

    npc_tab.select_player(player(npc_tab, "bghall_1", "seito6"))
    player(npc_tab, "bghall_1", "seito6").params[PARAM_RARE_CHANCE].set_literal(12)
    npc_tab._NpcCardGameWidget__player_changed(player(npc_tab, "bghall_1", "seito6"))
    hall = map_item("bghall_1")
    assert hall.text(0).startswith("* ") and hall.font(0).bold()


def test_missing_map_files_say_what_to_open(npc_tab, tmp_path):
    """A mod folder holds only the files it changes: no background is a message, not an error."""
    npc_tab.set_working_folder(make_vanilla(tmp_path / "mod"))   # scripts only, no .mim/.map/.ca
    view = npc_tab.field_view
    scene = view.scene(file_of(npc_tab, "bghall_1"))
    assert scene.pixmap is None and "Errno" not in scene.error
    assert "bghall_1.mim / bghall_1.map is not in the folder you edit" in scene.error
    assert "Import complementary" in scene.error and "bghall_1.ca" in scene.camera_error
    npc_tab.set_reference_folder(make_vanilla(tmp_path / "vanilla"))  # an incomplete vanilla
    scene = view.scene(file_of(npc_tab, "bghall_1"))
    assert "not in the vanilla field folder nor in the folder you edit" in scene.error


def test_a_refused_pick_is_remembered(qapp, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QFileDialog
    from Common.fieldfolder import pick_field_folder
    picked = tmp_path / "field" / "mapdata"
    picked.mkdir(parents=True)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(picked))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    remembered = []
    assert pick_field_folder(None, "CC Group", "pick", remember=remembered.append) is None
    assert remembered == [str(picked)]   # the next dialog opens there, to pick its parent


def test_a_card_game_put_after_the_npc_talk_is_read_back_and_applied(npc_tab, game_data, qapp, tmp_path):
    npc_tab.set_reference_folder(make_vanilla(tmp_path / "vanilla"))
    mod = tmp_path / "mod" / "field"
    mod.mkdir(parents=True)
    npc_tab.set_working_folder(str(mod))
    npc_tab.add_card_game(file_of(npc_tab, "bghall_1"), npc(npc_tab, "bghall_1", "seito5"), "Cards?\nYes\nNo",
                          "Need 5.", placement=jsmnpc.PLACEMENT_AFTER_TALK)
    path = tmp_path / "after.cardplayers.json"
    npc_tab.export_card_players(str(path))
    records = {r["entity"]: r for r in json.loads(path.read_text(encoding="utf-8"))["players"]}
    assert records["seito5"]["added"]["placement"] == jsmnpc.PLACEMENT_AFTER_TALK

    from CCGroup.npccardgamewidget import NpcCardGameWidget
    other = NpcCardGameWidget(game_data=game_data)
    other.set_reference_folder(make_vanilla(tmp_path / "other"))
    report = other.apply_card_players(str(path))
    assert report.added == ["bghall_1 seito5"] and not report.problems and not report.not_found
    assert bytes(file_of(other, "bghall_1").output_data()) == bytes(file_of(npc_tab, "bghall_1").output_data())
    other.deleteLater()


@pytest.mark.parametrize("turn", [True, False])
def test_a_card_game_on_the_card_button_is_read_back_and_applied(npc_tab, game_data, qapp, tmp_path, turn):
    npc_tab.set_reference_folder(make_vanilla(tmp_path / "vanilla"))
    mod = tmp_path / "mod" / "field"
    mod.mkdir(parents=True)
    npc_tab.set_working_folder(str(mod))
    npc_tab.add_card_game(file_of(npc_tab, "bghall_1"), npc(npc_tab, "bghall_1", "seito5"), "Cards?\nYes\nNo",
                          "Need 5.", placement=jsmnpc.PLACEMENT_CARD_BUTTON, turn=turn)
    path = tmp_path / "button.cardplayers.json"
    npc_tab.export_card_players(str(path))
    records = {r["entity"]: r for r in json.loads(path.read_text(encoding="utf-8"))["players"]}
    assert records["seito5"]["added"] == {"region": 0, "on_no": jsmnpc.ON_NO_NOTHING,
                                          "placement": jsmnpc.PLACEMENT_CARD_BUTTON, "turn": turn}

    from CCGroup.npccardgamewidget import NpcCardGameWidget
    other = NpcCardGameWidget(game_data=game_data)
    other.set_reference_folder(make_vanilla(tmp_path / "other"))
    report = other.apply_card_players(str(path))
    assert report.added == ["bghall_1 seito5"] and not report.problems and not report.not_found
    assert bytes(file_of(other, "bghall_1").output_data()) == bytes(file_of(npc_tab, "bghall_1").output_data())
    other.deleteLater()


def test_card_texts_only_leave_the_npc_lines_alone(npc_tab, game_data, qapp, tmp_path):
    """A file listing only a player's card texts (no Dialogue) sets those and keeps the NPC's own lines,
    e.g. a card game put after the NPC's talk."""
    npc_tab.set_reference_folder(make_vanilla(tmp_path / "vanilla"))
    hall = file_of(npc_tab, "bghall_1")
    seito5 = npc_tab.add_card_game(hall, npc(npc_tab, "bghall_1", "seito5"), "Q\nYes\nNo", "N",
                                   placement=jsmnpc.PLACEMENT_AFTER_TALK)
    msd = npc_tab.manager.msd(hall)
    lines = {use.message_id: msd.text(use.message_id) for use in jsmnpc.player_messages(hall, seito5)
             if use.role == jsmnpc.ROLE_DIALOGUE}
    assert lines  # seito5 says something before its card question
    record = cardplayersfile.player_record(hall, seito5, msd)
    record["texts"] = [{"role": jsmnpc.ROLE_QUESTION, "text": "Cards?\nYes\nNo"},
                       {"role": jsmnpc.ROLE_NOT_ENOUGH, "text": "Need 5."}]
    report = cardplayersfile.apply_players(npc_tab.manager, {"players": [record]})
    assert not report.problems and report.changed == ["bghall_1 seito5"]
    texts = [(use.role, msd.text(use.message_id)) for use in jsmnpc.player_messages(hall, seito5)
             if use.role != jsmnpc.ROLE_DIALOGUE]
    assert texts == [(jsmnpc.ROLE_QUESTION, "Cards?\nYes\nNo"), (jsmnpc.ROLE_NOT_ENOUGH, "Need 5.")]
    assert {message_id: msd.text(message_id) for message_id in lines} == lines
