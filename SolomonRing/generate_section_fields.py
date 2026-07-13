"""Generator for kernel_section_fields.json (all 30 kernel data sections).

Fields are listed in payload order; the offset of each is computed from the
section's payload start (= nb_text_offsets * 2). Every section asserts its
computed end offset against the known sub_section_size, catching any drift.

Sources: FF8ModdingWiki 'Section Structure' tables, cross-checked against the
doomtrain KernelWorker.cs structs. Section 3 (GFs) reuses the proven
`junctionable_gf_data` offsets from kernel_bin_data.json (the wiki's section-3
tail is off by one - flagged for the IDA pass).
"""
import json
import os

_JSON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "FF8GameData", "Resources", "json")
DEST = os.path.join(_JSON_DIR, "kernel_section_fields.json")
KERNEL = os.path.join(_JSON_DIR, "kernel_bin_data.json")

sections = {}


def sec(section_id, nb_text, text_labels, groups, sub_size, entry_names=None):
    offset = nb_text * 2
    fields = []
    for gname, items in groups:
        for it in items:
            name, size, lookup = it[0], it[1], it[2]
            label = it[3] if len(it) > 3 else None
            f = {"name": name, "offset": offset, "size": size}
            if lookup:
                f["lookup"] = lookup
            if label:
                f["label"] = label
            if gname:
                f["group"] = gname
            fields.append(f)
            offset += size
    assert offset == sub_size, f"section {section_id}: end {offset:#x} != sub_size {sub_size:#x}"
    cfg = {"section_id": section_id, "fields": fields}
    if text_labels:
        cfg["text_labels"] = text_labels
    if entry_names:
        cfg["entry_names"] = entry_names
    sections[str(section_id)] = cfg


# common ---------------------------------------------------------------------
NAMEDESC = ["Name", "Description"]
COMPAT = ["quezacotl", "shiva", "ifrit", "siren", "brothers", "diablos", "carbuncle",
          "leviathan", "pandemona", "cerberus", "alexander", "doomtrain", "bahamut",
          "cactuar", "tonberry", "eden"]
COMPAT_LABELS = ["Quezacotl", "Shiva", "Ifrit", "Siren", "Brothers", "Diablos", "Carbuncle",
                 "Leviathan", "Pandemona", "Cerberus", "Alexander", "Doomtrain", "Bahamut",
                 "Cactuar", "Tonberry", "Eden"]


def status_pair_1_then_2():
    return [("status_1", 2, "status_1", "Status 1 (0-15)"),
            ("status_2", 4, "status_2", "Status 2 (16-47)")]


# 1: Battle commands ---------------------------------------------------------
sec(1, 2, NAMEDESC, [("Data", [
    ("ability_data_id", 1, None, "Ability data ID"),
    ("unknown_flags", 1, None, "Unknown flags"),
    ("target_info", 1, "target_info"),
    ("unknown_0x07", 1, None, "Unknown 0x07"),
])], sub_size=8)

# 2: Magic (built earlier - keep identical) ----------------------------------
JSTATS = ["hp", "str", "vit", "mag", "spr", "spd", "eva", "hit", "luck"]
sec(2, 2, NAMEDESC, [
    ("General", [
        ("magic_id", 2, "magic", "Magic ID (effect/anim)"),
        ("animation", 1, None, "Animation category"),
        ("attack_type", 1, "attack_type"),
        ("spell_power", 1, None, "Spell power"),
        ("unknown_0x09", 1, None, "Unknown 0x09"),
        ("target_info", 1, "target_info"),
        ("attack_flags", 1, "attack_flags"),
        ("draw_resist", 1, None, "Draw resist"),
        ("hit_count", 1, None, "Hit count"),
        ("element", 1, "element"),
        ("unknown_0x0f", 1, None, "Unknown 0x0F"),
        ("status_2", 4, "status_2", "Status 2 (attack)"),
        ("status_1", 2, "status_1", "Status 1 (attack)"),
        ("status_accuracy", 1, None, "Status attack accuracy"),
    ]),
    ("Junction (stats)", [(f"j_{s}", 1, None, f"J-{s.upper()}") for s in JSTATS] + [
        ("j_elem_attack", 1, "element", "J-Elem attack"),
        ("j_elem_attack_value", 1, None, "J-Elem attack value"),
        ("j_elem_defense", 1, "element", "J-Elem defense"),
        ("j_elem_defense_value", 1, None, "J-Elem defense value"),
        ("j_status_attack_value", 1, None, "J-Status attack value"),
        ("j_status_defense_value", 1, None, "J-Status defense value"),
        ("j_status_attack", 2, "j_status", "J-Status attack"),
        ("j_status_defend", 2, "j_status", "J-Status defend"),
    ]),
    ("GF Compatibility", [(f"compat_{c}", 1, None, COMPAT_LABELS[i]) for i, c in enumerate(COMPAT)]),
    ("Misc", [("unknown_0x3a", 2, None, "Unknown 0x3A")]),
], sub_size=60)

