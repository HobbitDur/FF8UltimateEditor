import os

from FF8GameData.FF8HexReader.mngrp import Mngrp
from FF8GameData.FF8HexReader.mngrphd import Mngrphd
from FF8GameData.gamedata import GameData
from FF8GameData.m00x.dataclass import m000bin, m001bin, m002bin, m003bin, m004bin


class RefineEntry:
    """One 8-byte refine entry of a m00x bin section, with its text decoded from the msg section."""
    ENTRY_SIZE = 8

    def __init__(self, text="", element_in_id=0, amount_required=0, element_out_id=0, amount_received=0, unk=0):
        self.text = text
        self.element_in_id = element_in_id
        self.amount_required = amount_required
        self.element_out_id = element_out_id
        self.amount_received = amount_received
        self.unk = unk

    @classmethod
    def from_bytes(cls, entry_bytes, text=""):
        return cls(text=text,
                   element_in_id=entry_bytes[5],
                   amount_required=entry_bytes[6],
                   element_out_id=entry_bytes[7],
                   amount_received=entry_bytes[2],
                   unk=int.from_bytes(entry_bytes[3:5], byteorder='little'))

    def to_bytes(self, text_offset):
        entry_bytes = bytearray()
        entry_bytes.extend(text_offset.to_bytes(2, byteorder='little'))
        entry_bytes.append(self.amount_received)
        entry_bytes.extend(self.unk.to_bytes(2, byteorder='little'))
        entry_bytes.append(self.element_in_id)
        entry_bytes.append(self.amount_required)
        entry_bytes.append(self.element_out_id)
        return entry_bytes

    def __str__(self):
        return (f"RefineEntry(text: {self.text}, in: {self.element_in_id} x{self.amount_required}, "
                f"out: {self.element_out_id} x{self.amount_received}, unk: {self.unk})")


class RefineSection:
    """One refine ability (t_mag_rf, card_mod...), a list of entries from one Data of a m00x file."""

    def __init__(self, bin_name, name, description, input_type, output_type, entries):
        self.bin_name = bin_name  # m000 to m004
        self.name = name  # t_mag_rf, card_mod...
        self.description = description
        self.input_type = input_type  # TypeId of element_in_id (item, spell or card)
        self.output_type = output_type  # TypeId of element_out_id
        self.entries = entries

    def __str__(self):
        return f"RefineSection({self.bin_name} - {self.name}: {len(self.entries)} entries)"


class PandemonaManager:
    """Read/write of the refine abilities (m00x) data inside mngrp.bin/mngrphd.bin"""

    def __init__(self, game_data: GameData):
        self.game_data = game_data
        self.bin_list = (m000bin(), m001bin(), m002bin(), m003bin(), m004bin())
        self.refine_sections = []
        self.mngrp_path = ""
        self.mngrphd_path = ""
        self._mngrp_data = bytearray()
        self._mngrphd_data = bytearray()

    def load_file(self, mngrp_path, mngrphd_path=""):
        """Load the refine data from mngrp.bin, mngrphd.bin is searched next to it if not given."""
        if not mngrphd_path:
            mngrphd_path = os.path.join(os.path.dirname(mngrp_path), "mngrphd.bin")
        if not os.path.exists(mngrphd_path):
            raise FileNotFoundError(f"mngrphd.bin is needed to locate the sections of mngrp.bin, "
                                    f"not found at: {mngrphd_path}")
        self.mngrp_path = mngrp_path
        self.mngrphd_path = mngrphd_path
        with open(mngrp_path, "rb") as in_file:
            self._mngrp_data = bytearray(in_file.read())
        with open(mngrphd_path, "rb") as in_file:
            self._mngrphd_data = bytearray(in_file.read())

        mngrphd = Mngrphd(game_data=self.game_data, data_hex=bytearray(self._mngrphd_data))
        mngrp = Mngrp(game_data=self.game_data, data_hex=bytearray(self._mngrp_data),
                      header_entry_list=mngrphd.get_valid_entry_list())

        self.refine_sections = []
        for mbin in self.bin_list:
            bin_data = mngrp.get_section_by_id(mbin.mngrp_bin_id).get_data_hex()
            msg_data = mngrp.get_section_by_id(mbin.mngrp_msg_id).get_data_hex()
            for data in mbin.list_data:
                entries = []
                for index_entry in range(data.nb_entries):
                    offset = data.offset + index_entry * RefineEntry.ENTRY_SIZE
                    entry_bytes = bin_data[offset:offset + RefineEntry.ENTRY_SIZE]
                    text_offset = int.from_bytes(entry_bytes[0:2], byteorder='little')
                    entry = RefineEntry.from_bytes(entry_bytes, text=self._read_text(msg_data, text_offset))
                    entries.append(entry)
                self.refine_sections.append(RefineSection(bin_name=mbin.name, name=data.name,
                                                          description=data.description,
                                                          input_type=mbin.input_id, output_type=mbin.output_id,
                                                          entries=entries))

    def save_file(self, mngrp_path="", mngrphd_path=""):
        """Write back the refine data inside the loaded mngrp.bin/mngrphd.bin (in place by default).
        The other mngrp sections are untouched, the text offsets are recomputed."""
        if not self.refine_sections:
            raise ValueError("No file loaded")
        if not mngrp_path:
            mngrp_path = self.mngrp_path
        if not mngrphd_path:
            mngrphd_path = self.mngrphd_path

        # The full entry list (invalid included) is used so the rebuilt mngrphd keeps all its entries
        mngrphd = Mngrphd(game_data=self.game_data, data_hex=bytearray(self._mngrphd_data))
        mngrp = Mngrp(game_data=self.game_data, data_hex=bytearray(self._mngrp_data),
                      header_entry_list=mngrphd.get_entry_list())

        section_index = 0
        for mbin in self.bin_list:
            bin_bytes = bytearray()
            msg_bytes = bytearray()
            text_offset = 0
            for _ in mbin.list_data:
                for entry in self.refine_sections[section_index].entries:
                    text_hex = bytearray(self.game_data.translate_str_to_hex(entry.text))
                    text_hex.append(0x00)  # End of string
                    bin_bytes.extend(entry.to_bytes(text_offset))
                    msg_bytes.extend(text_hex)
                    text_offset += len(text_hex)
                section_index += 1
            mngrp.set_section_by_id_and_bytearray(mbin.mngrp_bin_id, bin_bytes)
            mngrp.set_section_by_id_and_bytearray(mbin.mngrp_msg_id, msg_bytes)

        mngrp.update_data_hex()
        mngrphd.update_from_section_list(mngrp.get_section_list())
        mngrphd.update_data_hex()

        with open(mngrp_path, "wb") as out_file:
            out_file.write(mngrp.get_data_hex())
        with open(mngrphd_path, "wb") as out_file:
            out_file.write(mngrphd.get_data_hex())

    def _read_text(self, msg_data, text_offset):
        """Decode the 0x00-terminated FF8 string at the given offset of a msg section."""
        if text_offset >= len(msg_data):
            return ""
        end_offset = msg_data.find(0x00, text_offset)
        if end_offset == -1:
            end_offset = len(msg_data)
        return self.game_data.translate_hex_to_str(msg_data[text_offset:end_offset])
