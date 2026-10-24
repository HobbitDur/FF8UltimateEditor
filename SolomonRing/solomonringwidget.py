import json
import os

from PyQt6.QtCore import pyqtSignal, QSignalBlocker
from PyQt6.QtWidgets import (
    QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QMessageBox, QGroupBox, QPushButton
)

from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from FF8GameData.gamedata import GameData
from FF8GameData import itemids
from ShumiTranslator.model.kernel.kernelmanager import KernelManager
from SolomonRing.kernellookups import LookupRegistry
from SolomonRing.kernelentry import KernelEntry
from SolomonRing.kernelsectiontab import KernelSectionTab
from SolomonRing.commandanimationpanel import CommandAnimationPanel
from SolomonRing.commandtypes import command_type_options, FIRST_DLL_TYPE, LAST_DLL_TYPE
from SolomonRing.battle_setup import SETUP as BATTLE_SETUP
from SolomonRing.cronos_elemdef import (CronosElemDefDialog, GF_COUNT, CHARA_COUNT, MAGIC_PAGE, GF_PAGE,
                                        CHARACTER_PAGE)


# One top-level tab per kernel section (a kernel section == a tab). Order follows the
# section ids. Format kept as (tab title, [(section_id, sub-tab label)]) so multi-section
# groups are still possible if ever needed; here every group is a single section.
TAB_LAYOUT = [
    ("Battle Commands", [(1, "Battle Commands")]),
    ("Magic", [(2, "Magic")]),
    ("G-Forces", [(3, "G-Forces")]),
    ("Enemy Attacks", [(4, "Enemy Attacks")]),
    ("Weapons", [(5, "Weapons")]),
    ("Renzokuken", [(6, "Renzokuken")]),
    ("Characters", [(7, "Characters")]),
    ("Battle Items", [(8, "Battle Items")]),
    ("Item Names", [(9, "Item Names")]),
    ("Non-junctionable GF", [(10, "Non-junctionable GF")]),
    ("Command Ability Data", [(11, "Command Ability Data")]),
    ("Junction Abilities", [(12, "Junction Abilities")]),
    ("Command Abilities", [(13, "Command Abilities")]),
    ("Stat % Abilities", [(14, "Stat % Abilities")]),
    ("Character Abilities", [(15, "Character Abilities")]),
    ("Party Abilities", [(16, "Party Abilities")]),
    ("GF Abilities", [(17, "GF Abilities")]),
    ("Menu Abilities", [(18, "Menu Abilities")]),
    ("T. Character Limits", [(19, "T. Character Limits")]),
    ("Blue Magic", [(20, "Blue Magic")]),
    ("Blue Magic Params", [(21, "Blue Magic Params")]),
    ("Shot", [(22, "Shot")]),
    ("Duel", [(23, "Duel")]),
    ("Duel Params", [(24, "Duel Params")]),
    ("Rinoa 1", [(25, "Rinoa 1")]),
    ("Rinoa 2", [(26, "Rinoa 2")]),
    ("Slot Array", [(27, "Slot Array")]),
    ("Slot Sets", [(28, "Slot Sets")]),
    ("Devour", [(29, "Devour")]),
    ("Misc", [(30, "Misc")]),
    ("Misc Text", [(31, "Misc Text")]),
]


