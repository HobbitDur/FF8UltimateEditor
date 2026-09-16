"""Animation sequence section as xml: one <animation id="N"> per sequence, its byte code in hex.

    <?xml version="1.0" encoding="UTF-8"?>
    <sequence_animations>
      <animation id="1">
        <data>A3 00 E6 FF</data>
      </animation>
    </sequence_animations>

The animations are kept in file order (the order their byte code is laid out in the section); the
id is the sequence number the game plays. To be applied onto a .dat, the ids must run from 1 to the
number of animations.
"""
import pathlib
import xml.etree.ElementTree as ET

from .common import SectionFileError, bytes_to_hex, hex_to_bytes, parse_int


def write_seq_animation_data(seq_animation_data: list, xml_file):
    xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<sequence_animations>']
    for item in seq_animation_data:
        xml_lines.append(f'  <animation id="{item["id"]}">')
        xml_lines.append(f'    <data>{bytes_to_hex(item["data"])}</data>')
        xml_lines.append('  </animation>')
    xml_lines.append('</sequence_animations>')
    with open(xml_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(xml_lines))


def read_seq_animation_data(xml_file) -> list:
    """Xml -> [{'id': 1, 'data': bytearray(...)}, ...]. Raises SectionFileError on any problem."""
    try:
        root = ET.parse(xml_file).getroot()
    except ET.ParseError as error:
        raise SectionFileError(f"{xml_file}: the xml could not be parsed: {error}")
    except FileNotFoundError:
        raise SectionFileError(f"{xml_file}: file not found")
    seq_animation_data = []
    for animation_element in root.findall('animation'):
        anim_id = parse_int(animation_element.get('id', ''), xml_file, "animation id")
        data_element = animation_element.find('data')
        data_text = data_element.text if data_element is not None else ""
        seq_animation_data.append({'id': anim_id, 'data': hex_to_bytes(data_text, xml_file)})
    return seq_animation_data


def export_section(enemy, file_path: pathlib.Path, tools):
    write_seq_animation_data(enemy.seq_animation_data['seq_animation_data'], file_path)


def apply_section(enemy, file_path: pathlib.Path, tools):
    seq_animation_data = read_seq_animation_data(file_path)
    # The .dat stores one offset per id, from 1 to the number of sequences: a missing id cannot be
    # written (the writer would search for it forever)
    id_list = sorted(seq['id'] for seq in seq_animation_data)
    if id_list != list(range(1, len(seq_animation_data) + 1)):
        raise SectionFileError(f"{file_path}: the animation ids must be 1 to {len(seq_animation_data)}, "
                               f"each exactly once (found {id_list})")
    enemy.seq_animation_data['seq_animation_data'] = seq_animation_data
