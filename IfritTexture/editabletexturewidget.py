import os
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtWidgets import QLabel, QPushButton, QFileDialog, QFrame


class EditableTextureWidget(QLabel):
    # Custom signals so the parent widget knows when data actually changes
    imageChanged = pyqtSignal(str)  # Sends the new file path
    imageRefreshed = pyqtSignal()  # Notification of a reset

    def __init__(self, image_path, max_size=256,  icon_path="Resources", parent=None):
        super().__init__(parent)
        self.setMaximumSize(max_size, max_size)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: #2a2a2a; border: 1px solid #555;")

        self.icon_path = icon_path
        self.original_pixmap =  QPixmap(str(image_path))
        self.setPixmap(self.original_pixmap)
        self.setFixedSize(self.original_pixmap.size())
        self.current_pixmap = None

        # --- Overlay Buttons ---
        btn_size = 30
        btn_style = """
            QPushButton { 
                background-color: rgba(60, 60, 60, 180); 
                border-radius: 4px; 
                border: 1px solid #888;
            }
            QPushButton:hover { background-color: rgba(100, 100, 100, 220); }
        """

        # Edit Button (Bottom Right)
        self.edit_btn = QPushButton(self)
        self.edit_btn.setIcon(QIcon(os.path.join(icon_path, 'pencil.webp')))
        self.edit_btn.setFixedSize(btn_size, btn_size)
        self.edit_btn.setToolTip("Change Image")
        self.edit_btn.setStyleSheet(btn_style)
        self.edit_btn.move(self.original_pixmap.size().width() - btn_size - 5, self.original_pixmap.size().height() - btn_size - 5)
        self.edit_btn.clicked.connect(self._on_edit)

        # Refresh Button (Bottom Left)
        self.refresh_btn = QPushButton(self)
        self.refresh_btn.setIcon(QIcon(os.path.join(icon_path, 'refresh.png')))
        self.refresh_btn.setFixedSize(btn_size, btn_size)
        self.refresh_btn.setToolTip("Restore Original")
        self.refresh_btn.setStyleSheet(btn_style)
        self.refresh_btn.move(5, self.original_pixmap.size().height() - btn_size - 5)
        self.refresh_btn.clicked.connect(self._on_refresh)

    def set_image(self, path, is_original=False):
        """Loads and displays an image from path."""
        pix = QPixmap(str(path))
        if not pix.isNull():
            if is_original:
                self.original_pixmap = pix
            self.current_pixmap = pix
            self.setPixmap(pix)

    def _on_edit(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Texture", "", "Images (*.png *.jpg *.bmp *.tif)"
        )
        if path:
            self.set_image(path)
            self.imageChanged.emit(path)

    def _on_refresh(self):
        if self.original_pixmap:
            self.setPixmap(self.original_pixmap)
            self.imageRefreshed.emit()