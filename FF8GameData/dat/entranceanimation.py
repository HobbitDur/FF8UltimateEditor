"""The battle-entrance animation of a character body or weapon, as something to look at.

A character body (section 7), a standard weapon (section 8) and Edea (section 10) end with an
extra single-animation block: the animation the character plays when the battle starts.
initAnimationSequenceAtStartBattle (0x5027D0) binds it in place of section 3 with
setComFileData (0x502270) for sequence 8, whose AC 00 then puts the section 3 animations back.
The block uses the section 3 format (offset table + animations) on the file's own skeleton, and
the body and its weapon play their blocks in lockstep like any other animation index.

The block is only READ here: a view never writes it back, so the saved file keeps the raw
section bytes exactly (dat30.convert_extra_animation_block is the only writer).
"""
import copy

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


def make_entrance_view(monster):
    """A shallow copy of `monster` whose animation_data is the entrance block, or None.

    Everything else (skeleton, geometry, textures, raw sections) is the SAME object as the
    file's, so the view poses the real mesh; only the animation list differs. The view is for
    display: it is never saved, and edits to its animation are not kept."""
    section = parse_entrance_animation(monster)
    if section is None:
        return None
    view = copy.copy(monster)
    view.animation_data = section
    view._animation_expanded = True   # nothing to re-expand: ensure_animation_expanded no-op
    return view
