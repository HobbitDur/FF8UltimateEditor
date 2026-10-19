"""The 3D preview of Fujin's Camera effect editor: an effect's camera, played around a caster and
a target in a battle-like scene.

The effect's camera script picks which keyframe animation of its track plays from the battle
state (FF8GameData.dat.camerascript); the Script inputs set that state - opening shot, attacker
and target slots, target status, random value... - and the result line tells which animation
index the script chose and what it read to choose it. The chosen animation is then played by the
shared battle camera preview (Ifrit's CameraPreviewPanel + BattlePreviewSetup), which resolves
the caster/target reference frames of its keyframes from the imported models.

Caster and target are battle models (d?c###.dat characters, c0m###.dat monsters) imported
read-only through the header's Import read-only (shared FileRegistry memory, never a guessed
folder); this tool never writes them.
"""
import os
import random
import re
from types import SimpleNamespace

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QComboBox,
                             QSpinBox, QPushButton, QFileDialog, QMessageBox, QApplication)

from Common.collapsiblesection import CollapsibleSection
from FF8GameData.dat.camerascript import (CameraScriptInputs, OPENING_MONSTER_MAGIC, OPENING_NONE,
                                          STATUS_DEAD, STATUS_LOW_HEALTH, animation_index_parts,
                                          camera_animation_at, camera_category_value,
                                          run_camera_script)

MODEL_FOLDER_KEY = "battle model (.dat)"           # same remembered folder as Ifrit's and Xu's dialogs
MODEL_SELECTION_KEY = "Fujin camera preview models"
MODEL_PATTERNS = ("c0m*.dat", "d?c*.dat")
_MODEL_FILE = re.compile(r"^(c0m\d{3}|d[0-9a-f]c\d{3})\.dat$", re.IGNORECASE)
FIRST_MONSTER_SLOT = 3

# Script played when the script starts no animation: the preview holds the starting view
EMPTY_ANIMATION = SimpleNamespace(blocks=[])

TARGET_STATUSES = (("Normal", 0),
                   ("Kneeling: low HP, Poison, Sleep or Curse (characters only)", STATUS_LOW_HEALTH),
                   ("KO", STATUS_DEAD))


def is_monster(manager) -> bool:
    return getattr(manager.enemy.entity_type, "name", "").startswith("MONSTER")


class _NoWheelSpinBox(QSpinBox):
    """Ignores the wheel so scrolling the panel never changes an input by accident."""

    def wheelEvent(self, event):
        event.ignore()


