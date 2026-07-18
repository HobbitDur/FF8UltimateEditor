import os
import re

from PyQt6.QtCore import Qt, QSignalBlocker
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel,
                             QGroupBox, QMessageBox, QScrollArea, QSpinBox, QDoubleSpinBox,
                             QFormLayout, QComboBox, QSplitter, QFileDialog)

from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from FF8GameData.gamedata import GameData
from FF8GameData.monsterdata import EntityType
from Ifrit.IfritSeq.seqwidget import SeqWidget
from Ifrit.IfritSeq.seqcommandwidget import build_op_code_model
from Watts.wattsmanager import WattsManager
from Watts.cameracollectionwidget import CameraCollectionWidget
from FF8GameData.dat.camerabake import BakedAnimation


class WattsWidget(QWidget):
    """r0win.dat editor: the battle victory sequence - win fanfare, victory camera, and
    the six dedicated character win poses (Rinoa, Quistis, Irvine, Edea, Selphie, Kiros).

    The two things a modder can actually change are exposed inline: the fanfare song id
    (Section 1) and each win pose's animation sequence (Sections 3-8, edited with the
    same three-view sequence editor as IfritSeq). The camera and the raw pose animations
    are shown read-only.

    Named after Watts, the Forest Owls' intelligence expert - he always has the info,
    sir!"""

    # Same three views as IfritSeq's expert selector (raw code has no meaning here)
    SEQUENCE_VIEW_ITEMS = ["User-friendly", "Hex-editor", "IfritSeq-code"]
    # Held copies of the win pose's last frame so it winds up once then holds (like the
    # game) instead of looping; larger than any camera slot / whole-set playback.
    _WIN_POSE_HOLD_FRAMES = 2048

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData", file_registry=None):
        QWidget.__init__(self)

        if file_registry is None:  # The tool is used alone, it shares its files with nobody
            file_registry = FileRegistry()

        self._game_data_folder = game_data_folder
        self.game_data = GameData(game_data_folder)
        # The sequence editor needs the AnimSeq op-code data (translation, op-code
        # dropdown, code<->bytes); nothing else in r0win.dat needs game data.
        self.game_data.load_anim_sequence_data()
        self.manager = WattsManager(self.game_data)
        self._op_code_model = build_op_code_model(self.game_data)
        self._pose_seq_widgets = {}  # character name -> SeqWidget

        self.setWindowTitle("Watts")
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'hobbitdur.ico')))

        # File section: r0win.dat, driven by the shared header toolbar (Import / Save).
        self.r0win_binding = FileBinding("r0win.dat", file_registry,
                                         load_callback=self.load_file, save_callback=self.save_file)

        self.sequence_view_selector = QComboBox()
        self.sequence_view_selector.addItems(self.SEQUENCE_VIEW_ITEMS)
        self.sequence_view_selector.setToolTip(
            "How every win-pose sequence is shown:\n"
            "- User-friendly: one row per command (op-code dropdown + parameters)\n"
            "- Hex-editor: the raw sequence bytes\n"
            "- IfritSeq-code: the sequence as one command per line of IfritSeq-code")
        self.sequence_view_selector.activated.connect(self._change_sequence_view)

        file_section_layout = QHBoxLayout()
        file_section_layout.addStretch(1)
        file_section_layout.addWidget(QLabel("Sequence view:"))
        file_section_layout.addWidget(self.sequence_view_selector)

        # Editor
        editor_layout = QVBoxLayout()

        # Section 1 - fanfare: only the song id is meaningful on PC, so that is all we edit
        fanfare_group = QGroupBox("Section 1 - Victory fanfare (music)")
        fanfare_form = QFormLayout()
        self.song_id_spinbox = QSpinBox()
        self.song_id_spinbox.setRange(1, 255)
        self.song_id_spinbox.setToolTip(
            "AKAO id of the fanfare. On PC the game plays DirectMusic song id = AKAO id - 1;\n"
            "the rest of Section 1 (the AKAO score and sample bank) is not used on PC.")
        self.song_id_spinbox.valueChanged.connect(self._on_song_id_changed)
        self.song_id_hint = QLabel("-")
        fanfare_form.addRow("AKAO song id:", self.song_id_spinbox)
        fanfare_form.addRow("PC plays music id:", self.song_id_hint)
        fanfare_group.setLayout(fanfare_form)
        editor_layout.addWidget(fanfare_group)

        # Section 2 - camera: the keyframed animation collection is editable (reusing the
        # same CameraCollection model as Ifrit's camera tab); the camera setting (the
        # camera-sequence byte-code) is kept read-only.
        self.camera_group = QGroupBox("Section 2 - Victory camera")
        self.camera_layout = QVBoxLayout()
        self.camera_label = QLabel("-")
        self.camera_label.setWordWrap(True)
        self.camera_layout.addWidget(self.camera_label)
        self._camera_editor = None  # CameraCollectionWidget, rebuilt on load
        self.camera_group.setLayout(self.camera_layout)
        editor_layout.addWidget(self.camera_group)

        # Sections 3-8 - win poses, rebuilt on load
        self._pose_groups_layout = QVBoxLayout()
        editor_layout.addLayout(self._pose_groups_layout)
        editor_layout.addStretch(1)

        self.editor_container = QWidget()
        self.editor_container.setLayout(editor_layout)
        self.editor_container.setEnabled(False)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self.editor_container)

        # Right side: the shared 3D camera preview, fed by a character model the user
        # imports (r0win.dat carries no model of its own).
        self._preview_models = []      # up to 3 dicts {name, manager, win_pose_id, frame_count}
        self._preview_game_data = None  # one load_all()ed GameData shared by all party models
        self._preview_panel = None     # CameraPreviewPanel over the current composite
        self._preview_zoom = 1.5       # extra dolly-back on top of the party recentre
        self._preview_source = None    # ("slot", animation) | ("set", camera_set) - to re-bake
        self._preview_holder = self._build_preview_side(icon_path)

        body_splitter = QSplitter(Qt.Orientation.Horizontal)
        body_splitter.addWidget(scroll_area)
        body_splitter.addWidget(self._preview_holder)
        body_splitter.setStretchFactor(0, 3)
        body_splitter.setStretchFactor(1, 2)

        main_layout = QVBoxLayout()
        main_layout.addLayout(file_section_layout)
        main_layout.addWidget(body_splitter, 1)
        self.setLayout(main_layout)

        self.r0win_binding.load_opened_file()  # Another tool may have opened r0win.dat already

    def file_bindings(self):
        """The files the shared header toolbar drives for this tool (just r0win.dat)."""
        return [self.r0win_binding]

    # ---------------------------------------------------------------- preview
    _MAX_MODELS = 3          # a battle party is at most 3
    _PARTY_SPACING = 7.0     # lateral gap between characters, in model vertex units
    # com_id -> character name (all 11), for labels
    _COM_ID_NAME = {0: "Squall", 1: "Zell", 2: "Irvine", 3: "Quistis", 4: "Rinoa",
                    5: "Selphie", 6: "Seifer", 7: "Edea", 8: "Laguna", 9: "Kiros",
                    10: "Ward"}
    # Fallback vanilla body animation played by weapon sequence 18 ("Victory Animation")
    # for the characters with no r0win pose (values verified from their weapon seq 18).
    _OWN_VICTORY_ANIM = {0: 30, 1: 30, 6: 26, 8: 28, 10: 26}

    def _build_preview_side(self, icon_path) -> QWidget:
        holder = QWidget()
        layout = QVBoxLayout()
        self._import_dat_button = QPushButton("Select character .dat files (up to 3)")
        self._import_dat_button.setToolTip(
            "Pick 1-3 character battle models (d?c???.dat) at once to stand in as the victory "
            "party (Ctrl/Shift-click to multi-select). The set list greys out to match how "
            "many you load.")
        self._import_dat_button.clicked.connect(self._import_character_dat)
        self._clear_models_button = QPushButton("Clear")
        self._clear_models_button.setToolTip("Remove all imported characters")
        self._clear_models_button.clicked.connect(self._clear_preview_models)
        import_row = QHBoxLayout()
        import_row.addWidget(self._import_dat_button)
        import_row.addWidget(self._clear_models_button)

        self._preview_model_label = QLabel("No character imported")
        self._preview_model_label.setStyleSheet("color: gray")
        self._preview_model_label.setWordWrap(True)

        # Extra dolly-back on top of the automatic party recentre, for headroom.
        self._zoom_spinbox = QDoubleSpinBox()
        self._zoom_spinbox.setRange(1.0, 8.0)
        self._zoom_spinbox.setSingleStep(0.25)
        self._zoom_spinbox.setValue(self._preview_zoom)
        self._zoom_spinbox.setToolTip("Pull the camera further back for more headroom "
                                      "(1.0 = the recentred game distance)")
        self._zoom_spinbox.valueChanged.connect(self._on_zoom_changed)
        zoom_row = QHBoxLayout()
        zoom_row.addWidget(QLabel("Zoom out:"))
        zoom_row.addWidget(self._zoom_spinbox)
        zoom_row.addStretch(1)

        self._preview_container = QVBoxLayout()
        layout.addLayout(import_row)
        layout.addWidget(self._preview_model_label)
        layout.addLayout(zoom_row)
        layout.addLayout(self._preview_container, 1)
        holder.setLayout(layout)
        self._preview_icon_path = icon_path
        return holder

    def _import_character_dat(self):
        remaining = self._MAX_MODELS - len(self._preview_models)
        if remaining <= 0:
            QMessageBox.information(self, "Watts",
                                    f"A party is at most {self._MAX_MODELS} characters. "
                                    "Use Clear to start over.")
            return
        file_names = QFileDialog.getOpenFileNames(
            parent=self,
            caption=f"Select up to {remaining} character battle model(s) (d?c???.dat)",
            filter="Character battle model (d?c*.dat)", directory=os.getcwd())[0]
        if not file_names:
            return
        added, errors = 0, []
        for file_name in file_names:
            if len(self._preview_models) >= self._MAX_MODELS:
                errors.append(f"{os.path.basename(file_name)}: party is already full "
                              f"({self._MAX_MODELS} characters)")
                break
            try:
                self._preview_models.append(self._load_character_entry(file_name))
                added += 1
            except Exception as error:
                errors.append(f"{os.path.basename(file_name)}: {error}")
        if added:
            self._rebuild_preview_panel()
            self._update_set_gating()
            self._refresh_model_label()
        if errors:
            QMessageBox.warning(self, "Watts",
                                "Some files were not added:\n- " + "\n- ".join(errors))

    def _shared_preview_game_data(self):
        """One fully-loaded GameData reused by every party model, so load_all() (the heavy
        part of importing a model) runs once instead of once per character."""
        if self._preview_game_data is None:
            self._preview_game_data = GameData(self._game_data_folder)
            self._preview_game_data.load_all()
        return self._preview_game_data

    def _load_character_entry(self, file_name):
        """Load one character .dat and prepare its victory pose; raise on any problem.
        Only a character battle model is accepted (its skeleton is what the win poses were
        authored for): monster (c0m*) and weapon (d?w*) files are rejected."""
        if not re.match(r"^d[0-9a-f]c\d+\.dat$", os.path.basename(file_name), re.IGNORECASE):
            raise ValueError("not a character model (expected a name like d4c009.dat)")
        from Ifrit.ifritmanager import IfritManager
        manager = IfritManager(self._game_data_folder,
                               game_data=self._shared_preview_game_data())
        manager.init_from_file(file_name)
        if manager.enemy.entity_type not in (EntityType.CHARACTER,
                                             EntityType.CHARACTER_NO_WEAPON):
            raise ValueError("not a character battle model (unexpected section layout)")
        entry = self._setup_victory_pose(manager, file_name)
        if entry is None:
            raise ValueError("could not identify the character or its victory pose")
        return entry

    def _clear_preview_models(self):
        self._preview_models = []
        self._preview_source = None
        if self._preview_panel is not None:
            self._preview_panel.setParent(None)
            self._preview_panel.deleteLater()
            self._preview_panel = None
        self._update_set_gating()
        self._refresh_model_label()

    def _refresh_model_label(self):
        if not self._preview_models:
            self._preview_model_label.setText("No character imported")
            return
        parts = [f"{e['name']} ({e['pose_label']})" for e in self._preview_models]
        self._preview_model_label.setText(f"Party ({len(parts)}): " + ", ".join(parts))

    # ----------------------------------------------------------- victory pose
    def _setup_victory_pose(self, manager, file_name):
        """Prepare `manager` to render its character's victory pose. Returns an entry dict
        {name, manager, win_pose_id, frame_count, pose_label}, or None if unidentified.

        The six r0win characters get the r0win pose grafted; the others (Squall, Zell,
        Seifer, Laguna, Ward) use their own model animation played by weapon sequence 18."""
        match = re.match(r"^d([0-9a-f])c\d+\.dat$", os.path.basename(file_name).lower())
        if not match:
            return None
        com_id = int(match.group(1), 16)
        name = self._COM_ID_NAME.get(com_id, f"com_id {com_id}")
        enemy = manager.enemy
        pose = next((p for p in self.manager.poses if p.character.com_id == com_id), None)
        if pose is not None:
            win_pose_id, label = self._graft_r0win_pose(pose, enemy)
        else:
            win_pose_id, label = self._select_own_victory_anim(com_id, file_name, enemy)
        if win_pose_id is None:
            return None
        frame_count = len(enemy.animation_data.animations[win_pose_id].frames)
        # Unique frames = before the held padding; the rest repeat, so the composite need
        # only compute these once (playback then holds the last one).
        real_frame_count = max(1, frame_count - self._WIN_POSE_HOLD_FRAMES)
        return {"name": name, "manager": manager, "win_pose_id": win_pose_id,
                "frame_count": frame_count, "real_frame_count": real_frame_count,
                "pose_label": label}

    def _graft_r0win_pose(self, pose, enemy):
        bone_section = enemy.bone_data
        if bone_section is None or bone_section.nb_bone != pose.character.body_bones:
            return None, None
        try:
            from FF8GameData.monsterdata import AnimationSection
            pose_section = AnimationSection()
            pose_section.analyze(bytes(pose.body_anim), bone_section)
            animation = pose_section.animations[0]
            self._hold_last_frame(animation)
            enemy.animation_data.animations.append(animation)
            enemy.animation_data.nb_animations = len(enemy.animation_data.animations)
            return enemy.animation_data.nb_animations - 1, "r0win pose"
        except Exception:
            return None, None

    def _select_own_victory_anim(self, com_id, file_name, enemy):
        anim_id = self._victory_anim_from_weapon(com_id, file_name)
        label = f"own seq 18, anim {anim_id}"
        if anim_id is None:
            anim_id = self._OWN_VICTORY_ANIM.get(com_id)
            label = f"own victory anim {anim_id}"
        if anim_id is None or not (0 <= anim_id < enemy.animation_data.nb_animations):
            return None, None
        self._hold_last_frame(enemy.animation_data.animations[anim_id])
        return anim_id, label

    def _victory_anim_from_weapon(self, com_id, file_name):
        """The body animation id that weapon sequence 18 plays, read from a sibling weapon
        file (d<comId>w*.dat). None if no readable weapon is found."""
        import glob
        pattern = os.path.join(os.path.dirname(file_name), f"d{com_id:x}w*.dat")
        for weapon_path in sorted(glob.glob(pattern)):
            anim_id = self._seq18_anim_id(weapon_path)
            if anim_id is not None:
                return anim_id
        return None

    def _seq18_anim_id(self, path):
        try:
            from FF8GameData.dat.monsteranalyser import MonsterAnalyser
            from FF8GameData.dat.sequencecommand import read_sequence
            game_data = self._shared_preview_game_data()
            analyser = MonsterAnalyser(game_data)
            analyser.load_file_data(path, game_data)
            analyser.analyse_loaded_data(game_data)
            sequences = {s["id"]: bytes(s["data"])
                         for s in analyser.seq_animation_data["seq_animation_data"]}
            data = sequences.get(18)
            if not data:
                return None
            for command in read_sequence(game_data, data):
                if command.is_animation():
                    return command.get_animation_id()
        except Exception:
            return None
        return None

    def _hold_last_frame(self, animation):
        """Pad an animation with copies of its final frame so the preview panel (which
        loops model animations) winds it up once and then holds the pose, like the game."""
        if animation.frames:
            animation.frames = list(animation.frames) + \
                [animation.frames[-1]] * self._WIN_POSE_HOLD_FRAMES

    # -------------------------------------------------------- composite / play
    def _rebuild_preview_panel(self):
        """(Re)build the composite of the loaded characters and the panel that films it."""
        from Watts.compositemodel import CompositeVictoryModel, party_slot_offsets
        from Ifrit.IfritCameraSeq.camerapreview import CameraPreviewPanel
        if self._preview_panel is not None:
            self._preview_panel.setParent(None)
            self._preview_panel.deleteLater()
            self._preview_panel = None
        if not self._preview_models:
            return
        offsets = party_slot_offsets(len(self._preview_models), self._PARTY_SPACING)
        entries = [dict(entry, offset=offset)
                   for entry, offset in zip(self._preview_models, offsets)]
        composite = CompositeVictoryModel(entries)
        self._preview_panel = CameraPreviewPanel(composite)
        self._preview_container.addWidget(self._preview_panel, 1)

    def _update_set_gating(self):
        """Grey out the camera sets that do not match the party size: set 2 is the
        full-party framing (needs 3), sets 0/1 are the general pair (need at least 1)."""
        if self._camera_editor is None:
            return
        count = len(self._preview_models)
        if count == 0:
            enabled = None  # nothing imported yet: leave all usable
        else:
            enabled = {0, 1} if count < 3 else {0, 1, 2}
        self._camera_editor.set_enabled_set_indices(enabled)

    def _on_preview_requested(self, animation):
        if not self._require_preview_model():
            return
        self._preview_source = animation
        self._play_preview()

    def _on_zoom_changed(self, value):
        self._preview_zoom = value
        if self._preview_panel is not None and self._preview_source is not None:
            self._play_preview()  # re-frame the current playback

    def _play_preview(self):
        """Bake the slot (engine-faithful), recentre it on the party position so the
        characters are in frame, dolly back by the zoom factor, and play it. The game
        plays one slot per victory (never a whole set), so only a single slot is previewed."""
        from FF8GameData.dat.camerabake import bake_camera_animation, zoom_out
        frames = bake_camera_animation(self._preview_source)
        frames = self._recenter_on_party(frames)
        self._preview_panel.preview(BakedAnimation(zoom_out(frames, self._preview_zoom)))

    @staticmethod
    def _recenter_on_party(frames):
        """Shift the whole camera path so its average look-at (the party position it films)
        sits at the origin - which the preview maps to the model centre - so the imported
        characters are actually in frame instead of off to the side / above."""
        if not frames:
            return frames
        n = len(frames)
        rx = sum(f[3] for f in frames) / n
        ry = sum(f[4] for f in frames) / n
        rz = sum(f[5] for f in frames) / n
        return [(f[0] - rx, f[1] - ry, f[2] - rz, f[3] - rx, f[4] - ry, f[5] - rz)
                for f in frames]

    def _require_preview_model(self) -> bool:
        if self._preview_panel is None:
            QMessageBox.information(
                self, "Watts",
                "Add a character .dat first (button on the right) so the camera has "
                "characters to film.")
            return False
        return True

    # ------------------------------------------------------------- pose groups
    def _rebuild_pose_groups(self):
        while self._pose_groups_layout.count():
            item = self._pose_groups_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._pose_seq_widgets.clear()
        view = self.sequence_view_selector.currentIndex()
        for pose in self.manager.poses:
            character = pose.character
            pose_group = QGroupBox(
                f"Section {character.section_id} - {character.name} win pose "
                f"(com_id {character.com_id})")
            pose_layout = QVBoxLayout()

            # The character body animation and, when present, the weapon animation - both
            # driven by the one sequence below - shown read-only.
            body_frames = pose.anim_frame_count(pose.body_anim)
            info_label = QLabel(
                f"Character animation: {len(pose.body_anim)} bytes, {body_frames} frames "
                f"({character.body_bones} bones)")
            pose_layout.addWidget(info_label)
            if pose.weapon_anim is not None:
                weapon_frames = pose.anim_frame_count(pose.weapon_anim)
                pose_layout.addWidget(QLabel(
                    f"Weapon animation: {len(pose.weapon_anim)} bytes, {weapon_frames} "
                    f"frames ({character.weapon_bones} bones)"))

            pose_layout.addWidget(QLabel("Animation sequence (drives both):"))
            seq_widget = SeqWidget(bytearray(pose.get_seq_bytecode()), 0,
                                   EntityType.MONSTER, game_data=self.game_data,
                                   op_code_model=self._op_code_model,
                                   title=f"{character.name} win-pose sequence")
            seq_widget.set_view(view)
            seq_widget.data_changed.connect(self._make_seq_handler(pose, seq_widget))
            self._pose_seq_widgets[character.name] = seq_widget
            pose_layout.addWidget(seq_widget)

            pose_group.setLayout(pose_layout)
            self._pose_groups_layout.addWidget(pose_group)

    def _make_seq_handler(self, pose, seq_widget):
        def handler():
            pose.set_seq_bytecode(bytes(seq_widget.getByteData()))
        return handler

    # ------------------------------------------------------------------- camera
    def _rebuild_camera(self):
        if self._camera_editor is not None:
            self._camera_editor.setParent(None)
            self._camera_editor.deleteLater()
            self._camera_editor = None
        collection = self.manager.camera_collection
        if collection is not None and not collection.is_empty():
            self._camera_editor = CameraCollectionWidget(
                collection, set_notes=self._camera_set_notes(collection))
            self._camera_editor.preview_requested.connect(self._on_preview_requested)
            self.camera_layout.addWidget(self._camera_editor)
            self._update_set_gating()

    @staticmethod
    def _camera_set_notes(collection):
        """What the r0win camera sequence uses each set for. Its byte-code branches on
        whether all 3 party members are celebrating: a full party of 3 uses set 2, any
        smaller party uses set 0 or set 1 (chosen at random). So set 2 is the full-party
        framing and sets 0/1 are the general pair - it is not a plain 1/2/3 mapping."""
        notes = {
            0: "1-2 characters (random)",
            1: "1-2 characters (random)",
            2: "3 characters - full party",
        }
        # Only annotate if the collection has exactly the 3 vanilla sets
        if len(collection.sets) != 3:
            return {}
        return notes

    def _change_sequence_view(self):
        view = self.sequence_view_selector.currentIndex()
        for seq_widget in self._pose_seq_widgets.values():
            seq_widget.set_view(view)

    # ------------------------------------------------------------------ actions
    def load_file(self, file_name):
        try:
            self.manager.load_file(file_name)
        except ValueError as error:
            QMessageBox.critical(self, "Watts", f"Not a r0win.dat file:\n{error}")
            return
        self._rebuild_camera()
        self._rebuild_pose_groups()
        self.editor_container.setEnabled(True)
        self.refresh_info()

    def save_file(self):
        if self.manager.file_path:
            self.manager.save_file()

    def _on_song_id_changed(self, value):
        if not self.manager.poses:
            return
        self.manager.set_fanfare_akao_id(value)
        self.song_id_hint.setText(f"{value - 1}")

    def refresh_info(self):
        summary = self.manager.get_summary()
        with QSignalBlocker(self.song_id_spinbox):
            self.song_id_spinbox.setValue(summary["fanfare_akao_id"])
        self.song_id_hint.setText(f"{summary['fanfare_akao_id'] - 1}")
        camera = summary["camera"]
        set_frames = ["+".join(str(slot["frames"]) for slot in cam_set["slots"] if not slot["empty"])
                      for cam_set in camera["sets"]]
        collection_note = (f"{camera['nb_set']} animation sets" if camera["collection_parsed"]
                           else "collection not recognised (kept raw)")
        self.camera_label.setText(
            f"{summary['camera_size']} bytes total: camera sequence (byte-code) "
            f"{camera['setting_size']} bytes - read-only; animation collection "
            f"{camera['collection_size']} bytes - {collection_note}. "
            f"Keyframes per set: {'; '.join(set_frames)}.")
