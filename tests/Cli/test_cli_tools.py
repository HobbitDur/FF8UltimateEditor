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
def test_pupu_cargo_roundtrip(tmp_path):
    from Cli.pupu_cargo import PuPuCargoCliTool
    original, rebuilt = _roundtrip_csv(PuPuCargoCliTool, EXTRACTED / "menu" / "mitem.bin", tmp_path)
    assert original == rebuilt


@pytest.mark.ff8data("extracted_files/menu/mngrp.bin", "extracted_files/menu/mngrphd.bin")
def test_pandemona_roundtrip(tmp_path):
    from Cli.pandemona import PandemonaCliTool
    mngrp = tmp_path / "mngrp.bin"
    mngrphd = tmp_path / "mngrphd.bin"
    shutil.copy(EXTRACTED / "menu" / "mngrp.bin", mngrp)
    shutil.copy(EXTRACTED / "menu" / "mngrphd.bin", mngrphd)
    csv_path = tmp_path / "refine.csv"
    out = tmp_path / "mngrp_out.bin"
    out_hd = tmp_path / "mngrphd_out.bin"
    assert _run(PandemonaCliTool, ["export-csv", "--input", str(mngrp), "--output", str(csv_path)]) == 0
    assert _run(PandemonaCliTool, ["import-csv", "--input", str(mngrp), "--csv", str(csv_path),
                                   "--output", str(out), "--output-mngrphd", str(out_hd)]) == 0
    assert out.read_bytes() == mngrp.read_bytes()
    assert out_hd.read_bytes() == mngrphd.read_bytes()


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
    from Cli.ifrit_model import IfritModelCliTool
    dat = EXTRACTED / "battle" / "c0m001.dat"
    xml = tmp_path / "seq.xml"
    out = tmp_path / "c0m001.dat"
    assert _run(IfritModelCliTool, ["export-seq-xml", "--input", str(dat), "--output", str(xml)]) == 0
    assert _run(IfritModelCliTool, ["import-seq-xml", "--input", str(dat), "--xml", str(xml),
                                    "--output", str(out)]) == 0
    assert out.read_bytes() == dat.read_bytes()


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


def test_all_tools_registered():
    """cli.py must expose every Cli tool module."""
    import cli
    from Cli.registry import get_registry
    registry = get_registry()
    if not registry.list_tools():  # the registry is a process-wide singleton
        cli._register_all_tools()
    names = set(registry.list_tools())
    assert {"shumi-translator", "ifrit-ai", "ifrit", "jp-font-builder", "tonberry-shop", "siren",
            "junkshop", "quezacotl", "pupu-cargo", "pandemona", "ccgroup", "cid",
            "julia", "solomon-ring", "alexander", "seed"} <= names