"""Fujin's Models / animation 3D view: every object of one MAG file, whatever the effect.

 - packed MAG files (cinematic family, GF or not): meshes, morph targets (vertex clouds) and
   embedded battle models, from the object table (MagContainer);
 - indexed containers holding a standard four-section battle model (timeline-family GF creatures
   such as mag186_b.dat): that model.
Battle models play their own animations (.dat section 3), posed by IfritManager through
CreatureLoader, the same code as the GF Playback. Where the script moves objects, the motion is in
Choreography > Playback. Faces are untextured: an effect's texture placement in VRAM is known only
for the seven GF summons (their exe descriptors), so faces show their primitive colour."""
from types import SimpleNamespace

import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSlider, QPushButton,
                             QCheckBox, QSplitter, QTreeWidget, QTreeWidgetItem, QHeaderView)

from FF8GameData.magcine.magcontainer import MagContainer, PRIM_NAME
from Fujin.creature import CreatureLoader
from Fujin.meshpreview import MeshPreview

TICKS_PER_SECOND = 15
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
    def __init__(self):
        super().__init__()
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
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.tree)
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
                      if self.tree.topLevelItem(i).text(1) in ("mesh", "model")), None)
        if first is not None:
            self.tree.setCurrentItem(self.tree.topLevelItem(first))

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
    def _selected(self, item, _previous=None):
        self.play_button.setChecked(False)
        self._animations = None
        self.controls.setVisible(False)
        if item is None:
            return
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
