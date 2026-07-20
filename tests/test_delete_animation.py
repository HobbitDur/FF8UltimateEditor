"""IfritManager.delete_animation removes a whole animation from a battle .dat.

Animations are identified by position, so the editor warns that deleting a non-last one shifts
later ids down (a bare sequence op code IS the animation id). These tests lock in the data-model
behaviour: the right animation is dropped, the count stays in sync, the last one is never dropped,
and the file still saves and reparses to the reduced set.
"""
import copy
import os

import pytest

from Ifrit.ifritmanager import IfritManager

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BATTLE = os.path.join(REPO, "extracted_files", "battle")


def _first_multi_anim_file():
    for i in range(30):
        p = os.path.join(BATTLE, f"c0m{i:03d}.dat")
        if not os.path.isfile(p):
            continue
        m = IfritManager("FF8GameData")
        try:
            enemy = m.parse_file(p)
        except Exception:
            continue
        if enemy.animation_data and enemy.animation_data.nb_animations >= 3:
            return m, p, enemy
    return None, None, None


_M, _PATH, _ENEMY = _first_multi_anim_file()
pytestmark = pytest.mark.skipif(_ENEMY is None,
                                reason="no c0m*.dat with >=3 animations available")


def _fresh():
    m = IfritManager("FF8GameData")
    enemy = m.parse_file(_PATH)
    m.set_active_enemy(enemy, _PATH, textures=([], True))
    return m


def test_delete_middle_animation_shifts_later_ones_down():
    m = _fresh()
    ad = m.enemy.animation_data
    n0 = ad.nb_animations
    # remember the frame count of the animation that follows the one we delete
    after_frames = len(ad.animations[2].frames)
    assert m.delete_animation(1) is True
    assert ad.nb_animations == n0 - 1
    assert len(ad.animations) == ad.nb_animations          # count stays == list length
    # what was id 2 is now id 1 (everything after the gap slid down by one)
    assert len(ad.animations[1].frames) == after_frames


def test_delete_last_animation_leaves_others_untouched():
    m = _fresh()
    ad = m.enemy.animation_data
    n0 = ad.nb_animations
    kept = [len(a.frames) for a in ad.animations[:-1]]
    assert m.delete_animation(n0 - 1) is True
    assert ad.nb_animations == n0 - 1
    assert [len(a.frames) for a in ad.animations] == kept  # no id below the last one moved


def test_cannot_delete_the_last_remaining_animation():
    m = _fresh()
    ad = m.enemy.animation_data
    while ad.nb_animations > 1:
        assert m.delete_animation(ad.nb_animations - 1) is True
    assert ad.nb_animations == 1
    assert m.delete_animation(0) is False                  # the one survivor is protected
    assert ad.nb_animations == 1


def test_out_of_range_id_is_a_noop():
    m = _fresh()
    ad = m.enemy.animation_data
    n0 = ad.nb_animations
    assert m.delete_animation(ad.nb_animations) is False
    assert m.delete_animation(-1) is False
    assert ad.nb_animations == n0


def test_file_saves_and_reparses_with_the_reduced_set(tmp_path):
    m = _fresh()
    n0 = m.enemy.animation_data.nb_animations
    m.delete_animation(1)
    out = str(tmp_path / "reduced.dat")
    m.save_enemy(m.enemy, out)
    # reparse from disk: the saved file really carries one fewer animation and is valid
    m2 = IfritManager("FF8GameData")
    enemy2 = m2.parse_file(out)
    assert enemy2.animation_data.nb_animations == n0 - 1
    assert len(enemy2.animation_data.animations) == n0 - 1
