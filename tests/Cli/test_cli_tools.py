"""Smoke tests for the unified CLI (cli.py + Cli/*).

Each tool is driven exactly like the command line does it (build_parser().parse_args
+ execute) against the real extracted game files, asserting the export→import
round-trip reproduces the input byte-for-byte where the underlying manager is
byte-exact.

Needs the real (copyright, gitignored) files under extracted_files/, so every
test is marked ff8data and skipped in CI.
"""
import pathlib
import shutil

import pytest

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
EXTRACTED = PROJECT_ROOT / "extracted_files"


def _run(tool_class, argv) -> int:
    tool = tool_class()
    args = tool.build_parser().parse_args(argv)
    return tool.execute(args)


def _roundtrip_csv(tool_class, source: pathlib.Path, tmp_path, extra_export=(), extra_import=()):
    """export-csv then import-csv onto a copy; return (original, rebuilt) bytes."""
    csv_path = tmp_path / "data.csv"
    out_path = tmp_path / ("out" + source.suffix)
    assert _run(tool_class, ["export-csv", "--input", str(source), "--output", str(csv_path),
                             *extra_export]) == 0
    assert _run(tool_class, ["import-csv", "--input", str(source), "--csv", str(csv_path),
                             "--output", str(out_path), *extra_import]) == 0
    return source.read_bytes(), out_path.read_bytes()


@pytest.mark.ff8data("extracted_files/menu/shop.bin")
def test_tonberry_shop_roundtrip(tmp_path):
    from Cli.tonberry_shop import TonberryShopCliTool
    original, rebuilt = _roundtrip_csv(TonberryShopCliTool, EXTRACTED / "menu" / "shop.bin", tmp_path)
    assert original == rebuilt


@pytest.mark.ff8data("extracted_files/menu/price.bin")
def test_siren_roundtrip_and_set(tmp_path):
    from Cli.siren import SirenCliTool
    source = EXTRACTED / "menu" / "price.bin"
    original, rebuilt = _roundtrip_csv(SirenCliTool, source, tmp_path)
    assert original == rebuilt

    edited = tmp_path / "edited.bin"
    assert _run(SirenCliTool, ["set-price", "--input", str(source), "--item-id", "1",
                               "--buy-price", "1230", "--output", str(edited)]) == 0
    assert edited.read_bytes()[4:6] == (123).to_bytes(2, "little")


@pytest.mark.ff8data("extracted_files/menu/mwepon.bin")
def test_junkshop_roundtrip(tmp_path):
    from Cli.junkshop import JunkshopCliTool
    original, rebuilt = _roundtrip_csv(JunkshopCliTool, EXTRACTED / "menu" / "mwepon.bin", tmp_path)
    assert original == rebuilt


@pytest.mark.ff8data("extracted_files/menu/mitem.bin")
def test_kadowaki_roundtrip(tmp_path):
    from Cli.kadowaki import KadowakiCliTool
    original, rebuilt = _roundtrip_csv(KadowakiCliTool, EXTRACTED / "menu" / "mitem.bin", tmp_path)
    assert original == rebuilt


@pytest.mark.ff8data("extracted_files/menu/icon.sp1", "extracted_files/menu/icon.TEX")
def test_minimog_list_set_add_and_png(capsys, tmp_path):
    from Cli.minimog import MinimogCliTool
    source = EXTRACTED / "menu" / "icon.sp1"

    assert _run(MinimogCliTool, ["list", "--input", str(source), "--icon-id", "1"]) == 0
    assert "Icon 1" in capsys.readouterr().out

    edited = tmp_path / "edited.sp1"
    assert _run(MinimogCliTool, ["set-quad", "--input", str(source), "--icon-id", "1",
                                 "--quad", "0", "--u", "42", "--output", str(edited)]) == 0
    # only icon 1's quad changed: restoring its U byte gives back the original file
    original = bytearray(source.read_bytes())
    rebuilt = bytearray(edited.read_bytes())
    assert rebuilt != original
    quad_offset = int.from_bytes(rebuilt[4 + 4 * 1:4 + 4 * 1 + 2], "little")
    assert rebuilt[quad_offset] == 42
    rebuilt[quad_offset] = original[quad_offset]
    assert rebuilt == original

    added = tmp_path / "added.sp1"
    assert _run(MinimogCliTool, ["add-quad", "--input", str(source), "--icon-id", "0",
                                 "--width", "16", "--height", "16", "--clut", "32",
                                 "--output", str(added)]) == 0
    assert len(added.read_bytes()) == len(original) + 8

    png = tmp_path / "icon1.png"
    assert _run(MinimogCliTool, ["export-png", "--input", str(source),
                                 "--tex", str(EXTRACTED / "menu" / "icon.TEX"),
                                 "--icon-id", "1", "--output", str(png)]) == 0
    assert png.stat().st_size > 0


