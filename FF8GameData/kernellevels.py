"""EXP -> level, the way the game computes it, from the curves of a kernel.bin.

Characters (Stat_ComputeLevelFromExp) and GFs (GetGFLevelFromExperience) share one curve with two
kernel.bin bytes each, a linear one A and a quadratic one B: level n+1 is reached at

    10 * A * n + n * n * B / 256 EXP    (integer division, n = 1..99)

and the level is the first n whose threshold the EXP does not reach, capped at 100.
  - GF: Junctionable GFs section, bytes 24 (A) and 25 (B) of the GF's 132-byte entry.
  - Character: Characters section, bytes 6 (A) and 7 (B) of the 36-byte entry of its savemap comId.
Vanilla characters have A = 100, B = 0: one level per 1000 EXP.
"""
from dataclasses import dataclass

MAX_LEVEL = 100
GF_SECTION_ID = 3
GF_ENTRY_SIZE = 132
GF_LINEAR_OFFSET = 24
GF_QUADRATIC_OFFSET = 25
CHARACTER_SECTION_ID = 7
CHARACTER_ENTRY_SIZE = 36
CHARACTER_LINEAR_OFFSET = 6
CHARACTER_QUADRATIC_OFFSET = 7


@dataclass(frozen=True)
class LevelCurve:
    linear: int
    quadratic: int

    def exp_to_leave(self, level):
        """The EXP at which `level` becomes level + 1 (0 for level 0)."""
        return 10 * self.linear * level + level * level * self.quadratic // 256

    def level_from_exp(self, exp):
        """(level, EXP past the start of that level), as the game reads it."""
        level = 1
        while level < MAX_LEVEL and exp >= self.exp_to_leave(level):
            level += 1
        return level, exp - self.exp_to_leave(level - 1)


def _curves(data, entry_size, linear_offset, quadratic_offset):
    return [LevelCurve(data[start + linear_offset], data[start + quadratic_offset])
            for start in range(0, len(data) - entry_size + 1, entry_size)]


def load_kernel(game_data, kernel_path):
    """A KernelManager holding kernel_path, to read several things out of one parse."""
    from ShumiTranslator.model.kernel.kernelmanager import KernelManager
    if not getattr(game_data, "kernel_data_json", None):
        game_data.load_kernel_data()
    kernel_manager = KernelManager(game_data)
    kernel_manager.load_file(str(kernel_path))
    return kernel_manager


def read_level_curves(game_data, kernel_path):
    """{"gf": [LevelCurve by GF id], "character": [LevelCurve by comId]} of a kernel.bin."""
    return level_curves(load_kernel(game_data, kernel_path))


def level_curves(kernel_manager):
    """read_level_curves of an already loaded KernelManager."""
    by_id = {section.id: section for section in kernel_manager.section_list if section is not None}
    return {"gf": _curves(by_id[GF_SECTION_ID].get_data_hex(), GF_ENTRY_SIZE,
                          GF_LINEAR_OFFSET, GF_QUADRATIC_OFFSET),
            "character": _curves(by_id[CHARACTER_SECTION_ID].get_data_hex(), CHARACTER_ENTRY_SIZE,
                                 CHARACTER_LINEAR_OFFSET, CHARACTER_QUADRATIC_OFFSET)}
