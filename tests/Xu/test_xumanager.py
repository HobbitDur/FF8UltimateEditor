"""Xu: the scan camera table (battle_scan_cameras.bin) model, row mapping and file format."""
import struct

import pytest

from Xu.xumanager import (XuManager, ScanCameraRow, FILE_SIZE, ROW_COUNT, VANILLA_ROW_COUNT,
                          DEFAULT_ROW, ALTERNATE_ROWS, row_for_c0m, c0m_for_row, com_id_for_row,
                          read_rows_from_exe)

EXE = "extracted_files/FF8_EN.exe"
G_SOLDIER = (-0x1200, 0x200, -0x280, 0x280, 1, 0, 1, 1, 1, 0)


def synthetic_bin() -> bytes:
    """262 distinct rows: row r has distance -r and everything else from G-Soldier."""
    return b"".join(ScanCameraRow(-row, *G_SOLDIER[1:]).to_bytes() for row in range(ROW_COUNT))


@pytest.fixture(scope="module")
def exe_data_json():
    from FF8GameData.gamedata import GameData
    game_data = GameData("FF8GameData")
    game_data.load_exe_data()
    return game_data.exe_data_json


@pytest.mark.ff8data(EXE)
def test_vanilla_rows_come_from_the_exe(exe_data_json):
    with open(EXE, "rb") as file:
        rows = read_rows_from_exe(file.read(), exe_data_json)
    assert len(rows) == ROW_COUNT == 262
    assert rows[87].values() == G_SOLDIER            # G-Soldier, the generic framing
    assert rows[162].distance == -18496             # Abadon's alternate form (what c0m146 got before FFNx)
    assert (rows[161].can_pitch, rows[161].can_yaw) == (0, 0)  # Armadodo rolled up can't be turned
    # FFNx gives every new-monster row G-Soldier's framing
    assert all(rows[row] == rows[DEFAULT_ROW] for row in range(VANILLA_ROW_COUNT, ROW_COUNT))


@pytest.mark.ff8data(EXE)
def test_bin_compared_with_the_exe(exe_data_json, tmp_path):
    manager = XuManager()
    manager.load_exe(EXE, exe_data_json)
    assert manager.loaded and manager.changed_rows() == []  # starts from the vanilla rows
    manager.set_field(168, "distance", -0x1300)
    path = tmp_path / "battle_scan_cameras.bin"
    manager.save_file(str(path))
    other = XuManager()
    other.load_file(str(path))
    other.load_exe(EXE, exe_data_json)   # opened after the file: it only becomes the reference
    assert other.rows[168].distance == -0x1300 and other.changed_rows() == [168]
    other.rows[168] = other.reference_row(168)
    assert other.changed_rows() == []


def test_unknown_exe_language(exe_data_json):
    with pytest.raises(ValueError):
        read_rows_from_exe(bytes(0x200), exe_data_json)


def test_row_mapping():
    assert row_for_c0m(0) == 16 and row_for_c0m(143) == 159
    assert row_for_c0m(144) == 166 and row_for_c0m(146) == 168 and row_for_c0m(199) == 221
    assert c0m_for_row(87) == 71 and c0m_for_row(168) == 146
    assert c0m_for_row(162) == ALTERNATE_ROWS[162][0] == 103
    assert c0m_for_row(3) is None
    assert com_id_for_row(168) == 162 and com_id_for_row(162) is None and com_id_for_row(87) == 87
    with pytest.raises(ValueError):
        row_for_c0m(240)


def test_round_trip_and_size_check(tmp_path):
    data = synthetic_bin()
    manager = XuManager()
    assert not manager.loaded and manager.reference is None
    manager.load_bytes(data)
    assert manager.to_bytes() == data and manager.changed_rows() == []  # no exe: compared with the file
    manager.set_field(168, "distance", -0x1300)
    manager.copy_row(87, 169)
    assert manager.changed_rows() == [168, 169]
    path = tmp_path / "battle_scan_cameras.bin"
    manager.save_file(str(path))
    saved = path.read_bytes()
    assert len(saved) == FILE_SIZE == 4192
    assert struct.unpack_from("<h", saved, 168 * 16)[0] == -0x1300

    (tmp_path / "short.bin").write_bytes(saved[:-1])
    with pytest.raises(ValueError):
        manager.load_file(str(tmp_path / "short.bin"))
    with pytest.raises(ValueError):
        XuManager().save_file(str(tmp_path / "empty.bin"))  # nothing loaded, nothing invented


