"""Battle anim sets of the exe (FF8GameData/dat/exeanimset.py): FFNx effect_NNN.animset export,
validation (the same checks as FFNx), write back into the exe, 30 fps conversion, the Fujin CLI and
button."""
import struct
import sys
from pathlib import Path

import pytest

from FF8GameData.dat import exeanimset as ea
from FF8GameData.gamedata import GameData

ROOT = Path(__file__).resolve().parents[2]
EXE = "extracted_files/FF8_EN.exe"


@pytest.fixture(scope="module")
def exe():
    return (ROOT / EXE).read_bytes()


@pytest.fixture(scope="module")
def anim_sets(exe):
    return ea.read_exe_anim_sets(exe)


@pytest.fixture(scope="module")
def game_data():
    data = GameData(str(ROOT / "FF8GameData"))
    data.load_anim_sequence_data()
    return data


def test_table_names_every_set_once():
    names = [info.file_name for info in ea.ANIM_SETS]
    assert len(names) == 72 == len(set(names))
    assert ea.anim_set_file_name(188) == "effect_188.animset"
    assert ea.anim_set_file_name(339, 2) == "effect_339_2.animset"
    assert ea.info_from_file_name("some/dir/EFFECT_161_1.animset") is ea.anim_set_info(161, 1)
    assert ea.character_of_model_file("d2c006.dat") == "Irvine" and ea.character_of_model_file("c0m001.dat") is None
    assert {info.effect_id for info in ea.sets_of_character("Irvine")} == {188, 192, 193, 194, 195, 196, 197, 198}
    assert ea.anim_set_info(161, 1).character == ea.TARGET_MODEL


@pytest.mark.ff8data(EXE)
def test_every_set_is_found_and_round_trips(exe, anim_sets):
    located = ea.locate_anim_sets(exe)
    assert len(located) == 72
    for info, offset in located.items():
        block = exe[offset:offset + info.size]
        anim_set = anim_sets[info]
        assert anim_set.to_bytes() == block
        assert ea.build_sequence_section(anim_set.sequence_list()) == anim_set.sequences
        assert ea.anim_set_error(block, info.section_count) is None
    exported = dict(ea.export_files(exe))
    assert len(exported) == 72
    assert exported["effect_188.animset"] == exe[located[ea.anim_set_info(188)]:][:0x1570]


@pytest.mark.ff8data(EXE)
def test_copies_are_told_apart_by_their_order(exe):
    located = ea.locate_anim_sets(exe)
    blue_magic = sorted((info for info in located if info.fnv1a == 0xAB77A114), key=lambda i: i.en_address)
    assert len(blue_magic) == 16
    offsets = [located[info] for info in blue_magic]
    assert offsets == sorted(offsets) and len(set(offsets)) == 16


