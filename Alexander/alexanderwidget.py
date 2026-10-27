"""Alexander: battle stage (a0stgXXX.x) viewer tool - the GUI part.

All parsing/logic lives in AlexanderManager (no Qt); this module only adapts
it to the Ifrit3D viewer (QPixmap textures) and provides the tool UI.

Two tabs: the 3D view of the stage, and its Camera - the camera section (intro cameras) in the
shared camera track editor (Common.cameratrackeditor: keyframes, slots and script), filmed by the
shared battle preview (Common.battlescenepreview) on this stage, with an encounter of scene.out and
the monster / party models opened as read-only side files.
"""

import os

from PIL.ImageQt import ImageQt
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
                             QListWidget, QFileDialog, QMessageBox, QSplitter, QCheckBox,
                             QTabWidget, QComboBox, QSizePolicy)

from Common.fileregistry import FileRegistry
from Common.autoimport import AutoImportSource
from Common.battlescenepreview import BattleScenePreview
from Common.battlesidefiles import BattleSideFiles
from Common.cameratrackeditor import CameraTrackEditor
from Common.filebinding import FileBinding
from FF8GameData.sceneout import EncounterRecord
from Ifrit.Ifrit3D.ifrit3dwidget import Ifrit3DWidget
from Alexander.alexandermanager import AlexanderManager
from SmallWidget.listsearchbar import ListSearchBar


class StageTextureData:
    """Duck-types Ifrit's TextureData: the 3D widget only reads texture_image."""

    def __init__(self, pil_image):
        self.texture_image = QPixmap.fromImage(ImageQt(pil_image.convert("RGBA")))
        self.palette_image = None


class ViewerBridge:
    """Adapts the pure-python AlexanderManager to what Ifrit3DWidget expects
    of an IfritManager (enemy, texture_data with QPixmaps, vertex getters)."""

    def __init__(self, manager: AlexanderManager):
        self._manager = manager
        self.texture_data = []

    def refresh_textures(self):
        self.texture_data = [StageTextureData(img)
                             for img in self._manager.visible_textures()]

    # attributes/methods the viewer reads, delegated to the manager
    @property
    def enemy(self):
        return self._manager.enemy

    @property
    def max_animation_frames(self):
        return self._manager.max_animation_frames

    @property
    def texture_black_is_transparent(self):
        return self._manager.texture_black_is_transparent

    @property
    def backface_cull_mode(self):
        """'all' (the Ifrit3DWidget default) does real per-face, eye-relative
        culling - correct for monsters, built for the game's one fixed camera
        direction. A battle stage is orbited freely, so the same geometry is
        seen from every angle: 'all' made faces pop in/out as the camera moved.
        'duplicates' still drops truly-coincident duplicate faces (kept to
        avoid z-fighting) without hiding single-layer stage geometry."""
        return "duplicates"

    def get_bone_rotation_gizmo(self, *args, **kwargs):
        """Battle stages have no posable skeleton; the bone_editor guard in
        Ifrit3DWidget._update_gizmo should already skip this call, but this stub
        keeps the bridge duck-type-complete in case that guard is ever bypassed."""
        return None

    def get_animated_vertices(self, *args, **kwargs):
        return self._manager.get_animated_vertices(*args, **kwargs)

    def get_skeleton_lines(self, *args, **kwargs):
        return self._manager.get_skeleton_lines(*args, **kwargs)

# Default framing for a battle stage: a tilted 3/4 aerial view (the stage floor
# lies in the viewer's X-Z plane with Y up, so the default rot_x=0 camera looks
# along -Z - straight into the floor plane, i.e. edge-on - and a large X tilt is
# what turns that flat "map" view into a readable arena) plus a fitted zoom that
# isn't miles away.
STAGE_ROT_X = 25.0
STAGE_ROT_Y = 0.0
STAGE_ZOOM_FACTOR = 1.6

