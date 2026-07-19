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
    return [("status_1", 2, "status_1", "Status 1"),
            ("status_2", 4, "status_2", "Status 2")]


# 1: Battle commands ---------------------------------------------------------
# Menu flags (0x05) is a bitfield: bits 7-5 are 3 independent flags, bits 4-0 are
# the submenu id - both share the same byte, so they're two field defs at the
# same offset distinguished by "mask" (KernelEntry does read-modify-write so
# neither field clobbers the other on save).
sections["1"] = {"section_id": 1, "text_labels": NAMEDESC, "fields": [
    {"name": "ability_data_id", "offset": 4, "size": 1, "group": "Data",
     "lookup": "command_ability_ref", "label": "Ability data ID"},
    {"name": "menu_bits", "offset": 5, "size": 1, "group": "Data", "mask": 0xE0,
     "lookup": "command_menu_bits", "label": "Menu flags"},
    {"name": "menu_submenu", "offset": 5, "size": 1, "group": "Data", "mask": 0x1F,
     "lookup": "command_menu_submenu", "label": "Submenu",
     "enabled_unless_bit": {"field": "menu_bits", "mask": 0x20}},
    {"name": "target_info", "offset": 6, "size": 1, "group": "Data", "lookup": "target_info"},
    {"name": "unknown_0x07", "offset": 7, "size": 1, "group": "Data", "label": "Unknown 0x07"},
]}

