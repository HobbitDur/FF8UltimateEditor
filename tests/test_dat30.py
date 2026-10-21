"""Tests for the real 30 fps conversion of a battle .dat (FF8GameData/dat/dat30.py, wired into
IfritManager.convert_file_list_to_fps at 30 fps and Ifrit3D's "Convert ALL animations").

A converted file is played by FFNx True30FPS with the animation reader and the sequence VM on
every 30 Hz host frame: every animation must have exactly 2n frames, every sequence must be
rewritten (seqrewrite30), and a character body and its weapons must stay in lockstep.
"""
import pathlib
import shutil

import pytest

from FF8GameData.dat import dat30
from FF8GameData.dat.animsplitter import rewrite_sequence_list_for_split
from FF8GameData.dat.monsteranalyser import MonsterAnalyser
from FF8GameData.dat.seqrewrite30 import rewrite_sequence_dict
from FF8GameData.dat.sequencevm import entity_sequence_vm
from FF8GameData.monsterdata import AnimationSection
from Ifrit.ifritmanager import IfritManager
from tests.dat30_verifier import read_sequence_dict, read_frame_count_list, verify_sequence

PROJECT_ROOT = pathlib.Path(__file__).parent.parent
BATTLE_PATH = PROJECT_ROOT / "extracted_files" / "battle"
pytestmark = pytest.mark.skipif(not (BATTLE_PATH / "c0m001.dat").exists(),
                                reason="extracted battle files not available")


@pytest.fixture(scope="module")
def manager():
    return IfritManager(str(PROJECT_ROOT / "FF8GameData"))


@pytest.fixture(scope="module")
def vm(manager):
    return entity_sequence_vm(manager.game_data)


def _copy(tmp_path, *name_list):
    """Never convert the real extracted files: work on copies."""
    path_list = []
    for name in name_list:
        shutil.copy(BATTLE_PATH / name, tmp_path / name)
        path_list.append(str(tmp_path / name))
    return path_list


def _load(manager, path):
    monster = MonsterAnalyser(manager.game_data)
    monster.load_file_data(str(path), manager.game_data)
    monster.analyse_loaded_data(manager.game_data)
    return monster


def _verify_file(vm, original_path, converted_path, frames=None, anim_alias=None):
    """{seq id: problems} of every sequence of a converted file against the vanilla one."""
    original, converted = original_path.read_bytes(), pathlib.Path(converted_path).read_bytes()
    sequence_15, sequence_30 = read_sequence_dict(original), read_sequence_dict(converted)
    frame_15 = frames[0] if frames else read_frame_count_list(original)
    frame_30 = frames[1] if frames else read_frame_count_list(converted)
    problem = {}
    for seq_id, data in sequence_15.items():
        if data:
            problem_list = verify_sequence(vm, sequence_15, sequence_30, seq_id, frame_15, frame_30,
                                           anim_alias=anim_alias, drift_per_tick=1)
            if problem_list:
                problem[seq_id] = problem_list
    return problem


class TestSplitAndRewriteCompose:
    """The sequences are rewritten first, then a too-long animation is split (the splitter
    inserts the part ids). Both orders give the same bytes on the three vanilla animations
    that need a split, and the result plays like the original."""

    @pytest.mark.parametrize("name, anim_id", [("c0m091.dat", 27), ("c0m131.dat", 27),
                                               ("c0m114.dat", 32)])
    def test_the_two_orders_give_the_same_sequences(self, manager, vm, name, anim_id):
        data = (BATTLE_PATH / name).read_bytes()
        sequence = read_sequence_dict(data)
        new_id = len(read_frame_count_list(data))

        def as_section(by_id):
            return {'seq_animation_data': [{'id': k, 'data': bytearray(v)} for k, v in by_id.items()]}

        rewritten, _ = rewrite_sequence_dict(vm, sequence)            # rewrite, then split
        section = as_section(rewritten)
        rewrite_sequence_list_for_split(manager.game_data, section, anim_id, [new_id])
        rewrite_then_split = {s['id']: bytes(s['data']) for s in section['seq_animation_data']}

        section = as_section(sequence)                                # split, then rewrite
        rewrite_sequence_list_for_split(manager.game_data, section, anim_id, [new_id])
        split_then_rewrite, _ = rewrite_sequence_dict(
            vm, {s['id']: bytes(s['data']) for s in section['seq_animation_data']})
        assert rewrite_then_split == split_then_rewrite

    def test_the_split_and_rewritten_file_plays_like_the_original(self, manager, vm, tmp_path):
        path = _copy(tmp_path, "c0m091.dat")[0]   # Elvoret: animation 27 is 140 frames
        report = manager.convert_file_list_to_fps([path], 30)[0]
        assert report['error'] == "" and report['skipped_list'] == []
        anim_id, nb_frame, nb_part, new_id_list = report['split_list'][0]
        assert (anim_id, nb_frame, nb_part) == (27, 140, 2)
        frames = read_frame_count_list(pathlib.Path(path).read_bytes())
        assert frames[27] + frames[new_id_list[0]] == 280
        problem = _verify_file(vm, BATTLE_PATH / "c0m091.dat", path,
                               anim_alias={new_id: 27 for new_id in new_id_list})
        assert problem == {}


