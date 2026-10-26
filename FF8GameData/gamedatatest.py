import unittest

from gamedata import GameData


class TestGameData(unittest.TestCase):

    def setUp(self):
        self.game_data = GameData()
        self.game_data.load_all()


    def test_sysfnt_basic(self):
        ff8_str = "This {in}"
        ff8_list = self.game_data.translate_str_to_hex(ff8_str)
        ff8_hex = bytearray(ff8_list)
        self.assertEqual(len(ff8_hex), 6)
        self.assertEqual(ff8_hex, b'Xfgq \xe8')
        ff8_re_str = self.game_data.translate_hex_to_str(ff8_hex)
        self.assertEqual(ff8_re_str, ff8_str)

    def test_sysfnt_basic2(self):
        ff8_str = "{x0a27}s {x0a26}OK?"
        ff8_list = self.game_data.translate_str_to_hex(ff8_str)
        ff8_hex = bytearray(ff8_list)
        #self.assertEqual(len(ff8_hex), 6)
        #self.assertEqual(ff8_hex, b'Xfgq \xe8')
        ff8_re_str = self.game_data.translate_hex_to_str(ff8_hex)
        self.assertEqual(ff8_re_str, ff8_str)

    def test_sysfnt_var_simple(self):
        ff8_str = "{xdf}"
        ff8_list = self.game_data.translate_str_to_hex(ff8_str)
        ff8_hex = bytearray(ff8_list)
        self.assertEqual(len(ff8_hex), 1)
        self.assertEqual(ff8_hex, bytes([0xdf]))
        ff8_re_str = self.game_data.translate_hex_to_str(ff8_hex)
        self.assertEqual(ff8_re_str, ff8_str)

    def test_sysfnt_var_double(self):
        ff8_str = "{x1e1f}"
        ff8_list = self.game_data.translate_str_to_hex(ff8_str)
        ff8_hex = bytearray(ff8_list)
        self.assertEqual(len(ff8_hex), 2)
        self.assertEqual(ff8_hex, bytes([0x1e, 0x1f]))
        ff8_re_str = self.game_data.translate_hex_to_str(ff8_hex)
        self.assertEqual(ff8_re_str, ff8_str)

    def test_sysfnt_character(self):
        ff8_str = "{x0330}"
        ff8_list = self.game_data.translate_str_to_hex(ff8_str)
        ff8_hex = bytearray(ff8_list)
        self.assertEqual(len(ff8_hex), 2)
        self.assertEqual(ff8_hex, bytes([0x03, 0x30]))
        ff8_re_str = self.game_data.translate_hex_to_str(ff8_hex)
        self.assertEqual(ff8_re_str, "{Squall}")

        ff8_str = "{Squall}{Zell}{Irvine}{Quistis}{Rinoa}{Selphie}{Seifer}{Edea}{Laguna}{Kiros}{Ward}{Angelo}{Griever}{Boko}"
        ff8_list = self.game_data.translate_str_to_hex(ff8_str)
        ff8_hex = bytearray(ff8_list)
        self.assertEqual(len(ff8_hex), 28)
        self.assertEqual(ff8_hex, bytes([0x03, 0x30, 0x03, 0x31, 0x03, 0x32, 0x03, 0x33, 0x03, 0x34, 0x03, 0x35,
                                         0x03, 0x36, 0x03, 0x37, 0x03, 0x38, 0x03, 0x39, 0x03, 0x3a, 0x03, 0x40, 0x03,
                                         0x50, 0x03, 0x60]))
        ff8_re_str = self.game_data.translate_hex_to_str(ff8_hex)
        self.assertEqual(ff8_re_str, ff8_str)

    def test_sysfnt_icons(self):
        ff8_str = "{x0520}"
        ff8_list = self.game_data.translate_str_to_hex(ff8_str)
        ff8_hex = bytearray(ff8_list)
        self.assertEqual(len(ff8_hex), 2)
        self.assertEqual(ff8_hex, bytes([0x05, 0x20]))
        ff8_re_str = self.game_data.translate_hex_to_str(ff8_hex)
        self.assertEqual(ff8_re_str, "{L2}")

        # Every code the exe resolves (0x20-0x7E, TEXT_ICON_CODE_TO_SPRITE) has a name that round-trips
        icon_names = self.game_data.sysfnt_data_json['Icons']
        self.assertEqual(len(icon_names), 0x7F - 0x20)
        ff8_str = "".join("{" + name + "}" for name in icon_names)
        ff8_hex = bytearray(self.game_data.translate_str_to_hex(ff8_str))
        self.assertEqual(ff8_hex, bytes(b for code in range(0x20, 0x7F) for b in (0x05, code)))
        self.assertEqual(self.game_data.translate_hex_to_str(ff8_hex), ff8_str)

        # The two stars text can draw: 0x43 = sprite 175 (green, absorb), 0x44 = sprite 214
        self.assertEqual(self.game_data.translate_hex_to_str(bytes([0x05, 0x43, 0x05, 0x44])),
                         "{AbsorbStar}{WhiteStar}")
        self.assertEqual(self.game_data.translate_hex_to_str(bytes([0x05, 0x5D])), "{ElementFire}")
        self.assertEqual(self.game_data.translate_hex_to_str(bytes([0x05, 0x7F])), "{x057f}")

        # Names from before the fix still encode to their old byte (old CSVs stay byte-exact)
        self.assertEqual(bytes(self.game_data.translate_str_to_hex("{CommandAbility}{Fire}{Drain}")),
                         bytes([0x05, 0x43, 0x05, 0x49, 0x05, 0x5D]))

    def test_sysfnt_color(self):
        ff8_str = "{x0620}"
        ff8_list = self.game_data.translate_str_to_hex(ff8_str)
        ff8_hex = bytearray(ff8_list)
        self.assertEqual(len(ff8_hex), 2)
        self.assertEqual(ff8_hex, bytes([0x06, 0x20]))
        ff8_re_str = self.game_data.translate_hex_to_str(ff8_hex)
        self.assertEqual(ff8_re_str, "{Darkgrey}")
        # Test char to char
        ff8_str = ("{Darkgrey}{Grey}{Yellow}{Red}{Green}{Blue}{Purple}{White}{DarkgreyBlink}{GreyBlink}"
                   "{YellowBlink}{RedBlink}{GreenBlink}{BlueBlink}{PurpleBlink}{WhiteBlink}")
        ff8_list = self.game_data.translate_str_to_hex(ff8_str)
        ff8_hex = bytearray(ff8_list)
        self.assertEqual(len(ff8_hex), 32)
        ff8_re_str = self.game_data.translate_hex_to_str(ff8_hex)
        self.assertEqual(ff8_re_str, ff8_str)

    def test_sysfnt_skill(self):
        ff8_str = "{x0c60}"
        ff8_list = self.game_data.translate_str_to_hex(ff8_str)
        ff8_hex = bytearray(ff8_list)
        self.assertEqual(len(ff8_hex), 2)
        self.assertEqual(ff8_hex, bytes([0x0c, 0x60]))
        ff8_re_str = self.game_data.translate_hex_to_str(ff8_hex)
        self.assertEqual(ff8_re_str, "{Quezacotl}")
        # Test char to char
        ff8_str = ("{Quezacotl}{Shiva}{Ifrit}{Sire}{Brothers}{Diablos}{Carbuncle}{Leviathan}{Pandemona}{Cerberus}"
                   "{Alexander}{Doomtrain}{Bahamut}{Cactuar}{Tonberry}{Eden}")
        ff8_list = self.game_data.translate_str_to_hex(ff8_str)
        ff8_hex = bytearray(ff8_list)
        self.assertEqual(len(ff8_hex), 32)
        ff8_re_str = self.game_data.translate_hex_to_str(ff8_hex)
        self.assertEqual(ff8_re_str, ff8_str)

    def test_sysfnt_cursor_location(self):
        ff8_str = "{x0b20}"
        ff8_list = self.game_data.translate_str_to_hex(ff8_str)
        ff8_hex = bytearray(ff8_list)
        self.assertEqual(len(ff8_hex), 2)
        self.assertEqual(ff8_hex, bytes([0x0b, 0x20]))
        ff8_re_str = self.game_data.translate_hex_to_str(ff8_hex)
        self.assertEqual(ff8_re_str, "{Cursor_location_id:0x20}")

        ff8_hex = bytes([0x0b, 0x20, 0x21])
        ff8_re_str = self.game_data.translate_hex_to_str(ff8_hex, cursor_location_size=3)
        self.assertEqual(ff8_re_str, "{Cursor_location_id:0x2021}")

        ff8_str = "{Cursor_location_id:0x2021}"
        ff8_list = self.game_data.translate_str_to_hex(ff8_str)
        ff8_hex = bytearray(ff8_list)
        self.assertEqual(len(ff8_hex), 3)
        self.assertEqual(ff8_hex, bytes([0x0b, 0x20, 0x021]))
        ff8_re_str = self.game_data.translate_hex_to_str(ff8_hex, cursor_location_size=3)
        self.assertEqual(ff8_re_str, "{Cursor_location_id:0x2021}")

        ff8_str = "{Cursor_location_id:0x20}"
        ff8_list = self.game_data.translate_str_to_hex(ff8_str)
        ff8_hex = bytearray(ff8_list)
        self.assertEqual(len(ff8_hex), 2)
        self.assertEqual(ff8_hex, bytes([0x0b, 0x20]))
        ff8_re_str = self.game_data.translate_hex_to_str(ff8_hex)
        self.assertEqual(ff8_re_str, "{Cursor_location_id:0x20}")

    def test_card_img(self):
        for el in self.game_data.card_data_json["card_type"]:
            self.assertNotEqual(el['img'], None)
        for el in self.game_data.card_data_json["card_info"]:
            self.assertNotEqual(el['img'], None)


if __name__ == '__main__':
    unittest.main()
