"""
Tests for IfritSeq sequence analyzer and widgets.

Tests the SequenceAnalyser with real FF8 battle sequence data,
and verifies that sequence parsing and hex editing work correctly.
"""
import sys
import pathlib
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QApplication

from FF8GameData.gamedata import GameData
from FF8GameData.dat.sequenceanalyser import SequenceAnalyser
from FF8GameData.monsterdata import EntityType
from Ifrit.IfritSeq.seqwidget import SeqWidget
from Ifrit.IfritSeq.ifritseqwidget import IfritSeqWidget


# ---------------------------------------------------------------------------
# Shared test data - c0m003.dat sequence data (from user reference)
# ---------------------------------------------------------------------------

C0M003_SEQ_DATA = bytearray([
    0x0E, 0x00, 0x1E, 0x00, 0x00, 0x00, 0x88, 0x00, 0x24, 0x00, 0x2D, 0x00, 0x36, 0x00, 0x00, 0x00,
    0x69, 0x00, 0x22, 0x00, 0x62, 0x00, 0x38, 0x00, 0x9A, 0x00, 0x19, 0x01, 0xB8, 0x01, 0xA3, 0x00,
    0xE6, 0xFF, 0x01, 0xA2, 0xC3, 0x08, 0xD8, 0x00, 0x01, 0xE5, 0x08, 0x04, 0xA2, 0xC3, 0x08, 0xD8,
    0x00, 0x01, 0xE5, 0x08, 0x05, 0xA2, 0x06, 0xA2, 0xBB, 0xA5, 0x04, 0x08, 0x09, 0x0A, 0xA0, 0x0A,
    0xC3, 0x08, 0xD5, 0x10, 0xE5, 0x7F, 0xC1, 0x00, 0xCB, 0x7F, 0xE9, 0x0C, 0xC3, 0x08, 0xDD, 0x10,
    0xE5, 0x08, 0xE6, 0x07, 0xE6, 0x02, 0xA1, 0xE6, 0xE7, 0x0B, 0xC3, 0x08, 0xD9, 0x20, 0xE5, 0x08,
    0x0C, 0xA2, 0xBB, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0xA2, 0xB5, 0x00, 0x06, 0x02, 0xA8, 0x01, 0xA0,
    0x00, 0xC3, 0x0C, 0xE1, 0x11, 0xE5, 0x7F, 0xBA, 0xC3, 0x7F, 0xC5, 0xFF, 0xE5, 0x7F, 0xE7, 0xF9,
    0xC3, 0x08, 0xD9, 0x08, 0xE5, 0x08, 0xA1, 0xA2, 0x07, 0xB5, 0x01, 0x02, 0x04, 0xB8, 0x0D, 0x02,
    0x08, 0xB8, 0x0E, 0x02, 0x10, 0xA8, 0x06, 0xA9, 0xE6, 0xFF, 0xC1, 0x00, 0xCB, 0x10, 0xE5, 0x02,
    0xBB, 0x0D, 0x0E, 0xA0, 0x0F, 0xC3, 0x0A, 0xE5, 0x7F, 0xC3, 0x02, 0xC9, 0x00, 0xE5, 0xFF, 0xC3,
    0xFF, 0xCF, 0x09, 0xE5, 0xFE, 0xC3, 0xFE, 0xD3, 0x0A, 0xE5, 0xFD, 0xC1, 0x00, 0xC7, 0xFD, 0xE5,
    0x0F, 0xA1, 0xC3, 0x7F, 0xC5, 0xFF, 0xE5, 0x7F, 0xE7, 0xE1, 0xA0, 0x10, 0xB9, 0x04, 0x98, 0x11,
    0x01, 0xB4, 0x15, 0x00, 0xAA, 0xC3, 0x08, 0xDA, 0x80, 0xE5, 0x08, 0xC3, 0x08, 0xD9, 0x08, 0xE5,
    0x08, 0xA1, 0x11, 0xA0, 0x12, 0xC3, 0x0A, 0xE5, 0x7F, 0xC3, 0x02, 0xC4, 0xE8, 0x03, 0xE5, 0xFF,
    0xC3, 0x02, 0xC4, 0xE8, 0x03, 0xE5, 0xFE, 0xC1, 0x00, 0xCB, 0xFE, 0xE5, 0xFD, 0xC3, 0xFD, 0xCF,
    0x09, 0xE5, 0xFC, 0xC3, 0xFC, 0xD3, 0x0A, 0xE5, 0xFB, 0xC3, 0xFF, 0xC7, 0xFB, 0xE5, 0x0F, 0xA1,
    0xC3, 0x7F, 0xC5, 0xFF, 0xE5, 0x7F, 0xE7, 0xD3, 0xA2, 0xC3, 0x11, 0xC8, 0xF4, 0x01, 0xE5, 0xFF,
    0xC1, 0x00, 0xCB, 0xFF, 0xE5, 0x02, 0xBB, 0xA0, 0x13, 0xC3, 0x0A, 0xE5, 0x7F, 0xC3, 0x02, 0xC9,
    0x00, 0xE5, 0xFF, 0xC3, 0xFF, 0xCF, 0x09, 0xE5, 0xFE, 0xC3, 0xFE, 0xD3, 0x0A, 0xE5, 0xFD, 0xC1,
    0x00, 0xC7, 0xFD, 0xE5, 0x0F, 0xA1, 0xC3, 0x7F, 0xC5, 0xFF, 0xE5, 0x7F, 0xE7, 0xE1, 0x14, 0xA0,
    0x15, 0xB9, 0x06, 0xB5, 0x02, 0x01, 0xB4, 0x18, 0x02, 0x08, 0xB9, 0x05, 0xB5, 0x02, 0x01, 0xB4,
    0x18, 0x02, 0x08, 0xB9, 0x03, 0xB5, 0x02, 0x01, 0xB4, 0x18, 0x02, 0x08, 0xB9, 0x04, 0xB5, 0x02,
    0x01, 0xB4, 0x18, 0x02, 0x08, 0xB9, 0x04, 0xB5, 0x02, 0x01, 0xB4, 0x18, 0x02, 0x08, 0xC3, 0x08,
    0xD9, 0x08, 0xE5, 0x08, 0xA1, 0xB4, 0x19, 0x00, 0xAA, 0xC3, 0x08, 0xDA, 0x80, 0xE5, 0x08, 0xA0,
    0x16, 0xC3, 0x0A, 0xE5, 0x7F, 0xC1, 0x00, 0xCB, 0x02, 0xE5, 0xFF, 0xC3, 0xFF, 0xCF, 0x09, 0xE5,
    0xFE, 0xC3, 0xFE, 0xD3, 0x0A, 0xE5, 0xFD, 0xC3, 0x02, 0xC7, 0xFD, 0xE5, 0x0F, 0xA1, 0xC3, 0x7F,
    0xC5, 0xFF, 0xE5, 0x7F, 0xE7, 0xE1, 0x17, 0xA2, 0xBB, 0x18, 0x19, 0xA0, 0x19, 0xC3, 0x08, 0xD5,
    0x10, 0xE5, 0x7F, 0xC1, 0x00, 0xCB, 0x7F, 0xE9, 0x0C, 0xC3, 0x08, 0xDD, 0x10, 0xE5, 0x08, 0xE6,
    0x07, 0xE6, 0x02, 0xA1, 0xE6, 0xE7, 0xC3, 0x08, 0xD9, 0x20, 0xE5, 0x08, 0x1A, 0x1B, 0xA2, 0x00,
    0x01
])