@pytest.mark.ff8data("extracted_files/menu/icon.TEX")
def test_minimog_export_tex_png(tmp_path):
    """export-tex-png needs no icon.sp1 - it's a raw TexFile -> PNG conversion,
    and the same atlas must come out differently per chosen palette."""
    from Cli.minimog import MinimogCliTool
    from PIL import Image
    tex = EXTRACTED / "menu" / "icon.TEX"

    png0 = tmp_path / "tex_p0.png"
    png2 = tmp_path / "tex_p2.png"
    assert _run(MinimogCliTool, ["export-tex-png", "--tex", str(tex),
                                 "--palette", "0", "--output", str(png0)]) == 0
    assert _run(MinimogCliTool, ["export-tex-png", "--tex", str(tex),
                                 "--palette", "2", "--output", str(png2)]) == 0
    image0, image2 = Image.open(png0), Image.open(png2)
    assert image0.size == image2.size == (256, 256)
    assert image0.tobytes() != image2.tobytes(), \
        "different palettes over the same pixel data must render differently"

    assert _run(MinimogCliTool, ["export-tex-png", "--tex", str(tex),
                                 "--palette", "99", "--output", str(tmp_path / "bad.png")]) == 1


@pytest.mark.ff8data("extracted_files/menu/icon.sp1", "extracted_files/menu/icon.TEX")
def test_minimog_export_tex_true_colors(tmp_path):
    """export-tex-true-colors keeps icon.TEX's own layout/size (unlike export-png's
    grid-by-id sheet) but resolves each region through its own icon's CLUT - no
    palette to pick. Icon 15 ("Target") must come out red at its own UV rectangle."""
    from Cli.minimog import MinimogCliTool
    from PIL import Image
    from Minimog.minimogmanager import MinimogManager

    sp1 = EXTRACTED / "menu" / "icon.sp1"
    tex = EXTRACTED / "menu" / "icon.TEX"
    out = tmp_path / "true_colors.png"

    assert _run(MinimogCliTool, ["export-tex-true-colors", "--input", str(sp1),
                                 "--tex", str(tex), "--output", str(out)]) == 0

    manager = MinimogManager()
    manager.load_file(str(sp1))
    image = Image.open(out).convert("RGBA")
    assert image.size == (256, 256), "must match icon.TEX's native layout, not a grid of cells"

    quad = manager.icons[15].quads[0]
    r, g, b, a = image.getpixel((quad.u + 8, quad.v + 4))
    assert a != 0 and r > 120 and r > g + 30, "Target's own UV rectangle should be red"


@pytest.mark.ff8data("extracted_files/menu/mngrp.bin", "extracted_files/menu/mngrphd.bin")
def test_shiva_refine_roundtrip(tmp_path):
    from Cli.shiva import ShivaCliTool
    mngrp = tmp_path / "mngrp.bin"
    mngrphd = tmp_path / "mngrphd.bin"
    shutil.copy(EXTRACTED / "menu" / "mngrp.bin", mngrp)
    shutil.copy(EXTRACTED / "menu" / "mngrphd.bin", mngrphd)
    csv_path = tmp_path / "refine.csv"
    out = tmp_path / "mngrp_out.bin"
    out_hd = tmp_path / "mngrphd_out.bin"
    assert _run(ShivaCliTool, ["export-refine-csv", "--input", str(mngrp), "--output", str(csv_path)]) == 0
    assert _run(ShivaCliTool, ["import-refine-csv", "--input", str(mngrp), "--csv", str(csv_path),
                                   "--output", str(out), "--output-mngrphd", str(out_hd)]) == 0

    # Shiva writes the whole file through one model, so the sections it edits are re-encoded and
    # their bytes can move even with nothing changed. What must survive is the refine data, so
    # the check is that a second export gives back the very same CSV.
    csv_again = tmp_path / "refine_again.csv"
    assert _run(ShivaCliTool, ["export-refine-csv", "--input", str(out), "--mngrphd", str(out_hd),
                               "--output", str(csv_again)]) == 0
    assert csv_again.read_bytes() == csv_path.read_bytes()


