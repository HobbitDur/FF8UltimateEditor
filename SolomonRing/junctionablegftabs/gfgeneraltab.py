from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QSpinBox
)
import json

from SolomonRing.gfdata import GFData


class GFGeneralTab(QWidget):
    def __init__(self, game_data_folder="FF8GameData"):
        super().__init__()

        # Load json
        json_path = game_data_folder + "/Resources/json/special_action.json"
        with open(json_path, "r", encoding="utf-8") as f:
            self.data = json.load(f)

        # Main layout
        main_layout = QVBoxLayout()

        label_width = 100
        combo_width = 250
        spin_width = 50
        pair_spacing = 50

        # Animation row
        row = QHBoxLayout()

        self.animation_combo = QComboBox()
        for action in self.data["special_action"]:
            self.animation_combo.addItem(action["name"], action["id"])
        self.animation_combo.setCurrentIndex(0)

        lbl = QLabel("Animation")
        lbl.setFixedWidth(label_width)
        self.animation_combo.setFixedWidth(combo_width)
        row.addWidget(lbl)
        row.addWidget(self.animation_combo)
        row.addStretch()
        main_layout.addLayout(row)

        # Element row
        row = QHBoxLayout()

        self.element_combo = QComboBox()
        elements = [
            ("None", 0),
            ("Fire", 1),
            ("Ice", 2),
            ("Thunder", 4),
            ("Earth", 8),
            ("Poison", 16),
            ("Wind", 32),
            ("Water", 64),
            ("Holy", 128)
        ]
        for name, value in elements:
            self.element_combo.addItem(name, value)

        lbl = QLabel("Element")
        lbl.setFixedWidth(label_width)
        self.element_combo.setFixedWidth(combo_width)
        row.addWidget(lbl)
        row.addWidget(self.element_combo)
        row.addStretch()
        main_layout.addLayout(row)

        # Attack Type row
        row = QHBoxLayout()

        self.attack_type_combo = QComboBox()
        self.attack_type_combo.addItems(["None", "Physical", "Magical", "Curative Magic", "Curative Item", "Revive", "Full HP Revive", "% Physical", "% Magical", "Renzokuken Finisher",
                                         "Squall Gunblade", "GF", "Scan", "LV Down", "Summon Item", "GF (Ignore SPR)", "LV Up", "Card", "Kamikaze", "Devour", "% GF", "Unknown 1",
                                         "Magical (Ignore SPR)", "Angelo Search", "Moogle Dance", "White Wind (Quistis)", "LV X", "Fixed Damage", "Current HP - 1",
                                         "Fixed Damage based on GF LV", "Unknown 2", "Unknown 3", "Curative % HP", "Unknown 4", "Everyone's Grudge", "1 HP", "Physical (Ignore VIT)"])
        self.attack_type_combo.setCurrentIndex(0)
        lbl = QLabel("Type")
        lbl.setFixedWidth(label_width)
        self.attack_type_combo.setFixedWidth(combo_width)
        row.addWidget(lbl)
        row.addWidget(self.attack_type_combo)
        row.addStretch()
        main_layout.addLayout(row)

        # Power / Power Mod / Level Mod
        self.power_spin = QSpinBox()
        self.power_spin.setRange(0, 255)
        self.power_spin.setFixedWidth(spin_width)

        self.power_mod_spin = QSpinBox()
        self.power_mod_spin.setRange(0, 255)
        self.power_mod_spin.setFixedWidth(spin_width)

        self.level_mod_spin = QSpinBox()
        self.level_mod_spin.setRange(0, 255)
        self.level_mod_spin.setFixedWidth(spin_width)

        row = QHBoxLayout()

        for i, (name, spin) in enumerate([("Power", self.power_spin), ("Power Mod", self.power_mod_spin), ("Level Mod", self.level_mod_spin)]):
            lbl = QLabel(name)
            lbl.setFixedWidth(label_width)

            row.addWidget(lbl)
            row.addWidget(spin)

            if i < 2:  # after spinner 1 and 2
                row.addSpacing(pair_spacing)  # adjust spacing to taste

        row.addStretch()
        main_layout.addLayout(row)

        # HP1 / HP2 / HP3
        self.hp1_spin = QSpinBox()
        self.hp1_spin.setRange(0, 255)
        self.hp1_spin.setFixedWidth(spin_width)

        self.hp2_spin = QSpinBox()
        self.hp2_spin.setRange(0, 255)
        self.hp2_spin.setFixedWidth(spin_width)

        self.hp3_spin = QSpinBox()
        self.hp3_spin.setRange(0, 255)
        self.hp3_spin.setFixedWidth(spin_width)

        row = QHBoxLayout()

        for i, (name, spin) in enumerate([("HP1", self.hp1_spin), ("HP2", self.hp2_spin), ("HP3", self.hp3_spin)]):
            lbl = QLabel(name)
            lbl.setFixedWidth(label_width)

            row.addWidget(lbl)
            row.addWidget(spin)

            if i < 2:
                row.addSpacing(pair_spacing)

        row.addStretch()
        main_layout.addLayout(row)

        main_layout.addStretch()
        self.setLayout(main_layout)

    def load_gf_data(self, gf_data: GFData):
        # Animation - find the combo index whose user data matches the value
        animation_value = gf_data.get("animation")
        index = self.animation_combo.findData(animation_value)
        self.animation_combo.setCurrentIndex(index if index >= 0 else 0)

        # Element
        element_value = gf_data.get("element")
        index = self.element_combo.findData(element_value)
        self.element_combo.setCurrentIndex(index if index >= 0 else 0)

        # Attack type
        self.attack_type_combo.setCurrentIndex(gf_data.get("attack_type"))

        # Spinboxes
        self.power_spin.setValue(gf_data.get("power"))
        self.power_mod_spin.setValue(gf_data.get("power_mod"))
        self.level_mod_spin.setValue(gf_data.get("level_mod"))
        self.hp1_spin.setValue(gf_data.get("hp1"))
        self.hp2_spin.setValue(gf_data.get("hp2"))
        self.hp3_spin.setValue(gf_data.get("hp3"))

    def save_gf_data(self, gf_data: GFData):
        gf_data.set("animation", self.animation_combo.currentData())
        gf_data.set("element", self.element_combo.currentData())
        gf_data.set("attack_type", self.attack_type_combo.currentIndex())
        gf_data.set("power", self.power_spin.value())
        gf_data.set("power_mod", self.power_mod_spin.value())
        gf_data.set("level_mod", self.level_mod_spin.value())
        gf_data.set("hp1", self.hp1_spin.value())
        gf_data.set("hp2", self.hp2_spin.value())
        gf_data.set("hp3", self.hp3_spin.value())