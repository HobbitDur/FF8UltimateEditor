import os
from dataclasses import dataclass

from FF8GameData.GenericSection.section import Section
from FF8GameData.gamedata import GameData


@dataclass
class MngrphdEntry:
    seek: int
    size: int
    invalid_value: bool = False
    SEEK_LENGTH: int = 4
    SIZE_LENGTH: int = 4


class Mngrphd(Section):

    def __init__(self, game_data: GameData, data_hex: bytearray):
        Section.__init__(self, game_data=game_data, data_hex=data_hex, id=0, own_offset=0, name="mngrphd")
        self._mngprhd_entry_list = []
        self._mngprhd_entry_valid_list = []
        i = 0
        while i < len(data_hex):
            seek = int.from_bytes(self._data_hex[i: i + MngrphdEntry.SEEK_LENGTH], byteorder='little')
            size = int.from_bytes(
                self._data_hex[i + MngrphdEntry.SEEK_LENGTH: i + MngrphdEntry.SEEK_LENGTH + MngrphdEntry.SIZE_LENGTH],
                byteorder='little')
            if seek == 0xFFFFFF or size == 0:
                invalid_value = True
            else:
                invalid_value = False
                seek = seek - 1
            new_entry = MngrphdEntry(seek=seek, size=size, invalid_value=invalid_value)
            self._mngprhd_entry_list.append(new_entry)
            if not invalid_value:
                self._mngprhd_entry_valid_list.append(new_entry)
            i += MngrphdEntry.SEEK_LENGTH + MngrphdEntry.SIZE_LENGTH

    def get_entry_list(self):
        return self._mngprhd_entry_list

    def get_valid_entry_list(self):
        return self._mngprhd_entry_valid_list

    def update_from_section_list(self, section_list):
        self._mngprhd_entry_list = []
        self._mngprhd_entry_valid_list = []
        for section in section_list:
            seek = section.own_offset
            size = len(section)
            if seek == 0xFFFFFF or size == 0:
                invalid = True
            else:
                invalid = False
            new_entry = MngrphdEntry(seek=seek, size=len(section), invalid_value=invalid)
            self._mngprhd_entry_list.append(new_entry)
            if not invalid:
                self._mngprhd_entry_valid_list.append(new_entry)

    def update_data_hex(self):
        data_valid_hex = bytearray()
        for entry in self._mngprhd_entry_list:
            entry_hex = bytearray()
            if entry.invalid_value:
                new_seek = entry.seek
            else:
                new_seek = entry.seek + 1
            entry_hex.extend(new_seek.to_bytes(length=MngrphdEntry.SEEK_LENGTH, byteorder='little'))
            entry_hex.extend(entry.size.to_bytes(length=MngrphdEntry.SIZE_LENGTH, byteorder='little'))
            data_valid_hex.extend(entry_hex)
        self._data_hex = data_valid_hex
        self._size = len(self._data_hex)

    def __str__(self):
        str_return = ""
        for i, entry in enumerate(self._mngprhd_entry_list):
            str_return += f"Entry n°{i}: " + str(entry) + "\n"
        return str_return

    def __repr__(self):
        return self.__str__()


if __name__ == "__main__":
    game_data = GameData(os.path.join("..", "..", "FF8GameData"))
    file_mngrphd_in = "mngrphd.bin"
    file_mngrphd_data = bytearray()
    with open(file_mngrphd_in, "rb") as file:
        file_mngrphd_data.extend(file.read())
    mngprhd_section = Mngrphd(game_data, file_mngrphd_data)

    file_mngrphd_out = "mngrphd_out.bin"
    with open(file_mngrphd_out, "wb") as file:
        file.write(mngprhd_section.get_data_hex())
