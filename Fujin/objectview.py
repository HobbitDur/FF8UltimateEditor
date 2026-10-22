"""Fujin's Models / animation 3D view: every object of one MAG file, whatever the effect.

 - packed MAG files (cinematic family, GF or not): meshes, morph targets (vertex clouds) and
   embedded battle models, from the object table (MagContainer);
 - indexed containers holding a standard four-section battle model (timeline-family GF creatures
   such as mag186_b.dat): that model.
Battle models play their own animations (.dat section 3), posed by IfritManager through
CreatureLoader, the same code as the GF Playback. Where the script moves objects, the motion is in
Choreography > Playback. Faces are untextured: an effect's texture placement in VRAM is known only
for the seven GF summons (their exe descriptors), so faces show their primitive colour.

Editing goes through Blender: Export .glb writes the selected object, Import .glb brings back its
vertex positions (the MAG keeps its size, so faces, colours, UVs, bones and animations stay).
A battle model's bones (length, rotation) and the pose of each animation frame (bone rotations,
root position) are edited in the Skeleton and Pose tables (Fujin.modeledit)."""
import os
from types import SimpleNamespace

import numpy as np
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSlider, QPushButton,
                             QCheckBox, QSplitter, QTreeWidget, QTreeWidgetItem, QHeaderView, QFileDialog,
                             QMessageBox, QTabWidget, QTableWidget, QTableWidgetItem, QSpinBox, QDoubleSpinBox)

from FF8GameData.magcine.magcontainer import MagContainer, PRIM_NAME
from FF8GameData.magcine import magmeshgltf
from Fujin.creature import CreatureLoader
from Fujin.meshpreview import MeshPreview

TICKS_PER_SECOND = 15
GLB_FILTER = "glTF binary (*.glb)"
RAW_PER_DEGREE = 4096 / 360.0
GLB_FOLDER_KEY = "Fujin model glb"
_FAMILY_NOTES = {
    "PlayStation TIM": "A texture file: see Textures. It holds no 3D object.",
    "SCOT sound": "A streamed sound part: see Sound. It holds no 3D object.",
    "AKAO audio": "A PlayStation sample bank: see Sound. It holds no 3D object.",
    "Four-byte reference": "A four-byte reference read by the effect's code: no 3D object.",
    "Raw / undecoded": ("No validated directory: VRAM pages, particle or effect-specific data. Nothing here is "
                        "known to be a 3D object, so nothing is drawn rather than guessing."),
    "Indexed MAG container": ("An indexed container whose parts are not a standard battle model. Their meaning "
                              "depends on the effect's code (not decoded), so nothing is drawn."),
    "Native camera parameter": "A camera value in the exe: no 3D object.",
}


def model_sources(data, document):
    """[(label, kind, payload)] of the 3D-viewable objects of one MAG byte image.

    kind: "mesh" / "morph" / "model" / "sprite" / "error"; payload: the CineObject, or for a model
    (container, object id) as CreatureLoader takes it."""
    data = bytes(data)
    if document.format == "Packed MAG":
        container = MagContainer(data)
        result = []
        for obj in container.objects:
            if obj.error:
                result.append((f"Object {obj.index}", "error", obj))
            elif obj.kind == "mesh":
                result.append((f"Object {obj.index}", "morph" if obj.mesh.is_morph_target else "mesh", obj))
            elif obj.kind == "model":
                result.append((f"Object {obj.index}", "model", (container, obj.index)))
            else:
                result.append((f"Object {obj.index}", "sprite", obj))
        return result
    if document.format == "Indexed MAG container":
        starts = {s.kind: s.start for s in document.sections}
        if {"skeleton", "geometry", "animation"} <= starts.keys():
            end = starts.get("model_trailer", len(data))
            model = SimpleNamespace(index=0, kind="model", offset=starts["skeleton"],
                                    info={"sections": (starts["skeleton"], starts["geometry"], starts["animation"]),
                                          "size": end - starts["skeleton"]})
            return [("Battle model", "model", (SimpleNamespace(data=data, objects=[model]), 0))]
    return []


