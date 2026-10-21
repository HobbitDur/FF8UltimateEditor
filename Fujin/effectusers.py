"""Which spells, items, GFs, enemy attacks, limit breaks... play each battle effect, read from a
kernel.bin (Qt-free).

Every kernel.bin entry that performs an action stores the effect it plays as its "Attack
animation" field (the attack-animation id: Fujin's effect id). kernel_section_fields.json marks
that field in each section (lookup "attack_animation"), so the sections read here follow that
file - a section that gains such a field is read too. Names are the kernel.bin's own texts (a
mod's renames and added spells included), or the field file's entry names for the sections the
kernel leaves unnamed (command abilities, enemy attacks without a text).
"""
import json
import pathlib
import struct
from dataclasses import dataclass

# Short, user-facing names of the sections (the others fall back to the kernel layout's name)
SECTION_KINDS = {
    2: "Magic",
    3: "GF",
    4: "Enemy attack",
    6: "Renzokuken finisher",
    8: "Battle item",
    10: "GF attack",
    11: "Command ability",
    19: "Limit break",
    20: "Blue magic",
    22: "Shot",
    23: "Duel",
    26: "Rinoa limit break",
}


@dataclass(frozen=True)
class EffectUser:
    kind: str           # "Magic", "Battle item"...
    section_id: int
    entry_id: int       # index of the entry in its kernel section
    name: str

    def label(self):
        return f"{self.name} ({self.kind} {self.entry_id})"


def effect_fields(game_data) -> dict:
    """{section id: (offset, size)} of each section's attack-animation field."""
    path = pathlib.Path(game_data.resource_folder_json) / "kernel_section_fields.json"
    sections = json.loads(path.read_text(encoding="utf-8"))
    fields = {}
    for key, config in sections.items():
        field = next((f for f in config.get("fields", []) if f.get("lookup") == "attack_animation"), None)
        if field is not None:
            fields[int(key)] = (field["offset"], field["size"], config.get("entry_names") or [])
    return fields


def _kind(game_data, section_id):
    if section_id in SECTION_KINDS:
        return SECTION_KINDS[section_id]
    config = next((c for c in game_data.kernel_data_json["sections"] if c["id"] == section_id), {})
    return config.get("section_name", f"Section {section_id}").removesuffix(" section")


def read_effect_users(game_data, kernel_file) -> dict:
    """{effect id: [EffectUser, ...]} of every kernel.bin entry, in section then entry order."""
    from FF8GameData.kernelnames import _reserved_ids, _section_names
    from ShumiTranslator.model.kernel.kernelmanager import KernelManager

    if not getattr(game_data, "kernel_data_json", None):
        game_data.load_kernel_data()
    kernel_manager = KernelManager(game_data)
    kernel_manager.load_file(str(kernel_file))
    by_id = {section.id: section for section in kernel_manager.section_list if section}
    users = {}
    for section_id, (offset, size, entry_names) in sorted(effect_fields(game_data).items()):
        section = by_id.get(section_id)
        if section is None:
            continue
        names = _section_names(game_data, kernel_manager, section_id)
        reserved = _reserved_ids(game_data, section_id)   # the magic ids 64-95 kept for the GFs
        kind = _kind(game_data, section_id)
        for entry_id, entry in enumerate(section.get_subsection_list()):
            data = bytes(entry.get_data_hex())
            if entry_id in reserved or len(data) < offset + size:
                continue
            effect = int.from_bytes(data[offset:offset + size], "little")
            name = (names[entry_id] if entry_id < len(names) else "") or (
                entry_names[entry_id] if entry_id < len(entry_names) else "")
            users.setdefault(effect, []).append(EffectUser(kind, section_id, entry_id,
                                                           name.strip() or f"Entry {entry_id}"))
    return users