class SolomonRingWidget(QWidget):
    """kernel.bin editor with full doomtrain field parity, driven by JSON field defs."""

    CURRENT_TAB_KEY = "solomonring/current_tab"
    file_bindings_changed = pyqtSignal()

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData", file_registry=None,
                 settings=None):
        super().__init__()
        # The app's QSettings: remembers the last section tab across sessions (None: not kept).
        self.settings = settings

        if file_registry is None:  # The tool is used alone, it shares its files with nobody
            file_registry = FileRegistry()

        self.game_data_folder = game_data_folder
        self.file_registry = file_registry
        self.command_animation_panel = None
        self.game_data = GameData(game_data_folder)
        self.game_data.load_all()

        self.kernel_manager = KernelManager(self.game_data)
        self.registry = LookupRegistry(self.game_data, game_data_folder)
        self.loaded_filename = None

        with open(os.path.join(game_data_folder, "Resources", "json", "kernel_section_fields.json"),
                  encoding="utf-8") as f:
            self._section_configs = json.load(f)
        with open(os.path.join(game_data_folder, "Resources", "json", "kernel_bin_data.json"),
                  encoding="utf-8") as f:
            kernel_json = json.load(f)
        self._text_link = {s["id"]: s["section_id_text_linked"] for s in kernel_json["sections"]
                           if s["type"] == "data"}

        self._section_tabs = {}  # section_id -> KernelSectionTab
        self._tab_index_by_section = {}  # section_id -> top-level QTabWidget index

        main_layout = QVBoxLayout()

        # --- File toolbar -----------------------------------------------------
        # kernel.bin's Import / Save / Reload live in the shared header toolbar (via this binding),
        # and so do the Compress / Uncompress text buttons (via compress_text / uncompress_text,
        # shown only for tools that have them). Nothing tool-specific left to show here.
        self.kernel_binding = FileBinding("kernel.bin", file_registry,
                                          load_callback=self.load_file, save_callback=self._save_kernel)

        # --- Unlock switch ----------------------------------------------------
        # Fields the unmodified game never reads (padding, dead bytes, flags with no consumer,
        # values their owning enum makes meaningless) are greyed out by default, so what you can
        # edit is what actually does something. A mod may have given one of them a meaning, so
        # this ticks every tab into "edit anything" mode.
        self.unlock_check = QCheckBox("Unlock fields unused by the vanilla game")
        self.unlock_check.setToolTip(
            "Off (default): a field the unmodified game never reads is shown - so you can see its "
            "value - but greyed out, so you cannot change something that does nothing.\n"
            "On: every field becomes editable, for a mod that gave those bytes/flags a purpose. "
            "This only changes what the UI lets you edit; loading and saving are identical either way.")
        self.unlock_check.toggled.connect(self._set_unlock_all)
        unlock_row = QHBoxLayout()
        unlock_row.addWidget(self.unlock_check)
        unlock_row.addStretch(1)
        main_layout.addLayout(unlock_row)

        # --- Section tabs -----------------------------------------------------
        self.tabs = QTabWidget()
        for index, (title, entries) in enumerate(TAB_LAYOUT):
            self.tabs.addTab(self._build_group(entries), title)
            for section_id, _ in entries:
                self._tab_index_by_section[section_id] = index
        main_layout.addWidget(self.tabs)
        self._add_cronos_extension()
        self._restore_current_tab()
        self.tabs.currentChanged.connect(self._remember_current_tab)

        self.setLayout(main_layout)
        self.tabs.setEnabled(False)

        self.kernel_binding.load_opened_file()  # Another tool may have opened kernel.bin already

        # The damage formula popups' battle setup picks a character of this kernel.bin; the
        # monsters come from Ifrit, connected by the main window (set_monster_provider).
        BATTLE_SETUP.characters_provider = self._battle_characters

    CHARACTER_SECTION = 7

    def _battle_characters(self):
        """[(name, entry)] of the Characters section, as currently edited."""
        if not self.loaded_filename:
            return []
        tab = self._section_tabs.get(self.CHARACTER_SECTION)
        if tab is not None:
            tab.commit()                 # its open form may hold curve edits not written back yet
        names = self._section_configs[str(self.CHARACTER_SECTION)].get("entry_names") or []
        characters = []
        for index, entry in enumerate(self._section_entries(self.CHARACTER_SECTION)):
            name = entry.get_text(0).strip() or (names[index] if index < len(names) else f"#{index}")
            characters.append((name, entry))
        return characters

    def set_monster_provider(self, provider):
        """callable() -> [{'name', 'curves'}]: the monsters the battle setup can pick (Ifrit's
        opened ones, IfritMonsterWidget.battle_setup_monsters)."""
        BATTLE_SETUP.monsters_provider = provider

    def _set_unlock_all(self, unlocked):
        """Apply the "unlock unused fields" switch to every section tab at once."""
        for tab in self._section_tabs.values():
            tab.set_unlock_all(unlocked)
        self._refresh_command_data_enabled()

    def file_bindings(self):
        """kernel.bin and the read-only battle files imported for animation previews."""
        preview = self.command_animation_panel
        return [self.kernel_binding] + (preview.file_bindings() if preview else [])

    def _build_group(self, entries):
        if len(entries) == 1:
            section_id, _ = entries[0]
            tab = self._make_section_tab(section_id)
            if section_id == self.BATTLE_COMMAND_SECTION:
                panel = self.command_animation_panel = CommandAnimationPanel(self.game_data, self.file_registry)
                panel.file_bindings_changed.connect(self.file_bindings_changed.emit)
                tab.list_widget.currentRowChanged.connect(
                    lambda _row: self._refresh_command_preview())
                tab._field_widgets["behaves_like"][2].currentIndexChanged.connect(
                    lambda _index: self._refresh_command_preview())
                container = QWidget()
                row = QHBoxLayout(container)
                row.setContentsMargins(0, 0, 0, 0)
                row.addWidget(tab, 1)
                row.addWidget(panel)
                def preview_layout(active):
                    tab.set_render_preview_active(active)
                    panel.setMaximumWidth(16777215 if active else panel.minimumWidth())
                    row.setStretch(0, 0 if active else 1)
                    row.setStretch(1, 1 if active else 0)
                panel.preview_available_changed.connect(preview_layout)
                tab.command_type_requested.connect(self._add_command_type)
                preview_layout(False)
                return container
            if section_id == itemids.BATTLE_ITEM_SECTION:
                self._add_battle_use_button(tab)
            return tab
        inner = QTabWidget()
        inner.setTabPosition(QTabWidget.TabPosition.West)
        for section_id, label in entries:
            inner.addTab(self._make_section_tab(section_id), label)
        return inner

    def _refresh_command_preview(self):
        tab = self._section_tabs[self.BATTLE_COMMAND_SECTION]
        command = tab.current_entry_index()
        execution_type = tab._field_widgets["behaves_like"][2].currentData() \
            if command is not None and command >= self.VANILLA_COMMAND_COUNT else None
        self.command_animation_panel.set_command(command, execution_type)

    def _restore_current_tab(self):
        """Re-open on the section tab used last time (like Ifrit does)."""
        if self.settings is None:
            return
        index = self.settings.value(self.CURRENT_TAB_KEY, defaultValue=0, type=int)
        if 0 <= index < self.tabs.count():
            self.tabs.setCurrentIndex(index)

    def _commit_ability_tabs(self):
        """Write back the ability tabs' open forms and re-read their names.

        A name typed into a form only reaches the data when that form is written back,
        which otherwise waits for a row change - so an ability renamed and then looked
        for on the G-Forces tab (one tab away) would still show its old name in the
        learn-slot pickers."""
        if not self.loaded_filename:
            return
        for section_id in self._ability_section_ids():
            tab = self._section_tabs.get(section_id)
            if tab is not None:
                tab.commit()
        self._refresh_ability_names()

    def _remember_current_tab(self, index):
        self._commit_ability_tabs()
        self._commit_command_tab()
        self._commit_item_tabs()
        if self.settings is not None:
            self.settings.setValue(self.CURRENT_TAB_KEY, index)

    def _make_section_tab(self, section_id):
        config = dict(self._section_configs[str(section_id)])
        config["compact_form"] = section_id == self.BATTLE_COMMAND_SECTION
        config["entry_fallback_name"] = self._section_name(section_id)
        if section_id in self.REMOVABLE_ENGINE_SECTIONS:
            config["removed_entry_field"] = self.REMOVABLE_ENGINE_SECTIONS[section_id][0]
            config["removed_entry_value"] = self.REMOVED_ENTRY
        if section_id == self.BATTLE_COMMAND_SECTION:
            config["keep_removed_entries"] = True
            config["disable_entry_count"] = self.VANILLA_COMMAND_COUNT
        # _checked absorbs the bool QPushButton.clicked emits, which would land in sid
        add_entry_callback = (lambda _checked=False, sid=section_id: self._add_growable_entry(sid)) \
            if config.get("growable") else None
        remove_entry_callback = (lambda _checked=False, sid=section_id: self._remove_growable_entry(sid)) \
            if config.get("growable") else None
        static_config = self.kernel_manager.get_section_config(section_id) or {}
        if config.get("ability_pool"):
            pool_callback = lambda sid=section_id: self._ability_pool_status(sid)
            pool_tooltip = ("The category maximum assumes abilities in the other categories are removed.\n"
                            "Ability ID 0 (None) is always kept. The menu group's first ID must\n"
                            "stay below 128, and menu abilities have their own 32-entry limit.\n"
                            "The shared pool shows how many IDs are available right now;\n"
                            "removing an ability frees an ID for any category.")
        elif config.get("max_count"):
            pool_callback = lambda sid=section_id: self._entry_budget_status(sid)
            pool_tooltip = self.ENTRY_BUDGET_TOOLTIPS.get(section_id)
        else:
            pool_callback, pool_tooltip = None, None
        tab = KernelSectionTab(self.game_data, self.registry, config,
                               jump_callback=self._jump_to_section,
                               add_entry_callback=add_entry_callback,
                               remove_entry_callback=remove_entry_callback,
                               protected_count=self._protected_entry_count(section_id, static_config),
                               pool_callback=pool_callback,
                               pool_tooltip=pool_tooltip,
                               copy_between_entries=(static_config.get("number_sub_section") or 0) > 1
                               or bool(config.get("growable")))
        # A group paste / "Apply to..." writes the data without typing in a field, so it marks
        # the unsaved-edit state itself (dirty_state is installed on this tool by the main window).
        tab.edited.connect(self._mark_edited)
        if section_id == self.BATTLE_COMMAND_SECTION:
            # The data picker names each entry by the commands using it; a pick made on one
            # command is written back when another is selected, so relabel right then -
            # otherwise the entry just assigned still reads "(unused)".
            tab.list_widget.currentRowChanged.connect(lambda _row: self._refresh_command_lookups())
        self._section_tabs[section_id] = tab
        return tab

    def _mark_edited(self):
        dirty_state = getattr(self, "dirty_state", None)
        if dirty_state is not None:
            dirty_state.mark()

    def _section_name(self, section_id):
        return next(title for title, sections in TAB_LAYOUT
                    if any(sid == section_id for sid, _label in sections))

    def _entry_name(self, section_id, index, entry):
        return entry.display_name(f"{self._section_name(section_id)} {index}")

    def _protected_entry_count(self, section_id, static_config):
        """Keep fixed vanilla IDs, and the ability-zero sentinel, undeletable."""
        config = self._section_configs.get(str(section_id)) or {}
        if section_id in self.REMOVABLE_ENGINE_SECTIONS:
            return 1 if section_id == self.BATTLE_COMMAND_SECTION else 0
        if not config.get("ability_pool"):
            return static_config.get("number_sub_section") or 0
        return 1 if section_id == self._ability_section_ids()[0] else 0

    def _jump_to_section(self, section_id):
        # TAB_LAYOUT groups are all single-section today, so a top-level tab index is
        # enough; a future multi-section group would also need to pick the right inner tab.
        index = self._tab_index_by_section.get(section_id)
        if index is not None:
            self.tabs.setCurrentIndex(index)

    # ------------------------------------------------------------------ file IO
    def load_file(self, filename):
        self.loaded_filename = filename
        self.kernel_manager.load_file(filename)
        self._battle_data_kept = {}   # item id -> battle data switched off since the last save
        self._sync_battle_rows()
        self._populate_tabs()
        self.tabs.setEnabled(True)
        for button in self.elemdef_buttons.values():
            button.setEnabled(True)

    MAGIC_SECTION = 2
    GF_SECTION = 3
    # Where each "Elemental defense table..." button sits: under the kernel.bin data it extends.
    CRONOS_ELEMDEF_PLACES = {MAGIC_SECTION: "Junction (stats)", GF_SECTION: "General", CHARACTER_SECTION: "General"}

    def _add_cronos_extension(self):
        """Data the Cronos DLLs read beside kernel.bin, edited where the kernel.bin data it extends is:
        the elemental defense table opens from Magic > Junction (stats) (on its Magic page, under
        J-Elem defense) and from G-Forces > General (on its G-Forces page)."""
        self.elemdef_buttons = {}
        tips = {self.MAGIC_SECTION: "Per-element Elem-Def junction values, weaknesses included (Cronos "
                                    "NegativeElemDef.dll).\nReplaces the J-Elem defense / value above for "
                                    "every spell the table lists.",
                self.GF_SECTION: "Elemental defense a junctioned G-Force gives its character, per element, "
                                 "weaknesses included (Cronos NegativeElemDef.dll).",
                self.CHARACTER_SECTION: "The character's own base elemental defense, per element, weaknesses "
                                        "included, always active (Cronos NegativeElemDef.dll)."}
        for section_id, group_name in self.CRONOS_ELEMDEF_PLACES.items():
            tab = self._section_tabs.get(section_id)
            group = next((box for box in (tab.findChildren(QGroupBox) if tab else [])
                          if box.property("group_name") == group_name), None)
            if group is None:
                continue
            button = QPushButton("Elemental defense table...")
            button.setToolTip(tips[section_id])
            button.clicked.connect(lambda _checked=False, sid=section_id: self._open_elemdef_table(sid))
            button.setEnabled(False)   # needs the spells / GFs of a loaded kernel.bin
            cronos_box = QGroupBox("Cronos extension")
            cronos_layout = QHBoxLayout(cronos_box)
            cronos_layout.addWidget(button)
            cronos_layout.addStretch(1)
            group.layout().addWidget(cronos_box)
            self.elemdef_buttons[section_id] = button

    def _open_elemdef_table(self, section_id=MAGIC_SECTION):
        """The Cronos elemental defense table, for the spells and GFs of the kernel.bin loaded now."""
        magic_tab = self._section_tabs.get(self.MAGIC_SECTION)
        if not magic_tab:
            return
        magic_tab.commit()   # the table's "Fill spells from kernel.bin" reads what the Magic tab shows
        entries = {i: magic_tab._entries[i] for i in magic_tab._visible_indices}
        names = {i: (entry.get_text(0).strip() or f"(unnamed {i})") for i, entry in entries.items()}
        # The G-Forces section's own text is the summon's attack name ("Thunder Storm"): the GF
        # names (also the junction bit order, GF0 = Quezacotl) come from gforce.json.
        gf_names = {gf["id"]: gf["name"] for gf in self.game_data.gforce_data_json.get("gforce", [])
                    if 0 <= gf["id"] < GF_COUNT}
        page = {self.GF_SECTION: GF_PAGE, self.CHARACTER_SECTION: CHARACTER_PAGE}.get(section_id, MAGIC_PAGE)
        CronosElemDefDialog(self, entries, names, gf_names, self.default_character_names(), self.settings,
                            page).exec()

    def default_character_names(self):
        """The save's 8 character records under the game's default names. kernel.bin is no use here:
        Squall's and Rinoa's names are empty in it (the player names them). Laguna, Kiros and Ward use
        Squall, Zell and Irvine's records in the dreams."""
        names = self._section_configs.get(str(self.CHARACTER_SECTION), {}).get("entry_names", [])
        return {i: names[i] if i < len(names) else f"Character {i}" for i in range(CHARA_COUNT)}
    def _populate_tabs(self):
        by_id = {s.id: s for s in self.kernel_manager.section_list if s is not None}
        for section_id, tab in self._section_tabs.items():
            section = by_id.get(section_id)
            text_id = self._text_link.get(section_id, 0)
            text_section = by_id.get(text_id) if text_id else None
            tab.load_section(section, text_section)
        self._refresh_magic_names()
        self._refresh_ability_names()
        self._refresh_ability_pool()
        self._refresh_command_lookups()
        self._refresh_entry_budgets()
        self._refresh_slot_set_summaries()
        self._refresh_item_names()
        self._refresh_battle_use_button()

    def _refresh_slot_set_summaries(self):
        """Slot array's set-id fields reference Slot Sets (section 28), whose content is
        per-file - not something a static lookup table could describe. Build each set's
        actual spell list from what Slot Sets just loaded and push it into the Slot array
        tab's dropdowns, so you see e.g. "3: Cure x10, Curaga x5" instead of a bare index."""
        if 27 not in self._section_tabs or 28 not in self._section_tabs:
            return
        magic_lookup = self.registry.resolve("magic")
        magic_names = {e["value"]: e["name"] for e in magic_lookup["entries"]} if magic_lookup else {}
        entries = []
        for i, set_entry in enumerate(self._section_tabs[28]._entries):
            parts = []
            for slot in range(1, 9):
                magic_id = set_entry.get(f"magic_{slot}")
                count = set_entry.get(f"magic_{slot}_count")
                if count:
                    parts.append(f"{magic_names.get(magic_id, f'0x{magic_id:X}')} x{count}")
            entries.append({"value": i, "name": f"{i}: " + (", ".join(parts) if parts else "(empty)")})
        self.registry.set_dynamic("slot_set_summary", entries)
        self._section_tabs[27].refresh_dynamic_combos()

    def _refresh_magic_names(self):
        """The "magic" lookup (Slot Sets' spell picker) reflects whatever is ACTUALLY
        loaded right now - vanilla names you've renamed, and any spells added via
        "+ Add entry" - not the static vanilla magic.json list. Skips the same hidden
        id range the Magic tab itself hides (ids 64-79, GF-reserved) - picking one of
        those as a Slot Sets spell would be just as broken as editing it directly."""
        tab = self._section_tabs.get(2)
        if not tab:
            return
        entries = [{"value": i, "name": (tab._entries[i].get_text(0).strip() or f"(unnamed {i})")}
                  for i in tab._visible_indices]
        self.registry.set_dynamic("magic", entries)
        for other_tab in self._section_tabs.values():
            other_tab.refresh_dynamic_combos()

    # ---- the shared ability id space --------------------------------------------
    # Sections 12-18 are ONE array to the engine: getAbilityName(id) and friends index
    # them as a single 8-byte-entry array and decide the group from where the id falls,
    # so an entry appended to one section takes the id just after that section's last,
    # and every ability behind it shifts up by one. The budget they share is
    # kernel_bin_data.json's "ability_id_max" - 128, the width of a savegame's per-GF
    # learned-ability mask, and what FFNx's AddMoreAbility patch refuses to exceed.

    ABILITY_REF_SECTION = 3      # Junctionable GFs: the only section storing ability ids
    # Learned menu abilities also have their own 32-bit mask.
    MENU_ABILITY_SECTION = 18
    MAX_MENU_ABILITIES = 32

    def _ability_id_max(self):
        return self.game_data.kernel_data_json.get("ability_id_max", 128)

    def _ability_section_ids(self):
        """The sections sharing the ability id space, in id order."""
        return [section["id"] for section in self.game_data.kernel_data_json["sections"]
                if section.get("ability_pool")]

    def _section_by_id(self, section_id):
        return next((s for s in self.kernel_manager.section_list if s is not None and s.id == section_id), None)

    def _ability_entry_count(self, section_id):
        section = self._section_by_id(section_id)
        return len(section.get_subsection_list()) if section else 0

    def _ability_total(self):
        return sum(self._ability_entry_count(sid) for sid in self._ability_section_ids())

    def _ability_first_id(self, section_id):
        """Global id of a section's first entry: everything in the sections before it."""
        total = 0
        for sid in self._ability_section_ids():
            if sid == section_id:
                break
            total += self._ability_entry_count(sid)
        return total

    def _ability_category_max(self, section_id):
        """Maximum after removing the other groups' removable entries, not today's free IDs."""
        # Only the first group's None entry is protected. Even an empty menu group
        # must start at an ID below 128, leaving at most 127 entries before it.
        reserved_elsewhere = 0 if section_id == self._ability_section_ids()[0] else 1
        maximum = self._ability_id_max() - reserved_elsewhere
        if section_id == self.MENU_ABILITY_SECTION:
            return max(0, min(maximum, self.MAX_MENU_ABILITIES))
        return max(0, min(maximum, 127 - reserved_elsewhere))

    def _ability_pool_status(self, section_id=None):
        """(counter text, may another entry be added) for a pooled tab's Add button.
        The shared budget applies everywhere; the menu tab also shows its own cap,
        which can stop it while other sections still have room.

        The tabs are built before any kernel.bin is open, when every section is empty -
        so with no file loaded this says nothing rather than claiming all 128 ids are
        free."""
        if not self.loaded_filename:
            return "", False
        used, maximum = self._ability_total(), self._ability_id_max()
        text = f"{used} / {maximum} ability ids - {maximum - used} left"
        if section_id is not None:
            entries = self._ability_entry_count(section_id)
            text = (f"{entries} entries - category maximum {self._ability_category_max(section_id)}\n"
                    f"Shared pool: {text}")
        can_add = used < maximum
        if section_id is not None and section_id != self.MENU_ABILITY_SECTION and self._ability_first_id(self.MENU_ABILITY_SECTION) >= 127:
            text += "  (menu group start must stay below 128)"
            can_add = False
        if section_id == self.MENU_ABILITY_SECTION:
            menu = self._ability_entry_count(section_id)
            text += f"  (menu {menu} / {self.MAX_MENU_ABILITIES})"
            can_add = can_add and menu < self.MAX_MENU_ABILITIES
        return text, can_add

    def _refresh_ability_pool(self):
        for sid in self._ability_section_ids():
            tab = self._section_tabs.get(sid)
            if tab:
                tab.refresh_pool_status()

    def _refresh_ability_names(self):
        """The "junctionable_ability" lookup (the GF learn-list pickers on the
        G-Forces tab) reflects what is ACTUALLY loaded - renamed abilities and any
        added through "+ Add entry" - rather than the static vanilla list, and stays
        correct after a renumbering."""
        entries, ability_id = [], 0
        for sid in self._ability_section_ids():
            tab = self._section_tabs.get(sid)
            if not tab:
                return
            for index in range(len(tab._entries)):
                name = self._entry_name(sid, ability_id, tab._entries[index])
                entries.append({"value": ability_id, "name": name})
                ability_id += 1
        self.registry.set_dynamic("junctionable_ability", entries)
        ref_tab = self._section_tabs.get(self.ABILITY_REF_SECTION)
        if ref_tab:
            ref_tab.refresh_dynamic_combos()

    def _ability_reference_entries(self):
        """Every (entry, field name) in section 3 that stores an ability id."""
        section = self._section_by_id(self.ABILITY_REF_SECTION)
        config = self._section_configs.get(str(self.ABILITY_REF_SECTION))
        if section is None or config is None or not section.section_text_linked:
            return
        fields = config["fields"]
        names = [f["name"] for f in fields if f.get("lookup") == "junctionable_ability"]
        nb_text = len(config.get("text_labels", [])) or 1
        for index, subsection in enumerate(section.get_subsection_list()):
            entry = KernelEntry(subsection, section.section_text_linked, nb_text, index,
                                fields, self.game_data)
            for name in names:
                yield entry, name

    def _count_ability_references(self, ability_id):
        return sum(1 for entry, name in self._ability_reference_entries() if entry.get(name) == ability_id)

    def _renumber_ability_references(self, from_id, delta, removed_id=None):
        """Follow an insert or delete through every stored ability id: ids at or past
        ``from_id`` move by ``delta``, and any slot still pointing at ``removed_id``
        falls back to 0 (None) because the ability it named is gone.

        The G-Forces tab keeps its selected GF in an open form, which is written back on
        the next row change or save: flushed before the renumbering and rebuilt after it,
        or it would restore that GF's old ids (the selected GF - Quezacotl by default -
        kept its whole learn list un-renumbered)."""
        ref_tab = self._section_tabs.get(self.ABILITY_REF_SECTION)
        if ref_tab is not None:
            ref_tab.commit()
        cleared = 0
        for entry, name in self._ability_reference_entries():
            value = entry.get(name)
            if removed_id is not None and value == removed_id:
                entry.set(name, 0)
                cleared += 1
            elif value >= from_id:
                entry.set(name, value + delta)
        ref_section = self._section_by_id(self.ABILITY_REF_SECTION)
        if ref_tab is not None and ref_section is not None:
            ref_tab.load_section(ref_section, ref_section.section_text_linked)
        return cleared

    # ---- battle commands and their command ability data ------------------------
    # With FFNx's AddMoreCommand patch, the battle commands (section 1) and the command
    # ability data (section 11) may grow. A command ability names a battle command by
    # id, and a battle command names its data entry by id. The engine has no code for a
    # command id past the vanilla 39, so FFNx runs a new one as one of the ten commands
    # whose effect comes entirely from their data entry - "Behaves like" picks which.

    BATTLE_COMMAND_SECTION = 1
    COMMAND_DATA_SECTION = 11
    COMMAND_ABILITY_SECTION = 13
    VANILLA_COMMAND_COUNT = 39
    NO_COMMAND_DATA = 0xFF
    # Defend, Mad Rush, Treatment, Recover, Revive, Doom, Kamikaze, Trance, LV Down, LV Up.
    DATA_DRIVEN_COMMANDS = (0x17, 0x18, 0x19, 0x1A, 0x1B, 0x1E, 0x1F, 0x20, 0x21, 0x22)
    DEFAULT_FAMILY = 0x18   # Mad Rush: what 0 in "Behaves like" means, and a new command's template

    ENTRY_BUDGET_TOOLTIPS = {
        BATTLE_COMMAND_SECTION:
            "FFNx's AddMoreCommand loader takes up to 176 battle commands: command ids\n"
            "from 0xB0 up belong to the engine itself (Renzokuken finisher, G-Force...).\n"
            "A new command copies the selected data-driven command (otherwise Mad Rush).\n"
            "Pick its effect data, then point a command ability at it.",
        COMMAND_DATA_SECTION:
            "Up to 255 entries: a battle command stores which one it uses in a byte where\n"
            "0xFF means \"none\".",
        itemids.BATTLE_ITEM_SECTION:
            "FFNx's AddMoreItems gives battle use to items 199-254 (255 is the engine's\n"
            "\"no item\" result of a random item pick). Every added item has a record here,\n"
            "greyed until \"Usable in battle\" is on. Its name and description are on Item Names\n"
            "(this tab's own name of an added item is never shown). \"+ Add entry\" adds a new\n"
            "item on both tabs; only the last item can be removed, as items are stored by id.",
        itemids.NON_BATTLE_ITEM_SECTION:
            "FFNx's AddMoreItems takes up to 57 added items, ids 199-255. Their field use\n"
            "comes from mitem.bin (Kadowaki) and their price from price.bin (Siren), both\n"
            "extended to the same id; battle use is switched on, on Battle Items. Only the last\n"
            "item can be removed: inventories, shops and drops store items by id.",
    }

    REMOVED_ENTRY = 0xFE
    REMOVABLE_ENGINE_SECTIONS = {1: ("unused_0x07", 39), 11: ("unknown_0x02", 12)}

    def _entry_removed(self, section_id, index, entry=None):
        spec = self.REMOVABLE_ENGINE_SECTIONS.get(section_id)
        if spec is None:
            return False
        if entry is None:
            entries = self._section_entries(section_id)
            if not 0 <= index < len(entries):
                return False
            entry = entries[index]
        return entry.get(spec[0]) == self.REMOVED_ENTRY

    def _entry_budget_status(self, section_id):
        """(counter text, may another entry be added) for a section with a "max_count"."""
        if not self.loaded_filename:
            return "", False
        if section_id == itemids.BATTLE_ITEM_SECTION:
            added = len(self._section_entries(section_id)) - itemids.VANILLA_BATTLE_ITEMS
            battle = sum(1 for item_id in range(itemids.FIRST_ADDED_ITEM, itemids.LAST_ITEM_ID)
                         if self.item_has_battle_use(item_id))
            next_id = itemids.item_count(self._item_name_rows())
            return (f"{battle} of {added} added items usable in battle",
                    next_id <= itemids.LAST_ITEM_ID)
        used = self._ability_entry_count(section_id)
        maximum = self._section_configs[str(section_id)]["max_count"]
        removed = sum(self._entry_removed(section_id, i, e)
                      for i, e in enumerate(self._section_entries(section_id)))
        text = (f"{used - removed} active / {used} slots ({removed} disabled; maximum {maximum})"
                if removed and section_id == self.BATTLE_COMMAND_SECTION else
                f"{used - removed} entries / {maximum} slots ({removed} reserved after removal)"
                if removed else f"{used} / {maximum} entries - {maximum - used} left")
        return text, used < maximum

    def _refresh_entry_budgets(self):
        for section_id, tab in self._section_tabs.items():
            if self._section_configs[str(section_id)].get("max_count"):
                tab.refresh_pool_status()

    def _section_entries(self, section_id):
        """A KernelEntry for every entry of a data section, straight from the data."""
        section = self._section_by_id(section_id)
        config = self._section_configs.get(str(section_id))
        if section is None or config is None:
            return []
        nb_text = len(config.get("text_labels", [])) or 1
        return [KernelEntry(subsection, section.section_text_linked, nb_text, index,
                            config["fields"], self.game_data)
                for index, subsection in enumerate(section.get_subsection_list())]

    def _battle_command_names(self):
        tab = self._section_tabs.get(self.BATTLE_COMMAND_SECTION)
        if not tab:
            return []
        return [self._entry_name(self.BATTLE_COMMAND_SECTION, i, entry)
                for i, entry in enumerate(tab._entries)]

    def _commit_command_tab(self):
        """Write back the battle command form, so a renamed or re-pointed command shows
        up in the pickers of the other tabs."""
        if not self.loaded_filename:
            return
        tab = self._section_tabs.get(self.BATTLE_COMMAND_SECTION)
        if tab is not None:
            tab.commit()
        self._refresh_command_lookups()

    def _refresh_command_data_enabled(self):
        """Only commands with a fixed effect use this picker during execution."""
        tab = self._section_tabs.get(self.BATTLE_COMMAND_SECTION)
        if tab is None:
            return
        index = tab.current_entry_index()
        uses_data = index is not None and (
            index in (7, 29) or index in self.DATA_DRIVEN_COMMANDS
            or index >= self.VANILLA_COMMAND_COUNT)
        tab._field_widgets["ability_data_id"][2].setEnabled(tab._unlock_all or uses_data)

    def _refresh_command_lookups(self):
        """Three pickers depend on what is loaded, not on the vanilla lists: the battle
        command a command ability grants, the data entry a battle command uses (named by
        the commands that use it), and the family a new command behaves like."""
        names = self._battle_command_names()
        if not names:
            return
        commands = [{"value": i, "name": f"{i}: {name or '(unnamed)'}"} for i, name in enumerate(names)
                    if not self._entry_removed(self.BATTLE_COMMAND_SECTION, i)]
        self.registry.set_dynamic("battle_command", commands)

        users = {}
        for index, entry in enumerate(self._section_entries(self.BATTLE_COMMAND_SECTION)):
            if self._entry_removed(self.BATTLE_COMMAND_SECTION, index, entry):
                continue
            users.setdefault(entry.get("ability_data_id"), []).append(names[index] or f"#{index}")
        data = [{"value": i, "name": f"{i}: " + (", ".join(users.get(i, []))
                                               or f"{self._section_name(self.COMMAND_DATA_SECTION)} (unused)")}
                for i in range(self._ability_entry_count(self.COMMAND_DATA_SECTION))
                if not self._entry_removed(self.COMMAND_DATA_SECTION, i)]
        data.append({"value": self.NO_COMMAND_DATA, "name": "None (chosen at runtime)"})
        self.registry.set_dynamic("command_ability_ref", data)

        used_types = {entry.get("behaves_like") for i, entry in enumerate(
            self._section_entries(self.BATTLE_COMMAND_SECTION))
            if i >= self.VANILLA_COMMAND_COUNT and not self._entry_removed(self.BATTLE_COMMAND_SECTION, i)}
        self.registry.set_dynamic("command_family", command_type_options(used_types))

        for tab in self._section_tabs.values():
            tab.refresh_dynamic_combos()
        self._refresh_command_data_enabled()

    def _add_command_type(self):
        """Allocate an execution ID; its switch case belongs to the user's independent DLL."""
        tab = self._section_tabs[self.BATTLE_COMMAND_SECTION]
        index = tab.current_entry_index()
        if index is None or index < self.VANILLA_COMMAND_COUNT or tab.entry_disabled(index):
            return
        tab.commit()
        used = {entry.get("behaves_like") for entry in tab._entries[self.VANILLA_COMMAND_COUNT:]}
        code = next((value for value in range(FIRST_DLL_TYPE, LAST_DLL_TYPE + 1) if value not in used), None)
        if code is None:
            QMessageBox.information(self, "Execution IDs", "No free DLL execution IDs remain below 0xB0.")
            return
        tab._entries[index].set("behaves_like", code)
        self._refresh_command_lookups()
        combo = tab._field_widgets["behaves_like"][2]
        position = combo.findData(code)
        combo.setCurrentIndex(position)
        tab.commit()
        combo.activated.emit(position)
        tab.edited.emit()

    def _init_new_battle_command(self, index, selected):
        """Copy an eligible selected command; use Mad Rush for menu-driven commands."""
        entries = self._section_entries(self.BATTLE_COMMAND_SECTION)
        source = selected if selected is not None else self.DEFAULT_FAMILY
        family = source if source < self.VANILLA_COMMAND_COUNT else (entries[source].get("behaves_like") or self.DEFAULT_FAMILY)
        dll_type = FIRST_DLL_TYPE <= family <= LAST_DLL_TYPE
        if not dll_type and (family not in self.DATA_DRIVEN_COMMANDS
                             or entries[source].get("ability_data_id") == self.NO_COMMAND_DATA):
            source = family = self.DEFAULT_FAMILY
        subsections = self._section_by_id(self.BATTLE_COMMAND_SECTION).get_subsection_list()
        template = subsections[source].get_data_list()[-1].get_data_hex()
        new = subsections[index].get_data_list()[-1].get_data_hex()
        new[:] = template
        entries[index].set("behaves_like", family)
        if self._entry_removed(self.COMMAND_DATA_SECTION, entries[index].get("ability_data_id")):
            entries[index].set("ability_data_id", self.NO_COMMAND_DATA)

    def _renumber_command_references(self, section_id, removed, compact=True):
        """Follow a deleted battle command or data entry through what points at it: ids
        past it move down one, and what pointed at it falls back to "nothing" (command 0 /
        no data). Returns how many references were cleared."""
        if section_id == self.BATTLE_COMMAND_SECTION:
            refs, field, fallback = self.COMMAND_ABILITY_SECTION, "battle_command_index", 0
        else:
            refs, field, fallback = self.BATTLE_COMMAND_SECTION, "ability_data_id", self.NO_COMMAND_DATA
        cleared = 0
        for entry in self._section_entries(refs):
            value = entry.get(field)
            if value == removed:
                entry.set(field, fallback)
                cleared += 1
            elif compact and value != self.NO_COMMAND_DATA and value > removed:
                entry.set(field, value - 1)
        return cleared

    def _count_command_references(self, section_id, index):
        if section_id == self.BATTLE_COMMAND_SECTION:
            refs, field = self.COMMAND_ABILITY_SECTION, "battle_command_index"
        else:
            refs, field = self.BATTLE_COMMAND_SECTION, "ability_data_id"
        return sum(1 for entry in self._section_entries(refs) if entry.get(field) == index)

    def command_problems(self):
        """What FFNx's AddMoreCommand loader would refuse in the current file. It drops
        the whole extension on any of these, so they are shown before saving."""
        problems = []
        names = self._battle_command_names()
        data_count = self._ability_entry_count(self.COMMAND_DATA_SECTION)
        for index, entry in enumerate(self._section_entries(self.BATTLE_COMMAND_SECTION)):
            if self._entry_removed(self.BATTLE_COMMAND_SECTION, index, entry):
                continue
            label = f"Battle command {index} ({names[index] if index < len(names) and names[index] else 'unnamed'})"
            data_id = entry.get("ability_data_id")
            if data_id != self.NO_COMMAND_DATA and (data_id >= data_count or self._entry_removed(self.COMMAND_DATA_SECTION, data_id)):
                problems.append(f"{label} uses command ability data {data_id}, but there are only {data_count}.")
            if index < self.VANILLA_COMMAND_COUNT:
                continue
            if data_id == self.NO_COMMAND_DATA:
                problems.append(f"{label} has no command ability data - a new command needs one.")
            family = entry.get("behaves_like")
            if family and family not in self.DATA_DRIVEN_COMMANDS:
                problems.append(f"{label} uses execution ID {family}, which standard FFNx's AddMoreCommand "
                                "does not accept. An independent DLL must implement this ID and handle "
                                "command dispatch and loader compatibility.")
        return problems

    # ---- items (FFNx AddMoreItems) ----------------------------------------------
    # Item ids are positions in two sections: battle records 0-32 (section 8) and the names of
    # 33-198 (section 9). AddMoreItems appends to both: section 9 row k is always item 33 + k,
    # and the added battle records 33 + k are items 199 + k - so an added battle item needs its
    # Item Names row, which holds its name (FF8GameData/itemids.py).

    def _item_name_rows(self):
        return self._ability_entry_count(itemids.NON_BATTLE_ITEM_SECTION)

    def _battle_item_rows(self):
        return self._ability_entry_count(itemids.BATTLE_ITEM_SECTION)

    def item_problems(self):
        """What FFNx's AddMoreItems loader would refuse in the current file (it then rejects the
        whole kernel.bin), shown before saving."""
        if not self.loaded_filename:
            return []
        return itemids.item_problems(self._battle_item_rows(), self._item_name_rows())

    def _commit_item_tabs(self):
        if not self.loaded_filename:
            return
        for section_id in (itemids.BATTLE_ITEM_SECTION, itemids.NON_BATTLE_ITEM_SECTION):
            tab = self._section_tabs.get(section_id)
            if tab is not None:
                tab.commit()
        self._refresh_item_names()

    def _refresh_item_names(self):
        """The "item" lookup (Shot's ammo picker) offers the items this file holds - renamed,
        and ids 199-255 once added - and the added battle items show their Item Names name."""
        battle_tab = self._section_tabs.get(itemids.BATTLE_ITEM_SECTION)
        names_tab = self._section_tabs.get(itemids.NON_BATTLE_ITEM_SECTION)
        if not self.loaded_filename or battle_tab is None or names_tab is None:
            return
        fallback = {entry["id"]: entry["name"] for entry in self.game_data.item_data_json["items"]}
        names = {}
        for index, entry in enumerate(battle_tab._entries[:itemids.VANILLA_BATTLE_ITEMS]):
            names[index] = entry.get_text(0).strip() if entry.has_text(0) else ""
        for index, entry in enumerate(names_tab._entries):
            names[itemids.non_battle_row_to_item_id(index)] = entry.get_text(0).strip() if entry.has_text(0) else ""
        entries = [{"value": item_id, "name": name or fallback.get(item_id) or f"Item {item_id}"}
                   for item_id, name in sorted(names.items())]
        self.registry.set_dynamic("item", entries)
        by_id = {entry["value"]: entry["name"] for entry in entries}
        added_rows = range(itemids.VANILLA_BATTLE_ITEMS, len(battle_tab._entries))
        # An added battle item's name and description are its Item Names row's (the game never
        # shows the record's own): shown greyed in its fields, edited on Item Names.
        texts = {}
        for row in added_rows:
            name_row = itemids.battle_row_to_item_id(row) - itemids.VANILLA_BATTLE_ITEMS
            entry = names_tab._entries[name_row] if name_row < len(names_tab._entries) else None
            texts[row] = [entry.get_text(i) if entry is not None and entry.has_text(i) else ""
                          for i in range(len(names_tab.text_labels))]
        battle_tab.set_borrowed_names({row: by_id.get(itemids.battle_row_to_item_id(row), "") for row in added_rows},
                                      texts, source="Item Names")
        for tab in self._section_tabs.values():
            tab.refresh_dynamic_combos()

    def item_has_battle_use(self, item_id):
        """Whether an item has a real battle record (not none, not a placeholder)."""
        row = itemids.item_id_to_battle_row(item_id)
        entries = self._section_entries(itemids.BATTLE_ITEM_SECTION)
        return row is not None and row < len(entries) and any(entries[row]._payload)

    def _item_texts_per_entry(self, section_id):
        return len(self._section_configs[str(section_id)].get("text_labels") or []) or 1

    def _sync_battle_rows(self):
        """Every added item that can have a battle record (199-254) has one, a placeholder (all
        zero: no battle use, greyed on Battle Items) unless it is usable in battle; the records of
        items that no longer exist go. So both tabs list the same items."""
        section = self._section_by_id(itemids.BATTLE_ITEM_SECTION)
        if section is None or section.section_text_linked is None:
            return
        text_section = section.section_text_linked
        nb_text = self._item_texts_per_entry(itemids.BATTLE_ITEM_SECTION)
        added = max(0, min(self._item_name_rows() - itemids.VANILLA_NON_BATTLE_ITEMS,
                           itemids.MAX_ADDED_BATTLE_ITEMS))
        target = itemids.VANILLA_BATTLE_ITEMS + added
        while len(section.get_subsection_list()) < target:
            section.append_blank_subsection()
            for _ in range(nb_text):
                text_section.add_text(bytearray([0x00]))
        entries = self._section_entries(itemids.BATTLE_ITEM_SECTION)
        while len(entries) > target and not any(entries[-1]._payload):
            section.remove_subsection(len(entries) - 1)
            for _ in range(nb_text):
                text_section.remove_text((len(entries) - 1) * nb_text)
            entries = self._section_entries(itemids.BATTLE_ITEM_SECTION)

    def set_item_battle_use(self, item_id, usable):
        """Give an added item (199-254) battle use - its record gets back the data it had before
        it was switched off this session, or the Potion's - or take it away: the record becomes a
        placeholder, its data kept until the next save in case it is switched back on.
        Returns whether anything changed."""
        row = itemids.item_id_to_battle_row(item_id)
        section = self._section_by_id(itemids.BATTLE_ITEM_SECTION)
        tab = self._section_tabs.get(itemids.BATTLE_ITEM_SECTION)
        if row is None or row < itemids.VANILLA_BATTLE_ITEMS or section is None or tab is None \
                or row >= len(section.get_subsection_list()) or usable == self.item_has_battle_use(item_id):
            return False
        tab.commit()
        subsections = section.get_subsection_list()
        payload = subsections[row].get_data_list()[-1].get_data_hex()
        if usable:
            payload[:] = self._battle_data_kept.pop(item_id, None) or \
                subsections[1].get_data_list()[-1].get_data_hex()
        else:
            self._battle_data_kept[item_id] = bytes(payload)
            payload[:] = bytes(len(payload))
        tab.load_section(section, section.section_text_linked)
        if row in tab._visible_indices:
            tab.list_widget.setCurrentRow(tab._visible_indices.index(row))
        self._refresh_entry_budgets()
        self._refresh_item_names()
        self._refresh_battle_use_button()
        self._mark_edited()
        return True

    def _add_battle_use_button(self, tab):
        """The "Usable in battle" switch under Battle Items' Add / Remove entry."""
        button = self.battle_use_button = QPushButton("Usable in battle")
        button.setCheckable(True)
        button.setToolTip(
            "An item added to the game (199-254) has a Battle Items record, greyed while it is not\n"
            "usable in battle. Switching this on makes it a battle item (FFNx AddMoreItems): it\n"
            "appears in the battle Item menu, after the game's own battle items, with the battle data\n"
            "edited here (the Potion's at first). Switching it off makes it a field item again; its\n"
            "battle data is erased when the file is saved. 255 can never be a battle item.")
        button.clicked.connect(self._on_battle_use_clicked)
        tab.list_widget.currentRowChanged.connect(lambda _row: self._refresh_battle_use_button())
        tab.add_list_widget(button)
        self._refresh_battle_use_button()

    def _selected_battle_item_id(self):
        tab = self._section_tabs.get(itemids.BATTLE_ITEM_SECTION)
        index = tab.current_entry_index() if tab else None
        return None if index is None else itemids.battle_row_to_item_id(index)

    def _refresh_battle_use_button(self):
        button = getattr(self, "battle_use_button", None)
        if button is None:
            return
        item_id = self._selected_battle_item_id()
        added = bool(self.loaded_filename) and item_id is not None and item_id >= itemids.FIRST_ADDED_ITEM
        with QSignalBlocker(button):
            button.setChecked(bool(added and self.item_has_battle_use(item_id)))
        button.setEnabled(added)

    def _on_battle_use_clicked(self, usable):
        item_id = self._selected_battle_item_id()
        if item_id is None:
            return
        if not usable and QMessageBox.question(
                self, "Field item",
                f"Item {item_id} will no longer be usable in battle. All its battle data will be lost "
                "when the file is saved. Continue?") != QMessageBox.StandardButton.Yes:
            self._refresh_battle_use_button()
            return
        self.set_item_battle_use(item_id, usable)

    def _add_item(self, section_id):
        """"+ Add entry" on either item tab: a new item at the next free id, with its name row and,
        up to 254, its Battle Items record - not usable in battle until switched on."""
        if self._item_name_rows() >= itemids.MAX_NON_BATTLE_ITEM_ROWS:
            return
        names_section = self._section_by_id(itemids.NON_BATTLE_ITEM_SECTION)
        names_tab = self._section_tabs[itemids.NON_BATTLE_ITEM_SECTION]
        battle_section = self._section_by_id(itemids.BATTLE_ITEM_SECTION)
        battle_tab = self._section_tabs[itemids.BATTLE_ITEM_SECTION]
        if names_section is None or names_section.section_text_linked is None:
            return
        names_tab.commit()
        battle_tab.commit()
        text_section = names_section.section_text_linked
        nb_text = self._item_texts_per_entry(itemids.NON_BATTLE_ITEM_SECTION)
        names_section.append_blank_subsection()
        for _ in range(nb_text):
            text_section.add_text(bytearray([0x00]))
        new_row = len(names_section.get_subsection_list()) - 1
        item_id = itemids.non_battle_row_to_item_id(new_row)
        text_section.get_text_list()[new_row * nb_text].set_str(f"Item {item_id}")
        self._sync_battle_rows()
        names_tab.load_section(names_section, text_section)
        battle_tab.load_section(battle_section, battle_section.section_text_linked)
        self._select_item(section_id, item_id)
        self._after_item_change()

    def _remove_last_item(self, section_id):
        """"- Remove entry" on either item tab: the last added item goes, name and battle record
        (an id is a position: one in the middle would shift every item after it)."""
        item_id = itemids.item_count(self._item_name_rows()) - 1
        if item_id < itemids.FIRST_ADDED_ITEM:
            return
        if section_id == itemids.BATTLE_ITEM_SECTION and self._selected_battle_item_id() != item_id:
            QMessageBox.information(self, "Remove item",
                                    f"Only the last item, {item_id}, can be removed: its id is its place.")
            return
        if self.item_has_battle_use(item_id) and QMessageBox.question(
                self, "Remove item",
                f"Item {item_id} is usable in battle. Removing it loses its name and its battle data. "
                "Continue?") != QMessageBox.StandardButton.Yes:
            return
        names_section = self._section_by_id(itemids.NON_BATTLE_ITEM_SECTION)
        names_tab = self._section_tabs[itemids.NON_BATTLE_ITEM_SECTION]
        battle_section = self._section_by_id(itemids.BATTLE_ITEM_SECTION)
        battle_tab = self._section_tabs[itemids.BATTLE_ITEM_SECTION]
        names_tab.commit()
        battle_tab.commit()
        row = itemids.item_id_to_battle_row(item_id)
        if row is not None and row < len(battle_section.get_subsection_list()):
            payload = battle_section.get_subsection_list()[row].get_data_list()[-1].get_data_hex()
            payload[:] = bytes(len(payload))      # so _sync_battle_rows drops the record
        self._battle_data_kept.pop(item_id, None)
        nb_text = self._item_texts_per_entry(itemids.NON_BATTLE_ITEM_SECTION)
        last = len(names_section.get_subsection_list()) - 1
        names_section.remove_subsection(last)
        for _ in range(nb_text):
            names_section.section_text_linked.remove_text(last * nb_text)
        self._sync_battle_rows()
        names_tab.load_section(names_section, names_section.section_text_linked)
        battle_tab.load_section(battle_section, battle_section.section_text_linked)
        self._select_item(section_id, item_id - 1)
        self._after_item_change()

    def _select_item(self, section_id, item_id):
        tab = self._section_tabs[section_id]
        row = (itemids.item_id_to_battle_row(item_id) if section_id == itemids.BATTLE_ITEM_SECTION
               else item_id - itemids.VANILLA_BATTLE_ITEMS)
        if row is not None and row in tab._visible_indices:
            tab.list_widget.setCurrentRow(tab._visible_indices.index(row))
        elif tab._visible_indices:
            tab.list_widget.setCurrentRow(len(tab._visible_indices) - 1)

    def _after_item_change(self):
        self._refresh_entry_budgets()
        self._refresh_item_names()
        self._refresh_battle_use_button()
        self._mark_edited()

    def _add_growable_entry(self, section_id):
        """Append one new blank entry to a "growable" data section (today, only Magic -
        kernel_bin_data.json "growable": true) and its linked name/description text,
        then reload that tab and select the new entry. If the section reserves an id
        range for something else (Magic: ids 64-79 belong to GFs), crossing into it
        auto-inserts the required placeholder rows first so id numbering stays correct -
        the caller always ends up with exactly one new, real, editable entry. The tab
        hides that id range from its list entirely (kernel_section_fields.json's
        hidden_id_start/count), so the placeholder rows never actually appear - they're
        only labelled here for anyone inspecting the raw file outside SolomonRing."""
        if section_id in (itemids.BATTLE_ITEM_SECTION, itemids.NON_BATTLE_ITEM_SECTION):
            self._add_item(section_id)
            return
        section = next((s for s in self.kernel_manager.section_list if s is not None and s.id == section_id), None)
        tab = self._section_tabs.get(section_id)
        # Command ability data is the one growable section without any text.
        if section is None or tab is None or (tab.text_labels and section.section_text_linked is None):
            return
        cfg = self.kernel_manager.get_section_config(section_id)
        text_section = section.section_text_linked if tab.text_labels else None
        nb_text = len(tab.text_labels) or 1
        # The shown entry's form is only written back on a row change, and load_section() below
        # rebuilds every entry from the data: write it first, or a name/value just typed (a spell
        # renamed, then "+ Add entry") is lost.
        tab.commit()
        selected = tab.current_entry_index()
        pooled = bool(cfg.get("ability_pool"))
        # The seven ability sections share one id space, and the menu group has a cap
        # of its own; the button greys out when either is reached, but a stale click
        # (or a caller that is not the button) must not grow it anyway.
        if pooled and not self._ability_pool_status(section_id)[1]:
            return
        if self._section_configs[str(section_id)].get("max_count") and not self._entry_budget_status(section_id)[1]:
            return
        # The new entry goes right after the selected one (at the end when nothing is
        # selected), takes that id + 1, and pushes every ability id from there on up by
        # one - which the GF learn lists have to follow.
        insert_index = None
        new_ability_id = None
        if pooled:
            current = tab.current_entry_index()
            insert_index = current + 1 if current is not None and current >= 0 \
                else len(section.get_subsection_list())
            new_ability_id = self._ability_first_id(section_id) + insert_index

        def _append_one():
            section.append_blank_subsection()
            for _ in range(nb_text if text_section is not None else 0):
                text_section.add_text(bytearray([0x00]))

        def _insert_one(index):
            section.insert_blank_subsection(index)
            for i in range(nb_text if text_section is not None else 0):
                text_section.insert_text(index * nb_text + i, bytearray([0x00]))

        pad = 0
        if pooled:
            _insert_one(insert_index)
        else:
            gf_start = cfg.get("gf_reserved_start")
            gf_count = cfg.get("gf_reserved_count") or 0
            n = len(section.get_subsection_list())
            pad = gf_count if (gf_start is not None and n == gf_start) else 0
            for _ in range(pad):
                _append_one()
            _append_one()

        # Label the auto-inserted placeholder rows BEFORE load_section() builds the list
        # widget's item text from them, so they show as reserved from the moment they
        # appear rather than only after being clicked into once.
        if pad:
            text_list = text_section.get_text_list()
            new_total = len(section.get_subsection_list())
            for entry_index in range(new_total - pad - 1, new_total - 1):
                text_list[entry_index * nb_text].set_str("(reserved for GF - do not use)")

        if pooled:
            self._renumber_ability_references(new_ability_id, 1)
        new_index = insert_index if pooled else len(section.get_subsection_list()) - 1
        if section_id == self.BATTLE_COMMAND_SECTION:
            self._init_new_battle_command(new_index, selected)
        elif section_id == self.COMMAND_DATA_SECTION and selected is not None:
            # A new effect starts as a copy of the selected one.
            subsections = section.get_subsection_list()
            subsections[new_index].get_data_list()[-1].get_data_hex()[:] = subsections[selected].get_data_list()[-1].get_data_hex()
        if text_section is not None:
            name_id = new_ability_id if pooled else tab.entry_id(new_index)
            prefix = "Item" if section_id == itemids.NON_BATTLE_ITEM_SECTION else self._section_name(section_id)
            text_section.get_text_list()[new_index * nb_text].set_str(f"{prefix} {name_id}")

        tab.load_section(section, text_section)
        if insert_index is not None and insert_index in tab._visible_indices:
            tab.list_widget.setCurrentRow(tab._visible_indices.index(insert_index))
        else:
            tab.list_widget.setCurrentRow(len(tab._visible_indices) - 1)
        if section_id == 2:
            self._refresh_magic_names()
        if pooled:
            self._refresh_ability_names()
            self._refresh_ability_pool()
        if section_id in (self.BATTLE_COMMAND_SECTION, self.COMMAND_DATA_SECTION):
            self._refresh_command_lookups()
            self._refresh_entry_budgets()
        if section_id in (itemids.BATTLE_ITEM_SECTION, itemids.NON_BATTLE_ITEM_SECTION):
            self._refresh_entry_budgets()
            self._refresh_item_names()

    def _remove_growable_entry(self, section_id):
        """Delete the selected entry of a "growable" data section together with its linked
        name/description text. Ability sections compact and free their shared IDs.
        Original engine command/data rows retain reserved slots. Entries after
        the deleted one shift down one id, exactly as they would in any array. If that leaves the
        section with nothing above the GF-reserved block but the placeholder rows themselves, they
        go too, so the file never keeps a tail of reserved-only entries."""
        section = next((s for s in self.kernel_manager.section_list if s is not None and s.id == section_id), None)
        tab = self._section_tabs.get(section_id)
        if section is None or tab is None or (tab.text_labels and section.section_text_linked is None):
            return
        cfg = self.kernel_manager.get_section_config(section_id) or {}
        entry_index = tab.current_entry_index()
        if not tab.can_remove(entry_index):
            return
        if section_id in (itemids.BATTLE_ITEM_SECTION, itemids.NON_BATTLE_ITEM_SECTION):
            self._remove_last_item(section_id)
            return
        if section_id == self.BATTLE_COMMAND_SECTION and entry_index < self.VANILLA_COMMAND_COUNT:
            tab.commit()
            entry = self._section_entries(section_id)[entry_index]
            entry.set("unused_0x07", 0 if self._entry_removed(section_id, entry_index, entry)
                      else self.REMOVED_ENTRY)
            tab.load_section(section, section.section_text_linked)
            self._refresh_command_lookups()
            self._refresh_entry_budgets()
            self._mark_edited()
            return
        tab.commit()  # same as adding: load_section() below rebuilds the entries from the data
        text_section = section.section_text_linked if tab.text_labels else None
        nb_text = len(tab.text_labels) or 1
        commands = section_id in (self.BATTLE_COMMAND_SECTION, self.COMMAND_DATA_SECTION)
        if commands:
            # A command ability granting this command, or a command using this data
            # entry, would silently pick up whatever slides into the id - clear them.
            used_by = self._count_command_references(section_id, entry_index)
            what = ("command abilit(ies) grant this command. Removing it sets them to command 0"
                    if section_id == self.BATTLE_COMMAND_SECTION else
                    "battle command(s) use this data entry. Removing it sets them to None")
            if used_by and QMessageBox.question(
                    self, "Remove entry", f"{used_by} {what}. Continue?") != QMessageBox.StandardButton.Yes:
                return
        pooled = bool(cfg.get("ability_pool"))
        removed_ability_id = self._ability_first_id(section_id) + entry_index if pooled else None
        if pooled:
            # Deleting an ability a GF still teaches would leave that slot pointing at
            # whatever slides into the id, so those slots are cleared - say so first.
            used_by = self._count_ability_references(removed_ability_id)
            if used_by and QMessageBox.question(
                    self, "Remove ability",
                    f"{used_by} GF learn slot(s) still teach this ability. "
                    "Removing it sets them to None. Continue?") != QMessageBox.StandardButton.Yes:
                return

        def _remove_one(index):
            section.remove_subsection(index)
            for _ in range(nb_text if text_section is not None else 0):
                text_section.remove_text(index * nb_text)

        retired = commands and entry_index < self.REMOVABLE_ENGINE_SECTIONS[section_id][1]
        if retired:
            field = self.REMOVABLE_ENGINE_SECTIONS[section_id][0]
            self._section_entries(section_id)[entry_index].set(field, self.REMOVED_ENTRY)
        else:
            _remove_one(entry_index)

        # The placeholders only exist to pad the ids up to the first real entry above
        # them, so they go when that last entry does - and only then. Keying this off
        # the entry count alone also fired after deleting an entry below the block,
        # which threw away the rows above it.
        gf_start = cfg.get("gf_reserved_start")
        gf_count = cfg.get("gf_reserved_count") or 0
        if (gf_start is not None and entry_index >= gf_start + gf_count
                and len(section.get_subsection_list()) == gf_start + gf_count):
            for _ in range(gf_count):
                _remove_one(gf_start)

        if pooled:
            self._renumber_ability_references(removed_ability_id + 1, -1, removed_id=removed_ability_id)
        if commands:
            ref_id = self.COMMAND_ABILITY_SECTION if section_id == self.BATTLE_COMMAND_SECTION \
                else self.BATTLE_COMMAND_SECTION
            ref_tab, ref_section = self._section_tabs.get(ref_id), self._section_by_id(ref_id)
            # Its open form is written back first, then rebuilt from the renumbered data.
            if ref_tab is not None:
                ref_tab.commit()
            self._renumber_command_references(section_id, entry_index, compact=not retired)
            if ref_tab is not None and ref_section is not None:
                ref_tab.load_section(ref_section, ref_section.section_text_linked)

        tab.load_section(section, text_section)
        if tab._visible_indices:
            tab.list_widget.setCurrentRow(min(len(tab._visible_indices) - 1,
                                              max(0, tab.list_widget.currentRow())))
        if section_id == 2:
            self._refresh_magic_names()
        if pooled:
            self._refresh_ability_names()
            self._refresh_ability_pool()
        if commands:
            self._refresh_command_lookups()
            self._refresh_entry_budgets()
        if section_id in (itemids.BATTLE_ITEM_SECTION, itemids.NON_BATTLE_ITEM_SECTION):
            self._refresh_entry_budgets()
            self._refresh_item_names()
            self._refresh_battle_use_button()

    def compress_text(self):
        """Compress all kernel text (the shared toolbar's Compress button calls this)."""
        if not self.loaded_filename:
            return
        self._commit_all_tabs()
        by_id = {s.id: s for s in self.kernel_manager.section_list if s is not None}
        for data_id, text_id in self._text_link.items():
            text_section = by_id.get(text_id) if text_id else None
            config = self._section_configs.get(str(data_id))
            labels = config.get("text_labels", []) if config else []
            if not text_section or not labels:
                continue
            # Compress every string except plain "Name" fields (which ship uncompressed).
            for index, text in enumerate(text_section.get_text_list()):
                if labels[index % len(labels)] != "Name":
                    text.compress_str(3)
        self._populate_tabs()

    def uncompress_text(self):
        """Uncompress all kernel text (the shared toolbar's Uncompress button calls this)."""
        if not self.loaded_filename:
            return
        self._commit_all_tabs()
        for text_section in self._all_text_sections():
            for text in text_section.get_text_list():
                text.uncompress_str()
        self._populate_tabs()

    def _commit_all_tabs(self):
        """Write every form back to the data first: (un)compressing rebuilds the forms from the
        data, and a field only reaches it on a row change or a save - a name or description just
        typed would come back as the old text."""
        for tab in self._section_tabs.values():
            tab.commit()

    def _all_text_sections(self):
        linked_ids = {tid for tid in self._text_link.values() if tid}
        return [s for s in self.kernel_manager.section_list if s is not None and s.id in linked_ids]

    def _save_kernel(self):
        if not self.loaded_filename:
            return
        for tab in self._section_tabs.values():
            tab.commit()
        # Any magic name typed this session (including newly-added spells) needs to be
        # in the "magic" lookup BEFORE save, since Slot Sets' picker reads names from it.
        self._refresh_magic_names()
        # Saved regardless - the file is still valid for the unmodded game - but FFNx would
        # ignore every added command, so say why now rather than in its log.
        problems = self.command_problems()
        if problems:
            QMessageBox.warning(self, "Added battle commands",
                                "FFNx's AddMoreCommand will ignore the added battle commands "
                                "until this is fixed:\n\n" + "\n".join(problems))
        self._refresh_item_names()
        problems = self.item_problems()
        if problems:
            QMessageBox.warning(self, "Added items",
                                "FFNx's AddMoreItems will refuse this kernel.bin until this is fixed:\n\n"
                                + "\n".join(problems))
        self.kernel_manager.save_file(self.loaded_filename)
        self._battle_data_kept = {}   # the placeholders' data is gone from the file now
        print(f"Saved to {self.loaded_filename}")
