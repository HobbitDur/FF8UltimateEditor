"""Component views over shared MAG/native byte images."""
import struct
from PyQt6.QtCore import Qt, QSignalBlocker, pyqtSignal
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
                            QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget)
from Fujin.magsectionwidget import MagSectionTabs


class EffectResourceView(QWidget):
    data_changed = pyqtSignal()

    def __init__(self, mode, resolve):
        super().__init__()
        self.mode, self.resolve = mode, resolve
        self._pending = True
        self.sources = QComboBox()
        self.sources.setMinimumContentsLength(18)
        self.sources.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.sources.currentIndexChanged.connect(self.activate)
        self.undo_button = QPushButton("Undo")
        self.redo_button = QPushButton("Redo")
        self.undo_button.clicked.connect(lambda: self._history(False))
        self.redo_button.clicked.connect(lambda: self._history(True))
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.sections = MagSectionTabs()
        self.sections.data_changed.connect(self.data_changed)
        row = QHBoxLayout()
        row.addWidget(QLabel("Source:"))
        row.addWidget(self.sources, 1)
        row.addWidget(self.undo_button)
        row.addWidget(self.redo_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(row)
        layout.addWidget(self.status)
        if mode == "parameters":
            self.parameter_table = QTableWidget(0, 5)
            self.parameter_table.setHorizontalHeaderLabels(["Parameter", "Value", "Type", "EN address", "Behavior"])
            self.parameter_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
            self.parameter_table.setColumnWidth(0, 250)
            self.parameter_table.cellChanged.connect(self._parameter_changed)
            display = QTabWidget()
            display.addTab(self.parameter_table, "Parameters")
            display.addTab(self.sections, "Operand sections")
            layout.addWidget(display, 1)
        else:
            layout.addWidget(self.sections, 1)

    def _sections(self, resource, manager):
        sections = manager.document.sections
        if self.mode == "files" or self.mode == "models" and resource.kind == "model":
            return sections
        if self.mode == "textures" and manager.document.format == "PlayStation TIM":
            return sections
        if self.mode == "parameters" and resource.kind == "camera_parameter":
            return sections
        kinds = {"camera": {"camera"},
            "models": {"model_header", "skeleton", "geometry", "animation", "model_trailer", "object"},
            "textures": {"texture", "palette", "texture_table", "clut_table", "pixels", "tim_block"},
            "sound": {"sound", "audio", "voice", "music_table"}}.get(self.mode, set())
        return [s for s in sections if s.kind in kinds]

    def set_resources(self, resources):
        previous = self.sources.currentData()
        previous_key = previous.key if previous else None
        with QSignalBlocker(self.sources):
            self.sources.clear()
            for resource in resources:
                manager = self.resolve(resource)
                if self.mode != "files" and (manager is None or not self._sections(resource, manager)):
                    continue
                mark = "* " if manager and manager.modified else ""
                detail = manager.document.format if manager else "not imported"
                self.sources.addItem(f"{mark}{resource.name} — {resource.source}; {detail}", resource)
                if resource.key == previous_key:
                    self.sources.setCurrentIndex(self.sources.count()-1)
        self._pending = True

    def activate(self, *_args):
        resource = self.sources.currentData()
        manager = self.resolve(resource) if resource else None
        self.undo_button.setEnabled(bool(manager and manager._undo))
        self.redo_button.setEnabled(bool(manager and manager._redo))
        if resource is None:
            self.status.setText("No loaded resource for this component. Overview lists known sources and unresolved dependencies.")
        else:
            location = (f"{resource.address:#x} in EN exe → Hext export" if resource.source == "Executable"
                        else manager.file_path if manager else
                        "Not imported: open it with the header's Import (Effect files).")
            self.status.setText(f"{resource.evidence}. {resource.note}\n{location}")
        self.sections.set_manager(manager, self._sections(resource, manager) if manager else None)
        if self.mode == "parameters":
            self._fill_parameters()
        self._pending = False

    def _fill_parameters(self):
        with QSignalBlocker(self.parameter_table):
            self.parameter_table.setRowCount(self.sources.count())
            for row in range(self.sources.count()):
                resource = self.sources.itemData(row)
                manager = self.resolve(resource)
                field = manager.document.fields_for(manager.document.sections[0])[0]
                value = struct.unpack_from("<"+field.fmt, manager.data)[0]
                for column, text in enumerate((resource.name, value, f"signed {8*field.size}-bit",
                                                f"0x{resource.address:X}", resource.note)):
                    item = QTableWidgetItem(str(text))
                    if column != 1:
                        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.parameter_table.setItem(row, column, item)

    def _parameter_changed(self, row, column):
        if column != 1:
            return
        resource = self.sources.itemData(row)
        manager = self.resolve(resource)
        field = manager.document.fields_for(manager.document.sections[0])[0]
        try:
            value = int(self.parameter_table.item(row, 1).text(), 0)
            if manager.set_field(field, value):
                with QSignalBlocker(self.sources):
                    self.sources.setCurrentIndex(row)
                self.data_changed.emit()
        except ValueError as error:
            self.status.setText(str(error))
            self._fill_parameters()

    def _history(self, redo):
        resource = self.sources.currentData()
        manager = self.resolve(resource) if resource else None
        if manager and (manager.redo() if redo else manager.undo()):
            self.data_changed.emit()
