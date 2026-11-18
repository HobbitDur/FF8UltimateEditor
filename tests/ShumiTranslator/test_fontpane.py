"""ShumiTranslator's font tab (ShumiTranslator/view/fontpane.py) on a synthetic Japanese font and the
real Latin sysfnt.tdw (ff8data)."""
import pathlib
import shutil

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QFileDialog

from FF8GameData.gamedata import FileType, GameData
from tests.FF8GameData.test_tdwfile import make_tdw

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent


@pytest.fixture()
def game_data(tmp_path):
    """GameData whose character table files are copies: a Save of the font tab writes them."""
    data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    resources = tmp_path / "resources"
    resources.mkdir()
    for name in ("sysfnt.txt", "sysfnt_jp.txt", "sysfnt_viet.txt"):
        shutil.copy(PROJECT_ROOT / "FF8GameData" / "Resources" / name, resources / name)
    data.resource_folder = str(resources)
    return data


def _click(widget, x, y):
    for kind in (QMouseEvent.Type.MouseButtonPress, QMouseEvent.Type.MouseButtonRelease):
        event = QMouseEvent(kind, QPointF(x, y), QPointF(x, y), Qt.MouseButton.LeftButton,
                            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        (widget.mousePressEvent if kind == QMouseEvent.Type.MouseButtonPress else widget.mouseReleaseEvent)(event)


def test_japanese_font_tab_paints_saves_and_names_glyphs(tmp_path, game_data, monkeypatch):
    from ShumiTranslator.view.fontpane import GRID_CELL, PIXEL_SIZE, FontPane
    game_data.set_character_table("japanese")
    path = tmp_path / "sysfnt.tdw"
    path.write_bytes(make_tdw(bytes(3 * 112 + 108), palettes=32, height=252))
    pane = FontPane(game_data, str(path))
    assert pane.file_type == FileType.FONT and pane.japanese and pane.table_box.count() == 4

    pane.table_box.setCurrentIndex(2)
    letter = 0xc8 - 0x20
    _click(pane.grid, (letter % 16) * GRID_CELL + 5, (letter // 16) * GRID_CELL + 5)
    assert pane.text_edit.text() == "記" and pane.code_label.text().startswith("1a c8")

    # without a texture the 12 px glyph is the tdw's picture, read-only
    pane.editor.level = 3
    _click(pane.editor, 2 * PIXEL_SIZE + 3, 5 * PIXEL_SIZE + 3)
    assert pane.tdw.level(616, 2, 5) == 0 and not pane._undo.can_undo()
    # the texture is what is painted; Save writes it, and the glyph into the tdw's picture too
    tex_path = tmp_path / "sysfnt.TEX"
    _tex(256, 256, 32).write(str(tex_path))
    pane.attach_texture(str(tex_path))
    assert pane.editor.level == 1  # the paint level starts on the first visible level
    pane.editor.level = 3
    _click(pane.editor, 2 * PIXEL_SIZE + 3, 5 * PIXEL_SIZE + 3)
    assert pane.lowres.level(616, 2, 5) == 3 and pane._undo.can_undo()
    pane.width_spin.setValue(11)
    pane.save()
    from FF8GameData.font.lowresfont import LowresFont
    from FF8GameData.font.tdwfile import TdwFile
    saved = TdwFile.read(str(path))
    assert saved.level(616, 2, 5) == 3 and saved.char_width(2, letter) == 11
    lowres = LowresFont(japanese=True)
    lowres.attach(str(tex_path))
    assert lowres.level(616, 2, 5) == 3 and lowres.level(617, 2, 5) == 0

    # a character edit is used by the text tabs at once; Save asks where to write the table (.txt),
    # never over the table's own file unasked
    table_file = tmp_path / "resources" / "sysfnt_jp.txt"
    before = table_file.read_bytes()
    pane.text_edit.setText("X")
    pane.text_edit.textEdited.emit("X")
    assert game_data.character_table_modified
    assert game_data.translate_hex_to_str([0x1a, 0xc8]) == "X"
    exported = tmp_path / "my_jp.txt"
    asked = []
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: asked.append(a[2]) or (str(exported), ""))
    assert "my_jp.txt" in pane.save() and not game_data.character_table_modified
    assert asked == [str(tmp_path / "sysfnt_jp_custom.txt")] and table_file.read_bytes() == before
    again = GameData(str(PROJECT_ROOT / "FF8GameData"))
    again.set_custom_character_table(str(exported))
    assert again.jp_encoding and again.table_char(2, letter) == "X" and again.table_char(3, 0xa1 - 0x20) == "記"


def _tex(width, height, palettes, fill=0):
    from FF8GameData.tex.texfile import TexFile
    return TexFile(bytes(240), bytes(palettes * 16 * 4), bytearray([fill] * width * height), palettes, 16, 4,
                   width, height)


def test_font_tab_paints_the_attached_texture(tmp_path, game_data):
    from FF8GameData.tex.texfile import TexFile
    from ShumiTranslator.view.fontpane import PIXEL_SIZE, FontPane
    path = tmp_path / "sysfnt.tdw"
    path.write_bytes(make_tdw(bytes(100), palettes=8, height=120))
    tex_path = tmp_path / "sysfnt.TEX"
    _tex(256, 128, 16, fill=7).write(str(tex_path))
    pane = FontPane(game_data, str(path))
    with pytest.raises(ValueError):
        pane.attach_texture(_small_tex(tmp_path))  # a texture of another size is refused
    pane.attach_texture(str(tex_path))
    assert not pane.editor.read_only_pixels and pane.grid.lowres is pane.lowres
    pane.select_letter(0)
    pane.editor.level = 12
    _click(pane.editor, 1 * PIXEL_SIZE + 3, 1 * PIXEL_SIZE + 3)
    message = pane.save()
    assert "sysfnt.TEX" in message
    tex = TexFile.read(str(tex_path))
    assert tex.pixels[256 + 1] == 12 and tex.pixels[0] == 7  # only the painted pixel changes
    from FF8GameData.font.tdwfile import TdwFile
    assert TdwFile.read(str(path)).level(0, 1, 1) == 12  # the tdw's picture follows


def _small_tex(tmp_path):
    from FF8GameData.tex.texfile import TexFile
    small = tmp_path / "small.TEX"
    TexFile(bytes(240), bytes(16 * 4), bytearray(64 * 64), 1, 16, 4, 64, 64).write(str(small))
    return str(small)


def test_font_tab_shows_and_edits_the_vietnamese_table(tmp_path, game_data, monkeypatch):
    from ShumiTranslator.view.fontpane import FontPane
    game_data.set_character_table("vietnamese")
    path = tmp_path / "sysfnt.tdw"
    path.write_bytes(make_tdw(bytes(100), palettes=8, height=120))
    pane = FontPane(game_data, str(path))
    pane.select_letter(0x84 - 0x20)  # Î in the Latin table, drawn as ơ by the Vietnamese font
    assert pane.text_edit.text() == "ơ" and "Vietnamese" in pane.files_label.text()
    pane.text_edit.setText("Ơ")
    pane.text_edit.textEdited.emit("Ơ")
    assert game_data.translate_str_to_hex("Ơ") == [0x84]
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(tmp_path / "viet_mod.txt"), ""))
    pane.save()
    assert GameData.read_character_table_file(str(tmp_path / "viet_mod.txt"))[0x84] == "Ơ"
    assert GameData.read_character_table_file(str(tmp_path / "resources" / "sysfnt_viet.txt"))[0x84] == "ơ"


