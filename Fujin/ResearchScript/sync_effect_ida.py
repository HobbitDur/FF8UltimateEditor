"""Apply the verified effect audit to the current English IDA database.

In IDA: File -> Script file -> this file. The script saves and copies the current IDB
before changing annotations, validates all source bytes, preserves existing descriptive
names/comments, adds types and references, saves again, and writes a verification report.

Outside IDA: python -m Fujin.ResearchScript.sync_effect_ida --emit-plan Temp/ida-effect-plan.json
"""
import argparse
import hashlib
import json
import re
import shutil
import struct
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SHA256 = "064d466b5fe2ba901fd44abf19f37c0fd6a2db40aabd95c9e5959195b6589570"
BEGIN, END = "[FF8_EFFECT_AUDIT]", "[/FF8_EFFECT_AUDIT]"
TYPE_DECLARATIONS = """
typedef struct FF8EffectPackedMAGHeader {
 unsigned int reserved_00;
 unsigned int root_script_offset;
 unsigned int clut_table_offset;
 unsigned int object_table_offset;
 unsigned int sound_table_offset;
 unsigned int texture_table_offset;
 unsigned int music_table_offset;
 unsigned int end_of_tables;
 unsigned int stage_camera_offset;
 unsigned int voice_bank_offset;
 unsigned int reserved_28;
 unsigned int reserved_2C;
} FF8EffectPackedMAGHeader;
typedef struct FF8EffectCameraTrackHeader {
 unsigned short pointer_count;
 unsigned short script_offset;
 unsigned short keyframe_collection_offset;
 unsigned short byte_size;
} FF8EffectCameraTrackHeader;
typedef struct FF8EffectModelDirectory {
 unsigned int section_count;
 unsigned int skeleton_offset;
 unsigned int geometry_offset;
 unsigned int animation_offset;
 unsigned int trailer_offset;
 unsigned int byte_size;
} FF8EffectModelDirectory;
typedef struct FF8EffectTIMHeader {
 unsigned int magic;
 unsigned int flags;
} FF8EffectTIMHeader;
typedef struct FF8EffectCinematicDirectory {
 void *handlers[327];
} FF8EffectCinematicDirectory;
"""
MEMBER_COMMENTS = [
    ("FF8EffectPackedMAGHeader", "root_script_offset", "File-relative root of the 16-bit cinematic VM. Opcode = word & 0x1FF; modifier = word >> 9."),
    ("FF8EffectPackedMAGHeader", "stage_camera_offset", "File-relative normal camera track, not an unused field. Disease Breath MAG230_B.00: 0x870, 192 bytes, 3 blocks, 5 keyframes. Zero in the seven original GF roots does not establish unused semantics."),
    ("FF8EffectPackedMAGHeader", "texture_table_offset", "Packed entries: low 24 bits relative to this texture table, not the file base."),
    ("FF8EffectPackedMAGHeader", "clut_table_offset", "Packed entries: low 24 bits relative to this CLUT table, independent of the texture table base."),
    ("FF8EffectPackedMAGHeader", "object_table_offset", "u32 object count followed by u32 offsets relative to the object table."),
    ("FF8EffectPackedMAGHeader", "end_of_tables", "End of initial tables / runtime RAM boundary. Do not treat as the complete file size."),
    ("FF8EffectCameraTrackHeader", "script_offset", "Camera bytecode begins at track-relative +8. This VM is distinct from the 16-bit cinematic VM."),
    ("FF8EffectCameraTrackHeader", "keyframe_collection_offset", "Track-relative offset to the set/slot/block/keyframe collection; follows camera script and alignment padding."),
    ("FF8EffectCameraTrackHeader", "byte_size", "Complete track size. The same relocatable format appears in exe data, packed MAG files and FFNx .bcam files."),
    ("FF8EffectModelDirectory", "skeleton_offset", "Container-relative offset. Skeleton header is 16 bytes: u8 bone count, u8 extra flag, signed scales at +8/+A/+C, followed by 48-byte bone records."),
    ("FF8EffectModelDirectory", "animation_offset", "Container-relative u32 animation count plus relative offsets to bit-packed skeletal clips. Distinct from cinematic choreography."),
    ("FF8EffectTIMHeader", "flags", "PSX TIM depth in low bits, bit 3 = CLUT present. Walk complete block lengths; a file may concatenate more TIMs (Carbuncle mag277.tim body image begins at 172064)."),
    ("FF8EffectCinematicDirectory", "handlers", "327 entries indexed by opcode & 0x1FF. Availability is effect-specific. Null and immediate-RET entries are disabled; another effect may implement that opcode."),
]
TYPE_SIZES = {"FF8EffectPackedMAGHeader": 48, "FF8EffectCameraTrackHeader": 8,
              "FF8EffectModelDirectory": 24, "FF8EffectTIMHeader": 8,
              "FF8EffectCinematicDirectory": 327*4}