# 3: Junctionable GFs (reuse proven offsets from junctionable_gf_data) --------
gf_general = [
    ("attack_animation", 2, "attack_animation", "Attack animation"),
    ("attack_type", 1, "attack_type"),
    ("gf_power", 1, None, "GF power"),
    ("unknown_0x08", 1, None, "Unknown 0x08"),
    ("target_info", 1, "target_info"),
    ("attack_flags", 1, "attack_flags"),
    ("target_animation", 1, None, "Target hit animation"),
    ("hit_count", 1, None, "Hit count"),
    ("element", 1, "element"),
    ("status_1", 2, "status_1", "Status 1 (0-15)"),
    ("status_2", 4, "status_2", "Status 2 (16-47)"),
    ("gf_hp_modifier_1", 1, None, "GF HP modifier 1"),
    ("gf_hp_modifier_2", 1, None, "GF HP modifier 2"),
    ("gf_hp_modifier_3", 1, None, "GF HP modifier 3"),
    ("gf_level_modifier_1", 1, None, "GF level modifier 1"),
    ("gf_level_modifier_2", 1, None, "GF level modifier 2"),
    ("status_attack_enabler", 1, None, "Status attack enabler"),
    ("power_mod", 1, None, "Power mod"),
    ("level_mod", 1, None, "Level mod"),
]
# explicit offsets for the general block (non-contiguous: modifiers/tail)
gf_offsets = {
    "attack_animation": 0x04, "attack_type": 0x06, "gf_power": 0x07, "unknown_0x08": 0x08,
    "target_info": 0x09,
    "attack_flags": 0x0A, "target_animation": 0x0B, "hit_count": 0x0C, "element": 0x0D,
    "status_1": 0x0E, "status_2": 0x10, "gf_hp_modifier_1": 0x14, "gf_hp_modifier_2": 0x15,
    "gf_hp_modifier_3": 0x16, "gf_level_modifier_1": 0x18, "gf_level_modifier_2": 0x19,
    "status_attack_enabler": 0x1A, "power_mod": 0x82, "level_mod": 0x83,
}
gf_fields = []
for it in gf_general:
    name, size, lookup = it[0], it[1], it[2]
    label = it[3] if len(it) > 3 else None
    f = {"name": name, "offset": gf_offsets[name], "size": size, "group": "General"}
    if lookup:
        f["lookup"] = lookup
    if label:
        f["label"] = label
    gf_fields.append(f)
for i in range(1, 22):
    base = 0x1B + 4 * (i - 1)
    gf_fields.append({"name": f"ability{i}", "offset": base + 2, "size": 1,
                      "lookup": "junctionable_ability", "label": f"Ability {i}", "group": "Abilities"})
    gf_fields.append({"name": f"ability{i}_unlocker", "offset": base, "size": 1,
                      "label": f"Ability {i} unlocker", "group": "Abilities"})
    gf_fields.append({"name": f"ability{i}_learn", "offset": base + 3, "size": 1,
                      "label": f"Ability {i} learn order", "group": "Abilities",
                      "help": "GF ability-learning order byte - read by battleComputeEndBattle "
                              "to pick the GF's next LearningAbility after this one completes."})
# GF Boost parameters @0x80-0x81 (IDA gfBoostParams: each byte x15 -> Boost min/max,
# pre_computeGFBoost)
gf_fields.append({"name": "boost_param_1", "offset": 0x80, "size": 1, "group": "General",
                  "label": "Boost param 1 (x15)",
                  "help": "GF Boost parameter - multiplied by 15 by pre_computeGFBoost."})
gf_fields.append({"name": "boost_param_2", "offset": 0x81, "size": 1, "group": "General",
                  "label": "Boost param 2 (x15)",
                  "help": "GF Boost parameter - multiplied by 15 by pre_computeGFBoost."})
# IDA FF8KernelJunctionableGF: padding at 0x6F, compatibility block starts at 0x70
# (the old junctionable_gf_data json was off by one, leaving 0x7F unmapped).
for i, c in enumerate(COMPAT):
    gf_fields.append({"name": f"compat_{c}", "offset": 0x70 + i, "size": 1,
                      "label": COMPAT_LABELS[i], "group": "GF Compatibility"})
sections["3"] = {"section_id": 3, "text_labels": NAMEDESC, "fields": gf_fields}

