"""The global section-export choice: dialog, context menu and persisted user settings."""
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QPoint, QSettings, Qt
from PyQt6.QtWidgets import QDialogButtonBox, QMenu, QMessageBox, QPushButton

from FF8GameData.dat.sectionfiles import SECTION_FILES
from FF8GameData.monsterdata import EntityType
from Ifrit.ifritmonsterwidget import IfritMonsterWidget
from Ifrit.sectionexportdialog import SectionExportDialog


@pytest.fixture
def editor(tmp_path, monkeypatch):
    settings = QSettings(str(tmp_path / "export.ini"), QSettings.Format.IniFormat)
    widget = IfritMonsterWidget(settings)
    pane = SimpleNamespace(ifrit_manager=SimpleNamespace(enemy=SimpleNamespace(entity_type=EntityType.MONSTER)))
    monkeypatch.setattr(widget, "_active_pane", lambda: pane)
    yield widget
    widget.deleteLater()


def test_default_exports_all_sections(editor):
    assert editor._export_section_names() == [s.name for s in SECTION_FILES]


def test_dialog_select_all_clear_all_and_requires_a_selection(editor):
    dialog = SectionExportDialog(editor, ["ai", "camera"], EntityType.MONSTER)
    assert dialog.selected_names() == ["camera", "ai"]
    buttons = {b.text(): b for b in dialog.findChildren(QPushButton)}
    buttons["Clear all"].click()
    assert dialog.selected_names() == []
    ok = dialog._buttons.button(QDialogButtonBox.StandardButton.Ok)
    assert not ok.isEnabled()
    dialog._checks["ai"].setChecked(True)
    assert ok.isEnabled()
    buttons["Select all"].click()
    assert dialog.selected_names() == ["skeleton", "geometry", "animation", "dynamic_texture",
                                       "anim_seq", "camera", "info_stat", "ai", "sound",
                                       "sound_bank", "texture"]


def test_accept_saves_the_choice_for_a_new_editor_session(editor, monkeypatch):
    def choose(dialog):
        dialog._set_all(False)
        dialog._checks["ai"].setChecked(True)
        return dialog.DialogCode.Accepted

    monkeypatch.setattr(SectionExportDialog, "exec", choose)
    editor._define_export_sections()
    editor.settings.sync()
    settings = QSettings(editor.settings.fileName(), QSettings.Format.IniFormat)
    reopened = IfritMonsterWidget(settings)
    try:
        assert reopened._export_section_names() == ["extra_animation", "ai"]
    finally:
        reopened.deleteLater()


def test_cancel_does_not_change_the_saved_choice(editor, monkeypatch):
    editor.settings.setValue("ifrit/export_sections", ["camera"])

    def cancel(dialog):
        assert dialog.selected_names() == ["camera"]
        dialog._set_all(True)
        return dialog.DialogCode.Rejected

    monkeypatch.setattr(SectionExportDialog, "exec", cancel)
    editor._define_export_sections()
    assert editor._export_section_names() == ["camera"]


def test_right_click_menu_opens_the_picker_without_exporting(editor, monkeypatch):
    opened = []
    monkeypatch.setattr(editor, "_define_export_sections", lambda: opened.append(True))

    def choose(menu, position):
        assert [a.text() for a in menu.actions()] == ["Define sections..."]
        menu.actions()[0].trigger()

    monkeypatch.setattr(QMenu, "exec", choose)
    button = editor._extract_sections_btn
    assert button.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu
    button.customContextMenuRequested.emit(QPoint(5, 5))
    assert opened == [True]


def test_selection_absent_from_model_does_not_ask_for_a_folder(editor, monkeypatch):
    editor.settings.setValue("ifrit/export_sections", ["extra_animation"])
    pane = SimpleNamespace(ifrit_manager=SimpleNamespace(enemy=SimpleNamespace(entity_type=EntityType.MONSTER)))
    monkeypatch.setattr(editor, "_active_pane", lambda: pane)
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: messages.append(args[2]))
    editor._extract_sections()
    assert len(messages) == 1
    assert "none of the selected sections" in messages[0]


def test_obsolete_section_names_are_ignored(editor):
    editor.settings.setValue("ifrit/export_sections", ["removed_section", "ai"])
    assert editor._export_section_names() == ["ai"]


@pytest.mark.parametrize("entity_type, expected", [
    (EntityType.MONSTER, ["skeleton", "geometry", "animation", "dynamic_texture", "anim_seq",
                          "camera", "info_stat", "ai", "sound", "sound_bank", "texture"]),
    (EntityType.WEAPON, ["skeleton", "geometry", "animation", "anim_seq", "sound", "sound_bank",
                         "texture", "extra_animation"]),
    (EntityType.CHARACTER, ["skeleton", "geometry", "animation", "dynamic_texture", "camera",
                            "texture", "extra_animation"]),
    (EntityType.WEAPON_NO_ANIM, ["geometry", "anim_seq", "sound", "sound_bank", "texture"]),
    (EntityType.CHARACTER_NO_WEAPON, ["skeleton", "geometry", "animation", "dynamic_texture",
                                     "camera", "anim_seq", "sound", "sound_bank", "texture",
                                     "extra_animation"]),
    (EntityType.MONSTER_NO_MODEL, ["info_stat", "ai"]),
])
def test_picker_uses_the_open_models_section_ids_and_order(editor, entity_type, expected):
    dialog = SectionExportDialog(editor, [s.name for s in SECTION_FILES], entity_type)
    assert list(dialog._checks) == expected
    for section_id, check in enumerate(dialog._checks.values(), start=1):
        assert check.text().startswith(f"Section {section_id} - ")


def test_editing_weapon_selection_keeps_monster_only_preferences(editor, monkeypatch):
    editor.settings.setValue("ifrit/export_sections", ["ai", "camera", "animation"])
    pane = SimpleNamespace(ifrit_manager=SimpleNamespace(enemy=SimpleNamespace(entity_type=EntityType.WEAPON)))
    monkeypatch.setattr(editor, "_active_pane", lambda: pane)

    def choose(dialog):
        assert "ai" not in dialog._checks
        assert "camera" not in dialog._checks
        dialog._set_all(False)
        dialog._checks["texture"].setChecked(True)
        return dialog.DialogCode.Accepted

    monkeypatch.setattr(SectionExportDialog, "exec", choose)
    editor._define_export_sections()
    assert set(editor._export_section_names()) == {"ai", "camera", "texture"}
