"""
Field view of the NPC card players tab: where the selected NPC stands and what it looks like.

Top: the field background (rebuilt from the map's .mim/.map) with the NPC's initial position
(its first SET3/SET) projected through the field camera (.ca). Bottom: the NPC's 3D model, the
chara.one entry its SETMODEL picks, in the Seed/Ifrit 3D viewer.

Every file comes from the map's folder in the modified field folder when it has it, else from
the vanilla one (JsmCardGameFile.asset_path).
"""
import os

import numpy as np
from PIL.ImageQt import ImageQt
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor, QFont
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSplitter, QSizePolicy

from FF8GameData.field.fieldbackground import render_background
from FF8GameData.field.fieldcamera import FieldCamera, Walkmesh

MARKER_RADIUS = 6
MARKER_COLOR = QColor(255, 40, 40)
# Camera distance in model heights: (1/2) / tan(22.5 deg) = 1.21 fits the height exactly
CHARACTER_FRAMING = 1.35


class BackgroundView(QWidget):
    """The field picture scaled to the widget (aspect kept), with the NPC marker on top."""

    def __init__(self):
        QWidget.__init__(self)
        self.pixmap = None
        self.marker = None  # (x, y) in picture pixels
        self.marker_text = ""
        self.message = "Select a card player."
        self.setMinimumHeight(160)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_picture(self, pixmap, marker=None, marker_text="", message=""):
        self.pixmap = pixmap
        self.marker = marker
        self.marker_text = marker_text
        self.message = message
        self.update()

    def picture_rect(self):
        if self.pixmap is None or self.pixmap.isNull():
            return QRectF()
        scale = min(self.width() / self.pixmap.width(), self.height() / self.pixmap.height())
        width, height = self.pixmap.width() * scale, self.pixmap.height() * scale
        return QRectF((self.width() - width) / 2, (self.height() - height) / 2, width, height)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.pixmap is None or self.pixmap.isNull():
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.message)
            return
        rect = self.picture_rect()
        painter.drawPixmap(rect, self.pixmap, QRectF(self.pixmap.rect()))
        if self.marker is not None:
            scale = rect.width() / self.pixmap.width()
            center = QPointF(rect.x() + self.marker[0] * scale, rect.y() + self.marker[1] * scale)
            painter.setPen(QPen(MARKER_COLOR, 3))
            painter.drawEllipse(center, MARKER_RADIUS, MARKER_RADIUS)
            if self.marker_text:
                font = QFont(painter.font())
                font.setBold(True)
                painter.setFont(font)
                text_position = center + QPointF(MARKER_RADIUS + 3, -MARKER_RADIUS)
                painter.setPen(QPen(QColor(0, 0, 0), 1))
                painter.drawText(text_position + QPointF(1, 1), self.marker_text)
                painter.setPen(QPen(QColor(255, 255, 255), 1))
                painter.drawText(text_position, self.marker_text)
        if self.message:
            painter.setPen(QPen(QColor(255, 255, 255), 1))
            painter.drawText(rect.adjusted(4, 4, -4, -4), Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft,
                             self.message)


class FieldScene:
    """Background picture, camera and walkmesh of one map (built once, then cached). Each file is
    taken from the modified folder when it has it, else from vanilla (jsm_file.asset_path)."""

    def __init__(self, jsm_file):
        self.pixmap = None
        self.origin = (0, 0)
        self.camera = None
        self.walkmesh = None
        self.error = ""
        map_name = jsm_file.map_name
        try:
            with open(jsm_file.asset_path(map_name + ".mim"), "rb") as mim_file, \
                    open(jsm_file.asset_path(map_name + ".map"), "rb") as map_file:
                image, self.origin = render_background(mim_file.read(), map_file.read())
            self.pixmap = QPixmap.fromImage(ImageQt(image).copy())
        except (OSError, ValueError) as error:
            self.error = f"No background: {error}"
        try:
            with open(jsm_file.asset_path(map_name + ".ca"), "rb") as ca_file:
                self.camera = FieldCamera(ca_file.read())
        except (OSError, ValueError, IndexError):
            self.camera = None
        try:
            with open(jsm_file.asset_path(map_name + ".id"), "rb") as id_file:
                self.walkmesh = Walkmesh(id_file.read())
        except (OSError, ValueError, IndexError):
            self.walkmesh = None

    def picture_position(self, position):
        """Picture pixel of an entity position (x, y, z or None, triangle), or None."""
        if position is None or self.camera is None:
            return None
        x, y, z, triangle = position
        if z is None:
            z = self.walkmesh.height_at(triangle, x, y) if self.walkmesh is not None else 0.0
        screen = self.camera.project((x, y, z))
        if screen is None:
            return None
        return screen[0] + self.origin[0], screen[1] + self.origin[1]