class MagObjectView(QWidget):
    data_changed = pyqtSignal()

    def __init__(self, registry=None):
        super().__init__()
        self.registry = registry
        self.manager = None
        self._sources = []
        self._animations = None      # [[CreatureFrame]] of the selected model
        self._loaders = {}           # id(container) -> CreatureLoader (posing is costly)
        self.family = QLabel()
        self.family.setWordWrap(True)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Object", "Kind", "Details"])
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tree.setColumnWidth(0, 90)
        self.tree.setColumnWidth(1, 90)
        self.tree.currentItemChanged.connect(self._selected)
        self.preview = MeshPreview()
        self.animation_combo = QComboBox()
        self.animation_combo.currentIndexChanged.connect(self._animation_changed)
        self.frame_slider = QSlider(Qt.Orientation.Horizontal)
        self.frame_slider.valueChanged.connect(self._show_frame)
        self.frame_label = QLabel()
        self.play_button = QPushButton("Play")
        self.play_button.setCheckable(True)
        self.play_button.toggled.connect(self._toggle_play)
        self.wireframe = QCheckBox("Wireframe")
        self.wireframe.toggled.connect(self._wireframe)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.export_button = QPushButton("Export .glb…")
        self.export_button.setToolTip("Save the selected object as a glTF file (Blender: File > Import > glTF 2.0)")
        self.export_button.clicked.connect(lambda: self.export_glb())
        self.import_button = QPushButton("Import .glb…")
        self.import_button.setToolTip(
            "Bring back an edited .glb of this object: its vertices move to the new positions. Keep the faces "
            "(no face added, removed or split): the MAG keeps its size, so faces, colours, bones and animations "
            "stay as they are. Undo / Redo above, Save in the header.")
        self.import_button.clicked.connect(lambda: self.import_glb())
        self.timer = QTimer(self)
        self.timer.setInterval(int(1000 / TICKS_PER_SECOND))
        self.timer.timeout.connect(self._advance)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Animation:"))
        controls.addWidget(self.animation_combo)
        controls.addWidget(self.play_button)
        controls.addWidget(self.frame_slider, 1)
        controls.addWidget(self.frame_label)
        controls.addWidget(self.wireframe)
        self.controls = QWidget()
        self.controls.setLayout(controls)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self.preview, 1)
        right_layout.addWidget(self.controls)
        right_layout.addWidget(self.info)
        self._edit_model = None        # EmbeddedModel of the selected battle model, for its tables
        self._edit_key = None
        self.model_edit = QTabWidget()
        self.skeleton_table = QTableWidget(0, 6)
        self.skeleton_table.setHorizontalHeaderLabels(["Bone", "Parent", "Length", "Rot X°", "Rot Y°", "Rot Z°"])
        self.skeleton_table.setToolTip("The bones as the skeleton stores them: length (2048 = one unit) and rest "
                                       "rotation. Every animation poses the bones from here.")
        self.pose_table = QTableWidget(0, 4)
        self.pose_table.setHorizontalHeaderLabels(["", "X", "Y", "Z"])
        self.pose_table.setToolTip(
            "This frame of the animation: the root position (raw units), then each bone's rotation (degrees). "
            "A frame is stored as "
            "the change from the previous one: an edit re-encodes this animation only, and it must still fit "
            "the model's animation section (the MAG keeps its size; the room left is shown above).")
        for table in (self.skeleton_table, self.pose_table):
            table.verticalHeader().hide()
            table.verticalHeader().setDefaultSectionSize(26)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.pose_label = QLabel()
        self.pose_label.setWordWrap(True)
        pose_page = QWidget()
        pose_layout = QVBoxLayout(pose_page)
        pose_layout.setContentsMargins(0, 0, 0, 0)
        pose_layout.addWidget(self.pose_label)
        pose_layout.addWidget(self.pose_table, 1)
        self.model_edit.addTab(self.skeleton_table, "Skeleton")
        self.model_edit.addTab(pose_page, "Pose (this frame)")
        self.model_edit.currentChanged.connect(lambda _index: self._fill_pose())
        self.model_edit.hide()
        right_layout.addWidget(self.model_edit, 1)
        edit_row = QHBoxLayout()
        edit_row.addWidget(self.export_button)
        edit_row.addWidget(self.import_button)
        edit_row.addStretch(1)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.tree, 1)
        left_layout.addLayout(edit_row)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([380, 700])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.family)
        layout.addWidget(splitter, 1)
        self.set_manager(None)

    # ------------------------------------------------------------------ content
    def set_manager(self, manager):
        """EffectResourceView hook: show the objects of the selected source file."""
        self.play_button.setChecked(False)
        selected = self.tree.currentItem().text(0) if self.tree.currentItem() and manager is self.manager else None
        self.manager = manager
        self.tree.clear()
        self._loaders = {}
        self._sources = model_sources(manager.data, manager.document) if manager is not None else []
        if manager is None:
            self.family.setText("No imported MAG file of this effect holds 3D objects. Effects drawn by game code "
                                "keep their models in FF8_EN.exe (see Choreography > Native code).")
        elif self._sources:
            scripted = manager.program is not None
            self.family.setText(
                f"{len(self._sources)} object(s). Untextured: the faces show their primitive colour (an effect's "
                "texture placement is extracted for the seven GF summons only). "
                + ("The script moves them: Choreography > Playback." if scripted else
                   "No script in this file: the effect's other MAG file or its game code places them."))
        else:
            self.family.setText(_FAMILY_NOTES.get(manager.document.format,
                                                  f"{manager.document.format}: no 3D object in this file."))
        for label, kind, payload in self._sources:
            item = QTreeWidgetItem([label, kind, self._details(kind, payload)])
            item.setToolTip(2, item.text(2))
            item.setData(0, Qt.ItemDataRole.UserRole, (kind, payload))
            self.tree.addTopLevelItem(item)
        self.preview.set_mesh(None)
        self.controls.setVisible(False)
        self.info.setText("Select an object. Drag to rotate, wheel to zoom." if self._sources else "")
        first = next((i for i in range(self.tree.topLevelItemCount())
                      if self.tree.topLevelItem(i).text(0) == selected), None)
        if first is None:
            first = next((i for i in range(self.tree.topLevelItemCount())
                          if self.tree.topLevelItem(i).text(1) in ("mesh", "model")), None)
        if first is not None:
            self.tree.setCurrentItem(self.tree.topLevelItem(first))
        self._update_edit_buttons()

    @staticmethod
    def _details(kind, payload):
        if kind == "error":
            return "could not be decoded: " + payload.error
        if kind in ("mesh", "morph"):
            mesh = payload.mesh
            if kind == "morph":
                return f"morph target: {len(mesh.vertices)} vertices, no faces"
            prims = ", ".join(f"{count} {PRIM_NAME.get(t, t)}" for t, count in sorted(mesh.prim_counts.items()))
            return f"{len(mesh.vertices)} vertices, {prims}"
        if kind == "model":
            container, object_id = payload
            obj = next(o for o in container.objects if o.index == object_id)
            info = obj.info
            if "bones" in info:
                return (f"battle model: {info['bones']} bones, {info['geometry objects']} geometry objects, "
                        f"{info['animations']} animations")
            return "battle model (skeleton, geometry, animation)"
        return f"sprite frame list: {len(payload.info.get('frames', []))} entries"

    # ------------------------------------------------------------------ selection
    def _selected_object(self):
        item = self.tree.currentItem()
        if item is None:
            return None, None
        return item.data(0, Qt.ItemDataRole.UserRole)

    def _update_edit_buttons(self):
        kind, _payload = self._selected_object()
        editable = kind in ("mesh", "morph", "model")
        self.export_button.setEnabled(editable)
        self.import_button.setEnabled(editable and self.manager is not None)

    def _folder(self):
        return self.registry.last_folder(GLB_FOLDER_KEY) if self.registry else ""

    def _remember(self, path):
        if self.registry:
            self.registry.remember_folder(GLB_FOLDER_KEY, os.path.dirname(path))

    def _default_name(self):
        item = self.tree.currentItem()
        name = os.path.splitext(os.path.basename(self.manager.file_path))[0] if self.manager else "mag"
        return f"{name}_{item.text(0).lower().replace(' ', '')}.glb" if item else name + ".glb"

    def export_glb(self, path=None):
        """Write the selected object as a .glb (a battle model with its animations)."""
        kind, payload = self._selected_object()
        if kind not in ("mesh", "morph", "model"):
            return None
        if not path:
            path = QFileDialog.getSaveFileName(self, "Export the object as glTF",
                                               os.path.join(self._folder(), self._default_name()), GLB_FILTER)[0]
            if not path:
                return None
            self._remember(path)
        try:
            if kind == "model":
                from Fujin.modelgltf import export_model
                container, object_id = payload
                export_model(self._loaders.setdefault(id(container), CreatureLoader([container])), object_id, path)
            else:
                magmeshgltf.export_mesh(payload.mesh, path, self.tree.currentItem().text(0))
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Fujin", f"Not exported: {error}")
            return None
        self.info.setText(f"Exported {path}. Edit it in Blender (move vertices; keep every face), export it as "
                          "glTF binary, then Import .glb.")
        return path

    def import_glb(self, path=None):
        """Move the selected object's vertices to an edited .glb's positions (same faces)."""
        kind, payload = self._selected_object()
        if kind not in ("mesh", "morph", "model") or self.manager is None:
            return False
        if not path:
            path = QFileDialog.getOpenFileName(self, "Import the edited glTF", self._folder(), GLB_FILTER)[0]
            if not path:
                return False
            self._remember(path)
        try:
            if kind == "model":
                from Fujin.modelgltf import export_model, import_positions, vertex_patches
                container, object_id = payload
                loader = self._loaders.setdefault(id(container), CreatureLoader([container]))
                loader(object_id)
                obj = next(o for o in container.objects if o.index == object_id)
                positions = import_positions(loader._ifrit_manager(), path)
                patches = vertex_patches(self.manager.data, obj.info["sections"][1], positions)
            else:
                positions = magmeshgltf.import_positions(payload.mesh, path)
                patches = [magmeshgltf.vertex_bytes(self.manager.data, payload.offset, positions)]
        except (OSError, ValueError, KeyError, IndexError) as error:
            QMessageBox.warning(self, "Fujin", f"Not imported: {error}")
            return False
        patches = [(at, raw) for at, raw in patches if bytes(self.manager.data[at:at + len(raw)]) != raw]
        if not patches:
            self.info.setText("The file holds the same vertices: nothing changed.")
            return True
        start, end = min(at for at, _raw in patches), max(at + len(raw) for at, raw in patches)
        block = bytearray(self.manager.data[start:end])           # one write: one Undo step
        for at, raw in patches:
            block[at - start:at - start + len(raw)] = raw
        self.manager.patch_bytes(start, bytes(block))
        self.set_manager(self.manager)
        self.info.setText(f"Imported {os.path.basename(path)}: the vertices moved in place (Undo above).")
        self.data_changed.emit()
        return True

    def _selected(self, item, _previous=None):
        self.play_button.setChecked(False)
        self._animations = None
        self.controls.setVisible(False)
        self._update_edit_buttons()
        kind = item.data(0, Qt.ItemDataRole.UserRole)[0] if item is not None else None
        self.model_edit.setVisible(kind == "model" and self.manager is not None)
        if item is None:
            return
        if kind == "model" and self.manager is not None:
            self._fill_skeleton()
        kind, payload = item.data(0, Qt.ItemDataRole.UserRole)
        if kind in ("mesh", "morph"):
            self.preview.set_mesh(payload.mesh)
            self.info.setText("Morph target: vertices only, blended into another mesh by the script's draw handler. "
                              "Shown as points." if kind == "morph" else
                              "Mesh in its own coordinates. Drag to rotate, wheel to zoom.")
        elif kind == "model":
            self._show_model(*payload)
        else:
            self.preview.set_mesh(None)
            self.info.setText(
                "Not drawn: " + ("this object could not be decoded (" + payload.error + ")." if kind == "error" else
                "a sprite frame list is a flipbook of textured quads; drawing it needs the effect's texture "
                "placement in VRAM, which is extracted for the seven GF summons only. Frames (duration in ticks / "
                "then): " + ", ".join(f"{f['duration']}/{ {0: 'next', 1: 'end', 2: 'loop'}.get(f['code'], f['code'])}"
                                      for f in payload.info.get("frames", [])[:24])))

    # ------------------------------------------------------------------ skeleton / pose editing
    def _model_for_edit(self):
        """EmbeddedModel of the selected battle model (decoded once per selection and per edit)."""
        kind, payload = self._selected_object()
        if kind != "model" or self.manager is None:
            return None
        container, object_id = payload
        obj = next(o for o in container.objects if o.index == object_id)
        key = (id(self.manager), object_id, bytes(self.manager.data[obj.offset:obj.offset + obj.info["size"]]))
        if self._edit_key != key:
            from Fujin.modeledit import EmbeddedModel
            self._edit_model = EmbeddedModel(self.manager.data, obj.info["sections"], obj.offset + obj.info["size"])
            self._edit_key = key
        return self._edit_model

    @staticmethod
    def _degree_spin(raw, slot):
        spin = QDoubleSpinBox()
        spin.setRange(-32768 / RAW_PER_DEGREE, 32767 / RAW_PER_DEGREE)
        spin.setDecimals(2)
        spin.setSingleStep(1.0)
        spin.setKeyboardTracking(False)
        spin.setValue(raw / RAW_PER_DEGREE)
        spin.valueChanged.connect(slot)
        return spin

    def _fill_skeleton(self):
        model = self._model_for_edit()
        self.skeleton_table.setRowCount(0)
        if model is None:
            return
        self.skeleton_table.setRowCount(len(model.bones))
        for row, bone in enumerate(model.bones):
            self.skeleton_table.setItem(row, 0, QTableWidgetItem(str(row)))
            parent = "root" if bone.parent_id == 0xFFFF else str(bone.parent_id)
            self.skeleton_table.setItem(row, 1, QTableWidgetItem(parent))
            for column in (0, 1):
                self.skeleton_table.item(row, column).setFlags(Qt.ItemFlag.ItemIsEnabled)
            length = QSpinBox()
            length.setRange(-32768, 32767)
            length.setKeyboardTracking(False)
            length.setValue(bone.get_size_raw())
            length.valueChanged.connect(lambda _v, r=row: self._bone_edited(r))
            self.skeleton_table.setCellWidget(row, 2, length)
            for axis, raw in enumerate((bone._rotX, bone._rotY, bone._rotZ)):
                self.skeleton_table.setCellWidget(row, 3 + axis, self._degree_spin(raw, lambda _v, r=row: self._bone_edited(r)))

    def _bone_edited(self, row):
        model = self._model_for_edit()
        if model is None:
            return
        rotation = tuple(round(self.skeleton_table.cellWidget(row, 3 + axis).value() * RAW_PER_DEGREE) for axis in range(3))
        self._write_model(lambda: [model.set_bone(row, self.skeleton_table.cellWidget(row, 2).value(), rotation)])

    def _current_frame(self):
        return max(0, self.animation_combo.currentIndex()), self.frame_slider.value()

    def _fill_pose(self):
        if self.model_edit.currentIndex() != 1 or self.play_button.isChecked():
            return
        model = self._model_for_edit()
        self.pose_table.setRowCount(0)
        if model is None or not model.animations:
            self.pose_label.setText("This model has no animation frame.")
            return
        animation, frame = self._current_frame()
        if animation >= len(model.animations) or frame >= len(model.animations[animation].frames):
            return
        data = model.animations[animation].frames[frame]
        self.pose_label.setText(f"Animation {animation}, frame {frame + 1} of {len(model.animations[animation].frames)} "
                                f"(pick them above). Room left in the animation section: {model.free_bytes()} bytes.")
        self.pose_table.setRowCount(1 + len(data.rotation_vector_data))
        root = QTableWidgetItem("Root position")
        root.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self.pose_table.setItem(0, 0, root)
        for axis in range(3):
            spin = QSpinBox()
            spin.setRange(-32768, 32767)
            spin.setKeyboardTracking(False)
            spin.setValue(data.position[axis].get_pos_raw())
            spin.valueChanged.connect(lambda _v: self._pose_edited(None))
            self.pose_table.setCellWidget(0, 1 + axis, spin)
        for bone, axes in enumerate(data.rotation_vector_data):
            item = QTableWidgetItem(f"Bone {bone}")
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.pose_table.setItem(1 + bone, 0, item)
            for axis in range(3):
                self.pose_table.setCellWidget(1 + bone, 1 + axis, self._degree_spin(
                    int(axes[axis].get_rotate_raw()), lambda _v, b=bone: self._pose_edited(b)))

    def _pose_edited(self, bone):
        model = self._model_for_edit()
        if model is None:
            return
        animation, frame = self._current_frame()
        if bone is None:
            position = tuple(self.pose_table.cellWidget(0, 1 + axis).value() for axis in range(3))
            edit = lambda: model.set_frame(animation, frame, position=position)
        else:
            values = tuple(round(self.pose_table.cellWidget(1 + bone, 1 + axis).value() * RAW_PER_DEGREE)
                           for axis in range(3))
            edit = lambda: model.set_frame(animation, frame, rotations={bone: values})

        def patches():
            edit()
            return [model.animation_patch()]
        self._write_model(patches)

    def _write_model(self, patches_of):
        """Apply [(offset, bytes)] (one Undo step each), then show the model again where it was."""
        animation, frame = self._current_frame()
        try:
            patches = patches_of()
        except ValueError as error:
            QMessageBox.warning(self, "Fujin", f"Not applied: {error}")
            self._edit_key = None                     # decode again from the file: the edit is dropped
            self._fill_skeleton()
            self._fill_pose()
            return False
        changed = False
        for offset, raw in patches:
            if bytes(self.manager.data[offset:offset + len(raw)]) != raw:
                self.manager.patch_bytes(offset, raw)
                changed = True
        if not changed:
            return True
        tab = self.model_edit.currentIndex()
        self.set_manager(self.manager)
        if self._animations:
            self.animation_combo.setCurrentIndex(min(animation, self.animation_combo.count() - 1))
            self.frame_slider.setValue(frame)
        self.model_edit.setCurrentIndex(tab)
        self._fill_pose()
        self.data_changed.emit()
        return True

    def _show_model(self, container, object_id):
        loader = self._loaders.setdefault(id(container), CreatureLoader([container]))
        try:
            animations = loader(object_id)
        except Exception as error:  # noqa: BLE001 - a model IfritManager cannot pose
            self.preview.set_mesh(None)
            self.info.setText(f"This battle model could not be posed: {error}")
            return
        if not animations or not any(animations):
            self.preview.set_mesh(None)
            self.info.setText("This battle model has no animation frame to pose.")
            return
        self._animations = animations
        self.animation_combo.blockSignals(True)
        self.animation_combo.clear()
        for index, frames in enumerate(animations):
            self.animation_combo.addItem(f"{index} ({len(frames)} frames)", index)
        self.animation_combo.blockSignals(False)
        self.controls.setVisible(True)
        self.info.setText("Embedded battle model (.dat sections 1-3), posed by its own animations at the battle's "
                          "15 frames per second. Untextured.")
        self._animation_changed(0)

    def _animation_changed(self, index):
        if not self._animations or not 0 <= index < len(self._animations):
            return
        frames = self._animations[index]
        self.frame_slider.blockSignals(True)
        self.frame_slider.setRange(0, max(0, len(frames) - 1))
        self.frame_slider.setValue(0)
        self.frame_slider.blockSignals(False)
        # frame the first pose once, so playing does not re-centre each frame. Not the whole animation:
        # animations park hidden parts hundreds of thousands of units away, they leave the view here too
        points = frames[0].vertices if frames and len(frames[0].vertices) else np.zeros((1, 3))
        low, high = np.percentile(points, 2, axis=0), np.percentile(points, 98, axis=0)
        centre, half = (low + high) / 2, (high - low) * 0.75
        bounds = ((centre - half).tolist(), (centre + half).tolist())
        self.preview.set_mesh(None)
        self.preview.bounds = bounds
        self._show_frame(0, keep_view=True)

    def _show_frame(self, frame_id, keep_view=True):
        if not self._animations:
            return
        if self.model_edit.isVisible() and self.model_edit.currentIndex() == 1 and not self.play_button.isChecked():
            self._fill_pose()
        frames = self._animations[max(0, self.animation_combo.currentIndex())]
        if not frames:
            return
        frame = frames[min(frame_id, len(frames) - 1)]
        self.preview.set_mesh(SimpleNamespace(vertices=[tuple(v) for v in frame.vertices.tolist()],
                                              faces=[(0, indices, 0x6E96CD) for indices in frame.faces]),
                              keep_view=keep_view)
        self.frame_label.setText(f"frame {frame_id + 1}/{len(frames)}")

    def _toggle_play(self, playing):
        self.play_button.setText("Pause" if playing else "Play")
        if playing and self._animations:
            self.timer.start()
        else:
            self.timer.stop()

    def _advance(self):
        maximum = self.frame_slider.maximum()
        self.frame_slider.setValue(0 if self.frame_slider.value() >= maximum else self.frame_slider.value() + 1)

    def _wireframe(self, checked):
        self.preview.wireframe = checked
        self.preview.update()