class TestMonster:

    def test_every_animation_gets_2n_frames_and_the_sequences_are_rewritten(self, manager, vm,
                                                                            tmp_path):
        path = _copy(tmp_path, "c0m000.dat")[0]
        report = manager.convert_file_list_to_fps([path], 30)[0]
        assert report['error'] == ""
        assert report['real30']
        before = read_frame_count_list((BATTLE_PATH / "c0m000.dat").read_bytes())
        after = read_frame_count_list(pathlib.Path(path).read_bytes())
        assert after == [2 * n for n in before]
        assert report['sequence_report'].count().get('rewritten')
        assert _verify_file(vm, BATTLE_PATH / "c0m000.dat", path) == {}

    def test_the_other_sections_are_untouched(self, manager, tmp_path):
        path = _copy(tmp_path, "c0m001.dat")[0]
        manager.convert_file_list_to_fps([path], 30)
        original, converted = _load(manager, BATTLE_PATH / "c0m001.dat"), _load(manager, path)
        for index in (1, 2, 4, 6, 7, 8, 9, 10, 11):   # skeleton ... textures, camera included
            assert bytes(converted.section_raw_data[index]) == bytes(original.section_raw_data[index]), index

    def test_the_slow_limit_no_longer_applies(self, manager, tmp_path):
        """c0m083 animation 20 (116 frames) is played by the idle: Slow-limited to 128 frames
        for an interpolation-only file, but on a converted model FFNx emulates Slow by a hold:
        only the byte limit counts, so it gets 232 frames, unsplit."""
        path = _copy(tmp_path, "c0m083.dat")[0]
        report = manager.convert_file_list_to_fps([path], 30)[0]
        assert report['skipped_list'] == [] and report['split_list'] == []
        assert read_frame_count_list(pathlib.Path(path).read_bytes())[20] == 232

    def test_a_single_pose_animation_gets_two_frames(self, manager):
        monster = _load(manager, BATTLE_PATH / "c0m001.dat")
        animation = monster.animation_data.animations[0]
        animation.frames = animation.frames[:1]
        dat30._double_animation(animation, monster.bone_data.bones, False, None)
        assert len(animation.frames) == 2

    def test_converting_twice_is_warned_not_blocked(self, manager, tmp_path):
        """Nothing in the file marks it as converted (FFNx expects every file converted): a
        second conversion is only warned about, by a heuristic, never refused."""
        path = _copy(tmp_path, "c0m001.dat")[0]
        first = manager.convert_file_list_to_fps([path], 30)[0]
        assert first['warning_list'] == []
        second = manager.convert_file_list_to_fps([path], 30)[0]
        assert any("already converted" in warning for warning in second['warning_list'])

    def test_no_vanilla_file_looks_converted(self, manager):
        for name in ("c0m001.dat", "c0m125.dat", "c0m091.dat", "d0c000.dat"):
            monster = _load(manager, BATTLE_PATH / name)
            from FF8GameData.dat.animloopdetector import analyse_animation_usage
            kind_dict = analyse_animation_usage(manager.game_data, monster)['kind_dict']
            assert not dat30.looks_already_converted(monster, kind_dict), name

    def test_the_offset_tables_stay_vanilla_shaped(self, manager, tmp_path):
        """No marker: the first animation / sequence starts right after its offset table."""
        path = _copy(tmp_path, "c0m001.dat")[0]
        manager.convert_file_list_to_fps([path], 30)
        converted = _load(manager, path)
        animation = bytes(converted.section_raw_data[3])
        nb = int.from_bytes(animation[:4], "little")
        assert int.from_bytes(animation[4:8], "little") == 4 + 4 * nb
        sequence = bytes(converted.section_raw_data[5])
        nb = int.from_bytes(sequence[:2], "little")
        offset_list = [int.from_bytes(sequence[2 + 2 * i:4 + 2 * i], "little") for i in range(nb)]
        assert min(o for o in offset_list if o) == 2 + 2 * nb


