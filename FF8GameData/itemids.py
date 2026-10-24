"""Item ids and where each one lives, vanilla and with FFNx's AddMoreItems extension.

The game has items 0-198 (0 is "no item"). kernel.bin keeps them in two sections, numbered here
the way the editor numbers them (from 1):

* section 8, battle items: one 24-byte record per id 0-32, which battle reads;
* section 9, non-battle items: the name/description offsets of ids 33-198, one row per id.

AddMoreItems (FFNx branch AddMoreItems) grows both without moving any original id:

* section 9 takes up to 57 more rows, ids 199-255 (row = id - 33, as for the vanilla rows);
* section 8 takes up to 56 more records, ids 199-254: record 33 + k is id 199 + k. 255 stays
  the engine's "no item" result of the random battle-item pick, so it never has a battle record.

Every id from 33 up, the added battle items included, is named by its section 9 row; the
section 8 text of an added record is never shown. FFNx refuses a kernel.bin whose added battle
records reach past the last section 9 row, since that item would have no name.

menu/mitem.bin and menu/price.bin are flat 4-byte rows by item id: 199 rows vanilla, up to 256.
A save keeps the vanilla 198 inventory slots, plus all 255 in a block AddMoreItems writes in the
save image's unused tail (see Hyne).
"""

VANILLA_BATTLE_ITEMS = 33        # Section 8 rows: ids 0-32
VANILLA_NON_BATTLE_ITEMS = 166   # Section 9 rows: ids 33-198
VANILLA_ITEM_COUNT = VANILLA_BATTLE_ITEMS + VANILLA_NON_BATTLE_ITEMS   # 199 ids, 0-198
FIRST_ADDED_ITEM = 199
LAST_ITEM_ID = 255
ITEM_ID_COUNT = LAST_ITEM_ID + 1  # 256: the most rows mitem.bin / price.bin can have
MAX_ADDED_BATTLE_ITEMS = 56      # ids 199-254
MAX_ADDED_NON_BATTLE_ITEMS = 57  # ids 199-255
MAX_BATTLE_ITEM_ROWS = VANILLA_BATTLE_ITEMS + MAX_ADDED_BATTLE_ITEMS            # 89
MAX_NON_BATTLE_ITEM_ROWS = VANILLA_NON_BATTLE_ITEMS + MAX_ADDED_NON_BATTLE_ITEMS  # 223

BATTLE_ITEM_SECTION = 8
NON_BATTLE_ITEM_SECTION = 9


def battle_row_to_item_id(row: int) -> int:
    """The item id of section 8 row `row`."""
    if row < VANILLA_BATTLE_ITEMS:
        return row
    return FIRST_ADDED_ITEM + row - VANILLA_BATTLE_ITEMS


def item_id_to_battle_row(item_id: int):
    """The section 8 row of an item id, or None when that id can have no battle record."""
    if 0 <= item_id < VANILLA_BATTLE_ITEMS:
        return item_id
    if FIRST_ADDED_ITEM <= item_id < FIRST_ADDED_ITEM + MAX_ADDED_BATTLE_ITEMS:
        return VANILLA_BATTLE_ITEMS + item_id - FIRST_ADDED_ITEM
    return None


def non_battle_row_to_item_id(row: int) -> int:
    """The item id of section 9 row `row`."""
    return VANILLA_BATTLE_ITEMS + row


def item_count(non_battle_rows: int) -> int:
    """How many item ids (0 included) a kernel.bin defines, from its section 9 row count."""
    return VANILLA_BATTLE_ITEMS + non_battle_rows


def item_problems(battle_rows: int, non_battle_rows: int) -> list:
    """What FFNx's AddMoreItems loader would refuse in these section sizes (it then rejects the
    whole kernel.bin, so the game does not start with it)."""
    problems = []
    if battle_rows < VANILLA_BATTLE_ITEMS or non_battle_rows < VANILLA_NON_BATTLE_ITEMS:
        problems.append("The item sections must keep every original item.")
    if battle_rows > MAX_BATTLE_ITEM_ROWS:
        problems.append(f"There are {battle_rows} battle item records; AddMoreItems takes at most "
                        f"{MAX_BATTLE_ITEM_ROWS} (ids 0-32 and 199-254).")
    if non_battle_rows > MAX_NON_BATTLE_ITEM_ROWS:
        problems.append(f"There are {non_battle_rows} item name rows; AddMoreItems takes at most "
                        f"{MAX_NON_BATTLE_ITEM_ROWS} (ids 33-255).")
    if battle_rows > VANILLA_BATTLE_ITEMS:
        last_battle_id = battle_row_to_item_id(battle_rows - 1)
        if last_battle_id >= item_count(non_battle_rows):
            problems.append(f"Battle item {last_battle_id} has no Item Names row: the item names go up "
                            f"to id {item_count(non_battle_rows) - 1}.")
    return problems
