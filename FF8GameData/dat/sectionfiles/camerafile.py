"""Camera section as xml (monster section 6, character section 5).

The <raw> element is the lossless source of truth (the exact section bytes); the structured
set/animation/block/frame elements below it carry the same values in a readable, hand-editable
form. On import <raw> gives the structure and the structured values are applied on top of it, so
a hand-edited value takes effect while the layout stays exact.
"""
import pathlib
import xml.etree.ElementTree as ET

from FF8GameData.dat.cameracollection import parse_camera_collection, CameraParseError, CameraCollection
from .common import SectionFileError, bytes_to_hex, hex_to_bytes


def write_collection(collection: CameraCollection, xml_file):
    root = ET.Element("camera_collection")
    raw = ET.SubElement(root, "raw")
    raw.text = bytes_to_hex(collection.get_bytes())
    for camera_set in collection.sets:
        set_element = ET.SubElement(root, "set", index=str(camera_set.index))
        for animation in camera_set.animations:
            animation_element = ET.SubElement(set_element, "animation", slot=str(animation.slot))
            if animation.empty:
                animation_element.set("empty", "true")
                continue
            for block_index, block in enumerate(animation.blocks):
                block_element = ET.SubElement(
                    animation_element, "block", index=str(block_index),
                    control=f"0x{block.control_word:04X}", layout=str(block.layout))
                if block.fov_start is not None:
                    ET.SubElement(block_element, "fov", start=str(block.fov_start.get()),
                                  end=str(block.fov_end.get()))
                if block.roll_start is not None:
                    ET.SubElement(block_element, "roll", start=str(block.roll_start.get()),
                                  end=str(block.roll_end.get()))
                for frame_index, frame in enumerate(block.frames):
                    ET.SubElement(
                        block_element, "frame", index=str(frame_index),
                        duration=str(frame.duration.get()),
                        pos_x=str(frame.pos_x.get()), pos_y=str(frame.pos_y.get()),
                        pos_z=str(frame.pos_z.get()),
                        pos_interp=f"0x{frame.pos_interp_mode.get():02X}",
                        look_x=str(frame.look_x.get()), look_y=str(frame.look_y.get()),
                        look_z=str(frame.look_z.get()),
                        look_interp=f"0x{frame.look_interp_mode.get():02X}")
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(xml_file, encoding="utf-8", xml_declaration=True)


def read_collection(xml_file) -> CameraCollection:
    """Parse a camera xml back into a CameraCollection. Raises SectionFileError on any problem."""
    try:
        root = ET.parse(xml_file).getroot()
    except ET.ParseError as error:
        raise SectionFileError(f"{xml_file}: the xml could not be parsed: {error}")
    raw_element = root.find("raw")
    if raw_element is None or not (raw_element.text or "").strip():
        raise SectionFileError(f"{xml_file}: the xml has no <raw> section bytes to import.")
    data = hex_to_bytes(raw_element.text, xml_file)
    try:
        collection = parse_camera_collection(data)
    except CameraParseError as error:
        raise SectionFileError(f"{xml_file}: the <raw> bytes are not a valid camera collection: {error}")
    _apply_xml_values(root, collection)
    return collection


def _apply_xml_values(root, collection: CameraCollection):
    """Overwrite the editable values of an already-parsed collection from the structured xml,
    matching by index. Anything that does not line up with the <raw> structure is skipped."""
    def apply(field, text):
        if field is None or text is None:
            return
        text = text.strip()
        try:
            value = int(text, 16) if text.lower().startswith("0x") else int(text)
        except ValueError:
            return
        field.set(max(field.minimum, min(field.maximum, value)))

    for set_element in root.findall("set"):
        set_index = int(set_element.get("index", "-1"))
        if not 0 <= set_index < len(collection.sets):
            continue
        camera_set = collection.sets[set_index]
        for animation_element in set_element.findall("animation"):
            slot = int(animation_element.get("slot", "-1"))
            if not 0 <= slot < len(camera_set.animations):
                continue
            animation = camera_set.animations[slot]
            if animation.empty:
                continue
            for block_element in animation_element.findall("block"):
                block_index = int(block_element.get("index", "-1"))
                if not 0 <= block_index < len(animation.blocks):
                    continue
                block = animation.blocks[block_index]
                fov_element = block_element.find("fov")
                if fov_element is not None:
                    apply(block.fov_start, fov_element.get("start"))
                    apply(block.fov_end, fov_element.get("end"))
                roll_element = block_element.find("roll")
                if roll_element is not None:
                    apply(block.roll_start, roll_element.get("start"))
                    apply(block.roll_end, roll_element.get("end"))
                for frame_element in block_element.findall("frame"):
                    frame_index = int(frame_element.get("index", "-1"))
                    if not 0 <= frame_index < len(block.frames):
                        continue
                    frame = block.frames[frame_index]
                    apply(frame.duration, frame_element.get("duration"))
                    apply(frame.pos_x, frame_element.get("pos_x"))
                    apply(frame.pos_y, frame_element.get("pos_y"))
                    apply(frame.pos_z, frame_element.get("pos_z"))
                    apply(frame.pos_interp_mode, frame_element.get("pos_interp"))
                    apply(frame.look_x, frame_element.get("look_x"))
                    apply(frame.look_y, frame_element.get("look_y"))
                    apply(frame.look_z, frame_element.get("look_z"))
                    apply(frame.look_interp_mode, frame_element.get("look_interp"))


def write_section_bytes(section_bytes: bytes, xml_file: pathlib.Path):
    """A section too short to be a camera collection (no camera data) is written as <raw> only."""
    try:
        collection = parse_camera_collection(bytearray(section_bytes))
    except CameraParseError:
        root = ET.Element("camera_collection")
        ET.SubElement(root, "raw").text = bytes_to_hex(section_bytes)
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        tree.write(xml_file, encoding="utf-8", xml_declaration=True)
        return
    write_collection(collection, xml_file)


def read_section_bytes(xml_file: pathlib.Path) -> bytearray:
    try:
        root = ET.parse(xml_file).getroot()
    except ET.ParseError as error:
        raise SectionFileError(f"{xml_file}: the xml could not be parsed: {error}")
    raw_element = root.find("raw")
    raw = hex_to_bytes(raw_element.text if raw_element is not None else "", xml_file)
    if not raw:
        return raw  # An empty camera section
    try:
        parse_camera_collection(bytearray(raw))
    except CameraParseError:
        # Not a camera collection (a file without camera data): the raw bytes are all there is.
        return raw
    return read_collection(xml_file).get_bytes()
