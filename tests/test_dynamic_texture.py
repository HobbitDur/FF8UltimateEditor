import sys
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QApplication

from FF8GameData.monsterdata import DynamicTextureSection, DynamicTextureData, UV
from Ifrit.IfritDynamicTexture.destinationwidget import DestinationWidget
from Ifrit.IfritDynamicTexture.dynamictextureentrywidget import DynamicTextureEntryWidget
from Ifrit.IfritDynamicTexture.dynamictexturesectionwidget import DynamicTextureSectionWidget
from Ifrit.IfritDynamicTexture.ifritdynamictexturewidget import IfritDynamicTextureWidget

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

PUPU_DATA = bytearray([
    0x08, 0x00, 0x1C, 0x00, 0x28, 0x00, 0x38, 0x00,
    0x01, 0x08, 0x34, 0x15, 0x0D, 0x05, 0x08, 0x00,
    0x25, 0x1E, 0x25, 0x1E, 0x15, 0x59, 0x15, 0x59,
    0x00, 0x59, 0x00, 0x59, 0x01, 0x08, 0x34, 0x15,
    0x0D, 0x01, 0x00, 0x00, 0x25, 0x1E, 0x00, 0x73,
    0x01, 0x08, 0x34, 0x15, 0x0D, 0x03, 0x08, 0x00,
    0x15, 0x66, 0x15, 0x66, 0x15, 0x73, 0x15, 0x73,
    0x01, 0x33, 0x2C, 0x09, 0x1E, 0x0B, 0x08, 0x00,
    0x37, 0x00, 0x2E, 0x00, 0x25, 0x00, 0x2A, 0x2C,
    0x2A, 0x2C, 0x2A, 0x4A, 0x2A, 0x4A, 0x2A, 0x2C,
    0x2A, 0x2C, 0x25, 0x00, 0x2E, 0x00, 0x37, 0x00,
])


# ---------------------------------------------------------------------------
# Session-scoped QApplication (required for any Qt widget)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


# ---------------------------------------------------------------------------
# Helper: build a minimal IfritManager mock that the widgets can drive
# ---------------------------------------------------------------------------

def _make_mock_manager(data: bytearray | None = None) -> MagicMock:
    """
    Return a MagicMock shaped like IfritManager.
    - enemy.dynamic_texture_data  → real DynamicTextureSection (analyzed if data given)
    - texture_data                → list with 2 stub entries so the texture combo
                                    receives one item (the widget iterates len-1)
    """
    manager = MagicMock()

    dynamic_section = DynamicTextureSection()
    if data is not None:
        dynamic_section.analyze(data)
    manager.enemy.dynamic_texture_data = dynamic_section

    # _load_data iterates range(len(texture_data) - 1), so 3 stubs → "Texture 0"
    # and "Texture 1" in the combo.  All PUPU entries have texture_num == 1, so we
    # need index 1 to be selectable.
    from PyQt6.QtGui import QPixmap, QColor
    stub_tex = MagicMock()
    pix = QPixmap(128, 128)
    pix.fill(QColor(0, 0, 0))
    stub_tex.texture_image = pix
    manager.texture_data = [stub_tex, stub_tex, stub_tex]   # len == 3  →  "Texture 0" + "Texture 1"

    return manager


def _make_widget(data: bytearray | None = None) -> tuple[IfritDynamicTextureWidget, MagicMock]:
    """Instantiate a fully wired widget and return (widget, mock_manager)."""
    manager = _make_mock_manager(data)
    widget = IfritDynamicTextureWidget(manager)
    sw = widget.dynamic_texture_widget
    # Simulate opening a file so the texture/entry combos are populated
    sw._load_data()
    # All PUPU entries have texture_num == 1; switch to that texture so
    # _get_entries_for_current_texture() actually finds them.
    if sw.texture_combo.count() > 1:
        sw.texture_combo.setCurrentIndex(1)
    # Flush any pending deleteLater() calls so the layout is clean
    QApplication.processEvents()
    return widget, manager


