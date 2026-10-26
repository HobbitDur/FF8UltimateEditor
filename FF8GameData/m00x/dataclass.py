from dataclasses import dataclass


@dataclass
class TypeId:
    ITEM: int = 0
    SPELL: int = 1
    CARD: int = 2


@dataclass
class Entry:
    text_offset: int = 0
    text_offset_size = 2
    amount_received: int = 0  # u16 at 0x02 (the refine and its menu window both read 2 bytes)
    # Byte 0x04: the refine needs a GF that learned the refine ability at this level or higher
    # (Menu_Prog19_RefineMenu_Init, max level -> task+0x47, compared `>=` in the refine update).
    # The PC exe forces that level to 100, so it is ignored unless the Customizer's
    # Archeology/RefineGFLevel hext restores it. Vanilla: 1, 100 for Curse Spike -> Dark Matter
    # and Shaman Stone -> Hero-trial.
    required_gf_level: int = 0
    element_in_id: int = 0
    amount_required: int = 0
    element_out_id: int = 0
    ENTRY_SIZE: int = 8  # Nb_element
    text = "" # Str or list to be given to bytearray


class m00XTable:
    """One refine table of mngrp.bin (m000 to m004): what its entries take and give.

    Which entries each refine ability offers is NOT here: kernel.bin's menu abilities hold a first
    and last entry each (FF8GameData/menu/mngrp/m00x/refineabilities.py)."""

    def __init__(self, name, input_id, output_id, mngrp_bin_id, mngrp_msg_id):
        self.name = name
        self.input_id = input_id
        self.output_id = output_id
        self.mngrp_bin_id = mngrp_bin_id
        self.mngrp_msg_id = mngrp_msg_id


def m000bin():
    return m00XTable("m000", TypeId.ITEM, TypeId.SPELL, 106, 111)


def m001bin():
    return m00XTable("m001", TypeId.ITEM, TypeId.ITEM, 107, 112)


def m002bin():
    return m00XTable("m002", TypeId.SPELL, TypeId.SPELL, 108, 113)


def m003bin():
    return m00XTable("m003", TypeId.ITEM, TypeId.ITEM, 109, 114)


def m004bin():
    return m00XTable("m004", TypeId.CARD, TypeId.ITEM, 110, 115)
