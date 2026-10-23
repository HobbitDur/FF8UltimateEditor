"""GF learn slots: the raw unlock bytes <-> the choices the editor and the CLI show."""
import pytest

from SolomonRing import gf_learn


def _slots(*unlocks, hidden=None):
    """One slot per unlock byte, every slot teaching a real ability (id 10 + slot)."""
    hidden = hidden or {}
    return [(10 + index, raw, hidden.get(index, gf_learn.NO_HIDDEN)) for index, raw in enumerate(unlocks)]


def test_the_unlock_byte_reads_as_a_level_a_slot_or_never():
    assert gf_learn.decode_unlock(0) == (gf_learn.LEVEL, 0)
    assert gf_learn.decode_unlock(100) == (gf_learn.LEVEL, 100)
    assert gf_learn.decode_unlock(101) == (gf_learn.AFTER, 0)      # Ability 1
    assert gf_learn.decode_unlock(121) == (gf_learn.AFTER, 20)     # Ability 21
    assert gf_learn.decode_unlock(122) == (gf_learn.NEVER, 122)
    for raw in range(256):
        assert gf_learn.encode_unlock(*gf_learn.decode_unlock(raw)) == raw
    assert gf_learn.describe_unlock(101) == "after Ability 1"
    assert gf_learn.describe_unlock(10) == "GF level 10"
    assert gf_learn.describe_hidden(0xFF) == "never hidden"


def test_cli_values_count_slots_from_one():
    assert gf_learn.parse_unlock_text("level:30") == 30
    assert gf_learn.parse_unlock_text("after:1") == 101
    assert gf_learn.parse_unlock_text("AFTER:21") == 121
    assert gf_learn.parse_unlock_text("never") == 0xFF
    assert gf_learn.parse_unlock_text("0x65") == 101
    assert gf_learn.parse_hidden_text("none") == 0xFF
    assert gf_learn.parse_hidden_text("3") == 2
    assert gf_learn.parse_hidden_text("hidden:3") == 2
    assert gf_learn.parse_hidden_text("0xFF") == 0xFF
    for bad in ("level:101", "after:0", "after:22", "slot:3"):
        with pytest.raises(ValueError):
            gf_learn.parse_unlock_text(bad)
    with pytest.raises(ValueError):
        gf_learn.parse_hidden_text("22")


def test_a_vanilla_style_chain_has_no_problem_and_builds_a_tree():
    # Quezacotl's start: SumMag+10% (lv 1) -> +20% -> +30%, then GFHP+10% (lv 1) -> +20%.
    slots = _slots(1, 101, 102, 1, 104)
    assert gf_learn.learnability(slots) == [[]] * 5
    forest, orphans = gf_learn.learn_tree(slots)
    assert forest == [(0, [(1, [(2, [])])]), (3, [(4, [])])]
    assert orphans == []


def test_unlearnable_slots_are_explained():
    slots = _slots(1, 101 + 1, 101 + 3, 101 + 2, 200, 101 + 5, 101 + 0, hidden={6: 0})
    slots[5] = (15, 101 + 5, 0xFF)
    problems = gf_learn.learnability(slots)
    assert problems[0] == []
    assert "itself" in problems[1][0]                  # waits for its own slot
    assert "loop" in problems[2][0] and "loop" in problems[3][0]
    assert "never offers" in problems[4][0]            # raw 200
    assert "itself" in problems[5][0]
    assert "also what it waits for" in problems[6][0]  # hidden by its own prerequisite
    forest, orphans = gf_learn.learn_tree(slots)
    assert forest == [(0, [(6, [])])]
    assert orphans == [1, 2, 3, 4, 5]


def test_waiting_for_an_empty_slot_or_offering_one_is_flagged():
    slots = _slots(1, 101, 1)
    slots[0] = (0, 1, 0xFF)
    problems = gf_learn.learnability(slots)
    assert "empty ability" in problems[0][0]
    assert "empty" in problems[1][0]
    assert problems[2] == []