def _section_widget(w: IfritDynamicTextureWidget) -> DynamicTextureSectionWidget:
    return w.dynamic_texture_widget


def _get_entry_editor(sw: DynamicTextureSectionWidget) -> DynamicTextureEntryWidget:
    """
    Return the live DynamicTextureEntryWidget from the editor layout.

    _load_current_entry_editor() removes old widgets via deleteLater(), which is
    asynchronous — the old widget (possibly a QLabel from _show_empty_editor) stays
    in the layout until the event loop runs.  Calling processEvents() flushes those
    pending deletions, then we search by type so we always get the real editor.
    """
    QApplication.processEvents()
    layout = sw.entry_editor_layout
    # Walk in reverse: the freshly added widget is at the highest index
    for i in reversed(range(layout.count())):
        w = layout.itemAt(i).widget()
        if isinstance(w, DynamicTextureEntryWidget):
            return w
    raise RuntimeError(
        f"No DynamicTextureEntryWidget found in editor layout "
        f"(items: {[layout.itemAt(i).widget().__class__.__name__ for i in range(layout.count())]})"
    )


def _dynamic_data(manager: MagicMock) -> DynamicTextureSection:
    return manager.enemy.dynamic_texture_data


# ===========================================================================
# Section 1 – Pure data-model tests (no Qt widgets)
# ===========================================================================

