"""The names kernel.bin owns - spells, items and enemy attacks - read from a kernel.bin.

FF8GameData ships those names as json (magic.json, item.json, enemy_abilities.json), which is what
every tool shows: the xlsx columns and their drop-downs, the AI editor's parameters, the monster
drops and draws. They are the VANILLA names, and a mod that renames things in its kernel.bin - as
Cronos does for a few spells and items - makes them wrong for its own files.

Rather than keeping a second copy of those names by hand, a mod points at its kernel.bin and the
names it changed are applied over the json ones:

    changes = name_changes(game_data, "kernel.bin", vanilla_kernel_file="vanilla/kernel.bin")
    apply_names(game_data, changes)

Only the names that differ from the baseline are taken, never the whole kernel list, because the
json is deliberately richer than the file: the kernel leaves an entry's name empty when the game
never shows it, where the json labels it ("Not defined", "Physical attack", "Unnamed (1)"...).
Those labels are worth keeping; a rename is what the mod means to say.

The baseline is a vanilla kernel.bin when there is one, the json names otherwise (which also
reports the handful of places where the shipped json and the game file spell a name differently).
"""
import json
import pathlib
from dataclasses import dataclass


@dataclass(frozen=True)
class NameList:
    """One list of names: where FF8GameData keeps it, and the kernel.bin section it comes from.

    The ids of a section are consecutive from `first_id`, which is not always 0: the item names
    live in two sections, the 33 battle items (ids 0-32) and then all the others."""
    name: str            # How this list is named in a changes file
    game_data_field: str  # The GameData attribute holding it
    json_key: str        # The key of the list inside it
    section_id: int      # The kernel.bin data section the names come from
    first_id: int = 0    # The id of that section's first entry


# Every name list a kernel.bin owns and a tool of this repository shows.
NAME_LISTS = (
    NameList("magic", "magic_data_json", "magic", section_id=2),
    NameList("item", "item_data_json", "items", section_id=8),
    NameList("item", "item_data_json", "items", section_id=9, first_id=33),
    NameList("enemy_ability", "enemy_abilities_data_json", "abilities", section_id=4),
)


def _texts_per_entry(game_data, section_id: int) -> int:
    """How many texts a section holds per entry (a name and a description, usually), from the same
    field definitions SolomonRing edits the kernel with."""
    path = pathlib.Path(game_data.resource_folder_json) / "kernel_section_fields.json"
    with open(path, encoding="utf8") as fields_file:
        fields = json.load(fields_file)
    return len(fields.get(str(section_id), {}).get("text_labels") or [])


def _text_section_id(game_data, section_id: int) -> int:
    for config in game_data.kernel_data_json["sections"]:
        if config["id"] == section_id:
            return config["section_id_text_linked"]
    return 0


def _section_names(game_data, kernel_manager, section_id: int) -> list:
    """The name of every entry of a kernel data section, in order.

    A section's names are the first text of each of its entries, held in the text section linked to
    it: its texts run entry by entry (name, description, name, description... for a section with
    two of them), so entry i's name is at i * <texts per entry>."""
    by_id = {section.id: section for section in kernel_manager.section_list if section}
    text_section = by_id.get(_text_section_id(game_data, section_id))
    section = by_id.get(section_id)
    if section is None or text_section is None:
        return []
    per_entry = _texts_per_entry(game_data, section_id)
    if not per_entry:
        return []
    texts = text_section.get_text_list()
    return [texts[index * per_entry].get_str() if index * per_entry < len(texts) else ""
            for index in range(len(section.get_subsection_list()))]


def read_names(game_data, kernel_file) -> dict:
    """Every name a kernel.bin holds, as {list name: {id: name}}. Entries the file leaves unnamed
    are left out - the json is what names those."""
    from ShumiTranslator.model.kernel.kernelmanager import KernelManager

    kernel_manager = KernelManager(game_data)
    kernel_manager.load_file(str(kernel_file))
    names = {}
    for name_list in NAME_LISTS:
        section_names = _section_names(game_data, kernel_manager, name_list.section_id)
        found = names.setdefault(name_list.name, {})
        for index, name in enumerate(section_names):
            if name:
                found[name_list.first_id + index] = name
    return names


def json_names(game_data) -> dict:
    """The names FF8GameData ships, in the same shape as read_names."""
    names = {}
    for name_list in NAME_LISTS:
        entries = getattr(game_data, name_list.game_data_field)[name_list.json_key]
        names.setdefault(name_list.name, {}).update({entry["id"]: entry["name"] for entry in entries})
    return names


def name_changes(game_data, kernel_file, vanilla_kernel_file=None) -> dict:
    """What `kernel_file` renames, as {list name: {id: name}}.

    Compared with `vanilla_kernel_file` when given - the exact answer, "what this mod changed" -
    and with the json names otherwise, which also picks up the few entries the shipped json and a
    vanilla kernel.bin spell differently."""
    baseline = read_names(game_data, vanilla_kernel_file) if vanilla_kernel_file else json_names(game_data)
    changes = {}
    for list_name, names in read_names(game_data, kernel_file).items():
        renamed = {id_: name for id_, name in names.items() if baseline.get(list_name, {}).get(id_) != name}
        if renamed:
            changes[list_name] = renamed
    return changes


def apply_names(game_data, changes: dict) -> int:
    """Write `changes` into the names GameData holds. Returns how many names were changed.

    Everything showing a spell, an item or an enemy attack reads them from there, so this is what
    makes a mod's own names appear in the xlsx, in its drop-downs and in the AI editor."""
    applied = 0
    for name_list in NAME_LISTS:
        renamed = changes.get(name_list.name) or {}
        if not renamed:
            continue
        for entry in getattr(game_data, name_list.game_data_field)[name_list.json_key]:
            new_name = renamed.get(entry["id"], renamed.get(str(entry["id"])))
            if new_name is not None and entry["name"] != new_name:
                entry["name"] = new_name
                applied += 1
    return applied


def read_changes_file(path) -> dict:
    """Read a changes file written by write_changes_file (its ids are json keys, so strings)."""
    with open(path, encoding="utf8") as changes_file:
        changes = json.load(changes_file)
    return {list_name: {int(id_): name for id_, name in names.items()}
            for list_name, names in changes.items() if not list_name.startswith("_")}


def write_changes_file(path, changes: dict, comment: str = ""):
    """Write the changes as json: one block per list, ids in order, plus a line saying where they
    come from (they are generated, and a reader needs to know not to edit them by hand)."""
    content = {"_comment": comment} if comment else {}
    for list_name, names in changes.items():
        content[list_name] = {str(id_): names[id_] for id_ in sorted(names)}
    pathlib.Path(path).write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
