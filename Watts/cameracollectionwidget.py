"""A compact editor for a battle camera animation collection.

Reuses FF8GameData.dat.cameracollection (the same Qt-free model Ifrit's camera tab uses):
every value is a fixed-size field patched in place, so editing never changes the section
length. Unlike Ifrit's camera tab there is no 3D preview - r0win.dat carries no single
model to film - so this is a keyframe value editor only.

Each set is built lazily the first time it is expanded: the collection has dozens of
animations and hundreds of keyframe fields, and building them all up front would be slow.

A host whose collection may change size (Fujin's effect cameras saved as .cam files) turns on
structure_edits: keyframes can then be duplicated or removed and slots filled or emptied. Those
edits rebuild the collection bytes (FF8GameData.dat.cameracollection) and hand them over with
collection_rebuilt; the host swaps its collection and builds a new widget.
"""
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
                             QPushButton, QSpinBox, QGroupBox, QSizePolicy,
                             QGraphicsOpacityEffect, QMessageBox)

from FF8GameData.dat.cameracollection import (build_default_animation, clear_slot, insert_keyframe,
                                              remove_keyframe, set_slot_animation)


class _NoWheelSpinBox(QSpinBox):
    """Ignores the wheel so scrolling the panel never changes a value by accident."""

    def wheelEvent(self, event):
        event.ignore()


class _CollapsibleBox(QWidget):
    """A titled toggle button over a content area built lazily on first expand."""

    def __init__(self, title: str, builder):
        QWidget.__init__(self)
        self._builder = builder
        self._built = False
        self._toggle = QPushButton(f"▶ {title}")
        self._toggle.setStyleSheet("text-align: left;")
        self._toggle.setCheckable(True)
        # Shrink each set header to its text width instead of stretching across the panel.
        self._toggle.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self._toggle.clicked.connect(self._on_toggle)
        self._title = title
        self._content = QWidget()
        self._content_layout = QVBoxLayout()
        self._content_layout.setContentsMargins(12, 0, 0, 0)
        self._content.setLayout(self._content_layout)
        self._content.hide()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._toggle)
        layout.addWidget(self._content)
        self.setLayout(layout)
        # Whole-box fade used to grey the set out; theme-independent, unlike relying on the
        # subtle default disabled look.
        self._dim = QGraphicsOpacityEffect(self)
        self._dim.setOpacity(1.0)
        self.setGraphicsEffect(self._dim)

    def _on_toggle(self, checked):
        if checked and not self._built:
            self._builder(self._content_layout)
            self._built = True
        self._content.setVisible(checked)
        self._toggle.setText(f"{'▼' if checked else '▶'} {self._title}")

    def set_available(self, available: bool):
        """Grey out and lock this box when it does not apply. Combines three cues so it reads
        as unavailable on any Qt theme, not just the subtle default disabled look: it locks
        interaction, fades the whole box, and appends the reason to the header text."""
        self.setEnabled(available)
        self._dim.setOpacity(1.0 if available else 0.35)
        title = self._title if available else f"{self._title}  [unavailable]"
        self._toggle.setStyleSheet("text-align: left;" if available
                                   else "text-align: left; color: gray;")
        if not available and self._toggle.isChecked():  # collapse it
            self._toggle.setChecked(False)
            self._content.hide()
        self._toggle.setText(f"{'▼' if self._toggle.isChecked() else '▶'} {title}")


