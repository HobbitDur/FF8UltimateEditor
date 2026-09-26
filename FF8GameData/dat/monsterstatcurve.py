"""A monster's stats at a level, from the four bytes of each .dat stat curve (section 7,
info_stat), exactly as the game computes them.

Stat_ComputeMonsterStatCurve @0x48c3f0 (STR, VIT, MAG, SPR, SPD, EVA) and
Stat_ComputeMonsterMaxHP @0x48c500, with A, B, C, D the four curve bytes and L the level:

- STR, MAG:            (C + L*A/10 + L/B - (L*L/D)/2) / 4
- VIT, SPR, SPD, EVA:  C + L*A + L/B - L/D
- HP:                  A*L*L/20 + L*(A + 100*C) + 10*(B + 100*D)

Every division truncates toward zero. CapTo255 @0x495930 only caps the top, and the result is
stored in a byte: a negative value wraps (-3 is 253), which a steep STR/MAG curve at a high
level reaches. B and D are divided by unchecked, so a 0 there would crash the game; it counts
as 0 here. The AI stat multiplier (Stat_ComputeMonsterStats @0x48c1c0, 10 = x1) is not applied.
"""


def _div(a, b):
    """C integer division: truncates toward zero; a 0 divisor gives 0 instead of crashing."""
    if b == 0:
        return 0
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def to_stat_byte(value):
    """CapTo255, then stored in a byte: capped at 255, and a negative value wraps."""
    return min(value, 255) & 0xFF


def str_mag_terms(curve, level):
    """The four terms of STR / MAG before the /4: L*A/10, L/B, C and -(L*L/D)/2."""
    a, b, c, d = curve
    return [_div(level * a, 10), _div(level, b), c, -_div(_div(level * level, d), 2)]


def linear_terms(curve, level):
    """The four terms of VIT / SPR / SPD / EVA: L*A, L/B, C and -L/D."""
    a, b, c, d = curve
    return [level * a, _div(level, b), c, -_div(level, d)]


def monster_stat(stat, curve, level):
    """STR, VIT, MAG, SPR, SPD or EVA ('str', 'vit'...) at a level."""
    if stat in ('str', 'mag'):
        return to_stat_byte(_div(sum(str_mag_terms(curve, level)), 4))
    return to_stat_byte(sum(linear_terms(curve, level)))


def hp_terms(curve, level):
    """The four terms of HP: A*L*L/20 + A*L, 10*B, 100*C*L and 1000*D."""
    a, b, c, d = curve
    return [_div(a * level * level, 20) + a * level, 10 * b, 100 * c * level, 1000 * d]


def monster_hp(curve, level):
    return sum(hp_terms(curve, level))
