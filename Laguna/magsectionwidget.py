"""Lazy, bounded section editors sharing the LagunaManager byte image and undo history."""
import math
import struct

from PyQt6.QtCore import Qt, QSignalBlocker, pyqtSignal
from PyQt6.QtGui import QFont, QImage, QPixmap
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QTableWidget,
                             QTableWidgetItem, QSpinBox, QPushButton, QFileDialog, QPlainTextEdit,
                             QScrollArea, QHeaderView)


def _readonly(text):
    item = QTableWidgetItem(str(text))
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


class MagSectionTabs(QTabWidget):
    data_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = None
        self.setUsesScrollButtons(True)
        self.currentChanged.connect(self._open_page)

    def set_manager(self, manager):
        selected = self.currentWidget()
        selected_start = selected.property("section_start") if selected else None
        with QSignalBlocker(self):
            while self.count():
                page = self.widget(0)
                self.removeTab(0)
                page.deleteLater()
            self.manager = manager
            if manager:
                for section in manager.document.sections:
                    page = QWidget()
                    page.setProperty("section_start", section.start)
                    self.addTab(page, section.name)
                    self.setTabToolTip(self.count()-1, f"0x{section.start:X}–0x{section.end:X} ({section.size} bytes)")
                    if section.start == selected_start:
                        self.setCurrentIndex(self.count()-1)
        self._open_page(self.currentIndex())

    def _open_page(self, index):
        page = self.widget(index)
        if page is None or page.layout() is not None or not self.manager:
            return
        start = page.property("section_start")
        section = next(s for s in self.manager.document.sections if s.start == start)
        layout = QVBoxLayout(page)
        editor = MagSectionEditor(self.manager, section)
        editor.data_changed.connect(self.data_changed)
        layout.addWidget(editor)


