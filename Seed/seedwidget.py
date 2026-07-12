import os
import pathlib

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
                             QListWidget, QListWidgetItem, QFileDialog, QMessageBox,
                             QSplitter)

from Ifrit.Ifrit3D.ifrit3dwidget import Ifrit3DWidget
from Seed.seedmanager import SeedManager


class SeedWidget(QWidget):
    """Seed: field character model viewer (chara.one / main_chr .mch)."""

    def __init__(self, icon_path='Resources', settings=None):
        super().__init__()
        self.settings = settings
        self.seed_manager = SeedManager()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Toolbar ---
        toolbar = QWidget()
        toolbar.setStyleSheet("background:#2a2a2f; padding:5px;")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(8, 4, 8, 4)

        self.open_one_btn = QPushButton("Open chara.one")
        self.open_one_btn.setStyleSheet("background:#4a6e8a; color:white; padding:4px 12px; border-radius:3px;")
        self.open_one_btn.setToolTip("Open a field chara.one file (field/mapdata/<zone>/<field>/chara.one).\n"
                                     "It contains the NPC models of the field and the animations of the\n"
                                     "main characters appearing in it.")
        self.open_one_btn.clicked.connect(self._open_chara_one)
        toolbar_layout.addWidget(self.open_one_btn)

        self.open_mch_btn = QPushButton("Open .mch")
        self.open_mch_btn.setStyleSheet("background:#4a6e8a; color:white; padding:4px 12px; border-radius:3px;")
        self.open_mch_btn.setToolTip("Open a main character model (field/model/main_chr/d0xx.mch)\n"
                                     "standalone. Only its rest pose is available: field animations\n"
                                     "are stored per field in chara.one.")
        self.open_mch_btn.clicked.connect(self._open_mch)
        toolbar_layout.addWidget(self.open_mch_btn)

        self.save_one_btn = QPushButton("Save chara.one")
        self.save_one_btn.setStyleSheet("background:#6a8a4e; color:white; padding:4px 12px; border-radius:3px;")
        self.save_one_btn.setToolTip("Write the chara.one back with the current model's animations\n"
                                     "(bone edits, 60 FPS conversions...). Other models in the file\n"
                                     "are copied unchanged from the original.")
        self.save_one_btn.clicked.connect(self._save_chara_one)
        toolbar_layout.addWidget(self.save_one_btn)

        self.main_chr_btn = QPushButton("Set main_chr folder")
        self.main_chr_btn.setStyleSheet("background:#4a6e8a; color:white; padding:4px 12px; border-radius:3px;")
        self.main_chr_btn.setToolTip("Folder containing the d0xx.mch main character models\n"
                                     "(field/model/main_chr). Auto-detected when possible.")
        self.main_chr_btn.clicked.connect(self._choose_main_chr_folder)
        toolbar_layout.addWidget(self.main_chr_btn)

        self.file_label = QLabel("No file loaded")
        self.file_label.setStyleSheet("color:#aaa; padding:4px 8px;")
        toolbar_layout.addWidget(self.file_label)
        toolbar_layout.addStretch()

        main_layout.addWidget(toolbar)

        # --- Model list + 3D viewer ---
        splitter = QSplitter(Qt.Orientation.Horizontal)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        list_title = QLabel("Models")
        list_title.setStyleSheet("background:#2a2a2f; color:white; font-weight:bold; padding:4px 8px;")
        left_layout.addWidget(list_title)
        self.model_list = QListWidget()
        self.model_list.setStyleSheet("background:#1a1a1f; color:white; border:none;")
        self.model_list.currentRowChanged.connect(self._on_model_selected)
        left_layout.addWidget(self.model_list)

        self.viewer_3d = Ifrit3DWidget(self.seed_manager, show_controls=True)

        splitter.addWidget(left_panel)
        splitter.addWidget(self.viewer_3d)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 800])
        main_layout.addWidget(splitter, 1)

        if self.settings:
            saved_folder = self.settings.value("seed/main_chr_folder", defaultValue="", type=str)
            if saved_folder and pathlib.Path(saved_folder).is_dir():
                self.seed_manager.main_chr_folder = pathlib.Path(saved_folder)

    def _last_dir(self) -> str:
        if self.settings:
            return self.settings.value("seed/last_dir", defaultValue="", type=str)
        return ""

    def _save_last_dir(self, file_path: str):
        if self.settings:
            self.settings.setValue("seed/last_dir", os.path.dirname(file_path))

    def _open_chara_one(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open chara.one", self._last_dir(),
                                                   "Field model container (*.one);;All files (*)")
        if not file_path:
            return
        self._save_last_dir(file_path)
        try:
            entries = self.seed_manager.load_chara_one(file_path)
        except Exception as e:
            QMessageBox.critical(self, "Seed", f"Could not read {file_path}:\n{e}")
            return
        self.file_label.setText(f"{pathlib.Path(file_path).parent.name}/chara.one "
                                f"({len(entries)} models)")
        if self.settings and self.seed_manager.main_chr_folder:
            self.settings.setValue("seed/main_chr_folder", str(self.seed_manager.main_chr_folder))
        self.model_list.blockSignals(True)
        self.model_list.clear()
        for entry in entries:
            label = f"{entry.index}: {entry.name}"
            if entry.is_main:
                label += "  (main character)"
            item = QListWidgetItem(label)
            self.model_list.addItem(item)
        self.model_list.blockSignals(False)
        if entries:
            self.model_list.setCurrentRow(0)

    def _open_mch(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open field character model", self._last_dir(),
                                                   "Field character model (*.mch);;All files (*)")
        if not file_path:
            return
        self._save_last_dir(file_path)
        try:
            self.seed_manager.load_mch(file_path)
        except Exception as e:
            QMessageBox.critical(self, "Seed", f"Could not read {file_path}:\n{e}")
            return
        self.file_label.setText(pathlib.Path(file_path).name)
        self.model_list.blockSignals(True)
        self.model_list.clear()
        self.model_list.blockSignals(False)
        self.viewer_3d.load_file()

    def _save_chara_one(self):
        if not self.seed_manager.chara_one:
            QMessageBox.warning(self, "Seed", "Open a chara.one and select a model first.")
            return
        if self.seed_manager.current_entry_index is None:
            QMessageBox.warning(self, "Seed", "The current model was opened as a standalone .mch:\n"
                                              "only chara.one files can be saved.")
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "Save chara.one",
                                                   str(self.seed_manager.chara_one_path or self._last_dir()),
                                                   "Field model container (*.one);;All files (*)")
        if not file_path:
            return
        try:
            self.seed_manager.save_chara_one(file_path)
        except Exception as e:
            QMessageBox.critical(self, "Seed", f"Could not save {file_path}:\n{e}")
            return
        entry = self.seed_manager.chara_one.entries[self.seed_manager.current_entry_index]
        QMessageBox.information(self, "Seed",
                                f"Saved.\nThe animations of {entry.name} were written; the other "
                                f"models were copied unchanged from the original file.")

    def _choose_main_chr_folder(self):
        start = str(self.seed_manager.main_chr_folder or self._last_dir())
        folder = QFileDialog.getExistingDirectory(self, "Select main_chr folder", start)
        if not folder:
            return
        self.seed_manager.main_chr_folder = pathlib.Path(folder)
        if self.settings:
            self.settings.setValue("seed/main_chr_folder", folder)

    def _on_model_selected(self, row: int):
        if row < 0 or not self.seed_manager.chara_one:
            return
        try:
            self.seed_manager.load_entry(row)
        except FileNotFoundError as e:
            QMessageBox.warning(self, "Seed", str(e))
            return
        except Exception as e:
            QMessageBox.warning(self, "Seed", f"Could not load this model:\n{e}")
            return
        self.viewer_3d.load_file()