@pytest.mark.ff8data("extracted_files/menu/mngrp.bin", "extracted_files/menu/mngrphd.bin")
def test_shiva_seed_roundtrip_and_set_answer(tmp_path):
    from Cli.shiva import ShivaCliTool
    mngrp = tmp_path / "mngrp.bin"
    mngrphd = tmp_path / "mngrphd.bin"
    shutil.copy(EXTRACTED / "menu" / "mngrp.bin", mngrp)
    shutil.copy(EXTRACTED / "menu" / "mngrphd.bin", mngrphd)
    csv_path = tmp_path / "seed.csv"
    out = tmp_path / "mngrp_out.bin"
    out_hd = tmp_path / "mngrphd_out.bin"
    assert _run(ShivaCliTool, ["export-seed-csv", "--input", str(mngrp), "--output", str(csv_path)]) == 0
    assert _run(ShivaCliTool, ["import-seed-csv", "--input", str(mngrp), "--csv", str(csv_path),
                               "--output", str(out), "--output-mngrphd", str(out_hd)]) == 0
    # Shiva goes through the shared model, so bytes can move; the SeeD data must round-trip.
    csv_again = tmp_path / "seed_again.csv"
    assert _run(ShivaCliTool, ["export-seed-csv", "--input", str(out), "--mngrphd", str(out_hd),
                               "--output", str(csv_again)]) == 0
    assert csv_again.read_bytes() == csv_path.read_bytes()

    assert _run(ShivaCliTool, ["set-seed-answer", "--input", str(mngrp), "--test", "5", "--question", "3",
                               "--answer", "1", "--output", str(out), "--output-mngrphd", str(out_hd)]) == 0
    from FF8GameData.gamedata import GameData
    from FF8GameData.menu.mngrp.mngrpmanager import MngrpManager
    from Shiva.ShivaSeedTest.seedtest import SeedTestSet
    game_data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    game_data.load_all()
    manager = MngrpManager(game_data)
    manager.load_file(str(out_hd), str(out))
    seed_tests = SeedTestSet.from_mngrp(game_data, manager.mngrp)
    assert seed_tests.test_list[4].strings[2].answer == 1
    # An out-of-range answer must be refused
    assert _run(ShivaCliTool, ["set-seed-answer", "--input", str(mngrp), "--test", "5", "--question", "3",
                               "--answer", "9", "--output", str(out), "--output-mngrphd", str(out_hd)]) == 1


@pytest.mark.ff8data("extracted_files/main/init.out")
def test_quezacotl_roundtrip(tmp_path):
    from Cli.quezacotl import QuezacotlCliTool
    source = EXTRACTED / "main" / "init.out"
    json_path = tmp_path / "init.json"
    out = tmp_path / "init_out.out"
    assert _run(QuezacotlCliTool, ["export-json", "--input", str(source), "--output", str(json_path)]) == 0
    assert _run(QuezacotlCliTool, ["import-json", "--input", str(source), "--json", str(json_path),
                                   "--output", str(out)]) == 0
    original = source.read_bytes()
    rebuilt = out.read_bytes()
    # The manager grows a vanilla file to 3200 bytes (all item slots editable);
    # the original prefix must be untouched and the growth all zeroes.
    assert rebuilt[:len(original)] == original
    assert all(byte == 0 for byte in rebuilt[len(original):])


