"""Text flow of a card player's script (textflow) and the Texts panel built on it, on real fields:
bcport1a (3 variants of P067 sharing their question and "not enough cards" messages), dopub_2
(the Queen's pub man: talk menus before the card question, a line per match result) and
bghall1b (a card branch that returns, the talk button's lines after it)."""
import pathlib
import shutil
import sys

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QPlainTextEdit, QToolButton

from CCGroup import jsmnpc
from CCGroup.jsmcardgame import CardGameFolderManager
from CCGroup.textflow import TextFlow, FlowBranch, FlowCardGame

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MAPDATA = PROJECT_ROOT / "extracted_files" / "field" / "mapdata"
MAPS = {"bcport1a": "bc", "dopub_2": "do", "bghall1b": "bg"}

pytestmark = pytest.mark.ff8data(*[f"extracted_files/field/mapdata/{area}/{name}/{name}.{extension}"
                                   for name, area in MAPS.items() for extension in ("jsm", "sym", "msd")])


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture(scope="module")
def manager(tmp_path_factory):
    from FF8GameData.gamedata import GameData
    field = tmp_path_factory.mktemp("vanilla") / "field"
    for name, area in MAPS.items():
        folder = field / "mapdata" / area / name
        folder.mkdir(parents=True)
        for extension in ("jsm", "sym", "msd"):
            shutil.copy(MAPDATA / area / name / f"{name}.{extension}", folder / f"{name}.{extension}")
    manager = CardGameFolderManager(GameData(str(PROJECT_ROOT / "FF8GameData")))
    manager.load_folder(str(field))
    return manager


def map_file(manager, name):
    return next(jsm_file for jsm_file in manager.jsm_files if jsm_file.map_name == name)


def roles(jsm_file, player):
    return [(use.role, use.message_id) for use in jsmnpc.player_messages(jsm_file, player)]


def test_each_variant_gets_its_own_question_and_not_enough_line(manager):
    port = map_file(manager, "bcport1a")
    variants = [player for player in port.players if player.entity_name == "P067"]
    assert len(variants) == 3
    for index, player in enumerate(variants):
        card_roles = [(position, role) for position, (role, _) in enumerate(roles(port, player))
                      if role != jsmnpc.ROLE_DIALOGUE]
        # the 3 variants show messages 81 (question) and 99 (not enough cards) each in their branch
        assert card_roles == [(2 * index, jsmnpc.ROLE_QUESTION), (2 * index + 1, jsmnpc.ROLE_NOT_ENOUGH)]


def test_other_variants_and_the_talk_button_are_off_path(manager):
    port = map_file(manager, "bcport1a")
    player = [player for player in port.players if player.entity_name == "P067"][1]
    flow = TextFlow(port, player)
    card_games = [node for node in flow.walk() if isinstance(node, FlowCardGame)]
    assert [node.on_path for node in card_games] == [False, True, False]
    top = [node for node in flow.nodes if isinstance(node, FlowBranch)][0]
    assert top.condition.kind == "button" and top.condition.equals  # I[0] == 1: the card button
    assert flow.side_on_path(top, True) and not flow.side_on_path(top, False)
    talk_lines = [message for message in flow.messages() if not message.on_path and message.message_id not in (81, 99)]
    assert talk_lines and all(message.role == jsmnpc.ROLE_DIALOGUE for message in talk_lines)


def test_card_question_is_the_last_question_before_the_match(manager):
    pub = map_file(manager, "dopub_2")
    player = pub.players[0]
    flow = TextFlow(pub, player)
    questions = [message for message in flow.messages() if message.is_question]
    assert len(questions) == 3  # two talk menus, then the card question
    assert [message.role for message in questions] == [jsmnpc.ROLE_DIALOGUE] * 2 + [jsmnpc.ROLE_QUESTION]
    conditions = [node.condition for node in flow.walk() if isinstance(node, FlowBranch)]
    answers = [condition for condition in conditions if condition.kind == "answer"]
    assert answers and all(condition.line == 1 for condition in answers)  # answer 0 = the first choice line
    texts = [condition.text for condition in conditions if condition.kind == "expression"]
    assert "the player has fewer than 5 cards (no match)" in texts
    assert {"the player won", "the player lost", "the player drew"} <= set(texts)


def test_a_returning_card_branch_puts_the_rest_in_its_else(manager):
    hall = map_file(manager, "bghall1b")
    flow = TextFlow(hall, hall.players[0])
    button = next(node for node in flow.walk() if isinstance(node, FlowBranch) and node.condition is not None
                  and node.condition.kind == "button")
    assert button.else_nodes  # the talk button's story lines, after the card branch's RET
    assert not flow.side_on_path(button, False)
    assert all(not message.on_path for message in flow.messages() if message.path[:len(button.path) + 1]
               == button.path + ((button.jpf_index, False),))


def test_texts_panel_folds_other_branches_and_syncs_shared_messages(qapp, manager):
    from CCGroup.npccardgamewidget import TextsGroup
    port = map_file(manager, "bcport1a")
    player = [player for player in port.players if player.entity_name == "P067"][1]
    selected = []
    group = TextsGroup(player, port, manager, select_player_callback=selected.append)
    # Only this variant's question and "not enough cards" are built: the other branches are folded
    assert sorted(group.editors) == [81, 99] and all(len(editors) == 1 for editors in group.editors.values())
    folded = [button for button in group.findChildren(QToolButton) if button.arrowType() == Qt.ArrowType.RightArrow]
    assert folded
    for button in folded:
        button.click()
    assert len(group.editors[81]) == 3  # every variant's question is the same message
    group.editors[81][0].setPlainText("Cards?\nYes\nNo")
    assert all(editor.toPlainText() == "Cards?\nYes\nNo" for editor in group.editors[81])
    assert manager.msd(port).text(81) == "Cards?\nYes\nNo"
    assert len(group.findChildren(QPlainTextEdit)) > 2
    group.deleteLater()
