"""The Camera tab: an editor for a battle .dat's camera animation collection - monster
section 6, and character (dXc) section 5.

The camera section is NOT a byte-code program like the animation section IfritSeq edits; it is
a set of key-framed camera motions (see FF8GameData/dat/cameracollection.py). This tab shows
that structure - sets -> 8 animation slots -> blocks (FOV/roll) -> keyframes - and lets each
value be edited. The model is a view over the raw section bytes: every edit patches a
fixed-size field in place, so saving a file changes only the bytes the user actually touched
(byte-for-byte identical otherwise), exactly like IfritSeq's hex box is its source of truth.

The tab mirrors IfritSeq's shape (a scroll area of collapsible frames, a toolbar with an info
button and a raw-hex toggle) and its two public entry points, load_file() and save_file(),
called by IfritMonsterWidget. Both monster section 6 and character section 5 are the *same*
bare camera-animation collection format (verified against FF8_EN.exe: the game plays the
acting entity's own collection via cameraWhenDoingAction / command_queue->unk09). The only
difference is the set count: monsters usually have 1 set (8 slots), characters have 2 sets
(16 slots). The byte-code camera VM only exists in stage/R0WIN/spell blobs, not in these
per-entity sections, so there is nothing extra to edit for characters.
"""
import os
import xml.etree.ElementTree as ET

from PyQt6.QtCore import Qt, QSize, QSettings, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QScrollArea, QGroupBox, QSpinBox, QGridLayout, QCheckBox,
                             QMessageBox, QPlainTextEdit, QSizePolicy, QFileDialog,
                             QToolButton, QSplitter)

from FF8GameData.monsterdata import EntityType
from FF8GameData.dat.cameracollection import parse_camera_collection, CameraParseError
from Ifrit.ifritmanager import IfritManager
from Ifrit.IfritCameraSeq.camerapreview import CameraPreviewPanel

# Which raw section index holds the camera animation collection, per entity type. Both are the
# same bare-collection format; monsters carry it in section 6 (usually 1 set), characters in
# section 5 (2 sets). Weapons have no camera section.
_CAMERA_SECTION_BY_ENTITY = {
    EntityType.MONSTER: 6,
    EntityType.CHARACTER: 5,
    EntityType.CHARACTER_NO_WEAPON: 5,
}


# One-line explanation of every editable field, shown as hover text.
_FRAME_TOOLTIP = {
    "duration": "Frames this keyframe lasts: the camera glides from this keyframe to the "
                "next over this many frames (playback ≈15 fps). 0 = instant.",
    "pos_x": "Camera position X (side to side), world units, signed (−32768…32767).",
    "pos_y": "Camera position Y (up/down), world units, signed.",
    "pos_z": "Camera position Z (depth / forward-back), world units, signed.",
    "pos_interp": "Position easing mode (raw byte, e.g. 0x90 shown as 144): how the move to "
                  "the next keyframe is interpolated. Curve meaning not fully decoded yet.",
    "look_x": "Look-at target X — the point the camera faces, world units, signed.",
    "look_y": "Look-at target Y — the point the camera faces, world units, signed.",
    "look_z": "Look-at target Z — the point the camera faces, world units, signed.",
    "look_interp": "Look-at easing mode (raw byte). Curve meaning not fully decoded yet.",
}
_BLOCK_FIELD_TOOLTIP = {
    "FOV start": "Field of view at the start of this block. Lower = zoomed in (telephoto), "
                 "higher = wider. Default is 0x200 (512).",
    "FOV end": "Field of view at the end of this block (the FOV animates from start to end).",
    "Roll start": "Camera roll — tilt around the view direction — at the start of this block. "
                  "0 = level.",
    "Roll end": "Camera roll at the end of this block (roll animates from start to end).",
}
# Hover text for the collapsible group titles, explaining the camera hierarchy.
_SET_TOOLTIP = (
    "Set — a bank of 8 animation slots. The game chooses a set with the top nibble of a "
    "camera index ((index >> 4) & 0xF); vanilla monsters use 1 or 2 sets. Within a set, the "
    "low 3 bits (index & 7) pick the slot.")
_ANIMATION_TOOLTIP = (
    "Animation — one complete camera shot for a moment (e.g. the swoop for a particular "
    "attack). It is the unit the game plays: \"play camera animation N\". Made of one or more "
    "blocks played back to back. Empty slots (FFFF) do nothing.\n\n"
    "What triggers a shot lives in the attacking spell/ability effect, not here; section 6 is "
    "just this monster's library of shots.")
