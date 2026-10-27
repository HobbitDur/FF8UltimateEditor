"""The battle setup every battle preview shows, the same widget everywhere (Fujin's effect camera
and effect previews, Ifrit's Camera and Sequence tabs and its 3D battle view, SolomonRing's
commands): the scene.out encounter (and the slot of the model filmed), the party (a character and
its weapon per slot) and, for a camera, the caster and the target.

The models are only the .dat files the host's user loaded (Ifrit's file list, Fujin's imported
models...): the panel lists them, it never opens a file nor looks one up in a folder; scene.out
comes from the header toolbar too (the setup's encounter picker shares that file). The panel feeds
the scene builder, BattlePreviewSetup (apply), whose own state controls stay hidden.

Actor keys: ("party", party slot), ("enemy", scene.out slot index) in an encounter, ("monster",
path) for a loaded monster in manual placement, None (no model: a marker).

Modes:
  "cast"   no main model (Fujin): Caster and Target pick any actor; the caster is filmed.
  "role"   the host's model is the main one (Ifrit's Camera tab, SolomonRing): it is the Caster or
           the Target, and Other picks who stands for the other one.
  "other"  the host's model is the main one and no camera is played (3D battle view, Sequence
           tab): Other picks the model facing it (the target of a sequence's walk).
"""
import os
import re

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QGridLayout, QLabel, QComboBox, QApplication,
                             QMessageBox)

from FF8GameData.monsterdata import EntityType

PARTY_SIZE = 3
FIRST_ENEMY_SLOT = 3
_MONSTER_FILE = re.compile(r"^c0m(\d{3})\.dat$", re.IGNORECASE)
_CHARACTER_FILE = re.compile(r"^d([0-9a-f])c\d{3}\.dat$", re.IGNORECASE)
_WEAPON_FILE = re.compile(r"^d([0-9a-f])w\d{3}\.dat$", re.IGNORECASE)
# Read-only models of the loaded files, shared by every panel (Ifrit's Camera and Sequence tabs and
# 3D battle view stand the same files): (game data, path, modification time) -> IfritManager
_MODEL_CACHE = {}
_MODEL_CACHE_SIZE = 16
NO_CHARACTER_TEXT = ("No character loaded: open character .dat files (d?c###.dat, and their d?w###.dat "
                     "weapons) to stand the party.")


def file_name(path):
    return os.path.basename(str(path))


def is_character_file(path):
    return bool(_CHARACTER_FILE.match(file_name(path)))


def is_monster_file(path):
    return bool(_MONSTER_FILE.match(file_name(path)))


def is_weapon_file(path):
    return bool(_WEAPON_FILE.match(file_name(path)))


def character_digit(path):
    """The character a d?c###.dat is (its ? digit: 0 Squall, 1 Zell...)."""
    return _CHARACTER_FILE.match(file_name(path)).group(1).lower()


def index_of(combo, data):
    """The row whose data equals data (QComboBox.findData only matches the very same Python object)."""
    return next((row for row in range(combo.count()) if combo.itemData(row) == data), -1)


def _same(a, b):
    return a is not None and b is not None and os.path.normcase(os.path.abspath(str(a))) == \
        os.path.normcase(os.path.abspath(str(b)))


