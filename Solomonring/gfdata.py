import json

from FF8GameData.gamedata import GameData
from ShumiTranslator.model.kernel.kernelsubsectiondata import SubSectionData


class GFData:
    def __init__(self, subsection:SubSectionData, game_data:GameData):
        self.game_data = game_data
        self._subsection = subsection
        self._target_data = subsection.get_data_list()[-1].get_data_hex()
        self._target_data_start = subsection.nb_data_with_offset() * SubSectionData.OFFSET_SIZE
        self._fields = {f["name"]: f for f in game_data.kernel_data_json["junctionable_gf_data"][2:]}


    def get(self, field_name: str) -> int:
        field = self._fields[field_name]
        offset = field["offset"] - self._target_data_start
        return int.from_bytes(self._target_data[offset: offset + field["size"]], "little")

    def set(self, field_name: str, value: int):
        field = self._fields[field_name]
        offset = field["offset"] - self._target_data_start
        self._target_data[offset: offset + field["size"]] = value.to_bytes(length=field["size"], byteorder="little")