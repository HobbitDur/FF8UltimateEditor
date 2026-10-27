"""The battle stage values FF8_EN.exe hardcodes, as a .hext patch (FFNx applies it to the running game).

Each BS_StageNNN handler loads its stage with the camera and geometry section offsets as
immediates: `add eax, imm32` gives the geometry section (BS_ReadGeometry, the texture upload and
the model arena all use that one register). A stage whose camera section grew past its room has
its geometry further in the file (stagecamera.with_camera_section): the .hext writes the new
offset over that immediate. Addresses: the 2013 Steam English exe (FF8_EN.exe); the other
languages place the handlers elsewhere, so the patch says which exe it is for, as Fujin's do.
"""
import struct

from FF8GameData.battlestage.battlestageanalyser import STAGE_GEOMETRY_OFFSET

IMAGE_BASE = 0x400000

# Address of the geometry offset immediate (the imm32 of `add eax, imm32`) in each BS_StageNNN of
# FF8_EN.exe, found by its bytes (05 + the offset) inside the handler (stage_func_addrs.csv);
# exactly one per handler (stage 28's offset also appears inside another instruction).
GEOMETRY_OFFSET_OPERAND = {
    0: 0x51B07C, 1: 0x51AF9C, 2: 0x51AEBC, 3: 0x51ADDC, 4: 0x51ACFC, 5: 0x51AC1C, 6: 0x51AB3C, 7: 0x51AA5C,
    8: 0x51A97C, 9: 0x51A89C, 10: 0x51A7BC, 11: 0x51A6DC, 12: 0x51A5FC, 13: 0x51A51C, 14: 0x51A43C, 15: 0x51A35C,
    16: 0x51A27C, 17: 0x51A19C, 18: 0x51A0BC, 19: 0x519F9C, 20: 0x519EBC, 21: 0x519DDC, 22: 0x519CFC, 23: 0x519C1C,
    24: 0x519B3C, 25: 0x519A5C, 26: 0x51997C, 27: 0x51989C, 28: 0x5197BC, 29: 0x5196DC, 30: 0x5195FC, 31: 0x51951C,
    32: 0x51943C, 33: 0x51935C, 34: 0x51927C, 35: 0x51919C, 36: 0x5190BC, 37: 0x518AC8, 38: 0x518A2C, 39: 0x51894C,
    40: 0x51886C, 41: 0x51878C, 42: 0x5186AC, 43: 0x5185CC, 44: 0x518418, 45: 0x518268, 46: 0x518098, 47: 0x517F9C,
    48: 0x517EBC, 49: 0x517DDC, 50: 0x517CFC, 51: 0x517C0C, 52: 0x517B1C, 53: 0x517A3C, 54: 0x51795C, 55: 0x51787C,
    56: 0x51779C, 57: 0x5176BC, 58: 0x5175DC, 59: 0x5174FC, 60: 0x51741C, 61: 0x51733C, 62: 0x51725C, 63: 0x51717C,
    64: 0x51709C, 65: 0x516FBC, 66: 0x516EDC, 67: 0x516DFC, 68: 0x516D1C, 69: 0x516C3C, 70: 0x516B5C, 71: 0x516A7C,
    72: 0x51699C, 73: 0x5168BC, 74: 0x5167DC, 75: 0x5166FC, 76: 0x51661C, 77: 0x51653C, 78: 0x51645C, 79: 0x51637C,
    80: 0x51629C, 81: 0x5161BC, 82: 0x5160DC, 83: 0x515FFC, 84: 0x515F1C, 85: 0x515E3C, 86: 0x515D5C, 87: 0x515C7C,
    88: 0x515B9C, 89: 0x515ABC, 90: 0x5159DC, 91: 0x5158FC, 92: 0x5156AC, 93: 0x5155CC, 94: 0x5154EC, 95: 0x51540C,
    96: 0x51532C, 97: 0x51524C, 98: 0x51516C, 99: 0x51508C, 100: 0x514FAC, 101: 0x514ECC, 102: 0x514DEC, 103: 0x514D0C,
    104: 0x514C2C, 105: 0x514B4C, 106: 0x514A6C, 107: 0x51497C, 108: 0x51488C, 109: 0x5147AC, 110: 0x5146CC, 111: 0x5145EC,
    112: 0x51450C, 113: 0x51442C, 114: 0x51434C, 115: 0x51426C, 116: 0x51418C, 117: 0x5140AC, 118: 0x513FCC, 119: 0x513EEC,
    120: 0x513E0C, 121: 0x513D2C, 122: 0x513C4C, 123: 0x513B6C, 124: 0x513A8C, 125: 0x5139AC, 126: 0x5138CC, 127: 0x5137EC,
    128: 0x51370C, 129: 0x51362C, 130: 0x51354C, 131: 0x51346C, 132: 0x51338C, 133: 0x5132AC, 134: 0x5131CC, 135: 0x5130EC,
    136: 0x512FFC, 137: 0x50DF9F, 138: 0x512F1C, 139: 0x512E3C, 140: 0x512D5C, 141: 0x512C7C, 142: 0x512544, 143: 0x5124AC,
    144: 0x5123CC, 145: 0x5122EC, 146: 0x51220C, 147: 0x511E88, 148: 0x511D5C, 149: 0x511C7C, 150: 0x511B9C, 151: 0x511ABC,
    152: 0x5119DC, 153: 0x5118FC, 154: 0x51181C, 155: 0x51173C, 156: 0x51165C, 157: 0x51157C, 158: 0x51149C, 159: 0x5113BC,
    160: 0x5112DC, 161: 0x5111FC, 162: 0x51111C,
}


def stage_hext_text(stage_id: int, geometry_offset: int, stage_name: str = "") -> str:
    """The .hext giving FF8_EN.exe a stage's geometry section offset."""
    name = stage_name or f"a0stg{stage_id:03d}.x"
    vanilla = STAGE_GEOMETRY_OFFSET[stage_id]
    operand = GEOMETRY_OFFSET_OPERAND[stage_id]
    return "\n".join([
        f"#Alexander battle stage patch for the EN FF8 exe (FF8_EN.exe) - the address differs in the "
        "other languages, do not use it with them.",
        f"#{name}: its camera section grew, its geometry section starts at {geometry_offset} "
        f"(vanilla {vanilla}). Use it with that {name}.",
        f"+{IMAGE_BASE:X}",
        f"#BS_Stage{stage_id:03d}: add eax, {vanilla} -> {geometry_offset}",
        f"{operand - IMAGE_BASE:X} = {struct.pack('<I', geometry_offset).hex(' ').upper()}",
        ""])