# 4: Enemy attacks -----------------------------------------------------------
sec(4, 1, ["Name"], [("Data", [
    ("magic_id", 2, "magic", "Magic ID"),
    ("camera_change", 1, None, "Camera change"),
    ("animation", 1, None, "Animation triggered"),
    ("attack_type", 1, "attack_type"),
    ("attack_power", 1, None, "Attack power"),
    ("attack_flags", 1, "attack_flags"),
    ("unknown_0x09", 1, None, "Unknown 0x09"),
    ("element", 1, "element"),
    ("crit_bonus", 1, None, "Attack crit bonus"),
    ("status_attack_enabler", 1, None, "Status attack enabler"),
    ("attack_param", 1, None, "Attack parameter"),
    ("status_1", 2, "status_1", "Status 1 (0-15)"),
    ("status_2", 4, "status_2", "Status 2 (16-47)"),
])], sub_size=20)

# 5: Weapons -----------------------------------------------------------------
sec(5, 1, ["Name"], [("Data", [
    ("renzokuken_finishers", 1, "renzokuken_finisher", "Renzokuken finishers"),
    ("unknown_0x03", 1, None, "Unknown 0x03"),
    ("character_id", 1, "weapon_character", "Character"),
    ("attack_type", 1, "attack_type"),
    ("attack_power", 1, None, "Attack power"),
    ("attack_param", 1, None, "Attack parameter"),
    ("str_bonus", 1, None, "STR bonus"),
    ("weapon_tier", 1, None, "Weapon tier"),
    ("crit_bonus", 1, None, "Crit bonus"),
    ("melee", 1, None, "Melee weapon?"),
])], sub_size=12)

# 6: Renzokuken finishers ----------------------------------------------------
sec(6, 2, NAMEDESC, [("Data", [
    ("magic_id", 2, "magic", "Magic ID"),
    ("attack_type", 1, "attack_type"),
    ("unknown_0x07", 1, None, "Unknown 0x07"),
    ("attack_power", 1, None, "Attack power"),
    ("unknown_0x09", 1, None, "Unknown 0x09"),
    ("target_info", 1, "target_info"),
    ("attack_flags", 1, "attack_flags"),
    ("hit_count", 1, None, "Hit count"),
    ("element", 1, "element", "Element attack"),
    ("element_percent", 1, None, "Element attack %"),
    ("status_attack_enabler", 1, None, "Status attack enabler"),
    ("unknown_0x10", 2, None, "Unknown 0x10"),
    ("status_1", 2, "status_1", "Status 1 (0-15)"),
    ("status_2", 4, "status_2", "Status 2 (16-47)"),
])], sub_size=24)

# 7: Characters --------------------------------------------------------------
char_stats = []
for st in ["hp", "str", "vit", "mag", "spr", "spd", "luck"]:
    for k in range(1, 5):
        char_stats.append((f"{st}_{k}", 1, None, f"{st.upper()} coef {k}"))
sec(7, 1, ["Name"], [
    ("General", [
        ("crisis_level_hp_mult", 1, None, "Crisis level HP multiplier"),
        ("gender", 1, "gender"),
        ("limit_break_id", 1, None, "Limit break ID"),
        ("limit_break_param", 1, None, "Limit break param"),
        ("exp_modifier", 2, None, "EXP modifier"),
    ]),
    ("Stat coefficients", char_stats),
], sub_size=36,
    entry_names=["Squall", "Zell", "Irvine", "Quistis", "Rinoa", "Selphie",
                 "Seifer", "Edea", "Laguna", "Kiros", "Ward"])

# 8: Battle items ------------------------------------------------------------
sec(8, 2, NAMEDESC, [("Data", [
    ("magic_id", 2, "magic", "Magic ID"),
    ("attack_type", 1, "attack_type"),
    ("attack_power", 1, None, "Attack power"),
    ("battle_flag", 1, None, "Battle flag"),
    ("target_info", 1, "target_info"),
    ("unknown_0x0a", 1, None, "Unknown 0x0A"),
    ("attack_flags", 1, "attack_flags"),
    ("unknown_0x0c", 1, None, "Unknown 0x0C"),
    ("status_attack_enabler", 1, None, "Status attack enabler"),
    ("status_1", 2, "status_1", "Status 1 (0-15)"),
    ("status_2", 4, "status_2", "Status 2 (16-47)"),
    ("attack_param", 1, None, "Attack parameter"),
    ("unknown_0x15", 1, None, "Unknown 0x15"),
    ("hit_count", 1, None, "Hit count"),
    ("element", 1, "element"),
])], sub_size=24)

# 9: Non-battle item name/description offsets --------------------------------
sec(9, 2, NAMEDESC, [], sub_size=4)