class TestDynamicTextureDataModel:
    """
    These tests operate solely on DynamicTextureSection / DynamicTextureData
    and do NOT require a QApplication.
    """

    def test_save_pupu_no_change(self):
        """Round-trip: analyze → to_binary must reproduce the original bytes."""
        section = DynamicTextureSection()
        section.analyze(PUPU_DATA)
        result = section.to_binary()
        assert bytes(PUPU_DATA) == bytes(result)

    def test_entry_count_after_analyze(self):
        """The PUPU data encodes exactly 4 animation entries."""
        section = DynamicTextureSection()
        section.analyze(PUPU_DATA)
        assert len(section.dynamic_texture_data) == 4

    # --- source UV modification ---

    def test_modify_source_uv_x(self):
        section = DynamicTextureSection()
        section.analyze(PUPU_DATA)
        entry = section.dynamic_texture_data[0]
        original_y = entry.source_uv.get_v_pixel()
        entry.source_uv.set_u_pixel(100)
        result = section.to_binary()
        # Re-parse and verify the change persisted
        section2 = DynamicTextureSection()
        section2.analyze(result)
        assert section2.dynamic_texture_data[0].source_uv.get_u_pixel() == 100
        assert section2.dynamic_texture_data[0].source_uv.get_v_pixel() == original_y

    def test_modify_source_uv_y(self):
        section = DynamicTextureSection()
        section.analyze(PUPU_DATA)
        entry = section.dynamic_texture_data[0]
        original_x = entry.source_uv.get_u_pixel()
        entry.source_uv.set_v_pixel(200)
        result = section.to_binary()
        section2 = DynamicTextureSection()
        section2.analyze(result)
        assert section2.dynamic_texture_data[0].source_uv.get_u_pixel() == original_x
        assert section2.dynamic_texture_data[0].source_uv.get_v_pixel() == 200

    # --- sprite size modification ---

    def test_modify_sprite_width(self):
        section = DynamicTextureSection()
        section.analyze(PUPU_DATA)
        section.dynamic_texture_data[0].sprite_width = 64
        result = section.to_binary()
        section2 = DynamicTextureSection()
        section2.analyze(result)
        assert section2.dynamic_texture_data[0].sprite_width == 64

    def test_modify_sprite_height(self):
        section = DynamicTextureSection()
        section.analyze(PUPU_DATA)
        section.dynamic_texture_data[0].sprite_height = 48
        result = section.to_binary()
        section2 = DynamicTextureSection()
        section2.analyze(result)
        assert section2.dynamic_texture_data[0].sprite_height == 48

    # --- destination UV modification ---

    def test_modify_destination_uv(self):
        section = DynamicTextureSection()
        section.analyze(PUPU_DATA)
        entry = section.dynamic_texture_data[0]
        entry.dest_uv[0].set_u_pixel(50)
        entry.dest_uv[0].set_v_pixel(75)
        result = section.to_binary()
        section2 = DynamicTextureSection()
        section2.analyze(result)
        assert section2.dynamic_texture_data[0].dest_uv[0].get_u_pixel() == 50
        assert section2.dynamic_texture_data[0].dest_uv[0].get_v_pixel() == 75

    # --- add / remove entry ---

    def test_add_entry(self):
        section = DynamicTextureSection()
        section.analyze(PUPU_DATA)
        original_count = len(section.dynamic_texture_data)

        new_entry = DynamicTextureData()
        new_entry.texture_num = 0
        new_entry.clut_info = 0
        new_entry.source_uv = UV(member_size=1, vram_size=True)
        new_entry.source_uv.set_u_pixel(0)
        new_entry.source_uv.set_v_pixel(0)
        new_entry.sprite_width = 32
        new_entry.sprite_height = 32
        new_entry.number_destination = 1
        new_entry.unk1 = 0
        new_entry.unk2 = 0
        dest = UV(member_size=1, vram_size=True)
        dest.set_u_pixel(0)
        dest.set_v_pixel(0)
        new_entry.dest_uv = [dest]
        section.dynamic_texture_data.append(new_entry)

        result = section.to_binary()
        section2 = DynamicTextureSection()
        section2.analyze(result)
        assert len(section2.dynamic_texture_data) == original_count + 1

    def test_remove_entry(self):
        section = DynamicTextureSection()
        section.analyze(PUPU_DATA)
        original_count = len(section.dynamic_texture_data)
        section.dynamic_texture_data.pop(0)

        result = section.to_binary()
        section2 = DynamicTextureSection()
        section2.analyze(result)
        assert len(section2.dynamic_texture_data) == original_count - 1

    # --- add / remove destination ---

    def test_add_destination(self):
        section = DynamicTextureSection()
        section.analyze(PUPU_DATA)
        entry = section.dynamic_texture_data[0]
        original_dest_count = len(entry.dest_uv)

        new_dest = UV(member_size=1, vram_size=True)
        new_dest.set_u_pixel(10)
        new_dest.set_v_pixel(20)
        entry.dest_uv.append(new_dest)
        entry.number_destination = len(entry.dest_uv)

        result = section.to_binary()
        section2 = DynamicTextureSection()
        section2.analyze(result)
        assert len(section2.dynamic_texture_data[0].dest_uv) == original_dest_count + 1
        assert section2.dynamic_texture_data[0].dest_uv[-1].get_u_pixel() == 10
        assert section2.dynamic_texture_data[0].dest_uv[-1].get_v_pixel() == 20

    def test_remove_destination(self):
        section = DynamicTextureSection()
        section.analyze(PUPU_DATA)
        entry = section.dynamic_texture_data[0]
        original_dest_count = len(entry.dest_uv)
        assert original_dest_count > 1, "Need at least 2 destinations to test removal"

        entry.dest_uv.pop(0)
        entry.number_destination = len(entry.dest_uv)

        result = section.to_binary()
        section2 = DynamicTextureSection()
        section2.analyze(result)
        assert len(section2.dynamic_texture_data[0].dest_uv) == original_dest_count - 1


# ===========================================================================
# Section 2 – DestinationWidget unit tests
# ===========================================================================