@pytest.mark.ff8data("extracted_files/field/mapdata/bg/bghall_1/bghall_1.jsm",
                     "extracted_files/field/mapdata/bg/bghall_1/bghall_1.sym")
def test_ccgroup_roundtrip_and_set(tmp_path):
    from Cli.ccgroup import CCGroupCliTool
    folder = tmp_path / "field" / "bghall_1"
    folder.mkdir(parents=True)
    for name in ("bghall_1.jsm", "bghall_1.sym"):
        shutil.copy(EXTRACTED / "field" / "mapdata" / "bg" / "bghall_1" / name, folder / name)
    original = (folder / "bghall_1.jsm").read_bytes()

    csv_path = tmp_path / "players.csv"
    assert _run(CCGroupCliTool, ["export-csv", "--folder", str(tmp_path), "--output", str(csv_path)]) == 0
    assert _run(CCGroupCliTool, ["import-csv", "--folder", str(tmp_path), "--csv", str(csv_path)]) == 0
    assert (folder / "bghall_1.jsm").read_bytes() == original, "no-edit import must not rewrite"

    assert _run(CCGroupCliTool, ["set-param", "--jsm", str(folder / "bghall_1.jsm"),
                                 "--player", "0", "--param", "rare-chance", "--value", "42"]) == 0
    from CCGroup.jsmcardgame import JsmCardGameFile, PARAM_RARE_CHANCE
    reloaded = JsmCardGameFile(str(folder / "bghall_1.jsm"), str(folder / "bghall_1.sym"))
    assert reloaded.players[0].params[PARAM_RARE_CHANCE].value == 42


@pytest.mark.ff8data("extracted_files/FF8_EN.exe", "extracted_files/world/dat/wmset.obj")
def test_cid_roundtrip(tmp_path):
    from Cli.cid import CidCliTool
    exe = EXTRACTED / "FF8_EN.exe"
    wmset = EXTRACTED / "world" / "dat" / "wmset.obj"
    csv_path = tmp_path / "draws.csv"
    hext = tmp_path / "draw.hext"
    wmset_out = tmp_path / "wmset_out.obj"
    assert _run(CidCliTool, ["export-csv", "--exe", str(exe), "--wmset", str(wmset),
                                    "--output", str(csv_path)]) == 0
    assert _run(CidCliTool, ["import-csv", "--csv", str(csv_path), "--exe", str(exe),
                                    "--wmset", str(wmset), "--output-hext", str(hext),
                                    "--output-wmset", str(wmset_out)]) == 0
    assert wmset_out.read_bytes() == wmset.read_bytes()
    assert hext.read_text().startswith("#Offset to dynamic data")


@pytest.mark.ff8data("extracted_files/Sound/audio.fmt", "extracted_files/Sound/audio.dat")
def test_julia_export_wav(tmp_path):
    from Cli.julia import JuliaCliTool
    wav = tmp_path / "sound.wav"
    assert _run(JuliaCliTool, ["export-wav", "--fmt", str(EXTRACTED / "Sound" / "audio.fmt"),
                               "--index", "1", "--output", str(wav)]) == 0
    assert wav.read_bytes()[:4] == b"RIFF"


@pytest.mark.ff8data("extracted_files/main/kernel.bin")
def test_solomon_ring_get_set_and_csv(tmp_path):
    from Cli.solomon_ring import SolomonRingCliTool, _KernelFile
    kernel = EXTRACTED / "main" / "kernel.bin"
    csv_path = tmp_path / "magic.csv"
    out = tmp_path / "kernel_out.bin"
    assert _run(SolomonRingCliTool, ["export-csv", "--input", str(kernel), "--section", "2",
                                     "--output", str(csv_path)]) == 0
    assert _run(SolomonRingCliTool, ["import-csv", "--input", str(kernel), "--section", "2",
                                     "--csv", str(csv_path), "--output", str(out)]) == 0

    edited = tmp_path / "kernel_edit.bin"
    assert _run(SolomonRingCliTool, ["set", "--input", str(out), "--section", "2", "--entry", "1",
                                     "--field", "spell_power", "--value", "99",
                                     "--output", str(edited)]) == 0
    entry = _KernelFile(str(edited)).entries(2)[1]
    assert entry.get("spell_power") == 99
    assert entry.get_text(0) == "Fire"


