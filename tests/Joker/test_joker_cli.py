"""Smoke tests for the joker CLI tool (Cli/joker.py), driven exactly like the
command line does it (build_parser().parse_args + execute) against the real
extracted game files, asserting byte-exact round-trips on all three SP2 sources.

Needs the real (copyright, gitignored) files under extracted_files/, so every
test is marked ff8data and skipped in CI.
"""
import pathlib
import shutil

import pytest

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
MENU_DIR = PROJECT_ROOT / "extracted_files" / "menu"


def _run(argv) -> int:
    from Cli.joker import JokerCliTool
    tool = JokerCliTool()
    args = tool.build_parser().parse_args(argv)
    return tool.execute(args)


@pytest.mark.ff8data("extracted_files/menu/face.sp2")
def test_joker_cli_face_json_roundtrip(tmp_path):
    source = MENU_DIR / "face.sp2"
    json_path = tmp_path / "face.json"
    out_path = tmp_path / "face_out.sp2"
    assert _run(["export-json", "--input", str(source), "--output", str(json_path)]) == 0
    assert _run(["import-json", "--input", str(source), "--json", str(json_path),
                 "--output", str(out_path)]) == 0
    assert out_path.read_bytes() == source.read_bytes()


@pytest.mark.ff8data("extracted_files/menu/cardanm.sp2")
def test_joker_cli_cardanm_json_roundtrip_and_set_quad(tmp_path):
    source = MENU_DIR / "cardanm.sp2"
    json_path = tmp_path / "cardanm.json"
    out_path = tmp_path / "cardanm_out.sp2"
    assert _run(["export-json", "--input", str(source), "--output", str(json_path)]) == 0
    assert _run(["import-json", "--input", str(source), "--json", str(json_path),
                 "--output", str(out_path)]) == 0
    assert out_path.read_bytes() == source.read_bytes()

    edited = tmp_path / "cardanm_edited.sp2"
    assert _run(["set-quad", "--input", str(source), "--sprite", "0", "--quad", "0",
                 "--field", "width", "--value", "48", "--output", str(edited)]) == 0
    from Joker.jokermanager import Sp2File
    assert Sp2File.from_bytes(edited.read_bytes()).sprites[0].quads[0].width == 48


@pytest.mark.ff8data("extracted_files/menu/mngrp.bin", "extracted_files/menu/mngrphd.bin")
def test_joker_cli_mngrp_json_roundtrip(tmp_path):
    work_mngrp = tmp_path / "mngrp.bin"
    work_mngrphd = tmp_path / "mngrphd.bin"
    shutil.copy(MENU_DIR / "mngrp.bin", work_mngrp)
    shutil.copy(MENU_DIR / "mngrphd.bin", work_mngrphd)
    json_path = tmp_path / "pos4.json"

    assert _run(["export-json", "--mngrp", str(work_mngrp), "--output", str(json_path)]) == 0
    # import back in place with no changes: both files must stay byte-identical
    assert _run(["import-json", "--mngrp", str(work_mngrp), "--json", str(json_path)]) == 0
    assert work_mngrp.read_bytes() == (MENU_DIR / "mngrp.bin").read_bytes()
    assert work_mngrphd.read_bytes() == (MENU_DIR / "mngrphd.bin").read_bytes()

    assert _run(["list", "--mngrp", str(work_mngrp)]) == 0
