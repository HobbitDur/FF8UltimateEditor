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
