import json
import os

from PyQt6.QtWidgets import (
    QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QMessageBox
)

from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from FF8GameData.gamedata import GameData
from ShumiTranslator.model.kernel.kernelmanager import KernelManager
from SolomonRing.kernellookups import LookupRegistry
from SolomonRing.kernelentry import KernelEntry
from SolomonRing.kernelsectiontab import KernelSectionTab


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

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData", file_registry=None,
                 settings=None):
        super().__init__()
        # The app's QSettings: remembers the last section tab across sessions (None: not kept).
        self.settings = settings

        if file_registry is None:  # The tool is used alone, it shares its files with nobody
            file_registry = FileRegistry()

        self.game_data_folder = game_data_folder
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
        self._restore_current_tab()
        self.tabs.currentChanged.connect(self._remember_current_tab)

        self.setLayout(main_layout)
        self.tabs.setEnabled(False)

        self.kernel_binding.load_opened_file()  # Another tool may have opened kernel.bin already

    def _set_unlock_all(self, unlocked):
        """Apply the "unlock unused fields" switch to every section tab at once."""
        for tab in self._section_tabs.values():
            tab.set_unlock_all(unlocked)

    def file_bindings(self):
        """The files the shared header toolbar drives for this tool (just kernel.bin)."""
        return [self.kernel_binding]

    def _build_group(self, entries):
        if len(entries) == 1:
            section_id, _ = entries[0]
            return self._make_section_tab(section_id)
        inner = QTabWidget()
        inner.setTabPosition(QTabWidget.TabPosition.West)
        for section_id, label in entries:
            inner.addTab(self._make_section_tab(section_id), label)
        return inner

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
        if self.settings is not None:
            self.settings.setValue(self.CURRENT_TAB_KEY, index)

    def _make_section_tab(self, section_id):
        config = self._section_configs[str(section_id)]
        # _checked absorbs the bool QPushButton.clicked emits, which would land in sid
        add_entry_callback = (lambda _checked=False, sid=section_id: self._add_growable_entry(sid)) \
            if config.get("growable") else None
        remove_entry_callback = (lambda _checked=False, sid=section_id: self._remove_growable_entry(sid)) \
            if config.get("growable") else None
        # Everything below the vanilla entry count is what the unmodded engine indexes by id,
        # so only what a mod added on top may be removed again.
        static_config = self.kernel_manager.get_section_config(section_id) or {}
        tab = KernelSectionTab(self.game_data, self.registry, config,
                               jump_callback=self._jump_to_section,
                               add_entry_callback=add_entry_callback,
                               remove_entry_callback=remove_entry_callback,
                               protected_count=self._protected_entry_count(section_id, static_config),
                               pool_callback=(lambda sid=section_id: self._ability_pool_status(sid))
                               if config.get("ability_pool") else None,
                               copy_between_entries=(static_config.get("number_sub_section") or 0) > 1
                               or bool(config.get("growable")))
        # A group paste / "Apply to..." writes the data without typing in a field, so it marks
        # the unsaved-edit state itself (dirty_state is installed on this tool by the main window).
        tab.edited.connect(self._mark_edited)
        self._section_tabs[section_id] = tab
        return tab

    def _mark_edited(self):
        dirty_state = getattr(self, "dirty_state", None)
        if dirty_state is not None:
            dirty_state.mark()

    def _protected_entry_count(self, section_id, static_config):
        """How many leading entries of a section may never be deleted.

        For Magic that is every vanilla spell: the unmodded engine indexes them by id.
        The ability sections are different - FFNx's AddMoreAbility patch rewrites every
        group boundary from the section sizes it reads, so no ability id is fixed and a
        vanilla one may be dropped to spend its id in another section. The single
        exception is ability id 0, the "no ability" value a GF's empty learn slots hold,
        which is the first entry of the first ability section."""
        config = self._section_configs.get(str(section_id)) or {}
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
        self._populate_tabs()
        self.tabs.setEnabled(True)

    def _populate_tabs(self):
        by_id = {s.id: s for s in self.kernel_manager.section_list if s}
        for section_id, tab in self._section_tabs.items():
            section = by_id.get(section_id)
            text_id = self._text_link.get(section_id, 0)
            text_section = by_id.get(text_id) if text_id else None
            tab.load_section(section, text_section)
        self._refresh_magic_names()
        self._refresh_ability_names()
        self._refresh_ability_pool()
        self._refresh_slot_set_summaries()

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
    # Mirrors what FFNx's AddMoreAbility patch refuses at load: besides the shared
    # 128, a learned menu ability is one bit of a single dword, so that group tops
    # out at 32 entries. (Its other rule - the GF group must still start at id 64
    # or above - cannot be reached from here: only sections before it could push it
    # down, and their vanilla entries are not removable.)
    MENU_ABILITY_SECTION = 18
    MAX_MENU_ABILITIES = 32

    def _ability_id_max(self):
        return self.game_data.kernel_data_json.get("ability_id_max", 128)

    def _ability_section_ids(self):
        """The sections sharing the ability id space, in id order."""
        return [section["id"] for section in self.game_data.kernel_data_json["sections"]
                if section.get("ability_pool")]

    def _section_by_id(self, section_id):
        return next((s for s in self.kernel_manager.section_list if s and s.id == section_id), None)

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
        can_add = used < maximum
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
                name = tab._entries[index].get_text(0).strip()
                entries.append({"value": ability_id, "name": name or f"(unnamed {ability_id})"})
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
        falls back to 0 (None) because the ability it named is gone."""
        cleared = 0
        for entry, name in self._ability_reference_entries():
            value = entry.get(name)
            if removed_id is not None and value == removed_id:
                entry.set(name, 0)
                cleared += 1
            elif value >= from_id:
                entry.set(name, value + delta)
        return cleared

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
        section = next((s for s in self.kernel_manager.section_list if s and s.id == section_id), None)
        tab = self._section_tabs.get(section_id)
        if section is None or tab is None or not section.section_text_linked:
            return
        cfg = self.kernel_manager.get_section_config(section_id)
        text_section = section.section_text_linked
        nb_text = len(tab.text_labels) or 1
        # The shown entry's form is only written back on a row change, and load_section() below
        # rebuilds every entry from the data: write it first, or a name/value just typed (a spell
        # renamed, then "+ Add entry") is lost.
        tab.commit()
        pooled = bool(cfg.get("ability_pool"))
        # The seven ability sections share one id space, and the menu group has a cap
        # of its own; the button greys out when either is reached, but a stale click
        # (or a caller that is not the button) must not grow it anyway.
        if pooled and not self._ability_pool_status(section_id)[1]:
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
            for _ in range(nb_text):
                text_section.add_text(bytearray([0x00]))

        def _insert_one(index):
            section.insert_blank_subsection(index)
            for i in range(nb_text):
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

    def _remove_growable_entry(self, section_id):
        """Delete the selected entry of a "growable" data section together with its linked
        name/description text. What may go depends on the section - see
        _protected_entry_count: every vanilla spell stays, while a vanilla ability may be
        removed to free its id for another ability section. Entries after
        the deleted one shift down one id, exactly as they would in any array. If that leaves the
        section with nothing above the GF-reserved block but the placeholder rows themselves, they
        go too, so the file never keeps a tail of reserved-only entries."""
        section = next((s for s in self.kernel_manager.section_list if s and s.id == section_id), None)
        tab = self._section_tabs.get(section_id)
        if section is None or tab is None or not section.section_text_linked:
            return
        cfg = self.kernel_manager.get_section_config(section_id) or {}
        entry_index = tab.current_entry_index()
        if not tab.can_remove(entry_index):
            return
        tab.commit()  # same as adding: load_section() below rebuilds the entries from the data
        text_section = section.section_text_linked
        nb_text = len(tab.text_labels) or 1
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
            for _ in range(nb_text):
                text_section.remove_text(index * nb_text)

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

        tab.load_section(section, text_section)
        if tab._visible_indices:
            tab.list_widget.setCurrentRow(min(len(tab._visible_indices) - 1,
                                              max(0, tab.list_widget.currentRow())))
        if section_id == 2:
            self._refresh_magic_names()
        if pooled:
            self._refresh_ability_names()
            self._refresh_ability_pool()

    def compress_text(self):
        """Compress all kernel text (the shared toolbar's Compress button calls this)."""
        if not self.loaded_filename:
            return
        by_id = {s.id: s for s in self.kernel_manager.section_list if s}
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
        for text_section in self._all_text_sections():
            for text in text_section.get_text_list():
                text.uncompress_str()
        self._populate_tabs()

    def _all_text_sections(self):
        linked_ids = {tid for tid in self._text_link.values() if tid}
        return [s for s in self.kernel_manager.section_list if s and s.id in linked_ids]

    def _save_kernel(self):
        if not self.loaded_filename:
            return
        for tab in self._section_tabs.values():
            tab.commit()
        # Any magic name typed this session (including newly-added spells) needs to be
        # in the "magic" lookup BEFORE save, since Slot Sets' picker reads names from it.
        self._refresh_magic_names()
        self.kernel_manager.save_file(self.loaded_filename)
        print(f"Saved to {self.loaded_filename}")
