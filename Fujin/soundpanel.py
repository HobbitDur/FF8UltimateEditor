"""Fujin's Sound tab: the MAG file's sound blocks resolved to audio.dat entries and played with
Julia's archive, plus the controller vibration patterns the "voice bank" really holds.

The archive (audio.fmt + audio.dat) comes from the shared file bank only: the header's Import
menu opens it (complementary files), and an archive Julia or the IfritSeq preview opened is
picked up as well. Playback uses Julia's construction (unparented QMediaPlayer + QAudioOutput,
the buffer kept alive until the next sound replaces it).

Edits are high level and keep the file's size: a sound block is pointed at another audio.dat entry
(its world sound id is rewritten, in the same category when it reaches the entry), and a vibration
pattern's points take a new strength and ramp length (their number is fixed)."""
import os

from PyQt6.QtCore import (Qt, QBuffer, QByteArray, QUrl, QLoggingCategory, QPointF, pyqtSignal,
                          QItemSelectionModel)
from PyQt6.QtGui import QColor, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
                             QTableWidgetItem, QHeaderView, QSplitter, QAbstractItemView, QSpinBox,
                             QMessageBox)

from Common.filebinding import FileBinding
from FF8GameData.magcine.magsound import sound_entries, vibration_patterns, set_sound, set_vibration, AKAO
from Julia.juliamanager import JuliaManager

try:
    from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
    QLoggingCategory.setFilterRules("qt.multimedia.ffmpeg*.debug=false\nqt.multimedia.ffmpeg*.info=false")
    MULTIMEDIA_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on the installed Qt build
    MULTIMEDIA_AVAILABLE = False

TICKS_PER_SECOND = 15


def strength_percent(level):
    """A pattern level as the motor strength the engine sends (level x 2, max 255), in %."""
    return min(100, round(level * 200 / 255))


def level_for_percent(percent):
    return min(255, round(percent * 255 / 200))


class VibrationCurve(QWidget):
    """Left (orange) and right (blue) motor levels of one pattern, one point per battle tick."""

    def __init__(self):
        super().__init__()
        self.pattern = None
        self.setMinimumHeight(90)

    def set_pattern(self, pattern):
        self.pattern = pattern
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(40, 40, 48))
        painter.setPen(QColor(200, 200, 200))
        if self.pattern is None or not self.pattern.ticks:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Select a vibration pattern")
            return
        width, height, ticks = self.width() - 8, self.height() - 20, self.pattern.ticks
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for levels, color in ((self.pattern.left, QColor(244, 160, 0)), (self.pattern.right, QColor(90, 160, 240))):
            points = [QPointF(4 + width * i / max(1, ticks - 1), 4 + height * (1 - level / 255))
                      for i, level in enumerate(levels)]
            painter.setPen(QPen(color, 1.5))
            painter.drawPolyline(QPolygonF(points))
        painter.setPen(QColor(200, 200, 200))
        painter.drawText(6, self.height() - 4, f"left motor (orange) / right motor (blue) — {ticks} ticks "
                                               f"= {ticks / TICKS_PER_SECOND:.1f} s")


def _select_row(table, row):
    """Select exactly this row. QTableView.selectRow follows the keys held down: with Ctrl held it
    TOGGLES the row, so restoring the selection after an edit could clear it instead."""
    flags = QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows
    table.selectionModel().select(table.model().index(row, 0), flags)
    table.setCurrentCell(row, 0, QItemSelectionModel.SelectionFlag.NoUpdate)