# 2: Magic (built earlier - keep identical) ----------------------------------
JSTATS = ["hp", "str", "vit", "mag", "spr", "spd", "eva", "hit", "luck"]
sec(2, 2, NAMEDESC, [
    ("General", [
        ("magic_id", 2, "magic", "Magic ID (effect/anim)"),
        ("animation", 1, None, "Animation category"),
        ("attack_type", 1, "attack_type"),
        ("spell_power", 1, None, "Spell power"),
        ("status_window_flags", 1, "status_window_flags", "Status window"),
        ("target_info", 1, "target_info"),
        ("attack_flags", 1, "attack_flags"),
        ("draw_resist", 1, None, "Draw resist"),
        ("hit_count", 1, None, "Hit count"),
        ("element", 1, "element"),
        ("unknown_0x0f", 1, None, "Unknown 0x0F"),
        ("status_2", 4, "status_2", "Status 2"),
        ("status_1", 2, "status_1", "Status 1"),
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
# Magic is the one section KernelManager treats as variable-length (kernel_bin_data.json
# "growable": true) - the "Add Magic" button in the tab appends new entries. Flag it here
# so KernelSectionTab knows to show that button.
sections["2"]["growable"] = True
# Ids 64-79 are hard-reserved for GFs by the exe's own classification logic (every magic-
# id consumer does `cmp id, 0x40` and routes id>=64 to GF handling) - real magic data can
# never live there, so the tab hides them from the entry list entirely rather than just
# labelling them (matches kernel_bin_data.json's gf_reserved_start/gf_reserved_count).
sections["2"]["hidden_id_start"] = 64
sections["2"]["hidden_id_count"] = 32   # reserve ids 64-95 for GFs (16 used + 16 future); extended magic starts at 96

# 3: Junctionable GFs (reuse proven offsets from junctionable_gf_data) --------
gf_general = [
    ("attack_animation", 2, "attack_animation", "Attack animation"),
    ("attack_type", 1, "attack_type"),
    ("gf_power", 1, None, "GF power"),
    ("status_window_flags", 1, "status_window_flags", "Status window"),
    ("target_info", 1, "target_info"),
    ("attack_flags", 1, "attack_flags"),
    ("target_animation", 1, None, "Target hit animation"),
    ("hit_count", 1, None, "Hit count"),
    ("element", 1, "element"),
    ("status_1", 2, "status_1", "Status 1"),
    ("status_2", 4, "status_2", "Status 2"),
    ("gf_hp_modifier_1", 1, None, "GF HP modifier 1"),
    ("gf_hp_modifier_2", 1, None, "GF HP modifier 2"),
    ("gf_hp_modifier_3", 1, None, "GF HP modifier 3"),
    ("gf_level_modifier_1", 1, None, "GF level modifier 1"),
    ("gf_level_modifier_2", 1, None, "GF level modifier 2"),
    ("status_attack_enabler", 1, None, "Status attack accuracy"),
    ("power_mod", 1, None, "Power mod"),
    ("level_mod", 1, None, "Level mod"),
]
# explicit offsets for the general block (non-contiguous: modifiers/tail)
gf_offsets = {
    "attack_animation": 0x04, "attack_type": 0x06, "gf_power": 0x07, "status_window_flags": 0x08,
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
    row = f"ability{i}"
    # BuildGFAbilityList (0x4ACB70) is the decisive reader: it walks these 21 slots
    # to build the Junction menu's "learnable abilities" list. Byte+3 is used
    # directly as the ability id (indexed into a 128-slot seen-flags buffer sized
    # for the ability list) - that is the REAL ability, not byte+2 (which is always
    # 0xFF in retail and reads as raw garbage in a plain "ability" picker).
    gf_fields.append({"name": f"ability{i}", "offset": base + 3, "size": 1,
                      "lookup": "junctionable_ability", "label": f"Ability {i}",
                      "group": "Abilities", "row": row})
    gf_fields.append({"name": f"ability{i}_unlocker", "offset": base, "size": 1,
                      "label": "Unlocker", "group": "Abilities", "row": row})
    gf_fields.append({"name": f"ability{i}_level_or_prereq", "offset": base + 1, "size": 1,
                      "label": "Level/prereq", "group": "Abilities", "row": row,
                      "help": "What this ability needs to unlock (read by BuildGFAbilityList, "
                              "the Junction-menu ability list builder):\n"
                              "1-100 = the GF must be at least this level.\n"
                              "101-121 = instead of a level, ability slot (value-101) on this "
                              "same GF must already be fully learned first - i.e. \"finish "
                              "that ability before this one becomes available\" (a same-GF "
                              "unlock chain, e.g. SumMag+20% requires SumMag+10% first)."})
    gf_fields.append({"name": f"ability{i}_alt_prereq", "offset": base + 2, "size": 1,
                      "label": "Alt prereq slot", "group": "Abilities", "row": row,
                      "help": "Points at another ability slot (0-20) on this same GF and makes "
                              "the two mutually exclusive until one is done: this ability keeps "
                              "being offered only while the OTHER slot's ability is still "
                              "unfinished, and gets cut off the moment that other ability is "
                              "completed. 0xFF = no such restriction (the normal case).\n"
                              "Always 0xFF in the retail kernel - a working feature the engine "
                              "supports (BuildGFAbilityList) but the shipped data never turns "
                              "on. (This is the byte that used to display as raw 0xFF for "
                              "every ability before the fields were remapped - it was never "
                              "the ability id.)"})
# GF Boost parameters @0x80-0x81 (IDA gfBoostParams: each byte x15 -> Boost min/max,
# pre_computeGFBoost)
gf_fields.append({"name": "boost_param_1", "offset": 0x80, "size": 1, "group": "General",
                  "label": "Boost phase 1 length (x15)",
                  "help": "Initial length (x15 = ticks) of the FIRST 'safe' Boost phase\n"
                          "where pressing Square raises Boost.\n"
                          "NOT a min/max value - the Boost figure itself runs 75..250\n"
                          "(100 if untouched).\n"
                          "Later phases are re-rolled to 15*(1..3 + 1..3).\n"
                          "(pre_computeGFBoost / computeGFBoost)"})
gf_fields.append({"name": "boost_param_2", "offset": 0x81, "size": 1, "group": "General",
                  "label": "Boost total window (x15)",
                  "help": "Initial length (x15 = ticks) of the overall Boost input window\n"
                          "(word_209CEF4), counted down while you mash.\n"
                          "NOT a min/max value.\n"
                          "(pre_computeGFBoost / computeGFBoost)"})
# IDA FF8KernelJunctionableGF: padding at 0x6F, compatibility block starts at 0x70
# (the old junctionable_gf_data json was off by one, leaving 0x7F unmapped).
for i, c in enumerate(COMPAT):
    gf_fields.append({"name": f"compat_{c}", "offset": 0x70 + i, "size": 1,
                      "label": COMPAT_LABELS[i], "group": "GF Compatibility",
                      "help": (f"When THIS GF is summoned in battle, how much the casting "
                               f"character's compatibility with {COMPAT_LABELS[i]} changes.\n"
                               f"100 = no change; >100 raises it, <100 lowers it "
                               f"(delta = value - 100).\n"
                               f"The stored total is clamped to 1000-6000; higher compatibility "
                               f"fills that GF's summon (Boost) gauge faster, so it appears sooner.\n"
                               f"Player characters only. (BattleAction_ExecuteCommand)")})
sections["3"] = {"section_id": 3, "text_labels": NAMEDESC, "fields": gf_fields}

# 4: Enemy attacks -----------------------------------------------------------
sec(4, 1, ["Name"], [("Data", [
    ("magic_id", 2, "magic", "Magic ID"),
    ("camera_change", 1, None, "Camera"),
    ("animation", 1, None, "Animation triggered"),
    ("attack_type", 1, "attack_type"),
    ("attack_power", 1, None, "Attack power"),
    ("attack_flags", 1, "attack_flags"),
    ("unknown_0x09", 1, None, "Unknown 0x09"),
    ("element", 1, "element"),
    ("crit_bonus", 1, None, "Attack crit bonus"),
    ("status_attack_enabler", 1, None, "Status attack accuracy"),
    ("hit_rate", 1, None, "Hit rate"),
    ("status_1", 2, "status_1", "Status 1"),
    ("status_2", 4, "status_2", "Status 2"),
])], sub_size=20)

# 5: Weapons -----------------------------------------------------------------
sec(5, 1, ["Name"], [("Data", [
    ("renzokuken_finishers", 1, "renzokuken_finisher", "Renzokuken finishers"),
    ("unknown_0x03", 1, None, "Unknown 0x03"),
    ("character_id", 1, "weapon_character", "Character"),
    ("attack_type", 1, "attack_type"),
    ("attack_power", 1, None, "Attack power"),
    ("hit_rate", 1, None, "Hit rate"),
    ("str_bonus", 1, None, "STR bonus"),
    ("weapon_tier", 1, None, "Weapon tier"),
    ("crit_bonus", 1, None, "Crit bonus"),
    ("melee", 1, None, "Melee weapon"),
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
    ("status_attack_enabler", 1, None, "Status attack accuracy"),
    ("unknown_0x10", 2, None, "Unknown 0x10"),
    ("status_1", 2, "status_1", "Status 1"),
    ("status_2", 4, "status_2", "Status 2"),
])], sub_size=24)

# 7: Characters --------------------------------------------------------------
char_stats = []
for st in ["hp", "str", "vit", "mag", "spr", "spd", "luck"]:
    for k in range(1, 5):
        char_stats.append((f"{st}_{k}", 1, None, f"c{k}"))
sec(7, 1, ["Name"], [
    ("General", [
        ("crisis_level_hp_mult", 1, None, "Crisis level HP multiplier"),
        ("gender", 1, "gender"),
        ("limit_break_id", 1, None, "Limit break ID"),
        ("limit_break_param", 1, None, "Limit break param"),
        ("exp_linear", 1, None, "c1"),
        ("exp_quadratic", 1, None, "c2"),
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
    ("battle_flag", 1, "battle_item_category", "Category (unused)"),
    ("target_info", 1, "target_info"),
    ("attack_flags", 1, "attack_flags"),
    ("target_animation", 1, None, "Target hit animation"),
    ("padding_0x0c", 1, None, "Padding"),
    ("status_attack_enabler", 1, None, "Status attack accuracy"),
    ("status_1", 2, "status_1", "Status 1"),
    ("status_2", 4, "status_2", "Status 2"),
    ("hit_rate", 1, None, "Hit rate"),
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
    ("status_attack_enabler", 1, None, "Status attack accuracy"),
    ("target_info", 1, "target_info"),
    ("attack_flags", 1, "attack_flags"),
    ("target_hit_animation", 1, None, "Target hit animation"),
    ("hit_count", 1, None, "Hit count"),
    ("element", 1, "element"),
    ("status_group_1", 1, "nonjgf_status_1", "Status (Sleep..Reflect)"),
    ("status_group_2", 1, "nonjgf_status_2", "Status (Aura..Drain)"),
    ("status_group_3", 1, "nonjgf_status_3", "Status (Eject..Back attack)"),
    ("status_group_4", 1, "nonjgf_status_4", "Status (Vit0..Summon GF)"),
    ("status_group_5", 1, "nonjgf_status_5", "Status (Death..Zombie)"),
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
    ("status_attack_enabler", 1, None, "Status attack accuracy"),
    ("status_1", 2, "status_1", "Status 1"),
    ("status_2", 4, "status_2", "Status 2"),
])], sub_size=16)

# 12: Junction abilities -----------------------------------------------------
sec(12, 2, NAMEDESC, [("Data", [
    ("ap", 1, None, "AP to learn"),
    ("junction_flag", 3, "junction_ability_flags", "Junction ability flag"),
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
    ("chara_stat_to_increase", 1, "chara_stat_index", "Stat to increase"),
    ("increase_value", 1, None, "Increase value"),
    ("unknown_0x07", 1, None, "Unknown / Unused"),
])], sub_size=8)

# 15: Character abilities -----------------------------------------------------
sec(15, 2, NAMEDESC, [("Data", [
    ("ap", 1, None, "AP to learn"),
    ("chara_flag", 3, "character_ability_flags", "Character ability flag"),
])], sub_size=8)

# 16: Party abilities ---------------------------------------------------------
sec(16, 2, NAMEDESC, [("Data", [
    ("ap", 1, None, "AP to learn"),
    ("party_flag", 1, "party_ability_flags", "Party ability flag"),
    ("unused_0x06", 2, None, "Unused"),
])], sub_size=8)

# 17: GF abilities ------------------------------------------------------------
sec(17, 2, NAMEDESC, [("Data", [
    ("ap", 1, None, "AP to learn"),
    ("enable_boost", 1, None, "Enable boost"),
    ("stat_to_increase", 1, "gf_ability_stat", "Stat to increase"),
    ("increase_value", 1, None, "Increase value"),
])], sub_size=8)

# 18: Menu abilities ----------------------------------------------------------
sec(18, 2, NAMEDESC, [("Data", [
    ("ap", 1, None, "AP to learn"),
    ("menu_index", 1, "refine_table", "Refine table"),
    ("start_offset", 1, None, "Start offset"),
    ("end_offset", 1, None, "End offset"),
])], sub_size=8)

# 19: Temporary character limit breaks ---------------------------------------
sec(19, 2, NAMEDESC, [("Data", [
    ("magic_id", 2, "magic", "Magic ID"),
    ("attack_type", 1, "attack_type"),
    ("attack_power", 1, None, "Attack power"),
    ("target_animation", 1, None, "Target hit animation"),
    ("status_window_flags", 1, "status_window_flags", "Status window"),
    ("target_info", 1, "target_info"),
    ("attack_flags", 1, "attack_flags"),
    ("hit_count", 1, None, "Hit count"),
    ("element", 1, "element", "Element attack"),
    ("element_percent", 1, None, "Element attack %"),
    ("status_attack_enabler", 1, None, "Status attack accuracy"),
    ("status_1", 2, "status_1", "Status 1"),
    ("unknown_0x12", 2, None, "Unknown 0x12"),
    ("status_2", 4, "status_2", "Status 2"),
])], sub_size=24)

# 20: Blue magic (Quistis) ----------------------------------------------------
sec(20, 2, NAMEDESC, [("Data", [
    ("attack_animation", 2, "attack_animation", "Attack animation"),
    ("unknown_0x06", 1, None, "Unknown 0x06"),
    ("attack_type", 1, "attack_type"),
    ("status_window_flags", 1, "status_window_flags", "Status window"),
    ("target_info", 1, "target_info"),
    ("attack_flags", 1, "attack_flags"),
    ("hit_count", 1, None, "Hit count"),
    ("element", 1, "element"),
    ("status_attack", 1, None, "Status attack accuracy"),
    ("crit_bonus", 1, None, "Crit bonus"),
    ("unknown_0x0f", 1, None, "Unknown 0x0F"),
])], sub_size=16)

# 21: Blue magic params (16 moves x 4 crisis levels) -------------------------
BLUE_MAGIC_MOVES = ["Laser Eye", "Ultra Waves", "Electrocute", "LV?Death", "Degenerator",
                    "Aqua Breath", "Micro Missiles", "Acid", "Gatling Gun", "Fire Breath",
                    "Bad Breath", "White Wind", "Homing Laser", "Mighty Guard", "Ray-Bomb",
                    "Shockwave Pulsar"]
BLUE_MAGIC_ENTRY_NAMES = [f"{m} CL{cl}" for m in BLUE_MAGIC_MOVES for cl in range(1, 5)]
sec(21, 0, [], [("Data", [
    ("status_2", 4, "status_2", "Status 2"),
    ("status_1", 2, "status_1", "Status 1"),
    ("attack_power", 1, None, "Attack power"),
    ("hit_rate", 1, None, "Hit rate"),
])], sub_size=8, entry_names=BLUE_MAGIC_ENTRY_NAMES)

# 22: Shot (Irvine) ----------------------------------------------------------
sec(22, 2, NAMEDESC, [("Data", [
    ("magic_id", 2, "magic", "Magic ID"),
    ("attack_type", 1, "attack_type"),
    ("attack_power", 1, None, "Attack power"),
    ("target_animation", 1, None, "Target hit animation"),
    ("status_window_flags", 1, "status_window_flags", "Status window"),
    ("target_info", 1, "target_info"),
    ("attack_flags", 1, "attack_flags"),
    ("hit_count", 1, None, "Hit count"),
    ("element", 1, "element", "Element attack"),
    ("element_percent", 1, None, "Element attack %"),
    ("status_attack_enabler", 1, None, "Status attack accuracy"),
    ("status_1", 2, "status_1", "Status 1"),
    ("used_item_index", 1, "item", "Used item"),
    ("crit_increase", 1, None, "Crit increase"),
    ("status_2", 4, "status_2", "Status 2"),
])], sub_size=24)

# 23: Duel (Zell) ------------------------------------------------------------
sec(23, 2, NAMEDESC, [("Data", [
    ("magic_id", 2, "magic", "Magic ID"),
    ("attack_type", 1, "attack_type"),
    ("attack_power", 1, None, "Attack power"),
    ("target_animation", 1, None, "Target hit animation"),
    ("unknown_0x09", 1, None, "Unknown 0x09"),
    ("target_info", 1, "target_info"),
    ("attack_flags", 1, "attack_flags"),
    ("hit_count", 1, None, "Hit count"),
    ("element", 1, "element", "Element attack"),
    ("element_percent", 1, None, "Element attack %"),
    ("status_attack_enabler", 1, None, "Status attack accuracy"),
    ("button_1", 2, "duel_button", "Sequence button 1"),
    ("button_2", 2, "duel_button", "Sequence button 2"),
    ("button_3", 2, "duel_button", "Sequence button 3"),
    ("button_4", 2, "duel_button", "Sequence button 4"),
    ("button_5", 2, "duel_button", "Sequence button 5"),
    ("status_1", 2, "status_1", "Status 1"),
    ("status_2", 4, "status_2", "Status 2"),
])], sub_size=32)

# 24: Duel params (25 sequence entries x [start, next1, next2, next3]) --------
# Built with explicit "row" so each sequence entry is one line of 4 spinboxes.
duel_fields = []
for g in range(25):
    base = g * 4
    row = f"duel_seq_{g}"
    duel_fields.append({"name": f"start_move_{g}", "offset": base, "size": 1,
                        "label": f"Seq {g}: start", "group": "Duel move graph", "row": row})
    for j in (1, 2, 3):
        duel_fields.append({"name": f"next_seq_{g}_{j}", "offset": base + j, "size": 1,
                            "label": f"→ next {j}", "group": "Duel move graph", "row": row})
sections["24"] = {"section_id": 24, "fields": duel_fields, "entry_names": ["Duel move graph"]}

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
    ("target_animation", 1, None, "Target hit animation"),
    ("unknown_0x07", 1, None, "Unknown 0x07"),
    ("target_info", 1, "target_info"),
    ("attack_flags", 1, "attack_flags"),
    ("hit_count", 1, None, "Hit count"),
    ("element", 1, "element", "Element attack"),
    ("element_percent", 1, None, "Element attack %"),
    ("status_attack_enabler", 1, None, "Status attack accuracy"),
    ("status_1", 2, "status_1", "Status 1"),
    ("status_2", 4, "status_2", "Status 2"),
])], sub_size=20)

# 27: Slot array -------------------------------------------------------------
# One 60-byte table (was 60 x 1-byte subsections). Each byte is the slot-set id
# used for that roll position; presented as a 10-wide grid instead of 60 pages.
slot_fields = []
for i in range(60):
    f = {"name": f"slot_{i}", "offset": i, "size": 1,
         "label": str(i), "group": "Slot roll table (set id per position)",
         "row": f"slot_row_{i // 10}",
         "lookup": "slot_set_summary", "dynamic_lookup": True,
         "help": "Slot-set id (0-15) - index into the Selphie limit-break sets (section 28) "
                 "selected for this roll position. The dropdown is built live from whatever "
                 "kernel.bin is currently loaded, listing each set's actual 8 spells (a static "
                 "list can't work here - a different file could have different spells in each "
                 "set). Use the button above to jump to Slot Sets and edit a set's contents."}
    if i == 0:
        f["jump_to_section"] = (28, "Slot Sets")
    slot_fields.append(f)
sections["27"] = {"section_id": 27, "fields": slot_fields}

# 28: Selphie limit break sets (8 magic/count pairs) -------------------------
# Exception to the usual spins-then-combos layout: each magic's Id/Count belong
# together, so they share a "row" and render as one line (magic combo + count spin).
slot_set_items = []
for i in range(1, 9):
    slot_set_items.append((f"magic_{i}", 1, "magic", f"Magic {i}"))
    slot_set_items.append((f"magic_{i}_count", 1, None, f"Magic {i} count"))
sec(28, 0, [], [("Data", slot_set_items)], sub_size=16)
for f in sections["28"]["fields"]:
    if f["name"].startswith("magic_"):
        idx = f["name"].split("_")[1]
        f["row"] = f"slot_{idx}"
    # Real cross-reference to the Magic section's own (possibly modded, possibly grown)
    # entries - not the static vanilla list - so a newly-added spell shows up here too.
    if f.get("lookup") == "magic":
        f["dynamic_lookup"] = True

# 29: Devour (description only) ----------------------------------------------
sec(29, 1, ["Description"], [("Data", [
    ("heal_dmg", 1, "heal_dmg", "Damage or heal"),
    ("hp_quantity", 1, None, "HP heal/dmg quantity (sixteenths of max HP)"),
    ("status_2", 4, "status_2", "Status 2"),
    ("status_1", 2, "status_1", "Status 1"),
    ("raised_stat", 1, "devour_raised_stat", "Raised stat"),
    ("raised_stat_hp", 1, None, "Raised stat HP quantity"),
])], sub_size=12)

# 30: Misc (single 60-byte block) --------------------------------------------
TIMERS = ["Sleep", "Haste", "Slow", "Stop", "Regen", "Protect", "Shell", "Reflect",
          "Aura", "Curse", "Doom", "Invincible", "Petrifying", "Float"]
LIMIT_EFFECTS = ["Death", "Poison", "Petrify", "Darkness", "Silence", "Berserk", "Zombie",
                 "Unused (Status-1 bit 7)", "Sleep", "Haste", "Slow", "Stop", "Regen", "Protect",
                 "Shell", "Reflect", "Aura", "Curse", "Doom", "Invincible", "Petrifying",
                 "Float", "Confusion", "Drain", "Eject", "Double", "Triple", "Defend",
                 "Immune Physical attack", "Immune Magic attack", "Charged", "Back Attack"]
misc_timers = [(f"timer_{t.lower()}", 1, None, f"{t} timer") for t in TIMERS]
misc_timers += [("atb_speed_multiplier", 1, None, "ATB speed multiplier"),
                ("dead_timer", 1, None, "Gilgamesh/Angelo\nsummon interval")]
_LIMIT_EFFECT_HELP = (
    "How much having this status active contributes to a character's crisis/Limit-Break "
    "gauge, read by Battle_ComputeCrisisLevelAndLimitFlag. Every one of a character's "
    "active statuses (from both Status 1 and Status 2) adds its byte here into one running "
    "total each frame:\n"
    "crisis = (10*(statusSum + 4*(5*deadAllies + 40)) - 10*crisisLevelHPMultiplier*curHP/"
    "maxHP) / (rand(0..255)+160) - 4, clamped 0-4.\n"
    "Higher values push the crisis level (and so Limit Break availability) up faster; 0 "
    "means that status doesn't affect it at all. Death/Poison/etc. push it up because "
    "you're worse off; there's no term that lowers it.")
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
# command ability data (section 11) names + GF names for the G-Forces list
try:
    gforce = json.load(open(os.path.join(JSON_DIR, "gforce.json"), encoding="utf-8"))
    sections["11"]["entry_names"] = [c["Ability"] for c in gforce["command_abilities_data"]]
    # Section 3's text is the GF *attack* name; show the GF name in the list instead.
    sections["3"]["entry_names"] = [g["name"] for g in gforce["gforce"]]
    sections["3"]["entry_name_primary"] = True
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
    "camera_change": "Which battle-stage camera animation plays while the monster performs this "
                     "attack. Read only for monster attacks (computeCommandAction, COMMAND_MONSTER"
                     "_ATTACK) and consumed by cameraWhenDoingAction @0x506190:\n"
                     "- low 7 bits (value & 0x7F) = the camera-animation INDEX picked from the "
                     "battle stage's camera-animation collection (BS_GetCameraAnimationPointer).\n"
                     "- bit 0x80 = force this camera even in the state that would otherwise skip it "
                     "(sub_4A7120). ~70% of retail attacks set it.\n"
                     "0xFF = default / no specific camera. Retail values are index 1-7 (e.g. 1-4, or "
                     "0x81-0x87 with the force bit). For player commands this byte is unused - their "
                     "camera is chosen randomly.",
    "attack_type": "How the damage / effect is calculated (see Attack Type list).",
    "spell_power": "Base power fed into the damage formula.",
    "attack_power": "Base power fed into the damage formula.",
    "gf_power": "GF base power (the `Power` term of the GF damage formula, appearing 3× in it). "
                "Click f(x) for the full GF damage.",
    "power_mod": "Flat power modifier added inside the GF damage formula "
                 "(levelMod×GFLvl/10 + Power + powerMod). Click f(x) on Level mod for the full "
                 "formula.",
    "level_mod": "Scales the GF-level term of the GF damage formula "
                 "(levelMod×GFLvl/10 + Power + powerMod). Click f(x) for the full GF damage.",
    "gf_hp_modifier_1": "Linear (per-level) term of the GF HP curve: "
                        "HP = HPMod3 + level×HPMod1 + 10×level²/HPMod2 (getGFhpForLvl). Click f(x).",
    "gf_hp_modifier_2": "Quadratic divisor of the GF HP curve (10×level²/HPMod2) - larger = flatter "
                        "growth; must be non-zero. Click f(x) on GF HP modifier 3 for the curve.",
    "gf_hp_modifier_3": "Flat base of the GF HP curve. Click f(x) for the whole level→HP curve.",
    "gf_level_modifier_1": "Linear term of the GF EXP curve: total EXP for level L = "
                           "10×mod1×L + mod2×L²/256 (GetGFLevelFromExperience). Click f(x) on "
                           "GF level modifier 2.",
    "gf_level_modifier_2": "Quadratic (÷256) acceleration of the GF EXP curve. Click f(x) for the "
                           "level→EXP curve.",
    "hit_count": "Number of hits (interacts with certain animations).",
    "draw_resist": "How hard the spell is to draw (higher = harder).",
    "element": "Elemental type(s) of the attack. Bitfield: combine flags.",
    "target_info": "Default targeting behavior. Bitfield: combine flags.",
    "status_attack_enabler": "Accuracy for inflicting/curing the statuses below - what it actually "
                             "does depends on this entry's Attack Type: an STR/VIT or MAG/SPR "
                             "inflict roll for physical/magic attacks, a flat % cure chance for "
                             "Curative Item family, unconditional (byte unused) for Curative "
                             "Magic/Revive, an action-success gate for LV Up/Down, or unused "
                             "entirely for Fixed Damage types. Click f(x) for the exact mechanic.",
    "status_accuracy": "Accuracy for inflicting/curing the statuses below - what it actually "
                       "does depends on this entry's Attack Type: an STR/VIT or MAG/SPR "
                       "inflict roll for physical/magic attacks, a flat % cure chance for "
                       "Curative Item family, unconditional (byte unused) for Curative "
                       "Magic/Revive, an action-success gate for LV Up/Down, or unused "
                       "entirely for Fixed Damage types. Click f(x) for the exact mechanic.",
    "status_attack": "Accuracy for inflicting/curing the statuses below - what it actually "
                     "does depends on this entry's Attack Type: an STR/VIT or MAG/SPR "
                     "inflict roll for physical/magic attacks, a flat % cure chance for "
                     "Curative Item family, unconditional (byte unused) for Curative "
                     "Magic/Revive, an action-success gate for LV Up/Down, or unused "
                     "entirely for Fixed Damage types. Click f(x) for the exact mechanic.",
    "status_1": "Statuses 0-15 inflicted / affected. Bitfield: tick each status.",
    "status_2": "Statuses 16-47 inflicted / affected. Bitfield: tick each status.",
    "ap": "Ability Points required to learn this ability.",
    "crit_bonus": "Bonus to the critical-hit rate. Damage_RollCrit: crit if rand(0-255) <= this "
                  "+ attacker LUCK; a crit doubles physical damage. Click f(x) for detail.",
    "crit_increase": "Bonus to the critical-hit rate. Damage_RollCrit: crit if rand(0-255) <= "
                     "this + attacker LUCK; a crit doubles physical damage. Click f(x) for detail.",
    "element_percent": "Elemental percentage of the attack. 100 = fully elemental, but the "
                       "byte can exceed 100 (e.g. 200 = double elemental weight); full range 0-255.",
    "character_id": "Which playable character wields this weapon.",
    "renzokuken_finishers": "Which Renzokuken finishers this weapon can trigger. Bitfield.",
    "str_bonus": "Flat STR bonus granted by the weapon.",
    "weapon_tier": "Weapon tier (affects some formulas / upgrade order).",
    "melee": "Melee-weapon flag: bit 0 set marks the character a melee attacker "
             "(sets BATTLE_FLAG_MELEE_CHARA in initializeBattleSlotData).",
    "hit_rate": "Physical hit rate — accuracy rolled against the target's Evade to decide "
                "hit vs. miss. 0xFF (255) = always hits. Battle_applyDamage loads it into "
                "HIT_ATTACK_HITPERCENT, the same slot a character's Hit% stat fills; separate "
                "from status attack accuracy (which governs status infliction).",
    "attack_param": "Secondary value read by Battle_applyDamage; its exact role depends on "
                    "the attack type.",
    "crisis_level_hp_mult": "Multiplier turning missing HP into the limit / crisis gauge.",
    "limit_break_id": "Which limit-break routine this character uses.",
    "limit_break_param": "Per-hit power used before the Renzokuken finisher.",
    "gender": "Character gender (used by some status targeting).",
    "battle_command_index": "Battle command granted when this ability is learned.",
    "stat_to_increase": "Which GF stat this ability raises (SumMag/GFHP - the GF-specific counterpart "
                        "of a character stat).",
    "used_item_index": "Ammo item consumed by this Shot attack.",
}

