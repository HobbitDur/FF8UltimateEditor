"""One in-memory item/menu/price project per FileRegistry.

All item editors share the same objects, so opening SolomonRing or adding an
item cannot overwrite an unsaved PuPuCargo/Siren edit with a fresh disk load.
"""
from copy import copy, deepcopy

from PyQt6.QtCore import QObject, pyqtSignal

from Common.filebinding import FileBinding
from FF8GameData.gamedata import GameData
from FF8GameData.kernelnames import read_names
from Kadowaki.kadowakimanager import KadowakiManager, MenuItem
from Siren.sirenmanager import SirenManager, PriceEntry


class ItemFiles(QObject):
    mitem_changed = pyqtSignal()
    price_changed = pyqtSignal()
    names_changed = pyqtSignal()

    @classmethod
    def for_registry(cls, registry, game_data_folder="FF8GameData"):
        if not hasattr(registry, "_item_files"):
            registry._item_files = cls(registry, game_data_folder)
        return registry._item_files

    def __init__(self, registry, game_data_folder):
        super().__init__(registry)
        self.game_data = GameData(game_data_folder)
        self.game_data.load_all()
        self._baseline_items = deepcopy(self.game_data.item_data_json["items"])
        self.names = {}
        self.mitem = KadowakiManager(self.game_data)
        self.price = SirenManager(self.game_data)
        self.mitem_binding = FileBinding("mitem.bin", registry, load_callback=self.load_mitem,
                                         save_callback=self.save_mitem)
        self.price_binding = FileBinding("price.bin", registry, load_callback=self.load_price,
                                         save_callback=self.save_price)
        self.mitem_complementary = ComplementaryBinding(self.mitem_binding)
        self.price_complementary = ComplementaryBinding(self.price_binding)
        self.kernel_binding = FileBinding("kernel.bin", registry, load_callback=self.load_names,
                                          read_only=True, complementary=True)
        self.mitem_binding.file_closed.connect(self._close_mitem)
        self.price_binding.file_closed.connect(self._close_price)
        self.kernel_binding.file_closed.connect(lambda _path: self.set_names({}))
        self.mitem_binding.load_opened_file()
        self.price_binding.load_opened_file()
        self.kernel_binding.load_opened_file()

    @property
    def ready(self):
        return bool(self.mitem.file_path and self.price.file_path)

    @staticmethod
    def _check_file(path):
        from pathlib import Path
        size = Path(path).stat().st_size
        if not size or size % 4 or size > 1024:
            raise ValueError("Item metadata must contain 1-256 complete four-byte records.")

    def load_mitem(self, path):
        self._check_file(path)
        self.mitem.load_file(path)
        self.mitem_changed.emit()

    def load_price(self, path):
        self._check_file(path)
        self.price.load_file(path)
        self.price_changed.emit()

    def save_mitem(self):
        if self.mitem.file_path:
            self.mitem.save_file()

    def save_price(self):
        if self.price.file_path:
            self.price.save_file()

    def _close_mitem(self, _path):
        self.mitem.file_path = ""
        self.mitem.menu_items = []
        self.mitem_changed.emit()

    def _close_price(self, _path):
        self.price.file_path = ""
        self.price.price_entries = []
        self.price_changed.emit()

    def load_names(self, path):
        self.set_names(read_names(self.game_data, path, keep_unnamed=True).get("item", {}))

    def set_names(self, names):
        names = dict(names)
        if names == self.names:
            return
        self.names = names
        self.apply_names(self.game_data)
        for item in self.mitem.menu_items:
            item.name = self.mitem.get_item_name(item.item_id)
        for item in self.price.price_entries:
            item.name = self.price.get_item_name(item.item_id)
        self.names_changed.emit()

    def apply_names(self, game_data):
        baseline = getattr(game_data, "_item_name_baseline", None)
        if baseline is None:
            baseline = deepcopy(self._baseline_items)
            game_data._item_name_baseline = baseline
        entries = {item["id"]: deepcopy(item) for item in baseline}
        for item_id, name in self.names.items():
            if name and name.casefold() != "#nomsg":
                entries.setdefault(item_id, {"id": item_id})["name"] = name
            elif item_id not in entries:
                entries[item_id] = {"id": item_id, "name": f"Item {item_id}"}
        game_data.item_data_json["items"] = [entries[i] for i in sorted(entries)]
        if self.names:
            game_data.kernel_names["item"] = dict(self.names)
        else:
            game_data.kernel_names.pop("item", None)

    def create(self, definitions, name, description="", template_id=1, battle=True):
        if not self.ready:
            raise ValueError("Open mitem.bin and price.bin with Import complementary before adding an item.")
        definitions.validate()
        item_id = definitions.count
        field = copy(self.mitem.menu_items[template_id]) if template_id < len(self.mitem.menu_items) else MenuItem(item_id, name, 10)
        price = copy(self.price.price_entries[template_id]) if template_id < len(self.price.price_entries) else PriceEntry(item_id, name)
        if not 0 <= field.type_id <= 21:
            raise ValueError("The template uses an unsupported field-effect type.")
        field.item_id = price.item_id = item_id
        field.name = price.name = name
        # All validation happens before the kernel or the side files are changed.
        definitions.add(name, description, template_id, battle)
        for index in range(len(self.mitem.menu_items), item_id + 1):
            self.mitem.menu_items.append(MenuItem(index, f"Item {index}", 10))
        for index in range(len(self.price.price_entries), item_id + 1):
            self.price.price_entries.append(PriceEntry(index, f"Item {index}"))
        self.mitem.menu_items[item_id] = field
        self.price.price_entries[item_id] = price
        self.set_names(definitions.names())
        self.mitem_changed.emit()
        self.price_changed.emit()
        return item_id

class ComplementaryBinding:
    """A toolbar view of a shared binding, editable as a side file of SolomonRing."""
    complementary = True

    def __init__(self, binding):
        self.binding = binding

    def __getattr__(self, name):
        return getattr(self.binding, name)
