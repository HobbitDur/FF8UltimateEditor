"""Verified annotation scope and checkpoint-before-mutation behavior without requiring IDA."""
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from Fujin.ResearchScript.sync_effect_ida import (BEGIN, END, SHA256, apply_in_ida,
                                                 add_directory_reference, build_plan, merge_comment)


def test_comment_merge_retains_user_notes_and_replaces_only_our_block():
    original = "User's analysis\n\n"+BEGIN+"\nOutdated finding\n"+END+"\nMore user notes"
    merged = merge_comment(original, "Verified finding")
    assert "User's analysis" in merged and "More user notes" in merged
    assert "Outdated finding" not in merged
    assert merged.count(BEGIN) == 1
    assert merge_comment(merged, "Verified finding") == merged


@pytest.mark.ff8data("extracted_files/FF8_EN.exe")
def test_plan_covers_audited_resources_and_cinematic_directories():
    plan = build_plan()
    entries = {int(e["address"], 16): e for e in plan["entries"]}
    assert len(entries) == len(plan["entries"])
    assert len([e for e in entries.values() if e.get("type") == "FF8EffectCinematicDirectory"]) == 58
    assert len([e for e in entries.values() if e.get("type") == "FF8EffectCameraTrackHeader"]) == 221
    assert len([e for e in entries.values() if e.get("type") == "FF8EffectModelDirectory"]) == 24
    assert len([e for e in entries.values() if e.get("type") == "FF8EffectTIMHeader"]) == 26
    assert len(plan["references"]) == 96
    disease = entries[0xA6C240]["comment"]
    assert "0x870" in disease and "3 blocks, 5 keyframe" in disease
    assert entries[0x681DE6]["check_size"] == 2  # sign-extended imm8 push; preserve its opcode
    assert "0x681DE7" in entries[0x681630]["comment"]
    assert "does not advance" in entries[0xAD29D0]["comment"]
    for entry in entries.values():
        if entry.get("check_size"):
            assert len(entry["check_sha256"]) == 64


def _fake_ida(monkeypatch, tmp_path, *, fail_save=False, mismatch=False):
    events, comments = [], {0x1000: "Previous user note"}
    database = tmp_path / "database.i64"
    database.write_bytes(b"saved database contents")

    def save(path, flags):
        events.append(("save", path))
        return not fail_save

    def set_comment(ea, comment, repeatable):
        events.append(("comment", ea))
        comments[ea] = comment
        return True

    modules = dict(
        ida_auto=SimpleNamespace(auto_wait=lambda: None),
        ida_bytes=SimpleNamespace(get_bytes=lambda ea, size: b"\0\0" if mismatch else b"\x12\x34",
                                 get_cmt=lambda ea, r: comments.get(ea), set_cmt=set_comment,
                                 get_dword=lambda ea: 0x2000, get_full_flags=lambda ea: "head",
                                 is_unknown=lambda flags: flags == "unknown", is_head=lambda flags: flags == "head",
                                 get_item_head=lambda ea: ea),
        ida_funcs=SimpleNamespace(get_func=lambda ea: None),
        ida_loader=SimpleNamespace(PATH_TYPE_IDB=0, get_path=lambda kind: str(database), save_database=save),
        ida_name=SimpleNamespace(get_name=lambda ea: "ExistingDescriptiveName"),
        ida_nalt=SimpleNamespace(retrieve_input_file_sha256=lambda: bytes.fromhex(SHA256)),
        ida_typeinf=SimpleNamespace(),
        ida_xref=SimpleNamespace(add_dref=lambda a, b, t: events.append(("xref", a, b)) or True, dr_O=1, XREF_USER=32),
        idautils=SimpleNamespace(DataRefsFrom=lambda ea: []),
        idc=SimpleNamespace(parse_decls=lambda text, flags: 0, PT_SIL=1),
    )
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    plan = dict(exe_sha256=SHA256, entries=[dict(address="0x1000", kind="data", name="ProposedName",
        comment="Verified finding", check_size=2, check_sha256=hashlib.sha256(b"\x12\x34").hexdigest())],
        type_declarations="", member_comments=[], references=[dict(from_address="0x1000", to_address="0x2000")])
    return plan, events, comments, database


