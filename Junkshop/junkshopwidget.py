import os

from PyQt6.QtCore import QSignalBlocker, QSettings
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QListWidget, QSpinBox, QComboBox, QGroupBox, QFormLayout, QCheckBox)

from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from Common.kernelnamesource import KernelNameSource
from FF8GameData.gamedata import GameData
from FF8GameData.menu.mweponmsg import text_at
from Junkshop.junkshopmanager import JunkshopManager, WeaponUpgrade
from SmallWidget.listsearchbar import ListSearchBar


class JunkshopWidget(QWidget):
    """mwepon.bin editor (Junk Shop weapon-upgrade recipes).

    Ported from the original JunkShop tool: each weapon upgrade has a price (stored as a
    multiple of 10) and a recipe of up to four (item, quantity) pairs the game consumes when
    the upgrade is bought. An item id of 0 (Nothing) disables that recipe slot.

    The Cronos checkbox reads and writes the prices on 16 bits, as Cronos's JunkShopPrice16.hext
    has the game do: byte 2 of the record is the high byte, up to 655,350 gil instead of 2,550."""

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData", file_registry=None):
        QWidget.__init__(self)

        if file_registry is None:  # The tool is used alone, it shares its files with nobody
            file_registry = FileRegistry()

        self.game_data = GameData(game_data_folder)
        self.game_data.load_item_data()
        self.manager = JunkshopManager(self.game_data)
        self.settings = QSettings("HobbitDur", "FF8UltimateEditor")

        self.cronos_checkbox = QCheckBox("Cronos")
        self.cronos_checkbox.setToolTip(
            "Prices on 16 bits, as Cronos's JunkShopPrice16.hext has the game read them: byte 2 of the record\n"
            "is the high byte of price / 10, up to 655,350 G instead of 2,550 G.\n"
            "Unticked: the vanilla game, byte 3 only. A vanilla file has 0 in byte 2, so its prices read the same.")
        self.cronos_checkbox.setChecked(self.settings.value("junkshop/cronos_checkbox", defaultValue=False, type=bool))
        self.manager.set_cronos(self.cronos_checkbox.isChecked())
        self.cronos_checkbox.toggled.connect(self._on_cronos_toggled)

        self.setWindowTitle("Junkshop")
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'junkshop.ico')))

        # File section: mwepon.bin, driven by the shared header toolbar (Import / Save).
        self.mwepon_binding = FileBinding("mwepon.bin", file_registry,
                                          load_callback=self.load_file, save_callback=self.save_file)
        # mwepon.msg, read-only (ShumiTranslator edits it): the text each upgrade's offset points at
        self.msg_binding = FileBinding("mwepon.msg", file_registry, file_filter="mwepon*.msg",
                                       read_only=True, complementary=True)
        self.msg_binding.file_opened.connect(self._load_msg)
        self.msg_binding.file_closed.connect(self._clear_msg)
        self.msg_data = None
        # kernel.bin, complementary: the only source of the weapon names.
        self.kernel_names = KernelNameSource(self.game_data, file_registry)
        self.kernel_names.changed.connect(self._on_kernel_names_changed)
        self.weapon_notice = KernelNameSource.make_notice("weapon")

        # Weapon list (left side)
        self.weapon_list = QListWidget()
        self.weapon_list.setFixedWidth(180)
        self.weapon_list.currentRowChanged.connect(self.reload_selected_weapon)
        # Ctrl+F search bar filtering the weapon list (weapon name or weapon id)
        self.weapon_search = ListSearchBar.wrap(self.weapon_list, match_index=True)

        # Editor (right side)
        self.weapon_name_label = QLabel("")
        self.weapon_name_label.setStyleSheet("font-size: 14pt; font-weight: bold;")

        self.price_spinbox = QSpinBox()
        self.price_spinbox.setRange(0, self.manager.max_price)  # price / 10 on 1 byte, or 2 with Cronos
        self.price_spinbox.setSingleStep(10)
        self.price_spinbox.setSuffix(" G")
        self.price_spinbox.setToolTip("Upgrade price in gils (stored as price / 10, so it is a multiple of 10)")
        self.price_spinbox.valueChanged.connect(self._on_data_changed)
        # Vanilla mode on a record whose byte 2 is set: what Cronos would charge for it
        self.cronos_price_label = QLabel("")
        self.cronos_price_label.setStyleSheet("color: #c07000;")
        self.cronos_price_label.setVisible(False)

        self.name_offset_label = QLabel("")
        self.name_offset_label.setToolTip(
            "Where this upgrade's text starts in mwepon.msg (bytes 0-1 of the record). The weapon's name\n"
            "is not there: it comes from kernel.bin. Read-only here: ShumiTranslator edits mwepon.msg and\n"
            "moves these offsets with its texts; Save here keeps them as they are on disk.")
        self.msg_text_label = QLabel("")
        self.msg_text_label.setWordWrap(True)
        self.msg_text_label.setMinimumWidth(360)  # a full line of the shop text, wrapped past that
        self.msg_text_label.setToolTip(
            "The text the Junk Shop shows in the bar under \"Remodel to which weapon?\" while the cursor is\n"
            "on this upgrade: mwepon.msg at the offset above (blank in the retail game). Edited in\n"
            "ShumiTranslator; one line, about 50 characters, and a colour code ends it.")

        price_group = QGroupBox("Price and shop text")
        price_form = QFormLayout()
        price_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        price_form.addRow("Upgrade price:", self.price_spinbox)
        price_form.addRow("", self.cronos_price_label)
        price_form.addRow("Text offset (read-only):", self.name_offset_label)
        price_form.addRow("Shop text (mwepon.msg):", self.msg_text_label)
        price_group.setLayout(price_form)

        # Four recipe slots (item + quantity)
        self.item_comboboxes = []
        self.quantity_spinboxes = []
        recipe_form = QFormLayout()
        recipe_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        for i in range(WeaponUpgrade.NB_ITEM):
            item_combobox = QComboBox()   # filled by _fill_item_combos: the item id is each entry's data
            item_combobox.setToolTip("Item consumed by this recipe slot (Nothing = slot disabled)")
            item_combobox.currentIndexChanged.connect(self._on_data_changed)

            quantity_spinbox = QSpinBox()
            quantity_spinbox.setRange(0, 255)
            quantity_spinbox.setToolTip("Quantity of the item consumed")
            quantity_spinbox.valueChanged.connect(self._on_data_changed)

            self.item_comboboxes.append(item_combobox)
            self.quantity_spinboxes.append(quantity_spinbox)

            slot_layout = QHBoxLayout()
            slot_layout.addWidget(item_combobox)
            slot_layout.addWidget(QLabel("x"))
            slot_layout.addWidget(quantity_spinbox)
            slot_layout.addStretch(1)
            recipe_form.addRow(f"Item {i + 1}:", slot_layout)

        recipe_group = QGroupBox("Recipe (items required to buy)")
        recipe_group.setLayout(recipe_form)

        self.editor_container = QWidget()
        editor_layout = QVBoxLayout()
        editor_layout.addWidget(self.weapon_name_label)
        editor_layout.addWidget(price_group)
        editor_layout.addWidget(recipe_group)
        editor_layout.addStretch(1)
        self.editor_container.setLayout(editor_layout)
        self.editor_container.setEnabled(False)

        main_editor_layout = QHBoxLayout()
        main_editor_layout.addWidget(self.weapon_search.column)
        main_editor_layout.addWidget(self.editor_container)
        main_editor_layout.addStretch(1)  # the editor keeps its natural width, the room is left after it

        top_layout = QHBoxLayout()
        top_layout.addWidget(self.cronos_checkbox)
        top_layout.addStretch(1)

        main_layout = QVBoxLayout()
        main_layout.addLayout(top_layout)
        main_layout.addWidget(self.weapon_notice)
        main_layout.addLayout(main_editor_layout)
        self.setLayout(main_layout)

        self._fill_item_combos()
        self.mwepon_binding.load_opened_file()  # Another tool may have opened mwepon.bin already
        self.kernel_names.binding.load_opened_file()  # ...or a kernel.bin
        self.msg_binding.load_opened_file()  # ...or a mwepon.msg

    def file_bindings(self):
        """The files the shared header toolbar drives for this tool: mwepon.bin, kernel.bin as
        a complementary file naming the weapons, and mwepon.msg (read-only) for the shop texts."""
        return [self.mwepon_binding, self.kernel_names.binding, self.msg_binding]

    def _load_msg(self, file_name):
        try:
            with open(file_name, "rb") as msg_file:
                self.msg_data = msg_file.read()
        except OSError:
            self.msg_data = None
        self.reload_selected_weapon()

    def _clear_msg(self, _path=None):
        self.msg_data = None
        self.reload_selected_weapon()

    def _shop_text(self, weapon):
        """What the Junk Shop shows for that upgrade, as a label (or what is missing to show it)."""
        if self.msg_data is None:
            return "(open mwepon.msg with \"Import complementary\" to see it)"
        text = text_at(self.game_data, self.msg_data, weapon.name_offset)
        if text is None:
            return f"(offset past the end of mwepon.msg, {len(self.msg_data)} bytes: not this file's mwepon.msg)"
        return f"\"{text}\"" + (" (blank)" if not text.strip() else "")

    def _fill_item_combos(self):
        """The recipe items: the game's, then those a kernel.bin adds (FFNx AddMoreItems, 199+)."""
        entries = self.kernel_names.item_entries()
        for combo in self.item_comboboxes:
            with QSignalBlocker(combo):
                combo.clear()
                for entry in entries:
                    combo.addItem(f"{entry['value']}: {entry['name']}" if entry["value"] >= 199
                                  else entry["name"], entry["value"])

    def _on_kernel_names_changed(self):
        """A kernel.bin was opened or removed: re-label the weapons and items (their data is
        untouched)."""
        self._fill_item_combos()
        self.reload_selected_weapon()
        self.weapon_notice.setVisible(not self.kernel_names.weapons)
        self.manager.set_weapon_names(self.kernel_names.weapons)
        for row, weapon in enumerate(self.manager.weapon_upgrades):
            item = self.weapon_list.item(row)
            if item is not None:
                item.setText(weapon.name)
        weapon = self._selected_weapon()
        if weapon:
            self.weapon_name_label.setText(weapon.name)

    def load_file(self, file_name):
        self.manager.load_file(file_name)
        self.manager.set_weapon_names(self.kernel_names.weapons)
        self.editor_container.setEnabled(True)
        with QSignalBlocker(self.weapon_list):
            self.weapon_list.clear()
            self.weapon_list.addItems([weapon.name for weapon in self.manager.weapon_upgrades])
        self.weapon_search.select_first_match()  # Row 0, or the first match if a search is typed in

    def save_file(self):
        if self.manager.file_path:
            self.manager.save_file()

    def _on_cronos_toggled(self, checked):
        """16-bit prices on or off: the range and the shown price follow; no byte changes until an edit."""
        self.settings.setValue("junkshop/cronos_checkbox", checked)
        self.manager.set_cronos(checked)
        with QSignalBlocker(self.price_spinbox):  # a narrower range must not write a clamped price
            self.price_spinbox.setRange(0, self.manager.max_price)
        self.reload_selected_weapon()

    def reload_selected_weapon(self):
        weapon = self._selected_weapon()
        if not weapon:
            return
        self.weapon_name_label.setText(weapon.name)
        with QSignalBlocker(self.price_spinbox):
            self.price_spinbox.setValue(weapon.price)
        self._show_cronos_price(weapon)
        self.name_offset_label.setText(f"0x{weapon.name_offset:04X}")
        self.msg_text_label.setText(self._shop_text(weapon))
        for i in range(WeaponUpgrade.NB_ITEM):
            item_id, quantity = weapon.items[i]
            combo = self.item_comboboxes[i]
            with QSignalBlocker(combo):
                if combo.findData(item_id) < 0:   # no list names it: kept, by its id
                    combo.addItem(f"{item_id}: (unknown)", item_id)
                combo.setCurrentIndex(combo.findData(item_id))
            with QSignalBlocker(self.quantity_spinboxes[i]):
                self.quantity_spinboxes[i].setValue(quantity)

    def _selected_weapon(self):
        index = self.weapon_list.currentRow()
        if 0 <= index < len(self.manager.weapon_upgrades):
            return self.manager.weapon_upgrades[index]
        return None

    def _on_data_changed(self):
        weapon = self._selected_weapon()
        if not weapon:
            return
        weapon.price = self.price_spinbox.value()
        self._show_cronos_price(weapon)
        for i in range(WeaponUpgrade.NB_ITEM):
            weapon.items[i][0] = self.item_comboboxes[i].currentData()
            weapon.items[i][1] = self.quantity_spinboxes[i].value()

    def _show_cronos_price(self, weapon):
        """Unticked Cronos on a record with a high byte: the vanilla game ignores it, Cronos does not."""
        shown = not self.manager.cronos and weapon.padding != 0
        if shown:
            self.cronos_price_label.setText(
                f"Byte 2 is {weapon.padding}: with Cronos this upgrade costs {weapon.cronos_price:,} G")
        self.cronos_price_label.setVisible(shown)
