"""Xu: the scan camera table (battle_scan_cameras.bin) model, row mapping and file format."""
import struct

import pytest

from Xu.xumanager import (XuManager, ScanCameraRow, FILE_SIZE, ROW_COUNT, VANILLA_ROW_COUNT,
                          DEFAULT_ROW, ALTERNATE_ROWS, row_for_c0m, c0m_for_row, com_id_for_row)


def test_vanilla_rows_match_the_exe_layout():
    manager = XuManager()
    assert len(manager.rows) == ROW_COUNT == 262
    assert len(manager.to_bytes()) == FILE_SIZE == 4192
    # G-Soldier (com_id 87), the generic framing
    assert manager.rows[87].values() == (-0x1200, 0x200, -0x280, 0x280, 1, 0, 1, 1, 1, 0)
    # Abadon's alternate form: the far camera the c0m146 G-Sldr. Medic got before FFNx moved it
    assert manager.rows[162].distance == -18496
    # Armadodo rolled up can't be turned
    assert (manager.rows[161].can_pitch, manager.rows[161].can_yaw) == (0, 0)
    # every new-monster row starts as a copy of G-Soldier
    assert all(manager.rows[row] == manager.rows[DEFAULT_ROW] for row in range(VANILLA_ROW_COUNT, ROW_COUNT))


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
    manager = XuManager()
    manager.set_field(168, "distance", -0x1300)
    manager.copy_row(87, 169)
    path = tmp_path / "battle_scan_cameras.bin"
    manager.save_file(str(path))
    data = path.read_bytes()
    assert len(data) == FILE_SIZE
    assert struct.unpack_from("<h", data, 168 * 16)[0] == -0x1300

    loaded = XuManager()
    loaded.load_file(str(path))
    assert loaded.to_bytes() == data
    assert not loaded.is_vanilla(168) and loaded.is_vanilla(87)

    (tmp_path / "short.bin").write_bytes(data[:-1])
    with pytest.raises(ValueError):
        loaded.load_file(str(tmp_path / "short.bin"))


def test_field_ranges():
    manager = XuManager()
    with pytest.raises(ValueError):
        manager.set_field(87, "distance", 0x8000)
    with pytest.raises(ValueError):
        manager.set_field(87, "can_yaw", 256)
    with pytest.raises(ValueError):
        manager.set_field(87, "nope", 1)
    manager.reset_to_vanilla()
    assert manager.rows[87] == ScanCameraRow()


def test_labels():
    manager = XuManager()
    assert manager.row_label(87) == "087  c0m071 G-Soldier"
    assert "Abadon" in manager.row_label(162)
    assert "not scannable" in manager.row_label(0)
    assert "no c0m file" in manager.row_label(230)


def test_scan_camera_geometry():
    """Scan screen = mode 1: aim offset sideways, eye straight in front at the row distance."""
    import numpy as np
    from Xu.xupreview import scan_camera
    row = ScanCameraRow()
    eye, target = scan_camera(row, (0., -900., 0.), yaw=0.)
    assert np.allclose(target, (512., -640., 0.))          # centre height dropped to the floor
    assert np.allclose(eye, (512., -640., -4608.))
    eye, target = scan_camera(row, (100., -900., 50.), yaw=0., zoom_in=True)
    assert np.allclose(target, (100., -640., 50.))         # no side offset while locking on
    assert np.allclose(eye - target, (0., -1728., -3456.))  # 3/4 of the distance, raised by half
    row.aim_at_model = 0
    eye, target = scan_camera(row, (100., -900., 50.), yaw=0.)
    assert np.allclose(target, (512., -640., 0.))          # aimed at the target position instead


def test_cli_new_set_copy_csv(tmp_path, capsys):
    from Cli.xu import XuCliTool
    tool = XuCliTool()
    path, csv_path, out = tmp_path / "s.bin", tmp_path / "s.csv", tmp_path / "s2.bin"

    def run(*argv):
        return tool.execute(tool.build_parser().parse_args([str(a) for a in argv]))

    assert run("new", "-o", path) == 0
    assert run("set", "-i", path, "--c0m", 146, "--distance", "-0x1300", "--can-yaw", 0) == 0
    assert run("copy", "-i", path, "--from-row", 162, "--to-c0m", 147) == 0
    assert run("set", "-i", path, "--row", 3, "--c0m", 3, "--distance", 1) == 1  # ambiguous selector
    manager = XuManager()
    manager.load_file(str(path))
    assert (manager.rows[168].distance, manager.rows[168].can_yaw) == (-0x1300, 0)
    assert manager.rows[169] == manager.rows[162]
    assert run("export-csv", "-i", path, "-o", csv_path) == 0
    assert run("import-csv", "-i", path, "-c", csv_path, "-o", out) == 0
    assert out.read_bytes() == path.read_bytes()
