import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QLabel, QPushButton,
                             QFileDialog, QMessageBox)

from FF8GameData.menu.magpagemanager import TEXTURE_CATEGORIES
from FF8GameData.menu.magpicture import (ADDED_FIRST_SLOT, ADDED_LAST_SLOT, PC_PICTURE_FILES, TEMPLATE_SLOT,
                                         encode_picture_tim, is_added_slot, is_page_picture_tim, pc_picture_file_name,
                                         pc_picture_name, picture_from_indices, quantize_picture,
                                         replace_picture_tim, slot_picture, write_picture_tex)

PREVIEW_SCALE = 2
NEW_PICTURE_COLOR = (96, 96, 96, 255)  # a new picture's placeholder, until its image is set


def slot_label(raw_file):
    """"28: mag00 - Weapons Monthly": the slot, its PC texture and the page family using it; an
    added picture: "206: mag206 (added, FFNx)"."""
    if is_added_slot(raw_file):
        return f"{raw_file}: {pc_picture_name(raw_file)} (added, FFNx)"
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
        self._fill_slots()
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
        # Under the list, like the Sprites tab's "Add sprite id": a new picture is a new entry
        self.add_button = QPushButton("+ Add new picture")
        self.add_button.setToolTip(
            f"A new picture of its own, in the next free mngrp.bin slot (206 first, up to {ADDED_LAST_SLOT}: after\n"
            "the last slot mngrp.bin uses, so nothing else moves). It starts grey: set its image with\n"
            "\"Replace from PNG...\". Save writes its menu/magNNN.TEX and its copy in mngrp.bin.\n"
            "A page shows it with Zone's \"Page texture\" set to that slot. In game it needs FFNx with\n"
            "AddMorePictures (FFNx PR #1111), which reads it from direct/menu/magNNN.TEX.")
        self.add_button.clicked.connect(self.add_picture)
        self.remove_button = QPushButton("- Remove last added picture")
        self.remove_button.setToolTip("Remove the last picture added (only the last one: removing an earlier one\n"
                                      "would move the slots after it). Its .TEX already saved next to mngrp.bin\n"
                                      "is left on disk.")
        self.remove_button.clicked.connect(self.remove_last_picture)

        buttons = QHBoxLayout()
        buttons.addWidget(self.export_button)
        buttons.addWidget(self.replace_button)
        buttons.addWidget(self.revert_button)
        buttons.addStretch(1)

        help_label = QLabel(
            "On PC, the game shows 30 page pictures: it reads them from menu/*.TEX, chosen by the page's "
            "mngrp slot (Zone, \"Page texture\"). Replacing one changes every page using it, the game's own "
            "books too. \"+ Add new picture\" (under the list) makes one of its own instead, in a free slot "
            "(206 and up); the game shows it only with FFNx's AddMorePictures. Saving writes the .TEX next "
            "to mngrp.bin and the copy inside mngrp.bin.")
        help_label.setWordWrap(True)

        right = QVBoxLayout()
        right.addWidget(help_label)
        right.addLayout(buttons)  # above the 512x384 picture, so a short window cannot hide them
        right.addWidget(self.info_label)
        right.addWidget(self.picture_label)
        right.addStretch(1)

        left = QVBoxLayout()
        left.addWidget(self.slot_list)
        left.addWidget(self.add_button)
        left.addWidget(self.remove_button)
        left_widget = QWidget()
        left.setContentsMargins(0, 0, 0, 0)
        left_widget.setLayout(left)
        left_widget.setFixedWidth(self.slot_list.width())

        layout = QHBoxLayout(self)
        layout.addWidget(left_widget)
        layout.addLayout(right, 1)
        self._update_buttons()

    # --- shared mngrp ------------------------------------------------------------------------

    def load_from_mngrp(self, manager):
        self.manager = manager
        self.menu_folder = os.path.dirname(manager.mngrp_path) if manager.mngrp_path else ""
        self._pending = {}
        self._image_cache = {}
        self._fill_slots()
        if self.slot_list.currentRow() < 0:
            self.slot_list.setCurrentRow(0)
        else:
            self._slot_changed(self.slot_list.currentRow())

    def save_to_mngrp(self, manager):
        """Write each replaced picture: its TIM into the shared mngrp, its .TEX into the menu folder."""
        problems = []
        for raw_file, (palette, indices) in sorted(self._pending.items()):
            replace_picture_tim(manager, raw_file, palette, indices)
            if not write_picture_tex(self.menu_folder, raw_file, palette, indices):
                problems.append(f"{pc_picture_file_name(raw_file)}: no .TEX next to mngrp.bin to take "
                                f"the header from, only the mngrp copy was written")
        self._pending = {}
        self._image_cache = {}
        self._slot_changed(self.slot_list.currentRow())
        if problems:
            QMessageBox.warning(self, "Shiva - Magazine pictures", "\n".join(problems))

    def _picture(self, raw_file):
        """(image, where it comes from) of a slot: the pending replacement, else the .TEX the game
        shows, else the mngrp copy."""
        if raw_file in self._pending:
            if is_added_slot(raw_file):
                return (picture_from_indices(*self._pending[raw_file]),
                        "new picture, written at the next Save (set its image with \"Replace from PNG...\")")
            return picture_from_indices(*self._pending[raw_file]), "replacement, written at the next Save"
        if raw_file not in self._image_cache:
            tim_bytes = b""
            if self.manager is not None:
                tim_bytes = bytes(self.manager.mngrp.get_section_list()[raw_file].get_data_hex())
            self._image_cache[raw_file] = slot_picture(self.menu_folder, raw_file, tim_bytes)
        return self._image_cache[raw_file]

    def _picture_slots(self):
        """The game's 30 picture slots, then the added ones this mngrp.bin holds."""
        slots = sorted(PC_PICTURE_FILES)
        if self.manager is not None and self.manager.mngrphd is not None:
            entries = self.manager.mngrphd.get_entry_list()
            sections = self.manager.mngrp.get_section_list()
            # Past 185 only the slots holding a page picture: the game's 188-205 are other data
            slots += [slot for slot in range(len(entries))
                      if is_added_slot(slot) and not entries[slot].invalid_value
                      and is_page_picture_tim(sections[slot].get_data_hex())]
        return slots

    def _fill_slots(self, select=None):
        current = select if select is not None else self._current_slot()
        self.slot_list.blockSignals(True)
        self.slot_list.clear()
        for raw_file in self._picture_slots():
            self.slot_list.addItem(slot_label(raw_file))
            self.slot_list.item(self.slot_list.count() - 1).setData(Qt.ItemDataRole.UserRole, raw_file)
        self.slot_list.blockSignals(False)
        for row in range(self.slot_list.count()):
            if self.slot_list.item(row).data(Qt.ItemDataRole.UserRole) == current:
                self.slot_list.setCurrentRow(row)
                break

    def free_slots(self):
        """The slots a new picture can take: empty, past the game's pictures and after every slot
        mngrp.bin uses."""
        if self.manager is None or self.manager.mngrphd is None:
            return []
        return [slot for slot in self.manager.free_slots_after(ADDED_FIRST_SLOT) if slot <= ADDED_LAST_SLOT]

    def add_picture(self, image=None):
        """Add a new picture entry in the first free slot (its TIM in mngrp.bin now, its .TEX at Save)
        and select it: `image` (PIL), or a plain grey one to set with "Replace from PNG...". Returns the
        slot, or None (with a message) when no slot is free."""
        from PIL import Image
        free = self.free_slots()
        if not free:
            QMessageBox.warning(self, "Shiva - Magazine pictures",
                                f"mngrp.bin has no free slot left for a picture ({ADDED_FIRST_SLOT}-{ADDED_LAST_SLOT}).")
            return None
        if image is None:
            image = Image.new("RGBA", (256, 192), NEW_PICTURE_COLOR)
        palette, indices = quantize_picture(image)
        template = bytes(self.manager.mngrp.get_section_list()[TEMPLATE_SLOT].get_data_hex())
        slot = free[0]
        self.manager.add_raw_section(slot, encode_picture_tim(palette, indices, template))
        self._pending[slot] = (palette, indices)
        self._fill_slots(select=slot)
        self._slot_changed(self.slot_list.currentRow())
        return slot

    def add_from_file(self, path):
        """Add a new picture from an image file: add_picture, then its image. Returns the slot or None."""
        from PIL import Image
        try:
            with Image.open(path) as image:
                image.load()
                quantize_picture(image)  # refuse an image that cannot be a page picture first
                return self.add_picture(image.copy())
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Shiva - Magazine pictures", f"Cannot use {os.path.basename(path)}:\n{error}")
            return None

    def last_added_slot(self):
        """The last added picture, the only one that can be removed (None when there is none)."""
        slots = [slot for slot in self._picture_slots() if is_added_slot(slot)]
        if not slots or self.manager is None or slots[-1] != self.manager.last_used_slot():
            return None
        return slots[-1]

    def remove_last_picture(self):
        """Remove the last added picture from mngrp.bin (its .TEX on disk stays). Returns its slot."""
        slot = self.last_added_slot()
        if slot is None:
            return None
        self.manager.remove_last_raw_section(slot)
        self._pending.pop(slot, None)
        self._image_cache.pop(slot, None)
        self._fill_slots(select=slot - 1)
        if self._current_slot() is None and self.slot_list.count():
            self.slot_list.setCurrentRow(self.slot_list.count() - 1)
        self._slot_changed(self.slot_list.currentRow())
        return slot

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
        # An added picture is undone by not saving (its slot is already in the shared mngrp)
        self.revert_button.setEnabled(ready and self._current_slot() in self._pending
                                      and not is_added_slot(self._current_slot()))
        self.add_button.setEnabled(bool(self.free_slots()))
        self.remove_button.setEnabled(self.last_added_slot() is not None)

    def _export(self):
        raw_file = self._current_slot()
        image, _origin = self._picture(raw_file)
        if image is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export the picture",
                                              f"{pc_picture_name(raw_file)}.png", "PNG (*.png)")
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
