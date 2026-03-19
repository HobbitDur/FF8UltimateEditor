import os
import sys
from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QWidget, QComboBox, QHBoxLayout, QVBoxLayout, QLabel, QFrame, QStackedWidget

from CCGroup.ccgroup import CCGroupWidget
from DrawEditor.draweditorwidget import DrawEditorWidget
from ExeLauncher.cactiliolauncher import CactilioLauncher
from ExeLauncher.delinglauncher import DelingLauncher
from ExeLauncher.doomtrainlauncher import DoomtrainLauncher
from ExeLauncher.ff8ultimatelauncher import FF8UltimateLauncher
from ExeLauncher.hynelauncher import HyneLauncher
from ExeLauncher.ifritguilauncher import IfritGuiLauncher
from ExeLauncher.junkshop import JunkshopLauncher
from ExeLauncher.quezacotllauncher import QuezacotlLauncher
from ExeLauncher.sirenlauncher import SirenLauncher
from IfritAI.ifritaiwidget import IfritAIWidget
from IfritSeq.ifritseqwidget import IfritSeqWidget
from IfritTexture.ifrittexturewidget import IfritTextureWidget
from IfritXlsx.ifritxlsxwidget import IfritXlsxWidget
from ShumiTranslator.shumitranslator import ShumiTranslator
from SmallWidget.externaltoolwidget import ExternalToolWidget
from TonberryShop.tonberryshop import TonberryShop
from ToolUpdate.toolupdatewidget import ToolUpdateWidget


