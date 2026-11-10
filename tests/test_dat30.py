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
from FF8GameData.dat.seqframeratio import end_frame_ratio_movements
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
    # A way back the conversion makes reach its end (seqframeratio) is compared with the same
    # way back ending in vanilla: everything else must still match the original exactly.
    reference = {'seq_animation_data': [{'id': seq_id, 'data': bytearray(data)}
                                        for seq_id, data in sequence_15.items()]}
    end_frame_ratio_movements(vm, reference, lambda anim_id: frame_15[anim_id] if anim_id < len(frame_15) else 0)
    sequence_15 = {sequence['id']: bytes(sequence['data']) for sequence in reference['seq_animation_data']}
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
        for index in (1, 2, 4, 7, 8, 9, 10, 11):   # skeleton ... textures (not the camera)
            assert bytes(converted.section_raw_data[index]) == bytes(original.section_raw_data[index]), index

    def test_the_camera_durations_double(self, manager, tmp_path):
        from FF8GameData.dat.cameracollection import parse_camera_collection
        path = _copy(tmp_path, "c0m001.dat")[0]
        report = manager.convert_file_list_to_fps([path], 30)[0]
        assert report['camera_report'] is not None and report['camera_report'].nb_keyframe
        original, converted = _load(manager, BATTLE_PATH / "c0m001.dat"), _load(manager, path)

        def durations(monster):
            collection = parse_camera_collection(bytes(monster.section_raw_data[6]))
            return [frame.duration.get() for camera_set in collection.sets
                    for animation in camera_set.animations for block in animation.blocks
                    for frame in block.frames]
        assert durations(converted) == [2 * d for d in durations(original)]
        assert len(converted.section_raw_data[6]) == len(original.section_raw_data[6])

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


