"""Formula previews for kernel fields that feed a runtime formula.

A field tagged ``"formula": "<key>"`` gets a small "f(x)" button next to its editor
(see kernelsectiontab). Clicking it opens a popup that shows the formula, the same
formula with the current value + assumed parameters substituted, and the numeric
result - all live.

The *assumed parameters* (caster MAG, target SPR, battle speed, ...) are NOT stored in
kernel.bin; they're the runtime/battle inputs the player or enemy brings. They live in
the shared, user-editable ``PARAM_VALUES`` store so a value edited in one popup persists
and is reused by the next. Defaults follow doomtrain's damage-chart defaults where it has
them; the rest are sourced from IDA (noted per-parameter).
"""
from __future__ import annotations

# --- assumed parameters -----------------------------------------------------
# name -> (label, default, min, max, help). Defaults sourced as noted.
PARAM_DEFS = {
    "caster_mag":     ("Caster MAG", 0, 0, 255,
                       "The MAG stat of the magic/GF caster. Doomtrain damage-chart default 0."),
    "target_spr":     ("Target SPR", 0, 0, 255,
                       "The SPR (spirit) stat of the target - magic defence. Doomtrain default 0."),
    "elem_defense":   ("Target element damage %", 100, -1650, 900,
                       "How much damage of the spell's element the target takes, as the Ifrit Stat "
                       "tab shows it: 100 = normal, 200 = double (weak), 0 = none (immune), below "
                       "0 = absorbs (heals). Steps of 10.\n"
                       "The game keeps elemDef = 900 - this value (a monster's .dat byte x 10, "
                       "setMonsterInfoFromDatInfoSection @0x48bbd0) and multiplies magic/GF damage "
                       "by (900 - elemDef)/100, i.e. by this %.\n"
                       "Vanilla monsters: mostly 100; e.g. Snow Lion Fire 250 / Ice -100, Bomb Fire "
                       "-100 / Ice 300."),
    "target_hp":      ("Target current HP", 1000, 1, 99999999,
                       "Target's current HP - used by Demi / %-HP attacks. Doomtrain default 1000."),
    "target_maxhp":   ("Target max HP", 1000, 1, 99999999,
                       "Target's max HP - used by Devour and Angelo Recover (value/16 x maxHP)."),
    "battle_speed":   ("Battle speed", 2, 0, 4,
                       "FF8 config Battle Speed (SG_SETTING.battleSpeed), 0 (fast) … 4 (slow) — five "
                       "settings, not 0-255 (Battle_SetMaxAtbFromBattleSpeed @0x484490: "
                       "max_atb = 4000×(battleSpeed+1)). Higher = slower ATB AND longer status timers, "
                       "since timer ticks = 4×(battleSpeed+1)×value. 2 is the config midpoint."),
    "dead_allies":    ("KO'd allies", 0, 0, 2,
                       "Number of KO'd party members - raises the crisis level (Limit Break "
                       "availability) faster."),
    "hp_ratio":       ("HP % (cur/max)", 25, 0, 100,
                       "Character's current HP as a percent of max. Lower HP raises the crisis "
                       "level; this is the dominant term in the crisis formula."),
    "crisis_hp_mult": ("Crisis HP mult", 250, 0, 255,
                       "Per-character crisisLevelHPMultiplier (kernel Characters section). Retail: "
                       "250 for everyone except Seifer (100). Weights the missing-HP term."),
    "char_level":     ("Character level", 100, 1, 100,
                       "The level (1-100) at which to evaluate the stat curve. The 4 coefficients "
                       "define the whole curve; this just picks which level's value to show."),
    "attacker_str":   ("Attacker STR", 128, 0, 255,
                       "The attacker's STR stat (the weapon's STR bonus is added on top). Drives "
                       "physical damage. A mid/late-game value is ~120-255."),
    "attacker_luck":  ("Attacker LUCK", 20, 0, 255,
                       "The attacker's LUCK stat — feeds critical-hit chance and half of it feeds "
                       "hit%."),
    "target_vit":     ("Target VIT", 64, 0, 255,
                       "The target's VIT stat — physical defence. Vit0/Meltdown force it to 0."),
    "target_eva":     ("Target EVA", 10, 0, 255,
                       "The target's Evade stat — subtracted from the attacker's hit%."),
    "target_luck":    ("Target LUCK", 20, 0, 255,
                       "The target CHARACTER's LUCK — also subtracted from the attacker's hit%. "
                       "Only asked when a character is the target: a monster's LUCK is always 0."),
    "monster_str":    ("Monster STR", 40, 0, 255,
                       "The attacking monster's STR (its .dat STR curve at its level × the AI "
                       "stat multiplier, capped 255). Monsters get no weapon STR bonus."),
    "monster_mag":    ("Monster MAG", 40, 0, 255,
                       "The attacking monster's MAG (its .dat MAG curve at its level × the AI "
                       "stat multiplier, capped 255)."),
    "attacker_maxhp": ("Attacker max HP", 2000, 1, 999999,
                       "The attacking monster's own max HP (Kamikaze deals 5× this)."),
    "target_kills":   ("Target kill count", 50, 0, 65535,
                       "How many enemies the target character has killed (savemap NumKills) - "
                       "Everyone's Grudge multiplies its power by this."),
    "hit_junction_bonus": ("Junctioned HIT bonus", 0, 0, 255,
                       "Extra Hit% from magic junctioned to the character's HIT stat "
                       "(K_MAGIC.hitJunctionValue × stock / 100). Added to the weapon's hit "
                       "rate; the total is capped at 255."),
    "attacker_spd":   ("Attacker SPD", 30, 0, 255,
                       "The battler's SPD stat — drives how fast their own ATB gauge fills. A "
                       "mid-game value is ~20-40."),
    "render_fps":     ("Assumed render FPS", 30, 15, 240,
                       "ATB is ticked 3x per RENDERED frame (Battle_TickAtbGaugesAndGfCountdown, "
                       "called from isBattle_HUDdisplay, called 3x per frame by "
                       "battle_cardgame_main_loop) — NOT on a fixed logic clock like the status "
                       "timers. This is the PC port's well-known 'ATB speeds up with framerate' "
                       "quirk: an uncapped/high-FPS setup fills ATB faster in real time. This value "
                       "is only a what-if assumption to turn ticks into seconds."),
    "target_resistance": ("Target status resistance %", 0, -100, 155,
                       "The target's resistance to this status, as the Ifrit Stat tab shows it: "
                       "0 = neutral, 100 or more = immune, below 0 = more vulnerable. Each point "
                       "lowers the chance by 1%.\n"
                       "The game stores it as this value + 100: setBattleSlotData @0x48b310 fills "
                       "every status resistance with 100 before a battle, then a monster's .dat or a "
                       "character's ST-Def junctions overwrite it.\n"
                       "Vanilla monsters: mostly 20 for Poison / Blind / Silence / Sleep / Doom, 0 "
                       "for Haste / Regen / Reflect / Drain, 155 (immune) for bosses.\n"
                       "Immunity (stored >= 200: Battle_ApplyStatusWithResistRoll @0x48f9f0, cmp "
                       "cl, 0C8h) is skipped only by an accuracy of 255."),
    "gf_level":       ("GF level", 100, 1, 100,
                       "The GF's level (1-100), at which to evaluate its HP / next-level EXP / "
                       "damage. GFs level from experience like characters."),
    "gf_boost":       ("GF Boost %", 100, 100, 250,
                       "The GF Boost minigame result: 100 = no boost (default), up to 250 for a "
                       "perfect boost. Multiplies GF damage."),
    "gf_summon_mag":  ("Summon MAG bonus", 0, 0, 255,
                       "The SumMag% bonus from magic junctioned to the GF's SumMag slots (raises GF "
                       "damage by (this+100)/100). 0 = no SumMag magic junctioned."),
    # A switch, not a number: the popup shows it as a checkbox in its battle setup, never as
    # a spinbox (no formula lists it in its "params").
    "cronos_formula": ("Cronos damage formula", 0, 0, 1,
                       "Cronos's DamageFormulaUpdate hext: magic uses (320 - SPR) x 2 x MAG instead "
                       "of (265 - SPR) x (Power + MAG) and is no longer halved for a monster caster; "
                       "the gunblade uses 320 - VIT instead of 265 - VIT. Other physical attacks and "
                       "GF damage are unchanged."),
}

# Live, user-editable values (start at defaults). Edited in the formula popups.
PARAM_VALUES = {k: v[1] for k, v in PARAM_DEFS.items()}

# callable(formula_key) -> {param: value}, applied on top of PARAM_VALUES by compute(): the
# stats of a real character and monster picked in the battle setup (battle_setup.py) replace
# the typed assumptions they cover. None: typed assumptions only.
PARAM_OVERRIDES = None


def reset_params():
    for k, v in PARAM_DEFS.items():
        PARAM_VALUES[k] = v[1]


def _idiv(a, b):
    """C-style integer division truncating toward zero (matches the game / doomtrain)."""
    if b == 0:
        return 0
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


# --- Cronos's DamageFormulaUpdate hext -------------------------------------
# Four patches, checked against the exe (Cronos CronosFiles/DifficultyBalance/
# DamageFormulaUpdate): in Damage_ComputeMagicAndGF's Magic case the defence constant 265
# (0x491C90) becomes 320, "add eax, ebp" (MAG + Power, 0x491C95) becomes "add eax, eax"
# (MAG + MAG), and "cmp ebx, 3" before the monster-caster halving (0x491CC6) becomes
# "cmp ebx, 15", which no slot reaches. In Damage_ComputeGunblade the 265 (0x48F58F) becomes
# 320. GF damage and every other physical attack keep 265.
def _cronos(P):
    return bool(P.get("cronos_formula"))


def _magic_core(P, power, mag):
    """(defence constant, magic term, then that term as text / substituted text / LaTeX /
    substituted LaTeX) for an offensive spell, vanilla or Cronos."""
    if _cronos(P):
        return 320, 2 * mag, "(2×MAG)", f"(2×{mag})", r"(2\,MAG)", rf"(2\cdot{mag})"
    return 265, power + mag, "(P+MAG)", f"({power}+{mag})", r"(P+MAG)", rf"({power}+{mag})"


def _cronos_magic_note(P):
    return ("Cronos damage formula: 320 instead of 265, 2×MAG instead of Power+MAG (the power "
            "still multiplies the result), no halving for a monster caster. ") if _cronos(P) else ""


# --- formula computations ---------------------------------------------------
# Each returns a dict: symbolic (str), substituted (str), result (str), note (str|None),
# params (tuple of PARAM_DEFS keys to expose editors for).
# A formula that is a CURVE over one of its params can add two more keys, and the popup then
# draws it (like doomtrain's stat charts) instead of only showing the single sampled value:
#   value: the numeric result at the current params (None when the formula can't be evaluated)
#   plot:  {"param": <PARAM_DEFS key to sweep>, "x_label": str, "y_label": str}