_BLOCK_TOOLTIP = (
    "Block — a run of keyframes sharing one FOV and one roll setting (each glides from its "
    "start value to its end value across the block). A new block begins when the lens "
    "behaviour changes. A block can hold 1 keyframe (a static pose), 2 (a move from A to B, "
    "the common case) or more (a multi-point path).")

# The frame-grid columns, paired with their tooltip key (None = the '#' index column).
_FRAME_COLUMNS = [("#", None), ("Duration", "duration"),
                  ("Pos X", "pos_x"), ("Pos Y", "pos_y"), ("Pos Z", "pos_z"),
                  ("Pos interp", "pos_interp"),
                  ("Look X", "look_x"), ("Look Y", "look_y"), ("Look Z", "look_z"),
                  ("Look interp", "look_interp")]


class NoWheelSpinBox(QSpinBox):
    """A spin box that ignores the mouse wheel, so scrolling the tab never changes a value by
    accident. Overriding the method (not reassigning wheelEvent on the instance) is what makes
    this reliable - Qt dispatches the wheel event to the C++ virtual, i.e. this override."""

    def wheelEvent(self, event):
        event.ignore()


def _bind_spin(field, tooltip: str = "") -> NoWheelSpinBox:
    """A decimal spin box bound to a CameraField: editing it patches the section bytes.

    Camera coordinates are signed 16-bit spatial values, so decimal (not IfritSeq's hex
    QSpinHex) is the readable form; the field's own kind gives the range and signedness.
    """
    spin = NoWheelSpinBox()
    spin.setRange(field.minimum, field.maximum)
    spin.setValue(field.get())
    spin.setKeyboardTracking(False)
    # Keep every spin at its minimum useful width so a row of them stays compact and left
    # aligned instead of each cell stretching to fill the tab.
    spin.setMaximumWidth(72)
    spin.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    if tooltip:
        spin.setToolTip(tooltip)
    # Write edits straight back into the section bytes (the field patches the raw buffer).
    # A lambda, not field.set directly: CameraField uses __slots__ and cannot be weak-referenced.
    spin.valueChanged.connect(lambda value: field.set(value))
    return spin


class CollapsibleSection(QWidget):
    """A titled section that folds away by clicking an arrow (▼ open / ▶ collapsed).

    Used for both the sets and the animation slots, matching the fold-to-focus feel of the
    Sequence tab but with an arrow toggle instead of a checkbox. Extra header widgets (e.g. a
    Preview button) sit next to the arrow; content goes in content_layout(), slightly indented.
    """

    def __init__(self, title: str, parent=None, expanded: bool = True, tooltip: str = ""):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self._toggle = QToolButton()
        self._toggle.setStyleSheet("QToolButton { border: none; font-weight: bold; }")
        self._toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle.setText(title)
        if tooltip:
            self._toggle.setToolTip(tooltip)
        self._toggle.setCheckable(True)
        self._toggle.setChecked(expanded)
        self._toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self._toggle.clicked.connect(self.__on_toggle)

        self._header = QHBoxLayout()
        self._header.setContentsMargins(0, 0, 0, 0)
        self._header.addWidget(self._toggle)
        self._header.addStretch(1)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(16, 0, 0, 0)  # indent under the arrow
        self._content.setVisible(expanded)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)
        outer.addLayout(self._header)
        outer.addWidget(self._content)

    def content_layout(self) -> QVBoxLayout:
        return self._content_layout

    def add_header_widget(self, widget):
        self._header.insertWidget(self._header.count() - 1, widget)  # before the stretch

    def set_expanded(self, expanded: bool):
        self._toggle.setChecked(expanded)
        self._toggle.setArrowType(Qt.ArrowType.DownArrow if expanded
                                  else Qt.ArrowType.RightArrow)
        self._content.setVisible(expanded)

    def __on_toggle(self):
        self.set_expanded(self._toggle.isChecked())


