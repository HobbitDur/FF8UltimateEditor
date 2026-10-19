"""Xu Scan screen graphics: the exe's effect models (backdrop, spinner, stat board/bars) and
their software rendering."""
import struct

import numpy as np
import pytest

from Xu.xubackground import (PrimModel, Canvas, TimTexture, ScanBackground, BarValues, background_from_exe,
                             bar_length, hud_matrix, BAR_COUNT, SECTIONS)

EXE = "extracted_files/FF8_EN.exe"
TEXTURE = "extracted_files/magic/mag039-067.tim"


def model_bytes(vertices, sections):
    """An Effect_RenderPrimModel model: {section name: [entry bytes]}."""
    data = bytearray(struct.pack("<II", 8 + 8 * len(vertices), len(vertices)))
    for x, y, z in vertices:
        data += struct.pack("<hhhh", x, y, z, 0)
    for name, size in SECTIONS:
        entries = sections.get(name, [])
        data += struct.pack("<I", len(entries))
        for entry in entries:
            assert len(entry) == size
            data += entry
    return bytes(data)


def rgb_code(r, g, b, code):
    return struct.pack("<BBBB", r, g, b, code)


def numbers(*vertex_numbers):
    """Vertex numbers as stored: x2 (4-byte units), padded to 8 bytes."""
    packed = struct.pack(f"<{len(vertex_numbers)}H", *(2 * n for n in vertex_numbers))
    return packed + bytes(8 - len(packed))


TRIANGLE = [(-10, -10, 0), (10, -10, 0), (0, 10, 0), (10, 10, 0)]