@pytest.mark.ff8data("extracted_files/battle/c0m001.dat")
def test_ifrit_seq_xml_roundtrip(tmp_path):
    from Cli.ifrit_model import IfritModelCliTool, _load_enemy
    dat = EXTRACTED / "battle" / "c0m001.dat"
    xml = tmp_path / "seq.xml"
    out = tmp_path / "c0m001.dat"

    # Baseline = what a no-edit load + save produces. Writing a .dat is not
    # byte-identical to the source: the animation section is re-encoded from
    # its parsed bit-stream and the leftover high bits at the tail of each
    # animation (never read by the game, garbage in Square's files) are
    # zero-filled. tests/Ifrit/test_realfile_monster.py covers that property
    # on every monster; comparing against the baseline here isolates what the
    # seq XML round-trip itself changes -- which must be nothing at all.
    baseline = tmp_path / "baseline.dat"
    game_data, enemy = _load_enemy(str(dat))
    enemy.write_data_to_file(game_data, str(baseline))

    assert _run(IfritModelCliTool, ["export-seq-xml", "--input", str(dat), "--output", str(xml)]) == 0
    assert _run(IfritModelCliTool, ["import-seq-xml", "--input", str(dat), "--xml", str(xml),
                                    "--output", str(out)]) == 0
    assert out.read_bytes() == baseline.read_bytes()


@pytest.mark.ff8data("extracted_files/battle/c0m001.dat")
def test_ifrit_gltf_export_import(tmp_path):
    from Cli.ifrit_model import IfritModelCliTool
    dat = EXTRACTED / "battle" / "c0m001.dat"
    glb = tmp_path / "c0m001.glb"
    out = tmp_path / "c0m001_rebuilt.dat"
    assert _run(IfritModelCliTool, ["export-gltf", "--input", str(dat), "--output", str(glb)]) == 0
    assert glb.read_bytes()[:4] == b"glTF"
    assert _run(IfritModelCliTool, ["import-gltf", "--input", str(dat), "--glb", str(glb),
                                    "--output", str(out)]) == 0
    assert out.exists() and out.stat().st_size > 0


@pytest.mark.ff8data("extracted_files/battle/a0stg001.x")
def test_alexander_glb_export_import(tmp_path):
    from Cli.alexander import AlexanderCliTool
    stage = EXTRACTED / "battle" / "a0stg001.x"
    glb = tmp_path / "stage.glb"
    out = tmp_path / "stage_rebuilt.x"
    assert _run(AlexanderCliTool, ["export-glb", "--input", str(stage), "--output", str(glb)]) == 0
    assert glb.read_bytes()[:4] == b"glTF"
    assert _run(AlexanderCliTool, ["import-glb", "--input", str(stage), "--glb", str(glb),
                                   "--output", str(out)]) == 0
    assert out.exists() and out.stat().st_size > 0


@pytest.mark.ff8data("extracted_files/field/mapdata/bc/bccent12/chara.one")
def test_seed_list_models(capsys):
    from Cli.seed import SeedCliTool
    assert _run(SeedCliTool, ["list-models",
                              "--input", str(EXTRACTED / "field" / "mapdata" / "bc" / "bccent12" / "chara.one")]) == 0
    assert "models in" in capsys.readouterr().out


@pytest.mark.ff8data("extracted_files/menu/mtmag.bin")
def test_piet_show_and_set_range(capsys, tmp_path):
    from Cli.piet import PietCliTool
    source = EXTRACTED / "menu" / "mtmag.bin"
    assert _run(PietCliTool, ["show", "--input", str(source)]) == 0
    assert "Battle tutorial" in capsys.readouterr().out

    edited = tmp_path / "mtmag.bin"
    assert _run(PietCliTool, ["set-range", "--input", str(source), "--book", "1",
                              "--first", "51", "--last", "60", "--output", str(edited)]) == 0
    rebuilt = bytearray(source.read_bytes())
    rebuilt[4:6] = bytes([51, 60])
    assert edited.read_bytes() == bytes(rebuilt), "only book 1's range bytes may change"

    # Invalid ranges must be refused (first > last)
    assert _run(PietCliTool, ["set-range", "--input", str(source), "--book", "0",
                              "--first", "50", "--last", "43", "--output", str(tmp_path / "bad.bin")]) == 1