# Ifrit3DWidget child widgets that only make sense for animated models; battle
# stages are static, so they are hidden.
_ANIM_WIDGETS = ("play_btn", "reset_anim_btn", "fps_label", "fps_slider", "cb_ground",
                 "frame_label", "frame_slider", "anim_label", "anim_selector",
                 "bone_editor", "playlist_container",
                 # The "Frames ▾" menu (frame/animation authoring + fps conversion) is meaningless
                 # for a static stage; "3D files ▾" holds the viewer's generic glTF import/export,
                 # and Alexander replaces the export with its own group-aware "Export .glb" (keeps
                 # the 4-group / sky structure) - so both dropdowns are hidden.
                 "anim_tools_btn", "files_btn")

BATTLE_FILES_KEY = "Alexander battle files"   # the Opened files entry of the preview's side files
SCENE_OUT = "scene.out"
STAGE_GROWTH_NOTE = ("the geometry section after it moves further in the file, and Save writes a .hext "
                     "giving FF8_EN.exe its new offset")
MAX_ENCOUNTERS_IN_NOTE = 6


class AlexanderWidget(QWidget):
    """Alexander: FF8 battle stage viewer (a0stgXXX.x)."""

    # Import/Save readiness changed (opening/importing a stage, not routed through the shared
    # toolbar's own Import handler) - tells the shared header toolbar to re-check can_save_folder.
    # Alexander has no FileBinding of its own (a0stgXXX.x has no fixed name, and several are
    # opened into an internal list at once), so it can't rely on the registry's file_changed signal
    # the way every other converted tool does.
    file_bindings_changed = pyqtSignal()
    # The one summary entry the opened stages have in the Opened files panel.
    REGISTRY_NAME = "Alexander battle stage(s)"

    def __init__(self, icon_path='Resources', settings=None, file_registry=None, game_data_folder="FF8GameData"):
        super().__init__()
        if file_registry is None:  # Used alone, it shares its files with nobody
            file_registry = FileRegistry()
        self.file_registry = file_registry
        file_registry.file_closed.connect(self._on_registry_file_closed)
        self.settings = settings
        self.manager = AlexanderManager(game_data_folder)
        self.bridge = ViewerBridge(self.manager)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        toolbar = QWidget()
        toolbar.setStyleSheet("background:#2a2a2f; padding:5px;")
        tl = QHBoxLayout(toolbar)
        tl.setContentsMargins(8, 4, 8, 4)

        # Open (one or more battle stages at once) and Save (.x) both run from the shared header
        # toolbar: Import calls open_files() below (no FileBinding fits a0stgXXX.x - it has no
        # fixed name and several are opened into the list at once); Save calls save_folder() (it
        # always needs a destination picker, even for an unedited stage, so it isn't a plain
        # single-file overwrite either).
        self.export_glb_btn = QPushButton("Export .glb")
        self.export_glb_btn.setStyleSheet("background:#4a6e8a; color:white; padding:4px 12px; border-radius:3px;")
        self.export_glb_btn.setToolTip("Export the whole stage to a .glb (all 4 groups kept as\n"
                                       "separate meshes named group0..sky_group3), editable in\n"
                                       "Blender and re-importable with the group structure intact.")
        self.export_glb_btn.clicked.connect(self._export_glb)
        self.export_glb_btn.setEnabled(False)
        tl.addWidget(self.export_glb_btn)

        self.import_glb_btn = QPushButton("Import .glb")
        self.import_glb_btn.setStyleSheet("background:#4a6e8a; color:white; padding:4px 12px; border-radius:3px;")
        self.import_glb_btn.setToolTip("Load a .glb file (e.g. one exported here and edited in\n"
                                       "Blender) back into the viewer. Its group tags are read\n"
                                       "back so Save can restore the group structure.")
        self.import_glb_btn.clicked.connect(self._import_glb)
        tl.addWidget(self.import_glb_btn)

        self.cb_sky = QCheckBox("Show sky dome")
        self.cb_sky.setChecked(False)
        # A stylesheet color applies to every state, so the disabled greying
        # must be spelled out explicitly (otherwise the text stays white).
        self.cb_sky.setStyleSheet(
            "QCheckBox { color: white; padding: 4px 8px; }"
            "QCheckBox:disabled { color: #666; }")
        self.cb_sky.setToolTip("The sky is a large dome that surrounds and hides the stage;\n"
                               "off by default so the stage geometry is visible.")
        self.cb_sky.toggled.connect(self._on_sky_toggle)
        self.cb_sky.setEnabled(False)   # no stage loaded yet
        tl.addWidget(self.cb_sky)

        self.file_label = QLabel("No stage loaded  -  Open a battle stage (.x) file")
        self.file_label.setStyleSheet("color:#aaa; padding:4px 8px;")
        tl.addWidget(self.file_label)
        tl.addStretch()
        main_layout.addWidget(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(0)
        title = QLabel("Stages")
        title.setStyleSheet("background:#2a2a2f; color:white; font-weight:bold; padding:4px 8px;")
        ll.addWidget(title)
        self.stage_list = QListWidget()
        self.stage_list.setStyleSheet("background:#1a1a1f; color:white; border:none;")
        self.stage_list.currentRowChanged.connect(self._on_stage_selected)
        self.stage_search = ListSearchBar(self.stage_list)
        self.stage_search.setStyleSheet("QLineEdit {background:#1a1a1f; color:white; border:1px solid #3a3a3f;}")
        ll.addWidget(self.stage_search)
        ll.addWidget(self.stage_list)

        self.viewer_3d = Ifrit3DWidget(self.bridge, show_controls=True)
        self._hide_animation_controls()
        # The viewer sits in its own page: it is hidden while no stage is open, and showing it must
        # not show it over the Camera tab
        view_page = QWidget()
        view_layout = QVBoxLayout(view_page)
        view_layout.setContentsMargins(0, 0, 0, 0)
        view_layout.addWidget(self.viewer_3d)
        self.tabs = QTabWidget()
        self.tabs.addTab(view_page, "3D view")
        self.tabs.addTab(self._build_camera_tab(game_data_folder), "Camera")

        splitter.addWidget(left)
        splitter.addWidget(self.tabs)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([200, 820])
        main_layout.addWidget(splitter, 1)

        self._stage_names = []
        self._show_camera()

    # ------------------------------------------------------------------ camera tab

    def _build_camera_tab(self, game_data_folder):
        """The stage's camera section in the shared track editor, filmed by the shared battle preview."""
        self.preview = BattleScenePreview(game_data_folder)
        self.battle_files = BattleSideFiles(self, self.file_registry, BATTLE_FILES_KEY, self.preview,
                                            patterns=("c0m*.dat", "d?c*.dat", "d?w*.dat"))
        self.preview.file_source = self._battle_file_path
        # scene.out (read only, edited in JumboCactuar): the encounters fought on this stage
        from JumboCactuar.jumbocactuarmanager import JumboCactuarManager
        self.scene = JumboCactuarManager()
        self.sceneout_binding = FileBinding(SCENE_OUT, self.file_registry, load_callback=self._on_sceneout_opened,
                                            file_filter=SCENE_OUT, read_only=True)
        self.sceneout_binding.file_closed.connect(self._on_sceneout_closed)

        self.camera_editor = CameraTrackEditor(self.manager, self.preview, room_name="stage file",
                                               growth_note=STAGE_GROWTH_NOTE, context="stage")
        self.camera_editor.keyframes_changed.connect(self._on_camera_edited)
        self.camera_editor.track_changed.connect(self._on_camera_edited)
        self.camera_info = QLabel()
        self.camera_info.setWordWrap(True)
        self.camera_info.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)
        self.camera_info.setToolTip(
            "The camera section holds the stage's intro cameras: scene.out bytes 0x02/0x03 of an encounter "
            "pick one animation (set = high nibble, slot = bits 0-2), main or secondary at random. Its "
            "script (Script tab) plays the animation of camera variable 0, that byte. FF8_EN.exe hardcodes "
            "where the camera and the geometry sections start: a camera that grows past its room pushes "
            "the geometry, and the exe then needs the .hext Save writes.")
        editor_side = QWidget()
        editor_layout = QVBoxLayout(editor_side)
        editor_layout.setContentsMargins(4, 4, 4, 4)
        editor_layout.addWidget(self.camera_info)
        editor_layout.addWidget(self.camera_editor, 1)

        self.encounter_combo = QComboBox()
        self.encounter_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.encounter_combo.setMinimumContentsLength(20)
        self.encounter_combo.setToolTip("The encounter the preview stands on this stage (scene.out, opened with "
                                        "Import read-only): its enemies, and its intro cameras to play")
        self.encounter_combo.currentIndexChanged.connect(self._show_preview_encounter)
        encounter_row = QHBoxLayout()
        encounter_row.addWidget(QLabel("Encounter:"))
        encounter_row.addWidget(self.encounter_combo, 1)
        preview_side = QWidget()
        preview_layout = QVBoxLayout(preview_side)
        preview_layout.setContentsMargins(4, 4, 4, 4)
        preview_layout.addLayout(encounter_row)
        preview_layout.addWidget(self.preview, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(editor_side)
        splitter.addWidget(preview_side)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        return splitter

    def _battle_file_path(self, name):
        """The preview's files: the opened stages, then the side files."""
        for stage_name, path in self.manager._folder_files.items():
            if os.path.basename(stage_name).lower() == name.lower():
                return path
        return self.battle_files.path(name)

    def _show_camera(self):
        """Show the current stage's camera track, its encounters and the preview on it."""
        self.camera_editor.set_track(self.manager.camera_track)
        self._fill_encounters()
        self._update_camera_info()

    def _stage_encounters(self):
        stage_id = self.manager.stage_id
        if stage_id is None or not self.scene.loaded:
            return []
        return [index for index, record in enumerate(self.scene.records) if record.stage_id == stage_id]

    def _fill_encounters(self):
        encounters = self._stage_encounters()
        self.encounter_combo.blockSignals(True)
        self.encounter_combo.clear()
        self.encounter_combo.addItem("(no encounter: the party only)" if self.scene.loaded else
                                     "(open scene.out with Import read-only for this stage's encounters)", None)
        for index in encounters:
            record = self.scene.records[index]
            cameras = ", ".join(f"{name} {record.camera(i)[0]}/{record.camera(i)[1]}"
                                for i, name in enumerate(("main", "secondary")))
            self.encounter_combo.addItem(f"{self.scene.summary(index)}  ·  intro {cameras}", index)
        self.encounter_combo.setCurrentIndex(1 if encounters else 0)
        self.encounter_combo.blockSignals(False)
        self.camera_editor.set_slot_notes(self._slot_notes(encounters))
        self._show_preview_encounter()

    def _slot_notes(self, encounters):
        """(set, slot) -> 'intro of encounter 12 (main), 13 (secondary)' for this stage's encounters."""
        users = {}
        for index in encounters:
            record = self.scene.records[index]
            for camera, name in enumerate(("main", "secondary")):
                users.setdefault(record.camera(camera), []).append(f"{index} ({name})")
        notes = {}
        for key, names in users.items():
            shown = names[:MAX_ENCOUNTERS_IN_NOTE] + ([f"+{len(names) - MAX_ENCOUNTERS_IN_NOTE}"]
                                                      if len(names) > MAX_ENCOUNTERS_IN_NOTE else [])
            notes[key] = "intro of encounter " + ", ".join(shown)
        return notes

    def _show_preview_encounter(self, _index=None):
        if self.manager.stage_id is None:
            self.preview.show_encounter(None)
            return
        index = self.encounter_combo.currentData()
        if index is None:
            record = EncounterRecord()
            record.stage_id = self.manager.stage_id
        else:
            record = self.scene.records[index]
        self.preview.show_encounter(record, index)

    def _on_sceneout_opened(self, path):
        try:
            self.scene.load_file(path)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Alexander", f"Could not read {path}:\n{error}")
            return
        self._fill_encounters()

    def _on_sceneout_closed(self, _path):
        from JumboCactuar.jumbocactuarmanager import JumboCactuarManager
        self.scene = JumboCactuarManager()
        self._fill_encounters()

    def _on_camera_edited(self):
        self._update_camera_info()
        self._refresh_stage_marks()
        self.file_bindings_changed.emit()   # Save may now have something to write

    def _update_camera_info(self):
        layout = self.manager.camera_layout() if self.manager.current_stage_path else None
        if layout is None:
            self.camera_info.setText("No battle stage camera: open an a0stgNNN.x stage." if not self.manager.is_loaded
                                     else "This file is not a known battle stage (a0stgNNN.x): no camera to edit.")
            return
        size, room, geometry = layout
        text = f"Camera section: {size} bytes, {room} bytes of room before the geometry section."
        if size > room:
            name = os.path.splitext(os.path.basename(self.manager.current_stage_path))[0]
            text += (f" It grew {size - room} bytes: Save moves the geometry section to {geometry} and writes "
                     f"{name}.hext, which FF8_EN.exe needs (FFNx hext) to read this stage.")
        else:
            text += " The geometry section stays where FF8_EN.exe reads it."
        self.camera_info.setText(text)

    def _refresh_stage_marks(self):
        """'* ' before the stages whose camera has unsaved edits."""
        modified = set(self.manager.modified_camera_paths())
        for row, name in enumerate(self._stage_names):
            item = self.stage_list.item(row)
            if item is not None:
                item.setText(("* " if self.manager._folder_files.get(name) in modified else "") + name)

    # ------------------------------------------------------------------ side files

    def file_bindings(self):
        """scene.out, read only (the encounters the Camera preview shows). The stages themselves are
        opened with open_files (no fixed name)."""
        return [self.sceneout_binding]

    def complementary_entries(self):
        """The header's Import read-only menu: scene.out and the models the Camera preview draws."""
        return [("Encounters: scene.out", self._import_sceneout)] + self.battle_files.entries()

    def _import_sceneout(self):
        path = self.sceneout_binding.open_dialog(self, default_dir=self.file_registry.last_folder(SCENE_OUT))
        if path:
            self.file_registry.remember_folder(SCENE_OUT, os.path.dirname(path))

    def load_folder(self, folder):
        """The header's Open folder: its battle stages, and the models the Camera preview draws
        (scene.out is found by the shared folder scan)."""
        stages = []
        for root, _folders, names in os.walk(folder):
            stages += [os.path.join(root, name) for name in names
                       if name.lower().startswith("a0stg") and name.lower().endswith(".x")]
        if stages:
            self.open_files(sorted(stages))
        self.battle_files.load_folder(folder)

    # ------------------------------------------------------------------ helpers

    def _hide_animation_controls(self):
        """Battle stages are static: remove the animation UI from the viewer.
        Disabling (not just hiding) bone_editor matters: Ifrit3DWidget._update_gizmo()
        gates on bone_editor.isEnabled() to decide whether to ask the manager for a
        rotation gizmo, and Alexander's ViewerBridge has no bones/animation frames to
        answer that with."""
        for attr in _ANIM_WIDGETS:
            w = getattr(self.viewer_3d, attr, None)
            if w is not None:
                w.hide()
                w.setEnabled(False)

    def _frame_stage(self):
        """Apply Alexander's default camera after a load (the viewer's own
        reset_view leaves the flat stage edge-on and zoomed too far out)."""
        gl = self.viewer_3d.gl_widget
        gl.rot_x = STAGE_ROT_X
        gl.rot_y = STAGE_ROT_Y
        gl.reference_position = [float(c) for c in gl.MODEL_CENTER]
        gl.zoom = float(gl.MODEL_SIZE) * STAGE_ZOOM_FACTOR
        gl.pan_x = gl.pan_y = 0.0
        gl.update()

    _CAMERA_ATTRS = ("rot_x", "rot_y", "zoom", "pan_x", "pan_y", "reference_position")

    def _save_camera(self):
        gl = self.viewer_3d.gl_widget
        return {a: getattr(gl, a, None) for a in self._CAMERA_ATTRS}

    def _restore_camera(self, cam):
        gl = self.viewer_3d.gl_widget
        for a, v in cam.items():
            if v is not None:
                setattr(gl, a, list(v) if a == "reference_position" else v)
        gl.update()

    def _load_into_viewer(self, keep_view: bool = False):
        self.viewer_3d.show()  # hidden while no stage is open (see _close_stages)
        cam = self._save_camera() if keep_view else None
        self.bridge.refresh_textures()
        self.viewer_3d.load_file()
        if keep_view and cam:
            self._restore_camera(cam)
        else:
            self._frame_stage()

    def _last_dir(self) -> str:
        if self.settings:
            return self.settings.value("alexander/last_dir", defaultValue="", type=str)
        return ""

    def _save_last_dir(self, path: str):
        if self.settings:
            self.settings.setValue("alexander/last_dir", path if os.path.isdir(path)
                                   else os.path.dirname(path))

    # ------------------------------------------------------------------ actions

    def auto_import_sources(self):
        return [AutoImportSource(self.REGISTRY_NAME, ("a0stg*.x",), self.open_files,
                                 selection_only=True),
                AutoImportSource.for_binding(self.sceneout_binding, self.file_registry.last_folder(SCENE_OUT)),
                self.battle_files.auto_import_source()]

    def open_files(self, file_paths=None):
        """Open one or more battle stage files at once (the shared header Import button calls
        this - a0stgXXX.x has no fixed name, and several are loaded into the list together)."""
        if file_paths is None:
            file_paths, _ = QFileDialog.getOpenFileNames(
                self, "Open battle stage file(s)", self._last_dir(),
                "Battle stage (a0stg*.x);;All files (*)")
        if not file_paths:
            return
        if self.manager.modified_camera_paths() and QMessageBox.question(
                self, "Alexander", "Some stage cameras have unsaved edits. Open other stages and drop them?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self.manager.camera_tracks.clear()   # the new list's cameras are read from its files
        self._save_last_dir(file_paths[0])
        self.file_registry.remember_files(self.REGISTRY_NAME, file_paths)
        names = self.manager.open_files(file_paths)
        self._stage_names = names
        self.stage_list.blockSignals(True)
        self.stage_list.clear()
        self.stage_list.addItems(names)
        self.stage_list.blockSignals(False)
        self.file_label.setText(
            f"{len(names)} stage{'s' if len(names) != 1 else ''} loaded")
        self.stage_search.select_first_match()  # Row 0, or the first match if a search is typed in
        # a0stgXXX.x has no fixed name, so it can't have its own FileBinding - list it under one
        # summary entry in the Opened files panel instead (each name when there are few, otherwise
        # just the count and folder, so opening dozens at once doesn't flood the panel).
        self.file_registry.open_file(
            self.REGISTRY_NAME, FileRegistry.summarize_paths(file_paths, "stage"))

    def _export_glb(self):
        if not self.manager.is_loaded:
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export stage to glTF", self._last_dir(),
            "glTF binary (*.glb);;All files (*)")
        if not file_path:
            return
        self._save_last_dir(file_path)
        try:
            self.manager.export_glb(file_path)
        except Exception as e:
            QMessageBox.critical(self, "Alexander", f"Could not export {file_path}:\n{e}")
            return
        QMessageBox.information(self, "Alexander",
                               f"Exported to {os.path.basename(file_path)}")

    def save_folder(self):
        """Write the current stage back to its a0stgXXX.x (the shared header Save button calls
        this), and every other opened stage whose camera was edited. Writes straight back to the
        loaded file, no dialog - unless there is none to write back to (only a .glb was imported,
        with no original .x of its own), in which case it asks where to save."""
        if not self.manager.can_save:
            QMessageBox.warning(self, "Alexander", "Nothing to save yet.")
            return
        others = [path for path in self.manager.modified_camera_paths() if path != self.manager.current_stage_path]
        notes = []
        for path in others:
            try:
                notes.append(f"{os.path.basename(path)}: {self.manager.save_camera(path)}")
            except Exception as e:
                QMessageBox.critical(self, "Alexander", f"Could not save {path}:\n{e}")
                return
        file_path = self.manager.current_stage_path
        if not file_path:
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Save battle stage", self._last_dir(),
                "Battle stage (*.x);;All files (*)")
            if not file_path:
                return
            self._save_last_dir(file_path)
        try:
            note = self.manager.save(file_path)
        except Exception as e:
            QMessageBox.critical(self, "Alexander", f"Could not save {file_path}:\n{e}")
            return
        self._unsaved_import = False
        self.preview.files_changed(reload=True)   # the saved stage is read again
        self._refresh_stage_marks()
        self._update_camera_info()
        self.file_bindings_changed.emit()
        QMessageBox.information(self, "Alexander",
                               "\n\n".join([f"{os.path.basename(file_path)}\n\n{note}"] + notes))

    def _import_glb(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import a glTF binary", self._last_dir(),
            "glTF binary (*.glb);;All files (*)")
        if not file_path:
            return
        self._save_last_dir(file_path)
        try:
            self.manager.load_glb(file_path)
        except Exception as e:
            QMessageBox.critical(self, "Alexander", f"Could not import {file_path}:\n{e}")
            return
        self._unsaved_import = True   # the imported mesh exists only here until it is saved
        self._stage_names = []
        self.stage_list.blockSignals(True)
        self.stage_list.clear()
        self.stage_list.blockSignals(False)
        self.file_label.setText(f"{os.path.basename(file_path)}  (imported glb)")
        self._update_sky_button()
        self._load_into_viewer()
        self._show_camera()

    def _on_sky_toggle(self, checked: bool):
        self.manager.set_show_sky(checked)
        if self.manager.is_loaded:
            self._load_into_viewer(keep_view=True)   # toggling sky keeps the camera

    def _update_sky_button(self):
        """Enable the sky toggle only when the stage actually has a sky dome."""
        self.export_glb_btn.setEnabled(self.manager.is_loaded)
        has_sky = self.manager.has_sky()
        self.cb_sky.setEnabled(has_sky)
        if not has_sky:
            self.cb_sky.blockSignals(True)
            self.cb_sky.setChecked(False)
            self.cb_sky.blockSignals(False)
        self.cb_sky.setToolTip(
            "The sky is a large dome that surrounds and hides the stage;\n"
            "off by default so the stage geometry is visible."
            if has_sky else "This stage has no separate sky dome.")
        # can_save may have just flipped true (a stage/mesh is now loaded): let the shared header
        # toolbar re-check can_save_folder (see the file_bindings_changed docstring above).
        self.file_bindings_changed.emit()

    def _on_registry_file_closed(self, file_name, _path):
        """The stages were removed from the Opened files panel: drop them all."""
        if file_name == self.REGISTRY_NAME:
            self._close_stages()

    def _close_stages(self):
        self._unsaved_import = False
        self.manager.close()
        self._stage_names = []
        self.stage_list.blockSignals(True)
        self.stage_list.clear()
        self.stage_list.blockSignals(False)
        self.file_label.setText("No stage loaded  -  Open a battle stage (.x) file")
        self._update_sky_button()
        self.viewer_3d.hide()  # it would keep drawing the last stage; shown again on the next load
        self._show_camera()
        self.file_bindings_changed.emit()

    def can_save_folder(self):
        """Whether there is a loaded stage/mesh the shared header Save button can write."""
        return self.manager.can_save

    def has_unsaved_changes(self):
        """An imported .glb mesh, or an edited camera, is an edit until it is saved."""
        return getattr(self, "_unsaved_import", False) or bool(self.manager.modified_camera_paths())

    def _on_stage_selected(self, row: int):
        if row < 0 or row >= len(self._stage_names):
            return
        try:
            self.manager.load_stage_by_name(self._stage_names[row])
        except Exception as e:
            QMessageBox.warning(self, "Alexander", f"Could not load this stage:\n{e}")
            return
        self._update_sky_button()
        self._load_into_viewer()
        self._show_camera()
