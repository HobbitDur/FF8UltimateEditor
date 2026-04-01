from PyQt6.QtCore import QObject, pyqtSignal
from typing import List, Tuple


class BoneEditorController(QObject):
    """Controller that mediates between BoneEditor and Ifrit3DWidget"""

    # Signals that the bone editor can emit
    bone_selected = pyqtSignal(int)
    bone_length_changed = pyqtSignal(int, float)
    bone_parent_changed = pyqtSignal(int, int)
    animation_rotation_changed = pyqtSignal(int, int, int, float, float, float)
    skeleton_visibility_requested = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.current_anim_id = 0
        self.current_frame = 0
        self.bone_count = 0

    def set_current_animation_frame(self, anim_id: int, frame_id: int):
        """Called by Ifrit3DWidget when animation/frame changes"""
        self.current_anim_id = anim_id
        self.current_frame = frame_id

    def set_bone_count(self, count: int):
        """Called by Ifrit3DWidget when model loads"""
        self.bone_count = count

    def get_bone_data(self, bone_id: int) -> dict:
        """Get bone data (to be implemented by the main widget)"""
        # This will be connected from the main widget
        pass