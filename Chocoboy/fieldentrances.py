"""Where a ``WARP_TO_FIELD`` actually sends the player.

The opcode's parameter is an entrance id, and an entrance is a 24-byte record in ``wm2field.tbl``
holding the destination field's numeric id and where on it the party lands. The field id in turn
is a line number in ``field/mapdata/maplist``, the game's list of field names. So with both files
open, ``WARP_TO_FIELD 44`` reads as "the Ragnarok cockpit" instead of "44".

Both are optional: without them the tool just shows the number it was given. Neither is ever
written - this only reads them to put names on things.

Formats as documented on the FF8ModdingWiki (Field jump), and as read by
``FFModuleHandler_main_loop`` at 0x4708C7, which is where ``CURRENT_FIELD_ID`` is taken from the
record's ``+6`` word.
"""

import struct

RECORD_SIZE = 24


class FieldEntranceTable:
    """``wm2field.tbl``: one record per world-map entrance."""

    def __init__(self, data=b""):
        self.entrances = []
        for start in range(0, len(data) - len(data) % RECORD_SIZE, RECORD_SIZE):
            x, y, triangle, field_id = struct.unpack_from("<hhhh", data, start)
            self.entrances.append({"x": x, "y": y, "triangle": triangle,
                                   "field_id": field_id, "facing": data[start + 8]})

    @classmethod
    def from_file(cls, file_path):
        with open(file_path, "rb") as in_file:
            return cls(in_file.read())

    def __len__(self):
        return len(self.entrances)

    def get(self, entrance):
        return self.entrances[entrance] if 0 <= entrance < len(self.entrances) else None


class FieldNameList:
    """``field/mapdata/maplist``: a field's id is its 0-based line number in it."""

    def __init__(self, text=""):
        self.names = text.split()

    @classmethod
    def from_file(cls, file_path):
        with open(file_path, "rb") as in_file:
            return cls(in_file.read().decode("ascii", "replace"))

    def __len__(self):
        return len(self.names)

    def get(self, field_id):
        return self.names[field_id] if 0 <= field_id < len(self.names) else None


def describe_entrance(entrance, table, field_names):
    """One line about where an entrance sends the player, with whatever files are open.

    Nothing open says so rather than staying silent: a bare entrance number is the kind of thing
    a modder would otherwise go and look up by hand.
    """
    if table is None or not len(table):
        return f"entrance {entrance} of wm2field.tbl - open that file to see where it goes"
    record = table.get(entrance)
    if record is None:
        return f"entrance {entrance}, which wm2field.tbl does not have ({len(table)} entrances)"
    name = field_names.get(record["field_id"]) if field_names is not None else None
    where = name or f"field {record['field_id']}"
    return (f"{where}, at x {record['x']}, y {record['y']}, triangle {record['triangle']}, "
            f"facing {record['facing']}")


def entrance_field_name(entrance, table, field_names):
    """Just the destination's name, for the one-line summary of a script ("" when unknown)."""
    if table is None:
        return ""
    record = table.get(entrance)
    if record is None:
        return ""
    if field_names is not None:
        name = field_names.get(record["field_id"])
        if name:
            return name
    return f"field {record['field_id']}"
