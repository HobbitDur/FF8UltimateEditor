"""Output routing and failure feedback, independent of the test machine's devices."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt6.QtMultimedia import QMediaDevices, QMediaPlayer
from PyQt6.QtWidgets import QApplication, QMessageBox

from Julia.juliamanager import FF8Sound
from Julia.juliawidget import JuliaWidget


def device(identifier, name):
    return SimpleNamespace(id=lambda: identifier, description=lambda: name,
                           isNull=lambda: not identifier)


@pytest.fixture
def audio_widget(monkeypatch):
    app = QApplication.instance() or QApplication([])
    widget = JuliaWidget(game_data_folder=str(Path(__file__).resolve().parents[2] / "FF8GameData"))
    speakers = device(b"speakers", "Speakers")
    headphones = device(b"headphones", "Headphones")
    hardware = SimpleNamespace(outputs=[speakers, headphones], default=speakers)
    monkeypatch.setattr(QMediaDevices, "audioOutputs", staticmethod(lambda: hardware.outputs))
    monkeypatch.setattr(QMediaDevices, "defaultAudioOutput", staticmethod(lambda: hardware.default))
    output = SimpleNamespace(selected=None)
    widget.audio_output = SimpleNamespace(setDevice=lambda value: setattr(output, "selected", value),
                                         device=lambda: output.selected)
    calls = []
    widget.player = SimpleNamespace(isAvailable=lambda: True, stop=lambda: calls.append("stop"),
                                    setSourceDevice=lambda *_args: calls.append("source"),
                                    play=lambda: calls.append("play"), hasAudio=lambda: True)
    sound = FF8Sound()
    sound.data = b"\x80" * 100
    sound.data_length = len(sound.data)
    sound.wave_format = (1, 1, 8000, 8000, 1, 8, 0)
    widget.manager.sounds = [FF8Sound(), sound]
    widget._refresh_audio_outputs()
    try:
        yield widget, hardware, output, calls
    finally:
        widget.close()
        widget.deleteLater()
        app.processEvents()


def test_explicit_output_is_used_for_playback_and_survives_refresh(audio_widget):
    widget, hardware, output, calls = audio_widget
    assert output.selected is hardware.outputs[0]
    widget.output_combo.setCurrentIndex(2)
    assert output.selected is hardware.outputs[1]
    widget.play_sound(1)
    assert calls == ["stop", "source", "play"]
    assert "Headphones" in widget.playback_label.text()
    assert widget._play_buffer.isOpen()

    # Reorder the list: selection follows device identity, not the combo index.
    hardware.outputs.reverse()
    widget.media_devices.audioOutputsChanged.emit()
    assert widget.output_combo.currentData() == b"headphones"
    assert output.selected.description() == "Headphones"


def test_system_default_tracks_changes_and_unplugged_choice_falls_back(audio_widget):
    widget, hardware, output, _calls = audio_widget
    hardware.default = hardware.outputs[1]
    widget.media_devices.audioOutputsChanged.emit()
    assert widget.output_combo.currentIndex() == 0
    assert output.selected.description() == "Headphones"
    assert "Headphones" in widget.output_combo.currentText()

    widget.output_combo.setCurrentIndex(1)  # explicitly select speakers
    hardware.outputs = [hardware.default]  # unplug speakers
    widget.media_devices.audioOutputsChanged.emit()
    assert widget.output_combo.currentIndex() == 0
    assert output.selected is hardware.default


def test_missing_device_reports_problem_and_recovers_when_connected(audio_widget):
    widget, hardware, output, calls = audio_widget
    headphones = hardware.outputs[1]
    hardware.outputs = []
    hardware.default = device(b"", "")
    widget.media_devices.audioOutputsChanged.emit()
    widget.play_sound(1)
    assert calls == []
    assert "No audio output detected" in widget.playback_label.text()

    hardware.outputs = [headphones]
    hardware.default = headphones
    widget.media_devices.audioOutputsChanged.emit()
    widget.play_sound(1)
    assert calls == ["stop", "source", "play"]
    assert output.selected is headphones


def test_empty_sound_and_unavailable_backend_are_explained(audio_widget):
    widget, _hardware, _output, calls = audio_widget
    widget._populate_table()
    widget.table.selectRow(0)
    assert not widget.play_button.isEnabled()
    assert widget.replace_button.isEnabled()
    widget.play_sound(0)
    assert "no audio data" in widget.playback_label.text()
    widget.table.selectRow(1)
    assert widget.play_button.isEnabled()
    widget.player.isAvailable = lambda: False
    widget.play_sound(1)
    assert "unavailable" in widget.playback_label.text()
    assert calls == []


def test_playback_status_and_errors_are_visible_on_both_tabs(audio_widget, monkeypatch):
    widget, _hardware, _output, _calls = audio_widget
    widget.play_sound(1)
    widget.tabs.setCurrentIndex(1)
    assert widget.playback_label.parent() is widget
    widget._on_media_status(QMediaPlayer.MediaStatus.BufferedMedia)
    assert "Playing sound #1" in widget.playback_label.text()
    widget._on_media_status(QMediaPlayer.MediaStatus.EndOfMedia)
    assert "Finished sound #1" in widget.playback_label.text()
    widget.player.hasAudio = lambda: False
    widget._on_media_status(QMediaPlayer.MediaStatus.BufferedMedia)
    assert "without a playable audio track" in widget.playback_label.text()
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[-1]))
    widget._on_player_error(QMediaPlayer.Error.FormatError, "Unsupported codec")
    assert "Unsupported codec" in widget.playback_label.text()
    assert "Unsupported codec" in warnings[0]
