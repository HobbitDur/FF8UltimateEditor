"""Renaming a bone in the 3D tab's bone editor (AnimEditor): the name field, the labels, and the
rename going to the user's bone-name file through the 3D widget."""
import json
import sys
from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QApplication

from FF8GameData.dat.bonenames import BoneNames, write_shipped_file
from Ifrit.Ifrit3D import bonenamestore
from Ifrit.Ifrit3D.boneeditorwidget import AnimEditor
from Ifrit.Ifrit3D.ifrit3dwidget import Ifrit3DWidget


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def test_editor_shows_names_and_emits_renames(qapp):
    editor = AnimEditor()
    editor.set_bone_range(2)
    editor.set_bone_names(["Root", "Body", "Head"], user_named={2})
    editor.bone_spin.setValue(2)
    editor.set_bone_data(2, 1.0, 1024, 1, 0, 0, 0, 0, 0, 0)
    assert editor.bone_name_edit.text() == "Head"
    assert editor.bone_name_edit.font().italic()        # the user's own name
    assert editor.info_label.text() == "2 · Head"
    assert editor.bone_label(7) == "Bone 7"

    renamed = []
    editor.bone_renamed.connect(lambda bone, name: renamed.append((bone, name)))
    editor.bone_name_edit.setText("Lion head")
    editor.bone_name_edit.editingFinished.emit()
    editor.set_bone_names(["Root", "Body", "Lion head"], user_named={2})   # what the widget does next
    editor.bone_name_edit.editingFinished.emit()        # unchanged since: nothing more
    assert renamed == [(2, "Lion head")]


def test_widget_rename_goes_to_the_user_file(qapp, tmp_path):
    shipped = tmp_path / "bone_names.json"
    write_shipped_file(shipped, {"c0m012.dat": ["Root", "Body", "Head"]})
    user = tmp_path / "UserData" / "bone_names.json"
    bonenamestore.set_shared_bone_names(BoneNames(shipped, user))
    try:
        editor = AnimEditor()
        editor.set_bone_range(2)
        # Only what _refresh_bone_names / _on_bone_renamed touch on the widget
        host = SimpleNamespace(
            bone_editor=editor,
            ifrit_manager=SimpleNamespace(enemy=SimpleNamespace(
                origin_file_name="c0m012.dat",
                bone_data=SimpleNamespace(bones=[object()] * 3))))
        host._bone_names_key = lambda: Ifrit3DWidget._bone_names_key(host)
        host._refresh_bone_names = lambda: Ifrit3DWidget._refresh_bone_names(host)
        host._refresh_bone_names()
        assert editor.bone_name(2) == "Head"

        Ifrit3DWidget._on_bone_renamed(host, 2, "Lion head")
        assert json.loads(user.read_text(encoding="utf-8")) == {"c0m012.dat": {"2": "Lion head"}}
        assert editor.bone_name(2) == "Lion head" and 2 in editor._user_named
    finally:
        bonenamestore.set_shared_bone_names(None)
