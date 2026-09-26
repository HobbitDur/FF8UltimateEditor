"""SolomonRing's f(x) formulas: every one renders as math, and the status resistance input uses the
Ifrit Stat tab's scale.

matplotlib's mathtext is a LaTeX subset: \\tfrac, \\iff, \\bmod, \\ge are not in it, and a formula
using one silently falls back to plain text. Rendering all of them catches that."""
import pytest
from PyQt6.QtWidgets import QApplication

from SolomonRing import formula_latex, formula_specs

ATTACK_TYPED = ("magic_damage", "monster_damage", "status_accuracy", "weapon_hit", "monster_hit")


class _Entry(dict):
    """Any field an entry is asked for exists and holds 10, unless set."""

    def has_field(self, _name):
        return True

    def get(self, key, default=None):
        return dict.get(self, key, 10)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.mark.skipif(not formula_latex.AVAILABLE, reason="matplotlib not installed")
def test_every_formula_renders_as_math(qapp):
    failed = []
    for key in formula_specs.FORMULAS:
        for attack_type in (range(37) if key in ATTACK_TYPED else [None]):
            entry = _Entry() if attack_type is None else _Entry(attack_type=attack_type)
            out = formula_specs.compute(key, 20, entry)
            for field in ("latex", "latex_sub"):
                if out.get(field) and formula_latex.render(out[field], "#000000") is None:
                    failed.append((key, attack_type, field, out[field]))
    assert failed == []


def test_status_resistance_is_the_ifrit_percentage():
    """0 = neutral (stored 100), 100+ = immune (stored 200+), as the Ifrit Stat tab shows it."""
    label, default, low, high, _help = formula_specs.PARAM_DEFS["target_resistance"]
    assert (default, low, high) == (0, -100, 155) and "%" in label
    saved = formula_specs.PARAM_VALUES["target_resistance"]
    try:
        formula_specs.PARAM_VALUES["target_resistance"] = 0
        # accuracy 150 + STR 128/4 - VIT 64/4 - (0 + 100) = 66
        assert "= 66%" in formula_specs.compute("status_accuracy", 150, _Entry(attack_type=1))["substituted"]
        formula_specs.PARAM_VALUES["target_resistance"] = 100
        assert "immune" in formula_specs.compute("status_accuracy", 150, _Entry(attack_type=1))["result"]
    finally:
        formula_specs.PARAM_VALUES["target_resistance"] = saved


def test_element_input_is_the_ifrit_damage_percentage():
    """100 = normal damage, 200 = double, 0 = none, negative = absorbs - Ifrit Stat's scale; the
    engine multiplies magic damage by (900 - elemDef)/100 where elemDef = 900 - this %."""
    label, default, low, high, _help = formula_specs.PARAM_DEFS["elem_defense"]
    assert (default, low, high) == (100, -1650, 900) and "%" in label
    saved = formula_specs.PARAM_VALUES["elem_defense"]
    try:
        results = {}
        for pct in (100, 200, 0, -100):
            formula_specs.PARAM_VALUES["elem_defense"] = pct
            out = formula_specs.compute("magic_damage", 20, _Entry(attack_type=2, spell_power=20, hit_count=1))
            results[pct] = int(out["result"].split("≈ ")[1].split(" ")[0])
        assert results[200] == 2 * results[100] or abs(results[200] - 2 * results[100]) <= 1
        assert results[0] == 0 and results[-100] == -results[100]
    finally:
        formula_specs.PARAM_VALUES["elem_defense"] = saved
        assert "weakness caps" not in formula_specs.compute(
            "magic_damage", 20, _Entry(attack_type=2))["note"]


def test_ifrit_element_range_covers_every_byte():
    from FF8GameData.monsterdata import AIData
    # 900 - 10 * byte, byte 0..255
    assert (AIData.ELEM_DEF_MAX_VAL, AIData.ELEM_DEF_MIN_VAL) == (900 - 10 * 0, 900 - 10 * 255)


# --- Cronos damage formula and battle setup ----------------------------------
from SolomonRing import battle_setup  # noqa: E402


@pytest.fixture
def cronos():
    formula_specs.PARAM_VALUES["cronos_formula"] = 1
    yield
    formula_specs.PARAM_VALUES["cronos_formula"] = 0


@pytest.mark.skipif(not formula_latex.AVAILABLE, reason="matplotlib not installed")
def test_every_formula_renders_as_math_with_the_cronos_formula(qapp, cronos):
    failed = []
    for key in formula_specs.FORMULAS:
        for attack_type in (range(37) if key in ATTACK_TYPED else [None]):
            entry = _Entry() if attack_type is None else _Entry(attack_type=attack_type)
            out = formula_specs.compute(key, 20, entry)
            for field in ("latex", "latex_sub"):
                if out.get(field) and formula_latex.render(out[field], "#000000") is None:
                    failed.append((key, attack_type, field, out[field]))
    assert failed == []


