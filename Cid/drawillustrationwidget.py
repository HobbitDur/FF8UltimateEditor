import os

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget, QSizePolicy

from Cid.drawmapwidget import DrawMapWidget


class AspectImageLabel(QLabel):
    """QLabel that scales its pixmap to fill the label while keeping aspect ratio."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(1, 1)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self._pixmap = QPixmap()

    def set_source(self, pixmap):
        self._pixmap = pixmap
        self._rescale()

    def _rescale(self):
        if self._pixmap.isNull():
            self.setText("(no image available)")
            return
        self.setPixmap(self._pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        self._rescale()
        super().resizeEvent(event)


class FieldImageView(QWidget):
    """Shows every field screenshot a draw point appears in, side by side."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._title = QLabel("Select a field draw point")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._row = QHBoxLayout()
        self._row.setContentsMargins(0, 0, 0, 0)
        row_container = QWidget()
        row_container.setLayout(self._row)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._title)
        layout.addWidget(row_container, 1)

    def set_fields(self, draw_id, fields):
        """fields: list of (field_name, image_path)."""
        while self._row.count():
            widget = self._row.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()

        if not fields:
            self._title.setText(f"No field image for Draw ID {draw_id}")
            self._row.addWidget(AspectImageLabel())
            return

        plural = "s" if len(fields) > 1 else ""
        self._title.setText(f"Draw ID {draw_id}  —  {len(fields)} field{plural}")
        for name, path in fields:
            panel = QWidget()
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(2, 2, 2, 2)
            caption = QLabel(name)
            caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
            image = AspectImageLabel()
            image.set_source(QPixmap(path))
            panel_layout.addWidget(caption)
            panel_layout.addWidget(image, 1)
            self._row.addWidget(panel)


class DrawIllustrationWidget(QWidget):
    """Context-aware illustration for the selected draw point.

    World draw points (129..256) show the clickable world map with markers;
    field draw points (1..128) show every field screenshot the draw point
    appears in (from the Deling image export), resolved through
    ``draw_field.json`` (draw ID -> field name(s)).
    """

    position_picked = pyqtSignal(int, int)  # re-emitted from the world map

    def __init__(self, map_path, draw_field_map, images_dir, parent=None):
        super().__init__(parent)
        self._draw_field_map = draw_field_map or {}
        self._images_dir = images_dir

        self.map = DrawMapWidget(map_path)
        self.field_view = FieldImageView()
        self._stack = QStackedWidget()
        self._stack.addWidget(self.map)         # index 0
        self._stack.addWidget(self.field_view)  # index 1

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)

        self.map.position_picked.connect(self.position_picked)

    def set_draw_list(self, draw_list):
        self.map.set_draw_list(draw_list)

    def refresh(self):
        self.map.refresh()

    def set_selected(self, row, draw):
        if draw is not None and not draw.is_world():
            self._show_field_image(draw)
            self._stack.setCurrentWidget(self.field_view)
        else:
            self.map.set_selected(row if (draw is not None and draw.is_world()) else -1)
            self._stack.setCurrentWidget(self.map)

    def _show_field_image(self, draw):
        fields = []
        for name in self._draw_field_map.get(str(draw.get_id()), []):
            path = os.path.join(self._images_dir, name + ".png")
            if os.path.exists(path):
                fields.append((name, path))
        self.field_view.set_fields(draw.get_id(), fields)
