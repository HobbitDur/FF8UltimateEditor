from FF8GameData.gamedata import GameData
from ShumiTranslator.model.kernel.kernelsubsectiondata import SubSectionData


class KernelEntry:
    """Generic accessor for a single entry (subsection) of a kernel data section.

    Generalizes the original ``GFData`` helper: raw numeric/flag fields are read
    and written in place on the subsection payload (offset math identical to
    ``GFData``), while name/description strings are read and written through the
    linked text section. On save the ``KernelManager`` recomputes every text
    offset and rebuilds the section bytes, so callers only mutate values here.

    ``field_defs`` is the list of field dicts for the section (see
    ``kernel_bin_data.json`` -> ``section_fields``). Each field has at least
    ``name``, ``offset`` (from the start of the subsection, i.e. including the
    leading text-offset words) and ``size``. Optional ``kind`` drives the editor
    widget (``int`` | ``enum`` | ``flags`` | ``ref``); it is irrelevant here.
    """

    def __init__(self, subsection: SubSectionData, text_section, nb_text_offset: int,
                 entry_index: int, field_defs: list, game_data: GameData):
        self.game_data = game_data
        self._subsection = subsection
        self._text_section = text_section
        self._nb_text_offset = nb_text_offset
        self._entry_index = entry_index
        self._fields = {f["name"]: f for f in field_defs}
        # The payload is the last data element of the subsection (after the text offsets).
        self._payload = subsection.get_data_list()[-1].get_data_hex()
        self._payload_start = subsection.nb_data_with_offset() * SubSectionData.OFFSET_SIZE

    # ------------------------------------------------------------------ raw fields
    def has_field(self, name: str) -> bool:
        return name in self._fields

    def get(self, field_name: str) -> int:
        field = self._fields[field_name]
        offset = field["offset"] - self._payload_start
        return int.from_bytes(self._payload[offset: offset + field["size"]], "little")

    def set(self, field_name: str, value: int):
        field = self._fields[field_name]
        offset = field["offset"] - self._payload_start
        value = int(value) & ((1 << (8 * field["size"])) - 1)
        self._payload[offset: offset + field["size"]] = value.to_bytes(length=field["size"], byteorder="little")

    # ------------------------------------------------------------------ text fields
    def has_text(self, text_index: int) -> bool:
        if not self._text_section or text_index >= self._nb_text_offset:
            return False
        return self._text_list_index(text_index) < len(self._text_section.get_text_list())

    def _text_list_index(self, text_index: int) -> int:
        return self._entry_index * self._nb_text_offset + text_index

    def get_text(self, text_index: int) -> str:
        if not self.has_text(text_index):
            return ""
        return self._text_section.get_text_list()[self._text_list_index(text_index)].get_str()

    def set_text(self, text_index: int, value: str):
        if not self.has_text(text_index):
            return
        self._text_section.get_text_list()[self._text_list_index(text_index)].set_str(value)