class TestDestinationWidget:

    def test_get_data_default(self, qapp):
        w = DestinationWidget(dest_index=0)
        data = w.get_data()
        assert data == {'x': 0, 'y': 0}

    def test_set_get_roundtrip(self, qapp):
        w = DestinationWidget(dest_index=0)
        w.set_data(x=42, y=99)
        data = w.get_data()
        assert data['x'] == 42
        assert data['y'] == 99

    def test_dataChanged_signal_on_x_change(self, qapp):
        w = DestinationWidget(dest_index=0)
        received = []
        w.dataChanged.connect(lambda: received.append(True))
        w.dst_x.setValue(10)
        assert len(received) > 0

    def test_dataChanged_signal_on_y_change(self, qapp):
        w = DestinationWidget(dest_index=0)
        received = []
        w.dataChanged.connect(lambda: received.append(True))
        w.dst_y.setValue(55)
        assert len(received) > 0

    def test_remove_requested_signal(self, qapp):
        w = DestinationWidget(dest_index=3)
        received = []
        w.removeRequested.connect(lambda idx: received.append(idx))
        w.remove_btn.click()
        assert received == [3]


# ===========================================================================
# Section 3 – DynamicTextureEntryWidget unit tests
# ===========================================================================

class TestDynamicTextureEntryWidget:

    def _make_entry_widget(self) -> DynamicTextureEntryWidget:
        return DynamicTextureEntryWidget(entry_index=0)

    def test_default_values(self, qapp):
        w = self._make_entry_widget()
        data = w.get_data()
        assert data['src_x'] == 0
        assert data['src_y'] == 0
        assert data['src_width'] == 32
        assert data['src_height'] == 32
        assert data['destinations'] == []

    def test_set_data_roundtrip(self, qapp):
        w = self._make_entry_widget()
        destinations = [{'x': 10, 'y': 20}, {'x': 30, 'y': 40}]
        w.set_data(src_x=16, src_y=32, src_width=64, src_height=48, destinations=destinations)
        data = w.get_data()
        assert data['src_x'] == 16
        assert data['src_y'] == 32
        assert data['src_width'] == 64
        assert data['src_height'] == 48
        assert len(data['destinations']) == 2
        assert data['destinations'][0] == {'x': 10, 'y': 20}
        assert data['destinations'][1] == {'x': 30, 'y': 40}

    def test_add_destination(self, qapp):
        w = self._make_entry_widget()
        assert len(w.destination_widgets) == 0
        w._add_destination()
        assert len(w.destination_widgets) == 1
        w._add_destination()
        assert len(w.destination_widgets) == 2

    def test_remove_destination(self, qapp):
        w = self._make_entry_widget()
        w._add_destination()
        w._add_destination()
        assert len(w.destination_widgets) == 2
        w._remove_destination(0)
        assert len(w.destination_widgets) == 1

    def test_remove_destination_renumbers(self, qapp):
        w = self._make_entry_widget()
        w._add_destination()
        w._add_destination()
        w._add_destination()
        w._remove_destination(0)
        for i, dest_w in enumerate(w.destination_widgets):
            assert dest_w.dest_index == i

    def test_dataChanged_emitted_on_src_x_change(self, qapp):
        w = self._make_entry_widget()
        received = []
        w.dataChanged.connect(lambda: received.append(True))
        w.src_x.setValue(50)
        assert len(received) > 0

    def test_dataChanged_emitted_on_add_destination(self, qapp):
        w = self._make_entry_widget()
        received = []
        w.dataChanged.connect(lambda: received.append(True))
        w._add_destination()
        assert len(received) > 0


# ===========================================================================
# Section 4 – Full widget integration tests (GUI → data model → binary)
# ===========================================================================

