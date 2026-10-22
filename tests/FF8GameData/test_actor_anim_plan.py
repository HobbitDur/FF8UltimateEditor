"""What a battle actor plays, read from its dat sequences (FF8GameData.dat.actoranimplan): its idle
loop and its Magic cast, split where the sequence starts the effect."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BATTLE = ROOT / "extracted_files" / "battle"


@pytest.fixture(scope="module")
def vm():
    from FF8GameData.gamedata import GameData
    from FF8GameData.dat.sequencevm import as_sequence_vm
    game_data = GameData(str(ROOT / "FF8GameData"))
    game_data.load_all()
    return as_sequence_vm(game_data)


@pytest.mark.ff8data("extracted_files/battle/d0c000.dat", "extracted_files/battle/d0w000.dat")
def test_squall_idle_and_magic_cast(vm):
    from FF8GameData.dat.actoranimplan import cast_plan, idle_animation, read_frame_counts, read_sequences
    sequences = read_sequences(BATTLE / "d0w000.dat")              # a character's are in its weapon file
    frames = read_frame_counts(BATTLE / "d0c000.dat")
    assert len(frames) == 42 and frames[:4] == [30, 13, 1, 10]
    assert sequences[22].hex() == "c10fe57fa004a1c37fc5ffe57fe7f795a2"   # numbered as the engine does
    assert idle_animation(vm, sequences) == 0                     # sequence 1: "A3 00 E6 FF"
    before, during = cast_plan(vm, sequences, frames)             # sequence 11, Magic
    # 8, 18, 19, then 19 looped until the files are loaded (at once here), 20 for 12 frames: the
    # sequence sets the "start the effect" flag; 20 for 2 more, then 21 looped while it runs
    assert before == [(8, 10), (18, 15), (19, 6), (20, 12)]
    assert during == [(20, 2), (21, 0)]


@pytest.mark.ff8data("extracted_files/battle/c0m009.dat")
def test_monster_sequences_are_its_own(vm):
    from FF8GameData.dat.actoranimplan import cast_plan, idle_animation, read_frame_counts, read_sequences
    sequences = read_sequences(BATTLE / "c0m009.dat")
    assert sequences[1] == bytes.fromhex("a300e6ff") and idle_animation(vm, sequences) == 0
    before, during = cast_plan(vm, sequences, read_frame_counts(BATTLE / "c0m009.dat"))
    assert before and during and all(ticks > 0 for _animation, ticks in before)


def test_missing_files_give_no_plan(vm, tmp_path):
    from FF8GameData.dat.actoranimplan import cast_plan, idle_animation, read_frame_counts, read_sequences
    assert read_sequences(tmp_path / "none.dat") == {} and read_frame_counts(tmp_path / "none.dat") == []
    assert idle_animation(vm, {}) == 0 and cast_plan(vm, {}, []) == ([], [])
