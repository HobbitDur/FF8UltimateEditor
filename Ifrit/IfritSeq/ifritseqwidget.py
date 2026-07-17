import os
import xml.etree.ElementTree as ET

from PyQt6.QtCore import QSize, QSettings
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QVBoxLayout, QWidget, QScrollArea, QPushButton, QFileDialog,
                             QHBoxLayout, QMessageBox, QLabel, QComboBox, QDialog,
                             QTextBrowser)

from FF8GameData.dat.commandanalyser import CurrentIfType
from FF8GameData.dat.sequencecodec import generate_help_html
from Ifrit.ifritmanager import IfritManager
from Ifrit.IfritSeq.seqwidget import SeqWidget, VIEW_HEX
from Ifrit.IfritSeq.seqcommandwidget import build_op_code_model


class IfritSeqWidget(QWidget):
    ADD_LINE_SELECTOR_ITEMS = ["Condition", "Command"]
    # Same pattern as IfritAI's expert modes, minus Raw-code which has no meaning here:
    # every view shows this sequence's translation next to it except the raw hex one.
    EXPERT_SELECTOR_ITEMS = ["User-friendly", "Hex-editor", "IfritSeq-code"]
    MAX_COMMAND_PARAM = 7
    MAX_OP_ID = 61
    MAX_OP_CODE_VALUE = 255
    MIN_OP_CODE_VALUE = 0

    def __init__(self, ifrit_manager: IfritManager, icon_path="Resources"):
        QWidget.__init__(self)
        self.current_if_index = 0
        self.file_loaded = ""
        self.window_layout = QVBoxLayout()
        self.setLayout(self.window_layout)
        self.scroll_widget = QWidget()
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.scroll_widget)
        self.ifrit_manager = ifrit_manager
        self.current_if_type = CurrentIfType.NONE
        self.file_dialog = QFileDialog()
        self.settings = QSettings("FF8UltimateEditor", "FF8UltimateEditor")
        self.__ifrit_icon = QIcon(os.path.join(icon_path, 'ifrit.ico'))
        self.__op_code_model = None  # built on first load, shared by every command row
        # Main window
        self._import_xml_button = QPushButton()
        self._import_xml_button.setIcon(QIcon(os.path.join(icon_path, 'xml_upload.png')))
        self._import_xml_button.setIconSize(QSize(30, 30))
        self._import_xml_button.setFixedSize(40, 40)
        self._import_xml_button.setToolTip("This allow to import sequence from xml file")
        self._import_xml_button.clicked.connect(self._load_xml_file)
        self._import_xml_button.setEnabled(False)

        self._export_xml_button = QPushButton()
        self._export_xml_button.setIcon(QIcon(os.path.join(icon_path, 'xml_save.png')))
        self._export_xml_button.setIconSize(QSize(30, 30))
        self._export_xml_button.setFixedSize(40, 40)
        self._export_xml_button.setToolTip("This allow to export sequence to xml file")
        self._export_xml_button.clicked.connect(self._export_xml_file)
        self._export_xml_button.setEnabled(False)

        self.info_button = QPushButton()
        self.info_button.setIcon(QIcon(os.path.join(icon_path, 'info.png')))
        self.info_button.setIconSize(QSize(30, 30))
        self.info_button.setFixedSize(40, 40)
        self.info_button.setToolTip("Show toolmaker info")
        self.info_button.clicked.connect(self.__show_info)

        expert_tooltip_text = "The expert mode allow you to change the display: <br/>" + \
            "<b><u>" + self.EXPERT_SELECTOR_ITEMS[0] + ":</u></b> One line per command " \
            "(op code names, one box per parameter), with the sequence translation<br/>" + \
            "<b><u>" + self.EXPERT_SELECTOR_ITEMS[1] + ":</u></b> For modifying directly the hex<br/>" + \
            "<b><u>" + self.EXPERT_SELECTOR_ITEMS[2] + ":</u></b> Sequence editor with the " \
            "IfritSeq language (one command per line, translation beside)"
        self.expert_selector_title = QLabel("Expert mode: ")
        self.expert_selector_title.setToolTip(expert_tooltip_text)
        self.expert_selector = QComboBox()
        self.expert_selector.addItems(self.EXPERT_SELECTOR_ITEMS)
        self.expert_selector.setCurrentIndex(
            self.settings.value("ifrit/Seq/expert_selector", defaultValue=0, type=int))
        self.expert_selector.setToolTip(expert_tooltip_text)
        self.expert_selector.activated.connect(self.__change_expert)

        # A standing reference for the IfritSeq-code language: every command it knows,
        # its syntax and what it does, generated straight from the same json + parser
        # logic the IfritSeq-code view itself uses (so it cannot say something the
        # parser would then refuse). Non-modal: it stays open for reference while typing.
        self.code_help_button = QPushButton("Code help")
        self.code_help_button.setToolTip("Reference for the IfritSeq-code language: "
                                         "every command, its syntax and what it does")
        self.code_help_button.clicked.connect(self.__show_code_help)
        self.__code_help_dialog = None

        self.seq_data_widget = []
        self.add_sequence_button = None  # trailing "append a new sequence" button

        self.layout_top = QHBoxLayout()
        self.layout_top.addWidget(self._import_xml_button)
        self.layout_top.addWidget(self._export_xml_button)
        self.layout_top.addWidget(self.info_button)
        self.layout_top.addWidget(self.expert_selector_title)
        self.layout_top.addWidget(self.expert_selector)
        self.layout_top.addWidget(self.code_help_button)
        self.layout_top.addStretch(1)

        self.main_vertical_layout = QVBoxLayout()
        self.main_vertical_layout.setSpacing(10)  # gap between each sequence frame
        self.window_layout.addLayout(self.layout_top)

        self.layout_main = QVBoxLayout()
        self.window_layout.addWidget(self.scroll_area)
        self.scroll_widget.setLayout(self.layout_main)
        self.layout_main.addLayout(self.main_vertical_layout)
        self.layout_main.addStretch(1)

    def __show_info(self):
        message_box = QMessageBox()
        message_box.setText(f"Tool done by <b>Hobbitdur</b>.<br/>"
                            f"You can support me on <a href='https://www.patreon.com/HobbitMods'>Patreon</a>.<br/>"
                            f"Special thanks to :<br/>"
                            f"&nbsp;&nbsp;-<b>Nihil</b> for beta testing and finding unknown values.<br/>"
                            f"&nbsp;&nbsp;-<b>myst6re</b> for all the retro-engineering.<br/>"
                            f"For more info on the command, you can check the <a href=\"https://hobbitdur.github.io/FF8ModdingWiki/technical-reference/battle/battle-scripts/\">wiki</a>.")
        message_box.setIcon(QMessageBox.Icon.Information)
        message_box.setWindowIcon(self.__ifrit_icon)
        message_box.setWindowTitle("IfritAI - Info")
        message_box.exec()

    def __show_code_help(self):
        if self.__code_help_dialog is None:
            self.__code_help_dialog = QDialog(self)
            self.__code_help_dialog.setWindowTitle("IfritSeq-code reference")
            self.__code_help_dialog.resize(900, 700)
            browser = QTextBrowser()
            browser.setOpenExternalLinks(True)
            browser.setHtml(generate_help_html(self.ifrit_manager.game_data))
            layout = QVBoxLayout()
            layout.addWidget(browser)
            self.__code_help_dialog.setLayout(layout)
        # Non-modal (show(), not exec()): the dialog stays open and usable side by side
        # with the code you are typing, instead of blocking the rest of the window.
        self.__code_help_dialog.show()
        self.__code_help_dialog.raise_()
        self.__code_help_dialog.activateWindow()

    def load_file(self, path: str):
        self.__load_file(path)

    def save_file(self):
        self.__save_file()

    def __save_file(self):
        self.ifrit_manager.enemy.seq_animation_data['seq_animation_data'] = []
        for index, seq_widget in enumerate(self.seq_data_widget):
            self.ifrit_manager.enemy.seq_animation_data['seq_animation_data'].append(
                {"id": seq_widget.getId(), "data": seq_widget.getByteData()})

    def __load_file(self, file_to_load: str = ""):
        if not file_to_load:
            file_to_load = self.file_dialog.getOpenFileName(parent=self, caption="Search dat file", filter="*.dat")[0]
        if file_to_load:
            self.file_loaded = file_to_load
            self.clear_lines()
            self.__setup_section_data()
        self._export_xml_button.setEnabled(True)
        self._import_xml_button.setEnabled(True)

    def clear_lines(self):
        self.seq_data_widget = []
        self.add_sequence_button = None
        while self.main_vertical_layout.count():
            item = self.main_vertical_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def __setup_section_data(self):
        if self.__op_code_model is None and self.ifrit_manager.game_data is not None:
            self.__op_code_model = build_op_code_model(self.ifrit_manager.game_data)
        view = self.expert_selector.currentIndex()
        # Show the sequences by id, not by their byte order in the file: the id is what
        # the game (and the user) refers to, so gaps - the sequences a monster does not
        # have - line up in order and their "Add" placeholder sits in the right place.
        seq_list = sorted(self.ifrit_manager.enemy.seq_animation_data['seq_animation_data'],
                          key=lambda seq: seq['id'])
        for seq_data in seq_list:
            self.__add_seq_widget(seq_data['data'], seq_data['id'], view)
        self.__add_trailing_button()

    def __add_seq_widget(self, data, seq_id, view):
        seq_widget = SeqWidget(data, seq_id, self.ifrit_manager.enemy.entity_type,
                               game_data=self.ifrit_manager.game_data,
                               op_code_model=self.__op_code_model)
        seq_widget.set_view(view)
        self.seq_data_widget.append(seq_widget)
        self.main_vertical_layout.addWidget(seq_widget)
        return seq_widget

    def __add_trailing_button(self):
        next_id = max((widget.getId() for widget in self.seq_data_widget), default=0) + 1
        self.add_sequence_button = QPushButton(f"+ Add sequence {next_id}")
        self.add_sequence_button.setToolTip("Append a brand-new sequence with the next "
                                            "id, extending the section")
        self.add_sequence_button.clicked.connect(self.__append_sequence)
        self.main_vertical_layout.addWidget(self.add_sequence_button)

    def __append_sequence(self):
        next_id = max((widget.getId() for widget in self.seq_data_widget), default=0) + 1
        view = self.expert_selector.currentIndex()
        # Drop the trailing button, add the new (already-present) sequence, put the button
        # back below it with the next id.
        self.add_sequence_button.setParent(None)
        self.add_sequence_button.deleteLater()
        self.add_sequence_button = None
        self.__add_seq_widget(bytearray(SeqWidget.DEFAULT_NEW_SEQUENCE), next_id, view)
        self.__add_trailing_button()

    def __change_expert(self):
        expert_chosen = self.expert_selector.currentIndex()
        self.settings.setValue("ifrit/Seq/expert_selector", expert_chosen)
        for seq_widget in self.seq_data_widget:
            seq_widget.set_view(expert_chosen)

    def _export_xml_file(self):
        default_name = self.ifrit_manager.enemy.origin_file_name.replace('.dat', '.xml')
        xml_file_to_export = self.file_dialog.getSaveFileName(parent=self, caption="Xml file to save", directory=default_name)[0]
        if xml_file_to_export:
            # Export what is on screen, not the last-saved model: fold the current widgets
            # back into the model first so unsaved edits are included.
            self.__save_file()
            self.create_anim_seq_xml(self.ifrit_manager.enemy.seq_animation_data['seq_animation_data'], xml_file_to_export)

    @staticmethod
    def create_anim_seq_xml(seq_animation_data: dict, xml_file: str):

        if xml_file:
            xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<sequence_animations>']

            for item in seq_animation_data:
                # Convert bytearray to hex string with spaces and uppercase
                if item['data']:
                    hex_data = ' '.join(f'{byte:02X}' for byte in item['data'])
                else:
                    hex_data = ""
                xml_lines.append(f'  <animation id="{item["id"]}">')
                xml_lines.append(f'    <data>{hex_data}</data>')
                xml_lines.append('  </animation>')

            xml_lines.append('</sequence_animations>')

            # Write to file
            with open(xml_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(xml_lines))

    def _load_xml_file(self):
        xml_file_to_load = self.file_dialog.getOpenFileName(parent=self, caption="Xml file to import", filter="*.xml")[0]
        if xml_file_to_load:
            seq_animation_data = self.create_anim_seq_data_from_xml(xml_file_to_load)
            if seq_animation_data:
                self.ifrit_manager.enemy.seq_animation_data['seq_animation_data'] = seq_animation_data
                self.clear_lines()
                self.__setup_section_data()

    @staticmethod
    def create_anim_seq_data_from_xml(xml_file: str) -> list[dict[str, bytearray | int]]:
        if xml_file:
            try:
                tree = ET.parse(xml_file)
                root = tree.getroot()

                seq_animation_data = []

                for animation_elem in root.findall('animation'):
                    anim_id = int(animation_elem.get('id'))
                    data_elem = animation_elem.find('data')

                    if data_elem.text and data_elem.text.strip():
                        # Convert space-separated hex string back to bytearray
                        hex_values = data_elem.text.strip().split()
                        byte_data = bytearray(int(hex_val, 16) for hex_val in hex_values)
                    else:
                        byte_data = bytearray()

                    seq_animation_data.append({
                        'id': anim_id,
                        'data': byte_data
                    })
                return seq_animation_data

            except ET.ParseError as e:
                print(f"Error parsing XML file: {e}")
                return None
            except FileNotFoundError:
                print(f"XML file not found: {xml_file}")
                return None
