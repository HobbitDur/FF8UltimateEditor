"""The English 2013 EXE's ordered group searches for world draw points.

Five phase rows, four signed group bytes per row. A negative byte terminates a
row; positive group indices address the five ranges in wmset section 34.
"""
class WorldDrawPhases:
    FILE_OFFSET = 0x876770
    MEMORY_ADDRESS = 0xC76770
    PHASE_COUNT = 5
    SEARCH_COUNT = 4
    GROUP_COUNT = 5
    DEFAULT_DATA = bytes((0, 1, 255, 255, 0, 2, 255, 255, 0, 2, 3, 255,
                          0, 2, 3, 4, 0, 2, 3, 4))

    def __init__(self):
        self._data = bytearray(self.DEFAULT_DATA)
        self.loaded = False

    @staticmethod
    def _decode(row):
        groups = []
        for value in row:
            if value >= 128:
                break
            if value >= WorldDrawPhases.GROUP_COUNT:
                raise ValueError(f'Unsupported draw group {value}; the original wmset has groups 0-4')
            groups.append(value)
        return tuple(groups)

    def load_exe_bytes(self, data):
        size = self.PHASE_COUNT * self.SEARCH_COUNT
        raw = bytes(data[self.FILE_OFFSET:self.FILE_OFFSET + size])
        if len(raw) != size:
            raise ValueError('File is too short for the OG English 2013 world draw phase table')
        self.load_table_bytes(raw)

    def table_bytes(self):
        return bytes(self._data)

    def load_table_bytes(self, raw):
        """Restore the complete table, preserving terminators and ignored tail bytes."""
        if len(raw) != self.PHASE_COUNT * self.SEARCH_COUNT:
            raise ValueError('The world draw phase table must contain 20 bytes')
        for phase in range(self.PHASE_COUNT):
            self._decode(raw[phase * 4:phase * 4 + 4])
        self._data = bytearray(raw)
        self.loaded = True

    def groups_for_phase(self, phase):
        if not 0 <= phase < self.PHASE_COUNT:
            raise ValueError('World phase must be between 0 and 4')
        return self._decode(self._data[phase * 4:phase * 4 + 4])

    @property
    def phase_groups(self):
        return tuple(self.groups_for_phase(phase) for phase in range(self.PHASE_COUNT))

    def set_groups(self, phase, groups):
        if not self.loaded:
            raise ValueError('Load the FF8 EXE before editing phase rules')
        self.groups_for_phase(phase)  # bounds check
        groups = tuple(groups)
        if len(groups) > self.SEARCH_COUNT or any(type(g) is not int or not 0 <= g < 5 for g in groups):
            raise ValueError('A phase can search up to four groups, numbered 0-4')
        if groups == self.groups_for_phase(phase):
            return False  # preserve even non-canonical negative terminators and ignored tail bytes
        self._data[phase * 4:phase * 4 + 4] = bytes(groups) + b'\xff' * (4 - len(groups))
        return True

    def hext_lines(self, base_offset=0x400000):
        """Export the loaded rules, including existing custom rows and ignored tail bytes."""
        if not self.loaded:
            return []
        return [f' {self.MEMORY_ADDRESS - base_offset + i:X} = {value:02X}'
                for i, value in enumerate(self._data)]