def test_shell_opens_a_font_tab_without_csv(tmp_path):
    from ShumiTranslator.shumitranslator import ShumiTranslator
    from ShumiTranslator.view.fontpane import FontPane
    path = tmp_path / "sysfnt.tdw"
    path.write_bytes(make_tdw(bytes(100), palettes=8, height=120))
    tool = ShumiTranslator(icon_path=str(PROJECT_ROOT / "Resources"), game_data_folder=str(PROJECT_ROOT / "FF8GameData"))
    tool.open_files([str(path)])
    pane = tool.tab_widget.currentWidget()
    assert isinstance(pane, FontPane) and not pane.japanese
    assert not tool.csv_save_button.isEnabled() and not tool.csv_upload_button.isEnabled()
    tool.table_box.setCurrentIndex(tool.table_box.findData("japanese"))  # the font tab stays, not rebuilt
    assert tool.game_data.jp_encoding and tool.tab_widget.currentWidget() is pane
    assert "Japanese</b> table" in pane.files_label.text()


@pytest.mark.ff8data("extracted_files/menu/sysfnt.tdw")
def test_real_latin_font_opens_and_saves_unchanged(tmp_path, game_data):
    from ShumiTranslator.view.fontpane import FontPane
    path = tmp_path / "sysfnt.tdw"
    shutil.copy(PROJECT_ROOT / "extracted_files" / "menu" / "sysfnt.tdw", path)
    original = path.read_bytes()
    pane = FontPane(game_data, str(path))
    pane.select_letter(0x21 - 0x20)
    assert pane.text_edit.text() == "0" and pane.width_spin.value() == pane.tdw.char_width(0, 1)
    pane.save()
    assert path.read_bytes() == original


