import json

from ShumiTranslator.model.kernel.kernelsubsectiondata import SubSectionData


class GFData:
    def __init__(self, subsection, json_path: str):
        self._subsection = subsection
        self._target_data = subsection.get_data_list()[-1]._data_hex
        self._target_data_start = subsection._nb_text_offset * SubSectionData.OFFSET_SIZE
        with open(json_path, "r") as f:
            all_fields = json.load(f)
        self._fields = {f["name"]: f for f in all_fields[2:]}

    def get(self, field_name: str) -> int:
        field = self._fields[field_name]
        offset = field["offset"] - self._target_data_start
        return int.from_bytes(self._target_data[offset: offset + field["size"]], "little")

    def set(self, field_name: str, value: int):
        field = self._fields[field_name]
        offset = field["offset"] - self._target_data_start
        self._target_data[offset: offset + field["size"]] = value.to_bytes(length=field["size"], byteorder="little")