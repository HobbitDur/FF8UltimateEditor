import csv
import json
import os

from PIL.ImageQt import ImageQt
from PyQt6.QtCore import QSignalBlocker, Qt
from PyQt6.QtGui import QIcon, QPixmap, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QSpinBox, QDoubleSpinBox, QLineEdit, QGroupBox, QFormLayout, QTabWidget, QCheckBox,
    QGridLayout, QScrollArea, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractSpinBox,
    QAbstractItemView, QSizePolicy, QStyle, QMessageBox, QPushButton,
)

U32_MAX = 0xFFFFFFFF

# Tooltip shown on the read-only (greyed) padding fields.
RESERVED_TOOLTIP = ("Read-only: this byte has no meaning in the game (confirmed unused / padding — "
                    "no code reads it). It is shown for completeness and preserved on save, but "
                    "editing it would have no effect.")

from CCGroup import cardlocation
from CCGroup.ccgroup import CCGroupWidget
from CCGroup.jsmcardgame import CardGameFolderManager, GAME_RULE_BITS, TRADE_RULE_NAMES
from Common.fieldfolder import pick_field_folder
from Common.filebinding import FileBinding
from Common.fileregistry import busy_cursor
from Common.fileregistry import FileRegistry
from Common.kernelnamesource import KernelNameSource
from FF8GameData.gamedata import GameData
from FF8GameData.itemids import FIRST_ADDED_ITEM
from FF8GameData.kernelgfabilities import ABILITY_LIST_COUNT, gf_ability_slots
from FF8GameData.kernellevels import load_kernel
from SolomonRing.kernellookups import LookupRegistry
from Quezacotl.quezacotlmanager import (
    CHARACTER_NAMES, COMMAND_ABILITY_GROUPS, EQUIPPED_ABILITY_GROUPS, CharacterEntry,
    VANILLA_ABILITY_COUNT,
    GF_COMPATIBILITY_MIN, GF_COMPATIBILITY_MAX,
)
from Hyne.hynesavemap import EXTENDED_MAGIC_FIRST, read_shop_file, scene_uses_extra_monsters
from Hyne.hynesavepages import (
    BattlePage, ChocoboPage, DrawPointsPage, FieldVariablesPage, ItemsExtrasPage, LoadScreenPage, PartyPage, ProgressPage,
    ShopsPage, WorldMapPage,
)
from Hyne.hynemanager import (
    HyneManager, LEARNED_ABILITY_BITS, SAVE_ABILITY_IDS, kernel_widens_abilities, TT_CARD_COPIES_MASK, TT_NB_RARE_CARDS, TT_NB_REGIONS, TT_NB_LAST_RULES,
    TT_VAR_REGION_RULES, TT_VAR_REGION_TRADE_RULE, TT_VAR_LAST_RULES, TT_VAR_LAST_REGIONS,
    TT_VAR_QUEEN_LOCATION, TT_VAR_TRADE_RATING_REGION, TT_VAR_TRADE_RATING, TT_VAR_DEGENERATION,
    TT_VAR_QUEEN_TRADE_RULE, TT_VAR_QUEEN_QUEST, TT_VAR_BGU_DIALOGS, TT_VAR_CC_QUEST, TT_VAR_BGU_WINS,
    TT_CC_DIALOG_MASK, ITEM_MAX_QUANTITY,
)

# Junction stat slots: (manager field, label). Each stores a magic id (0 = none); the
# potency comes from that spell's kernel junction value scaled by the quantity stocked.
JUNCTION_FIELDS = [
    ("jun_hp", "HP"), ("jun_str", "Str"), ("jun_vit", "Vit"), ("jun_mag", "Mag"),
    ("jun_spr", "Spr"), ("jun_spd", "Spd"), ("jun_eva", "Eva"), ("jun_hit", "Hit"),
    ("jun_luck", "Luck"), ("jun_ele_atk", "Elem Atk"), ("jun_status_atk", "Status Atk"),
    ("jun_ele_def1", "Elem Def 1"), ("jun_ele_def2", "Elem Def 2"),
    ("jun_ele_def3", "Elem Def 3"), ("jun_ele_def4", "Elem Def 4"),
    ("jun_status_def1", "Status Def 1"), ("jun_status_def2", "Status Def 2"),
    ("jun_status_def3", "Status Def 3"), ("jun_status_def4", "Status Def 4"),
]

TT_MAX_COPIES = 100   # MoveCardToLocation@0x5347F0 adds no copy past this
TT_PREVIEW_SIZE = 128
TT_SMALL_SPIN_WIDTH = 78   # a 3-digit value next to the arrows of the Windows 11 style
# The regions of the card rule variables, in their order
TT_REGION_NAMES = ["Balamb", "Galbadia", "Trabia", "Centra", "Dollet", "Fishermans Horizon", "Lunar Gate", "Esthar"]
# The Queen's towns: value N is the town of region N-1
TT_QUEEN_CITIES = ["Balamb", "Deling City", "Shumi Village", "Winhill", "Dollet", "Fishermans Horizon", "Lunar Gate",
                   "Esthar City"]
TT_QUEEN_QUEST_CARDS = ["None", "Kiros", "Irvine", "Chubby Chocobo", "Doomtrain", "Phoenix"]
# (cc_quest value, the last member beaten): each step adds its bits to the previous ones
TT_CC_QUEST_STEPS = [(0, "None"), (0x01, "Jack"), (0x03, "Clover"), (0x13, "Diamonds"), (0x17, "Spade"),
                     (0x1F, "Queen of Hearts"), (0x021F, "Kadowaki"), (0x221F, "King of Cards")]