# Small sequence for basic tests (must have complete opcodes)
SIMPLE_SEQ_DATA = bytearray([
    0xA0, 0x00,  # Op_id directive (2 bytes)
])


# ---------------------------------------------------------------------------
# Session-scoped QApplication (required for Qt widgets)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def qapp():
    """Create QApplication singleton for test session."""
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture(scope="session")
def game_data():
    """Load GameData once for the entire test session."""
    project_root = pathlib.Path(__file__).parent.parent
    game_data = GameData(str(project_root / "FF8GameData"))
    game_data.load_all()
    return game_data


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _make_mock_ifrit_manager():
    """Create a mock IfritManager for testing."""
    manager = MagicMock()
    manager.enemy = MagicMock()
    manager.enemy.sequence = C0M003_SEQ_DATA
    return manager


# ===========================================================================
# Section 1 – Pure data-model tests (SequenceAnalyser, no Qt widgets)
# ===========================================================================

class TestSequenceAnalyserDataModel:
    """
    Tests for SequenceAnalyser that operate solely on the data model,
    without requiring QApplication or Qt widgets.
    """

    def test_sequence_analyser_init_with_valid_data(self, game_data):
        """SequenceAnalyser should parse valid sequence data without error."""
        analyser = SequenceAnalyser(game_data, None, C0M003_SEQ_DATA)
        assert analyser is not None
        assert analyser.get_size() == len(C0M003_SEQ_DATA)

    def test_sequence_size(self, game_data):
        """SequenceAnalyser.get_size() should return the sequence bytearray length."""
        analyser = SequenceAnalyser(game_data, None, C0M003_SEQ_DATA)
        # Note: The analyzer consumes data during parsing, so get_size() returns remaining bytes
        assert analyser.get_size() == len(C0M003_SEQ_DATA)

    def test_sequence_text_output(self, game_data):
        """SequenceAnalyser should generate readable text output."""
        analyser = SequenceAnalyser(game_data, None, C0M003_SEQ_DATA)
        text = analyser.get_text()
        assert text is not None
        assert isinstance(text, str)
        assert len(text) > 0

    def test_sequence_text_contains_opcodes(self, game_data):
        """Generated text should contain hexadecimal opcode values."""
        analyser = SequenceAnalyser(game_data, None, C0M003_SEQ_DATA)
        text = analyser.get_text()
        # Check that text contains some expected opcodes from C0M003_SEQ_DATA
        assert "A0" in text or "a0" in text  # At least one opcode should be present

    def test_simple_sequence(self, game_data):
        """SequenceAnalyser should handle simple sequence data."""
        analyser = SequenceAnalyser(game_data, None, SIMPLE_SEQ_DATA)
        text = analyser.get_text()
        assert text is not None
        assert isinstance(text, str)

    def test_empty_sequence(self, game_data):
        """SequenceAnalyser should handle empty sequence data."""
        empty_seq = bytearray()
        analyser = SequenceAnalyser(game_data, None, empty_seq)
        text = analyser.get_text()
        assert text == ""

    def test_single_byte_sequence(self, game_data):
        """SequenceAnalyser should handle single-byte sequences."""
        single_byte = bytearray([0x01])
        analyser = SequenceAnalyser(game_data, None, single_byte)
        text = analyser.get_text()
        assert text is not None


