"""NPC tab with a modified field folder on top of the vanilla one (e.g. Cronos's FieldRework\\field):
reading, naming and saving only what differs from vanilla into the modified folder."""
import hashlib
import os
import pathlib
import shutil

import pytest

from CCGroup.jsmcardgame import CardGameFolderManager, JsmCardGameFile, PARAM_RARE_CHANCE

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
FIELD = PROJECT_ROOT / "extracted_files" / "field" / "mapdata" / "bg"
MAPS = ("bghall_1", "bgmon_4", "bgroad_7")

pytestmark = pytest.mark.ff8data(*[f"extracted_files/field/mapdata/bg/{name}/{name}.{extension}"
                                   for name in MAPS for extension in ("jsm", "sym")])


def tree_hashes(folder):
    return {path.relative_to(folder): hashlib.md5(path.read_bytes()).hexdigest()
            for path in pathlib.Path(folder).rglob("*") if path.is_file()}


@pytest.fixture
def folders(tmp_path):
    """vanilla/field/mapdata/bg/<3 maps> and modified/field holding a bghall_1 whose seito6
    rare chance is 99 instead of 80 (a mod change)."""
    vanilla = tmp_path / "vanilla" / "field"
    for name in MAPS:
        (vanilla / "mapdata" / "bg" / name).mkdir(parents=True)
        for extension in ("jsm", "sym"):
            shutil.copy(FIELD / name / f"{name}.{extension}", vanilla / "mapdata" / "bg" / name / f"{name}.{extension}")
    modified = tmp_path / "modified" / "field"
    (modified / "mapdata" / "bg" / "bghall_1").mkdir(parents=True)
    modded = JsmCardGameFile(str(vanilla / "mapdata" / "bg" / "bghall_1" / "bghall_1.jsm"),
                             str(vanilla / "mapdata" / "bg" / "bghall_1" / "bghall_1.sym"))
    modded.players[0].params[PARAM_RARE_CHANCE].set_literal(99)
    modded.save(str(modified / "mapdata" / "bg" / "bghall_1" / "bghall_1.jsm"))
    return vanilla, modified


def files_by_map(manager):
    return {jsm_file.map_name: jsm_file for jsm_file in manager.jsm_files}


def test_modified_maps_are_read_from_the_modified_folder(folders):
    vanilla, modified = folders
    manager = CardGameFolderManager()
    manager.load_folder(str(vanilla), str(modified))
    files = files_by_map(manager)
    assert manager.nb_from_modified_folder() == 1
    hall = files["bghall_1"]
    assert hall.modified_path and hall.players[0].params[PARAM_RARE_CHANCE].value == 99
    # No .sym next to the modded script: the vanilla one names it (same entity table)
    assert hall.names_from_sym and hall.players[0].entity_name == "seito6"
    assert not files["bgmon_4"].modified_path


def test_save_writes_only_differences_into_the_modified_folder(folders):
    vanilla, modified = folders
    vanilla_before = tree_hashes(vanilla)
    manager = CardGameFolderManager()
    manager.load_folder(str(vanilla), str(modified))
    files = files_by_map(manager)
    files["bgmon_4"].players[0].params[PARAM_RARE_CHANCE].set_literal(77)  # vanilla map edited
    road = files["bgroad_7"].players[0].params[PARAM_RARE_CHANCE]
    original = road.value
    road.set_literal(5)
    road.set_literal(original)  # edited back: identical to vanilla, nothing to write
    report = manager.save_all_report()

    assert [jsm_file.map_name for jsm_file in report.written] == ["bgmon_4"]
    assert not report.identical_to_vanilla
    assert tree_hashes(vanilla) == vanilla_before  # vanilla is never written
    written = modified / "mapdata" / "bg" / "bgmon_4" / "bgmon_4.jsm"
    assert written.is_file() and files["bgmon_4"].jsm_path == str(written)
    assert not (modified / "mapdata" / "bg" / "bgroad_7").exists()
    original_bytes = (vanilla / "mapdata" / "bg" / "bgmon_4" / "bgmon_4.jsm").read_bytes()
    diff = [index for index in range(len(original_bytes)) if written.read_bytes()[index] != original_bytes[index]]
    offset = files["bgmon_4"].players[0].params[PARAM_RARE_CHANCE].file_offset
    assert diff and all(offset <= index < offset + 3 for index in diff)


def test_modified_map_back_to_vanilla_can_be_deleted(folders):
    vanilla, modified = folders
    manager = CardGameFolderManager()
    manager.load_folder(str(vanilla), str(modified))
    hall = files_by_map(manager)["bghall_1"]
    hall.players[0].params[PARAM_RARE_CHANCE].set_literal(80)  # the vanilla value
    report = manager.save_all_report()
    assert not report.written and report.identical_to_vanilla == [hall]
    manager.delete_from_modified_folder(hall)
    assert not (modified / "mapdata" / "bg" / "bghall_1").exists()
    assert hall.jsm_path == hall.vanilla_path and not hall.modified_path


def test_mismatched_sym_is_not_used(folders):
    """A .sym that does not describe the script's entity table (here bghall_1's for bgmon_4) must
    not name its scripts: generic names instead of wrong ones."""
    vanilla, _ = folders
    jsm_file = JsmCardGameFile(str(vanilla / "mapdata" / "bg" / "bgmon_4" / "bgmon_4.jsm"),
                               str(vanilla / "mapdata" / "bg" / "bghall_1" / "bghall_1.sym"))
    assert not jsm_file.names_from_sym
    assert all(player.entity_name.startswith("entity") for player in jsm_file.players)
    # ... and a vanilla reference names it back by matching the scripts
    named = JsmCardGameFile(str(vanilla / "mapdata" / "bg" / "bgmon_4" / "bgmon_4.jsm"),
                            str(vanilla / "mapdata" / "bg" / "bghall_1" / "bghall_1.sym"),
                            name_reference=JsmCardGameFile(
                                str(vanilla / "mapdata" / "bg" / "bgmon_4" / "bgmon_4.jsm"),
                                str(vanilla / "mapdata" / "bg" / "bgmon_4" / "bgmon_4.sym")))
    assert [(player.entity_name, player.script_name) for player in named.players] == [("joker", "talk")] * 3
