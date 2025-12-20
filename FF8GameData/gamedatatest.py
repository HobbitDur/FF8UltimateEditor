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

        ff8_str = ("{L2}{R2}{L1}{R1}{Circle}{Triangle}{X}{Square}{0x0528:Unknown}{0x0529:Unknown}{0x052a:Unknown}"
                   "{0x052b:Unknown}{CrossTop}{CrossRight}{CrossDown}{CrossLeft}{0x0530:Unknown}{0x0531:Unknown}"
                   "{0x0532:Unknown}{0x0533:Unknown}{0x0534:Unknown}{0x0535:Unknown}{0x0536:Unknown}{0x0537:Unknown}"
                   "{Select}{0x0539:Unknown}{0x053a:Unknown}{START}{0x053c:Unknown}{0x053d:Unknown}{0x053e:Unknown}"
                   "{0x053f:Unknown}{MagicJunctioned}{LimitBreakArrow}{JunctionAbility}{CommandAbility}{0x0545:Unknown}"
                   "{CharacterAbility}{PartyAbility}{GFAbility}{MenuAbility}{Fire}{Ice}{Thunder}{Earth}{PoisonType}"
                   "{Wind}{Water}{Holy}{Death}{PoisonStatus}{Petrify}{Darkness}{Silence}{Berserk}{Zombie}{Sleep}{Slow}"
                   "{Stop}{Curse}{Confuse}{Drain}")
        ff8_list = self.game_data.translate_str_to_hex(ff8_str)
        ff8_hex = bytearray(ff8_list)
        self.assertEqual(len(ff8_hex), 124)
        ff8_re_str = self.game_data.translate_hex_to_str(ff8_hex)
        self.assertEqual(ff8_re_str, ff8_str)

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
