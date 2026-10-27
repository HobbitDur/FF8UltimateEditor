"""The Keyframes + Script editor of one camera track (FF8GameData.dat.cameratrack), shared by Fujin
(spell cameras) and Alexander (battle stage cameras).

A track may change size where its host can store a bigger one (`growth_note` says how): an exe
spell track no longer fits the exe but an FFNx .bcam file can still use it, a battle stage's
camera pushes the geometry after it. A track stored inside another file (a MAG section) has a
fixed room, `fixed_size`: the script and the keyframes share it. Removing keyframes or applying a
shorter script leaves filler after the script's last command (never run); added keyframes or a
longer script use that filler, and an edit that needs more than the room is refused.

`manager` edits the script (FF8GameData.dat.cameratrack.CameraScriptTools); `preview`, if any,
plays the track: set_track(track), preview_animation(animation), refresh(), a `track` attribute
and an `animation_chosen` signal (the animation index the script plays, or None).

The Script tab has two views of the same code: User-friendly (Common.camerascripteditor, one row
per command with lists of values) and Code (text). The code text is what Apply reads; a
user-friendly edit rewrites it. `context` ("spell", "stage") picks what the info button and the
value lists say about the track's script (camera_script.json)."""
from PyQt6.QtCore import pyqtSignal, QSize, Qt
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QPlainTextEdit,
                             QPushButton, QScrollArea, QSplitter, QMessageBox, QComboBox, QStackedWidget)

from FF8GameData.dat.camerascript import animation_index_parts
from FF8GameData.dat.sequencecodec import code_to_sequence, sequence_to_code
from Common.apppaths import app_path
from Common.cameracollectionwidget import CameraCollectionWidget
from Common.camerascripteditor import CameraScriptStepsWidget

VIEW_USER_FRIENDLY = 0
VIEW_CODE = 1


