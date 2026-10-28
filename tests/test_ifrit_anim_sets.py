"""Ifrit's "Exe - Limit anim." tab: the exe's battle anim sets of the loaded character, from the FF8
exe or FFNx effect_NNN.animset files (a file wins), previewed and edited on the character's own
skeleton, converted to 30 fps, saved as .animset or back into the exe when it fits. On a character
body the body animations + sequences, on its weapon the weapon animations, both tabs editing the
same set (one document per set, held by the shared AnimSetSource)."""
import os
import shutil

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QMessageBox
_APP = QApplication.instance() or QApplication([])

from Common.fileregistry import FileRegistry
from FF8GameData.dat import exeanimset
from Ifrit.IfritAnimSet.ifritanimsetwidget import ANIM_SET_FILE_NAME, EXE_FILE_NAME, NO_SOURCE_TOOLTIP, TAB_LABEL
from Ifrit.ifritmonsterwidget import IfritMonsterWidget

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BATTLE = os.path.join(REPO, "extracted_files", "battle")
EXE = os.path.join(REPO, "extracted_files", "FF8_EN.exe")
NAMES = ["d2c006.dat", "d2w013.dat", "d1w008.dat"]   # Irvine, his first gun, Zell's (reduced) gloves

pytestmark = pytest.mark.skipif(not os.path.isfile(EXE) or not all(os.path.isfile(os.path.join(BATTLE, n))
                                                                     for n in NAMES),
                                reason="FF8_EN.exe / Irvine's models not available")


def _settle():
    for _ in range(5):
        QApplication.processEvents()


@pytest.fixture
def session(tmp_path):
    for name in NAMES:
        shutil.copy(os.path.join(BATTLE, name), tmp_path / name)
    exe = tmp_path / "FF8_EN.exe"
    shutil.copy(EXE, exe)
    registry = FileRegistry()
    widget = IfritMonsterWidget(settings=QSettings("test", "ifrit_anim_sets"), icon_path="Resources",
                                game_data_folder="FF8GameData", file_registry=registry)
    widget.resize(1400, 850)
    widget.show()
    widget._build_session([str(tmp_path / name) for name in NAMES])
    _settle()
    yield widget, registry, tmp_path, exe
    widget.close()


def _pane(widget, name):
    for entry in widget._files:
        if os.path.basename(entry['path']) == name:
            widget._file_list.setCurrentRow(widget._files.index(entry))
            _settle()
            return entry['pane']
    raise AssertionError(name)


def _tab_state(pane):
    """'hidden', 'greyed' (with the tooltip asking for the exe) or 'usable'."""
    index = pane._tabs.indexOf(pane._anim_set_widget)
    if not pane._tabs.isTabVisible(index):
        return "hidden"
    if not pane._tabs.isTabEnabled(index):
        assert pane._tabs.tabToolTip(index) == NO_SOURCE_TOOLTIP and "FF8_EN.exe" in NO_SOURCE_TOOLTIP
        return "greyed"
    assert pane._tabs.tabToolTip(index) == ""
    return "usable"


def test_tab_follows_the_exe_and_the_character(session):
    widget, registry, _tmp, exe = session
    body = _pane(widget, "d2c006.dat")
    assert pane_label(body) == TAB_LABEL and _tab_state(body) == "greyed"  # no exe, no file: greyed
    assert _tab_state(_pane(widget, "d2w013.dat")) == "greyed"
    registry.open_file(EXE_FILE_NAME, str(exe))
    _settle()
    assert _tab_state(_pane(widget, "d2c006.dat")) == "usable"
    weapon = _pane(widget, "d2w013.dat")
    assert pane_label(weapon) == TAB_LABEL and _tab_state(weapon) == "usable"   # a weapon with its own anims
    assert _tab_state(_pane(widget, "d1w008.dat")) == "hidden"            # a reduced weapon never has any
    registry.close_file(EXE_FILE_NAME)
    _settle()
    assert _tab_state(_pane(widget, "d2c006.dat")) == "greyed"
    weapon = _pane(widget, "d2w013.dat")
    assert _tab_state(weapon) == "greyed"
    # the exe closed while the tab is on screen: greyed, another tab is shown
    registry.open_file(EXE_FILE_NAME, str(exe))
    _settle()
    weapon._tabs.setCurrentWidget(weapon._anim_set_widget)
    _settle()
    registry.close_file(EXE_FILE_NAME)
    _settle()
    assert _tab_state(weapon) == "greyed" and weapon._tabs.currentWidget() is not weapon._anim_set_widget


