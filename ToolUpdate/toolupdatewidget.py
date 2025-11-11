import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QObject, pyqtSignal, QThread, Qt, pyqtSlot
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QComboBox, QPushButton, QProgressBar, QVBoxLayout, QMessageBox, QApplication, QCheckBox, QGroupBox

from ToolUpdate.toolupdate import ToolDownloader


class OpIdChangedEmitter(QObject):
    op_id_signal = pyqtSignal()


class Installer(QObject):
    progress = pyqtSignal(int)
    completed = pyqtSignal(int)
    download_progress = pyqtSignal(int, int)
    update_mod_list_completed = pyqtSignal()

    @pyqtSlot(ToolDownloader, bool, list)
    def install(self, tool_updater:ToolDownloader, canary:bool, tool_list:list):
        for index, tool_name in enumerate(tool_list):
            if tool_name == "Self":
                tool_updater.download_self(self.download_progress.emit, canary=canary)
            else:
                tool_updater.update_one_tool(tool_name, self.download_progress.emit, canary=canary)
            self.progress.emit(index + 1)

        self.completed.emit(len(tool_list))


class ToolUpdateWidget(QWidget):
    install_requested = pyqtSignal(ToolDownloader, bool, list)

    def __init__(self,tool_list_callback:Callable, resource_path: str = "Resources" ):
        QWidget.__init__(self)
        self._tool_list_callback = tool_list_callback
        self.resource_path = resource_path
        self.self_update_request = False

        # Managing thread
        self.installer = Installer()
        self.installer_thread = QThread()
        self.installer.progress.connect(self.install_progress)
        self.installer.completed.connect(self.install_completed)
        self.installer.download_progress.connect(self.update_download)
        self.install_requested.connect(self.installer.install)
        self.installer.moveToThread(self.installer_thread)
        self.installer_thread.start()

        self.progress_install_index = 0

        self.install_over = QMessageBox(parent=self)
        self.install_over.setWindowTitle("Installing over! Now patching the tool")
        self.install_over.setText("Installing over!")

        self.progress = QProgressBar(parent=self)
        self.progress.setTextVisible(True)
        self.progress.setFormat("Full installation status")
        self.progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_current_download = QProgressBar(parent=self)
        self.progress_current_download.setTextVisible(True)
        self.progress_current_download.setFormat("Current download status")
        self.progress_current_download.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress.hide()
        self.progress_current_download.hide()
        self.tool_updater = ToolDownloader()

        self.canal_label = QLabel("Canal: ")

        self.canal_widget = QComboBox()
        self.canal_widget.addItems(["Stable", "Canary"])
        self.canal_widget.setCurrentIndex(0)
        # self.canal_widget.activated.connect(self.__section_change)
        self.canal_widget.setToolTip("Stable: Last official release\n"
                                     "Canary: Last version build, latest development but contains bug")

        self.download_button_widget = QPushButton()
        self.download_button_widget.setFixedSize(40, 40)
        self.download_button_widget.setIcon(QIcon(os.path.join(resource_path, 'download.ico')))
        self.download_button_widget.clicked.connect(self.install_click)
        self.download_button_widget.setToolTip("Download all tools")

        self.canal_layout = QHBoxLayout()
        self.canal_layout.addWidget(self.canal_label)
        self.canal_layout.addWidget(self.canal_widget)
        self.canal_layout.addWidget(self.download_button_widget)

        self.tools_group = QGroupBox("Tools update")
        checkbox_layout = QVBoxLayout()

        # Create checkboxes for each tool
        self.checkboxes = {}

        # Ifrit GUI
        self.checkboxes['ifrit'] = self.__create_checkbox(
            'ifritGui.ico',
            "Ifrit GUI",
            "Launch original ifrit soft"
        )

        # Quezacotl
        self.checkboxes['quezacotl'] = self.__create_checkbox(
            'Quezacotl.ico',
            "Quezacotl",
            "Launch Quezacotl (init.out editor)"
        )

        # Siren
        self.checkboxes['siren'] = self.__create_checkbox(
            'siren.ico',
            "Siren",
            "Launch siren (price.bin editor)"
        )

        # Junkshop
        self.checkboxes['junkshop'] = self.__create_checkbox(
            'junkshop.ico',
            "Junkshop",
            "Launch junkshop (mweapon.bin editor)"
        )

        # Doomtrain
        self.checkboxes['doomtrain'] = self.__create_checkbox(
            'doomtrain.ico',
            "Doomtrain",
            "Launch doomtrain (kernel.bin editor)"
        )

        # Cactilio
        self.checkboxes['cactilio'] = self.__create_checkbox(
            'jumbo_cactuar.ico',
            "Jumbo Cactuar",
            "Launch Jumbo cactuar (Scene.out editor)"
        )

        # Deling
        self.checkboxes['deling'] = self.__create_checkbox(
            'deling.ico',
            "Deling",
            "Launch deling (Archive editor)"
        )

        # Hyne
        self.checkboxes['hyne'] = self.__create_checkbox(
            'hyne.ico',
            "Hyne",
            "Launch hyne (Save editor)"
        )

        # Add all checkboxes to layout
        for checkbox in self.checkboxes.values():
            checkbox_layout.addWidget(checkbox)

        # Add the launch button
        #self.launch_button = QPushButton("Launch Selected Tools")
        #self.launch_button.clicked.connect(self.launch_selected_tools)
        #checkbox_layout.addWidget(self.launch_button)

        self.tools_group.setLayout(checkbox_layout)

        self.main_layout = QVBoxLayout()

        self.main_layout.addLayout(self.canal_layout)
        self.main_layout.addWidget(self.progress)
        self.main_layout.addWidget(self.progress_current_download)
        #self.main_layout.addWidget(self.tools_group)
        self.main_layout.addStretch(1)

        self.setLayout(self.main_layout)


    def install_progress(self, nb_install_done):
        self.progress.setValue(nb_install_done)
        self.progress_current_download.setValue(0)
        self.progress_install_index +=1


    def install_completed(self, nb_install_done):
        self.progress.setValue(nb_install_done)
        #self.install_over.exec()

        self.progress.setValue(0)
        self.progress_current_download.setValue(0)
        self.progress_current_download.setFormat("Current download status")
        self.progress.hide()
        self.progress_install_index = 0
        self.progress_current_download.hide()
        self.download_button_widget.setEnabled(True)
        if self.self_update_request:
            self.start_self_update_process()
        self.self_update_request = False

    def update_download(self, advancement: int, max_size: int):
        tool_list = self._tool_list_callback()
        if "Self" in tool_list:
            self.self_update_request = True
        if advancement >= 0 and max_size >= 0:
            if self.progress_install_index >= len(tool_list):
                progress_name = "FF8UltimateEditor"
            else:
                progress_name = tool_list[self.progress_install_index]
            self.progress_current_download.setFormat(f"Downloading {progress_name}")
            self.progress_current_download.setRange(0, max_size)
            self.progress_current_download.setValue(advancement)
        else:
            self.progress_current_download.setFormat("No download information")


    def install_click(self):
        tool_list = self._tool_list_callback()
        if not tool_list:
            QMessageBox.information(self, "No program selected",
                                 "Please select the program you want to update")
            return
        self.download_button_widget.setEnabled(False)
        self.progress.show()
        self.progress_current_download.show()

        nb_tools = len(tool_list)
        self.progress.setRange(0, nb_tools+1)
        self.progress.setValue(0)
        if self.canal_widget.currentIndex() == 0:
            canary = False
        else:
            canary = True
        self.install_requested.emit(self.tool_updater, canary, tool_list)

    def start_self_update_process(self):
        # Path to the updater executable
        updater_path = Path("Patcher/Patcher.exe")

        # Launch updater and close this app
        if updater_path.exists():
            QMessageBox.information(self, "Update in progress",
                                 "Self updating, the program will restart")
            subprocess.Popen([str(updater_path)])
            QApplication.quit()
        else:
            shutil.rmtree("SelfUpdate", ignore_errors=True)
            QMessageBox.critical(self, "Update Error",
                "Updater tool not found. Please update manually.")


    def __create_checkbox(self, icon_filename, text, tooltip):
        """Helper method to create a checkbox with icon and tooltip"""
        icon_path = os.path.join(self.resource_path, icon_filename)
        checkbox = QCheckBox(text)

        if os.path.exists(icon_path):
            checkbox.setIcon(QIcon(icon_path))

        checkbox.setToolTip(tooltip)
        return checkbox