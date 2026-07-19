from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QFrame, QPushButton

from FF8GameData.GenericSection.listff8text import ListFF8Text
from ShumiTranslator.view.translationwidget import TranslationWidget


class SectionWidget(QWidget):

    def __init__(self, section: ListFF8Text, first_section_line_index, allow_add=False):
        QWidget.__init__(self)

        self.section = section
        self.first_section_line_index = first_section_line_index
        self.__section_name_widget = QLabel()
        self.__section_name_widget.setText(f"<b><u>Section text n°{self.section.id}:</u></b> " + self.section.name)

        self.translation_widget_list = []
        self.__add_button = None

        self.__main_layout = QVBoxLayout()
        self.__main_layout.addWidget(self.__section_name_widget)

        self.setLayout(self.__main_layout)
        self.__create_sub_section_widget(allow_add)

    def __str__(self):
        return "Widget " + str(self.section)

    def __create_sub_section_widget(self, allow_add):
        for i, ff8_text in enumerate(self.section.get_text_list()):
            translation_widget = TranslationWidget(ff8_text, self.first_section_line_index + i)
            self.translation_widget_list.append(translation_widget)
            self.__main_layout.addWidget(self.translation_widget_list[-1])
        if allow_add:
            # Appends a new, empty entry (data_read starts blank - nothing to decode yet; fill in
            # data_modified, then Save). Whether/how the underlying format can address a new entry
            # (spare offset slot, growable table...) is on the format/section, not this widget.
            # Sits at the end of the section's entry list, left-aligned.
            self.__add_button = QPushButton("+ Add entry")
            self.__add_button.setToolTip("Append a new, empty text entry to this section")
            self.__add_button.clicked.connect(self.add_entry)
            self.__main_layout.addWidget(self.__add_button, alignment=Qt.AlignmentFlag.AlignLeft)
        end_separator_line = QFrame()
        end_separator_line.setFrameStyle(0x04)# Horizontal line
        end_separator_line.setLineWidth(2)
        self.__main_layout.addWidget(end_separator_line)


    def add_entry(self):
        """Append a new, empty text entry: data_read starts blank, data_modified is ready to type."""
        self.section.add_text(bytearray())
        new_text = self.section.get_text_list()[-1]
        line_number = self.first_section_line_index + len(self.translation_widget_list)
        translation_widget = TranslationWidget(new_text, line_number)
        self.translation_widget_list.append(translation_widget)
        # New entries land right above the Add-entry button, which stays the last row before the
        # trailing separator.
        insert_index = (self.__main_layout.indexOf(self.__add_button) if self.__add_button
                        else self.__main_layout.count() - 1)
        self.__main_layout.insertWidget(insert_index, translation_widget)
        return translation_widget

    def set_text_from_id(self, id: int, text: str):
        if id < len(self.translation_widget_list):
            self.translation_widget_list[id].change_custom_text(text)

    def get_text_from_id(self, id: int):
        if id < len(self.translation_widget_list):
            self.translation_widget_list[id].get_custom_text()

    def compress_str(self, compressible=3):
        for translation_widget in self.translation_widget_list:
            translation_widget.compress_str(compressible)

    def uncompress_str(self):
        for translation_widget in self.translation_widget_list:
            translation_widget.uncompress_str()

