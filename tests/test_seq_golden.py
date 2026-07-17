"""Characterisation tests: the sequence analyser's output must not move.

IfritSeq is a heavily used tool whose current output is trusted, so these tests
pin down what it produces TODAY, byte for byte, over every real battle file that
has a sequence section. They are deliberately dumb: they assert nothing about
what the text *should* say, only that it does not change.

The point is to be able to refactor the parser underneath (unify the two byte
walkers, introduce a command model) and prove the tool still says exactly what it
said before. A diff here means a regression, not a test to update - unless the
change is intended, in which case regenerate the golden file with:

    python -m tests.test_seq_golden --regenerate

The golden file stores a hash per sequence rather than the full text: the full
text of every sequence of every file is several MB, and a hash localises a
regression to one sequence of one file just as well.
"""
import hashlib
import json
import pathlib
import sys

import pytest

from FF8GameData.dat.sequenceanalyser import SequenceAnalyser
from FF8GameData.gamedata import GameData

PROJECT_ROOT = pathlib.Path(__file__).parent.parent
BATTLE_PATH = PROJECT_ROOT / "extracted_files" / "battle"
GOLDEN_PATH = pathlib.Path(__file__).parent / "seq_golden.json"

pytestmark = pytest.mark.skipif(not BATTLE_PATH.is_dir(),
                                reason="extracted battle files not available")


def _load_game_data():
    game_data = GameData(str(PROJECT_ROOT / "FF8GameData"))
    game_data.load_all()
    return game_data


def _corpus_file_list():
    """The battle files this corpus covers: monsters (c0m), characters (dXc), weapons (dXw).

    mag*.dat are excluded on purpose. They are magic effect files, not entity models, and
    MonsterAnalyser does not terminate in any reasonable time on them - unrelated to
    IfritSeq, but it would make this whole module unrunnable. Everything IfritSeq is
    actually pointed at is a monster, character or weapon file, and those are all here.
    """
    return sorted(path for path in BATTLE_PATH.glob("*.dat")
                  if not path.name.startswith("mag"))


def _iter_sequence_file(game_data):
    """(file name, [(seq id, seq bytes)]) for every battle file with a sequence section.

    MonsterAnalyser rejects some files in extracted_files/battle (b0wave.dat is not a
    model file at all); those are skipped rather than failed, they have no sequence to
    analyse in the first place.
    """
    from FF8GameData.dat.monsteranalyser import MonsterAnalyser
    for path in _corpus_file_list():
        try:
            monster = MonsterAnalyser(game_data)
            monster.load_file_data(str(path), game_data)
            monster.analyse_loaded_data(game_data)
        except Exception:  # not a model file, or one this tool cannot read
            continue
        seq_section = getattr(monster, "seq_animation_data", None) or {}
        seq_list = [(seq["id"], bytes(seq["data"]))
                    for seq in seq_section.get("seq_animation_data", []) if seq["data"]]
        if seq_list:
            yield path.name, seq_list


def _analyse(game_data, sequence):
    return SequenceAnalyser(game_data=game_data, model_anim_data=None,
                            sequence=bytearray(sequence)).get_text()


def _observed(game_data, sequence):
    """What the analyser does with this sequence today, as a comparable string.

    Raising IS part of the current behaviour (a fade effect id absent from the json makes
    it raise IndexError), so an exception is recorded rather than escaping: a
    characterisation test that only accepts success cannot pin down a tool that throws,
    and 'it used to crash here and no longer does' is exactly the kind of change worth
    seeing in the diff.
    """
    try:
        return "sha1:" + hashlib.sha1(_analyse(game_data, sequence).encode()).hexdigest()
    except Exception as error:  # noqa: BLE001 - the point is to record whatever happens
        return f"raises:{type(error).__name__}"


def _fingerprint(game_data):
    """{file name: {seq id: observed behaviour}} over every real sequence."""
    golden = {}
    for file_name, seq_list in _iter_sequence_file(game_data):
        golden[file_name] = {str(seq_id): _observed(game_data, data)
                             for seq_id, data in seq_list}
    return golden


@pytest.fixture(scope="module")
def game_data():
    return _load_game_data()


@pytest.fixture(scope="module")
def golden():
    if not GOLDEN_PATH.is_file():
        pytest.skip(f"{GOLDEN_PATH.name} not generated yet "
                    f"(python -m tests.test_seq_golden --regenerate)")
    with open(GOLDEN_PATH, encoding="utf-8") as file:
        return json.load(file)


def test_the_golden_file_covers_every_real_sequence(game_data, golden):
    """A regression that makes files unreadable would otherwise silently shrink the
    corpus and let every other test here pass."""
    current = {file_name: [str(seq_id) for seq_id, _data in seq_list]
               for file_name, seq_list in _iter_sequence_file(game_data)}
    assert set(current) == set(golden), "the set of files with a sequence section moved"
    for file_name, id_list in current.items():
        assert set(id_list) == set(golden[file_name]), f"{file_name}: sequence ids moved"


def test_every_sequence_still_analyses_to_the_same_text(game_data, golden):
    """The output of the tool, over the whole vanilla corpus, byte for byte."""
    changed = []
    for file_name, seq_list in _iter_sequence_file(game_data):
        for seq_id, data in seq_list:
            observed = _observed(game_data, data)
            expected = golden.get(file_name, {}).get(str(seq_id))
            if observed != expected:
                changed.append(f"{file_name} seq {seq_id}: {expected} -> {observed}")
    assert not changed, ("the analyser behaviour changed for:\n  " + "\n  ".join(changed[:40])
                         + (f"\n  ... and {len(changed) - 40} more" if len(changed) > 40 else ""))


def test_analysing_a_sequence_twice_gives_the_same_text(game_data):
    """No hidden state between runs - the golden hashes mean nothing otherwise."""
    for file_name, seq_list in _iter_sequence_file(game_data):
        seq_id, data = seq_list[0]
        assert _observed(game_data, data) == _observed(game_data, data), file_name
        break


def _regenerate():
    game_data = _load_game_data()
    golden = _fingerprint(game_data)
    with open(GOLDEN_PATH, "w", encoding="utf-8") as file:
        json.dump(golden, file, indent=1, sort_keys=True)
    nb_seq = sum(len(v) for v in golden.values())
    print(f"[ok] {GOLDEN_PATH.name}: {len(golden)} files, {nb_seq} sequences")


if __name__ == "__main__":
    if "--regenerate" in sys.argv:
        _regenerate()
    else:
        print("Use --regenerate to rewrite the golden file.")