def test_field_ranges():
    manager = XuManager()
    manager.load_bytes(synthetic_bin())
    with pytest.raises(ValueError):
        manager.set_field(87, "distance", 0x8000)
    with pytest.raises(ValueError):
        manager.set_field(87, "can_yaw", 256)
    with pytest.raises(ValueError):
        manager.set_field(87, "nope", 1)


def test_labels():
    manager = XuManager()
    assert manager.row_label(87) == "087  c0m071 G-Soldier"
    assert "Abadon" in manager.row_label(162)
    assert manager.row_label(0) == "000  d0c Squall"  # characters are scannable too
    assert "no c0m file" in manager.row_label(230)


def test_scan_camera_geometry():
    """Scan screen = mode 1: aim offset sideways, eye straight in front at the row distance."""
    import numpy as np
    from Xu.xupreview import scan_camera
    row = ScanCameraRow(*G_SOLDIER)
    eye, target = scan_camera(row, (0., -900., 0.), yaw=0.)
    assert np.allclose(target, (512., -640., 0.))          # centre height dropped to the floor
    assert np.allclose(eye, (512., -640., -4608.))
    eye, target = scan_camera(row, (100., -900., 50.), yaw=0., zoom_in=True)
    assert np.allclose(target, (100., -640., 50.))         # no side offset while locking on
    assert np.allclose(eye - target, (0., -1728., -3456.))  # 3/4 of the distance, raised by half
    row.aim_at_model = 0
    eye, target = scan_camera(row, (100., -900., 50.), yaw=0.)
    assert np.allclose(target, (512., -640., 0.))          # aimed at the target position instead


@pytest.mark.ff8data(EXE)
def test_cli_new_set_copy_csv(tmp_path):
    from Cli.xu import XuCliTool
    tool = XuCliTool()
    path, csv_path, out = tmp_path / "s.bin", tmp_path / "s.csv", tmp_path / "s2.bin"

    def run(*argv):
        return tool.execute(tool.build_parser().parse_args([str(a) for a in argv]))

    assert run("new", "--exe", EXE, "-o", path) == 0
    assert run("set", "-i", path, "--c0m", 146, "--distance", "-0x1300", "--can-yaw", 0) == 0
    assert run("copy", "-i", path, "--from-row", 162, "--to-c0m", 147) == 0
    assert run("set", "-i", path, "--row", 3, "--c0m", 3, "--distance", 1) == 1  # ambiguous selector
    assert run("list", "-i", path, "--changed") == 1  # --changed needs the exe
    assert run("list", "-i", path, "--exe", EXE, "--changed") == 0
    manager = XuManager()
    manager.load_file(str(path))
    assert (manager.rows[168].distance, manager.rows[168].can_yaw) == (-0x1300, 0)
    assert manager.rows[169] == manager.rows[162]
    assert run("export-csv", "-i", path, "-o", csv_path) == 0
    assert run("import-csv", "-i", path, "-c", csv_path, "-o", out) == 0
    assert out.read_bytes() == path.read_bytes()


def test_viewer_pose_turns_around_the_pivot():
    """Scan screen pose (MAG_040_SCAN_Viewer_Update): R = RotY(turn) * RotX(tilt) * zoom, and
    the point model_offset_y above the origin stays put whatever the turn, tilt and zoom."""
    import sys
    import numpy as np
    from PyQt6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)
    from Xu.xupreview import XuPreviewPanel
    panel = XuPreviewPanel()
    panel._row = ScanCameraRow(*G_SOLDIER)
    panel._spin, panel._tilt, panel._zoom = 700, 300, 6000
    linear, position = panel.viewer_transform()
    pivot = np.array((0., -G_SOLDIER[3], 0.))  # model_offset_y up (negative = up)
    assert np.allclose(linear @ pivot + position, pivot)
    assert np.isclose(abs(np.linalg.det(linear)), (6000 / 4096) ** 3)
    panel._idle_ticks = 75
    panel.turn_check.setChecked(True)
    for _ in range(75):
        panel._advance()
    assert (panel._spin, panel._tilt, panel._zoom) == (0, 0, 4096)  # the game's 5 s reset