class TestWidgetIntegration:
    """
    These tests wire the full widget stack to a mock IfritManager,
    interact through the public widget API, then verify that
    DynamicTextureSection.to_binary() reflects the changes correctly.
    """

    # --- No change ---

    def test_widget_no_change_roundtrip(self, qapp):
        """Loading data into the widget and not touching anything must not corrupt bytes."""
        widget, manager = _make_widget(PUPU_DATA)
        result = _dynamic_data(manager).to_binary()
        assert bytes(PUPU_DATA) == bytes(result)

    # --- Modify source UV via widget ---

    def test_widget_modify_source_x(self, qapp):
        widget, manager = _make_widget(PUPU_DATA)
        sw = _section_widget(widget)

        # Select first entry and get the editor
        sw.entry_combo.setCurrentIndex(0)
        entry_editor = _get_entry_editor(sw)

        original_y = entry_editor.src_y.value()
        entry_editor.src_x.setValue(100)

        result = _dynamic_data(manager).to_binary()
        section2 = DynamicTextureSection()
        section2.analyze(result)
        assert section2.dynamic_texture_data[0].source_uv.get_u_pixel() == 100
        assert section2.dynamic_texture_data[0].source_uv.get_v_pixel() == original_y

    def test_widget_modify_source_y(self, qapp):
        widget, manager = _make_widget(PUPU_DATA)
        sw = _section_widget(widget)

        sw.entry_combo.setCurrentIndex(0)
        entry_editor = _get_entry_editor(sw)

        original_x = entry_editor.src_x.value()
        entry_editor.src_y.setValue(200)

        result = _dynamic_data(manager).to_binary()
        section2 = DynamicTextureSection()
        section2.analyze(result)
        assert section2.dynamic_texture_data[0].source_uv.get_u_pixel() == original_x
        assert section2.dynamic_texture_data[0].source_uv.get_v_pixel() == 200

    # --- Modify sprite size via widget ---

    def test_widget_modify_sprite_width(self, qapp):
        widget, manager = _make_widget(PUPU_DATA)
        sw = _section_widget(widget)

        sw.entry_combo.setCurrentIndex(0)
        entry_editor = _get_entry_editor(sw)
        entry_editor.src_width.setValue(64)

        result = _dynamic_data(manager).to_binary()
        section2 = DynamicTextureSection()
        section2.analyze(result)
        assert section2.dynamic_texture_data[0].sprite_width == 64

    def test_widget_modify_sprite_height(self, qapp):
        widget, manager = _make_widget(PUPU_DATA)
        sw = _section_widget(widget)

        sw.entry_combo.setCurrentIndex(0)
        entry_editor = _get_entry_editor(sw)
        entry_editor.src_height.setValue(16)

        result = _dynamic_data(manager).to_binary()
        section2 = DynamicTextureSection()
        section2.analyze(result)
        assert section2.dynamic_texture_data[0].sprite_height == 16

    # --- Modify destination via widget ---

    def test_widget_modify_destination_x(self, qapp):
        widget, manager = _make_widget(PUPU_DATA)
        sw = _section_widget(widget)

        sw.entry_combo.setCurrentIndex(0)
        entry_editor = _get_entry_editor(sw)
        assert len(entry_editor.destination_widgets) > 0, "Expected destinations in entry 0"

        entry_editor.destination_widgets[0].dst_x.setValue(88)

        result = _dynamic_data(manager).to_binary()
        section2 = DynamicTextureSection()
        section2.analyze(result)
        assert section2.dynamic_texture_data[0].dest_uv[0].get_u_pixel() == 88

    def test_widget_modify_destination_y(self, qapp):
        widget, manager = _make_widget(PUPU_DATA)
        sw = _section_widget(widget)

        sw.entry_combo.setCurrentIndex(0)
        entry_editor = _get_entry_editor(sw)

        entry_editor.destination_widgets[0].dst_y.setValue(66)

        result = _dynamic_data(manager).to_binary()
        section2 = DynamicTextureSection()
        section2.analyze(result)
        assert section2.dynamic_texture_data[0].dest_uv[0].get_v_pixel() == 66

    # --- Add destination via widget ---

    def test_widget_add_destination(self, qapp):
        widget, manager = _make_widget(PUPU_DATA)
        sw = _section_widget(widget)

        sw.entry_combo.setCurrentIndex(0)
        entry_editor = _get_entry_editor(sw)
        original_count = len(entry_editor.destination_widgets)

        entry_editor.add_dest_btn.click()
        assert len(entry_editor.destination_widgets) == original_count + 1

        result = _dynamic_data(manager).to_binary()
        section2 = DynamicTextureSection()
        section2.analyze(result)
        assert len(section2.dynamic_texture_data[0].dest_uv) == original_count + 1

    # --- Remove destination via widget ---

    def test_widget_remove_destination(self, qapp):
        widget, manager = _make_widget(PUPU_DATA)
        sw = _section_widget(widget)

        sw.entry_combo.setCurrentIndex(0)
        entry_editor = _get_entry_editor(sw)
        original_count = len(entry_editor.destination_widgets)
        assert original_count > 1, "Need ≥2 destinations in entry 0 to remove one"

        entry_editor.destination_widgets[0].remove_btn.click()
        assert len(entry_editor.destination_widgets) == original_count - 1

        result = _dynamic_data(manager).to_binary()
        section2 = DynamicTextureSection()
        section2.analyze(result)
        assert len(section2.dynamic_texture_data[0].dest_uv) == original_count - 1

    # --- Add entry via widget ---

    def test_widget_add_entry(self, qapp):
        widget, manager = _make_widget(PUPU_DATA)
        sw = _section_widget(widget)

        original_count = len(_dynamic_data(manager).dynamic_texture_data)
        sw.add_entry_btn.click()

        assert len(_dynamic_data(manager).dynamic_texture_data) == original_count + 1

        result = _dynamic_data(manager).to_binary()
        section2 = DynamicTextureSection()
        section2.analyze(result)
        assert len(section2.dynamic_texture_data) == original_count + 1

    # --- Remove entry via widget ---

    def test_widget_remove_entry(self, qapp):
        widget, manager = _make_widget(PUPU_DATA)
        sw = _section_widget(widget)

        original_count = len(_dynamic_data(manager).dynamic_texture_data)
        sw.entry_combo.setCurrentIndex(0)
        sw._remove_current_entry()

        assert len(_dynamic_data(manager).dynamic_texture_data) == original_count - 1

        result = _dynamic_data(manager).to_binary()
        section2 = DynamicTextureSection()
        section2.analyze(result)
        assert len(section2.dynamic_texture_data) == original_count - 1

    # --- Add entry then edit it ---

    def test_widget_add_entry_and_edit_source(self, qapp):
        widget, manager = _make_widget(PUPU_DATA)
        sw = _section_widget(widget)

        sw.add_entry_btn.click()
        # The combo should now point to the newly added entry
        new_index = sw.entry_combo.count() - 1
        sw.entry_combo.setCurrentIndex(new_index)

        entry_editor = _get_entry_editor(sw)
        entry_editor.src_x.setValue(32)
        entry_editor.src_y.setValue(64)

        result = _dynamic_data(manager).to_binary()
        section2 = DynamicTextureSection()
        section2.analyze(result)
        new_entry = section2.dynamic_texture_data[-1]
        assert new_entry.source_uv.get_u_pixel() == 32
        assert new_entry.source_uv.get_v_pixel() == 64

    # --- Switch entries and verify independent edits ---

    def test_widget_edit_multiple_entries_independently(self, qapp):
        widget, manager = _make_widget(PUPU_DATA)
        sw = _section_widget(widget)

        # Edit entry 0 source X
        sw.entry_combo.setCurrentIndex(0)
        editor0 = _get_entry_editor(sw)
        editor0.src_x.setValue(10)

        # Edit entry 1 source X
        sw.entry_combo.setCurrentIndex(1)
        editor1 = _get_entry_editor(sw)
        editor1.src_x.setValue(20)

        result = _dynamic_data(manager).to_binary()
        section2 = DynamicTextureSection()
        section2.analyze(result)
        assert section2.dynamic_texture_data[0].source_uv.get_u_pixel() == 10
        assert section2.dynamic_texture_data[1].source_uv.get_u_pixel() == 20