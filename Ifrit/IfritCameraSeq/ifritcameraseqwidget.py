"""The Camera tab: an editor for a battle .dat's camera animation collection - monster
section 6, and character (dXc) section 5.

The camera section is NOT a byte-code program like the animation section IfritSeq edits; it is
a set of key-framed camera motions (see FF8GameData/dat/cameracollection.py): sets -> 8
animation slots -> blocks (easing, layout, FOV, roll) -> keyframes. The keyframes are edited
with the shared Common/cameracollectionwidget grid, the same one Fujin's and Alexander's camera
editors use, so every camera editor offers the same lists and layout. A value edit patches its
field in place (saving changes only the bytes touched); adding or removing a keyframe, a slot's
animation or changing a block's FOV/roll mode rebuilds the collection.

Both monster section 6 and character section 5 are the *same* bare camera-animation collection
format (verified against FF8_EN.exe: the game plays the acting entity's own collection via
cameraWhenDoingAction / command_queue->unk09). The only difference is the set count: monsters
usually have 1 set (8 slots), characters have 2 sets (16 slots). The byte-code camera VM only
exists in stage/R0WIN/spell blobs, not in these per-entity sections.
"""
import os

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
                             QCheckBox, QMessageBox, QPlainTextEdit, QSplitter)

from Common.cameracollectionwidget import CameraCollectionWidget
from Common.deferredcall import defer
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


