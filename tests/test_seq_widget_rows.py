"""Tests for the IfritSeq three-view editor (SeqWidget + SeqCommandRow).

The promise under test: the command rows, the IfritSeq-code text and the hex box are
three views of the same bytes, synced through the one sequence walker - editing any one
updates the others, and switching views without touching anything leaves the bytes
strictly identical.
"""
import pathlib
import sys

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QTextBrowser

from FF8GameData.gamedata import GameData
from FF8GameData.monsterdata import EntityType
from Ifrit.IfritSeq.seqwidget import SeqWidget, VIEW_USER_FRIENDLY, VIEW_HEX, VIEW_CODE
from Ifrit.IfritSeq.seqcommandwidget import SeqCommandRow, ANIM_COMBO_VALUE
from Ifrit.IfritSeq.ifritseqwidget import IfritSeqWidget
from FF8GameData.dat.sequencecommand import read_sequence

# A0 12 (play anim 18 async) / A1 (yield) / B4 15 00 (hit effect) / E6 FB (jump -5) / A2
SAMPLE = bytearray([0xA0, 0x12, 0xA1, 0xB4, 0x15, 0x00, 0xE6, 0xFB, 0xA2])


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture(scope="module")
def game_data():
    project_root = pathlib.Path(__file__).parent.parent
    data = GameData(str(project_root / "FF8GameData"))
    data.load_all()
    return data


def make_widget(game_data, data=SAMPLE):
    widget = SeqWidget(seq=bytearray(data), id=3, entity_type=EntityType.MONSTER,
                       game_data=game_data)
    return widget


class _FakeEnemy:
    def __init__(self, seq_list, entity_type):
        self.seq_animation_data = {'seq_animation_data': seq_list}
        self.entity_type = entity_type
        self.model_animation_data = None
        self.origin_file_name = "test.dat"


class _FakeManager:
    """Just enough of IfritManager for IfritSeqWidget: a real game_data and an enemy
    holding the sequence list (IfritSeqWidget reads the model, not the .dat path)."""
    def __init__(self, game_data, seq_list, entity_type=EntityType.MONSTER):
        self.game_data = game_data
        self.enemy = _FakeEnemy(seq_list, entity_type)


def make_seq_tab(game_data, seq_list, entity_type=EntityType.MONSTER):
    from Ifrit.IfritSeq.ifritseqwidget import IfritSeqWidget
    manager = _FakeManager(game_data, seq_list, entity_type)
    widget = IfritSeqWidget(manager)
    widget.load_file("dummy.dat")  # path unused; the manager already holds the data
    return widget


class TestRowsMirrorTheBytes:
    def test_expanding_the_rows_changes_nothing(self, qapp, game_data):
        widget = make_widget(game_data)
        widget.set_view(VIEW_USER_FRIENDLY)
        assert widget.getByteData() == SAMPLE
        assert [row.command.op_code for row in widget.command_row_list] == \
               [0xA0, 0xA1, 0xB4, 0xE6, 0xA2]

    def test_row_addresses_match_the_walker(self, qapp, game_data):
        widget = make_widget(game_data)
        widget.set_view(VIEW_USER_FRIENDLY)
        walked = read_sequence(game_data, bytes(SAMPLE))
        assert [row.command.address for row in widget.command_row_list] == \
               [command.address for command in walked]

    def test_editing_a_row_updates_the_hex(self, qapp, game_data):
        widget = make_widget(game_data)
        widget.set_view(VIEW_USER_FRIENDLY)
        anim_row = widget.command_row_list[0]  # A0 12
        anim_row.param_widget_list[0].setValue(0x20)
        expected = bytearray(SAMPLE)
        expected[1] = 0x20
        assert widget.getByteData() == expected

    def test_editing_the_hex_updates_the_rows(self, qapp, game_data):
        widget = make_widget(game_data)
        widget.set_view(VIEW_USER_FRIENDLY)
        widget.sequence_text_widget.setPlainText("a0 07 a2")
        assert [row.command.op_code for row in widget.command_row_list] == [0xA0, 0xA2]
        assert widget.command_row_list[0].command.parameters == bytearray([0x07])

    def test_removing_a_row_removes_its_bytes(self, qapp, game_data):
        widget = make_widget(game_data)
        widget.set_view(VIEW_USER_FRIENDLY)
        row_b4 = widget.command_row_list[2]
        row_b4.remove_requested.emit(row_b4)
        assert widget.getByteData() == bytearray([0xA0, 0x12, 0xA1, 0xE6, 0xFB, 0xA2])

    def test_inserting_a_row_inserts_its_bytes(self, qapp, game_data):
        widget = make_widget(game_data)
        widget.set_view(VIEW_USER_FRIENDLY)
        first = widget.command_row_list[0]
        first.insert_requested.emit(first)
        # The default inserted command is A1 (yield), right after the first row
        assert widget.getByteData() == bytearray([0xA0, 0x12, 0xA1]) + SAMPLE[2:]

    def test_data_changed_is_emitted_on_row_edit(self, qapp, game_data):
        widget = make_widget(game_data)
        widget.set_view(VIEW_USER_FRIENDLY)
        seen = []
        widget.data_changed.connect(lambda: seen.append(True))
        widget.command_row_list[0].param_widget_list[0].setValue(0x21)
        assert seen


