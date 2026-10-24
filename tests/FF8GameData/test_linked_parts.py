"""Multi-part monsters (AnimSeq opcode 90): which monsters the game links into one body, and
what each part plays. Checked on the real files: Seifer's gunblade is the "Gunblade" monster."""
import os

import pytest

from FF8GameData.dat.linkedparts import (animation_map, idle_animation, link_targets,
                                         linked_part_setups, read_sequences)

BATTLE = "extracted_files/battle"


@pytest.fixture(scope="module")
def game_data():
    if not os.path.isfile(os.path.join(BATTLE, "scene.out")):
        pytest.skip("needs the game's battle files in extracted_files/battle")
    from FF8GameData.gamedata import GameData
    data = GameData("FF8GameData")
    data.load_anim_sequence_data()
    return data


def _dat(c0m):
    with open(os.path.join(BATTLE, f"c0m{c0m:03d}.dat"), "rb") as file:
        return file.read()


@pytest.fixture(scope="module")
def encounters(game_data):
    from FF8GameData.sceneout import read_encounters
    with open(os.path.join(BATTLE, "scene.out"), "rb") as file:
        return read_encounters(file.read())


def _targets(game_data):
    cache = {}

    def targets_of(c0m):
        if c0m not in cache:
            try:
                cache[c0m] = link_targets(game_data, read_sequences(_dat(c0m)))
            except FileNotFoundError:
                cache[c0m] = None
        return cache[c0m]
    return targets_of


def test_seifer_is_linked_to_his_gunblade(game_data, encounters):
    targets_of = _targets(game_data)
    # Seifer links himself to battle slot 4, the Gunblade to slot 3 (encounter slots 1 and 0)
    assert targets_of(86) == {("slot", 4)} and targets_of(82) == {("slot", 3)}
    assert linked_part_setups(encounters, 86, targets_of) == [([119], [82])]
    assert linked_part_setups(encounters, 85, targets_of) == [([195], [82])]
    assert linked_part_setups(encounters, 87, targets_of) == [([120], [142])]
    assert linked_part_setups(encounters, 128, targets_of) == [([795], [82])]
    # Mobile Type 8 and its two probes; a monster with no link has no part
    assert linked_part_setups(encounters, 105, targets_of) == [([794], [106, 107])]
    assert linked_part_setups(encounters, 59, targets_of) == []


def test_part_plays_its_sequence_with_the_same_index(game_data):
    # c0m087 stands in anim 0 (its sequence 0), its Gunblade c0m142 in anim 13 (ITS sequence 0)
    assert idle_animation(game_data, _dat(87)) == 0
    assert idle_animation(game_data, _dat(142)) == 13
    mapping = animation_map(game_data, _dat(87), _dat(142))
    assert mapping[0] == 13 and mapping[1] == 42
    assert animation_map(game_data, _dat(86), _dat(82))[0] == 0


def test_characters_have_no_sequences_to_read():
    path = os.path.join(BATTLE, "d6c014.dat")
    if not os.path.isfile(path):
        pytest.skip("needs the game's battle files")
    with open(path, "rb") as file:
        assert read_sequences(file.read()) == []
