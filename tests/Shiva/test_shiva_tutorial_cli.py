"""Smoke tests for the tutorial-demo commands of the shiva CLI (was the trepies CLI):
drive the tool exactly like the command line does and assert byte-exact round-trips.
"""
import pathlib
import shutil

import pytest

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MENU_DIR = PROJECT_ROOT / "extracted_files" / "menu"
MNGRP_REL = "extracted_files/menu/mngrp.bin"
MNGRPHD_REL = "extracted_files/menu/mngrphd.bin"

pytestmark = pytest.mark.ff8data(MNGRP_REL, MNGRPHD_REL)


def _run(argv) -> int:
    from Cli.shiva import ShivaCliTool
    tool = ShivaCliTool()
    args = tool.build_parser().parse_args(argv)
    return tool.execute(args)


@pytest.fixture()
def work_files(tmp_path):
    """Copies of the real files, so import commands can overwrite them."""
    work_mngrp = tmp_path / "mngrp.bin"
    work_mngrphd = tmp_path / "mngrphd.bin"
    shutil.copy(MENU_DIR / "mngrp.bin", work_mngrp)
    shutil.copy(MENU_DIR / "mngrphd.bin", work_mngrphd)
    return work_mngrp, work_mngrphd


def test_tutorial_list(capsys, work_files):
    work_mngrp, _ = work_files
    assert _run(["tutorial-list", "--input", str(work_mngrp)]) == 0
    out = capsys.readouterr().out
    assert "Junction demo" in out
    assert "Character switch demo" in out
    assert "Mock GFs raw 177" in out


def test_tutorial_script_roundtrip_byte_exact(tmp_path, work_files):
    work_mngrp, work_mngrphd = work_files
    original_mngrp = work_mngrp.read_bytes()
    original_mngrphd = work_mngrphd.read_bytes()
    script_txt = tmp_path / "script168.txt"
    assert _run(["export-tutorial-script", "--input", str(work_mngrp), "--slot", "168",
                 "--output", str(script_txt)]) == 0
    assert "SET_TEXT_X 192" in script_txt.read_text(encoding="utf8")
    assert _run(["import-tutorial-script", "--input", str(work_mngrp), "--slot", "168",
                 "--script", str(script_txt)]) == 0
    # Shiva keeps unowned sections raw and the tutorial slots round-trip, so the file is exact.
    assert work_mngrp.read_bytes() == original_mngrp
    assert work_mngrphd.read_bytes() == original_mngrphd


def test_tutorial_json_roundtrip_byte_exact(tmp_path, work_files):
    work_mngrp, work_mngrphd = work_files
    original_mngrp = work_mngrp.read_bytes()
    original_mngrphd = work_mngrphd.read_bytes()
    json_path = tmp_path / "demo.json"
    assert _run(["export-tutorial-json", "--input", str(work_mngrp), "--output", str(json_path)]) == 0
    assert _run(["import-tutorial-json", "--input", str(work_mngrp), "--json", str(json_path)]) == 0
    assert work_mngrp.read_bytes() == original_mngrp
    assert work_mngrphd.read_bytes() == original_mngrphd


def test_import_edited_tutorial_script(tmp_path, work_files):
    work_mngrp, work_mngrphd = work_files
    script_txt = tmp_path / "script174.txt"
    assert _run(["export-tutorial-script", "--input", str(work_mngrp), "--slot", "174",
                 "--output", str(script_txt)]) == 0
    lines = script_txt.read_text(encoding="utf8").splitlines()
    lines.insert(1, "WAIT 42")
    script_txt.write_text("\n".join(lines) + "\n", encoding="utf8")
    out_mngrp = tmp_path / "out_mngrp.bin"
    out_mngrphd = tmp_path / "out_mngrphd.bin"
    assert _run(["import-tutorial-script", "--input", str(work_mngrp), "--slot", "174",
                 "--script", str(script_txt), "--output", str(out_mngrp),
                 "--output-mngrphd", str(out_mngrphd)]) == 0

    from Cli.common import load_game_data
    from FF8GameData.menu.mngrp.mngrpmanager import MngrpManager
    from Shiva.ShivaTutorial.tutorialmanager import TutorialManager
    manager = MngrpManager(load_game_data())
    manager.load_file(str(out_mngrphd), str(out_mngrp))
    tutorial = TutorialManager.from_mngrp(manager.game_data, manager.mngrp)
    assert str(tutorial.scripts[174].ops[0]) == "WAIT 42"
