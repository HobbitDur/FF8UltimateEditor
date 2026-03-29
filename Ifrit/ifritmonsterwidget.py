import os
import pathlib
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QTabWidget, QSpinBox, QSlider, QFrame, QMessageBox
)
from IfritAI.ifritaiwidget import IfritAIWidget
from IfritSeq.ifritseqwidget import IfritSeqWidget
from Ifrit3D.ifrit3dwidget import Ifrit3DWidget


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

        self._open_btn   = self._icon_btn('folder.png', "Open .dat file", self._open_file)
        self._save_btn   = self._icon_btn('save.svg',   "Save",           self._save_file)
        self._reload_btn = self._icon_btn('reset.png',  "Reload file",    self._reload_file)
        self._save_btn.setEnabled(False)
        self._reload_btn.setEnabled(False)

        self._monster_label = QLabel("No file loaded")

        for w in [self._open_btn, self._save_btn, self._reload_btn, self._monster_label]:
            tl.addWidget(w)
        tl.addStretch()

        # ── Sub-widgets ──────────────────────────────────────────────
        # AI: keeps its own sub-toolbar (expert, section, color…) minus file buttons
        self._ai_widget = IfritAIWidget(icon_path=icon_path, game_data_folder=game_data_folder)
        self._ai_widget.hide_file_controls()

        # Seq: keeps xml import/export sub-toolbar minus file buttons
        self._seq_widget = IfritSeqWidget(icon_path=icon_path, game_data_folder=game_data_folder)
        self._seq_widget.hide_file_controls()

        # 3D: keeps its own sub-toolbar (mesh/wire/play/frame…)
        self._d3_widget = Ifrit3DWidget(show_controls=True)

        # ── Tabs ─────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.addTab(self._ai_widget,  "AI Editor")
        self._tabs.addTab(self._seq_widget, "Seq Editor")
        self._tabs.addTab(self._d3_widget,  "3D Viewer")
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
        self._save_btn.setEnabled(bool(self.file_loaded) and index != 2)

    # ── File operations ───────────────────────────────────────────────

    def _open_file(self):
        path = self._file_dialog.getOpenFileName(
            parent=self, caption="Open .dat file",
            filter="*.dat", directory=self._file_dialog_folder)[0]
        if path:
            self._file_dialog_folder = os.path.dirname(path)
            self._load_all(path)

    def _load_all(self, path: str):
        self.file_loaded = path
        self._ai_widget.load_file(path)
        self._seq_widget.load_file(path)
        self._d3_widget.load_file(path)

        try:
            name = self._ai_widget.ifrit_manager.enemy.info_stat_data['monster_name'].get_str().strip('\x00')
            self._monster_label.setText(f"{name}  [{pathlib.Path(path).name}]")
        except Exception:
            self._monster_label.setText(pathlib.Path(path).name)

        self._save_btn.setEnabled(self._tabs.currentIndex() != 2)
        self._reload_btn.setEnabled(True)

    def _save_file(self):
        idx = self._tabs.currentIndex()
        if idx == 0:
            self._ai_widget.save_file()
        elif idx == 1:
            self._seq_widget.save_file()

    def _reload_file(self):
        if self.file_loaded:
            self._load_all(self.file_loaded)

    def _show_info(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("Ifrit Monster Tools")
        msg.setText("Combined AI / Seq / 3D monster editor.\nDone by Hobbitdur.")
        msg.exec()