class CameraCollectionWidget(QWidget):
    """Editor for one CameraCollection: sets -> animation slots -> blocks -> keyframes."""

    data_changed = pyqtSignal()
    preview_requested = pyqtSignal(object)      # a CameraAnimation to play in the preview
    collection_rebuilt = pyqtSignal(object)     # new collection bytes after a structural edit

    # (label, attribute on CameraFrame) in display order
    _FRAME_COLUMNS = [
        ("Dur", "duration"),
        ("PosInt", "pos_interp_mode"),
        ("PosX", "pos_x"), ("PosY", "pos_y"), ("PosZ", "pos_z"),
        ("LookInt", "look_interp_mode"),
        ("LookX", "look_x"), ("LookY", "look_y"), ("LookZ", "look_z"),
    ]
    # Hover help per keyframe column (shown on both the header and each field).
    _COLUMN_TOOLTIPS = {
        "duration": "How long this keyframe holds, in engine ticks (the camera advances "
                    "16 units of animation time per frame).",
        "pos_interp_mode": "Interpolation/easing mode for the camera position between this "
                           "keyframe and the next.",
        "pos_x": "Camera position X (where the camera is).",
        "pos_y": "Camera position Y (where the camera is).",
        "pos_z": "Camera position Z (where the camera is).",
        "look_interp_mode": "Interpolation/easing mode for the look-at target.",
        "look_x": "Look-at target X (what the camera aims at).",
        "look_y": "Look-at target Y (what the camera aims at).",
        "look_z": "Look-at target Z (what the camera aims at).",
    }

    def __init__(self, collection, set_notes=None, show_preview_buttons=True, structure_edits=False,
                 expanded_sets=()):
        QWidget.__init__(self)
        self._collection = collection
        self._show_preview_buttons = show_preview_buttons
        self._structure_edits = structure_edits
        set_notes = set_notes or {}
        self._set_boxes = {}  # set index -> _CollapsibleBox, for enabling/greying out
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        for camera_set in collection.sets:
            frame_total = sum(len(block.frames)
                              for animation in camera_set.animations
                              for block in animation.blocks)
            note = set_notes.get(camera_set.index, "")
            title = f"Set {camera_set.index}"
            if note:
                title += f" - {note}"
            title += f" ({frame_total} keyframes)"
            box = _CollapsibleBox(title, self._make_set_builder(camera_set))
            self._set_boxes[camera_set.index] = box
            layout.addWidget(box)
        layout.addStretch(1)
        self.setLayout(layout)
        for index in expanded_sets:
            if index in self._set_boxes:
                self._set_boxes[index]._toggle.setChecked(True)
                self._set_boxes[index]._on_toggle(True)

    def expanded_set_indices(self):
        """The sets currently unfolded (to unfold them again in a rebuilt widget)."""
        return [index for index, box in self._set_boxes.items() if box._toggle.isChecked()]

    def set_enabled_set_indices(self, indices):
        """Grey out the sets whose index is not in `indices` (None = all enabled), e.g. to
        show only the sets that match the number of imported party members."""
        for index, box in self._set_boxes.items():
            box.set_available(indices is None or index in indices)

    def _make_set_builder(self, camera_set):
        def build(target_layout):
            for animation in camera_set.animations:
                if animation.empty or not animation.blocks:
                    if self._structure_edits:
                        target_layout.addLayout(self._empty_slot_row(camera_set.index, animation.slot))
                    continue
                frames = sum(len(block.frames) for block in animation.blocks)
                slot_group = QGroupBox(f"Slot {animation.slot} - {frames} keyframes")
                slot_layout = QVBoxLayout()
                if self._structure_edits:
                    clear_button = QPushButton("Clear slot")
                    clear_button.setToolTip("Remove this camera animation (the slot plays nothing)")
                    clear_button.setMaximumWidth(110)
                    clear_button.clicked.connect(lambda _checked, s=camera_set.index, a=animation.slot:
                                                 self._rebuild(clear_slot, s, a))
                    clear_row = QHBoxLayout()
                    clear_row.addWidget(clear_button)
                    clear_row.addStretch(1)
                    slot_layout.addLayout(clear_row)
                if self._show_preview_buttons:
                    preview_button = QPushButton("▶ Preview")
                    preview_button.setToolTip("Play this camera animation on the imported "
                                              "character model (right panel)")
                    preview_button.setMaximumWidth(110)
                    preview_button.clicked.connect(
                        lambda _checked, anim=animation: self.preview_requested.emit(anim))
                    preview_row = QHBoxLayout()
                    preview_row.addWidget(preview_button)
                    preview_row.addStretch(1)
                    slot_layout.addLayout(preview_row)
                for block_index, block in enumerate(animation.blocks):
                    slot_layout.addWidget(self._build_block(block_index, block,
                                                            (camera_set.index, animation.slot)))
                slot_group.setLayout(slot_layout)
                target_layout.addWidget(slot_group)
        return build

    def _empty_slot_row(self, set_index, slot):
        row = QHBoxLayout()
        row.addWidget(QLabel(f"Slot {slot} - empty"))
        add_button = QPushButton("Add camera")
        add_button.setToolTip("Put a new 2-keyframe camera animation in this slot, ready to edit")
        add_button.clicked.connect(lambda _checked: self._rebuild(set_slot_animation, set_index, slot,
                                                                  build_default_animation()))
        row.addWidget(add_button)
        row.addStretch(1)
        return row

    def _rebuild(self, edit, *args):
        """Run a structural edit on the collection bytes and hand the result to the host."""
        try:
            data = edit(self._collection.get_bytes(), *args)
        except ValueError as error:
            QMessageBox.warning(self, "Camera keyframes", str(error))
            return
        self.collection_rebuilt.emit(data)

    def _build_block(self, block_index: int, block, slot_key=None) -> QWidget:
        container = QWidget()
        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(0, 0, 0, 0)

        header = (f"Block {block_index}: FOV mode {block.fov_mode}, roll mode "
                  f"{block.roll_mode}, layout {block.layout}")
        header_label = QLabel(header)
        header_label.setToolTip("One chained camera move: FOV mode, roll (camera tilt) "
                                "mode and keyframe layout, followed by its keyframes below.")
        container_layout.addWidget(header_label)

        optional = block.optional_fields()
        if optional:
            optional_row = QHBoxLayout()
            for label, field in optional:
                field_label = QLabel(label + ":")
                field_label.setToolTip(f"Optional block parameter: {label}")
                optional_row.addWidget(field_label)
                spin = self._spin_for(field)
                spin.setToolTip(f"Optional block parameter: {label}")
                optional_row.addWidget(spin)
            optional_row.addStretch(1)
            container_layout.addLayout(optional_row)

        grid = QGridLayout()
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(2)
        for column, (label, _attribute) in enumerate(self._FRAME_COLUMNS):
            header = QLabel(label)
            header.setToolTip(self._COLUMN_TOOLTIPS.get(_attribute, ""))
            grid.addWidget(header, 0, column + 1)
        for row, frame in enumerate(block.frames):
            grid.addWidget(self._frame_label(row, block, (*slot_key, block_index, row)
                                             if self._structure_edits and slot_key is not None else None),
                           row + 1, 0)
            for column, (label, _attribute) in enumerate(self._FRAME_COLUMNS):
                field = getattr(frame, _attribute)
                spin = self._spin_for(field)
                spin.setToolTip(self._COLUMN_TOOLTIPS.get(_attribute, ""))
                grid.addWidget(spin, row + 1, column + 1)
        # Absorb all slack in a trailing empty column so the fields stay packed left
        grid.setColumnStretch(len(self._FRAME_COLUMNS) + 1, 1)
        grid_row = QHBoxLayout()
        grid_row.addLayout(grid)
        grid_row.addStretch(1)
        container_layout.addLayout(grid_row)
        container.setLayout(container_layout)
        return container

    def _frame_label(self, row, block, key=None) -> QWidget:
        """'#row', with the duplicate (+) / remove (-) buttons in front when structure edits are on
        (left of the fields, so a narrow panel never hides them)."""
        if key is None:
            return QLabel(f"#{row}")
        cell = QWidget()
        cell_layout = QHBoxLayout(cell)
        cell_layout.setContentsMargins(0, 0, 0, 0)
        cell_layout.setSpacing(1)
        add_button = QPushButton("+")
        add_button.setToolTip("Duplicate this keyframe right after it")
        add_button.setFixedWidth(22)
        add_button.clicked.connect(lambda _checked: self._rebuild(insert_keyframe, *key))
        remove_button = QPushButton("−")
        remove_button.setToolTip("Remove this keyframe (a block keeps at least one)")
        remove_button.setFixedWidth(22)
        remove_button.setEnabled(len(block.frames) > 1)
        remove_button.clicked.connect(lambda _checked: self._rebuild(remove_keyframe, *key))
        cell_layout.addWidget(add_button)
        cell_layout.addWidget(remove_button)
        cell_layout.addWidget(QLabel(f"#{row}"))
        return cell

    def _spin_for(self, field) -> QSpinBox:
        spin = _NoWheelSpinBox()
        spin.setRange(field.minimum, field.maximum)
        spin.setValue(field.get())
        spin.setFixedWidth(70)
        spin.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        spin.valueChanged.connect(lambda value, f=field: self._on_field_changed(f, value))
        return spin

    def _on_field_changed(self, field, value):
        field.set(value)
        self.data_changed.emit()
