"""_PlaybackTimer suspends Python's cyclic GC while the 3D animation plays.

Automatic GC pauses scale with the TOTAL live-object count of every loaded file, so with many
files open a gen1/gen2 collection stutters the 3D player mid-playback (measured: a 31 ms hitch at
16 files vs 1.5 ms with GC suspended). The timer turns GC off for the duration of playback and
collects once on stop. These tests lock in that contract - ref-counted across viewers, idempotent
on restart, and never fighting an external gc.disable().
"""
import gc

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication([])

from Ifrit.Ifrit3D.ifrit3dwidget import _PlaybackTimer


def _reset():
    _PlaybackTimer._running = 0
    _PlaybackTimer._we_disabled = False
    if not gc.isenabled():
        gc.enable()


def test_start_suspends_gc_and_stop_restores():
    _reset()
    assert gc.isenabled()
    t = _PlaybackTimer()
    t.start(1000)
    assert not gc.isenabled()          # playing -> GC off (no collection pauses mid-animation)
    t.stop()
    assert gc.isenabled()              # stopped -> GC back on
    _reset()


def test_multiple_viewers_are_refcounted():
    _reset()
    a, b = _PlaybackTimer(), _PlaybackTimer()
    a.start(1000)
    b.start(1000)
    assert not gc.isenabled()
    a.stop()
    assert not gc.isenabled()          # b still playing -> stay off
    b.stop()
    assert gc.isenabled()              # last one stopped -> back on
    _reset()


def test_restart_is_idempotent():
    _reset()
    t = _PlaybackTimer()
    t.start(1000)
    t.start(1000)                      # restart of an already-active timer, not a 2nd play
    assert not gc.isenabled()
    t.stop()                           # a single stop balances it
    assert gc.isenabled()
    _reset()


def test_never_re_enables_an_external_gc_disable():
    _reset()
    gc.disable()                       # some other code turned GC off for its own reasons
    try:
        t = _PlaybackTimer()
        t.start(1000)
        t.stop()
        assert not gc.isenabled()      # we didn't disable it, so we must not enable it
    finally:
        _reset()