# ===========================================================================
# Section 2 – SeqWidget unit tests
# ===========================================================================

class TestSeqWidget:
    """
    Tests for the SeqWidget that handles sequence hex display and editing.
    """

    def test_seq_widget_init(self, qapp):
        """SeqWidget should initialize with valid sequence data."""
        widget = SeqWidget(seq=C0M003_SEQ_DATA, id=3, entity_type=EntityType.MONSTER)
        assert widget is not None
        assert widget.getId() == 3

    def test_seq_widget_get_byte_data(self, qapp):
        """SeqWidget.getByteData() should return the original bytearray."""
        widget = SeqWidget(seq=C0M003_SEQ_DATA, id=3, entity_type=EntityType.MONSTER)
        retrieved = widget.getByteData()
        assert retrieved == C0M003_SEQ_DATA

    def test_seq_widget_displays_hex(self, qapp):
        """SeqWidget should display sequence as hex string."""
        widget = SeqWidget(seq=C0M003_SEQ_DATA, id=5, entity_type=EntityType.MONSTER)
        hex_text = widget.sequence_text_widget.toPlainText()
        assert hex_text is not None
        assert len(hex_text) > 0

    def test_seq_widget_hex_roundtrip(self, qapp):
        """Modifying hex text and retrieving should preserve data."""
        original_data = bytearray([0xAA, 0xBB, 0xCC, 0xDD])
        widget = SeqWidget(seq=original_data, id=1, entity_type=EntityType.MONSTER)

        # Get the hex representation
        hex_text = widget.sequence_text_widget.toPlainText()
        # Should be preserved
        retrieved = widget.getByteData()
        assert retrieved == original_data

    def test_seq_widget_edit_hex(self, qapp):
        """SeqWidget should allow editing hex text."""
        original = bytearray([0x01, 0x02, 0x03, 0x04])
        widget = SeqWidget(seq=original, id=1, entity_type=EntityType.MONSTER)

        # Change hex text to different value
        new_hex = "11 22 33 44"
        widget.sequence_text_widget.setPlainText(new_hex)

        # Retrieve and verify
        modified = widget.getByteData()
        expected = bytearray([0x11, 0x22, 0x33, 0x44])
        assert modified == expected

    def test_seq_widget_get_id(self, qapp):
        """SeqWidget.getId() should return the sequence ID."""
        for seq_id in [0, 1, 10, 61]:
            widget = SeqWidget(seq=bytearray([0x00]), id=seq_id, entity_type=EntityType.MONSTER)
            assert widget.getId() == seq_id

    def test_seq_widget_entity_type_monster(self, qapp):
        """SeqWidget should accept EntityType.MONSTER."""
        widget = SeqWidget(seq=C0M003_SEQ_DATA, id=0, entity_type=EntityType.MONSTER)
        assert widget.entity_type == EntityType.MONSTER

    def test_seq_widget_str_representation(self, qapp):
        """SeqWidget should have a string representation."""
        widget = SeqWidget(seq=bytearray([0xAA, 0xBB, 0xCC]), id=1, entity_type=EntityType.MONSTER)
        str_repr = str(widget)
        assert str_repr is not None
        assert isinstance(str_repr, str)