def _status_timer(value, P, entry):
    bs = P["battle_speed"]
    ticks = 4 * (bs + 1) * value
    # computeTimerStatus (0x483470) subtracts timer_speed_multiplier from the timer every
    # battle frame: 2 by default, 3 under Haste, 1 under Slow, 0 under Stop. The battle loop
    # runs ~15 fps, so ~30 ticks are consumed per second at the default rate.
    secs = ticks / 30.0
    return {
        "params": ("battle_speed",),
        "symbolic": "ticks = 4 × (battleSpeed+1) × value ;  −2 per frame (default) at ~15 fps → ÷30",
        "substituted": f"4 × ({bs}+1) × {value} = {ticks} ticks   →   {ticks} / 30",
        "result": f"≈ {secs:.1f} s  ({ticks} ticks)   default rate — Haste ≈1.5× faster, "
                  f"Slow 2× slower, Stop freezes it",
        "note": "setupStatus2Timer @0x4832f0 loads 4×(battleSpeed+1)×value ticks; computeTimerStatus "
                "@0x483470 subtracts 2 each idle battle frame (3 under Haste, 1 Slow, 0 Stop) at ~15 fps "
                "(pinned by the Regen tick: it heals every 30 frames ≈ 2 s). battleSpeed is the config "
                "0 (fast) … 4 (slow), midpoint 2 — NOT 0-255 (Battle_SetMaxAtbFromBattleSpeed: "
                "max_atb = 4000×(battleSpeed+1), the same tick unit). Timers only tick during idle ATB "
                "time, not during action animations, so real fights feel longer than this estimate.",
        "latex": r"t \approx \frac{4\,(battleSpeed+1)\,value}{2 \times 15}\ \text{s}",
        "latex_sub": rf"\frac{{4\cdot({bs}+1)\cdot{value}}}{{30}}\approx{secs:.1f}\ \text{{s}}",
    }


def _dead_timer(value, P, entry):
    return {
        "params": (),
        "symbolic": "interval ≈ value / 15   s   (decremented once per battle tick)",
        "substituted": f"{value} / 15",
        "result": f"≈ {value / 15:.1f} s between summon checks",
        "note": "Interval between the random Gilgamesh / Angelo / Phoenix auto-summon checks "
                "(summonGilgaAngelStartFight), not a death countdown.",
        "latex": r"interval \approx \frac{value}{15}\ \text{s}",
        "latex_sub": rf"\frac{{{value}}}{{15}}",
    }


def _atb_speed(value, P, entry):
    # Battle_TickAtbGaugesAndGfCountdown @0x4842b0: cur_atb += rate * K_MISC.atb_speed_multiplier *
    # (SPD+30) / 100 each tick; rate = 10 normal / 15 Haste / 5 Slow. Ticked 3x per RENDERED frame
    # (isBattle_HUDdisplay, called 3x/frame by battle_cardgame_main_loop) - not the fixed ~15fps
    # logic clock the status timers use. max_atb = 4000*(battleSpeed+1) (Battle_SetMaxAtbFromBattle
    # Speed @0x484490).
    spd = P["attacker_spd"]
    bs = P["battle_speed"]
    fps = P["render_fps"]
    per_tick = _idiv(10 * value * (spd + 30), 100)
    per_frame = 3 * per_tick
    max_atb = 4000 * (bs + 1)
    if per_frame <= 0:
        return {
            "params": ("attacker_spd", "battle_speed", "render_fps"),
            "symbolic": "cur_atb += 10 × multiplier × (SPD+30) / 100, 3×/rendered frame",
            "substituted": f"multiplier {value} → 0 gain per tick",
            "result": "ATB never fills (multiplier or SPD too low)",
            "note": "See below.",
            "latex": r"\Delta atb = \frac{10\cdot mult\cdot(SPD+30)}{100}",
            "latex_sub": "0",
        }
    frames = max_atb / per_frame
    secs = frames / fps
    return {
        "params": ("attacker_spd", "battle_speed", "render_fps"),
        "symbolic": "cur_atb += 10 × multiplier × (SPD+30) / 100, applied 3×/rendered frame  "
                    "(max_atb = 4000×(battleSpeed+1))",
        "substituted": f"10 × {value} × ({spd}+30)/100 = {per_tick}/tick × 3 = {per_frame}/frame;  "
                       f"max_atb {max_atb} / {per_frame} = {frames:.0f} frames",
        "result": f"≈ {frames:.0f} frames to fill the ATB gauge  (≈ {secs:.1f} s at {fps} fps)",
        "note": "Battle_TickAtbGaugesAndGfCountdown @0x4842b0. ATB is ticked on the RENDER loop, not "
                "a fixed logic clock - this is the PC port's well-known framerate-coupled-ATB quirk, "
                "so the seconds figure is only as good as the FPS assumption above, not a fixed "
                "constant like the status timers. Retail value is 10 (not 100 - not a %-of-normal "
                "multiplier despite the name).",
        "latex": r"frames = \frac{4000(battleSpeed{+}1)}{3\left\lfloor\frac{10\cdot mult\cdot(SPD+30)}{100}\right\rfloor}",
        "latex_sub": rf"\frac{{{max_atb}}}{{{per_frame}}}\approx{frames:.0f}\ \text{{frames}}",
    }


def _devour_hp(value, P, entry):
    mhp = P["target_maxhp"]
    amount = _idiv(value * mhp, 16)
    return {
        "params": ("target_maxhp",),
        "symbolic": "HP healed/damaged = floor(value / 16 x maxHP)",
        "substituted": f"{value} / 16 x {mhp} = {amount}",
        "result": f"{amount} HP  ({value}/16 = {value / 16 * 100:.1f}% of max HP)",
        "note": "Devour restores (or, for a damage entry, deals) this many HP.",
        "latex": r"HP = \left\lfloor \frac{value}{16}\cdot maxHP \right\rfloor",
        "latex_sub": rf"\frac{{{value}}}{{16}}\cdot{mhp}={amount}",
    }


def _gf_compat(value, P, entry):
    # Verified in BattleAction_ExecuteCommand (0x485a2b): each time this magic is cast /
    # this GF is summoned, the character's stored compatibility with that GF changes by
    # (byte - 100), clamped to [1000, 6000]. NOT a per-tick summon-gauge fill.
    delta = value - 100
    if delta > 0:
        change = f"rises by {delta}"
    elif delta < 0:
        change = f"falls by {-delta}"
    else:
        change = "does not change"
    zero_hint = (" — NOTE: 100 is the neutral value, so 0 here is a real −100, not 'no change'."
                 if value == 0 else "")
    return {
        "params": (),
        "symbolic": "on each cast/summon:  storedCompatibility += (value − 100)   "
                    "[clamped 1000..6000;  100 = no change]",
        "substituted": f"delta = {value} − 100 = {delta:+d}",
        "result": f"Compatibility with this GF {change} each time it's used.{zero_hint}",
        "note": "100 = no change; >100 raises, <100 lowers. Verified in BattleAction_ExecuteCommand "
                "(0x485a2b): the change is applied to EVERY owned GF, the acting one included — there "
                "is no self-exclusion. That's why every GF's own column is 0 in retail (Eden 90): "
                "summoning a GF deliberately LOWERS your compatibility with that same GF by 100, "
                "while nudging the others up (108=+8, 'friendly' GF pairs 150=+50). Compatibility is "
                "raised mainly by casting magic the GF likes, not by summoning it. The stored value "
                "(1000-6000) then sets summon-gauge speed — higher = the GF arrives sooner.",
        "latex": r"\Delta\,compat = value - 100 \quad [1000..6000]",
        "latex_sub": rf"\Delta\,compat = {value} - 100 = {delta:+d}",
    }


# The elemental term, checked in IDA (Damage_ComputeMagicAndGF @0x491ad0 for magic/GF,
# Damage_ApplyPhysicalModifiers @0x48f600 for physical): the engine keeps elemDef = 900 - element%
# per element (a monster's .dat byte x 10), so "element%" here is what the Ifrit Stat tab shows.
_ELEMENT_NOTE = (
    "elemental term: damage × element%/100, where element% is the target's damage taken for "
    "that element as the Ifrit Stat tab shows it (100 = normal, 200 = double, 0 = immune, "
    "negative = absorbs: the result heals, shown as a GREEN number). Applied only when the "
    "attack has an element, and with several elements only the FIRST one set (lowest bit: Fire, "
    "Ice, Thunder, Earth, Bio, Wind, Water, Holy) counts. Holy against a Zombie target always "
    "counts as 200%. No cap on weakness. (Physical attacks use the attack's element % too: "
    "damage + damage × elementPercent/100 × (element% - 100)/100.)")


# The real FF8 attack_type enum (kernel value -> meaning), from the attack_type dispatcher
# Damage_DispatchByAttackType (0x4922b0). Used to pick the correct damage formula per spell.
ATTACK_TYPE_NAMES = {
    0: "None", 1: "Physical Attack", 2: "Magic Attack", 3: "Curative Magic",
    4: "Curative Item", 5: "Revive", 6: "Revive at Full HP", 7: "% Physical Damage",
    8: "% Magic Damage (Demi)", 9: "Renzokuken Finisher", 10: "Squall Gunblade", 11: "GF",
    12: "Scan", 13: "LV Down", 14: "Summon Item", 15: "GF (Ignore SPR)", 16: "LV Up",
    17: "Card", 18: "Kamikaze", 19: "Devour", 20: "% GF Damage (Diablos)", 21: "Heal maxHP/16",
    22: "Magic Attack (Ignore SPR)", 23: "Angelo Search", 24: "Moogle Dance", 25: "White Wind",
    26: "LV? Attack", 27: "Fixed Damage", 28: "Target HP − 1", 29: "Fixed (GF level)",
    30: "Unknown", 31: "Unknown", 32: "Give % HP (heal)", 33: "Unknown",
    34: "Everyone's Grudge", 35: "1 HP Damage", 36: "Physical (Ignore VIT)",
}


# Magic/GF damage, per the real attack_type dispatch (Damage_DispatchByAttackType 0x4922b0).
# The offensive-magic core is Damage_ComputeMagicAndGF (0x491ad0); curative is computeCurativeMagic
# (0x493280). Includes the 240..272/256 random spread + elemental term that doomtrain drops. Every
# attack type resolves to a clean message (never a dead-end) even when it deals no HP damage.
def _gf_hp(value, P, entry):
    # getGFhpForLvl @0x496120: HP = HPMod3 + level*HPMod1 + 10*level^2/HPMod2.
    m1 = (entry.get("gf_hp_modifier_1") if entry else 0) or 0
    m2 = (entry.get("gf_hp_modifier_2") if entry else 0) or 0
    m3 = (entry.get("gf_hp_modifier_3") if entry else 0) or 0
    lvl = P["gf_level"]
    if m2 == 0:
        result = "HPMod2 = 0 → division by zero (invalid; retail HPMod2 is never 0)"
        hp = None
    else:
        hp = m3 + lvl * m1 + _idiv(10 * lvl * lvl, m2)
        result = f"{hp} HP at GF level {lvl}"
    return {
        "params": ("gf_level",),
        "symbolic": "GF HP = HPMod3 + level × HPMod1 + 10 × level² / HPMod2",
        "substituted": (f"{m3} + {lvl}×{m1} + 10×{lvl}²/{m2}" if m2 else f"{m3} + {lvl}×{m1} + 10×{lvl}²/0"),
        "result": result,
        "value": hp,
        "plot": {"param": "gf_level", "x_label": "GF level", "y_label": "HP"},
        "note": "getGFhpForLvl @0x496120. The three HP modifiers define the GF's whole HP curve; "
                "level is where it's sampled. HPMod1 = linear/level, HPMod2 = quadratic divisor, "
                "HPMod3 = flat base.",
        "latex": r"HP = HPMod_3 + level\cdot HPMod_1 + \left\lfloor\frac{10\,level^2}{HPMod_2}\right\rfloor",
        "latex_sub": (rf"{m3} + {lvl}\cdot{m1} + \lfloor 10\cdot{lvl}^2/{m2}\rfloor = {hp}"
                      if m2 else r"\text{div by 0}"),
    }