def test_font_tab_edits_and_saves_the_hires_glyph(tmp_path, game_data):
    from FF8GameData.font.hiresfont import HiresFont
    from ShumiTranslator.view.fontpane import HIRES_PIXEL_SIZE, FontPane
    from tests.FF8GameData.test_hiresfont import make_latin
    path = tmp_path / "sysfnt.tdw"
    path.write_bytes(make_tdw(bytes(100), palettes=8, height=120))
    make_latin(tmp_path)
    pane = FontPane(game_data, str(path))
    assert pane.hires_box.isHidden()
    pane.attach_hires(str(tmp_path / "sysfld00.TEX"))
    assert not pane.hires_box.isHidden() and pane.grid.hires is pane.hires
    pane.select_letter(10)
    pane.hires_editor.level = 33
    _click(pane.hires_editor, 20 * HIRES_PIXEL_SIZE + 2, 5 * HIRES_PIXEL_SIZE + 2)
    assert pane.hires.level(10, 20, 5) == 33 and pane._undo.can_undo()
    message = pane.save()
    assert "sysfld01.tex" in message
    assert HiresFont.from_path(str(tmp_path / "sysfld00.TEX")).level(10, 20, 5) == 33
    assert pane.undo() and pane.hires.level(10, 20, 5) != 33  # the stroke undone
    assert pane.redo() and pane.hires.level(10, 20, 5) == 33


def test_shell_custom_character_table_from_the_list(tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QFileDialog
    from ShumiTranslator.shumitranslator import ShumiTranslator
    custom = tmp_path / "my_font.txt"
    values = GameData.read_character_table_file(str(PROJECT_ROOT / "FF8GameData" / "Resources" / "sysfnt.txt"))
    shutil.copy(PROJECT_ROOT / "FF8GameData" / "Resources" / "sysfnt.txt", custom)
    values[0x21] = "Ж"
    GameData.write_character_table_file(str(custom), values)
    tool = ShumiTranslator(icon_path=str(PROJECT_ROOT / "Resources"), game_data_folder=str(PROJECT_ROOT / "FF8GameData"))
    labels = [tool.table_box.itemText(i) for i in range(tool.table_box.count())]
    assert labels == ["Latin", "Japanese", "Vietnamese", "Custom file..."]
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(custom), ""))
    tool.table_box.setCurrentIndex(tool.table_box.findData(tool.PICK_TABLE))
    assert tool.game_data.character_table == "custom" and tool.game_data.translate_hex_to_str([0x21]) == "Ж"
    assert tool.table_box.currentText() == "Custom: my_font.txt"
    # cancelling the picker keeps the table in use
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
    tool.table_box.setCurrentIndex(tool.table_box.findData(tool.PICK_TABLE))
    assert tool.table_box.currentText() == "Custom: my_font.txt"
    tool.table_box.setCurrentIndex(tool.table_box.findData("latin"))
    assert tool.game_data.translate_hex_to_str([0x21]) == "0"
    assert tool.table_box.findText("Custom: my_font.txt") == -1


def test_shell_opens_every_hires_texture_at_once(tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QFileDialog
    from ShumiTranslator.shumitranslator import ShumiTranslator
    from tests.FF8GameData.test_hiresfont import make_latin
    path = tmp_path / "sysfnt.tdw"
    path.write_bytes(make_tdw(bytes(100), palettes=8, height=120))
    hires = tmp_path / "hires"
    hires.mkdir()
    make_latin(hires)
    tool = ShumiTranslator(icon_path=str(PROJECT_ROOT / "Resources"), game_data_folder=str(PROJECT_ROOT / "FF8GameData"))
    tool.open_files([str(path)])
    labels = [label for label, _callback in tool.complementary_entries()]
    assert labels[-1].startswith("font textures, high res")
    picked = [str(hires / "sysfld00.TEX"), str(hires / "sysfld01.tex")]
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: (picked, ""))
    tool.complementary_entries()[-1][1]()
    pane = tool.tab_widget.currentWidget()
    assert pane.hires is not None and len(pane.hires.paths) == 2


