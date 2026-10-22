"""The 3D tab's animation selector: animation ids, plus one extra entry for the battle-entrance
animation of a character/weapon (the extra single-animation block, see
FF8GameData/dat/entranceanimation.py)."""
from PyQt6.QtGui import QValidator
from PyQt6.QtWidgets import QSpinBox


class AnimationSelector(QSpinBox):
    """A QSpinBox over 0..nb-1, plus the value nb shown as a label when an extra entry is set."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._extra_value = None
        self._extra_label = ""

    def set_extra_entry(self, value, label=""):
        """Show `value` as `label` (value None: no extra entry). The caller sets the range."""
        self._extra_value = value
        self._extra_label = label
        self.updateGeometry()
        self.lineEdit().setText(self.textFromValue(self.value()))

    def is_extra(self, value) -> bool:
        return self._extra_value is not None and value == self._extra_value

    def textFromValue(self, value):
        if self.is_extra(value):
            return self._extra_label
        return super().textFromValue(value)

    def valueFromText(self, text):
        if self._extra_value is not None and text.strip().lower() == self._extra_label.lower():
            return self._extra_value
        return super().valueFromText(text)

    def validate(self, text, pos):
        typed = text.strip().lower()
        if self._extra_value is not None and typed and self._extra_label.lower().startswith(typed):
            state = (QValidator.State.Acceptable if typed == self._extra_label.lower()
                     else QValidator.State.Intermediate)
            return state, text, pos
        return super().validate(text, pos)