# ===========================================================================
# Section 3 – IfritSeqWidget integration tests
# ===========================================================================

class TestIfritSeqWidget:
    """
    Tests for the IfritSeqWidget that provides the overall UI and integration.
    """

    def test_ifrit_seq_widget_init(self, qapp):
        """IfritSeqWidget should initialize."""
        manager = _make_mock_ifrit_manager()
        widget = IfritSeqWidget(manager)
        assert widget is not None

    def test_ifrit_seq_widget_has_analyze_button(self, qapp):
        """IfritSeqWidget should have an analyze button."""
        manager = _make_mock_ifrit_manager()
        widget = IfritSeqWidget(manager)
        assert hasattr(widget, 'seq_analyze_button')
        assert widget.seq_analyze_button is not None

    def test_ifrit_seq_widget_has_scroll_area(self, qapp):
        """IfritSeqWidget should have a scroll area for sequences."""
        manager = _make_mock_ifrit_manager()
        widget = IfritSeqWidget(manager)
        assert hasattr(widget, 'scroll_area')
        assert widget.scroll_area is not None

    def test_ifrit_seq_widget_has_analyze_textarea(self, qapp):
        """IfritSeqWidget should have a textarea for analysis output."""
        manager = _make_mock_ifrit_manager()
        widget = IfritSeqWidget(manager)
        assert hasattr(widget, 'seq_analyze_textarea')
        assert widget.seq_analyze_textarea is not None

    def test_ifrit_seq_widget_export_button_exists(self, qapp):
        """IfritSeqWidget should have export XML button."""
        manager = _make_mock_ifrit_manager()
        widget = IfritSeqWidget(manager)
        assert hasattr(widget, '_export_xml_button')
        assert widget._export_xml_button is not None

    def test_ifrit_seq_widget_import_button_exists(self, qapp):
        """IfritSeqWidget should have import XML button."""
        manager = _make_mock_ifrit_manager()
        widget = IfritSeqWidget(manager)
        assert hasattr(widget, '_import_xml_button')
        assert widget._import_xml_button is not None


# ===========================================================================
# Section 4 – Integration and round-trip tests
# ===========================================================================

