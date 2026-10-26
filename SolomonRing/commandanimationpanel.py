"""Read-only animation references for built-in direct execution types."""
import os

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
                             QPushButton, QGroupBox, QPlainTextEdit)

from Common.filebinding import FileBinding
from SmallWidget.nowheel import NoWheelComboBox
from FF8GameData.dat.cameracollection import parse_camera_collection, CameraParseError
from FF8GameData.dat.sequencecodec import sequence_to_code
from FF8GameData.dat.animloopdetector import find_character_weapon_file_list
from FF8GameData.dat.monsteranalyser import MonsterAnalyser
from FF8GameData.monsterdata import EntityType
from SolomonRing.commandtypes import DIRECT_COMMAND_ANIMATIONS


class CommandAnimationPanel(QWidget):
    file_bindings_changed = pyqtSignal()
    render_preview_changed = pyqtSignal(bool)
    preview_available_changed = pyqtSignal(bool)

    def __init__(self, game_data, file_registry, parent=None):
        super().__init__(parent)
        self.setProperty("read_only_preview", True)
        self.game_data = game_data
        self.file_registry = file_registry
        self._sources = {}
        self._character = None
        self.character_binding = FileBinding(
            "Battle character", file_registry, load_callback=self._load_character,
            file_filter="Character model (d?c*.dat)", read_only=True)
        self.character_binding.file_closed.connect(self._clear_character)
        self._command = None
        self._execution_type = None
        self._seq_id = None
        self._cam_ids = ()
        self._preview = None
        self._preview_source = None
        self._render_active = False
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        group = QGroupBox("Command animations (read-only)")
        form = QFormLayout(group)
        self.seq_value = QLabel()
        self.cam_value = QLabel()
        self.cam_algorithm = QLabel()
        self.cam_algorithm.setWordWrap(True)
        self.cam_algorithm.setToolTip(
            "previous is the last cam anim entry remembered for the acting character. "
            "random(a–b) includes both ends; % 6 wraps the result into 0–5.\n"
            "Rounding is applied after that calculation: 1→0, 3→2, 5→4, then the result is remembered.\n"
            "The single-character test reads animation flags (mask 0x41021), not the command's targeting flags.\n"
            "The targeting guard checks active target display mode: 1 = on-model targeting, "
            "2 = target-name list, 0 = no active target-display mode.")
        form.addRow("Seq anim:", self.seq_value)
        form.addRow("Initial cam anim:", self.cam_value)
        form.addRow("Selection:", self.cam_algorithm)
        self.cam_value.setToolTip("Entries in the acting character's camera collection. "
                                 "The effect may start another cam anim afterward.")
        layout.addWidget(group)

        self.import_button = QPushButton("Import character…")
        self.import_button.setToolTip(
            "Load or replace the preview character. Its linked weapon files are loaded "
            "automatically from the same folder. All imported files are read-only.")
        self.import_button.clicked.connect(self._import_dialog)
        layout.addWidget(self.import_button)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        seq_group = QGroupBox("Seq anim code (IfritSeq-code)")
        seq_layout = QVBoxLayout(seq_group)
        self.seq_source = NoWheelComboBox()
        self.seq_source.currentIndexChanged.connect(self._refresh_seq)
        seq_layout.addWidget(self.seq_source)
        self.seq_code = QPlainTextEdit()
        self.seq_code.setReadOnly(True)
        self.seq_code.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.seq_code.setMinimumHeight(90)
        seq_layout.addWidget(self.seq_code)
        layout.addWidget(seq_group, 1)

        cam_group = QGroupBox("Initial cam anim preview")
        self._camera_layout = QVBoxLayout(cam_group)
        row = QHBoxLayout()
        self.cam_choice = NoWheelComboBox()
        self.cam_choice.setToolTip("Choose which possible initial cam anim to preview. "
                                   "This does not change the command.")
        self.cam_choice.currentIndexChanged.connect(self._refresh_camera)
        self.preview_button = QPushButton("Preview cam anim")
        self.preview_button.clicked.connect(self._preview_camera)
        row.addWidget(self.cam_choice, 1)
        row.addWidget(self.preview_button)
        self._camera_layout.addLayout(row)
        self.cam_status = QLabel()
        self.cam_status.setWordWrap(True)
        self._camera_layout.addWidget(self.cam_status)
        layout.addWidget(cam_group, 2)
        self._refresh_sources()
        self.set_command(None)

    def file_bindings(self):
        # One import/reload route replaces the whole character, including its weapons.
        return [self.character_binding]

    def set_command(self, command, execution_type=None):
        if (command, execution_type) == (self._command, self._execution_type) and command is not None:
            return
        self._command = command
        self._execution_type = execution_type
        self._stop_preview()
        code = (execution_type or 24) if command is not None and command >= 39 \
            and execution_type is not None else command
        profile = DIRECT_COMMAND_ANIMATIONS.get(code)
        self.setVisible(profile is not None)
        self._seq_id, self._cam_ids = profile if profile else (None, ())
        self.seq_value.setText(str(self._seq_id) if profile else "—")
        self.cam_value.setText("0–5 (random)" if len(self._cam_ids) == 6 else
                               "6 or 7 (random)" if self._cam_ids else "None")
        if len(self._cam_ids) == 6:
            algorithm = ("(previous + 2 + random(0–3)) % 6. For multiple targets, or a character "
                         "target with low-HP, Poison, Sleep or Curse animation flags, use an even "
                         "entry (0, 2 or 4). This initial camera is skipped during on-model target selection.")
        elif self._cam_ids:
            algorithm = ("6 + random(0–1): selects 6 or 7. This initial camera can also start "
                         "during on-model target selection.")
        else:
            algorithm = "This command does not select an initial cam anim."
        self.cam_algorithm.setText(algorithm if profile else "")
        self.cam_choice.blockSignals(True)
        self.cam_choice.clear()
        for cam_id in self._cam_ids:
            self.cam_choice.addItem(f"Cam anim {cam_id} (set 0)", cam_id)
        self.cam_choice.blockSignals(False)
        self._refresh_seq()
        self._refresh_camera()
        self.preview_available_changed.emit(profile is not None)

    def _import_dialog(self):
        self.character_binding.open_dialog(
            self, self.file_registry.last_folder("solomonring_animations"))

    def import_character(self, path):
        self.character_binding.open_path(str(path))

    def _load_character(self, path):
        name = os.path.basename(path)
        try:
            character = self._read_source(path)
            if character['manager'].enemy.entity_type not in (
                    EntityType.CHARACTER, EntityType.CHARACTER_NO_WEAPON):
                raise ValueError("select a character body file, not a weapon or monster")
        except Exception as error:
            self.file_registry.close_file(self.character_binding.file_name)
            self.status.setText(f"Cannot import {name}: {error}")
            return

        self._clear_character()
        self._character = character
        self._sources[name] = character
        skipped = []
        for weapon_path in find_character_weapon_file_list(path):
            try:
                if weapon_path.stat().st_size == 0:
                    continue  # Ifrit also skips empty, unused weapon slots.
                self._sources[weapon_path.name] = self._read_source(str(weapon_path))
            except Exception as error:
                skipped.append(f"{weapon_path.name}: {error}")
        self.file_registry.remember_folder("solomonring_animations", os.path.dirname(path))
        self.import_button.setText("Replace character…")
        self.status.setText(f"{name} — imported read-only with {len(self._sources) - 1} weapon file(s)."
                            + ("\nCould not load: " + "; ".join(skipped) if skipped else ""))
        self._refresh_sources()
        self.file_bindings_changed.emit()

    def _read_source(self, path):
        # Reject a non-model before the shared parser allocates its section table.
        with open(path, 'rb') as file:
            header = file.read(4)
            count = int.from_bytes(header, 'little')
            if len(header) != 4 or count + 1 not in MonsterAnalyser.NB_SECTION_BY_ENTITY.values():
                raise ValueError("not a supported battle model header")
            table = file.read(count * 4)
        positions = [int.from_bytes(table[i:i + 4], 'little') for i in range(0, len(table), 4)]
        if len(table) != count * 4 or positions != sorted(positions) \
                or positions[0] < 4 + count * 4 or positions[-1] > os.path.getsize(path):
            raise ValueError("invalid battle model section offsets")
        from Ifrit.ifritmanager import IfritManager

        manager = IfritManager(game_data=self.game_data)
        enemy = manager.parse_file(path, free_animation=True)
        sections = MonsterAnalyser.SECTION_INDEX_BY_ENTITY.get(enemy.entity_type, {})
        camera, camera_error = None, ""
        if sections.get("camera"):
            try:
                camera = parse_camera_collection(bytearray(enemy.section_raw_data[sections['camera']]))
            except CameraParseError as error:
                camera_error = str(error)
        manager.set_active_enemy(enemy, path, textures=([], True))
        return {"manager": manager, "path": path, "sections": sections,
                "camera": camera, "camera_error": camera_error, "textures_ready": False}

    def _clear_character(self, _path=None):
        self._discard_preview()
        self._character = None
        for source in self._sources.values():
            source['manager'].free_matrices()
        self._sources.clear()
        self.import_button.setText("Import character…")
        self.status.clear()
        self._refresh_sources()
        self.file_bindings_changed.emit()

    def _refresh_sources(self):
        selected = self.seq_source.currentData()
        self.seq_source.blockSignals(True)
        self.seq_source.clear()
        for name, source in self._sources.items():
            if source["sections"].get("anim_seq"):
                self.seq_source.addItem(name, name)
                self.seq_source.setItemData(self.seq_source.count() - 1, source["path"], Qt.ItemDataRole.ToolTipRole)
        if not self.seq_source.count():
            self.seq_source.addItem("No Seq anim file available", None)
        index = self.seq_source.findData(selected)
        self.seq_source.setCurrentIndex(max(0, index))
        self.seq_source.setEnabled(self.seq_source.currentData() is not None)
        self.seq_source.blockSignals(False)
        self._refresh_seq()
        self._refresh_camera()

    def _refresh_seq(self, _index=None):
        self._stop_preview()  # a different weapon must also replace the preview mesh
        source = self._sources.get(self.seq_source.currentData())
        if self._seq_id is None:
            self.seq_code.clear()
        elif source is None:
            self.seq_code.setPlainText("Import a character with its linked weapon files in the same folder "
                                       f"to show Seq anim {self._seq_id}.")
        else:
            enemy = source["manager"].enemy
            sequence = next((seq for seq in enemy.seq_animation_data['seq_animation_data']
                             if seq['id'] == self._seq_id), None)
            if sequence is None or not sequence['data']:
                self.seq_code.setPlainText(f"Seq anim {self._seq_id} is missing or empty in {self.seq_source.currentText()}.")
            else:
                self.seq_code.setPlainText(sequence_to_code(self.game_data, bytes(sequence['data'])))

    def _selected_camera(self):
        source = self._character
        cam_id = self.cam_choice.currentData()
        collection = source["camera"] if source else None
        if cam_id is None or collection is None or not collection.sets:
            return None
        animation = collection.sets[0].animations[cam_id]
        return animation if not animation.empty else None

    def _refresh_camera(self, _index=None):
        self._stop_preview()
        animation = self._selected_camera()
        self.preview_button.setEnabled(animation is not None)
        self.cam_choice.setEnabled(bool(self._cam_ids))
        source = self._character
        if not self._cam_ids:
            text = "This command does not start an initial cam anim."
        elif source is None:
            text = "Import a character to preview its initial cam anim entries."
        elif source['camera_error']:
            text = f"Cannot read cam anim: {source['camera_error']}"
        elif animation is None:
            text = "The selected cam anim entry is missing or empty in this file."
        else:
            text = "Preview from the imported file. The command's effect may start another cam anim."
        self.cam_status.setText(text)

    def _preview_camera(self):
        animation = self._selected_camera()
        if animation is None:
            return
        source = self._character
        manager = source['manager']
        if self._preview is None:
            from Ifrit.IfritCameraSeq.camerapreview import CameraPreviewPanel

            self._ensure_textures(source)
            self._preview = CameraPreviewPanel(manager, show_model_animation=False,
                                               file_registry=self.file_registry)
            # the battle setup stands only the files imported here
            self._preview._battle_setup.set_model_paths(
                lambda: [source['path'] for source in self._sources.values()])
            self._preview._animate_model.setChecked(False)
            self._camera_layout.addWidget(self._preview, 1)
            self._preview_source = source
        weapon = self._sources.get(self.seq_source.currentData())
        if weapon and weapon['manager'].enemy.entity_type in (EntityType.WEAPON, EntityType.WEAPON_NO_ANIM):
            self._ensure_textures(weapon)
            self._preview.set_weapon(weapon['manager'])
        else:
            self._preview.set_weapon(None)
        self._preview.preview(animation)
        self._set_render_active(self._preview._animation is not None)

    @staticmethod
    def _ensure_textures(source):
        if not source['textures_ready']:
            manager = source['manager']
            manager.set_active_enemy(manager.enemy, source['path'])
            source['textures_ready'] = True

    def _stop_preview(self):
        if self._preview is not None:
            self._preview.invalidate()
        self._set_render_active(False)

    def _set_render_active(self, active):
        if self._render_active != active:
            self._render_active = active
            self.render_preview_changed.emit(active)

    def _discard_preview(self):
        self._set_render_active(False)
        if self._preview is not None:
            self._preview.invalidate()
            self._camera_layout.removeWidget(self._preview)
            self._preview.deleteLater()
            self._preview = None
        if self._preview_source is not None:
            self._preview_source['manager'].free_matrices()
            self._preview_source = None

    def hideEvent(self, event):
        self._stop_preview()
        super().hideEvent(event)