@pytest.mark.ff8data(EXE)
def test_the_validator_refuses_what_ffnx_refuses(anim_sets):
    good = anim_sets[ea.anim_set_info(188)].to_bytes()

    def changed(offset, fmt, value, data=good):
        data = bytearray(data)
        struct.pack_into(fmt, data, offset, value)
        return bytes(data)
    body, sequences, weapon = struct.unpack_from("<3I", good, 4)
    first_anim = struct.unpack_from("<I", good, body + 4)[0]
    bad = {
        "truncated": good[:len(good) // 2],
        "count": changed(0, "<I", 2),
        "first offset": changed(4, "<I", 24),
        "size": changed(16, "<I", len(good) + 4),
        "extra bytes": good + b"\0\0\0\0",
        "zero frames": changed(body + first_anim, "<B", 0),
        "animation offset": changed(body + 4, "<I", 0xFFFF),
        "sequence offset": changed(sequences + 2, "<H", 0x7FFF),
        "sequence count": changed(sequences, "<H", 0),
        "weapon offset": changed(weapon + 4, "<I", 2),
    }
    for name, data in bad.items():
        assert ea.anim_set_error(data, 3) is not None, name
    # an empty sequence (offset 0) is accepted, like in a .dat sequence section
    assert ea.anim_set_error(changed(sequences + 2, "<H", 0), 3) is None


def _same_but_slack_bits(rebuilt: bytes, original: bytes) -> bool:
    """The re-encode of a decoded animation section only zeroes the alignment slack bits at the end of
    each bit stream (never read by the engine): any other change means a wrong bone count."""
    return len(rebuilt) == len(original) and all(
        old == new or not (old ^ new) & new for old, new in zip(original, rebuilt))


@pytest.mark.ff8data(EXE)
def test_every_animation_decodes_on_its_bone_count(anim_sets):
    for info, anim_set in anim_sets.items():
        body = ea.parse_animation_section(anim_set.body, info.body_bones_of)
        assert _same_but_slack_bits(ea._pad4(body.to_binary()), anim_set.body), info.label
        if anim_set.weapon is not None:
            weapon = ea.parse_animation_section(anim_set.weapon, info.weapon_bones)
            assert _same_but_slack_bits(ea._pad4(weapon.to_binary()), anim_set.weapon), info.label
    # one wrong count is caught: Ward's 8 body animations do not decode on 2 bones
    ward = ea.anim_set_info(263)
    assert not _same_but_slack_bits(ea._pad4(ea.parse_animation_section(anim_sets[ward].body, 23).to_binary()),
                                    anim_sets[ward].body)


@pytest.mark.ff8data(EXE)
@pytest.mark.parametrize("effect_id, index", [(188, 0), (261, 0), (263, 0), (334, 1), (274, 0)])
def test_convert_to_real30(game_data, anim_sets, effect_id, index):
    info = ea.anim_set_info(effect_id, index)
    anim_set = anim_sets[info]
    before = anim_set.to_bytes()
    converted, report = ea.convert_to_real30(game_data, anim_set)
    assert anim_set.to_bytes() == before               # the source is left alone
    data = converted.to_bytes()
    assert ea.anim_set_error(data, info.section_count) is None and len(data) > len(before)
    frames_before = [len(a.frames) for a in ea.parse_animation_section(anim_set.body, info.body_bones_of).animations]
    frames_after = [len(a.frames) for a in ea.parse_animation_section(converted.body, info.body_bones_of).animations]
    assert all(n <= 255 for n in frames_after)
    split = {anim_id: new_ids for anim_id, _n, _parts, new_ids in report['split_list']}
    for anim_id, nb_frame in enumerate(frames_before):
        parts = [anim_id] + split.get(anim_id, [])
        assert sum(frames_after[part] for part in parts) == 2 * nb_frame
    if split:
        played = b"".join(converted.sequence_list())
        for anim_id, new_ids in split.items():
            assert bytes([anim_id] + new_ids) in played     # the sequence plays the parts in a row
    if converted.weapon is not None:
        weapon_after = ea.parse_animation_section(converted.weapon, info.weapon_bones).animations
        assert len(weapon_after) == len(ea.parse_animation_section(anim_set.weapon, info.weapon_bones).animations) \
            + sum(len(ids) for ids in split.values())


@pytest.mark.ff8data(EXE)
def test_patch_exe_only_when_it_fits(exe, anim_sets, game_data):
    info = ea.anim_set_info(196)
    copy = bytearray(exe)
    same = anim_sets[info].to_bytes()
    assert ea.patch_exe(copy, info, same) == ea.locate_anim_sets(exe)[info] and bytes(copy) == exe
    converted, _report = ea.convert_to_real30(game_data, anim_sets[info])
    with pytest.raises(ea.AnimSetError, match="effect_196.animset"):
        ea.patch_exe(copy, info, converted.to_bytes())
    assert bytes(copy) == exe


@pytest.mark.ff8data(EXE)
def test_cli_anim_sets(tmp_path, capsys, exe):
    from Cli.fujin import FujinCliTool
    tool = FujinCliTool()
    args = tool.build_parser().parse_args(["anim-sets", "--exe", str(ROOT / EXE), "-o", str(tmp_path / "vanilla")])
    assert tool.execute(args) == 0
    files = dict(ea.export_files(exe))
    assert sorted(p.name for p in (tmp_path / "vanilla").iterdir()) == sorted(files)
    assert (tmp_path / "vanilla" / "effect_274.animset").read_bytes() == files["effect_274.animset"]
    args = tool.build_parser().parse_args(["anim-sets", "--files", str(tmp_path / "vanilla" / "effect_261.animset"),
                                           "-o", str(tmp_path / "30"), "--fps", "30"])
    assert tool.execute(args) == 0
    assert "1 split" in capsys.readouterr().out
    data = (tmp_path / "30" / "effect_261.animset").read_bytes()
    assert ea.anim_set_error(data, 3) is None and len(data) > len(files["effect_261.animset"])


@pytest.mark.ff8data(EXE)
def test_fujin_export_button(tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication(sys.argv)
    from Fujin.fujinwidget import FujinWidget
    monkeypatch.setattr(QMessageBox, "information", lambda *args: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: pytest.fail(str(args[2])))
    fujin = FujinWidget()
    editor = fujin.camera_editor
    editor.exe_binding.open_path(str(ROOT / EXE))
    written = editor.export_anim_sets(convert=False, folder=str(tmp_path))
    assert len(written) == 72 and (tmp_path / "effect_339_2.animset").exists()
    assert app is not None
