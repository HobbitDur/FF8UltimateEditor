"""Moomba — Japanese font atlas builder (GUI).

Combines the Japanese ``sysfnt_even.TEX`` / ``sysfnt_odd.TEX`` pair into a single
linear font atlas the Western FF8 engine can sample, for the ILP-JP mod. Thin GUI
over :mod:`FF8GameData.tex.jpfontatlas`; also previews/decodes any FF8 PC ``.TEX``.
"""
import os

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon, QImage, QPixmap
from PyQt6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel,
                             QFileDialog, QSpinBox, QScrollArea, QMessageBox, QFrame)

from PIL import Image

from FF8GameData.tex.texfile import TexFile
from FF8GameData.tex.jpfontatlas import build_linear_atlas, JP_GLYPH_COUNT


class MoombaWidget(QWidget):
    """Build the Japanese linear font atlas from the even/odd TEX pair."""

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData"):
        QWidget.__init__(self)
        self._icon_path = icon_path

        self.setWindowTitle("Moomba")
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'hobbitdur.ico')))

        self.even_tex = None       # TexFile
        self.odd_tex = None        # TexFile
        self.atlas = None          # TexFile (built)
        self.even_path = ""
        self.odd_path = ""

        self.file_dialog = QFileDialog()

        # --- Input row: load even / odd ------------------------------------
        self.load_even_button = QPushButton("Load sysfnt_even.TEX")
        self.load_even_button.setToolTip("Load the Japanese even-parity font texture (menu/sysfnt_even.TEX)")
        self.load_even_button.clicked.connect(self._load_even)
        self.even_label = QLabel("even: none")

        self.load_odd_button = QPushButton("Load sysfnt_odd.TEX")
        self.load_odd_button.setToolTip("Load the Japanese odd-parity font texture (menu/sysfnt_odd.TEX)")
        self.load_odd_button.clicked.connect(self._load_odd)
        self.odd_label = QLabel("odd: none")

        input_row = QHBoxLayout()
        input_row.addWidget(self.load_even_button)
        input_row.addWidget(self.even_label)
        input_row.addSpacing(20)
        input_row.addWidget(self.load_odd_button)
        input_row.addWidget(self.odd_label)
        input_row.addStretch(1)

        # --- Action row: build / save --------------------------------------
        self.build_button = QPushButton("Build linear atlas")
        self.build_button.setToolTip("De-interleave even/odd into the single linear atlas the Western engine samples")
        self.build_button.setEnabled(False)
        self.build_button.clicked.connect(self._build)

        self.save_tex_button = QPushButton("Save .TEX")
        self.save_tex_button.setToolTip("Write the combined atlas as an FF8 .TEX")
        self.save_tex_button.setEnabled(False)
        self.save_tex_button.clicked.connect(self._save_tex)

        self.save_png_button = QPushButton("Save PNG")
        self.save_png_button.setToolTip("Write the current preview as a PNG")
        self.save_png_button.setEnabled(False)
        self.save_png_button.clicked.connect(self._save_png)

        self.palette_label = QLabel("Preview palette:")
        self.palette_spin = QSpinBox()
        self.palette_spin.setRange(0, 0)
        self.palette_spin.setToolTip("Which colour palette to render in the preview")
        self.palette_spin.valueChanged.connect(self._refresh_preview)

        action_row = QHBoxLayout()
        action_row.addWidget(self.build_button)
        action_row.addWidget(self.save_tex_button)
        action_row.addWidget(self.save_png_button)
        action_row.addSpacing(20)
        action_row.addWidget(self.palette_label)
        action_row.addWidget(self.palette_spin)
        action_row.addStretch(1)

        # --- Preview --------------------------------------------------------
        self.preview_label = QLabel("Load sysfnt_even.TEX and sysfnt_odd.TEX to build the atlas.")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.preview_label.setStyleSheet("background-color: #202020;")
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidget(self.preview_label)
        self.preview_scroll.setWidgetResizable(True)

        self.info_label = QLabel("")
        self.info_label.setStyleSheet("font-style: italic;")

        separator = QFrame()
        separator.setFrameStyle(QFrame.Shape.HLine | QFrame.Shadow.Sunken)

        # --- Assembly -------------------------------------------------------
        layout = QVBoxLayout(self)
        layout.addLayout(input_row)
        layout.addLayout(action_row)
        layout.addWidget(self.info_label)
        layout.addWidget(separator)
        layout.addWidget(self.preview_scroll, 1)
        self.setLayout(layout)

    # ---------------------------------------------------------------- loaders
    def _load_even(self):
        path = self.file_dialog.getOpenFileName(self, "Load sysfnt_even.TEX", "", "TEX files (*.TEX *.tex);;All files (*)")[0]
        if not path:
            return
        try:
            self.even_tex = TexFile.read(path)
        except Exception as e:
            QMessageBox.critical(self, "Load error", f"Could not read TEX:\n{e}")
            return
        self.even_path = path
        self.even_label.setText(f"even: {os.path.basename(path)} ({self.even_tex.width}x{self.even_tex.height})")
        self._update_ready()

    def _load_odd(self):
        path = self.file_dialog.getOpenFileName(self, "Load sysfnt_odd.TEX", "", "TEX files (*.TEX *.tex);;All files (*)")[0]
        if not path:
            return
        try:
            self.odd_tex = TexFile.read(path)
        except Exception as e:
            QMessageBox.critical(self, "Load error", f"Could not read TEX:\n{e}")
            return
        self.odd_path = path
        self.odd_label.setText(f"odd: {os.path.basename(path)} ({self.odd_tex.width}x{self.odd_tex.height})")
        self._update_ready()

    def _update_ready(self):
        self.build_button.setEnabled(self.even_tex is not None and self.odd_tex is not None)

    # ---------------------------------------------------------------- actions
    def _build(self):
        try:
            self.atlas = build_linear_atlas(self.even_tex, self.odd_tex, glyph_count=JP_GLYPH_COUNT)
        except Exception as e:
            QMessageBox.critical(self, "Build error", f"Could not build atlas:\n{e}")
            return
        self.palette_spin.setRange(0, max(0, self.atlas.num_palettes - 1))
        self.save_tex_button.setEnabled(True)
        self.save_png_button.setEnabled(True)
        self.info_label.setText(
            f"Atlas: {self.atlas.width}x{self.atlas.height}  |  {JP_GLYPH_COUNT} glyphs  |  "
            f"{self.atlas.height // 12} rows x 21 cols  |  {self.atlas.num_palettes} palettes")
        self._refresh_preview()

    def _refresh_preview(self):
        if self.atlas is None:
            return
        image = self.atlas.to_image(self.palette_spin.value())
        # Composite onto a dark background so the transparent glyph sheet is visible.
        background = Image.new("RGBA", image.size, (32, 32, 32, 255))
        background.alpha_composite(image)
        rgb = background.convert("RGB")
        data = rgb.tobytes()
        qimage = QImage(data, rgb.width, rgb.height, rgb.width * 3, QImage.Format.Format_RGB888).copy()
        self.preview_label.setText("")
        self.preview_label.setPixmap(QPixmap.fromImage(qimage))
        self.preview_label.resize(rgb.width, rgb.height)

    def _save_tex(self):
        if self.atlas is None:
            return
        path = self.file_dialog.getSaveFileName(self, "Save combined atlas", "sysfnt_jp_linear.TEX",
                                                "TEX files (*.TEX);;All files (*)")[0]
        if not path:
            return
        try:
            self.atlas.write(path)
        except Exception as e:
            QMessageBox.critical(self, "Save error", f"Could not write TEX:\n{e}")
            return
        QMessageBox.information(self, "Saved", f"Wrote linear atlas:\n{path}")

    def _save_png(self):
        if self.atlas is None:
            return
        path = self.file_dialog.getSaveFileName(self, "Save preview PNG", "sysfnt_jp_linear.png",
                                                "PNG files (*.png);;All files (*)")[0]
        if not path:
            return
        try:
            self.atlas.to_image(self.palette_spin.value()).save(path)
        except Exception as e:
            QMessageBox.critical(self, "Save error", f"Could not write PNG:\n{e}")
            return
        QMessageBox.information(self, "Saved", f"Wrote preview PNG:\n{path}")
