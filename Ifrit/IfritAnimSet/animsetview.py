"""A loaded character model seen through one of the exe's battle anim sets (limit breaks, Blue
Magic...), for Ifrit's "Exe - Limit anim." tab.

The game binds such a set on the character's model for one action: its body animations, its
sequences and its weapon animations replace the model's own while the action plays
(BattleEntity_BindExternalAnimSet, FF8_EN.exe 0x5022C0; FF8GameData/dat/exeanimset.py). The same is
done here: AnimSetModelView is the SAME file (skeleton, mesh, textures) whose `animation_data` and
`seq_animation_data` are the set's (an AnimSetDocument), and AnimSetManagerView an IfritManager
sharing the file manager's whole state with that view as its `enemy`, so Ifrit's own 3D view and
sequence editor work on the set unchanged. Which set is shown is held by an AnimSetHolder shared by
the body and weapon views: switching sets swaps the document, the views stay.
"""
import copy

from FF8GameData.dat import interpolation
from FF8GameData.dat.animsplitter import MAX_ANIMATION_FRAME
from FF8GameData.monsterdata import Animation
from Ifrit.ifritmanager import IfritManager


class AnimSetHolder:
    """The set document on screen (None when there is none), shared by every view."""

    def __init__(self):
        self.document = None


class AnimSetModelView:
    """The file `monster` with the animations of pool 'body' or 'weapon' of the held set (an empty
    section when there is none) and the set's sequences. Everything else is the file's own."""

    def __init__(self, monster, holder: AnimSetHolder, pool: str):
        object.__setattr__(self, 'monster', monster)
        object.__setattr__(self, 'holder', holder)
        object.__setattr__(self, 'pool', pool)
        from FF8GameData.monsterdata import AnimationSection
        object.__setattr__(self, '_empty', AnimationSection())

    @property
    def animation_data(self):
        document = self.holder.document
        section = None if document is None else (document.body if self.pool == 'body' else document.weapon)
        return section if section is not None else self._empty

    @property
    def seq_animation_data(self):
        document = self.holder.document
        return document.seq_animation_data if document is not None else {'seq_animation_data': []}

    def __getattr__(self, name):
        return getattr(self.monster, name)

    def __setattr__(self, name, value):
        if name == 'animation_data':
            document = self.holder.document
            if document is not None:
                setattr(document, 'body' if self.pool == 'body' else 'weapon', value)
        elif name == 'seq_animation_data':
            if self.holder.document is not None:
                self.holder.document.seq_animation_data = value
        else:
            setattr(self.monster, name, value)


