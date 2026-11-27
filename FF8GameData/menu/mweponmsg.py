"""mwepon.msg: the Junk Shop's text per weapon upgrade, and the offsets mwepon.bin keeps for it.

mwepon.msg is a file of its own in the menu folder (not a section of mngrp.bin): FF8 text strings,
each ended by a zero byte. Menu_Prog12_JunkShop_Init (0x4EA4D0) loads it beside mwepon.bin, whose
12-byte upgrade records start with a u16 offset into it. While the cursor is on an upgrade in the
"Remodel to which weapon?" list, JunkShop_UpgradeMenuHandler (0x4EA890, state 7) points the bar
under that line at ``mwepon.msg + offset``, and sub_4EB4B0 draws it at (40, 54) after
ProcessBattleTextExpansion.

What the bar shows (checked in game with AutoTest): one line, cut at the bar's right edge (about
50 characters); a colour code ends the text there. The retail PC file holds 33 strings of one or
two spaces, one per upgrade, so the bar is empty.

The strings are kept in file order, one per offset the upgrades use (an upgrade may share another's
string). Saving writes them back in that order and moves each upgrade's offset with its string:
only bytes 0-1 of each mwepon.bin record change, read from the file on disk so whatever else was
saved there (Junkshop's prices and items) stays.
"""
from FF8GameData.GenericSection.listff8text import ListFF8Text
from FF8GameData.gamedata import GameData

RECORD_SIZE = 12  # one mwepon.bin upgrade record
SECTION_NAME = "mwepon.msg - Junk Shop text per upgrade"


def read_offsets(bin_data):
    """Each upgrade's offset into mwepon.msg (bytes 0-1 of its mwepon.bin record)."""
    return [bin_data[RECORD_SIZE * index] | bin_data[RECORD_SIZE * index + 1] << 8
            for index in range(len(bin_data) // RECORD_SIZE)]


def text_at(game_data: GameData, msg_data, offset):
    """The text mwepon.msg holds at that offset (up to its zero byte), as the editor writes it;
    None when the offset is past the end of the file."""
    if not 0 <= offset < len(msg_data):
        return None
    end = msg_data.find(b"\x00", offset)
    return game_data.translate_hex_to_str(bytearray(msg_data[offset:end if end >= 0 else len(msg_data)]))


class MweponMsg:
    """mwepon.msg's strings (a ListFF8Text, in file order) and which string each upgrade shows."""

    def __init__(self, game_data: GameData, msg_data, bin_data):
        offsets = read_offsets(bin_data)
        past_end = [index for index, offset in enumerate(offsets) if offset >= len(msg_data)]
        if past_end:
            raise ValueError(f"mwepon.bin points past the end of mwepon.msg ({len(msg_data)} bytes) for "
                             f"upgrade(s) {', '.join(map(str, past_end))}: not the mwepon.msg of this mwepon.bin")
        starts = sorted(set(offsets))
        self.text_section = ListFF8Text(game_data=game_data, data_hex=bytearray(msg_data), id=0, own_offset=0,
                                        name=SECTION_NAME, terminate_empty=True)
        self.text_section.init_text(starts)
        self.upgrade_string = [starts.index(offset) for offset in offsets]  # upgrade -> string index

    @classmethod
    def from_files(cls, game_data: GameData, msg_path, bin_path):
        with open(msg_path, "rb") as msg_file:
            msg_data = msg_file.read()
        with open(bin_path, "rb") as bin_file:
            bin_data = bin_file.read()
        return cls(game_data, msg_data, bin_data)

    def get_text_list(self):
        return self.text_section.get_text_list()

    def upgrades_of(self, string_index):
        """The upgrades (mwepon.bin record numbers) showing that string."""
        return [upgrade for upgrade, index in enumerate(self.upgrade_string) if index == string_index]

    def build(self):
        """(mwepon.msg bytes, each upgrade's new offset)."""
        msg_data = bytearray()
        starts = []
        for text in self.get_text_list():
            starts.append(len(msg_data))
            msg_data.extend(text.get_data_hex())
        if len(msg_data) > 0xFFFF:
            raise ValueError(f"mwepon.msg would be {len(msg_data)} bytes: the offsets in mwepon.bin are 16 bits")
        return bytes(msg_data), [starts[index] for index in self.upgrade_string]

    def save(self, msg_path, bin_path):
        """Write mwepon.msg and move the offsets in the mwepon.bin on disk (only bytes 0-1 of each record)."""
        msg_data, offsets = self.build()
        with open(bin_path, "rb") as bin_file:
            bin_data = bytearray(bin_file.read())
        if len(bin_data) // RECORD_SIZE != len(offsets):
            raise ValueError(f"{bin_path} now has {len(bin_data) // RECORD_SIZE} upgrades, not "
                             f"{len(offsets)}: open mwepon.msg again with it")
        for index, offset in enumerate(offsets):
            bin_data[RECORD_SIZE * index] = offset & 0xFF
            bin_data[RECORD_SIZE * index + 1] = offset >> 8
        with open(msg_path, "wb") as msg_file:
            msg_file.write(msg_data)
        with open(bin_path, "wb") as bin_file:
            bin_file.write(bin_data)