def _gf_next_exp(value, P, entry):
    # GetGFLevelFromExperience @0x4960c0: cumulative EXP threshold for level L is
    # 10*mod1*L + mod2*L^2/256 (the loop accumulates 10*mod1 and mod2 per level).
    m1 = (entry.get("gf_level_modifier_1") if entry else 0) or 0
    m2 = (entry.get("gf_level_modifier_2") if entry else 0) or 0
    lvl = P["gf_level"]
    exp = 10 * m1 * lvl + _idiv(m2 * lvl * lvl, 256)
    return {
        "params": ("gf_level",),
        "symbolic": "total EXP to reach level L = 10 × mod1 × L + mod2 × L² / 256",
        "substituted": f"10×{m1}×{lvl} + {m2}×{lvl}²/256 = {exp}",
        "result": f"≈ {exp} total EXP to reach GF level {lvl}",
        "value": exp,
        "plot": {"param": "gf_level", "x_label": "GF level", "y_label": "Total EXP"},
        "note": "GetGFLevelFromExperience @0x4960c0 walks levels while "
                "experience ≥ 10×mod1×L + mod2×L²/256, so this is the cumulative EXP threshold "
                "for level L. mod1 = linear term, mod2 = quadratic (÷256) acceleration.",
        "latex": r"Exp(L) = 10\,mod_1\,L + \left\lfloor\frac{mod_2\,L^2}{256}\right\rfloor",
        "latex_sub": rf"10\cdot{m1}\cdot{lvl} + \lfloor {m2}\cdot{lvl}^2/256\rfloor = {exp}",
    }


def _gf_damage(value, P, entry):
    # ComputeMagicAndGFDamage @0x491ad0 (GF_DAMAGE case): dmg = (rand%33+240) *
    # ((SumMag+100) * (Boost * (P * ((265-spr)*(levelMod*GFLvl/10 + P + powerMod)/8)/256)/100)/100)/256
    p = (entry.get("gf_power") if entry else 0) or 0
    lmod = (entry.get("level_mod") if entry else 0) or 0
    pmod = (entry.get("power_mod") if entry else 0) or 0
    lvl = P["gf_level"]
    spr = P["target_spr"]
    boost = P["gf_boost"]
    smag = P["gf_summon_mag"]
    inner = _idiv((265 - spr) * (_idiv(lmod * lvl, 10) + p + pmod), 8)
    a = _idiv(p * inner, 256)
    b = _idiv(boost * a, 100)
    c = _idiv((smag + 100) * b, 100)

    def roll(r):
        return _idiv(r * c, 256)

    avg, lo, hi = roll(256), roll(240), roll(272)
    return {
        "params": ("gf_level", "target_spr", "gf_boost", "gf_summon_mag"),
        "symbolic": "dmg = P × (265−SPR) × (levelMod×GFLvl/10 + P + powerMod)/8 /256 × Boost/100 × "
                    "(SumMag+100)/100 × rand[240..272]/256",
        "substituted": f"P={p}, levelMod={lmod}, powerMod={pmod}, GFLvl={lvl}, SPR={spr}, "
                       f"Boost={boost}, SumMag={smag}",
        "result": f"≈ {avg} damage  (random {lo}–{hi})",
        "note": "ComputeMagicAndGFDamage @0x491ad0 (GF damage case). P = GF power, levelMod & "
                "powerMod are the GF-damage tail bytes. Then Shell/Defend halve, and the elemental "
                "term applies (not shown). Monster casters halve the result.",
        "latex": (r"dmg = \frac{SumMag{+}100}{100}\cdot\frac{Boost}{100}\cdot\left\lfloor\frac{P\,"
                  r"\lfloor(265{-}SPR)\lfloor levelMod\cdot GFLvl/10 + P + powerMod\rfloor/8\rfloor}"
                  r"{256}\right\rfloor\cdot\frac{rand}{256}"),
        "latex_sub": rf"\approx {avg}\ \text{{damage}}",
    }


def _magic_damage(value, P, entry):
    # Read every input from the (live) entry so the f(x) button works from ANY of them
    # (spell power, attack type, hit count), not just the field the button sits on.
    p = (entry.get("spell_power") if entry else None)
    if p is None:
        p = value                   # fallback when opened without an entry
    att = entry.get("attack_type") if entry else 2
    hit = (entry.get("hit_count") if entry else 1) or 1
    name = ATTACK_TYPE_NAMES.get(att, f"type {att}")
    hits_txt = f"  × {hit} hits" if hit > 1 else ""

    def _msg(sym, sub, res, note, params=(), latex=None, latex_sub=None):
        return {"params": params, "symbolic": sym, "substituted": sub, "result": res,
                "note": note, "latex": latex, "latex_sub": latex_sub}

    # --- offensive magic (Magic Attack, Ignore-SPR variant, LV? Attack all share the core) ---
    # att 0 (None / empty entry) also shows this formula: the formula is a property of the
    # field, not of whether this particular entry happens to hold data.
    if att in (0, 2, 22, 26):
        ignore = att == 22
        spr_eff = 0 if ignore else P["target_spr"]
        elem = P["elem_defense"]   # damage taken %, as Ifrit shows it (= 900 - engine elemDef)
        k, base, base_sym, base_sub, base_tex, base_tex_sub = _magic_core(P, p, P["caster_mag"])
        t1 = _idiv((k - spr_eff) * base, 4)
        t2 = _idiv(p * t1, 256)

        def roll(r):
            return _idiv(_idiv(r * t2, 256) * elem, 100) * hit

        avg, lo, hi = roll(256), roll(240), roll(272)
        return _msg(
            f"t1=({k}−SPR)×{base_sym}/4   t2=P×t1/256   dmg=(rand[240..272]/256)×t2×element%/100"
            + (" [SPR forced 0]" if ignore else ""),
            f"t1=({k}−{spr_eff})×{base_sub}/4={t1}   t2={p}×{t1}/256={t2}   "
            f"×{elem}/100{hits_txt}",
            f"≈ {avg} damage   (random spread {lo}–{hi})",
            (f"This entry's attack type is None (unused/empty slot); showing the standard Magic "
             f"Attack formula for reference. " if att == 0 else f"Attack type '{name}'. ")
            + _cronos_magic_note(P)
            + "Real formula (Damage_ComputeMagicAndGF), incl. the random roll and " + _ELEMENT_NOTE
            + " Not modelled: monster casters halve, Shell halves (and shows the Shell shimmer, "
            "effect 40), Defend halves (magic only — Defend fully nullifies PHYSICAL)."
            + (" LV? Attack also only hits on matching level." if att == 26 else ""),
            ("caster_mag", "target_spr", "elem_defense"),
            latex=(rf"dmg=\left\lfloor\frac{{rand}}{{256}}\cdot\frac{{P\,({k}-SPR){base_tex}}}{{4\cdot256}}"
                   r"\right\rfloor\cdot\frac{element\%}{100}"),
            latex_sub=(rf"\frac{{240..272}}{{256}}\cdot"
                       rf"\frac{{{p}\,({k}-{spr_eff}){base_tex_sub}}}{{1024}}\cdot"
                       rf"\frac{{{elem}}}{{100}}" + (rf"\cdot{hit}" if hit > 1 else "")))

    # --- curative magic ---
    if att == 3:
        half = _idiv(p + P["caster_mag"], 2)

        def roll(r):
            return _idiv(p * r * half, 256) * hit

        avg, lo, hi = roll(256), roll(240), roll(272)
        return _msg(
            "heal = P × (rand[240..272]/256) × ((P+MAG)/2)",
            f"(P+MAG)/2=({p}+{P['caster_mag']})/2={half}   heal={p}×(≈1)×{half}{hits_txt}",
            f"≈ {avg} HP healed   (random spread {lo}–{hi})",
            "Real formula (computeCurativeMagic). Shell halves healing in-game; Zombie targets take "
            "it as damage.", ("caster_mag",),
            latex=r"heal=P\cdot\frac{rand}{256}\cdot\frac{P+MAG}{2}",
            latex_sub=(rf"{p}\cdot\frac{{240..272}}{{256}}\cdot\frac{{{p}+{P['caster_mag']}}}{{2}}"
                       + (rf"\cdot{hit}" if hit > 1 else "")))

    # --- % current-HP damage (Demi family) ---
    if att == 8:
        hp = P["target_hp"]
        dmg = _idiv(p * hp, 16) * hit
        return _msg(
            "damage = P × currentHP / 16",
            f"{p} × {hp} / 16{hits_txt}",
            f"≈ {dmg} damage   ({p}/16 = {p / 16 * 100:.1f}% of current HP)",
            "% current-HP attack (Demi). Misses Float / gravity-immune targets.", ("target_hp",),
            latex=r"dmg=\frac{P\cdot currentHP}{16}",
            latex_sub=rf"\frac{{{p}\cdot{hp}}}{{16}}" + (rf"\cdot{hit}" if hit > 1 else ""))

    # --- revive ---
    if att == 5:
        mhp = P["target_maxhp"]
        return _msg(
            "revive HP = maxHP / 8",
            f"{mhp} / 8",
            f"≈ {_idiv(mhp, 8)} HP on revive  (1/8 of max)",
            "Life-type revive (Damage_ComputeReviveHP). From the Item command with Med Data it's "
            "maxHP/4 instead.", ("target_maxhp",),
            latex=r"revive=\frac{maxHP}{8}", latex_sub=rf"\frac{{{mhp}}}{{8}}")
    if att == 6:
        mhp = P["target_maxhp"]
        return _msg("revive HP = maxHP (full)", f"maxHP = {mhp}", f"{mhp} HP  (revive to full)",
                    "Full-Life-type: revives the target to full HP.", ("target_maxhp",),
                    latex=r"revive=maxHP", latex_sub=rf"maxHP={mhp}")

    # --- %-of-maxHP heals (Full-cure / Angelo Recover; Unknown-1 also maxHP/16) ---
    if att in (21, 32):
        mhp = P["target_maxhp"]
        heal = _idiv(p * mhp, 16) * hit
        return _msg(
            "heal = P × maxHP / 16",
            f"{p} × {mhp} / 16{hits_txt}",
            f"≈ {heal} HP healed   ({p}/16 = {p / 16 * 100:.1f}% of max HP)",
            "Percent-of-maxHP heal (Damage_ComputeCurativeItemSpecial). Full-cure uses P=16 → full "
            "heal.", ("target_maxhp",),
            latex=r"heal=\frac{P\cdot maxHP}{16}",
            latex_sub=rf"\frac{{{p}\cdot{mhp}}}{{16}}" + (rf"\cdot{hit}" if hit > 1 else ""))

    # --- curative item (50 × power) ---
    if att == 4:
        heal = 50 * p * hit
        return _msg("heal = 50 × P", f"50 × {p}{hits_txt}", f"≈ {heal} HP healed",
                    "Curative-item formula; Med Data doubles it (not shown).", (),
                    latex=r"heal=50\cdot P", latex_sub=rf"50\cdot{p}" + (rf"\cdot{hit}" if hit > 1 else ""))

    # --- types that deal no HP damage (status / support / utility) ---
    if att in (12, 17, 23, 24):
        return _msg("—", f"attack type: {name}",
                    f"No HP damage — '{name}' is a status/support/utility effect.",
                    "This spell's power isn't used for an HP formula; its effect is the attached "
                    "status or special action.")

    # --- everything else needs inputs this preview doesn't model (STR, GF level, fixed, ...) ---
    return _msg(
        f"'{name}': formula uses inputs not previewed here.",
        f"power = {p}, attack type = {att} ({name})",
        f"'{name}' — power {p}. (Physical/GF/fixed-damage types aren't modelled in this preview.)",
        "Only magic, curative, %-HP and revive families have a modelled formula here; physical, GF "
        "and fixed-damage types depend on STR/GF-level/etc.")