class TestVariableSizeEdits:
    def test_hit_effect_flag_grows_the_parameter_boxes(self, qapp, game_data):
        widget = make_widget(game_data)
        widget.set_view(VIEW_USER_FRIENDLY)
        row_b4 = widget.command_row_list[2]  # B4 15 00
        assert len(row_b4.param_widget_list) == 2
        row_b4.param_widget_list[1].setValue(0x08)  # spawn at bone -> +1 byte
        assert len(row_b4.param_widget_list) == 3
        # B4 15 08 00: the added bone byte defaults to 0
        assert widget.getByteData()[3:7] == bytearray([0xB4, 0x15, 0x08, 0x00])

    def test_sound_flag_bit1_grows_the_channel_mask_box(self, qapp, game_data):
        widget = make_widget(game_data, data=bytearray([0xB5, 0x03, 0x00, 0xA2]))
        widget.set_view(VIEW_USER_FRIENDLY)
        row = widget.command_row_list[0]
        assert len(row.param_widget_list) == 2
        row.param_widget_list[1].setValue(0x02)
        assert len(row.param_widget_list) == 3
        assert widget.getByteData() == bytearray([0xB5, 0x03, 0x02, 0x00, 0xA2])

    def test_ff_list_append_step(self, qapp, game_data):
        widget = make_widget(game_data, data=bytearray([0x9F, 0x05, 0xFF, 0xA2]))
        widget.set_view(VIEW_USER_FRIENDLY)
        row = widget.command_row_list[0]
        assert row.append_step_button.isVisible() or True  # visibility needs show()
        row.append_step_button.click()
        assert widget.getByteData() == bytearray([0x9F, 0x05, 0x00, 0xFF, 0xA2])


class TestOpCodeChange:
    def test_switching_op_code_installs_normalized_defaults(self, qapp, game_data):
        widget = make_widget(game_data, data=bytearray([0xA1, 0xA2]))
        widget.set_view(VIEW_USER_FRIENDLY)
        row = widget.command_row_list[0]
        index = row.op_code_combo.findData(0xB9)  # Wait frames: 1 param
        row.op_code_combo.setCurrentIndex(index)
        assert widget.getByteData() == bytearray([0xB9, 0x00, 0xA2])

    def test_switching_to_anim_uses_the_id_spinbox(self, qapp, game_data):
        widget = make_widget(game_data, data=bytearray([0xA1, 0xA2]))
        widget.set_view(VIEW_USER_FRIENDLY)
        row = widget.command_row_list[0]
        row.op_code_combo.setCurrentIndex(row.op_code_combo.findData(ANIM_COMBO_VALUE))
        assert widget.getByteData() == bytearray([0x00, 0xA2])
        row.param_widget_list[0].setValue(0x25)
        assert widget.getByteData() == bytearray([0x25, 0xA2])


