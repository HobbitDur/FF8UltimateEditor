"""Skeleton and animation edits of a battle model embedded in a MAG file, in place.

The model is a standard battle .dat skeleton (section 1), geometry (2) and animation (3) stored
inside the MAG (an embedded object of a packed MAG, or the model of an indexed container). It is
decoded by Ifrit's code (IfritManager through Fujin.creature.build_dat), and edits go back as byte
patches of the MAG, which keeps its size - the objects and tables after a model are addressed by
absolute offsets the engine reads as they are, so a model section cannot grow:

 - a bone (length, rotation) is a fixed 48-byte entry: written in place;
 - an animation is a bit-stream of per-frame deltas (FF8GameData.monsterdata.Animation). Only
   the edited animation is re-encoded; every other one keeps its exact bytes, and the animations
   are laid out again in the section with their offset table. The section's slack (the bytes
   after the last animation's bits, and the alignment tails) is what an edited animation may
   grow into; one that would need more is refused with the number of bytes missing.

Untouched, nothing is rewritten: every vanilla model gives its own bytes back (tested).
"""
import os
import struct
import tempfile

from FF8GameData.monsterdata import BitReader

BONE_HEADER_SIZE = 16
BONE_SIZE = 48


def _fits(delta, bits):
    return -(1 << (bits - 1)) <= delta < (1 << (bits - 1))


def _smallest(delta, sizes):
    return next((index for index, bits in enumerate(sizes) if _fits(delta, bits)), len(sizes) - 1)


def refit_frame_types(animation, frame_index):
    """After frame `frame_index` changed, give its values (and the next frame's, whose deltas
    changed too) a storage size that holds their new delta, keeping the stored one when it still
    does - so an edit changes as few bits as possible."""
    frames = animation.frames
    for index in (frame_index, frame_index + 1):
        if not 0 <= index < len(frames):
            continue
        frame, previous = frames[index], frames[index - 1] if index else None
        for axis in range(3):
            position = frame.position[axis]
            delta = position.get_pos_raw() - (previous.position[axis].get_pos_raw() if previous else 0)
            if BitReader.POSITION_READ_HELPER[position.position_type_bits] < 16 and \
                    not _fits(delta, BitReader.POSITION_READ_HELPER[position.position_type_bits]):
                position.position_type_bits = _smallest(delta, BitReader.POSITION_READ_HELPER)
        for bone in range(len(frame.rotation_vector_data)):
            for axis in range(3):
                rotation = frame.rotation_vector_data[bone][axis]
                before = int(previous.rotation_vector_data[bone][axis].get_rotate_raw()) if previous else 0
                delta = int(rotation.get_rotate_raw()) - before
                if not rotation.is_rotation_type_available:
                    if delta:
                        rotation.is_rotation_type_available = True
                        rotation.rotation_type_bits = _smallest(delta, BitReader.ROTATION_READ_HELPER)
                elif not _fits(delta, BitReader.ROTATION_READ_HELPER[rotation.rotation_type_bits]):
                    rotation.rotation_type_bits = _smallest(delta, BitReader.ROTATION_READ_HELPER)


