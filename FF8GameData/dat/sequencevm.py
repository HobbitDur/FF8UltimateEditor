"""What makes the byte-code walker VM-specific: one spec object, two instances.

The battle engine runs the SAME byte-code VM for two different things:
- entity animation sequences (monster section 5 / weapon section 4), and
- camera sequences (monster section 6 / character section 5).

The arithmetic op codes (C0-E5) and the jumps (E6-F3) are byte-for-byte identical between
the two - `computeAnimationSequence` @0x50DB40 is literally the same function reused. What
differs is only:
  - the set of action op codes below 0xC0 (entity: ~0x00-0xBF; camera: 00-09);
  - whether a bare op code < 0x80 means "play animation <op code>" (entity yes, camera no);
  - the handful of variable-size op codes (entity: FF-lists, sound, hit-effect, Renzokuken;
    camera: none, every action op code is fixed size);
  - which json tables the C3/E5 special op codes read from and write to.

SequenceVM captures exactly those differences and nothing else, so sequencecommand,
sequenceanalyser, sequencecodec and the IfritSeq/IfritCameraSeq widgets are all driven by
whichever VM they are handed, with a different json underneath. The entity spec reproduces
byte-for-byte what IfritSeq did before this was factored out (see tests/test_seq_golden.py
and tests/test_seq_command.py, which still pass game_data and get the entity VM).

Callers that only have a GameData keep passing it: as_sequence_vm() normalises a GameData to
its (cached) entity VM, so the whole entity code path - loop detector, splitter, Watts, the
tests - is untouched. Only the camera path builds and passes a camera VM explicitly.
"""

# Entity (animation-sequence) VM specifics. These lived as module constants in
# sequencecommand before; they are the op codes whose parameter length is not simply the
# json `size` field but depends on the op code family or its own parameters.
_ENTITY_ANIMATION_OP_CODE_MAX = 0x80  # op code < this IS the animation id it plays
_ENTITY_ASYNC_ANIM_OP_CODE = 0xA0     # A0 XX plays animation XX without pausing the sequence
_ENTITY_FF_LIST_OPS = (0x99, 0xB1, 0x9F)          # parameter list terminated by an FF byte
_ENTITY_FF_LIST_WITH_BONE_OPS = (0x99, 0xB1)      # ...preceded by one bone id byte
_ENTITY_SOUND_OPS = (0x97, 0x98, 0xB5, 0xB6, 0xB8)  # sound id, flag, channel mask if flag&2
_ENTITY_HIT_EFFECT_OPS = (0xB0, 0xB4)             # effect id, flag, then flag-selected bytes
_ENTITY_RENZOKUKEN_OP = 0xAB                       # two parameter bytes, then plain op codes
_ENTITY_RENZOKUKEN_SIZE = 2


class SequenceVM:
    """The policy the byte-code walker needs to decode one flavour of sequence.

    Everything VM-specific lives here; the walker, analyser, codec and widgets carry no
    hard-coded op code family any more, they ask the VM. Build one with entity_sequence_vm()
    or camera_sequence_vm() rather than by hand.
    """

    def __init__(self, data_json, *, animation_op_code_max=0, async_anim_op_code=None,
                 ff_list_ops=(), ff_list_with_bone_ops=(), sound_ops=(), hit_effect_ops=(),
                 renzokuken_op=None, renzokuken_size=2, name="sequence"):
        self.data_json = data_json
        # Op codes strictly below this play "animation <op code>"; 0 means the VM has no
        # animation-by-op-code range at all (the camera VM: its 00 is a real action op code).
        self.animation_op_code_max = animation_op_code_max
        self.async_anim_op_code = async_anim_op_code
        self.ff_list_ops = tuple(ff_list_ops)
        self.ff_list_with_bone_ops = tuple(ff_list_with_bone_ops)
        self.sound_ops = tuple(sound_ops)
        self.hit_effect_ops = tuple(hit_effect_ops)
        self.renzokuken_op = renzokuken_op
        self.renzokuken_size = renzokuken_size
        self.name = name
        self._op_code_info_by_code = None  # built lazily from data_json
        self._func_name_table = None       # sequencecodec cache, per VM (names differ)

    def op_code_info(self, op_code: int):
        """The json entry describing an op code, or None. Animation op codes (when the VM has
        an animation range) all fold to the shared 0x00 'play animation' entry."""
        if self._op_code_info_by_code is None:
            self._op_code_info_by_code = {element["op_code"]: element
                                          for element in self.data_json["op_code_info"]}
        searched = 0x00 if op_code < self.animation_op_code_max else op_code
        return self._op_code_info_by_code.get(searched)

    def op_code_size(self, op_code: int):
        info = self.op_code_info(op_code)
        return None if info is None else info["size"]

    def is_animation(self, op_code: int) -> bool:
        """A bare op code that IS the animation id it plays. Always False on a VM without an
        animation range (camera)."""
        return op_code < self.animation_op_code_max


def entity_sequence_vm(game_data) -> SequenceVM:
    """The animation-sequence VM IfritSeq edits (anim_sequence_info.json)."""
    return SequenceVM(game_data.anim_sequence_data_json,
                      animation_op_code_max=_ENTITY_ANIMATION_OP_CODE_MAX,
                      async_anim_op_code=_ENTITY_ASYNC_ANIM_OP_CODE,
                      ff_list_ops=_ENTITY_FF_LIST_OPS,
                      ff_list_with_bone_ops=_ENTITY_FF_LIST_WITH_BONE_OPS,
                      sound_ops=_ENTITY_SOUND_OPS, hit_effect_ops=_ENTITY_HIT_EFFECT_OPS,
                      renzokuken_op=_ENTITY_RENZOKUKEN_OP,
                      renzokuken_size=_ENTITY_RENZOKUKEN_SIZE, name="entity")


def camera_sequence_vm(game_data) -> SequenceVM:
    """The camera VM (camera_sequence_info.json): opcodes 00-09, no animation range, no
    variable-size families - every action op code is fixed size from the json."""
    return SequenceVM(game_data.camera_sequence_data_json,
                      animation_op_code_max=0, async_anim_op_code=None, name="camera")


def as_sequence_vm(game_data_or_vm) -> SequenceVM:
    """A SequenceVM from either a SequenceVM (returned as-is) or a GameData (its cached
    entity VM). This is what keeps every entity caller that passes game_data unchanged."""
    if isinstance(game_data_or_vm, SequenceVM):
        return game_data_or_vm
    game_data = game_data_or_vm
    vm = getattr(game_data, "_entity_sequence_vm_cache", None)
    if vm is None:
        vm = entity_sequence_vm(game_data)
        try:
            game_data._entity_sequence_vm_cache = vm
        except AttributeError:
            pass  # a game_data that does not accept attributes: rebuild each time
    return vm