class U32SpinBox(QDoubleSpinBox):
    """A whole-number spin box for the save's 32-bit UNSIGNED fields (exp, gil).

    QSpinBox is limited to a signed 32-bit int, so it stops at 2147483647 while those fields
    hold up to 4294967295. Half the range being unreachable is bad enough on its own; worse,
    handing QSpinBox.setValue a bigger number raises OverflowError, and an exception raised
    inside a Qt slot (loading a save runs through one) takes the whole application down with
    it. A QDoubleSpinBox showing no decimals looks and behaves the same and covers the range -
    every u32 value is exact in a double, whose integers are exact up to 2^53.

    value() hands back an int so the manager writes an int straight into the save.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDecimals(0)
        self.setRange(0, U32_MAX)
        self.setSingleStep(1)
        self.setGroupSeparatorShown(False)

    def value(self) -> int:
        return int(super().value())


class HyneWidget(QWidget):
    """.ff8 Steam save-file editor, native to this project's PyQt6 toolset (replaces the
    need for the third-party Hyne.exe GUI tool in ExternalTools/Hyne, which shares the name).

    Same GF / character / config / misc / items data as Quezacotl (init.out editor) — a
    save's savemap+80 region is byte-identical in layout to init.out, so this widget reuses
    Quezacotl's exact entry classes via HyneManager, which only differs in how it reads and
    writes the outer .ff8 envelope (LZSS compression + CRC16 checksum + a mandatory .bak
    backup before every save). The Triple Triad tab is here too; the other tabs of what init.out
    doesn't hold are in hynesavepages.py."""

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData", file_registry=None, settings=None):
        QWidget.__init__(self)
        self.settings = settings

        if file_registry is None:  # Used alone, it shares its files with nobody
            file_registry = FileRegistry()
        self.file_registry = file_registry

        self.game_data = GameData(game_data_folder)
        self.manager = HyneManager(self.game_data)
        self.manager.follow_mod_files = True
        self.game_data.load_card_data()
        self._card_info = self.game_data.card_data_json["card_info"]
        self.tt_var_widgets = []   # (widget, field variable) of the Triple Triad tab
        self.game_data.load_monster_data()
        self.game_data.load_field_data()
        self.field_names = {entry["id"]: entry["name"] for entry in self.game_data.field_data_json["field"]
                            if entry["id"] >= 0}
        self.icon_path = icon_path

        # Named option lists shared with the rest of the suite.
        self.lookups = LookupRegistry(self.game_data, game_data_folder)
        self._magic_entries = self.lookups.resolve("magic")["entries"]
        self._magic_names = {entry["value"]: entry["name"] for entry in self._magic_entries}
        self._item_entries = self.lookups.resolve("item")["entries"]
        self._gforce_entries = self.lookups.resolve("gforce")["entries"]
        self._status_entries = self.lookups.resolve("status_1")["entries"]
        self._party_entries = (self.lookups.resolve("weapon_character")["entries"]
                               + [{"value": 0xFF, "name": "None"}])
        # The ability and weapon NAMES come only from a kernel.bin, opened as a complementary
        # file (see _on_kernel_names_changed) - there is no built-in list of them.

        json_dir = os.path.join(game_data_folder, "Resources", "json")

        def _load_json(name):
            with open(os.path.join(json_dir, name), encoding="utf-8") as json_file:
                return json.load(json_file)

        self.hyne_data = _load_json("hyne_data.json")
        self._added_magic_ids = set()   # the spells of the open kernel.bin in the magic lists
        self.field_variable_entries = _load_json("hyne_field_variables.json")

        # Button-remap action list (dedicated json — the config bytes store a logical action id).
        button_config = _load_json("button_config.json")
        self._button_action_entries = [{"value": a["id"], "name": a["name"]} for a in button_config["action"]]
        self._button_action_notes = {a["id"]: a.get("note", "") for a in button_config["action"]}

        # Weapon names for the "unlocked weapons" bitmask: bit i = kernel weapon id i (1:1).
        # Only bits 0-27 (the 28 junk-shop-upgradeable party weapons) are used by the game.
        # The names come from kernel.bin; only whose weapon each bit is stays built in.
        weapon_data = _load_json("kernel_bin_data.json")["weapon_data"]
        self._weapon_characters = {w["id"]: w["character"] for w in weapon_data if w["id"] < 28}

        # Limit-break unlock bitfields. Irvine's shot names come from item.json (ids 101-108).
        limit_data = _load_json("limit_break.json")
        item_name = {e["value"]: e["name"] for e in self._item_entries}
        irvine_shot = [{"bit": i, "name": item_name.get(101 + i, f"Ammo {101 + i}")} for i in range(8)]
        self._limit_bitfield_defs = [
            ("limit_quistis", "Quistis — Blue Magic", limit_data["quistis_blue_magic"],
             "Learned Blue Magic (Quistis limit break) — 16-bit mask"),
            ("limit_zell", "Zell — Duel", limit_data["zell_duel"],
             "Known Duel moves (Zell limit break)"),
            ("limit_irvine", "Irvine — Shot", irvine_shot,
             "Unlocked Shot ammo types (Irvine limit break); each also usable if you carry that ammo"),
            ("limit_selphie", "Selphie — Slot", limit_data["selphie_slot"],
             "Unlocked Slot special spells (Selphie limit break)"),
            ("limit_angelo_known", "Angelo — Known", limit_data["angelo_command"],
             "Angelo commands known / in learning"),
            ("limit_angelo_completed", "Angelo — Completed", limit_data["angelo_command"],
             "Angelo commands fully learned"),
        ]

        self.setWindowTitle("Hyne")
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'hobbitdur.ico')))

        # Open/Save run from the shared header toolbar. A .ff8 save has no fixed FF8 name (each is
        # slotX_saveYY.ff8, user save names…), so the binding is a single-select wildcard, like
        # Joker's *.sp2. Save writes straight back to the loaded file (a .bak backup is made first
        # by HyneManager). It is the only editor of .ff8 saves, so nothing else shares this key.
        self.ff8_binding = FileBinding("save file (.ff8)", file_registry, load_callback=self.load_file,
                                       save_callback=self.save_file, file_filter="*.ff8")
        # kernel.bin, complementary: the only source of the ability and weapon names.
        self.kernel_names = KernelNameSource(self.game_data, file_registry)
        self.kernel_names.changed.connect(self._on_kernel_names_changed)
        self.kernel_notice = KernelNameSource.make_notice("ability and weapon")
        # ...and of each GF's learnable-ability list, which the AP slots count toward
        self.gf_slots = None
        self.kernel_names.binding.file_opened.connect(self._load_kernel_data)
        self.kernel_names.binding.file_closed.connect(self._clear_kernel_data)
        # What a mod changes in the lists of the savemap tabs, each optional and vanilla without it
        self.draw_binding = FileBinding("draw_data.csv", file_registry, load_callback=self._load_draw_data,
                                        file_filter="*.csv", read_only=True)
        self.draw_binding.file_closed.connect(lambda _path: self.draw_points_page.set_magic_ids(None))
        self.shop_binding = FileBinding("shop.bin", file_registry, load_callback=self._load_shop_file, read_only=True)
        self.shop_binding.file_closed.connect(lambda _path: self.shops_page.set_file_shops(None))
        self.scene_binding = FileBinding("scene.out", file_registry, load_callback=self._load_scene_file, read_only=True)
        self.scene_binding.file_closed.connect(self._clear_scene_file)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_gf_tab(), "G-Forces")
        self.tabs.addTab(self._build_character_tab(), "Characters")
        self.tabs.addTab(self._build_config_tab(), "Config")
        self.tabs.addTab(self._build_misc_tab(), "Misc")
        self.tabs.addTab(self._build_items_tab(), "Items")
        self.tabs.addTab(self._build_triple_triad_tab(), "Triple Triad")
        self.progress_page = ProgressPage(self)
        self.party_page = PartyPage(self)
        self.battle_page = BattlePage(self)
        self.shops_page = ShopsPage(self)
        self.draw_points_page = DrawPointsPage(self)
        self.world_map_page = WorldMapPage(self)
        self.chocobo_page = ChocoboPage(self)
        self.load_screen_page = LoadScreenPage(self)
        self.field_variables_page = FieldVariablesPage(self)
        self.tabs.addTab(self.progress_page, "Progress")
        self.tabs.addTab(self.party_page, "Party")
        self.tabs.addTab(self.battle_page, "Battle")
        self.tabs.addTab(self.shops_page, "Shops")
        self.tabs.addTab(self.draw_points_page, "Draw points")
        self.tabs.addTab(self.world_map_page, "World map")
        self.tabs.addTab(self.chocobo_page, "Chocobo World")
        self.tabs.addTab(self.load_screen_page, "Load screen")
        self.tabs.addTab(self.field_variables_page, "Variables")
        self.save_pages = [self.items_extras_page, self.progress_page, self.party_page, self.battle_page, self.shops_page,
                           self.draw_points_page, self.world_map_page, self.chocobo_page, self.load_screen_page,
                           self.field_variables_page]
        self.tabs.setTabToolTip(0, "The 16 Guardian Forces: stats, learned abilities and AP")
        self.tabs.setTabToolTip(1, "The 8 playable characters: stats, magic, junctions and abilities")
        self.tabs.setTabToolTip(2, "Saved game configuration (speeds, controls, map seal)")
        self.tabs.setTabToolTip(3, "Party, gil, weapons, Griever name and limit-break unlocks")
        self.tabs.setTabToolTip(4, "Current inventory (item id + quantity per slot)")
        self.tabs.setTabToolTip(5, "Cards owned, rare card locations, region rules, Queen of Cards and CC Group")
        self.tabs.setTabToolTip(6, "Story moment, disc, play time, steps, SeeD and tutorial entries")
        self.tabs.setTabToolTip(7, "The party walking on the field and where it stands")
        self.tabs.setTabToolTip(8, "Battle counts and flags, summon flags, magic drawn and enemies scanned once")
        self.tabs.setTabToolTip(9, "Shops visited and their items")
        self.tabs.setTabToolTip(10, "State of the 256 draw points")
        self.tabs.setTabToolTip(11, "Steps, rental car, displayed map, vehicles, PuPu and Obel Lake quests")
        self.tabs.setTabToolTip(12, "Boko's level, HP, weapon, items and quest progress")
        self.tabs.setTabToolTip(13, "What the load screen shows for this save")
        self.tabs.setTabToolTip(14, "The field variables the game and Cronos really use, named and editable")
        self.tabs.setEnabled(False)

        main_layout = QVBoxLayout()
        main_layout.addWidget(self.kernel_notice)
        main_layout.addWidget(self.tabs)
        self.setLayout(main_layout)

        self._on_kernel_names_changed()  # no kernel.bin yet: ids only, greyed out
        self.ff8_binding.load_opened_file()  # pick up a .ff8 another instance already opened
        self.kernel_names.binding.load_opened_file()  # ...or a kernel.bin
        for binding in (self.draw_binding, self.shop_binding, self.scene_binding):
            binding.load_opened_file()

    def file_bindings(self):
        """The files the shared header toolbar drives for this tool: the .ff8 save; kernel.bin as a
        complementary file naming the abilities, weapons and magic; and what a mod changes in the
        lists of the savemap tabs."""
        return [self.ff8_binding, self.kernel_names.binding, self.draw_binding, self.shop_binding, self.scene_binding]

    # ── A mod's files ────────────────────────────────────────────────────

    def magic_label(self, magic_id, unknown=""):
        """A magic's name: the open kernel.bin's, else the built-in list's."""
        return (self.kernel_names.magic_name(magic_id) or self._magic_names.get(magic_id)
                or unknown or f"Magic {magic_id}")

    def _relabel_magic(self):
        kernel_magic = self.kernel_names.magic
        added = [magic_id for magic_id, name in kernel_magic.items() if name and magic_id not in self._magic_names]
        gone = self._added_magic_ids - set(added)
        self._added_magic_ids = set(added)
        for combo in [*self.char_magic_combos, *self.char_junction_combos.values()]:
            with QSignalBlocker(combo):
                for magic_id in gone:   # a save's value stays, by its id
                    index = combo.findData(magic_id)
                    if index >= 0 and index != combo.currentIndex():
                        combo.removeItem(index)
                    elif index >= 0:
                        combo.setItemText(index, f"{magic_id}: (unknown)")
                for magic_id in added:   # spells FFNx's AddMoreMagic lets a kernel.bin add
                    if combo.findData(magic_id) < 0:
                        combo.addItem("", magic_id)
                for index in range(combo.count()):
                    magic_id = combo.itemData(index)
                    if magic_id in self._magic_names or magic_id in kernel_magic:
                        combo.setItemText(index, f"{magic_id}: {self.magic_label(magic_id)}")
        self.battle_page.relabel_magic()
        self.draw_points_page.relabel_magic()
        if self.manager.battle:
            self.battle_page.reload()

    def _load_draw_data(self, path):
        """Cid's draw_data.csv: Draw ID 1-256 with its Magic ID."""
        try:
            with open(path, encoding="utf-8-sig", newline="") as csv_file:
                rows = list(csv.DictReader(csv_file, delimiter="|"))
            magic_ids = list(self.hyne_data["draw_point_magic"])
            for row in rows:
                magic_ids[int(row["Draw ID"]) - 1] = int(row["Magic ID"])
        except (OSError, KeyError, ValueError, IndexError, TypeError) as error:
            QMessageBox.warning(self, "Hyne", f"Not a draw_data.csv made by the Cid tool:\n{path}\n{error}")
            return
        self.draw_points_page.set_magic_ids(magic_ids, os.path.basename(path))

    def _load_shop_file(self, path):
        try:
            with open(path, "rb") as shop_file:
                shops = read_shop_file(shop_file.read())
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Hyne", f"Not a usable shop.bin:\n{path}\n{error}")
            return
        self.shops_page.set_file_shops(shops)

    def _load_scene_file(self, path):
        try:
            with open(path, "rb") as scene_file:
                self.manager.scene_uses_extra_monsters = scene_uses_extra_monsters(scene_file.read())
        except OSError as error:
            QMessageBox.warning(self, "Hyne", f"Could not read scene.out:\n{path}\n{error}")
            return
        self._refresh_scan_place()

    def _clear_scene_file(self, _path=None):
        self.manager.scene_uses_extra_monsters = None
        self._refresh_scan_place()

    def _refresh_scan_place(self):
        if self.manager.battle:
            self.manager.detect_scan_moved()
            self.battle_page.reload()

    def _location_label(self, location):
        """A rare card location: what the game makes of it, then who has that Deck ID - the card players
        of the field folders when they are open, else the place myst6re's Hyne lists for vanilla."""
        label = cardlocation.location_label(location, [card["name"] for card in self._card_info])
        users = self.deck_users.get(location)
        if users:
            more = f" +{len(users) - 1}" if len(users) > 1 else ""
            return f"{location}: {label} - {users[0]}{more}"
        if self.deck_users and location != cardlocation.LOCATION_PLAYER:
            return f"{location}: {label}"
        place = self.field_names.get(self.hyne_data["card_locations"][location], "???")
        return f"{location}: {label}" + ("" if place == "???" else f" - {place}")

    def _relabel_locations(self):
        for row in range(self.tt_location_model.rowCount()):
            item = self.tt_location_model.item(row)
            item.setText(self._location_label(item.data(Qt.ItemDataRole.UserRole)))

    def set_deck_users(self, users):
        """{Deck ID: ["<map> <entity>", ...]} from field folders; {} for the vanilla places."""
        self.deck_users = users
        self._relabel_locations()
        self.tt_deck_folder_label.setText(f"{len(users)} Deck IDs named from field folders" if users
                                          else "Places are the vanilla game's")
        self.tt_deck_clear_button.setVisible(bool(users))

    def _pick_deck_folders(self):
        """The whole game's field folder, then optionally a mod's on top (Cronos's FieldRework\\field), to
        name who holds each Deck ID. Remembered with the CC Group tool's, which opens the same two."""
        registry = self.file_registry
        check = pick_field_folder(self, "Hyne", "The whole game's 'field' folder holding mapdata",
                                  registry.last_folder(CCGroupWidget.REFERENCE_FOLDER_KEY), complete=True,
                                  remember=lambda folder: registry.remember_folder(CCGroupWidget.REFERENCE_FOLDER_KEY, folder))
        if check is None:
            return
        modified = ""
        answer = QMessageBox.question(self, "Hyne", "Does a mod change the field scripts? Pick its 'field' folder next.")
        if answer == QMessageBox.StandardButton.Yes:
            mod_check = pick_field_folder(self, "Hyne", "The mod's 'field' folder",
                                          registry.last_folder(CCGroupWidget.EDITED_FOLDER_KEY),
                                          remember=lambda folder: registry.remember_folder(CCGroupWidget.EDITED_FOLDER_KEY, folder))
            if mod_check is None:
                return
            modified = mod_check.root
        with busy_cursor():
            self.set_deck_users(self.read_deck_users(check.root, modified))

    @staticmethod
    def read_deck_users(vanilla_folder, modified_folder=""):
        """{Deck ID: card players with it} of field folders, a mod's maps read over the game's."""
        folders = CardGameFolderManager()
        folders.load_folder(vanilla_folder, modified_folder)
        deck_ids = range(256)
        users = {deck_id: folders.deck_id_users(deck_id) for deck_id in deck_ids}
        return {deck_id: names for deck_id, names in users.items() if names}

    # ── Names from kernel.bin ────────────────────────────────────────────

    def _ability_choices(self, allowed):
        """The abilities a combo offers: 'None' plus those in `allowed` (every one when None),
        named by the open kernel.bin - an empty list without one."""
        entries = self.kernel_names.ability_entries()
        if not entries:
            return []
        return [entries[0]] + [e for e in entries[1:] if allowed is None or e["value"] in allowed]

    def _fill_ability_combo(self, combo, value, allowed):
        """Fill an ability combo and select `value`. Without a kernel.bin there is no name to
        offer: only the value itself, greyed out - it is never changed."""
        choices = self._ability_choices(allowed)
        with QSignalBlocker(combo):
            combo.clear()
            for entry in choices:
                combo.addItem(f"{entry['value']}: {entry['name']}", entry["value"])
            if not choices:
                combo.addItem(f"{value}: open kernel.bin to name it", value)
            self._select_combo(combo, value)
        combo.setEnabled(bool(choices))

    def _on_kernel_names_changed(self):
        """A kernel.bin was opened or removed: re-label the abilities and weapons. The values in
        the file (and unsaved edits) are untouched - only the names change."""
        names = self.kernel_names
        self.kernel_notice.setVisible(not (names.abilities and names.weapons))
        self.manager.set_kernel_extensions(
            items=bool(names.items) and max(names.items) != FIRST_ADDED_ITEM - 1,
            abilities=kernel_widens_abilities(names.ability_groups),
            magic=any(magic_id >= EXTENDED_MAGIC_FIRST for magic_id in names.magic))
        commands = names.ability_group_ids(*COMMAND_ABILITY_GROUPS)
        equipped = names.ability_group_ids(*EQUIPPED_ABILITY_GROUPS)
        for combo, allowed in ([(self.gf_learning_ability_combo, None)]
                               + [(c, commands) for c in self.char_active_combos]
                               + [(c, equipped) for c in self.char_passive_combos]):
            current = combo.currentData()
            self._fill_ability_combo(combo, 0 if current is None else current, allowed)
        for ability_id, check in self.gf_ability_checks.items():
            check.setText(names.ability_name(ability_id) or f"Ability {ability_id}")
            check.setEnabled(bool(names.abilities))
        self._show_defined_abilities()
        for bit, check in self.misc_weapon_checks:
            name = names.weapon_name(bit)
            check.setText(f"{name} ({self._weapon_characters.get(bit, '?')})" if name
                          else f"Weapon {bit}")
            check.setEnabled(bool(names.weapons))
        if self.manager.item_entries:
            self._reload_items()   # the item names (and ids 199-255) come from it too
            self.shops_page.reload()
            self.items_extras_page.reload()
        self._update_ap_slots()
        if self._selected_gf():
            self._fill_learning_combo(self._selected_gf())
        self._relabel_magic()

    # ── GF ability lists from kernel.bin ─────────────────────────────────

    def _load_kernel_data(self, kernel_path):
        try:
            self.gf_slots = gf_ability_slots(load_kernel(self.game_data, kernel_path))
        except Exception as error:  # noqa: BLE001 - a bad kernel.bin just gives no slots
            print(f"[Hyne] could not read the GF abilities of {kernel_path}: {error}")
            self.gf_slots = None
        self._update_ap_slots()
        if self._selected_gf():
            self._fill_learning_combo(self._selected_gf())

    def _clear_kernel_data(self, _path=None):
        self.gf_slots = None
        self._update_ap_slots()
        if self._selected_gf():
            self._fill_learning_combo(self._selected_gf())

    def _fill_learning_combo(self, gf):
        """The Learning choice. With a kernel.bin open: None and the GF's own 21 abilities, each marked
        when the GF cannot earn AP toward it (GF_AddApToLearningAbility only credits an ability of
        the GF's list, and the battle results only one it can learn now). Without one: every ability."""
        slots = (self.gf_slots or {}).get("slots", [])
        if not slots or gf.gf_id >= len(slots):
            self._fill_ability_combo(self.gf_learning_ability_combo, gf.learning_ability, None)
            return
        names = self.kernel_names
        combo = self.gf_learning_ability_combo
        with QSignalBlocker(combo):
            combo.clear()
            combo.addItem("0: None", 0)
            for slot, entry in enumerate(slots[gf.gf_id], start=1):
                if entry.ability == 0 or combo.findData(entry.ability) >= 0:
                    continue
                name = names.ability_name(entry.ability) or f"Ability {entry.ability}"
                if gf.has_ability(entry.ability):
                    name += " (learned)"
                elif gf.is_forgotten(slot):
                    name += " (forgotten)"
                combo.addItem(f"{entry.ability}: {name}", entry.ability)
            if combo.findData(gf.learning_ability) < 0:  # never lose the file's value
                combo.addItem(f"{gf.learning_ability}: not in this GF's list - earns no AP",
                              gf.learning_ability)
            combo.setCurrentIndex(combo.findData(gf.learning_ability))
        combo.setEnabled(True)

    def _update_ap_slots(self):
        """Name each AP slot after the ability of the selected GF's kernel.bin list it counts toward,
        with that ability's AP cost and when it unlocks."""
        gf = self._selected_gf()
        slots = (self.gf_slots or {}).get("slots", [])
        costs = (self.gf_slots or {}).get("ap", [])
        gf_list = slots[gf.gf_id] if gf and gf.gf_id < len(slots) else None
        names = self.kernel_names

        def ability_name(ability_id):
            return names.ability_name(ability_id) or f"Ability {ability_id}"

        for index, (label, info) in enumerate(zip(self.gf_ap_labels, self.gf_ap_infos)):
            slot = index + 1
            if index >= ABILITY_LIST_COUNT:
                label.setText(f"Slot {slot}: -")
                info.setText(f"unused: a GF's ability list has {ABILITY_LIST_COUNT} entries, no code reads this one")
                continue
            if gf_list is None:
                label.setText(f"Slot {slot}:")
                info.setText("")
                continue
            entry = gf_list[index]
            if entry.ability == 0:
                label.setText(f"Slot {slot}: -")
                info.setText("no ability in this slot of the GF's kernel.bin list")
                continue
            label.setText(f"Slot {slot}: {ability_name(entry.ability)}")
            parts = [f"/ {costs[entry.ability]} AP" if entry.ability < len(costs) else "/ ? AP"]
            if entry.unlock_level is not None:
                parts.append(f"from GF level {entry.unlock_level}" if entry.unlock_level > 1 else "from the start")
            elif entry.unlock_after_slot is not None:
                parts.append(f"after {ability_name(gf_list[entry.unlock_after_slot].ability)}")
            if gf.has_ability(entry.ability):
                parts.append("learned")
            info.setText(" - ".join(parts))

    def _item_choices(self):
        """The items an inventory slot offers: the game's 0-198, named by the open kernel.bin when
        there is one, then the items it adds with FFNx's AddMoreItems (199-255) - which only a
        kernel.bin names, so without one they are not offered (a slot already holding one keeps
        it, shown by its id)."""
        return self.kernel_names.item_entries()

    # ── Small widget helpers ─────────────────────────────────────────────

    @staticmethod
    def _compact_spin(spin):
        """Cap a spinbox width to just fit its largest value, so it doesn't stretch."""
        digits = max(len(str(spin.maximum())), 2)
        spin.setMaximumWidth(spin.fontMetrics().horizontalAdvance("9" * digits) + 36)

    @staticmethod
    def _compact_line(line_edit, chars=14):
        line_edit.setMaximumWidth(line_edit.fontMetrics().horizontalAdvance("W" * chars))

    def _spinbox(self, minimum, maximum, slot=None, tooltip="", step=1):
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        self._compact_spin(spin)
        if tooltip:
            spin.setToolTip(tooltip)
        if slot:
            spin.valueChanged.connect(slot)
        return spin

    def _u32_spinbox(self, slot=None, tooltip=""):
        """A spin box for a 32-bit unsigned field of the save (see U32SpinBox)."""
        spin = U32SpinBox()
        self._compact_spin(spin)
        if tooltip:
            spin.setToolTip(tooltip)
        if slot:
            spin.valueChanged.connect(slot)
        return spin

    @staticmethod
    def _set_spin_value(spin, value):
        """Show `value` in `spin`, kept inside what the widget can hold.

        Every value here comes out of a save file, and a save is not always what this editor
        expects: a hacked one, a slot from another game, a field this project has not decoded
        right. Out of range, Qt's own setValue raises - inside the load slot, where an exception
        does not surface as an error message but kills the process - so the clamp happens here.
        A clamped field is visibly at its limit and the user can see something is off; the rest
        of the save still loads and stays editable.
        """
        value = int(value)
        spin.setValue(max(int(spin.minimum()), min(int(spin.maximum()), value)))

    def _enum_combo(self, entries, slot=None, tooltip="", adjust_size=False):
        combo = QComboBox()
        for entry in entries:
            combo.addItem(f"{entry['value']}: {entry['name']}", entry["value"])
        # Size to the widest entry and don't stretch to fill the row/cell.
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        combo.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        if tooltip:
            combo.setToolTip(tooltip)
        if slot:
            combo.currentIndexChanged.connect(slot)
        return combo

    @staticmethod
    def _configure_list_table(table):
        """Size an (item/magic, quantity) table to its content so the quantity column sits
        right next to the name column instead of the name stretching across the pane."""
        header = table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)

    @staticmethod
    def _select_combo(combo, value):
        index = combo.findData(value)
        if index < 0:  # value outside the known list — keep it so we never lose data
            combo.addItem(f"{value}: (unknown)", value)
            index = combo.findData(value)
        combo.setCurrentIndex(index)

    def _readonly_spin(self, tooltip, maximum=0xFF):
        """A greyed, non-editable spinbox for showing a byte the tool won't let you change.
        Kept enabled (read-only) so the hover tooltip still works."""
        spin = QSpinBox()
        spin.setRange(0, maximum)
        spin.setReadOnly(True)
        spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._compact_spin(spin)
        spin.setToolTip(tooltip)
        spin.setStyleSheet("color: gray;")
        return spin

    @staticmethod
    def _grey_label(text, tooltip):
        label = QLabel(text)
        label.setToolTip(tooltip)
        label.setStyleSheet("color: gray;")
        return label

    def _reserved_group(self, rows):
        """Build a 'Reserved (read-only)' group from rows of (label, offset_tooltip). Returns
        (group, [(spin, ...)]) so the caller can populate values on reload."""
        form = QFormLayout()
        spins = []
        for label_text in rows:
            spin = self._readonly_spin(RESERVED_TOOLTIP)
            form.addRow(self._grey_label(label_text, RESERVED_TOOLTIP), spin)
            spins.append(spin)
        group = QGroupBox("Reserved (read-only)")
        group.setToolTip("Bytes with no game meaning — shown for completeness, not editable")
        group.setLayout(form)
        return group, spins

    def _left_column_scroll(self, group_widgets):
        """Stack groups vertically, hugged to the left with a stretch filling the right, inside
        a scroll area — so the content stays at its natural width instead of spreading."""
        column = QVBoxLayout()
        for widget in group_widgets:
            column.addWidget(widget)
        column.addStretch(1)
        column_widget = QWidget()
        column_widget.setLayout(column)
        column_widget.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)

        outer = QHBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(column_widget)
        outer.addStretch(1)
        container = QWidget()
        container.setLayout(outer)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(container)
        return scroll

    def _bitfield_group(self, title, tooltip, entries, changed_slot, columns=2):
        """Build a QGroupBox of checkboxes over a bitfield. Returns (group, [(bit, checkbox)])."""
        group = QGroupBox(title)
        group.setToolTip(tooltip)
        grid = QGridLayout()
        checks = []
        for i, entry in enumerate(entries):
            bit = entry["bit"]
            check = QCheckBox(entry["name"])
            check.setToolTip(f"Bit {bit}")
            check.stateChanged.connect(changed_slot)
            checks.append((bit, check))
            grid.addWidget(check, i // columns, i % columns)
        group.setLayout(grid)
        return group, checks

    # ── File operations ────────────────────────────────────────────────

    def load_file(self, file_name):
        try:
            self.manager.load_file(file_name)
        except ValueError as error:
            QMessageBox.critical(self, "Hyne", f"Not a valid .ff8 save file:\n{error}")
            return
        self.tabs.setEnabled(True)

        with QSignalBlocker(self.gf_list):
            self.gf_list.clear()
            self.gf_list.addItems([gf.gf_name for gf in self.manager.gf_entries])
        self.gf_list.setCurrentRow(0)

        with QSignalBlocker(self.character_list):
            self.character_list.clear()
            self.character_list.addItems([c.name for c in self.manager.character_entries])
        self.character_list.setCurrentRow(0)

        self._reload_config()
        self._reload_misc()
        self._reload_items()
        self._reload_triple_triad()
        self._reload_names()
        for page in self.save_pages:
            page.reload()

    def save_file(self):
        if self.manager.file_path:
            self.manager.save_file()
            self.load_screen_page.reload()   # saving updates what the load screen shows

    # ── GF tab ───────────────────────────────────────────────────────────

    def _build_gf_tab(self):
        self.gf_list = QListWidget()
        self.gf_list.setFixedWidth(160)
        self.gf_list.currentRowChanged.connect(self._reload_gf)

        self.gf_name_edit = QLineEdit()
        self.gf_name_edit.setToolTip("GF name shown in menus (FF8 text, max 12 bytes)")
        self._compact_line(self.gf_name_edit)
        self.gf_name_edit.editingFinished.connect(self._on_gf_name_changed)

        self.gf_exp_spin = self._u32_spinbox(self._on_gf_data_changed, "Total experience earned by this GF")
        self.gf_hp_spin = self._spinbox(0, 0xFFFF, self._on_gf_data_changed, "Current HP")
        self.gf_kills_spin = self._spinbox(0, 0xFFFF, self._on_gf_data_changed, "Number of enemies this GF has killed")
        self.gf_kos_spin = self._spinbox(0, 0xFFFF, self._on_gf_data_changed, "Number of times this GF was KO'd")
        self.gf_learning_ability_combo = self._enum_combo(
            [], self._on_gf_data_changed,
            "Ability the GF is currently set to learn — earned AP is applied to it. This is an "
            "ability id, not an AP amount; the AP invested per ability is on the AP tab.")
        self.gf_available_check = QCheckBox("Available")
        self.gf_available_check.setToolTip("GF has been obtained — set once the GF is junctioned/acquired at least once")
        self.gf_available_check.stateChanged.connect(self._on_gf_data_changed)

        status_form = QFormLayout()
        status_form.addRow("Name:", self.gf_name_edit)
        status_form.addRow("EXP:", self.gf_exp_spin)
        status_form.addRow("Current HP:", self.gf_hp_spin)
        status_form.addRow("Kills:", self.gf_kills_spin)
        status_form.addRow("KOs:", self.gf_kos_spin)
        status_form.addRow("Learning:", self.gf_learning_ability_combo)
        status_form.addRow(self.gf_available_check)
        status_group = QGroupBox("Status")
        status_group.setToolTip("Core stats and state of the selected GF")
        status_group.setLayout(status_form)

        gf_reserved_group, gf_reserved_spins = self._reserved_group(["Unused (0x10):"])
        self.gf_unused_spin = gf_reserved_spins[0]
        status_tab_container = QWidget()
        status_tab_layout = QVBoxLayout()
        status_tab_layout.setContentsMargins(0, 0, 0, 0)
        status_tab_layout.addWidget(status_group)
        status_tab_layout.addWidget(gf_reserved_group)
        status_tab_layout.addStretch(1)
        status_tab_container.setLayout(status_tab_layout)

        # Learned abilities: one checkbox per junctionable_ability id - ids 0-127 in the GF's
        # 128-bit "complete abilities" field, 128-254 in FFNx AddMoreAbility's save block.
        # Value 0 (None) is skipped.
        self.gf_ability_checks = {}
        ability_grid = QGridLayout()
        columns = 4
        for i, ability_id in enumerate(range(1, SAVE_ABILITY_IDS)):
            check = QCheckBox(f"Ability {ability_id}")  # named once a kernel.bin is open
            check.setToolTip(f"Ability id {ability_id} learned")
            check.stateChanged.connect(self._on_gf_ability_changed)
            self.gf_ability_checks[ability_id] = check
            ability_grid.addWidget(check, i // columns, i % columns)
        ability_container = QWidget()
        ability_container.setLayout(ability_grid)
        ability_scroll = QScrollArea()
        ability_scroll.setWidgetResizable(True)
        ability_scroll.setWidget(ability_container)

        # AP invested per ability slot. The slots are NOT global ability ids: slot N is the
        # N-th entry in *this GF's* learnable-ability list, whose abilities, AP costs and unlocks
        # are in kernel.bin (Junctionable GFs section), not in the savemap: the slots are named
        # from an opened kernel.bin (_update_ap_slots), numbered without one.
        self.gf_ap_spins = []
        self.gf_ap_labels = []
        self.gf_ap_infos = []
        self.gf_forgotten_checks = []
        ap_form = QFormLayout()
        ap_note = QLabel("Slot N = AP invested in this GF's N-th learnable ability, named from kernel.bin\n"
                         "(Junctionable GFs section) with the AP it costs and when it unlocks.")
        ap_note.setWordWrap(True)
        ap_form.addRow(ap_note)
        for slot in range(1, 23):
            spin = self._spinbox(0, 0xFF, self._on_gf_ap_changed,
                                "AP invested in this GF's learnable-ability slot "
                                f"{slot} (its ability is defined by the GF's kernel.bin ability list)")
            label = QLabel(f"Slot {slot}:")
            info = QLabel()
            info.setStyleSheet("color: gray;")
            row = QHBoxLayout()
            row.addWidget(spin)
            if slot <= ABILITY_LIST_COUNT:
                forgotten = QCheckBox("Forgotten")
                forgotten.setToolTip("The GF forgot this ability (an Amnesia Greens): it leaves the list of what the GF can learn.")
                forgotten.toggled.connect(lambda checked, s=slot: self._on_gf_forgotten_changed(s, checked))
                self.gf_forgotten_checks.append(forgotten)
                row.addWidget(forgotten)
            row.addWidget(info)
            row.addStretch(1)
            self.gf_ap_spins.append(spin)
            self.gf_ap_labels.append(label)
            self.gf_ap_infos.append(info)
            ap_form.addRow(label, row)
        ap_container = QWidget()
        ap_container.setLayout(ap_form)
        ap_scroll = QScrollArea()
        ap_scroll.setWidgetResizable(True)
        ap_scroll.setWidget(ap_container)

        sub_tabs = QTabWidget()
        sub_tabs.addTab(status_tab_container, "Status")
        sub_tabs.addTab(ability_scroll, "Learned Abilities")
        sub_tabs.addTab(ap_scroll, "AP")
        sub_tabs.setTabToolTip(0, "Name, EXP, HP, kills and availability of the GF")
        sub_tabs.setTabToolTip(1, "Abilities this GF has finished learning (ids 128+ are kept in FFNx AddMoreAbility's save block)")
        sub_tabs.setTabToolTip(2, "AP invested toward each of the GF's learnable abilities")

        layout = QHBoxLayout()
        layout.addWidget(self.gf_list)
        layout.addWidget(sub_tabs, 1)
        container = QWidget()
        container.setLayout(layout)
        return container

    def _show_defined_abilities(self):
        """Show a Learned checkbox per ability id the kernel.bin defines (the vanilla 115 without
        one), plus any id the selected GF has learned beyond that."""
        count = len(self.kernel_names.abilities) or VANILLA_ABILITY_COUNT
        gf = self._selected_gf()
        for ability_id, check in self.gf_ability_checks.items():
            usable = ability_id < LEARNED_ABILITY_BITS or self.manager.abilities_extended
            check.setVisible(usable and (ability_id < count or bool(gf and gf.has_ability(ability_id))))

    def _selected_gf(self):
        index = self.gf_list.currentRow()
        if self.manager.gf_entries and 0 <= index < len(self.manager.gf_entries):
            return self.manager.gf_entries[index]
        return None

    def _reload_gf(self):
        gf = self._selected_gf()
        if not gf:
            return
        with QSignalBlocker(self.gf_name_edit):
            self.gf_name_edit.setText(gf.name)
        for spin, value in [
            (self.gf_exp_spin, gf.exp), (self.gf_hp_spin, gf.current_hp),
            (self.gf_kills_spin, gf.kills), (self.gf_kos_spin, gf.kos),
        ]:
            with QSignalBlocker(spin):
                self._set_spin_value(spin, value)
        self._fill_learning_combo(gf)
        self._set_spin_value(self.gf_unused_spin, gf.unknown1)
        with QSignalBlocker(self.gf_available_check):
            self.gf_available_check.setChecked(gf.available)
        for ability_id, check in self.gf_ability_checks.items():
            with QSignalBlocker(check):
                check.setChecked(gf.has_ability(ability_id))
        self._show_defined_abilities()
        for slot, spin in enumerate(self.gf_ap_spins, start=1):
            with QSignalBlocker(spin):
                self._set_spin_value(spin, gf.get_ap_ability(slot))
        for slot, check in enumerate(self.gf_forgotten_checks, start=1):
            with QSignalBlocker(check):
                check.setChecked(gf.is_forgotten(slot))
        self._update_ap_slots()

    def _on_gf_name_changed(self):
        gf = self._selected_gf()
        if gf:
            gf.name = self.gf_name_edit.text()

    def _on_gf_data_changed(self):
        gf = self._selected_gf()
        if not gf:
            return
        gf.exp = self.gf_exp_spin.value()
        gf.current_hp = self.gf_hp_spin.value()
        gf.kills = self.gf_kills_spin.value()
        gf.kos = self.gf_kos_spin.value()
        gf.learning_ability = self.gf_learning_ability_combo.currentData()
        gf.available = self.gf_available_check.isChecked()

    def _on_gf_ability_changed(self):
        gf = self._selected_gf()
        if not gf:
            return
        for ability_id, check in self.gf_ability_checks.items():
            gf.set_ability(ability_id, check.isChecked())
        self._update_ap_slots()  # the "learned" marks of the AP tab
        self._fill_learning_combo(gf)

    def _on_gf_forgotten_changed(self, slot, checked):
        gf = self._selected_gf()
        if gf:
            gf.set_forgotten(slot, checked)
            self._fill_learning_combo(gf)

    def _on_gf_ap_changed(self):
        gf = self._selected_gf()
        if not gf:
            return
        for slot, spin in enumerate(self.gf_ap_spins, start=1):
            gf.set_ap_ability(slot, spin.value())

    # ── Character tab ────────────────────────────────────────────────────

    def _build_character_tab(self):
        self.character_list = QListWidget()
        self.character_list.setFixedWidth(160)
        self.character_list.currentRowChanged.connect(self._reload_character)

        # Status
        self.char_hp_spin = self._spinbox(0, 0xFFFF, self._on_character_status_changed, "Current HP")
        self.char_hp_bonus_spin = self._spinbox(0, 0xFFFF, self._on_character_status_changed,
                                               "Max-HP bonus from HP-Bonus ability (added to base max HP)")
        self.char_exp_spin = self._u32_spinbox(self._on_character_status_changed, "Total experience")
        self.char_model_spin = self._spinbox(0, 0xFF, self._on_character_status_changed, "Field/battle model id")
        self.char_weapon_spin = self._spinbox(0, 0xFF, self._on_character_status_changed, "Equipped weapon id")
        self.char_kills_spin = self._spinbox(0, 0xFFFF, self._on_character_status_changed, "Number of enemies killed")
        self.char_kos_spin = self._spinbox(0, 0xFFFF, self._on_character_status_changed, "Number of times KO'd")
        self.char_alt_model_check = QCheckBox("Alternative Model (SeeD, Galbadian)")
        self.char_alt_model_check.setToolTip("Use the alternative outfit model (e.g. SeeD uniform, Galbadian soldier)")
        self.char_alt_model_check.stateChanged.connect(self._on_character_status_changed)
        self.char_exist_check = QCheckBox("Exists (recruited)")
        self.char_exist_check.setToolTip("Character has joined the party at least once — available in menus/party select")
        self.char_exist_check.stateChanged.connect(self._on_character_status_changed)
        self.char_exist_bit_checks = []  # the bits past "in the roster"
        for mask, name in CharacterEntry.EXIST_BITS[1:]:
            check = QCheckBox(name)
            check.setToolTip(f"Mask 0x{mask:02X} of the character's exist flags. HOLD = set by the field scripts.")
            check.toggled.connect(lambda checked, m=mask: self._on_character_exist_bit_changed(m, checked))
            self.char_exist_bit_checks.append((mask, check))

        self.char_str_spin = self._spinbox(0, 0xFF, self._on_character_status_changed, "Base Strength")
        self.char_vit_spin = self._spinbox(0, 0xFF, self._on_character_status_changed, "Base Vitality")
        self.char_mag_spin = self._spinbox(0, 0xFF, self._on_character_status_changed, "Base Magic")
        self.char_spr_spin = self._spinbox(0, 0xFF, self._on_character_status_changed, "Base Spirit")
        self.char_spd_spin = self._spinbox(0, 0xFF, self._on_character_status_changed, "Base Speed")
        self.char_luck_spin = self._spinbox(0, 0xFF, self._on_character_status_changed, "Base Luck")

        status_form = QFormLayout()
        status_form.addRow("Current HP:", self.char_hp_spin)
        status_form.addRow("Max HP bonus:", self.char_hp_bonus_spin)
        status_form.addRow("EXP:", self.char_exp_spin)
        status_form.addRow("Model:", self.char_model_spin)
        status_form.addRow("Weapon:", self.char_weapon_spin)
        status_form.addRow("Kills:", self.char_kills_spin)
        status_form.addRow("KOs:", self.char_kos_spin)
        status_form.addRow(self.char_alt_model_check)
        status_form.addRow(self.char_exist_check)
        for _mask, check in self.char_exist_bit_checks:
            status_form.addRow(check)
        stats_form = QFormLayout()
        stats_form.addRow("Str:", self.char_str_spin)
        stats_form.addRow("Vit:", self.char_vit_spin)
        stats_form.addRow("Mag:", self.char_mag_spin)
        stats_form.addRow("Spr:", self.char_spr_spin)
        stats_form.addRow("Spd:", self.char_spd_spin)
        stats_form.addRow("Luck:", self.char_luck_spin)
        status_group = QGroupBox("Status")
        status_group.setToolTip("HP, EXP, model/weapon and base stats of the selected character")
        status_layout = QHBoxLayout()
        status_layout.addLayout(status_form)
        status_layout.addLayout(stats_form)
        status_group.setLayout(status_layout)

        # Persistent status flags: only bits 0-6 of the 16-bit status_1 field are real,
        # persistable statuses (bit 7 padding; bits 8-9 are HP-derived synthetic flags the
        # game recomputes; 10-15 unused).
        self.char_status_checks = {}
        status_checks_form = QGridLayout()
        persistent_statuses = [e for e in self._status_entries if e["mask"] <= 0x40]
        for i, entry in enumerate(persistent_statuses):
            check = QCheckBox(entry["name"])
            check.stateChanged.connect(self._on_character_status_flags_changed)
            bit = entry["mask"].bit_length() - 1
            self.char_status_checks[bit] = check
            status_checks_form.addWidget(check, i // 4, i % 4)
        status_checks_group = QGroupBox("Current Status")
        status_checks_group.setToolTip("Persistent statuses (status_1 bits 0-6). Higher bits are unused or "
                                       "HP-derived and are recomputed by the game.")
        status_checks_group.setLayout(status_checks_form)

        char_reserved_group, char_reserved_spins = self._reserved_group(
            ["Unused (0x5A):", "Unused (0x6F):", "Unused (0x95):"])
        self.char_unused_spins = char_reserved_spins

        status_tab_layout = QVBoxLayout()
        status_tab_layout.addWidget(status_group)
        status_tab_layout.addWidget(status_checks_group)
        status_tab_layout.addWidget(char_reserved_group)
        status_tab_layout.addStretch(1)
        status_tab = QWidget()
        status_tab.setLayout(status_tab_layout)

        # Magic
        self.char_magic_table = QTableWidget(32, 2)
        self.char_magic_table.setHorizontalHeaderLabels(["Magic", "Quantity"])
        self._configure_list_table(self.char_magic_table)
        self.char_magic_combos = []
        self.char_magic_qty_spins = []
        for row in range(32):
            combo = self._enum_combo(self._magic_entries, self._on_character_magic_changed, adjust_size=True)
            self.char_magic_table.setCellWidget(row, 0, combo)
            self.char_magic_combos.append(combo)
            qty = self._spinbox(0, 0xFF, self._on_character_magic_changed, "Amount of this spell stocked")
            self.char_magic_table.setCellWidget(row, 1, qty)
            self.char_magic_qty_spins.append(qty)

        # Command / passive abilities (4 slots each, shared FF8Abilities enum)
        self.char_active_combos = [
            self._enum_combo([], self._on_character_abilities_changed,
                             "Equipped command ability (Magic, GF, Draw, Item, Card…)")
            for _ in range(4)]
        self.char_passive_combos = [
            self._enum_combo([], self._on_character_abilities_changed,
                             "Equipped passive/junction ability (HP+20%, Str+40%…)")
            for _ in range(4)]
        abilities_form = QFormLayout()
        for i, combo in enumerate(self.char_active_combos, start=1):
            abilities_form.addRow(f"Command {i}:", combo)
        for i, combo in enumerate(self.char_passive_combos, start=1):
            abilities_form.addRow(f"Ability {i}:", combo)
        abilities_group = QGroupBox("Equipped abilities")
        abilities_group.setToolTip("The 4 equipped command abilities and 4 equipped passive abilities")
        abilities_group.setLayout(abilities_form)
        abilities_layout = QVBoxLayout()
        abilities_layout.addWidget(abilities_group)
        abilities_layout.addStretch(1)
        abilities_tab = QWidget()
        abilities_tab.setLayout(abilities_layout)

        # G-Forces (junctioned GFs + compatibility): one row per GF, junctioned is a bitmask
        self.char_gf_junction_checks = []
        self.char_gf_compat_spins = []
        compat_form = QFormLayout()
        compat_tooltip = (f"Compatibility with this GF. Game range: {GF_COMPATIBILITY_MIN} (minimum / neutral) "
                          f"to {GF_COMPATIBILITY_MAX} (maximum). Higher = summons faster.")
        for gf_id, entry in enumerate(self._gforce_entries):
            check = QCheckBox("Junctioned")
            check.setToolTip("GF junctioned to this character (any number of GFs). A GF can only be "
                             "junctioned to one character: checking it here removes it from the others.")
            check.toggled.connect(lambda checked, g=gf_id: self._on_character_gf_junction_changed(g, checked))
            self.char_gf_junction_checks.append(check)
            spin = self._spinbox(0, 0xFFFF, self._on_character_gf_changed, compat_tooltip)
            self.char_gf_compat_spins.append(spin)
            row = QHBoxLayout()
            row.addWidget(check)
            row.addWidget(spin)
            compat_form.addRow(f"{entry['name']}:", row)
        compat_container = QWidget()
        compat_container.setLayout(compat_form)
        compat_scroll = QScrollArea()
        compat_scroll.setWidgetResizable(True)
        compat_scroll.setWidget(compat_container)

        gf_layout = QVBoxLayout()
        compat_group = QGroupBox("Junction && compatibility")
        compat_group.setToolTip(f"Junctioned GFs and per-GF compatibility ({GF_COMPATIBILITY_MIN}-{GF_COMPATIBILITY_MAX}); higher summons faster")
        compat_group_layout = QVBoxLayout()
        compat_group_layout.addWidget(compat_scroll)
        compat_group.setLayout(compat_group_layout)
        gf_layout.addWidget(compat_group)
        gf_tab = QWidget()
        gf_tab.setLayout(gf_layout)

        # Junction stat assignments (each stores a magic id)
        self.char_junction_combos = {}
        junction_stats_form = QFormLayout()
        junction_tooltip = ("Magic junctioned to this stat (0 = none). The bonus = the spell's kernel "
                            "junction value for this stat, scaled by the quantity stocked.")
        for field, label in JUNCTION_FIELDS:
            combo = self._enum_combo(self._magic_entries, self._on_character_junction_changed, junction_tooltip)
            self.char_junction_combos[field] = combo
            junction_stats_form.addRow(f"{label}:", combo)
        junction_stats_container = QWidget()
        junction_stats_container.setLayout(junction_stats_form)
        junction_stats_scroll = QScrollArea()
        junction_stats_scroll.setWidgetResizable(True)
        junction_stats_scroll.setWidget(junction_stats_container)

        sub_tabs = QTabWidget()
        sub_tabs.addTab(status_tab, "Status")
        sub_tabs.addTab(self.char_magic_table, "Magic")
        sub_tabs.addTab(abilities_tab, "Abilities")
        sub_tabs.addTab(gf_tab, "G-Forces")
        sub_tabs.addTab(junction_stats_scroll, "Junction")
        sub_tabs.setTabToolTip(0, "HP, stats and current status")
        sub_tabs.setTabToolTip(1, "Stocked magic (spell + quantity, 32 slots)")
        sub_tabs.setTabToolTip(2, "Equipped command and passive abilities")
        sub_tabs.setTabToolTip(3, "Junctioned GFs and per-GF compatibility")
        sub_tabs.setTabToolTip(4, "Which magic is junctioned to each stat")

        layout = QHBoxLayout()
        layout.addWidget(self.character_list)
        layout.addWidget(sub_tabs, 1)
        container = QWidget()
        container.setLayout(layout)
        return container

    def _selected_character(self):
        index = self.character_list.currentRow()
        if self.manager.character_entries and 0 <= index < len(self.manager.character_entries):
            return self.manager.character_entries[index]
        return None

    def _reload_character(self):
        char = self._selected_character()
        if not char:
            return
        for spin, value in [
            (self.char_hp_spin, char.current_hp), (self.char_hp_bonus_spin, char.hp_bonus),
            (self.char_exp_spin, char.exp), (self.char_model_spin, char.model_id),
            (self.char_weapon_spin, char.weapon_id), (self.char_kills_spin, char.kills),
            (self.char_kos_spin, char.kos), (self.char_str_spin, char.str_stat),
            (self.char_vit_spin, char.vit), (self.char_mag_spin, char.mag),
            (self.char_spr_spin, char.spr), (self.char_spd_spin, char.spd),
            (self.char_luck_spin, char.luck),
        ]:
            with QSignalBlocker(spin):
                self._set_spin_value(spin, value)
        with QSignalBlocker(self.char_alt_model_check):
            self.char_alt_model_check.setChecked(char.alt_model)
        with QSignalBlocker(self.char_exist_check):
            self.char_exist_check.setChecked(char.exist)
        for mask, check in self.char_exist_bit_checks:
            with QSignalBlocker(check):
                check.setChecked(bool(char.exist_flags & mask))
        for spin, value in zip(self.char_unused_spins, [char.unknown2, char.unknown3, char.unknown4]):
            self._set_spin_value(spin, value)
        for bit, check in self.char_status_checks.items():
            with QSignalBlocker(check):
                check.setChecked(char.has_status(bit))

        for i, magic in enumerate(char.magics):
            with QSignalBlocker(self.char_magic_combos[i]):
                self._select_combo(self.char_magic_combos[i], magic.magic_id)
            with QSignalBlocker(self.char_magic_qty_spins[i]):
                self._set_spin_value(self.char_magic_qty_spins[i], magic.quantity)

        for slot, combo in enumerate(self.char_active_combos):
            self._fill_ability_combo(combo, char.get_active_ability(slot),
                                     self.kernel_names.ability_group_ids(*COMMAND_ABILITY_GROUPS))
        for slot, combo in enumerate(self.char_passive_combos):
            self._fill_ability_combo(combo, char.get_passive_ability(slot),
                                     self.kernel_names.ability_group_ids(*EQUIPPED_ABILITY_GROUPS))

        for gf_id, check in enumerate(self.char_gf_junction_checks):
            with QSignalBlocker(check):
                check.setChecked(char.is_gf_junctioned(gf_id))
        for gf_id, spin in enumerate(self.char_gf_compat_spins):
            with QSignalBlocker(spin):
                self._set_spin_value(spin, char.get_gf_compatibility(gf_id))

        for field, combo in self.char_junction_combos.items():
            with QSignalBlocker(combo):
                self._select_combo(combo, getattr(char, field))

    def _on_character_status_changed(self):
        char = self._selected_character()
        if not char:
            return
        char.current_hp = self.char_hp_spin.value()
        char.hp_bonus = self.char_hp_bonus_spin.value()
        char.exp = self.char_exp_spin.value()
        char.model_id = self.char_model_spin.value()
        char.weapon_id = self.char_weapon_spin.value()
        char.kills = self.char_kills_spin.value()
        char.kos = self.char_kos_spin.value()
        char.str_stat = self.char_str_spin.value()
        char.vit = self.char_vit_spin.value()
        char.mag = self.char_mag_spin.value()
        char.spr = self.char_spr_spin.value()
        char.spd = self.char_spd_spin.value()
        char.luck = self.char_luck_spin.value()
        char.alt_model = self.char_alt_model_check.isChecked()
        char.exist = self.char_exist_check.isChecked()

    def _on_character_exist_bit_changed(self, mask, checked):
        char = self._selected_character()
        if char:
            char.set_exist_flag(mask, checked)

    def _on_character_status_flags_changed(self):
        char = self._selected_character()
        if not char:
            return
        for bit, check in self.char_status_checks.items():
            char.set_status(bit, check.isChecked())

    def _on_character_magic_changed(self):
        char = self._selected_character()
        if not char:
            return
        for i, magic in enumerate(char.magics):
            magic.magic_id = self.char_magic_combos[i].currentData()
            magic.quantity = self.char_magic_qty_spins[i].value()

    def _on_character_abilities_changed(self):
        char = self._selected_character()
        if not char:
            return
        for slot, combo in enumerate(self.char_active_combos):
            char.set_active_ability(slot, combo.currentData())
        for slot, combo in enumerate(self.char_passive_combos):
            char.set_passive_ability(slot, combo.currentData())

    def _on_character_gf_changed(self):
        char = self._selected_character()
        if not char:
            return
        for gf_id, spin in enumerate(self.char_gf_compat_spins):
            char.set_gf_compatibility(gf_id, spin.value())

    def _on_character_gf_junction_changed(self, gf_id, checked):
        char = self._selected_character()
        if not char:
            return
        if checked:
            for other in self.manager.character_entries:
                other.set_gf_junctioned(gf_id, False)
        char.set_gf_junctioned(gf_id, checked)

    def _on_character_junction_changed(self):
        char = self._selected_character()
        if not char:
            return
        for field, combo in self.char_junction_combos.items():
            setattr(char, field, combo.currentData())

    # ── Config tab ───────────────────────────────────────────────────────

    def _build_config_tab(self):
        from Quezacotl.quezacotlmanager import ConfigEntry
        self.config_spins = {}
        speed_tip = "0 = slowest, 4 = fastest"
        sliders = [
            ("battle_speed", "Battle speed", 4, "Battle ATB speed. 0 = slowest, 4 = fastest (ATB gauge = 4000 x (value+1))"),
            ("battle_message_speed", "Battle message speed", 4, f"Battle message scroll speed. {speed_tip}"),
            ("field_message_speed", "Field message speed", 4, f"Field/menu message scroll speed. {speed_tip}"),
            ("volume", "Analog stick dead zone", 0xFF, ConfigEntry.ANALOG_DEAD_ZONE_HELP),
            ("camera", "Battle camera speed", 4, f"Battle camera movement speed. {speed_tip}"),
        ]
        form = QFormLayout()
        for field, label, maximum, tip in sliders:
            spin = self._spinbox(0, maximum, self._on_config_changed, tip)
            self.config_spins[field] = spin
            form.addRow(f"{label}:", spin)

        self.config_scan_check = QCheckBox("Always show full Scan detail")
        self.config_scan_check.setToolTip("Scan detail mode (offset 0x05 bit 0). Off = repeat Scans on an already-"
                                          "scanned enemy show an abbreviated result; on = always show the full "
                                          "Scan info window.")
        self.config_scan_check.stateChanged.connect(self._on_config_changed)
        form.addRow("Scan:", self.config_scan_check)

        settings_group = QGroupBox("Settings")
        settings_group.setToolTip("In-game options: speeds, analog dead zone, camera, scan detail")
        settings_group.setLayout(form)

        # Config flag (offset 4): editable as a bitfield of named checkboxes.
        self.config_flag_checks = []
        flag_grid = QGridLayout()
        for i, (mask, name) in enumerate(ConfigEntry.FLAG_BITS):
            check = QCheckBox(name)
            check.setToolTip(f"Mask 0x{mask:02X}" + (" — normally managed by the game, not the player"
                                                     if "auto" in name else ""))
            check.stateChanged.connect(self._on_config_changed)
            self.config_flag_checks.append((mask, check))
            flag_grid.addWidget(check, i // 2, i % 2)
        flag_group = QGroupBox("Config flags")
        flag_group.setToolTip("Controller / config bitfield (offset 0x04). Some bits are set automatically "
                              "by the game from the detected hardware.")
        flag_group.setLayout(flag_grid)

        # Map seal (offset 7): 8 named lock bits.
        self.config_map_seal_checks = []
        seal_grid = QGridLayout()
        for i, (mask, name) in enumerate(ConfigEntry.MAP_SEAL_BITS):
            check = QCheckBox(name)
            check.setToolTip(f"Mask 0x{mask:02X} — set by story events that seal this menu action")
            check.stateChanged.connect(self._on_config_changed)
            self.config_map_seal_checks.append((mask, check))
            seal_grid.addWidget(check, i // 2, i % 2)
        seal_group = QGroupBox("Map seal (locked menu actions)")
        seal_group.setToolTip("Which menu actions are currently sealed by the map/story (offset 0x07)")
        seal_group.setLayout(seal_grid)

        # Button remap table (offsets 8-19): each physical button picks a logical action.
        # Slots 9/10 (0x11/0x12) are L3 and R3 - the slot order is the PSX DualShock button word
        # (remap_pad_input @0x4A2D60). They are real, editable buttons on a PSX analog pad; it is
        # only the PC input layer that can never emit them, so say that rather than grey them out.
        pc_inert_tip = ("Analog-pad only. This is a real config slot and the PSX engine remaps it, but "
                        "the PC input layer never emits pad bit 0x200/0x400 (Input_Cfg_ApplyBindingToPadBit "
                        "has no binding for them), so on PC the button can never fire whatever you set here.")
        self.config_key_combos = {}
        key_form = QFormLayout()
        for field, label in ConfigEntry.KEY_FIELDS:
            pc_inert = field in ("key_l3", "key_r3")
            combo = self._enum_combo(self._button_action_entries, self._on_config_changed,
                                     pc_inert_tip if pc_inert else
                                     f"Logical action triggered by the {label} button")
            self.config_key_combos[field] = combo
            if pc_inert:
                key_form.addRow(self._grey_label(f"{label} button:", pc_inert_tip), combo)
            else:
                key_form.addRow(f"{label} button:", combo)
        key_group = QGroupBox("Button config (physical button → action)")
        key_group.setToolTip("FF8's remap swaps roles between the 12 physical buttons; each button here is "
                             "assigned the logical action it performs (default = its own role). Known roles: "
                             "L2+R2 held = flee battle, R1 = Renzokuken critical timing.")
        key_group.setLayout(key_form)

        return self._left_column_scroll([settings_group, flag_group, seal_group, key_group])

    def _reload_config(self):
        config = self.manager.config
        for field, spin in self.config_spins.items():
            with QSignalBlocker(spin):
                self._set_spin_value(spin, getattr(config, field))
        with QSignalBlocker(self.config_scan_check):
            self.config_scan_check.setChecked(bool(config.scan & 0x01))
        for mask, check in self.config_flag_checks:
            with QSignalBlocker(check):
                check.setChecked(bool(config.flag & mask))
        for mask, check in self.config_map_seal_checks:
            with QSignalBlocker(check):
                check.setChecked(bool(config.map_seal & mask))
        for field, combo in self.config_key_combos.items():
            with QSignalBlocker(combo):
                self._select_combo(combo, getattr(config, field))

    def _on_config_changed(self):
        config = self.manager.config
        if not config:
            return
        for field, spin in self.config_spins.items():
            setattr(config, field, spin.value())
        # Only bit 0 of scan is meaningful; preserve any other bits.
        config.scan = (config.scan & ~0x01) | (0x01 if self.config_scan_check.isChecked() else 0)
        flag = 0
        for mask, check in self.config_flag_checks:
            if check.isChecked():
                flag |= mask
        config.flag = flag
        seal = 0
        for mask, check in self.config_map_seal_checks:
            if check.isChecked():
                seal |= mask
        config.map_seal = seal
        for field, combo in self.config_key_combos.items():
            setattr(config, field, combo.currentData())

    # ── Misc tab ─────────────────────────────────────────────────────────

    def _build_misc_tab(self):
        # Party slots 1-3 are the real party; slot 4 (party[3]) is unused padding (the top byte
        # of the 32-bit party word) — FF8's party is fixed at 3, so it is shown read-only.
        party4_tip = ("Read-only: party slot 4 is unused padding (the high byte of the 32-bit party word). "
                      "FF8's party is fixed at 3 members; the game never stores a character here.")
        self.misc_party_combos = []
        self._party_rows = []
        for i in range(4):
            phantom = i == 3
            combo = self._enum_combo(self._party_entries, None if phantom else self._on_misc_changed,
                                     party4_tip if phantom else f"Party slot {i + 1} character (None = empty)")
            self.misc_party_combos.append(combo)
            if phantom:
                combo.setEnabled(False)
                self._party_rows.append((self._grey_label("Party member 4:", party4_tip), combo))
            else:
                self._party_rows.append((f"Party member {i + 1}:", combo))
        self.misc_griever_name_edit = QLineEdit()
        self.misc_griever_name_edit.setToolTip("Griever GF name (FF8 text, max 12 bytes)")
        self._compact_line(self.misc_griever_name_edit)
        self.misc_griever_name_edit.editingFinished.connect(self._on_misc_griever_name_changed)
        self.misc_name_edits = {}
        for field, whose in (("squall_name", "Squall"), ("rinoa_name", "Rinoa"), ("angelo_name", "Angelo"), ("boko_name", "Boko")):
            edit = QLineEdit()
            edit.setToolTip(f"{whose}'s name (FF8 text, max 12 bytes), stored in the save's header")
            self._compact_line(edit)
            edit.editingFinished.connect(lambda f=field, e=edit: self._on_misc_name_changed(f, e))
            self.misc_name_edits[field] = edit
        self.misc_gil_spin = self._u32_spinbox(self._on_misc_changed, "Party gil (its copy in field variable 72 follows on save)")
        self.misc_gil_laguna_spin = self._u32_spinbox(self._on_misc_changed, "Laguna-squad gil (its copy in field variable 76 follows on save)")
        self.misc_weapon_laguna_spin = self._spinbox(0, 0xFF, self._on_misc_changed, "Laguna's weapon id")
        self.misc_weapon_kiros_spin = self._spinbox(0, 0xFF, self._on_misc_changed, "Kiros's weapon id")
        self.misc_weapon_ward_spin = self._spinbox(0, 0xFF, self._on_misc_changed, "Ward's weapon id")

        general_form = QFormLayout()
        for label, combo in self._party_rows:
            general_form.addRow(label, combo)
        general_form.addRow("Squall name:", self.misc_name_edits["squall_name"])
        general_form.addRow("Rinoa name:", self.misc_name_edits["rinoa_name"])
        general_form.addRow("Griever name:", self.misc_griever_name_edit)
        general_form.addRow("Angelo name:", self.misc_name_edits["angelo_name"])
        general_form.addRow("Boko name:", self.misc_name_edits["boko_name"])
        general_form.addRow("Gil:", self.misc_gil_spin)
        general_form.addRow("Gil (Laguna squad):", self.misc_gil_laguna_spin)
        general_form.addRow("Laguna weapon:", self.misc_weapon_laguna_spin)
        general_form.addRow("Kiros weapon:", self.misc_weapon_kiros_spin)
        general_form.addRow("Ward weapon:", self.misc_weapon_ward_spin)
        general_group = QGroupBox("General")
        general_group.setToolTip("Party, Griever name, gil and Laguna-squad weapons")
        general_group.setLayout(general_form)

        # Unlocked weapons: bit i = kernel weapon id i (28 upgradeable party weapons).
        weapon_entries = [{"bit": wid, "name": f"Weapon {wid}"} for wid in self._weapon_characters]
        weapons_group, self.misc_weapon_checks = self._bitfield_group(
            "Unlocked weapons",
            "Weapon-upgrade recipes already built/owned (Junk Shop). Bit i = kernel weapon id i.",
            weapon_entries, self._on_misc_changed, columns=3)

        # Limit-break unlocks: each is a bitfield → a checkbox group.
        self.misc_limit_bitfields = []  # (manager field, [(bit, checkbox)])
        limit_groups = []
        for field, title, entries, tip in self._limit_bitfield_defs:
            group, checks = self._bitfield_group(title, tip, entries, self._on_misc_changed)
            self.misc_limit_bitfields.append((field, checks))
            limit_groups.append(group)

        # Angelo Search points are per-command learning counters (not a bitfield).
        self.misc_angelo_point_spins = [
            self._spinbox(0, 0xFF, self._on_misc_changed,
                         "Remaining points to learn this Angelo command (counts down to 0)")
            for _ in range(8)]
        points_form = QFormLayout()
        for i, spin in enumerate(self.misc_angelo_point_spins):
            angelo_name = self._limit_bitfield_defs[-1][2][i]["name"]
            points_form.addRow(f"{angelo_name}:", spin)
        points_group = QGroupBox("Angelo Search — learning points")
        points_group.setToolTip("Per-command AP-like learning progress; 0 = learned")
        points_group.setLayout(points_form)

        return self._left_column_scroll([general_group, weapons_group, *limit_groups, points_group])

    def _reload_names(self):
        for field, edit in self.misc_name_edits.items():
            with QSignalBlocker(edit):
                edit.setText(getattr(self.manager.header, field))

    def _on_misc_name_changed(self, field, edit):
        if self.manager.header and edit.text() != getattr(self.manager.header, field):
            setattr(self.manager.header, field, edit.text())

    def _reload_misc(self):
        misc = self.manager.misc
        for combo, value in zip(self.misc_party_combos,
                                [misc.party_mem1, misc.party_mem2, misc.party_mem3, misc.party_mem4]):
            with QSignalBlocker(combo):
                self._select_combo(combo, value)
        with QSignalBlocker(self.misc_griever_name_edit):
            self.misc_griever_name_edit.setText(misc.griever_name)
        for spin, value in [
            (self.misc_gil_spin, misc.gil), (self.misc_gil_laguna_spin, misc.gil_laguna),
            (self.misc_weapon_laguna_spin, misc.weapon_id_laguna),
            (self.misc_weapon_kiros_spin, misc.weapon_id_kiros),
            (self.misc_weapon_ward_spin, misc.weapon_id_ward),
        ]:
            with QSignalBlocker(spin):
                self._set_spin_value(spin, value)
        unlocked = misc.unlocked_weapons
        for bit, check in self.misc_weapon_checks:
            with QSignalBlocker(check):
                check.setChecked(bool(unlocked & (1 << bit)))
        for field, checks in self.misc_limit_bitfields:
            value = getattr(misc, field)
            for bit, check in checks:
                with QSignalBlocker(check):
                    check.setChecked(bool(value & (1 << bit)))
        for i, spin in enumerate(self.misc_angelo_point_spins):
            with QSignalBlocker(spin):
                self._set_spin_value(spin, misc.get_angelo_point(i))

    def _on_misc_griever_name_changed(self):
        self.manager.misc.griever_name = self.misc_griever_name_edit.text()

    def _on_misc_changed(self):
        misc = self.manager.misc
        if not misc:
            return
        (misc.party_mem1, misc.party_mem2,
         misc.party_mem3, misc.party_mem4) = (c.currentData() for c in self.misc_party_combos)
        misc.gil = self.misc_gil_spin.value()
        misc.gil_laguna = self.misc_gil_laguna_spin.value()
        misc.weapon_id_laguna = self.misc_weapon_laguna_spin.value()
        misc.weapon_id_kiros = self.misc_weapon_kiros_spin.value()
        misc.weapon_id_ward = self.misc_weapon_ward_spin.value()
        # unlocked_weapons keeps any high bits (28-31) the game doesn't use but we shouldn't drop.
        unlocked = misc.unlocked_weapons
        for bit, check in self.misc_weapon_checks:
            unlocked = (unlocked | (1 << bit)) if check.isChecked() else (unlocked & ~(1 << bit))
        misc.unlocked_weapons = unlocked
        for field, checks in self.misc_limit_bitfields:
            value = getattr(misc, field)  # preserve any bits not shown as a checkbox
            for bit, check in checks:
                value = (value | (1 << bit)) if check.isChecked() else (value & ~(1 << bit))
            setattr(misc, field, value)
        for i, spin in enumerate(self.misc_angelo_point_spins):
            misc.set_angelo_point(i, spin.value())

    # ── Triple Triad tab ─────────────────────────────────────────────────

    def _build_triple_triad_tab(self):
        sub_tabs = QTabWidget()
        sub_tabs.addTab(self._build_cards_page(), "Cards")
        sub_tabs.addTab(self._build_card_rules_page(), "Rules and quests")
        sub_tabs.setTabToolTip(0, "The cards you own: copies of the common ones, where each rare one is")
        sub_tabs.setTabToolTip(1, "Rules of each region, Queen of Cards, CC Group and match counts")
        return sub_tabs

    @staticmethod
    def _configure_card_table(table, labels):
        table.setHorizontalHeaderLabels(labels)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(24)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = table.horizontalHeader()
        header.setStretchLastSection(False)
        for column in range(table.columnCount()):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)

    @staticmethod
    def _fit_card_table_width(table):
        """As wide as its columns, so it never scrolls sideways and nothing stretches."""
        table.resizeColumnsToContents()
        scroll_bar = table.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent)
        table.setFixedWidth(table.horizontalHeader().length() + scroll_bar + 2 * table.frameWidth() + 4)

    def _card_label(self, card_id):
        level = card_id // cardlocation.NB_CARDS_PER_LEVEL + 1
        return f"Lv{level} {card_id}: {self._card_info[card_id]['name']}"

    def _centered_cell(self, widget):
        cell = QWidget()
        layout = QHBoxLayout(cell)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignCenter)
        return cell

    def _build_cards_page(self):
        obtained_tip = ("The card was obtained at least once. The game ignores a card without it: no copies\n"
                        "of it count, and it stays unknown in the card menu. Unticking takes the card away\n"
                        "(copies to 0, or a rare card held by you back to its starting owner).")
        # Common cards: obtained + copies
        self.tt_common_table = QTableWidget(cardlocation.RARE_CARD_FIRST_ID, 3)
        self._configure_card_table(self.tt_common_table, ["Card", "Obtained", "Copies"])
        self.tt_common_checks = []
        self.tt_common_spins = []
        for card_id in range(cardlocation.RARE_CARD_FIRST_ID):
            self.tt_common_table.setItem(card_id, 0, QTableWidgetItem(self._card_label(card_id)))
            check = QCheckBox()
            check.setToolTip(obtained_tip)
            check.toggled.connect(lambda checked, c=card_id: self._on_card_obtained_changed(c, checked))
            self.tt_common_checks.append(check)
            self.tt_common_table.setCellWidget(card_id, 1, self._centered_cell(check))
            spin = self._spinbox(0, TT_CARD_COPIES_MASK, tooltip=(
                f"Copies owned. The game itself adds no copy past {TT_MAX_COPIES}."))
            spin.setMaximumWidth(TT_SMALL_SPIN_WIDTH)
            spin.valueChanged.connect(lambda value, c=card_id: self._on_card_copies_changed(c, value))
            self.tt_common_spins.append(spin)
            self.tt_common_table.setCellWidget(card_id, 2, spin)

        self.tt_all_common_check = QCheckBox("All obtained")
        self.tt_all_common_check.setToolTip("Tick or untick every common card. Unticking also removes their copies.")
        self.tt_all_common_check.clicked.connect(self._on_all_common_obtained)
        self.tt_all_copies_spin = self._spinbox(0, TT_MAX_COPIES, tooltip="Copies the button below gives every common card")
        self.tt_all_copies_spin.setMaximumWidth(TT_SMALL_SPIN_WIDTH)
        self.tt_all_copies_spin.setValue(TT_MAX_COPIES)
        self.tt_all_copies_button = QPushButton("Set all copies")
        self.tt_all_copies_button.setToolTip("Give every common card this number of copies")
        self.tt_all_copies_button.clicked.connect(self._on_all_common_copies)
        common_row = QHBoxLayout()
        common_row.addWidget(self.tt_all_common_check)
        common_row.addStretch(1)
        common_row.addWidget(self.tt_all_copies_spin)
        common_row.addWidget(self.tt_all_copies_button)
        self._fit_card_table_width(self.tt_common_table)
        common_layout = QVBoxLayout()
        common_layout.addWidget(self.tt_common_table)
        common_layout.addLayout(common_row)
        common_group = QGroupBox("Common cards (levels 1-7)")
        common_group.setLayout(common_layout)

        # Rare cards: obtained + location. The 256 locations, the player's first, in one shared model.
        self.deck_users = {}   # {Deck ID: card players} from field folders
        location_model = QStandardItemModel(self)
        self.tt_location_model = location_model
        for location in [cardlocation.LOCATION_PLAYER, *(i for i in range(256) if i != cardlocation.LOCATION_PLAYER)]:
            item = QStandardItem(self._location_label(location))
            item.setData(location, Qt.ItemDataRole.UserRole)
            location_model.appendRow(item)
        location_tip = ("Who holds this rare card. The player's own cards = you own it. Anything else is a Deck ID:\n"
                        "the card players with that Deck ID can deal it (see the CC Group tool).")
        self.tt_rare_table = QTableWidget(TT_NB_RARE_CARDS, 3)
        self._configure_card_table(self.tt_rare_table, ["Card", "Obtained", "Location"])
        self.tt_rare_checks = {}
        self.tt_rare_combos = {}
        for row in range(TT_NB_RARE_CARDS):
            card_id = cardlocation.RARE_CARD_FIRST_ID + row
            self.tt_rare_table.setItem(row, 0, QTableWidgetItem(self._card_label(card_id)))
            check = QCheckBox()
            check.setToolTip(obtained_tip)
            check.toggled.connect(lambda checked, c=card_id: self._on_card_obtained_changed(c, checked))
            self.tt_rare_checks[card_id] = check
            self.tt_rare_table.setCellWidget(row, 1, self._centered_cell(check))
            combo = QComboBox()
            combo.setModel(location_model)
            combo.setToolTip(location_tip)
            combo.setMinimumContentsLength(60)
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.currentIndexChanged.connect(lambda _index, c=card_id, b=combo: self._on_card_location_changed(c, b))
            self.tt_rare_combos[card_id] = combo
            self.tt_rare_table.setCellWidget(row, 2, combo)

        self.tt_all_rare_check = QCheckBox("All obtained")
        self.tt_all_rare_check.setToolTip("Tick or untick every rare card. Unticking sends the ones you hold back to "
                                          "their starting owners.")
        self.tt_all_rare_check.clicked.connect(self._on_all_rare_obtained)
        self.tt_all_rare_button = QPushButton("All to the player")
        self.tt_all_rare_button.setToolTip("Give yourself every rare card")
        self.tt_all_rare_button.clicked.connect(self._on_all_rare_to_player)
        rare_row = QHBoxLayout()
        rare_row.addWidget(self.tt_all_rare_check)
        rare_row.addStretch(1)
        rare_row.addWidget(self.tt_all_rare_button)
        self.tt_deck_folder_label = QLabel("Places are the vanilla game's")
        self.tt_deck_folder_label.setStyleSheet("color: gray;")
        self.tt_deck_folder_button = QPushButton("Name from field folders...")
        self.tt_deck_folder_button.setToolTip("Read the field scripts of the game and of a mod (e.g. Cronos's FieldRework\\field)\n"
                                              "to name the card players holding each Deck ID. A mod can move them.")
        self.tt_deck_folder_button.clicked.connect(self._pick_deck_folders)
        self.tt_deck_clear_button = QPushButton("Vanilla places")
        self.tt_deck_clear_button.setVisible(False)
        self.tt_deck_clear_button.clicked.connect(lambda: self.set_deck_users({}))
        deck_row = QHBoxLayout()
        deck_row.addWidget(self.tt_deck_folder_label)
        deck_row.addStretch(1)
        deck_row.addWidget(self.tt_deck_clear_button)
        deck_row.addWidget(self.tt_deck_folder_button)
        self._fit_card_table_width(self.tt_rare_table)
        rare_layout = QVBoxLayout()
        rare_layout.addWidget(self.tt_rare_table)
        rare_layout.addLayout(rare_row)
        rare_layout.addLayout(deck_row)
        rare_group = QGroupBox("Rare cards (levels 8-10)")
        rare_group.setLayout(rare_layout)

        # Preview of the selected card
        self.tt_card_preview = QLabel()
        self.tt_card_preview.setFixedSize(TT_PREVIEW_SIZE, TT_PREVIEW_SIZE)
        self.tt_card_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tt_card_name = QLabel()
        self.tt_card_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tt_card_name.setWordWrap(True)
        preview_layout = QVBoxLayout()
        preview_layout.addWidget(self.tt_card_preview)
        preview_layout.addWidget(self.tt_card_name)
        preview_layout.addStretch(1)
        self.tt_common_table.currentCellChanged.connect(lambda row, *_: self._show_card_preview(row))
        self.tt_rare_table.currentCellChanged.connect(
            lambda row, *_: self._show_card_preview(cardlocation.RARE_CARD_FIRST_ID + row if row >= 0 else -1))

        layout = QHBoxLayout()
        layout.addWidget(common_group)
        layout.addWidget(rare_group)
        layout.addLayout(preview_layout)
        layout.addStretch(1)
        page = QWidget()
        page.setLayout(layout)
        return page

    def _build_card_rules_page(self):
        rules_grid = QGridLayout()
        rules_grid.addWidget(QLabel("Region"), 0, 0)
        for column, (mask, name) in enumerate(GAME_RULE_BITS, start=1):
            rules_grid.addWidget(QLabel(name), 0, column, Qt.AlignmentFlag.AlignCenter)
        trade_column = len(GAME_RULE_BITS) + 1
        rules_grid.addWidget(QLabel("Trade rule"), 0, trade_column)
        trade_entries = [{"value": value, "name": name} for value, name in enumerate(TRADE_RULE_NAMES)]
        region_entries = [{"value": 0, "name": "None"}] + [{"value": index + 1, "name": name}
                                                           for index, name in enumerate(TT_REGION_NAMES)]

        def rule_checks(row, number):
            for column, (mask, name) in enumerate(GAME_RULE_BITS, start=1):
                check = QCheckBox()
                check.setToolTip(f"{name} (variable {number}, mask 0x{mask:02X})")
                check.toggled.connect(lambda checked, n=number, m=mask: self._on_card_rule_changed(n, m, checked))
                self.tt_rule_checks.append((number, mask, check))
                rules_grid.addWidget(check, row, column, Qt.AlignmentFlag.AlignCenter)

        self.tt_rule_checks = []  # (variable, mask, checkbox)
        self.tt_trade_combos = []
        for region, name in enumerate(TT_REGION_NAMES):
            row = region + 1
            rules_grid.addWidget(QLabel(f"{name}:"), row, 0)
            rule_checks(row, TT_VAR_REGION_RULES + region)
            combo = self._enum_combo(trade_entries, tooltip=f"Trade rule of {name} (variable {TT_VAR_REGION_TRADE_RULE + region}, low 3 bits)")
            combo.currentIndexChanged.connect(lambda _index, r=region, b=combo: self._on_card_trade_rule_changed(r, b))
            self.tt_trade_combos.append(combo)
            rules_grid.addWidget(combo, row, trade_column)

        # The two rule sets Squall carries, each with its region
        self.tt_last_region_combos = []
        rules_grid.addWidget(QLabel("Region"), TT_NB_REGIONS + 1, trade_column)
        for index in range(TT_NB_LAST_RULES):
            row = TT_NB_REGIONS + 2 + index
            rules_grid.addWidget(QLabel(f"Carried rules {index + 1}:"), row, 0)
            rule_checks(row, TT_VAR_LAST_RULES + index)
            number = TT_VAR_LAST_REGIONS + index
            combo = self._enum_combo(region_entries, tooltip=f"Region these rules Squall carries come from (variable {number})")
            self._connect_card_var(combo, number)
            self.tt_last_region_combos.append((number, combo))
            rules_grid.addWidget(combo, row, trade_column)
        rules_grid.setColumnStretch(trade_column + 1, 1)   # the columns stay close together
        rules_group = QGroupBox("Rules")
        rules_group.setToolTip("The rules the Queen of Cards spreads and abolishes, per region. Most card players use "
                               "their region's rules (a card player's own rules are in the CC Group tool).")
        rules_group.setLayout(rules_grid)

        # Queen of Cards + CC Group
        self.tt_queen_location_combo = self._enum_combo(
            [{"value": 0, "name": "Nowhere"}] + [{"value": index + 1, "name": name}
                                                 for index, name in enumerate(TT_QUEEN_CITIES)],
            tooltip=f"Where the Queen of Cards is (variable {TT_VAR_QUEEN_LOCATION})")
        self.tt_queen_trade_combo = self._enum_combo(
            trade_entries, tooltip=f"Trade rule of the Queen of Cards, in matches against her and spreading where she is (variable {TT_VAR_QUEEN_TRADE_RULE})")
        self.tt_rating_spin = self._spinbox(0, 0xFF, tooltip=f"How busy trading is in the region below, 0 to 10: the chance its rule spreads (variable {TT_VAR_TRADE_RATING})")
        self.tt_rating_spin.setMaximumWidth(TT_SMALL_SPIN_WIDTH)
        self.tt_rating_region_combo = self._enum_combo(
            region_entries, tooltip=f"Region where trading is busiest, whose trade rule spreads (variable {TT_VAR_TRADE_RATING_REGION})")
        self.tt_degeneration_spin = self._spinbox(0, 0xFF, tooltip=f"Pull of the trade rules back to One: its chance in 256 after each match (variable {TT_VAR_DEGENERATION})")
        self.tt_degeneration_spin.setMaximumWidth(TT_SMALL_SPIN_WIDTH)
        self.tt_queen_quest_combo = self._enum_combo(
            [{"value": value, "name": name} for value, name in enumerate(TT_QUEEN_QUEST_CARDS)],
            tooltip=f"Last card made in the Queen of Cards' quest (variable {TT_VAR_QUEEN_QUEST})")
        self.tt_cc_combo = self._enum_combo(
            [{"value": value, "name": name} for value, name in TT_CC_QUEST_STEPS],
            tooltip=f"CC Group members beaten (variable {TT_VAR_CC_QUEST}, low 5 bits, and variable "
                    f"{TT_VAR_BGU_DIALOGS}, mask 0x{TT_CC_DIALOG_MASK:02X})")
        self.tt_cc_combo.currentIndexChanged.connect(self._on_card_cc_quest_changed)
        self._connect_card_var(self.tt_queen_location_combo, TT_VAR_QUEEN_LOCATION)
        self._connect_card_var(self.tt_queen_trade_combo, TT_VAR_QUEEN_TRADE_RULE)
        self._connect_card_var(self.tt_rating_spin, TT_VAR_TRADE_RATING)
        self._connect_card_var(self.tt_rating_region_combo, TT_VAR_TRADE_RATING_REGION)
        self._connect_card_var(self.tt_degeneration_spin, TT_VAR_DEGENERATION)
        self._connect_card_var(self.tt_queen_quest_combo, TT_VAR_QUEEN_QUEST)
        quest_form = QFormLayout()
        quest_form.addRow("Queen location:", self.tt_queen_location_combo)
        quest_form.addRow("Queen trade rule:", self.tt_queen_trade_combo)
        quest_form.addRow("Trade rating:", self.tt_rating_spin)
        quest_form.addRow("Trade rating region:", self.tt_rating_region_combo)
        quest_form.addRow("Degeneration:", self.tt_degeneration_spin)
        quest_form.addRow("Last card made:", self.tt_queen_quest_combo)
        quest_form.addRow("CC Group quest:", self.tt_cc_combo)
        quest_group = QGroupBox("Quests")
        quest_group.setLayout(quest_form)

        # Match counts
        self.tt_count_spins = {
            "wins": self._spinbox(0, 0xFFFF, tooltip="Card games won"),
            "losses": self._spinbox(0, 0xFFFF, tooltip="Card games lost"),
            "draws": self._spinbox(0, 0xFFFF, tooltip="Card games drawn"),
        }
        for field, spin in self.tt_count_spins.items():
            spin.valueChanged.connect(lambda value, f=field: self._on_card_count_changed(f, value))
        self.tt_bgu_wins_spin = self._spinbox(0, 0xFF, tooltip=f"Card games won in Balamb Garden (variable {TT_VAR_BGU_WINS})")
        self.tt_bgu_wins_spin.setMaximumWidth(TT_SMALL_SPIN_WIDTH)
        self._connect_card_var(self.tt_bgu_wins_spin, TT_VAR_BGU_WINS)
        self.tt_seed_spin = self._u32_spinbox(tooltip="Random seed of the card game: the game draws from it and updates it")
        self.tt_seed_spin.valueChanged.connect(self._on_card_seed_changed)
        self.tt_complete_check = QCheckBox("Collection completed")
        self.tt_complete_check.setToolTip("The game sets this the first time every card has been obtained and never clears it.")
        self.tt_complete_check.toggled.connect(self._on_card_complete_changed)
        self.tt_unused_spin = self._readonly_spin(RESERVED_TOOLTIP, 0xFFFF)
        counts_form = QFormLayout()
        counts_form.addRow("Wins:", self.tt_count_spins["wins"])
        counts_form.addRow("Losses:", self.tt_count_spins["losses"])
        counts_form.addRow("Draws:", self.tt_count_spins["draws"])
        counts_form.addRow("Balamb Garden wins:", self.tt_bgu_wins_spin)
        counts_form.addRow("Random seed:", self.tt_seed_spin)
        counts_form.addRow(self.tt_complete_check)
        counts_form.addRow(self._grey_label("Unused:", RESERVED_TOOLTIP), self.tt_unused_spin)
        counts_group = QGroupBox("Statistics")
        counts_group.setLayout(counts_form)

        lower = QHBoxLayout()
        lower.addWidget(quest_group)
        lower.addWidget(counts_group)
        lower.addStretch(1)
        layout = QVBoxLayout()
        layout.addWidget(rules_group)
        layout.addLayout(lower)
        layout.addStretch(1)
        page = QWidget()
        page.setLayout(layout)
        return page

    def _connect_card_var(self, widget, number):
        """A combo or spin box holding one whole field variable."""
        if isinstance(widget, QComboBox):
            widget.currentIndexChanged.connect(lambda _index: self.manager.triple_triad.set_var(number, widget.currentData()))
        else:
            widget.valueChanged.connect(lambda value: self.manager.triple_triad.set_var(number, value))
        self.tt_var_widgets.append((widget, number))

    def _mark_dirty(self):
        dirty_state = getattr(self, "dirty_state", None)
        if dirty_state is not None:
            dirty_state.mark()

    def _show_card_preview(self, card_id):
        if card_id < 0:
            return
        card = self._card_info[card_id]
        self.tt_card_name.setText(card["name"])
        pixmap = QPixmap.fromImage(ImageQt(card["img_remaster"]).copy())
        self.tt_card_preview.setPixmap(pixmap.scaled(TT_PREVIEW_SIZE, TT_PREVIEW_SIZE,
                                                     Qt.AspectRatioMode.KeepAspectRatio,
                                                     Qt.TransformationMode.SmoothTransformation))

    def _reload_cards(self):
        """Show the cards of the save, nothing written back."""
        tt = self.manager.triple_triad
        for card_id in range(cardlocation.RARE_CARD_FIRST_ID):
            with QSignalBlocker(self.tt_common_checks[card_id]):
                self.tt_common_checks[card_id].setChecked(tt.is_obtained(card_id))
            with QSignalBlocker(self.tt_common_spins[card_id]):
                self._set_spin_value(self.tt_common_spins[card_id], tt.copies(card_id))
        for card_id, check in self.tt_rare_checks.items():
            with QSignalBlocker(check):
                check.setChecked(tt.is_obtained(card_id))
            combo = self.tt_rare_combos[card_id]
            with QSignalBlocker(combo):
                combo.setCurrentIndex(combo.findData(tt.location(card_id), Qt.ItemDataRole.UserRole))
        with QSignalBlocker(self.tt_all_common_check):
            self.tt_all_common_check.setChecked(all(tt.is_obtained(c) for c in range(cardlocation.RARE_CARD_FIRST_ID)))
        with QSignalBlocker(self.tt_all_rare_check):
            self.tt_all_rare_check.setChecked(all(tt.is_obtained(c) for c in self.tt_rare_checks))

    def _reload_triple_triad(self):
        tt = self.manager.triple_triad
        self._reload_cards()
        for number, mask, check in self.tt_rule_checks:
            with QSignalBlocker(check):
                check.setChecked(bool(tt.var(number) & mask))
        for region, combo in enumerate(self.tt_trade_combos):
            with QSignalBlocker(combo):
                self._select_combo(combo, tt.region_trade_rule(region))
        for widget, number in self.tt_var_widgets:
            with QSignalBlocker(widget):
                if isinstance(widget, QComboBox):
                    self._select_combo(widget, tt.var(number))
                else:
                    self._set_spin_value(widget, tt.var(number))
        with QSignalBlocker(self.tt_cc_combo):
            self._select_combo(self.tt_cc_combo, tt.cc_quest)
        for field, spin in self.tt_count_spins.items():
            with QSignalBlocker(spin):
                self._set_spin_value(spin, getattr(tt, field))
        with QSignalBlocker(self.tt_seed_spin):
            self._set_spin_value(self.tt_seed_spin, tt.seed)
        with QSignalBlocker(self.tt_complete_check):
            self.tt_complete_check.setChecked(tt.collection_complete)
        self._set_spin_value(self.tt_unused_spin, tt.unused)

    def _on_card_obtained_changed(self, card_id, obtained):
        self.manager.triple_triad.set_obtained(card_id, obtained)
        self._reload_cards()   # unticking also changes the copies or the location

    def _on_card_copies_changed(self, card_id, copies):
        self.manager.triple_triad.set_copies(card_id, copies)
        self._reload_cards()   # copies tick Obtained

    def _on_card_location_changed(self, card_id, combo):
        self.manager.triple_triad.set_location(card_id, combo.currentData(Qt.ItemDataRole.UserRole))
        self._reload_cards()   # at the player ticks Obtained

    def _on_all_common_obtained(self, checked):
        for card_id in range(cardlocation.RARE_CARD_FIRST_ID):
            self.manager.triple_triad.set_obtained(card_id, checked)
        self._reload_cards()

    def _on_all_common_copies(self):
        for card_id in range(cardlocation.RARE_CARD_FIRST_ID):
            self.manager.triple_triad.set_copies(card_id, self.tt_all_copies_spin.value())
        self._reload_cards()
        self._mark_dirty()

    def _on_all_rare_obtained(self, checked):
        for card_id in self.tt_rare_checks:
            self.manager.triple_triad.set_obtained(card_id, checked)
        self._reload_cards()

    def _on_all_rare_to_player(self):
        for card_id in self.tt_rare_checks:
            self.manager.triple_triad.set_location(card_id, cardlocation.LOCATION_PLAYER)
        self._reload_cards()
        self._mark_dirty()

    def _on_card_rule_changed(self, number, mask, checked):
        tt = self.manager.triple_triad
        tt.set_var(number, tt.var(number) | mask if checked else tt.var(number) & ~mask & 0xFF)

    def _on_card_trade_rule_changed(self, region, combo):
        self.manager.triple_triad.set_region_trade_rule(region, combo.currentData())

    def _on_card_cc_quest_changed(self):
        self.manager.triple_triad.cc_quest = self.tt_cc_combo.currentData()

    def _on_card_count_changed(self, field, value):
        setattr(self.manager.triple_triad, field, value)

    def _on_card_seed_changed(self):
        self.manager.triple_triad.seed = self.tt_seed_spin.value()

    def _on_card_complete_changed(self, checked):
        self.manager.triple_triad.collection_complete = checked

    # ── Items tab ────────────────────────────────────────────────────────

    ITEM_EXTENSION_TEXT = {
        "none": ("255 inventory slots: this kernel.bin adds items (FFNx AddMoreItems). The save holds slots "
                 "199-255 from the first time one of them has an item."),
        "stale": ("255 inventory slots: this kernel.bin adds items (FFNx AddMoreItems). The save has a block for "
                  "them that FFNx ignores (damaged, or the inventory changed after it), so they start empty."),
        "extended": ("255 inventory slots (FFNx AddMoreItems). The first 198 are also the save's "
                     "own inventory, which the game without FFNx reads."),
    }

    ITEM_EXTENSION_HIDDEN_TEXT = {
        False: "198 inventory slots.",
        True: ("198 inventory slots. The save also has an FFNx AddMoreItems block, kept as it is: its 255 slots "
               "show with a kernel.bin that adds items."),
    }

    def _build_items_tab(self):
        self.items_table = QTableWidget(0, 2)
        self.items_table.setHorizontalHeaderLabels(["Item", "Quantity"])
        self._configure_list_table(self.items_table)
        self.item_extension_label = QLabel()
        self.item_extension_label.setWordWrap(True)
        self.item_extension_label.setToolTip(
            "A kernel.bin that adds items gives FFNx 255 slots, and the tool follows: open yours with the\n"
            "toolbar's Import complementary. The game without FFNx keeps the first 198.")
        self.all_items_button = QPushButton("All items")
        self.all_items_button.setToolTip(f"Fill the inventory with every item, {ITEM_MAX_QUANTITY} of each")
        self.all_items_button.clicked.connect(self._fill_all_items)
        self.sort_by_id_button = QPushButton("Sort by type")
        self.sort_by_id_button.setToolTip("Sort the inventory by item id, which groups items by type. Empty slots go last.")
        self.sort_by_id_button.clicked.connect(lambda: self._sort_items(lambda item_id: item_id))
        self.sort_by_name_button = QPushButton("Sort by name")
        self.sort_by_name_button.setToolTip("Sort the inventory by item name. Empty slots go last.")
        self.sort_by_name_button.clicked.connect(lambda: self._sort_items(self._item_sort_name))
        bottom = QHBoxLayout()
        bottom.addWidget(self.all_items_button)
        bottom.addStretch(1)
        bottom.addWidget(self.sort_by_id_button)
        bottom.addWidget(self.sort_by_name_button)
        inventory = QWidget()
        layout = QVBoxLayout(inventory)
        layout.addWidget(self.item_extension_label)
        layout.addWidget(self.items_table)
        layout.addLayout(bottom)
        self.items_extras_page = ItemsExtrasPage(self)
        sub_tabs = QTabWidget()
        sub_tabs.addTab(inventory, "Inventory")
        sub_tabs.addTab(self.items_extras_page, "Battle order and magazines")
        return sub_tabs

    def _item_sort_name(self, item_id):
        return (self.kernel_names.item_name(item_id) or f"Item {item_id}").lower()

    def _set_item_slots(self, pairs):
        for entry, (item_id, quantity) in zip(self.manager.item_entries, pairs):
            entry.item_id = item_id
            entry.quantity = quantity
        self._reload_items()
        self._mark_dirty()

    def _fill_all_items(self):
        ids = [entry["value"] for entry in self._item_choices() if entry["value"]]
        slots = len(self.manager.item_entries)
        pairs = [(item_id, ITEM_MAX_QUANTITY) for item_id in ids[:slots]]
        self._set_item_slots(pairs + [(0, 0)] * (slots - len(pairs)))

    def _sort_items(self, key):
        """Empty slots last, an item's quantity staying with it."""
        held = [(entry.item_id, entry.quantity) for entry in self.manager.item_entries if entry.item_id]
        empty = [(0, 0)] * (len(self.manager.item_entries) - len(held))
        self._set_item_slots(sorted(held, key=lambda pair: key(pair[0])) + empty)

    def _reload_items(self):
        state = self.manager.item_extension
        self.item_extension_label.setText(self.ITEM_EXTENSION_TEXT[state] if self.manager.kernel_items_extended else
                                          self.ITEM_EXTENSION_HIDDEN_TEXT[state != "none"])
        choices = self._item_choices()
        self.items_table.setRowCount(0)
        self.items_table.setRowCount(len(self.manager.item_entries))
        for row, entry in enumerate(self.manager.item_entries):
            combo = self._enum_combo(choices, adjust_size=True)
            self._select_combo(combo, entry.item_id)
            combo.currentIndexChanged.connect(self._make_item_id_handler(entry, combo))
            self.items_table.setCellWidget(row, 0, combo)

            # FFNx's 255-slot block accepts at most 100 of an item (it keeps an item's slots valid).
            qty = self._spinbox(0, 100 if state == "extended" else 0xFF, tooltip="Amount held")
            self._set_spin_value(qty, entry.quantity)
            qty.valueChanged.connect(self._make_item_qty_handler(entry))
            self.items_table.setCellWidget(row, 1, qty)

    def _make_item_id_handler(self, entry, combo):
        def handler(_index):
            entry.item_id = combo.currentData()
        return handler

    def _make_item_qty_handler(self, entry):
        def handler(value):
            entry.quantity = value
        return handler
