import os
from contextlib import contextmanager

from PyQt6.QtCore import Qt, QSignalBlocker, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap, QFontDatabase
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QListWidget,
                             QComboBox, QSpinBox, QCheckBox, QPushButton, QGroupBox, QLineEdit,
                             QFileDialog, QMessageBox, QDialog)

from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from FF8GameData.sceneout import (NB_SLOT, UNKNOWN_SIZE, BATTLE_FLAG_NAMES, CAMERA_SET_MAX,
                                  CAMERA_ANIM_MAX, SlotData)
from JumboCactuar.jumbocactuarmanager import JumboCactuarManager, FILE_NAME
from SmallWidget.listsearchbar import ListSearchBar

STAGE_PICTURE_FOLDER = ("JumboCactuar", "stages")  # under Resources: NNN.jpg per battle stage
THUMBNAIL_WIDTH = 192
SLOT_FLAGS = [("enabled", "Enabled"), ("not_targetable", "Not targetable"),
              ("not_visible", "Not visible"), ("not_loaded", "Not loaded")]
UNKNOWN_ROWS = [(0, 16), (16, 16), (32, 16), (48, 8)]  # (start, size) of the 4 unknown fields
CAMERA_NAMES = ["Main", "Secondary"]
WIKI_ENCOUNTERS = "https://hobbitdur.github.io/FF8ModdingWiki/technical-reference/battle/encounter-codes/"
WIKI_SCENE_OUT = "https://hobbitdur.github.io/FF8ModdingWiki/technical-reference/battle/battle-structure-sceneout/"


def _copy_paste_buttons(what, copy, paste):
    """The small C / P pair of a section: copy it from this encounter, paste it into the shown one."""
    copy_button = QPushButton("C")
    copy_button.setToolTip(f"Copy {what}")
    paste_button = QPushButton("P")
    paste_button.setToolTip(f"Paste {what}")
    paste_button.setEnabled(False)  # until something was copied
    for button, slot in ((copy_button, copy), (paste_button, paste)):
        button.setFixedSize(24, 22)
        button.clicked.connect(slot)
    return copy_button, paste_button


def _hex_text(data):
    return " ".join(f"{byte:02X}" for byte in data)


class _StagePicture(QLabel):
    """Thumbnail of the battle stage; a click shows it bigger."""

    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class _SlotPanel(QGroupBox):
    """One of the 8 enemy slots of the shown encounter."""

    def __init__(self, slot_index, manager):
        QGroupBox.__init__(self, f"Enemy slot {slot_index}")
        self.slot_index = slot_index
        self.enemy_combo = QComboBox()
        for enemy_byte in range(256):  # index = the raw id byte (c0m number + 0x10)
            self.enemy_combo.addItem(manager.enemy_label(enemy_byte), enemy_byte)
        self.enemy_combo.setMaximumWidth(230)
        self.level_spin = QSpinBox()
        self.level_spin.setRange(0, 255)
        self.flag_boxes = {name: QCheckBox(label) for name, label in SLOT_FLAGS}
        self.position_spins = []
        for _axis in range(3):
            spin = QSpinBox()
            spin.setRange(-32768, 32767)
            self.position_spins.append(spin)
        self.select_box = QCheckBox("Select")
        self.select_box.setToolTip("Select the slot for 'Copy selected slots' / 'Paste into selected slots'")
        self.select_box.setProperty("read_only_preview", True)  # choosing slots is not an edit
        self.copy_button = None
        self.paste_button = None

        grid = QGridLayout()
        grid.addWidget(QLabel("Enemy:"), 0, 0)
        grid.addWidget(self.enemy_combo, 0, 1, 1, 3)
        grid.addWidget(QLabel("Level:"), 1, 0)
        grid.addWidget(self.level_spin, 1, 1)
        for row, (name, _label) in enumerate(SLOT_FLAGS):
            grid.addWidget(self.flag_boxes[name], 2 + row, 0, 1, 2)
        grid.addWidget(QLabel("Position"), 2, 2, 1, 2)
        for axis, spin in enumerate(self.position_spins):
            grid.addWidget(QLabel("xyz"[axis] + ":"), 3 + axis, 2)
            grid.addWidget(spin, 3 + axis, 3)
        self.button_row = QHBoxLayout()
        self.button_row.addWidget(self.select_box)
        self.button_row.addStretch(1)
        grid.addLayout(self.button_row, 6, 0, 1, 4)
        self.setLayout(grid)

    def editors(self):
        return [self.enemy_combo, self.level_spin, *self.flag_boxes.values(), *self.position_spins]

    def show_slot(self, slot: SlotData):
        self.enemy_combo.setCurrentIndex(slot.enemy_byte)
        self.level_spin.setValue(slot.level)
        for name, box in self.flag_boxes.items():
            box.setChecked(getattr(slot, name))
        for spin, value in zip(self.position_spins, slot.position):
            spin.setValue(value)