# 10: Non-junctionable GF attacks --------------------------------------------
sec(10, 1, ["Name"], [("Data", [
    ("attack_animation", 2, "attack_animation", "Attack animation"),
    ("attack_type", 1, "attack_type"),
    ("gf_power", 1, None, "GF power"),
    ("status_attack_enabler", 1, None, "Status attack enabler"),
    ("target_info", 1, "target_info"),
    ("attack_flags", 1, "attack_flags"),
    ("target_hit_animation", 1, None, "Target hit animation"),
    ("hit_count", 1, None, "Hit count"),
    ("element", 1, "element"),
    ("status_group_1", 1, None, "Status 1 (Sleep/Haste/...)"),
    ("status_group_2", 1, None, "Status 2 (Aura/Curse/...)"),
    ("status_group_3", 1, None, "Status 3 (Eject/Double/...)"),
    ("status_group_4", 1, None, "Status 4 (Vit0/...)"),
    ("status_group_5", 1, None, "Status 5 (Death/Poison/...)"),
    ("unknown_0x11", 1, None, "Unknown 0x11"),
    ("power_mod", 1, None, "Power mod"),
    ("level_mod", 1, None, "Level mod"),
])], sub_size=20)

# 11: Command ability data (in battle) ---------------------------------------
sec(11, 0, [], [("Data", [
    ("magic_id", 2, "magic", "Magic ID"),
    ("unknown_0x02", 1, None, "Unknown 0x02"),
    ("animation", 1, None, "Animation triggered"),
    ("attack_type", 1, "attack_type"),
    ("attack_power", 1, None, "Attack power"),
    ("attack_flags", 1, "attack_flags"),
    ("hit_count", 1, None, "Hit count"),
    ("element", 1, "element"),
    ("status_attack_enabler", 1, None, "Status attack enabler"),
    ("status_1", 2, "status_1", "Status 1 (0-15)"),
    ("status_2", 4, "status_2", "Status 2 (16-47)"),
])], sub_size=16)

# 12: Junction abilities -----------------------------------------------------
sec(12, 2, NAMEDESC, [("Data", [
    ("ap", 1, None, "AP to learn"),
    ("junction_flag", 3, None, "Junction ability flag"),
])], sub_size=8)

# 13: Command abilities (GF) -------------------------------------------------
sec(13, 2, NAMEDESC, [("Data", [
    ("ap", 1, None, "AP to learn"),
    ("battle_command_index", 1, "battle_command", "Battle command"),
    ("unknown_0x06", 2, None, "Unknown / Unused"),
])], sub_size=8)

# 14: Stat percentage increasing abilities -----------------------------------
sec(14, 2, NAMEDESC, [("Data", [
    ("ap", 1, None, "AP to learn"),
    ("stat_to_increase", 1, None, "Stat to increase"),
    ("increase_value", 1, None, "Increase value"),
    ("unknown_0x07", 1, None, "Unknown / Unused"),
])], sub_size=8)

# 15: Character abilities -----------------------------------------------------
sec(15, 2, NAMEDESC, [("Data", [
    ("ap", 1, None, "AP to learn"),
    ("chara_flag", 3, None, "Character ability flag"),
])], sub_size=8)

# 16: Party abilities ---------------------------------------------------------
sec(16, 2, NAMEDESC, [("Data", [
    ("ap", 1, None, "AP to learn"),
    ("party_flag", 1, None, "Party ability flag"),
    ("unused_0x06", 2, None, "Unused"),
])], sub_size=8)

# 17: GF abilities ------------------------------------------------------------
sec(17, 2, NAMEDESC, [("Data", [
    ("ap", 1, None, "AP to learn"),
    ("enable_boost", 1, None, "Enable boost"),
    ("stat_to_increase", 1, "stat_to_increase", "Stat to increase"),
    ("increase_value", 1, None, "Increase value"),
])], sub_size=8)

# 18: Menu abilities ----------------------------------------------------------
sec(18, 2, NAMEDESC, [("Data", [
    ("ap", 1, None, "AP to learn"),
    ("menu_index", 1, None, "Index to m00X files"),
    ("start_offset", 1, None, "Start offset"),
    ("end_offset", 1, None, "End offset"),
])], sub_size=8)

# 19: Temporary character limit breaks ---------------------------------------
sec(19, 2, NAMEDESC, [("Data", [
    ("magic_id", 2, "magic", "Magic ID"),
    ("attack_type", 1, "attack_type"),
    ("attack_power", 1, None, "Attack power"),
    ("unknown_0x08", 2, None, "Unknown 0x08"),
    ("target_info", 1, "target_info"),
    ("attack_flags", 1, "attack_flags"),
    ("hit_count", 1, None, "Hit count"),
    ("element", 1, "element", "Element attack"),
    ("element_percent", 1, None, "Element attack %"),
    ("status_attack_enabler", 1, None, "Status attack enabler"),
    ("status_1", 2, "status_1", "Status 1 (0-15)"),
    ("unknown_0x12", 2, None, "Unknown 0x12"),
    ("status_2", 4, "status_2", "Status 2 (16-47)"),
])], sub_size=24)

