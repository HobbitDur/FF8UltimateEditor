"""A cinematic effect's MAG script edited part by part: what a description's "script" names (its parts and their
values, each at a place of the file) on top of the parameters of its part tabs. A value is read from the file and
written to it (same size, every jump is relative): it goes with the file, not with the effect's program."""
import struct

SCRIPT_PREFIX = "script."


def is_script_key(key):
    return key.startswith(SCRIPT_PREFIX)


def with_script_parts(schema, description):
    """`schema` (a part tabs' table) and its description's script parts after its own."""
    script = (description or {}).get("script")
    if schema is None or not script:
        return schema
    return dict(schema, parts=[*schema["parts"], *script["parts"]], fields=[*schema["fields"], *script["fields"]],
                groups=[*schema.get("groups", []), *script.get("groups", [])])


def _options(field):
    return [{int(at, 16): bytes.fromhex(raw) for at, raw in option["bytes"].items()} for option in field["options"]]


def read_value(field, data):
    """A field's value in the file, None when the file holds none of its choices."""
    if field["type"] == "choice":
        for index, option in enumerate(_options(field)):
            if all(data[at:at + len(raw)] == raw for at, raw in option.items()):
                return index
        return None
    at, form = int(field["at"], 16), field["form"]
    if form == "s16":
        return struct.unpack_from("<h", data, at)[0]
    if form == "op":
        return struct.unpack_from("<H", data, at)[0] >> 9
    if form == "s8":
        return struct.unpack_from("<b", data, at)[0]
    return data[at]


def edits(field, value, data):
    """[(offset, bytes)] that give a field this value in the file."""
    if field["type"] == "choice":
        option = field["options"][value]
        return [(int(at, 16), bytes.fromhex(raw)) for at, raw in {**option["bytes"], **option.get("also", {})}.items()]
    at, form = int(field["at"], 16), field["form"]
    if form == "s16":
        return [(at, struct.pack("<h", value))]
    if form == "op":
        return [(at, struct.pack("<H", struct.unpack_from("<H", data, at)[0] & 0x1FF | value << 9))]
    return [(at, struct.pack("<b" if form == "s8" else "<B", value))]


def script_values(script, data):
    """{key: value} of a script's fields in a file."""
    return {field["key"]: read_value(field, data) for field in script["fields"]}


def _sized(script, data):
    """The file's size is the game's, or only its stage camera track ("camera": where the game's is, its size) has
    another size (Cronos Bio's holds the exe Bio's): the track in its place, the rest of the file as long as the game's
    (up to the zero padding a resize keeps 4-byte aligned)."""
    if len(data) == script["size"]:
        return True
    if "camera" not in script:
        return False
    from FF8GameData.magcine.packedmag import PackedMag
    try:
        camera = PackedMag(bytes(data)).camera
    except (ValueError, IndexError, struct.error):
        return False
    at, size = int(script["camera"]["at"], 16), int(script["camera"]["size"], 16)
    rest = (len(data) - camera[1]) - (script["size"] - size) if camera else None
    return camera is not None and camera[0] == at and rest is not None and -4 < rest < 4 and len(data) % 4 == script["size"] % 4


def script_matches(script, data):
    """Whether a file is laid out as the script says (a mod's may not be): the file's size (its camera track's aside),
    each value's instruction in its place, each choice one of its own."""
    return _sized(script, data) and all(
        data[int(field["inst"], 16)] == int(field["code"], 16) and read_value(field, data) is not None for field in script["fields"])


def apply_script_values(script, data, values):
    """The file's bytes with these {key: value}."""
    result = bytearray(data)
    for field in script["fields"]:
        if field["key"] in values:
            for at, raw in edits(field, values[field["key"]], result):
                result[at:at + len(raw)] = raw
    return bytes(result)