class IfritCameraSeqWidget(QWidget):
    """Camera animation collection editor for a monster's section 6 (a character's section 5)."""

    # Emitted after any edit is written into enemy.section_raw_data (value change or structural
    # edit). The host pane dirties the file and records an undo step from it (camera writes
    # the model live, like Stat/3D/Seq - nothing deferred to Save).
    data_edited = pyqtSignal()

    def __init__(self, ifrit_manager: IfritManager, icon_path="Resources", file_registry=None):
        QWidget.__init__(self)
        self.ifrit_manager = ifrit_manager
        self.icon_path = icon_path
        self._collection = None       # the parsed CameraCollection (a copy we edit)
        self._editable = False        # False for a file with no editable camera section
        self._collection_widget = None
        self.__camera_icon = QIcon(os.path.join(icon_path, 'ifrit.ico'))

        root = QVBoxLayout()
        self.setLayout(root)

        # ── Toolbar ──────────────────────────────────────────────────
        toolbar = QHBoxLayout()
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

        # ── Keyframes (left) + shared 3D preview (right), split ──────
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self._preview_panel = CameraPreviewPanel(self.ifrit_manager, file_registry=file_registry)
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self.scroll_area)
        self._splitter.addWidget(self._preview_panel)
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 1)
        root.addWidget(self._splitter, 1)

    # ── Public API (called by IfritMonsterWidget) ─────────────────────
    def load_file(self, path: str = ""):
        self.__load()

    def set_model_paths(self, paths):
        """The models the user opened in the session (callable -> paths), the only ones the
        preview's battle stands."""
        if self._preview_panel._battle_setup is not None:
            self._preview_panel._battle_setup.set_model_paths(paths)

    def save_file(self):
        """Fold the edited bytes back into the model the file writer persists."""
        if self._editable and self._collection is not None:
            index = _CAMERA_SECTION_BY_ENTITY.get(self.ifrit_manager.enemy.entity_type)
            if index is not None:
                self.ifrit_manager.enemy.section_raw_data[index] = self._collection.get_bytes()

    # ── Loading ───────────────────────────────────────────────────────
    def __load(self):
        self.__set_collection(None)
        # The monster changed: stop any preview and reload its model on the next Preview.
        self._preview_panel.invalidate()
        self._editable = False
        enemy = getattr(self.ifrit_manager, "enemy", None)
        if enemy is None:
            self.summary_label.setText("No file loaded")
            return
        index = _CAMERA_SECTION_BY_ENTITY.get(enemy.entity_type)
        if index is None or index >= len(enemy.section_raw_data):
            self.summary_label.setText("This file type has no camera section.")
            return
        raw = bytes(enemy.section_raw_data[index])
        if len(raw) < 6:
            self.summary_label.setText(f"This file has no camera data (empty section {index}).")
            return
        try:
            collection = parse_camera_collection(raw)
        except CameraParseError as error:
            self.summary_label.setText(f"Section {index} is not a camera collection: {error}")
            return
        self._editable = True
        self.__set_collection(collection)
        self.__size_left_pane()

    def __set_collection(self, collection, expanded_sets=None):
        """Show `collection` in a new shared keyframe grid (None: nothing). Every set starts
        unfolded unless `expanded_sets` says which."""
        self._collection = collection
        if self._collection_widget is not None:
            self.scroll_area.takeWidget()
            self._collection_widget.deleteLater()
            self._collection_widget = None
        if collection is None:
            self.hex_view.clear()
            return
        if expanded_sets is None:
            expanded_sets = [camera_set.index for camera_set in collection.sets]
        self._collection_widget = CameraCollectionWidget(collection, structure_edits=True,
                                                         expanded_sets=expanded_sets)
        self._collection_widget.data_changed.connect(self.__on_value_changed)
        self._collection_widget.preview_requested.connect(self._preview_panel.preview)
        self._collection_widget.collection_rebuilt.connect(self.__on_collection_rebuilt)
        self.scroll_area.setWidget(self._collection_widget)
        self.__update_summary()
        self.__refresh_hex()

    def __update_summary(self):
        animations = [animation for camera_set in self._collection.sets
                      for animation in camera_set.animations if not animation.empty]
        frames = sum(len(block.frames) for animation in animations for block in animation.blocks)
        self.summary_label.setText(
            f"{self._collection.nb_set} set(s), {len(animations)} animation(s), {frames} keyframe(s)")

    def __on_collection_rebuilt(self, data):
        """A keyframe, a slot's animation or a block's FOV/roll mode was added or removed: show
        the new collection where the user was, and write it to the monster."""
        expanded = self._collection_widget.expanded_set_indices()
        scroll = self.scroll_area.verticalScrollBar().value()
        self.__set_collection(parse_camera_collection(data), expanded)
        self.scroll_area.verticalScrollBar().setValue(scroll)
        self._preview_panel.invalidate()  # its animation objects are gone
        self.__sync_and_notify()

    def __size_left_pane(self):
        def apply():
            total = self._splitter.width()
            if total <= 0 or self._collection_widget is None:
                return
            # The keyframe grid is the widest thing; add the scrollbar.
            needed = self._collection_widget.sizeHint().width() + 30
            preview_min = max(self._preview_panel.minimumWidth(), 300)
            left = min(needed, max(total - preview_min, 300), max(300, int(total * .65)))
            self._splitter.setSizes([left, max(total - left, 1)])

        # Defer one tick so the widgets have real size hints and the splitter a real width.
        # Tied to this widget: a call arriving after it is gone would size a deleted C++ splitter,
        # which aborts the process rather than reporting (see Common/deferredcall).
        defer(self, apply)

    # ── Hex view / change tracking ────────────────────────────────────
    def __on_value_changed(self):
        self.__refresh_hex()
        self._preview_panel.refresh()      # taken on the next ▶ Play
        self.__sync_and_notify()

    def __sync_and_notify(self):
        """Push the edited collection into the in-memory monster now and tell the host pane."""
        self.save_file()                   # collection.get_bytes() -> enemy.section_raw_data (live)
        self.data_edited.emit()

    def __toggle_hex(self):
        self.hex_view.setVisible(self.hex_checkbox.isChecked())
        self.__refresh_hex()

    def __refresh_hex(self):
        if self._collection is not None and not self.hex_view.isHidden():
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
            "<b>blocks</b> (easing, layout, FOV, roll) made of <b>keyframes</b>. A keyframe "
            "places the camera (Pos X/Y/Z) and its look-at target (Look X/Y/Z) in the frame its "
            "mode names; <i>Frames</i> is the time to the next keyframe (1/15 s each) and the "
            "engine interpolates between keyframes.<br/><br/>"
            "Values are edited in place — saving changes only the bytes you touch.<br/>"
            "See the <a href=\"https://hobbitdur.github.io/FF8ModdingWiki/technical-reference/"
            "battle/model-sections/camera-sequence/\">wiki</a> for the format.")
        message.exec()
