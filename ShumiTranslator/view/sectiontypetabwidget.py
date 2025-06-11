from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy

from ShumiTranslator.view.sectionwidget import SectionWidget


class SectionTypeTabWidget(QWidget):
    def __init__(self, section_list: [SectionWidget], section_type=None):
        QWidget.__init__(self)
        self._main_layout = QVBoxLayout()
        self._section_list = section_list
        if section_list:
            self._type_tab = section_list[0].section.type
        else:
            self._type_tab = section_type

        for section_widget in section_list:
            if section_widget.section.type != self._type_tab:
                print(
                    f"Error in sectiontabwidget, type {section_widget.section.type} given when expected {self._type_tab}")
            self._main_layout.addWidget(section_widget)
        self._main_layout.addStretch(1)
        self.setSizePolicy(QSizePolicy.Policy.Maximum,QSizePolicy.Policy.Maximum)
        self.setLayout(self._main_layout)

    def add_section_widget(self, section_widget: SectionWidget):
        if self._type_tab:
            if section_widget.section.type != self._type_tab:
                print(
                    f"Error in sectiontabwidget, type {section_widget.section.type} given when expected {self._type_tab}")
        else:
            self._type_tab = section_widget.section.type
        self._section_list.append(section_widget)
        self._main_layout.insertWidget(self._main_layout.count() - 1, section_widget)

    def get_type(self):
        return self._type_tab

