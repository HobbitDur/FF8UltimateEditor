import os

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                             QPushButton, QSplitter, QMessageBox, QFileDialog, QComboBox, QMenu)

from Common.filebinding import FileBinding
from Fujin.cameraeffectmanager import (CAM_FFNX_FOLDER, CREATABLE_CAMERA_EFFECTS, DEFAULT_CAMERA_SOURCE,
                                       CameraEffectManager, cam_file_name)
from Fujin.cameraeffectpreview import CameraEffectPreview
from Common.cameratrackeditor import CameraTrackEditor
from SmallWidget.listsearchbar import ListSearchBar

HEXT_FOLDER_KEY = "camera effect .hext"
CAM_FOLDER_KEY = "camera effect .bcam"
CAM_SELECTION_KEY = "camera effect .bcam files"   # the .bcam files last imported, reloaded by Import previous
ANIM_SET_FOLDER_KEY = "battle anim set .animset"

_NO_TRACK_TEXT = {
    "file": "This effect uses a file camera: its camera data or commands are stored in a loaded "
            "cinematic file. Some files embed a normal camera track; others drive the view with "
            "cinematic commands. This tab only edits and previews tracks stored in the exe.",
    "none": "This effect never starts a camera track (no Battle_PlayCameraAnimation call). With "
            "the Item command the battle view stays as it is; with Magic or a command that "
            "opened on the caster, the camera stays on the caster for the whole effect "
            "(e.g. 5 Phoenix Down, 7 Mega Phoenix). Some effects move the camera with their own code.",
}
_NOT_CREATABLE_TEXT = (
    "No camera can be created here: an effect with no track may move the camera with its own code "
    "(GF summons, Shot, Duel, Zell's finishers, Angelo, Gilgamesh...), and FFNx would start the created "
    "camera on top of it. Only the items and commands known to start no camera at all can get one: "
    + ", ".join(str(effect) for effect in CREATABLE_CAMERA_EFFECTS) + ".")


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
        self.game_data = game_data
        self.manager = CameraEffectManager(game_data)
        self.exe_binding = FileBinding("FF8 exe", file_registry, load_callback=self.load_exe,
                                       file_filter="*.exe")
        self.exe_binding.file_closed.connect(lambda _path: self._close_exe())
        # The unsaved-changes '*' follows the tracks' real state (modified_changed), not every
        # keystroke in the script editor before Apply.
        self.setProperty("read_only_preview", True)
        self.preview = CameraEffectPreview(self.manager, file_registry)
        self.track_editor = CameraTrackEditor(self.manager, self.preview)
        self.track_editor.keyframes_changed.connect(lambda: self._track_edited(self._selected_effect()))
        self.track_editor.track_changed.connect(lambda: self._track_edited(self._selected_effect()))
        self.tabs = self.track_editor.tabs
        self.keyframe_scroll = self.track_editor.keyframe_scroll
        self.script_editor = self.track_editor.script_editor
        self.apply_script_button = self.track_editor.apply_script_button
        self.script_size_label = self.track_editor.script_size_label
        self.script_description = self.track_editor.script_description

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
        # An effect that starts no camera (items, commands) can be given one, .bcam only
        self.create_source = QComboBox()
        self.create_source.setToolTip("What the new camera starts as: a copy of another effect's camera track "
                                      "(with its edits), or a minimal one (slot 0 played, 2 keyframes)")
        self.create_button = QPushButton("Create a camera")
        self.create_button.setToolTip(
            "Give this effect a camera of its own. It has no place in the exe: Save writes it as\n"
            f"{CAM_FFNX_FOLDER}/effect_NNN.bcam, which FFNx starts right after the effect starts.")
        self.create_button.clicked.connect(lambda: self.create_camera())
        create_row = QHBoxLayout()
        create_row.addWidget(QLabel("Start from:"))
        create_row.addWidget(self.create_source, 1)
        create_row.addWidget(self.create_button)
        self.create_box = QWidget()
        self.create_box.setLayout(create_row)
        self.create_box.hide()
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

        details = QWidget()
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.addLayout(info_row)
        details_layout.addWidget(self.create_box)
        details_layout.addWidget(self.size_warning)
        details_layout.addWidget(self.track_editor, 1)

        splitter = QSplitter()
        splitter.addWidget(self.effect_search.column)
        splitter.addWidget(details)
        splitter.addWidget(self.preview)
        if embedded:
            self.effect_search.column.hide()
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 1)

        # FFNx True30FPS plays every battle camera at 30 Hz and expects every file converted
        self.convert_30fps_button = QPushButton("All to 30 fps…")
        self.convert_30fps_button.setToolTip(
            "Convert every camera track (the exe's, the created ones, the .bcam read back) for FFNx\n"
            "True30FPS, which plays every battle camera at 30 Hz with no marker: every keyframe\n"
            "duration doubles, a one-frame script wait is repeated. Vanilla tracks keep their size:\n"
            "Save writes them in the .hext, Export all .bcam… as FFNx files. Convert once.")
        self.convert_30fps_button.clicked.connect(lambda: self.convert_all_to_30fps())
        self.export_all_button = QPushButton("Export all .bcam…")
        self.export_all_button.setToolTip(
            f"Write every changed camera track as effect_NNN.bcam into a folder (FFNx reads them from the\n"
            f"game folder's {CAM_FFNX_FOLDER}/, any exe language).")
        self.export_all_button.clicked.connect(lambda: self.export_all_cam())
        # The limit break / Blue Magic... anim sets of the exe, as FFNx effect_NNN.animset files
        self.export_anim_sets_button = QPushButton("Export anim sets…")
        self.export_anim_sets_button.setToolTip(
            "Write the exe's 72 battle anim sets (limit breaks, Blue Magic cast, Shot, Duel, Angelo...) as\n"
            f"effect_NNN.animset files, which FFNx binds instead of the exe's (game folder's {CAM_FFNX_FOLDER}/,\n"
            "any size, any exe language). Converted to 30 fps: 2n frames per animation, sequences rewritten\n"
            "for FFNx True30FPS, animations over 255 frames split.")
        anim_set_menu = QMenu(self.export_anim_sets_button)
        anim_set_menu.addAction("As in the exe…", lambda: self.export_anim_sets(convert=False))
        anim_set_menu.addAction("Converted to 30 fps (FFNx True30FPS)…", lambda: self.export_anim_sets(convert=True))
        self.export_anim_sets_button.setMenu(anim_set_menu)
        status_row = QHBoxLayout()
        status_row.addWidget(self.status_label, 1)
        status_row.addWidget(self.convert_30fps_button)
        status_row.addWidget(self.export_all_button)
        status_row.addWidget(self.export_anim_sets_button)

        layout = QVBoxLayout()
        layout.addLayout(status_row)
        layout.addWidget(splitter, 1)
        self.setLayout(layout)

        self._fill_list()
        self._update_status()
        self.effect_list.setCurrentRow(0)

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

    def convert_all_to_30fps(self, confirm=True) -> list:
        """Every loaded camera track converted for FFNx True30FPS (CameraEffectManager.convert_tracks_to_real30)."""
        title = "Camera tracks to 30 fps (FFNx)"
        if not self.manager.tracks:
            if confirm:
                QMessageBox.information(self, title, "Open the FF8 exe (or import .bcam files) first.")
            return []
        if confirm and QMessageBox.question(
                self, title, f"Convert the {len(self.manager.tracks)} camera tracks for FFNx True30FPS? Every "
                "keyframe duration doubles. Convert vanilla tracks only once: converting twice doubles "
                "again.") != QMessageBox.StandardButton.Yes:
            return []
        result = self.manager.convert_tracks_to_real30()
        self._after_tracks_changed()
        if confirm:
            done = [effect_id for effect_id, report, _message in result if report is not None]
            notes = [f"effect {effect_id}: {message}" for effect_id, _report, message in result if message]
            QMessageBox.information(self, title, "\n".join(
                [f"{len(done)} camera track(s) converted."] + notes[:30]
                + (["..."] if len(notes) > 30 else [])
                + ["Save writes the .hext (exe tracks that kept their size), Export all .bcam… the FFNx files."]))
        return result

    def export_all_cam(self, folder=None) -> list:
        """Write every changed track as effect_NNN.bcam into `folder` (asked when not given).
        Every file is checked before any is written. Returns the paths written."""
        title = "Export all .bcam"
        try:
            files = self.manager.all_cam_files()
        except ValueError as error:
            QMessageBox.warning(self, title, f"Nothing was written:\n{error}")
            return []
        if not files:
            QMessageBox.information(self, title, "No camera track was changed: nothing to export.")
            return []
        if not folder:
            folder = QFileDialog.getExistingDirectory(
                self, f"Folder for the .bcam files (FFNx: the game folder's {CAM_FFNX_FOLDER}/)",
                self.file_registry.last_folder(CAM_FOLDER_KEY) or os.getcwd())
        if not folder:
            return []
        written = []
        for name, data in files:
            path = os.path.join(folder, name)
            with open(path, "wb") as file:
                file.write(data)
            written.append(path)
        self.file_registry.remember_folder(CAM_FOLDER_KEY, folder)
        self.status_label.setText(self.status_label.text() + f" - {len(written)} .bcam file(s) written.")
        return written

    def export_anim_sets(self, convert=False, folder=None) -> list:
        """Write every anim set of the opened exe as effect_NNN.animset into `folder` (asked when not
        given), as is or converted to 30 fps. Every file is built and checked before any is written.
        Returns the paths written."""
        from FF8GameData.dat import exeanimset
        title = "Export anim sets"
        path = self.exe_binding.current_path
        if not path:
            QMessageBox.information(self, title, "Open the FF8 exe first.")
            return []
        with open(path, "rb") as file:
            anim_sets = exeanimset.read_exe_anim_sets(file.read())
        if not anim_sets:
            QMessageBox.warning(self, title, "No vanilla anim set was found in this exe.")
            return []
        files, _reports, error_list = exeanimset.build_export_files(anim_sets, convert, self.game_data)
        errors = [f"{info.file_name} ({info.label}): {error}" for info, error in error_list]
        if not folder:
            folder = QFileDialog.getExistingDirectory(
                self, f"Folder for the .animset files (FFNx: the game folder's {CAM_FFNX_FOLDER}/)",
                self.file_registry.last_folder(ANIM_SET_FOLDER_KEY) or os.getcwd())
        if not folder:
            return []
        written = []
        for name, data in files:
            file_path = os.path.join(folder, name)
            with open(file_path, "wb") as file:
                file.write(data)
            written.append(file_path)
        self.file_registry.remember_folder(ANIM_SET_FOLDER_KEY, folder)
        missing = len(exeanimset.ANIM_SETS) - len(anim_sets)
        lines = [f"{len(written)} anim set file(s) written" + (" (converted to 30 fps)" if convert else "") + "."]
        if missing:
            lines.append(f"{missing} vanilla set(s) not found in this exe (already changed?).")
        lines += errors[:20]
        (QMessageBox.warning if errors else QMessageBox.information)(self, title, "\n".join(lines))
        return written

    # ------------------------------------------------------------------ list
    def _fill_list(self):
        row = self.effect_list.currentRow()
        self.effect_list.blockSignals(True)
        self.effect_list.clear()
        for effect_id in self.manager.effect_ids():
            kind = self.manager.camera_kind(effect_id)
            item = QListWidgetItem(self._item_text(effect_id))
            item.setData(Qt.ItemDataRole.UserRole, effect_id)
            if kind not in ("track", "created"):
                item.setForeground(QBrush(QColor("gray")))
                item.setToolTip(_NO_TRACK_TEXT[kind])
            self.effect_list.addItem(item)
        self.effect_list.blockSignals(False)
        if self.effect_list.count():
            self.effect_list.setCurrentRow(max(0, row))

    def _item_text(self, effect_id):
        track = self.manager.track(effect_id)
        mark = "* " if track is not None and track.modified else ""
        suffix = {"track": "", "file": " (file camera)", "none": " (no exe track)", "created": " (.bcam camera)"}[
            self.manager.camera_kind(effect_id)]
        if track is not None and not track.created and not track.fits_exe:
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
        created = len(self.manager.created_tracks())
        modified = len(self.manager.modified_tracks()) - created
        resized = len(self.manager.resized_tracks()) - created
        resized_text = f" ({resized} resized: .bcam only)" if resized else ""
        created_text = f", {created} created camera{'s' if created > 1 else ''} (.bcam)" if created else ""
        self.status_label.setText(f"{self.manager.language_name} exe: {len(self.manager.tracks) - created} camera "
                                  f"tracks, {modified} changed{resized_text}{created_text}. Save writes a .hext for the "
                                  f"{self.manager.language_name} exe only (the addresses differ between "
                                  "languages); Export .bcam… writes one effect for FFNx, any language.")

    def _show_selected(self, *_args):
        effect_id = self._selected_effect()
        if effect_id is None:
            self._set_editors_enabled(False)
            self.track_editor.set_track(None)
            return
        name = self.manager.effect_names.get(effect_id, "")
        track = self.manager.track(effect_id)
        kind = self.manager.camera_kind(effect_id)
        self._set_editors_enabled(track is not None)
        self.create_box.setVisible(track is None and self.manager.can_create(effect_id))
        if track is None:
            if kind == "track":
                text = f"<b>Effect {effect_id} - {name}</b><br>Open the FF8 exe to edit its camera track."
            else:
                text = f"<b>Effect {effect_id} - {name}</b><br>{_NO_TRACK_TEXT[kind]}"
                if kind == "none":
                    text += "<br><br>" + (
                        "<b>It can be given a camera:</b> Create a camera (below) makes one for FFNx, which plays "
                        f"it from {CAM_FFNX_FOLDER}/{cam_file_name(effect_id)} right after the effect starts."
                        if self.manager.can_create(effect_id) else _NOT_CREATABLE_TEXT)
            self.info_label.setText(text)
            self.size_warning.hide()
            self.track_editor.set_track(None)
            self._fill_create_sources(effect_id)
            return
        self._update_info(track)
        self.track_editor.set_track(track)

    def _update_info(self, track):
        name = self.manager.effect_names.get(track.effect_id, "")
        self.reset_button.setText("Remove this camera" if track.created else "Reset to the exe values")
        self.reset_button.setToolTip("Delete the created camera: the effect starts no camera again" if track.created
                                     else "Undo every change made to this effect's camera track")
        if track.created:
            self.info_label.setText(
                f"<b>Effect {track.effect_id} - {name}</b> &nbsp; created camera<br>"
                f"No camera in the exe: FFNx starts this one from {CAM_FFNX_FOLDER}/{cam_file_name(track.effect_id)} "
                f"right after the effect starts (Save or Export .bcam… writes it). {track.current_size} bytes: script "
                f"{len(track.script)} bytes, {track.keyframe_count()} keyframes. The vanilla game, without FFNx, "
                "ignores it.")
            self.size_warning.hide()
            return
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
        self.track_editor.set_enabled(enabled)

    @property
    def _collection_widget(self):
        return self.track_editor._collection_widget

    # ------------------------------------------------------------------ edits
    def _apply_script(self):
        self.track_editor._apply_script()

    def _reset_selected(self):
        effect_id = self._selected_effect()
        track = self.manager.track(effect_id)
        if track is None:
            return
        if track.created and QMessageBox.question(
                self, "Camera effect editor", f"Remove the camera created for effect {effect_id}? Its edits are lost "
                "(a .bcam already written stays on disk).") != QMessageBox.StandardButton.Yes:
            return
        self.manager.reset_track(effect_id)
        self._show_selected()
        self._track_edited(effect_id)

    # ------------------------------------------------------------------ created cameras
    def _fill_create_sources(self, effect_id):
        self.create_source.clear()
        default = DEFAULT_CAMERA_SOURCE.get(effect_id)
        names = self.manager.effect_names
        exe_tracks = sorted(e for e, t in self.manager.tracks.items() if not t.created)
        if default in exe_tracks:
            self.create_source.addItem(f"Copy of {default} {names.get(default, '')} (suggested: same kind of cast)",
                                       default)
        self.create_source.addItem("Minimal camera: plays slot 0, one 2-keyframe shot", None)
        for other in exe_tracks:
            if other != default:
                self.create_source.addItem(f"Copy of {other} {names.get(other, '')}", other)
        if not exe_tracks:
            self.create_source.setToolTip("Open the FF8 exe (Import) to start from another effect's camera; "
                                          "without it only the minimal camera is offered.")

    def create_camera(self, source_effect="selected"):
        """Create the selected effect's camera from the chosen source (an effect id or None = minimal)."""
        effect_id = self._selected_effect()
        if effect_id is None or not self.manager.can_create(effect_id):
            return None
        if source_effect == "selected":
            source_effect = self.create_source.currentData()
        try:
            track = self.manager.create_track(effect_id, source_effect)
        except ValueError as error:
            QMessageBox.warning(self, "Camera effect editor", f"No camera created:\n{error}")
            return None
        self._fill_list()
        self.select_effect(effect_id)
        self._show_selected()
        self._track_edited(effect_id)
        return track

    # ------------------------------------------------------------------ .bcam import
    def import_bcam(self, paths=None):
        """Header Import: effect_NNN.bcam files (several at once) as their effects' cameras."""
        if paths is None:
            paths = QFileDialog.getOpenFileNames(self, "Import FFNx effect cameras (effect_NNN.bcam)",
                                                 self.file_registry.last_folder(CAM_FOLDER_KEY) or os.getcwd(),
                                                 "FFNx effect camera (*.bcam)")[0]
        if not paths:
            return [], []
        return self._load_bcam_paths(paths)

    def reload_bcam(self, paths):
        """Import previous: the .bcam files last imported, without changing the selected effect."""
        return self._load_bcam_paths(paths, select=False) if paths else ([], [])

    def _load_bcam_paths(self, paths, select=True):
        files = list(paths)
        loaded, refused = self.manager.load_bcam_files(files)
        self.file_registry.remember_folder(CAM_FOLDER_KEY, os.path.dirname(files[0]))
        refused_paths = {path for path, _reason in refused}
        self.file_registry.remember_files(CAM_SELECTION_KEY, [path for path in files if path not in refused_paths])
        self._after_tracks_changed()
        if loaded and select:
            self.select_effect(loaded[0])
        if refused:
            QMessageBox.warning(self, "Camera effect editor",
                                f"{len(loaded)} camera(s) loaded, {len(refused)} refused:\n"
                                + "\n".join(f"{os.path.basename(path)}: {reason}" for path, reason in refused[:20]))
        elif not loaded:
            QMessageBox.information(self, "Camera effect editor", "No effect_NNN.bcam file found.")
        return loaded, refused

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