# ---- IDA field-xref findings for previously-unknown bytes -------------------
# (section_id, field_name) -> (new_label or None, help)
_STATUS_WIN = (None,
    "Status-window flags for battle target selection (same bits as the top of a battle "
    "command's Menu flags). 'Hide ally status panel' CLEAR = while the target cursor is up, "
    "the party HP/status panel opens (heal spells use 0x00); 'shows ailments' switches that "
    "panel to list status ailments instead of HP (Esuna/Dispel/support use 0x40). Offensive "
    "entries use 0x80 (panel hidden).\n"
    "(Confirm path: list entry -> target cursor +36 -> sub_4B1E70 -> "
    "BattleHUD_StatusWinOpenRequest/DetailMode.)")
FINDINGS = {
    (2, "unknown_0x0f"): ("Unused (padding)", "No code references this byte (IDA: 0 xrefs)."),
    (2, "unknown_0x3a"): ("Unused (padding)", "No code references these 2 bytes (IDA: 0 xrefs)."),
    (5, "unknown_0x03"): ("Unused (padding)", "No code references this byte (IDA: 0 xrefs)."),
    (4, "unknown_0x09"): ("Hit count / name flag",
                          "Bits 0-6 = hit count; bit 7 = show attack name (if clear, the "
                          "attack-name text is suppressed). Read in computeCommandAction."),
    (2, "status_window_flags"): _STATUS_WIN,
    (3, "status_window_flags"): _STATUS_WIN,
    (19, "status_window_flags"): _STATUS_WIN,
    (20, "status_window_flags"): _STATUS_WIN,
    (22, "status_window_flags"): _STATUS_WIN,
    (8, "attack_flags"): (None,
        "Dual-purpose byte (IDA attackFlagsAndSelectability). In battle it is the item's "
        "ATTACK FLAGS: Battle_applyDamage loads it into ATTACK_FLAG (low 2 bits = damage-type "
        "pair - retail curatives use 2 = Item/Medicine so MedData doubles their healing, "
        "offensive stones use 1 = Magical so Shell halves them; 0x80 also gates the revive "
        "path for Phoenix Down-likes).\n"
        "In the MENU the same byte feeds updateBattleItemData: bit 0x80 set = item selectable/"
        "usable in battle, bit 0x20 clear = marks the entry dimmed (all retail items have 0x20 "
        "set)."),
    (8, "padding_0x0c"): ("Padding",
        "Unused - 0x00 for all 33 items; its only xref is pointer arithmetic in "
        "getTextBattleItem's non-battle-item branch, not a semantic read."),
    (8, "battle_flag"): (None,
        "NOT a bitfield - the retail values (0x00/0x40/0x80) never combine, they're 3 mutually "
        "exclusive category codes that line up cleanly with item type: 0x00 = pure curatives "
        "(Potion..Megalixir), 0x40 = status-cure/support items (Antidote, Remedy, Hero, Holy "
        "War, Shell/Protect/Aura Stone), 0x80 = offensive/special items (the 6 elemental stones, "
        "Gysahl Greens, Phoenix Pinion, Friendship).\n"
        "It IS copied into the runtime battle-item inventory by updateBattleItemData - but "
        "nothing then reads that copy, and nothing reads this kernel byte directly either "
        "(exhaustive xref sweep: item-use AI keys on item id, the item-menu draw path only uses "
        "the selectability byte, and the item-effect dispatcher (computeCommandAction) resolves "
        "everything from attackType/specialActionID). The category grouping is real, deliberate "
        "design data - it's just inert in the shipped PC engine."),
}

