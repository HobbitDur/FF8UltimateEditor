import os

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QWidget, QComboBox, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QSizePolicy, QFrame

from CCGroup.ccgroup import CCGroupWidget
from ExeLauncher.cactiliolauncher import CactilioLauncher
from ExeLauncher.delinglauncher import DelingLauncher
from ExeLauncher.doomtrainlauncher import DoomtrainLauncher
from ExeLauncher.ifritguilauncher import IfritGuiLauncher
from ExeLauncher.junkshop import JunkshopLauncher
from ExeLauncher.quezacotllauncher import QuezacotlLauncher
from ExeLauncher.sirenlauncher import SirenLauncher
from IfritAI.ifritaiwidget import IfritAIWidget
from IfritSeq.ifritseqwidget import IfritSeqWidget
from IfritXlsx.ifritxlsxwidget import IfritXlsxWidget
from ShumiTranslator.shumitranslator import ShumiTranslator
from SmallWidget.externaltoolwidget import ExternalToolWidget
from TonberryShop.tonberryshop import TonberryShop
from ToolUpdate.toolupdatewidget import ToolUpdateWidget


class FF8UltimateEditorWidget(QWidget):

    def __init__(self, resources_path='Resources', game_data_path='FF8GameData'):
        QWidget.__init__(self)
        self.setWindowTitle("FF8 ultimate editor")
        #self.setMinimumSize(1280, 720)
        self.setWindowIcon(QIcon(os.path.join(resources_path, 'hobbitdur.ico')))
        self._main_layout = QVBoxLayout()
        self.setLayout(self._main_layout)

        self.HOBBIT_OPTION_ITEMS = ["AI editor (IfritAI)", "Stat editor (IfritXlsx)", "All text editor (ShumiTranslator)", "Shop editor (TonberryShop)", "Card value editor (CCGroup)", "IfritSeq (Anim seq editor)"]

        # Top widget to select what option we want
        self._program_option_title = QLabel("Hobbit tools:")
        self._program_option = QComboBox()
        self._program_option.addItems(self.HOBBIT_OPTION_ITEMS)
        self._program_option.setCurrentIndex(0)

        self._program_option.activated.connect(self._program_option_change)
        self._program_option.setToolTip("Choose which program to edit your c0m file")
        self._program_option_layout = QHBoxLayout()
        self._program_option_layout.addWidget(self._program_option_title)
        self._program_option_layout.addWidget(self._program_option)

        # External program
        self._external_program_title = QLabel("External program:")

        self._ifrit_gui_button = ExternalToolWidget(os.path.join(resources_path, 'ifritGui.ico'), self._launch_ifritGui, "Launch original ifrit soft")
        self._Quezacotl_button = ExternalToolWidget(os.path.join(resources_path, 'Quezacotl.ico'), self._launch_Quezacotl, "Launch Quezacotl (init.out editor)")
        self._siren_button = ExternalToolWidget(os.path.join(resources_path, 'siren.ico'), self._launch_siren, "Launch siren (price.bin editor)")
        self._junkshop_button = ExternalToolWidget(os.path.join(resources_path, 'junkshop.ico'), self._launch_junkshop, "Launch junkshop (mweapon.bin editor)")
        self._doomtrain_button = ExternalToolWidget(os.path.join(resources_path, 'doomtrain.ico'), self._launch_doomtrain, "Launch doomtrain (kernel.bin editor)")
        self._cactilio_button = ExternalToolWidget(os.path.join(resources_path, 'jumbo_cactuar.ico'), self._launch_cactilio, "Launch Jumbo cactuar (Scene.out editor)")
        self._deling_button = ExternalToolWidget(os.path.join(resources_path, 'deling.ico'), self._launch_deling, "Launch deling (Archive editor)")

        self._tool_update_widget = ToolUpdateWidget(self.tools_to_update)

        self._external_program_layout = QHBoxLayout()
        self._external_program_layout.addWidget(self._tool_update_widget, alignment=Qt.AlignmentFlag.AlignCenter)
        self._external_program_layout.addWidget(self._external_program_title, alignment=Qt.AlignmentFlag.AlignCenter)
        self._external_program_layout.addWidget(self._ifrit_gui_button, alignment=Qt.AlignmentFlag.AlignCenter)
        self._external_program_layout.addWidget(self._Quezacotl_button, alignment=Qt.AlignmentFlag.AlignCenter)
        self._external_program_layout.addWidget(self._siren_button, alignment=Qt.AlignmentFlag.AlignCenter)
        self._external_program_layout.addWidget(self._junkshop_button, alignment=Qt.AlignmentFlag.AlignCenter)
        self._external_program_layout.addWidget(self._doomtrain_button, alignment=Qt.AlignmentFlag.AlignCenter)
        self._external_program_layout.addWidget(self._cactilio_button, alignment=Qt.AlignmentFlag.AlignCenter)
        self._external_program_layout.addWidget(self._deling_button, alignment=Qt.AlignmentFlag.AlignCenter)
        self._external_program_layout.addStretch(1)

        self._enhance_end_separator_line = QFrame()
        self._enhance_end_separator_line.setFrameStyle(0x04)# Horizontal line
        self._enhance_end_separator_line.setLineWidth(1)

        self._enhance_layout = QHBoxLayout()
        self._enhance_layout.addLayout(self._program_option_layout)
        self._enhance_layout.addLayout(self._external_program_layout)
        self._enhance_layout.addStretch(1)




        # Man made widget
        self._ifritAI_widget = IfritAIWidget(icon_path=resources_path, game_data_folder=os.path.join(game_data_path))
        self._ifritxlsx_widget = IfritXlsxWidget(icon_path=os.path.join(resources_path), game_data_folder=os.path.join(game_data_path))
        self._shumi_translator_widget = ShumiTranslator(icon_path=os.path.join(resources_path), game_data_folder=os.path.join(game_data_path))
        self._tonberry_shop_widget = TonberryShop(resource_folder=os.path.join(resources_path))
        self._ccgroup_widget = CCGroupWidget(icon_path=os.path.join(resources_path), game_data_path=os.path.join(game_data_path) )
        self._ifritseq_widget = IfritSeqWidget(icon_path=os.path.join(resources_path), game_data_folder=os.path.join(game_data_path) )

        self._ifritxlsx_widget.hide()
        self._shumi_translator_widget.hide()
        self._tonberry_shop_widget.hide()
        self._ccgroup_widget.hide()
        self._ifritseq_widget.hide()
        self.ifritGui_launcher = IfritGuiLauncher(os.path.join("IfritGui", "publish", "Ifrit.exe"), callback=self._ifritGui_exit)
        self.Quezacotl_launcher = QuezacotlLauncher(os.path.join("Quezacotl", "Quezacotl.exe"), callback=None)
        self.siren_launcher = SirenLauncher(os.path.join("Siren", "Siren.exe"), callback=None)
        self.junkshop_launcher = JunkshopLauncher(os.path.join("Junkshop", "Junkshop.exe"), callback=None)
        self.doomtrain_launcher = DoomtrainLauncher(os.path.join("Doomtrain", "Doomtrain.exe"), callback=None)
        self.cactilio_launcher = CactilioLauncher(os.path.join("JumboCactuar", "Jumbo Cactuar.exe"), callback=None)
        self.deling_launcher = DelingLauncher(os.path.join("Deling", "Deling.exe"), callback=None)

        self._enhance_container = QWidget()
        self._enhance_container.setLayout(self._enhance_layout)
        self._main_layout.addWidget(self._enhance_container)
        self._main_layout.addWidget(self._enhance_end_separator_line)
        self._main_layout.addWidget(self._ifritAI_widget)
        self._main_layout.addWidget(self._ifritxlsx_widget)
        self._main_layout.addWidget(self._shumi_translator_widget)
        self._main_layout.addWidget(self._tonberry_shop_widget)
        self._main_layout.addWidget(self._ccgroup_widget)
        self._main_layout.addWidget(self._ifritseq_widget)

        self._tool_update_widget.progress.show()
        self._tool_update_widget.progress_current_download.show()
        self._enhance_container.setFixedHeight(self._enhance_container.sizeHint().height())
        self._tool_update_widget.progress.hide()
        self._tool_update_widget.progress_current_download.hide()

        self._ifritAI_widget.adjustSize()
        self._ifritxlsx_widget.adjustSize()
        self._shumi_translator_widget.adjustSize()
        self._ccgroup_widget.adjustSize()
        self._tonberry_shop_widget.adjustSize()
        # After adding to layout, get the natural height and set it as fixed
        self.adjustSize()

        #self._program_option_change()  # For dev faster

    def _launch_ifritGui(self):
        self.ifritGui_launcher.launch()
    def _launch_Quezacotl(self):
        self.Quezacotl_launcher.launch()
    def _launch_junkshop(self):
        self.junkshop_launcher.launch()
    def _launch_siren(self):
        self.siren_launcher.launch()
    def _launch_doomtrain(self):
        self.doomtrain_launcher.launch()
    def _launch_cactilio(self):
        self.cactilio_launcher.launch()
    def _launch_deling(self):
        self.deling_launcher.launch()

    def _ifritGui_exit(self):
        pass
        #if not self._ifritAI_widget.isVisible() and not self._ifritxlsx_widget.isVisible():
        #    exit(0)

    def _program_option_change(self):
        if self._program_option.currentIndex() == 0:
            self._ifritAI_widget.show()
            self._ifritxlsx_widget.hide()
            self._shumi_translator_widget.hide()
            self._tonberry_shop_widget.hide()
            self._ccgroup_widget.hide()
            self._ifritseq_widget.hide()
        elif self._program_option.currentIndex() == 1:
            self._ifritAI_widget.hide()
            self._ifritxlsx_widget.show()
            self._shumi_translator_widget.hide()
            self._tonberry_shop_widget.hide()
            self._ccgroup_widget.hide()
            self._ifritseq_widget.hide()
        elif self._program_option.currentIndex() == 2:
            self._ifritAI_widget.hide()
            self._ifritxlsx_widget.hide()
            self._shumi_translator_widget.show()
            self._tonberry_shop_widget.hide()
            self._ccgroup_widget.hide()
            self._ifritseq_widget.hide()
        elif self._program_option.currentIndex() == 3:
            self._ifritAI_widget.hide()
            self._ifritxlsx_widget.hide()
            self._shumi_translator_widget.hide()
            self._tonberry_shop_widget.show()
            self._ccgroup_widget.hide()
            self._ifritseq_widget.hide()
        elif self._program_option.currentIndex() == 4:
            self._ifritAI_widget.hide()
            self._ifritxlsx_widget.hide()
            self._shumi_translator_widget.hide()
            self._tonberry_shop_widget.hide()
            self._ccgroup_widget.show()
            self._ifritseq_widget.hide()
        elif self._program_option.currentIndex() == 5:
            self._ifritAI_widget.hide()
            self._ifritxlsx_widget.hide()
            self._shumi_translator_widget.hide()
            self._tonberry_shop_widget.hide()
            self._ccgroup_widget.hide()
            self._ifritseq_widget.show()
        else:
            print(f"Unexpected program option index:{self._program_option.currentIndex()} and name {self._program_option.currentText()}")

        self._ifritAI_widget.adjustSize()
        self._ifritxlsx_widget.adjustSize()
        self.adjustSize()

    def tools_to_update(self):
        tool_list = []
        if self._ifrit_gui_button.update_selected:
            tool_list.append("IfritGui")
        if self._Quezacotl_button.update_selected:
            tool_list.append("Quezacotl")
        if self._siren_button.update_selected:
            tool_list.append("Siren")
        if self._junkshop_button.update_selected:
            tool_list.append("Junkshop")
        if self._doomtrain_button.update_selected:
            tool_list.append("Doomtrain")
        if self._cactilio_button.update_selected:
            tool_list.append("JumboCactuar")
        if self._deling_button.update_selected:
            tool_list.append("Deling")
            tool_list.append("DelingCli")
        return tool_list












