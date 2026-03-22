import os
import pathlib
import shutil
from typing import List

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
                             QScrollArea, QGridLayout, QSizePolicy, QFileDialog, QMessageBox)

from IfritTexture.ifrittexturemanager import IfritTextureManager, TextureData, MetaData
from IfritTexture.texturewidget import TextureWidget


class IfritTextureWidget(QWidget):
    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData"):
        QWidget.__init__(self)
        self.ifrit_manager = IfritTextureManager()
        self.icon_path = icon_path

        # 1. Main Root Layout
        self.main_layout = QVBoxLayout(self)

        # 2. Top Button Bar
        self._button_layout = QHBoxLayout()

        self._analyse_button = QPushButton("Analyse")
        self._analyse_button.clicked.connect(self._analyze)
        self._inject_button = QPushButton("Inject")
        self._inject_button.clicked.connect(self._inject)
        self._export_button = QPushButton("Export")
        self._export_button.clicked.connect(self._export)

        self._button_layout.addWidget(self._analyse_button)
        self._button_layout.addWidget(self._export_button)
        self._button_layout.addWidget(self._inject_button)

        self.main_layout.addLayout(self._button_layout)

        # 3. Scroll Area Setup
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        self.scroll_content = QWidget()
        self._texture_layout = QGridLayout(self.scroll_content)
        self._texture_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._texture_layout.setSpacing(10)

        self.scroll.setWidget(self.scroll_content)
        self.main_layout.addWidget(self.scroll)

        self._texture_widgets: List[TextureWidget] = []
        self._current_folder_dialog = ""

        # Initial empty state shows just the Plus button
        self._refresh_texture_grid()

    def _refresh_texture_grid(self):
        """Clears the grid and rebuilds it with current data + one Plus button."""
        # 1. Clear existing widgets from the layout
        while self._texture_layout.count():
            item = self._texture_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._texture_widgets.clear()


        # 2. Add existing textures from the manager
        last_index = -1
        for index, texture in enumerate(self.ifrit_manager.texture_data):
            new_widget = TextureWidget(texture_data=texture, icon_path=self.icon_path, title=f"Texture {index}")
            self._texture_widgets.append(new_widget)
            self._texture_layout.addWidget(new_widget, index // 2, index % 2)
            last_index = index

        self.add_plus_widget(last_index + 1)

        # 4. Handle Row Stretching so things stay at the top
        last_row = (last_index + 1 // 2) + 1
        for r in range(self._texture_layout.rowCount()):
            self._texture_layout.setRowStretch(r, 0)
        self._texture_layout.setRowStretch(last_row, 1)

    def add_plus_widget(self, next_index):
        self.ifrit_manager.texture_data.append(TextureData(None, None, None))
        self._texture_widgets.append(TextureWidget(texture_data=self.ifrit_manager.texture_data[-1], icon_path=self.icon_path, title="Add New", plus_type=True))
        self._texture_widgets[-1].request_new_texture.connect(self._handle_add_new)
        self._texture_layout.addWidget(self._texture_widgets[-1], next_index // 2, next_index % 2)


    def _handle_add_new(self):
        """Creates a blank TextureData and refreshes the UI."""
        self.ifrit_manager.texture_data[-1].create_dummy_images()
        self._refresh_texture_grid()

    def _analyze(self):
        files_to_load, _ = QFileDialog.getOpenFileNames(
            parent=self,
            caption="Search files containing tim",
            directory=self._current_folder_dialog
        )
        if files_to_load:
            self.ifrit_manager.texture_data.clear()
            for file_path in files_to_load:
                self.ifrit_manager.analyze(file_path)

            self._refresh_texture_grid()
            self.window().adjustSize()

            if self.ifrit_manager.temp_path.exists() and self.ifrit_manager.temp_path.is_dir():
                shutil.rmtree(self.ifrit_manager.temp_path)

    def _inject(self):
        if len([x for x in self._texture_widgets if not x.get_plus_type()]) > 0:
            self._export(export_dir=self.ifrit_manager.temp_path)
            file_to_load = QFileDialog.getOpenFileName(
                parent=self,
                caption="Search dat file",
                filter="*.dat",
                directory=self._current_folder_dialog
            )[0]
            if file_to_load:
                self.ifrit_manager.inject(self.ifrit_manager.temp_path, file_to_load)
                if self.ifrit_manager.temp_path.exists() and self.ifrit_manager.temp_path.is_dir():
                    shutil.rmtree(self.ifrit_manager.temp_path)
        else:
            message_box = QMessageBox()
            message_box.setText(f"Please create any image with plus button or import before injecting")
            message_box.setIcon(QMessageBox.Icon.Warning)
            message_box.setWindowTitle("IfritTexture - Warning")
            message_box.exec()
            return

    def _export(self, export_dir=None):
        if not export_dir:
            export_dir = QFileDialog.getExistingDirectory(self, "Select Export Directory")
        else:
            from pathlib import Path
            Path(export_dir).mkdir(parents=True, exist_ok=True)

        if not export_dir:
            return

        for index, widget in enumerate(self._texture_widgets):
            if not widget.get_plus_type():
                base_name = f"texture_{index}"
                meta_path = os.path.join(export_dir, f"{base_name}.meta")
                try:
                    with open(meta_path, 'w') as f:
                        f.write(f"depth={widget.get_depth()}\n")
                        f.write(f"imageX={widget.get_imageX()}\n")
                        f.write(f"imageY={widget.get_imageY()}\n")
                        f.write(f"paletteX={widget.get_paletteX()}\n")
                        f.write(f"paletteY={widget.get_paletteY()}\n")
                except Exception as e:
                    print(f"Failed to save meta: {e}")

                texture_pixmap = widget.get_texture_img()
                if texture_pixmap:
                    texture_pixmap.save(os.path.join(export_dir, f"{base_name}_texture.png"), "PNG")

                palette_pixmap = widget.get_palette_img()
                if palette_pixmap:
                    palette_pixmap.save(os.path.join(export_dir, f"{base_name}_palette.png"), "PNG")

    def sizeHint(self):
        return QSize(800, 600)  # Provided a more standard default size