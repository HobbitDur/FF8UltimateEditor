import os


class Shop():
    NB_ITEM_PER_SHOP = 16

    def __init__(self):
        self.item_ids = [0] * self.NB_ITEM_PER_SHOP
        self.item = [""] * self.NB_ITEM_PER_SHOP
        self.rare = [False] * self.NB_ITEM_PER_SHOP

    def __str__(self):
        str_return = ""
        for i in range(self.NB_ITEM_PER_SHOP):
            str_return += f"Item{i + 1}: {self.item[i]}, rare: {str(self.rare[i])}\n"
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
        self.item_values = {}
        self._item_file = os.path.join(resource_folder, "item.txt")
        self.__load_item_data(self._item_file)
        self._baseline_item_values = dict(self.item_values)


    def __load_item_data(self, file):
        with (open(file, "r") as f):
            file_split = f.read().split('\n')
            for el_split in file_split:
                split_line = el_split.split('<')
                self.item_values[int(split_line[0], 16)] = split_line[1]

    def read_shop_file(self, file_path):
        if file_path:
            self.file_path = file_path
            self.shop_file_data = bytearray()
            with open(file_path, "rb") as in_file:
                while el := in_file.read(1):
                    self.shop_file_data.extend(el)

    def analyze_shop_file(self):
        for shop_index in range(self.NB_SHOP):
            for item_index in range(Shop.NB_ITEM_PER_SHOP):
                current_data_index = shop_index * Shop.NB_ITEM_PER_SHOP * self.NB_BYTE_PER_ITEM + item_index * self.NB_BYTE_PER_ITEM
                item_id = self.shop_file_data[current_data_index]
                self.item_values.setdefault(item_id, f"Item {item_id}")
                self.shop_info[shop_index].item_ids[item_index] = item_id
                self.shop_info[shop_index].item[item_index] = self.item_values[item_id]
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
                shop = self.shop_info[shop_index]
                item_id = shop.item_ids[item_index]
                if self.item_values.get(item_id) != shop.item[item_index]:
                    matches = [key for key, value in self.item_values.items() if value == shop.item[item_index]]
                    if len(matches) != 1:
                        raise ValueError("Select the shop item by ID; its name is missing or ambiguous.")
                    item_id = shop.item_ids[item_index] = matches[0]
                self.shop_file_data[current_data_index] = item_id
                if self.shop_info[shop_index].rare[item_index]:
                    rare = 0x00
                else:
                    rare = 0xFF
                self.shop_file_data[current_data_index + 1] = rare
        with open(file_path, "wb") as out_file:
            out_file.write(self.shop_file_data)