class MagSectionEditor(QWidget):
    """Named fields, camera controls, and paged byte editing/export for every section."""
    data_changed = pyqtSignal()
    PAGE_BYTES = 512
    PAGE_FIELDS = 256

    def __init__(self, manager, section):
        super().__init__()
        self.manager, self.section = manager, section
        self.fields = manager.document.fields_for(section)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color: #d45c4c")
        layout = QVBoxLayout(self)
        info = QLabel(f"{section.name} — 0x{section.start:X} to 0x{section.end:X}, {section.size:,} bytes. "
                      "Edits keep the size and all following offsets.")
        info.setWordWrap(True)
        info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(info)
        if section.note:
            note = QLabel(section.note)
            note.setWordWrap(True)
            layout.addWidget(note)
        buttons = QHBoxLayout()
        export = QPushButton("Export section…")
        export.clicked.connect(self._export)
        replace = QPushButton("Replace section…")
        replace.clicked.connect(self._replace)
        buttons.addWidget(export)
        buttons.addWidget(replace)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.views = QTabWidget()
        if section.kind == "camera":
            self._camera_view()
        if self.fields:
            self._fields_view()
        if manager.document.format == "PlayStation TIM":
            self._texture_view()
        self._bytes_view()
        layout.addWidget(self.views, 1)
        layout.addWidget(self.error)

    def _announce(self):
        self.error.clear()
        self._fill_bytes()
        if self.fields:
            self._fill_fields()
        self.data_changed.emit()

    def _fields_view(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.field_page = QSpinBox()
        self.field_page.setRange(0, max(0, math.ceil(len(self.fields)/self.PAGE_FIELDS)-1))
        self.field_page.setPrefix("Page ")
        self.field_page.valueChanged.connect(self._fill_fields)
        layout.addWidget(self.field_page)
        self.field_table = QTableWidget(0, 4)
        self.field_table.setHorizontalHeaderLabels(["Field", "File offset", "Type", "Value"])
        self.field_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.field_table.cellChanged.connect(self._field_changed)
        layout.addWidget(self.field_table)
        self.views.addTab(page, "Fields")
        self._fill_fields()

    def _fill_fields(self, *_args):
        with QSignalBlocker(self.field_table):
            first = self.field_page.value()*self.PAGE_FIELDS
            fields = self.fields[first:first+self.PAGE_FIELDS]
            self.field_table.setRowCount(len(fields))
            for row, f in enumerate(fields):
                value = struct.unpack_from("<"+f.fmt, self.manager.data, f.offset)[0]
                for column, text in enumerate((f.name, f"0x{f.offset:X}", f.fmt)):
                    self.field_table.setItem(row, column, _readonly(text))
                self.field_table.setItem(row, 3, QTableWidgetItem(str(value) if f.fmt.islower() else f"0x{value:X}"))

    def _field_changed(self, row, column):
        if column != 3:
            return
        try:
            field = self.fields[self.field_page.value()*self.PAGE_FIELDS+row]
            text = self.field_table.item(row, column).text().strip()
            value = int(text, 16 if text.lower().startswith(("0x", "-0x")) else 10)
            if self.manager.set_field(field, value):
                self._announce()
        except (ValueError, IndexError) as error:
            self.error.setText(str(error))
            self._fill_fields()

    def _bytes_view(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.byte_page = QSpinBox()
        self.byte_page.setRange(0, max(0, math.ceil(self.section.size/self.PAGE_BYTES)-1))
        self.byte_page.setPrefix("Byte page ")
        self.byte_page.valueChanged.connect(self._fill_bytes)
        layout.addWidget(self.byte_page)
        self.byte_table = QTableWidget(0, 17)
        self.byte_table.setHorizontalHeaderLabels(["File offset"]+[f"{i:X}" for i in range(16)])
        self.byte_table.setFont(QFont("Consolas", 10))
        self.byte_table.horizontalHeader().setDefaultSectionSize(38)
        self.byte_table.setColumnWidth(0, 110)
        self.byte_table.cellChanged.connect(self._byte_changed)
        layout.addWidget(self.byte_table)
        self.views.addTab(page, "Bytes (hex)")
        self._fill_bytes()

    def _fill_bytes(self, *_args):
        start = self.section.start+self.byte_page.value()*self.PAGE_BYTES
        end = min(start+self.PAGE_BYTES, self.section.end)
        with QSignalBlocker(self.byte_table):
            self.byte_table.clearContents()
            self.byte_table.setRowCount(math.ceil((end-start)/16))
            for row, offset in enumerate(range(start, end, 16)):
                self.byte_table.setItem(row, 0, _readonly(f"0x{offset:06X}"))
                for column in range(16):
                    at = offset+column
                    item = QTableWidgetItem(f"{self.manager.data[at]:02X}") if at < end else _readonly("")
                    self.byte_table.setItem(row, column+1, item)

    def _byte_changed(self, row, column):
        if column == 0:
            return
        offset = self.section.start+self.byte_page.value()*self.PAGE_BYTES+16*row+column-1
        try:
            if not self.section.start <= offset < self.section.end:
                raise ValueError("Outside the section")
            value = int(self.byte_table.item(row, column).text(), 16)
            if not 0 <= value <= 255:
                raise ValueError("A byte must be between 00 and FF")
            if self.manager.patch_bytes(offset, bytes([value])):
                self._announce()
        except ValueError as error:
            self.error.setText(str(error))
            self._fill_bytes()

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export MAG section", self.section.name+".bin", "Binary (*.bin);;All files (*)")
        if path:
            try:
                with open(path, "wb") as f:
                    f.write(self.manager.data[self.section.start:self.section.end])
            except OSError as error:
                self.error.setText(str(error))

    def _replace(self):
        path, _ = QFileDialog.getOpenFileName(self, "Replace MAG section (same byte size)", "", "All files (*)")
        if path:
            try:
                with open(path, "rb") as f:
                    data = f.read()
                if self.manager.replace_section(self.section.start, data):
                    self._announce()
            except (OSError, ValueError) as error:
                self.error.setText(str(error))

    def _texture_view(self):
        from FF8GameData.tim.timfile import decode_tim
        try:
            tim = decode_tim(bytes(self.manager.data))
            if tim is None:
                return
            rgba = tim.image.convert("RGBA")
            picture = QLabel()
            picture.setPixmap(QPixmap.fromImage(QImage(rgba.tobytes(), rgba.width, rgba.height,
                                                      rgba.width*4, QImage.Format.Format_RGBA8888).copy()))
            picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
            scroll = QScrollArea()
            scroll.setWidget(picture)
            self.views.addTab(scroll, f"Texture preview ({rgba.width}×{rgba.height})")
        except (ValueError, IndexError, struct.error):
            pass  # Malformed/unsupported TIM remains editable in the bounded byte view.

    def _camera_view(self):
        from FF8GameData.gamedata import GameData
        from Fujin.cameraeffectmanager import CameraEffectManager, CameraTrack
        from Watts.cameracollectionwidget import CameraCollectionWidget
        try:
            self.camera_manager = CameraEffectManager(GameData(getattr(self.manager, "game_data_folder", "FF8GameData")))
            self.camera_track = CameraTrack.from_bytes(
                self.camera_manager.vm, bytes(self.manager.data[self.section.start:self.section.end]),
                effect_id=0, name="Embedded camera", label="MAG camera", address=self.section.start, push_operand=0)
        except (ValueError, IndexError, struct.error) as error:
            self.error.setText(f"Camera could not be decoded: {error}. The raw bytes remain available.")
            return
        script = QWidget()
        layout = QVBoxLayout(script)
        self.camera_script = QPlainTextEdit(self.camera_manager.script_code(self.camera_track))
        self.camera_script.setFont(QFont("Consolas", 10))
        layout.addWidget(self.camera_script)
        apply = QPushButton("Apply camera script (same size)")
        apply.clicked.connect(self._apply_camera_script)
        layout.addWidget(apply)
        self.views.addTab(script, "Camera script")
        collection = CameraCollectionWidget(self.camera_track.collection, show_preview_buttons=False)
        collection.data_changed.connect(self._apply_camera)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(collection)
        self.views.addTab(scroll, "Keyframes")

    def _apply_camera_script(self):
        try:
            track = self.camera_track
            before = track.script
            self.camera_manager.set_script_code(track, self.camera_script.toPlainText())
            if len(track.to_bytes()) != self.section.size:
                track.script = before
                raise ValueError("The camera script must fit its current space in the MAG file")
            self._apply_camera()
        except ValueError as error:
            self.error.setText(str(error))

    def _apply_camera(self):
        try:
            if self.manager.replace_section(self.section.start, self.camera_track.to_bytes()):
                self._announce()
        except ValueError as error:
            self.error.setText(str(error))
