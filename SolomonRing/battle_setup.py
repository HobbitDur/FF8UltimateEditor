"""Battle setup for the damage formula popups: a real character and a real monster instead of
typed stats.

A character comes from the loaded kernel.bin (its stat curves, section Characters) at a level,
plus the bonuses the curves do not cover - junctioned magic, weapon, abilities - typed per stat.
A monster comes from the monsters opened in Ifrit (their .dat stat curves) at a level. Their
stats then replace the typed assumptions of the formula being shown, on the side each one is
on: the character attacks in a spell's / weapon's / GF's formula, the monster in an enemy
attack's.
"""
from . import formula_specs as fs

# Formulas where the character attacks the monster, and where the monster attacks.
CHARACTER_ATTACKS = {"magic_damage", "physical_damage", "weapon_hit", "weapon_crit", "gf_damage"}
MONSTER_ATTACKS = {"monster_damage", "monster_hit", "monster_crit"}
SETUP_FORMULAS = CHARACTER_ATTACKS | MONSTER_ATTACKS

BONUS_STATS = ("str", "vit", "mag", "spr")


def _idiv(a, b):
    return fs._idiv(a, b)


def _cap(value):
    return max(0, min(255, value))


def monster_stat(name, curve, level):
    """A monster's stat at a level, as Stat_ComputeMonsterStatCurve @0x48c3f0 computes it from
    the four bytes A, B, C, D of its .dat curve (before the AI stat multiplier, 10 = x1).

    STR and MAG: (C + L*A/10 + L/B - (L*L/D)/2) / 4. VIT, SPR, SPD, EVA: C + L*A + L/B - L/D.
    Every division truncates and the result is capped at 255. The game divides by B and D
    unchecked, so a 0 there would crash it; it counts as 0 here."""
    a, b, c, d = curve
    if name in ("str", "mag"):
        return _cap(_idiv(c + _idiv(level * a, 10) + _idiv(level, b) - _idiv(_idiv(level * level, d), 2), 4))
    return _cap(c + level * a + _idiv(level, b) - _idiv(level, d))


def monster_hp(curve, level):
    """Stat_ComputeMonsterMaxHP @0x48c500: HP1*L*L/20 + L*(HP1 + 100*HP3) + 10*(HP2 + 100*HP4)."""
    hp1, hp2, hp3, hp4 = curve
    return _idiv(hp1 * level * level, 20) + level * (hp1 + 100 * hp3) + 10 * (hp2 + 100 * hp4)


class BattleSetup:
    """The chosen character and monster, shared by every formula popup."""

    def __init__(self):
        # () -> [(name, KernelEntry of the Characters section)]
        self.characters_provider = None
        # () -> [{"name": str, "curves": {"hp"|"str"|...: [4 bytes]}}]
        self.monsters_provider = None
        self.character = None      # index into characters(), None: typed stats
        self.character_level = 30
        self.bonus = {stat: 0 for stat in BONUS_STATS}
        self.monster = None        # index into monsters(), None: typed stats
        self.monster_level = 30

    def characters(self):
        return self.characters_provider() if self.characters_provider else []

    def monsters(self):
        return self.monsters_provider() if self.monsters_provider else []

    def character_stats(self):
        """{stat: value} of the chosen character with its bonuses, or None."""
        characters = self.characters()
        if self.character is None or self.character >= len(characters):
            return None
        name, entry = characters[self.character]
        level = {"char_level": self.character_level}
        stats = {"name": name, "level": self.character_level}
        for stat in ("hp", "str", "vit", "mag", "spr", "spd", "luck"):
            base = fs.FORMULAS[f"char_{stat}"][1](0, level, entry)["value"]
            stats[stat] = _cap(base + self.bonus[stat]) if stat in self.bonus else base
        return stats

    def monster_stats(self):
        """{stat: value} of the chosen monster, or None."""
        monsters = self.monsters()
        if self.monster is None or self.monster >= len(monsters):
            return None
        monster = monsters[self.monster]
        curves, level = monster["curves"], self.monster_level
        stats = {"name": monster["name"], "level": level, "hp": monster_hp(curves["hp"], level)}
        for stat in ("str", "vit", "mag", "spr", "spd", "eva"):
            stats[stat] = monster_stat(stat, curves[stat], level)
        return stats

    def overrides(self, formula_key):
        """The params the chosen character and monster supply for that formula, and who
        supplies each: ({param: value}, {param: name})."""
        values, sources = {}, {}
        if formula_key not in SETUP_FORMULAS:
            return values, sources
        char, mon = self.character_stats(), self.monster_stats()

        def put(param, stats, stat):
            if stats is not None:
                values[param] = stats[stat]
                sources[param] = stats["name"]

        if formula_key in CHARACTER_ATTACKS:
            put("attacker_str", char, "str")
            put("caster_mag", char, "mag")
            put("attacker_luck", char, "luck")
            put("target_vit", mon, "vit")
            put("target_spr", mon, "spr")
            put("target_eva", mon, "eva")
            put("target_hp", mon, "hp")
            put("target_maxhp", mon, "hp")
        else:
            put("monster_str", mon, "str")
            put("monster_mag", mon, "mag")
            put("caster_mag", mon, "mag")
            put("attacker_maxhp", mon, "hp")
            put("target_vit", char, "vit")
            put("target_spr", char, "spr")
            put("target_luck", char, "luck")
            put("target_hp", char, "hp")
            put("target_maxhp", char, "hp")
        return values, sources


SETUP = BattleSetup()
fs.PARAM_OVERRIDES = lambda formula_key: SETUP.overrides(formula_key)[0]