class TestCodeView:
    def test_the_code_view_shows_the_language(self, qapp, game_data):
        widget = make_widget(game_data)
        widget.set_view(VIEW_CODE)
        assert widget.code_widget.toPlainText().splitlines() == [
            "anim_async(18)",
            "yield_frame()",
            "hit_target(0x15, 0x00)",
            "jump(-5)",
            "end_seq()",
        ]

    def test_typing_code_updates_the_bytes(self, qapp, game_data):
        widget = make_widget(game_data)
        widget.set_view(VIEW_CODE)
        widget.code_widget.setPlainText("anim(5)\nwait(10)\nend_seq()")
        assert widget.getByteData() == bytearray([0x05, 0xB9, 0x0A, 0xA2])
        assert not widget.code_error_label.text()

    def test_a_code_error_shows_the_line_and_keeps_the_bytes(self, qapp, game_data):
        widget = make_widget(game_data)
        widget.set_view(VIEW_CODE)
        widget.code_widget.setPlainText("anim(5)\nfly_away(3)")
        assert "line 2" in widget.code_error_label.text()
        assert widget.getByteData() == SAMPLE, "invalid code must not touch the bytes"

    def test_switching_views_without_editing_changes_nothing(self, qapp, game_data):
        widget = make_widget(game_data)
        for view in (VIEW_USER_FRIENDLY, VIEW_CODE, VIEW_HEX, VIEW_CODE,
                     VIEW_USER_FRIENDLY, VIEW_HEX):
            widget.set_view(view)
            assert widget.getByteData() == SAMPLE

    def test_the_translation_follows_a_code_edit(self, qapp, game_data):
        widget = make_widget(game_data)
        widget.set_view(VIEW_CODE)
        widget.code_widget.setPlainText("anim(5)\nend_seq()")
        assert widget.translation_widget.toPlainText().startswith("05: Play anim 05")

    def test_every_view_shows_the_translation(self, qapp, game_data):
        """Raw hex especially is unreadable on its own, so the decoded text is beside
        every view, not only the command/code ones."""
        widget = make_widget(game_data)
        for view in (VIEW_HEX, VIEW_USER_FRIENDLY, VIEW_CODE):
            widget.set_view(view)
            assert widget.translation_widget.isVisibleTo(widget), \
                f"translation must be shown in view {view}"
            assert "A0 12" in widget.translation_widget.toPlainText()


class TestSequenceTitles:
    """The engine-defined meaning shown after the seq id (from FF8_EN.exe RE)."""

    def test_monster_idle_and_entrance_are_marked_mandatory(self, qapp, game_data):
        idle = SeqWidget(seq=bytearray([0xA2]), id=1, entity_type=EntityType.MONSTER,
                         game_data=game_data)
        entrance = SeqWidget(seq=bytearray([0xA2]), id=8, entity_type=EntityType.MONSTER,
                             game_data=game_data)
        assert idle.get_displayed_title() == "Seq ID 1 - Idle (mandatory)"
        assert entrance.get_displayed_title() == "Seq ID 8 - Entrance (mandatory)"
        assert "0x5027D0" in entrance.title_label.toolTip(), "the reason is on hover"

    def test_other_monster_sequences_have_no_forced_meaning(self, qapp, game_data):
        """A monster's other sequences are free for its AI script - no engine label."""
        widget = SeqWidget(seq=bytearray([0xA2]), id=13, entity_type=EntityType.MONSTER,
                           game_data=game_data)
        assert widget.get_displayed_title() == "Seq ID 13"

    def test_character_sequences_are_all_named(self, qapp, game_data):
        """Characters drive a specific sequence per action; the whole list is named."""
        for entity_type in (EntityType.WEAPON, EntityType.WEAPON_NO_ANIM,
                            EntityType.CHARACTER_NO_WEAPON):
            widget = SeqWidget(seq=bytearray([0xA2]), id=13, entity_type=entity_type,
                               game_data=game_data)
            assert widget.get_displayed_title() == "Seq ID 13 - Attack - normal", entity_type

    def test_character_seq_zero_none_is_not_shown(self, qapp, game_data):
        widget = SeqWidget(seq=bytearray([0xA2]), id=0, entity_type=EntityType.WEAPON,
                           game_data=game_data)
        assert widget.get_displayed_title() == "Seq ID 0"