class SoundPanel(QWidget):
    HEADERS = ["Table", "#", "Offset", "Sound id", "audio.dat entry", "Length", "How the PC plays it"]
    data_changed = pyqtSignal()

    def __init__(self, file_registry, game_data=None):
        super().__init__()
        self.game_data = game_data
        self.manager = None
        self.julia = None
        self.entries = []
        self.patterns = []
        self._player = self._output = self._buffer = None
        self.audio_binding = FileBinding("audio.fmt", file_registry, load_callback=self._load_archive,
                                         file_filter="audio.fmt", read_only=True, complementary=True)
        self.dat_binding = FileBinding("audio.dat", file_registry, file_filter="audio.dat",
                                       read_only=True, complementary=True)
        self.dat_binding.file_opened.connect(self._reload_with_dat)
        self.archive_label = QLabel()
        self.archive_label.setWordWrap(True)
        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(len(self.HEADERS) - 1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.itemDoubleClicked.connect(lambda _item: self.play_selected())
        self.play_button = QPushButton("Play")
        self.play_button.setToolTip("Play the selected block's audio.dat entry (double-click a row too)")
        self.play_button.clicked.connect(self.play_selected)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.entry_spin = QSpinBox()
        self.entry_spin.setRange(0, 9999)
        self.entry_spin.setPrefix("audio.dat entry #")
        self.entry_spin.setToolTip("The audio.dat entry the selected block should play")
        self.entry_spin.valueChanged.connect(self._update_buttons)
        self.preview_button = QPushButton("Preview")
        self.preview_button.setToolTip("Play that entry before using it")
        self.preview_button.clicked.connect(lambda: self.play(self.entry_spin.value()))
        self.use_button = QPushButton("Use for this block")
        self.use_button.setToolTip("The selected block plays this entry from now on (Undo / Redo above, "
                                   "Save in the header)")
        self.use_button.clicked.connect(self.use_entry)
        self.vibration_table = QTableWidget(0, 5)
        self.vibration_table.setHorizontalHeaderLabels(["Slot", "Offset", "Ticks", "Peak left", "Peak right"])
        self.vibration_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.vibration_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.vibration_table.verticalHeader().hide()
        self.vibration_table.itemSelectionChanged.connect(self._show_pattern)
        self.curve = VibrationCurve()
        self.point_tables = {}
        for side in ("left", "right"):
            table = QTableWidget(0, 2)
            table.setHorizontalHeaderLabels(["Strength %", "Ramp to next (ticks)"])
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            table.verticalHeader().setDefaultSectionSize(26)
            table.setToolTip("Each point: the motor strength, then how many ticks (15 per second) it takes "
                             "to reach the next point. The last point ends the pattern. The number of points "
                             "is fixed (the file keeps its size).")
            self.point_tables[side] = table
        self.vibration_label = QLabel(
            "Controller vibration (header +0x24, often called the voice bank): not sound. Cinematic opcode "
            "0x39 sub-op 2 starts a pattern; the engine steps its two envelopes every tick into the pad's "
            "left and right motors.")
        self.vibration_label.setWordWrap(True)

        buttons = QHBoxLayout()
        buttons.addWidget(self.play_button)
        buttons.addWidget(self.stop_button)
        buttons.addWidget(QLabel("  Change to:"))
        buttons.addWidget(self.entry_spin)
        buttons.addWidget(self.preview_button)
        buttons.addWidget(self.use_button)
        buttons.addWidget(self.status, 1)
        sounds = QWidget()
        sounds_layout = QVBoxLayout(sounds)
        sounds_layout.setContentsMargins(0, 0, 0, 0)
        sounds_layout.addWidget(self.archive_label)
        sounds_layout.addWidget(self.table, 1)
        sounds_layout.addLayout(buttons)
        vibration = QWidget()
        vibration_layout = QVBoxLayout(vibration)
        vibration_layout.setContentsMargins(0, 0, 0, 0)
        vibration_layout.addWidget(self.vibration_label)
        row = QHBoxLayout()
        row.addWidget(self.vibration_table, 1)
        right = QVBoxLayout()
        right.addWidget(self.curve, 1)
        motors = QHBoxLayout()
        for side, title in (("left", "Left motor (orange)"), ("right", "Right motor (blue)")):
            column = QVBoxLayout()
            column.addWidget(QLabel(title))
            column.addWidget(self.point_tables[side])
            motors.addLayout(column)
        right.addLayout(motors, 1)
        row.addLayout(right, 2)
        vibration_layout.addLayout(row, 1)
        self.vibration_box = vibration
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(sounds)
        splitter.addWidget(vibration)
        splitter.setSizes([300, 300])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)
        self.audio_binding.load_opened_file()
        self._update_archive_label()
        self._update_buttons()

    # ------------------------------------------------------------------ archive
    def file_bindings(self):
        return [self.audio_binding, self.dat_binding]

    def import_archive(self):
        """Header Import entry: audio.fmt through the shared bank (Julia loads it too)."""
        registry = self.audio_binding.registry
        path = self.audio_binding.open_dialog(self, registry.last_folder("audio.fmt"))
        if path:
            registry.remember_folder("audio.fmt", os.path.dirname(path))

    def _load_archive(self, fmt_path):
        try:
            julia = JuliaManager(self.game_data)
            julia.load(fmt_path, self.dat_binding.current_path or None)
            self.julia = julia
        except (OSError, ValueError) as error:
            self.julia = None
            self.status.setText(f"Sound archive could not be opened: {error}")
        self._update_archive_label()
        self._fill_sounds()

    def _reload_with_dat(self, _path):
        if self.audio_binding.current_path:
            self._load_archive(self.audio_binding.current_path)

    def _update_archive_label(self):
        if self.julia is not None:
            self.archive_label.setText(f"Sound archive: {self.julia.fmt_path} ({len(self.julia.sounds)} entries).")
        else:
            self.archive_label.setText("No sound archive: import audio.fmt (+ audio.dat) from the header's Import "
                                       "menu, under the complementary files, to hear these sounds.")

    # ------------------------------------------------------------------ content
    def set_manager(self, manager):
        """EffectResourceView hook: the selected source file (None = no MAG file with sounds)."""
        self.manager = manager
        self.set_data(manager.data if manager is not None else None)
        if manager is None:
            self.status.setText("No imported MAG file of this effect holds sounds. Effects driven by game code "
                                "play sound blocks stored in FF8_EN.exe instead; those are not listed here.")

    def set_data(self, data):
        """Show the sound blocks and vibration patterns of one MAG byte image (None = nothing)."""
        self.entries = sound_entries(data) if data is not None else []
        self.patterns = vibration_patterns(data) if data is not None else []
        self._fill_sounds()
        self.vibration_table.setRowCount(len(self.patterns))
        for row, pattern in enumerate(self.patterns):
            for column, value in enumerate((pattern.index, f"0x{pattern.offset:X}", pattern.ticks,
                                            max(pattern.left or [0]), max(pattern.right or [0]))):
                self.vibration_table.setItem(row, column, QTableWidgetItem(str(value)))
        self.vibration_box.setVisible(bool(self.patterns))
        self.curve.set_pattern(self.patterns[0] if self.patterns else None)
        if self.patterns:
            _select_row(self.vibration_table, min(getattr(self, "_pattern_row", 0), len(self.patterns) - 1))
        self._fill_points()

    def _duration(self, archive_id):
        if self.julia is None or archive_id is None or not 0 <= archive_id < len(self.julia.sounds):
            return ""
        sound = self.julia.sounds[archive_id]
        if not sound.is_valid:
            return "empty entry"
        rate = sound.wave_format[3]
        return f"{sound.data_length / rate:.2f} s" + (" (loops)" if sound.is_looping else "") if rate else ""

    def _fill_sounds(self):
        self.table.setRowCount(len(self.entries))
        for row, entry in enumerate(self.entries):
            values = (entry.table, entry.index, f"0x{entry.offset:X}",
                      "" if entry.sound_id is None else str(entry.sound_id),
                      "not playable" if entry.archive_id is None else f"#{entry.archive_id}",
                      self._duration(entry.archive_id),
                      ("" if entry.verified or entry.archive_id is None else "UNVERIFIED: ") + entry.note)
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(entry.note)
                if entry.archive_id is None:
                    item.setForeground(QColor(150, 150, 150))
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        if self.entries and not self.table.selectionModel().selectedRows():
            _select_row(self.table, min(getattr(self, "_entry_row", 0), len(self.entries) - 1))
        if not self.entries:
            self.status.setText("This file has no sound blocks.")
        elif not self.status.text().startswith("Sound archive could not"):
            self.status.setText("")
        self._update_buttons()

    def _selected_entry(self):
        rows = self.table.selectionModel().selectedRows()
        return self.entries[rows[0].row()] if rows else None

    def _editable(self, entry):
        return bool(self.manager is not None and entry is not None and entry.sound_id is not None
                    and entry.archive_id is not None)

    def _update_buttons(self, *_args):
        entry = self._selected_entry()
        if entry is not None and entry.archive_id is not None and self.sender() is not self.entry_spin:
            self.entry_spin.blockSignals(True)
            self.entry_spin.setValue(entry.archive_id)
            self.entry_spin.blockSignals(False)
        editable = self._editable(entry)
        self.entry_spin.setEnabled(editable)
        self.use_button.setEnabled(editable and self.entry_spin.value() != entry.archive_id)
        self.preview_button.setEnabled(editable and self._can_play(self.entry_spin.value()))
        playable = bool(entry and entry.archive_id is not None and self.julia is not None and MULTIMEDIA_AVAILABLE
                        and 0 <= entry.archive_id < len(self.julia.sounds)
                        and self.julia.sounds[entry.archive_id].is_valid)
        self.play_button.setEnabled(playable)
        if entry is not None and not playable:
            reason = (entry.note if entry.archive_id is None else
                      "Import the sound archive first" if self.julia is None else
                      "Qt multimedia is not available" if not MULTIMEDIA_AVAILABLE else
                      f"audio.dat entry #{entry.archive_id} is empty in this archive")
            self.play_button.setToolTip(reason)
        else:
            self.play_button.setToolTip("Play the selected block's audio.dat entry (double-click a row too)")

    def _can_play(self, archive_id):
        return bool(self.julia is not None and MULTIMEDIA_AVAILABLE and 0 <= archive_id < len(self.julia.sounds)
                    and self.julia.sounds[archive_id].is_valid)

    def _show_pattern(self):
        rows = self.vibration_table.selectionModel().selectedRows()
        self.curve.set_pattern(self.patterns[rows[0].row()] if rows else None)
        self._fill_points()

    def _selected_pattern(self):
        rows = self.vibration_table.selectionModel().selectedRows()
        return self.patterns[rows[0].row()] if rows and rows[0].row() < len(self.patterns) else None

    def _fill_points(self):
        pattern = self._selected_pattern()
        for side, table in self.point_tables.items():
            points = getattr(pattern, side + "_points") if pattern is not None else []
            table.clearContents()
            table.setRowCount(len(points))
            for row, (level, frames) in enumerate(points):
                strength = QSpinBox()
                strength.setRange(0, 100)
                strength.setSuffix(" %")
                strength.setValue(strength_percent(level))
                strength.setKeyboardTracking(False)
                strength.setEnabled(self.manager is not None)
                strength.valueChanged.connect(lambda _v, s=side, r=row: self._point_changed(s, r))
                table.setCellWidget(row, 0, strength)
                if frames == 0xFF:
                    item = QTableWidgetItem("end")
                    item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                    table.setItem(row, 1, item)
                    continue
                ramp = QSpinBox()
                ramp.setRange(1, 255)
                ramp.setValue(frames + 1)
                ramp.setKeyboardTracking(False)
                ramp.setEnabled(self.manager is not None)
                ramp.valueChanged.connect(lambda _v, s=side, r=row: self._point_changed(s, r))
                table.setCellWidget(row, 1, ramp)
            if not points:
                table.setRowCount(1)
                item = QTableWidgetItem("unused")
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                table.setItem(0, 0, item)

    def _point_changed(self, side, row):
        pattern = self._selected_pattern()
        if pattern is None or self.manager is None:
            return
        table = self.point_tables[side]
        points = list(getattr(pattern, side + "_points"))
        level, frames = points[row]
        percent = table.cellWidget(row, 0).value()
        if percent != strength_percent(level):
            level = level_for_percent(percent)
        ramp = table.cellWidget(row, 1)
        if ramp is not None:
            frames = ramp.value() - 1
        points[row] = (level, frames)
        self._write(lambda: set_vibration(self.manager.data, pattern, side, points))

    def use_entry(self):
        entry = self._selected_entry()
        if not self._editable(entry):
            return False
        archive_id = self.entry_spin.value()
        return self._write(lambda: (entry.offset, set_sound(self.manager.data, entry, archive_id)))

    def _write(self, edit):
        """Apply (offset, bytes) from `edit` to the file, keep the selections, tell the host."""
        try:
            offset, raw = edit()
        except ValueError as error:
            QMessageBox.warning(self, "Fujin", f"Not applied: {error}")
            self.set_data(self.manager.data)
            return False
        rows = self.table.selectionModel().selectedRows()
        self._entry_row = rows[0].row() if rows else 0
        rows = self.vibration_table.selectionModel().selectedRows()
        self._pattern_row = rows[0].row() if rows else 0
        self.manager.patch_bytes(offset, raw)
        self.table.clearSelection()
        self.set_data(self.manager.data)
        self.data_changed.emit()
        return True

    # ------------------------------------------------------------------ playback
    def play_selected(self):
        entry = self._selected_entry()
        if entry is None or not self.play_button.isEnabled():
            return
        self.play(entry.archive_id)

    def play(self, archive_id):
        try:
            wav = self.julia.get_wav(archive_id)
        except Exception as error:  # noqa: BLE001 - an entry the archive cannot serve
            self.status.setText(f"Could not read audio.dat entry #{archive_id}: {error}")
            return
        if self._player is None:
            self._output = QAudioOutput()
            self._player = QMediaPlayer()
            self._player.setAudioOutput(self._output)
            self._player.errorOccurred.connect(lambda _e, text: self.status.setText(f"Playback error: {text}"))
        self._player.stop()
        buffer = QBuffer(self)
        buffer.setData(QByteArray(wav))
        buffer.open(QBuffer.OpenModeFlag.ReadOnly)
        previous, self._buffer = self._buffer, buffer
        self._player.setSourceDevice(buffer, QUrl(f"fujin_{archive_id}.wav"))
        if previous is not None:
            previous.close()
            previous.deleteLater()
        self._player.play()
        self.status.setText(f"Playing audio.dat entry #{archive_id}.")

    def stop(self):
        if self._player is not None:
            self._player.stop()
