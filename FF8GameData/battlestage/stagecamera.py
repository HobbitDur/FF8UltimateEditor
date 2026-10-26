"""The intro camera of a battle: the camera section of a battle stage (a0stgXXX.x).

A stage file has no header: FF8_EN.exe hardcodes where each stage's camera section starts
(BS_Stage000..162, table below, extracted from the 163 handlers). The section is

    u16 pointerCount (= 2)
    u16 offsetCameraSettings              relative to the section start
    u16 offsetCameraAnimationCollection
    u16 cameraDataSize                    the whole section
    settings: byte-code of the camera VM run each frame (starts with 05 00: play the camera
              animation whose id is variable 0)
    collection: camera animation sets, the format of a monster .dat section 6
                (FF8GameData.dat.cameracollection)

How the intro camera is chosen (BS_CameraInit 0x500F70, BS_GetCameraAnimationPointer
0x503520): the battle starts with the encounter's main or secondary camera byte (scene.out
0x02 / 0x03), picked 50/50 at random; encounter 33 (Dollet, the elevator) always uses the
main one. The byte goes to the camera VM's variable 0: its high nibble is the animation SET
of the stage's collection, bits 0-2 the animation in that set (bit 3 is unused). A set the
stage does not have plays nothing: the battle keeps the default camera.
"""
import struct

from FF8GameData.dat.cameracollection import parse_camera_collection

STAGE_CAMERA_OFFSET = {
    0: 1496, 1: 1496, 2: 1496, 3: 1496, 4: 1492, 5: 1492, 6: 1496, 7: 1496, 8: 1560, 9: 1492,
    10: 1496, 11: 1496, 12: 1492, 13: 1492, 14: 1492, 15: 1492, 16: 1576, 17: 1496, 18: 1496,
    19: 1604, 20: 1564, 21: 1492, 22: 1492, 23: 1492, 24: 1492, 25: 1496, 26: 1492, 27: 1496,
    28: 1496, 29: 1492, 30: 2356, 31: 2356, 32: 1492, 33: 1492, 34: 1492, 35: 1492, 36: 1492,
    37: 3264, 38: 1496, 39: 1492, 40: 1492, 41: 1496, 42: 1496, 43: 1496, 44: 2468, 45: 2468,
    46: 2468, 47: 1496, 48: 1560, 49: 1496, 50: 1492, 51: 1536, 52: 1536, 53: 1492, 54: 1568,
    55: 1492, 56: 1568, 57: 1496, 58: 1496, 59: 1496, 60: 1496, 61: 1492, 62: 1492, 63: 1492,
    64: 1492, 65: 1492, 66: 1492, 67: 1492, 68: 1492, 69: 1492, 70: 1492, 71: 1492, 72: 1492,
    73: 1492, 74: 1496, 75: 1492, 76: 1496, 77: 1496, 78: 1492, 79: 1560, 80: 1496, 81: 1496,
    82: 1492, 83: 1492, 84: 1496, 85: 1492, 86: 1492, 87: 1492, 88: 1492, 89: 1492, 90: 1492,
    91: 1492, 92: 2108, 93: 1496, 94: 1492, 95: 1496, 96: 1492, 97: 1492, 98: 1492, 99: 1492,
    100: 1492, 101: 1496, 102: 1496, 103: 1496, 104: 1496, 105: 1492, 106: 1492, 107: 1536,
    108: 1536, 109: 1496, 110: 1496, 111: 1496, 112: 1496, 113: 1496, 114: 1496, 115: 1496,
    116: 1496, 117: 1496, 118: 1496, 119: 1496, 120: 1496, 121: 1492, 122: 1492, 123: 1492,
    124: 1492, 125: 1492, 126: 1492, 127: 1492, 128: 1496, 129: 1496, 130: 1496, 131: 1496,
    132: 1496, 133: 1496, 134: 1496, 135: 1492, 136: 1532, 137: 4060, 138: 1492, 139: 1496,
    140: 1496, 141: 1492, 142: 6204, 143: 1496, 144: 1492, 145: 1492, 146: 1496, 147: 2572,
    148: 1492, 149: 1492, 150: 1492, 151: 1492, 152: 1496, 153: 1496, 154: 1496, 155: 1496,
    156: 1496, 157: 1592, 158: 1492, 159: 1496, 160: 1492, 161: 1496, 162: 1496,
}

ALWAYS_MAIN_CAMERA_ENCOUNTER = 33
INTRO_CAMERA_NOTE = (
    "The battle starts with the main or the secondary intro camera, picked 50/50 at random "
    f"(encounter {ALWAYS_MAIN_CAMERA_ENCOUNTER} always uses the main one). Set = the camera "
    "animation set of the battle stage file, Anim = the animation in that set (0-7). A set "
    "the stage does not have plays nothing: the battle keeps the default camera.")


class StageCamera:
    """The camera section of one battle stage."""

    def __init__(self, data, stage_id):
        offset = STAGE_CAMERA_OFFSET[stage_id]
        _count, settings, collection, size = struct.unpack_from("<4H", data, offset)
        self.stage_id = stage_id
        self.settings = bytes(data[offset + settings:offset + collection])
        self.collection = parse_camera_collection(bytearray(data[offset + collection:offset + size]))

    @property
    def set_count(self):
        return len(self.collection.sets)

    def animation(self, camera_set, camera_anim):
        """The camera animation of that set and slot, None when the stage has none there."""
        if not 0 <= camera_set < self.set_count:
            return None
        animations = self.collection.sets[camera_set].animations
        return animations[camera_anim] if 0 <= camera_anim < len(animations) else None

    def intro_animation(self, camera_byte):
        """The animation an encounter's intro camera byte plays (None: the default camera)."""
        return self.animation(camera_byte >> 4, camera_byte & 0x07)


def read_stage_camera(path_or_data, stage_id) -> StageCamera:
    if isinstance(path_or_data, (bytes, bytearray)):
        return StageCamera(path_or_data, stage_id)
    with open(path_or_data, "rb") as file:
        return StageCamera(file.read(), stage_id)