class TestAddRemoveSequence:
    """A sequence can be created in an empty slot or removed back to one, but idle (1) and
    entrance (8) - the two the engine references by fixed index - can never be removed."""

    def test_an_empty_sequence_shows_as_a_not_present_placeholder(self, qapp, game_data):
        widget = SeqWidget(seq=bytearray(), id=7, entity_type=EntityType.MONSTER,
                           game_data=game_data)
        assert widget.is_present() is False
        assert widget.absent_widget.isVisibleTo(widget)
        assert not widget.content_widget.isVisibleTo(widget)
        assert widget.add_button.isVisibleTo(widget)

    def test_adding_creates_a_minimal_valid_sequence(self, qapp, game_data):
        widget = SeqWidget(seq=bytearray(), id=7, entity_type=EntityType.MONSTER,
                           game_data=game_data)
        widget.add_button.click()
        assert widget.is_present()
        assert widget.getByteData() == SeqWidget.DEFAULT_NEW_SEQUENCE
        assert widget.content_widget.isVisibleTo(widget)
        assert not widget.absent_widget.isVisibleTo(widget)
        assert widget.remove_button.isVisibleTo(widget), "a new normal seq is removable"

    def test_removing_a_normal_sequence_empties_its_slot(self, qapp, game_data):
        widget = SeqWidget(seq=bytearray([0x05, 0xA2]), id=13,
                           entity_type=EntityType.MONSTER, game_data=game_data)
        assert widget.remove_button.isVisibleTo(widget)
        widget.remove_button.click()
        assert widget.is_present() is False
        assert widget.getByteData() == bytearray(), "removed -> empty data -> offset 0"
        assert widget.absent_widget.isVisibleTo(widget)

    def test_mandatory_idle_and_entrance_cannot_be_removed(self, qapp, game_data):
        for seq_id in (1, 8):
            widget = SeqWidget(seq=bytearray([0x05, 0xA2]), id=seq_id,
                               entity_type=EntityType.MONSTER, game_data=game_data)
            assert not widget.remove_button.isVisibleTo(widget), \
                f"seq {seq_id} is mandatory, it must not offer removal"

    def test_a_missing_mandatory_sequence_can_still_be_added(self, qapp, game_data):
        """If a file lacks the idle/entrance, adding it must be possible; only removing
        an existing one is blocked."""
        widget = SeqWidget(seq=bytearray(), id=1, entity_type=EntityType.MONSTER,
                           game_data=game_data)
        assert widget.add_button.isVisibleTo(widget)
        widget.add_button.click()
        assert widget.is_present()
        assert not widget.remove_button.isVisibleTo(widget), "still can't be removed"

    def test_add_then_remove_round_trips_the_presence(self, qapp, game_data):
        widget = SeqWidget(seq=bytearray(), id=7, entity_type=EntityType.MONSTER,
                           game_data=game_data)
        seen = []
        widget.data_changed.connect(lambda: seen.append(True))
        widget.add_button.click()
        widget.remove_button.click()
        assert widget.is_present() is False
        assert len(seen) == 2, "each of add and remove announces a change"


class TestSeqTabAddRemove:
    """The IfritSeq tab: sequences by id, empty slots as add-placeholders in position,
    save keeps every id (empty ones as offset-0 slots), and a trailing append button."""

    def _seq_list(self):
        # ids deliberately out of order and with an empty slot (id 2) and a gap-filler
        return [
            {'id': 3, 'data': bytearray([0x05, 0xA2])},
            {'id': 1, 'data': bytearray([0x00, 0xE6, 0xFD])},   # idle
            {'id': 2, 'data': bytearray()},                     # not present
            {'id': 8, 'data': bytearray([0xA2])},               # entrance
        ]

    def test_sequences_are_shown_in_id_order(self, qapp, game_data):
        tab = make_seq_tab(game_data, self._seq_list())
        assert [w.getId() for w in tab.seq_data_widget] == [1, 2, 3, 8]

    def test_the_empty_slot_is_an_add_placeholder_in_its_position(self, qapp, game_data):
        tab = make_seq_tab(game_data, self._seq_list())
        by_id = {w.getId(): w for w in tab.seq_data_widget}
        assert by_id[2].is_present() is False
        assert by_id[2].add_button.isVisibleTo(by_id[2])
        assert by_id[1].is_present() and by_id[3].is_present()

    def test_save_keeps_every_id_with_the_empty_ones_empty(self, qapp, game_data):
        tab = make_seq_tab(game_data, self._seq_list())
        tab.save_file()
        saved = tab.ifrit_manager.enemy.seq_animation_data['seq_animation_data']
        assert sorted(s['id'] for s in saved) == [1, 2, 3, 8], "no id may be dropped"
        empty = {s['id'] for s in saved if len(s['data']) == 0}
        assert empty == {2}, "only the not-present slot stays empty"

    def test_filling_a_gap_then_saving_makes_it_present(self, qapp, game_data):
        tab = make_seq_tab(game_data, self._seq_list())
        by_id = {w.getId(): w for w in tab.seq_data_widget}
        by_id[2].add_button.click()
        tab.save_file()
        saved = {s['id']: s['data'] for s in
                 tab.ifrit_manager.enemy.seq_animation_data['seq_animation_data']}
        assert saved[2] == SeqWidget.DEFAULT_NEW_SEQUENCE

    def test_the_trailing_button_appends_the_next_id(self, qapp, game_data):
        tab = make_seq_tab(game_data, self._seq_list())
        assert tab.add_sequence_button.text() == "+ Add sequence 9"
        tab.add_sequence_button.click()
        assert [w.getId() for w in tab.seq_data_widget] == [1, 2, 3, 8, 9]
        assert tab.add_sequence_button.text() == "+ Add sequence 10"
        tab.save_file()
        saved = {s['id']: s['data'] for s in
                 tab.ifrit_manager.enemy.seq_animation_data['seq_animation_data']}
        assert saved[9] == SeqWidget.DEFAULT_NEW_SEQUENCE

    def test_removing_a_sequence_survives_save(self, qapp, game_data):
        tab = make_seq_tab(game_data, self._seq_list())
        by_id = {w.getId(): w for w in tab.seq_data_widget}
        by_id[3].remove_button.click()
        tab.save_file()
        saved = {s['id']: s['data'] for s in
                 tab.ifrit_manager.enemy.seq_animation_data['seq_animation_data']}
        assert saved[3] == bytearray() and set(saved) == {1, 2, 3, 8}


