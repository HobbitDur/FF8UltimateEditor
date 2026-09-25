"""
Field dialogue file (.msd): the texts a field's scripts show (MES, AMESW, AASK... take a message
index into it).

Layout: a table of u32 offsets (one per message; the first offset / 4 = number of messages), then
the messages, each FF8-encoded and terminated by 0x00. A line break is 0x02 (written "\\n" in the
text form used by GameData.translate_hex_to_str / translate_str_to_hex).

Messages are kept as raw bytes and only re-encoded when edited, so an untouched file is rebuilt
byte for byte. Appending a message never changes the index of the existing ones.
"""
import struct

LINE_BREAK_TEXT = "\\n"  # how GameData writes the 0x02 line break in text


class MsdFile:
    def __init__(self, data: bytes, game_data):
        self.game_data = game_data
        self.original_data = bytes(data)
        self.messages = []  # raw bytes of each message, terminator included
        if len(data) >= 4:
            (first_offset,) = struct.unpack_from("<I", data, 0)
            nb_messages = first_offset // 4
            offsets = [struct.unpack_from("<I", data, 4 * index)[0] for index in range(nb_messages)] + [len(data)]
            for index in range(nb_messages):
                self.messages.append(bytes(data[offsets[index]:offsets[index + 1]]))

    def __len__(self):
        return len(self.messages)

    def text(self, index: int):
        """Message as editable text: real newlines for the 0x02 line breaks."""
        raw = self.messages[index]
        if raw.endswith(b"\x00"):
            raw = raw[:-1]
        return self.game_data.translate_hex_to_str(list(raw)).replace(LINE_BREAK_TEXT, "\n")

    def encode(self, text: str):
        return bytes(self.game_data.translate_str_to_hex(text.replace("\n", LINE_BREAK_TEXT))) + b"\x00"

    def set_text(self, index: int, text: str):
        encoded = self.encode(text)
        if encoded != self.messages[index]:
            self.messages[index] = encoded

    def add_text(self, text: str):
        """Append a message; returns its index."""
        self.messages.append(self.encode(text))
        return len(self.messages) - 1

    def to_bytes(self):
        table_size = 4 * len(self.messages)
        offsets, position = [], table_size
        for message in self.messages:
            offsets.append(position)
            position += len(message)
        return struct.pack(f"<{len(offsets)}I", *offsets) + b"".join(self.messages)

    def is_modified(self):
        return self.to_bytes() != self.original_data

    def mark_saved(self):
        self.original_data = self.to_bytes()
