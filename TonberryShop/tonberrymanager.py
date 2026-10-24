import os


class Shop():
    NB_ITEM_PER_SHOP = 16

    def __init__(self):
        # Item ids, as the file stores them: a name can be shared (or be an item FFNx's
        # AddMoreItems adds, 199-255, which only a kernel.bin names), an id cannot.
        self.item_id = [0] * self.NB_ITEM_PER_SHOP
        self.rare = [False] * self.NB_ITEM_PER_SHOP

    def __str__(self):
        str_return = ""
        for i in range(self.NB_ITEM_PER_SHOP):
            str_return += f"Item{i + 1}: {self.item_id[i]}, rare: {str(self.rare[i])}\n"
        return str_return


class TonberryManager():
    NB_SHOP = 20
    NB_BYTE_PER_ITEM = 2
    SHOP_NAME_LIST = ["Timber Pet Shop", "Balamb Shop", "Dollet Shop", "Timber Shop", "Deling City Shop",
                      "Winhill Shop", "FH Shop",
                      "Trabia Shop - UNUSED!", "Esthar Shop (Cloud's Shop)", "Balamb Shop (Laguna's World) - UNUSED!",
                      "Dollet Shop (Laguna's World) - UNUSED!", "Timber Shop (Laguna's World) - UNUSED!",
                      "Deling City Shop (Laguna's World) - UNUSED!", "Winhill Shop (Laguna's World)",
                      "FH Shop (Laguna's World) - UNUSED!", "Trabia Shop (Laguna's World) - UNUSED!", "Man from Garden",
                      "Esthar Pet Shop (Cheryl's store)", "Esthar Book Store (Karen's shop)",
                      "Esthar Shop!!! (Johnny's shop)"]

    def __init__(self, resource_folder=os.path.join("Resources")):
        self.shop_file_data = bytearray()
        self.file_path = ""
        self.shop_info = [Shop() for x in range(self.NB_SHOP)]
        self.item_values = {}   # the game's item names by id (item.txt, 0-198)
        # Names from an opened kernel.bin ({id: name}), over item.txt's: a mod's renames, and the
        # items FFNx's AddMoreItems adds (199-255).
        self.kernel_item_names = {}
        self._item_file = os.path.join(resource_folder, "item.txt")
        self.__load_item_data(self._item_file)

    def item_name(self, item_id):
        return self.kernel_item_names.get(item_id) or self.item_values.get(item_id) or f"Item {item_id}"

    def item_choices(self):
        """[(id, name)] a shop slot can hold: the game's items, then those the kernel.bin adds."""
        ids = sorted(set(self.item_values) | set(self.kernel_item_names))
        return [(item_id, self.item_name(item_id)) for item_id in ids]

    def item_id_from_name(self, name):
        for item_id, item_name in self.item_choices():
            if item_name == name:
                return item_id
        raise ValueError(f"Unknown item name '{name}'")


    def __load_item_data(self, file):
        with (open(file, "r") as f):
            file_split = f.read().split('\n')
            for el_split in file_split:
                split_line = el_split.split('<')
                self.item_values[int(split_line[0], 16)] = split_line[1]

    def read_shop_file(self, file_path):
        if file_path:
            self.file_path = file_path
            with open(file_path, "rb") as in_file:
                self.shop_file_data.extend(in_file.read())  # one read: byte by byte took seconds on the exe

    def analyze_shop_file(self):
        for shop_index in range(self.NB_SHOP):
            for item_index in range(Shop.NB_ITEM_PER_SHOP):
                current_data_index = shop_index * Shop.NB_ITEM_PER_SHOP * self.NB_BYTE_PER_ITEM + item_index * self.NB_BYTE_PER_ITEM
                self.shop_info[shop_index].item_id[item_index] = self.shop_file_data[current_data_index]
                if self.shop_file_data[current_data_index + 1] == 0xFF:
                    rare = False
                elif self.shop_file_data[current_data_index + 1] == 0x00:
                    rare = True
                else:
                    print("Unexpected rarity")
                    rare = False
                self.shop_info[shop_index].rare[item_index] = rare

    def write_shop_file(self, file_path=""):
        if not file_path:
            file_path = self.file_path
        for shop_index in range(self.NB_SHOP):
            for item_index in range(Shop.NB_ITEM_PER_SHOP):
                current_data_index = shop_index * Shop.NB_ITEM_PER_SHOP * self.NB_BYTE_PER_ITEM + item_index * self.NB_BYTE_PER_ITEM
                self.shop_file_data[current_data_index] = self.shop_info[shop_index].item_id[item_index] & 0xFF
                if self.shop_info[shop_index].rare[item_index]:
                    rare = 0x00
                else:
                    rare = 0xFF
                self.shop_file_data[current_data_index + 1] = rare
        with open(file_path, "wb") as out_file:
            out_file.write(self.shop_file_data)
