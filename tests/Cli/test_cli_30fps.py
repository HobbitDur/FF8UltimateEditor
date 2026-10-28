"""The unified CLI's 30 fps conversions: ifrit convert-fps (the per-tool ones are tested with their
tool: tests/Watts/test_watts30.py, tests/Alexander/test_alexander30.py, tests/Fujin/test_camera30_fujin.py)."""
import pathlib

import pytest

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
C0M001 = PROJECT_ROOT / "extracted_files" / "battle" / "c0m001.dat"


@pytest.mark.ff8data("extracted_files/battle/c0m001.dat")
def test_ifrit_convert_fps_writes_a_converted_copy(tmp_path, capsys):
    from Cli.ifrit_model import IfritModelCliTool
    from tests.dat30_verifier import read_frame_count_list
    tool = IfritModelCliTool()
    args = tool.build_parser().parse_args(["convert-fps", "-i", str(C0M001), "-o", str(tmp_path)])
    assert tool.execute(args) == 0
    out = capsys.readouterr().out
    assert "[ok] c0m001.dat" in out and "camera" in out
    before = read_frame_count_list(C0M001.read_bytes())
    assert read_frame_count_list((tmp_path / "c0m001.dat").read_bytes()) == [2 * n for n in before]


def test_every_30fps_command_is_registered():
    from Cli.alexander import AlexanderCliTool
    from Cli.fujin import FujinCliTool
    from Cli.ifrit_model import IfritModelCliTool
    from Cli.watts import WattsCliTool
    for tool, command in ((IfritModelCliTool(), "convert-fps"), (WattsCliTool(), "convert-30fps"),
                          (AlexanderCliTool(), "convert-30fps"), (FujinCliTool(), "camera-30fps")):
        assert command in tool.build_parser().format_help()
