import os

from PyQt6.QtCore import QSize, Qt, QSignalBlocker
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel,
                             QFileDialog, QGroupBox, QMessageBox, QScrollArea, QSpinBox,
                             QFormLayout, QComboBox)

from FF8GameData.gamedata import GameData
from FF8GameData.monsterdata import EntityType
from Ifrit.IfritSeq.seqwidget import SeqWidget
from Ifrit.IfritSeq.seqcommandwidget import build_op_code_model
from Watts.wattsmanager import WattsManager


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

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData"):
        QWidget.__init__(self)

        self.game_data = GameData(game_data_folder)
        # The sequence editor needs the AnimSeq op-code data (translation, op-code
        # dropdown, code<->bytes); nothing else in r0win.dat needs game data.
        self.game_data.load_anim_sequence_data()
        self.manager = WattsManager(self.game_data)
        self._op_code_model = build_op_code_model(self.game_data)
        self._pose_seq_widgets = {}  # character name -> SeqWidget

        self.setWindowTitle("Watts")
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'hobbitdur.ico')))

        # File section
        self.file_dialog = QFileDialog()
        self.load_button = QPushButton()
        self.load_button.setIcon(QIcon(os.path.join(icon_path, 'folder.png')))
        self.load_button.setIconSize(QSize(30, 30))
        self.load_button.setFixedSize(40, 40)
        self.load_button.setToolTip("Open a r0win.dat file")
        self.load_button.clicked.connect(self.load_file)

        self.save_button = QPushButton()
        self.save_button.setIcon(QIcon(os.path.join(icon_path, 'save.svg')))
        self.save_button.setIconSize(QSize(30, 30))
        self.save_button.setFixedSize(40, 40)
        self.save_button.setToolTip("Save all modifications in the opened r0win.dat (irreversible)")
        self.save_button.clicked.connect(self.save_file)

        self.file_label = QLabel("No file loaded")

        self.sequence_view_selector = QComboBox()
        self.sequence_view_selector.addItems(self.SEQUENCE_VIEW_ITEMS)
        self.sequence_view_selector.setToolTip(
            "How every win-pose sequence is shown:\n"
            "- User-friendly: one row per command (op-code dropdown + parameters)\n"
            "- Hex-editor: the raw sequence bytes\n"
            "- IfritSeq-code: the sequence as one command per line of IfritSeq-code")
        self.sequence_view_selector.activated.connect(self._change_sequence_view)

        file_section_layout = QHBoxLayout()
        file_section_layout.addWidget(self.load_button)
        file_section_layout.addWidget(self.save_button)
        file_section_layout.addWidget(self.file_label)
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

        # Section 2 - camera: shown read-only (no dedicated editor)
        self.camera_group = QGroupBox("Section 2 - Victory camera")
        camera_layout = QVBoxLayout()
        self.camera_label = QLabel("-")
        camera_layout.addWidget(self.camera_label)
        self.camera_group.setLayout(camera_layout)
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

        main_layout = QVBoxLayout()
        main_layout.addLayout(file_section_layout)
        main_layout.addWidget(scroll_area)
        self.setLayout(main_layout)

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
                                   op_code_model=self._op_code_model)
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

    def _change_sequence_view(self):
        view = self.sequence_view_selector.currentIndex()
        for seq_widget in self._pose_seq_widgets.values():
            seq_widget.set_view(view)

    # ------------------------------------------------------------------ actions
    def load_file(self):
        file_name = self.file_dialog.getOpenFileName(parent=self, caption="Search r0win.dat file",
                                                     filter="*.dat", directory=os.getcwd())[0]
        if not file_name:
            return
        try:
            self.manager.load_file(file_name)
        except ValueError as error:
            QMessageBox.critical(self, "Watts", f"Not a r0win.dat file:\n{error}")
            return
        self.file_label.setText(os.path.basename(file_name))
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
        camera_sets = ", ".join(str(count) for count in summary["camera_sets"])
        self.camera_label.setText(
            f"{summary['camera_size']} bytes, {len(summary['camera_sets'])} animation sets "
            f"({camera_sets} animations) - read-only")
