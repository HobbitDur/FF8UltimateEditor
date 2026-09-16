"""Dynamic texture section as xml (monster and character section 4).

Same idea as the camera xml: <raw> is the exact section bytes and gives the structure, the <entry>
elements carry each entry's values in readable form and are applied on top of it by index.

    <dynamic_texture>
      <raw>...</raw>
      <entry index="0" texture_num="1" clut_info="0x0000" unk1="0" sprite_width="16"
             sprite_height="8" unk2="0" anchor_u="10" anchor_v="20">
        <frame u="10" v="20"/>
        ...
      </entry>
    </dynamic_texture>

The frame list of an entry is replaced by the <frame> elements, so frames can be added or
removed. An unedited section is written back byte-for-byte (see DynamicTextureSection.to_binary).
u/v are the raw file values.
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
                clut_info=f"0x{entry.clut_info:04X}", unk1=str(entry.unk1),
                sprite_width=str(entry.sprite_width), sprite_height=str(entry.sprite_height),
                unk2=str(entry.unk2), anchor_u=str(entry.anchor_uv.get_u_raw()),
                anchor_v=str(entry.anchor_uv.get_v_raw()))
            for frame in entry.frames:
                ET.SubElement(entry_element, "frame", u=str(frame.get_u_raw()), v=str(frame.get_v_raw()))
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

        entry.texture_num = value("texture_num")
        entry.clut_info = value("clut_info")
        entry.unk1 = value("unk1")
        entry.sprite_width = value("sprite_width")
        entry.sprite_height = value("sprite_height")
        entry.unk2 = value("unk2")
        entry.anchor_uv = _make_uv(value("anchor_u"), value("anchor_v"), xml_file)
        entry.frames = []
        for frame_element in entry_element.findall("frame"):
            entry.frames.append(_make_uv(parse_int(frame_element.get("u", ""), xml_file, f"entry {index} frame u"),
                                         parse_int(frame_element.get("v", ""), xml_file, f"entry {index} frame v"),
                                         xml_file))
        entry.number_frames = len(entry.frames)
    return section.to_binary()


def _make_uv(u: int, v: int, xml_file) -> UV:
    if not (0 <= u <= 255 and 0 <= v <= 255):
        raise SectionFileError(f"{xml_file}: u/v values must be between 0 and 255 (got {u}, {v})")
    uv = UV(member_size=1, vram_size=True)
    uv.analyze(bytes([u, v]))
    return uv
