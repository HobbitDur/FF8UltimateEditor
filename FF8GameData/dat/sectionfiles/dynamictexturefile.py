"""Dynamic texture section as xml (monster and character section 4).

Same idea as the camera xml: <raw> is the exact section bytes and gives the structure, the <entry>
elements carry each entry's values in readable form and are applied on top of it by index.

    <dynamic_texture>
      <raw>...</raw>
      <entry index="0" texture_num="1" destination_u="32" destination_v="29" sprite_width="12"
             sprite_height="6" anim_speed="0" frame_counter="0">
        <sprite u="22" v="90"/>     sprite 0: the resting picture (the open eye)
        <sprite u="29" v="90"/>     sprite 1.. (the closed eye)
      </entry>
    </dynamic_texture>

The game copies one sprite at a time ONTO the destination rectangle (see DynamicTextureData). The
sprite list of an entry is replaced by the <sprite> elements, so sprites can be added or removed.
An unedited section is written back byte-for-byte (see DynamicTextureSection.to_binary). u/v are
the raw file values (u in VRAM halfwords). Files written before the fields were understood
(clut_info / unk1 / unk2 / anchor_u / <frame>) are still read.
"""
import pathlib
import xml.etree.ElementTree as ET

from FF8GameData.monsterdata import DynamicTextureSection, UV
from .common import SectionFileError, bytes_to_hex, hex_to_bytes, parse_int


def write_section_bytes(section_bytes: bytes, xml_file: pathlib.Path):
    root = ET.Element("dynamic_texture")
    ET.SubElement(root, "raw").text = bytes_to_hex(section_bytes)
    if section_bytes:
        section = DynamicTextureSection()
        section.analyze(bytes(section_bytes))
        for index, entry in enumerate(section.dynamic_texture_data):
            entry_element = ET.SubElement(
                root, "entry", index=str(index), texture_num=str(entry.texture_num),
                destination_u=str(entry.destination.get_u_raw()),
                destination_v=str(entry.destination.get_v_raw()),
                sprite_width=str(entry.sprite_width), sprite_height=str(entry.sprite_height),
                anim_speed=str(entry.anim_speed), frame_counter=str(entry.frame_counter))
            for sprite in entry.sprites:
                ET.SubElement(entry_element, "sprite", u=str(sprite.get_u_raw()), v=str(sprite.get_v_raw()))
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(xml_file, encoding="utf-8", xml_declaration=True)


def read_section_bytes(xml_file: pathlib.Path) -> bytearray:
    try:
        root = ET.parse(xml_file).getroot()
    except ET.ParseError as error:
        raise SectionFileError(f"{xml_file}: the xml could not be parsed: {error}")
    raw_element = root.find("raw")
    raw = hex_to_bytes(raw_element.text if raw_element is not None else "", xml_file)
    if not raw:
        return raw
    section = DynamicTextureSection()
    section.analyze(bytes(raw))

    for entry_element in root.findall("entry"):
        index = parse_int(entry_element.get("index", ""), xml_file, "entry index")
        if not 0 <= index < len(section.dynamic_texture_data):
            raise SectionFileError(f"{xml_file}: entry {index} does not exist in the <raw> bytes "
                                   f"({len(section.dynamic_texture_data)} entries)")
        entry = section.dynamic_texture_data[index]

        def value(name):
            return parse_int(entry_element.get(name, ""), xml_file, f"entry {index} {name}")

        def uv(element, u_name="u", v_name="v"):
            return _make_uv(parse_int(element.get(u_name, ""), xml_file, f"entry {index} {u_name}"),
                            parse_int(element.get(v_name, ""), xml_file, f"entry {index} {v_name}"), xml_file)

        if entry_element.get("destination_u") is None and entry_element.get("clut_info") is not None:
            _apply_old_names(entry, entry_element, value, uv)
            continue
        entry.texture_num = value("texture_num")
        entry.destination = uv(entry_element, "destination_u", "destination_v")
        entry.sprite_width = value("sprite_width")
        entry.sprite_height = value("sprite_height")
        entry.anim_speed = value("anim_speed")
        entry.frame_counter = value("frame_counter")
        entry.sprites = [uv(sprite_element) for sprite_element in entry_element.findall("sprite")]
    return section.to_binary()


def _apply_old_names(entry, entry_element, value, uv):
    """An xml written with the old field names: texture_num + clut_info were the first two bytes
    read as one u16 (texture_num the low 6 bits), unk1 the third, unk2 bytes 6-7, anchor sprite 0
    and the <frame> elements the other sprites."""
    first_word = (value("clut_info") & 0xFFC0) | (value("texture_num") & 0x3F)
    entry.texture_num = first_word & 0xFF
    destination = UV(member_size=1, vram_size=True)
    destination.analyze(bytes([first_word >> 8, value("unk1") & 0xFF]))
    entry.destination = destination
    entry.sprite_width = value("sprite_width")
    entry.sprite_height = value("sprite_height")
    entry.anim_speed = value("unk2") & 0xFF
    entry.frame_counter = (value("unk2") >> 8) & 0xFF
    entry.sprites = [uv(entry_element, "anchor_u", "anchor_v")] + [
        uv(frame_element) for frame_element in entry_element.findall("frame")]


def _make_uv(u: int, v: int, xml_file) -> UV:
    if not (0 <= u <= 255 and 0 <= v <= 255):
        raise SectionFileError(f"{xml_file}: u/v values must be between 0 and 255 (got {u}, {v})")
    uv = UV(member_size=1, vram_size=True)
    uv.analyze(bytes([u, v]))
    return uv
