"""The unified CLI's 30 fps conversions: ifrit convert-fps (the per-tool ones are tested with their
tool: tests/Watts/test_watts30.py, tests/Alexander/test_alexander30.py, tests/Fujin/test_camera30_fujin.py)."""
import pathlib

import pytest

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
BATTLE = PROJECT_ROOT / "extracted_files" / "battle"
C0M001 = BATTLE / "c0m001.dat"


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
    file when there is one, else from the loaded file, packed after a fresh header with the loaded
    file's section count (11 for a c0m, 7/10 for a dXc, 8/5 for a dXw)."""
    import struct
    from FF8GameData.dat.ffnxchunks import section_list
    section_bytes = []
    for number, section in enumerate(section_list(vanilla), 1):
        chunk = chunk_folder / f"{name}.chunk.{number}"
        section_bytes.append(chunk.read_bytes() if chunk.exists() else section)
    count = len(section_bytes)
    offset_list, position = [], (count + 2) * 4
    for section in section_bytes:
        offset_list.append(position)
        position += len(section)
    return struct.pack(f"<{count + 2}I", count, *offset_list, position) + b"".join(section_bytes)


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


@pytest.mark.ff8data("extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat",
                     "extracted_files/battle/d9c019.dat", "extracted_files/battle/d9w037.dat")
@pytest.mark.parametrize("family, sections", [
    (("d0c000.dat", "d0w000.dat"), {"d0c000.dat": "3, 5, 7", "d0w000.dat": "3, 4, 8"}),   # 8-section weapon
    (("d9c019.dat", "d9w037.dat"), {"d9c019.dat": "3, 5, 7", "d9w037.dat": "2"}),          # 5-section weapon
])
def test_ifrit_convert_fps_ffnx_chunks_for_a_character_and_its_weapon(tmp_path, capsys, family, sections):
    from Cli.ifrit_model import IfritModelCliTool
    tool = IfritModelCliTool()
    parser = tool.build_parser()
    source_list = [str(BATTLE / name) for name in family]
    assert tool.execute(parser.parse_args(["convert-fps", "-i", *source_list, "-o", str(tmp_path / "full")])) == 0
    assert tool.execute(parser.parse_args(["convert-fps", "-i", *source_list, "-o", str(tmp_path / "whole"),
                                           "--ffnx-chunks", str(tmp_path / "chunks")])) == 0
    out = capsys.readouterr().out
    assert "2 file(s) as chunks" in out and "0 kept whole" in out
    for name in family:
        assert f"[chunks] {name}: section(s) {sections[name]}" in out
        assert not (tmp_path / "whole" / name).exists()
        full = (tmp_path / "full" / name).read_bytes()
        assert full != (BATTLE / name).read_bytes()
        assert _ffnx_rebuild((BATTLE / name).read_bytes(), tmp_path / "chunks", name) == full


def test_ffnx_chunks_only_for_the_files_ffnx_rebuilds():
    import struct
    from FF8GameData.dat.ffnxchunks import accepts_chunks
    eleven = struct.pack("<13I", 11, *([52] * 12))
    assert accepts_chunks("c0m143.dat", eleven) and accepts_chunks("C0M000.DAT", eleven)
    assert not accepts_chunks("c0m144.dat", eleven)       # extended monsters: FFNx's own loader
    assert not accepts_chunks("c0m127.dat", struct.pack("<4I", 2, 16, 16, 16))
    seven = struct.pack("<9I", 7, *([36] * 8))
    five = struct.pack("<7I", 5, *([28] * 6))
    assert accepts_chunks("d0c000.dat", seven) and accepts_chunks("DAC022.DAT", seven)
    assert accepts_chunks("d9w037.dat", five) and accepts_chunks("d7c016.dat", struct.pack("<12I", 10, *([48] * 11)))
    assert not accepts_chunks("d0w007.dat", b"")                        # the empty weapon file
    assert not accepts_chunks("d0c000.dat", struct.pack("<9I", 7, *([40] * 8)))   # not packed after the header
    assert not accepts_chunks("d0c000.dat", struct.pack("<9I", 7, 36, 40, 38, 40, 40, 40, 40, 40))  # goes back
    assert not accepts_chunks("d0c000.dat", struct.pack("<19I", 17, *([76] * 18)))  # more than FFNx takes
    assert not accepts_chunks("r0win.dat", seven) and not accepts_chunks("d0def.tim", seven)


def test_ffnx_chunks_rebuild_matches_the_test_helper(tmp_path):
    import struct
    from FF8GameData.dat.ffnxchunks import rebuild
    loaded = struct.pack("<7I", 5, 28, 30, 30, 33, 34, 34) + b"ab" + b"cde" + b"f"
    (tmp_path / "d9w037.dat.chunk.2").write_bytes(b"XYZW")
    (tmp_path / "d9w037.dat.chunk.4").write_bytes(b"")
    expected = struct.pack("<7I", 5, 28, 30, 34, 37, 37, 37) + b"ab" + b"XYZW" + b"cde"
    assert rebuild(loaded, tmp_path, "d9w037.dat") == expected
    assert _ffnx_rebuild(loaded, tmp_path, "d9w037.dat") == expected


def test_every_30fps_command_is_registered():
    from Cli.alexander import AlexanderCliTool
    from Cli.fujin import FujinCliTool
    from Cli.ifrit_model import IfritModelCliTool
    from Cli.watts import WattsCliTool
    for tool, command in ((IfritModelCliTool(), "convert-fps"), (WattsCliTool(), "convert-30fps"),
                          (AlexanderCliTool(), "convert-30fps"), (FujinCliTool(), "camera-30fps")):
        assert command in tool.build_parser().format_help()