class CameraTrackEditor(QWidget):
    keyframes_changed = pyqtSignal()   # a keyframe value changed in place (same size)
    track_changed = pyqtSignal()       # the script was applied or keyframes/slots added or removed

    # Where a grown track goes (no fixed_size): an exe spell track only fits an FFNx .bcam file
    EXE_GROWTH_NOTE = "the vanilla exe cannot use it any more, an FFNx .bcam file can"

    def __init__(self, manager, preview=None, room_name="exe", parent=None, growth_note=EXE_GROWTH_NOTE,
                 context="spell"):
        super().__init__(parent)
        self.manager = manager
        self.preview = preview
        self.room_name = room_name
        self.growth_note = growth_note
        self.context = context
        self.slot_notes = {}       # (set index, slot) -> note shown with the slot
        self.track = None
        self.fixed_size = None
        self._code = b""           # fixed size: the script without the filler added after it
        self._collection_widget = None
        if preview is not None:
            preview.animation_chosen.connect(self._show_chosen_slot)

        self.tabs = QTabWidget()
        self.keyframe_scroll = QScrollArea()
        self.keyframe_scroll.setWidgetResizable(True)
        self.tabs.addTab(self.keyframe_scroll, "Keyframes")
        self.tabs.addTab(self._build_script_tab(), "Script")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)

    def _build_script_tab(self):
        monospace = QFont("Courier New")
        monospace.setStyleHint(QFont.StyleHint.Monospace)
        self.script_editor = QPlainTextEdit()
        self.script_editor.setFont(monospace)
        self.script_editor.textChanged.connect(self._update_script_size)
        self.apply_script_button = QPushButton("Apply script")
        self.apply_script_button.clicked.connect(self._apply_script)
        self.script_size_label = QLabel()
        self.script_steps = CameraScriptStepsWidget(lambda: self.manager.vm, self.context)
        self.script_steps.script_edited.connect(self._on_steps_edited)

        self.script_info_button = QPushButton()
        self.script_info_button.setIcon(QIcon(str(app_path("Resources", "info.png"))))
        self.script_info_button.setIconSize(QSize(30, 30))
        self.script_info_button.setFixedSize(40, 40)
        self.script_info_button.setToolTip("What the camera script does and what can be edited")
        self.script_info_button.clicked.connect(self._show_script_info)
        self.script_view_combo = QComboBox()
        self.script_view_combo.addItems(["User-friendly", "Code"])
        self.script_view_combo.setToolTip("User-friendly: one row per command, values picked from lists. "
                                          "Code: the same script as text. Both are kept until Apply.")
        self.script_view_combo.currentIndexChanged.connect(self._change_script_view)
        self.script_description = QPlainTextEdit()
        self.script_description.setReadOnly(True)
        self.script_description.setFont(monospace)
        self.script_description.setToolTip("What each command does (bytes, then meaning)")

        editor_side = QWidget()
        editor_layout = QVBoxLayout(editor_side)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.addWidget(QLabel("Code (editable)"))
        editor_layout.addWidget(self.script_editor, 1)
        description_side = QWidget()
        description_layout = QVBoxLayout(description_side)
        description_layout.setContentsMargins(0, 0, 0, 0)
        description_layout.addWidget(QLabel("Meaning"))
        description_layout.addWidget(self.script_description, 1)

        splitter = QSplitter()
        splitter.addWidget(editor_side)
        splitter.addWidget(description_side)
        splitter.setStretchFactor(1, 2)

        self.script_views = QStackedWidget()
        self.script_views.addWidget(self.script_steps)   # VIEW_USER_FRIENDLY
        self.script_views.addWidget(splitter)            # VIEW_CODE
        top_row = QHBoxLayout()
        top_row.addWidget(self.script_info_button)
        top_row.addWidget(QLabel("View:"))
        top_row.addWidget(self.script_view_combo)
        top_row.addStretch(1)
        apply_row = QHBoxLayout()
        apply_row.addWidget(self.apply_script_button)
        apply_row.addWidget(self.script_size_label, 1)
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top_row)
        layout.addWidget(self.script_views, 1)
        layout.addLayout(apply_row)
        return tab

    def _show_script_info(self):
        info = self.script_steps.info
        message = QMessageBox(self)
        message.setIcon(QMessageBox.Icon.Information)
        message.setWindowTitle(info.info["title"])
        message.setTextFormat(Qt.TextFormat.RichText)
        message.setText(info.info_html(self.context))
        message.exec()

    def _change_script_view(self, view):
        """Code -> User-friendly shows the code as it is now; code that does not parse keeps the Code view."""
        if view == VIEW_USER_FRIENDLY:
            try:
                script = bytes(code_to_sequence(self.manager.vm, self.script_editor.toPlainText()))
            except ValueError as error:
                self.script_view_combo.blockSignals(True)
                self.script_view_combo.setCurrentIndex(VIEW_CODE)
                self.script_view_combo.blockSignals(False)
                self._refuse("The code cannot be shown as commands", error)
                return
            if self.track is not None:
                self.script_steps.set_script(script)
        self.script_views.setCurrentIndex(view)

    def _on_steps_edited(self, script):
        """A user-friendly edit: the code text follows (Apply reads it)."""
        self.script_editor.setPlainText(sequence_to_code(self.manager.vm, script))

    # ------------------------------------------------------------------ track
    def set_track(self, track, fixed_size=None):
        """Show `track` (None: nothing). `fixed_size`: the track must stay that many bytes."""
        self.track, self.fixed_size = track, fixed_size
        self._code = b""
        if track is not None:
            self._code = track.script if fixed_size is None else self.manager.script_without_filler(track.script)
        if fixed_size is None:
            tip = ("The camera script as code, one command per line. It picks which keyframe animation "
                   "plays (play / play_var) from the attacker, the target, random values... A shorter "
                   f"script is filled up on Apply (the track keeps its {self.room_name} size); a longer one "
                   f"makes the track grow: {self.growth_note}.")
        else:
            tip = ("The camera script as code, one command per line. It picks which keyframe animation "
                   "plays (play / play_var) from the attacker, the target, random values... The script "
                   f"and the keyframes share the camera's {fixed_size} bytes in the {self.room_name}: a "
                   "shorter script is filled up on Apply, a longer one only fits after keyframes are removed.")
        self.script_editor.setToolTip(tip)
        self.set_enabled(track is not None)
        self._set_collection_widget(track)
        if track is None:
            self._set_script_texts("", "")
        else:  # a fixed room shows the script without its filler, whose size follows the keyframes
            self._set_script_texts(sequence_to_code(self.manager.vm, self._code), self.manager.script_text(track))
        self.script_steps.collection = None if track is None else track.collection
        self.script_steps.slot_notes = dict(self.slot_notes)
        self.script_steps.set_script(None if track is None else self._code)
        if self.preview is not None:
            self.preview.set_track(track)

    def set_slot_notes(self, notes):
        """Notes shown with the slots, {(set index, slot): text}; the keyframes are shown again."""
        self.slot_notes = dict(notes)
        if self.track is not None:
            expanded = self._collection_widget.expanded_set_indices() if self._collection_widget else ()
            self._set_collection_widget(self.track, expanded)
            self.script_steps.set_collection(self.track.collection, self.slot_notes)

    def set_enabled(self, enabled):
        self.apply_script_button.setEnabled(enabled)
        self.script_editor.setReadOnly(not enabled)
        self.script_steps.setEnabled(enabled)

    def script_room(self):
        """Bytes the script may use: its exe length, or what the fixed room leaves after the keyframes."""
        if self.track is None:
            return 0
        if self.fixed_size is None:
            return self.track.script_room
        return self.manager.fixed_script_room(self.track, self.fixed_size)

    def _set_collection_widget(self, track, expanded_sets=()):
        self._collection_widget = None
        if track is None:
            self.keyframe_scroll.setWidget(QLabel(""))
            return
        widget = CameraCollectionWidget(track.collection, structure_edits=True, expanded_sets=expanded_sets,
                                        show_preview_buttons=self.preview is not None, slot_notes=self.slot_notes)
        widget.data_changed.connect(self._on_keyframes_changed)
        widget.collection_rebuilt.connect(self._on_collection_rebuilt)
        if self.preview is not None:
            widget.preview_requested.connect(self.preview.preview_animation)
        self._collection_widget = widget
        self.keyframe_scroll.setWidget(widget)

    def _show_chosen_slot(self, chosen):
        """Unfold and mark, in the keyframes, the animation the camera script plays (only when the
        preview plays this editor's track: several editors may share one preview)."""
        if self._collection_widget is None or self.track is None or self.preview.track is not self.track:
            return
        if chosen is None:
            self._collection_widget.highlight_slot(None, None)
        else:
            set_index, slot = animation_index_parts(chosen)
            self._collection_widget.highlight_slot(set_index, slot)

    def _set_script_texts(self, code, description):
        self.script_editor.blockSignals(True)
        self.script_editor.setPlainText(code)
        self.script_editor.blockSignals(False)
        self.script_description.setPlainText(description)
        self._update_script_size()

    def _update_script_size(self):
        """Live 'used / room' byte count. An exe track may grow (.bcam); a fixed room refuses it."""
        if self.track is None:
            self.script_size_label.setText("")
            return
        room = self.script_room()
        try:
            size = self.manager.script_size(self.script_editor.toPlainText())
        except ValueError:
            self.script_size_label.setStyleSheet("color: red;")
            self.script_size_label.setText(f"Not valid code - room: {room} bytes")
            self.apply_script_button.setEnabled(True)  # Apply tells which line is wrong
            return
        longer = size > room
        if longer and self.fixed_size is not None:
            self.script_size_label.setStyleSheet("color: red;")
            text = (f"{size} / {room} bytes: {size - room} more than the {self.room_name} has - the camera "
                    f"keeps its {self.fixed_size} bytes there; remove keyframes first to make room")
        elif longer:
            self.script_size_label.setStyleSheet("color: #c77800;")
            text = (f"{size} / {room} bytes: {size - room} more than the {self.room_name} has - "
                    f"the track grows: {self.growth_note}")
        elif size < room:
            self.script_size_label.setStyleSheet("")
            text = f"{size} / {room} bytes (Apply fills the {room - size} left)"
        else:
            self.script_size_label.setStyleSheet("")
            text = f"{size} / {room} bytes"
        self.script_size_label.setText(text)
        self.apply_script_button.setEnabled(not (longer and self.fixed_size is not None))

    # ------------------------------------------------------------------ edits
    def _refuse(self, what, error):
        QMessageBox.warning(self, "Camera track", f"{what}:\n{error}")

    def _on_keyframes_changed(self):
        self.keyframes_changed.emit()
        if self.preview is not None:
            self.preview.refresh()

    def _on_collection_rebuilt(self, data):
        """A keyframe or slot was added/removed: the track takes the new collection and the editor
        is rebuilt where it was. In a fixed room the script's filler makes up the difference."""
        track = self.track
        if track is None:
            return
        if self.fixed_size is not None:
            before = (track.collection, track.script, track.padding, track.exe_script_size)
            track.set_collection(data)
            try:
                self.manager.fit_track_to_size(track, self._code, self.fixed_size)
            except ValueError as error:
                track.collection, track.script, track.padding, track.exe_script_size = before
                self._refuse("The keyframes were not changed", f"{error}. {self._fixed_size_hint()}")
                return
        else:
            track.set_collection(data)
        expanded = self._collection_widget.expanded_set_indices() if self._collection_widget else ()
        scroll = self.keyframe_scroll.verticalScrollBar().value()
        self._set_collection_widget(track, expanded)
        self.keyframe_scroll.verticalScrollBar().setValue(scroll)
        self.script_description.setPlainText(self.manager.script_text(track))
        self.script_steps.set_collection(track.collection, self.slot_notes)   # sets and empty slots changed
        self._update_script_size()
        self.track_changed.emit()
        if self.preview is not None:
            self.preview.set_track(track)  # new animation objects: run the script again

    def _apply_script(self):
        track = self.track
        if track is None:
            return
        try:
            if self.fixed_size is None:
                self.manager.set_script_code(track, self.script_editor.toPlainText())
                code = self.manager.script_code(track)
            else:
                script = bytes(code_to_sequence(self.manager.vm, self.script_editor.toPlainText()))
                try:
                    self.manager.fit_track_to_size(track, script, self.fixed_size)
                except ValueError as error:
                    raise ValueError(f"{error}. {self._fixed_size_hint()}") from error
                self._code = script
                code = sequence_to_code(self.manager.vm, script)  # without the filler, which varies
        except ValueError as error:
            self._refuse("The script was not applied", error)
            return
        self._set_script_texts(code, self.manager.script_text(track))
        self.script_steps.set_script(bytes(code_to_sequence(self.manager.vm, code)))
        self.track_changed.emit()
        if self.preview is not None:
            self.preview.set_track(track)  # the script may now choose another animation

    def _fixed_size_hint(self):
        return (f"The camera keeps its {self.fixed_size} bytes in the {self.room_name} (the bytes after it "
                "are not moved): remove keyframes or apply a shorter script to make room first")
