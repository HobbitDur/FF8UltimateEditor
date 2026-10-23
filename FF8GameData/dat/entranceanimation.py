"""The battle-entrance animation of a character body or weapon.

A character body (section 7), a standard weapon (section 8) and Edea (section 10) end with an
extra single-animation block: the animation the character plays when the battle starts.
initAnimationSequenceAtStartBattle (0x5027D0) binds it in place of section 3 with
setComFileData (0x502270) for sequence 8, whose AC 00 then puts the section 3 animations back.
The block uses the section 3 format (offset table + animations) on the file's own skeleton, and
the body and its weapon play their blocks in lockstep like any other animation index.

MonsterAnalyser.ensure_entrance_animation() parses it once; the file is then saved from that
object (the re-encoding of an unedited block is byte-exact on every vanilla file).
EntranceAnimationView shows the file with that block as its animation list, for an editor that
works on `enemy.animation_data` (Ifrit's 3D view).
"""
from .dat30 import get_extra_animation_section_index
from ..monsterdata import AnimationSection


def get_entrance_section_index(monster):
    """Section index of the entrance block when the file has a non-empty one, else None."""
    index = get_extra_animation_section_index(monster)
    if index is None or index >= len(monster.section_raw_data):
        return None
    if len(monster.section_raw_data[index]) < 8:
        return None
    return index


def parse_entrance_animation(monster):
    """The entrance block parsed on the file's skeleton (AnimationSection, bone matrices
    built), or None when the file has none."""
    index = get_entrance_section_index(monster)
    if index is None or not monster.bone_data or not monster.bone_data.bones:
        return None
    section = AnimationSection()
    section.analyze(bytes(monster.section_raw_data[index]), monster.bone_data)
    return section if section.animations else None


class EntranceAnimationView:
    """The SAME file, seen with its entrance block as `animation_data`.

    Every other attribute and method is the file's own (read and written through), so an edit to
    the skeleton or the mesh goes to the file, and saving, undo and re-expansion keep working on
    section 3. Only `animation_data` is the entrance block (the file's entrance_animation_data,
    an empty section when the file has none)."""

    def __init__(self, monster):
        object.__setattr__(self, 'monster', monster)
        object.__setattr__(self, '_empty', AnimationSection())

    @property
    def animation_data(self):
        return self.monster.ensure_entrance_animation() or self._empty

    @animation_data.setter
    def animation_data(self, value):
        self.monster.entrance_animation_data = value

    def __getattr__(self, name):
        return getattr(self.monster, name)

    def __setattr__(self, name, value):
        if name == 'animation_data':
            object.__setattr__(self, name, value)   # goes through the property setter
        else:
            setattr(self.monster, name, value)