@pytest.mark.ff8data("extracted_files/menu/mmag2.bin")
def test_moomba_roundtrip_and_list(capsys, tmp_path):
    from Cli.moomba import MoombaCliTool
    source = EXTRACTED / "menu" / "mmag2.bin"
    json_path = tmp_path / "mmag2.json"
    out = tmp_path / "mmag2_out.bin"
    assert _run(MoombaCliTool, ["export-json", "--input", str(source), "--output", str(json_path)]) == 0
    assert _run(MoombaCliTool, ["import-json", "--input", str(source), "--json", str(json_path),
                                "--output", str(out)]) == 0
    assert out.read_bytes() == source.read_bytes()

    capsys.readouterr()
    assert _run(MoombaCliTool, ["list", "--input", str(source)]) == 0
    assert "Story slide" in capsys.readouterr().out


@pytest.mark.ff8data("extracted_files/menu/mmag.bin", "extracted_files/menu/mngrp.bin",
                     "extracted_files/menu/mngrphd.bin")
def test_zone_roundtrip_and_show(capsys, tmp_path):
    from Cli.zone import ZoneCliTool
    source = EXTRACTED / "menu" / "mmag.bin"
    original, rebuilt = _roundtrip_csv(ZoneCliTool, source, tmp_path)
    assert original == rebuilt

    capsys.readouterr()
    assert _run(ZoneCliTool, ["show", "--input", str(source), "--entry", "0",
                              "--mngrp", str(EXTRACTED / "menu" / "mngrp.bin")]) == 0
    out = capsys.readouterr().out
    assert "Weapons Monthly 1st Issue" in out  # magazine map + resolved text overlay
    assert "Lion Heart" in out  # weapon unlock resolved by name


def _shumi_csv_stable(argv_export_extra, source_files, tmp_path, import_extra=()):
    """export-csv -> import-csv -> export-csv again through the CLI; the two CSVs must
    match, proving the import path actually pushes the text back (regression guard for the
    set_text_from_id bug where import silently applied nothing / crashed)."""
    from Cli.shumi_translator import ShumiTranslatorCliTool
    primary = source_files[0]
    csv1 = tmp_path / "first.csv"
    csv2 = tmp_path / "second.csv"
    assert _run(ShumiTranslatorCliTool,
                ["export-csv", "-i", str(primary), "-o", str(csv1), *argv_export_extra]) == 0
    assert _run(ShumiTranslatorCliTool,
                ["import-csv", "-i", str(primary), "-c", str(csv1), "-o", str(primary),
                 *argv_export_extra, *import_extra]) == 0
    assert _run(ShumiTranslatorCliTool,
                ["export-csv", "-i", str(primary), "-o", str(csv2), *argv_export_extra]) == 0
    assert csv1.read_text(encoding="utf-8") == csv2.read_text(encoding="utf-8")


@pytest.mark.ff8data("extracted_files/main/kernel.bin")
def test_shumi_kernel_csv_roundtrip(tmp_path):
    work = tmp_path / "kernel.bin"
    shutil.copy(EXTRACTED / "main" / "kernel.bin", work)
    _shumi_csv_stable([], [work], tmp_path)


@pytest.mark.ff8data("extracted_files/main/namedic.bin")
def test_shumi_namedic_csv_roundtrip(tmp_path):
    work = tmp_path / "namedic.bin"
    shutil.copy(EXTRACTED / "main" / "namedic.bin", work)
    _shumi_csv_stable([], [work], tmp_path)


