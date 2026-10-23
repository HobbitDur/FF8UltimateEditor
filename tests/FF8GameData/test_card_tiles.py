"""Card art tiles: decoded once per process and shared, identical to cropping the atlases."""
import os

from PIL import Image

from Common.apppaths import APP_FOLDER
from FF8GameData.gamedata import GameData

GAME_DATA_FOLDER = str(APP_FOLDER / "FF8GameData")


def test_card_tiles_are_shared_and_match_the_atlas():
    first = GameData(GAME_DATA_FOLDER)
    first.load_card_data()
    second = GameData(GAME_DATA_FOLDER)
    second.load_card_data()

    # Each GameData keeps its own JSON (a tool may rename a card), but the art is decoded once.
    assert first.card_data_json is not second.card_data_json
    for key in ("img", "img_remaster", "img_xylomod"):
        assert all(a[key] is b[key] for a, b in zip(first.card_data_json["card_info"],
                                                    second.card_data_json["card_info"]))
    assert first.card_data_json["card_type"][0]["img"] is second.card_data_json["card_type"][0]["img"]

    images = first.resource_folder_image
    for name, size, key in (("cards_00.png", 64, "img"), ("cards_00_remaster.png", 256, "img_remaster"),
                            ("cards_00_xylomod.png", 256, "img_xylomod")):
        atlas = Image.open(os.path.join(images, name))
        for card in first.card_data_json["card_info"][::17]:
            left, upper = card["img_x"] * size, card["img_y"] * size
            expected = atlas.crop((left, upper, left + size, upper + size))
            assert card[key].size == (size, size) and card[key].tobytes() == expected.tobytes()
    atlas = Image.open(os.path.join(images, "text_0.png"))
    for card_type in first.card_data_json["card_type"]:
        left, upper = card_type["img_x"] * 128, card_type["img_y"] * 128
        assert card_type["img"].tobytes() == atlas.crop((left, upper, left + 128, upper + 128)).tobytes()
