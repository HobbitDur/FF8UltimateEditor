"""The 68-byte magazine page entry shared by mmag.bin and mmag2.bin.

Both files are a headerless array of these entries: mmag.bin holds the in-menu
magazines and tutorial books (the Zone editor), mmag2.bin the save-point Chocobo
World screens (the Moomba editor). Every field is kept, including the ones a
given screen never reads, so a load + save is byte-exact on both.

Layout (little endian), as read by Menu_Magazine_Draw (0x4C9330) and friends:

| Offset | Size | Field                                                          |
|--------|------|----------------------------------------------------------------|
| 0x00   | 2x4  | window_x / window_y / window_width / window_height              |
| 0x08   | 2x4  | picture_x / picture_y / picture_width / picture_height          |
| 0x10   | 1x3  | picture_tint_r / picture_tint_g / picture_tint_b                |
| 0x13   | 1    | paper_e1 (PS1 GPU E1 texture page bits)                         |
| 0x14   | 1    | paper_e2 (PS1 GPU E2 texture window bits)                       |
| 0x15   | 1    | text_file_index (book text = mngrp raw file 87 + this)          |
| 0x16   | 1    | texture_category                                                |
| 0x17   | 1    | texture_page                                                    |
| 0x18   | 1    | weapon_index (0xFF = none)                                      |
| 0x19   | 1    | weapon_line_spacing                                             |
| 0x1A   | 1    | duel_move_id (0xFF = none)                                      |
| 0x1B   | 1    | angelo_move_id (0xFF = none)                                    |
| 0x1C   | 2    | weapon_list_x                                                   |
| 0x1E   | 1    | weapon_list_y                                                   |
| 0x1F   | 1    | weapon_quantity_column_x                                        |
| 0x20   | 2    | duel_combo_x                                                    |
| 0x22   | 1    | duel_combo_y                                                    |
| 0x23   | 1    | footer_flag                                                     |
| 0x24   | 4x4  | picture_overlays (SP2 sprite ids)                               |
| 0x34   | 4x4  | text_overlays (book-text string ids)                            |

**0x10-0x12 are a colour, not a geometry scale.** Menu_Magazine_DrawPageImage
(0x4C95A0) builds a GP0(0x62) primitive - a monochrome, semi-transparent
rectangle with no UV at all - whose R/G/B are these three bytes each multiplied
by the matching byte of the zoom colour and divided by 128. So the "page
picture" rect is the tinted paper mat drawn behind the art; the art itself comes
from the picture overlays. (The FF8ModdingWiki called these "Picture X/Y/Z
scale", which is what the field names used to say.)
"""

UNUSED_ID = 0xFF


class OverlaySlot:
    """One 4-byte overlay slot of a mmag/mmag2 entry (picture or text overlay).

    Layout (little endian):
        - offset 0 (int16): X position, relative to the window position
        - offset 2 (byte) : Y position
        - offset 3 (byte) : id (SP2 sprite id for picture slots, string id for text slots),
                            0xFF = slot unused
    """

    SIZE = 4
    UNUSED_ID = UNUSED_ID

    def __init__(self, x=0, y=0, id=UNUSED_ID):
        self.x = x
        self.y = y
        self.id = id

    @classmethod
    def from_bytes(cls, slot_bytes):
        x = int.from_bytes(slot_bytes[0:2], byteorder='little', signed=True)
        return cls(x=x, y=slot_bytes[2], id=slot_bytes[3])

    def to_bytes(self):
        slot_bytes = bytearray()
        slot_bytes.extend((self.x & 0xFFFF).to_bytes(2, byteorder='little'))
        slot_bytes.append(self.y & 0xFF)
        slot_bytes.append(self.id & 0xFF)
        return slot_bytes

    @property
    def unused(self):
        return self.id == UNUSED_ID

    def __str__(self):
        if self.unused:
            return "OverlaySlot(unused)"
        return f"OverlaySlot(x: {self.x}, y: {self.y}, id: {self.id})"


