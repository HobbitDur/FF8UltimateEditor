"""What an effect asks the battle, previewed in Choreography's part tabs: the sounds it plays and
the action results it gives (the recorder's S and N lines, FF8GameData/psxgpu/fxdump.py).

Sound: a sound block in FF8_EN.exe's data whose leading u32 is a world sound id (BdPlaySE 0x501330
reads nothing else), an audio.dat entry through GetSoundID_ForWorld (Julia's
world_sound_to_archive_id); Fujin's Sound tab plays it once audio.fmt + audio.dat are opened.

Number: the battle shows a result as a number above its target for 10 ticks
(BattleFx_DamageNumbers_TaskTick 0x5069B0): green (0x40, 0x80, 0x40) for a restorative one, grey
otherwise, at a point above the target, its y moved by BattleFx_DamageNumbers_AnimTable (0xB8B830,
2 bytes a tick: y offset, fade flag) - a heal rises steadily (12 to 21 pixels up), a hit bounces;
the last 2 ticks are blended, the very last darkened half way. The amount comes from the battle,
not the effect: the preview shows a stand-in."""
import struct

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QWidget

from Julia.actorsoundtable import world_sound_to_archive_id

NUMBER_TICKS = 10
# BattleFx_DamageNumbers_AnimTable (0xB8B830): per tick (y offset in pixels, fade flag); hit, then heal
HIT_MOTION = [(-12, 0), (-16, 0), (-17, 0), (-17, 0), (-16, 0), (-12, 0), (-13, 0), (-13, 0), (-12, 0x80), (-12, 0x88)]
HEAL_MOTION = [(-12, 0), (-13, 0), (-14, 0), (-15, 0), (-16, 0), (-17, 0), (-18, 0), (-19, 0), (-20, 0x80), (-21, 0x88)]
HEAL_COLOUR, HIT_COLOUR = (0x40, 0x80, 0x40), (0x80, 0x80, 0x80)
IMAGE_BASE = 0x400000                  # FF8_EN.exe: its data's file offset = address - this
_SOUNDS = {}                           # (exe path, address) -> audio.dat entry or None


def sound_archive_id(exe_path, address):
    """The audio.dat entry the sound block at `address` (FF8_EN.exe memory) plays, or None."""
    key = (exe_path, address)
    if key not in _SOUNDS:
        archive = None
        try:
            with open(exe_path, "rb") as exe:
                exe.seek(address - IMAGE_BASE)
                data = exe.read(4)
            if len(data) == 4:
                archive = world_sound_to_archive_id(struct.unpack("<I", data)[0])
        except (OSError, ValueError):
            archive = None
        _SOUNDS[key] = archive
    return _SOUNDS[key]


def number_state(age, heal):
    """(y offset in pixels, opacity 0-1, darkening 0-1) of a result's number `age` ticks after it
    shows, or None once it is gone."""
    if not 0 <= age < NUMBER_TICKS:
        return None
    offset, flag = (HEAL_MOTION if heal else HIT_MOTION)[age]
    return offset, 0.6 if flag & 0x80 else 1.0, (flag & 0xF) / 16


class SoundField(QWidget):
    """A part's Sound parameter: the block's address and the audio.dat entry it plays, a play
    button - the QSpinBox calls a part tab makes (value, setValue, setRange, valueChanged)."""
    valueChanged = pyqtSignal(int)

    def __init__(self, runner, sounds=None):
        super().__init__()
        self.runner, self.sounds, self._value = runner, sounds, 0
        self.label = QLabel()
        self.play = QToolButton()
        self.play.setText("▶")
        self.play.clicked.connect(self.play_sound)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label, 1)
        layout.addWidget(self.play)
        runner.recording_changed.connect(self._show)        # the exe may come after the field
        self._show()

    def value(self):
        return self._value

    def setValue(self, value):
        if value != self._value:
            self._value = value
            self._show()
            if not self.signalsBlocked():
                self.valueChanged.emit(value)

    def setRange(self, _low, _high):
        pass

    def archive_id(self):
        exe = self.runner.exe_path()
        return sound_archive_id(exe, self._value) if exe and self._value else None

    def _show(self):
        archive = self.archive_id()
        self.label.setText(f"0x{self._value:X}" + (f" - audio.dat #{archive}" if archive is not None else ""))
        playable = archive is not None and self.sounds is not None and self.sounds._can_play(archive)
        self.play.setEnabled(playable)
        self.play.setToolTip("Play it" if playable else "Open audio.fmt + audio.dat (header's Import) to hear it")

    def play_sound(self):
        archive = self.archive_id()
        if archive is not None and self.sounds is not None:
            self.sounds.play(archive)
