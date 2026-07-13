"""Alexander: battle stage (a0stgXXX.x) viewer tool - the GUI part.

All parsing/logic lives in AlexanderManager (no Qt); this module only adapts
it to the Ifrit3D viewer (QPixmap textures) and provides the tool UI.
"""

import os

from PIL.ImageQt import ImageQt
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
                             QListWidget, QFileDialog, QMessageBox, QSplitter, QCheckBox)

from Ifrit.Ifrit3D.ifrit3dwidget import Ifrit3DWidget
from Alexander.alexandermanager import AlexanderManager


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

    def get_animated_vertices(self, *args, **kwargs):
        return self._manager.get_animated_vertices(*args, **kwargs)

    def get_skeleton_lines(self, *args, **kwargs):
        return self._manager.get_skeleton_lines(*args, **kwargs)

# Default framing for a battle stage: a tilted 3/4 aerial view (the stage floor
# lies in the viewer's X-Y plane, so a large X tilt turns the flat "map" view
# into a readable arena) plus a fitted zoom that isn't miles away.
STAGE_ROT_X = 25.0
STAGE_ROT_Y = 180.0
STAGE_ZOOM_FACTOR = 1.6

# Ifrit3DWidget child widgets that only make sense for animated models; battle
# stages are static, so they are hidden.
_ANIM_WIDGETS = ("play_btn", "reset_anim_btn", "fps_label", "fps_slider",
                 "frame_label", "frame_slider", "anim_label", "anim_selector",
                 "fps60_btn", "fps60_all_btn", "bone_editor", "playlist_container",
                 # the viewer's generic glTF export is replaced by Alexander's own
                 # group-aware "Export .glb" (keeps the 4-group / sky structure).
                 "export_gltf_btn")


class AlexanderWidget(QWidget):
    """Alexander: FF8 battle stage viewer (a0stgXXX.x)."""

    def __init__(self, icon_path='Resources', settings=None):
        super().__init__()
        self.settings = settings
        self.manager = AlexanderManager()
        self.bridge = ViewerBridge(self.manager)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        toolbar = QWidget()
        toolbar.setStyleSheet("background:#2a2a2f; padding:5px;")
        tl = QHBoxLayout(toolbar)
        tl.setContentsMargins(8, 4, 8, 4)

        self.open_x_btn = QPushButton("Open battle stage(s)...")
        self.open_x_btn.setStyleSheet("background:#6a8a4e; color:white; padding:4px 12px; border-radius:3px;")
        self.open_x_btn.setToolTip("Open one or more battle stage files directly (a0stgXXX.x),\n"
                                   "e.g. extracted with Deling. Select several to switch\n"
                                   "between them in the list on the left.")
        self.open_x_btn.clicked.connect(self._open_files)
        tl.addWidget(self.open_x_btn)

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

        self.save_btn = QPushButton("Save .x")
        self.save_btn.setStyleSheet("background:#8a6a4e; color:white; padding:4px 12px; border-radius:3px;")
        self.save_btn.setToolTip("Write the current stage to an a0stgXXX.x file.\n"
                                 "An unedited loaded stage is written byte-for-byte; an\n"
                                 "imported/edited mesh is re-encoded into the last loaded\n"
                                 "stage's camera and texture template.")
        self.save_btn.clicked.connect(self._save_x)
        self.save_btn.setEnabled(False)
        tl.addWidget(self.save_btn)

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
        ll.addWidget(self.stage_list)

        self.viewer_3d = Ifrit3DWidget(self.bridge, show_controls=True)
        self._hide_animation_controls()

        splitter.addWidget(left)
        splitter.addWidget(self.viewer_3d)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([200, 820])
        main_layout.addWidget(splitter, 1)

        self._stage_names = []

    # ------------------------------------------------------------------ helpers

    def _hide_animation_controls(self):
        """Battle stages are static: remove the animation UI from the viewer."""
        for attr in _ANIM_WIDGETS:
            w = getattr(self.viewer_3d, attr, None)
            if w is not None:
                w.hide()

    def _frame_stage(self):
        """Apply Alexander's default camera after a load (the viewer's own
        reset_view leaves the flat stage edge-on and zoomed too far out)."""
        gl = self.viewer_3d.gl_widget
        gl.rot_x = STAGE_ROT_X
        gl.rot_y = STAGE_ROT_Y
        try:
            gl.reference_position = [float(c) for c in gl.MODEL_CENTER]
            gl.zoom = float(gl.MODEL_SIZE) * STAGE_ZOOM_FACTOR
        except Exception:
            pass
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

    def _open_files(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Open battle stage file(s)", self._last_dir(),
            "Battle stage (a0stg*.x);;All files (*)")
        if not file_paths:
            return
        self._save_last_dir(file_paths[0])
        names = self.manager.open_files(file_paths)
        self._stage_names = names
        self.stage_list.blockSignals(True)
        self.stage_list.clear()
        self.stage_list.addItems(names)
        self.stage_list.blockSignals(False)
        self.file_label.setText(
            f"{len(names)} stage{'s' if len(names) != 1 else ''} loaded")
        self.stage_list.setCurrentRow(0)

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

    def _save_x(self):
        if not self.manager.can_save:
            QMessageBox.warning(self, "Alexander", "Nothing to save yet.")
            return
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
        QMessageBox.information(self, "Alexander",
                               f"{os.path.basename(file_path)}\n\n{note}")

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
        self._stage_names = []
        self.stage_list.blockSignals(True)
        self.stage_list.clear()
        self.stage_list.blockSignals(False)
        self.file_label.setText(f"{os.path.basename(file_path)}  (imported glb)")
        self._update_sky_button()
        self._load_into_viewer()

    def _on_sky_toggle(self, checked: bool):
        self.manager.set_show_sky(checked)
        if self.manager.is_loaded:
            self._load_into_viewer(keep_view=True)   # toggling sky keeps the camera

    def _update_sky_button(self):
        """Enable the sky toggle only when the stage actually has a sky dome."""
        self.save_btn.setEnabled(self.manager.can_save)
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