class NpcFieldView(QWidget):
    """Background + 3D model of the selected card player."""

    def __init__(self):
        QWidget.__init__(self)
        self.__scenes = {}  # jsm folder -> FieldScene
        self.seed_manager = None
        self.viewer_3d = None
        self.__chara_one_path = None
        self.main_chr_folders = []

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
        self.background_view = BackgroundView()
        self.model_label = QLabel()
        self.model_label.setWordWrap(True)
        self.__model_container = QWidget()
        self.__model_layout = QVBoxLayout()
        self.__model_layout.setContentsMargins(0, 0, 0, 0)
        self.__model_layout.addWidget(self.model_label)
        self.__model_container.setLayout(self.__model_layout)
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.addWidget(self.background_view)
        self.splitter.addWidget(self.__model_container)
        self.splitter.setSizes([300, 400])
        layout.addWidget(self.splitter)

    def __ensure_viewer(self):
        """The 3D viewer is heavy (OpenGL): created on the first model shown. View only: no
        toolbar, anim editor or playlist (show_controls=False), the skeleton stays hidden so
        bones cannot be picked or edited; mouse rotate / pan / zoom only, on the first frame."""
        if self.viewer_3d is None:
            from Ifrit.Ifrit3D.ifrit3dwidget import Ifrit3DWidget
            from Seed.seedmanager import SeedManager
            self.seed_manager = SeedManager()
            self.viewer_3d = Ifrit3DWidget(self.seed_manager, show_controls=False)
            self.viewer_3d.setToolTip("Left drag: rotate - Right drag: pan - Wheel: zoom")
            self.__model_layout.addWidget(self.viewer_3d, 1)
        return self.viewer_3d

    def scene(self, jsm_file):
        key = (jsm_file.map_name, tuple(jsm_file.asset_folders))
        if key not in self.__scenes:
            self.__scenes[key] = FieldScene(jsm_file)
        return self.__scenes[key]

    def set_field_folders(self, vanilla_folder: str, modified_folder: str = ""):
        """The opened field folders: scenes are rebuilt on demand, and main characters (whose
        chara.one entry points to field/model/main_chr/d0xx.mch) are read from their
        model/main_chr subfolder - the modified folder's first, then vanilla's."""
        self.__scenes = {}
        self.__chara_one_path = None
        self.main_chr_folders = [os.path.join(folder, "model", "main_chr")
                                 for folder in (modified_folder, vanilla_folder) if folder]

    def clear(self):
        self.background_view.set_picture(None, message="Select a card player.")
        self.model_label.setText("")
        if self.viewer_3d is not None:
            self.viewer_3d.hide()

    def show_player(self, jsm_file, player):
        scene = self.scene(jsm_file)
        position = jsm_file.entity_position(player.entity_name)
        marker = scene.picture_position(position)
        if scene.pixmap is None:
            message = scene.error
        elif position is None:
            message = "Initial position computed at runtime"
        elif marker is None:
            message = "No camera (.ca): position not shown"
        else:
            message = f"{jsm_file.map_name}: initial position ({position[0]}, {position[1]})"
        self.background_view.set_picture(scene.pixmap, marker, player.entity_name, message)
        self.__show_model(jsm_file, player)

    def __show_model(self, jsm_file, player):
        model_index = jsm_file.entity_model_index(player.entity_name)
        chara_one_path = jsm_file.asset_path("chara.one")
        if model_index is None:
            self.__model_failed(f"{player.entity_name} has no SETMODEL: no model to show.")
            return
        if not chara_one_path:
            self.__model_failed(f"No chara.one for {jsm_file.map_name} (neither in the modified nor the vanilla"
                                f" folder).")
            return
        viewer = self.__ensure_viewer()
        try:
            if self.__chara_one_path != chara_one_path:
                self.seed_manager.load_chara_one(chara_one_path)
                self.__chara_one_path = chara_one_path
            entries = self.seed_manager.chara_one.entries
            if model_index < len(entries) and entries[model_index].is_main:
                mch_name = entries[model_index].name + ".mch"
                folder = next((folder for folder in self.main_chr_folders
                               if os.path.isfile(os.path.join(folder, mch_name))), None)
                if folder is not None:
                    import pathlib
                    self.seed_manager.main_chr_folder = pathlib.Path(folder)
            entries = self.seed_manager.chara_one.entries
            if model_index >= len(entries):
                self.__model_failed(f"SETMODEL {model_index}: the chara.one only has {len(entries)} models.")
                return
            self.seed_manager.load_entry(model_index)
        except Exception as error:  # a model that cannot be built must not break the editor
            self.__model_failed(f"Model {model_index} could not be loaded: {error}")
            return
        entry = entries[model_index]
        kind = "main character, from main_chr" if entry.is_main else "NPC model"
        self.model_label.setText(f"<b>{entry.name}</b> ({kind}) - chara.one model {model_index}"
                                 f" (SETMODEL of {player.entity_name})")
        viewer.show()
        viewer.load_file()
        self.__frame_character(viewer.gl_widget)

    @staticmethod
    def __frame_character(gl_widget):
        """reset_view treats a standing character as an elongated shape and backs off to 3.5x its
        height: frame the height in the 45 deg field of view instead, with a small margin."""
        if len(gl_widget.vertices) == 0:
            return
        bbox_min = gl_widget.vertices_array.min(axis=0)
        bbox_max = gl_widget.vertices_array.max(axis=0)
        gl_widget.zoom = max(bbox_max - bbox_min) * CHARACTER_FRAMING
        # The orbit targets the frame-0 reference position, not the middle of the model (a
        # standing character's feet are much further from it than its head): pan to the box
        # center. reset_view's front view is rot_x 0 / rot_y 180, which mirrors x.
        center = ((bbox_min + bbox_max) / 2 - np.asarray(gl_widget.reference_position, dtype=float)
                  + np.asarray(gl_widget.model_translation, dtype=float))
        gl_widget.pan_x = float(center[0])
        gl_widget.pan_y = float(-center[1])
        gl_widget.update()

    def __model_failed(self, text: str):
        self.model_label.setText(text)
        if self.viewer_3d is not None:
            self.viewer_3d.hide()
