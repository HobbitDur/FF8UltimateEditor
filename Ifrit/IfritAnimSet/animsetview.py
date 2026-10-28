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