def test_parse_sections():
    g3 = rgb_code(255, 0, 0, 0x32) + numbers(0, 1, 2) + rgb_code(0, 255, 0, 0) + rgb_code(0, 0, 255, 0)
    f4 = rgb_code(1, 2, 3, 0x28) + numbers(0, 1, 2, 3)
    ft4 = (rgb_code(128, 128, 128, 0x2E) + numbers(0, 1, 2, 3) + struct.pack("<BBH", 47, 64, 0x3CD4)
           + struct.pack("<BBH", 47, 95, 0xBA) + struct.pack("<BBBB", 0, 64, 0, 95))
    ft3 = (rgb_code(9, 9, 9, 0x24) + struct.pack("<HHHBB", 0, 2, 4, 5, 6) + struct.pack("<BBH", 1, 2, 7)
           + struct.pack("<BBH", 3, 4, 8))
    model = PrimModel.from_bytes(model_bytes(TRIANGLE, {"G3": [g3], "F4": [f4], "FT4": [ft4], "FT3": [ft3]}))
    assert model.vertices.shape == (4, 3)
    by_kind = {prim.kind: prim for prim in model.prims}
    assert [prim.kind for prim in model.prims] == ["F4", "FT3", "FT4", "G3"]  # section order
    assert by_kind["G3"].indices == [0, 1, 2] and by_kind["G3"].colors == [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    assert by_kind["G3"].semi_transparent and not by_kind["F4"].semi_transparent
    assert by_kind["F4"].indices == [0, 1, 2, 3] and by_kind["F4"].colors == [(1, 2, 3)]
    assert by_kind["FT4"].uvs == [(47, 64), (47, 95), (0, 64), (0, 95)]
    assert by_kind["FT4"].clut == 0x3CD4 and by_kind["FT4"].tpage == 0xBA
    assert by_kind["FT3"].uvs == [(1, 2), (3, 4), (5, 6)]  # uv2 in the slot after the 3 numbers
    with pytest.raises(ValueError):
        PrimModel.from_bytes(model_bytes(TRIANGLE[:2], {"F4": [f4]}))  # vertex 2 and 3 missing


def test_bar_length():
    """StatBar_State0_Init: 16384 (4x) at the top value of each stat, capped above it."""
    assert bar_length("hp", 999) == bar_length("hp", 50000) == 16384
    assert bar_length("str", 127) == bar_length("str", 255) == 16384
    assert bar_length("eva", 25) == bar_length("eva", 99) == 16384
    assert bar_length("hp", 0) == 0 and 8100 < bar_length("hp", 500) < 8300


def test_hud_matrix():
    """RotZ * RotX * RotY then the per-axis scale: a 2048 Z turn sends +x to -x."""
    matrix = hud_matrix((0, 0, 2048), (8192, 4096, 4096))
    assert np.allclose(matrix @ np.array((1., 0., 0.)), (-2., 0., 0.))
    assert np.allclose(hud_matrix((0, 1024, 0)) @ np.array((0., 0., 1.)), (1., 0., 0.))


def test_canvas_blending():
    """Semi-transparent faces add up, opaque ones replace; fade 2048 halves the colour; at z 576
    one unit is one pixel around the screen centre."""
    flat = rgb_code(100, 0, 0, 0x22) + numbers(0, 1, 2)
    model = PrimModel.from_bytes(model_bytes(TRIANGLE, {"F3": [flat]}))
    canvas = Canvas(supersample=1)
    canvas.draw_model(model, (0, 0, 576), hud_matrix())
    canvas.draw_model(model, (0, 0, 576), hud_matrix(), fade=2048)
    assert tuple(canvas.rgb[120, 160].round()) == (150, 0, 0)
    assert canvas.rgb[120, 140].sum() == 0 and canvas.alpha[120, 160] == 1  # 20 px left: outside
    opaque = PrimModel.from_bytes(model_bytes(TRIANGLE, {"F3": [rgb_code(0, 50, 0, 0x20) + numbers(0, 1, 2)]}))
    canvas.draw_model(opaque, (0, 0, 576), hud_matrix())
    assert tuple(canvas.rgb[120, 160].round()) == (0, 50, 0)
    image = canvas.image(opaque=False)
    assert image.getpixel((160, 120))[3] == 255 and image.getpixel((10, 10))[3] == 0


def tim_bytes():
    """A 4x2 8-bit TIM at VRAM (640, 256) with a 16-colour CLUT at (320, 243)."""
    clut = [0] * 16
    clut[1] = 0x001F           # red, opaque
    clut[2] = 0x8000 | 0x03E0  # green, STP: blends
    clut_block = struct.pack("<IHHHH", 12 + 32, 320, 243, 16, 1) + struct.pack("<16H", *clut)
    pixels = bytes((1, 2, 0, 1, 1, 1, 1, 1))
    image_block = struct.pack("<IHHHH", 12 + len(pixels), 640, 256, 2, 2) + pixels
    return struct.pack("<II", 0x10, 0x09) + clut_block + image_block


def test_tim_texture_lookup():
    texture = TimTexture(tim_bytes())
    clut = (243 << 6) | (320 // 16)
    u, v = np.array([0, 1, 2, 9]), np.array([0, 0, 0, 0])
    rgb, drawn, blended = texture.lookup(u, v, 0xBA, clut)  # tpage x 640, y 256, 8 bit
    assert list(drawn) == [True, True, False, False]  # texel 0 transparent, u 9 outside
    assert list(blended) == [False, True, False, False]
    assert np.allclose(rgb[0], (255, 0, 0)) and np.allclose(rgb[1], (0, 255, 0))
    with pytest.raises(ValueError):
        TimTexture(b"\x00" * 16)


def fake_exe(game_data, language="english_value"):
    """An exe holding one small model at every Scan screen offset (shifted for its language)."""
    offsets = game_data.exe_data_json["scan_background_offset"]
    lang = game_data.exe_data_json["lang"]
    prefix = {"english_value": None, "french_value": "fr"}[language]
    shift = offsets[f"{prefix}_offset"] if prefix else 0
    model = model_bytes(TRIANGLE, {"F3": [rgb_code(10, 20, 30, 0x22) + numbers(0, 1, 2)]})
    keys = [key for key in offsets if key not in ("comment", "bar_layout") and not key.endswith("_offset")]
    exe = bytearray(max(offsets[key] for key in keys + ["bar_layout"]) + shift + len(model) + 0x1000)
    exe[lang["offset"]] = lang[language]
    for key in keys:
        exe[offsets[key] + shift:offsets[key] + shift + len(model)] = model
    # the backdrop sits at z 32767: big enough to cover pixels there
    big = model_bytes([(x * 300, y * 300, z) for x, y, z in TRIANGLE],
                      {"F3": [rgb_code(10, 20, 30, 0x22) + numbers(0, 1, 2)]})
    exe[offsets["backdrop"] + shift:offsets["backdrop"] + shift + len(big)] = big
    table = offsets["bar_layout"] + shift
    for i in range(BAR_COUNT):
        exe[table + 10 * i:table + 10 * i + 10] = struct.pack("<5h", -16 + i, 22, 2048 * (i % 2), i, 100 * i)
    return bytes(exe)


@pytest.fixture(scope="module")
def game_data():
    from FF8GameData.gamedata import GameData
    data = GameData("FF8GameData")
    data.load_exe_data()
    return data


@pytest.mark.parametrize("language", ["english_value", "french_value"])
def test_background_from_exe(game_data, language):
    data = background_from_exe(fake_exe(game_data, language), game_data.exe_data_json)
    assert len(data.bars) == BAR_COUNT and data.bar_layout[3] == (-13, 22, 2048, 3, 300)
    assert data.backdrop.prims[0].colors == [(10, 20, 30)]
    with pytest.raises(ValueError):
        background_from_exe(fake_exe(game_data)[:0x200000], game_data.exe_data_json)


def test_bars_appear_after_their_delay(game_data):
    """Bar i of the fake exe waits i + 1 ticks after tick 1, then grows 768 a tick."""
    background = ScanBackground(background_from_exe(fake_exe(game_data), game_data.exe_data_json), supersample=1)
    values = BarValues(hp=999, str=127, vit=127, mag=127, spr=127, spd=127, eva=25)
    early = np.asarray(background.hud(1, values))[..., 3].sum()
    late = np.asarray(background.hud(100, values))[..., 3].sum()
    assert late > early
    assert np.asarray(background.backdrop(0))[..., :3].sum() == 0  # the backdrop starts on tick 1
    assert np.asarray(background.backdrop(9))[..., :3].sum() > np.asarray(background.backdrop(5))[..., :3].sum()


def test_bar_values_from_dat_stats():
    from FF8GameData.dat.monsterstatcurve import monster_stat
    curve = [10, 20, 5, 4]
    stats = {name: curve for name in ("str", "vit", "mag", "spr", "spd", "eva")}
    values = BarValues.from_info_stat(stats, 30, 1234)
    assert values.hp == 1234 and values.eva == monster_stat("eva", curve, 30) and values.str == monster_stat("str", curve, 30)


@pytest.mark.ff8data(EXE, TEXTURE)
def test_real_scan_screen(game_data):
    """The vanilla models: the blue backdrop lights the left of the screen only, the board's
    labels come from the texture, the spinner sits at the board's centre."""
    with open(EXE, "rb") as file:
        data = background_from_exe(file.read(), game_data.exe_data_json)
    assert [len(model.prims) for model in (data.backdrop, data.spinner, data.board)] == [72, 28, 1]
    assert data.bar_layout[0] == (-16, -18, 0, 1, 0) and data.bar_layout[7][1:3] == (22, 2048)
    background = ScanBackground(data, TimTexture.from_file(TEXTURE), supersample=1)
    backdrop = np.asarray(background.backdrop())[..., :3].astype(int)
    assert backdrop[120, 80, 2] > 40 and backdrop[120, 80, 0] == 0  # blue on the left
    assert backdrop[120, 260].sum() == 0                            # black under the text
    with_texture = np.asarray(background.hud())[16:48, 72:120, 3].sum()
    without = np.asarray(ScanBackground(data, supersample=1).hud())[16:48, 72:120, 3].sum()
    assert with_texture > without
