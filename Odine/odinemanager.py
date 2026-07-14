from FF8GameData.gamedata import GameData

LIST_SIZE = 64
NB_LISTS = 7

# The 6 permutations the game stores, in file order (list 0 is always the unused all-zero list).
# Each permutation concatenates the 3 category lists in the given order, zero-padded to 64 bytes.
PERMUTATIONS = [
    ("offensive", "supportive", "disruptive"),
    ("offensive", "disruptive", "supportive"),
    ("supportive", "offensive", "disruptive"),
    ("supportive", "disruptive", "offensive"),
    ("disruptive", "offensive", "supportive"),
    ("disruptive", "supportive", "offensive"),
]


class OdineManager:
    """magsort.bin editor logic (menu Magic screen Offensive/Supportive/Disruptive sort order).

    Named after Dr. Odine, the Esthar scientist who invented para-magic and the junction system
    that the drawn spells this file sorts all rely on.

    magsort.bin is 7 lists of 64 bytes. List 0 is always zero (unused). Lists 1-6 are every
    permutation of the 3 categories (Offensive, Supportive, Disruptive) concatenated back to
    back and zero-padded to 64 bytes, in the fixed order given by PERMUTATIONS. Editing is done
    on the 3 category lists; save_file() regenerates all 7 lists from them.
    """

    def __init__(self, game_data: GameData):
        self.game_data = game_data
        self.file_path = ""
        self.offensive = []
        self.supportive = []
        self.disruptive = []

    def load_file(self, file_path):
        self.file_path = file_path
        with open(file_path, "rb") as in_file:
            file_data = in_file.read()

        lists = [list(file_data[i * LIST_SIZE:(i + 1) * LIST_SIZE]) for i in range(NB_LISTS)]

        # Any two permutations that share the same leading category have byte-identical prefixes
        # up to the point their second category diverges: that prefix length is the category size.
        self.offensive = lists[1][:self._common_prefix_length(lists[1], lists[2])]
        self.supportive = lists[3][:self._common_prefix_length(lists[3], lists[4])]
        self.disruptive = lists[5][:self._common_prefix_length(lists[5], lists[6])]

    @staticmethod
    def _common_prefix_length(list_a, list_b):
        length = 0
        for byte_a, byte_b in zip(list_a, list_b):
            if byte_a != byte_b:
                break
            length += 1
        return length

    def build_list(self, *groups):
        result = []
        for group in groups:
            result.extend(group)
        if len(result) > LIST_SIZE:
            raise ValueError(f"List would contain {len(result)} bytes, max is {LIST_SIZE}")
        result.extend([0] * (LIST_SIZE - len(result)))
        return result

    def save_file(self, file_path=""):
        if not file_path:
            file_path = self.file_path

        self.validate()

        groups = {
            "offensive": self.offensive,
            "supportive": self.supportive,
            "disruptive": self.disruptive,
        }

        output = bytearray(LIST_SIZE)  # List 0: always zero
        for permutation in PERMUTATIONS:
            output.extend(self.build_list(*(groups[category] for category in permutation)))

        with open(file_path, "wb") as out_file:
            out_file.write(bytes(output))

    def validate(self):
        all_spells = self.offensive + self.supportive + self.disruptive

        invalid_ids = sorted(x for x in set(all_spells) if x < 0 or x > 255)
        if invalid_ids:
            raise ValueError("Invalid spell IDs: " + ", ".join(map(str, invalid_ids)))

        duplicates = sorted(x for x in set(all_spells) if all_spells.count(x) > 1)
        if duplicates:
            raise ValueError("Duplicate spell IDs: " + ", ".join(map(str, duplicates)))

        if len(all_spells) > LIST_SIZE:
            raise ValueError(f"Too many spells ({len(all_spells)}). Maximum is {LIST_SIZE}.")

    def get_magic_name(self, magic_id):
        for magic in self.game_data.magic_data_json["magic"]:
            if magic["id"] == magic_id:
                return magic["name"]
        return f"Magic {magic_id}"

    def all_magic_ids(self):
        """Every real spell id (id 0 is the dummy "Nothing" entry, never sorted)."""
        return [magic["id"] for magic in self.game_data.magic_data_json["magic"] if magic["id"] != 0]

    def unused_magic_ids(self):
        used = set(self.offensive + self.supportive + self.disruptive)
        return sorted(set(self.all_magic_ids()) - used)
