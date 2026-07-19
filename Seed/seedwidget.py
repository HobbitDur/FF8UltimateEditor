import pathlib

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel,
                             QListWidget, QListWidgetItem, QMessageBox,
                             QSplitter)

from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from Ifrit.Ifrit3D.ifrit3dwidget import Ifrit3DWidget
from Seed.seedmanager import SeedManager


class SeedWidget(QWidget):
    """Seed: field character model viewer (chara.one / main_chr .mch)."""

    def __init__(self, icon_path='Resources', settings=None, file_registry=None):
        super().__init__()
        if file_registry is None:  # Used alone, it shares its files with nobody
            file_registry = FileRegistry()
        self.file_registry = file_registry
        self.settings = settings
        self.seed_manager = SeedManager()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Files, driven by the shared header toolbar. chara.one is the edited/saved file; the
        # standalone field character model is a second, view-only main file (no save - only
        # chara.one is ever written back). The main_chr folder (the main characters' models,
        # auto-detected from chara.one's path when possible) is set from the header's Open-folder
        # button, the same load_folder() hook CCGroup's NPC tab uses.
        self.chara_one_binding = FileBinding(
            "chara.one", file_registry, load_callback=self.load_chara_one,
            save_callback=self._save_chara_one, file_filter="chara.one;;*.one")
        self.mch_binding = FileBinding(
            "field character model (.mch)", file_registry, load_callback=self.load_mch,
            file_filter="*.mch")

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
        self.viewer_3d.set_fps(self.seed_manager.anim_native_fps)  # field animations run at 30 fps

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

        self.chara_one_binding.load_opened_file()  # Another tool instance may have opened one
        self.mch_binding.load_opened_file()

    def file_bindings(self):
        """The files the shared header toolbar drives: chara.one (edited/saved) and a standalone
        field character model (view-only - only chara.one is ever written back)."""
        return [self.chara_one_binding, self.mch_binding]

    def load_folder(self, folder_path):
        """The header's Open-folder button: set the main_chr folder (the d0xx.mch main character
        models chara.one's "main" entries load from). load_chara_one already auto-detects it from
        the chara.one path when possible - this is for overriding or supplying it by hand."""
        self.seed_manager.main_chr_folder = pathlib.Path(folder_path)
        if self.settings:
            self.settings.setValue("seed/main_chr_folder", folder_path)
        # It's a folder setting, not a single FF8 file, but still worth a line in Opened files.
        self.file_registry.open_file("Seed main_chr folder", folder_path)

    def load_chara_one(self, file_path):
        """Load a field chara.one (path from the shared header toolbar)."""
        modified = self.seed_manager.modified_entry_names()
        if modified:
            answer = QMessageBox.question(
                self, "Seed",
                f"Unsaved animation changes on: {', '.join(modified)}.\n"
                "Opening another file will discard them. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            entries = self.seed_manager.load_chara_one(file_path)
        except Exception as e:
            QMessageBox.critical(self, "Seed", f"Could not read {file_path}:\n{e}")
            return
        if self.seed_manager.main_chr_folder:
            # Usually auto-detected here (not through the explicit Open-folder override below),
            # so this is where it needs to be reflected in Opened files for the common case too.
            folder = str(self.seed_manager.main_chr_folder)
            if self.settings:
                self.settings.setValue("seed/main_chr_folder", folder)
            self.file_registry.open_file("Seed main_chr folder", folder)
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

    def load_mch(self, file_path):
        """Load a standalone field character model (path from the shared header toolbar)."""
        try:
            self.seed_manager.load_mch(file_path)
        except Exception as e:
            QMessageBox.critical(self, "Seed", f"Could not read {file_path}:\n{e}")
            return
        self.model_list.blockSignals(True)
        self.model_list.clear()
        self.model_list.blockSignals(False)
        self.viewer_3d.load_file()

    def _save_chara_one(self):
        """Write the chara.one back with every model's animations modified this session (the
        shared header Save button calls this). Other entries are copied unchanged."""
        if not self.seed_manager.chara_one:
            QMessageBox.warning(self, "Seed", "Open a chara.one and select a model first.")
            return
        modified = self.seed_manager.modified_entry_names()
        if not modified:
            QMessageBox.information(self, "Seed", "No animation changes to save: the file "
                                                  "would be identical to the original.")
            return
        try:
            saved = self.seed_manager.save_chara_one(self.seed_manager.chara_one_path)
        except Exception as e:
            QMessageBox.critical(self, "Seed", f"Could not save {self.seed_manager.chara_one_path}:\n{e}")
            return
        QMessageBox.information(self, "Seed",
                                f"Saved.\nAnimations written for: {', '.join(saved)}.\n"
                                f"All other models were copied unchanged from the original file.")

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
