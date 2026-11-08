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


def _ffnx_rebuild(vanilla: bytes, chunk_folder: pathlib.Path, name: str) -> bytes:
    """What FFNx loads (src/ff8/vram.cpp ff8_battle_open_and_read_file): each section from its chunk
    file when there is one, else from the loaded file, packed after a fresh 11-section header."""
    import struct
    from FF8GameData.dat.ffnxchunks import section_list
    section_bytes = []
    for number, section in enumerate(section_list(vanilla), 1):
        chunk = chunk_folder / f"{name}.chunk.{number}"
        section_bytes.append(chunk.read_bytes() if chunk.exists() else section)
    offset_list, position = [], (11 + 2) * 4
    for section in section_bytes:
        offset_list.append(position)
        position += len(section)
    return struct.pack("<13I", 11, *offset_list, position) + b"".join(section_bytes)


@pytest.mark.ff8data("extracted_files/battle/c0m001.dat")
def test_ifrit_convert_fps_ffnx_chunks_rebuild_the_converted_file(tmp_path, capsys):
    from Cli.ifrit_model import IfritModelCliTool
    tool = IfritModelCliTool()
    parser = tool.build_parser()
    assert tool.execute(parser.parse_args(["convert-fps", "-i", str(C0M001), "-o", str(tmp_path / "full")])) == 0
    assert tool.execute(parser.parse_args(["convert-fps", "-i", str(C0M001), "-o", str(tmp_path / "whole"),
                                           "--ffnx-chunks", str(tmp_path / "chunks")])) == 0
    assert "[chunks] c0m001.dat: section(s) 3, 6" in capsys.readouterr().out
    assert not (tmp_path / "whole" / "c0m001.dat").exists()
    assert sorted(p.name for p in (tmp_path / "chunks").iterdir())[0] == "c0m001.dat.chunk.3"
    full = (tmp_path / "full" / "c0m001.dat").read_bytes()
    assert _ffnx_rebuild(C0M001.read_bytes(), tmp_path / "chunks", "c0m001.dat") == full


def test_ffnx_chunks_only_for_the_monsters_ffnx_rebuilds():
    import struct
    from FF8GameData.dat.ffnxchunks import accepts_chunks
    eleven = struct.pack("<13I", 11, *([52] * 12))
    assert accepts_chunks("c0m143.dat", eleven) and accepts_chunks("C0M000.DAT", eleven)
    assert not accepts_chunks("c0m144.dat", eleven)       # extended monsters: FFNx's own loader
    assert not accepts_chunks("d0c000.dat", eleven)
    assert not accepts_chunks("c0m127.dat", struct.pack("<4I", 2, 16, 16, 16))


def test_every_30fps_command_is_registered():
    from Cli.alexander import AlexanderCliTool
    from Cli.fujin import FujinCliTool
    from Cli.ifrit_model import IfritModelCliTool
    from Cli.watts import WattsCliTool
    for tool, command in ((IfritModelCliTool(), "convert-fps"), (WattsCliTool(), "convert-30fps"),
                          (AlexanderCliTool(), "convert-30fps"), (FujinCliTool(), "camera-30fps")):
        assert command in tool.build_parser().format_help()