class _PowerAs:
    """Entry view that answers ``get("spell_power")`` with another field (the Enemy-attack
    section calls its power byte ``attack_power``), so _magic_damage can be reused as is."""

    def __init__(self, entry, power):
        self._entry = entry
        self._power = power

    def get(self, name):
        if name == "spell_power":
            return self._power
        if name == "hit_count":
            return 1
        return self._entry.get(name) if self._entry else None


def _monster_damage(value, P, entry):
    # Enemy attack (kernel §4) power, per attack type through Damage_DispatchByAttackType
    # @0x4922b0. The attacker is a MONSTER: its STR/MAG come from the .dat stat curves, it has no
    # LUCK and no weapon STR bonus, and Damage_ComputeMagicAndGF @0x491ad0 HALVES offensive magic
    # when the attacker slot is >= 3 (a monster).
    p = entry.get("attack_power") if entry else None
    if p is None:
        p = value
    att = entry.get("attack_type") if entry else 1
    name = ATTACK_TYPE_NAMES.get(att, f"type {att}")

    def out(params, sym, sub, res, note, latex, latex_sub):
        return {"params": params, "symbolic": sym, "substituted": sub, "result": res,
                "note": note, "latex": latex, "latex_sub": latex_sub}

    # --- physical (Damage_ComputePhysicalCore @0x492c40 mode 0; 36 = mode 19, VIT forced 0) ---
    if att in (1, 36):
        s = P["monster_str"]
        vit = 0 if att == 36 else P["target_vit"]
        mid = _idiv(p * _idiv((265 - vit) * (s + _idiv(s * s, 16)), 256), 16)
        avg, lo, hi = (_idiv(r * mid, 256) for r in (256, 240, 272))
        return out(
            ("monster_str",) + (() if att == 36 else ("target_vit",)),
            "dmg = P × (265−VIT) × (STR + STR²/16) / 256 / 16 × rand[240..272]/256   (×2 on crit)"
            + ("   [VIT forced 0]" if att == 36 else ""),
            f"{p} × (265−{vit}) × ({s} + {s}²/16)/256 / 16 × ~1",
            f"≈ {avg} damage per hit  (random {lo}–{hi}; a crit doubles it → ≈{2 * avg})",
            f"Attack type '{name}'. Damage_ComputePhysicalCore @0x492c40 with the MONSTER's STR "
            "(its .dat STR curve × the AI stat multiplier) - no weapon STR bonus. VIT is the "
            "target character's (0 under Vit0/Meltdown). Crit ×2, Back Attack ×2, Protect ÷2, "
            "Zombie target ÷2 (Damage_ApplyPhysicalModifiers @0x48f600); Defend / Invincible / "
            "Petrify nullify it. Hit roll: see the Hit rate f(x). Elemental not shown.",
            r"dmg = \left\lfloor\frac{P\,(265{-}VIT)\,(STR + \lfloor STR^2/16\rfloor)}{256\cdot 16}"
            r"\right\rfloor\cdot\frac{rand}{256}",
            rf"\frac{{{p}\,(265{{-}}{vit})\,({s}+\lfloor {s}^2/16\rfloor)}}{{4096}}\approx {avg}")

    # --- offensive magic: same core as a spell, then halved for a monster caster ---
    if att in (0, 2, 22, 26):
        spr = 0 if att == 22 else P["target_spr"]
        elem = P["elem_defense"]   # damage taken %, as Ifrit shows it (= 900 - engine elemDef)
        k, base, base_sym, base_sub, base_tex, base_tex_sub = _magic_core(P, p, P["monster_mag"])
        t2 = _idiv(p * _idiv((k - spr) * base, 4), 256)
        halve = 1 if _cronos(P) else 2       # Cronos never halves a monster caster

        def roll(r):
            return _idiv(_idiv(_idiv(r * t2, 256), halve) * elem, 100)

        avg, lo, hi = roll(256), roll(240), roll(272)
        halving_sym = "" if halve == 1 else " ÷ 2 (monster)"
        return out(
            ("monster_mag",) + (() if att == 22 else ("target_spr",)) + ("elem_defense",),
            f"dmg = P × ({k}−SPR) × {base_sym}/4 / 256 × rand[240..272]/256{halving_sym} "
            "× element%/100" + ("   [SPR forced 0]" if att == 22 else ""),
            f"{p} × ({k}−{spr}) × {base_sub}/4 / 256 → {t2};" + ("  ÷2;" if halve == 2 else "")
            + f"  ×{elem}/100",
            f"≈ {avg} damage   (random {lo}–{hi})",
            (f"Attack type is None (empty slot); showing the Magic Attack formula for reference. "
             if att == 0 else f"Attack type '{name}'. ")
            + _cronos_magic_note(P)
            + ("Damage_ComputeMagicAndGF @0x491ad0: a MONSTER caster's magic damage is halved "
               "(damage >>= 1 when the attacker slot >= 3) - the same spell hurts half as much from "
               "a monster as from a character. " if halve == 2 else "Damage_ComputeMagicAndGF @0x491ad0. ")
            + "Then Shell ÷2, Defend ÷2, then the " + _ELEMENT_NOTE
            + (" LV? Attack only hits targets whose level is a multiple of the hit rate byte."
               if att == 26 else ""),
            rf"dmg = \left\lfloor\frac{{rand}}{{256}}\cdot\frac{{P\,({k}-SPR){base_tex}}}{{4\cdot256}}"
            r"\right\rfloor" + (r"\cdot\frac{1}{2}" if halve == 2 else "") + r"\cdot\frac{element\%}{100}",
            rf"\frac{{{p}\,({k}-{spr}){base_tex_sub}}}{{1024}}"
            + (r"\cdot\frac{1}{2}" if halve == 2 else "")
            + rf"\cdot\frac{{{elem}}}{{100}}\approx {avg}")

    # --- % current HP (7 = physical path mode 1, 8 = magic path): P × curHP / 16 ---
    if att in (7, 8):
        hp = P["target_hp"]
        dmg = _idiv(p * hp, 16)
        return out(
            ("target_hp",), "damage = P × currentHP / 16", f"{p} × {hp} / 16",
            f"≈ {dmg} damage   ({p}/16 = {p / 16 * 100:.1f}% of current HP)",
            f"Attack type '{name}'. Gravity-immune targets are missed"
            + (" (physical path: also needs the hit roll; Protect halves)." if att == 7 else
               " (magic path: Shell / Defend halve). Not halved for a monster caster."),
            r"dmg=\frac{P\cdot currentHP}{16}", rf"\frac{{{p}\cdot{hp}}}{{16}}={dmg}")

    # --- Kamikaze: Damage_ComputePhysicalCore mode 3 ---
    if att == 18:
        mhp = P["attacker_maxhp"]
        return out(
            ("attacker_maxhp",), "damage = 5 × attacker max HP   (power not used)",
            f"5 × {mhp}", f"≈ {5 * mhp} damage  (before the 9999 cap)",
            "Kamikaze (Damage_ComputePhysicalCore @0x492c40 mode 3): 5 × the monster's own max "
            "HP; the power byte is ignored. Rolls the physical hit; Protect halves.",
            r"dmg = 5\cdot maxHP_{atk}", rf"5\cdot{mhp}={5 * mhp}")

    # --- Everyone's Grudge: mode 16, P × target character's kill count ---
    if att == 34:
        kills = P["target_kills"]
        return out(
            ("target_kills",), "damage = P × target's kill count", f"{p} × {kills}",
            f"≈ {p * kills} damage  (before the 9999 cap)",
            "Everyone's Grudge (Damage_ComputePhysicalWithHitCritRoll @0x492e10 mode 16): power × "
            "the TARGET character's NumKills from the savemap; 0 against a monster target.",
            r"dmg = P\cdot kills_{tgt}", rf"{p}\cdot{kills}={p * kills}")

    # --- fixed family: Damage_ComputeFixedSpecial @0x4931c0 ---
    if att == 27:
        hr = (entry.get("hit_rate") if entry else 0) or 0
        dmg = 100 * p - hr
        return out(
            (), "damage = 100 × P − hitRate", f"100 × {p} − {hr}", f"{dmg} damage  (no random spread)",
            "Fixed Damage (Damage_ComputeFixedSpecial @0x4931c0 mode 11): the hit rate byte is "
            "SUBTRACTED from 100 × power - it is not an accuracy here. Ignores STR/MAG/VIT/SPR; "
            "misses Petrify/Invincible targets.",
            r"dmg = 100\,P - hitRate", rf"100\cdot{p}-{hr}={dmg}")
    if att == 28:
        hp = P["target_hp"]
        return out(("target_hp",), "damage = target current HP − 1", f"{hp} − 1",
                   f"{hp - 1} damage  (leaves the target at 1 HP)",
                   "Damage_ComputeFixedSpecial @0x4931c0 mode 12; power is ignored.",
                   r"dmg = currentHP - 1", rf"{hp}-1={hp - 1}")
    if att == 35:
        return out((), "damage = 1", "power not used", "1 damage",
                   "Damage_ComputeFixedSpecial @0x4931c0 mode 18 (Excalipoor-style): always 1.",
                   r"dmg = 1", r"1")

    # --- heals / revive / status-only types: same formulas as a spell, power = this byte ---
    return _magic_damage(p, P, _PowerAs(entry, p))