def pane_label(pane):
    return pane._tabs.tabText(pane._tabs.indexOf(pane._anim_set_widget))


def test_sets_preview_convert_and_save(session, monkeypatch):
    widget, registry, tmp_path, exe = session
    registry.open_file(EXE_FILE_NAME, str(exe))
    body = _pane(widget, "d2c006.dat")
    body._tabs.setCurrentWidget(body._anim_set_widget)
    _settle()
    tab = body._anim_set_widget
    assert [info.effect_id for info in tab._infos] == [188, 192, 193, 194, 195, 196, 197, 198]
    document = tab.holder.document
    assert document is not None and document.body.nb_animations == 8 and document.weapon.nb_animations == 8
    assert tab.view_3d.ifrit_manager.enemy.animation_data is document.body   # the 3D view plays the set
    assert len(document.seq_animation_data['seq_animation_data']) == 5 and len(tab.seq_widget.seq_data_widget) == 5
    assert not body.dirty

    # 30 fps: an edit of the set, not of the .dat
    report = tab.convert_to_30fps(confirm=False)
    assert report['nb_converted'] == 8 and not body.dirty and tab.is_modified()
    assert "*" in tab.set_selector.currentText()
    # it no longer fits the exe: refused, nothing written
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda _parent, _title, text: warnings.append(text))
    before = exe.read_bytes()
    assert not tab.save_into_exe(confirm=False)
    assert "effect_188.animset" in warnings[-1] and exe.read_bytes() == before
    # as an FFNx file it is fine
    path = tab.save_file(folder=str(tmp_path))
    assert os.path.basename(path) == "effect_188.animset" and not tab.is_modified()
    data = open(path, "rb").read()
    assert exeanimset.anim_set_error(data, 3) is None and len(data) > 0x1570

    # opening that file: it wins over the exe for 188, the other sets still come from the exe
    registry.open_file(ANIM_SET_FILE_NAME, path)
    _settle()
    body._tabs.setCurrentWidget(body._anim_set_widget)
    _settle()
    assert tab.source.entry(tab._infos[0]).kind == "file"
    assert len(tab.holder.document.body.animations[0].frames) % 2 == 0

    # an unedited exe set saved back into the exe keeps the exe as it was
    tab.set_selector.setCurrentIndex(1)                                    # 192 Scatter Shot, from the exe
    _settle()
    assert tab.source.entry(tab._infos[1]).kind == "exe"
    assert tab.save_into_exe(confirm=False) and exe.read_bytes() == before
    assert not warnings[1:]


# ----------------------------------------------------------------------------- the weapon's tab
def _show_tab(pane):
    pane._tabs.setCurrentWidget(pane._anim_set_widget)
    _settle()
    return pane._anim_set_widget


def test_weapon_tab_lists_the_sets_with_weapon_animations_for_its_skeleton(session, monkeypatch):
    widget, registry, _tmp, exe = session
    registry.open_file(EXE_FILE_NAME, str(exe))
    tab = _show_tab(_pane(widget, "d2w013.dat"))
    assert tab.pool == "weapon" and tab.seq_widget is None                 # no sequence editor here
    assert [info.effect_id for info in tab._infos] == [188, 192, 193, 194, 195, 196, 197, 198]
    document = tab.holder.document
    # the set's WEAPON animations, on the opened weapon's own skeleton and mesh
    assert tab.view_3d.ifrit_manager.enemy.animation_data is document.weapon
    assert document.weapon.nb_animations == 8
    assert len(tab.view_3d.ifrit_manager.enemy.bone_data.bones) == 3
    assert "Weapon animation N plays with body animation N" in tab.source_label.text()
    assert tab.inner_tabs.tabText(1) == "Sequences (body, read-only)" and tab.seq_text.isReadOnly()
    assert "# Sequence 1" in tab.seq_text.toPlainText()
    # a set whose weapon animations are for another bone count is not listed: nothing left, tab hidden
    monkeypatch.setitem(exeanimset.CHARACTER_MODELS, "Irvine", ("d2c", 34, 4))
    assert tab.set_infos() == [] and not tab.has_sets() and not tab.can_have_sets()
    # sets without weapon animations (Zell, Kiros, Edea) never list on a weapon
    assert not [info for character in ("Zell", "Kiros", "Edea")
                for info in exeanimset.sets_of_character(character) if info.weapon_bones]