@pytest.mark.ff8data("extracted_files/menu/mngrp.bin", "extracted_files/menu/mngrphd.bin")
def test_shumi_mngrp_csv_roundtrip(tmp_path):
    work = tmp_path / "mngrp.bin"
    work_hd = tmp_path / "mngrphd.bin"
    shutil.copy(EXTRACTED / "menu" / "mngrp.bin", work)
    shutil.copy(EXTRACTED / "menu" / "mngrphd.bin", work_hd)
    _shumi_csv_stable(["--mngrphd", str(work_hd)], [work, work_hd], tmp_path)


@pytest.mark.ff8data("extracted_files/FF8_EN.exe")
def test_shumi_exe_import_runs(tmp_path):
    """The EXE importer writes .msd side files; assert export+import both succeed (the import
    exercises the same _apply_csv_to_sections path as the other types)."""
    from Cli.shumi_translator import ShumiTranslatorCliTool
    exe = EXTRACTED / "FF8_EN.exe"
    csv_path = tmp_path / "exe.csv"
    out_dir = tmp_path / "msd"
    assert _run(ShumiTranslatorCliTool, ["export-csv", "-i", str(exe), "-o", str(csv_path)]) == 0
    assert _run(ShumiTranslatorCliTool,
                ["import-csv", "-i", str(exe), "-c", str(csv_path), "--output-dir", str(out_dir)]) == 0
    assert list(out_dir.glob("*.msd")), "exe import produced no .msd files"


@pytest.mark.ff8data("extracted_files/menu/mmag.bin", "extracted_files/menu/mngrp.bin",
                     "extracted_files/menu/mngrphd.bin", "extracted_files/menu/sysfnt.TEX",
                     "extracted_files/menu/mwepon.bin", "extracted_files/main/kernel.bin")
def test_zone_export_png(tmp_path):
    from Cli.zone import ZoneCliTool
    source = EXTRACTED / "menu" / "mmag.bin"
    mngrp = EXTRACTED / "menu" / "mngrp.bin"
    extra = ["--kernel", str(EXTRACTED / "main" / "kernel.bin"),
             "--mwepon", str(EXTRACTED / "menu" / "mwepon.bin")]

    single = tmp_path / "page0.png"
    assert _run(ZoneCliTool, ["export-png", "--input", str(source), "--mngrp", str(mngrp),
                              "--entry", "0", "--output", str(single), "--scale", "2",
                              *extra]) == 0
    from PIL import Image
    with Image.open(single) as image:
        assert image.size == (768, 480)  # 384x240 canvas at --scale 2

    folder = tmp_path / "pages"
    assert _run(ZoneCliTool, ["export-png", "--input", str(source), "--mngrp", str(mngrp),
                              "--output", str(folder), *extra]) == 0
    assert len(list(folder.glob("mmag_*.png"))) == 69  # every entry rendered


@pytest.mark.ff8data("extracted_files/menu/mmag.bin", "extracted_files/menu/mngrp.bin",
                     "extracted_files/menu/mngrphd.bin")
def test_zone_export_png_warns_without_the_unlock_sources(capsys, tmp_path):
    """kernel.bin/mwepon.bin are optional, but their absence is said out loud."""
    from Cli.zone import ZoneCliTool
    capsys.readouterr()
    assert _run(ZoneCliTool, ["export-png", "--input", str(EXTRACTED / "menu" / "mmag.bin"),
                              "--mngrp", str(EXTRACTED / "menu" / "mngrp.bin"),
                              "--entry", "28", "--output", str(tmp_path / "ck.png")]) == 0
    out = capsys.readouterr().out
    assert "no --kernel" in out and "no --mwepon" in out


def test_all_tools_registered():
    """cli.py must expose every Cli tool module."""
    import cli
    from Cli.registry import get_registry
    registry = get_registry()
    if not registry.list_tools():  # the registry is a process-wide singleton
        cli._register_all_tools()
    names = set(registry.list_tools())
    assert {"shumi-translator", "ifrit-ai", "ifrit", "tonberry-shop", "siren",
            "junkshop", "quezacotl", "kadowaki", "minimog", "shiva", "ccgroup", "cid",
            "julia", "solomon-ring", "alexander", "seed", "piet", "moomba",
            "zone", "watts"} <= names