"""r0win.dat (battle victory sequence) manager.

r0win.dat is entry 766 of the battle file table, loaded by BS_R0win_PlayVictorySequence
(FF8_EN.exe 0x503040) when a battle is won. It carries:
 - Section 1: the victory fanfare, as an AKAO sample/instrument bank (PSX-only, the
   PC sound upload is stubbed) + the AKAO music sequence actually played
   (queued by BS_R0win_QueueVictoryFanfare 0x501A20, dispatched by
   BS_Music_ProcessCommand 0x501B60 through PlayMusic_SdMusicPlay),
 - Section 2: the victory camera, a standard BattleStageCameraData blob
   (played by BS_R0win_PlayVictoryCamera 0x5064F0),
 - Sections 3-8: one win-pose block per character that has a dedicated victory pose
   (Rinoa, Quistis, Irvine, Edea, Selphie, Kiros - mapped by com_id through
   R0win_WinPoseComIdMap 0xB8B7E0), bound onto the live entity by
   BS_BindEntityModelFromComData 0x5022C0.

Every section but the camera is a little offset table {u32 count; u32 offset[count];
u32 end} with `count` data blocks, offsets relative to the section start. A pose block
holds [0] a body animation section, [1] an AnimSeq byte-code section, and optionally
[2] a weapon animation section. The animation sections are the monster .dat section 3
format (1 animation, 60 frames in vanilla) and only decode against the right bone
count, which lives in the character's own dXc/dXw model - not in r0win.dat.

An unmodified load/save is byte-exact.
"""
import os
import struct

from FF8GameData.monsterdata import AnimationSection, BoneSection
from FF8GameData.dat.cameracollection import parse_camera_collection, CameraParseError

_UINT = struct.Struct("<I")


def _read_u32(data, offset):
    return _UINT.unpack_from(data, offset)[0]


def _pad4(data: bytes) -> bytes:
    remainder = len(data) % 4
    if remainder:
        return bytes(data) + b"\x00" * (4 - remainder)
    return bytes(data)


class R0winCharacter:
    """One entry of R0win_WinPoseComIdMap: which pose section drives which character,
    and the bone counts (from the character's own battle models) its animation
    sections decode against."""

    def __init__(self, section_id, name, com_id, body_bones, weapon_bones):
        self.section_id = section_id  # 1-based section number in the file (3..8)
        self.name = name
        self.com_id = com_id
        self.body_bones = body_bones
        self.weapon_bones = weapon_bones  # None: no weapon anim in the vanilla file


# Section order 3..8. Bone counts verified byte-exact against d4c009/d3c007/d2c006/
# d7c016/d5c011/d9c019 and the matching dXw weapon models.
R0WIN_CHARACTERS = [
    R0winCharacter(3, "Rinoa", 4, 32, 2),
    R0winCharacter(4, "Quistis", 3, 27, 9),
    R0winCharacter(5, "Irvine", 2, 34, 3),
    R0winCharacter(6, "Edea", 7, 35, None),
    R0winCharacter(7, "Selphie", 5, 25, 7),
    R0winCharacter(8, "Kiros", 9, 35, None),
]

# The characters missing from R0win_WinPoseComIdMap fall back to chain-transformation 18
# (their win pose comes from their own model): Squall(0), Zell(1), Seifer(6), Laguna(8),
# Ward(10).


def _parse_offset_table(data: bytes) -> list:
    """Split a {u32 count; u32 offset[count]; u32 end} section into its blocks."""
    if len(data) < 8:
        raise ValueError(f"Offset-table section too short ({len(data)} bytes)")
    count = _read_u32(data, 0)
    header_size = 4 + count * 4 + 4
    if count == 0 or count > 64 or len(data) < header_size:
        raise ValueError(f"Invalid offset-table block count {count}")
    offsets = [_read_u32(data, 4 + 4 * i) for i in range(count)]
    end = _read_u32(data, 4 + 4 * count)
    if offsets[0] != header_size:
        raise ValueError(f"First block offset 0x{offsets[0]:x} does not follow the "
                         f"header (expected 0x{header_size:x})")
    bounds = offsets + [end]
    if bounds != sorted(bounds) or end > len(data):
        raise ValueError("Offset-table blocks are not contiguous ascending")
    return [bytes(data[bounds[i]:bounds[i + 1]]) for i in range(count)]