def _average(out):
    return int(out["result"].split("≈ ")[1].split()[0])


def test_cronos_magic_uses_320_and_twice_the_mag(cronos):
    """DamageFormulaUpdate: 265 -> 320 and Power+MAG -> MAG+MAG, the power still multiplying."""
    params = {"caster_mag": 100, "target_spr": 50, "elem_defense": 100}
    saved = {k: formula_specs.PARAM_VALUES[k] for k in params}
    formula_specs.PARAM_VALUES.update(params)
    try:
        spell = _Entry(attack_type=2, spell_power=20, hit_count=1)
        # t1 = (320-50) * 200 / 4 = 13500, t2 = 20 * 13500 / 256 = 1054
        assert _average(formula_specs.compute("magic_damage", 20, spell)) == 1054
        formula_specs.PARAM_VALUES["cronos_formula"] = 0
        # t1 = (265-50) * 120 / 4 = 6450, t2 = 20 * 6450 / 256 = 503
        assert _average(formula_specs.compute("magic_damage", 20, spell)) == 503
    finally:
        formula_specs.PARAM_VALUES.update(saved)


def test_cronos_does_not_halve_a_monster_caster(cronos):
    attack = _Entry(attack_type=2, attack_power=20)
    params = {"monster_mag": 100, "target_spr": 50, "elem_defense": 100}
    saved = {k: formula_specs.PARAM_VALUES[k] for k in params}
    formula_specs.PARAM_VALUES.update(params)
    try:
        assert _average(formula_specs.compute("monster_damage", 20, attack)) == 1054
        formula_specs.PARAM_VALUES["cronos_formula"] = 0
        assert _average(formula_specs.compute("monster_damage", 20, attack)) == 251   # 503 / 2
    finally:
        formula_specs.PARAM_VALUES.update(saved)


def test_cronos_changes_only_the_gunblade(cronos):
    params = {"attacker_str": 100, "target_vit": 50}
    saved = {k: formula_specs.PARAM_VALUES[k] for k in params}
    formula_specs.PARAM_VALUES.update(params)
    try:
        gunblade = _Entry(attack_type=formula_specs.ATTACK_TYPE_GUNBLADE, attack_power=20, str_bonus=0)
        other = _Entry(attack_type=1, attack_power=20, str_bonus=0)
        # (320-50) * (100 + 625) / 256 = 764, * 20 / 16 = 955
        assert _average(formula_specs.compute("physical_damage", 20, gunblade)) == 955
        # (265-50) * 725 / 256 = 608, * 20 / 16 = 760
        assert _average(formula_specs.compute("physical_damage", 20, other)) == 760
    finally:
        formula_specs.PARAM_VALUES.update(saved)


def _c_div(a, b):
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def test_monster_stats_follow_the_game_curve():
    """Stat_ComputeMonsterStatCurve @0x48c3f0, instruction by instruction: STR/MAG subtract the
    quadratic term, VIT/SPR/SPD/EVA are linear, and a negative result wraps into a byte."""
    for curve in ([40, 5, 20, 30], [12, 3, 200, 7], [255, 1, 255, 1]):
        a, b, c, d = curve
        for level in (1, 30, 60, 100):
            quad = _c_div(level * level, d)
            # CapTo255 caps the top only; the byte store wraps a negative value
            want = min(255, _c_div(_c_div(level * a, 10) + _c_div(level, b) - (quad - (quad >> 31)) // 2 + c, 4)) & 0xFF
            assert battle_setup.monster_stat("str", curve, level) == want
            assert battle_setup.monster_stat("vit", curve, level) == min(255, c + level * a + level // b - level // d) & 0xFF
    assert battle_setup.monster_hp([10, 20, 1, 2], 30) == 10 * 900 // 20 + 30 * 110 + 10 * 220


def test_the_setup_fills_each_side_of_the_formula():
    setup = battle_setup.BattleSetup()
    setup.monsters_provider = lambda: [{"name": "Grat", "curves": {s: [10, 2, 5, 4] for s in
                                                                  ("hp", "str", "vit", "mag", "spr", "spd", "eva")}}]
    setup.monster = 0
    setup.monster_level = 20
    values, sources = setup.overrides("magic_damage")
    assert values["target_spr"] == battle_setup.monster_stat("spr", [10, 2, 5, 4], 20)
    assert sources["target_spr"] == "Grat" and "caster_mag" not in values   # no character picked
    values, _ = setup.overrides("monster_damage")
    assert values["monster_mag"] == battle_setup.monster_stat("mag", [10, 2, 5, 4], 20)
    assert "target_spr" not in values                                      # the target is the character
    assert setup.overrides("gf_hp") == ({}, {})
