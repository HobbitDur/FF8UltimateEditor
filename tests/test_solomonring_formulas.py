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
