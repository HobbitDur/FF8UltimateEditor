import struct


class WorldDrawSection:
    """Parses and rebuilds Section 34 of a ``wmsetxx.obj`` file (world-map draw points).

    Section 34 only stores the *position* of each world draw point, not its magic.
    Layout (see FF8ModdingWiki - WorldMap wmsetxx File Format):

    - ``0x00`` : 44-byte header (5 x 8-byte phase ranges + a 4-byte records base at +40).
    - ``0x2C`` : ``nb_record`` records of 4 bytes each -> ``(x, y, sub_id, pad)``.

    Record index ``N`` maps to the EXE ``DrawPointData`` entry ``128 + N``
    (Draw ID ``129 + N`` in the 1-based numbering used by the Draw editor).
    The magic / refill / high-yield of a world draw point lives in the EXE, not here.

    The header and every other section are preserved untouched: records are edited
    in place, the record count never changes, so the section size (and therefore the
    whole file's section-offset table) stays valid.
    """

    NB_SECTION = 48
    SECTION_INDEX = 34
    HEADER_SIZE = 0x2C
    RECORD_SIZE = 4
    # FF8_EN.exe 2013, VA 0xC76770. Indexed by WM_WorldPhase, not region or disc.
    PHASE_GROUPS = ((0, 1), (0, 2), (0, 2, 3), (0, 2, 3, 4), (0, 2, 3, 4))

    def __init__(self):
        self._file_data = bytearray()
        self._file_path = ""
        self._section_offset = 0
        self._section_end = 0
        self.header = bytearray()
        self.records = []  # list of [x, y, sub_id, pad]
        self._loaded = False

    def is_loaded(self):
        return self._loaded

    def get_nb_record(self):
        return len(self.records)

    def load(self, file_path):
        # Parse into a temporary object so a rejected file leaves the current one intact.
        parsed = WorldDrawSection()
        with open(file_path, "rb") as in_file:
            parsed._file_data = bytearray(in_file.read())
        parsed._file_path = file_path
        parsed._parse()
        parsed._loaded = True
        self.__dict__.update(parsed.__dict__)

    def _parse(self):
        data = self._file_data
        if len(data) < self.NB_SECTION * 4:
            raise ValueError("Truncated wmset section-offset table")
        offsets = [struct.unpack_from("<I", data, i * 4)[0] for i in range(self.NB_SECTION)]
        self._section_offset = offsets[self.SECTION_INDEX]
        self._section_end = offsets[self.SECTION_INDEX + 1]
        if not self.NB_SECTION * 4 <= self._section_offset < self._section_end <= len(data):
            raise ValueError("Invalid world draw section bounds")
        section = data[self._section_offset:self._section_end]
        if len(section) < self.HEADER_SIZE or (len(section) - self.HEADER_SIZE) % self.RECORD_SIZE:
            raise ValueError("Truncated world draw records")
        if struct.unpack_from('<I', section, 40)[0] != self.HEADER_SIZE:
            raise ValueError("Unsupported draw record base")
        for start, end in struct.iter_unpack('<II', section[:40]):
            if not self.HEADER_SIZE <= start <= end <= len(section):
                raise ValueError("Invalid world phase record range")
            if (start - self.HEADER_SIZE) % 4 or (end - self.HEADER_SIZE) % 4:
                raise ValueError("Unaligned world phase record range")

        self.header = bytearray(section[:self.HEADER_SIZE])
        nb_record = (len(section) - self.HEADER_SIZE) // self.RECORD_SIZE
        self.records = []
        for i in range(nb_record):
            base = self.HEADER_SIZE + i * self.RECORD_SIZE
            self.records.append([section[base], section[base + 1], section[base + 2], section[base + 3]])

    def phases_for_record(self, index, phase_groups=None):
        """World phases scanning this record, using the loaded file's own range header."""
        offset = self.HEADER_SIZE + index * self.RECORD_SIZE
        groups = list(struct.iter_unpack('<II', self.header[:40]))
        return tuple(phase for phase, selected in enumerate(phase_groups or self.PHASE_GROUPS)
                     if any(groups[group][0] <= offset < groups[group][1] for group in selected))

    def set_position(self, index, x, y, sub_id):
        record = self.records[index]
        record[0] = x & 0xFF
        record[1] = y & 0xFF
        record[2] = sub_id & 0xFF
        # record[3] (padding) is preserved as read

    def rebuild_section_bytes(self):
        out = bytearray(self.header)
        for record in self.records:
            out += bytes((record[0] & 0xFF, record[1] & 0xFF, record[2] & 0xFF, record[3] & 0xFF))
        return out

    def save(self, dest_path):
        section_bytes = self.rebuild_section_bytes()
        expected_size = self._section_end - self._section_offset
        if len(section_bytes) != expected_size:
            raise ValueError(
                f"Section 34 size changed ({len(section_bytes)} != {expected_size}); refusing to write.")
        new_data = bytearray(self._file_data)
        new_data[self._section_offset:self._section_end] = section_bytes
        with open(dest_path, "wb") as out_file:
            out_file.write(new_data)
