"""The Hyne tabs over Hyne/hynesavemap.py: progress, party, battle, shops, draw points, world map,
Chocobo World, load screen, field variables, and the battle order and Timber Maniacs pages of the Items tab.

A SavePage builds its widgets through binding helpers: each widget is tied to one field of a section
of HyneManager, written at once on edit and refilled by reload() with its signals blocked."""
from PyQt6.QtCore import QSignalBlocker, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton, QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from Hyne.hynesavemap import (
    BattleState, ChocoboWorld, DRAW_POINT_STATES, MAGIC_MOVED_BITS, NB_DRAW_POINTS, NB_SHOPS, NB_WORLD_POSITIONS, SCANNED_MOVED_BITS,
    SHOP_NB_ITEMS, WORLD_POSITION_VALUES, field_var_tab,
)

SPIN_WIDTH_3_DIGITS = 78
SPIN_WIDTH_5_DIGITS = 92
I16_MIN, I16_MAX = -32768, 32767
I32_MIN, I32_MAX = -2147483648, 2147483647
U16_MAX = 0xFFFF
U8_MAX = 0xFF
DISC_MOMENTS = (395, 901, 3860)   # the story moments each disc after the first starts at
FIELD_PARTY_NAMES = ["Squall", "Zell", "Irvine", "Quistis", "Rinoa", "Selphie", "Seifer", "Edea", "Laguna", "Kiros", "Ward"]
SCAN_PARTY_SLOTS = 16
MODULE_ENTRIES = [{"value": 0, "name": "Field"}, {"value": 1, "name": "Field"}, {"value": 2, "name": "World map"},
                  {"value": 3, "name": "Battle"}]
TIMBER_MANIACS_ISSUES = [
    "Balamb Hotel", "Balamb Station", "Dollet Pub", "Dollet Hotel", "Timber Maniacs Redaction", "Timber Hotel",
    "Deling City Hotel", "Horizon: handyman's House", "Horizon Hotel", "Trabia Garden - Cemetery",
    "Centra Ruins (automatic)", "Shumi Village: Handyman's House", "Edea's House", "White SeeD Ship", "Unused", "Unused",
]
UNUSED_NAME = "Unused"
# The world map scripts' bits 0-15, from section 36 of wmsetus.obj. Nothing tests or sets the unused ones.
WORLD_MESSAGE_NAMES = ["Car controls", UNUSED_NAME, "Garden controls", "Chocobo controls", "Ragnarok controls",
                       "Selphie: to the Missile Base", "Edea's house looks familiar", "Garden: gauge going berserk"]
PUPU_QUEST_NAMES = [UNUSED_NAME, UNUSED_NAME, "Mandy Beach", "Winhill", "Trabia", "Kashkabald Desert", "UFO defeated", "PuPu defeated"]
# (text, byte of the quest block, bit)
OBEL_QUEST_FLAGS = [
    ("Hummed a song twice", 0, 0),
    ("Didn't tell the shadow where the Monkey is", 0, 6), ("The shadow gave the Balamb hint", 3, 6),
    ("Rock beach Balamb", 3, 1), ("The Monkey said he's stronger than you", 0, 7), ("Did some skimming stones", 0, 4),
    ("Made a countless amount of ricochets", 0, 5), ("The Monkey rock", 3, 2), ("Galbadia mountain rock", 3, 3),
    ("Timber island rock", 3, 4), ("All rocks", 3, 5), ("The shadow gave the Eldbeak hint", 1, 6),
    ("Saw the pillar at Eldbeak", 1, 7), ("Minde island treasure found", 2, 0), ("Esthar's mountains treasure found", 2, 1),
]
# The first script variable, which the world map scripts compare and set as a whole value
OBEL_STATES = [{"value": 0, "name": "Lake not found"}, {"value": 1, "name": "Lake found"},
               {"value": 2, "name": "Asked to find Mr. Monkey"}, {"value": 4, "name": "Mr. Monkey found"},
               {"value": 121, "name": "Liar Rocks: black-faced rock"}, {"value": 122, "name": "Liar Rocks: white-faced rock"},
               {"value": 123, "name": "Liar Rocks: red-faced rock"}, {"value": 124, "name": "Liar Rocks: blue-faced rock"}]
WORLD_POSITION_ROWS = ["Party", "Party, second set", "Ragnarok", "Balamb Garden", "Rental car", "Rental car, second set",
                       UNUSED_NAME, UNUSED_NAME]
WORLD_UNUSED_POSITIONS = (1, 5, 6, 7)   # the second set hangs on a flag FFWorldInit clears and nothing sets; no code reads the last two
WORLD_POSITION_COLUMNS = [("X", I32_MIN, I32_MAX), ("Y", I32_MIN, I32_MAX), ("Height", I16_MIN, I16_MAX), ("Angle", 0, U16_MAX)]
SUMMON_LEVEL_NAMES = ["ChocoFire", "ChocoFlare", "ChocoMeteor", "ChocoBocle"]


def format_seconds(seconds):
    return f"{seconds // 3600}:{seconds // 60 % 60:02}:{seconds % 60:02}"


def _shared_model(owner, entries):
    """One combo model for many combos, so hundreds of them stay cheap."""
    model = QStandardItemModel(owner)
    for entry in entries:
        item = QStandardItem(f"{entry['value']}: {entry['name']}")
        item.setData(entry["value"], Qt.ItemDataRole.UserRole)
        model.appendRow(item)
    return model