def test_save_and_verified_backup_precede_annotation_changes(monkeypatch, tmp_path):
    plan, events, comments, database = _fake_ida(monkeypatch, tmp_path)
    report = apply_in_ida(plan, backup_folder=tmp_path / "backups")
    assert events[0] == ("save", str(database))
    assert events[-1] == ("save", str(database))
    assert Path(report["backup"]).read_bytes() == database.read_bytes()
    assert report["backup_sha256"] == hashlib.sha256(database.read_bytes()).hexdigest()
    assert report["saved"] and report["changes"][0]["name"] == "ExistingDescriptiveName"
    assert comments[0x1000].startswith("Previous user note")
    assert json.loads(Path(report["backup"]).with_name("effect-update-report.json").read_text())["saved"]


@pytest.mark.parametrize("failure", ["save", "bytes"])
def test_failed_checkpoint_or_byte_validation_changes_no_annotations(monkeypatch, tmp_path, failure):
    plan, events, comments, _database = _fake_ida(monkeypatch, tmp_path,
        fail_save=failure == "save", mismatch=failure == "bytes")
    with pytest.raises((OSError, ValueError)):
        apply_in_ida(plan, backup_folder=tmp_path / "backups")
    assert not any(event[0] == "comment" for event in events)
    assert comments[0x1000] == "Previous user note"
    assert not (tmp_path / "backups").exists()


@pytest.mark.parametrize("existing", [True, False])
def test_structured_directory_reference_uses_item_head_without_splitting(existing):
    # Reported IDA warning: opcode 0x39 is inside the 0x1877864 directory structure.
    source, head, target = 0x1877948, 0x1877864, 0xB60140
    calls = []
    byte_api = SimpleNamespace(get_dword=lambda ea: target, get_item_head=lambda ea: head,
        get_full_flags=lambda ea: "head" if ea == head else "tail",
        is_unknown=lambda flags: flags == "unknown", is_head=lambda flags: flags == "head")
    xref_api = SimpleNamespace(dr_O=1, XREF_USER=32,
        add_dref=lambda a, b, flags: calls.append((a, b, flags)) or True)
    ref = dict(from_address=hex(source), to_address=hex(target))
    result = add_directory_reference(ref, byte_api, xref_api, lambda ea: [target] if existing else [])
    assert result == dict(source=hex(source), anchor=hex(head), target=hex(target), existing=existing)
    assert calls == ([] if existing else [(head, target, 33)])


def test_unknown_directory_pointer_is_defined_before_adding_reference():
    source, target = 0x1000, 0x2000
    events = []
    flags = {source: "unknown"}

    def define(ea, size):
        events.append(("define", ea, size))
        flags[ea] = "head"
        return True

    byte_api = SimpleNamespace(get_dword=lambda ea: target, get_item_head=lambda ea: ea,
        get_full_flags=lambda ea: flags[ea], create_dword=define,
        is_unknown=lambda flag: flag == "unknown", is_head=lambda flag: flag == "head")
    xref_api = SimpleNamespace(dr_O=1, XREF_USER=32,
        add_dref=lambda a, b, flags: events.append(("xref", a, b)) or True)
    add_directory_reference(dict(from_address=hex(source), to_address=hex(target)),
                            byte_api, xref_api, lambda ea: [])
    assert events == [("define", source, 4), ("xref", source, target)]


def test_mismatched_directory_pointer_adds_no_reference():
    byte_api = SimpleNamespace(get_dword=lambda ea: 0xDEADBEEF)
    with pytest.raises(ValueError, match="Directory pointer differs"):
        add_directory_reference(dict(from_address="0x1000", to_address="0x2000"),
                                byte_api, SimpleNamespace(), lambda ea: [])
