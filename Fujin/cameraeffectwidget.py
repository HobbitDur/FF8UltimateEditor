import os

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                             QTabWidget, QPlainTextEdit, QPushButton, QScrollArea, QSplitter,
                             QMessageBox, QFileDialog)

from Common.filebinding import FileBinding
from Fujin.cameraeffectmanager import CAM_FFNX_FOLDER, CameraEffectManager, cam_file_name
from Fujin.cameraeffectpreview import CameraEffectPreview
from SmallWidget.listsearchbar import ListSearchBar
from Watts.cameracollectionwidget import CameraCollectionWidget

HEXT_FOLDER_KEY = "camera effect .hext"
CAM_FOLDER_KEY = "camera effect .bcam"

_NO_TRACK_TEXT = {
    "file": "This effect uses a file camera: its camera data or commands are stored in a loaded "
            "cinematic file. Some files embed a normal camera track; others drive the view with "
            "cinematic commands. This tab only edits and previews tracks stored in the exe.",
    "none": "This effect never starts a camera track (no Battle_PlayCameraAnimation call). With "
            "the Item command the battle view stays as it is; with Magic or a command that "
            "opened on the caster, the camera stays on the caster for the whole effect "
            "(e.g. 5 Phoenix Down, 7 Mega Phoenix). Some effects move the camera with their own code.",
}


