"""The 3D toolbar's skeleton options menu: its "Apply to all following frames" entry is the same
switch as the Rotation tab's checkbox (both ways), follows the Entrance tab's view too, and is
remembered across sessions."""
import sys

import pytest
from PyQt6.QtWidgets import QApplication

from Ifrit.ifritmanager import IfritManager
from Ifrit.Ifrit3D.ifrit3dwidget import Ifrit3DWidget


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def test_menu_entry_and_rotation_checkbox_are_one_switch(qapp):
    manager = IfritManager()
    view = Ifrit3DWidget(manager)
    view.bone_editor.propagate_rotation_cb.setChecked(True)     # whatever an earlier test saved
    action, checkbox = view._propagate_action, view.bone_editor.propagate_rotation_cb
    assert action in view._skeleton_menu.actions()
    assert action.isChecked() and checkbox.isChecked()
    assert action.toolTip() == checkbox.toolTip()
    action.setChecked(False)
    assert not checkbox.isChecked() and not view._propagate_rotation_enabled()
    checkbox.setChecked(True)
    assert action.isChecked() and view._propagate_rotation_enabled()

    entrance = Ifrit3DWidget(manager)
    view.share_view_toggles(entrance)
    action.setChecked(False)
    assert not entrance._propagate_action.isChecked()
    assert not entrance.bone_editor.propagate_rotation_cb.isChecked()


def test_the_choice_is_remembered(qapp):
    manager = IfritManager()
    view = Ifrit3DWidget(manager)
    view._propagate_action.setChecked(False)
    reopened = Ifrit3DWidget(manager)                # a new session reads the saved choice
    assert not reopened._propagate_action.isChecked()
    assert not reopened.bone_editor.propagate_rotation_cb.isChecked()
    reopened.bone_editor.propagate_rotation_cb.setChecked(True)
    assert Ifrit3DWidget(manager)._propagate_action.isChecked()
