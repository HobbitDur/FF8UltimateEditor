"""
Tests for the IfritStat stat-curve formula (Ifrit/IfritStat/ifritstatwidget.py).

StatCurvePlot._stat_value reproduces the FF8 per-level stat computation from the
4 curve bytes of section 7. It is a pure static method, so it is exercised
directly without building the Qt widget (no QApplication needed).
"""
import pytest

from Ifrit.IfritStat.ifritstatwidget import StatCurvePlot

stat_value = StatCurvePlot._stat_value


class TestHp:
    def test_base_growth(self):
        # floor(b0 * (lvl^2/20 + lvl)) + 10*b1 + b2*100*lvl + 1000*b3
        assert stat_value('hp', [1, 0, 0, 0], 10) == 15
        assert stat_value('hp', [2, 3, 1, 4], 50) == 9380

    def test_level_one(self):
        assert stat_value('hp', [1, 0, 0, 0], 1) == 1  # floor(1*(1/20+1)) = 1


class TestStrMag:
    def test_str_linear_term(self):
        assert stat_value('str', [40, 0, 0, 0], 40) == 40  # floor(40*40/40)

    def test_str_and_mag_share_formula(self):
        b = [30, 8, 12, 16]
        assert stat_value('str', b, 60) == stat_value('mag', b, 60)

    def test_zero_divisor_bytes_do_not_raise(self):
        # b1 and b3 are divisors; 0 must be guarded, not crash
        assert stat_value('str', [40, 0, 5, 0], 40) == 40 + (5 // 4)

    def test_the_level_squared_term_is_subtracted(self):
        # Stat_ComputeMonsterStatCurve: (C + L*A/10 + L/B - (L*L/D)/2) / 4
        # L=100: (4 + 300 + 12 - 10000/16/2) / 4 = (316 - 312) / 4 = 1
        assert stat_value('str', [30, 8, 4, 16], 100) == 1
        assert stat_value('str', [30, 8, 4, 16], 20) == (4 + 60 + 2 - 400 // 16 // 2) // 4

    def test_a_negative_result_wraps_into_a_byte(self):
        # The game only caps the top, then stores the stat in a byte: -1225 becomes 55
        assert stat_value('mag', [10, 255, 0, 1], 100) == (-1225) & 0xFF


class TestOtherStats:
    def test_vit_formula(self):
        # lvl*b0 + floor(lvl/b1) + b2 - floor(lvl/b3)
        assert stat_value('vit', [2, 0, 5, 0], 10) == 25
        assert stat_value('vit', [2, 5, 5, 10], 50) == 110

    @pytest.mark.parametrize("name", ["vit", "spr", "spd", "eva"])
    def test_all_share_the_same_formula(self, name):
        b = [3, 7, 4, 9]
        expected = stat_value('vit', b, 33)
        assert stat_value(name, b, 33) == expected

    def test_zero_divisor_bytes_do_not_raise(self):
        assert stat_value('spd', [3, 0, 4, 0], 20) == 20 * 3 + 4


class TestMonotonicity:
    @pytest.mark.parametrize("name,bytes_", [
        ('hp', [5, 2, 1, 0]),
        ('str', [30, 8, 4, 255]),
        ('vit', [2, 10, 3, 0]),
    ])
    def test_stat_is_non_decreasing_with_level(self, name, bytes_):
        values = [stat_value(name, bytes_, level) for level in range(1, 101)]
        assert all(b >= a for a, b in zip(values, values[1:]))
