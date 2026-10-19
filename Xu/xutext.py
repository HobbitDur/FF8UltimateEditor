"""battle_scans.msd: the Scan text of every monster, as FFNx reads it from direct/exe/.

The game keeps the texts inside FF8_EN.exe (160 of them, one per com_id). FFNx dumps them to
``direct/exe/battle_scans.msd`` (``save_exe_data``) and, when the file is there, shows
``text[BATTLE_SLOT_DATA[target].com_file_id]`` instead (ff8_battle_get_scan_text) - so the
entry index is the com_id: a monster's entry is its c0m number + 16. A monster added with
FFNx (c0m144+, com_id 160+) needs the file to reach its com_id, or FFNx reads past the
offset table.

MSD layout: u32 offsets (count = first offset / 4), each from the file start, then the FF8
encoded texts, each ending with 0x00.
"""
import struct

from FF8GameData.GenericSection.ff8text import FF8Text

FILE_NAME = "battle_scans.msd"
SECTION_NAME = "Scan text"


class XuTextManager:
    """The scan texts, one FF8Text per com_id."""

    def __init__(self, game_data):
        self.game_data = game_data
        self.texts = []
        self._original = []
        self.file_path = ""

    def _new_text(self, data_hex=b"", index=0) -> FF8Text:
        # terminate_empty: an empty entry still gets its own 0x00, otherwise its offset would
        # point at the next text and the game would show that one instead.
        return FF8Text(game_data=self.game_data, own_offset=0, data_hex=bytearray(data_hex), id=index,
                       terminate_empty=True)

    # ------------------------------------------------------------------ file
    def load_file(self, path: str):
        with open(path, "rb") as file:
            self.load_bytes(file.read())
        self.file_path = path

    def load_bytes(self, data: bytes):
        if len(data) < 4:
            raise ValueError(f"{FILE_NAME} is too short")
        count = struct.unpack_from("<I", data, 0)[0] // 4
        if count == 0 or count * 4 > len(data):
            raise ValueError(f"{FILE_NAME}: bad offset table (first offset {count * 4})")
        offsets = struct.unpack_from(f"<{count}I", data, 0)
        texts = []
        for index, offset in enumerate(offsets):
            if not count * 4 <= offset <= len(data):
                raise ValueError(f"{FILE_NAME}: text {index} starts outside the file ({offset})")
            end = data.find(b"\x00", offset)
            end = len(data) if end < 0 else end + 1  # keep the terminator, like the game reads it
            texts.append(self._new_text(data[offset:end], index))
        self.texts = texts
        self._original = [text.get_str() for text in texts]

    def to_bytes(self) -> bytes:
        count = len(self.texts)
        offsets, blob = [], bytearray()
        for text in self.texts:
            offsets.append(count * 4 + len(blob))
            data = bytes(text.get_data_hex())
            blob += data if data.endswith(b"\x00") else data + b"\x00"
        return struct.pack(f"<{count}I", *offsets) + bytes(blob)

    def save_file(self, path: str = ""):
        path = path or self.file_path
        if not path:
            raise ValueError("no path to save to")
        with open(path, "wb") as file:
            file.write(self.to_bytes())
        self.file_path = path

    # ------------------------------------------------------------------ texts
    @property
    def loaded(self) -> bool:
        return bool(self.texts)

    def ensure_count(self, count: int):
        """Grow the file with empty texts so it reaches `count` entries (com_id count - 1)."""
        while len(self.texts) < count:
            self.texts.append(self._new_text(index=len(self.texts)))
            self._original.append(None)

    def text(self, com_id: int):
        """The FF8Text of a com_id, or None when the file stops before it."""
        return self.texts[com_id] if 0 <= com_id < len(self.texts) else None

    def get_str(self, com_id: int) -> str:
        text = self.text(com_id)
        return text.get_str() if text is not None else ""

    def set_str(self, com_id: int, value: str):
        self.ensure_count(com_id + 1)
        self.texts[com_id].set_str(value)

    def is_modified(self, com_id: int) -> bool:
        text = self.text(com_id)
        return text is not None and (com_id >= len(self._original) or text.get_str() != self._original[com_id])
