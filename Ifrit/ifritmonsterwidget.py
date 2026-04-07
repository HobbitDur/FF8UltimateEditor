import os
import pathlib
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QTabWidget, QMessageBox, QCheckBox
)
from IfritAI.ifritaiwidget import IfritAIWidget
from Ifrit.ifritmanager import IfritManager
from IfritSeq.ifritseqwidget import IfritSeqWidget
from Ifrit3D.ifrit3dwidget import Ifrit3DWidget
from IfritTexture.ifrittexturewidget import IfritTextureWidget
from IfritXlsx.ifritxlsxwidget import IfritXlsxWidget


class IfritMonsterWidget(QWidget):
    """IfritAI + IfritSeq + Ifrit3D with a single shared file toolbar."""

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData"):
        super().__init__()
        self.icon_path = icon_path
        self.file_loaded = ""
        self._file_dialog_folder = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Shared toolbar ───────────────────────────────────────────
        toolbar = QWidget()
        tl = QHBoxLayout(toolbar)
        tl.setContentsMargins(6, 4, 6, 4)
        tl.setSpacing(4)

        self._file_dialog = QFileDialog()

        self._open_btn = self._icon_btn('folder.png', "Open .dat file", self._open_file)
        self._save_btn = self._icon_btn('save.svg', "Save", self._save_file)
        self._reload_btn = self._icon_btn('reset.png', "Reload file", self._reload_file)
        self._save_btn.setEnabled(False)
        self._reload_btn.setEnabled(False)

        # Add Cronos checkbox
        self._cronos_checkbox = QCheckBox("Cronos")
        self._cronos_checkbox.setToolTip("Load AI data with cronos configuration")
        self._cronos_checkbox.stateChanged.connect(self._on_cronos_toggled)

        self._monster_label = QLabel("No file loaded")

        for w in [self._open_btn, self._save_btn, self._reload_btn, self._cronos_checkbox, self._monster_label]:
            tl.addWidget(w)
        tl.addStretch()

        self.ifrit_manager = IfritManager(game_data_folder)
        # ── Sub-widgets ──────────────────────────────────────────────
        # AI: keeps its own sub-toolbar (expert, section, color…) minus file buttons
        self._ai_widget = IfritAIWidget(self.ifrit_manager, icon_path=icon_path)
        self._ai_widget.hide_file_controls()

        # Seq: keeps xml import/export sub-toolbar minus file buttons
        self._seq_widget = IfritSeqWidget(self.ifrit_manager, icon_path=icon_path)
        self._seq_widget.hide_file_controls()

        # 3D: keeps its own sub-toolbar (mesh/wire/play/frame…)
        self._3d_widget = Ifrit3DWidget(self.ifrit_manager, show_controls=True)

        self._texture_widget = IfritTextureWidget(self.ifrit_manager)
        self._xlsx_widget = IfritXlsxWidget(self.ifrit_manager)

        # ── Tabs ─────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.addTab(self._3d_widget, "3D")
        self._tabs.addTab(self._xlsx_widget, "Stat")
        self._tabs.addTab(self._ai_widget, "AI")
        self._tabs.addTab(self._texture_widget, "Texture")
        self._tabs.addTab(self._seq_widget, "Sequence")
        self._tabs.currentChanged.connect(self._on_tab_changed)

        root.addWidget(toolbar)
        root.addWidget(self._tabs, 1)

        self._on_tab_changed(0)

    # ── Utilities ─────────────────────────────────────────────────────

    def _icon_btn(self, name: str, tip: str, slot) -> QPushButton:
        btn = QPushButton()
        btn.setIcon(QIcon(os.path.join(self.icon_path, name)))
        btn.setIconSize(QSize(22, 22))
        btn.setFixedSize(32, 32)
        btn.setToolTip(tip)
        if slot:
            btn.clicked.connect(slot)
        return btn

    # ── Tab switching ─────────────────────────────────────────────────

    def _on_tab_changed(self, index: int):
        # Save not applicable for the 3D viewer
        self._save_btn.setEnabled(bool(self.file_loaded) and index not in (0,))

    # ── Cronos checkbox handler ───────────────────────────────────────

    def _on_cronos_toggled(self, state):
        """Handle Cronos checkbox state changes"""
        if state:  # Checked
            self.ifrit_manager.game_data.load_ai_data("ai_cronos.json")
        else:  # Unchecked
            self.ifrit_manager.game_data.load_ai_data("ai_vanilla.json")

        # Call reload function to refresh the display
        self._reload_file()


    # ── File operations ───────────────────────────────────────────────

    def _open_file(self):
        path = ""
        path = "c0m001.dat" # For developing faster
        if not path:
            path = self._file_dialog.getOpenFileName(
                parent=self, caption="Open .dat file",
                filter="*.dat", directory=self._file_dialog_folder)[0]
        if path:
            self._file_dialog_folder = os.path.dirname(path)
            self._load_all(path)

    def _load_all(self, path: str):
        self.file_loaded = path
        self.ifrit_manager.init_from_file(path)
        self._ai_widget.load_file(path)
        self._seq_widget.load_file(path)
        self._3d_widget.load_file(path)
        self._texture_widget.load_file(path)
        try:
            name = self._ai_widget.ifrit_manager.enemy.info_stat_data['monster_name'].get_str().strip('\x00')
            self._monster_label.setText(f"{name}  [{pathlib.Path(path).name}]")
        except Exception:
            self._monster_label.setText(pathlib.Path(path).name)

        self._save_btn.setEnabled(self._tabs.currentIndex() != 0)
        self._reload_btn.setEnabled(True)

    def _save_file(self):
        self._ai_widget.save_file()
        self._seq_widget.save_file()
        self._texture_widget.save_file()
        self.ifrit_manager.save_file(self.file_loaded)

    def _reload_file(self):
        if self.file_loaded:
            self._load_all(self.file_loaded)

    def _show_info(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("Ifrit Monster Tools")
        msg.setText("Combined 3D / Stat / AI / Seq / Texture monster editor.\nDone by Hobbitdur.")
        msg.exec()