# Verified via IDA get_xrefs_to_field (round 2). Padding = 0 xrefs (renamed to
# "padding*" in the FF8Kernel* structs); used = has xrefs but purpose still TBD.
_PADDING = [(6, "unknown_0x07"), (6, "unknown_0x10"), (10, "unknown_0x11"),
            (11, "unknown_0x02"), (13, "unknown_0x06"), (14, "unknown_0x07"),
            (16, "unused_0x06"), (19, "unknown_0x12"), (20, "unknown_0x0f"),
            (23, "unknown_0x09"), (25, "unknown_0x07"),
            (26, "unknown_0x07"), (1, "unknown_0x07")]
_USED = {
    (6, "unknown_0x09"): "Battle_applyDamage",
    (8, "unknown_0x15"): "sub_483CA0",
    (20, "unknown_0x06"): "Battle_applyDamage",
    (25, "unknown_flags"): "sub_48CFB0",
}
for _k in _PADDING:
    FINDINGS[_k] = ("Padding", "Unused padding - no code references this byte (IDA: 0 xrefs).")
for _k, _fn in _USED.items():
    FINDINGS[_k] = (None, f"Unknown but used - read by `{_fn}` (purpose not yet identified).")

# Round 30: these 5 padding bytes hold the SAME constant across every entry of their
# section (not 0, not random garbage) - suspicious enough, after the attack_flags 0x20
# precedent, to re-check beyond the original 0-xref pass. A deeper sweep cross-referenced
# every sibling field's reader function per struct (11 functions total, incl.
# BuildLimitCommandMenu's shifted-pointer/HIBYTE path that caught the earlier attack_flags
# miss) - every other field of each struct has a confirmed reader; these offsets alone
# have none. Confirmed genuinely unused; the constant values are most likely a leftover
# stamp from the original kernel-authoring tool, not engine-consumed data.
_PADDING_RECHECKED = {
    (6, "unknown_0x07"): "Renzokuken finishers: retail value 100 (0x64) in all 4 entries.",
    (19, "unknown_0x12"): "Temp-character limits: retail value 200 (0xC8, as a WORD) in all 5 entries.",
    (20, "unknown_0x0f"): "Blue Magic: retail value 200 (0xC8) in only 1/16 entries (Laser Eye) - "
                          "likely stray authoring noise rather than even a constant stamp.",
    (23, "unknown_0x09"): "Duel (Zell): retail value 128 (0x80) in all 10 entries.",
    (26, "unknown_0x07"): "Rinoa limit breaks part 2: retail value 128 (0x80) in all 5 entries.",
}
for _k, _note in _PADDING_RECHECKED.items():
    FINDINGS[_k] = ("Padding", "Unused padding - re-checked beyond the original 0-xref pass "
                    "(every sibling field of this struct has a confirmed reader; this offset has "
                    "none in any of them, including the menu-building code). " + _note)