class JumboCactuarWidget(QWidget):
    """scene.out editor: the 1024 encounters - battle stage, battle flags, intro cameras and the
    8 enemy slots (monster, level, position, flags) of each.

    Python port of Jumbo Cactuar by Nihil (github.com/Nihil-1/JumboCactuar), same name, same
    sections and the same C / P copy-paste buttons. Battle stage pictures by Maki."""

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData", file_registry=None):
        QWidget.__init__(self)
        if file_registry is None:  # The tool is used alone, it shares its files with nobody
            file_registry = FileRegistry()
        self.file_registry = file_registry
        self.setWindowTitle("Jumbo Cactuar")
        self.setWindowIcon(QIcon(os.path.join(icon_path, "jumbo_cactuar.ico")))
        self.setAcceptDrops(True)  # drop a .out file to open it

        self.manager = JumboCactuarManager()
        self._picture_folder = os.path.join(icon_path, *STAGE_PICTURE_FOLDER)
        self._current = -1     # encounter shown
        self._filling = False  # widgets being set from the encounter: not an edit
        self._clipboard = {}   # kind -> copied value (encounter, stage, flags, camera, unknown, slot, slots)
        self._paste_buttons = {}

        # scene.out, shared with Xu and Ifrit (read-only there). Any .out can be opened, as in
        # the original tool (a renamed copy, a mod's file).
        self.binding = FileBinding(FILE_NAME, file_registry, load_callback=self.load_file,
                                   save_callback=self.save_file, file_filter="FF8 encounter list (*.out)")
        self.binding.file_closed.connect(self._close_file)

        # Encounter list (left), Ctrl+F filters it by stage/enemy name or encounter id
        self.encounter_list = QListWidget()
        self.encounter_list.setFixedWidth(330)
        self.encounter_list.currentRowChanged.connect(self._on_encounter_selected)
        self.encounter_search = ListSearchBar.wrap(self.encounter_list, match_index=True)

        # Encounter actions
        self.copy_encounter_button = QPushButton("Copy encounter")
        self.copy_encounter_button.clicked.connect(self._copy_encounter)
        self.paste_encounter_button = QPushButton("Paste encounter")
        self.paste_encounter_button.setEnabled(False)
        self.paste_encounter_button.clicked.connect(self._paste_encounter)
        self._paste_buttons["encounter"] = [self.paste_encounter_button]
        self.revert_button = QPushButton("Revert this encounter")
        self.revert_button.setToolTip("Back to the encounter as it was last opened or saved")
        self.revert_button.clicked.connect(self._revert_encounter)
        self.copy_slots_button = QPushButton("Copy selected slots")
        self.copy_slots_button.clicked.connect(self._copy_selected_slots)
        self.paste_slots_button = QPushButton("Paste into selected slots")
        self.paste_slots_button.setEnabled(False)
        self.paste_slots_button.clicked.connect(self._paste_selected_slots)
        self._paste_buttons["slots"] = [self.paste_slots_button]
        self.save_as_button = QPushButton("Save as...")
        self.save_as_button.clicked.connect(self._save_as)
        self.about_button = QPushButton("About")
        self.about_button.clicked.connect(self._about)
        action_bar = QHBoxLayout()
        for widget in (self.copy_encounter_button, self.paste_encounter_button, self.revert_button):
            action_bar.addWidget(widget)
        action_bar.addSpacing(20)
        action_bar.addWidget(self.copy_slots_button)
        action_bar.addWidget(self.paste_slots_button)
        action_bar.addStretch(1)
        action_bar.addWidget(self.save_as_button)
        action_bar.addWidget(self.about_button)

        self._build_stage_group()
        self._build_flags_group()
        self._build_camera_group()
        self._build_unknown_group()
        self.slot_panels = []
        slot_grid = QGridLayout()
        for slot_index in range(NB_SLOT):
            panel = _SlotPanel(slot_index, self.manager)
            copy_button, paste_button = _copy_paste_buttons(
                "this enemy slot", lambda _c=False, s=slot_index: self._copy_slot(s),
                lambda _c=False, s=slot_index: self._paste_slot(s))
            self._paste_buttons.setdefault("slot", []).append(paste_button)
            panel.button_row.addWidget(copy_button)
            panel.button_row.addWidget(paste_button)
            self._connect_slot(panel)
            self.slot_panels.append(panel)
            slot_grid.addWidget(panel, slot_index // 4, slot_index % 4)

        left_column = QVBoxLayout()
        left_column.addWidget(self.stage_group)
        left_column.addWidget(self.flags_group)
        left_column.addWidget(self.camera_group)
        left_column.addStretch(1)
        slot_column = QVBoxLayout()
        slot_column.addLayout(slot_grid)
        slot_column.addWidget(self.unknown_group, alignment=Qt.AlignmentFlag.AlignLeft)
        slot_column.addStretch(1)
        body = QHBoxLayout()
        body.addLayout(left_column)
        body.addLayout(slot_column, 1)

        self.editor = QWidget()
        editor_layout = QVBoxLayout()
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.addLayout(action_bar)
        editor_layout.addLayout(body, 1)
        self.editor.setLayout(editor_layout)
        self.editor.setEnabled(False)

        main_layout = QHBoxLayout()
        main_layout.addWidget(self.encounter_search.column)
        main_layout.addWidget(self.editor, 1)
        self.setLayout(main_layout)

        self.binding.load_opened_file()  # Another tool may have opened scene.out already

    # --- Building ---

    def _build_stage_group(self):
        self.stage_combo = QComboBox()
        for stage_id in range(256):  # index = the raw stage byte
            label = self.manager.stage_label(stage_id) if stage_id < len(self.manager.stage_names) \
                else f"{stage_id:3d} - (no a0stg file)"
            self.stage_combo.addItem(label, stage_id)
        self.stage_combo.setMaximumWidth(280)
        self.stage_combo.currentIndexChanged.connect(
            lambda stage_id: self._edit("stage", lambda record: setattr(record, "stage_id", stage_id)))
        self.stage_picture = _StagePicture()
        self.stage_picture.setFixedSize(THUMBNAIL_WIDTH, THUMBNAIL_WIDTH * 9 // 16)
        self.stage_picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stage_picture.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stage_picture.setToolTip("Click to see it bigger")
        self.stage_picture.clicked.connect(self._show_stage_picture)
        copy_button, paste_button = _copy_paste_buttons("the battle stage", self._copy_stage, self._paste_stage)
        self._paste_buttons["stage"] = [paste_button]
        picture_row = QHBoxLayout()
        picture_row.addWidget(self.stage_picture)
        buttons = QVBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(copy_button)
        buttons.addWidget(paste_button)
        picture_row.addLayout(buttons)
        layout = QVBoxLayout()
        layout.addWidget(self.stage_combo)
        layout.addLayout(picture_row)
        self.stage_group = QGroupBox("Battle stage")
        self.stage_group.setLayout(layout)

    def _build_flags_group(self):
        self.flag_boxes = []
        grid = QGridLayout()
        for bit, name in enumerate(BATTLE_FLAG_NAMES):
            box = QCheckBox(name)
            box.setToolTip(f"Battle flags bit {bit} (0x{1 << bit:02X})")
            box.toggled.connect(lambda checked, b=bit: self._edit(f"flag{b}", lambda record: record.set_flag(b, checked)))
            self.flag_boxes.append(box)
            grid.addWidget(box, bit, 0)
        copy_button, paste_button = _copy_paste_buttons("the battle flags", self._copy_flags, self._paste_flags)
        self._paste_buttons["flags"] = [paste_button]
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(copy_button)
        buttons.addWidget(paste_button)
        grid.addLayout(buttons, len(BATTLE_FLAG_NAMES), 0)
        grid.setVerticalSpacing(2)
        self.flags_group = QGroupBox("Battle flags")
        self.flags_group.setLayout(grid)

    def _build_camera_group(self):
        self.camera_spins = []  # per camera: (set spin, animation spin)
        grid = QGridLayout()
        grid.addWidget(QLabel("Set"), 0, 1)
        grid.addWidget(QLabel("Anim"), 0, 2)
        for index, name in enumerate(CAMERA_NAMES):
            set_spin, anim_spin = QSpinBox(), QSpinBox()
            set_spin.setRange(0, CAMERA_SET_MAX)
            anim_spin.setRange(0, CAMERA_ANIM_MAX)
            set_spin.setToolTip("Camera animation set of the stage .x (high nibble of the byte)")
            anim_spin.setToolTip("Animation in that set (bits 0-2 of the byte)")
            for spin in (set_spin, anim_spin):
                spin.valueChanged.connect(lambda _value, i=index: self._edit_camera(i))
            self.camera_spins.append((set_spin, anim_spin))
            copy_button, paste_button = _copy_paste_buttons(
                f"the {name.lower()} intro camera", lambda _c=False, i=index: self._copy_camera(i),
                lambda _c=False, i=index: self._paste_camera(i))
            self._paste_buttons.setdefault("camera", []).append(paste_button)
            grid.addWidget(QLabel(name + ":"), index + 1, 0)
            grid.addWidget(set_spin, index + 1, 1)
            grid.addWidget(anim_spin, index + 1, 2)
            grid.addWidget(copy_button, index + 1, 3)
            grid.addWidget(paste_button, index + 1, 4)
        self.camera_group = QGroupBox("Intro camera")
        self.camera_group.setToolTip("The battle starts with one of the two, 50/50 (encounter 33 always uses the main one)")
        self.camera_group.setLayout(grid)

    def _build_unknown_group(self):
        self.unknown_edits = []
        grid = QGridLayout()
        for row, (start, size) in enumerate(UNKNOWN_ROWS):
            edit = QLineEdit()
            edit.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
            edit.setMinimumWidth(edit.fontMetrics().horizontalAdvance("00 " * 16) + 12)
            edit.setToolTip(f"{size} bytes at 0x{0x40 + start:02X}, in hexadecimal\n"
                            f"Applied when the field is left with all {size} bytes typed")
            edit.editingFinished.connect(self._edit_unknown)
            self.unknown_edits.append(edit)
            grid.addWidget(QLabel(f"Unknown {row}:"), row, 0)
            grid.addWidget(edit, row, 1)
        copy_button, paste_button = _copy_paste_buttons("the unknown bytes", self._copy_unknown, self._paste_unknown)
        self._paste_buttons["unknown"] = [paste_button]
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(copy_button)
        buttons.addWidget(paste_button)
        grid.addLayout(buttons, len(UNKNOWN_ROWS), 0, 1, 2)
        grid.setVerticalSpacing(2)
        self.unknown_group = QGroupBox("Unknowns - edit with caution")
        self.unknown_group.setToolTip("Never read by FF8_EN.exe (PC): free for mods")
        self.unknown_group.setLayout(grid)

    def _connect_slot(self, panel):
        index = panel.slot_index
        panel.enemy_combo.currentIndexChanged.connect(
            lambda value: self._edit(f"enemy{index}", lambda record: record.set_enemy_byte(index, value)))
        panel.level_spin.valueChanged.connect(
            lambda value: self._edit(f"level{index}", lambda record: record.set_level(index, value)))
        for name, box in panel.flag_boxes.items():
            box.toggled.connect(lambda checked, n=name: self._edit(
                f"{n}{index}", lambda record: record.set_slot_flag(n, index, checked)))
        for axis, spin in enumerate(panel.position_spins):
            spin.valueChanged.connect(lambda _value, a=axis: self._edit(
                f"position{index}{a}", lambda record: record.set_position(
                    index, [s.value() for s in panel.position_spins])))

    # --- Shared toolbar ---

    def file_bindings(self):
        """The file the shared header toolbar drives for this tool: scene.out."""
        return [self.binding]

    def load_file(self, path):
        self.manager.load_file(path)
        self._fill_list()
        self.editor.setEnabled(True)
        if 0 <= self._current < self.encounter_list.count():
            self.encounter_list.setCurrentRow(self._current)  # a reload stays on the same encounter
        else:
            self.encounter_search.select_first_match()
        self._show_encounter()

    def _close_file(self, _path):
        """scene.out was removed from the opened files: its edits can't be saved any more."""
        self.manager = JumboCactuarManager()
        self._current = -1
        with QSignalBlocker(self.encounter_list):
            self.encounter_list.clear()
        self.editor.setEnabled(False)

    def save_file(self):
        if not self.manager.loaded:
            return
        self.manager.save_file(self.binding.current_path or self.manager.file_path)
        self._refresh_list_labels()

    def has_unsaved_changes(self):
        return self.manager.loaded and bool(self.manager.modified_indices())

    def undo(self):
        self._show_undone(self.manager.undo())

    def redo(self):
        self._show_undone(self.manager.redo())

    def _show_undone(self, index):
        if index is None:
            return
        self._changed(index)
        if index != self._current:
            self.encounter_list.setCurrentRow(index)
        else:
            self._show_encounter()

    # --- Encounter list ---

    def _fill_list(self):
        with QSignalBlocker(self.encounter_list):
            self.encounter_list.clear()
            for index in range(len(self.manager.records)):
                self.encounter_list.addItem(self._list_label(index))
        self.encounter_search.search()

    def _list_label(self, index):
        return ("* " if self.manager.is_modified(index) else "") + self.manager.summary(index)

    def _refresh_list_labels(self):
        for index in range(self.encounter_list.count()):
            self.encounter_list.item(index).setText(self._list_label(index))

    def _on_encounter_selected(self, row):
        if row < 0:
            return
        self.manager.end_edit_group()  # a new encounter starts a new undo step
        self._current = row
        self._show_encounter()

    # --- Showing the encounter ---

    @contextmanager
    def _filling_widgets(self):
        widgets = [self.stage_combo, *self.flag_boxes, *(spin for pair in self.camera_spins for spin in pair),
                   *self.unknown_edits, *(editor for panel in self.slot_panels for editor in panel.editors())]
        blockers = [QSignalBlocker(widget) for widget in widgets]
        self._filling = True
        try:
            yield
        finally:
            self._filling = False
            for blocker in blockers:
                blocker.unblock()

    def _show_encounter(self):
        if not self.manager.loaded or not 0 <= self._current < len(self.manager.records):
            return
        record = self.manager.records[self._current]
        with self._filling_widgets():
            self.stage_combo.setCurrentIndex(record.stage_id)
            for bit, box in enumerate(self.flag_boxes):
                box.setChecked(record.flag(bit))
            for index, (set_spin, anim_spin) in enumerate(self.camera_spins):
                camera_set, camera_anim = record.camera(index)
                set_spin.setValue(camera_set)
                anim_spin.setValue(camera_anim)
            unknown = record.unknown
            for edit, (start, size) in zip(self.unknown_edits, UNKNOWN_ROWS):
                edit.setText(_hex_text(unknown[start:start + size]))
            for panel in self.slot_panels:
                panel.show_slot(record.slot(panel.slot_index))
        self._show_stage_thumbnail(record.stage_id)

    def _stage_picture_path(self, stage_id):
        return os.path.join(self._picture_folder, f"{stage_id:03d}.jpg")

    def _show_stage_thumbnail(self, stage_id):
        pixmap = QPixmap(self._stage_picture_path(stage_id))
        if pixmap.isNull():
            self.stage_picture.setPixmap(QPixmap())
            self.stage_picture.setText("No picture")
            return
        self.stage_picture.setPixmap(pixmap.scaled(self.stage_picture.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                                   Qt.TransformationMode.SmoothTransformation))

    def _show_stage_picture(self):
        stage_id = self.stage_combo.currentIndex()
        pixmap = QPixmap(self._stage_picture_path(stage_id))
        if pixmap.isNull():
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(self.stage_combo.currentText().strip())
        label = QLabel()
        label.setPixmap(pixmap)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label)
        dialog.setLayout(layout)
        dialog.exec()

    # --- Editing ---

    def _edit(self, key, change):
        """Apply a change to the shown encounter (key groups successive edits of one field into
        one undo step)."""
        if self._filling or not self.manager.loaded or self._current < 0:
            return
        self.manager.before_edit(self._current, key)
        change(self.manager.records[self._current])
        self._changed(self._current)
        if key == "stage":
            self._show_stage_thumbnail(self.manager.records[self._current].stage_id)

    def _replace(self, change):
        """A whole-section change (paste, revert): one undo step, then the encounter is shown again."""
        if not self.manager.loaded or self._current < 0:
            return
        self.manager.before_edit(self._current)
        change(self.manager.records[self._current])
        self._changed(self._current)
        self._show_encounter()

    def _changed(self, index):
        item = self.encounter_list.item(index)
        if item is not None:
            item.setText(self._list_label(index))
        state = getattr(self, "dirty_state", None)
        if state is not None:
            state.mark()

    def _edit_camera(self, index):
        set_spin, anim_spin = self.camera_spins[index]
        self._edit(f"camera{index}", lambda record: record.set_camera(index, set_spin.value(), anim_spin.value()))

    def _unknown_from_edits(self):
        """The 56 unknown bytes typed in the 4 fields, or None while one is incomplete."""
        data = bytearray()
        for edit, (_start, size) in zip(self.unknown_edits, UNKNOWN_ROWS):
            try:
                part = bytes.fromhex(edit.text())
            except ValueError:
                return None
            if len(part) != size:
                return None
            data += part
        return bytes(data)

    def _edit_unknown(self):
        if self._filling or not self.manager.loaded or self._current < 0:
            return
        data = self._unknown_from_edits()
        if data is None:  # incomplete: back to what the encounter holds
            self._show_encounter()
            return
        if data != self.manager.records[self._current].unknown:
            self._edit("unknown", lambda record: setattr(record, "unknown", data))
        self._show_encounter()  # normalized spacing and case

    # --- Copy / paste ---

    def _set_clipboard(self, kind, value):
        self._clipboard[kind] = value
        for button in self._paste_buttons.get(kind, []):
            button.setEnabled(True)

    def _record(self):
        return self.manager.records[self._current]

    def _copy_encounter(self):
        self._set_clipboard("encounter", self._record().to_bytes())

    def _paste_encounter(self):
        data = self._clipboard.get("encounter")
        if data is None:
            return

        def paste(record):
            record.data[:] = data
        self._replace(paste)

    def _revert_encounter(self):
        if self.manager.loaded and self._current >= 0:
            self.manager.revert(self._current)
            self._changed(self._current)
            self._show_encounter()

    def _copy_stage(self):
        self._set_clipboard("stage", self._record().stage_id)

    def _paste_stage(self):
        if "stage" in self._clipboard:
            self._replace(lambda record: setattr(record, "stage_id", self._clipboard["stage"]))

    def _copy_flags(self):
        self._set_clipboard("flags", self._record().flags)

    def _paste_flags(self):
        if "flags" in self._clipboard:
            self._replace(lambda record: setattr(record, "flags", self._clipboard["flags"]))

    def _copy_camera(self, index):
        self._set_clipboard("camera", self._record().camera_byte(index))

    def _paste_camera(self, index):
        if "camera" in self._clipboard:
            self._replace(lambda record: record.set_camera_byte(index, self._clipboard["camera"]))

    def _copy_unknown(self):
        self._set_clipboard("unknown", self._record().unknown)

    def _paste_unknown(self):
        if "unknown" in self._clipboard:
            self._replace(lambda record: setattr(record, "unknown", self._clipboard["unknown"]))

    def _copy_slot(self, slot_index):
        self._set_clipboard("slot", self._record().slot(slot_index))

    def _paste_slot(self, slot_index):
        if "slot" in self._clipboard:
            self._replace(lambda record: record.set_slot(slot_index, self._clipboard["slot"]))

    def _selected_slots(self):
        return [panel.slot_index for panel in self.slot_panels if panel.select_box.isChecked()]

    def _clear_slot_selection(self):
        for panel in self.slot_panels:
            panel.select_box.setChecked(False)

    def _copy_selected_slots(self):
        selected = self._selected_slots()
        if not selected:
            QMessageBox.information(self, "No slot selected", "Tick 'Select' on the slots to copy first.")
            return
        self._set_clipboard("slots", [self._record().slot(slot_index) for slot_index in selected])
        self._clear_slot_selection()

    def _paste_selected_slots(self):
        copied = self._clipboard.get("slots")
        if not copied:
            return
        selected = self._selected_slots()
        if len(selected) != len(copied):
            QMessageBox.warning(self, "Wrong amount of slots selected",
                                f"{len(copied)} slots were copied, please select {len(copied)} slots before pasting.")
            return

        def paste(record):
            for slot_index, slot in zip(selected, copied):
                record.set_slot(slot_index, slot)
        self._replace(paste)
        self._clear_slot_selection()

    # --- Files ---

    def _save_as(self):
        if not self.manager.loaded:
            return
        path = QFileDialog.getSaveFileName(self, "Save scene.out as", self.binding.current_path or "",
                                           "FF8 encounter list (*.out)")[0]
        if not path:
            return
        if not path.lower().endswith(".out"):
            path += ".out"
        self.manager.save_file(path)
        if state := getattr(self, "dirty_state", None):
            state.clear()
        self.binding.open_path(path)  # the saved file is the one open now, here and in the other tools

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if not paths:
            return
        if not paths[0].lower().endswith(".out"):
            QMessageBox.warning(self, "Invalid file", "Only .out files are supported.")
            return
        self.binding.open_path(paths[0])
        event.acceptProposedAction()

    def _about(self):
        QMessageBox.about(
            self, "About Jumbo Cactuar",
            "<h3>Jumbo Cactuar - scene.out editor</h3>"
            "Python port of <a href='https://github.com/Nihil-1/JumboCactuar'>Jumbo Cactuar</a>, made by Nihil.<br><br>"
            "Click the C buttons to copy parts of an encounter, then the P buttons to paste them into "
            "another encounter (or, for enemy slots, into another slot of the same one).<br><br>"
            f"<a href='{WIKI_ENCOUNTERS}'>Encounters list</a><br>"
            f"<a href='{WIKI_SCENE_OUT}'>scene.out format</a><br><br>"
            "Special thanks to <a href='https://github.com/MaKiPL/'>Maki</a> for the battle stage pictures!")