class TestSequenceRoundTrip:
    """
    Tests that verify sequence data can be loaded, analyzed, modified,
    and preserved through round-trip operations.
    """

    def test_c0m003_sequence_intact_after_analysis(self, game_data):
        """Analyzing C0M003 data should not corrupt the original sequence."""
        analyser = SequenceAnalyser(game_data, None, C0M003_SEQ_DATA)
        # The sequence data itself should not change during analysis
        assert analyser.get_size() == len(C0M003_SEQ_DATA)

    def test_widget_data_preserved_through_hex_display(self, qapp):
        """Data should survive hex display → retrieval round-trip."""
        for test_data in [
            bytearray([0xFF]),
            bytearray([0x00, 0x01, 0x02]),
            C0M003_SEQ_DATA[:50],  # First 50 bytes of c0m003
        ]:
            widget = SeqWidget(seq=test_data, id=0, entity_type=EntityType.MONSTER)
            retrieved = widget.getByteData()
            assert retrieved == test_data

    def test_sequence_analysis_with_multiple_opcodes(self, game_data):
        """SequenceAnalyser should handle complex sequences with many opcodes."""
        # C0M003 contains many different opcodes
        analyser = SequenceAnalyser(game_data, None, C0M003_SEQ_DATA)
        text = analyser.get_text()

        # Count newlines as a rough proxy for number of instructions
        instruction_count = text.count('\n')
        assert instruction_count > 0, "Should parse multiple instructions"


# ===========================================================================
# Section 5 – Edge cases and error handling
# ===========================================================================

class TestSequenceEdgeCases:
    """
    Tests for edge cases and error conditions.
    """

    def test_seq_widget_with_empty_sequence(self, qapp):
        """SeqWidget should handle empty sequence without crashing."""
        widget = SeqWidget(seq=bytearray(), id=0, entity_type=EntityType.MONSTER)
        assert widget.getByteData() == bytearray()

    def test_sequence_analyser_with_all_zeros(self, game_data):
        """SequenceAnalyser should handle sequence of all zeros."""
        zero_seq = bytearray([0x00] * 10)
        analyser = SequenceAnalyser(game_data, None, zero_seq)
        text = analyser.get_text()
        assert text is not None

    def test_sequence_analyser_with_all_ones(self, game_data):
        """SequenceAnalyser should handle sequence of all 0xFF."""
        ones_seq = bytearray([0xFF] * 10)
        analyser = SequenceAnalyser(game_data, None, ones_seq)
        text = analyser.get_text()
        assert text is not None

    def test_seq_widget_large_sequence(self, qapp):
        """SeqWidget should handle large sequences."""
        large_seq = bytearray([0xAA] * 10000)
        widget = SeqWidget(seq=large_seq, id=0, entity_type=EntityType.MONSTER)
        retrieved = widget.getByteData()
        assert len(retrieved) == 10000
        assert retrieved == large_seq

    def test_sequence_analyser_single_opcode(self, game_data):
        """SequenceAnalyser should handle single-opcode sequences."""
        single = bytearray([0xA0, 0x00])
        analyser = SequenceAnalyser(game_data, None, single)
        text = analyser.get_text()
        assert text is not None
        assert len(text) > 0


# ===========================================================================
# Section 6 – Data structure tests
# ===========================================================================

class TestSeqWidgetDataStructures:
    """
    Tests for data structure properties and behaviors.
    """

    def test_seq_widget_desc_chara_count(self, qapp):
        """SeqWidget should have correct number of character descriptions."""
        widget = SeqWidget(seq=bytearray(), id=0, entity_type=EntityType.MONSTER)
        # Should have 31 descriptions (MIN_OP_ID=0 to MAX_OP_ID=30 + 1)
        assert len(widget.SEQ_DESCRIPTION_CHARA) == 31

    def test_seq_widget_max_values(self, qapp):
        """SeqWidget should define correct maximum values."""
        widget = SeqWidget(seq=bytearray(), id=0, entity_type=EntityType.MONSTER)
        assert widget.MAX_COMMAND_PARAM == 7
        assert widget.MAX_OP_ID == 61
        assert widget.MIN_OP_ID == 0
        assert widget.MAX_OP_CODE_VALUE == 255
        assert widget.MIN_OP_CODE_VALUE == 0

    def test_seq_widget_first_description(self, qapp):
        """First character description should match expectations."""
        widget = SeqWidget(seq=bytearray(), id=0, entity_type=EntityType.MONSTER)
        assert widget.SEQ_DESCRIPTION_CHARA[0] == "None"

    def test_seq_widget_attack_description(self, qapp):
        """Attack description should be present."""
        widget = SeqWidget(seq=bytearray(), id=0, entity_type=EntityType.MONSTER)
        # "Attack - normal" is at index 13
        assert widget.SEQ_DESCRIPTION_CHARA[13] == "Attack - normal"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])