class EmbeddedModel:
    """One battle model inside a MAG byte image, decoded for editing.

    sections: absolute offsets of its skeleton, geometry and animation sections; end: the end of
    the animation section (the model's end)."""

    def __init__(self, data, sections, end):
        self.data = bytes(data)
        self.skeleton, self.geometry, self.animation = sections
        self.end = end
        self.enemy = self._parse()
        self.edited = set()               # animations re-encoded by the next patch

    def _parse(self):
        from Fujin.creature import build_dat
        from Ifrit.ifritmanager import IfritManager
        raw = [self.data[self.skeleton:self.geometry], self.data[self.geometry:self.animation],
               self.data[self.animation:self.end]]
        path = os.path.join(tempfile.gettempdir(), f"fujin_model_edit_{os.getpid()}_{id(self)}.dat")
        with open(path, "wb") as file:
            file.write(build_dat(raw))
        try:
            manager = IfritManager()
            enemy = manager.parse_file(path)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        manager.enemy = enemy
        self.manager = manager
        return enemy

    @property
    def bones(self):
        return self.enemy.bone_data.bones

    @property
    def animations(self):
        return self.enemy.animation_data.animations

    # ------------------------------------------------------------------ skeleton
    def bone_offset(self, index):
        return self.skeleton + BONE_HEADER_SIZE + BONE_SIZE * index

    def set_bone(self, index, length=None, rotation=None):
        """(offset, bytes) of bone `index` with a new length and/or (x, y, z) rotation (raw units:
        2048 per unit of length, 4096 per turn)."""
        bone = self.bones[index]
        if length is not None:
            if not -32768 <= length <= 32767:
                raise ValueError("a bone length is a 16-bit value (-32768 to 32767)")
            bone.set_size_raw(int(length))
        if rotation is not None:
            if any(not -32768 <= value <= 32767 for value in rotation):
                raise ValueError("a bone rotation is a 16-bit value")
            bone._rotX, bone._rotY, bone._rotZ = (int(value) for value in rotation)
        return self.bone_offset(index), bytes(bone.get_byte())

    # ------------------------------------------------------------------ animations
    def _animation_slices(self):
        """The section's animations as their stored bytes, each up to the next one's offset."""
        section = self.data[self.animation:self.end]
        count = struct.unpack_from("<I", section)[0]
        offsets = list(struct.unpack_from(f"<{count}I", section, 4))
        ends = offsets[1:] + [len(section)]
        return [section[start:stop] for start, stop in zip(offsets, ends)]

    def set_frame(self, animation, frame, rotations=None, position=None):
        """Change frame `frame` of animation `animation`: rotations {bone: (x, y, z) raw}, position
        (x, y, z) raw root position. The animation is re-encoded by animation_patch()."""
        target = self.animations[animation].frames[frame]
        for bone, values in (rotations or {}).items():
            for axis, value in enumerate(values):
                target.rotation_vector_data[bone][axis].rotate_raw(int(value))
        if position is not None:
            for axis, value in enumerate(position):
                target.position[axis].set_pos_raw(int(value))
        refit_frame_types(self.animations[animation], frame)
        self.edited.add(animation)

    def _cores(self, slices):
        """Each animation's own bytes: its slice without the tail the game never reads (the
        bytes between its bit-stream's last byte and the next animation)."""
        return [piece[:len(piece) - len(animation.original_tail)] if animation.original_tail else piece
                for piece, animation in zip(slices, self.animations)]

    def animation_patch(self):
        """(offset, bytes) of the whole animation section with the edited animations re-encoded,
        the others byte for byte. An edited animation that fits its old place keeps every offset;
        a longer one moves the next animations up into the section's slack (the tails the game
        never reads). ValueError when even that is not enough."""
        slices = self._animation_slices()
        encoded = {}
        for index in self.edited:
            animation = self.animations[index]
            tail, animation.original_tail = animation.original_tail, b""
            try:
                encoded[index] = bytes(animation.to_binary())
            finally:
                animation.original_tail = tail
        size = self.end - self.animation
        header = 4 + 4 * len(slices)
        if all(len(data) <= len(slices[index]) for index, data in encoded.items()):
            pieces = [encoded[index] + bytes(len(piece) - len(encoded[index])) if index in encoded else piece
                      for index, piece in enumerate(slices)]
        else:
            pieces = [encoded.get(index, core) for index, core in enumerate(self._cores(slices))]
        needed = header + sum(len(piece) for piece in pieces)
        if needed > size:
            raise ValueError(f"the animation needs {needed - size} more bytes than its section has "
                             f"({size}): the MAG keeps its size - change fewer values or smaller steps")
        out = bytearray(struct.pack("<I", len(pieces)))
        position = header
        for piece in pieces:
            out += struct.pack("<I", position)
            position += len(piece)
        for piece in pieces:
            out += piece
        out += bytes(size - len(out))
        return self.animation, bytes(out)

    def free_bytes(self):
        """Bytes an edited animation can grow by: the section's slack (the tails the game never reads)."""
        slices = self._animation_slices()
        return (self.end - self.animation) - (4 + 4 * len(slices)) - sum(len(core) for core in self._cores(slices))