# 20: Blue magic (Quistis) ----------------------------------------------------
sec(20, 2, NAMEDESC, [("Data", [
    ("attack_animation", 2, "attack_animation", "Attack animation"),
    ("unknown_0x06", 1, None, "Unknown 0x06"),
    ("attack_type", 1, "attack_type"),
    ("unknown_0x08", 2, None, "Unknown 0x08"),
    ("attack_flags", 1, "attack_flags"),
    ("hit_count", 1, None, "Hit count"),
    ("element", 1, "element"),
    ("status_attack", 1, None, "Status attack"),
    ("crit_bonus", 1, None, "Crit bonus"),
    ("unknown_0x0f", 1, None, "Unknown 0x0F"),
])], sub_size=16)

# 21: Blue magic params (4 crisis levels x 16) -------------------------------
sec(21, 0, [], [("Data", [
    ("status_2", 4, "status_2", "Status 2 (16-47)"),
    ("status_1", 2, "status_1", "Status 1 (0-15)"),
    ("attack_power", 1, None, "Attack power"),
    ("attack_param", 1, None, "Attack parameter"),
])], sub_size=8)

# 22: Shot (Irvine) ----------------------------------------------------------
sec(22, 2, NAMEDESC, [("Data", [
    ("magic_id", 2, "magic", "Magic ID"),
    ("attack_type", 1, "attack_type"),
    ("attack_power", 1, None, "Attack power"),
    ("unknown_0x08", 2, None, "Unknown 0x08"),
    ("target_info", 1, "target_info"),
    ("attack_flags", 1, "attack_flags"),
    ("hit_count", 1, None, "Hit count"),
    ("element", 1, "element", "Element attack"),
    ("element_percent", 1, None, "Element attack %"),
    ("status_attack_enabler", 1, None, "Status attack enabler"),
    ("status_1", 2, "status_1", "Status 1 (0-15)"),
    ("used_item_index", 1, "item", "Used item"),
    ("crit_increase", 1, None, "Crit increase"),
    ("status_2", 4, "status_2", "Status 2 (16-47)"),
])], sub_size=24)

# 23: Duel (Zell) ------------------------------------------------------------
sec(23, 2, NAMEDESC, [("Data", [
    ("magic_id", 2, "magic", "Magic ID"),
    ("attack_type", 1, "attack_type"),
    ("attack_power", 1, None, "Attack power"),
    ("attack_flags", 1, "attack_flags"),
    ("unknown_0x09", 1, None, "Unknown 0x09"),
    ("target_info", 1, "target_info"),
    ("unknown_0x0b", 1, None, "Unknown 0x0B"),
    ("hit_count", 1, None, "Hit count"),
    ("element", 1, "element", "Element attack"),
    ("element_percent", 1, None, "Element attack %"),
    ("status_attack_enabler", 1, None, "Status attack enabler"),
    ("button_1", 2, "duel_button", "Sequence button 1"),
    ("button_2", 2, "duel_button", "Sequence button 2"),
    ("button_3", 2, "duel_button", "Sequence button 3"),
    ("button_4", 2, "duel_button", "Sequence button 4"),
    ("button_5", 2, "duel_button", "Sequence button 5"),
    ("status_1", 2, "status_1", "Status 1 (0-15)"),
    ("status_2", 4, "status_2", "Status 2 (16-47)"),
])], sub_size=32)

# 24: Duel params (25 moves x [start, next1, next2, next3]) -------------------
duel_items = []
for g in range(25):
    duel_items.append((f"start_move_{g}", 1, None, f"Start move {g}"))
    duel_items.append((f"next_seq_{g}_1", 1, None, f"Next seq {g}.1"))
    duel_items.append((f"next_seq_{g}_2", 1, None, f"Next seq {g}.2"))
    duel_items.append((f"next_seq_{g}_3", 1, None, f"Next seq {g}.3"))
sec(24, 0, [], [("Duel move table", duel_items)], sub_size=100, entry_names=["Duel move table"])

# 25: Rinoa limit breaks part 1 ----------------------------------------------
sec(25, 2, NAMEDESC, [("Data", [
    ("unknown_flags", 1, None, "Unknown flags"),
    ("target", 1, "target_info", "Target"),
    ("ability_data_id", 1, None, "Ability data ID"),
    ("unknown_0x07", 1, None, "Unknown / Unused"),
])], sub_size=8)

# 26: Rinoa limit breaks part 2 (name only) ----------------------------------
sec(26, 1, ["Name"], [("Data", [
    ("magic_id", 2, "magic", "Magic ID"),
    ("attack_type", 1, "attack_type"),
    ("attack_power", 1, None, "Attack power"),
    ("attack_flags", 1, "attack_flags"),
    ("unknown_0x07", 1, None, "Unknown 0x07"),
    ("target_info", 1, "target_info"),
    ("unknown_0x09", 1, None, "Unknown 0x09"),
    ("hit_count", 1, None, "Hit count"),
    ("element", 1, "element", "Element attack"),
    ("element_percent", 1, None, "Element attack %"),
    ("status_attack_enabler", 1, None, "Status attack enabler"),
    ("status_1", 2, "status_1", "Status 1 (0-15)"),
    ("status_2", 4, "status_2", "Status 2 (16-47)"),
])], sub_size=20)

