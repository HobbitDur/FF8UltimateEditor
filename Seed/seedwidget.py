import pathlib

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel,
                             QListWidget, QListWidgetItem, QMessageBox,
                             QSplitter)

from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from Ifrit.Ifrit3D.ifrit3dwidget import Ifrit3DWidget
from Seed.seedmanager import SeedManager
from SmallWidget.listsearchbar import ListSearchBar


class SeedWidget(QWidget):
    """Seed: field character model viewer (chara.one / main_chr .mch)."""

    # The main_chr folder's entry in the Opened files panel.
    MAIN_CHR_REGISTRY_NAME = "Seed main_chr folder"

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
        self.chara_one_binding.file_closed.connect(self._close_chara_one)
        self.mch_binding.file_closed.connect(self._close_mch)
        file_registry.file_closed.connect(self._on_registry_file_closed)

        # --- Model list + 3D viewer ---
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: the fields of an opened folder (every chara.one in it, from the header's Open-folder
        # button; hidden until one is opened) above the models of the selected chara.one.
        left_panel = QSplitter(Qt.Orientation.Vertical)
        self.field_panel, self.field_list, self.field_search = self._make_list_panel("Fields")
        self.field_list.currentRowChanged.connect(self._on_field_selected)
        self.field_panel.hide()
        model_panel, self.model_list, self.model_search = self._make_list_panel("Models")
        self.model_list.currentRowChanged.connect(self._on_model_selected)
        left_panel.addWidget(self.field_panel)
        left_panel.addWidget(model_panel)
        self._field_paths = []      # chara.one path per field_list row
        self._field_row = -1        # row whose chara.one is loaded (restored when a switch is cancelled)
        self._discard_confirmed = False

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
            if SeedManager.is_main_chr_folder(saved_folder or None):  # ignore a stale/wrong pick
                self.seed_manager.main_chr_folder = pathlib.Path(saved_folder)

        self.chara_one_binding.load_opened_file()  # Another tool instance may have opened one
        self.mch_binding.load_opened_file()

    @staticmethod
    def _make_list_panel(title):
        """A titled, searchable list (the Fields and Models panels)."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        title_label = QLabel(title)
        title_label.setStyleSheet("background:#2a2a2f; color:white; font-weight:bold; padding:4px 8px;")
        layout.addWidget(title_label)
        list_widget = QListWidget()
        list_widget.setStyleSheet("background:#1a1a1f; color:white; border:none;")
        search = ListSearchBar(list_widget)
        search.setStyleSheet("QLineEdit {background:#1a1a1f; color:white; border:1px solid #3a3a3f;}")
        layout.addWidget(search)
        layout.addWidget(list_widget)
        return panel, list_widget, search

    def _on_registry_file_closed(self, file_name, _path):
        """The main_chr folder was removed from the Opened files panel: stop using it (it is
        auto-detected again from the next chara.one opened)."""
        if file_name != self.MAIN_CHR_REGISTRY_NAME:
            return
        self.seed_manager.main_chr_folder = None
        if self.settings:
            self.settings.remove("seed/main_chr_folder")

    def _close_chara_one(self, _path):
        """chara.one was removed from the Opened files panel: empty the model list and viewer."""
        self.seed_manager.close_chara_one()
        self.model_list.blockSignals(True)
        self.model_list.clear()
        self.model_list.blockSignals(False)
        self._field_row = -1
        self.field_list.blockSignals(True)
        self.field_list.setCurrentRow(-1)
        self.field_list.blockSignals(False)
        self.viewer_3d.hide()  # it would keep drawing the last model; shown again on the next load

    def _close_mch(self, _path):
        """The standalone .mch was removed: hide it, unless a chara.one model replaced it since."""
        if self.seed_manager.current_entry_index is None:
            self.viewer_3d.hide()

    def file_bindings(self):
        """The files the shared header toolbar drives: chara.one (edited/saved) and a standalone
        field character model (view-only - only chara.one is ever written back)."""
        return [self.chara_one_binding, self.mch_binding]

    def load_folder(self, folder_path):
        """The header's Open-folder button. Every chara.one inside the folder (e.g. the 'field'
        folder: one per field room) is listed under Fields; selecting one opens it. The main_chr
        folder (the d0xx.mch main character models) is found inside it too - or is the picked
        folder itself when it holds .mch files, which still sets it by hand."""
        main_chr = SeedManager.find_main_chr_folder_in(folder_path)
        if main_chr is not None:
            self._set_main_chr_folder(main_chr)
        self._field_paths = SeedManager.find_chara_ones(folder_path)
        self.field_list.blockSignals(True)
        self.field_list.clear()
        for path in self._field_paths:
            item = QListWidgetItem(path.parent.name)
            item.setToolTip(str(path))
            self.field_list.addItem(item)
        self._field_row = -1
        self.field_list.blockSignals(False)
        self.field_panel.setVisible(bool(self._field_paths))
        if not self._field_paths:
            if main_chr is None:
                QMessageBox.information(self, "Seed", f"No chara.one or main_chr .mch model found in:\n"
                                                      f"{folder_path}")
            return
        # Keep the chara.one already open (e.g. the one the folder scan just opened) if it's listed.
        if self.seed_manager.chara_one_path is not None:
            self._sync_field_row()
        if self._field_row < 0:
            self.field_search.select_first_match()

    def _set_main_chr_folder(self, folder):
        folder = str(folder)
        self.seed_manager.main_chr_folder = pathlib.Path(folder)
        if self.settings:
            self.settings.setValue("seed/main_chr_folder", folder)
        # It's a folder setting, not a single FF8 file, but still worth a line in Opened files.
        self.file_registry.open_file(self.MAIN_CHR_REGISTRY_NAME, folder)

    def _confirm_discard(self):
        """Ask before unsaved animation edits are thrown away by opening another chara.one."""
        modified = self.seed_manager.modified_entry_names()
        if not modified:
            return True
        answer = QMessageBox.question(
            self, "Seed",
            f"Unsaved animation changes on: {', '.join(modified)}.\n"
            "Opening another file will discard them. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes

    def _on_field_selected(self, row: int):
        """A field picked in the Fields list: open its chara.one (shared like an Import)."""
        if row < 0 or row >= len(self._field_paths) or row == self._field_row:
            return
        if not self._confirm_discard():
            self.field_list.blockSignals(True)
            self.field_list.setCurrentRow(self._field_row)
            self.field_list.blockSignals(False)
            return
        self._field_row = row
        self._discard_confirmed = True
        try:
            self.chara_one_binding.open_path(str(self._field_paths[row]))
        finally:
            self._discard_confirmed = False

    def load_chara_one(self, file_path):
        """Load a field chara.one (path from the shared header toolbar or the Fields list)."""
        if not self._discard_confirmed and not self._confirm_discard():
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
            self.file_registry.open_file(self.MAIN_CHR_REGISTRY_NAME, folder)
        self.model_list.blockSignals(True)
        self.model_list.clear()
        for entry in entries:
            label = f"{entry.index}: {entry.name}"
            if entry.is_main:
                label += "  (main character)"
            item = QListWidgetItem(label)
            self.model_list.addItem(item)
        self.model_list.blockSignals(False)
        self._sync_field_row()
        if entries:
            self.model_search.select_first_match()  # Row 0, or the first match if a search is typed in

    def _sync_field_row(self):
        """Highlight the loaded chara.one in the Fields list (it may come from Import instead)."""
        current = self.seed_manager.chara_one_path.resolve()
        self._field_row = next((row for row, path in enumerate(self._field_paths)
                                if path.resolve() == current), -1)
        self.field_list.blockSignals(True)
        self.field_list.setCurrentRow(self._field_row)
        self.field_list.blockSignals(False)

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
        self.viewer_3d.show()
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
        self.viewer_3d.show()
        self.viewer_3d.load_file()
