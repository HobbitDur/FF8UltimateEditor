"""The 3D preview of Fujin's Camera effect editor: an effect's camera, played around a caster and
a target in a battle scene.

The scene is the shared battle camera preview (Ifrit's CameraPreviewPanel + BattlePreviewSetup):
with scene.out open and an encounter picked, the enemies stand at their scene.out slot positions
and the party in the game's battle formation; without one, the setup's manual placement puts the
caster and the target face to face. Fujin only feeds that setup: the imported models, the party
(a character and its weapon per slot), and which battle slots cast and receive the effect.

The effect's camera script picks which keyframe animation of its track plays from the battle
state (FF8GameData.dat.camerascript). The attacker/target slots come from the setup; the Script
inputs set the rest - opening shot, target status, random value... - and the result line tells
which animation index the script chose and what it read to choose it.

Every file the preview uses (the models, scene.out) is imported read-only from the header
toolbar's Import complementary (shared FileRegistry memory, never a guessed folder); the preview
has no file buttons of its own and never writes them.
"""
import os
import random
import re
from types import SimpleNamespace

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
                             QComboBox, QSpinBox, QPushButton, QFileDialog, QMessageBox, QApplication,
                             QSizePolicy)

from Common.collapsiblesection import CollapsibleSection
from Common.filebinding import FileBinding
from FF8GameData.dat.camerascript import (CameraScriptInputs, OPENING_MONSTER_MAGIC, STATUS_DEAD,
                                          STATUS_LOW_HEALTH, animation_index_parts, camera_animation_at,
                                          camera_category_value, run_camera_script)

SETTINGS_STATE_KEY = "fujin/camera preview settings expanded"   # QSettings key of its folded state
INPUTS_STATE_KEY = "fujin/camera preview script inputs expanded"
MODEL_FOLDER_KEY = "battle model (.dat)"           # same remembered folder as Ifrit's and Xu's dialogs
MODEL_SELECTION_KEY = "Fujin camera preview models"
MODEL_PATTERNS = ("c0m*.dat", "d?c*.dat", "d?w*.dat")
_MONSTER_FILE = re.compile(r"^c0m(\d{3})\.dat$", re.IGNORECASE)
_CHARACTER_FILE = re.compile(r"^d([0-9a-f])c\d{3}\.dat$", re.IGNORECASE)
_WEAPON_FILE = re.compile(r"^d([0-9a-f])w\d{3}\.dat$", re.IGNORECASE)
PARTY_SIZE = 3
FIRST_ENEMY_SLOT = 3

# Script played when the script starts no animation: the preview holds the starting view
EMPTY_ANIMATION = SimpleNamespace(blocks=[])

TARGET_STATUSES = (("Normal", 0),
                   ("Kneeling: low HP, Poison, Sleep or Curse (characters only)", STATUS_LOW_HEALTH),
                   ("KO", STATUS_DEAD))


def is_monster(manager) -> bool:
    return getattr(manager.enemy.entity_type, "name", "").startswith("MONSTER")


def _name(path):
    return os.path.basename(path)


class _NoWheelSpinBox(QSpinBox):
    """Ignores the wheel so scrolling the panel never changes an input by accident."""

    def wheelEvent(self, event):
        event.ignore()