class MagPageEntry:
    """One 68-byte page entry of mmag.bin / mmag2.bin (see the module docstring)."""

    SIZE = 68
    NB_OVERLAY_SLOTS = 4

    def __init__(self, entry_id=0):
        self.entry_id = entry_id
        # Text window rectangle
        self.window_x = 0
        self.window_y = 0
        self.window_width = 0
        self.window_height = 0
        # Paper mat rectangle drawn behind the page art (width/height 0 = not drawn)
        self.picture_x = 0
        self.picture_y = 0
        self.picture_width = 0
        self.picture_height = 0
        # Its colour: each channel is multiplied by the zoom byte and divided by 128
        self.picture_tint_r = 0
        self.picture_tint_g = 0
        self.picture_tint_b = 0
        # Paper background (PS1 GPU E1/E2 primitive bits)
        self.paper_e1 = 0
        self.paper_e2 = 0
        # The string section loaded for the book text is raw file 87 + this value
        # (unused by mmag2.bin, whose text comes from raw file 90)
        self.text_file_index = 0
        # Page texture: the loaded picture is raw file (category base) + page
        self.texture_category = 0
        self.texture_page = 0
        # Unlock block, only processed by the item-menu magazine reader (0xFF = none);
        # unused by mmag2.bin but preserved
        self.weapon_index = UNUSED_ID
        self.weapon_line_spacing = UNUSED_ID
        self.duel_move_id = UNUSED_ID
        self.angelo_move_id = UNUSED_ID
        self.weapon_list_x = 0
        self.weapon_list_y = 0
        self.weapon_quantity_column_x = 0
        self.duel_combo_x = 0
        self.duel_combo_y = 0
        # 1 = draw the "To be continued"-style footer line (menu string 1/13/28)
        self.footer_flag = 0
        self.picture_overlays = [OverlaySlot() for _ in range(self.NB_OVERLAY_SLOTS)]
        self.text_overlays = [OverlaySlot() for _ in range(self.NB_OVERLAY_SLOTS)]

    @classmethod
    def from_bytes(cls, entry_id, entry_bytes):
        entry = cls(entry_id)

        def int16(offset):
            return int.from_bytes(entry_bytes[offset:offset + 2], byteorder='little', signed=True)

        entry.window_x = int16(0x00)
        entry.window_y = int16(0x02)
        entry.window_width = int16(0x04)
        entry.window_height = int16(0x06)
        entry.picture_x = int16(0x08)
        entry.picture_y = int16(0x0A)
        entry.picture_width = int16(0x0C)
        entry.picture_height = int16(0x0E)
        entry.picture_tint_r = entry_bytes[0x10]
        entry.picture_tint_g = entry_bytes[0x11]
        entry.picture_tint_b = entry_bytes[0x12]
        entry.paper_e1 = entry_bytes[0x13]
        entry.paper_e2 = entry_bytes[0x14]
        entry.text_file_index = entry_bytes[0x15]
        entry.texture_category = entry_bytes[0x16]
        entry.texture_page = entry_bytes[0x17]
        entry.weapon_index = entry_bytes[0x18]
        entry.weapon_line_spacing = entry_bytes[0x19]
        entry.duel_move_id = entry_bytes[0x1A]
        entry.angelo_move_id = entry_bytes[0x1B]
        entry.weapon_list_x = int16(0x1C)
        entry.weapon_list_y = entry_bytes[0x1E]
        entry.weapon_quantity_column_x = entry_bytes[0x1F]
        entry.duel_combo_x = int16(0x20)
        entry.duel_combo_y = entry_bytes[0x22]
        entry.footer_flag = entry_bytes[0x23]
        entry.picture_overlays = [
            OverlaySlot.from_bytes(entry_bytes[0x24 + i * OverlaySlot.SIZE:0x24 + (i + 1) * OverlaySlot.SIZE])
            for i in range(cls.NB_OVERLAY_SLOTS)]
        entry.text_overlays = [
            OverlaySlot.from_bytes(entry_bytes[0x34 + i * OverlaySlot.SIZE:0x34 + (i + 1) * OverlaySlot.SIZE])
            for i in range(cls.NB_OVERLAY_SLOTS)]
        return entry

    def to_bytes(self):
        entry_bytes = bytearray()

        def put_int16(value):
            entry_bytes.extend((value & 0xFFFF).to_bytes(2, byteorder='little'))

        put_int16(self.window_x)
        put_int16(self.window_y)
        put_int16(self.window_width)
        put_int16(self.window_height)
        put_int16(self.picture_x)
        put_int16(self.picture_y)
        put_int16(self.picture_width)
        put_int16(self.picture_height)
        entry_bytes.append(self.picture_tint_r & 0xFF)
        entry_bytes.append(self.picture_tint_g & 0xFF)
        entry_bytes.append(self.picture_tint_b & 0xFF)
        entry_bytes.append(self.paper_e1 & 0xFF)
        entry_bytes.append(self.paper_e2 & 0xFF)
        entry_bytes.append(self.text_file_index & 0xFF)
        entry_bytes.append(self.texture_category & 0xFF)
        entry_bytes.append(self.texture_page & 0xFF)
        entry_bytes.append(self.weapon_index & 0xFF)
        entry_bytes.append(self.weapon_line_spacing & 0xFF)
        entry_bytes.append(self.duel_move_id & 0xFF)
        entry_bytes.append(self.angelo_move_id & 0xFF)
        put_int16(self.weapon_list_x)
        entry_bytes.append(self.weapon_list_y & 0xFF)
        entry_bytes.append(self.weapon_quantity_column_x & 0xFF)
        put_int16(self.duel_combo_x)
        entry_bytes.append(self.duel_combo_y & 0xFF)
        entry_bytes.append(self.footer_flag & 0xFF)
        for slot in self.picture_overlays:
            entry_bytes.extend(slot.to_bytes())
        for slot in self.text_overlays:
            entry_bytes.extend(slot.to_bytes())
        return entry_bytes

    def __str__(self):
        return (f"MagPageEntry(id: {self.entry_id}, window: {self.window_width}x{self.window_height}, "
                f"texture: cat {self.texture_category} page {self.texture_page})")
