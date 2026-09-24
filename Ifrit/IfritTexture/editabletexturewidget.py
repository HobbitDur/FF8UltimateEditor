import os
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QIcon, QImage, QPainter
from PyQt6.QtWidgets import QLabel, QPushButton, QFileDialog, QFrame, QMessageBox, QInputDialog


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
            if self.type == 1:
                # One pixel row per CLUT row (a TIM can hold several), each shown 10 px tall.
                # FastTransformation: smoothing would blend neighbouring palette entries
                scaled_pix = pix.scaled(
                    QSize(pix.size().width(), 10 * pix.size().height()),
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.FastTransformation
                )
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
            # via QImage: QPixmap(fileName) caches on path + size + mtime-in-
            # seconds, so re-importing the same file after editing it would
            # show the previous version (see IfritManager.TextureData)
            pix = QPixmap.fromImage(QImage(str(path)))
            current = self._current_pixmap
            if (self.type == 1 and current is not None and not current.isNull()
                    and pix.size() != current.size()):
                pix = self._fit_palette(pix, current)
                if pix is None:
                    return
            self.set_image(pix)
            self.imageChanged.emit(path)

    def _fit_palette(self, pix: QPixmap, current: QPixmap):
        """A palette image whose row count differs from the current palette: ask whether it
        replaces some rows (fewer rows) or the whole palette. None when cancelled/impossible."""
        rows, current_rows = pix.height(), current.height()
        if pix.width() != current.width():
            QMessageBox.critical(
                self, "IfritTexture - Error",
                f"This palette has {current.width()} colors per row; the selected image is "
                f"{pix.width()} pixels wide.")
            return None
        whole = f"Replace the whole palette ({current_rows} rows -> {rows} row{'s' if rows > 1 else ''})"
        choices = []
        if rows < current_rows:
            for start in range(current_rows - rows + 1):
                choices.append(f"Replace row {start}" if rows == 1
                               else f"Replace rows {start}-{start + rows - 1}")
        choices.append(whole)
        choice, ok = QInputDialog.getItem(
            self, "Import palette",
            f"The palette has {current_rows} row(s), the selected image has {rows}:",
            choices, 0, False)
        if not ok:
            return None
        if choice == whole:
            return pix
        return self.replace_palette_rows(current, pix, choices.index(choice))

    @staticmethod
    def replace_palette_rows(current: QPixmap, rows: QPixmap, start_row: int) -> QPixmap:
        """`current` with its rows start_row.. overwritten by `rows` (alpha copied as is)."""
        image = current.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        painter = QPainter(image)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.drawImage(0, start_row, rows.toImage().convertToFormat(QImage.Format.Format_ARGB32))
        painter.end()
        return QPixmap.fromImage(image)

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
