"""The learnable-ability list of each GF in a kernel.bin, which is what init.out's / a save's AP slots
count toward.

BuildGFAbilityList: AP slot k of a GF (SG_GFData.APs[k]) is the AP earned toward entry k of its
Junctionable GFs entry's ability list (21 entries of 4 bytes from byte 27):
  byte 1  unlock: <= 100 = the GF level it is learnable from; 101-121 = learnable once the ability of
          slot (value - 101) is learned
  byte 3  the ability (unified id: kernel sections 12-18 one after another, 0 = none)
The AP the ability costs is byte 4 of its own entry in those sections.
"""
from dataclasses import dataclass

from FF8GameData.kernellevels import GF_ENTRY_SIZE, GF_SECTION_ID

ABILITY_LIST_OFFSET = 27
ABILITY_LIST_ENTRY_SIZE = 4
ABILITY_LIST_COUNT = 21
UNLOCK_BYTE = 1
ABILITY_BYTE = 3
ABILITY_SECTION_IDS = (12, 13, 14, 15, 16, 17, 18)
ABILITY_ENTRY_SIZE = 8
ABILITY_AP_OFFSET = 4
UNLOCK_MAX_LEVEL = 100
UNLOCK_SLOT_BASE = 101


@dataclass(frozen=True)
class GFAbilitySlot:
    ability: int  # unified ability id, 0 = none
    unlock: int   # raw unlock byte

    @property
    def unlock_level(self):
        return self.unlock if self.unlock <= UNLOCK_MAX_LEVEL else None

    @property
    def unlock_after_slot(self):
        """The 0-based slot whose ability must be learned first, or None."""
        index = self.unlock - UNLOCK_SLOT_BASE
        return index if 0 <= index < ABILITY_LIST_COUNT else None


def gf_ability_slots(kernel_manager):
    """{"slots": [[GFAbilitySlot] * 21 by GF id], "ap": [AP cost by unified ability id]} of a loaded
    KernelManager."""
    by_id = {section.id: section for section in kernel_manager.section_list if section is not None}
    gf_data = by_id[GF_SECTION_ID].get_data_hex()
    slots = []
    for start in range(0, len(gf_data) - GF_ENTRY_SIZE + 1, GF_ENTRY_SIZE):
        entries = []
        for index in range(ABILITY_LIST_COUNT):
            entry = start + ABILITY_LIST_OFFSET + index * ABILITY_LIST_ENTRY_SIZE
            entries.append(GFAbilitySlot(gf_data[entry + ABILITY_BYTE], gf_data[entry + UNLOCK_BYTE]))
        slots.append(entries)
    ap = []
    for section_id in ABILITY_SECTION_IDS:
        data = by_id[section_id].get_data_hex()
        ap.extend(data[start + ABILITY_AP_OFFSET] for start in range(0, len(data) - ABILITY_ENTRY_SIZE + 1,
                                                                      ABILITY_ENTRY_SIZE))
    return {"slots": slots, "ap": ap}
