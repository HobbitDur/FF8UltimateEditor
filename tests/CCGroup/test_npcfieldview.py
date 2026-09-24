"""Field view of the NPC tab: background rebuild, camera projection, NPC model/position lookup,
and the .sym script naming, on the real field files."""
import pathlib
import struct

import numpy as np
import pytest

from CCGroup.jsmcardgame import JsmCardGameFile
from FF8GameData.field.fieldbackground import render_field_folder, parse_map
from FF8GameData.field.fieldcamera import FieldCamera, Walkmesh

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
BGHALL = PROJECT_ROOT / "extracted_files" / "field" / "mapdata" / "bg" / "bghall_1"
BGMON = PROJECT_ROOT / "extracted_files" / "field" / "mapdata" / "bg" / "bgmon_4"
BGHOKE = PROJECT_ROOT / "extracted_files" / "field" / "mapdata" / "bg" / "bghoke_1"

pytestmark = pytest.mark.ff8data(*[f"extracted_files/field/mapdata/bg/{name}/{name}.{extension}"
                                   for name in ("bghall_1", "bgmon_4") for extension in ("mim", "map", "ca", "id")],
                                 "extracted_files/field/mapdata/bg/bgmon_4/bgmon_4.jsm",
                                 "extracted_files/field/mapdata/bg/bgmon_4/bgmon_4.sym",
                                 "extracted_files/field/mapdata/bg/bghoke_1/bghoke_1.jsm",
                                 "extracted_files/field/mapdata/bg/bghoke_1/bghoke_1.sym")


def test_background_is_rebuilt_from_the_tiles():
    image, origin = render_field_folder(str(BGHALL))
    assert image.size == (368, 368) and origin == (184, 184)
    pixels = np.asarray(image)
    assert (pixels[..., 3] == 255).mean() > 0.99  # the whole picture is covered
    assert len({tuple(pixel) for pixel in pixels[::8, ::8].reshape(-1, 4)}) > 200  # a real picture, not noise


def test_tile_depth_is_read_from_bits_7_8():
    tiles = parse_map((BGMON / "bgmon_4.map").read_bytes(), is_type2=False)
    assert {tile.depth for tile in tiles} <= {0, 1, 2}
    assert tiles[0].depth == 1  # tex 0x90: 8-bit tile


def test_walkmesh_projects_inside_the_background():
    image, origin = render_field_folder(str(BGHALL))
    camera = FieldCamera((BGHALL / "bghall_1.ca").read_bytes())
    walkmesh = Walkmesh((BGHALL / "bghall_1.id").read_bytes())
    points = [camera.project(vertex) for triangle in walkmesh.triangles for vertex in triangle]
    inside = [0 <= x + origin[0] < image.width and 0 <= y + origin[1] < image.height for x, y in points]
    assert sum(inside) / len(inside) > 0.8


def test_joker_model_and_position():
    jsm_file = JsmCardGameFile(str(BGMON / "bgmon_4.jsm"), str(BGMON / "bgmon_4.sym"))
    assert jsm_file.entity_model_index("joker") == 9  # p051 in bgmon_4's chara.one
    x, y, z, triangle = jsm_file.entity_position("joker")
    assert (x, y, z, triangle) == (3458, 389, 21, 112)
    walkmesh = Walkmesh((BGMON / "bgmon_4.id").read_bytes())
    assert walkmesh.height_at(triangle, x, y) == pytest.approx(21)


def test_sym_names_follow_the_entity_table():
    """The .sym name list at the top is one line short in bghoke_1: the scripts must still be
    named from the entity table (Kadowaki plays cards from her talk script, SETMODEL 9)."""
    jsm_file = JsmCardGameFile(str(BGHOKE / "bghoke_1.jsm"), str(BGHOKE / "bghoke_1.sym"))
    assert {(player.entity_name, player.script_name) for player in jsm_file.players} == {("kadowaki", "talk")}
    for script_index, name in enumerate(jsm_file.script_names):
        if name is not None and name[1] == "init":
            opcode_and_label = struct.unpack_from(
                "<I", jsm_file.data, jsm_file.offset_script + jsm_file.script_positions[script_index])[0]
            assert opcode_and_label == (0x05 << 24) | script_index  # LBL <script index>
    assert jsm_file.entity_model_index("kadowaki") == 9
