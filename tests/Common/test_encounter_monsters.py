"""The check box per monster every battle preview shares: by default what scene.out has there at the battle's start."""
import pytest

from FF8GameData.sceneout import ENCOUNTER_SIZE, Encounter, EncounterRecord


def _record():
    """Slot 0 there; slot 1 enabled but not loaded; slot 2 not enabled, for a script to bring in; the others empty."""
    record = EncounterRecord(bytes(ENCOUNTER_SIZE))
    for slot in range(8):
        record.set_slot_flag("enabled", slot, slot < 2)
        record.set_slot_flag("not_loaded", slot, slot == 1)
    record.data[0x38:0x3B] = bytes((0x10 + 71, 0x10 + 72, 0x10 + 73))
    record.data[0x3B:0x40] = bytes((0x10,)) * 5
    return record


def test_an_encounter_names_its_monsters_there_or_not():
    encounter = Encounter(3, _record().to_bytes())
    assert [slot.slot_index for slot in encounter.monster_slots()] == [0, 1, 2]
    assert [slot.present for slot in encounter.monster_slots()] == [True, False, False]


def test_the_check_boxes_default_to_scene_out_and_keep_your_picks(qapp):
    from Common.encountermonsters import EncounterMonsterChecks
    checks = EncounterMonsterChecks()
    encounter = Encounter(3, _record().to_bytes())
    checks.show_encounter(encounter)
    assert [slot.slot_index for slot in checks.present_slots()] == [0]
    changes = []
    checks.changed.connect(lambda: changes.append(1))
    checks._checks[2].setChecked(True)
    assert changes == [1] and [slot.slot_index for slot in checks.present_slots()] == [0, 2]
    checks.show_encounter(Encounter(3, _record().to_bytes()))          # the same encounter read again
    assert [slot.slot_index for slot in checks.present_slots()] == [0, 2]
    checks.show_encounter(Encounter(4, _record().to_bytes()))          # another one starts from its scene.out
    assert [slot.slot_index for slot in checks.present_slots()] == [0]
    checks.require(1)                                                  # the model a host films
    assert checks.present(1) and not checks._checks[1].isEnabled()
    checks.show_encounter(None)
    assert not checks.present_slots() and checks.isHidden()


class _Enemy:
    entity_type = None
    id = None
    origin_path = ""


class _Manager:
    enemy = _Enemy()
    game_data = None


def test_the_picker_offers_the_monsters_ticked(qapp):
    from Ifrit.IfritCameraSeq.encounterpreview import EncounterPicker
    picker = EncounterPicker(_Manager())
    picker.encounters = [Encounter(3, _record().to_bytes())]
    picker.refresh_model(force=True)
    picker.encounter.setCurrentIndex(1)
    assert [picker.enemy_slot.itemData(i).slot_index for i in range(picker.enemy_slot.count())] == [0]
    picker.monsters._checks[2].setChecked(True)
    assert [slot.slot_index for slot in picker.present_slots()] == [0, 2]
    assert [picker.enemy_slot.itemData(i).slot_index for i in range(picker.enemy_slot.count())] == [0, 2]
    picker.monsters._checks[0].setChecked(False)
    picker.monsters._checks[2].setChecked(False)
    assert picker.present_slots() == [] and picker.selected_slot is None


def test_a_filmed_monster_stands_even_if_scene_out_brings_it_in_later(qapp):
    from Ifrit.IfritCameraSeq.encounterpreview import EncounterPicker

    class Monster(_Enemy):
        id = 73
        class entity_type:
            name = "MONSTER"

    class Manager(_Manager):
        enemy = Monster()
    picker = EncounterPicker(Manager())
    picker.encounters = [Encounter(3, _record().to_bytes())]
    picker.refresh_model(force=True)
    assert picker.encounter.count() == 2                               # its encounter is offered: it is in slot 2
    picker.encounter.setCurrentIndex(1)
    assert picker.selected_slot.slot_index == 2
    assert [slot.slot_index for slot in picker.present_slots()] == [0, 2] and not picker.monsters._checks[2].isEnabled()


def test_the_scene_preview_stands_the_monsters_ticked(qapp):
    from Common.battlescenepreview import BattleScenePreview
    preview = BattleScenePreview("FF8GameData")
    preview.show_encounter(_record(), 3)
    preview._rebuild()
    assert 3 in preview._slots
    assert 4 not in preview._slots and 5 not in preview._slots
    preview.monsters._checks[2].setChecked(True)
    preview._rebuild()
    assert 5 in preview._slots
    preview.monsters._checks[0].setChecked(False)
    preview._rebuild()
    assert 3 not in preview._slots and 5 in preview._slots


@pytest.fixture
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])