# 27: Slot array -------------------------------------------------------------
sec(27, 0, [], [("Data", [("slot_set_id", 1, None, "Slot set ID")])], sub_size=1)

# 28: Selphie limit break sets (8 magic/count pairs) -------------------------
slot_set_items = []
for i in range(1, 9):
    slot_set_items.append((f"magic_{i}", 1, "magic", f"Magic {i}"))
    slot_set_items.append((f"magic_{i}_count", 1, None, f"Magic {i} count"))
sec(28, 0, [], [("Data", slot_set_items)], sub_size=16)

# 29: Devour (description only) ----------------------------------------------
sec(29, 1, ["Description"], [("Data", [
    ("heal_dmg", 1, "heal_dmg", "Damage or heal"),
    ("hp_quantity", 1, "devour_hp_quantity", "HP heal/dmg quantity"),
    ("status_2", 4, "status_2", "Status 2 (16-47)"),
    ("status_1", 2, "status_1", "Status 1 (0-15)"),
    ("raised_stat", 1, "devour_raised_stat", "Raised stat"),
    ("raised_stat_hp", 1, None, "Raised stat HP quantity"),
])], sub_size=12)

# 30: Misc (single 60-byte block) --------------------------------------------
TIMERS = ["Sleep", "Haste", "Slow", "Stop", "Regen", "Protect", "Shell", "Reflect",
          "Aura", "Curse", "Doom", "Invincible", "Petrifying", "Float"]
LIMIT_EFFECTS = ["Death", "Poison", "Petrify", "Darkness", "Silence", "Berserk", "Zombie",
                 "Unknown status", "Sleep", "Haste", "Slow", "Stop", "Regen", "Protect",
                 "Shell", "Reflect", "Aura", "Curse", "Doom", "Invincible", "Petrifying",
                 "Float", "Confusion", "Drain", "Eject", "Double", "Triple", "Defend",
                 "Unknown status 2", "Unknown status 3", "Charged", "Back Attack"]
misc_timers = [(f"timer_{t.lower()}", 1, None, f"{t} timer") for t in TIMERS]
misc_timers += [("atb_speed_multiplier", 1, None, "ATB speed multiplier"),
                ("dead_timer", 1, None, "Dead timer")]
misc_limits = [(f"limit_{n.lower().replace(' ', '_')}_{i}", 1, None, f"{n} limit effect")
               for i, n in enumerate(LIMIT_EFFECTS)]
misc_duel = []
for cl in range(1, 5):
    misc_duel.append((f"duel_start_seq_cl{cl}", 1, None, f"Duel start seq CL{cl}"))
    misc_duel.append((f"duel_timer_cl{cl}", 1, None, f"Duel timer CL{cl}"))
misc_shot = [(f"shot_timer_cl{cl}", 1, None, f"Shot timer CL{cl}") for cl in range(1, 5)]
sec(30, 0, [], [
    ("Status timers", misc_timers),
    ("Status limit effects", misc_limits),
    ("Duel timers", misc_duel),
    ("Shot timers", misc_shot),
], sub_size=60, entry_names=["Misc"])

# 31: Misc text pointers (128 text entries) ----------------------------------
sec(31, 1, ["Text"], [], sub_size=2)


# ---- entry_names pulled from existing json ---------------------------------
kd = json.load(open(KERNEL, encoding="utf-8"))
JSON_DIR = os.path.dirname(KERNEL)
# command ability data (section 11) names
try:
    gforce = json.load(open(os.path.join(JSON_DIR, "gforce.json"), encoding="utf-8"))
    sections["11"]["entry_names"] = [c["Ability"] for c in gforce["command_abilities_data"]]
except Exception as e:
    print("warn:", e)
# enemy attacks (section 4): the 384 entries are the enemy abilities; use their
# canonical names as a fallback for entries whose kernel text name is blank.
try:
    enemy_abilities = json.load(open(os.path.join(JSON_DIR, "enemy_abilities.json"), encoding="utf-8"))
    sections["4"]["entry_names"] = [a["name"] for a in enemy_abilities["abilities"]]
except Exception as e:
    print("warn:", e)

