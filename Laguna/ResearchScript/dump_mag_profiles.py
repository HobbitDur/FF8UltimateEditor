"""Extract per-effect VM tables from the English 2013 Steam exe (no IDA required).

Run from the repository root: python -m Laguna.ResearchScript.dump_mag_profiles EXE --out JSON
The StageCameraAnim call is 0x40 bytes into op 0x39 in these copies. A candidate directory
must have all 327 entries either null or in .text and at least 150 non-null entries. Ambiguous
candidates are refused. Addresses/availability are extracted; operand rules below were read
from the native handlers, not inferred from a successful linear disassembly.
"""
import argparse
import hashlib
import json
import struct

from Fujin.ResearchScript.dump_effect_cameras import Exe, effect_inits, find_camera_calls, owner_effect


def rule(name, length, operands, semantics, address, refs=None, high_bits="Effect-specific; preserve unless understood"):
    return dict(name=name, length=str(length), operands=[dict(name=n, type="s16") for n in operands],
                high_bits=high_bits, flow="branch" if refs else "none", semantics=semantics,
                confidence="high", notes=f"English 2013 native handler reference: 0x{address:X}. Not simulated.",
                refs=refs or [], fallthrough=True)


EXTRA_OPS = {
    0x94: rule("BranchIfWithinBoneXZ", 10, ["bone reference", "X radius", "Z radius", "relative branch"],
               "Branches when the referenced bone is inside the current bone's X/Z rectangle.", 0xA26E20,
               [dict(word=3, kind="code", base="op")]),
    0x9A: rule("SetEntityList", "2 + 2 * (op >> 12)", [],
               "High nibble is the entity count; each following word contributes its low byte to the scene entity list.",
               0x9C5700, high_bits="op >> 12 = number of entity words"),
    0xAB: rule("StartEntityAnimation", 4, ["animation ID"],
               "Initializes the current battle entity's animation block and starts the requested animation.", 0xA86690),
    0xAD: rule("PlaceAtEntityJoint", 4, ["joint selector"],
               "Resolves a joint in the current battle entity and copies its transformed position to the bone accumulators.", 0x9A1A30),
    0xAF: rule("SetInlineDescriptor", "80 if w[0] == 0 else 4", ["mode (0 for inline descriptor)"],
               "Mode 0 installs the following 0x4C-byte descriptor and advances 0x50 bytes total. "
               "The native handler does not advance for nonzero mode; retain original mode.", 0xAD29D0),
    0xB3: rule("SetBoneFacingReference", 4, ["bone reference"],
               "Builds reference-position/facing data from the current and referenced bones; flag-dependent runtime behavior.", 0xAC7800),
    0xB4: rule("PlaceAtRandomEntityJoint", 2, [],
               "Chooses a random joint of the current battle entity, copies its transformed position to the accumulators and updates the bone.", 0x963B80),
    0xB5: rule("BranchIfBattleSlot", 6, ["battle slot", "relative branch"],
               "Branches when the current bone's battle slot equals the operand.", 0x8E4B30,
               [dict(word=1, kind="code", base="op")]),
    0xBB: rule("CopyAlternativeTexture", 6, ["texture ID", "buffer offset / 16"],
               "Copies the selected alternative texture into the magic texture buffer at 16 times the second operand.", 0xA997A0),
    0xBD: rule("ProcessRelativeTextureData", 6, ["relative data offset", "buffer offset / 16"],
               "In the enabled path, passes instruction-relative data and a magic-buffer destination to sub_B66F40. "
               "Six-byte encoding; runtime behavior is flag-dependent and is not simulated.", 0xA99730,
               [dict(word=0, kind="data", base="op")]),
    0xBE: rule("BranchOnEntityState", 4, ["relative branch"],
               "Falls through when the current battle entity has flag bit 1 and the opcode's top nibble is zero; otherwise branches.",
               0xB3A9B0, [dict(word=0, kind="code", base="op")]),
    0x112: rule("AccumulatorFromBoneDistance", 10, ["component / axis mask", "bone A", "bone B", "divisor"],
                "Writes a scaled distance between two bones to an accumulator; operand/high-bit masks choose components. "
                "A zero divisor is invalid at runtime.", 0xA32E10),
    0x113: rule("AccumulatorFromBoneAngleXZ", 8, ["component", "bone A", "bone B"],
                "Writes the X/Z facing angle between two referenced bones into the selected accumulator and updates the bone.", 0xA32F50),
    0x12E: rule("ApplyNextActionRecord", 2, [],
                "Applies the next available action-result record through sub_506690 and increments the scene record index.", 0xAC53A0),
}
EXTRA_OPS[0xAF]["invalid_when"] = [dict(condition="w[0] != 0", error="Nonzero mode does not advance the native descriptor opcode")]
EXTRA_OPS[0x112]["invalid_when"] = [dict(condition="w[3] == 0", error="Bone-distance divisor must be nonzero")]


def build(path):
    exe = Exe(path)
    inits = effect_inits(exe)
    _name, text_start, text_size, _raw, _size = exe.section(".text")
    profiles = {}
    for call, track in find_camera_calls(exe):
        if track is not None:
            continue
        effect = owner_effect(inits, call)
        if effect is None:
            continue
        needle = struct.pack("<I", call-0x40)
        matches = []
        p = exe.data.find(needle)
        while p >= 0:
            start = p-0x39*4
            if start >= 0 and start+327*4 <= len(exe.data):
                values = struct.unpack_from("<327I", exe.data, start)
                if (all(v == 0 or text_start <= v < text_start+text_size for v in values)
                        and sum(bool(v) for v in values) > 150):
                    matches.append((exe.address(start), values))
            p = exe.data.find(needle, p+1)
        if not matches:
            continue  # victory/intro and other non-cinematic callers
        if len(matches) != 1:
            raise ValueError(f"Ambiguous opcode directory for effect {effect}")
        address, values = matches[0]
        disabled = []
        overrides = {}
        for code, handler in enumerate(values):
            off = exe.offset(handler) if handler else None
            if off is None or exe.data[off] == 0xC3:
                disabled.append(code)
            elif code in EXTRA_OPS:
                overrides[f"0x{code:03X}"] = {**EXTRA_OPS[code], "handler": f"0x{handler:X}"}
        profiles[str(effect)] = dict(table=f"0x{address:X}", disabled=disabled, overrides=overrides)
    return dict(comment="Per-effect cinematic VM availability, English 2013 Steam. Generated by Laguna/ResearchScript/dump_mag_profiles.py. "
                        "Extra operand rules were verified in native handlers; playback remains limited to the seven verified GFs.",
                exe_sha256=hashlib.sha256(exe.data).hexdigest(), effects=profiles)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exe")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = build(args.exe)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1)
        f.write("\n")
    print(f"{len(result['effects'])} per-effect opcode profiles")


if __name__ == "__main__":
    main()