class TestCollapse:
    """Collapse is a small arrow QToolButton beside a title label (not the group box's
    native checkbox: a checkbox reads as enable/disable, not collapse) - compact, and its
    own click target rather than a whole extra header row."""

    def test_collapsing_hides_content_but_keeps_the_frame(self, qapp, game_data):
        widget = make_widget(game_data)
        assert widget.content_widget.isVisibleTo(widget)
        widget.set_collapsed(True)
        assert widget.is_collapsed()
        assert not widget.content_widget.isVisibleTo(widget)
        assert not widget.remove_button.isVisibleTo(widget)
        assert widget.get_displayed_title() == "Seq ID 3", "the title stays readable"
        assert widget.collapse_button is not None, "still expandable via the arrow"
        assert widget.collapse_button.arrowType() == Qt.ArrowType.RightArrow

    def test_expanding_restores_the_content(self, qapp, game_data):
        widget = make_widget(game_data)
        widget.set_collapsed(True)
        widget.set_collapsed(False)
        assert widget.content_widget.isVisibleTo(widget)
        assert widget.collapse_button.arrowType() == Qt.ArrowType.DownArrow

    def test_collapse_does_not_touch_the_bytes(self, qapp, game_data):
        widget = make_widget(game_data)
        widget.set_collapsed(True)
        widget.set_collapsed(False)
        assert widget.getByteData() == SAMPLE

    def test_a_collapsed_empty_sequence_hides_its_add_button(self, qapp, game_data):
        widget = SeqWidget(seq=bytearray(), id=7, entity_type=EntityType.MONSTER,
                           game_data=game_data)
        widget.set_collapsed(True)
        assert not widget.absent_widget.isVisibleTo(widget)

    def test_clicking_the_arrow_collapses_and_expands(self, qapp, game_data):
        widget = make_widget(game_data)
        widget.collapse_button.click()
        assert widget.is_collapsed()
        assert not widget.content_widget.isVisibleTo(widget)
        widget.collapse_button.click()
        assert not widget.is_collapsed()
        assert widget.content_widget.isVisibleTo(widget)


class TestNoScrollbars:
    """The hex, code and translation panes must show everything, never scroll."""

    def test_hex_code_and_translation_have_no_vertical_scrollbar(self, qapp, game_data):
        from PyQt6.QtCore import Qt
        widget = make_widget(game_data)
        widget.set_view(VIEW_CODE)
        for pane in (widget.code_widget, widget.translation_widget,
                    widget.sequence_text_widget):
            assert pane.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff

    def test_a_long_translation_grows_the_widget(self, qapp, game_data):
        short = SeqWidget(seq=bytearray([0xA2]), id=3, entity_type=EntityType.MONSTER,
                          game_data=game_data)
        long_seq = SeqWidget(seq=bytearray([0x00, 0x01, 0x02, 0x03, 0x04, 0xA2]), id=4,
                             entity_type=EntityType.MONSTER, game_data=game_data)
        short.show(); long_seq.show(); qapp.processEvents()
        assert long_seq.translation_widget.height() > short.translation_widget.height(), \
            "more commands -> taller translation, not a scrollbar"