class AnimSetManagerView(IfritManager):
    """An IfritManager sharing ANOTHER manager's state (its very attribute dict) whose `enemy` is that
    manager's file seen through the held anim set (AnimSetModelView). Every IfritManager method works
    unchanged on the set's animations."""
    __slots__ = ('_holder', '_pool', '_enemy_view')

    def __init__(self, manager, holder: AnimSetHolder, pool: str = 'body'):   # noqa - shares the state
        self.__dict__ = manager.__dict__
        self._holder = holder
        self._pool = pool
        self._enemy_view = None

    @property
    def enemy(self):
        monster = self.__dict__.get('enemy')
        if self._enemy_view is None or self._enemy_view.monster is not monster:
            self._enemy_view = AnimSetModelView(monster, self._holder, self._pool)
        return self._enemy_view

    @enemy.setter
    def enemy(self, value):
        self.__dict__['enemy'] = getattr(value, 'monster', value)

    def _animation_sections(self):
        """The set's animations, then the file's own: a skeleton edit made here reposes them all."""
        section = self.enemy.animation_data
        return ([section] if section.animations else []) + IfritManager._animation_sections(self)

    # ------------------------------------------------------------------ lockstep with the other pool
    # The engine plays weapon animation N with body animation N (Battle_QueueAnimation 0x509520):
    # in a set holding both, every edit that adds, removes or re-times animations or frames on one
    # pool is made on the other too, so the ids and the frame counts keep matching. The authoring
    # itself is IfritManager's (the .dat editor's), run on this pool; only the mirroring is here.
    def _other_pool(self):
        """(AnimationSection of the other pool, the bones it is shown on), or (None, None) when the
        set has no weapon animations."""
        document = self._holder.document
        if document is None or document.weapon is None:
            return None, None
        other = 'weapon' if self._pool == 'body' else 'body'
        return document.pool(other), document.bones_of(other)

    def _check_animation_list_edit(self):
        """Adding or deleting animations must keep the ids of the set: refused (ValueError, which the
        editor shows) when it cannot."""
        document = self._holder.document
        if document is None:
            raise ValueError("no anim set shown")
        if document.foreign_body_animations:
            raise ValueError(f"this set keeps {len(document.foreign_body_animations)} animations on another "
                             "skeleton after the body ones: adding or deleting an animation would move them")
        other, _bones = self._other_pool()
        own = self.enemy.animation_data
        if other is not None and len(other.animations) != len(own.animations):
            raise ValueError(f"the body and weapon pools no longer have the same number of animations "
                             f"({len(own.animations)} / {len(other.animations)})")

    def _other_animation(self, anim_id):
        other, bones = self._other_pool()
        if other is None or not 0 <= anim_id < len(other.animations):
            return None, None
        return other.animations[anim_id], bones

    def create_animation_from_frame_range(self, src_anim_id: int, start_frame: int, end_frame: int) -> int:
        self._check_animation_list_edit()
        new_id = IfritManager.create_animation_from_frame_range(self, src_anim_id, start_frame, end_frame)
        other, _bones = self._other_pool()
        source, _bones = self._other_animation(src_anim_id)
        if source is not None:
            low, high = sorted((int(start_frame), int(end_frame)))
            high = min(len(source.frames) - 1, high)
            low = min(max(0, low), high)
            animation = Animation()
            animation.frames = [copy.deepcopy(source.frames[i]) for i in range(low, high + 1)]
            animation.original_tail = b""
            animation._recompute_frame_storage_types()
            other.animations.append(animation)
            other.nb_animations = len(other.animations)
        return new_id

    def delete_animation(self, anim_id: int) -> bool:
        self._check_animation_list_edit()
        if not IfritManager.delete_animation(self, anim_id):
            return False
        other, _bones = self._other_pool()
        if other is not None and anim_id < len(other.animations):
            del other.animations[anim_id]
            other.nb_animations = len(other.animations)
        return True

    def duplicate_animation_frame(self, anim_id: int, frame_id: int) -> int:
        new_index = IfritManager.duplicate_animation_frame(self, anim_id, frame_id)
        animation, _bones = self._other_animation(anim_id)
        if animation is not None and animation.frames and len(animation.frames) < MAX_ANIMATION_FRAME:
            index = min(frame_id, len(animation.frames) - 1)
            animation.frames.insert(index + 1, copy.deepcopy(animation.frames[index]))
            animation._recompute_frame_storage_types()
        return new_index

    def delete_animation_frame(self, anim_id: int, frame_id: int) -> bool:
        if not IfritManager.delete_animation_frame(self, anim_id, frame_id):
            return False
        animation, _bones = self._other_animation(anim_id)
        if animation is not None and frame_id < len(animation.frames) and len(animation.frames) > 1:
            del animation.frames[frame_id]
            animation._recompute_frame_storage_types()
        return True

    def paste_animation_frames(self, anim_id: int, at_index: int, frames: list) -> int:
        """The pasted frames are this pool's; the other pool holds its pose there for as many
        frames (the clipboard has no frames of it)."""
        count = IfritManager.paste_animation_frames(self, anim_id, at_index, frames)
        self._mirror_inserted(anim_id, at_index, count)
        return count

    def interpolate_between_frames(self, anim_id: int, frame_a: int, frame_b: int, nb_insert: int,
                                   mode: str = interpolation.LINEAR) -> int:
        count = IfritManager.interpolate_between_frames(self, anim_id, frame_a, frame_b, nb_insert, mode)
        animation, bones = self._other_animation(anim_id)
        if count and animation is not None:
            frames = animation.frames
            if frame_a < len(frames) and frame_b < len(frames) and len(frames) + count <= MAX_ANIMATION_FRAME:
                before = frames[frame_a - 1] if frame_a > 0 else None
                after = frames[frame_b + 1] if frame_b + 1 < len(frames) else None
                new_frames = [Animation._create_frame_between(frames[frame_a], frames[frame_b], k / (count + 1),
                                                              bones, mode=mode, frame_before=before,
                                                              frame_after=after)
                              for k in range(1, count + 1)]
                frames[frame_a + 1:frame_a + 1] = new_frames
                animation._recompute_frame_storage_types()
            else:
                self._mirror_inserted(anim_id, frame_a, count)
        return count

    def _mirror_inserted(self, anim_id, at_index, count):
        """`count` frames were inserted after frame at_index of this pool's animation: the other
        pool's animation holds its pose at that point for as many frames."""
        animation, _bones = self._other_animation(anim_id)
        if not count or animation is None or not animation.frames:
            return
        count = min(count, MAX_ANIMATION_FRAME - len(animation.frames))
        index = max(0, min(len(animation.frames) - 1, int(at_index)))
        position = max(0, min(len(animation.frames), int(at_index) + 1))
        animation.frames[position:position] = [copy.deepcopy(animation.frames[index]) for _ in range(count)]
        animation._recompute_frame_storage_types()

    def mirror_interpolated_frames(self, anim_id: int, factor: int, smooth_loop: bool, mode):
        """This pool's animation anim_id was converted (fps): the other pool's the same way."""
        animation, bones = self._other_animation(anim_id)
        if animation is not None and len(animation.frames) >= 2:
            animation.create_interpolated_frames(bones, factor, smooth_loop, mode=mode)