class FF8UltimateEditorWidget(QWidget):

    def __init__(self, resources_path='Resources', game_data_path='FF8GameData'):
        QWidget.__init__(self)

        # 1. Basic Window Setup
        if getattr(sys, 'frozen', False):  # Check if running as exe
            self.setup_logging()

        self.setWindowTitle("FF8 ultimate editor")
        self.setWindowIcon(QIcon(os.path.join(resources_path, 'hobbitdur.ico')))

        self._main_layout = QVBoxLayout(self)
        self.setLayout(self._main_layout)

        # 2. Define the Tool Options
        self.HOBBIT_OPTION_ITEMS = [
            "IfritAI (AI editor)",
            "IfritXlsx (Stat editor)",
            "ShumiTranslator(All text editor)",
            "TonberryShop (Shop editor)",
            "CCGroup (Card value editor)",
            "IfritSeq (Anim seq editor)",
            "Draw editor",
            "IfritTexture (Monster texture editor)"
        ]

        # 3. Header: Program Selection (ComboBox)
        self._program_option_title = QLabel("Hobbit tools:")
        self._program_option = QComboBox()
        self._program_option.addItems(self.HOBBIT_OPTION_ITEMS)
        self._program_option.setCurrentIndex(0)
        self._program_option.activated.connect(self._program_option_change)
        self._program_option.setToolTip("Choose which program to edit your c0m file")

        self._program_option_layout = QHBoxLayout()
        self._program_option_layout.addWidget(self._program_option_title)
        self._program_option_layout.addWidget(self._program_option)

        # 4. Header: External Tool Buttons
        self._external_program_title = QLabel("External program:")
        self._tool_update_widget = ToolUpdateWidget(self.tools_to_update)

        # Initialize External Tool Buttons
        self._self_button = ExternalToolWidget(os.path.join(resources_path, 'hobbitdur.ico'), self._launch_FF8Ultimate, "Launch FF8UltimateEditor")
        self._ifrit_gui_button = ExternalToolWidget(os.path.join(resources_path, 'ifritGui.ico'), self._launch_ifritGui, "Launch original ifrit soft")
        self._Quezacotl_button = ExternalToolWidget(os.path.join(resources_path, 'Quezacotl.ico'), self._launch_Quezacotl, "Launch Quezacotl (init.out editor)")
        self._siren_button = ExternalToolWidget(os.path.join(resources_path, 'siren.ico'), self._launch_siren, "Launch siren (price.bin editor)")
        self._junkshop_button = ExternalToolWidget(os.path.join(resources_path, 'junkshop.ico'), self._launch_junkshop, "Launch junkshop (mweapon.bin editor)")
        self._doomtrain_button = ExternalToolWidget(os.path.join(resources_path, 'doomtrain.ico'), self._launch_doomtrain, "Launch doomtrain (kernel.bin editor)")
        self._cactilio_button = ExternalToolWidget(os.path.join(resources_path, 'jumbo_cactuar.ico'), self._launch_cactilio, "Launch Jumbo cactuar (Scene.out editor)")
        self._deling_button = ExternalToolWidget(os.path.join(resources_path, 'deling.ico'), self._launch_deling, "Launch deling (Archive editor)")
        self._hyne_button = ExternalToolWidget(os.path.join(resources_path, 'hyne.ico'), self._launch_hyne, "Launch hyne (Save editor)")

        # External Program Layout Assembly
        self._external_program_layout = QHBoxLayout()
        self._external_program_layout.addWidget(self._tool_update_widget, alignment=Qt.AlignmentFlag.AlignCenter)
        self._external_program_layout.addWidget(self._external_program_title, alignment=Qt.AlignmentFlag.AlignCenter)
        self._external_program_layout.addWidget(self._self_button, alignment=Qt.AlignmentFlag.AlignCenter)
        self._external_program_layout.addWidget(self._ifrit_gui_button, alignment=Qt.AlignmentFlag.AlignCenter)
        self._external_program_layout.addWidget(self._Quezacotl_button, alignment=Qt.AlignmentFlag.AlignCenter)
        self._external_program_layout.addWidget(self._siren_button, alignment=Qt.AlignmentFlag.AlignCenter)
        self._external_program_layout.addWidget(self._junkshop_button, alignment=Qt.AlignmentFlag.AlignCenter)
        self._external_program_layout.addWidget(self._doomtrain_button, alignment=Qt.AlignmentFlag.AlignCenter)
        self._external_program_layout.addWidget(self._cactilio_button, alignment=Qt.AlignmentFlag.AlignCenter)
        self._external_program_layout.addWidget(self._hyne_button, alignment=Qt.AlignmentFlag.AlignCenter)
        self._external_program_layout.addWidget(self._deling_button, alignment=Qt.AlignmentFlag.AlignCenter)
        self._external_program_layout.addStretch(1)

        # Combine Header Layouts
        self._enhance_layout = QHBoxLayout()
        self._enhance_layout.addLayout(self._program_option_layout)
        self._enhance_layout.addLayout(self._external_program_layout)
        self._enhance_layout.addStretch(1)

        self._enhance_container = QWidget()
        self._enhance_container.setLayout(self._enhance_layout)

        # Separator Line
        self._enhance_end_separator_line = QFrame()
        self._enhance_end_separator_line.setFrameStyle(QFrame.Shape.HLine | QFrame.Shadow.Sunken)
        self._enhance_end_separator_line.setLineWidth(1)

        # 5. Middle Section: Tool Widgets & QStackedWidget
        self.tool_stack = QStackedWidget()

        # Initialize internal tools
        self._ifritAI_widget = IfritAIWidget(icon_path=resources_path, game_data_folder=os.path.join(game_data_path))
        self._ifritxlsx_widget = IfritXlsxWidget(icon_path=os.path.join(resources_path), game_data_folder=os.path.join(game_data_path))
        self._shumi_translator_widget = ShumiTranslator(icon_path=os.path.join(resources_path), game_data_folder=os.path.join(game_data_path))
        self._tonberry_shop_widget = TonberryShop(resource_folder=os.path.join(resources_path))
        self._ccgroup_widget = CCGroupWidget(icon_path=os.path.join(resources_path), game_data_path=os.path.join(game_data_path))
        self._ifritseq_widget = IfritSeqWidget(icon_path=os.path.join(resources_path), game_data_folder=os.path.join(game_data_path))
        self._draw_editor_widget = DrawEditorWidget(icon_path=os.path.join(resources_path), game_data_folder=os.path.join(game_data_path))
        self._ifrittexture_widget = IfritTextureWidget(game_data_folder=os.path.join(game_data_path))

        # Add to Stack (MUST match HOBBIT_OPTION_ITEMS order)
        self.tool_stack.addWidget(self._ifritAI_widget)  # Index 0
        self.tool_stack.addWidget(self._ifritxlsx_widget)  # Index 1
        self.tool_stack.addWidget(self._shumi_translator_widget)  # Index 2
        self.tool_stack.addWidget(self._tonberry_shop_widget)  # Index 3
        self.tool_stack.addWidget(self._ccgroup_widget)  # Index 4
        self.tool_stack.addWidget(self._ifritseq_widget)  # Index 5
        self.tool_stack.addWidget(self._draw_editor_widget)  # Index 6
        self.tool_stack.addWidget(self._ifrittexture_widget)  # Index 7

        # 6. Final UI Assembly
        self._main_layout.addWidget(self._enhance_container)
        self._main_layout.addWidget(self._enhance_end_separator_line)
        self._main_layout.addWidget(self.tool_stack)

        # 7. Initialize Launchers
        self.ifritGui_launcher = IfritGuiLauncher(os.path.join("ExternalTools", "IfritGui", "Ifrit.exe"), callback=None)
        self.Quezacotl_launcher = QuezacotlLauncher(os.path.join("ExternalTools", "Quezacotl", "Quezacotl.exe"), callback=None)
        self.siren_launcher = SirenLauncher(os.path.join("ExternalTools", "Siren", "Siren.exe"), callback=None)
        self.junkshop_launcher = JunkshopLauncher(os.path.join("ExternalTools", "Junkshop", "Junkshop.exe"), callback=None)
        self.doomtrain_launcher = DoomtrainLauncher(os.path.join("ExternalTools", "Doomtrain", "Doomtrain.exe"), callback=None)
        self.cactilio_launcher = CactilioLauncher(os.path.join("ExternalTools", "JumboCactuar", "Jumbo Cactuar.exe"), callback=None)
        self.deling_launcher = DelingLauncher(os.path.join("ExternalTools", "Deling", "Deling.exe"), callback=None)
        self.hyne_launcher = HyneLauncher(os.path.join("ExternalTools", "Hyne", "Hyne.exe"), callback=None)
        self.ff8ultimate_launcher = FF8UltimateLauncher(os.path.join("", "FF8UltimateEditor.exe"), callback=None)

        # Final setup for header height and initial state
        self._tool_update_widget.progress.show()
        self._tool_update_widget.progress_current_download.show()
        #self._enhance_container.setFixedHeight(self._enhance_container.sizeHint().height())
        self._tool_update_widget.progress.hide()
        self._tool_update_widget.progress_current_download.hide()

        #self.debug_widget_sizes()

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

    def _launch_hyne(self):
        self.hyne_launcher.launch()

    def _launch_FF8Ultimate(self):
        self.ff8ultimate_launcher.launch()

    def _program_option_change(self):
        """Simple logic to switch between tools"""
        index = self._program_option.currentIndex()
        self.tool_stack.setCurrentIndex(index)

    def tools_to_update(self):
        tool_list = []
        if self._self_button.update_selected:
            tool_list.append("Self")
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
        if self._hyne_button.update_selected:
            tool_list.append("Hyne")
        if self._deling_button.update_selected:
            tool_list.append("Deling")
            tool_list.append("DelingCli")
        tool_list.append("VincentTim")
        return tool_list

    @staticmethod
    def setup_logging():
        # Create logs directory
        if not os.path.exists('logs'):
            os.makedirs('logs')

        # Log file with timestamp
        log_file = f"logs/FF8UltimateEditor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

        # Redirect stdout and stderr to file
        sys.stdout = open(log_file, 'w')
        sys.stderr = sys.stdout

    def debug_widget_sizes(self):
        print("\n--- WIDGET HEIGHT DEBUGGER ---")
        widgets_to_check = [
            ("Main Window", self),
            ("Header Container", self._enhance_container),
            ("Separator Line", self._enhance_end_separator_line),
            ("Stacked Widget", self.tool_stack),
            ("IfritAI", self._ifritAI_widget),
            ("IfritXlsx", self._ifritxlsx_widget),
            ("IfritTexture", self._ifrittexture_widget),
            # Add any others you suspect here
        ]

        for name, widget in widgets_to_check:
            # sizeHint: What the widget PREFERS to be
            # minimumSize: The absolute limit the widget CANNOT go below
            # frameGeometry: What the widget currently IS in pixels
            hint = widget.sizeHint().height()
            min_h = widget.minimumSize().height()
            actual = widget.frameGeometry().height()

            print(f"{name.ljust(20)} | Actual: {actual}px | Hint: {hint}px | Min: {min_h}px")
        print("------------------------------\n")
