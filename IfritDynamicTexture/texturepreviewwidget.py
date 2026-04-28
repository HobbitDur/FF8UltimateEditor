from PyQt6.QtCore import Qt, QRect, QSize, pyqtSignal
from PyQt6.QtGui import QPen, QColor, QBrush, QPainter, QPixmap
from PyQt6.QtWidgets import QFrame, QLabel


class TexturePreviewWidget(QLabel):
    """Widget that displays texture with source (blue) and target (red) rectangles"""

    rectangleClicked = pyqtSignal(int, int)  # entry_index, dest_index

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(300, 300)
        self.setFrameShape(QFrame.Shape.Box)
        self.setStyleSheet("background-color: #2a2a2a;")

        self.original_pixmap = None
        self.scaled_pixmap = None
        self.rectangles = []  # (x, y, width, height, color, line_width, label, entry_idx, dest_idx)
        self.scale_factor = 1.0

    def set_texture(self, pixmap: QPixmap):
        """Set the texture image to display"""
        self.original_pixmap = pixmap.scaled(128, 128, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.update_display()

    def add_rectangle(self, x: int, y: int, width: int, height: int, color: QColor,
                      line_width: int = 2, label: str = "", entry_idx: int = -1, dest_idx: int = -1):
        """Add a rectangle to overlay on the texture"""
        self.rectangles.append((x, y, width, height, color, line_width, label, entry_idx, dest_idx))
        self.update_display()

    def clear_rectangles(self):
        """Clear all overlay rectangles"""
        self.rectangles.clear()
        self.update_display()

    def mousePressEvent(self, event):
        """Handle mouse click to select rectangles"""
        if not self.scaled_pixmap:
            return

        pos = event.position()
        for x, y, w, h, color, line_width, label, entry_idx, dest_idx in self.rectangles:
            scaled_x = int(x * self.scale_factor)
            scaled_y = int(y * self.scale_factor)
            scaled_w = max(1, int(w * self.scale_factor))
            scaled_h = max(1, int(h * self.scale_factor))

            if scaled_x <= pos.x() <= scaled_x + scaled_w and scaled_y <= pos.y() <= scaled_y + scaled_h:
                self.rectangleClicked.emit(entry_idx, dest_idx)
                break

        super().mousePressEvent(event)

    def _draw_text_with_background(self, painter: QPainter, text: str, rect: QRect):
        """Draw text with a dark semi-transparent background for better visibility"""
        # Draw dark background with some transparency
        painter.setBrush(QBrush(QColor(0, 0, 0, 180)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, 3, 3)

        # Draw white text with black outline
        painter.setPen(QPen(Qt.GlobalColor.black, 2))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.setPen(QPen(Qt.GlobalColor.white, 1))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

    def update_display(self):
        """Update the displayed image with rectangles"""
        if self.original_pixmap is None or self.original_pixmap.isNull():
            self.setText("No texture loaded")
            return
        #self.scale_factor = 1.0 # To force no scale
        widget_size = self.size()
        if widget_size.width() <= 1 or widget_size.height() <= 1:
            widget_size = self.minimumSize()

        pix_size = self.original_pixmap.size()
        self.scale_factor = min(widget_size.width() / pix_size.width(),
                                widget_size.height() / pix_size.height())

        scaled_size = QSize(int(pix_size.width() * self.scale_factor),
                            int(pix_size.height() * self.scale_factor))
        self.scaled_pixmap = self.original_pixmap.scaled(scaled_size,
                                                         Qt.AspectRatioMode.KeepAspectRatio,
                                                         Qt.TransformationMode.SmoothTransformation)

        result = self.scaled_pixmap.copy()
        painter = QPainter(result)

        # First pass: Draw ALL destination rectangles (red)
        dest_rects = []
        for x, y, w, h, color, line_width, label, entry_idx, dest_idx in self.rectangles:
            if color == QColor(255, 0, 0, 255):  # Red destination
                scaled_x = int(x * self.scale_factor)
                scaled_y = int(y * self.scale_factor)
                scaled_w = max(1, int(w * self.scale_factor))
                scaled_h = max(1, int(h * self.scale_factor))
                dest_rects.append((scaled_x, scaled_y, scaled_w, scaled_h, color, line_width, label, entry_idx, dest_idx))

                pen = QPen(color, line_width)
                pen.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(pen)
                painter.setBrush(QBrush(Qt.GlobalColor.transparent))
                painter.drawRect(scaled_x, scaled_y, scaled_w, scaled_h)
                if label:
                    text_rect = QRect(scaled_x + 2, scaled_y + 2, scaled_w - 4, 20)
                    self._draw_text_with_background(painter, label, text_rect)

        # Second pass: Draw ALL source rectangles (blue) - on top of destinations
        for x, y, w, h, color, line_width, label, entry_idx, dest_idx in self.rectangles:
            if color == QColor(0, 0, 255, 255):  # Blue source
                scaled_x = int(x * self.scale_factor)
                scaled_y = int(y * self.scale_factor)
                scaled_w = max(1, int(w * self.scale_factor))
                scaled_h = max(1, int(h * self.scale_factor))

                # Check if this source overlaps with any destination at the same position
                overlapping = False
                for dx, dy, dw, dh, dcolor, dline_width, dlabel, dentry_idx, ddest_idx in dest_rects:
                    if (scaled_x == dx and scaled_y == dy and scaled_w == dw and scaled_h == dh):
                        overlapping = True
                        break

                if overlapping:
                    # Draw mixed purple color for the rectangle
                    pen = QPen(QColor(0, 255, 0, 255), line_width)
                    pen.setStyle(Qt.PenStyle.SolidLine)
                    painter.setPen(pen)
                    painter.setBrush(QBrush(Qt.GlobalColor.transparent))
                    painter.drawRect(scaled_x, scaled_y, scaled_w, scaled_h)
                    if label:
                        # Get the destination label too
                        dest_label = ""
                        for dx, dy, dw, dh, dcolor, dline_width, dlabel, dentry_idx, ddest_idx in dest_rects:
                            if (scaled_x == dx and scaled_y == dy and scaled_w == dw and scaled_h == dh):
                                dest_label = dlabel
                                break
                        combined_label = f"{label}/{dest_label}" if dest_label else label
                        text_rect = QRect(scaled_x + 2, scaled_y + 2, scaled_w - 4, 20)
                        self._draw_text_with_background(painter, combined_label, text_rect)
                else:
                    # Draw normal blue solid line
                    pen = QPen(color, line_width)
                    pen.setStyle(Qt.PenStyle.SolidLine)
                    painter.setPen(pen)
                    painter.setBrush(QBrush(Qt.GlobalColor.transparent))
                    painter.drawRect(scaled_x, scaled_y, scaled_w, scaled_h)
                    if label:
                        text_rect = QRect(scaled_x + 2, scaled_y + 2, scaled_w - 4, 20)
                        self._draw_text_with_background(painter, label, text_rect)

        painter.end()
        self.setPixmap(result)

    def resizeEvent(self, event):
        self.update_display()
        super().resizeEvent(event)