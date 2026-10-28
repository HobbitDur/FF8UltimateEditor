"""Ifrit's "Exe - Limit anim." tab: the exe's battle anim sets of the loaded character, from the FF8
exe or FFNx effect_NNN.animset files (a file wins), previewed and edited on the character's own
skeleton, converted to 30 fps, saved as .animset or back into the exe when it fits."""
import os
import shutil

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QMessageBox
_APP = QApplication.instance() or QApplication([])

from Common.fileregistry import FileRegistry
from FF8GameData.dat import exeanimset
from Ifrit.IfritAnimSet.ifritanimsetwidget import ANIM_SET_FILE_NAME, EXE_FILE_NAME, TAB_LABEL
from Ifrit.ifritmonsterwidget import IfritMonsterWidget

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BATTLE = os.path.join(REPO, "extracted_files", "battle")
EXE = os.path.join(REPO, "extracted_files", "FF8_EN.exe")
NAMES = ["d2c006.dat", "d2w013.dat"]   # Irvine and his first gun

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


def _tab_shown(pane):
    return pane._tabs.isTabVisible(pane._tabs.indexOf(pane._anim_set_widget))


def test_tab_follows_the_exe_and_the_character(session):
    widget, registry, _tmp, exe = session
    body = _pane(widget, "d2c006.dat")
    assert pane_label(body) == TAB_LABEL and not _tab_shown(body)          # no exe, no file: hidden
    registry.open_file(EXE_FILE_NAME, str(exe))
    _settle()
    assert _tab_shown(body)
    weapon = _pane(widget, "d2w013.dat")
    assert not _tab_shown(weapon)                                           # a weapon has none
    registry.close_file(EXE_FILE_NAME)
    _settle()
    assert not _tab_shown(_pane(widget, "d2c006.dat"))


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
    assert tab._origins[tab._infos[0]][0] == "file" and len(tab.holder.document.body.animations[0].frames) % 2 == 0

    # an unedited exe set saved back into the exe keeps the exe as it was
    tab.set_selector.setCurrentIndex(1)                                    # 192 Scatter Shot, from the exe
    _settle()
    assert tab._origins[tab._infos[1]][0] == "exe"
    assert tab.save_into_exe(confirm=False) and exe.read_bytes() == before
    assert not warnings[1:]