# Resolved in IDA (round 3): concrete meanings from decompiling the accessing code.
_ANIM = ("Target hit animation",
         "Index of the reaction/impact animation the TARGET plays when the ability lands "
         "(HIT_TYPE_TARGET_ANIMATION_TO_PLAY) - a flinch, knock-back, blown-away pose, etc. "
         "A plain animation index, not a bitfield.\n"
         "(What used to look like a 2-byte value in Shot/T.Char limits was really this byte "
         "plus the separate Status window byte next to it.)\n"
         "Runtime can override the stored value: e.g. a crit forces 6, a miss forces 0/9, a "
         "monster death forces 3 (Battle_applyDamage / computeTargetData).")
_FLAGS = ("Attack flags (swapped)",
          "Attack flags - low 2 bits become the last-attacker flag (ATTACK_FLAG). In this "
          "command type the flags/animation byte order is swapped vs other attacks. (Battle_applyDamage)")
_MEANING = {
    (2, "animation"): _ANIM, (6, "unknown_0x09"): _ANIM, (22, "target_animation"): _ANIM,
    (20, "unknown_0x06"): _ANIM, (19, "target_animation"): _ANIM, (10, "target_hit_animation"): _ANIM,
    (23, "target_animation"): _ANIM, (26, "target_animation"): _ANIM,
    (8, "target_animation"): _ANIM,
    (8, "unknown_0x15"): ("Random-select flag",
                          "Bit 0 marks the item eligible for random battle-item selection "
                          "(sub_483CA0 picks a random inventory item with this bit set)."),
    (5, "hit_rate"): (None,
        "The character's base Hit% stat while this weapon is equipped. GetCharacterHit reads it "
        "directly: HIT% = weapon.hitRate + (junctioned HIT magic bonus), capped at 255 - there is "
        "no character-level term, so this byte alone sets a character's baseline accuracy."),
    (1, "ability_data_id"): (None,
        "Index into kernel section 11 (Command ability data in battle) giving this command's "
        "fixed built-in effect - magic/effect id, attack type, power, hit count, element, status "
        "and animation all come from that section-11 entry (computeCommandAction).\n"
        "0xFF (255) = no fixed effect: the command's action is chosen at runtime from the player's "
        "selection. Attack, Magic, Draw, GF and Item all use 0xFF (they resolve to the spell/GF/item "
        "you pick). Fixed-effect commands (Card, Devour, Defend, Mad Rush, Treatment, Recover, Revive, "
        "Doom, Absorb, LV Up/Down) carry a real index. Also checked at setup: if the linked entry's "
        "attack flags have the Revive bit, the command is flagged as a revive."),
    (17, "enable_boost"): (None,
        "Whether learning this ability enables the GF Boost minigame. In the retail kernel only "
        "the 'Boost' entry itself sets this (the 8 stat-percentage abilities - SumMag/GFHP+10-"
        "40% - all leave it clear); Stat to increase is the 0xFF sentinel on that same entry, "
        "since Boost isn't a stat-increase ability."),
    (12, "junction_flag"): (None,
        "A genuine 24-bit bitfield - each of the 20 junction abilities is assigned its own "
        "dedicated bit (retail data: every entry sets exactly one bit, matching its position in "
        "the list - HP-J is bit 0, Abilityx4 is bit 19).\n"
        "ResetAndParseBattleAndFieldCharacter ORs this value into the character's "
        "FF8CharaAbilities bitmask for every junction ability the character has equipped, so "
        "these bits are what other systems actually test at runtime (e.g. the Double/Triple-cast "
        "check in BattleAction_ExecuteCommand reads the Abilityx3/Abilityx4 bits directly).\n"
        "Because it's a real bitfield you can combine bits on a custom ability to grant several "
        "effects from one learned ability."),
    (14, "chara_stat_to_increase"): (None,
        "NOT a bitfield, despite sharing a kernel array slot with the (real bitfield) Junction "
        "ability flag - this is a plain index picking ONE of the 9 standard stats (retail: one "
        "ability per stat, values never combine). sub_4962C0 tests it with a straight equality "
        "compare (not bitwise) against the stat being computed, one comparison per owned Stat% "
        "ability; matching abilities' Increase Value bytes just sum onto a 100 base (e.g. owning "
        "both HP+20% and HP+40% gives a combined 100+20+40=160% multiplier). Applied in "
        "Stat_RefreshCharaBattleStats: stat = multiplier * baseStat / 100."),
    (15, "chara_flag"): (None,
        "A genuine 24-bit bitfield, same JFlag mechanism as Junction ability flag - each ability "
        "is assigned its own dedicated bit (retail data: every entry sets exactly one bit). "
        "ResetAndParseBattleAndFieldCharacter ORs it into the character's FF8CharaAbilities "
        "bitmask for every character ability equipped; other systems test individual bits at "
        "runtime (e.g. the Expendx2-1/Expendx3-1 bits gate not consuming a spell charge on "
        "Double/Triple)."),
    (16, "party_flag"): (None,
        "A genuine 8-bit bitfield, same JFlag mechanism as Junction/Character ability flags "
        "(only the low byte is used here). ResetAndParseBattleAndFieldCharacter ORs it into "
        "PASSIF_ABILITIES_ACTIVE for every party ability any active character has equipped."),
    (18, "menu_index"): (None,
        "Which Refine data table this ability's item list is drawn from. The Refine screen "
        "handler (Menu_Prog19_RefineMenu_Init) switches on this byte to load a pair of mngrp "
        "resource files holding that table's item/magic records: 0=Magic Refine, 1=Tool/Medicine "
        "Refine, 2=Mid/High Magic Refine, 3=LV Up Refine. 4 (Card Mod) is special-cased - instead "
        "of loading a fixed file it dynamically lists every card type the player owns. "
        "255/128/129 (Haggle, Sell-High, Familiar, Call Shop, Junk Shop) aren't Refine abilities "
        "at all and ignore Start/End offset."),
    (18, "start_offset"): (None,
        "Start of this ability's INCLUSIVE slice of its Refine table's records - "
        "Menu_Prog19_RefineMenu_Init computes `count = End offset - Start offset + 1` and offsets "
        "the table pointer by `8 * Start offset` (each record is 8 bytes). Abilities sharing the "
        "same Refine table use non-overlapping slices, e.g. T Mag-RF (table 0, 0-6) and I Mag-RF "
        "(table 0, 7-13) split the same loaded item list by element."),
    (18, "end_offset"): (None,
        "End of this ability's INCLUSIVE slice of its Refine table's records - see Start offset. "
        "Must be >= Start offset."),
    (1, "menu_bits"): (None,
        "Battle-menu descriptor bits - purely UI, never read by battle logic. Shares its byte "
        "with Submenu (the low 5 bits); each is saved independently, the other's bits are "
        "preserved.\n"
        "'Hide ally status panel' clear (only Recover/Revive/Treatment) makes targeting an ally "
        "open the party HP/status panel; 'Status panel shows ailments' switches that panel to "
        "list ailments instead of HP (Treatment); 'Instant' skips the Submenu entirely and goes "
        "straight to target selection.\n"
        "(BattleMenu_ExecuteSelectedCommand; copied per-slot by "
        "ResetAndParseBattleAndFieldCharacter)"),
    (1, "menu_submenu"): (None,
        "Which submenu opens on this command - only takes effect when Menu flags' 'Instant' bit "
        "is CLEAR (greyed out here otherwise, since the game never reads it in that case).\n"
        "Shares its byte with Menu flags (the top 3 bits); each is saved independently, the "
        "other's bits are preserved.\n"
        "(BattleMenu_ExecuteSelectedCommand)"),
    (25, "ability_data_id"): (None,
        "Rinoa 'Combine' (Angelo) entry field. NOT the same as the battle-command Ability data ID: "
        "it does NOT index section 11 - no code reads this byte (only UnknownFlags and Target of "
        "this section are consumed, by sub_48CFB0), so any linkage is positional/unused. Left as a "
        "raw value rather than a section-11 picker."),
}
FINDINGS.update(_MEANING)

