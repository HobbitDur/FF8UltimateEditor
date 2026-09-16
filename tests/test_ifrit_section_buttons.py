"""The Extract sections / Apply sections buttons of the Ifrit monster editor.

They drive the section files (FF8GameData/dat/sectionfiles) from the GUI: extract writes one file
per section of the open .dat, apply puts a folder's files back onto it, taking only the sections
the user ticked. What is pinned here is the wiring around them, which the CLI tests cannot see:
the chosen sections (and only those) reach the model, the file is marked edited, the apply is one
undo step, and a folder holding no usable file is refused.

Needs the real (copyright, gitignored) monster files under extracted_files/battle/.
"""
import os
import pathlib

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox

PROJECT_ROOT = pathlib.Path(__file__).parent.parent
BATTLE_DIR = PROJECT_ROOT / "extracted_files" / "battle"
FIRST = "c0m071.dat"
SECOND = "c0m072.dat"
NEEDS_FILES = pytest.mark.ff8data(f"extracted_files/battle/{FIRST}", f"extracted_files/battle/{SECOND}")


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def editor(app, monkeypatch):
    """The Ifrit tool with c0m071 open, and every message box silenced."""
    from PyQt6.QtCore import QSettings
    from Ifrit.ifritmonsterwidget import IfritMonsterWidget

    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Ok)
    widget = IfritMonsterWidget(QSettings("FF8UltimateEditorTest", "SectionButtons"),
                                game_data_folder=str(PROJECT_ROOT / "FF8GameData"))
    widget.load_file(str(BATTLE_DIR / FIRST))
    yield widget
    widget.deleteLater()


def _pane(editor):
    return editor._files[editor._active_index]['pane']


def _section_bytes(editor, name):
    from FF8GameData.dat.monsteranalyser import MonsterAnalyser
    enemy = _pane(editor).ifrit_manager.enemy
    enemy.get_bytes(editor._game_data)
    index = MonsterAnalyser.SECTION_INDEX_BY_ENTITY[enemy.entity_type][name]
    return bytes(enemy.section_raw_data[index])


def _other_texture_section(editor, folder) -> bytes:
    """The texture section the TIMs of `folder` make up."""
    from FF8GameData.dat.sectionfiles import texturefile
    return bytes(texturefile.read_section_bytes(pathlib.Path(folder)))


def _extract_into(editor, monkeypatch, folder) -> pathlib.Path:
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(folder))
    editor._extract_sections()
    return pathlib.Path(folder) / FIRST.replace(".dat", "")


def _apply_files(editor, monkeypatch, paths):
    """Apply the given files: picking them in the dialog IS choosing the sections."""
    monkeypatch.setattr(QFileDialog, "getOpenFileNames",
                        lambda *a, **k: ([str(path) for path in paths], ""))
    editor._apply_sections()


@NEEDS_FILES
def test_extract_writes_one_file_per_section_in_a_folder_named_after_the_dat(editor, monkeypatch, tmp_path):
    folder = _extract_into(editor, monkeypatch, tmp_path)
    assert folder.name == "c0m071"
    written = sorted(path.name for path in folder.iterdir())
    assert set(written) >= {"skeleton.bin", "geometry.bin", "animation.bin", "dynamic_texture.xml",
                            "anim_seq.xml", "camera.xml", "battle_text.txt",
                            "ai.md", "sound.bin", "sound_bank.bin", "texture_00.tim"}
    # Every section is a FILE of the folder, textures included (nothing in a sub-folder), so
    # selecting everything in it selects every section in one go
    assert all(path.is_file() for path in folder.iterdir())


@NEEDS_FILES
def test_apply_takes_only_the_ticked_sections(editor, monkeypatch, tmp_path):
    # Extract the sections of ANOTHER monster, then apply them onto the open one
    editor.load_file(str(BATTLE_DIR / SECOND))
    _extract_into(editor, monkeypatch, tmp_path / "other")
    other_folder = tmp_path / "other" / "c0m072"
    editor.load_file(str(BATTLE_DIR / FIRST))

    before = {name: _section_bytes(editor, name) for name in ("camera", "dynamic_texture", "anim_seq")}
    _apply_files(editor, monkeypatch, [other_folder / "camera.xml"])
    after = {name: _section_bytes(editor, name) for name in ("camera", "dynamic_texture", "anim_seq")}
    assert after["camera"] != before["camera"], "the chosen file must be applied"
    assert after["dynamic_texture"] == before["dynamic_texture"], "a file not chosen must be left alone"
    assert after["anim_seq"] == before["anim_seq"]


@NEEDS_FILES
def test_apply_marks_the_file_edited_and_is_one_undo_step(editor, monkeypatch, tmp_path):
    editor.load_file(str(BATTLE_DIR / SECOND))
    _extract_into(editor, monkeypatch, tmp_path / "other")
    other_folder = tmp_path / "other" / "c0m072"
    editor.load_file(str(BATTLE_DIR / FIRST))

    before = _section_bytes(editor, "camera")
    assert not _pane(editor).dirty
    _apply_files(editor, monkeypatch, [other_folder / "camera.xml"])
    assert _pane(editor).dirty, "applying sections must mark the file as edited"
    assert _section_bytes(editor, "camera") != before

    editor.undo()
    assert _section_bytes(editor, "camera") == before, "one Ctrl+Z must undo the whole apply"


@NEEDS_FILES
def test_a_file_that_is_not_a_section_file_is_ignored(editor, monkeypatch, tmp_path):
    stray = tmp_path / "notes.txt"
    stray.write_text("not a section file", encoding="utf-8")
    before = _section_bytes(editor, "camera")
    _apply_files(editor, monkeypatch, [stray])
    assert _section_bytes(editor, "camera") == before
    assert not _pane(editor).dirty


@NEEDS_FILES
def test_several_files_at_once_and_a_tim_takes_the_whole_texture_folder(editor, monkeypatch, tmp_path):
    editor.load_file(str(BATTLE_DIR / SECOND))
    _extract_into(editor, monkeypatch, tmp_path / "other")
    other_folder = tmp_path / "other" / "c0m072"
    editor.load_file(str(BATTLE_DIR / FIRST))

    before = {name: _section_bytes(editor, name) for name in ("camera", "anim_seq", "texture", "dynamic_texture")}
    _apply_files(editor, monkeypatch, [other_folder / "camera.xml",
                                       other_folder / "anim_seq.xml",
                                       other_folder / "texture_00.tim"])
    after = {name: _section_bytes(editor, name) for name in ("camera", "anim_seq", "texture", "dynamic_texture")}
    assert after["camera"] != before["camera"]
    assert after["anim_seq"] != before["anim_seq"]
    # One texture file picked = the whole texture set of that folder
    assert after["texture"] == _other_texture_section(editor, other_folder)
    assert after["dynamic_texture"] == before["dynamic_texture"], "sections whose file was not picked stay"


@NEEDS_FILES
def test_buttons_are_off_until_a_file_is_shown(app, monkeypatch):
    from PyQt6.QtCore import QSettings
    from Ifrit.ifritmonsterwidget import IfritMonsterWidget
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    widget = IfritMonsterWidget(QSettings("FF8UltimateEditorTest", "SectionButtons"),
                                game_data_folder=str(PROJECT_ROOT / "FF8GameData"))
    try:
        assert not widget._extract_sections_btn.isEnabled()
        assert not widget._apply_sections_btn.isEnabled()
        widget.load_file(str(BATTLE_DIR / FIRST))
        assert widget._extract_sections_btn.isEnabled()
        assert widget._apply_sections_btn.isEnabled()
    finally:
        widget.deleteLater()
