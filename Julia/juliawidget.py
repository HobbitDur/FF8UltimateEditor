"""Julia - FF8 battle sound editor widget.

Browse the FF8 sound archive (audio.fmt / audio.dat), play sounds, export them to
WAV, and replace them from WAV for modding. Playback goes through QMediaPlayer,
streaming the rebuilt WAV straight from memory. The "Used by" column shows which
battle actors (characters / monsters) reference each sound, resolved through the
stru_B8A418 table extracted from FF8_EN.exe.
"""
import os
import sys

from PyQt6.QtCore import QBuffer, QByteArray, QLoggingCategory, QSize, Qt, QUrl
from PyQt6.QtGui import QIcon
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog,
                             QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QAbstractItemView)

from FF8GameData.gamedata import GameData
from Julia.juliamanager import JuliaManager

# Qt's FFmpeg backend dumps the stream layout to the console on every play.
# QT_LOGGING_RULES still overrides this, so it can be turned back on to debug.
QLoggingCategory.setFilterRules("qt.multimedia.ffmpeg*=false")


class JuliaWidget(QWidget):
    """Editor for the FF8 sound archive (audio.fmt + audio.dat)."""

    COL_INDEX = 0
    COL_FORMAT = 1
    COL_CHANNELS = 2
    COL_RATE = 3
    COL_LENGTH = 4
    COL_LOOP = 5
    COL_USED_BY = 6
    HEADERS = ["#", "Format", "Ch", "Rate (Hz)", "Length", "Loop", "Used by"]

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData"):
        QWidget.__init__(self)
        self.icon_path = icon_path

        self.game_data = GameData(game_data_folder)
        self.game_data.load_monster_data()
        self.manager = JuliaManager(self.game_data)

        # The buffer must outlive the play() call: the player streams from it.
        self._play_buffer = None
        self.audio_output = QAudioOutput()
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio_output)
        self.player.errorOccurred.connect(self._on_player_error)

        self.setWindowTitle("Julia")
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'hobbitdur.ico')))

        # --- File section ---
        self.load_button = QPushButton()
        self.load_button.setIcon(QIcon(os.path.join(icon_path, 'folder.png')))
        self.load_button.setIconSize(QSize(30, 30))
        self.load_button.setFixedSize(40, 40)
        self.load_button.setToolTip("Open audio.fmt (audio.dat must be in the same folder)")
        self.load_button.clicked.connect(self.load_file)

        self.save_button = QPushButton()
        self.save_button.setIcon(QIcon(os.path.join(icon_path, 'save.svg')))
        self.save_button.setIconSize(QSize(30, 30))
        self.save_button.setFixedSize(40, 40)
        self.save_button.setToolTip("Rebuild and overwrite audio.fmt and audio.dat (irreversible)")
        self.save_button.clicked.connect(self.save_file)
        self.save_button.setEnabled(False)

        self.file_label = QLabel("No file loaded")

        file_layout = QHBoxLayout()
        file_layout.addWidget(self.load_button)
        file_layout.addWidget(self.save_button)
        file_layout.addWidget(self.file_label)
        file_layout.addStretch(1)

        # --- Sound table ---
        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = self.table.horizontalHeader()
        for col in range(len(self.HEADERS)):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_USED_BY, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._update_action_buttons)
        self.table.itemDoubleClicked.connect(lambda _item: self.play_selected())

        # --- Action buttons ---
        self.play_button = QPushButton("Play")
        self.play_button.setToolTip("Play the selected sound")
        self.play_button.clicked.connect(self.play_selected)

        self.export_button = QPushButton("Export WAV...")
        self.export_button.setToolTip("Export the selected sound to a .wav file")
        self.export_button.clicked.connect(self.export_selected)

        self.replace_button = QPushButton("Replace from WAV...")
        self.replace_button.setToolTip("Replace the selected sound with a .wav file (PCM or MS-ADPCM)")
        self.replace_button.clicked.connect(self.replace_selected)

        self.export_all_button = QPushButton("Export all...")
        self.export_all_button.setToolTip("Export every sound to a chosen folder")
        self.export_all_button.clicked.connect(self.export_all)
        self.export_all_button.setEnabled(False)

        action_layout = QHBoxLayout()
        action_layout.addWidget(self.play_button)
        action_layout.addWidget(self.export_button)
        action_layout.addWidget(self.replace_button)
        action_layout.addStretch(1)
        action_layout.addWidget(self.export_all_button)

        self.info_label = QLabel("")
        self.info_label.setStyleSheet("font-style: italic;")

        main_layout = QVBoxLayout(self)
        main_layout.addLayout(file_layout)
        main_layout.addWidget(self.table)
        main_layout.addLayout(action_layout)
        main_layout.addWidget(self.info_label)
        self.setLayout(main_layout)

        self._update_action_buttons()

    # ------------------------------------------------------------------ helpers
    def _selected_index(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return rows[0].row()

    def _update_action_buttons(self):
        has_selection = self._selected_index() is not None
        self.play_button.setEnabled(has_selection)
        self.export_button.setEnabled(has_selection)
        self.replace_button.setEnabled(has_selection)

    def _refresh_row(self, row):
        sound = self.manager.sounds[row]
        used_by = ", ".join(self.manager.actor_names_for(row))
        values = {
            self.COL_INDEX: str(row),
            self.COL_FORMAT: sound.format_label(),
            self.COL_CHANNELS: str(sound.channels),
            self.COL_RATE: str(sound.sample_rate),
            self.COL_LENGTH: f"{sound.data_length:,}",
            self.COL_LOOP: "yes" if sound.is_looping else "",
            self.COL_USED_BY: used_by,
        }
        for col, text in values.items():
            item = QTableWidgetItem(text)
            if col in (self.COL_INDEX, self.COL_CHANNELS, self.COL_RATE, self.COL_LENGTH):
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, col, item)

    def _populate_table(self):
        self.table.setRowCount(len(self.manager.sounds))
        for row in range(len(self.manager.sounds)):
            self._refresh_row(row)

    # ------------------------------------------------------------------ actions
    def load_file(self):
        file_name, _ = QFileDialog.getOpenFileName(
            parent=self, caption="Open audio.fmt", filter="FF8 sound format (audio.fmt);;All files (*)")
        if not file_name:
            return
        try:
            self.manager.load(file_name)
        except (OSError, ValueError, FileNotFoundError) as error:
            QMessageBox.critical(self, "Julia", f"Could not open the sound archive:\n{error}")
            return
        self._populate_table()
        self.file_label.setText(f"{file_name}  ({len(self.manager.sounds)} sounds)")
        self.save_button.setEnabled(True)
        self.export_all_button.setEnabled(True)
        self.info_label.setText("")

    def play_selected(self):
        index = self._selected_index()
        if index is None:
            return
        try:
            wav = self.manager.get_wav(index)
        except Exception as error:  # noqa: BLE001 - decoding can fail on exotic formats
            QMessageBox.warning(self, "Julia", f"Could not read this sound:\n{error}")
            return
        self.player.stop()
        buffer = QBuffer(self)
        buffer.setData(QByteArray(wav))
        buffer.open(QBuffer.OpenModeFlag.ReadOnly)
        # Hand the player the new buffer before dropping the old one, so it is
        # never left streaming from a buffer we just closed.
        previous, self._play_buffer = self._play_buffer, buffer
        self.player.setSourceDevice(buffer, QUrl("julia.wav"))
        if previous is not None:
            previous.close()
            previous.deleteLater()
        self.player.play()

    def _on_player_error(self, _error, error_string):
        # Playback is asynchronous, so failures arrive here rather than as an
        # exception out of play().
        QMessageBox.warning(self, "Julia", f"Could not play this sound:\n{error_string}")

    def closeEvent(self, event):
        self.player.stop()
        QWidget.closeEvent(self, event)

    def export_selected(self):
        index = self._selected_index()
        if index is None:
            return
        default_name = f"sound_{index:04d}.wav"
        file_name, _ = QFileDialog.getSaveFileName(
            parent=self, caption="Export sound to WAV", directory=default_name,
            filter="WAV audio (*.wav)")
        if not file_name:
            return
        try:
            self.manager.export_wav(index, file_name)
        except OSError as error:
            QMessageBox.critical(self, "Julia", f"Could not export:\n{error}")
            return
        self.info_label.setText(f"Exported sound {index} to {file_name}")

    def replace_selected(self):
        index = self._selected_index()
        if index is None:
            return
        file_name, _ = QFileDialog.getOpenFileName(
            parent=self, caption="Replace sound from WAV", filter="WAV audio (*.wav);;All files (*)")
        if not file_name:
            return
        try:
            self.manager.replace_from_wav(index, file_name)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "Julia", f"Could not import this WAV:\n{error}")
            return
        self._refresh_row(index)
        self.info_label.setText(f"Sound {index} replaced (not saved yet - use the save button).")

    def export_all(self):
        folder = QFileDialog.getExistingDirectory(self, "Export all sounds to folder")
        if not folder:
            return
        try:
            count = self.manager.export_all(folder)
        except OSError as error:
            QMessageBox.critical(self, "Julia", f"Could not export:\n{error}")
            return
        self.info_label.setText(f"Exported {count} sounds to {folder}")

    def save_file(self):
        if not self.manager.sounds:
            return
        answer = QMessageBox.question(
            self, "Julia",
            "This will rebuild and overwrite audio.fmt and audio.dat.\n"
            "Make sure you have a backup. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.manager.save()
        except OSError as error:
            QMessageBox.critical(self, "Julia", f"Could not save:\n{error}")
            return
        self._populate_table()
        self.info_label.setText("Saved audio.fmt and audio.dat.")