def test_changed_characters_are_unsaved_until_a_txt_is_chosen(tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    from ShumiTranslator.shumitranslator import ShumiTranslator
    monkeypatch.setattr(QMessageBox, "exec", lambda self: None)  # Save's "Data saved" box
    path = tmp_path / "sysfnt.tdw"
    path.write_bytes(make_tdw(bytes(100), palettes=8, height=120))
    tool = ShumiTranslator(icon_path=str(PROJECT_ROOT / "Resources"), game_data_folder=str(PROJECT_ROOT / "FF8GameData"))
    builtin = PROJECT_ROOT / "FF8GameData" / "Resources" / "sysfnt.txt"
    before = builtin.read_bytes()
    tool.open_files([str(path)])
    pane = tool.tab_widget.currentWidget()
    pane.select_letter(0x21 - 0x20)
    pane.text_edit.setText("Ж")
    pane.text_edit.textEdited.emit("Ж")
    assert pane.dirty_state.dirty and tool.has_unsaved_changes()
    # no .txt chosen: the font is saved, the characters stay unsaved
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    tool.save_folder()
    assert pane.dirty_state.dirty and tool.game_data.character_table_modified
    saved = tmp_path / "my_table.txt"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(saved), ""))
    tool.save_folder()
    assert not pane.dirty_state.dirty and GameData.read_character_table_file(str(saved))[0x21] == "Ж"
    assert builtin.read_bytes() == before  # the built-in table is left as it was
    assert tool.game_data.character_table == "latin" and tool.game_data.translate_hex_to_str([0x21]) == "Ж"


def test_undo_back_to_the_saved_font_clears_the_star(tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    from ShumiTranslator.shumitranslator import ShumiTranslator
    from ShumiTranslator.view.fontpane import PIXEL_SIZE
    monkeypatch.setattr(QMessageBox, "exec", lambda self: None)
    path = tmp_path / "sysfnt.tdw"
    path.write_bytes(make_tdw(bytes(100), palettes=8, height=120))
    tex_path = tmp_path / "sysfnt.TEX"
    _tex(256, 128, 8).write(str(tex_path))
    tool = ShumiTranslator(icon_path=str(PROJECT_ROOT / "Resources"), game_data_folder=str(PROJECT_ROOT / "FF8GameData"))
    tool.open_files([str(path)])
    pane = tool.tab_widget.currentWidget()
    pane.attach_texture(str(tex_path))
    pane.select_letter(1)
    letter_char, width = pane.text_edit.text(), pane.width_spin.value()
    assert not pane.text_edit.isUndoAvailable()  # Ctrl+Z in the Text field is the tab's undo

    pane.text_edit.setText("Ж")
    pane.text_edit.textEdited.emit("Ж")
    pane.width_spin.setValue(width + 3)
    pane.editor.level = 5
    _click(pane.editor, 2 * PIXEL_SIZE + 3, 5 * PIXEL_SIZE + 3)  # one stroke: one step
    assert pane.dirty_state.dirty and tool.game_data.character_table_modified

    assert tool.undo() and pane.lowres.level(pane.editor.glyph, 2, 5) == 0
    assert tool.undo() and pane.width_spin.value() == width
    assert pane.dirty_state.dirty  # the character is still changed
    assert tool.undo() and pane.text_edit.text() == letter_char
    assert not pane.dirty_state.dirty and not tool.game_data.character_table_modified
    assert not tool.undo()

    assert tool.redo() and pane.text_edit.text() == "Ж" and pane.dirty_state.dirty
    assert tool.undo() and not pane.dirty_state.dirty
    # an edit undone after a Save is unsaved again
    pane.width_spin.setValue(width + 1)
    tool.save_folder()
    assert not pane.dirty_state.dirty
    assert tool.undo() and pane.dirty_state.dirty and pane.width_spin.value() == width
    assert tool.redo() and not pane.dirty_state.dirty
