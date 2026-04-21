import os
import pathlib
import xml.etree.ElementTree as ET

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QVBoxLayout, QWidget, QScrollArea, QPushButton, QFileDialog, QHBoxLayout, QLabel, \
    QMessageBox, QPlainTextEdit

from FF8GameData.dat.commandanalyser import CurrentIfType
from FF8GameData.dat.sequenceanalyser import SequenceAnalyser
from Ifrit.ifritmanager import IfritManager
from IfritSeq.seqwidget import SeqWidget


class IfritSeqWidget(QWidget):
    ADD_LINE_SELECTOR_ITEMS = ["Condition", "Command"]
    EXPERT_SELECTOR_ITEMS = ["User-friendly", "Hex-editor", "Raw-code", "IfritAI-code"]
    MAX_COMMAND_PARAM = 7
    MAX_OP_ID = 61
    MAX_OP_CODE_VALUE = 255
    MIN_OP_CODE_VALUE = 0

    def __init__(self, ifrit_manager:IfritManager,icon_path="Resources"):
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
        self.__ifrit_icon = QIcon(os.path.join(icon_path, 'ifrit.ico'))
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

        self.seq_data_widget= []

        self.seq_analyze_textarea = QPlainTextEdit()
        self.seq_analyze_button = QPushButton("Analyze")
        self.seq_analyze_button.clicked.connect(self.__analyze_sequence)
        self.layout_top = QHBoxLayout()
        self.layout_top.addWidget(self._import_xml_button)
        self.layout_top.addWidget(self._export_xml_button)
        self.layout_top.addWidget(self.info_button)
        self.layout_top.addStretch(1)


        # The main horizontal will be for code expert, when ai layout will be for others

        self.main_vertical_layout = QVBoxLayout()
        self.main_horizontal_layout = QHBoxLayout()
        self.main_horizontal_layout.addLayout(self.main_vertical_layout)
        self.main_horizontal_layout.addWidget(self.seq_analyze_textarea)
        self.window_layout.addLayout(self.layout_top)

        self.layout_main = QVBoxLayout()

        self.window_layout.addWidget(self.seq_analyze_button)
        self.window_layout.addWidget(self.scroll_area)
        self.scroll_widget.setLayout(self.layout_main)
        self.layout_main.addLayout(self.main_horizontal_layout)

        #self.show()

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


    def load_file(self, path: str):
        self.__load_file(path)

    def save_file(self):
        self.__save_file()
    def __save_file(self):
        self.ifrit_manager.enemy.seq_animation_data['seq_animation_data'] = []
        for index, seq_widget in enumerate(self.seq_data_widget):
            self.ifrit_manager.enemy.seq_animation_data['seq_animation_data'].append({"id": seq_widget.getId(), "data":seq_widget.getByteData()})
        self.ifrit_manager.save_file(self.file_loaded)
        print("File saved")

    def __load_file(self, file_to_load: str = ""):
        #file_to_load = os.path.join("c0m028.dat")  # For developing faster
        if not file_to_load:
            file_to_load = self.file_dialog.getOpenFileName(parent=self, caption="Search dat file", filter="*.dat")[0]
        if file_to_load:
            #self.__clear_lines(delete_data=True)
            self.file_loaded = file_to_load
            self.clear_lines()
            self.__setup_section_data()
            self.__analyze_sequence()
        self._export_xml_button.setEnabled(True)
        self._import_xml_button.setEnabled(True)

    def __reload_file(self):
        self.clear_lines()

        self.__load_file(self.file_loaded)

    def clear_lines(self):
        for index_to_remove in range(len(self.seq_data_widget)):
            self.seq_data_widget[index_to_remove].deleteLater()
            self.seq_data_widget[index_to_remove].setParent(None)
            self.main_vertical_layout.takeAt(index_to_remove)
        self.seq_data_widget= []

    def __setup_section_data(self):
        for index, seq_data in enumerate(self.ifrit_manager.enemy.seq_animation_data['seq_animation_data']):
            self.seq_data_widget.append(SeqWidget(seq_data["data"], seq_data['id']))
        for index, seq_widget in enumerate( self.seq_data_widget):
            self.main_vertical_layout.addWidget(seq_widget)

    def __analyze_sequence(self):
        text_analyze = ""
        for seq_widget in self.seq_data_widget:
            text_analyze += f"--- seq {seq_widget.getId()} ---\n"
            text_analyze +=  SequenceAnalyser(game_data=self.ifrit_manager.game_data, model_anim_data=self.ifrit_manager.enemy.model_animation_data, sequence=seq_widget.getByteData()).get_text()
            text_analyze += "\n"
        self.seq_analyze_textarea.setPlainText(text_analyze)

    def _export_xml_file(self):
        default_name = self.ifrit_manager.enemy.origin_file_name.replace('.dat', '.xml')
        xml_file_to_export = self.file_dialog.getSaveFileName(parent=self, caption="Xml file to save", directory=default_name)[0]
        # xml_file_to_export = os.path.join("../Cronos/md_file", "c0m001.md")  # For developing faster
        if xml_file_to_export:
            self.create_anim_seq_xml(self.ifrit_manager.enemy.seq_animation_data['seq_animation_data'], xml_file_to_export)

    @staticmethod
    def create_anim_seq_xml(seq_animation_data:dict, xml_file:str):

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
        # xml_file_to_load = os.path.join("../Cronos/md_file", "c0m001.md")  # For developing faster
        if xml_file_to_load:
            seq_animation_data = self.create_anim_seq_data_from_xml(xml_file_to_load)
            if seq_animation_data:
                self.ifrit_manager.enemy.seq_animation_data['seq_animation_data'] = seq_animation_data
                self.clear_lines()
                self.__setup_section_data()
                self.__analyze_sequence()


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