def merge_comment(existing, finding):
    """Replace only our marked block, retaining every unrelated annotation."""
    old = re.sub(re.escape(BEGIN)+r".*?"+re.escape(END), "", existing or "", flags=re.S).strip()
    block = BEGIN+"\n"+finding.strip()+"\n"+END
    return old+"\n\n"+block if old else block


def build_plan(exe_path=None):
    from Fujin.ResearchScript.dump_effect_cameras import Exe
    folder = ROOT / "FF8GameData/Resources/json"
    load = lambda name: json.loads((folder / name).read_text(encoding="utf-8"))
    native, profiles = load("effect_resources.json"), load("mag_cinematic_profiles.json")["effects"]
    dispatch, cameras = load("magic_effect.json"), load("effect_camera.json")
    facts = load("effect_runtime.json")["effects"]
    names = {e["id"]: e["name"] for e in load("attack_animation.json")["attack_animation"]}
    exe = Exe(str(exe_path or ROOT / "extracted_files/FF8_EN.exe"))
    if hashlib.sha256(exe.data).hexdigest() != SHA256:
        raise ValueError("Annotation generation requires the audited original English executable")
    entries, references = {}, []

    def add(address, text, name=None, kind="data", type_name=None, size=0):
        address = int(address, 16) if isinstance(address, str) else address
        item = entries.setdefault(address, dict(address=f"0x{address:X}", kind=kind, comment=""))
        item["comment"] += ("\n\n" if item["comment"] else "")+text
        if name:
            item["name"] = name
        if type_name:
            item["type"] = type_name
        if size:
            offset = exe.offset(address)
            if offset is None or offset+size > len(exe.data):
                raise ValueError(f"Unmapped source span at 0x{address:X}")
            raw = exe.data[offset:offset+size]
            item.update(check_size=size, check_sha256=hashlib.sha256(raw).hexdigest())

    for entry in native["resources"]:
        effect_text = ", ".join(f"{i}: {names.get(i, 'Unknown')}" for i in entry["effect_ids"])
        text = f"Verified effect resource {entry['id']}. Effects: {effect_text}. {entry['size']} bytes; English 2013 Steam only."
        if entry["kind"] == "camera_parameter":
            text += (f"\n{entry['label']}: {entry['note']} Operand VA {entry['address']}, signed "
                     f"{8*entry['size']}-bit ({entry['fmt']}). Owns only the immediate, never the surrounding opcode/address. "
                     "Procedural camera logic, not a camera VM track. Export through Fujin as Hext.")
            add(entry["instruction_address"], text, kind="instruction", size=len(bytes.fromhex(entry["instruction_hex"])))
        else:
            is_model = entry["kind"] == "model"
            text += ("\nStandard 4-section battle creature container: skeleton, geometry, skeletal animation, optional trailer. "
                     "Container offsets are relative to its own base; native timing can coexist with file textures."
                     if is_model else "\nComplete PSX TIM; follow its CLUT/image block sizes. VRAM placement comes from TIM headers.")
            text += "\nIdentical bytes in a different resource remain an independent copy. Fingerprint: "+entry["sha256"]
            add(entry["address"], text, entry["id"], type_name="FF8EffectModelDirectory" if is_model else "FF8EffectTIMHeader", size=entry["size"])

    for key, profile in sorted(profiles.items(), key=lambda pair: int(pair[0])):
        effect, table = int(key), int(profile["table"], 16)
        pointers = [exe.u32(table+4*i) for i in range(327)]
        title = f"Effect {effect} ({names.get(effect, 'Unknown')}): MAG cinematic interpreter, with its own 327-entry opcode directory at 0x{table:X}."
        availability = "Disabled opcode indices (null or immediate RET): "+", ".join(f"0x{i:03X}" for i in profile["disabled"])
        add(table, title+"\n"+availability+"\nDo not classify this effect as a generic native timeline from initializer shape. VM opcode = word & 0x1FF; modifier = word >> 9. Runtime handlers and supported simulation are different questions.",
            f"MAG_{effect:03d}_CinematicOpcodeDirectory", type_name="FF8EffectCinematicDirectory", size=327*4)
        info = dispatch[key]
        add(info["logic_addr"], title+"\nNative initialization starts a file-supplied program; choreography is not entirely compiled into the exe. The audited root is mag%03d_b.00; resolve actual loader/stream references rather than assuming filename ownership." % (effect-1),
            f"MAG_{effect:03d}_CinematicInit", kind="function", size=8)
        add(info["fl_addr"], title+"\nDirect loader references: "+", ".join(info.get("files_loaded", []))+". Streamed/deferred resources are not fully enumerated by string extraction.",
            f"MAG_{effect:03d}_CinematicResourceLoader", kind="function", size=8)
        stage = pointers[0x39]
        add(stage, f"Effect {effect}, cinematic opcode 0x039 StageCameraAnim. High-bit modifier 8 starts the normal camera track at file_base + header.stage_camera_offset (+0x20). Other suboperations can drive cinematic camera bones. Presence of a handler alone does not prove script execution.",
            f"MAG_{effect:03d}_CineOp039_StageCameraAnim", kind="function", size=8)
        call = stage+0x40
        raw_offset = exe.offset(call)
        if raw_offset is None or exe.data[raw_offset] != 0xE8 or call+5+struct.unpack_from("<i", exe.data, raw_offset+1)[0] != 0x5099A0:
            raise ValueError(f"Stage-camera call guard failed for effect {effect}")
        add(call, f"Normal track argument is file_base + *(u32 *)(file_base + 0x20); not a static exe track. Effect {effect}. Camera bytecode and 16-bit cinematic bytecode are distinct VMs.", kind="instruction", size=5)
        references.append(dict(from_address=f"0x{table+4*0x39:X}", to_address=f"0x{stage:X}", type="offset"))
        for opcode_text, opcode in profile["overrides"].items():
            code, handler = int(opcode_text, 16), int(opcode["handler"], 16)
            if pointers[code] != handler:
                raise ValueError(f"Opcode pointer mismatch for effect {effect}, {opcode_text}")
            text = (f"Effect {effect}: opcode {opcode_text} {opcode['name']}. Total encoded byte length: {opcode['length']}.\n"
                    +opcode["semantics"]+"\nHigh bits: "+opcode["high_bits"]+"\n"
                    +"; ".join(f"operand {i}: {o['name']}" for i, o in enumerate(opcode["operands"]))
                    +"\nAvailability and encoding verified in native code; this variant is not simulated. "+opcode.get("notes", ""))
            for ref in opcode.get("refs", []):
                text += f"\nOperand word {ref['word']} is a relative {ref['kind']} reference, based at {ref['base']}."
            for condition in opcode.get("invalid_when", []):
                text += "\nInvalid when "+condition["condition"]+": "+condition["error"]
            add(handler, text, f"MAG_{effect:03d}_CineOp{code:03X}_{opcode['name']}", kind="function", size=8)
            references.append(dict(from_address=f"0x{table+4*code:X}", to_address=f"0x{handler:X}", type="offset"))

    for track in cameras["tracks"]:
        address = int(track["eng_address"], 16)
        raw = exe.offset(address)
        count, script, keyframes, size = struct.unpack_from("<4H", exe.data, raw)
        add(address, f"Effect {track['effect_id']} ({track['name']}): normal static camera track in exe data. Header: count={count}, script=+0x{script:X}, keyframe collection=+0x{keyframes:X}, total {size} bytes.\n"
            "Same relocatable camera format as the tracks embedded in MAG files and FFNx .bcam files. A same-byte sibling at another address remains independent. Hext must use this executable's language-specific address; a resized track requires FFNx .bcam export.",
            track["label"], type_name="FF8EffectCameraTrackHeader", size=size)

    for key, fact in facts.items():
        effect, info = int(key), dispatch[key]
        text = f"Effect {effect}: {names.get(effect, 'Unknown')}. "+fact.get("runtime", "Native effect")+". "+fact.get("note", "")
        for resource in fact.get("files", []):
            text += "\nVerified resource: "+resource["name"]+" ("+resource.get("kind", "file")+"). "+resource.get("note", "")
        text += "\nStorage and runtime are independent: file models do not imply file-driven choreography. No external file does not imply a free effect slot."
        add(info["logic_addr"], text, kind="function", size=8)

    add(0xA66470, "Disease Breath loader: opens MAG230_B.00 then MAG230_B.01. Script-file pointer stored at 0x2796AA4; companion pointer at 0x2796AA0. The root script is at file offset 0x58. At file offset 0x5A, words 0x1039 0x0000 invoke StageCameraAnim (modifier 8).", kind="function")
    add(0xA6C240, "Disease Breath normal camera track: MAG230_B.00 header +0x20 = 0x870; bytes [0x870,0x930), 192 bytes; header u16=(2,8,24,192). Camera script is 15 bytes plus one alignment byte. Collection: set 0 / slot 0, 3 blocks, 5 keyframe entries. This is a file camera, not an absent track.", kind="instruction")
    add(0x2796AA4, "Disease Breath: loaded MAG230_B.00 base pointer; its stage_camera_offset field (+0x20) locates the camera. File offsets are not IDB virtual addresses.", "g_MAG231_ScriptFile", type_name="FF8EffectPackedMAGHeader *")
    add(0x2796AA0, "Disease Breath: loaded MAG230_B.01 companion base pointer. Separate editable source image; do not alias it to .00.", "g_MAG231_CompanionFile")
    add(0x681630, "Carbuncle creature task combines skeletal animation, particles, native timing and procedural camera writes. Guarded camera immediate operands: 0x681D35 (s32 opening Y offset), 0x681D5E (s16 opening Z), 0x681D93 (s32 opening radius), 0x681DE2 (s32 middle radius), 0x681DE7 (sign-extended s8 angular step), 0x681F67 (s32 late radius). They are not a camera VM track.\nModel: 0x10B6F94. Body texture: second TIM in mag277.tim, file offset 172064. Direct camera preview cannot reproduce the entire native effect.", kind="function", size=8)
    add(0x683D10, "Carbuncle procedural camera orbit helper. Call sites push radius then signed angle step (cdecl stack order). Camera-facing/time-dependent native code; do not substitute camera VM semantics.", kind="function", size=8)
    add(0x6FE050, "Griever summon setup uses already-loaded battle actors; no dedicated mag068 creature asset. The boss creature is c0m122.dat. Camera setup has a normal static track, while model ownership is separate.", kind="function", size=8)
    add(0xC81774, "MagicList_Logic: 400 entries, effect ID is 1-based so entry is id-1. Native initializer does not identify a unique storage/runtime family. 58 audited effects use per-effect MAG cinematic interpreters.")
    add(0xC81DB8, "MagicList_TextureLoad: effect resource-loader callbacks, not necessarily texture-only. They may open .00/.01 packs, multiple files, no files, or defer streams. Filename ID-minus-one is a discovery convention, not proof of ownership.")
    return dict(schema_version=1, exe_sha256=SHA256, entries=sorted(entries.values(), key=lambda e: int(e["address"], 16)),
                references=references, type_declarations=TYPE_DECLARATIONS, member_comments=MEMBER_COMMENTS)


