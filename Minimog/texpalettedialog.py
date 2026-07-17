"""Modal picker: choose which of icon.TEX's palettes to export with, seeing the
whole atlas rendered through it before committing. icon.TEX only stores palette
indices per pixel, so the same bytes render as completely different colors
depending which palette is applied - this dialog exists so that choice isn't
a blind guess."""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox,
                             QDialogButtonBox, QSizePolicy)
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtCore import Qt

PREVIEW_SCALE = 2


class TexPalettePickerDialog(QDialog):
    """Pick a palette index (0..num_palettes-1), previewing the full atlas live."""

    def __init__(self, parent, tex_file, default_palette=0):
        super().__init__(parent)
        self.tex_file = tex_file
        self.setWindowTitle("Choose a palette")

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.palette_spinbox = QSpinBox()
        self.palette_spinbox.setRange(0, tex_file.num_palettes - 1)
        self.palette_spinbox.setValue(min(default_palette, tex_file.num_palettes - 1))
        self.palette_spinbox.setToolTip(
            "Same pixel data, different palette: icon.TEX stores only an index per\n"
            "pixel, the color comes entirely from whichever of these you pick.")
        self.palette_spinbox.valueChanged.connect(self._update_preview)

        palette_row = QHBoxLayout()
        palette_row.addWidget(QLabel("Palette:"))
        palette_row.addWidget(self.palette_spinbox)
        palette_row.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(self.preview_label)
        layout.addLayout(palette_row)
        layout.addWidget(buttons)
        self.setLayout(layout)

        self._update_preview()

    @property
    def palette_index(self):
        return self.palette_spinbox.value()

    def _update_preview(self):
        image = self.tex_file.to_image(self.palette_index)
        if PREVIEW_SCALE > 1:
            from PIL import Image
            image = image.resize((image.width * PREVIEW_SCALE, image.height * PREVIEW_SCALE),
                                 Image.NEAREST)
        qimage = QImage(image.tobytes(), image.width, image.height,
                        image.width * 4, QImage.Format.Format_RGBA8888)
        self.preview_label.setPixmap(QPixmap.fromImage(qimage))

    @staticmethod
    def get_palette(parent, tex_file, default_palette=0):
        """QInputDialog.getInt()-style convenience: returns (palette_index, accepted)."""
        dialog = TexPalettePickerDialog(parent, tex_file, default_palette)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        return dialog.palette_index, accepted