def _crisis(value, P, entry):
    da = P["dead_allies"]
    hpr = P["hp_ratio"]
    mult = P["crisis_hp_mult"]
    RAND = 127  # average of GetRandomInt() 0..255
    status_sum = value  # this status's contribution when it (alone) is active
    num = 10 * (status_sum + 4 * (5 * da + 40)) - 10 * mult * hpr // 100
    lvl = _idiv(num, RAND + 160) - 4
    lvl = max(0, min(4, lvl))
    return {
        "params": ("dead_allies", "hp_ratio", "crisis_hp_mult"),
        "symbolic": "crisis = (10 x (statusSum + 4 x (5 x deadAllies + 40)) "
                    "- 10 x hpMult x HP% ) / (rand + 160) - 4   [clamp 0..4]",
        "substituted": f"(10 x ({status_sum} + 4 x (5 x {da} + 40)) "
                       f"- 10 x {mult} x {hpr}%) / ({RAND}+160) - 4",
        "result": f"crisis level ≈ {lvl}   (Limit Break available if > 0)",
        "note": "This status alone contributes statusSum = its byte. rand (0-255) is fixed at "
                "its average 127 here; in-game it makes the level flicker. Higher = Limit Break "
                "triggers more readily.",
        "latex": (r"crisis=\left\lfloor\frac{10\,(statusSum+4(5\,deadAllies+40))-10\,hpMult\,"
                  r"\frac{HP\%}{100}}{rand+160}\right\rfloor-4"),
        "latex_sub": (rf"\left\lfloor\frac{{10\,({status_sum}+4(5\cdot{da}+40))-10\cdot{mult}\cdot"
                      rf"\frac{{{hpr}}}{{100}}}}{{{RAND}+160}}\right\rfloor-4={lvl}"),
    }


# --- character base-stat curves (kernel section 7) --------------------------
# Each stat stores 4 coefficients (c1..c4) defining the character's BASE value of that
# stat at a given level (before junctions/bonuses). Three distinct curve shapes, all
# verified against the engine:
#   HP            (Stat_ComputeCharaMaxHP  0x496310): L*c1 - 10*L^2/c2 + c3   (c4 UNUSED)
#   STR/VIT/MAG/SPR (Stat_ComputeCharaStat 0x496440): (L*c1/10 + L/c2 - L^2/(2*c4) + c3)/4
#   SPD/LUCK      (same fn, separate branch 0x496440): L*c1 + L/c2 - L/c4 + c3  (linear!)
# All divisions truncate. HP has no base cap (final maxHP capped 9999 after junction);
# the other stats are capped at 255 by CapTo255 (0x495930). doomtrain's charts get HP and
# the STR family right but apply the STR-family formula to SPD/LUCK, which is wrong - they
# use the simpler linear shape above.
_CHAR_STAT_LABELS = {"hp": "HP", "str": "STR", "vit": "VIT", "mag": "MAG",
                     "spr": "SPR", "spd": "SPD", "luck": "LUCK"}
_CHAR_STAT_KIND = {"hp": "hp", "str": "std", "vit": "std", "mag": "std", "spr": "std",
                   "spd": "lin", "luck": "lin"}


def _make_char_stat(stat):
    kind = _CHAR_STAT_KIND[stat]
    ST = _CHAR_STAT_LABELS[stat]

    def fn(value, P, entry):
        L = P["char_level"]
        c1 = entry.get(f"{stat}_1") if entry else 0
        c2 = entry.get(f"{stat}_2") if entry else 0
        c3 = entry.get(f"{stat}_3") if entry else 0
        c4 = entry.get(f"{stat}_4") if entry else 0
        if kind == "hp":
            base = L * c1 - _idiv(10 * L * L, c2) + c3
            capped = max(base, 0)
            sym = "HP = level x c1  -  10 x level² / c2  +  c3"
            sub = f"{L} x {c1} - 10 x {L}² / {c2} + {c3} = {base}"
            res = f"Base HP at level {L}: {capped}"
            note = ("Character base HP (Stat_ComputeCharaMaxHP @0x496310), before HP-J and "
                    "bonuses. c4 is unused for HP. Final battle maxHP = junctionMult% x this, "
                    "capped at 9999.")
            latex = r"HP = level\cdot c_1 - \frac{10\,level^2}{c_2} + c_3"
            latex_sub = rf"{L}\cdot{c1} - \frac{{10\cdot{L}^2}}{{{c2}}} + {c3} = {base}"
        elif kind == "std":
            base = _idiv(_idiv(L * c1, 10) + _idiv(L, c2) - _idiv(L * L, c4 * 2) + c3, 4)
            capped = max(0, min(255, base))
            sym = f"{ST} = ( level x c1 / 10  +  level / c2  -  level² / (2 x c4)  +  c3 ) / 4"
            sub = f"({L}x{c1}/10 + {L}/{c2} - {L}²/(2x{c4}) + {c3}) / 4 = {base}"
            res = f"Base {ST} at level {L}: {capped}" + ("  (capped at 255)" if base > 255 else "")
            note = ("Character base stat (Stat_ComputeCharaStat @0x496440), before junctions/"
                    "bonuses. All divisions truncate; result capped at 255.")
            latex = (rf"{ST} = \frac{{\dfrac{{level\cdot c_1}}{{10}} + \dfrac{{level}}{{c_2}} "
                     rf"- \dfrac{{level^2}}{{2c_4}} + c_3}}{{4}}")
            latex_sub = (rf"\frac{{\frac{{{L}\cdot{c1}}}{{10}} + \frac{{{L}}}{{{c2}}} "
                         rf"- \frac{{{L}^2}}{{2\cdot{c4}}} + {c3}}}{{4}} = {base}")
        else:  # lin (SPD, LUCK)
            base = L * c1 + _idiv(L, c2) - _idiv(L, c4) + c3
            capped = max(0, min(255, base))
            sym = f"{ST} = level x c1  +  level / c2  -  level / c4  +  c3"
            sub = f"{L}x{c1} + {L}/{c2} - {L}/{c4} + {c3} = {base}"
            res = f"Base {ST} at level {L}: {capped}" + ("  (capped at 255)" if base > 255 else "")
            note = (f"Character base {ST} (Stat_ComputeCharaStat @0x496440, SPD/LUCK branch). "
                    "A plain LINEAR curve — no quadratic term and no /4, unlike STR/VIT/MAG/SPR. "
                    "Divisions truncate; result capped at 255. (doomtrain charts this stat with "
                    "the STR-family formula, which is incorrect.)")
            latex = rf"{ST} = level\cdot c_1 + \frac{{level}}{{c_2}} - \frac{{level}}{{c_4}} + c_3"
            latex_sub = rf"{L}\cdot{c1} + \frac{{{L}}}{{{c2}}} - \frac{{{L}}}{{{c4}}} + {c3} = {base}"
        return {
            "params": ("char_level",),
            "symbolic": sym,
            "substituted": sub,
            "result": res,
            "note": note,
            "latex": latex,
            "latex_sub": latex_sub,
            "value": capped,
            "plot": {"param": "char_level", "x_label": "Level", "y_label": f"Base {ST}"},
        }

    return fn


def _char_exp(value, P, entry):
    # Verified in Stat_ComputeLevelFromExp @0x4961d0: the EXP curve has two sub-parameters, now
    # exposed as two separate bytes. LOW (exp_linear) scales a linear term (x10 EXP/level); HIGH
    # (exp_quadratic) scales a quadratic term (/256). Cumulative EXP to reach level L =
    # 10*(L-1)*lo + (L-1)^2*hi/256.
    lo = (entry.get("exp_linear") if entry else 0) or 0
    hi = (entry.get("exp_quadratic") if entry else 0) or 0
    L = P["char_level"]
    n = L - 1
    total = 10 * n * lo + _idiv(n * n * hi, 256)
    per = (10 * L * lo + _idiv(L * L * hi, 256)) - total  # L -> L+1 increment
    curve = "flat (linear)" if hi == 0 else "accelerating (quadratic)"
    return {
        "params": ("char_level",),
        "symbolic": "totalExp(L) = 10 x (L−1) x expLow  +  (L−1)² x expHigh / 256   "
                    "[expLow = low byte, expHigh = high byte]",
        "substituted": f"expLow={lo}, expHigh={hi}   →   10x{n}x{lo} + {n}²x{hi}/256 = {total}",
        "result": f"Total EXP to reach level {L}: {total}   (+{per} for the next level)",
        "value": total,
        "plot": {"param": "char_level", "x_label": "Level", "y_label": "Total EXP"},
        "note": (f"The 'EXP modifier' WORD packs two values: low byte {lo} (linear, x10/level) and "
                 f"high byte {hi} (quadratic, /256). Here the curve is {curve}. Retail value 100 "
                 "(low=100, high=0) → a flat 1000 EXP per level. Verified in "
                 "Stat_ComputeLevelFromExp @0x4961d0."),
        "latex": (r"totalExp(L) = 10\,(L-1)\,expLow + \left\lfloor\frac{(L-1)^2\,expHigh}{256}"
                  r"\right\rfloor"),
        "latex_sub": (rf"10\cdot{n}\cdot{lo} + \left\lfloor\frac{{{n}^2\cdot{hi}}}{{256}}"
                      rf"\right\rfloor = {total}"),
    }


# --- weapon / physical-combat formulas (kernel section 5) -------------------
def _physical_damage(value, P, entry):
    # Physical damage core, verified in ComputeWithDamageSTRFormula @0x492c40 /
    # computeAttackPhysical @0x492e10: dmg = P*(265-VIT)*(STR + STR^2/16)/256/16 * rand/256.
    # The weapon's STR bonus is added to the attacker's STR first; a crit doubles the result.
    p = entry.get("attack_power") if entry else None
    if p is None:
        p = value
    sbonus = (entry.get("str_bonus") if entry else 0) or 0
    base_str = P["attacker_str"]
    eff_str = min(255, base_str + sbonus)
    vit = P["target_vit"]
    # Cronos patches only Damage_ComputeGunblade's constant: a gunblade (Squall, Seifer) uses
    # 320 - VIT there, every other weapon keeps 265.
    gunblade = bool(entry) and entry.get("attack_type") == ATTACK_TYPE_GUNBLADE
    k = 320 if (_cronos(P) and gunblade) else 265
    inner = _idiv((k - vit) * (eff_str + _idiv(eff_str * eff_str, 16)), 256)
    mid = _idiv(p * inner, 16)

    def roll(r):
        return _idiv(r * mid, 256)

    avg, lo, hi = roll(256), roll(240), roll(272)
    strp = f"STR₊ = {base_str} + {sbonus} = {eff_str}" if sbonus else f"STR₊ = {eff_str}"
    return {
        "params": ("attacker_str", "target_vit"),
        "symbolic": "STR₊ = STR + weaponStrBonus;  "
                    f"dmg = power × ({k}−VIT) × (STR₊ + STR₊²/16) / 256 / 16 × rand[240..272]/256"
                    "   (×2 on crit)",
        "substituted": f"{strp};   {p} × ({k}−{vit}) × ({eff_str} + {eff_str}²/16)/256 / 16 × ~1",
        "result": f"≈ {avg} damage per hit  (random {lo}–{hi}; a crit doubles it → ≈{2 * avg})",
        "note": ("Cronos damage formula: a gunblade uses 320 instead of 265 (Damage_ComputeGunblade); "
                 "a trigger hit is ×1.5. " if k == 320 else
                 "Cronos damage formula: only gunblades change (320 instead of 265); this weapon "
                 "keeps the vanilla formula. " if _cronos(P) else "")
                + "Physical damage core (ComputeWithDamageSTRFormula @0x492c40). The STR bonus IS "
                "accounted for — this weapon's STR bonus is added into the STR stat (GetCharacterStat "
                "@0x496440, STR only) and that boosted STR₊ is what feeds this formula. So set "
                "'Attacker STR' to your STR before this weapon; the bonus is added on top. VIT is the "
                "target's (0 under Vit0/Meltdown). Crit ×2 (+ white screen flash), Back Attack ×2, "
                "Protect ÷2 (and shows the Protect shimmer, effect 39), Zombie target ÷2 "
                "(Damage_ApplyPhysicalModifiers @0x48f600). Defend/Invincible/Petrify fully NULLIFY "
                "physical (unlike magic, which Defend only halves). Elemental and drain modifiers "
                "not shown; a negative final result (elemental absorb) displays as a GREEN heal "
                "number (HIT_TYPE_RESTORATIVE).",
        "latex": (rf"dmg = \left\lfloor\frac{{power\,({k}{{-}}VIT)\,(STR_{{+}} + \lfloor STR_{{+}}^2/16\rfloor)}}"
                  r"{256\cdot 16}\right\rfloor\cdot\frac{rand}{256},\quad STR_{+}=STR+bonus"),
        "latex_sub": (rf"STR_{{+}}={eff_str};\ \frac{{{p}\,({k}{{-}}{vit})\,({eff_str}+\lfloor {eff_str}^2/16\rfloor)}}"
                      rf"{{4096}}\approx {avg}"),
    }