def apply_in_ida(plan, backup_folder=None):
    import ida_auto
    import ida_bytes
    import ida_funcs
    import ida_loader
    import ida_name
    import ida_nalt
    import ida_typeinf
    import ida_xref
    import idc
    if ida_nalt.retrieve_input_file_sha256().hex().lower() != plan["exe_sha256"]:
        raise ValueError("The current IDB does not match the audited English executable")
    # Complete all byte validation before saving/backing up or changing any annotations.
    for entry in plan["entries"]:
        if entry.get("check_size"):
            raw = ida_bytes.get_bytes(int(entry["address"], 16), entry["check_size"])
            if raw is None or hashlib.sha256(raw).hexdigest() != entry["check_sha256"]:
                raise ValueError("Current IDB bytes differ at "+entry["address"])
    idb = Path(ida_loader.get_path(ida_loader.PATH_TYPE_IDB))
    if not ida_loader.save_database(str(idb), 0):
        raise OSError("Could not save the current database; no annotations changed")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = Path(backup_folder or Path.home()/"Desktop/IDA_Backups") / ("FF8_EN_before_effect_audit_"+stamp)
    backup.mkdir(parents=True, exist_ok=False)
    copied = backup / idb.name
    shutil.copy2(idb, copied)
    def digest(path):
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
    if digest(idb) != digest(copied):
        raise OSError("Backup verification failed; no annotations changed")
    report = dict(idb=str(idb), backup=str(copied), backup_sha256=digest(copied), changes=[], warnings=[])
    for declaration in re.findall(r"typedef struct .*?}\s+\w+;", plan["type_declarations"], flags=re.S):
        type_name = re.search(r"typedef struct (\w+)", declaration)[1]
        tif = ida_typeinf.tinfo_t()
        if tif.get_named_type(None, type_name):
            if tif.get_size() != TYPE_SIZES[type_name]:
                raise ValueError("Existing audit type has an incompatible size: "+type_name)
        elif idc.parse_decls(declaration, idc.PT_SIL):
            raise ValueError("IDA rejected type "+type_name)
    for entry in plan["entries"]:
        ea = int(entry["address"], 16)
        old_name = ida_name.get_name(ea)
        desired = entry.get("name")
        generic = not old_name or re.match(r"^(?:sub_|off_|unk_|byte_|word_|dword_|qword_)", old_name) or re.fullmatch(r"MAG_?\d+_(?:UNKNOWN|UNK\d+)", old_name)
        if desired and (generic or old_name == desired):
            if not ida_name.set_name(ea, desired, ida_name.SN_CHECK | ida_name.SN_NOWARN):
                report["warnings"].append(f"Name retained at {entry['address']}: {old_name}")
        if entry["kind"] == "function" and ida_funcs.get_func(ea) is None:
            if not ida_funcs.add_func(ea):
                report["warnings"].append("Could not define function at "+entry["address"])
        old = ida_bytes.get_cmt(ea, False) or ""
        if not ida_bytes.set_cmt(ea, merge_comment(old, entry["comment"]), False):
            raise ValueError("Could not comment "+entry["address"])
        function = ida_funcs.get_func(ea)
        if function is not None and function.start_ea == ea:
            old = ida_funcs.get_func_cmt(function, True) or ""
            ida_funcs.set_func_cmt(function, merge_comment(old, entry["comment"]), True)
        if entry.get("type"):
            declaration = entry["type"]+" "+(ida_name.get_name(ea) or "audit_value")+";"
            if not idc.SetType(ea, declaration):
                report["warnings"].append("Could not apply type at "+entry["address"])
        report["changes"].append(dict(address=entry["address"], name=ida_name.get_name(ea), comment_verified=BEGIN in (ida_bytes.get_cmt(ea, False) or "")))
    for ref in plan["references"]:
        ida_xref.add_dref(int(ref["from_address"], 16), int(ref["to_address"], 16), ida_xref.dr_O | ida_xref.XREF_USER)
    # Member comments are also visible independently of any particular resource instance.
    for type_name, member, comment in plan["member_comments"]:
        tif = ida_typeinf.tinfo_t()
        if tif.get_named_type(None, type_name):
            udt = ida_typeinf.udt_type_data_t()
            if tif.get_udt_details(udt):
                for index, field in enumerate(udt):
                    if field.name == member:
                        tif.set_udm_cmt(index, merge_comment(field.cmt or "", comment))
    ida_auto.auto_wait()
    report["saved"] = bool(ida_loader.save_database(str(idb), 0))
    report_path = backup / "effect-update-report.json"
    report_path.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(f"Effect audit: {len(report['changes'])} addresses; {len(report['warnings'])} warnings. Saved={report['saved']}. Report: {report_path}")
    return report


if __name__ == "__main__":
    if "--emit-plan" in sys.argv:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--emit-plan", required=True)
        parser.add_argument("--exe")
        args = parser.parse_args()
        plan = build_plan(args.exe)
        Path(args.emit_plan).write_text(json.dumps(plan, indent=2)+"\n", encoding="utf-8")
        print(f"{len(plan['entries'])} annotated addresses, {len(plan['references'])} verified directory references")
    else:
        import ida_nalt
        apply_in_ida(build_plan(ida_nalt.get_input_file_path()))
