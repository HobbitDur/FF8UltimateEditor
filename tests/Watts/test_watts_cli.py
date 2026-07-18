"""Watts CLI tests - drive the tool exactly as the command line does."""
import pathlib
import shutil

import pytest

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
BATTLE_DIR = PROJECT_ROOT / "extracted_files" / "battle"
R0WIN = BATTLE_DIR / "r0win.dat"

R0WIN_MARK = "extracted_files/battle/r0win.dat"


def _run(argv) -> int:
    from Cli.watts import WattsCliTool
    tool = WattsCliTool()
    args = tool.build_parser().parse_args(argv)
    return tool.execute(args)


def test_registered_in_cli():
    from Cli.watts import WattsCliTool
    tool = WattsCliTool()
    assert tool.name == "watts"
    assert tool.build_parser() is not None


@pytest.mark.ff8data(R0WIN_MARK)
def test_info(capsys):
    assert _run(["info", "-i", str(R0WIN)]) == 0
    output = capsys.readouterr().out
    assert "fanfare-seq" in output
    assert "Rinoa" in output and "Kiros" in output


@pytest.mark.ff8data(R0WIN_MARK)
def test_show_seq(capsys):
    assert _run(["show-seq", "-i", str(R0WIN), "-c", "rinoa"]) == 0
    assert "anim" in capsys.readouterr().out.lower()


@pytest.mark.ff8data(R0WIN_MARK)
def test_camera(capsys):
    assert _run(["camera", "-i", str(R0WIN)]) == 0
    output = capsys.readouterr().out
    assert "3 sets" in output and "keyframes" in output
    assert _run(["camera", "-i", str(R0WIN), "-v"]) == 0
    assert "pos (" in capsys.readouterr().out


@pytest.mark.ff8data(R0WIN_MARK)
def test_export_import_round_trip(tmp_path):
    working_copy = tmp_path / "r0win.dat"
    shutil.copy(R0WIN, working_copy)
    exported = tmp_path / "rinoa_body.bin"
    assert _run(["export", "-i", str(working_copy), "-p", "rinoa-body",
                 "-o", str(exported)]) == 0
    assert exported.stat().st_size == 5016
    assert _run(["import", "-i", str(working_copy), "-p", "rinoa-body",
                 "-f", str(exported)]) == 0
    assert working_copy.read_bytes() == R0WIN.read_bytes()


@pytest.mark.ff8data(R0WIN_MARK)
def test_export_all(tmp_path):
    out_dir = tmp_path / "parts"
    assert _run(["export-all", "-i", str(R0WIN), "-o", str(out_dir)]) == 0
    assert (out_dir / "r0win_fanfare-seq.bin").exists()
    assert (out_dir / "r0win_kiros-body.bin").exists()
    assert not (out_dir / "r0win_edea-weapon.bin").exists()


@pytest.mark.ff8data(R0WIN_MARK, "extracted_files/battle/d4c009.dat")
def test_import_anim(tmp_path):
    working_copy = tmp_path / "r0win.dat"
    shutil.copy(R0WIN, working_copy)
    assert _run(["import-anim", "-i", str(working_copy), "-c", "rinoa", "-p", "body",
                 "-s", str(BATTLE_DIR / "d4c009.dat"), "-a", "2"]) == 0
    assert working_copy.read_bytes() != R0WIN.read_bytes()


@pytest.mark.ff8data(R0WIN_MARK, "extracted_files/battle/d3c007.dat")
def test_import_wrong_skeleton_fails(tmp_path):
    working_copy = tmp_path / "r0win.dat"
    shutil.copy(R0WIN, working_copy)
    exported = tmp_path / "quistis_body.bin"
    assert _run(["export", "-i", str(working_copy), "-p", "quistis-body",
                 "-o", str(exported)]) == 0
    assert _run(["import", "-i", str(working_copy), "-p", "rinoa-body",
                 "-f", str(exported)]) == 1
    assert working_copy.read_bytes() == R0WIN.read_bytes()  # refused import wrote nothing