class BattleCastPanel(QWidget):
    changed = pyqtSignal()

    def __init__(self, game_data, model_paths=None, mode="cast", main_manager=None, main_path=None,
                 file_registry=None, picker_manager=None, parent=None):
        """game_data: the GameData the models are read with, or a callable returning it fully loaded
        (Fujin loads its data on the first model). model_paths: callable -> the loaded .dat paths
        (None: none). main_manager/main_path: the host's own model (modes "role" and "other"), drawn
        live - its edits show. file_registry: the shared file bank (scene.out). picker_manager: the
        manager whose model the encounter list is filtered for (default main_manager; Fujin's stage)."""
        super().__init__(parent)
        self.game_data = game_data
        self.model_paths_source = model_paths
        self.mode = mode
        self.main_manager = main_manager
        self._main_path = main_path
        self.setup = None                      # the BattlePreviewSetup fed (attach)
        self._models = {}                      # path -> loaded read-only IfritManager
        self._failed = set()
        self._updating = False
        self._picker_slot = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        from .encounterpreview import EncounterPicker
        self.encounters = EncounterPicker(picker_manager if picker_manager is not None else main_manager,
                                          file_registry, host_cast=mode == "cast")
        # with a model of the host's, the encounter's slot pick is that model's own slot (a monster);
        # a character's opponent is Other's
        self.encounters.monster_slot_only = mode != "cast"
        self.encounters.refresh_model(force=True)
        self.encounters.changed.connect(self._encounter_changed)   # once the pickers below exist
        layout.addWidget(self.encounters)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.addWidget(QLabel("Party"), 0, 0)
        grid.addWidget(QLabel("Character"), 0, 1)
        grid.addWidget(QLabel("Weapon"), 0, 2)
        self.party_combos, self.weapon_combos = [], []
        for slot in range(PARTY_SIZE):
            character, weapon = QComboBox(), QComboBox()
            for combo in (character, weapon):
                combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
            character.setToolTip(f"Party slot {slot}: the character standing there (a loaded d?c###.dat)")
            weapon.setToolTip("The weapon in this character's hands (a loaded d?w###.dat of the same character)")
            character.currentIndexChanged.connect(lambda _index, row=slot: self._party_changed(row))
            weapon.currentIndexChanged.connect(lambda _index: self._emit())
            grid.addWidget(QLabel(f"{slot}:"), slot + 1, 0)
            grid.addWidget(character, slot + 1, 1)
            grid.addWidget(weapon, slot + 1, 2)
            self.party_combos.append(character)
            self.weapon_combos.append(weapon)
        row = PARTY_SIZE + 1
        self.role_combo = QComboBox()
        self.role_combo.addItems(["Caster", "Target"])
        self.role_combo.setToolTip("Whether this model casts the action the camera films, or receives it")
        self.role_combo.currentIndexChanged.connect(lambda _index: self._caster_changed())
        self.caster_combo = QComboBox()
        self.caster_combo.setToolTip("The battle slot casting the action: a party member, or an enemy of "
                                     "the encounter (a loaded monster without one)")
        self.caster_combo.currentIndexChanged.connect(lambda _index: self._caster_changed())
        self.target_combo = QComboBox()
        self.target_combo.setToolTip("The battle slot the action is cast on" if mode == "cast" else
                                     "Who stands for the other side: a party member, an enemy of the "
                                     "encounter, or a loaded monster without one")
        self.target_combo.currentIndexChanged.connect(lambda _index: self._emit())
        for combo in (self.role_combo, self.caster_combo, self.target_combo):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        rows = {"cast": (("Caster:", self.caster_combo), ("Target:", self.target_combo)),
                "role": (("This model is the:", self.role_combo), ("Other:", self.target_combo)),
                "other": (("Other model:", self.target_combo),)}[mode]
        self._cast_rows = []
        for label, combo in rows:
            label = QLabel(label)
            grid.addWidget(label, row, 0)
            grid.addWidget(combo, row, 1, 1, 2, Qt.AlignmentFlag.AlignLeft)
            self._cast_rows.append((label, combo))
            row += 1
        grid.setColumnStretch(3, 1)            # every box packed on the left
        layout.addLayout(grid)
        self.message = QLabel(NO_CHARACTER_TEXT)
        self.message.setWordWrap(True)
        self.message.setStyleSheet("color: gray")
        layout.addWidget(self.message)
        self.refresh()

    @property
    def main_path(self):
        """The host's model file: the one given, else the file its manager holds now (a camera
        preview reloads its manager with another file)."""
        if self._main_path is not None:
            return self._main_path
        enemy = getattr(self.main_manager, 'enemy', None)
        return getattr(enemy, 'origin_path', None) or None

    # ------------------------------------------------------------------ models
    def model_paths(self):
        paths = list(self.model_paths_source() or []) if self.model_paths_source is not None else []
        if self.main_path is not None and not any(_same(path, self.main_path) for path in paths):
            paths.insert(0, self.main_path)
        return [path for path in dict.fromkeys(str(path) for path in paths)
                if is_character_file(path) or is_monster_file(path) or is_weapon_file(path)]

    def character_paths(self):
        return [path for path in self.model_paths() if is_character_file(path)]

    def monster_paths(self):
        return [path for path in self.model_paths() if is_monster_file(path)]

    def weapon_paths(self, character_path):
        """The loaded weapons of a character: d?w###.dat with its d?c digit."""
        digit = character_digit(character_path)
        return [path for path in self.model_paths()
                if (match := _WEAPON_FILE.match(file_name(path))) and match.group(1).lower() == digit]

    def path_of(self, name):
        """The loaded file of that name (lower case: an encounter's c0mNNN.dat), or None."""
        return next((path for path in self.model_paths() if file_name(path).lower() == name.lower()), None)

    def model(self, path):
        """The model of a loaded path: the host's own for its file, else a read-only load; None when
        it cannot be read (reported once)."""
        if path is None or path in self._failed:
            return None
        if self.main_manager is not None and _same(path, self.main_path):
            return self.main_manager
        if path not in self._models:
            from Ifrit.IfritCameraSeq.battlepreview import BattlePreviewSetup
            game_data = self.game_data() if callable(self.game_data) else self.game_data
            try:
                key = (id(game_data), os.path.normcase(os.path.abspath(path)), os.path.getmtime(path))
            except OSError:
                key = None
            if key is not None and key in _MODEL_CACHE:
                self._models[path] = _MODEL_CACHE[key]
            else:
                QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                try:
                    manager = BattlePreviewSetup._load_model(path, game_data, weapon=is_weapon_file(path))
                except Exception as error:
                    self._failed.add(path)
                    QApplication.restoreOverrideCursor()
                    QMessageBox.warning(self, "Battle preview", f"Cannot use {file_name(path)}: {error}")
                    return None
                QApplication.restoreOverrideCursor()
                if key is not None:
                    _MODEL_CACHE[key] = manager
                    while len(_MODEL_CACHE) > _MODEL_CACHE_SIZE:  # a long session stays bounded
                        _MODEL_CACHE.pop(next(iter(_MODEL_CACHE)))
                self._models[path] = manager
            if len(self._models) > _MODEL_CACHE_SIZE:
                self._models.pop(next(iter(self._models)))
        return self._models[path]

    def refresh(self):
        """The loaded files changed: offer them; new characters fill the empty party slots, each with
        its first weapon - one file per character (d0c000 and d0c001 are both Squall), as a battle's
        party. The host's own character stands in the party."""
        party = [combo.currentData() for combo in self.party_combos]
        characters = self.character_paths()
        party = [member if member in characters else None for member in party]
        if self.main_path is not None and is_character_file(self.main_path) \
                and not any(_same(member, self.main_path) for member in party):
            main = next(path for path in characters if _same(path, self.main_path))
            party[party.index(None) if None in party else 0] = main
        for path in characters:
            in_party = {character_digit(member) for member in party if member}
            if path not in party and None in party and character_digit(path) not in in_party:
                party[party.index(None)] = path
        weapons = [combo.currentData() for combo in self.weapon_combos]
        self._updating = True
        try:
            self._fill_party_combos(party, weapons)
            self._fill_cast_combos()
        finally:
            self._updating = False
        self.message.setVisible(not characters)
        self._emit()

    # ------------------------------------------------------------------ party
    def _fill_party_combos(self, party=None, weapons=None):
        characters = self.character_paths()
        for slot, combo in enumerate(self.party_combos):
            selected = party[slot] if party else combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("(empty)", None)
            for path in characters:
                combo.addItem(file_name(path), path)
            combo.setCurrentIndex(max(0, combo.findData(selected)) if selected else 0)
            combo.setEnabled(bool(characters))
            combo.blockSignals(False)
            self._fill_weapon_combo(slot, weapons[slot] if weapons else None)

    def _fill_weapon_combo(self, slot, selected=None):
        combo = self.weapon_combos[slot]
        character = self.party_combos[slot].currentData()
        options = self.weapon_paths(character) if character else []
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("(no weapon)", None)
        for path in options:
            combo.addItem(file_name(path), path)
        combo.setCurrentIndex(combo.findData(selected) if selected in options else (1 if options else 0))
        combo.setEnabled(character is not None)
        combo.blockSignals(False)

    def party_members(self):
        """{party slot: (character path, weapon path or None)} of the filled party slots."""
        return {slot: (combo.currentData(), weapon.currentData())
                for slot, (combo, weapon) in enumerate(zip(self.party_combos, self.weapon_combos))
                if combo.currentData() is not None}

    def _party_changed(self, slot):
        if self._updating:
            return
        self._fill_weapon_combo(slot)
        self._updating = True
        try:
            self._fill_cast_combos()
        finally:
            self._updating = False
        self._emit()

    # ------------------------------------------------------------------ cast
    def _encounter(self):
        return self.encounters.selected

    def main_key(self):
        """The actor key of the host's model (modes "role" and "other"), None in "cast" mode."""
        if self.main_manager is None:
            return None
        character = (is_character_file(self.main_path) if self.main_path is not None else
                     getattr(getattr(self.main_manager.enemy, 'entity_type', None), 'name', '').startswith('CHARACTER'))
        if character:
            return next((("party", slot) for slot, (path, _weapon) in self.party_members().items()
                         if _same(path, self.main_path)), ("party", 0))
        slot = self.encounters.selected_slot if self._encounter() is not None else None
        if slot is not None:
            return "enemy", slot.slot_index
        return "monster", self.main_path      # (a model with no file: no path)

    def _cast_options(self):
        """[(label, actor key)] of the battle slots that can stand in the preview."""
        options = [(f"Party {slot}: {file_name(path)}", ("party", slot))
                   for slot, (path, _weapon) in self.party_members().items()]
        encounter = self._encounter()
        if encounter is not None:
            picker = self.encounters
            options += [(f"Enemy {FIRST_ENEMY_SLOT + slot.slot_index}: {picker.monster_name(slot.com_file_id)} "
                         f"(c0m{slot.com_file_id:03})", ("enemy", slot.slot_index))
                        for slot in encounter.enabled_slots()]
        else:
            options += [(f"Monster: {file_name(path)}", ("monster", path)) for path in self.monster_paths()]
        if self.mode != "cast":
            main = self.main_key()
            options = [(label, key) for label, key in options if key != main]
        return options

    def _fill_cast_combos(self):
        options = self._cast_options()
        keys = [key for _label, key in options]
        if self.mode == "cast":
            caster, target = self.caster_key(), self.target_key()
            if caster not in keys:
                caster = keys[0] if keys else None
            if target not in keys or target == caster:
                target = next((key for key in keys if key != caster and key[0] != caster[0]),
                              next((key for key in keys if key != caster), None)) if caster else None
            combos = ((self.caster_combo, caster, "(load a model)"), (self.target_combo, target, "(none: a marker)"))
        else:
            main, target = self.main_key(), self.target_key()
            if target not in keys:
                # the other side of the battle, else anybody
                side = (main or ("monster",))[0] == "party"
                target = next((key for key in keys if (key[0] == "party") != side), keys[0] if keys else None)
            combos = ((self.target_combo, target, "(none: a marker)"),)
        for combo, selected, none_text in combos:
            combo.blockSignals(True)
            combo.clear()
            if combo is self.target_combo or not options:
                combo.addItem(none_text, None)
            for label, key in options:
                combo.addItem(label, key)
            combo.setCurrentIndex(max(0, index_of(combo, selected)))
            combo.blockSignals(False)

    def set_cast_visible(self, visible):
        """Show the caster / target / other model rows (a host with nothing to pick there hides them:
        Ifrit3D's battle view in an encounter, where every actor already stands)."""
        for label, combo in self._cast_rows:
            label.setVisible(visible)
            combo.setVisible(visible)

    def caster_key(self):
        if self.mode == "cast":
            return self.caster_combo.currentData()
        return self.main_key() if self.role_combo.currentIndex() == 0 or self.mode == "other" else self.target_key()

    def target_key(self):
        if self.mode == "role" and self.role_combo.currentIndex() == 1:
            return self.main_key()
        return self.target_combo.currentData()

    def other_key(self):
        """The actor facing the host's model (modes "role" and "other")."""
        return self.target_combo.currentData()

    def _caster_changed(self):
        if self._updating:
            return
        if self.mode == "cast" and self.caster_key() is not None and self.caster_key() == self.target_key():
            self._updating = True
            try:
                self._fill_cast_combos()  # the target moves to another actor
            finally:
                self._updating = False
        self._emit()

    def actor_path(self, key):
        """The loaded body file of an actor key (None when not loaded)."""
        if key is None:
            return None
        if key[0] == "party":
            return self.party_members().get(key[1], (None, None))[0]
        if key[0] == "monster":
            return key[1]
        encounter = self._encounter()
        slot = next((slot for slot in encounter.enabled_slots() if slot.slot_index == key[1]), None) \
            if encounter is not None else None
        if slot is None:
            return None
        if self.main_path is not None and key == self.main_key():
            return self.main_path
        return self.path_of(f"c0m{slot.com_file_id:03}.dat")

    def actor_model(self, key):
        return self.model(self.actor_path(key))

    def actor_weapon(self, key):
        if key is None or key[0] != "party":
            return None
        return self.model(self.party_members().get(key[1], (None, None))[1])

    @staticmethod
    def slot_of(key, other_key=None):
        """The battle slot id of an actor key (a loaded monster in manual placement takes the first
        enemy slot, the next one when the other actor is a monster too)."""
        if key is None:  # no model: the other side
            return 0 if other_key is not None and other_key[0] != "party" else FIRST_ENEMY_SLOT
        if key[0] == "party":
            return key[1]
        if key[0] == "enemy":
            return FIRST_ENEMY_SLOT + key[1]
        return FIRST_ENEMY_SLOT + (1 if other_key is not None and other_key[0] == "monster"
                                   and str(other_key) < str(key) else 0)

    # ------------------------------------------------------------------ feeding the setup
    def attach(self, setup):
        """Drive this BattlePreviewSetup (its encounter picker is this panel's)."""
        self.setup = setup

    def _encounter_changed(self):
        """Another encounter (or slot of the host's monster): offer its slots. A character caster
        faces the picker's enemy slot."""
        if self._updating:
            return
        picker = self.encounters
        self._updating = True
        try:
            self._fill_cast_combos()
            slot = picker.selected_slot
            caster = self.caster_key()
            if self.mode == "cast" and slot is not None and slot is not self._picker_slot \
                    and caster is not None and caster[0] == "party":
                self.target_combo.setCurrentIndex(max(0, index_of(self.target_combo, ("enemy", slot.slot_index))))
            self._picker_slot = slot
        finally:
            self._updating = False
        self._emit()

    def apply(self, setup=None):
        """Stand the actors in the setup: its party, the model facing the main one and the battle
        slots. Returns the main actor key, or None without a model to film."""
        setup = setup or self.setup
        caster_key, target_key = self.caster_key(), self.target_key()
        if self.mode == "cast":
            main_key = caster_key if self.actor_model(caster_key) is not None else target_key
            if self.actor_model(main_key) is None:
                return None
        else:
            main_key = self.main_key()
            if main_key is None:
                return None
        other_key = target_key if main_key == caster_key else caster_key
        members = self.party_members()
        setup.model_source = lambda name: self.model(self.path_of(name))   # loaded files only, one cache
        setup.party_models = {slot: (self.model(body), self.model(weapon))
                              for slot, (body, weapon) in members.items()
                              if main_key != ("party", slot) and self.model(body) is not None}
        setup.role.setCurrentIndex(0 if main_key == caster_key else 1)
        # The other model stands by hand only without an encounter: in one, every actor already has
        # its place (party, scene.out slots) and Other only says which slot is the target
        manual = self._encounter() is None
        setup.opponent = self.actor_model(other_key) if manual and other_key != main_key else None
        setup.opponent_weapon = self.actor_weapon(other_key) if manual else None
        size = max(members) + 1 if members else 1
        if main_key[0] == "party":
            # the formation depends on the party size, with an encounter or without
            size = max(size, main_key[1] + 1)
            setup.party_size.setValue(size)
            setup.party_slot.setValue(main_key[1])
        elif self._encounter() is not None and members:
            setup.party_size.setValue(size)
        ids = (self.slot_of(caster_key, target_key), self.slot_of(target_key, caster_key))
        for spin, value in zip((setup.caster_slot, setup.target_slot), ids):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
        return main_key

    def _emit(self):
        if not self._updating:
            self.changed.emit()
