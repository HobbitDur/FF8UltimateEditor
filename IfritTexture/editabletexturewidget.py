import os
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtWidgets import QLabel, QPushButton, QFileDialog, QFrame, QMessageBox


class EditableTextureWidget(QLabel):
    # Custom signals so the parent widget knows when data actually changes
    imageChanged = pyqtSignal(str)  # Sends the new file path
    imageRefreshed = pyqtSignal()  # Notification of a reset

    # Type 1 is for palette, don't want to lose time to create a type.
    def __init__(self, image: QPixmap, max_size=256,  icon_path="Resources", parent=None, type = 0):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.type = type
        self.max_size = max_size
        self.setMaximumSize(max_size, max_size)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        #self.setStyleSheet("background-color: #2a2a2a; border: 1px solid #555;")
        self.setToolTip("Double-click to change image, Right-click to reset")

        self.icon_path = icon_path
        self._original_pixmap = image
        self._current_pixmap = image

        # --- Overlay Buttons ---
        btn_size = 30
        btn_style = """
            QPushButton { 
                /* The base state: subtle and semi-transparent */
                background-color: rgba(200, 220, 255, 180); 
                border: 1px solid rgba(255, 255, 255, 100);
                border-radius: 15px;
            }
            QPushButton:hover { 
                /* The hover state: different color/opacity */
                /* Let's try a light blue-ish tint as an example */
                background-color: rgba(150, 150, 255, 180); 
                border: 2px solid rgba(255, 255, 255, 255);
            }
            QPushButton:pressed {
                /* Optional: darken it when clicked so it feels responsive */
                background-color: rgba(50, 50, 50, 200);
            }
        """

        # Edit Button (Bottom Right)
        self._edit_btn = QPushButton(self)
        self._edit_btn.setIcon(QIcon(os.path.join(icon_path, 'pencil.webp')))
        self._edit_btn.setIconSize(QSize(22, 22))  # Makes the icon look "floating"
        self._edit_btn.setFixedSize(btn_size, btn_size)
        self._edit_btn.setToolTip("Change Image")
        self._edit_btn.setStyleSheet(btn_style)
        self._edit_btn.clicked.connect(self._on_edit)
        self._edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)  # Adds a "link" hand on hover

        # Position using the widget's current size
        self._edit_btn.move(self.width() - btn_size - 5, self.height() - btn_size - 5)
        # Refresh Button (Bottom Left)
        self._refresh_btn = QPushButton(self)
        self._refresh_btn.setIcon(QIcon(os.path.join(icon_path, 'reset.png')))
        self._refresh_btn.setFixedSize(btn_size, btn_size)
        self._refresh_btn.setToolTip("Restore Original")
        self._refresh_btn.setStyleSheet(btn_style)
        self._refresh_btn.move(5, self._original_pixmap.size().height() - btn_size - 5)
        self._refresh_btn.clicked.connect(self._on_refresh)

        self.set_image(image, True)



    def set_image(self, pix:QPixmap, is_original=False):
        """Loads and displays an image from path."""
        scaled_pix = None
        if not pix.isNull():
            if is_original:
                self._original_pixmap = pix
            if self.type == 1 and pix.size().height() == 1:
                scaled_pix = pix.scaled(
                    QSize(pix.size().width(),10),
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
            elif  self.type == 1 and pix.size().height() != 1:
                print(f"Unexpected height {pix.size().height} for a palette. Use only 1 px height")
                message_box = QMessageBox()
                message_box.setText(f"Unexpected height {pix.size().height()} for a palette. Use only 1 px height")
                message_box.setIcon(QMessageBox.Icon.Critical)
                message_box.setWindowTitle("IfritTexture - Error")
                message_box.exec()
                return
            elif pix.size().height() > 256 or pix.size().width() > 256:
                scaled_pix = pix.scaled(
                    QSize(self.max_size, self.max_size),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
            if scaled_pix:
                self.setPixmap(scaled_pix)
                self.setFixedSize(scaled_pix.size())
                self._current_pixmap = pix #We don't want to keep the upscale one, upscale is just to show in UI
                current_size = scaled_pix.size()
            else:
                self.setPixmap(pix)
                self.setFixedSize(pix.size())
                self._current_pixmap = pix
                current_size = pix.size()

            if current_size.height() < 50 or current_size.width() < 50:
                self._edit_btn.hide()
                self._refresh_btn.hide()

            self._reposition_buttons()


    def _on_edit(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Texture", "", "Images (*.png *.jpg *.bmp *.tif)"
        )
        if path:
            self.set_image(QPixmap(str(path)))
            self.imageChanged.emit(path)

    def _on_refresh(self):
        self.set_image(self._original_pixmap, False)
        self.imageRefreshed.emit()

    def _reposition_buttons(self):
        btn_size = self._edit_btn.width()
        # Move Edit to Bottom Right
        self._edit_btn.move(self.width() - btn_size - 5, self.height() - btn_size - 5)
        # Move Refresh to Bottom Left
        self._refresh_btn.move(5, self.height() - btn_size - 5)

    def get_image(self):
        return self._current_pixmap

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_edit()

    def contextMenuEvent(self, event):
        # Right-click to refresh
        self._on_refresh()
