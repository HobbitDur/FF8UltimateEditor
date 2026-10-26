"""scene.out model: every field reads/writes its own bytes, undo/revert, byte-exact round-trip."""
import pytest

from FF8GameData.sceneout import ENCOUNTER_SIZE, NB_ENCOUNTER, EncounterRecord, SlotData, read_encounters
from JumboCactuar.jumbocactuarmanager import JumboCactuarManager, load_names


def synthetic_scene_out(count=NB_ENCOUNTER):
    """Every byte set (pattern by encounter and offset), so a field writing the wrong bytes shows."""
    return bytes((index * 7 + offset * 13) & 0xFF for index in range(count) for offset in range(ENCOUNTER_SIZE))


def test_record_fields_read_their_bytes():
    data = bytearray(ENCOUNTER_SIZE)
    data[0x00], data[0x01], data[0x02], data[0x03] = 12, 0b1000_0101, 0x3A, 0x15
    data[0x07] = 0b1010_0000          # slots 0 and 2 enabled (MSB = slot 0)
    data[0x06] = 0b0100_0000          # slot 1 not targetable
    data[0x08:0x0E] = (-100).to_bytes(2, "little", signed=True) + (5).to_bytes(2, "little") + (-3600).to_bytes(2, "little", signed=True)
    data[0x38] = 0x10 + 84            # Jumbo Cactuar
    data[0x40:0x78] = bytes(range(56))
    data[0x78] = 42
    record = EncounterRecord(data)
    assert record.stage_id == 12
    assert [record.flag(bit) for bit in range(8)] == [True, False, True, False, False, False, False, True]
    assert record.camera(0) == (3, 2) and record.camera(1) == (1, 5)
    assert record.slot_flag("enabled", 0) and not record.slot_flag("enabled", 1) and record.slot_flag("enabled", 2)
    assert record.slot_flag("not_targetable", 1)
    assert record.position(0) == (-100, 5, -3600)
    assert record.enemy_byte(0) == 0x10 + 84 and record.level(0) == 42
    assert record.unknown == bytes(range(56))
    assert record.to_bytes() == bytes(data)


def test_each_setter_only_touches_its_field():
    original = synthetic_scene_out(1)
    record = EncounterRecord(original)
    record.stage_id = 7
    record.set_flag(3, not record.flag(3))
    record.set_slot_flag("not_loaded", 5, not record.slot_flag("not_loaded", 5))
    record.set_position(4, (1, -2, 3))
    record.set_enemy_byte(6, 0x20)
    record.set_level(7, 99)
    changed = [offset for offset in range(ENCOUNTER_SIZE) if record.data[offset] != original[offset]]
    assert set(changed) <= {0x00, 0x01, 0x05, 0x08 + 24, 0x08 + 25, 0x08 + 26, 0x08 + 27, 0x08 + 28, 0x08 + 29,
                            0x38 + 6, 0x78 + 7}
    # the view the previews use reads the same values
    view = read_encounters(record.to_bytes())[0]
    assert view.stage_id == 7 and view.slots[4].position == (1, -2, 3) and view.slots[7].level == 99


def test_camera_keeps_the_unused_bit():
    record = EncounterRecord()
    record.set_camera_byte(0, 0x08)   # bit 3: not part of set/anim, never dropped
    record.set_camera(0, 2, 7)
    assert record.camera_byte(0) == 0x2F and record.camera(0) == (2, 7)


def test_slot_copy_carries_every_slot_field():
    record = EncounterRecord(synthetic_scene_out(1))
    slot = record.slot(2)
    record.set_slot(5, slot)
    assert record.slot(5) == slot
    assert record.slot(5) == SlotData(slot.enemy_byte, slot.level, slot.position, slot.enabled,
                                      slot.not_targetable, slot.not_visible, slot.not_loaded)


def test_names_cover_every_stage():
    stages, enemies = load_names()
    assert len(stages) == 163 and stages[1] == "Dollet Bridge"
    assert enemies[84] == "Jumbo Cactuar"


def test_load_save_is_byte_exact_with_trailing_bytes(tmp_path):
    data = synthetic_scene_out(3) + b"\x01\x02\x03"
    path = tmp_path / "scene.out"
    path.write_bytes(data)
    manager = JumboCactuarManager()
    manager.load_file(str(path))
    assert len(manager.records) == 3
    manager.save_file()
    assert path.read_bytes() == data


def test_undo_groups_one_field_and_revert():
    manager = JumboCactuarManager()
    manager.load_bytes(synthetic_scene_out(4))
    original = manager.records[1].to_bytes()
    for level in (1, 12, 123):   # typing 1, 2, 3 in the level box: one undo step
        manager.before_edit(1, "level0")
        manager.records[1].set_level(0, level)
    manager.before_edit(1, "stage")
    manager.records[1].stage_id = 9
    assert manager.modified_indices() == [1]
    assert manager.undo() == 1 and manager.records[1].stage_id == original[0]
    assert manager.records[1].level(0) == 123
    assert manager.undo() == 1 and manager.records[1].to_bytes() == original
    assert manager.undo() is None
    assert manager.redo() == 1 and manager.records[1].level(0) == 123
    manager.revert(1)
    assert not manager.modified_indices()
    assert manager.undo() == 1 and manager.records[1].level(0) == 123  # a revert is undoable too


def test_summary_lists_enabled_enemies():
    manager = JumboCactuarManager()
    record = EncounterRecord()
    record.stage_id = 1
    record.set_enemy_byte(0, 0x10 + 84)
    record.set_slot_flag("enabled", 0, True)
    record.set_enemy_byte(1, 0x10 + 2)   # not enabled: not listed
    manager.load_bytes(record.to_bytes())
    assert manager.summary(0) == "0000 Dollet Bridge: Jumbo Cactuar"


@pytest.mark.ff8data("extracted_files/battle/scene.out")
def test_real_scene_out_round_trip(tmp_path):
    source = "extracted_files/battle/scene.out"
    manager = JumboCactuarManager()
    manager.load_file(source)
    assert len(manager.records) == NB_ENCOUNTER
    with open(source, "rb") as file:
        assert manager.to_bytes() == file.read()
    assert "Jumbo Cactuar" in manager.summary(712)