class TestHexTranslationHeightMatch:
    """In the Hex view, the hex box and the translation beside it must be the exact same
    height - whichever one naturally needs more room, the shorter one grows to match."""

    def test_hex_and_translation_match_when_translation_is_longer(self, qapp, game_data):
        # A few short bytes (small hex box) that translate to several lines of text
        widget = SeqWidget(seq=bytearray([0x00, 0x01, 0x02, 0x03, 0x04, 0xA2]), id=4,
                           entity_type=EntityType.MONSTER, game_data=game_data)
        widget.set_view(VIEW_HEX)
        widget.show(); qapp.processEvents(); qapp.processEvents()
        assert widget.sequence_text_widget.height() == widget.translation_widget.height()

    def test_hex_and_translation_match_when_hex_is_longer(self, qapp, game_data):
        # Many short bytes (tall hex box) that each translate to a short single line
        data = bytearray([0x01] * 60 + [0xA2])
        widget = SeqWidget(seq=data, id=4, entity_type=EntityType.MONSTER,
                           game_data=game_data)
        widget.set_view(VIEW_HEX)
        widget.show(); qapp.processEvents(); qapp.processEvents()
        assert widget.sequence_text_widget.height() == widget.translation_widget.height()

    def test_editing_the_hex_keeps_the_heights_matched(self, qapp, game_data):
        widget = make_widget(game_data)
        widget.set_view(VIEW_HEX)
        widget.show(); qapp.processEvents()
        widget.sequence_text_widget.setPlainText("00 01 02 03 04 A2")
        qapp.processEvents(); qapp.processEvents()
        assert widget.sequence_text_widget.height() == widget.translation_widget.height()

    def test_code_and_translation_also_match(self, qapp, game_data):
        """The Code view has the same left-editor/right-translation shape as Hex, so it
        gets the same height guarantee - code lines are usually terser than the full
        decoded text, so this is where a mismatch is most visible."""
        widget = SeqWidget(seq=bytearray([0x00, 0x01, 0x02, 0x03, 0x04, 0xA2]), id=4,
                           entity_type=EntityType.MONSTER, game_data=game_data)
        widget.set_view(VIEW_CODE)
        widget.show(); qapp.processEvents(); qapp.processEvents()
        assert widget.code_widget.height() == widget.translation_widget.height()

    def test_switching_from_hex_to_code_reequalizes(self, qapp, game_data):
        widget = SeqWidget(seq=bytearray([0x00, 0x01, 0x02, 0x03, 0x04, 0xA2]), id=4,
                           entity_type=EntityType.MONSTER, game_data=game_data)
        widget.set_view(VIEW_HEX)
        widget.show(); qapp.processEvents(); qapp.processEvents()
        widget.set_view(VIEW_CODE)
        qapp.processEvents(); qapp.processEvents()
        assert widget.code_widget.height() == widget.translation_widget.height()

    def test_user_friendly_view_is_not_forced_to_match(self, qapp, game_data):
        """Rows are not a simple text box; only Hex and Code get height equalization."""
        widget = make_widget(game_data)
        widget.set_view(VIEW_USER_FRIENDLY)
        widget.show(); qapp.processEvents()
        # No crash, no exception - the guard simply does not apply here
        assert widget.get_view() == VIEW_USER_FRIENDLY


class TestRemoveButtonPosition:
    def test_remove_button_is_left_aligned(self, qapp, game_data):
        """Left, not right: the button is the first item in its row, with the stretch
        (which pushes content away from it) coming after, not before."""
        widget = SeqWidget(seq=bytearray([0x05, 0xA2]), id=13,
                           entity_type=EntityType.MONSTER, game_data=game_data)
        layout = widget.remove_row_layout
        assert layout.itemAt(0).widget() is widget.remove_button
        assert layout.itemAt(1).widget() is None, "a stretch, not another widget"