class IfritCameraSeqWidget(QWidget):
    """Camera animation collection editor for a monster's section 6."""

    def __init__(self, ifrit_manager: IfritManager, icon_path="Resources"):
        QWidget.__init__(self)
        self.ifrit_manager = ifrit_manager
        self.icon_path = icon_path
        self.settings = QSettings("FF8UltimateEditor", "FF8UltimateEditor")
        self._collection = None       # the parsed CameraCollection (a copy we edit)
        self._editable = False        # False for a file with no editable camera section
        self._spin_list = []          # every bound spin box, to refresh the hex view
        self._animation_sections = []  # the animation-slot CollapsibleSections, to fold by default
        self._grid_holders = []       # each block's keyframe grid, to size the editor pane
        self.__camera_icon = QIcon(os.path.join(icon_path, 'ifrit.ico'))
        self.file_dialog = QFileDialog()

        root = QVBoxLayout()
        self.setLayout(root)

        # ── Toolbar ──────────────────────────────────────────────────
        toolbar = QHBoxLayout()
        self._import_xml_button = QPushButton()
        self._import_xml_button.setIcon(QIcon(os.path.join(icon_path, 'xml_upload.png')))
        self._import_xml_button.setIconSize(QSize(30, 30))
        self._import_xml_button.setFixedSize(40, 40)
        self._import_xml_button.setToolTip("Import the camera collection from an xml file")
        self._import_xml_button.clicked.connect(self._import_xml_file)
        self._import_xml_button.setEnabled(False)

        self._export_xml_button = QPushButton()
        self._export_xml_button.setIcon(QIcon(os.path.join(icon_path, 'xml_save.png')))
        self._export_xml_button.setIconSize(QSize(30, 30))
        self._export_xml_button.setFixedSize(40, 40)
        self._export_xml_button.setToolTip("Export the camera collection to an xml file")
        self._export_xml_button.clicked.connect(self._export_xml_file)
        self._export_xml_button.setEnabled(False)

        self.info_button = QPushButton()
        self.info_button.setIcon(QIcon(os.path.join(icon_path, 'info.png')))
        self.info_button.setFixedSize(40, 40)
        self.info_button.setToolTip("About the camera section")
        self.info_button.clicked.connect(self.__show_info)
        self.summary_label = QLabel("No file loaded")
        self.hex_checkbox = QCheckBox("Show raw bytes")
        self.hex_checkbox.setToolTip("Show the raw camera-section bytes (read-only), the source "
                                     "of truth every edit patches in place")
        self.hex_checkbox.stateChanged.connect(self.__toggle_hex)
        toolbar.addWidget(self._import_xml_button)
        toolbar.addWidget(self._export_xml_button)
        toolbar.addWidget(self.info_button)
        toolbar.addWidget(self.summary_label)
        toolbar.addStretch(1)
        toolbar.addWidget(self.hex_checkbox)
        root.addLayout(toolbar)

        # ── Read-only raw hex view (hidden until toggled) ────────────
        self.hex_view = QPlainTextEdit()
        self.hex_view.setReadOnly(True)
        self.hex_view.setMaximumHeight(120)
        self.hex_view.hide()
        root.addWidget(self.hex_view)

        # ── Editor (left) + shared 3D preview (right), split ─────────
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout()
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.content_widget.setLayout(self.content_layout)
        self.scroll_area.setWidget(self.content_widget)

        # One shared preview panel for every animation (not a popup per slot).
        self._preview_panel = CameraPreviewPanel(self.ifrit_manager)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self.scroll_area)
        self._splitter.addWidget(self._preview_panel)
        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 2)
        root.addWidget(self._splitter, 1)

    # ── Public API (called by IfritMonsterWidget) ─────────────────────
    def load_file(self, path: str = ""):
        self.__load()

    def save_file(self):
        """Fold the edited bytes back into the model the file writer persists."""
        if self._editable and self._collection is not None:
            index = _CAMERA_SECTION_BY_ENTITY.get(self.ifrit_manager.enemy.entity_type)
            if index is not None:
                self.ifrit_manager.enemy.section_raw_data[index] = self._collection.get_bytes()

    # ── XML import / export (like IfritSeq) ───────────────────────────
    def _export_xml_file(self):
        if not self._editable or self._collection is None:
            return
        default_name = self.ifrit_manager.enemy.origin_file_name.replace('.dat', '_camera.xml')
        path = self.file_dialog.getSaveFileName(parent=self, caption="Camera xml to save",
                                                directory=default_name)[0]
        if path:
            self.create_camera_xml(self._collection, path)

    def _import_xml_file(self):
        path = self.file_dialog.getOpenFileName(parent=self, caption="Camera xml to import",
                                                filter="*.xml")[0]
        if not path:
            return
        collection = self.create_camera_collection_from_xml(path, self)
        if collection is None:
            return
        # Replace the whole section: importing a different monster's camera changes its byte
        # length, and the file writer recomputes the header offsets from each section's size.
        self.__clear_content()
        self._collection = collection
        self._editable = True
        self._import_xml_button.setEnabled(True)
        self._export_xml_button.setEnabled(True)
        self.__build()
        self.__finish_build(collapse_slots=True)
        self.__refresh_hex()

    @staticmethod
    def create_camera_xml(collection, xml_file: str):
        """Write the collection as xml. The <raw> element is the lossless source of truth
        (the exact section bytes); the structured set/animation/block/frame elements below it
        carry the same values in a readable, hand-editable form. On import <raw> gives the
        structure and the structured values are applied on top of it."""
        root = ET.Element("camera_collection")
        raw = ET.SubElement(root, "raw")
        raw.text = bytes(collection.get_bytes()).hex(" ").upper()
        for camera_set in collection.sets:
            set_element = ET.SubElement(root, "set", index=str(camera_set.index))
            for animation in camera_set.animations:
                animation_element = ET.SubElement(set_element, "animation",
                                                  slot=str(animation.slot))
                if animation.empty:
                    animation_element.set("empty", "true")
                    continue
                for block_index, block in enumerate(animation.blocks):
                    block_element = ET.SubElement(
                        animation_element, "block", index=str(block_index),
                        control=f"0x{block.control_word:04X}", layout=str(block.layout))
                    if block.fov_start is not None:
                        ET.SubElement(block_element, "fov", start=str(block.fov_start.get()),
                                      end=str(block.fov_end.get()))
                    if block.roll_start is not None:
                        ET.SubElement(block_element, "roll", start=str(block.roll_start.get()),
                                      end=str(block.roll_end.get()))
                    for frame_index, frame in enumerate(block.frames):
                        ET.SubElement(
                            block_element, "frame", index=str(frame_index),
                            duration=str(frame.duration.get()),
                            pos_x=str(frame.pos_x.get()), pos_y=str(frame.pos_y.get()),
                            pos_z=str(frame.pos_z.get()),
                            pos_interp=f"0x{frame.pos_interp_mode.get():02X}",
                            look_x=str(frame.look_x.get()), look_y=str(frame.look_y.get()),
                            look_z=str(frame.look_z.get()),
                            look_interp=f"0x{frame.look_interp_mode.get():02X}")
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        tree.write(xml_file, encoding="utf-8", xml_declaration=True)

    @staticmethod
    def create_camera_collection_from_xml(xml_file: str, parent=None):
        """Parse a camera xml back into a CameraCollection, or None on any error (a message
        box explains why). Structure comes from <raw>; the structured elements override the
        editable values on top of it."""
        def fail(message):
            if parent is not None:
                QMessageBox.warning(parent, "Camera import", message)
            return None
        try:
            root = ET.parse(xml_file).getroot()
        except ET.ParseError as error:
            return fail(f"The xml could not be parsed: {error}")
        raw_element = root.find("raw")
        if raw_element is None or not (raw_element.text or "").strip():
            return fail("The xml has no <raw> section bytes to import.")
        try:
            data = bytearray(int(token, 16) for token in raw_element.text.split())
        except ValueError:
            return fail("The <raw> element is not valid hexadecimal bytes.")
        try:
            collection = parse_camera_collection(data)
        except CameraParseError as error:
            return fail(f"The <raw> bytes are not a valid camera collection: {error}")
        IfritCameraSeqWidget._apply_xml_values(root, collection)
        return collection

    @staticmethod
    def _apply_xml_values(root, collection):
        """Overwrite the editable values of an already-parsed collection from the structured
        xml, matching by index. Anything that does not line up with the <raw> structure is
        skipped, so a hand-edited value takes effect while the layout stays exact."""
        def apply(field, text):
            if field is None or text is None:
                return
            text = text.strip()
            try:
                value = int(text, 16) if text.lower().startswith("0x") else int(text)
            except ValueError:
                return
            field.set(max(field.minimum, min(field.maximum, value)))

        for set_element in root.findall("set"):
            set_index = int(set_element.get("index", "-1"))
            if not 0 <= set_index < len(collection.sets):
                continue
            camera_set = collection.sets[set_index]
            for animation_element in set_element.findall("animation"):
                slot = int(animation_element.get("slot", "-1"))
                if not 0 <= slot < len(camera_set.animations):
                    continue
                animation = camera_set.animations[slot]
                if animation.empty:
                    continue
                for block_element in animation_element.findall("block"):
                    block_index = int(block_element.get("index", "-1"))
                    if not 0 <= block_index < len(animation.blocks):
                        continue
                    block = animation.blocks[block_index]
                    fov_element = block_element.find("fov")
                    if fov_element is not None:
                        apply(block.fov_start, fov_element.get("start"))
                        apply(block.fov_end, fov_element.get("end"))
                    roll_element = block_element.find("roll")
                    if roll_element is not None:
                        apply(block.roll_start, roll_element.get("start"))
                        apply(block.roll_end, roll_element.get("end"))
                    for frame_element in block_element.findall("frame"):
                        frame_index = int(frame_element.get("index", "-1"))
                        if not 0 <= frame_index < len(block.frames):
                            continue
                        frame = block.frames[frame_index]
                        apply(frame.duration, frame_element.get("duration"))
                        apply(frame.pos_x, frame_element.get("pos_x"))
                        apply(frame.pos_y, frame_element.get("pos_y"))
                        apply(frame.pos_z, frame_element.get("pos_z"))
                        apply(frame.pos_interp_mode, frame_element.get("pos_interp"))
                        apply(frame.look_x, frame_element.get("look_x"))
                        apply(frame.look_y, frame_element.get("look_y"))
                        apply(frame.look_z, frame_element.get("look_z"))
                        apply(frame.look_interp_mode, frame_element.get("look_interp"))

    # ── Loading ───────────────────────────────────────────────────────
    def __load(self):
        self.__clear()
        # The monster changed: stop any preview and reload its model on the next Preview.
        self._preview_panel.invalidate()
        self._import_xml_button.setEnabled(False)
        self._export_xml_button.setEnabled(False)
        enemy = getattr(self.ifrit_manager, "enemy", None)
        if enemy is None:
            self.summary_label.setText("No file loaded")
            return
        index = _CAMERA_SECTION_BY_ENTITY.get(enemy.entity_type)
        if index is None or index >= len(enemy.section_raw_data):
            self._editable = False
            self.summary_label.setText("This file type has no camera section.")
            return
        raw = bytes(enemy.section_raw_data[index])
        if len(raw) < 6:
            self._editable = False
            self.summary_label.setText(f"This file has no camera data (empty section {index}).")
            return
        try:
            self._collection = parse_camera_collection(raw)
        except CameraParseError as error:
            self._editable = False
            self.summary_label.setText(f"Section 6 is not a camera collection: {error}")
            return
        self._editable = True
        self._import_xml_button.setEnabled(True)
        self._export_xml_button.setEnabled(True)
        self.__build()
        self.__finish_build(collapse_slots=True)  # default: only the animation slots are open
        self.__refresh_hex()

    def __clear(self):
        self._collection = None
        self.__clear_content()

    def __clear_content(self):
        self._spin_list = []
        self._animation_sections = []
        self._grid_holders = []
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def __finish_build(self, collapse_slots: bool):
        """After the tree is built: fold the animation slots so the default view is just the
        list of slots, then give the editor pane a width that shows every keyframe column."""
        if collapse_slots:
            for section in self._animation_sections:
                section.set_expanded(False)
        self.__size_left_pane()

    def __size_left_pane(self):
        def apply():
            total = self._splitter.width()
            if total <= 0:
                return
            # The keyframe grid is the widest thing; its size hint is intrinsic even while the
            # slot is collapsed. Add indentation (set + slot + block) and the scrollbar.
            grid_width = max((holder.sizeHint().width() for holder in self._grid_holders),
                             default=360)
            needed = grid_width + 90
            preview_min = max(self._preview_panel.minimumWidth(), 300)
            left = min(needed, max(total - preview_min, 300))
            self._splitter.setSizes([left, max(total - left, 1)])

        # Defer one tick so the widgets have real size hints and the splitter a real width.
        QTimer.singleShot(0, apply)

    def __build(self):
        nb_anim = sum(1 for camera_set in self._collection.sets
                      for animation in camera_set.animations if not animation.empty)
        nb_frame = sum(len(block.frames) for camera_set in self._collection.sets
                       for animation in camera_set.animations if not animation.empty
                       for block in animation.blocks)
        self.summary_label.setText(
            f"{self._collection.nb_set} set(s), {nb_anim} animation(s), {nb_frame} keyframe(s)")
        for camera_set in self._collection.sets:
            self.content_layout.addWidget(self.__build_set(camera_set), 0, Qt.AlignmentFlag.AlignLeft)

    def __build_set(self, camera_set) -> CollapsibleSection:
        nb_anim = sum(1 for animation in camera_set.animations if not animation.empty)
        section = CollapsibleSection(f"Set {camera_set.index}  —  {nb_anim} animation(s)",
                                     tooltip=_SET_TOOLTIP)
        for animation in camera_set.animations:
            if animation.empty:
                section.content_layout().addWidget(
                    self.__build_empty_slot(camera_set.index, animation.slot), 0,
                    Qt.AlignmentFlag.AlignLeft)
            else:
                section.content_layout().addWidget(self.__build_animation(animation), 0,
                                                   Qt.AlignmentFlag.AlignLeft)
        return section

    def __build_empty_slot(self, set_index: int, slot: int) -> QWidget:
        """An empty slot: a note plus a button that fills it with a new default animation."""
        label = QLabel(f"Slot {slot}: empty")
        label.setStyleSheet("color: gray")
        add_button = QPushButton("+ Add animation")
        add_button.setMaximumWidth(140)
        add_button.setToolTip("Create a new camera animation in this slot (one block, two "
                              "keyframes) to edit and preview")
        add_button.clicked.connect(
            lambda _checked, s=set_index, k=slot: self.__add_animation(s, k))
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(label)
        row.addWidget(add_button)
        row.addStretch(1)
        holder = QWidget()
        holder.setLayout(row)
        return holder

    def __add_animation(self, set_index: int, slot: int):
        if not self._editable or self._collection is None:
            return
        from FF8GameData.dat.cameracollection import add_animation_to_slot
        try:
            new_data = add_animation_to_slot(self._collection.get_bytes(), set_index, slot)
        except ValueError as error:
            QMessageBox.warning(self, "Add animation", str(error))
            return
        self._collection = parse_camera_collection(new_data)
        self.__clear_content()
        self.__build()
        self.__finish_build(collapse_slots=False)  # keep slots open so the new one is visible
        self.__refresh_hex()
        self._preview_panel.invalidate()  # the section bytes changed

    def __build_animation(self, animation) -> CollapsibleSection:
        section = CollapsibleSection(f"Animation slot {animation.slot}  "
                                     f"({len(animation.blocks)} block(s))",
                                     tooltip=_ANIMATION_TOOLTIP)
        self._animation_sections.append(section)
        # Preview: play this animation's camera in the 3D viewer, sitting next to the arrow.
        preview_button = QPushButton("▶ Preview")
        preview_button.setToolTip("Preview this camera animation on the monster model")
        preview_button.setMaximumWidth(110)
        preview_button.clicked.connect(lambda _checked, anim=animation: self.__open_preview(anim))
        section.add_header_widget(preview_button)
        for block_index, block in enumerate(animation.blocks):
            block_section = CollapsibleSection(f"Block {block_index}", tooltip=_BLOCK_TOOLTIP)
            block_section.content_layout().addWidget(self.__build_block(block), 0,
                                                     Qt.AlignmentFlag.AlignLeft)
            section.content_layout().addWidget(block_section, 0, Qt.AlignmentFlag.AlignLeft)
        return section

    def __open_preview(self, animation):
        # One shared panel on the right plays whichever animation's Preview was clicked.
        # Bake it into per-frame poses first so playback matches the engine exactly (block
        # chaining, hold, cubic spline, sine easing) instead of a plain linear interpolation.
        from FF8GameData.dat.camerabake import BakedAnimation
        self._preview_panel.preview(BakedAnimation(animation))

    def __build_block(self, block) -> QWidget:
        holder = QWidget()
        holder.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        holder.setLayout(outer)

        # FOV / roll header. Only the values actually stored in this block are editable; a
        # mode that keeps/defaults them (0/1) shows the fixed meaning instead.
        header = QHBoxLayout()
        control_label = QLabel(f"ctrl 0x{block.control_word:04X}")
        control_label.setToolTip("Block control word: bits select the FOV mode (bits 6-7), "
                                 "roll mode (bits 8-9) and layout (bit 0).")
        layout_label = QLabel(f"layout {block.layout}")
        layout_label.setToolTip("Layout flag from the control word (frame-encoding variant); "
                                "both variants store the same 18-byte keyframes.")
        header.addWidget(control_label)
        header.addWidget(layout_label)
        for label, field in block.optional_fields():
            field_label = QLabel(label + ":")
            field_label.setToolTip(_BLOCK_FIELD_TOOLTIP.get(label, label))
            header.addWidget(field_label)
            spin = _bind_spin(field, tooltip=_BLOCK_FIELD_TOOLTIP.get(label, label))
            self._spin_list.append(spin)
            spin.valueChanged.connect(self.__on_value_changed)
            header.addWidget(spin)
        if not block.optional_fields():
            default_label = QLabel("FOV/roll: default")
            default_label.setToolTip("This block keeps the default FOV (0x200) and roll (0); "
                                     "neither is stored, so neither is editable here.")
            header.addWidget(default_label)
        header.addStretch(1)
        outer.addLayout(header)

        # Frame grid: one row per keyframe. Header row of column titles, then a bound spin
        # box per editable field. A keyframe is a control point; the camera interpolates from
        # one keyframe to the next over the first keyframe's Duration.
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(2)
        for col, (title, key) in enumerate(_FRAME_COLUMNS):
            header_label = QLabel(title)
            header_label.setStyleSheet("color: gray; font-size: 11px")
            if key:
                header_label.setToolTip(_FRAME_TOOLTIP[key])
            grid.addWidget(header_label, 0, col)
        for row, frame in enumerate(block.frames, start=1):
            index_label = QLabel(str(row - 1))
            index_label.setToolTip("Keyframe index within this block.")
            grid.addWidget(index_label, row, 0)
            fields = [frame.duration, frame.pos_x, frame.pos_y, frame.pos_z,
                      frame.pos_interp_mode, frame.look_x, frame.look_y, frame.look_z,
                      frame.look_interp_mode]
            for col, ((_title, key), field) in enumerate(zip(_FRAME_COLUMNS[1:], fields), start=1):
                spin = _bind_spin(field, tooltip=_FRAME_TOOLTIP[key])
                self._spin_list.append(spin)
                spin.valueChanged.connect(self.__on_value_changed)
                grid.addWidget(spin, row, col)
        grid.setColumnStretch(len(_FRAME_COLUMNS), 1)  # soak up slack past the last column
        grid_holder = QWidget()
        grid_holder.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        grid_holder.setLayout(grid)
        self._grid_holders.append(grid_holder)  # used to size the editor pane on load
        outer.addWidget(grid_holder, 0, Qt.AlignmentFlag.AlignLeft)
        return holder

    # ── Hex view / change tracking ────────────────────────────────────
    def __on_value_changed(self, _value=None):
        if self.hex_view.isVisible():
            self.__refresh_hex()

    def __toggle_hex(self):
        show = self.hex_checkbox.isChecked()
        self.hex_view.setVisible(show)
        if show:
            self.__refresh_hex()

    def __refresh_hex(self):
        if self._collection is not None:
            self.hex_view.setPlainText(bytes(self._collection.get_bytes()).hex(" "))

    def __show_info(self):
        message = QMessageBox(self)
        message.setWindowIcon(self.__camera_icon)
        message.setWindowTitle("Camera section")
        message.setTextFormat(Qt.TextFormat.RichText)
        message.setText(
            "<b>Camera animation collection</b> — monster section 6, character section 5 "
            "(same format; monsters have 1 set, characters 2).<br/><br/>"
            "Each <b>set</b> holds 8 animation slots; each <b>animation</b> is a chain of "
            "<b>blocks</b> (FOV + roll) made of <b>keyframes</b>. A keyframe places the "
            "camera (Pos X/Y/Z) and its look-at target (Look X/Y/Z) for <i>Duration</i> "
            "ticks; the engine interpolates between keyframes.<br/><br/>"
            "Values are edited in place — saving changes only the bytes you touch.<br/>"
            "See the <a href=\"https://hobbitdur.github.io/FF8ModdingWiki/technical-reference/"
            "battle/model-sections/camera-sequence/\">wiki</a> for the format.")
        message.exec()