class CameraEffectEditorWidget(QWidget):
    """Fujin's "Camera effect editor" tab: the camera track of every spell/attack effect.

    Open the FF8 exe (shared "FF8 exe" file: opening it in Cid, Xu... opens it here too), pick an
    effect, edit its keyframes or its camera script, and Save writes a .hext of the changed bytes
    for that exe's language. A saved .hext can be imported back over the exe to go on editing.
    Edits keep each track at its exe size: the exe has no free room after a track.
    The preview on the right plays the effect's camera around an imported caster and target:
    the camera script chooses the animation from the Script inputs, a slot's ▶ Preview plays
    that slot as is, and keyframe edits replay at once."""

    modified_changed = pyqtSignal()

    def __init__(self, game_data, file_registry, embedded=False):
        QWidget.__init__(self)
        self.file_registry = file_registry
        self.manager = CameraEffectManager(game_data)
        self.exe_binding = FileBinding("FF8 exe", file_registry, load_callback=self.load_exe,
                                       file_filter="*.exe")
        self.exe_binding.file_closed.connect(lambda _path: self._close_exe())
        # The unsaved-changes '*' follows the tracks' real state (modified_changed), not every
        # keystroke in the script editor before Apply.
        self.setProperty("read_only_preview", True)
        self._collection_widget = None
        self.preview = CameraEffectPreview(self.manager, file_registry)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)

        self.effect_list = QListWidget()
        self.effect_list.setMinimumWidth(260)
        self.effect_list.currentRowChanged.connect(self._show_selected)
        self.effect_search = ListSearchBar.wrap(self.effect_list)

        self.info_label = QLabel()
        self.info_label.setWordWrap(True)
        self.info_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.reset_button = QPushButton("Reset to the exe values")
        self.reset_button.setToolTip("Undo every change made to this effect's camera track")
        self.reset_button.clicked.connect(self._reset_selected)
        self.export_cam_button = QPushButton("Export .bcam…")
        self.export_cam_button.setToolTip(
            "Save this effect's camera track (with its edits) as an FFNx camera file, effect_NNN.bcam.\n"
            f"FFNx plays it instead of the exe's from the game folder's {CAM_FFNX_FOLDER}/ - works with\n"
            "every exe language, and needs no .hext.")
        self.export_cam_button.clicked.connect(lambda: self.export_cam())
        info_row = QHBoxLayout()
        info_row.addWidget(self.info_label, 1)
        info_buttons = QVBoxLayout()
        info_buttons.addWidget(self.reset_button)
        info_buttons.addWidget(self.export_cam_button)
        info_buttons.addStretch(1)
        info_row.addLayout(info_buttons)
        # A track that changed size no longer fits the exe: only a .bcam file can use it
        self.size_warning = QLabel()
        self.size_warning.setWordWrap(True)
        self.size_warning.setStyleSheet("color: #c77800; font-size: small;")
        self.size_warning.hide()

        self.tabs = QTabWidget()
        self.keyframe_scroll = QScrollArea()
        self.keyframe_scroll.setWidgetResizable(True)
        self.tabs.addTab(self.keyframe_scroll, "Keyframes")
        self.tabs.addTab(self._build_script_tab(), "Script")

        details = QWidget()
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.addLayout(info_row)
        details_layout.addWidget(self.size_warning)
        details_layout.addWidget(self.tabs, 1)

        splitter = QSplitter()
        splitter.addWidget(self.effect_search.column)
        splitter.addWidget(details)
        splitter.addWidget(self.preview)
        if embedded:
            self.effect_search.column.hide()
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 1)

        layout = QVBoxLayout()
        layout.addWidget(self.status_label)
        layout.addWidget(splitter, 1)
        self.setLayout(layout)

        self._fill_list()
        self._update_status()
        self.effect_list.setCurrentRow(0)

    def _build_script_tab(self):
        monospace = QFont("Courier New")
        monospace.setStyleHint(QFont.StyleHint.Monospace)
        self.script_editor = QPlainTextEdit()
        self.script_editor.setFont(monospace)
        self.script_editor.setToolTip("The camera script as code, one command per line. It picks which "
                                      "keyframe animation plays (play / play_var) from the attacker, the "
                                      "target, random values... A shorter script is filled up on Apply "
                                      "(the track keeps its exe size); a longer one makes the track grow: "
                                      "the vanilla exe cannot use it any more, an FFNx .bcam file can.")
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

    # ------------------------------------------------------------------ files
    def load_exe(self, path):
        try:
            self.manager.load_exe(path)
        except (ValueError, OSError) as error:
            self.manager.close()
            QMessageBox.warning(self, "Camera effect editor", f"Could not read the camera tracks:\n{error}")
        self._after_tracks_changed()

    def _close_exe(self):
        self.manager.close()
        self._after_tracks_changed()

    def open_exe(self):
        path = self.exe_binding.open_dialog(self, default_dir=self.file_registry.last_folder("FF8 exe"))
        if path:
            self.file_registry.remember_folder("FF8 exe", os.path.dirname(path))

    def import_hext(self, path=None):
        if not self.manager.loaded:
            QMessageBox.information(self, "Camera effect editor",
                                    "Open the FF8 exe first: a camera .hext is applied over its tracks.")
            return
        if not path:
            path = QFileDialog.getOpenFileName(self, "Open a camera .hext", filter="*.hext",
                                               directory=self.file_registry.last_folder(HEXT_FOLDER_KEY)
                                               or os.getcwd())[0]
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as file:
                count = self.manager.apply_hext_text(file.read())
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "Camera effect editor", f"Could not apply {os.path.basename(path)}:\n{error}")
            return
        self.file_registry.remember_folder(HEXT_FOLDER_KEY, os.path.dirname(path))
        self._after_tracks_changed()
        self.status_label.setText(self.status_label.text() + f" - {os.path.basename(path)} applied to {count} track(s).")

    def has_changes(self) -> bool:
        return bool(self.manager.modified_tracks())

    def save_hext(self, path=None) -> bool:
        if not self.manager.loaded:
            return False
        if not self.has_changes():
            QMessageBox.information(self, "Camera effect editor", "No camera track was changed: nothing to save.")
            return False
        resized = self.manager.resized_tracks()
        if len(resized) == len(self.manager.modified_tracks()):
            QMessageBox.information(self, "Camera effect editor",
                                    "Every changed camera track was resized: the exe has no room for them, so "
                                    "there is nothing for a .hext. Export each one with Export .bcam… (FFNx).")
            return False
        if not path:
            default = os.path.join(self.file_registry.last_folder(HEXT_FOLDER_KEY) or os.getcwd(),
                                   f"camera_effects_{self.manager.language_name}.hext")
            path = QFileDialog.getSaveFileName(self, "Save the camera patch", default, "*.hext")[0]
        if not path:
            return False
        try:
            text = self.manager.hext_text()
        except ValueError as error:  # a track no longer fits its exe room: write nothing
            QMessageBox.warning(self, "Camera effect editor", f"The .hext was not saved:\n{error}")
            return False
        with open(path, "w", encoding="utf-8") as file:
            file.write(text)
        self.file_registry.remember_folder(HEXT_FOLDER_KEY, os.path.dirname(path))
        if resized:
            names = ", ".join(str(track.effect_id) for track in resized)
            self.status_label.setText(self.status_label.text() + f" - left out of the .hext (resized, "
                                      f"export them as .bcam): {names}.")
        return True

    def export_cam(self, path=None) -> bool:
        """Write the selected effect's track as an FFNx effect_NNN.bcam file."""
        effect_id = self._selected_effect()
        track = self.manager.track(effect_id)
        if track is None:
            return False
        try:
            data = self.manager.cam_bytes(track)  # checked before anything is written
        except ValueError as error:
            QMessageBox.warning(self, "Camera effect editor", f"Cannot export the camera:\n{error}")
            return False
        if not path:
            default = os.path.join(self.file_registry.last_folder(CAM_FOLDER_KEY) or os.getcwd(),
                                   cam_file_name(effect_id))
            path = QFileDialog.getSaveFileName(
                self, f"Export the camera of effect {effect_id} for FFNx ({CAM_FFNX_FOLDER}/)",
                default, "FFNx effect camera (*.bcam)")[0]
        if not path:
            return False
        with open(path, "wb") as file:
            file.write(data)
        self.file_registry.remember_folder(CAM_FOLDER_KEY, os.path.dirname(path))
        if os.path.basename(path).lower() != cam_file_name(effect_id):
            self.status_label.setText(self.status_label.text() + f" - {os.path.basename(path)} written: "
                                      f"FFNx only reads it named {cam_file_name(effect_id)}.")
        return True

    # ------------------------------------------------------------------ list
    def _fill_list(self):
        row = self.effect_list.currentRow()
        self.effect_list.blockSignals(True)
        self.effect_list.clear()
        for effect_id in self.manager.effect_ids():
            kind = self.manager.camera_kind(effect_id)
            item = QListWidgetItem(self._item_text(effect_id))
            item.setData(Qt.ItemDataRole.UserRole, effect_id)
            if kind != "track":
                item.setForeground(QBrush(QColor("gray")))
                item.setToolTip(_NO_TRACK_TEXT[kind])
            self.effect_list.addItem(item)
        self.effect_list.blockSignals(False)
        if self.effect_list.count():
            self.effect_list.setCurrentRow(max(0, row))

    def _item_text(self, effect_id):
        track = self.manager.track(effect_id)
        mark = "* " if track is not None and track.modified else ""
        suffix = {"track": "", "file": " (file camera)", "none": " (no exe track)"}[
            self.manager.camera_kind(effect_id)]
        if track is not None and not track.fits_exe:
            suffix = " (.bcam only)"
        return f"{mark}{effect_id:3d} - {self.manager.effect_names.get(effect_id, '')}{suffix}"

    def _refresh_item(self, effect_id):
        for row in range(self.effect_list.count()):
            item = self.effect_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == effect_id:
                item.setText(self._item_text(effect_id))
                return

    def _selected_effect(self):
        item = self.effect_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def select_effect(self, effect_id):
        for row in range(self.effect_list.count()):
            if self.effect_list.item(row).data(Qt.ItemDataRole.UserRole) == effect_id:
                self.effect_list.setCurrentRow(row)
                return
        self.effect_list.setCurrentRow(-1)

    # ------------------------------------------------------------------ details
    def _update_status(self):
        if not self.manager.loaded:
            self.status_label.setText("Open the FF8 exe with Import to read its 221 effect camera tracks "
                                      "(EN, FR, DE, IT or ES 2013 Steam exe). Save writes a .hext.")
            return
        modified = len(self.manager.modified_tracks())
        resized = len(self.manager.resized_tracks())
        resized_text = f" ({resized} resized: .bcam only)" if resized else ""
        self.status_label.setText(f"{self.manager.language_name} exe: {len(self.manager.tracks)} camera tracks, "
                                  f"{modified} changed{resized_text}. Save writes a .hext for the "
                                  f"{self.manager.language_name} exe only (the addresses differ between "
                                  "languages); Export .bcam… writes one effect for FFNx, any language.")

    def _show_selected(self, *_args):
        effect_id = self._selected_effect()
        if effect_id is None:
            self._set_editors_enabled(False)
            self._set_collection_widget(None)
            self._set_script_texts("", "")
            self.preview.set_track(None)
            return
        name = self.manager.effect_names.get(effect_id, "")
        track = self.manager.track(effect_id)
        kind = self.manager.camera_kind(effect_id)
        self._set_editors_enabled(track is not None)
        if track is None:
            if kind == "track":
                text = f"<b>Effect {effect_id} - {name}</b><br>Open the FF8 exe to edit its camera track."
            else:
                text = f"<b>Effect {effect_id} - {name}</b><br>{_NO_TRACK_TEXT[kind]}"
            self.info_label.setText(text)
            self.size_warning.hide()
            self._set_collection_widget(None)
            self._set_script_texts("", "")
            self.preview.set_track(None)
            return
        self._update_info(track)
        self._set_collection_widget(track)
        self._set_script_texts(self.manager.script_code(track), self.manager.script_text(track))
        self.preview.set_track(track)

    def _update_info(self, track):
        name = self.manager.effect_names.get(track.effect_id, "")
        same = ", ".join(f"{other} {self.manager.effect_names.get(other, '')}" for other in track.same_as)
        same_text = (f"<br>Same bytes in the exe as: {same} (separate copies: editing this one only "
                     "changes this effect)") if same else ""
        size = (f"{track.size} bytes" if track.fits_exe
                else f"{track.size} bytes in the exe, now {track.current_size}")
        self.info_label.setText(
            f"<b>Effect {track.effect_id} - {name}</b> &nbsp; <code>{track.label}</code><br>"
            f"Track at 0x{track.address:X} ({self.manager.language_name} exe), {size}: "
            f"script {len(track.script)} bytes, {track.keyframe_count()} keyframes. "
            f"Pushed by the effect's code at 0x{track.push_operand - 1:X}.{same_text}")
        self.size_warning.setText(
            f"⚠ This camera is now {track.current_size} bytes, its room in the exe is {track.size}: "
            "the vanilla exe cannot use it, so it is left out of the .hext. Export it with Export .bcam… - "
            "FFNx plays .bcam files of any size.")
        self.size_warning.setVisible(not track.fits_exe)

    def _set_editors_enabled(self, enabled):
        self.reset_button.setEnabled(enabled)
        self.export_cam_button.setEnabled(enabled)
        self.apply_script_button.setEnabled(enabled)
        self.script_editor.setReadOnly(not enabled)

    def _set_collection_widget(self, track, expanded_sets=()):
        self._collection_widget = None
        if track is None:
            placeholder = QLabel("")
            self.keyframe_scroll.setWidget(placeholder)
            return
        widget = CameraCollectionWidget(track.collection, structure_edits=True, expanded_sets=expanded_sets)
        widget.data_changed.connect(self._on_keyframes_changed)
        widget.collection_rebuilt.connect(self._on_collection_rebuilt)
        widget.preview_requested.connect(self.preview.preview_animation)
        self._collection_widget = widget
        self.keyframe_scroll.setWidget(widget)

    def _set_script_texts(self, code, description):
        self.script_editor.blockSignals(True)
        self.script_editor.setPlainText(code)
        self.script_editor.blockSignals(False)
        self.script_description.setPlainText(description)
        self._update_script_size()

    def _update_script_size(self):
        """Live 'used / room' byte count; Apply is off while the script is too long for the track."""
        track = self.manager.track(self._selected_effect())
        if track is None:
            self.script_size_label.setText("")
            return
        try:
            size = self.manager.script_size(self.script_editor.toPlainText())
        except ValueError:
            self.script_size_label.setStyleSheet("color: red;")
            self.script_size_label.setText(f"Not valid code - room: {track.script_room} bytes")
            self.apply_script_button.setEnabled(True)  # Apply tells which line is wrong
            return
        longer = size > track.script_room
        self.script_size_label.setStyleSheet("color: #c77800;" if longer else "")
        if longer:
            text = (f"{size} / {track.script_room} bytes: {size - track.script_room} more than the exe has - "
                    "the track grows, only an FFNx .bcam file can use it")
        elif size < track.script_room:
            text = f"{size} / {track.script_room} bytes (Apply fills the {track.script_room - size} left)"
        else:
            text = f"{size} / {track.script_room} bytes"
        self.script_size_label.setText(text)
        self.apply_script_button.setEnabled(True)

    # ------------------------------------------------------------------ edits
    def _on_keyframes_changed(self):
        self._track_edited(self._selected_effect())
        self.preview.refresh()

    def _on_collection_rebuilt(self, data):
        """A keyframe or slot was added/removed: the track takes the new collection (its size may
        change) and the editor is rebuilt where it was."""
        effect_id = self._selected_effect()
        track = self.manager.track(effect_id)
        if track is None:
            return
        expanded = self._collection_widget.expanded_set_indices() if self._collection_widget else ()
        scroll = self.keyframe_scroll.verticalScrollBar().value()
        track.set_collection(data)
        self._set_collection_widget(track, expanded)
        self.keyframe_scroll.verticalScrollBar().setValue(scroll)
        self._track_edited(effect_id)
        self.preview.set_track(track)  # new animation objects: run the script again

    def _apply_script(self):
        effect_id = self._selected_effect()
        track = self.manager.track(effect_id)
        if track is None:
            return
        try:
            self.manager.set_script_code(track, self.script_editor.toPlainText())
        except ValueError as error:
            QMessageBox.warning(self, "Camera effect editor", f"The script was not applied:\n{error}")
            return
        self._set_script_texts(self.manager.script_code(track), self.manager.script_text(track))
        self._track_edited(effect_id)
        self.preview.set_track(track)  # the script may now choose another animation

    def _reset_selected(self):
        effect_id = self._selected_effect()
        if self.manager.track(effect_id) is None:
            return
        self.manager.reset_track(effect_id)
        self._show_selected()
        self._track_edited(effect_id)

    def _track_edited(self, effect_id):
        self._refresh_item(effect_id)
        self._update_status()
        track = self.manager.track(effect_id)
        if track is not None and effect_id == self._selected_effect():
            self._update_info(track)
        self.modified_changed.emit()

    def _after_tracks_changed(self):
        self._fill_list()
        self._update_status()
        self._show_selected()
        self.modified_changed.emit()
