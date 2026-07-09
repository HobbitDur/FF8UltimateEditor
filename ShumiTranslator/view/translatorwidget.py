import string

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPlainTextEdit, QPushButton, QComboBox, \
    QMessageBox

from FF8GameData.gamedata import GameData


class TranslatorWidget(QWidget):
    AUTO_FORMAT = "Auto detect"
    HEX_FORMAT = "Hexa values"
    ASCII_FORMAT = "Ascii characters"

    def __init__(self, game_data: GameData):
        QWidget.__init__(self)
        self.game_data = game_data

        # FF8 side
        self.__ff8_label = QLabel("<b>FF8 text</b>")
        self.__ff8_format_widget = QComboBox()
        self.__ff8_format_widget.addItems([self.AUTO_FORMAT, self.HEX_FORMAT, self.ASCII_FORMAT])
        self.__ff8_format_widget.setToolTip("Format of the FF8 text.<br/>"
                                            "Hexa values are like \"48 65 6c\" (0x prefix optional, \"2 0\" means \"0x02 0x00\").<br/>"
                                            "Auto detect treats the text as hexa values if possible, ascii characters otherwise.<br/>"
                                            "Also used as output format when translating Classic -> FF8.")
        self.__ff8_text_widget = QPlainTextEdit()
        self.__ff8_text_widget.setPlaceholderText("FF8 text (hexa values or ascii characters)")
        self.__ff8_text_widget.setMinimumSize(400, 150)

        self.__ff8_top_layout = QHBoxLayout()
        self.__ff8_top_layout.addWidget(self.__ff8_label)
        self.__ff8_top_layout.addWidget(self.__ff8_format_widget)
        self.__ff8_top_layout.addStretch(1)

        self.__ff8_layout = QVBoxLayout()
        self.__ff8_layout.addLayout(self.__ff8_top_layout)
        self.__ff8_layout.addWidget(self.__ff8_text_widget)

        # Translation buttons
        self.__to_classic_button = QPushButton("FF8 -> Classic")
        self.__to_classic_button.setToolTip("Translate the FF8 text to readable text")
        self.__to_classic_button.clicked.connect(self.__translate_to_classic)
        self.__to_ff8_button = QPushButton("Classic -> FF8")
        self.__to_ff8_button.setToolTip("Translate the readable text to FF8 text")
        self.__to_ff8_button.clicked.connect(self.__translate_to_ff8)

        self.__button_layout = QVBoxLayout()
        self.__button_layout.addStretch(1)
        self.__button_layout.addWidget(self.__to_classic_button)
        self.__button_layout.addWidget(self.__to_ff8_button)
        self.__button_layout.addStretch(1)

        # Classic side
        self.__classic_label = QLabel("<b>Classic text</b>")
        self.__classic_text_widget = QPlainTextEdit()
        self.__classic_text_widget.setPlaceholderText("Readable text")
        self.__classic_text_widget.setMinimumSize(400, 150)

        self.__classic_top_layout = QHBoxLayout()
        self.__classic_top_layout.addWidget(self.__classic_label)
        self.__classic_top_layout.addStretch(1)

        self.__classic_layout = QVBoxLayout()
        self.__classic_layout.addLayout(self.__classic_top_layout)
        self.__classic_layout.addWidget(self.__classic_text_widget)

        self.__main_layout = QHBoxLayout()
        self.__main_layout.addLayout(self.__ff8_layout)
        self.__main_layout.addLayout(self.__button_layout)
        self.__main_layout.addLayout(self.__classic_layout)
        self.setLayout(self.__main_layout)

    @staticmethod
    def __hex_to_bytes(text: str):
        # Each token separated by spaces or commas is a hex byte value, 0x prefix optional.
        # Odd-length tokens are zero padded ("2 0" means "0x02 0x00"), longer ones split into bytes ("4c63" means "0x4c 0x63").
        data_hex = bytearray()
        for token in text.replace(",", " ").split():
            if token.lower().startswith("0x"):
                token = token[2:]
            if not token or any(char not in string.hexdigits for char in token):
                raise ValueError(f"'{token}' is not an hexa value")
            if len(token) % 2 == 1:
                token = "0" + token
            data_hex.extend(bytearray.fromhex(token))
        return data_hex

    @staticmethod
    def __ascii_to_bytes(text: str):
        data_hex = bytearray()
        for char in text:
            if ord(char) > 0xFF:
                raise ValueError(f"Character '{char}' is not an ascii character")
            data_hex.append(ord(char))
        return data_hex

    def __translate_to_classic(self):
        ff8_text = self.__ff8_text_widget.toPlainText()
        current_format = self.__ff8_format_widget.currentText()
        try:
            if current_format == self.HEX_FORMAT:
                data_hex = self.__hex_to_bytes(ff8_text)
            elif current_format == self.ASCII_FORMAT:
                data_hex = self.__ascii_to_bytes(ff8_text)
            else:  # Auto detect: hexa values if possible, ascii characters otherwise
                try:
                    data_hex = self.__hex_to_bytes(ff8_text)
                except ValueError:
                    data_hex = self.__ascii_to_bytes(ff8_text)
            classic_text = self.game_data.translate_hex_to_str(data_hex)
        except ValueError as e:
            print(f"Value Error: {ff8_text} with info: {e}")
            self.__show_error(f"Can't translate the FF8 text: <b>{e}</b><br>"
                              f"In hexa format, the text should only contain hexa values like <b>48 65 6c 6c 6f</b> (spaces, commas and 0x prefixes are accepted).")
            return
        self.__classic_text_widget.setPlainText(classic_text)

    def __translate_to_ff8(self):
        classic_text = self.__classic_text_widget.toPlainText()
        try:
            encode_list = self.game_data.translate_str_to_hex(classic_text)
        except ValueError as e:
            print(f"Value Error: {classic_text} with info: {e}")
            self.__show_error(f"Unknown character in sentence: <b>{classic_text}</b><br>"
                              "For the moment, the tool doesn't allow to just write a forbidden char like <b>{</b> or <b>}</b>.<br>"
                              "If you want to write a character like <b>{HP}</b>, copy paste both bracket.")
            return
        if self.__ff8_format_widget.currentText() == self.ASCII_FORMAT:
            self.__ff8_text_widget.setPlainText("".join(chr(x) for x in encode_list))
        else:
            self.__ff8_text_widget.setPlainText(bytearray(encode_list).hex(" "))

    def __show_error(self, text):
        message_box = QMessageBox()
        message_box.setText(text)
        message_box.setIcon(QMessageBox.Icon.Critical)
        message_box.setWindowTitle("ShumiTranslator - Translator")
        message_box.exec()