def _build_offset_table(blocks: list) -> bytes:
    """Rebuild a {u32 count; u32 offset[count]; u32 end} section from its blocks."""
    blocks = [_pad4(block) for block in blocks]
    header_size = 4 + len(blocks) * 4 + 4
    data = bytearray(_UINT.pack(len(blocks)))
    position = header_size
    for block in blocks:
        data.extend(_UINT.pack(position))
        position += len(block)
    data.extend(_UINT.pack(position))
    for block in blocks:
        data.extend(block)
    return bytes(data)


class R0winPose:
    """One character's win-pose section: body animation, AnimSeq byte-code, and an
    optional weapon animation, each kept as raw block bytes."""

    def __init__(self, character: R0winCharacter, blocks: list):
        if len(blocks) not in (2, 3):
            raise ValueError(f"Pose section {character.section_id} has {len(blocks)} "
                             "blocks, expected 2 or 3")
        self.character = character
        self.body_anim = blocks[0]
        self.seq_block = blocks[1]
        self.weapon_anim = blocks[2] if len(blocks) == 3 else None

    def blocks(self) -> list:
        result = [self.body_anim, self.seq_block]
        if self.weapon_anim is not None:
            result.append(self.weapon_anim)
        return result

    def get_seq_bytecode(self) -> bytes:
        """The AnimSeq byte-code, without its {u16 count; u16 offset[]} section header."""
        if len(self.seq_block) < 4:
            return b""
        count = struct.unpack_from("<H", self.seq_block, 0)[0]
        first = struct.unpack_from("<H", self.seq_block, 2)[0]
        if count != 1 or first > len(self.seq_block):
            return bytes(self.seq_block[4:])
        return bytes(self.seq_block[first:])

    def set_seq_bytecode(self, bytecode: bytes):
        self.seq_block = _pad4(struct.pack("<HH", 1, 4) + bytes(bytecode))

    @staticmethod
    def anim_frame_count(anim_block: bytes):
        """Frame count of a single-animation section block, or None if not readable."""
        if len(anim_block) < 9:
            return None
        nb_anim = _read_u32(anim_block, 0)
        if nb_anim != 1:
            return None
        offset = _read_u32(anim_block, 4)
        if offset >= len(anim_block):
            return None
        return anim_block[offset]