def _crit_chance(value, P, entry):
    # Damage_RollCrit @0x492b30: crit if random byte 0..255 <= critBonus + LUCK. The kernel byte
    # feeding this is named crit_bonus on Weapons/Enemy attacks/Blue Magic and crit_increase on
    # Shot - confirmed the SAME roll for all 4 via their RELATED_TO_CRIT_BONUS write sites in
    # Battle_applyDamage (0x4901e9 Blue Magic, 0x49041e default/weapon+enemy-attack+Shot dispatch).
    # `value` is always this specific field's own current value, so no need to know its name.
    if entry and entry.get("attack_type") == ATTACK_TYPE_GUNBLADE:
        # Damage_ComputeGunblade @0x48f480 clears BOOL_ATTACK_CRITED and never calls the roll.
        return {
            "params": (),
            "symbolic": "Gunblade attack: no crit roll",
            "substituted": f"crit bonus {value} is not read in battle",
            "result": "0% critical-hit chance — the trigger replaces crits (×1.5 on a perfect "
                      "trigger)",
            "note": "Damage_DispatchByAttackType @0x4922b0 sends Attack Type 10 to "
                    "Damage_ComputeGunblade @0x48f480, which sets BOOL_ATTACK_CRITED = 0 and never "
                    "calls Damage_RollCrit. Its damage multiplier is (triggerDamage/20 + 2)/2: "
                    "×1 without a trigger, ×1.5 with a perfect one.",
            "latex": r"\text{Gunblade: no crit roll}",
            "latex_sub": r"P(crit) = 0",
        }
    luck = P["attacker_luck"]
    thr = min(255, value + luck)
    pct = (thr + 1) / 256 * 100 if thr > 0 else 0.0
    return {
        "params": ("attacker_luck",),
        "symbolic": "crit if  rand(0..255) ≤ thisValue + LUCK",
        "substituted": f"{value} + {luck} = {thr}   (threshold out of 256)",
        "result": f"≈ {pct:.1f}% critical-hit chance",
        "note": "Damage_RollCrit @0x492b30: this value plus the attacker's LUCK is the threshold; "
                "a random byte (0-255) ≤ it crits, doubling physical damage. (The wiki's old "
                "255×(critBonus+LUCK)/255 is the same value — the ×255/255 is a no-op.) Verified "
                "for Weapons, Enemy attacks, Blue Magic and Shot - all four feed the identical roll.",
        "latex": r"P(crit) = \frac{value + LUCK}{256}",
        "latex_sub": rf"\frac{{{value} + {luck}}}{{256}}\approx {pct:.1f}\%",
    }


def _crit_chance_monster(value, P, entry):
    # Same Damage_RollCrit roll, but the attacker is a MONSTER, and a monster has no LUCK stat:
    # setMonsterInfoFromDatInfoSection @0x48bbd0 writes charaStat[5] (LUCK) = 0 at load and nothing
    # ever writes it again for a monster slot (the monster .dat info section only carries
    # HP/STR/VIT/MAG/SPR/SPD/EVA curves - there is no LUCK curve). Damage_RollCrit reads exactly
    # that byte, so the LUCK term is a hard 0 here and this kernel byte alone decides the chance.
    # Hence no editable LUCK parameter: offering one would only invite a wrong assumption.
    thr = min(255, value)
    pct = (thr + 1) / 256 * 100 if thr > 0 else 0.0
    return {
        "params": (),
        "symbolic": "crit if  rand(0..255) ≤ thisValue     (monster LUCK is always 0)",
        "substituted": f"{value} + 0 = {thr}   (threshold out of 256)",
        "result": f"≈ {pct:.1f}% critical-hit chance"
                  + ("   — 255 = always crits" if value >= 255 else ""),
        "note": "Damage_RollCrit @0x492b30 adds the attacker's LUCK (charaStat[5]) to this value, "
                "but a monster's LUCK is hard-set to 0 by setMonsterInfoFromDatInfoSection "
                "@0x48bbd0 and never changes - monsters have no LUCK stat in their .dat. So for "
                "enemy attacks the chance is exactly thisValue/256 and this byte is the ONLY source "
                "of crits for a monster. A crit doubles the physical damage (and fires the white "
                "screen flash). Only crit-rolling Attack Types use it: Physical (1), % physical (7), "
                "Physical ignore VIT (36) - on any other Attack Type this byte is inert.",
        # No \underbrace / \text here: matplotlib's mathtext (formula_latex.render) doesn't
        # support them and would silently fall back to the plain-text formula.
        "latex": r"P(crit) = \frac{value + LUCK_{monster}}{256} = \frac{value}{256}"
                 r"\quad (LUCK_{monster} = 0)",
        "latex_sub": rf"\frac{{{value} + 0}}{{256}}\approx {pct:.1f}\%",
    }


# ALL 37 Attack Types (0-36) are now individually decompiled and categorized off the dispatcher
# Battle_DamageGettingRelated @0x4922b0 - nothing below is inferred from a field name. Two sets
# route the status-accuracy byte through the real STR/VIT vs MAG/SPR Battle_ApplyStatusWithResist
# Roll; the remaining sets each use a DIFFERENT mechanism (or ignore the byte entirely) - see the
# per-set decompile notes just below.
#   STR/VIT physical: Damage_ComputePhysicalCore / Damage_ComputePhysicalWithHitCritRoll ->
#     HpModifierComputationForPhysical's STR/VIT status roll.
#   MAG/SPR magic/GF: Damage_ComputeMagicAndGF -> applyHitStatusEffect(STATUS_DEF_CATEGORY_MAGICAL).
_PHYSICAL_ATTACK_TYPES = {1, 7, 9, 10, 18, 34, 36}
_MAGICAL_ATTACK_TYPES = {2, 8, 11, 15, 20, 22, 26, 33}
# Every other Attack Type's downstream function was individually decompiled and read (not
# inferred) - each routes status_attack_enabler through a DIFFERENT, non-Battle_ApplyStatus
# WithResistRoll mechanism, or doesn't read it at all:
#   Curative Item / White Wind / Angelo Recover (Damage_ComputeCurativeItemSpecial @0x493450):
#     `if (HIT_ATTACK_ACCURACY > rand(1..100)) checkDoubleStatusApply(...)` - a flat %, no stat
#     terms at all, and it CURES the listed statuses (removeStatus), not inflicts them.
#   Curative Magic / the Demi-type Unknown_1 (Damage_ComputeCurativeMagic @0x493280): calls
#     checkDoubleStatusApply UNCONDITIONALLY - HIT_ATTACK_ACCURACY is never read. Byte is dead.
#   Revive / Revive At Full HP (GetReviveHP @0x491940): clears Death unconditionally (if present,
#     not sealed) - HIT_ATTACK_ACCURACY never read. Byte is dead, EXCEPT reviving a Zombie-status
#     target instead deals unmissable magic damage via the Magic-dispatch path.
#   LV Down / LV Up (computeLvlUpDown @0x493650): `if (accuracy <= rand(0..255)) fail` gates the
#     WHOLE level-change action (a plain byte-range roll, no STR/VIT or MAG/SPR term) - this is a
#     success chance, not a "status inflicted" roll, but reuses the same kernel byte position.
#   Fixed Damage / Target-Current-HP-1 / Fixed-Magic-Based-on-GF-Level / 1 HP Damage
#     (Damage_ComputeFixedSpecial @0x4931c0): no HIT_ATTACK_ACCURACY reference anywhere. Dead.
#   Card (Battle_DamageGettingRelated case @0x492796 -> the actual capture roll is
#     Battle_RollCardCommand @0x48fba0): capture = (256 - 255*curHP/maxHP)/256 vs rand byte, rare
#     card 6.25%. This byte is NOT read.
#   Devour (dispatcher case @0x4926cf): success needs attacker_HP >= target_HP, chance =
#     (attackerHP - targetHP)/attackerHP; the byte is NOT read (Devour's status/stat effect comes
#     from the Devour kernel section, applied on success).
#   Scan (case @0x4925a6): reveals monster info, no roll, byte not read.
#   Angelo Search (case @0x49284b): finds a random item, no roll, byte not read.
#   Moogle Dance (case @0x4928d3): flags the target's junctioned GFs for HP recovery, no roll,
#     byte not read.
_CURE_FLAT_TYPES = {4, 25, 32}
_CURE_ALWAYS_TYPES = {3, 21}
_REVIVE_ALWAYS_TYPES = {5, 6}
_LV_UPDOWN_TYPES = {13, 16}
_CARD_TYPES = {17}
_DEVOUR_TYPES = {19}
_UTILITY_TYPES = {12, 23, 24}  # Scan, Angelo Search, Moogle Dance
# None (0) hits the dispatcher's LABEL_46 (sets the success flag, no damage/roll); 14 (Summon
# Item?), 30/31 (Unknown 2/3) have no dispatcher case at all -> default -> no effect. None read
# HIT_ATTACK_ACCURACY.
_NO_EFFECT_TYPES = {0, 14, 30, 31}
_NO_ROLL_TYPES = {27, 28, 29, 35}