# ---- help text (hover) applied by field name across all sections ----------
HELP = {
    "attack_animation": "Battle effect / animation dispatched at runtime (attack-animation id).",
    "magic_id": "Battle effect / animation dispatched at runtime (attack-animation id).",
    "attack_type": "How the damage / effect is calculated (see Attack Type list).",
    "spell_power": "Base power fed into the damage formula.",
    "attack_power": "Base power fed into the damage formula.",
    "gf_power": "GF base power fed into the damage formula.",
    "power_mod": "Power modifier used in the damage formula.",
    "level_mod": "Level modifier used in the damage formula.",
    "hit_count": "Number of hits (interacts with certain animations).",
    "draw_resist": "How hard the spell is to draw (higher = harder).",
    "element": "Elemental type(s) of the attack. Bitfield: combine flags.",
    "target_info": "Default targeting behavior. Bitfield: combine flags.",
    "attack_flags": "Attack behavior flags. Bitfield: combine flags.",
    "status_attack_enabler": "Accuracy for inflicting the statuses below (0 = never lands).",
    "status_accuracy": "Accuracy for inflicting the statuses below (0 = never lands).",
    "status_attack": "Accuracy for inflicting the statuses below (0 = never lands).",
    "status_1": "Statuses 0-15 inflicted / affected. Bitfield: tick each status.",
    "status_2": "Statuses 16-47 inflicted / affected. Bitfield: tick each status.",
    "ap": "Ability Points required to learn this ability.",
    "crit_bonus": "Bonus to the critical-hit rate.",
    "crit_increase": "Bonus to the critical-hit rate.",
    "element_percent": "Percentage of the attack that is elemental (0-100).",
    "character_id": "Which playable character wields this weapon.",
    "renzokuken_finishers": "Which Renzokuken finishers this weapon can trigger. Bitfield.",
    "str_bonus": "Flat STR bonus granted by the weapon.",
    "weapon_tier": "Weapon tier (affects some formulas / upgrade order).",
    "crisis_level_hp_mult": "Multiplier turning missing HP into the limit / crisis gauge.",
    "limit_break_id": "Which limit-break routine this character uses.",
    "limit_break_param": "Per-hit power used before the Renzokuken finisher.",
    "gender": "Character gender (used by some status targeting).",
    "battle_command_index": "Battle command granted when this ability is learned.",
    "stat_to_increase": "Which stat this GF/junction ability raises.",
    "used_item_index": "Ammo item consumed by this Shot attack.",
}

# ---- IDA field-xref findings for previously-unknown bytes -------------------
# (section_id, field_name) -> (new_label or None, help)
FINDINGS = {
    (2, "unknown_0x09"): ("Unused menu copy",
                          "Copied into the field character data during menu magic setup "
                          "(setMenuFlagMagicOnCharaData), but that slot is never read back "
                          "(IDA: 0 readers) - effectively vestigial."),
    (2, "unknown_0x0f"): ("Unused (padding)", "No code references this byte (IDA: 0 xrefs)."),
    (2, "unknown_0x3a"): ("Unused (padding)", "No code references these 2 bytes (IDA: 0 xrefs)."),
    (5, "unknown_0x03"): ("Unused (padding)", "No code references this byte (IDA: 0 xrefs)."),
    (4, "unknown_0x09"): ("Hit count / name flag",
                          "Bits 0-6 = hit count; bit 7 = show attack name (if clear, the "
                          "attack-name text is suppressed). Read in computeCommandAction."),
    (3, "unknown_0x08"): (None,
                          "Copied per junctioned GF into the battle character data "
                          "(ResetAndParseBattleAndFieldCharacter); consumer not yet identified."),
    (8, "unknown_0x0a"): ("Linked to selectability",
                          "IDA linkedToSelectability - used by updateBattleItemData and "
                          "Battle_applyDamage to gate item selectability."),
}

# Verified via IDA get_xrefs_to_field (round 2). Padding = 0 xrefs (renamed to
# "padding*" in the FF8Kernel* structs); used = has xrefs but purpose still TBD.
_PADDING = [(6, "unknown_0x07"), (6, "unknown_0x10"), (10, "unknown_0x11"),
            (11, "unknown_0x02"), (13, "unknown_0x06"), (14, "unknown_0x07"),
            (16, "unused_0x06"), (19, "unknown_0x12"), (20, "unknown_0x0f"),
            (23, "unknown_0x09"), (25, "unknown_0x07"), (26, "unknown_0x07"),
            (1, "unknown_0x07")]
_USED = {
    (6, "unknown_0x09"): "Battle_applyDamage", (8, "unknown_0x0c"): "getTextBattleItem",
    (8, "unknown_0x15"): "sub_483CA0", (19, "unknown_0x08"): "linkedToLimitBreak / Battle_applyDamage",
    (20, "unknown_0x06"): "Battle_applyDamage", (22, "unknown_0x08"): "Battle_applyDamage",
    (23, "unknown_0x0b"): "Battle_applyDamage", (26, "unknown_0x09"): "Battle_applyDamage",
    (1, "unknown_flags"): "ResetAndParseBattleAndFieldCharacter (character setup)",
    (25, "unknown_flags"): "sub_48CFB0",
}
for _k in _PADDING:
    FINDINGS[_k] = ("Padding", "Unused padding - no code references this byte (IDA: 0 xrefs).")
