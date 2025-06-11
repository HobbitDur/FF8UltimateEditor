from PyQt6.QtCore import QSignalBlocker
from PyQt6.QtWidgets import QPlainTextEdit, QWidget, QHBoxLayout, QLabel, QVBoxLayout, QMessageBox, QFrame

from FF8GameData.GenericSection.ff8text import FF8Text


class TranslationWidget(QWidget):

    def __init__(self, translation: FF8Text, line_number):
        QWidget.__init__(self)
        self.translation = translation
        self.__line_number = line_number

        self.__label_line_widget = QLabel(f"Line {self.__line_number}")
        self.__file_text_description_widget = QLabel("<b>Data read: </b>")
        self.__file_text_widget = QLabel()
        text_to_show = self.translation.get_str().replace('\\n', '\\n\n')
        self.__file_text_widget.setText(text_to_show)
        # self.__file_text_widget.setWordWrap(True)

        self.__custom_text_description_widget = QLabel("<b>Data modified: </b>")
        self.__custom_text_widget = QPlainTextEdit()
        text_to_show = self.translation.get_str().replace('\\n', '\n')
        font_height = self.__custom_text_widget.font().pointSize()
        self.__custom_text_widget.setPlainText(text_to_show)
        self.__custom_text_widget.setMinimumWidth(500)
        height = ((text_to_show.count('\n') + 1) * (font_height + 10)) + 10
        self.__custom_text_widget.setFixedHeight(height)
        self.__custom_text_widget.textChanged.connect(self.__custom_text_changed)
        # self.__custom_text_widget.setMaximumHeight(28)

        self.__text_original_layout = QHBoxLayout()
        # self.__text_original_layout.addSpacing(20)
        self.__text_original_layout.addWidget(self.__file_text_description_widget)
        self.__text_original_layout.addWidget(self.__file_text_widget)
        self.__text_original_layout.addStretch(1)

        self.__text_custom_layout = QHBoxLayout()
        # self.__text_custom_layout.addSpacing(20)
        self.__text_custom_layout.addWidget(self.__custom_text_description_widget)
        self.__text_custom_layout.addWidget(self.__custom_text_widget)
        self.__text_custom_layout.addStretch(1)

        self.__translation_layout = QVBoxLayout()
        self.__translation_layout.addLayout(self.__text_original_layout)
        self.__translation_layout.addLayout(self.__text_custom_layout)
        self.__translation_layout.addStretch(1)

        self.__end_separator_line = QFrame()
        self.__end_separator_line.setFrameStyle(0x05)  # Vertical line
        self.__end_separator_line.setLineWidth(2)

        self.__main_layout = QHBoxLayout()
        self.__main_layout.addWidget(self.__label_line_widget)
        self.__main_layout.addSpacing(5)
        self.__main_layout.addWidget(self.__end_separator_line)
        self.__main_layout.addSpacing(5)
        self.__main_layout.addLayout(self.__translation_layout)

        self.setLayout(self.__main_layout)

    def __custom_text_changed(self):
        try:
            self.translation.set_str(self.__custom_text_widget.toPlainText())
        except ValueError as e:
            print(f"Value Error: {self.__custom_text_widget.toPlainText()} with info: {e}")
            message_box = QMessageBox()
            message_box.setText(f"Unknown character in sentence: <b>{self.__custom_text_widget.toPlainText()}</b><br>"
                                "For the moment, the tool doesn't allow to just write a forbidden char like <b>{</b> or <b>}</b>.<br>"
                                "If you want to write a character like <b>{HP}</b>, copy paste both bracket.<br>"
                                "If you want to delete bracket, delete both bracket at same time.<br>"
                                "Sorry for the inconvenience. The line will be reverted.")
            message_box.setIcon(QMessageBox.Icon.Critical)
            message_box.setWindowTitle("ShumiTranslator - Forbidden char")
            message_box.exec()
            with QSignalBlocker(self.__custom_text_widget):
                self.__custom_text_widget.setPlainText(self.translation.get_str().replace('\\n', '\n'))

    def change_custom_text(self, custom_text):
        self.__custom_text_widget.setPlainText(custom_text)
        self.__custom_text_widget.setPlainText(self.translation.get_str().replace('\\n', '\n'))

    def get_custom_text(self):
        self.__custom_text_widget.toPlainText()

    def compress_str(self, compressible=3):
        self.translation.compress_str(compressible)
        with QSignalBlocker(self.__custom_text_widget):
            self.__custom_text_widget.setPlainText(self.translation.get_str().replace('\\n', '\n'))

    def uncompress_str(self):
        self.translation.uncompress_str()
        with QSignalBlocker(self.__custom_text_widget):
            self.__custom_text_widget.setPlainText(self.translation.get_str().replace('\\n', '\n'))