def test_body_and_weapon_tabs_edit_one_document(session):
    widget, registry, _tmp, exe = session
    registry.open_file(EXE_FILE_NAME, str(exe))
    body_tab = _show_tab(_pane(widget, "d2c006.dat"))
    info = body_tab._infos[0]
    document = body_tab.holder.document
    assert widget.anim_set_source.entry(info).document is document
    assert not widget.has_unsaved_changes()
    # an edit in the body tab: the set is marked, the tool has unsaved changes
    position = document.body.animations[0].frames[0].position[0]
    position.set_pos_raw(position.get_pos_raw() + 7)
    body_tab._on_set_edit()
    assert body_tab.is_modified() and widget.has_unsaved_changes()
    assert "*" in body_tab.set_selector.currentText()

    # the weapon's tab shows the same set, edited (the body's pane is gone: only one pane lives)
    weapon_tab = _show_tab(_pane(widget, "d2w013.dat"))
    assert weapon_tab.holder.document is document and "*" in weapon_tab.set_selector.currentText()
    weapon_frame = document.weapon.animations[0].frames[0]
    assert weapon_tab.view_3d.ifrit_manager.enemy.animation_data.animations[0].frames[0] is weapon_frame
    weapon_tab._on_set_edit()

    # and back on the body: still that document (the edit kept), its weapon pool the weapon tab's
    body_tab = _show_tab(_pane(widget, "d2c006.dat"))
    assert body_tab.holder.document is document and body_tab._current_info() == info
    assert document.body.animations[0].frames[0].position[0] is position
    assert document.weapon.animations[0].frames[0] is weapon_frame
    rebuilt = document.to_anim_set()
    assert rebuilt.body != document.original.body and rebuilt.weapon is not None
    # opening or closing a source drops the unedited sets only
    other = body_tab._infos[1]
    body_tab.set_selector.setCurrentIndex(1)
    _settle()
    assert widget.anim_set_source.entry(other) is not None
    registry.close_file(EXE_FILE_NAME)
    _settle()
    assert widget.anim_set_source.entry(other) is None
    assert widget.anim_set_source.entry(info).document is document and widget.has_unsaved_changes()


def test_weapon_tab_converts_both_pools_and_saves_the_whole_set(session):
    widget, registry, tmp_path, exe = session
    registry.open_file(EXE_FILE_NAME, str(exe))
    weapon_tab = _show_tab(_pane(widget, "d2w013.dat"))
    info = weapon_tab._current_info()
    before = weapon_tab.holder.document
    body_frames = [len(animation.frames) for animation in before.body.animations]
    weapon_frames = [len(animation.frames) for animation in before.weapon.animations]
    assert body_frames == weapon_frames                                    # lockstep, same ids

    report = weapon_tab.convert_to_30fps(confirm=False)
    assert report['nb_converted'] == 8 and widget.has_unsaved_changes()
    converted = weapon_tab.holder.document
    assert converted is widget.anim_set_source.entry(info).document and converted is not before
    assert [len(a.frames) for a in converted.weapon.animations] == [2 * n for n in weapon_frames]
    assert [len(a.frames) for a in converted.body.animations] == [2 * n for n in body_frames]
    assert weapon_tab.view_3d.ifrit_manager.enemy.animation_data is converted.weapon

    # the body's tab sees the converted set
    body_tab = _show_tab(_pane(widget, "d2c006.dat"))
    assert body_tab.holder.document is converted and "*" in body_tab.set_selector.currentText()
    assert len(body_tab.seq_widget.seq_data_widget) == len(converted.seq_animation_data['seq_animation_data'])

    # saved from the weapon tab: the file holds the body, the sequences and the weapon, all converted
    weapon_tab = _show_tab(_pane(widget, "d2w013.dat"))
    path = weapon_tab.save_file(folder=str(tmp_path))
    assert os.path.basename(path) == "effect_188.animset"
    assert not widget.anim_set_source.has_modified() and not widget.has_unsaved_changes()
    saved = exeanimset.AnimSet.parse(open(path, "rb").read(), info)
    assert saved.section_count == 3
    body = exeanimset.parse_animation_section(saved.body, info.body_bones)
    weapon = exeanimset.parse_animation_section(saved.weapon, info.weapon_bones)
    assert [len(a.frames) for a in body.animations] == [2 * n for n in body_frames]
    assert [len(a.frames) for a in weapon.animations] == [2 * n for n in weapon_frames]
    assert "*" not in weapon_tab.set_selector.currentText()
