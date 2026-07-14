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
    "elem_defense":   ("Target elem def", 800, 0, 900,
                       "Target elemental defence: 800 = neutral (x1.0 damage), 900 = immune (x0), "
                       "0 = x9 weakness. Doomtrain default 800."),
    "target_hp":      ("Target current HP", 1000, 1, 99999999,
                       "Target's current HP - used by Demi / %-HP attacks. Doomtrain default 1000."),
    "target_maxhp":   ("Target max HP", 1000, 1, 99999999,
                       "Target's max HP - used by Devour and Angelo Recover (value/16 x maxHP)."),
    "battle_speed":   ("Battle speed", 3, 0, 255,
                       "FF8 config Battle Speed (SG_SETTING.battleSpeed). Higher = slower ATB and "
                       "longer status timers. Timer ticks = 4 x (battleSpeed+1) x value "
                       "(setupStatus2Timer). Default 3 matches the tool's ~16/15 s hint."),
    "dead_allies":    ("KO'd allies", 0, 0, 2,
                       "Number of KO'd party members - raises the crisis level (Limit Break "
                       "availability) faster."),
    "hp_ratio":       ("HP % (cur/max)", 25, 0, 100,
                       "Character's current HP as a percent of max. Lower HP raises the crisis "
                       "level; this is the dominant term in the crisis formula."),
    "crisis_hp_mult": ("Crisis HP mult", 250, 0, 255,
                       "Per-character crisisLevelHPMultiplier (kernel Characters section). Retail: "
                       "250 for everyone except Seifer (100). Weights the missing-HP term."),
}

# Live, user-editable values (start at defaults). Edited in the formula popups.
PARAM_VALUES = {k: v[1] for k, v in PARAM_DEFS.items()}


def reset_params():
    for k, v in PARAM_DEFS.items():
        PARAM_VALUES[k] = v[1]


def _idiv(a, b):
    """C-style integer division truncating toward zero (matches the game / doomtrain)."""
    if b == 0:
        return 0
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


# --- formula computations ---------------------------------------------------
# Each returns a dict: symbolic (str), substituted (str), result (str), note (str|None),
# params (tuple of PARAM_DEFS keys to expose editors for).

def _status_timer(value, P, entry):
    bs = P["battle_speed"]
    ticks = 4 * (bs + 1) * value
    return {
        "params": ("battle_speed",),
        "symbolic": "duration = 4 x (battleSpeed + 1) x value   ticks   (~15 ticks/s)",
        "substituted": f"4 x ({bs} + 1) x {value} = {ticks} ticks",
        "result": f"{ticks} ticks  ≈  {ticks / 15:.1f} s",
        "note": "Battle countdown loaded by setupStatus2Timer. Real speed varies with the "
                "in-game Battle Speed config.",
        "latex": r"ticks = 4\,(battleSpeed + 1)\,value",
        "latex_sub": rf"4\cdot({bs}+1)\cdot{value}={ticks}\ \text{{ticks}}",
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
        change = "is unchanged"
    return {
        "params": (),
        "symbolic": "on each cast/summon:  storedCompatibility += (value − 100)   "
                    "[clamped 1000..6000]",
        "substituted": f"delta = {value} − 100 = {delta:+d}",
        "result": f"Compatibility with this GF {change} each time it's used  (100 = no change).",
        "note": "The stored compatibility (1000-6000, starts 1000) sets how fast this GF's summon "
                "gauge fills — higher = the GF arrives sooner. This kernel byte is only the "
                "per-cast adjustment applied in BattleAction_ExecuteCommand; it is NOT itself a "
                "gauge-fill rate.",
        "latex": r"\Delta\,compat = value - 100 \quad [1000..6000]",
        "latex_sub": rf"\Delta\,compat = {value} - 100 = {delta:+d}",
    }


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
def _magic_damage(value, P, entry):
    p = value                       # spell power
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
        elem = P["elem_defense"]
        t1 = _idiv((265 - spr_eff) * (p + P["caster_mag"]), 4)
        t2 = _idiv(p * t1, 256)

        def roll(r):
            return _idiv(_idiv(r * t2, 256) * (900 - elem), 100) * hit

        avg, lo, hi = roll(256), roll(240), roll(272)
        return _msg(
            "t1=(265−SPR)×(P+MAG)/4   t2=P×t1/256   dmg=(rand[240..272]/256)×t2×(900−elemDef)/100"
            + (" [SPR forced 0]" if ignore else ""),
            f"t1=(265−{spr_eff})×({p}+{P['caster_mag']})/4={t1}   t2={p}×{t1}/256={t2}   "
            f"×(900−{elem})/100{hits_txt}",
            f"≈ {avg} damage   (random spread {lo}–{hi})",
            (f"This entry's attack type is None (unused/empty slot); showing the standard Magic "
             f"Attack formula for reference. " if att == 0 else f"Attack type '{name}'. ")
            + "Real formula (Damage_ComputeMagicAndGF), incl. the random roll and elemental "
            "(900−elemDef)/100. Not modelled: monster casters halve, Shell halves, Defend halves, "
            "weakness caps ×2." + (" LV? Attack also only hits on matching level." if att == 26 else ""),
            ("caster_mag", "target_spr", "elem_defense"),
            latex=(r"dmg=\left\lfloor\frac{rand}{256}\cdot\frac{P\,(265-SPR)(P+MAG)}{4\cdot256}"
                   r"\right\rfloor\cdot\frac{900-elemDef}{100}"),
            latex_sub=(rf"\frac{{240..272}}{{256}}\cdot"
                       rf"\frac{{{p}\,(265-{spr_eff})({p}+{P['caster_mag']})}}{{1024}}\cdot"
                       rf"\frac{{900-{elem}}}{{100}}" + (rf"\cdot{hit}" if hit > 1 else "")))

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


FORMULAS = {
    "status_timer": ("Status duration", _status_timer),
    "dead_timer": ("Summon-check interval", _dead_timer),
    "devour_hp": ("Devour HP amount", _devour_hp),
    "gf_compat": ("GF compatibility change", _gf_compat),
    "magic_damage": ("Magic damage / healing", _magic_damage),
    "crisis": ("Crisis level contribution", _crisis),
}


def compute(formula_key, value, entry):
    """Return the render dict for ``formula_key`` at ``value`` (entry supplies sibling
    fields for multi-input formulas). Returns None for an unknown key."""
    spec = FORMULAS.get(formula_key)
    if not spec:
        return None
    out = spec[1](value, PARAM_VALUES, entry)
    out["title"] = spec[0]
    return out
