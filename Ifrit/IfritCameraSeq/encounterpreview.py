"""Read-only encounter picker shared by monster and character camera previews."""
from pathlib import Path
import struct

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox, QLabel

from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from FF8GameData.sceneout import read_encounters, ENCOUNTER_SIZE, NB_ENCOUNTER


class EncounterPicker(QWidget):
    changed = pyqtSignal()

    def __init__(self, manager, registry=None, parent=None, host_cast=False):
        """host_cast: the host tool opens scene.out from the header toolbar and picks the
        actors itself (Fujin's Caster/Target), so the Open button and the slot pick are hidden."""
        super().__init__(parent)
        self.manager = manager
        self.encounters = []
        self.path = None
        self._model_key = None
        self._name_cache = {}
        self.host_cast = host_cast
        self.registry = registry if registry is not None else FileRegistry()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.open_button = QPushButton('Open scene.out…')
        self.open_button.clicked.connect(self._choose)
        self.open_button.setVisible(not host_cast)
        row.addWidget(self.open_button)
        self.encounter = QComboBox()
        self.encounter.setMinimumContentsLength(20)
        self.encounter.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.encounter.addItem('Manual placement', None)
        self.encounter.setToolTip('Encounter IDs are zero-based scene.out record numbers.')
        row.addWidget(self.encounter, 1)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.slot_label = QLabel('Enemy:')
        row.addWidget(self.slot_label)
        self.enemy_slot = QComboBox()
        row.addWidget(self.enemy_slot, 1)
        layout.addLayout(row)
        self.status = QLabel('Open scene.out to use encounter placement.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.encounter.currentIndexChanged.connect(self._picked)
        self.enemy_slot.currentIndexChanged.connect(lambda _i: self.changed.emit())
        self.binding = FileBinding('scene.out', self.registry, load_callback=self.load,
                                   read_only=True)
        self.binding.file_closed.connect(self._closed)
        self.binding.load_opened_file()
        self._picked()

    @property
    def is_monster(self):
        return getattr(self.manager.enemy.entity_type, 'name', '').startswith('MONSTER')

    @property
    def selected(self):
        return self.encounter.currentData()

    @property
    def selected_slot(self):
        return self.enemy_slot.currentData()

    def _choose(self):
        path = self.binding.open_dialog(self, self.registry.last_folder('scene.out'))
        if path:
            self.registry.remember_folder('scene.out', str(Path(path).parent))

    def load(self, path):
        try:
            raw = Path(path).read_bytes()
            if not raw or len(raw) % ENCOUNTER_SIZE or len(raw) > NB_ENCOUNTER * ENCOUNTER_SIZE:
                raise ValueError('expected complete 128-byte encounter records (up to 1024)')
            encounters = read_encounters(raw)
        except (OSError, ValueError) as error:
            self.status.setText(f'Cannot read scene.out: {error}')
            return False
        self.path = Path(path)
        self.encounters = encounters
        self.refresh_model(force=True)
        return True

    def _closed(self, _path):
        self.encounters = []
        self.path = None
        self.refresh_model(force=True)

    def monster_name(self, com_id):
        """Prefer the edited/current DAT name, then loose DAT names, then the catalog.

        Only read the section-7 name bytes; building a list must not expand every
        monster's geometry, animations or AI (including mod-added monsters).
        """
        enemy = self.manager.enemy
        if self.is_monster and com_id == getattr(enemy, 'id', None):
            name = getattr(enemy, 'info_stat_data', {}).get('monster_name')
            if name is not None:
                return str(name).strip('\x00').strip() or f'Monster {com_id}'
        if com_id in self._name_cache:
            return self._name_cache[com_id]
        game_data = getattr(self.manager, 'game_data', None)
        folders = ([self.path.parent] if self.path else []) + [
            Path(getattr(enemy, 'origin_path', '')).parent]
        for folder in folders:
            try:
                with (folder / f'c0m{com_id:03}.dat').open('rb') as source:
                    header = source.read(32)
                    if len(header) != 32 or struct.unpack_from('<I', header)[0] < 7:
                        continue
                    # Section 0 is the header itself; section N's pointer is DWORD N.
                    source.seek(struct.unpack_from('<I', header, 28)[0])
                    raw = source.read(24).split(b'\0', 1)[0]
                name = game_data.translate_hex_to_str(bytearray(raw)).strip()
                if name:
                    self._name_cache[com_id] = name
                    return name
            except (OSError, ValueError, AttributeError):
                continue
        catalog = getattr(game_data, 'monster_data_json', {}).get('monster', [])
        name = next((m['name'] for m in catalog if m['com_id'] == com_id), f'Monster {com_id}')
        self._name_cache[com_id] = name
        return name

    def refresh_model(self, force=False):
        key = (getattr(self.manager.enemy, 'origin_path', ''), self.is_monster,
               getattr(self.manager.enemy, 'id', None))
        if key == self._model_key and not force:
            return
        self._model_key = key
        self._name_cache.clear()
        previous = self.selected
        self.encounter.blockSignals(True)
        self.encounter.clear()
        self.encounter.addItem('Manual placement', None)
        for encounter in self.encounters:
            slots = encounter.enabled_slots()
            if not slots:
                continue
            if self.is_monster and not any(s.com_file_id == key[2] for s in slots):
                continue
            names = ', '.join(self.monster_name(s.com_file_id) for s in slots)
            self.encounter.addItem(f'Encounter {encounter.index} · stage {encounter.stage_id} · {names}', encounter)
            if previous is not None and encounter.index == previous.index:
                # Another model loaded: stay in the same encounter while it still matches
                self.encounter.setCurrentIndex(self.encounter.count() - 1)
        self.encounter.blockSignals(False)
        self._picked()

    def _picked(self, _index=0):
        encounter = self.selected
        previous = self.selected_slot
        self.enemy_slot.blockSignals(True)
        self.enemy_slot.clear()
        if encounter is not None:
            for slot in encounter.enabled_slots():
                if self.is_monster and slot.com_file_id != self.manager.enemy.id:
                    continue
                self.enemy_slot.addItem(
                    f'Slot {slot.slot_index} · {self.monster_name(slot.com_file_id)} · {slot.position}', slot)
                if previous is not None and slot.slot_index == previous.slot_index:
                    self.enemy_slot.setCurrentIndex(self.enemy_slot.count() - 1)
        self.enemy_slot.blockSignals(False)
        self.slot_label.setText('Loaded monster:' if self.is_monster else 'Enemy opponent:')
        self.slot_label.setVisible(encounter is not None and not self.host_cast)
        self.enemy_slot.setVisible(encounter is not None and not self.host_cast)
        if encounter is None:
            count = self.encounter.count() - 1
            self.status.setText(f'{count} matching encounters. Manual placement.' if self.path else
                                "Import scene.out (header's Import complementary) to use encounter placement."
                                if self.host_cast else 'Open scene.out to use encounter placement.')
        else:
            self.status.setText(f'Encounter {encounter.index} · stage {encounter.stage_id} · '
                                'Enemy positions from scene.out; normal party formation.')
        self.changed.emit()