class WattsManager:
    """r0win.dat editor logic (Qt-free)."""

    PART_FANFARE_BANK = "fanfare-bank"  # S1 block 0: AKAO instrument bank (PSX upload)
    PART_FANFARE_SEQ = "fanfare-seq"  # S1 block 1: AKAO score, the fanfare heard in game
    PART_CAMERA = "camera"
    POSE_PARTS = ("body", "seq", "weapon")

    def __init__(self, game_data=None):
        self.game_data = game_data
        self.file_path = ""
        self.fanfare_bank = b""
        self.fanfare_sequence = b""
        # Section 2 is a full battle camera blob: an 8-byte header, then the camera
        # setting (the camera-VM byte-code, kept raw), then the camera animation
        # collection (the keyframed motions, parsed into an editable model).
        self.camera_setting = b""            # the camera-sequence byte-code (raw)
        self.camera_collection = None        # CameraCollection over the collection half
        self._camera_collection_raw = b""    # kept when the collection does not parse
        self.poses = []  # List[R0winPose], in section order 3..8

    # ------------------------------------------------------------------ loading
    def load_file(self, file_path):
        with open(file_path, "rb") as in_file:
            self._parse(in_file.read())
        self.file_path = file_path

    def _parse(self, data: bytes):
        if len(data) < 44:
            raise ValueError("File too short to be r0win.dat")
        nb_section = _read_u32(data, 0)
        if nb_section != 8:
            raise ValueError(f"Expected 8 sections, found {nb_section} - not r0win.dat")
        offsets = [_read_u32(data, 4 + 4 * i) for i in range(9)]
        bounds = offsets + [len(data)]
        if bounds != sorted(bounds) or offsets[-1] > len(data):
            raise ValueError("Section offsets are not contiguous ascending")
        sections = [data[offsets[i]:offsets[i + 1]] for i in range(8)]

        fanfare_blocks = _parse_offset_table(sections[0])
        if len(fanfare_blocks) != 2:
            raise ValueError(f"Fanfare section has {len(fanfare_blocks)} blocks, expected 2")
        self.fanfare_bank, self.fanfare_sequence = fanfare_blocks
        self._set_camera(bytes(sections[1]))
        self.poses = [R0winPose(character, _parse_offset_table(sections[character.section_id - 1]))
                      for character in R0WIN_CHARACTERS]

    # ------------------------------------------------------------------- camera
    def _set_camera(self, blob: bytes):
        """Split a full battle camera blob into its setting (raw byte-code) and its
        animation collection (parsed into an editable model, or kept raw if it does not
        read as a collection)."""
        if len(blob) < 8:
            raise ValueError("Camera blob too short")
        pointer_count, rel_setting, rel_collection, _size = struct.unpack_from("<4H", blob, 0)
        if pointer_count != 2 or rel_setting != 8 or rel_collection > len(blob):
            raise ValueError("Not a battle camera blob (bad header)")
        self.camera_setting = bytes(blob[rel_setting:rel_collection])
        collection_bytes = bytes(blob[rel_collection:])
        try:
            self.camera_collection = parse_camera_collection(collection_bytes)
            self._camera_collection_raw = b""
        except CameraParseError:
            self.camera_collection = None
            self._camera_collection_raw = collection_bytes

    def _camera_collection_bytes(self) -> bytes:
        if self.camera_collection is not None:
            return bytes(self.camera_collection.get_bytes())
        return self._camera_collection_raw

    def camera_bytes(self) -> bytes:
        """Rebuild the full camera blob from the setting + (possibly edited) collection.
        Byte-identical to the original when nothing was changed."""
        collection = self._camera_collection_bytes()
        rel_collection = 8 + len(self.camera_setting)
        total = rel_collection + len(collection)
        header = struct.pack("<4H", 2, 8, rel_collection, total)
        return header + self.camera_setting + collection

    @property
    def camera(self) -> bytes:
        return self.camera_bytes()

    @camera.setter
    def camera(self, blob: bytes):
        self._set_camera(bytes(blob))

    # ------------------------------------------------------------------- saving
    def to_bytes(self) -> bytes:
        sections = [_build_offset_table([self.fanfare_bank, self.fanfare_sequence]),
                    _pad4(self.camera_bytes())]
        sections.extend(_build_offset_table(pose.blocks()) for pose in self.poses)
        header_size = 4 + 8 * 4 + 4
        data = bytearray(_UINT.pack(8))
        position = header_size
        for section in sections:
            data.extend(_UINT.pack(position))
            position += len(section)
        data.extend(_UINT.pack(position))  # EOF entry, runtime workspace base
        for section in sections:
            data.extend(section)
        return bytes(data)

    def save_file(self, file_path=""):
        if not self.poses:
            raise ValueError("No file loaded")
        if not file_path:
            file_path = self.file_path
        with open(file_path, "wb") as out_file:
            out_file.write(self.to_bytes())

    # ------------------------------------------------------------------- parts
    def part_keys(self) -> list:
        keys = [self.PART_FANFARE_BANK, self.PART_FANFARE_SEQ, self.PART_CAMERA]
        for pose in self.poses:
            name = pose.character.name.lower()
            keys.append(f"{name}-body")
            keys.append(f"{name}-seq")
            if pose.weapon_anim is not None:
                keys.append(f"{name}-weapon")
        return keys

    def get_pose(self, character_name: str) -> R0winPose:
        for pose in self.poses:
            if pose.character.name.lower() == character_name.lower():
                return pose
        raise ValueError(f"Unknown character '{character_name}' - r0win.dat only has "
                         + ", ".join(c.name for c in R0WIN_CHARACTERS))

    def export_part(self, part_key: str) -> bytes:
        return bytes(self._part_ref(part_key)[0])

    def import_part(self, part_key: str, data: bytes):
        _, setter, validate = self._part_ref(part_key)
        canonical = validate(data)
        setter(canonical if canonical is not None else _pad4(data))

    def _part_ref(self, part_key: str):
        """(current bytes, setter, validator) for a part key."""
        part_key = part_key.lower()
        if part_key == self.PART_FANFARE_BANK:
            return (self.fanfare_bank, lambda d: setattr(self, "fanfare_bank", d),
                    self._validate_akao)
        if part_key == self.PART_FANFARE_SEQ:
            return (self.fanfare_sequence, lambda d: setattr(self, "fanfare_sequence", d),
                    self._validate_akao)
        if part_key == self.PART_CAMERA:
            return self.camera, lambda d: setattr(self, "camera", d), self._validate_camera
        if "-" not in part_key:
            raise ValueError(f"Unknown part '{part_key}' (see the info command for the list)")
        character_name, _, sub_part = part_key.rpartition("-")
        pose = self.get_pose(character_name)
        if sub_part == "body":
            return (pose.body_anim, lambda d: setattr(pose, "body_anim", d),
                    lambda d: self.canonicalize_animation_block(d, pose.character.body_bones))
        if sub_part == "seq":
            return pose.seq_block, lambda d: setattr(pose, "seq_block", d), self._validate_seq_block
        if sub_part == "weapon":
            if pose.weapon_anim is None:
                raise ValueError(f"{pose.character.name} has no weapon animation in r0win.dat")
            return (pose.weapon_anim, lambda d: setattr(pose, "weapon_anim", d),
                    lambda d: self.canonicalize_animation_block(d, pose.character.weapon_bones))
        raise ValueError(f"Unknown pose part '{sub_part}', expected body, seq or weapon")

    # -------------------------------------------------------------- validation
    @staticmethod
    def _validate_akao(data: bytes):
        if len(data) < 8 or data[:4] != b"AKAO":
            raise ValueError("Not an AKAO block (missing 'AKAO' magic)")

    @staticmethod
    def _validate_camera(data: bytes):
        if len(data) < 8:
            raise ValueError("Camera blob too short")
        pointer_count, rel_setting, rel_collection, _size = struct.unpack_from("<4H", data, 0)
        if pointer_count != 2 or rel_setting != 8 or rel_collection > len(data):
            raise ValueError("Not a battle camera blob (bad header)")
        # Return the blob unchanged so import uses it verbatim (padding it would corrupt
        # the collection's trailing eof word).
        return bytes(data)

    @staticmethod
    def _validate_seq_block(data: bytes):
        if len(data) < 4 or struct.unpack_from("<H", data, 0)[0] != 1:
            raise ValueError("AnimSeq block must hold exactly 1 sequence "
                             "({u16 1; u16 4; byte-code})")

    @staticmethod
    def synthetic_bone_section(nb_bone: int) -> BoneSection:
        """A BoneSection with the right bone count and neutral bones: r0win.dat has no
        skeleton of its own, the real one lives in the character's dXc/dXw model."""
        bone_section = BoneSection()
        bone_section.analyze(bytes([nb_bone]) + b"\x00" * 15 + b"\x00" * 48 * nb_bone)
        return bone_section

    @classmethod
    def canonicalize_animation_block(cls, data: bytes, nb_bone: int) -> bytes:
        """Decode the block as a single-animation section against nb_bone bones and
        re-encode it, so a wrong-skeleton or corrupt animation is refused instead of
        playing garbage in game. The re-encode differs from the input only in the bit
        stream's alignment slack bits (zero-filled by design, the engine never reads
        them), so a canonical block - all vanilla r0win.dat blocks are - passes through
        byte-identical. A mismatch anywhere else means the frame data itself did not
        survive the decode, i.e. the bone count is wrong."""
        try:
            animation_section = AnimationSection()
            animation_section.analyze(bytes(data), cls.synthetic_bone_section(nb_bone))
            rebuilt = bytes(animation_section.to_binary())
        except Exception as error:
            raise ValueError(f"Not a valid animation section for {nb_bone} bones: {error}")
        padded = _pad4(data)
        if len(rebuilt) != len(padded) or any(
                old != new and (old ^ new) & new for old, new in zip(padded, rebuilt)):
            # A slack-bit zeroing can only CLEAR bits of the last stream byte; any byte
            # where the re-encode SETS a bit the input did not have is real corruption.
            raise ValueError(f"Animation block does not decode against {nb_bone} "
                             "bones (wrong skeleton?)")
        return rebuilt

    # ------------------------------------------------------- higher level edits
    def import_animation_from_dat(self, character_name: str, part: str, dat_path: str,
                                  anim_id: int):
        """Replace a pose animation with animation `anim_id` of a battle .dat model
        (monster c0m / character dXc / weapon dXw - section 3 is the animation section
        in all of them). The source model must have the same skeleton as the character,
        in practice the character's own dXc (body) or dXw (weapon) file."""
        pose = self.get_pose(character_name)
        if part == "weapon" and pose.weapon_anim is None:
            raise ValueError(f"{pose.character.name} has no weapon animation in r0win.dat")
        if part not in ("body", "weapon"):
            raise ValueError(f"Part must be body or weapon, not '{part}'")
        animation = self._extract_dat_animation(dat_path, anim_id)
        nb_bone = pose.character.body_bones if part == "body" else pose.character.weapon_bones
        block = self.canonicalize_animation_block(struct.pack("<II", 1, 8) + animation,
                                                  nb_bone)
        if part == "body":
            pose.body_anim = block
        else:
            pose.weapon_anim = block

    @staticmethod
    def _extract_dat_animation(dat_path: str, anim_id: int) -> bytes:
        with open(dat_path, "rb") as in_file:
            data = in_file.read()
        nb_section = _read_u32(data, 0) + 1
        section_pos = [_read_u32(data, 4 + 4 * i) for i in range(nb_section)]
        if len(section_pos) < 4:
            raise ValueError(f"{os.path.basename(dat_path)} has no animation section")
        anim_start, anim_end = section_pos[2], section_pos[3]
        section = data[anim_start:anim_end]
        nb_anim = _read_u32(section, 0)
        if not 0 <= anim_id < nb_anim:
            raise ValueError(f"{os.path.basename(dat_path)} has {nb_anim} animations, "
                             f"id {anim_id} is out of range")
        offsets = [_read_u32(section, 4 + 4 * i) for i in range(nb_anim)]
        following = [offset for offset in offsets if offset > offsets[anim_id]]
        end = min(following) if following else len(section)
        return bytes(section[offsets[anim_id]:end])

    def get_fanfare_akao_id(self) -> int:
        """The AKAO id of the fanfare sequence. On PC this byte is the ONLY part of
        Section 1 the game reads: Music_PlayFromAKAO plays DirectMusic song id
        (akao_id - 1), so changing it changes the victory music."""
        if len(self.fanfare_sequence) < 5:
            raise ValueError("Fanfare sequence too short")
        return self.fanfare_sequence[4]

    def set_fanfare_akao_id(self, akao_id: int):
        if not 1 <= akao_id <= 255:
            raise ValueError("AKAO id must be 1-255 (PC song id = AKAO id - 1)")
        if len(self.fanfare_sequence) < 5:
            raise ValueError("Fanfare sequence too short")
        sequence = bytearray(self.fanfare_sequence)
        sequence[4] = akao_id
        self.fanfare_sequence = bytes(sequence)

    # ------------------------------------------------------------------ camera info
    def camera_summary(self) -> dict:
        """Structure of the Section 2 camera: the setting (VM) size and, per set, the
        keyframe count of each of its 8 animation slots."""
        collection = self.camera_collection
        sets = []
        if collection is not None:
            for camera_set in collection.sets:
                slots = []
                for animation in camera_set.animations:
                    frame_count = sum(len(block.frames) for block in animation.blocks)
                    slots.append({
                        "slot": animation.slot,
                        "empty": animation.empty,
                        "blocks": len(animation.blocks),
                        "frames": frame_count,
                    })
                sets.append({"index": camera_set.index, "slots": slots})
        return {
            "setting_size": len(self.camera_setting),
            "collection_parsed": collection is not None,
            "collection_size": len(self._camera_collection_bytes()),
            "nb_set": len(collection.sets) if collection is not None else 0,
            "sets": sets,
        }

    # -------------------------------------------------------------------- info
    def get_summary(self) -> dict:
        camera = self.camera_summary()
        camera_sets = [len([s for s in cam_set["slots"] if not s["empty"]] or cam_set["slots"])
                       for cam_set in camera["sets"]]
        poses = []
        for pose in self.poses:
            poses.append({
                "name": pose.character.name,
                "com_id": pose.character.com_id,
                "section_id": pose.character.section_id,
                "body_size": len(pose.body_anim),
                "body_frames": R0winPose.anim_frame_count(pose.body_anim),
                "body_bones": pose.character.body_bones,
                "seq_size": len(pose.seq_block),
                "seq_bytecode": pose.get_seq_bytecode(),
                "weapon_size": len(pose.weapon_anim) if pose.weapon_anim is not None else None,
                "weapon_frames": (R0winPose.anim_frame_count(pose.weapon_anim)
                                  if pose.weapon_anim is not None else None),
                "weapon_bones": pose.character.weapon_bones,
            })
        return {
            "fanfare_seq_size": len(self.fanfare_sequence),
            "fanfare_bank_size": len(self.fanfare_bank),
            "fanfare_akao_id": (self.fanfare_sequence[4]
                                if len(self.fanfare_sequence) >= 5 else None),
            "camera_size": len(self.camera_bytes()),
            "camera_sets": camera_sets,
            "camera": camera,
            "poses": poses,
        }

    def describe_seq(self, character_name: str) -> str:
        """Disassemble a character's AnimSeq byte-code (needs game_data with
        anim sequence data loaded)."""
        if self.game_data is None:
            raise ValueError("No GameData available for sequence disassembly")
        if not self.game_data.anim_sequence_data_json:
            self.game_data.load_anim_sequence_data()
        from FF8GameData.dat.sequenceanalyser import SequenceAnalyser
        bytecode = self.get_pose(character_name).get_seq_bytecode()
        return SequenceAnalyser(self.game_data, None, bytearray(bytecode)).get_text()