# Fields that IDA proved unused/padding are marked read-only in the editor.
# (Magic 0x09 was here as "vestigial menu copy" - wrong: it is the status-window
# flag byte, read through the battle-menu list-confirm template path.)
_READONLY = set(_PADDING) | {
    (2, "unknown_0x0f"), (2, "unknown_0x3a"), (5, "unknown_0x03"), (8, "padding_0x0c"),
    (30, "limit_unused_(status-1_bit_7)_7"),  # Status 1 bit 7 has no real status - dead slot
}

# Fields confirmed to only ever be 0/1 across every entry of a genuinely multi-entry
# section (not a single-entry table where "one value observed" is meaningless), with
# an established single-bit/truthy semantic - not just a magnitude/id/count byte that
# happens to be 0 or 1 in this particular kernel.bin. Rendered as a plain checkbox.
_BOOL_FIELDS = {
    (5, "melee"),          # Weapon melee flag (33 weapons, real 0/1 split)
    (8, "unknown_0x15"),   # Battle item random-select flag (33 items, real 0/1 split)
    (17, "enable_boost"),  # GF ability "enables Boost" (9 abilities: 1 only on "Boost" itself)
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
        if key in _BOOL_FIELDS:
            f["bool"] = True
        # Only bits 7-6 of the status-window byte are live; mask them so saving the
        # flags widget never clobbers the (always-zero, dead) low 6 bits.
        if f["name"] == "status_window_flags":
            f["mask"] = 0xC0
        if sid == 30 and f["name"].startswith("limit_"):
            f["help"] = _LIMIT_EFFECT_HELP
        # Duel: the 5 sequence-button pickers belong together, not scattered among the
        # rest of the Data fields.
        if sid == 23 and f["name"].startswith("button_"):
            f["subgroup"] = "Sequence buttons"
        # Characters: each stat's 4 curve coefficients belong together on one line, in
        # their own labelled sub-box, with an f(x) button (on the last coef) that shows
        # the level-to-stat curve those 4 numbers define.
        # The former 2-byte "EXP modifier" is really two independent parameters (verified in
        # Stat_ComputeLevelFromExp @0x4961d0): c1 (low byte) drives a linear EXP/level term, c2
        # (high byte) a quadratic acceleration term. Presented like the stat curves - their own
        # "EXP" sub-box with c1/c2 on one row and the f(x) curve preview on c2.
        if sid == 7 and f["name"] in ("exp_linear", "exp_quadratic"):
            f["row"] = "exp_curve"
            f["subgroup"] = "EXP"
        if sid == 7 and f["name"] == "exp_quadratic":
            f["formula"] = "char_exp"  # one f(x) button for the EXP curve, on the last byte
        if sid == 7 and f["name"] == "exp_linear":
            f["help"] = ("Low byte of the EXP curve: the linear EXP-per-level factor (×10). "
                         "Cumulative EXP to reach level L = 10×(L−1)×this + the quadratic term. "
                         "Retail 100 → a flat 1000 EXP/level. (Stat_ComputeLevelFromExp @0x4961d0.)")
        if sid == 7 and f["name"] == "exp_quadratic":
            f["help"] = ("High byte of the EXP curve: a quadratic acceleration factor (÷256), "
                         "adding floor((L−1)²×this/256) to the cumulative EXP for level L. Retail 0 "
                         "= a flat (non-accelerating) curve. Click ƒ(x) for the full level→EXP curve.")
        if sid == 7:
            _st = f["name"].rsplit("_", 1)[0]
            if _st in ("hp", "str", "vit", "mag", "spr", "spd", "luck"):
                f["subgroup"] = _st.upper()
                f["row"] = f"charstat_{_st}"
                # One f(x) button per stat, on the last USED coefficient. HP uses only
                # c1..c3 (c4 confirmed unused - Stat_ComputeCharaMaxHP @0x496310 reads
                # struct offsets 0x08/0x09/0x0A only, never 0x0B; triple-checked incl. the
                # DWORD/HIBYTE trap, and c4 is 0 for all 11 retail chars), so HP's button
                # sits on c3 and c4 stays greyed; the other stats' button sits on c4.
                if _st == "hp" and f["name"] == "hp_4":
                    f["readonly"] = True
                    f["label"] = "c4 (unused)"
                elif f["name"] == ("hp_3" if _st == "hp" else f"{_st}_4"):
                    f["formula"] = f"char_{_st}"
        # Menu abilities: the Refine reference load button sits at the top of the main Data
        # group (it loads menu.fs data shared by EVERY menu ability, so it's tab-wide, not
        # per-entry); the table selector + slice offsets + the per-entry decoded panel go in
        # a nested "Refine" sub-box.
        if sid == 18 and f["name"] == "ap":
            f["menu_refine_button"] = True
        if sid == 18 and f["name"] in ("menu_index", "start_offset", "end_offset"):
            f["subgroup"] = "Refine"
        # Start/End offset (and the Refine button/panel, owned by start_offset) only apply
        # to the Refine tables 0-4; grey them out for shop/plain-menu abilities (128/129/255).
        if sid == 18 and f["name"] in ("start_offset", "end_offset"):
            f["enabled_when"] = {"field": "menu_index", "values": [0, 1, 2, 3, 4]}
        if sid == 18 and f["name"] == "start_offset":
            f["menu_refine_reference"] = True
        if sid == 18 and f["name"] == "menu_index":
            f["help"] = (
                "Which Refine data table this ability draws its item list from - this value "
                "picks the table, the Start/End offset (below) pick the slice of rows within it "
                "(each row is one 'N source -> M output' recipe).\n"
                "0 = Magic Refine, 1 = Tool/Medicine Refine, 2 = Mid/High Magic Refine, "
                "3 = LV Up Refine, 4 = Card Mod (card -> item; the menu only lists cards you "
                "own, but the recipe table is still sliced by Start/End). 128/129 = Call/Junk "
                "Shop and 255 = plain menu abilities (Haggle/Sell-High/Familiar) are not Refine "
                "abilities and ignore Start/End offset.\n"
                "The recipes themselves live in menu.fs, not kernel.bin - use the button below "
                "to view them.")
        # The 14 status timers (Misc 0x00-0x0D) are loaded as a battle countdown of
        # 4 * (battleSpeed + 1) * value ticks (setupStatus2Timer). At the PC battle tick
        # rate (~15/s) and the default battle speed, seconds ~= value * 16/15. The editor
        # shows a live "~ N s" hint below the spinbox using this factor.
        if sid == 30 and f["name"].startswith("timer_") and f["name"] != "timer_atb":
            f["seconds_factor"] = 12.0 / 30.0  # 4×(battleSpeed+1)/30 at battleSpeed 2 (config midpoint)
            f["seconds_note"] = ("Loaded as 4×(battleSpeed+1)×value ticks (setupStatus2Timer), then "
                                 "consumed 2 ticks per idle battle frame (computeTimerStatus) at ~15 fps. "
                                 "battleSpeed is the config 0 (fast) … 4 (slow); ~ shown at the midpoint "
                                 "(2), so it scales ×0.4 (fast 0) … ×1.0 (slow 4) of the value in seconds. "
                                 "Haste ticks 1.5× faster, Slow 2× slower, Stop freezes it. Click ƒ(x).")
            f["formula"] = "status_timer"
        # ATB speed multiplier: a genuine, IDA-verified formula input (Battle_TickAtbGaugesAndGf
        # Countdown @0x4842b0), NOT a percent - retail value is 10.
        if sid == 30 and f["name"] == "atb_speed_multiplier":
            f["formula"] = "atb_speed"
            f["help"] = ("Multiplies how fast ALL battlers' ATB gauges fill: "
                         "cur_atb += 10 x this x (SPD+30) / 100, applied 3x per rendered frame "
                         "(Battle_TickAtbGaugesAndGfCountdown). Retail value is 10, not a %-of-normal "
                         "multiplier despite the name - click f(x) for the full picture.")
        # "Dead timer" is really the interval between the random Gilgamesh/Angelo/Phoenix
        # auto-summon checks. summonGilgaAngelStartFight (called once per battle tick from
        # FFBattleDirector_battleLoop) decrements it; at 0 it rolls to summon Gilgamesh
        # (12/255) or trigger an Angelo/Phoenix auto-action, then reloads this value.
        if sid == 30 and f["name"] == "dead_timer":
            f["seconds_factor"] = 1.0 / 15.0
            f["formula"] = "dead_timer"
            f["seconds_note"] = ("Decremented once per battle tick (~15 ticks/s), so ~ value/15 s "
                                 "between summon-checks.")
            f["help"] = ("Interval between the random Gilgamesh / Angelo / Phoenix auto-summon "
                         "checks during battle (NOT a character-death countdown). "
                         "summonGilgaAngelStartFight decrements it once per battle tick; when it "
                         "reaches 0 the game rolls to summon Gilgamesh (12/255 chance, if you own "
                         "him and he hasn't come this fight) or fire an Angelo/Phoenix auto-action, "
                         "then reloads this value. Loaded into DEAD_TIMER_TO_SUMMON_GILGA. Lower = "
                         "checks happen more often.")
        # Devour's HP heal/dmg quantity is sixteenths of max HP, confirmed linear across
        # every retail entry (0->0%, 1->6.25%, 2->12.5%, 8->50%, 12->75%, 16->100%). Not
        # an enum - earlier tool builds wrongly snapped it to power-of-2 percentages only,
        # which showed later, perfectly-valid values (e.g. 12 = 75%) as unresolved "raw".
        if sid == 29 and f["name"] == "hp_quantity":
            f["percent_factor"] = 100.0 / 16.0
            f["formula"] = "devour_hp"
            f["percent_note"] = "Value is in sixteenths of max HP (value/16 * 100%); linear, not an enum."
        # GF compatibility feeds the summon-gauge fill; spell power feeds the magic damage
        # formula; the crisis/limit-effect bytes feed the crisis-level formula. Each gets an
        # f(x) preview button.
        # Weapons (section 5): attack power + STR bonus BOTH feed the physical damage formula,
        # so they share one "Physical damage" sub-box on a single row with ONE f(x) button
        # (on attack_power). Crit bonus feeds the crit-chance roll; hit rate feeds accuracy.
        if sid == 5 and f["name"] in ("attack_power", "str_bonus"):
            f["subgroup"] = "Physical damage"
            f["row"] = "phys_dmg"
        if sid == 5 and f["name"] == "attack_power":
            f["formula"] = "physical_damage"
        if sid == 5 and f["name"] == "crit_bonus":
            f["formula"] = "weapon_crit"
        if sid == 5 and f["name"] == "hit_rate":
            f["formula"] = "weapon_hit"
        # Crit chance: the SAME roll (Damage_RollCrit) also reads Enemy attacks' crit_bonus,
        # Blue Magic's crit_bonus and Shot's crit_increase - confirmed via their
        # RELATED_TO_CRIT_BONUS write sites in Battle_applyDamage.
        if (sid, f["name"]) in ((4, "crit_bonus"), (20, "crit_bonus"), (22, "crit_increase")):
            f["formula"] = "weapon_crit"
        # Status inflict chance: every "status attack accuracy" byte across the kernel feeds
        # Battle_ApplyStatusWithResistRoll: STR/VIT for physical-dispatch Attack Types, MAG/SPR
        # for the magic/GF-dispatch ones (picked live from this entry's own Attack Type field).
        if f["name"] in ("status_attack_enabler", "status_accuracy", "status_attack"):
            f["formula"] = "status_accuracy"
        if sid in (2, 3) and f["name"].startswith("compat_"):
            f["formula"] = "gf_compat"
        # Enemy attack Camera byte -> composite editor (default/none checkbox + force bit +
        # animation index). Verified: cameraWhenDoingAction @0x506190 uses value & 0x7F as the
        # battle-stage camera-animation index, bit 0x80 = force; 0xFF = default/none.
        if sid == 4 and f["name"] == "camera_change":
            f["camera_selector"] = True
        # G-Forces (section 3): three coupled groups, each rendered as a nested sub-box with one
        # shared f(x) button (like a character HP stat curve), plus a standalone GF power button.
        if sid == 3:
            # HP curve (getGFhpForLvl): the 3 HP modifiers on one row, one button on the last.
            if f["name"] in ("gf_hp_modifier_1", "gf_hp_modifier_2", "gf_hp_modifier_3"):
                f["subgroup"] = "GF HP curve"
                f["row"] = "gf_hp"
            if f["name"] == "gf_hp_modifier_3":
                f["formula"] = "gf_hp"
            # Next-level EXP curve (GetGFLevelFromExperience): the 2 level modifiers, one button.
            if f["name"] in ("gf_level_modifier_1", "gf_level_modifier_2"):
                f["subgroup"] = "Next-level EXP"
                f["row"] = "gf_next_exp"
            if f["name"] == "gf_level_modifier_2":
                f["formula"] = "gf_next_exp"
            # GF damage tail bytes (ComputeMagicAndGFDamage): Level mod + Power mod, one button.
            if f["name"] in ("power_mod", "level_mod"):
                f["subgroup"] = "GF damage mods"
                f["row"] = "gf_dmg_mods"
            if f["name"] == "level_mod":
                f["formula"] = "gf_damage"
            # GF power feeds the same GF-damage formula (it's in the General block, away from the
            # Level/Power mod pair, so it carries its own button).
            if f["name"] == "gf_power":
                f["formula"] = "gf_damage"
            # The "Status attack accuracy" byte at 0x1A (struct statusAttackAccuracy) is DEAD:
            # get_xrefs_to_field returns 0. The GF summon's real status-attack accuracy is at
            # 0x1B - abilityData[0].abilityUnlocker (Battle_applyDamage GF case @0x490043:
            # HIT_ATTACK_ACCURACY = abilityData[0].abilityUnlocker). So move the status formula
            # off 0x1A and onto ability1_unlocker, and mark 0x1A unused.
            if f["name"] == "status_attack_enabler":
                f.pop("formula", None)
                f["label"] = "Status attack acc. (unused)"
                f["readonly"] = True
                f["help"] = ("Struct byte 0x1A ('statusAttackAccuracy') - genuinely DEAD, read by "
                             "nothing. Deep-audited: 0 field xrefs, 0 direct-address xrefs, AND all "
                             "register-relative accesses checked (the case that hid the attack-flag "
                             "0x20 bug) - the 3 functions that hold a GF-entry pointer (incl. the GF/"
                             "junction menu and ability-learn code) touch only offset 0 or 0x1B, "
                             "never 0x1A; no aliases or bulk copies read it. The GF summon's real "
                             "status-attack accuracy lives at 0x1B ('Ability 1' row's first byte).")
            # The per-ability "unlocker" (byte+0 of each 4-byte slot) is NOT what unlocks the
            # ability - BuildGFAbilityList never reads it (the real condition is the next byte,
            # Level/prereq). It is 0 in every retail GF. The ONE exception is the first slot's
            # byte (ability1_unlocker, 0x1B), which the engine reuses as the GF summon's status
            # accuracy.
            if f["name"] == "ability1_unlocker":
                f["label"] = "GF summon status acc."
                f["formula"] = "status_accuracy"
                f["help"] = ("Despite sitting where 'Ability 1's unlocker byte' would be (0x1B), "
                             "this byte is the GF SUMMON's status-attack accuracy - "
                             "Battle_applyDamage's GF case reads it as HIT_ATTACK_ACCURACY "
                             "(the dedicated 0x1A 'Status attack accuracy' field is dead). "
                             "0 = the summon inflicts no status (e.g. Ifrit); it only matters "
                             "for GFs whose summon carries a Status 1/2. The ability-learning "
                             "code (BuildGFAbilityList) never reads this byte. Click f(x).")
            elif f["name"].endswith("_unlocker"):
                f["label"] = "Unused (byte+0)"
                f["readonly"] = True
                f["help"] = ("Byte+0 of this ability slot. The ability-learning code "
                             "(BuildGFAbilityList) never reads it - the REAL unlock condition is "
                             "the next byte, 'Level/prereq'. Always 0 in retail. (Only the FIRST "
                             "slot's byte+0 is used, and for something unrelated: the GF summon's "
                             "status-attack accuracy.)")
        # Magic damage reads spell power, attack type and hit count, but they're not a tightly-
        # coupled pair like Weapon's STR bonus (each is independently meaningful elsewhere -
        # attack_type also drives status accuracy's stat pair, hit_count is just hit count) - one
        # shared button on spell_power avoids 3 redundant buttons opening the identical popup.
        if sid == 2 and f["name"] == "spell_power":
            f["formula"] = "magic_damage"
        if sid == 30 and f["name"].startswith("limit_"):
            f["formula"] = "crisis"

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
                      f"level {_cl} (higher crisis = longer).\n"
                      f"Paired with 'Duel start seq CL{_cl}'.")
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