class CameraEffectPreview(QWidget):
    """The party, the caster/target pickers, the camera script inputs and the shared 3D preview.

    Caster and target are actor keys: ("party", party slot), ("enemy", scene.out slot index) in
    an encounter, ("monster", path) for an imported monster in manual placement, None (no target).
    """

    models_changed = pyqtSignal()
    animation_chosen = pyqtSignal(object)   # the animation index the script chose (None: none)

    def __init__(self, camera_manager, file_registry, parent=None):
        QWidget.__init__(self, parent)
        self.camera_manager = camera_manager   # CameraEffectManager: its camera VM runs the scripts
        self.file_registry = file_registry
        self._model_paths = []                 # imported d?c / c0m / d?w paths, in import order
        self._cast_pending = False             # models added while hidden: cast when first shown
        self._game_data = None                 # one load_all()ed GameData for every model
        self._stage = None                     # IfritManager the panel films: holds the main model
        self.panel = None                      # CameraPreviewPanel, built with the first model
        self.track = None                      # CameraTrack of the selected effect
        self.last_run = None                   # CameraScriptRun of the last resolve
        self.previewed = None                  # animation shown in the panel
        self._updating = False
        # scene.out goes through the shared binding: opening it here (or in Ifrit, Xu...) feeds
        # the setup's encounter picker, which shares the same file.
        self.sceneout_binding = FileBinding("scene.out", file_registry, read_only=True,
                                            file_filter="scene.out")

        # Who stands in the battle: the panel every battle preview shares (party, caster, target),
        # offering only the imported models
        from Ifrit.IfritCameraSeq.battlecast import BattleCastPanel
        # its models are read with the game data loaded in full on first use
        # (its encounter list follows the model filmed once there is one: the panel's stage)
        self.cast = BattleCastPanel(self._shared_game_data, self.model_paths, mode="cast",
                                    file_registry=file_registry, picker_manager=SimpleNamespace(enemy=None))
        self.cast.changed.connect(lambda: self._cast_changed(defaults=True))
        self.party_combos, self.weapon_combos = self.cast.party_combos, self.cast.weapon_combos
        self.caster_combo, self.target_combo = self.cast.caster_combo, self.cast.target_combo

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

        self.placeholder = QLabel("Import a caster and a target with the header's Import complementary "
                                  "(Camera preview models), and scene.out to place them in a real "
                                  "encounter.")
        self.placeholder.setWordWrap(True)
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setStyleSheet("color: gray")

        # Everything above the result line folds away, so the 3D view can take all the room
        self.settings_section = CollapsibleSection(
            "Preview settings", expanded=True,
            tooltip="Party, caster/target and script inputs: fold them to enlarge the 3D preview")
        self.settings_section.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        settings_layout = self.settings_section.content_layout()
        settings_layout.setContentsMargins(0, 0, 0, 0)
        # Its slot here: the same panel moves to the effect preview (Overview) while that one is shown
        self.battle_slot = QWidget()
        QVBoxLayout(self.battle_slot).setContentsMargins(0, 0, 0, 0)
        self.battle_slot.layout().addWidget(self.cast)
        settings_layout.addWidget(self.battle_slot)
        settings_layout.addWidget(self.inputs_section)
        settings = getattr(file_registry, "settings", None)
        self.settings_section.remember(settings, SETTINGS_STATE_KEY)
        self.inputs_section.remember(settings, INPUTS_STATE_KEY)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.addWidget(self.settings_section)
        self._layout.addWidget(self.result_label)
        self._layout.addWidget(self.play_button, 0, Qt.AlignmentFlag.AlignLeft)
        self._layout.addWidget(self.placeholder, 1)
        defaults = CameraScriptInputs()
        self._updating = True
        self.opening_spin.setValue(defaults.opening)
        self.targets_spin.setValue(defaults.affected_targets)
        self.cast.refresh()
        self._updating = False
        self._show_run(None)

    def _spin(self, minimum, maximum, tooltip):
        spin = _NoWheelSpinBox()
        spin.setRange(minimum, maximum)
        spin.setToolTip(tooltip)
        spin.setKeyboardTracking(False)
        spin.valueChanged.connect(lambda _value: self._inputs_changed())
        return spin

    # ------------------------------------------------------------------ imports
    def import_models(self):
        paths = QFileDialog.getOpenFileNames(
            self, "Characters, weapons and monsters for the preview (read-only)",
            self.file_registry.last_folder(MODEL_FOLDER_KEY) or os.getcwd(),
            "Battle models (c0m*.dat d?c*.dat d?w*.dat)")[0]
        if paths:
            self.add_models(paths)

    def import_sceneout(self):
        path = self.sceneout_binding.open_dialog(self, default_dir=self.file_registry.last_folder("scene.out"))
        if path:
            self.file_registry.remember_folder("scene.out", os.path.dirname(path))

    def add_models(self, paths):
        """Offer characters (d?c), their weapons (d?w) and monsters (c0m), loaded when used. New
        characters fill the empty party slots, each with its first weapon - one file per character
        (d0c000 and d0c001 are both Squall), as a battle's party."""
        added = [path for path in dict.fromkeys(paths) if path not in self._model_paths
                 and (_MONSTER_FILE.match(_name(path)) or _CHARACTER_FILE.match(_name(path))
                      or _WEAPON_FILE.match(_name(path)))]
        if paths:
            self.file_registry.remember_folder(MODEL_FOLDER_KEY, os.path.dirname(paths[0]))
            self.file_registry.remember_files(MODEL_SELECTION_KEY, paths)
        if not added:
            return
        self._model_paths.extend(added)
        self._updating = True
        try:
            self.cast.refresh()     # new characters fill the empty party slots
        finally:
            self._updating = False
        self.models_changed.emit()
        if self.window().isVisible() and not self.isVisible():
            # Import previous: loading the cast's models takes seconds; do it when first shown
            self._cast_pending = True
        else:
            self._cast_changed(defaults=True)

    def take_battle_setup(self):
        """Show the battle setup here (the effect preview borrows the very same panel while shown)."""
        if self.cast.parentWidget() is not self.battle_slot:
            self.battle_slot.layout().addWidget(self.cast)
            self.cast.show()

    def showEvent(self, event):
        super().showEvent(event)
        self.take_battle_setup()
        if self._cast_pending:
            self._cast_pending = False
            self._cast_changed(defaults=True)

    def model_paths(self):
        return list(self._model_paths)

    def character_paths(self):
        return self.cast.character_paths()

    def monster_paths(self):
        return self.cast.monster_paths()

    def weapon_paths(self, character_path):
        return self.cast.weapon_paths(character_path)

    def _shared_game_data(self):
        if self._game_data is None:
            game_data = self.camera_manager.game_data
            game_data.load_all()
            self._game_data = game_data
        return self._game_data

    def model(self, path):
        """The loaded (read-only) model of an imported path, or None; loading errors are reported."""
        return self.cast.model(path)

    def party_members(self):
        """{party slot: (character path, weapon path or None)} of the filled party slots."""
        return self.cast.party_members()

    def _encounter(self):
        """The encounter selected in the setup's picker, or None (manual placement)."""
        if self.panel is None:
            return None
        return self.panel._battle_setup.encounters.selected

    def caster_key(self):
        return self.cast.caster_key()

    def target_key(self):
        return self.cast.target_key()

    def caster_path(self):
        return self.cast.actor_path(self.caster_key())

    def target_path(self):
        return self.cast.actor_path(self.target_key())

    def _actor_path(self, key):
        return self.cast.actor_path(key)

    def battle_cast(self, placed=False):
        """The battle this preview films, for the effect recorder (Fujin.nativepreview.BattleCast):
        the party with its weapons, the encounter's enemies (an enemy not imported is named,
        c0mNNN.dat, and left out) or the imported caster / target monsters, in their
        battle slots (0-6: an enemy past the 4th is left out). placed: also where the setup stands
        them and the effect camera it plays (_place_cast). None without a caster."""
        from Fujin.nativepreview import BattleCast
        caster_key, target_key = self.caster_key(), self.target_key()
        if caster_key is None:
            return None
        slots = {slot: (body, weapon) for slot, (body, weapon) in self.party_members().items()}
        encounter = self._encounter()
        if encounter is not None:
            for enemy in encounter.enabled_slots():
                key = ("enemy", enemy.slot_index)
                slots[self._slot_of(key)] = (self._actor_path(key) or f"c0m{enemy.com_file_id:03}.dat", None)
        for key, other in ((caster_key, target_key), (target_key, caster_key)):
            if key is not None and key[0] == "monster":
                slots[self._slot_of(key, other)] = (key[1], None)
        slots = {slot: files for slot, files in slots.items() if slot <= 6}
        cast = BattleCast(slots, self._slot_of(caster_key, target_key), self._slot_of(target_key, caster_key))
        if placed:
            self._place_cast(cast)
        return cast

    def load_battle(self):
        """Cast the models imported while this preview was hidden, now (the effect preview needs
        the battle: its encounter picker, its placement)."""
        if self._cast_pending:
            self._cast_pending = False
            self._cast_changed(defaults=True)

    def encounter_combo(self):
        """The battle setup's scene.out encounter list."""
        return self.cast.encounters.encounter

    def _plan_animations(self, cast):
        """Each actor's idle animation and the caster's Magic cast, read from its sequences (a
        character's are in its weapon file: without one imported it stands in animation 0)."""
        from FF8GameData.dat.actoranimplan import cast_plan, idle_animation, read_frame_counts, read_sequences
        from FF8GameData.dat.sequencevm import as_sequence_vm
        vm = as_sequence_vm(self._shared_game_data())
        for slot, (body, weapon) in cast.slots.items():
            sequences = read_sequences(weapon if _CHARACTER_FILE.match(_name(body)) else body) \
                if (weapon or not _CHARACTER_FILE.match(_name(body))) else {}
            cast.idle[slot] = idle_animation(vm, sequences)
            if slot == cast.caster and sequences:
                cast.cast_before, cast.cast_during = cast_plan(vm, sequences, read_frame_counts(body))

    def _place_cast(self, cast):
        """Where this preview's battle setup stands each actor and the effect camera it plays there:
        the effect preview then shows the same shot. Models still waiting to be cast (imported
        while hidden) are loaded now."""
        self.load_battle()
        if self.panel is None:
            return
        from FF8GameData.dat.battlecamera import play_camera_animation
        try:
            context = self.panel._battle_setup.build(0, False)
        except Exception:
            return       # a setup the camera preview cannot build either: the recorder's places
        actors = {slot: actor for slot, actor in context.slots.items() if 0 <= slot <= 6}
        if cast.caster not in actors:
            return
        # one frame of reference: the actors the setup placed (manual placement is around the caster)
        cast.slots = {slot: files for slot, files in cast.slots.items() if slot in actors}
        cast.positions = {slot: tuple(float(v) for v in actor.position) for slot, actor in actors.items()}
        cast.yaws = {slot: float(actor.yaw) for slot, actor in actors.items()}
        cast.cast_camera = (tuple(float(v) for v in context.initial.eye), tuple(float(v) for v in context.initial.target))
        self._plan_animations(cast)
        _run, animation = self.resolve()
        if self.track is not None and animation is not None:
            cast.camera = play_camera_animation(animation, context) or None

    @staticmethod
    def _slot_of(key, other_key=None):
        from Ifrit.IfritCameraSeq.battlecast import BattleCastPanel
        return BattleCastPanel.slot_of(key, other_key)

    # ------------------------------------------------------------------ feeding the shared setup
    def _ensure_panel(self):
        if self.panel is not None:
            return self.panel
        from Ifrit.ifritmanager import IfritManager
        from Ifrit.IfritCameraSeq.camerapreview import CameraPreviewPanel
        self._stage = IfritManager(game_data=self._shared_game_data())
        # Fujin's battle setup panel places the actors (shown in Preview settings): the camera
        # preview keeps the manual placement and the views
        self.panel = CameraPreviewPanel(self._stage, file_registry=self.file_registry, cast=self.cast)
        self.cast.encounters.manager = self._stage   # the encounters of the model filmed
        from Ifrit.IfritCameraSeq.camerapreview import BATTLE_SETUP_STATE_KEY
        setup = self.panel._battle_setup
        settings = getattr(self.file_registry, "settings", None)
        if settings is None or not settings.contains(BATTLE_SETUP_STATE_KEY):
            setup.group.set_expanded(True)
        for spin in (setup.caster_slot, setup.target_slot):
            spin.valueChanged.connect(lambda _value: self._slots_changed())
        self._layout.replaceWidget(self.placeholder, self.panel)
        self.placeholder.hide()
        self._layout.setStretchFactor(self.panel, 1)
        return self.panel

    def _slots_changed(self):
        if not self._updating:
            self.play_effect()

    def _cast_changed(self, defaults=False):
        """Film the caster in the shared setup: main model, party, opponent and slots."""
        if self._updating:
            return
        caster_key, target_key = self.caster_key(), self.target_key()
        caster_model, target_model = self.cast.actor_model(caster_key), self.cast.actor_model(target_key)
        main = caster_model or target_model
        if main is None:
            self.play_effect()
            return
        panel = self._ensure_panel()
        setup = panel._battle_setup
        main_key = caster_key if caster_model is not None else target_key
        self._updating = True
        try:
            if self._stage.enemy is not main.enemy:
                self._stage.enemy = main.enemy
                self._stage.texture_data = list(main.texture_data)
                self._stage.texture_black_is_transparent = main.texture_black_is_transparent
                panel.invalidate()
            panel.set_weapon(self.cast.actor_weapon(main_key))
            if self._encounter() is not None:
                if main_key[0] == "enemy":
                    picker = setup.encounters
                    picker.enemy_slot.setCurrentIndex(max(0, next(
                        (index for index in range(picker.enemy_slot.count())
                         if picker.enemy_slot.itemData(index).slot_index == main_key[1]), 0)))
            self.cast.apply(setup)
            if defaults:
                self._set_default_inputs(caster_model, target_model)
        finally:
            self._updating = False
        self.play_effect()

    def _set_default_inputs(self, caster_model, target_model):
        caster_monster = caster_model is not None and is_monster(caster_model)
        self.opening_spin.setValue(OPENING_MONSTER_MAGIC if caster_monster else 0)
        category = (target_model.enemy.info_stat_data.get("camera_category", 0)
                    if target_model is not None and is_monster(target_model) else None)
        self.category_spin.setValue(camera_category_value(category) if category is not None else 0)

    # ------------------------------------------------------------------ script
    def battle_slots(self):
        """(attacker slot, target slot): the setup's, or the cast pickers' before any model loads."""
        if self.panel is not None:
            setup = self.panel._battle_setup
            return setup.caster_slot.value(), setup.target_slot.value()
        caster, target = self.caster_key(), self.target_key()
        return self._slot_of(caster, target) if caster else 0, self._slot_of(target, caster)

    def inputs(self) -> CameraScriptInputs:
        status = self.status_combo.currentData()
        target = self.cast._models.get(self.target_path())   # only if loaded already
        if target is not None and is_monster(target):
            status &= ~STATUS_LOW_HEALTH       # CameraSeq_ReadSpecialVar_C3: monsters never kneel
        attacker_slot, target_slot = self.battle_slots()
        return CameraScriptInputs(opening=self.opening_spin.value(), attacker_slot=attacker_slot,
                                  target_slot=target_slot, target_status=status,
                                  target_category=self.category_spin.value(),
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
        self.animation_chosen.emit(run.chosen)
        return run, animation

    # The script inputs by the names the form gives them (the VM's own names are for research)
    _INPUT_NAMES = {0x00: "Opening shot", 0x10: "a script shot already playing", 0x11: "Random value",
                    0x13: "party members alive", 0x15: "Target camera category", 0x16: "Target status",
                    0x17: "Action count - 1", 0x18: "attacker slot", 0x19: "target slot",
                    0x1A: "Affected targets", 0x1B: "party members with no status"}

    def _input_name(self, parameter):
        if parameter in self._INPUT_NAMES:
            return self._INPUT_NAMES[parameter]
        if 0x1C <= parameter <= 0x22:
            return f"Random value mod {parameter - 0x1A}"
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
        if not self._updating:
            self.play_effect()

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
                                    "Import a caster and a target first (header's Import complementary: "
                                    "Camera preview models).")
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
