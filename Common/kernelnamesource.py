from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QLabel

from Common.filebinding import FileBinding


class KernelNameSource(QObject):
    """kernel.bin as a complementary (read-only) file of a tool, giving it the weapon and ability
    names - which have NO built-in list: without a kernel.bin open there are no names, and the
    tool shows the ids alone with a notice (make_notice) saying which file to open.

    It also gives the item names, which do have a built-in list (item.json, ids 0-198): item_name
    prefers the kernel.bin's, which is the only source of the items FFNx's AddMoreItems adds.

    The file is shared through the registry like any other: a kernel.bin opened in SolomonRing or
    any tool names them here too, and removing it from the Opened files panel takes them away.
    `changed` fires after every load / removal so the tool re-labels what it shows - from its data
    in memory, so unsaved edits stay.
    """

    changed = pyqtSignal()

    NOTICE_TEXT = ("No {what} names: they come only from kernel.bin. Open one with the toolbar's "
                   "\"Import complementary\" button to fill this list.")

    def __init__(self, game_data, file_registry, binding=None):
        """binding: the tool's own read-only kernel.bin FileBinding when it already has one (Zone
        reads its Duel sequences from it); a new one is made otherwise."""
        QObject.__init__(self)
        self.game_data = game_data
        if binding is None:
            binding = FileBinding("kernel.bin", file_registry, file_filter="*kernel*.bin",
                                  read_only=True)
        self.binding = binding
        self.binding.file_opened.connect(self._load)
        self.binding.file_closed.connect(self._clear)
        self.weapons = []    # name by weapon id; empty without a kernel.bin
        self.abilities = []  # name by ability id (0 = none ... 115 = Card Mod)
        self.items = {}      # name by item id, ids 0-255 as far as the kernel.bin defines them

    @property
    def loaded(self):
        return bool(self.weapons or self.abilities)

    def item_entries(self):
        """[{"value", "name"}] of the items a tool offers: the game's 0-198 (item.json, renamed by
        the kernel.bin), then the ones the kernel.bin adds with FFNx's AddMoreItems (199-255)."""
        entries = [{"value": item["id"], "name": self.items.get(item["id"]) or item["name"]}
                   for item in (getattr(self.game_data, "item_data_json", None) or {}).get("items", [])
                   if item["id"] < 199]
        entries += [{"value": item_id, "name": name or f"Item {item_id}"}
                    for item_id, name in sorted(self.items.items()) if item_id >= 199]
        return entries

    def item_name(self, item_id):
        """The kernel.bin name of an item, else item.json's, else "Item <id>"."""
        name = self.items.get(item_id)
        if name:
            return name
        for item in (getattr(self.game_data, "item_data_json", None) or {}).get("items", []):
            if item["id"] == item_id and item_id < 199:   # 255 "Immune" is no item
                return item["name"]
        return f"Item {item_id}"

    def weapon_name(self, weapon_id):
        """The kernel.bin name of a weapon, or "" when there is none (no kernel.bin, unknown id)."""
        return self.weapons[weapon_id] if 0 <= weapon_id < len(self.weapons) else ""

    def ability_name(self, ability_id):
        return self.abilities[ability_id] if 0 <= ability_id < len(self.abilities) else ""

    def ability_entries(self):
        """[{"value", "name"}] of every ability (the shape of the kernel_lookups enums the tools
        used before); empty without a kernel.bin. Id 0 is the 'none' ability."""
        return [{"value": index, "name": name or ("None" if index == 0 else f"Ability {index}")}
                for index, name in enumerate(self.abilities)]

    @classmethod
    def make_notice(cls, what) -> QLabel:
        """The red "open kernel.bin" notice a tool shows while it has no names of `what`."""
        notice = QLabel(cls.NOTICE_TEXT.format(what=what))
        notice.setWordWrap(True)
        notice.setStyleSheet("color:#c0392b; font-weight:bold;")
        return notice

    def _load(self, path):
        from FF8GameData.kernelnames import read_weapon_and_ability_names
        if not getattr(self.game_data, "kernel_data_json", None):
            self.game_data.load_kernel_data()  # the kernel.bin layout, needed to read one
        try:
            names = read_weapon_and_ability_names(self.game_data, path)
        except Exception as error:  # noqa: BLE001 - a bad kernel.bin just gives no names
            print(f"[kernel names] could not read {path}: {error}")
            names = {"weapon": [], "ability": [], "item": {}}
        self.weapons, self.abilities, self.items = names["weapon"], names["ability"], names["item"]
        self.changed.emit()

    def _clear(self, _path=None):
        self.weapons, self.abilities, self.items = [], [], {}
        self.changed.emit()
