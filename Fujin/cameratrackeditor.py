"""The Keyframes + Script editor of one camera track, shared by every place Fujin edits one.

An exe track (Camera effect editor) may change size: the exe has no room for it any more, an
FFNx .bcam file can still use it. A track stored inside another file (a MAG section) has a fixed
room, `fixed_size`: the script and the keyframes share it. Removing keyframes or applying a
shorter script leaves filler after the script's last command (never run); added keyframes or a
longer script use that filler, and an edit that needs more than the room is refused."""
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QPlainTextEdit,
                             QPushButton, QScrollArea, QSplitter, QMessageBox)

from FF8GameData.dat.camerascript import animation_index_parts
from FF8GameData.dat.sequencecodec import code_to_sequence, sequence_to_code
from Watts.cameracollectionwidget import CameraCollectionWidget


class CameraTrackEditor(QWidget):
    keyframes_changed = pyqtSignal()   # a keyframe value changed in place (same size)
    track_changed = pyqtSignal()       # the script was applied or keyframes/slots added or removed

    def __init__(self, manager, preview=None, room_name="exe", parent=None):
        super().__init__(parent)
        self.manager = manager
        self.preview = preview
        self.room_name = room_name
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
        self.script_description = QPlainTextEdit()
        self.script_description.setReadOnly(True)
        self.script_description.setFont(monospace)
        self.script_description.setToolTip("What each command does (bytes, then meaning)")

        editor_side = QWidget()
        editor_layout = QVBoxLayout(editor_side)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.addWidget(QLabel("Code (editable)"))
        editor_layout.addWidget(self.script_editor, 1)
        apply_row = QHBoxLayout()
        apply_row.addWidget(self.apply_script_button)
        apply_row.addWidget(self.script_size_label, 1)
        editor_layout.addLayout(apply_row)
        description_side = QWidget()
        description_layout = QVBoxLayout(description_side)
        description_layout.setContentsMargins(0, 0, 0, 0)
        description_layout.addWidget(QLabel("Meaning"))
        description_layout.addWidget(self.script_description, 1)

        splitter = QSplitter()
        splitter.addWidget(editor_side)
        splitter.addWidget(description_side)
        splitter.setStretchFactor(1, 2)
        return splitter

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
                   "script is filled up on Apply (the track keeps its exe size); a longer one makes the "
                   "track grow: the vanilla exe cannot use it any more, an FFNx .bcam file can.")
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
        if self.preview is not None:
            self.preview.set_track(track)

    def set_enabled(self, enabled):
        self.apply_script_button.setEnabled(enabled)
        self.script_editor.setReadOnly(not enabled)

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
                                        show_preview_buttons=self.preview is not None)
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
            text = (f"{size} / {room} bytes: {size - room} more than the exe has - "
                    "the track grows, only an FFNx .bcam file can use it")
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
        self.track_changed.emit()
        if self.preview is not None:
            self.preview.set_track(track)  # the script may now choose another animation

    def _fixed_size_hint(self):
        return (f"The camera keeps its {self.fixed_size} bytes in the {self.room_name} (the bytes after it "
                "are not moved): remove keyframes or apply a shorter script to make room first")