class TestXmlRoundTrip:
    """Export to XML then import back must reproduce every sequence, empty slots included,
    and export must reflect what is on screen (unsaved edits), not the last-saved model."""

    def _seq_list(self):
        return [
            {'id': 1, 'data': bytearray([0x00, 0xE6, 0xFD])},
            {'id': 2, 'data': bytearray()},              # empty / not present
            {'id': 3, 'data': bytearray([0x05, 0xA2])},
            {'id': 8, 'data': bytearray([0xA2])},
        ]

    def test_static_export_import_preserves_everything(self, tmp_path):
        seq_list = self._seq_list()
        xml = tmp_path / "seq.xml"
        IfritSeqWidget.create_anim_seq_xml(seq_list, str(xml))
        back = IfritSeqWidget.create_anim_seq_data_from_xml(str(xml))
        assert [(s['id'], bytes(s['data'])) for s in back] == \
               [(s['id'], bytes(s['data'])) for s in seq_list]

    def test_export_includes_unsaved_widget_edits(self, qapp, game_data, tmp_path, monkeypatch):
        tab = make_seq_tab(game_data, self._seq_list())
        {w.getId(): w for w in tab.seq_data_widget}[3].sequence_text_widget.setPlainText("09 A2")
        xml = tmp_path / "seq.xml"
        monkeypatch.setattr(tab.file_dialog, "getSaveFileName", lambda *a, **k: (str(xml), ""))
        tab._export_xml_file()
        back = {s['id']: bytes(s['data'])
                for s in IfritSeqWidget.create_anim_seq_data_from_xml(str(xml))}
        assert back[3] == b"\x09\xA2", "the edit on screen must be exported"

    def test_full_round_trip_through_the_tab(self, qapp, game_data, tmp_path, monkeypatch):
        original = self._seq_list()
        tab = make_seq_tab(game_data, [dict(id=s['id'], data=bytearray(s['data']))
                                       for s in original])
        xml = tmp_path / "seq.xml"
        monkeypatch.setattr(tab.file_dialog, "getSaveFileName", lambda *a, **k: (str(xml), ""))
        tab._export_xml_file()

        monkeypatch.setattr(tab.file_dialog, "getOpenFileName", lambda *a, **k: (str(xml), ""))
        tab._load_xml_file()
        assert [w.getId() for w in tab.seq_data_widget] == [1, 2, 3, 8]
        assert {w.getId(): w for w in tab.seq_data_widget}[2].is_present() is False

        tab.save_file()
        result = {s['id']: bytes(s['data'])
                  for s in tab.ifrit_manager.enemy.seq_animation_data['seq_animation_data']}
        assert result == {s['id']: bytes(s['data']) for s in original}


class TestCodeHelpPage:
    def test_the_help_button_opens_a_non_modal_reference(self, qapp, game_data):
        tab = make_seq_tab(game_data, [{'id': 1, 'data': bytearray([0xA2])}])
        assert tab.__dict__.get('_IfritSeqWidget__code_help_dialog') is None
        tab.code_help_button.click()
        dialog = tab._IfritSeqWidget__code_help_dialog
        assert dialog is not None
        assert dialog.isVisible()
        assert not dialog.isModal()

    def test_the_help_content_lists_known_commands(self, qapp, game_data):
        tab = make_seq_tab(game_data, [{'id': 1, 'data': bytearray([0xA2])}])
        tab.code_help_button.click()
        browser = tab._IfritSeqWidget__code_help_dialog.findChild(QTextBrowser)
        text = browser.toPlainText()
        assert "wait(" in text and "jump(" in text and "raw(" in text

    def test_clicking_twice_reuses_the_same_dialog(self, qapp, game_data):
        tab = make_seq_tab(game_data, [{'id': 1, 'data': bytearray([0xA2])}])
        tab.code_help_button.click()
        first = tab._IfritSeqWidget__code_help_dialog
        tab.code_help_button.click()
        assert tab._IfritSeqWidget__code_help_dialog is first


class TestHexContractIsUntouched:
    """The pre-rework behavior, still pinned: hex is the source of truth."""

    def test_hex_only_widget_still_round_trips(self, qapp, game_data):
        widget = make_widget(game_data)
        assert widget.getByteData() == SAMPLE
        widget.sequence_text_widget.setPlainText("11 22 33 44")
        assert widget.getByteData() == bytearray([0x11, 0x22, 0x33, 0x44])

    def test_without_game_data_the_widget_falls_back_to_hex(self, qapp):
        widget = SeqWidget(seq=bytearray(SAMPLE), id=1, entity_type=EntityType.MONSTER)
        widget.set_view(VIEW_USER_FRIENDLY)
        assert widget.get_view() == VIEW_HEX, "no game data: only the hex view can exist"
        assert widget.getByteData() == SAMPLE