# The low 2 bits of every attack_flags byte are ONE 2-bit damage-type value (ATTACK_FLAG & 3:
# 0 Physical / 1 Magical / 2 Item-Medicine / 3 special), NOT two independent flags. Rendering
# them as separate "Magical" and "Item/Medicine" checkboxes wrongly implied both could be ticked
# (value 3 lit both, e.g. every Blue Magic reads 0x23 - looked like "Magical + Item/Medicine" but
# is really "special"). Split each attack_flags field into a masked damage-type dropdown + the
# masked remaining behaviour-flag checkboxes (KernelEntry's read-modify-write keeps them in sync).
_ATTACK_DT_HELP = ("The attack's damage TYPE (low 2 bits of the attack-flags byte, ATTACK_FLAG & 3) "
                   "- one value, not a set of flags:\n"
                   "Physical (0): the only type that can trigger the target's Counter, wake "
                   "Sleep/Confusion, or remove Back Attack.\n"
                   "Magical (1): the target's Shell status halves the damage/heal.\n"
                   "Item/Medicine (2): battle items; enables the Med Data ability's healing doubling "
                   "and (being non-Magical) dodges Shell.\n"
                   "Special (3): none of the above - forced by Renzokuken/Gunblade, and what every "
                   "Blue Magic uses. Not Physical, not Magical, not Item, so it gets no Counter, no "
                   "Shell halving and no Med Data.")