def _status_accuracy(value, P, entry):
    atk_type = entry.get("attack_type") if entry and entry.has_field("attack_type") else None
    res_pct = P["target_resistance"]   # as the Ifrit Stat tab shows it: 0 = neutral, >= 100 immune
    res = res_pct + 100                # the stored resistance the engine compares

    if atk_type in _PHYSICAL_ATTACK_TYPES or atk_type in _MAGICAL_ATTACK_TYPES:
        # Battle_ApplyStatusWithResistRoll @0x48f9f0: fails outright if the target already has
        # the status, or its per-status mental resistance is >=200 (0xC8). Otherwise:
        #   chance = accuracy + attackerStat/4 - targetStat/4 - targetResistance
        #   accuracy 255      -> guaranteed (stat/resistance check skipped entirely)
        #   chance <= 0       -> fails
        #   accuracy 250..254 -> guaranteed if chance > 0
        #   else              -> roll floor(chance*255/100) against rand(0..255)
        if atk_type in _PHYSICAL_ATTACK_TYPES:
            atk_stat, tgt_stat, stat_label = P["attacker_str"], P["target_vit"], "STR/VIT"
            params = ("attacker_str", "target_vit", "target_resistance")
        else:
            atk_stat, tgt_stat, stat_label = P["caster_mag"], P["target_spr"], "MAG/SPR"
            params = ("caster_mag", "target_spr", "target_resistance")
        physical = atk_type in _PHYSICAL_ATTACK_TYPES
        note = ("Battle_ApplyStatusWithResistRoll @0x48f9f0, called by "
                + ("Damage_ApplyPhysicalModifiers @0x48f600" if physical
                   else "applyHitStatusEffect @0x492090 (from Damage_ComputeMagicAndGF)")
                + f": this Attack Type goes through the {'physical' if physical else 'magic/GF'} "
                f"damage core, so the stat pair is {stat_label}. Each listed status is rolled "
                "separately.\n"
                "Also: Vit0 / Meltdown on the target makes its "
                + ("VIT" if physical else "SPR") + " count as 0; nothing is rolled if the attack "
                "itself missed, nor while the target still has hits to receive (a multi-hit "
                "attack rolls its statuses once, on the last hit); the target's resistance is "
                "per status (0% = neutral, >= 100% = immune, as the Ifrit Stat tab shows it).\n"
                "Exceptions, whatever the roll: Stop never lands on a monster; a Zombie target "
                "can't get Slow or Death; Angel Wing blocks Shell, Silence and Berserk; "
                "inflicting Zombie removes Doom.")
        if value == 255:
            return {"params": params, "note": note, "latex": r"accuracy=255\Rightarrow 100\%",
                    "latex_sub": r"255 \Rightarrow \text{always}",
                    "symbolic": f"accuracy 255 → guaranteed ({stat_label}/resistance ignored)",
                    "substituted": "accuracy = 255",
                    "result": "Always inflicts (100%) - unless the target already has it, or "
                              "it's immune"}
        if res >= 200:
            return {
                "params": params, "note": note,
                "symbolic": "resistance >= 100% -> immune, checked before any roll",
                "substituted": f"resistance {res_pct}% >= 100%  (stored {res} >= 200)",
                "result": "Never inflicts (0%) - the target is immune to this status. Only "
                          "accuracy 255 bypasses it, by skipping the resistance check.",
                "latex": r"resistance \geq 100\% \Rightarrow 0\%",
                "latex_sub": rf"{res_pct}\% \geq 100\% \Rightarrow \text{{immune}}",
            }
        chance = value + _idiv(atk_stat, 4) - _idiv(tgt_stat, 4) - res
        if chance <= 0:
            pct = 0.0
        elif 250 <= value <= 254:
            pct = 100.0
        else:
            thr = _idiv(chance * 255, 100)
            pct = min(100.0, (thr + 1) / 256 * 100) if thr > 0 else 0.0
        return {
            "params": params, "note": note,
            "symbolic": f"chance = accuracy + {stat_label.split('/')[0]}/4 − "
                        f"{stat_label.split('/')[1]}/4 − (resistance% + 100)  (255 = guaranteed, "
                        "250-254 = guaranteed-if-positive, else rolled)",
            "substituted": f"{value} + {atk_stat}/4 − {tgt_stat}/4 − ({res_pct} + 100) = {chance}%",
            "result": f"≈ {pct:.1f}% chance to inflict  (before target-already-has-it / "
                      "immunity checks)",
            "latex": r"chance = accuracy + \frac{atkStat}{4} - \frac{tgtStat}{4} - (resistance\% + 100)",
            "latex_sub": rf"{value} + \frac{{{atk_stat}}}{{4}} - \frac{{{tgt_stat}}}{{4}} "
                         rf"- ({res_pct} + 100) = {chance}\%",
        }

    if atk_type in _CURE_FLAT_TYPES:
        # Damage_ComputeCurativeItemSpecial @0x493450: cures if accuracy > rand(1..100) - a flat
        # percentage, no STR/VIT or MAG/SPR term. This CURES the listed statuses, not inflicts.
        successes = max(0, min(value - 1, 100))
        pct = successes
        return {
            "params": (), "symbolic": "cures if  accuracy > rand(1..100)  (flat %, no stat terms)",
            "substituted": f"accuracy {value} > rand(1..100)", "result": f"≈ {pct}% chance to CURE"
            " the listed statuses (Curative Item / White Wind / Angelo Recover)",
            "note": "Damage_ComputeCurativeItemSpecial @0x493450. This byte gates whether the "
                    "cure happens at all - it removes the Status 1/2 listed on this entry, it "
                    "does not inflict them.",
            "latex": r"P(cure) = \frac{accuracy}{100}", "latex_sub": rf"\approx {pct}\%",
        }
    if atk_type in _CURE_ALWAYS_TYPES:
        return {
            "params": (), "symbolic": "unconditional - this byte is never read",
            "substituted": f"accuracy = {value}  (ignored)",
            "result": "Always cures the listed statuses (100%) - this byte is dead for Curative "
                     "Magic / the Demi-type effect",
            "note": "Damage_ComputeCurativeMagic @0x493280 calls checkDoubleStatusApply "
                    "unconditionally - HIT_ATTACK_ACCURACY (this byte) is never read in this "
                    "function. Confirmed dead for this Attack Type.",
            "latex": r"\text{always cures}", "latex_sub": r"\text{byte unused}",
        }
    if atk_type in _REVIVE_ALWAYS_TYPES:
        return {
            "params": (), "symbolic": "unconditional - this byte is never read",
            "substituted": f"accuracy = {value}  (ignored)",
            "result": "Always revives (100%) if the target has Death and it isn't sealed - this "
                     "byte is dead for Revive / Revive At Full HP",
            "note": "GetReviveHP @0x491940 clears Death unconditionally - HIT_ATTACK_ACCURACY "
                    "(this byte) is never read. EXCEPTION: reviving a Zombie-status target "
                    "instead deals unmissable magic damage via the Magic-dispatch path (MAG/SPR, "
                    "always hits) - not modelled here.",
            "latex": r"\text{always revives}", "latex_sub": r"\text{byte unused}",
        }
    if atk_type in _LV_UPDOWN_TYPES:
        # computeLvlUpDown @0x493650: fails if accuracy <= rand(0..255) - a plain byte-range
        # roll gating the WHOLE level-change action, no stat terms.
        pct = min(100.0, value / 256 * 100)
        return {
            "params": (), "symbolic": "succeeds if  accuracy > rand(0..255)  (action gate, no "
                        "stat terms)",
            "substituted": f"accuracy {value} > rand(0..255)",
            "result": f"≈ {pct:.1f}% chance the level change happens at all",
            "note": "computeLvlUpDown @0x493650. This isn't a 'status inflicted' roll - it gates "
                    "whether the LV Up/Down action succeeds at all (also fails outright if the "
                    "target is level-change-immune).",
            "latex": r"P(succeed) = \frac{accuracy}{256}", "latex_sub": rf"\approx {pct:.1f}\%",
        }
    if atk_type in _NO_ROLL_TYPES:
        return {
            "params": (), "symbolic": "not read - no status/action roll happens for this "
                        "Attack Type",
            "substituted": f"accuracy = {value}  (unused)",
            "result": "This byte has no effect for Fixed Damage-family Attack Types",
            "note": "Damage_ComputeFixedSpecial @0x4931c0 has no reference to HIT_ATTACK_ACCURACY "
                    "anywhere in the function - confirmed dead, not just unconfirmed.",
            "latex": r"\text{unused for this Attack Type}", "latex_sub": "",
        }
    if atk_type in _CARD_TYPES:
        # Battle_RollCardCommand @0x48fba0: capture uses the TARGET monster's HP ratio, not this
        # byte. card_percent (byte scale) = 256 - 255*curHP/maxHP; crit if >= rand byte.
        hpr = P["hp_ratio"]
        card_thr = 256 - _idiv(255 * hpr, 100)
        pct = min(100.0, max(0.0, card_thr / 256 * 100))
        return {
            "params": ("hp_ratio",),
            "symbolic": "capture chance = (256 − 255 × curHP/maxHP) / 256   (this status byte is "
                        "NOT read)",
            "substituted": f"(256 − 255 × {hpr}/100) / 256 = {card_thr}/256",
            "result": f"≈ {pct:.1f}% capture chance at {hpr}% target HP  —  this status-accuracy "
                      "byte is DEAD for Card",
            "note": "Battle_RollCardCommand @0x48fba0: whether the monster is carded depends on its "
                    "HP ratio (~0.4% at full HP → 100% near 0 HP), not this kernel byte. On success "
                    "a second rand byte < 16 (6.25%) yields the rare (mod) card, else the common "
                    "card; fails outright if the monster has no card. Carded → ejected, AP but no "
                    "EXP. (Here 'HP %' is the TARGET monster's, not the caster's.)",
            "latex": r"P(card) = \frac{256 - \lfloor 255\,curHP/maxHP\rfloor}{256}",
            "latex_sub": rf"\frac{{{card_thr}}}{{256}}\approx {pct:.1f}\%",
        }
    if atk_type in _DEVOUR_TYPES:
        return {
            "params": (),
            "symbolic": "success if  attackerHP ≥ targetHP  and  rand < (attackerHP − targetHP)/"
                        "attackerHP   (this status byte is NOT read)",
            "substituted": "uses both combatants' current HP, not this byte",
            "result": "This status-accuracy byte is DEAD for Devour — success is an HP-ratio roll",
            "note": "Battle_DamageGettingRelated Devour case @0x4926cf: needs the attacker's "
                    "current HP ≥ the target's, then succeeds with chance (attackerHP − targetHP)/"
                    "attackerHP. On success the Devour effect (heal + temporary stat boost + status) "
                    "is read from the Devour kernel section, not from this byte.",
            "latex": r"P(devour) = \frac{HP_{atk} - HP_{tgt}}{HP_{atk}}\ (HP_{atk}\geq HP_{tgt})",
            "latex_sub": r"\text{HP-ratio roll}",
        }
    if atk_type in _UTILITY_TYPES:
        names = {12: ("Scan", "reveals the monster's info", "@0x4925a6"),
                 23: ("Angelo Search", "finds a random battle item", "@0x49284b"),
                 24: ("Moogle Dance", "flags the target's junctioned GFs for HP recovery",
                      "@0x4928d3")}
        nm, what, addr = names[atk_type]
        return {
            "params": (),
            "symbolic": f"{nm} {what} — no accuracy roll, this byte is NOT read",
            "substituted": f"accuracy = {value}  (unused)",
            "result": f"This status-accuracy byte is DEAD for {nm} (a utility action, no roll)",
            "note": f"Battle_DamageGettingRelated {nm} case {addr}: {what}; it never reads "
                    "HIT_ATTACK_ACCURACY. Confirmed dead.",
            "latex": rf"\text{{{nm}: no roll}}", "latex_sub": "",
        }
    if atk_type in _NO_EFFECT_TYPES:
        which = ("None" if atk_type == 0 else
                 "Summon Item?" if atk_type == 14 else "an Unknown/unused")
        return {
            "params": (),
            "symbolic": f"{which} Attack Type — the dispatcher does no damage or status roll",
            "substituted": f"accuracy = {value}  (unused)",
            "result": f"This status-accuracy byte is DEAD ({which} Attack Type does nothing "
                      "with it)",
            "note": "Battle_DamageGettingRelated @0x4922b0: None (0) hits LABEL_46 (sets the "
                    "success flag, no damage/roll); Attack Types 14/30/31 have no case at all and "
                    "fall to the no-op default. HIT_ATTACK_ACCURACY is never read for any of them.",
            "latex": r"\text{no effect}", "latex_sub": "",
        }
    # Genuinely out-of-range values only (attack_type is a byte; 37-255 are undefined).
    return {
        "params": (),
        "symbolic": f"Attack Type {atk_type} is out of range (defined values are 0-36)",
        "substituted": f"attack_type = {atk_type}",
        "result": "Out-of-range Attack Type — no dispatcher case, no status mechanism",
        "note": "This entry's Attack Type byte is above the 37 defined values (0-36); the damage "
                "dispatcher (Battle_DamageGettingRelated @0x4922b0) has no case for it and treats "
                "it as the no-op default.",
        "latex": r"\text{out-of-range Attack Type}", "latex_sub": "",
    }


