"""NPC tab's two field folders, opened from the header in any order: the one you edit (Save writes
there) and the vanilla reference (read-only). With only vanilla open, Save asks where to create
the mod's field folder - and refuses a folder where it would lose a mod's own changes."""
import os
import pathlib
import shutil
import sys

import pytest
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox

from CCGroup.jsmcardgame import JsmCardGameFile, PARAM_RARE_CHANCE

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
FIELD = PROJECT_ROOT / "extracted_files" / "field" / "mapdata" / "bg"
MAPS = ("bghall_1", "bgmon_4")
HALL = os.path.join("mapdata", "bg", "bghall_1", "bghall_1.jsm")

pytestmark = pytest.mark.ff8data(*[f"extracted_files/field/mapdata/bg/{name}/{name}.{extension}"
                                   for name in MAPS for extension in ("jsm", "sym")])


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def folders(tmp_path):
    """vanilla/field with 2 maps, and mod/field holding a bghall_1 whose first rare chance is 99."""
    vanilla = tmp_path / "vanilla" / "field"
    for name in MAPS:
        (vanilla / "mapdata" / "bg" / name).mkdir(parents=True)
        for extension in ("jsm", "sym"):
            shutil.copy(FIELD / name / f"{name}.{extension}", vanilla / "mapdata" / "bg" / name / f"{name}.{extension}")
    mod = tmp_path / "mod" / "field"
    (mod / "mapdata" / "bg" / "bghall_1").mkdir(parents=True)
    modded = JsmCardGameFile(str(vanilla / HALL), str(vanilla / HALL)[:-4] + ".sym")
    modded.players[0].params[PARAM_RARE_CHANCE].set_literal(99)
    modded.save(str(mod / HALL))
    return str(vanilla), str(mod)


@pytest.fixture
def cc(qapp, tmp_path, monkeypatch):
    from PyQt6.QtCore import QSettings
    from CCGroup.ccgroup import CCGroupWidget
    from Common.fileregistry import FileRegistry
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    widget = CCGroupWidget(settings=settings, file_registry=FileRegistry())
    yield widget
    widget.deleteLater()


def rare_chance(npc, map_name="bghall_1"):
    jsm_file = next(f for f in npc.manager.jsm_files if f.map_name == map_name)
    return jsm_file.players[0].params[PARAM_RARE_CHANCE]


@pytest.mark.parametrize("reference_first", [True, False])
def test_both_folders_in_any_order(cc, folders, reference_first):
    vanilla, mod = folders
    npc = cc.npc_card_game_widget
    steps = [lambda: cc.load_reference_folder(vanilla), lambda: cc.load_working_folder(mod)]
    for step in (steps if reference_first else steps[::-1]):
        step()
    assert (npc.reference_folder, npc.working_folder) == (vanilla, mod)
    assert rare_chance(npc).value == 99                         # the mod's own change is read
    assert {f.map_name for f in npc.manager.jsm_files} == set(MAPS)  # every map, from vanilla
    registry = cc.file_registry
    assert registry.get_path(cc.NPC_REGISTRY_NAME) == mod
    assert registry.get_path(cc.NPC_REFERENCE_REGISTRY_NAME) == vanilla

    registry.close_file(cc.NPC_REFERENCE_REGISTRY_NAME)        # removed from Opened files
    assert npc.reference_folder == "" and npc.working_folder == mod
    assert {f.map_name for f in npc.manager.jsm_files} == {"bghall_1"}  # the mod's maps only


def test_the_same_folder_cannot_be_both(cc, folders, monkeypatch):
    vanilla, _mod = folders
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda _parent, _title, text, *a: warnings.append(text))
    cc.load_working_folder(vanilla)
    cc.load_reference_folder(vanilla)
    npc = cc.npc_card_game_widget
    assert npc.reference_folder == "" and "already open as the folder you edit" in warnings[-1]