_ATTACK_BITS_HELP = ("Attack behaviour flags (upper 6 bits; the low 2 are the separate Damage type "
                     "field). Only 0x08 Break Damage Limit, 0x10 Reflectable and 0x80 Revive are "
                     "actually read by the engine. 0x04 and 0x40 have NO reader anywhere (0x40 is "
                     "set on curative magic/items in retail data but nothing consumes it). 0x20 is "
                     "set on virtually every player ability as an authoring convention, but is only "
                     "READ for battle items (see the Battle items tab) - here it is inert.")
_ATTACK_BITS_HELP_ITEM = ("Attack behaviour flags (upper 6 bits; the low 2 are the separate Damage "
                          "type field). 0x08 Break Damage Limit, 0x10 Reflectable and 0x80 Revive "
                          "behave as elsewhere. 0x04 and 0x40 have NO reader anywhere. 0x20 IS read "
                          "here - `updateBattleItemData` tests it directly to decide whether the "
                          "item is selectable in the battle Item menu (this is the ONE section where "
                          "this bit does anything; on magic/GF/limits it's inert).")
for cfg in sections.values():
    new_fields = []
    for f in cfg["fields"]:
        if f.get("lookup") == "attack_flags":
            dt = {"name": f["name"] + "_type", "offset": f["offset"], "size": f["size"],
                  "mask": 0x03, "lookup": "attack_damage_type", "label": "Damage type",
                  "help": _ATTACK_DT_HELP}
            # Battle items (section 8) are the ONE place 0x20 is actually read
            # (updateBattleItemData -> Item-menu selectability) - every other section's
            # copy of this byte is inert there, so the checkbox label must say so
            # per-section rather than sharing one generic (and, on Items, self-
            # contradictory) "inert" label.
            is_item = cfg["section_id"] == 8
            bits_lookup = "attack_flags_bits_item" if is_item else "attack_flags_bits"
            bits = {"name": f["name"], "offset": f["offset"], "size": f["size"],
                    "mask": 0xFC, "lookup": bits_lookup,
                    "label": f.get("label", "Attack flags"),
                    "help": _ATTACK_BITS_HELP_ITEM if is_item else _ATTACK_BITS_HELP}
            for key in ("group", "row", "subgroup"):
                if key in f:
                    dt[key] = f[key]
                    bits[key] = f[key]
            new_fields.append(dt)
            new_fields.append(bits)
        else:
            new_fields.append(f)
    cfg["fields"] = new_fields

with open(DEST, "w", encoding="utf-8") as f:
    json.dump(sections, f, indent=1, ensure_ascii=False)

print("wrote", DEST)
print("sections:", sorted(sections.keys(), key=int))
for k in sorted(sections, key=int):
    print(f"  section {k}: {len(sections[k]['fields'])} fields, text={sections[k].get('text_labels')}")