# Attack types whose damage path rolls the physical hit (Damage_DispatchByAttackType @0x4922b0):
# Physical (1), % Physical (7), Renzokuken finisher (9) and Kamikaze (18) call Damage_IsAutoHit +
# Damage_RollPhysicalHit; Everyone's Grudge (34) / Physical ignore VIT (36) roll the same formula
# inline in Damage_ComputePhysicalWithHitCritRoll @0x492e10.
_PHYS_HIT_ROLL_TYPES = {1, 7, 9, 18, 34, 36}
ATTACK_TYPE_GUNBLADE = 10
ATTACK_TYPE_LV_ATTACK = 26
ATTACK_TYPE_FIXED_DAMAGE = 27


def _hit_rate_not_rolled(att, hr):
    """Render dict for an attack type that never runs the physical hit roll."""
    name = ATTACK_TYPE_NAMES.get(att, f"type {att}")
    if att == ATTACK_TYPE_GUNBLADE:
        return {
            "params": (),
            "symbolic": "Gunblade attack: no hit roll (and no crit roll) → always hits",
            "substituted": f"Attack Type {att} ({name}) - hit rate {hr} is not read in battle",
            "result": "Always hits (100%) — only Petrify / Invincible / Defend on the target "
                      "nullify it",
            "note": "Damage_DispatchByAttackType @0x4922b0 sends type 10 straight to "
                    "Damage_ComputeGunblade @0x48f480, which has NO accuracy roll and NO crit roll "
                    "(the trigger replaces crits: ×1.5 on a perfect trigger). So for Squall's "
                    "gunblades this byte - like Darkness, target EVA and LUCK - never affects the "
                    "attack; it only shows as the Hit% stat in the Status menu "
                    "(Stat_ComputeCharaHit @0x4967c0).",
            "latex": r"\text{Gunblade: no hit roll} \Rightarrow 100\%",
            "latex_sub": rf"type\ {att} \Rightarrow \text{{always hits}}",
        }
    if att == ATTACK_TYPE_LV_ATTACK:
        return {
            "params": (),
            "symbolic": "LV? Attack: hits only if  targetLevel mod hitRate = 0",
            "substituted": f"divisor = {hr}",
            "result": (f"Hits targets whose level is a multiple of {hr}" if hr else
                       "Divisor 0 — the engine would divide by zero; do not use 0 here"),
            "note": "Damage_ComputeMagicAndGF @0x491ad0 (MAGIC_DAMAGE mode): for LV? Attack this "
                    "byte is the level divisor, not an accuracy percentage.",
            "latex": r"hit \Leftrightarrow level_{tgt} \mathrm{mod} hitRate = 0",
            "latex_sub": rf"level_{{tgt}} \mathrm{{mod}} {hr} = 0",
        }
    if att == ATTACK_TYPE_FIXED_DAMAGE:
        return {
            "params": (),
            "symbolic": "Fixed Damage: no hit roll;  damage = 100 × power − hitRate",
            "substituted": f"subtracts {hr} from the damage",
            "result": f"Always hits; this byte lowers the damage by {hr}",
            "note": "Damage_ComputeFixedSpecial @0x4931c0 (mode 11): damage = 100 × attack power "
                    "− this byte. It is a damage fine-tune here, not an accuracy.",
            "latex": r"dmg = 100\,P - hitRate",
            "latex_sub": rf"dmg = 100\,P - {hr}",
        }
    return {
        "params": (),
        "symbolic": "no physical hit roll for this Attack Type",
        "substituted": f"Attack Type {att} ({name})",
        "result": "This byte is not used as accuracy by this Attack Type",
        "note": "Only Physical (1), % Physical (7), Renzokuken finisher (9), Kamikaze (18), "
                "Everyone's Grudge (34) and Physical ignore VIT (36) roll the physical hit "
                "(Damage_DispatchByAttackType @0x4922b0). Magic/GF types never miss on accuracy; "
                "status landing uses the separate status accuracy byte.",
        "latex": r"\text{no hit roll}",
        "latex_sub": "",
    }


def _physical_hit_roll(hr, aluck, eva, tluck, params, who_note):
    # Damage_IsAutoHit @0x492b00 + Damage_RollPhysicalHit @0x492ba0: auto-hit if hit% == 255 (or
    # target Sleep/Stop); else (Darkness: hit% >>= 2) hit = hit% + atkLUCK/2 - tgtEVA - tgtLUCK,
    # clamped >= 0; lands if 255*hit/100 >= rand byte (and != 0).
    if hr >= 255:
        return {
            "params": params,
            "symbolic": "hit% = 255 → always hits (accuracy roll skipped)",
            "substituted": "hit% = 255",
            "result": "Always hits (100%) — only Petrify / Invincible / Defend on the target "
                      "nullify it",
            "note": "Damage_IsAutoHit @0x492b00: a hit% of exactly 255 (or a Sleeping/Stopped "
                    "target) skips the accuracy roll, so Darkness never applies. " + who_note,
            "latex": r"hit\% = 255 \Rightarrow 100\%",
            "latex_sub": r"255 \Rightarrow \text{always hits}",
        }
    hit = max(0, hr + aluck // 2 - eva - tluck)
    thr = _idiv(255 * hit, 100)
    pct = min(100.0, (thr + 1) / 256 * 100) if thr > 0 else 0.0
    return {
        "params": params,
        "symbolic": "hit = hit% + atkLUCK/2 − tgtEVA − tgtLUCK ;  lands if rand(0..255) ≤ 255×hit/100",
        "substituted": f"{hr} + {aluck}/2 − {eva} − {tluck} = {hit}   → threshold {thr}",
        "result": f"≈ {pct:.1f}% chance to land",
        "note": "Damage_RollPhysicalHit @0x492ba0. Darkness on the attacker quarters hit% first "
                "(hit% >> 2); a Sleeping/Stopped target is always hit. " + who_note,
        "latex": r"hit = hit\% + \frac{LUCK_{atk}}{2} - EVA_{tgt} - LUCK_{tgt}",
        "latex_sub": rf"{hr} + \frac{{{aluck}}}{{2}} - {eva} - {tluck} = {hit}",
    }


def _weapon_hit(value, P, entry):
    # A weapon is swung by a CHARACTER: HIT_ATTACK_HITPERCENT = charaStat[7] = the Hit% stat,
    # Stat_ComputeCharaHit @0x4967c0 = weapon.hitRate + HIT-junction bonus, capped 255; the 255
    # auto-hit test is on that FINAL stat. The target is a monster, whose LUCK is always 0
    # (setMonsterInfoFromDatInfoSection @0x48bbd0), so the target-LUCK term is a hard 0.
    hr = entry.get("hit_rate") if entry else None
    if hr is None:
        hr = value
    att = entry.get("attack_type") if entry else None
    if att is not None and att not in _PHYS_HIT_ROLL_TYPES:
        return _hit_rate_not_rolled(att, hr)
    bonus = P["hit_junction_bonus"]
    stat = min(255, hr + bonus)
    out = _physical_hit_roll(
        stat, P["attacker_luck"], P["target_eva"], 0,
        ("attacker_luck", "hit_junction_bonus", "target_eva"),
        "Target is a monster: monsters have no LUCK stat (always 0), so the target-LUCK term "
        f"drops out. hit% is the character's Hit% stat = weapon hit rate {hr} + junctioned HIT "
        f"bonus {bonus}, capped at 255 (Stat_ComputeCharaHit @0x4967c0) - reaching 255 through "
        "junctions also makes the character never miss.")
    if bonus:
        out["substituted"] = f"hit% = min(255, {hr} + {bonus}) = {stat};   " + out["substituted"]
    return out


def _monster_hit(value, P, entry):
    # Enemy attack (kernel §4): HIT_ATTACK_HITPERCENT = K_ENEMY_ATTACK.hitRate (Battle_applyDamage
    # @0x4902d9). Attacker is a monster -> attacker LUCK = 0; target is a character (EVA + LUCK).
    hr = entry.get("hit_rate") if entry else None
    if hr is None:
        hr = value
    att = entry.get("attack_type") if entry else None
    if att is not None and att not in _PHYS_HIT_ROLL_TYPES:
        return _hit_rate_not_rolled(att, hr)
    return _physical_hit_roll(
        hr, 0, P["target_eva"], P["target_luck"], ("target_eva", "target_luck"),
        "Attacker is a monster: monsters have no LUCK stat (always 0, "
        "setMonsterInfoFromDatInfoSection @0x48bbd0), so the attacker LUCK/2 bonus is 0. "
        "Target EVA and LUCK are the character's.")


FORMULAS = {
    "status_timer": ("Status duration", _status_timer),
    "dead_timer": ("Summon-check interval", _dead_timer),
    "atb_speed": ("ATB fill time", _atb_speed),
    "devour_hp": ("Devour HP amount", _devour_hp),
    "gf_compat": ("GF compatibility change", _gf_compat),
    "gf_hp": ("GF HP curve", _gf_hp),
    "gf_next_exp": ("GF next-level EXP", _gf_next_exp),
    "gf_damage": ("GF damage", _gf_damage),
    "magic_damage": ("Magic damage / healing", _magic_damage),
    "crisis": ("Crisis level contribution", _crisis),
    "char_exp": ("Character EXP curve", _char_exp),
    "physical_damage": ("Physical damage", _physical_damage),
    "weapon_crit": ("Critical-hit chance", _crit_chance),
    "monster_crit": ("Critical-hit chance (monster attacker)", _crit_chance_monster),
    "weapon_hit": ("Hit rate (character weapon)", _weapon_hit),
    "monster_hit": ("Hit rate (monster attacker)", _monster_hit),
    "monster_damage": ("Enemy attack damage", _monster_damage),
    "status_accuracy": ("Status inflict chance", _status_accuracy),
}
for _st in _CHAR_STAT_LABELS:
    FORMULAS[f"char_{_st}"] = (f"{_CHAR_STAT_LABELS[_st]} stat curve", _make_char_stat(_st))


def compute(formula_key, value, entry):
    """Return the render dict for ``formula_key`` at ``value`` (entry supplies sibling
    fields for multi-input formulas). Returns None for an unknown key."""
    spec = FORMULAS.get(formula_key)
    if not spec:
        return None
    params = dict(PARAM_VALUES)
    if PARAM_OVERRIDES is not None:
        params.update(PARAM_OVERRIDES(formula_key))
    out = spec[1](value, params, entry)
    out["title"] = spec[0]
    return out