class SavePage(QWidget):
    def __init__(self, tool):
        super().__init__()
        self.tool = tool
        self._refills = []

    def section(self, name):
        return getattr(self.tool.manager, name)

    def reload(self):
        for refill in self._refills:
            refill()

    def _bound(self, widget, refill):
        """Refill `widget` with its signals blocked."""
        def blocked():
            with QSignalBlocker(widget):
                refill()
        self._refills.append(blocked)
        return widget

    def spin(self, section, field, minimum, maximum, tooltip=""):
        spin = self.tool._spinbox(minimum, maximum, tooltip=tooltip)
        spin.setMaximumWidth(SPIN_WIDTH_3_DIGITS if maximum <= U8_MAX else SPIN_WIDTH_5_DIGITS)
        spin.valueChanged.connect(lambda value: setattr(self.section(section), field, value))
        return self._bound(spin, lambda: self.tool._set_spin_value(spin, getattr(self.section(section), field)))

    def u32_spin(self, section, field, tooltip=""):
        spin = self.tool._u32_spinbox(tooltip=tooltip)
        spin.valueChanged.connect(lambda _value: setattr(self.section(section), field, spin.value()))
        return self._bound(spin, lambda: self.tool._set_spin_value(spin, getattr(self.section(section), field)))

    def combo(self, section, field, entries, tooltip=""):
        combo = self.tool._enum_combo(entries, tooltip=tooltip)
        combo.currentIndexChanged.connect(lambda _index: setattr(self.section(section), field, combo.currentData()))
        return self._bound(combo, lambda: self.tool._select_combo(combo, getattr(self.section(section), field)))

    def shared_combo(self, section, field, model, tooltip=""):
        """A combo over a shared model, for lists too long to copy into each."""
        role = Qt.ItemDataRole.UserRole
        combo = QComboBox()
        combo.setModel(model)
        combo.setMinimumContentsLength(14)
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        if tooltip:
            combo.setToolTip(tooltip)
        combo.currentIndexChanged.connect(lambda _index: setattr(self.section(section), field, combo.currentData(role)))

        def refill():
            value = getattr(self.section(section), field)
            index = combo.findData(value, role)
            if index < 0:  # outside the known list: keep it so it is never lost
                item = QStandardItem(f"{value}: (unknown)")
                item.setData(value, role)
                model.appendRow(item)
                index = model.rowCount() - 1
            combo.setCurrentIndex(index)
        return self._bound(combo, refill)

    def check(self, section, field, text, tooltip=""):
        check = QCheckBox(text)
        if tooltip:
            check.setToolTip(tooltip)
        check.toggled.connect(lambda checked: setattr(self.section(section), field, checked))
        return self._bound(check, lambda: check.setChecked(getattr(self.section(section), field)))

    def unused_spin(self, section, field, maximum):
        spin = self.spin(section, field, 0, maximum, "No code reads this.")
        self.tool.mark_unused(spin)
        return spin

    def bit_check(self, section, bits, index, text, tooltip=""):
        check = QCheckBox(text)
        if tooltip:
            check.setToolTip(tooltip)
        check.toggled.connect(lambda checked: getattr(self.section(section), bits).__setitem__(index, checked))
        return self._bound(check, lambda: check.setChecked(getattr(self.section(section), bits)[index]))

    def byte_flag_check(self, section, field, mask, text, tooltip=""):
        """One flag of a whole-byte field, its other bits kept."""
        def toggled(checked):
            value = getattr(self.section(section), field)
            setattr(self.section(section), field, value | mask if checked else value & ~mask & U8_MAX)
        check = QCheckBox(text)
        if tooltip:
            check.setToolTip(tooltip)
        check.toggled.connect(toggled)
        return self._bound(check, lambda: check.setChecked(bool(getattr(self.section(section), field) & mask)))

    def bit_group(self, title, section, bits, names, columns=2, tooltip=""):
        grid = QGridLayout()
        for index, name in enumerate(names):
            check = self.bit_check(section, bits, index, name)
            if name == UNUSED_NAME:
                self.tool.mark_unused(check)
            grid.addWidget(check, index // columns, index % columns)
        group = QGroupBox(title)
        if tooltip:
            group.setToolTip(tooltip)
        group.setLayout(grid)
        return group

    def bit_list(self, title, section, bits, names, tooltip=""):
        """A long run of flags as a check list with a select-all box."""
        role = Qt.CheckState
        list_widget = QListWidget()
        list_widget.setUniformItemSizes(True)
        for name in names:
            item = QListWidgetItem(name)
            item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            item.setCheckState(role.Unchecked)
            list_widget.addItem(item)
            if name == UNUSED_NAME:
                self.tool.mark_unused(item)
        all_check = QCheckBox("Select all")

        def item_changed(item):
            getattr(self.section(section), bits)[list_widget.row(item)] = item.checkState() == role.Checked
            with QSignalBlocker(all_check):
                all_check.setChecked(all(getattr(self.section(section), bits)))

        def all_clicked(checked):
            values = getattr(self.section(section), bits)
            for index in range(len(values)):
                values[index] = checked
            self.reload()

        def refill():
            values = getattr(self.section(section), bits)
            for index in range(list_widget.count()):
                item = list_widget.item(index)
                item.setHidden(index >= len(values))   # a run can change length (the moved scan block)
                if index < len(values):
                    item.setCheckState(role.Checked if values[index] else role.Unchecked)
            with QSignalBlocker(all_check):
                all_check.setChecked(all(values))

        list_widget.itemChanged.connect(item_changed)
        all_check.clicked.connect(all_clicked)
        self._bound(list_widget, refill)
        layout = QVBoxLayout()
        layout.addWidget(list_widget)
        layout.addWidget(all_check)
        group = QGroupBox(title)
        if tooltip:
            group.setToolTip(tooltip)
        group.setLayout(layout)
        group.list_widget = list_widget
        group.all_check = all_check
        return group


def _form_group(title, rows, tooltip=""):
    form = QFormLayout()
    for label, widget in rows:
        form.addRow(label, widget)
    group = QGroupBox(title)
    if tooltip:
        group.setToolTip(tooltip)
    group.setLayout(form)
    return group


class ProgressPage(SavePage):
    """Story moment, disc, play time, steps, SeeD, tutorial entries."""

    def __init__(self, tool):
        super().__init__(tool)
        self.moments = tool.hyne_data["moments"]
        locations = tool.field_names

        self.moment_table = QTableWidget(len(self.moments), 2)
        self.moment_table.setHorizontalHeaderLabels(["Value", "Game moment"])
        self.moment_table.verticalHeader().setVisible(False)
        self.moment_table.verticalHeader().setDefaultSectionSize(22)
        self.moment_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.moment_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.moment_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.moment_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.moment_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        grey = QBrush(QColor("gray"))
        for row, (value, location) in enumerate(self.moments):
            value_item = QTableWidgetItem(str(value))
            name_item = QTableWidgetItem(locations.get(location, "???") if location >= 0 else f"Disc {-location}")
            if location < 0:  # the disc starts
                value_item.setForeground(grey)
                name_item.setForeground(grey)
            self.moment_table.setItem(row, 0, value_item)
            self.moment_table.setItem(row, 1, name_item)
        self.moment_table.currentCellChanged.connect(self._on_moment_row)

        self.moment_spin = self.spin("progress", "story_moment", 0, U16_MAX,
                                     "Story progress (field variable 256). Changes only this value: positions and "
                                     "side quests stay as they are.")
        self.moment_spin.valueChanged.connect(self._on_moment_value)
        self.disc_combo = self.combo("progress", "disc", [{"value": n, "name": f"Disc {n}"} for n in range(1, 5)],
                                     "Current disc (field variable 204)")
        self.auto_disc_check = QCheckBox("Disc follows the moment")
        self.auto_disc_check.setChecked(True)
        self.auto_disc_check.setToolTip("Changing the moment also sets the disc it belongs to")
        self._refills.append(self._select_moment_row)

        story_row = QHBoxLayout()
        story_row.addWidget(QLabel("Moment:"))
        story_row.addWidget(self.moment_spin)
        story_row.addWidget(self.disc_combo)
        story_row.addWidget(self.auto_disc_check)
        story_row.addStretch(1)
        story_layout = QVBoxLayout()
        story_layout.addLayout(story_row)
        story_layout.addWidget(self.moment_table)
        story_group = QGroupBox("Story")
        story_group.setLayout(story_layout)
        story_group.setMinimumWidth(460)

        self.time_label = QLabel()
        self.countdown_label = QLabel()
        time_spin = self.u32_spin("progress", "game_time", "Play time in seconds")
        countdown_spin = self.u32_spin("progress", "countdown", "Countdown in seconds")
        time_spin.valueChanged.connect(lambda _value: self.time_label.setText(format_seconds(time_spin.value())))
        countdown_spin.valueChanged.connect(lambda _value: self.countdown_label.setText(format_seconds(countdown_spin.value())))
        self._refills.append(lambda: self.time_label.setText(format_seconds(self.section("progress").game_time)))
        self._refills.append(lambda: self.countdown_label.setText(format_seconds(self.section("progress").countdown)))

        def with_label(spin, label):
            row = QHBoxLayout()
            row.addWidget(spin)
            row.addWidget(label)
            row.addStretch(1)
            return row

        self.seed_points_spin = self.spin("progress", "seed_points", 0, U16_MAX,
                                          "SeeD rank points: the rank shown is points / 100, between 1 and 31 (field variable 16)")
        self.seed_rank_label = QLabel()
        self.seed_points_spin.valueChanged.connect(self._show_seed_rank)
        self._refills.append(self._show_seed_rank)
        form = QFormLayout()
        form.addRow("Play time:", with_label(time_spin, self.time_label))
        form.addRow("Countdown:", with_label(countdown_spin, self.countdown_label))
        form.addRow("Steps:", self.u32_spin("progress", "steps", "Steps walked (field variable 4)"))
        form.addRow("SeeD points:", with_label(self.seed_points_spin, self.seed_rank_label))
        form.addRow("SeeD pay:", self.u32_spin("progress", "seed_pay", "Next SeeD salary counter (field variable 8)"))
        form.addRow("SeeD test level:", self.spin("progress", "seed_test_level", 0, U8_MAX, "Highest SeeD test level passed"))
        form.addRow("Last field visited:", self.spin("progress", "last_field", 0, U16_MAX, "Field variable 84"))
        form.addRow("Movie frame:", self.u32_spin("progress", "movie_frame", "Field variable 80"))
        values_group = QGroupBox("Progress")
        values_group.setLayout(form)
        values_column = QVBoxLayout()
        values_column.addWidget(values_group)
        values_column.addStretch(1)

        self.tutorial_group = self.bit_list("Tutorial entries read", "progress", "tutorials", tool.hyne_data["tutorial_entries"],
                                            "The entries of the Tutorial menu's Information pages already unlocked")
        layout = QHBoxLayout(self)
        layout.addWidget(story_group, 2)
        layout.addLayout(values_column)
        layout.addWidget(self.tutorial_group, 2)

    def _show_seed_rank(self):
        points = max(100, min(3100, self.section("progress").seed_points))
        self.seed_rank_label.setText(f"rank {points // 100}")

    def _select_moment_row(self):
        moment = self.section("progress").story_moment
        best = 0
        for row, (value, _location) in enumerate(self.moments):
            if value <= moment:
                best = row
        with QSignalBlocker(self.moment_table):
            self.moment_table.selectRow(best)
            self.moment_table.setCurrentCell(best, 0)

    def _follow_disc(self):
        if self.auto_disc_check.isChecked():
            moment = self.section("progress").story_moment
            self.section("progress").disc = 1 + sum(moment >= start for start in DISC_MOMENTS)
            with QSignalBlocker(self.disc_combo):
                self.tool._select_combo(self.disc_combo, self.section("progress").disc)

    def _on_moment_row(self, row, *_):
        if row < 0:
            return
        self.section("progress").story_moment = self.moments[row][0]
        with QSignalBlocker(self.moment_spin):
            self.moment_spin.setValue(self.moments[row][0])
        self._follow_disc()
        self.tool._mark_dirty()

    def _on_moment_value(self, _value):
        self._select_moment_row()
        self._follow_disc()


class PartyPage(SavePage):
    """The party on the field and where it stands; the party of the menus is on the Misc tab."""

    def __init__(self, tool):
        super().__init__(tool)
        member_entries = [{"value": value, "name": name} for value, name in enumerate(FIELD_PARTY_NAMES)]
        member_entries.append({"value": 0xFF, "name": "None"})
        party_row = QHBoxLayout()
        self.party_combos = [
            self.combo("party", f"party_{slot}", member_entries, f"Field party member {slot}. Laguna's squad can walk here too.")
            for slot in (1, 2, 3)]
        for combo in self.party_combos:
            party_row.addWidget(combo)
        party_row.addStretch(1)
        self.dream_check = self.byte_flag_check("battle", "special_flags", 0x01, "Dream world (Laguna's squad)",
                                                "The party isolated in a dream: battle and save screen use Laguna's squad and gil")
        party_layout = QVBoxLayout()
        party_layout.addLayout(party_row)
        party_layout.addWidget(self.dream_check)
        party_group = QGroupBox("Field party")
        party_group.setToolTip("Who walks on the field. The party of the menus is on the Misc tab.")
        party_group.setLayout(party_layout)

        map_entries = [{"value": value, "name": name} for value, name in enumerate(tool.hyne_data["maps"])]
        map_model = _shared_model(self, map_entries)
        self.module_combo = self.combo("party", "module", MODULE_ENTRIES, "Where the save was made")
        self.module_combo.currentIndexChanged.connect(self._show_presets)
        self.location_combo = self.shared_combo("party", "location", map_model, "The field the save opens on")
        self.last_location_combo = self.shared_combo("party", "last_location", map_model, "The field before it")
        location_group = _form_group("Location", [
            ("Module:", self.module_combo), ("Current field:", self.location_combo), ("Previous field:", self.last_location_combo)])

        self.position_spins = []
        grid = QGridLayout()
        for column, text in enumerate(("X", "Y", "Triangle", "Direction"), start=1):
            grid.addWidget(QLabel(text), 0, column)
        for member in range(3):
            grid.addWidget(QLabel(f"Member {member + 1}:"), member + 1, 0)
            row = []
            for column, (minimum, maximum) in enumerate(((I16_MIN, I16_MAX), (I16_MIN, I16_MAX), (0, U16_MAX), (0, U8_MAX))):
                spin = tool._spinbox(minimum, maximum)
                spin.setMaximumWidth(SPIN_WIDTH_5_DIGITS)
                spin.valueChanged.connect(lambda _value, m=member: self._on_position_changed(m))
                grid.addWidget(spin, member + 1, column + 1)
                row.append(spin)
            self.position_spins.append(row)
        self._refills.append(self._fill_positions)
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("Choose a place...")
        for preset in tool.hyne_data["world_presets"]:
            self.preset_combo.addItem(preset["name"], preset)
        self.preset_button = QPushButton("Move there")
        self.preset_button.setToolTip("World map only: put the party at this place")
        self.preset_button.clicked.connect(self._apply_preset)
        preset_row = QHBoxLayout()
        preset_row.addWidget(self.preset_combo)
        preset_row.addWidget(self.preset_button)
        preset_row.addStretch(1)
        position_layout = QVBoxLayout()
        position_layout.addLayout(grid)
        position_layout.addLayout(preset_row)
        position_group = QGroupBox("Position")
        position_group.setLayout(position_layout)
        self._refills.append(self._show_presets)

        column = QVBoxLayout()
        column.addWidget(party_group)
        column.addWidget(location_group)
        column.addWidget(position_group)
        column.addStretch(1)
        layout = QHBoxLayout(self)
        layout.addLayout(column)
        layout.addStretch(1)

    def _fill_positions(self):
        for member, row in enumerate(self.position_spins):
            for spin, value in zip(row, self.section("party").position(member)):
                with QSignalBlocker(spin):
                    spin.setValue(value)

    def _on_position_changed(self, member):
        self.section("party").set_position(member, *(spin.value() for spin in self.position_spins[member]))

    def _show_presets(self):
        on_world_map = self.module_combo.currentData() == 2
        self.preset_combo.setVisible(on_world_map)
        self.preset_button.setVisible(on_world_map)

    def _apply_preset(self):
        preset = self.preset_combo.currentData()
        if not preset:
            return
        party = self.section("party")
        party.set_position(0, preset["x"], preset["y"], preset["triangle"], preset["direction"])
        party.set_position(1, 0, 0, 0, 0)
        party.set_position(2, 0, 0, 0, 0)
        self._fill_positions()
        self.preset_combo.setCurrentIndex(0)
        self.tool._mark_dirty()


class BattlePage(SavePage):
    """Battle counts, first-time flags, special flags, magic drawn and enemies scanned once."""

    def __init__(self, tool):
        super().__init__(tool)
        counts_group = _form_group("Statistics", [
            ("Battles won:", self.u32_spin("battle", "wins", "Also written to its copy in field variable 20")),
            ("Battles escaped:", self.spin("battle", "escapes", 0, U16_MAX, "Also written to its copy in field variable 26")),
            ("Monsters killed:", self.u32_spin("battle", "total_kills", "Field variable 68. Editing a character's kills updates it on save.")),
            ("Tonberries killed:", self.u32_spin("battle", "tonberries", "Counts toward the Tonberry King")),
        ])
        flags = QVBoxLayout()
        flags.addWidget(self.check("battle", "tonberry_king", "Tonberry King killed"))
        flags.addWidget(self.check("battle", "ufo", "UFO killed"))
        flags.addWidget(self.check("battle", "first_bite_bug", "First Bite Bug"))
        flags.addWidget(self.check("battle", "first_bomb", "First Bomb"))
        flags.addWidget(self.check("battle", "first_t_rexaur", "First T-Rexaur"))
        flags.addWidget(self.check("battle", "first_irvine", "First battle with Irvine"))
        first_group = QGroupBox("Battle flags")
        first_group.setLayout(flags)

        special = QVBoxLayout()
        for bit, name in list(enumerate(BattleState.SPECIAL_FLAG_NAMES))[1:]:
            special.addWidget(self.byte_flag_check("battle", "special_flags", 1 << bit, name))
        special.addWidget(self.byte_flag_check("battle", "renzokuken_flags", 0x01, "Renzokuken auto"))
        special.addWidget(self.byte_flag_check("battle", "renzokuken_flags", 0x02, "Ring Master auto"))
        indicator_row = QHBoxLayout()
        indicator_row.addWidget(QLabel("Renzokuken indicator:"))
        indicator_row.addWidget(self.spin("battle", "renzokuken_indicator", 0, U8_MAX, "128 or more: no indicator"))
        indicator_row.addStretch(1)
        special.addLayout(indicator_row)
        special_group = QGroupBox("Special")
        special_group.setToolTip("Summons that can appear, Angelo and Renzokuken")
        special_group.setLayout(special)

        left = QVBoxLayout()
        left.addWidget(counts_group)
        left.addWidget(first_group)
        left.addWidget(special_group)
        left.addStretch(1)

        self.magic_group = self.bit_list("Magic drawn once", "battle", "magic_drawn",
                                         [tool.magic_label(index + 1, "Unused") for index in range(MAGIC_MOVED_BITS)],
                                         "Magic drawn at least once")
        self.magic_moved_check = self.check(
            "battle", "magic_moved", "Moved by FFNx (variables 753-784)",
            "FFNx keeps this list in field variables 753-784 when kernel.bin holds a magic id of 96 or more. The save's\n"
            "vanilla list is then ignored. Set from the kernel.bin opened with the toolbar's Import complementary.")
        self.magic_moved_check.toggled.connect(lambda _checked: self.reload())
        self.magic_moved_check.setEnabled(False)
        self._refills.append(lambda: self.magic_moved_check.setVisible(self.section("battle").magic_moved))
        magic_column = QVBoxLayout()
        magic_column.addWidget(self.magic_moved_check)
        magic_column.addWidget(self.magic_group, 1)
        monsters = tool.game_data.monster_data_json["monster"]
        monster_names = {monster["com_id"]: monster["name"] for monster in monsters}
        scan_names = [FIELD_PARTY_NAMES[slot] if slot < len(FIELD_PARTY_NAMES) else "Unused"
                      for slot in range(SCAN_PARTY_SLOTS)]
        scan_names += [f"c0m{com:03}: {monster_names.get(com, 'Unused')}" for com in range(SCANNED_MOVED_BITS - SCAN_PARTY_SLOTS)]
        self.scan_group = self.bit_list("Scanned once", "battle", "enemies_scanned", scan_names,
                                        "With the Scan option on Once, a repeat Scan of these shows the short result")
        self.scan_moved_check = self.check(
            "battle", "scan_moved", "Moved by FFNx (variables 785-816)",
            "FFNx keeps this list in field variables 785-816 when the game's scene.out uses a monster of its extra ones\n"
            "(c0m144 and up), as Cronos does. The save's vanilla list is then ignored. Set from the scene.out opened with\n"
            "the toolbar's Import complementary.")
        self.scan_moved_check.toggled.connect(lambda _checked: self.reload())
        self.scan_moved_check.setEnabled(False)
        self._refills.append(lambda: self.scan_moved_check.setVisible(self.section("battle").scan_moved))
        scan_column = QVBoxLayout()
        scan_column.addWidget(self.scan_moved_check)
        scan_column.addWidget(self.scan_group, 1)

        layout = QHBoxLayout(self)
        layout.addLayout(left)
        layout.addLayout(magic_column, 1)
        layout.addLayout(scan_column, 1)

    def relabel_magic(self):
        names = self.magic_group.list_widget
        with QSignalBlocker(names):
            for index in range(names.count()):
                names.item(index).setText(self.tool.magic_label(index + 1, "Unused"))


class ShopsPage(SavePage):
    """Which shops were visited, for Call Shop, and what they sell."""

    # The shops selling something else than the common list (myst6re's Hyne): shop -> item table
    SHOP_ITEM_TABLES = {0: 0, 8: 2, 17: 3, 18: 4, 19: 5}

    def __init__(self, tool):
        super().__init__(tool)
        data = tool.hyne_data
        self.item_tables = data["shop_items"]
        self.rare_slots = data["shop_rare_slots"]
        self.file_shops = None   # shop.bin's [(item ids, rare slots)] by shop, when one is open
        self.shop_list = QListWidget()
        self.shop_list.addItems(data["shops"])
        self.shop_list.setFixedWidth(240)
        self.shop_list.currentRowChanged.connect(self._fill_shop)
        self.visited_check = QCheckBox("Shop visited once")
        self.visited_check.setToolTip("The game ticks this when the shop opens. The Call Shop ability lists only "
                                      "the shops ticked.\nIt changes nothing to what a shop sells.")
        self.visited_check.toggled.connect(self._on_visited)
        self.item_labels = []
        grid = QGridLayout()
        for slot in range(SHOP_NB_ITEMS):
            label = QLabel()
            self.item_labels.append(label)
            grid.addWidget(label, slot % 8, slot // 8)
        items_group = QGroupBox("Items sold")
        items_group.setToolTip("The list is vanilla shop.bin's until a shop.bin is opened with the toolbar's "
                               "Import complementary.")
        items_group.setLayout(grid)
        items_note = QLabel("In italics: sold only with the Familiar ability. The game works out what is on sale each "
                            "time a shop opens, and the prices from price.bin, Haggle and Sell-High, so a save has "
                            "nothing to change here but the visit.")
        items_note.setWordWrap(True)
        right = QVBoxLayout()
        right.addWidget(self.visited_check)
        right.addWidget(items_group)
        right.addWidget(items_note)
        right.addStretch(1)
        layout = QHBoxLayout(self)
        layout.addWidget(self.shop_list)
        layout.addLayout(right)
        layout.addStretch(1)
        self._refills.append(self._fill_shop)

    def _items(self, shop):
        if self.file_shops:
            return self.file_shops[shop][0]
        return self.item_tables[self.SHOP_ITEM_TABLES.get(shop, 1)]

    def _rare(self, shop):
        if self.file_shops:
            return self.file_shops[shop][1]
        return self.rare_slots[self.SHOP_ITEM_TABLES.get(shop, 1)]

    def set_file_shops(self, shops):
        self.file_shops = shops
        if self.tool.manager.shops:
            self._fill_shop()

    def _fill_shop(self, *_):
        shop = max(0, self.shop_list.currentRow())
        with QSignalBlocker(self.shop_list):
            self.shop_list.setCurrentRow(shop)
        shops = self.section("shops")
        for row in range(NB_SHOPS):
            self.shop_list.item(row).setData(Qt.ItemDataRole.ForegroundRole, None if shops.is_visited(row) else QBrush(QColor("gray")))
        with QSignalBlocker(self.visited_check):
            self.visited_check.setChecked(shops.is_visited(shop))
        items, rare = self._items(shop), self._rare(shop)
        for slot, label in enumerate(self.item_labels):
            label.setVisible(items[slot] != 0)
            label.setText(self.tool.kernel_names.item_name(items[slot]) or f"Item {items[slot]}")
            font = QFont(label.font())
            font.setItalic(slot in rare)
            label.setFont(font)

    def _on_visited(self, checked):
        self.section("shops").set_visited(self.shop_list.currentRow(), checked)
        self._fill_shop()


class DrawPointsPage(SavePage):
    """The state of the 256 draw points."""

    VANILLA_NOTE = ("Magic and places are the vanilla game's. A mod can change the magic: open its draw_data.csv "
                    "(made by the Cid tool) with the toolbar's Import complementary.")

    def __init__(self, tool):
        super().__init__(tool)
        data = tool.hyne_data
        self.vanilla_magic = data["draw_point_magic"]
        self.magic_ids = list(self.vanilla_magic)
        state_entries = [{"value": value, "name": name} for value, name in enumerate(DRAW_POINT_STATES)]
        self.state_model = _shared_model(self, state_entries)
        self.table = QTableWidget(NB_DRAW_POINTS, 3)
        self.table.setHorizontalHeaderLabels(["Magic", "Location", "State"])
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setSizeAdjustPolicy(QAbstractItemView.SizeAdjustPolicy.AdjustToContents)
        self.table.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Expanding)
        self.state_combos = []
        for point in range(NB_DRAW_POINTS):
            location = data["draw_point_locations"][point]
            area = "World map" if point >= NB_DRAW_POINTS // 2 else "Field"
            place = tool.field_names.get(location, "???") if location >= 0 else "Nowhere"
            self.table.setItem(point, 0, QTableWidgetItem(tool.magic_label(self.magic_ids[point])))
            self.table.setItem(point, 1, QTableWidgetItem(f"{area} - {place}"))
            combo = QComboBox()
            combo.setModel(self.state_model)
            combo.currentIndexChanged.connect(lambda index, p=point: self.section("draw_points").set_state(p, index))
            self.state_combos.append(combo)
            self.table.setCellWidget(point, 2, combo)
        self.all_combo = QComboBox()
        self.all_combo.setModel(self.state_model)
        self.all_button = QPushButton("Set all")
        self.all_button.setToolTip("Give every draw point this state")
        self.all_button.clicked.connect(self._set_all)
        bottom = QHBoxLayout()
        bottom.addWidget(self.all_combo)
        bottom.addWidget(self.all_button)
        bottom.addStretch(1)
        layout = QVBoxLayout(self)
        self.note = QLabel(self.VANILLA_NOTE)
        self.note.setStyleSheet("color: gray;")
        layout.addWidget(self.note)
        table_row = QHBoxLayout()
        table_row.addWidget(self.table)
        table_row.addStretch(1)
        layout.addLayout(table_row, 1)
        layout.addLayout(bottom)
        self._refills.append(self._fill)

    def set_magic_ids(self, magic_ids, source=""):
        """The magic of each draw point, from a mod's file; None for the vanilla ones."""
        self.magic_ids = list(magic_ids) if magic_ids else list(self.vanilla_magic)
        self.note.setText(f"Magic from {source}. Places are the vanilla game's." if magic_ids else self.VANILLA_NOTE)
        self.relabel_magic()

    def relabel_magic(self):
        for point, magic in enumerate(self.magic_ids):
            self.table.item(point, 0).setText(self.tool.magic_label(magic))

    def _fill(self):
        for point, combo in enumerate(self.state_combos):
            with QSignalBlocker(combo):
                combo.setCurrentIndex(self.section("draw_points").state(point))

    def _set_all(self):
        for point in range(NB_DRAW_POINTS):
            self.section("draw_points").set_state(point, self.all_combo.currentIndex())
        self._fill()
        self.tool._mark_dirty()


class WorldMapPage(SavePage):
    """Camera, rental car, displayed map, messages shown once, quests, where the party and vehicles stand."""

    UNUSED_POSITION_TIP = "The game never writes this row in normal play."

    def __init__(self, tool):
        super().__init__(tool)
        values_group = _form_group("World map", [
            ("Camera angle:", self.spin("world_map", "steps", 0, U16_MAX, "Where the world map camera faces, 0 to 4095 for a full turn")),
            (tool._grey_label("Unused:", "No code reads these two bytes."), self.unused_spin("world_map", "car_steps", U16_MAX)),
            ("Rental car:", self.spin("world_map", "rental_car", 0, U8_MAX, "0 = not allowed, 255 = none")),
            ("Displayed map:", self.combo("world_map", "displayed_map",
                                          [{"value": 0, "name": "None"}, {"value": 1, "name": "Globe"}, {"value": 2, "name": "Map"}])),
        ])
        vehicles_group = self.bit_group("Messages shown once", "world_map", "vehicles", WORLD_MESSAGE_NAMES, columns=4,
                                        tooltip="The world map scripts show each of these the first time, then tick it: the "
                                                "controls of a vehicle when first boarded, and a few story lines.")
        pupu_group = self.bit_group("PuPu quest", "world_map", "pupu_quest", PUPU_QUEST_NAMES, columns=4)
        obel_grid = QGridLayout()
        for index, (text, byte, bit) in enumerate(OBEL_QUEST_FLAGS):
            obel_grid.addWidget(self.bit_check("world_map", "obel_quest", byte * 8 + bit, text), index // 2, index % 2)
        obel_state = QFormLayout()
        obel_state.addRow("Progress:", self.combo("world_map", "obel_state", OBEL_STATES,
                                                  "Where the quest stands. Meeting a Liar Rock replaces it with the kind "
                                                  "of rock, drawn at random, which decides what that rock says."))
        obel_layout = QVBoxLayout()
        obel_layout.addLayout(obel_state)
        obel_layout.addLayout(obel_grid)
        obel_group = QGroupBox("Obel Lake quest")
        obel_group.setLayout(obel_layout)

        self.position_spins = {}
        positions = QGridLayout()
        for column, (text, _low, _high) in enumerate(WORLD_POSITION_COLUMNS, start=1):
            positions.addWidget(QLabel(text), 0, column)
        for row in range(NB_WORLD_POSITIONS):
            unused = row in WORLD_UNUSED_POSITIONS
            name = f"{WORLD_POSITION_ROWS[row]}:"
            positions.addWidget(tool._grey_label(name, self.UNUSED_POSITION_TIP) if unused else QLabel(name), row + 1, 0)
            for column, (_text, low, high) in enumerate(WORLD_POSITION_COLUMNS):
                spin = tool._spinbox(low, high, tooltip=self.UNUSED_POSITION_TIP if unused else "")
                spin.valueChanged.connect(lambda _value, r=row: self._on_place(r))
                self.position_spins[row, column] = spin
                positions.addWidget(spin, row + 1, column + 1)
                if unused:
                    tool.mark_unused(spin)
        self._refills.append(self._fill_positions)
        positions_group = QGroupBox("Positions")
        positions_group.setToolTip("Where the party and each vehicle stand on the world map. Y is stored negated; the angle "
                                   "is 0 to 4095 for a full turn. Each row is 12 bytes: two longs and two words.")
        positions_group.setLayout(positions)

        left = QVBoxLayout()
        left.addWidget(values_group)
        left.addWidget(vehicles_group)
        left.addWidget(pupu_group)
        left.addWidget(positions_group)
        left.addStretch(1)
        right = QVBoxLayout()
        right.addWidget(obel_group)
        right.addStretch(1)
        layout = QHBoxLayout(self)
        layout.addLayout(left)
        layout.addLayout(right)
        layout.addStretch(1)

    def _on_place(self, row):
        self.section("world_map").set_place(row, *(self.position_spins[row, column].value()
                                                   for column in range(len(WORLD_POSITION_COLUMNS))))

    def _fill_positions(self):
        for row in range(NB_WORLD_POSITIONS):
            for column, value in enumerate(self.section("world_map").place(row)):
                with QSignalBlocker(self.position_spins[row, column]):
                    self.position_spins[row, column].setValue(value)


class ChocoboPage(SavePage):
    """Chocobo World: Boko's level, HP, weapon, items, quest flags."""

    def __init__(self, tool):
        super().__init__(tool)
        stats_group = _form_group("Boko", [
            ("ID:", self.spin("chocobo", "boko_id", 0, 999)),
            ("Level:", self.spin("chocobo", "level", 0, U8_MAX)),
            ("Current HP:", self.spin("chocobo", "current_hp", 0, U8_MAX)),
            ("Max HP:", self.spin("chocobo", "max_hp", 0, U8_MAX)),
            ("Weapon:", self.spin("chocobo", "weapon", 0, 9999)),
            ("Rank:", self.spin("chocobo", "rank", 1, U8_MAX + 1, "1 is the best")),
            ("Move:", self.spin("chocobo", "move", 0, U8_MAX)),
            ("Save count:", self.u32_spin("chocobo", "save_count")),
            ("Summon level in game:", self.combo("chocobo", "summon_level",
                                                 [{"value": value, "name": name} for value, name in enumerate(SUMMON_LEVEL_NAMES)])),
        ])
        items_group = _form_group("Items", [
            (f"Class {letter}:", self.spin("chocobo", f"class_{letter.lower()}_items", 0, U8_MAX))
            for letter in "ABCD"])
        flags_group = self.bit_group("Progress", "chocobo", "flags", ChocoboWorld.FLAG_NAMES)
        name_note = QLabel("Boko's name is on the Misc tab.")
        name_note.setStyleSheet("color: gray;")
        left = QVBoxLayout()
        left.addWidget(stats_group)
        left.addWidget(name_note)
        left.addStretch(1)
        right = QVBoxLayout()
        right.addWidget(items_group)
        right.addWidget(flags_group)
        right.addStretch(1)
        layout = QHBoxLayout(self)
        layout.addLayout(left)
        layout.addLayout(right)
        layout.addStretch(1)


class LoadScreenPage(SavePage):
    """What the load screen shows, the save's header. HyneManager updates what follows an edit on
    save, as the game does when it saves."""

    def __init__(self, tool):
        super().__init__(tool)
        location_entries = [{"value": value, "name": name} for value, name in sorted(tool.field_names.items())]
        self.location_combo = self.shared_combo("header", "location", _shared_model(self, location_entries),
                                                "The place shown (the game sets it when it saves)")
        member_entries = [{"value": value, "name": name} for value, name in enumerate(FIELD_PARTY_NAMES)]
        member_entries.append({"value": 0xFF, "name": "None"})
        self.time_label = QLabel()
        time_spin = self.u32_spin("header", "time", "Play time shown, in seconds")
        time_spin.valueChanged.connect(lambda _value: self.time_label.setText(format_seconds(time_spin.value())))
        self._refills.append(lambda: self.time_label.setText(format_seconds(self.section("header").time)))
        time_row = QHBoxLayout()
        time_row.addWidget(time_spin)
        time_row.addWidget(self.time_label)
        time_row.addStretch(1)
        party_row = QHBoxLayout()
        for slot in (1, 2, 3):
            party_row.addWidget(self.combo("header", f"party_{slot}", member_entries, "Model shown"))
        party_row.addStretch(1)
        disc_spin = self.spin("header", "disc", 0, U8_MAX, "0-based: 0 shows disc 1")
        form = QFormLayout()
        form.addRow("Location:", self.location_combo)
        form.addRow("Save count:", self.spin("header", "save_count", 0, U16_MAX, "Saves made in this game"))
        form.addRow("Current save:", self.u32_spin("header", "current_save", "The game's counter of saves over all slots"))
        form.addRow("Leader level:", self.spin("header", "level", 0, U8_MAX))
        form.addRow("Leader HP:", self.spin("header", "leader_hp", 0, U16_MAX))
        form.addRow("Leader max HP:", self.spin("header", "leader_max_hp", 0, U16_MAX))
        form.addRow("Gil:", self.u32_spin("header", "gil"))
        form.addRow("Play time:", time_row)
        form.addRow("Disc:", disc_spin)
        form.addRow("Party:", party_row)
        group = QGroupBox("Load screen")
        group.setLayout(form)
        note = QLabel("Saving keeps these following your edits: changing the party, the leader's EXP or HP, gil, play time "
                      "or disc updates them here.\nA value you set here yourself stays until its source changes. "
                      "Max HP is not updated: the game computes it from junctions.")
        note.setWordWrap(True)
        note.setStyleSheet("color: gray;")
        note.setMaximumWidth(640)
        column = QVBoxLayout()
        column.addWidget(group)
        column.addWidget(note)
        column.addStretch(1)
        layout = QHBoxLayout(self)
        layout.addLayout(column)
        layout.addStretch(1)


class FieldVariablesPage(SavePage):
    """The field variables the scripts and the engine use, named from the research on them. One another tab
    holds is only shown here: that tab keeps its copies in step."""
    CRONOS_SETTING = "hyne/cronos_variables"
    COLUMN_VALUE = 2
    COLUMN_TEXT = 4
    CERTAINTY_NAMES = {"sure": "Sure", "likely": "Likely", "unknown": "Unclear"}
    TYPE_NAMES = {(1, False): "Byte", (1, True): "Signed byte", (2, False): "Word", (2, True): "Signed word",
                  (4, False): "Long", (4, True): "Signed long"}
    BIT_NAME_LENGTH = 36

    def __init__(self, tool):
        super().__init__(tool)
        self.entries = tool.field_variable_entries
        self._current = None
        self._search_texts = [
            " ".join([str(entry["var"]), entry["text"], *entry["fields"], *entry.get("flags", {}).values(),
                      *entry.get("values", {}).values()]).lower() for entry in self.entries
        ]

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search a number, a word or a field name")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._apply_filter)
        self.cronos_check = QCheckBox("Cronos")
        self.cronos_check.setToolTip("Also lists the variables the Cronos mod adds. They mean nothing in another save")
        if tool.settings is not None:
            self.cronos_check.setChecked(tool.settings.value(self.CRONOS_SETTING, False, type=bool))
        self.cronos_check.toggled.connect(self._on_cronos)
        self.only_set_check = QCheckBox("Only values not zero")
        self.only_set_check.toggled.connect(self._apply_filter)
        filters = QWidget()
        filters.setProperty("read_only_preview", True)   # choosing what to show edits nothing
        filter_row = QHBoxLayout(filters)
        filter_row.setContentsMargins(0, 0, 0, 0)
        filter_row.addWidget(self.search_edit, 1)
        filter_row.addWidget(self.cronos_check)
        filter_row.addWidget(self.only_set_check)

        self.table = QTableWidget(len(self.entries), 5)
        self.table.setProperty("read_only_preview", True)
        self.table.setHorizontalHeaderLabels(["Var", "Type", "Value", "How sure", "What it holds"])
        self.table.horizontalHeaderItem(3).setToolTip(
            "Sure: the dialogue or the code shows it. Likely: the evidence points that way. "
            "Unclear: only where it is used is known.")
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.table.horizontalHeader()
        for column in (0, 1, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setColumnWidth(self.COLUMN_VALUE, 90)
        header.setSectionResizeMode(self.COLUMN_TEXT, QHeaderView.ResizeMode.Stretch)
        grey = QBrush(QColor("gray"))
        for row, entry in enumerate(self.entries):
            cells = [str(entry["var"]), self.TYPE_NAMES[entry["size"], entry["signed"]], "",
                     self.CERTAINTY_NAMES.get(entry.get("certainty"), ""), entry["text"].split("\n")[0]]
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if field_var_tab(entry["var"]):
                    item.setForeground(grey)
                self.table.setItem(row, column, item)
        self.table.currentCellChanged.connect(self._on_row)

        self.title_label = QLabel()
        title_font = QFont(self.title_label.font())
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        self.text_view = QPlainTextEdit()
        self.text_view.setProperty("read_only_preview", True)
        self.text_view.setReadOnly(True)
        self.fields_label = QLabel()
        self.fields_label.setWordWrap(True)
        self.value_spin = tool._u32_spinbox(tooltip="The variable's value in the save")
        self.value_spin.valueChanged.connect(self._on_value)
        self.value_name_label = QLabel()
        self.bit_group = QGroupBox("Bits")
        bit_layout = QVBoxLayout(self.bit_group)
        self.bit_checks = []
        for bit in range(8):
            check = QCheckBox()
            check.toggled.connect(lambda checked, mask=1 << bit: self._on_bit(mask, checked))
            bit_layout.addWidget(check)
            self.bit_checks.append(check)
        value_row = QHBoxLayout()
        value_row.addWidget(QLabel("Value:"))
        value_row.addWidget(self.value_spin)
        value_row.addWidget(self.value_name_label, 1)
        panel = QGroupBox("Selected variable")
        panel.setFixedWidth(330)
        panel_layout = QVBoxLayout(panel)
        panel_layout.addWidget(self.title_label)
        panel_layout.addWidget(self.text_view, 1)
        panel_layout.addWidget(self.fields_label)
        panel_layout.addLayout(value_row)
        panel_layout.addWidget(self.bit_group)

        left = QVBoxLayout()
        left.addWidget(filters)
        left.addWidget(self.table)
        layout = QHBoxLayout(self)
        layout.addLayout(left, 1)
        layout.addWidget(panel)
        self._refills.append(self._refresh)

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh()   # another tab may have changed a variable it holds

    def _value(self, entry):
        return self.section("field_variables").value(entry["var"], entry["size"], entry["signed"])

    def _refresh(self):
        if self.section("field_variables") is None:
            return
        for row, entry in enumerate(self.entries):
            self.table.item(row, self.COLUMN_VALUE).setText(str(self._value(entry)))
        self._apply_filter()
        if self.table.currentRow() < 0 and self.entries:
            self.table.setCurrentCell(0, 0)
        else:
            self._show_current()

    def _on_cronos(self, checked):
        if self.tool.settings is not None:
            self.tool.settings.setValue(self.CRONOS_SETTING, checked)
        self._apply_filter()

    def _apply_filter(self, *_):
        if self.section("field_variables") is None:
            return
        words = self.search_edit.text().lower().split()
        cronos = self.cronos_check.isChecked()
        only_set = self.only_set_check.isChecked()
        for row, entry in enumerate(self.entries):
            shown = cronos or "mod" not in entry
            shown = shown and not (only_set and not self._value(entry))
            shown = shown and all(word in self._search_texts[row] for word in words)
            self.table.setRowHidden(row, not shown)

    def _on_row(self, row, *_):
        self._current = self.entries[row] if 0 <= row < len(self.entries) else None
        self._show_current()

    def _show_current(self):
        entry = self._current
        if entry is None:
            return
        tab = field_var_tab(entry["var"])
        self.title_label.setText(f"Variable {entry['var']}: {self.TYPE_NAMES[entry['size'], entry['signed']].lower()}")
        values = entry.get("values", {})
        self.text_view.setPlainText("\n".join([entry["text"], *([""] if values else []),
                                               *(f"{value}: {name}" for value, name in values.items())]))
        if entry["nb_fields"]:
            more = entry["nb_fields"] - len(entry["fields"])
            where = f"Used in {', '.join(entry['fields'])}" + (f" and {more} more fields." if more else ".")
        else:
            where = "No field script uses it: only the engine does."
        self.fields_label.setText(where + (f"\nEdited on the {tab} tab." if tab else ""))
        bits = 8 * entry["size"]
        low = -(1 << (bits - 1)) if entry["signed"] else 0
        high = (1 << (bits - 1)) - 1 if entry["signed"] else (1 << bits) - 1
        with QSignalBlocker(self.value_spin):
            self.value_spin.setRange(low, high)
            self.value_spin.setValue(self._value(entry))
        self.value_name_label.setText(values.get(str(self._value(entry)), ""))
        self.value_spin.setEnabled(tab is None)
        self.bit_group.setVisible(entry["size"] == 1)
        self.bit_group.setEnabled(tab is None)
        if entry["size"] == 1:
            names = entry.get("flags", {})
            raw = self.section("field_variables").value(entry["var"])
            for bit, check in enumerate(self.bit_checks):
                mask = 1 << bit
                name = names.get(str(mask), "")
                with QSignalBlocker(check):
                    check.setText(f"{mask}: {name[:self.BIT_NAME_LENGTH]}" if name else str(mask))
                    check.setToolTip(name)
                    check.setChecked(bool(raw & mask))

    def _on_value(self, _value):
        entry = self._current
        if entry is None:
            return
        self.section("field_variables").set_value(entry["var"], self.value_spin.value(), entry["size"], entry["signed"])
        self._written()

    def _on_bit(self, mask, checked):
        entry = self._current
        if entry is None:
            return
        view = self.section("field_variables")
        raw = view.value(entry["var"])
        view.set_value(entry["var"], raw | mask if checked else raw & ~mask & U8_MAX)
        self._written()

    def _written(self):
        row = self.entries.index(self._current)
        self.table.item(row, self.COLUMN_VALUE).setText(str(self._value(self._current)))
        self._show_current()
        self.tool._mark_dirty()


class ItemsExtrasPage(SavePage):
    """The battle order and Timber Maniacs pages of the Items tab."""

    def __init__(self, tool):
        super().__init__(tool)
        self.order_list = QListWidget()
        self.order_list.setToolTip("Order of the 32 battle items in the in-battle Item list. A newly obtained battle "
                                   "item is moved to the first place no owned item uses.")
        self.order_up = QPushButton("Move up")
        self.order_down = QPushButton("Move down")
        self.order_up.clicked.connect(lambda: self._move_order(-1))
        self.order_down.clicked.connect(lambda: self._move_order(1))
        self.order_warning = QLabel()
        self.order_warning.setWordWrap(True)
        self.order_warning.setStyleSheet("color:#c0392b; font-weight:bold;")
        self.order_warning.setVisible(False)
        buttons = QHBoxLayout()
        buttons.addWidget(self.order_up)
        buttons.addWidget(self.order_down)
        buttons.addStretch(1)
        order_layout = QVBoxLayout()
        order_layout.addWidget(self.order_warning)
        order_layout.addWidget(self.order_list)
        order_layout.addLayout(buttons)
        order_group = QGroupBox("Battle item order")
        order_group.setLayout(order_layout)
        self._refills.append(self._fill_order)
        self.timber_group = self.bit_list("Timber Maniacs issues read", "progress", "timber_maniacs_bits", TIMBER_MANIACS_ISSUES)
        layout = QHBoxLayout(self)
        layout.addWidget(order_group, 1)
        layout.addWidget(self.timber_group, 1)

    def _fill_order(self, select_place=None):
        order = self.tool.manager.misc.get_battle_order()
        valid = sorted(order) == list(range(len(order)))
        self.order_warning.setVisible(not valid)
        self.order_warning.setText("This save's battle item order is not a valid ordering (each place 0-31 exactly once): "
                                   "the game would write past its arrays. Left as is, not editable here.")
        self.order_up.setEnabled(valid)
        self.order_down.setEnabled(valid)
        self.order_list.clear()
        by_place = {place: item_id for item_id, place in enumerate(order, start=1)}
        for place in range(len(order)):
            item_id = by_place.get(place)
            name = (self.tool.kernel_names.item_name(item_id) or f"Item {item_id}") if item_id else "(none)"
            self.order_list.addItem(f"{place + 1}. {name}" + (f"  [{item_id}]" if item_id else ""))
        if select_place is not None:
            self.order_list.setCurrentRow(select_place)

    def _move_order(self, step):
        """Swap the places of the selected battle item and its neighbour."""
        place = self.order_list.currentRow()
        other = place + step
        order = self.tool.manager.misc.get_battle_order()
        if place < 0 or not 0 <= other < len(order):
            return
        first, second = order.index(place), order.index(other)
        order[first], order[second] = other, place
        self.tool.manager.misc.set_battle_order(order)
        self._fill_order(select_place=other)
        self.tool._mark_dirty()