class TestCharacterFamily:

    def test_body_and_weapon_stay_in_lockstep(self, manager, vm, tmp_path):
        body, weapon = _copy(tmp_path, "d0c000.dat", "d0w000.dat")
        report_list = manager.convert_file_list_to_fps([body, weapon], 30)
        assert [r['error'] for r in report_list] == ["", ""]
        body_frames = read_frame_count_list(pathlib.Path(body).read_bytes())
        assert body_frames == read_frame_count_list(pathlib.Path(weapon).read_bytes())
        vanilla = read_frame_count_list((BATTLE_PATH / "d0c000.dat").read_bytes())
        assert body_frames == [2 * n for n in vanilla]
        # only the weapon carries the sequences
        assert report_list[0]['sequence_report'] is None
        assert report_list[1]['sequence_report'] is not None
        assert _verify_file(vm, BATTLE_PATH / "d0w000.dat", weapon) == {}

    def test_the_battle_entry_blocks_are_doubled(self, manager, tmp_path):
        body, weapon = _copy(tmp_path, "d0c000.dat", "d0w000.dat")
        manager.convert_file_list_to_fps([body, weapon], 30)
        for path, index in ((body, 7), (weapon, 8)):
            monster = _load(manager, path)
            section = AnimationSection()
            section.analyze(bytes(monster.section_raw_data[index]), monster.bone_data)
            assert [len(a.frames) for a in section.animations] == [80], path   # 40 -> 80

    def test_a_reduced_weapon_is_converted_with_its_body(self, manager, vm, tmp_path):
        """Zell's d1w (no animation section) carries the pair's sequences."""
        body, weapon = _copy(tmp_path, "d1c003.dat", "d1w008.dat")
        report_list = manager.convert_file_list_to_fps([body, weapon], 30)
        assert [r['error'] for r in report_list] == ["", ""]
        frames = read_frame_count_list((BATTLE_PATH / "d1c003.dat").read_bytes())
        assert _verify_file(vm, BATTLE_PATH / "d1w008.dat", weapon,
                            frames=(frames, [2 * n for n in frames])) == {}

    def test_a_refused_member_leaves_the_whole_family_untouched(self, manager, tmp_path,
                                                                monkeypatch):
        body, weapon = _copy(tmp_path, "d0c000.dat", "d0w000.dat")
        before = {path: pathlib.Path(path).read_bytes() for path in (body, weapon)}
        original = manager.convert_loaded_monster_to_real30

        def refuse_the_weapon(monster, *args, **kwargs):
            if monster.origin_path.endswith("d0w000.dat"):
                return "refused for the test"
            return original(monster, *args, **kwargs)

        monkeypatch.setattr(manager, "convert_loaded_monster_to_real30", refuse_the_weapon)
        report_list = manager.convert_file_list_to_fps([body, weapon], 30)
        assert all(report['error'] for report in report_list)
        for path, data in before.items():
            assert pathlib.Path(path).read_bytes() == data, "the family must stay untouched"

    def test_an_empty_placeholder_does_not_block_its_family(self, manager, tmp_path):
        """d0w007.dat is Squall's unused, empty weapon slot."""
        body, weapon, placeholder = _copy(tmp_path, "d0c000.dat", "d0w000.dat", "d0w007.dat")
        report_list = manager.convert_file_list_to_fps([body, weapon, placeholder], 30)
        assert report_list[0]['error'] == "" and report_list[1]['error'] == ""
        assert report_list[2]['error']
        assert pathlib.Path(body).read_bytes() != (BATTLE_PATH / "d0c000.dat").read_bytes()


class TestIfrit3DMenu:
    """The Ifrit3D 'Convert ALL animations' entry at 30 fps runs the same conversion on the
    open file (a monster), and sends a character to the batch conversion."""

    @pytest.fixture
    def viewer(self, monkeypatch):
        from PyQt6.QtWidgets import QMessageBox
        from Ifrit.Ifrit3D.ifrit3dwidget import Ifrit3DWidget
        message_list = []
        for name in ("information", "warning"):
            monkeypatch.setattr(QMessageBox, name,
                                staticmethod(lambda *a, **k: message_list.append(a[2])))

        def build(name):
            manager = IfritManager(str(PROJECT_ROOT / "FF8GameData"))
            path = str(BATTLE_PATH / name)
            enemy = manager.parse_file(path)
            manager.set_active_enemy(enemy, path, textures=([], True))
            widget = Ifrit3DWidget(manager, show_controls=False)
            return widget, manager, message_list
        return build

    def test_a_monster_is_converted_in_memory(self, viewer):
        widget, manager, message_list = viewer("c0m001.dat")
        before = [len(a.frames) for a in manager.enemy.animation_data.animations]
        widget._convert_loaded_file_to_real30("All to 30/60 FPS", None)
        after = [len(a.frames) for a in manager.enemy.animation_data.animations]
        assert after == [2 * n for n in before]
        assert "Sequences:" in message_list[-1]

    def test_a_character_is_sent_to_the_batch(self, viewer):
        widget, manager, message_list = viewer("d0w000.dat")
        before = [len(a.frames) for a in manager.enemy.animation_data.animations]
        widget._convert_loaded_file_to_real30("All to 30/60 FPS", None)
        assert [len(a.frames) for a in manager.enemy.animation_data.animations] == before
        assert "converted together" in message_list[-1]
