import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QLabel, QPushButton,
                             QFileDialog, QMessageBox)

from FF8GameData.menu.magpagemanager import TEXTURE_CATEGORIES
from FF8GameData.menu.magpicture import (PC_PICTURE_FILES, encode_picture_tex, encode_picture_tim,
                                         pc_picture_file_name, quantize_picture, tex_to_image)
from FF8GameData.tex.texfile import TexFile
from FF8GameData.tim.timfile import decode_tim

PREVIEW_SCALE = 2


def slot_label(raw_file):
    """"28: mag00 - Weapons Monthly": the slot, its PC texture and the page family using it."""
    family = ""
    bases = [(base, name) for name, base in TEXTURE_CATEGORIES.values() if base <= raw_file]
    if bases:
        family = f" - {max(bases)[1]}"
    return f"{raw_file}: {PC_PICTURE_FILES[raw_file]}{family}"


class ShivaMagazinePictureWidget(QWidget):
    """The magazine and tutorial page pictures, replaced from a PNG.

    On PC a page picture is a menu texture (mag00-19.TEX, mc00-09.TEX) picked by its mngrp slot:
    the exe never shows any other slot (FF8GameData/menu/magpicture.py). So a new book's pictures
    replace some of these 30. A replacement writes both copies at Shiva's Save: the .TEX next to
    mngrp.bin, which the game shows, and the TIM in mngrp.bin, which the page editors preview
    (Zone, Moomba) and the PSX path reads.
    """

    def __init__(self):
        QWidget.__init__(self)
        self.manager = None
        self.menu_folder = ""
        self._pending = {}       # slot -> (palette, indices) waiting for the next save
        self._image_cache = {}   # slot -> PIL image shown

        self.slot_list = QListWidget()
        self.slot_list.setFixedWidth(260)
        for raw_file in sorted(PC_PICTURE_FILES):
            self.slot_list.addItem(slot_label(raw_file))
            self.slot_list.item(self.slot_list.count() - 1).setData(Qt.ItemDataRole.UserRole, raw_file)
        self.slot_list.currentRowChanged.connect(self._slot_changed)

        self.picture_label = QLabel("Open mngrp.bin to see the pictures")
        self.picture_label.setFixedSize(256 * PREVIEW_SCALE, 192 * PREVIEW_SCALE)
        self.picture_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label = QLabel()
        self.info_label.setWordWrap(True)

        self.export_button = QPushButton("Export PNG...")
        self.export_button.clicked.connect(self._export)
        self.replace_button = QPushButton("Replace from PNG...")
        self.replace_button.setToolTip("A 256x192 image (a 256x256 one is cropped to its top 192 rows), reduced\n"
                                       "to 255 colours. Pixels with alpha under 128 are transparent. The page\n"
                                       "sprites (Sprites tab) crop fixed rectangles out of it.")
        self.replace_button.clicked.connect(self._replace)
        self.revert_button = QPushButton("Undo the replacement")
        self.revert_button.clicked.connect(self._revert)

        buttons = QHBoxLayout()
        buttons.addWidget(self.export_button)
        buttons.addWidget(self.replace_button)
        buttons.addWidget(self.revert_button)
        buttons.addStretch(1)

        help_label = QLabel(
            "On PC, a magazine or tutorial page can only show one of these 30 pictures: the game reads "
            "them from menu/*.TEX, chosen by the page's mngrp slot (Zone, \"Page texture\"). A new book's "
            "pictures replace some of them - and the pages using them in the game's own books too. "
            "Saving writes the .TEX next to mngrp.bin and the copy inside mngrp.bin.")
        help_label.setWordWrap(True)

        right = QVBoxLayout()
        right.addWidget(help_label)
        right.addWidget(self.picture_label)
        right.addWidget(self.info_label)
        right.addLayout(buttons)
        right.addStretch(1)

        layout = QHBoxLayout(self)
        layout.addWidget(self.slot_list)
        layout.addLayout(right, 1)
        self._update_buttons()

    # --- shared mngrp ------------------------------------------------------------------------

    def load_from_mngrp(self, manager):
        self.manager = manager
        self.menu_folder = os.path.dirname(manager.mngrp_path) if manager.mngrp_path else ""
        self._pending = {}
        self._image_cache = {}
        if self.slot_list.currentRow() < 0:
            self.slot_list.setCurrentRow(0)
        else:
            self._slot_changed(self.slot_list.currentRow())

    def save_to_mngrp(self, manager):
        """Write each replaced picture: its TIM into the shared mngrp, its .TEX into the menu folder."""
        problems = []
        for raw_file, (palette, indices) in sorted(self._pending.items()):
            section = manager.mngrp.get_section_list()[raw_file]
            manager.mngrp.set_section_by_id_and_bytearray(
                section.id, bytearray(encode_picture_tim(palette, indices, bytes(section.get_data_hex()))))
            template = self._tex_template(raw_file)
            if template is None:
                problems.append(f"{pc_picture_file_name(raw_file)}: no .TEX next to mngrp.bin to take "
                                f"the header from, only the mngrp copy was written")
                continue
            encode_picture_tex(palette, indices, template).write(self._tex_path(raw_file))
        self._pending = {}
        self._image_cache = {}
        self._slot_changed(self.slot_list.currentRow())
        if problems:
            QMessageBox.warning(self, "Shiva - Magazine pictures", "\n".join(problems))

    # --- files -------------------------------------------------------------------------------

    def _tex_path(self, raw_file):
        return os.path.join(self.menu_folder, pc_picture_file_name(raw_file))

    def _tex_template(self, raw_file):
        """The .TEX the replacement takes its header from: the slot's own one, else any other
        page picture of the folder (they all share the same header)."""
        candidates = [self._tex_path(raw_file)] + [os.path.join(self.menu_folder, f"{name}.TEX")
                                                   for name in PC_PICTURE_FILES.values()]
        for path in candidates:
            if self.menu_folder and os.path.exists(path):
                try:
                    return TexFile.read(path)
                except (OSError, ValueError):
                    continue
        return None

    def _picture(self, raw_file):
        """(image, where it comes from) of a slot: the pending replacement, else the .TEX the game
        shows, else the mngrp copy."""
        if raw_file in self._pending:
            from PIL import Image
            palette, indices = self._pending[raw_file]
            lut = [(0, 0, 0, 0)] + [(r, g, b, 255) for r, g, b in palette[1:]]
            image = Image.new("RGBA", (256, 192))
            image.putdata([lut[index] for index in indices])
            return image, "replacement, written at the next Save"
        if raw_file not in self._image_cache:
            image, origin = None, ""
            tex_path = self._tex_path(raw_file)
            if self.menu_folder and os.path.exists(tex_path):
                try:
                    image, origin = tex_to_image(TexFile.read(tex_path)), f"menu/{os.path.basename(tex_path)}"
                except (OSError, ValueError):
                    image = None
            if image is None and self.manager is not None:
                data = bytes(self.manager.mngrp.get_section_list()[raw_file].get_data_hex())
                tim = decode_tim(data) if data else None
                if tim is not None:
                    image, origin = tim.image, (f"mngrp copy ({os.path.basename(tex_path)} not found "
                                                f"next to mngrp.bin)")
            self._image_cache[raw_file] = (image, origin)
        return self._image_cache[raw_file]

    # --- UI ----------------------------------------------------------------------------------

    def _current_slot(self):
        item = self.slot_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _slot_changed(self, _row):
        raw_file = self._current_slot()
        if raw_file is None or self.manager is None:
            self._update_buttons()
            return
        image, origin = self._picture(raw_file)
        if image is None:
            self.picture_label.setPixmap(QPixmap())
            self.picture_label.setText("No picture in this slot")
        else:
            rgba = image.convert("RGBA")
            qt_image = QImage(rgba.tobytes("raw", "RGBA"), rgba.width, rgba.height, QImage.Format.Format_RGBA8888)
            self.picture_label.setPixmap(QPixmap.fromImage(qt_image).scaled(
                rgba.width * PREVIEW_SCALE, rgba.height * PREVIEW_SCALE,
                Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation))
        self.info_label.setText(f"Slot {raw_file}, menu/{pc_picture_file_name(raw_file)} - shown: {origin}")
        self._update_buttons()

    def _update_buttons(self):
        ready = self.manager is not None and self._current_slot() is not None
        self.export_button.setEnabled(ready)
        self.replace_button.setEnabled(ready)
        self.revert_button.setEnabled(ready and self._current_slot() in self._pending)

    def _export(self):
        raw_file = self._current_slot()
        image, _origin = self._picture(raw_file)
        if image is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export the picture",
                                              f"{PC_PICTURE_FILES[raw_file]}.png", "PNG (*.png)")
        if path:
            image.save(path)

    def _replace(self):
        raw_file = self._current_slot()
        path, _ = QFileDialog.getOpenFileName(self, "Picture to put in this slot", "", "Images (*.png *.bmp)")
        if path:
            self.replace_from_file(raw_file, path)

    def replace_from_file(self, raw_file, path):
        """Queue a replacement of slot `raw_file` from an image file. False (with a message) when the
        image cannot be a page picture."""
        from PIL import Image
        try:
            with Image.open(path) as image:
                self._pending[raw_file] = quantize_picture(image)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Shiva - Magazine pictures", f"Cannot use {os.path.basename(path)}:\n{error}")
            return False
        if raw_file == self._current_slot():
            self._slot_changed(self.slot_list.currentRow())
        return True

    def _revert(self):
        self._pending.pop(self._current_slot(), None)
        self._slot_changed(self.slot_list.currentRow())
