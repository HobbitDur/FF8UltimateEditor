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
    amount_received: int = 0
    unk: int = 0
    element_in_id: int = 0
    amount_required: int = 0
    element_out_id: int = 0
    ENTRY_SIZE: int = 8  # Nb_element
    text = "" # Str or list to be given to bytearray


@dataclass
class Data:
    name: str
    offset: int
    description: str
    nb_entries: int
    entries: list


@dataclass
class m000bin:
    def __init__(self):
        self.name = "m000"
        self.t_mag_rf = Data(name='t_mag_rf', offset=0x0, description='Item to Thunder/Wind Magic', nb_entries=7,
                             entries=[Entry() for _ in range(7)])
        self.i_mag_rf = Data(name='i_mag_rf', offset=0x38, description='Item to Ice/Water Magic', nb_entries=7,
                             entries=[Entry() for _ in range(7)])
        self.f_mag_rf = Data(name='f_mag_rf', offset=0x70, description='Item to Fire/Flare Magic', nb_entries=10,
                             entries=[Entry() for _ in range(10)])
        self.l_mag_rf = Data(name='l_mag_rf', offset=0xC0, description='Item to Life Magic', nb_entries=21,
                             entries=[Entry() for _ in range(21)])
        self.time_mag_rf = Data(name='time_mag_rf', offset=0x168, description='Item to Time Magic', nb_entries=14,
                                entries=[Entry() for _ in range(14)])
        self.st_mag_rf = Data(name='st_mag_rf', offset=0x1D8, description='Item to Status Magic', nb_entries=17,
                              entries=[Entry() for _ in range(17)])
        self.supt_mag_rf = Data(name='supt_mag_rf', offset=0x260, description='Item to Support Magic', nb_entries=20,
                                entries=[Entry() for _ in range(20)])
        self.forbid_mag_rf = Data(name='forbid_mag_rf', offset=0x300, description='Item to Support Magic', nb_entries=6,
                                  entries=[Entry() for _ in range(6)])
        self.list_data = (self.t_mag_rf, self.i_mag_rf, self.f_mag_rf, self.l_mag_rf, self.time_mag_rf, self.st_mag_rf, self.supt_mag_rf, self.forbid_mag_rf)
        self.input_id = TypeId.ITEM
        self.output_id = TypeId.SPELL
        self.mngrp_bin_id = 106
        self.mngrp_msg_id = 111


@dataclass
class m001bin:
    def __init__(self):
        self.name = "m001"
        self.recov_med_rf = Data(name='recov_med_rf', offset=0x0, description='Item to Recovery Items', nb_entries=9,
                                 entries=[Entry() for _ in range(9)])
        self.st_med_rf = Data(name='st_med_rf', offset=0x48, description='Item to Status Removal Items', nb_entries=12,
                              entries=[Entry() for _ in range(12)])
        self.amo_rf = Data(name='amo_rf', offset=0xA8, description='Item to Ammo Item', nb_entries=16,
                           entries=[Entry() for _ in range(16)])
        self.forbid_med_rf = Data(name='forbid_med_rf', offset=0x128, description='Item to Forbidden Medicine',
                                  nb_entries=20,
                                  entries=[Entry() for _ in range(20)])
        self.gfrecov_med_rf = Data(name='gfrecov_med_rf', offset=0x1C8, description='Item to GF Recovery Items',
                                   nb_entries=12,
                                   entries=[Entry() for _ in range(12)])
        self.gfabl_med_rf = Data(name='gfabl_med_rf', offset=0x228, description='Item to GF Ability Medicine Items',
                                 nb_entries=42,
                                 entries=[Entry() for _ in range(42)])
        self.tool_rf = Data(name='tool_rf', offset=0x378, description='Item to Tool Items', nb_entries=32,
                            entries=[Entry() for _ in range(32)])
        self.list_data = (self.recov_med_rf, self.st_med_rf, self.amo_rf, self.forbid_med_rf, self.gfrecov_med_rf, self.gfabl_med_rf, self.tool_rf)
        self.input_id = TypeId.ITEM
        self.output_id = TypeId.ITEM
        self.mngrp_bin_id = 107
        self.mngrp_msg_id = 112


@dataclass
class m002bin:
    def __init__(self):
        self.name = "m002"
        self.mid_mag_rf = Data(name='mid_mag_rf', offset=0x0, description='Upgrade Magic from low level to mid level',
                               nb_entries=4,
                               entries=[Entry() for _ in range(4)])
        self.high_mag_rf = Data(name='high_mag_rf', offset=0x20,
                                description='Upgrade Magic from mid level to high level', nb_entries=6,
                                entries=[Entry() for _ in range(6)])
        self.list_data = (self.mid_mag_rf, self.high_mag_rf)
        self.input_id = TypeId.ITEM
        self.output_id = TypeId.SPELL
        self.mngrp_bin_id = 108
        self.mngrp_msg_id = 113

@dataclass
class m003bin:
    def __init__(self):
        self.name = "m003"
        self.med_lv_up = Data(name='med_lv_up', offset=0x0,
                              description='Level up low level recovery items to higher items', nb_entries=12,
                              entries=[Entry() for _ in range(12)])
        self.list_data = (self.med_lv_up,)
        self.input_id = TypeId.ITEM
        self.output_id = TypeId.ITEM
        self.mngrp_bin_id = 109
        self.mngrp_msg_id = 114


@dataclass
class m004bin:
    def __init__(self):
        self.name = "m004"
        self.card_mod = Data(name='card_mod', offset=0x0, description='Card to Items', nb_entries=110,
                             entries=[Entry() for _ in range(110)])
        self.list_data = (self.card_mod,)
        self.input_id = TypeId.CARD
        self.output_id = TypeId.ITEM
        self.mngrp_bin_id = 110
        self.mngrp_msg_id = 115