def test_vanilla_only_save_creates_the_mod_folder(cc, folders, tmp_path, monkeypatch):
    vanilla, _mod = folders
    npc = cc.npc_card_game_widget
    cc.load_reference_folder(vanilla)
    rare_chance(npc, "bgmon_4").set_literal(42)
    new_mod = tmp_path / "new" / "field"
    new_mod.mkdir(parents=True)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(new_mod))
    before = (pathlib.Path(vanilla) / "mapdata" / "bg" / "bgmon_4" / "bgmon_4.jsm").read_bytes()
    npc.save_folder()
    written = new_mod / "mapdata" / "bg" / "bgmon_4" / "bgmon_4.jsm"
    assert written.is_file() and not (new_mod / HALL).exists()   # only the map that differs
    assert (pathlib.Path(vanilla) / "mapdata" / "bg" / "bgmon_4" / "bgmon_4.jsm").read_bytes() == before
    assert npc.working_folder == str(new_mod)                     # kept open as the folder you edit
    assert cc.file_registry.get_path(cc.NPC_REGISTRY_NAME) == str(new_mod)
    assert rare_chance(npc, "bgmon_4").value == 42 and not npc.manager.has_modifications()


def test_vanilla_only_save_refuses_a_mod_folder_it_would_overwrite(cc, folders, monkeypatch):
    """The mod already has its own bghall_1: writing ours there would lose the mod's change."""
    vanilla, mod = folders
    npc = cc.npc_card_game_widget
    cc.load_reference_folder(vanilla)
    rare_chance(npc).set_literal(7)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda _parent, _title, text, *a: warnings.append(text))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: mod)
    before = (pathlib.Path(mod) / HALL).read_bytes()
    npc.save_folder()
    assert "already has its own version" in warnings[-1] and HALL in warnings[-1]
    assert (pathlib.Path(mod) / HALL).read_bytes() == before
    assert npc.working_folder == "" and npc.manager.has_modifications()  # edits kept, nothing written

    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: vanilla)
    npc.save_folder()
    assert "vanilla is never written to" in warnings[-1]


def test_a_mod_folder_alone_hints_at_the_vanilla_reference(cc, folders):
    from PyQt6.QtWidgets import QLabel
    _vanilla, mod = folders
    cc.load_working_folder(mod)
    texts = " ".join(label.text() for label in cc.npc_card_game_widget.findChildren(QLabel))
    assert "Only 1 map(s) here" in texts and "Save writes the edited maps in place" in texts


def test_auto_upload_reopens_both_folders(cc, folders):
    vanilla, mod = folders
    cc.load_reference_folder(vanilla)
    cc.load_working_folder(mod)
    cc.npc_card_game_widget.close_folder()
    sources = {source.key: source for source in cc.auto_import_sources()}
    assert set(sources) == {cc.EDITED_FOLDER_KEY, cc.REFERENCE_FOLDER_KEY}
    # The reference is checked as the whole game: 2 maps -> refused, reported by Auto-upload
    with pytest.raises(ValueError, match="looks like a mod's field folder"):
        sources[cc.REFERENCE_FOLDER_KEY].loader([])
    sources[cc.EDITED_FOLDER_KEY].loader([])
    assert cc.npc_card_game_widget.working_folder == os.path.normpath(mod)


def test_folders_remembered_by_the_former_open_folder_button_carry_over(qapp, tmp_path):
    from PyQt6.QtCore import QSettings
    from CCGroup.ccgroup import CCGroupWidget
    from Common.fileregistry import FileRegistry
    settings = QSettings(str(tmp_path / "old.ini"), QSettings.Format.IniFormat)
    settings.setValue("ccgroup/npc_last_folder", "C:/game/field")
    settings.setValue("ccgroup/npc_modified_folder", "C:/mods/Rework/field")
    registry = FileRegistry()
    widget = CCGroupWidget(settings=settings, file_registry=registry)
    assert registry.last_folder(widget.REFERENCE_FOLDER_KEY) == "C:/game/field"
    assert registry.last_folder(widget.EDITED_FOLDER_KEY) == "C:/mods/Rework/field"
    widget.deleteLater()
