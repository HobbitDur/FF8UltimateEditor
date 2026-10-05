"""Julia - FF8 battle sound editor widget.

Browse the FF8 sound archive (audio.fmt / audio.dat), play sounds, export them to
WAV, and replace them from WAV for modding. Playback goes through QMediaPlayer,
streaming the rebuilt WAV straight from memory. The "Used by" column shows which
battle actors (characters / monsters) reference each sound, resolved through the
stru_B8A418 table extracted from FF8_EN.exe.
"""
import os
import sys
import struct

from PyQt6.QtCore import QBuffer, QByteArray, QLoggingCategory, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog,
                             QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QAbstractItemView, QTabWidget)

from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from FF8GameData.gamedata import GameData
from Julia.juliamanager import JuliaManager
from Julia.actorsoundwidget import ActorSoundWidget

# Qt's FFmpeg backend dumps the stream layout to the console on every play.
# QT_LOGGING_RULES still overrides this, so it can be turned back on to debug.
QLoggingCategory.setFilterRules("qt.multimedia.ffmpeg*=false")


class JuliaWidget(QWidget):
    """Editor for the FF8 sound archive (audio.fmt + audio.dat)."""

    file_bindings_changed = pyqtSignal()

    COL_INDEX = 0
    COL_FORMAT = 1
    COL_CHANNELS = 2
    COL_RATE = 3
    COL_LENGTH = 4
    COL_LOOP = 5
    COL_USED_BY = 6
    HEADERS = ["#", "Format", "Ch", "Rate (Hz)", "Length", "Loop", "Used by"]

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData", file_registry=None):
        QWidget.__init__(self)
        if file_registry is None:  # Used alone, it shares its files with nobody
            file_registry = FileRegistry()
        self.icon_path = icon_path
        self._opening_archive = False

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

        # audio.fmt (+ audio.dat, taken from the same folder), driven by the shared header
        # toolbar (Import / Save).
        self.audio_binding = FileBinding("audio.fmt", file_registry, load_callback=self.load_file,
                                         save_callback=self.save_file, file_filter="audio.fmt")
        self.dat_binding = FileBinding("audio.dat", file_registry, load_callback=self.load_dat_file,
                                       file_filter="audio.dat")

        # --- Sound table ---
        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        # Interactive: the user can drag every column edge (ResizeToContents locks
        # them). The last column (Used by) stretches into whatever width is left.
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        # '#' fits the full 4-digit sound ids from the start, not just the header glyph.
        self.table.setColumnWidth(self.COL_INDEX,
                                  self.fontMetrics().horizontalAdvance("99999") + 14)
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

        archive_widget = QWidget()
        archive_layout = QVBoxLayout(archive_widget)
        archive_layout.addWidget(self.table)
        archive_layout.addLayout(action_layout)
        archive_layout.addWidget(self.info_label)
        self.actor_sound_widget = ActorSoundWidget(self.game_data, file_registry, self.manager)
        self.actor_sound_widget.play_requested.connect(self.play_sound)
        self.actor_sound_widget.file_state_changed.connect(self.file_bindings_changed.emit)
        self.tabs = QTabWidget()
        self.tabs.addTab(archive_widget, "Audio archive")
        self.tabs.addTab(self.actor_sound_widget, "Actor sound IDs")
        self.tabs.currentChanged.connect(lambda _index: self.file_bindings_changed.emit())
        main_layout = QVBoxLayout(self)
        self.archive_label = QLabel("Main files: audio.fmt + audio.dat — Import opens both files.")
        self.archive_label.setWordWrap(True)
        main_layout.addWidget(self.archive_label)
        main_layout.addWidget(self.tabs)

        self._update_action_buttons()
        self.audio_binding.load_opened_file()  # another tool instance may have opened one already
        self.dat_binding.load_opened_file()

    def file_bindings(self):
        """The file the shared header toolbar drives for this tool (audio.fmt + audio.dat)."""
        return [self.audio_binding, self.dat_binding, self.actor_sound_widget.binding]

    def save_files(self):
        if self.tabs.currentWidget() is self.actor_sound_widget:
            self.actor_sound_widget.save_file()
        else:
            self.save_file()

    def can_save_folder(self):
        return (self.tabs.currentWidget() is self.actor_sound_widget
                and (self.actor_sound_widget.path is None or self.actor_sound_widget.dirty))

    def import_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Open sound archive: select audio.fmt and audio.dat",
            self.audio_binding.registry.last_folder("audio.fmt")
            or os.path.dirname(self.manager.fmt_path or "") or os.getcwd(),
            "FF8 sound archive (audio.fmt audio.dat)")
        if not paths:
            return
        selected = {os.path.basename(path).lower(): path for path in paths}
        if set(selected) != {"audio.fmt", "audio.dat"}:
            QMessageBox.warning(self, "Julia", "Select both audio.fmt and audio.dat to open the archive.")
            return
        self.load_archive(selected["audio.fmt"], selected["audio.dat"])

    def load_dat_file(self, path):
        if self._opening_archive:
            return
        fmt = os.path.join(os.path.dirname(path), "audio.fmt")
        self.load_archive(fmt if os.path.isfile(fmt) else self.audio_binding.current_path, path)

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
        # Fit the freshly loaded data once (the columns stay Interactive, so this is a
        # starting point the user can drag from, not a lock), then keep '#' wide enough
        # for every 4-digit id even if the top rows shown are short ones.
        self.table.resizeColumnsToContents()
        minimum_index_width = self.fontMetrics().horizontalAdvance("99999") + 14
        if self.table.columnWidth(self.COL_INDEX) < minimum_index_width:
            self.table.setColumnWidth(self.COL_INDEX, minimum_index_width)

    # ------------------------------------------------------------------ actions
    def load_file(self, file_name):
        """Load audio.fmt (+ audio.dat from the same folder); path from the shared header
        toolbar."""
        if self._opening_archive:
            return
        dat = os.path.join(os.path.dirname(file_name), "audio.dat")
        self.load_archive(file_name, dat if os.path.isfile(dat) else self.dat_binding.current_path)

    def load_archive(self, fmt_path, dat_path):
        try:
            self.manager.load(fmt_path, dat_path)
        except (OSError, ValueError, struct.error) as error:
            QMessageBox.critical(self, "Julia", f"Could not open the sound archive:\n{error}")
            return
        self._opening_archive = True
        try:
            self.audio_binding.open_path(fmt_path)
            self.dat_binding.open_path(dat_path)
        finally:
            self._opening_archive = False
        self.audio_binding.registry.remember_folder("audio.fmt", os.path.dirname(fmt_path))
        self.audio_binding.registry.remember_folder("audio.dat", os.path.dirname(dat_path))
        self.archive_label.setText(f"Main files — audio.fmt: {fmt_path}\naudio.dat: {dat_path}")
        self._populate_table()
        self.export_all_button.setEnabled(True)
        self.info_label.setText("")
        self.actor_sound_widget.update_preview()

    def play_selected(self):
        index = self._selected_index()
        if index is None:
            return
        self.play_sound(index)

    def play_sound(self, index):
        """Play an archive entry using the same player for both Julia tabs."""
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