class CameraEffectPreview(QWidget):
    """Caster/target pickers, the camera script inputs, and the shared 3D camera preview."""

    models_changed = pyqtSignal()

    def __init__(self, camera_manager, file_registry, parent=None):
        QWidget.__init__(self, parent)
        self.camera_manager = camera_manager   # CameraEffectManager: its camera VM runs the scripts
        self.file_registry = file_registry
        self._model_paths = []                 # imported caster/target candidates, in import order
        self._models = {}                      # path -> loaded IfritManager (read-only)
        self._game_data = None                 # one load_all()ed GameData for every model
        self._stage = None                     # IfritManager the panel films: holds the main model
        self.panel = None                      # CameraPreviewPanel, built with the first model
        self.track = None                      # CameraTrack of the selected effect
        self.last_run = None                   # CameraScriptRun of the last resolve
        self.previewed = None                  # animation shown in the panel
        self._updating = False

        self.caster_combo = QComboBox()
        self.caster_combo.setToolTip("The model casting the effect (a party character d?c###.dat or a "
                                     "monster c0m###.dat)")
        self.target_combo = QComboBox()
        self.target_combo.setToolTip("The model the effect is cast on. None: a marker at the "
                                     "target position.")
        self.import_button = QPushButton("Import models…")
        self.import_button.setToolTip("Battle models to use as caster and target, read-only "
                                      "(also in the header's Import read-only)")
        self.import_button.clicked.connect(self.import_models)
        self.caster_combo.currentIndexChanged.connect(lambda _index: self._cast_changed(caster=True))
        self.target_combo.currentIndexChanged.connect(lambda _index: self._cast_changed(caster=False))
        models = QFormLayout()
        models.addRow("Caster:", self.caster_combo)
        models.addRow("Target:", self.target_combo)

        self.inputs_section = CollapsibleSection(
            "Script inputs", expanded=True,
            tooltip="The battle state the effect's camera script reads to choose its animation")
        form = QFormLayout()
        self.inputs_section.content_layout().addLayout(form)
        self.opening_spin = self._spin(-1, 127, "Camera variable 0 (C3 00): the opening shot the action "
                                               "played before the effect. 0-5 = a character's opening "
                                               "shot, 8 = a monster's Magic, -1 = none (targeting on the "
                                               "model, or no opening shot).")
        self.opening_spin.setSpecialValueText("-1 (none)")
        form.addRow("Opening shot:", self.opening_spin)
        self.attacker_spin = self._spin(0, 10, "Attacker slot (C3 18): party 0-2, monsters 3-10. Also "
                                               "places the caster in the scene (Battle setup).")
        form.addRow("Attacker slot:", self.attacker_spin)
        self.target_slot_spin = self._spin(0, 10, "Target slot (C3 19): party 0-2, monsters 3-10. Also "
                                                  "places the target in the scene (Battle setup).")
        form.addRow("Target slot:", self.target_slot_spin)
        self.status_combo = QComboBox()
        for text, value in TARGET_STATUSES:
            self.status_combo.addItem(text, value)
        self.status_combo.setToolTip("Target's animation status (C3 16). A monster never reads as "
                                     "kneeling: the game clears that bit for monsters.")
        self.status_combo.currentIndexChanged.connect(lambda _index: self._inputs_changed())
        form.addRow("Target status:", self.status_combo)
        self.category_spin = self._spin(0, 255, "Target's camera category value (C3 15): set from the "
                                                "target monster's camera category (section 7 byte 246), "
                                                "0 for a character.")
        form.addRow("Target camera category:", self.category_spin)
        self.targets_spin = self._spin(1, 8, "Number of affected targets (C3 1A)")
        form.addRow("Affected targets:", self.targets_spin)
        self.action_count_spin = self._spin(0, 255, "Action count minus 1 (C3 17), e.g. the repeats of a "
                                                    "multi-hit action")
        form.addRow("Action count - 1:", self.action_count_spin)
        self.random_spin = self._spin(0, 32767, "The game's random value (C3 11; C3 1C-22 read it modulo "
                                                "2 to 8). Each value is one possible pick of the script.")
        reroll = QPushButton("🎲")
        reroll.setToolTip("Pick another random value")
        reroll.setMaximumWidth(36)
        reroll.clicked.connect(lambda: self.random_spin.setValue(random.randrange(32768)))
        random_row = QHBoxLayout()
        random_row.addWidget(self.random_spin, 1)
        random_row.addWidget(reroll)
        form.addRow("Random value:", random_row)

        self.result_label = QLabel()
        self.result_label.setWordWrap(True)
        self.result_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.play_button = QPushButton("▶ Play effect camera")
        self.play_button.setToolTip("Run the camera script with these inputs and play the animation "
                                    "it chooses")
        self.play_button.clicked.connect(self.play_effect)

        self.placeholder = QLabel()
        self.placeholder.setWordWrap(True)
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setStyleSheet("color: gray")

        top = QHBoxLayout()
        top.addLayout(models, 1)
        top.addWidget(self.import_button, 0, Qt.AlignmentFlag.AlignTop)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.addLayout(top)
        self._layout.addWidget(self.inputs_section)
        self._layout.addWidget(self.result_label)
        self._layout.addWidget(self.play_button, 0, Qt.AlignmentFlag.AlignLeft)
        self._layout.addWidget(self.placeholder, 1)
        defaults = CameraScriptInputs()
        self._updating = True
        for spin, value in ((self.opening_spin, defaults.opening), (self.attacker_spin, defaults.attacker_slot),
                            (self.target_slot_spin, defaults.target_slot),
                            (self.targets_spin, defaults.affected_targets)):
            spin.setValue(value)
        self._updating = False
        self._fill_model_combos()
        self._update_placeholder()
        self._show_run(None)

    def _spin(self, minimum, maximum, tooltip):
        spin = _NoWheelSpinBox()
        spin.setRange(minimum, maximum)
        spin.setToolTip(tooltip)
        spin.setKeyboardTracking(False)
        spin.valueChanged.connect(lambda _value: self._inputs_changed())
        return spin

    # ------------------------------------------------------------------ models
    def import_models(self):
        paths = QFileDialog.getOpenFileNames(
            self, "Caster and target battle models (read-only)",
            self.file_registry.last_folder(MODEL_FOLDER_KEY) or os.getcwd(),
            "Character and monster battle models (c0m*.dat d?c*.dat)")[0]
        if paths:
            self.add_models(paths)

    def add_models(self, paths):
        """Offer battle models as caster/target (loaded when picked). Weapons and other files are
        skipped. The first character becomes the caster, the first monster the target."""
        added = [path for path in dict.fromkeys(paths)
                 if path not in self._model_paths and _MODEL_FILE.match(os.path.basename(path))]
        if paths:
            self.file_registry.remember_folder(MODEL_FOLDER_KEY, os.path.dirname(paths[0]))
            self.file_registry.remember_files(MODEL_SELECTION_KEY, paths)
        if not added:
            return
        self._model_paths.extend(added)
        caster, target = self.caster_path(), self.target_path()
        names = [os.path.basename(path).lower() for path in self._model_paths]
        if caster is None:
            caster = next((path for path, name in zip(self._model_paths, names) if name.startswith("d")),
                          self._model_paths[0])
        if target is None:
            target = next((path for path, name in zip(self._model_paths, names)
                           if name.startswith("c0m") and path != caster), None)
        self._fill_model_combos(caster, target)
        self.models_changed.emit()
        self._cast_changed(caster=True)

    def model_paths(self):
        return list(self._model_paths)

    def caster_path(self):
        return self.caster_combo.currentData()

    def target_path(self):
        return self.target_combo.currentData()

    def _fill_model_combos(self, caster=None, target=None):
        self._updating = True
        try:
            for combo, selected, none_text in ((self.caster_combo, caster, "(import a model)"),
                                               (self.target_combo, target, "(none: a marker)")):
                combo.clear()
                if combo is self.target_combo or not self._model_paths:
                    combo.addItem(none_text, None)
                for path in self._model_paths:
                    combo.addItem(os.path.basename(path), path)
                index = combo.findData(selected) if selected is not None else 0
                combo.setCurrentIndex(max(index, 0))
        finally:
            self._updating = False

    def _shared_game_data(self):
        if self._game_data is None:
            game_data = self.camera_manager.game_data
            game_data.load_all()
            self._game_data = game_data
        return self._game_data

    def model(self, path):
        """The loaded (read-only) model of an imported path, or None; loading errors are reported."""
        if path is None:
            return None
        if path not in self._models:
            from Ifrit.IfritCameraSeq.battlepreview import BattlePreviewSetup
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                self._models[path] = BattlePreviewSetup._load_model(path, self._shared_game_data())
            except Exception as error:
                QApplication.restoreOverrideCursor()
                QMessageBox.warning(self, "Camera effect preview",
                                    f"Cannot use {os.path.basename(path)}: {error}")
                return None
            QApplication.restoreOverrideCursor()
        return self._models[path]

    def _ensure_panel(self):
        if self.panel is not None:
            return self.panel
        from Ifrit.ifritmanager import IfritManager
        from Ifrit.IfritCameraSeq.camerapreview import CameraPreviewPanel
        self._stage = IfritManager(game_data=self._shared_game_data())
        self.panel = CameraPreviewPanel(self._stage, file_registry=self.file_registry)
        setup = self.panel._battle_setup
        # The roles come from the Caster/Target pickers, and the opponent from the imported
        # models (the setup's own Load opponent opens a file outside the shared registry).
        setup.role.setEnabled(False)
        for button in setup.opponent_buttons:
            button.hide()
        setup.caster_slot.valueChanged.connect(self.attacker_spin.setValue)
        setup.target_slot.valueChanged.connect(self.target_slot_spin.setValue)
        self._layout.replaceWidget(self.placeholder, self.panel)
        self.placeholder.hide()
        self._layout.setStretchFactor(self.panel, 1)
        return self.panel

    def _cast_changed(self, caster):
        """A new caster or target: film it, and reset the inputs that follow from the models."""
        if self._updating:
            return
        caster_model = self.model(self.caster_path())
        target_model = self.model(self.target_path())
        main = caster_model or target_model
        if main is None:
            self._update_placeholder()
            return
        panel = self._ensure_panel()
        setup = panel._battle_setup
        self._stage.enemy = main.enemy
        self._stage.texture_data = list(main.texture_data)
        self._stage.texture_black_is_transparent = main.texture_black_is_transparent
        panel.invalidate()
        main_is_caster = caster_model is not None
        setup.role.setCurrentIndex(0 if main_is_caster else 1)
        setup.opponent = target_model if main_is_caster else None
        # The opponent stands in front of the main model (party faces -Z, monsters +Z)
        setup.position[2].blockSignals(True)
        setup.position[2].setValue(5000 if is_monster(main) else -5000)
        setup.position[2].blockSignals(False)
        self._set_default_inputs(caster_model, target_model, caster_changed=caster)
        self._sync_setup_slots()
        self.play_effect()

    def _set_default_inputs(self, caster_model, target_model, caster_changed):
        caster_monster = caster_model is not None and is_monster(caster_model)
        target_monster = target_model is not None and is_monster(target_model)
        self._updating = True
        try:
            if caster_changed:
                self.opening_spin.setValue(OPENING_MONSTER_MAGIC if caster_monster else 0)
            attacker = FIRST_MONSTER_SLOT if caster_monster else 0
            if target_model is None:
                target = 0 if caster_monster else FIRST_MONSTER_SLOT
            elif target_monster:
                target = FIRST_MONSTER_SLOT + 1 if caster_monster else FIRST_MONSTER_SLOT
            else:
                target = 0 if caster_monster else 1
            self.attacker_spin.setValue(attacker)
            self.target_slot_spin.setValue(target)
            category = target_model.enemy.info_stat_data.get("camera_category", 0) if target_monster else None
            self.category_spin.setValue(camera_category_value(category) if category is not None else 0)
        finally:
            self._updating = False

    def _update_placeholder(self):
        if self.panel is None:
            self.placeholder.setText("Import a caster and a target with Import models… (or the header's "
                                     "Import read-only) to play the effect's camera around them.")

    # ------------------------------------------------------------------ script
    def inputs(self) -> CameraScriptInputs:
        status = self.status_combo.currentData()
        target = self._models.get(self.target_path())
        if target is not None and is_monster(target):
            status &= ~STATUS_LOW_HEALTH       # CameraSeq_ReadSpecialVar_C3: monsters never kneel
        return CameraScriptInputs(opening=self.opening_spin.value(),
                                  attacker_slot=self.attacker_spin.value(),
                                  target_slot=self.target_slot_spin.value(),
                                  target_status=status, target_category=self.category_spin.value(),
                                  action_count=self.action_count_spin.value(),
                                  affected_targets=self.targets_spin.value(),
                                  random=self.random_spin.value())

    def resolve(self):
        """Run the selected effect's script: (CameraScriptRun, animation to play) or (None, None)."""
        if self.track is None:
            self.last_run = None
            self._show_run(None)
            return None, None
        run = run_camera_script(self.camera_manager.vm, self.track.script, self.inputs())
        self.last_run = run
        animation = camera_animation_at(self.track.collection, run.chosen) if run.chosen is not None else None
        self._show_run(run, animation)
        return run, animation

    def _input_name(self, parameter):
        for entry in self.camera_manager.vm.data_json.get("special_change_current_value_params", []):
            param_id = entry["param_id"]
            if (int(param_id, 16) if isinstance(param_id, str) else param_id) == parameter:
                return entry["text"]
        return f"0x{parameter:02X}"

    def _show_run(self, run, animation=None, slot_text=""):
        if slot_text:
            self.result_label.setText(slot_text)
            return
        if run is None:
            self.result_label.setText("<i>Select an effect with a camera track to run its camera script.</i>")
            return
        if run.chosen is None:
            text = "The script plays no camera animation with these inputs: the camera stays where it is."
        else:
            set_index, slot = animation_index_parts(run.chosen)
            text = f"The script plays animation <b>{run.chosen}</b> (set {set_index}, slot {slot})"
            text += "." if animation is not None else " - <b>not in this track</b> (no such set or an empty slot)."
            if len(run.played) > 1:
                text += f" It started {', '.join(map(str, run.played))}; the last one stays."
        reads = [f"{self._input_name(parameter)} = {value}" for parameter, value in run.reads
                 if parameter == 0 or 0x10 <= parameter <= 0x23]
        if reads:
            text += "<br><small>Read: " + "; ".join(reads) + "</small>"
        if run.events:
            text += "<br><small>Also: " + "; ".join(run.events) + "</small>"
        if not run.stop_reason.startswith(("end:", "end_clear:")):
            text += f"<br><small>Stops: {run.stop_reason}</small>"
        self.result_label.setText(text)

    def _inputs_changed(self):
        if self._updating:
            return
        self._sync_setup_slots()
        self.play_effect()

    def _sync_setup_slots(self):
        """The attacker/target slots also place the caster/target in the scene (Battle setup)."""
        if self.panel is None:
            return
        setup = self.panel._battle_setup
        for spin, value in ((setup.caster_slot, self.attacker_spin.value()),
                            (setup.target_slot, self.target_slot_spin.value())):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)

    # ------------------------------------------------------------------ playing
    def set_track(self, track):
        """The selected effect's camera track (None: no track): run its script and play it."""
        self.track = track
        self.play_effect()

    def play_effect(self):
        """Run the script with the inputs and play the animation it chooses."""
        run, animation = self.resolve()
        self.play_button.setEnabled(self.track is not None)
        if self.panel is None:
            return
        if self.track is None:
            self.previewed = None
            self.panel.invalidate()
            return
        self._play(animation if animation is not None else EMPTY_ANIMATION)

    def preview_animation(self, animation):
        """A slot's ▶ Preview: play that animation as is, whatever the script would choose."""
        if self.panel is None:
            QMessageBox.information(self, "Camera effect preview",
                                    "Import a caster and a target first (Import models…).")
            return
        set_index = slot = None
        for index, camera_set in enumerate(self.track.collection.sets if self.track else []):
            if animation in camera_set.animations:
                set_index, slot = index, camera_set.animations.index(animation)
        where = f"set {set_index}, slot {slot} = animation {set_index * 16 + slot}" if set_index is not None else ""
        self._show_run(None, slot_text=f"Slot preview: {where} as is (not the script's choice). "
                                       "▶ Play effect camera runs the script again.")
        self._play(animation)

    def _play(self, animation):
        self.previewed = animation
        self.panel.preview(animation)

    def refresh(self):
        """The track's keyframes were edited in place: replay the shown animation with them."""
        if self.panel is not None and self.previewed is not None:
            self.panel.refresh()