class TestChainedCut:
    """An animation the sequences always cut to another one ends toward that one's first frame
    (FF8GameData/dat/animchain.py), not back toward its own start nor on a held pose."""

    def test_the_followers_are_read_from_the_sequences(self, manager):
        from FF8GameData.dat.animchain import analyse_animation_chain
        ward = _load(manager, BATTLE_PATH / "daw039.dat")
        ward.origin_path = str(BATTLE_PATH / "daw039.dat")
        chain = analyse_animation_chain(manager.game_data, ward)
        assert chain[29] == 30          # the attack: 29 (A0, back from the target) -> 30 (landing)
        assert 0 not in chain           # the idle loops
        assert 30 not in chain          # the attack ends (A2): the next sequence is the battle's
        selphie = _load(manager, BATTLE_PATH / "d5w028.dat")
        selphie.origin_path = str(BATTLE_PATH / "d5w028.dat")
        # her wind-up 8 leads to 9, 23 and 29 (same first pose) but also to 18
        assert 8 not in analyse_animation_chain(manager.game_data, selphie)
        # a body reads its weapon's sequences and takes the same decisions (single followers only:
        # Ward's 10 is followed by 1 or by others starting like it in the weapon, not in the body)
        assert 10 not in chain
        body = _load(manager, BATTLE_PATH / "dac021.dat")
        body.origin_path = str(BATTLE_PATH / "dac021.dat")
        assert analyse_animation_chain(manager.game_data, body) == chain

    def test_ward_lands_without_swinging_back(self, manager, tmp_path):
        vanilla = _load(manager, BATTLE_PATH / "dac021.dat").animation_data.animations
        body, weapon = _copy(tmp_path, "dac021.dat", "daw039.dat")
        report_list = manager.convert_file_list_to_fps([body, weapon], 30)
        assert [r['error'] for r in report_list] == ["", ""]
        converted = _load(manager, body).animation_data.animations
        root = lambda frame: [p.get_pos_raw() for p in frame.position]
        frames = converted[29].frames
        assert len(frames) == 2 * len(vanilla[29].frames)
        assert root(frames[-2]) == root(vanilla[29].frames[-1])
        # half-way to the landing's first frame: [-143, -835, -1900] -> [-191, -757, -210]
        middle = [(a + b) / 2 for a, b in zip(root(vanilla[29].frames[-1]), root(vanilla[30].frames[0]))]
        assert all(abs(a - b) <= 1 for a, b in zip(root(frames[-1]), middle))
        # a one-shot the sequence ends on still holds its last pose
        assert root(converted[30].frames[-1]) == root(vanilla[30].frames[-1])

    def test_ward_ends_his_way_back_on_his_spot(self, manager, tmp_path):
        """The way back is `start * (1 - current_frame / total_frames)` over anim 29's frames: once
        converted it divides by total_frames - 1 (seqframeratio), so the last tick is home."""
        from FF8GameData.dat.sequencebake import BattleContext, bake_sequence, sequence_dict_from_section
        body, weapon = _copy(tmp_path, "dac021.dat", "daw039.dat")
        report_list = manager.convert_file_list_to_fps([body, weapon], 30)
        assert report_list[0]['ratio_list'] == []
        # sequences 13 (attack) and 25, each at its D3 0A after the A0 1D: D2 07 (8 frames - 1)
        assert [(seq, anim, divisor) for seq, _address, anim, divisor in report_list[1]['ratio_list']] == \
            [(13, 29, 7), (25, 29, 7)]
        weapon_data = _load(manager, weapon)
        frame_count = [len(a.frames) for a in _load(manager, body).animation_data.animations]
        result = bake_sequence(manager.game_data, sequence_dict_from_section(weapon_data.seq_animation_data),
                               13, frame_count, BattleContext(is_monster=False), follow_chain=False)
        way_back = [frame.position[2] for frame in result.frame_list if frame.anim_id == 29]
        assert way_back[0] < 0 and way_back[-1] == 0

    def test_a_cut_that_moves_the_entity_is_recorded_with_its_move(self, manager, vm):
        """Squall's attack: the run (anim 32) carries him 2078 forward in its root, then anim 34
        starts at root -286 while the sequence puts the entity 1756 forward on that same tick
        (E5 0F). The cut moves the entity: a root blended toward 34's first frame drew him 896
        back for one tick as he reached the target. The slash 36 -> 37 runs through a movement
        loop (one more step of it, not a jump) and Ward's landing does not move him."""
        from FF8GameData.dat.animchain import analyse_animation_chain, get_animation_chain_dict
        from FF8GameData.dat.sequencebake import (BattleContext, bake_sequence,
                                                  sequence_dict_from_section)
        body = _load(manager, BATTLE_PATH / "d0c000.dat")
        body.origin_path = str(BATTLE_PATH / "d0c000.dat")
        chain = analyse_animation_chain(manager.game_data, body)
        assert chain[32] == 34 and chain[36] == 37
        assert 32 in chain.moved_set and 36 not in chain.moved_set
        assert chain.moved_dict[32] == (0, 0, -1756)
        weapon = _load(manager, BATTLE_PATH / "d0w000.dat")
        weapon.origin_path = str(BATTLE_PATH / "d0w000.dat")
        assert analyse_animation_chain(manager.game_data, weapon).moved_set == chain.moved_set
        ward = _load(manager, BATTLE_PATH / "daw039.dat")
        ward.origin_path = str(BATTLE_PATH / "daw039.dat")
        assert 29 not in analyse_animation_chain(manager.game_data, ward).moved_set
        # a plain dict still works: no cut is known to move
        assert dat30.chain_frame_dict(body.animation_data.animations, {32: 34})[32].position[2].get_pos_raw() == -286
        # the move, in the skeleton's units (scale 175): 34's first root seen from the run's place
        frame = dat30.chain_frame_dict(body.animation_data.animations, chain, body.bone_data.unknown00)[32]
        assert body.bone_data.unknown00 == 175
        assert frame.position[2].get_pos_raw() == -286 + round(-1756 * 256 / 175)
        # scale unknown: the run's own last root is kept, never a step back
        frame = dat30.chain_frame_dict(body.animation_data.animations, chain)[32]
        assert frame.position[2].get_pos_raw() == -2078

    def test_squall_reaches_the_target_without_a_step_back(self, manager, tmp_path):
        """Where Squall stands (E5 0F forward offset + body root z * 175 / 256, negative = toward
        the target) on every 30 Hz tick of his attack: as the run ends he goes on toward the
        target, the in-between after the run's last frame half-way through the 531-unit jump
        vanilla makes in one 1/15 s step (no step back, no standstill before the whole jump)."""
        from FF8GameData.dat.sequencebake import BattleContext, bake_sequence, sequence_dict_from_section
        vanilla = _load(manager, BATTLE_PATH / "d0c000.dat").animation_data.animations
        body, weapon = _copy(tmp_path, "d0c000.dat", "d0w000.dat")
        report_list = manager.convert_file_list_to_fps([body, weapon], 30)
        assert [r['error'] for r in report_list] == ["", ""]
        root = lambda frame: [p.get_pos_raw() for p in frame.position]
        for path, model in ((body, "d0c000.dat"), (weapon, "d0w000.dat")):
            vanilla_run = _load(manager, BATTLE_PATH / model).animation_data.animations[32].frames
            run = _load(manager, path).animation_data.animations[32].frames
            assert root(run[-2]) == root(vanilla_run[-1])
            angles = lambda frame: [r.get_rotate_raw() for bone in frame.rotation_vector_data for r in bone]
            assert angles(run[-1]) != angles(run[-2])  # the bones still turn toward 34
        animations = _load(manager, body).animation_data.animations
        sequences = sequence_dict_from_section(_load(manager, weapon).seq_animation_data)
        result = bake_sequence(manager.game_data, sequences, 13, [len(a.frames) for a in animations],
                               BattleContext(is_monster=False), follow_chain=False)
        forward = [frame.position[2] + animations[frame.anim_id].frames[frame.anim_frame].position[2].get_pos_raw()
                   * 175 / 256 for frame in result.frame_list]
        arrival = next(i for i, frame in enumerate(result.frame_list) if frame.anim_id == 34
                       and result.frame_list[i - 1].anim_id == 32)
        run_end, between, landed = forward[arrival - 2:arrival + 1]
        assert round(run_end) == -1421 and round(landed) == -1952
        assert abs(between - (run_end + landed) / 2) < 1
        assert root(vanilla[34].frames[0])[2] == -286


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
        # the body's camera (section 5) is converted, the weapon has none
        assert report_list[0]['camera_report'].nb_keyframe and report_list[1]['camera_report'] is None
        # a converted pair no longer fits the vanilla 64 KB party slot: the user is told
        assert any("party slot" in warning for warning in report_list[0]['warning_list'])

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
