from FF8GameData.dat.animloopdetector import ANIM_ONE_SHOT
from Ifrit.Ifrit3D.ifrit3dwidget import Ifrit3DWidget


class Entrance3DWidget(Ifrit3DWidget):
    """Ifrit's 3D view on the battle-entrance block (character section 7, weapon 8, Edea 10): every
    action of the .dat viewer, with what differs for that block.
    - its animations are played once, by the battle-start sequence (not looked up in section 3's
      sequences, whose ids are another list's);
    - nothing can reach them in Slow, so they get the full frame limit;
    - a too-long animation is not split: no sequence chains the entrance block's parts;
    - "Convert ALL animations" at 30 fps is the file's conversion (real30_handler, the 3D tab's),
      which converts the entrance block with the rest of the file (the pane then reloads this tab)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.real30_handler = None        # callable(title, interpolation mode): the file's 30 fps conversion

    def _get_animation_usage(self):
        nb_animations = len(self.ifrit_manager.enemy.animation_data.animations)
        self.weapon_file_used = None
        return {'kind_dict': {anim_id: ANIM_ONE_SHOT for anim_id in range(nb_animations)},
                'slowable_set': set(), 'source': None}

    def _split_animation_to_fit(self, anim_id, factor, smooth_loop, max_frames, mode=None):
        return None, "the battle entrance plays its animation whole, no sequence chains parts of it"

    def _convert_loaded_file_to_real30(self, title, interpolation_mode):
        if self.real30_handler is not None:
            self.real30_handler(title, interpolation_mode)