for _k, _fn in _USED.items():
    FINDINGS[_k] = (None, f"Unknown but used - read by `{_fn}` (purpose not yet identified).")

# Resolved in IDA (round 3): concrete meanings from decompiling the accessing code.
_ANIM = ("Target hit animation",
         "Target hit/reaction animation ID (HIT_TYPE_TARGET_ANIMATION_TO_PLAY) played on the "
         "target when the ability lands - the per-command-type equivalent of the GF "
         "'target hit animation' field. (Battle_applyDamage)")
_FLAGS = ("Attack flags (swapped)",
          "Attack flags - low 2 bits become the last-attacker flag (ATTACK_FLAG). In this "
          "command type the flags/animation byte order is swapped vs other attacks. (Battle_applyDamage)")
_MEANING = {
    (2, "animation"): _ANIM, (6, "unknown_0x09"): _ANIM, (22, "unknown_0x08"): _ANIM,
    (20, "unknown_0x06"): _ANIM, (19, "unknown_0x08"): _ANIM, (10, "target_hit_animation"): _ANIM,
    (23, "unknown_0x0b"): _FLAGS, (26, "unknown_0x09"): _FLAGS,
    (8, "unknown_0x15"): ("Random-select flag",
                          "Bit 0 marks the item eligible for random battle-item selection "
                          "(sub_483CA0 picks a random inventory item with this bit set)."),
    (8, "unknown_0x0c"): (None, "Appears only in getTextBattleItem array indexing - not a semantic field read."),
}
FINDINGS.update(_MEANING)

# Fields that IDA proved unused/padding are marked read-only in the editor.
_READONLY = set(_PADDING) | {
    (2, "unknown_0x0f"), (2, "unknown_0x3a"), (5, "unknown_0x03"), (2, "unknown_0x09"),
}

for sid_s, cfg in sections.items():
    sid = int(sid_s)
    for f in cfg["fields"]:
        if f["name"] in HELP and "help" not in f:
            f["help"] = HELP[f["name"]]
        key = (sid, f["name"])
        if key in FINDINGS:
            new_label, help_text = FINDINGS[key]
            if new_label:
                f["label"] = new_label
            f["help"] = help_text
        if key in _READONLY:
            f["readonly"] = True

# Zell "Duel" limit-break help (decompiled: linkedToZellDuel / sub_4852B0 / K_DUEL_PARAM).
for _f in sections["30"]["fields"]:
    _n = _f["name"]
    if _n.startswith("duel_start_seq_cl"):
        _cl = _n[-1]
        _f["help"] = (f"Zell 'Duel' limit break - starting index into the Duel move table "
                      f"(section 24 'Duel Params') at crisis level {_cl}. `linkedToZellDuel` reads "
                      f"this to seed the move sequence; the per-tick driver `sub_4852B0` then plays "
                      f"`duelMoves[seq].StartMove` and the player's button input branches via that "
                      f"entry's Next Sequence bytes. Higher crisis level -> different opening chain.")
    elif _n.startswith("duel_timer_cl"):
        _cl = _n[-1]
        _f["help"] = (f"Zell 'Duel' limit break - duration of the Duel input window at crisis "
                      f"level {_cl} (higher crisis = longer). Paired with 'Duel start seq CL{_cl}'.")
for _f in sections["24"]["fields"]:
    if _f["name"].startswith("start_move_"):
        _f["help"] = ("Zell Duel move table: the Duel move performed when this sequence is the "
                      "current one (values >= 6 end the Duel with a finisher). Section 24 = the "
                      "move graph; the Misc 'Duel start seq' bytes pick the entry point per crisis level.")
    elif _f["name"].startswith("next_seq_"):
        _f["help"] = ("Zell Duel move table: which sequence index to jump to for the next move, "
                      "selected by the player's button input from this move.")

# IDA-driven normalization: every kernel "Magic ID" effect field is typed
# SpecialActionID (value 2 = Fire, 102 = Thundara) and indexes the special_action
# table, NOT the spell-name list (where 2 = Fira). Point them at special_action.
for cfg in sections.values():
    for f in cfg["fields"]:
        if f.get("lookup") == "magic":
            f["lookup"] = "attack_animation"
            if f.get("label", "").startswith("Magic ID"):
                f["label"] = "Attack animation"

with open(DEST, "w", encoding="utf-8") as f:
    json.dump(sections, f, indent=1, ensure_ascii=False)

print("wrote", DEST)
print("sections:", sorted(sections.keys(), key=int))
for k in sorted(sections, key=int):
    print(f"  section {k}: {len(sections[k]['fields'])} fields, text={sections[k].get('text_labels')}")
