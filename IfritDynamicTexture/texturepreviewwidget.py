from PyQt6.QtCore import Qt, QRect, QSize, pyqtSignal, QEvent, QTimer
from PyQt6.QtGui import QPen, QColor, QBrush, QPainter, QPixmap, QHelpEvent
from PyQt6.QtWidgets import QFrame, QLabel, QToolTip, QPushButton, QSlider

DEST_PALETTE = [
    QColor(255, 80, 80),
    QColor(255, 165, 0),
    QColor(255, 255, 0),
    QColor(0, 200, 80),
    QColor(0, 200, 255),
    QColor(200, 0, 255),
    QColor(255, 100, 200),
    QColor(180, 255, 100),
]
SOURCE_COLOR = QColor(80, 140, 255)
LEGEND_WIDTH = 140
LEGEND_PADDING = 8
LEGEND_ROW_H = 24
SWATCH_SIZE = 12


def _blend_colors(colors: list[QColor]) -> QColor:
    r = sum(c.red() for c in colors) // len(colors)
    g = sum(c.green() for c in colors) // len(colors)
    b = sum(c.blue() for c in colors) // len(colors)
    return QColor(r, g, b)


class TexturePreviewWidget(QLabel):
    rectangleClicked = pyqtSignal(int, int)
    # Emits (selected_dest_indices: set, source_selected: bool)
    legendSelectionChanged = pyqtSignal(object, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(300, 300)
        self.setFrameShape(QFrame.Shape.Box)
        self.setStyleSheet("background-color: #2a2a2a;")
        self._legend_tooltips: list[str] = []
        self.original_pixmap = None
        self.scaled_pixmap = None
        self.rectangles = []
        self.scale_factor = 1.0
        self._texture_offset_x = 0
        self._texture_offset_y = 0

        # Selection state
        self.selected_dest_indices: set = set()
        self.source_selected: bool = True

        # Legend hit areas: list of (y_top, y_bottom, is_source, dest_idx)
        self._legend_rows: list = []
        self._legend_x = 0
        # Animation state
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._animation_step)
        self._anim_steps: list = []  # list of (is_source, dest_idx or None)
        self._anim_current = 0
        self._anim_saved_dests: set = set()
        self._anim_saved_source: bool = True

        # Play button overlaid on legend panel
        self._play_btn = QPushButton("▶ Play", self)
        self._play_btn.setFixedHeight(28)
        self._play_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a5a2a;
                color: white;
                border: 1px solid #4a8a4a;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #3a7a3a; }
            QPushButton:checked {
                background-color: #8a2a2a;
                border: 1px solid #cc4a4a;
            }
            QPushButton:checked:hover { background-color: #aa3a3a; }
        """)
        self._play_btn.setCheckable(True)
        self._play_btn.toggled.connect(self._on_play_toggled)

        # Speed slider
        self._speed_slider = QSlider(Qt.Orientation.Horizontal, self)
        self._speed_slider.setMinimum(100)
        self._speed_slider.setMaximum(2000)
        self._speed_slider.setValue(500)
        self._speed_slider.setToolTip("Animation speed (ms per frame)")
        self._speed_slider.setStyleSheet("QSlider { background: transparent; }")

    def _on_play_toggled(self, checked: bool):
        if checked:
            self._start_animation()
        else:
            self.stop_animation()

    def _start_animation(self):
        """Save current selection and build step list from current rectangles."""
        self._anim_saved_dests = set(self.selected_dest_indices)
        self._anim_saved_source = self.source_selected

        # Build steps: source first, then each destination in order
        self._anim_steps = []
        has_source = any(color == QColor(0, 0, 255, 255)
                         for _, _, _, _, color, _, _, _, _ in self.rectangles)
        if has_source:
            self._anim_steps.append(('source', -1))
        for rect in self.rectangles:
            x, y, w, h, color, line_width, label, entry_idx, dest_idx = rect
            if color != QColor(0, 0, 255, 255):
                self._anim_steps.append(('dest', dest_idx))

        if not self._anim_steps:
            self._play_btn.setChecked(False)
            return

        self._anim_current = 0
        self._apply_animation_step(self._anim_current)
        self._anim_timer.start(self._speed_slider.value())
        self._play_btn.setText("■ Stop")

    def stop_animation(self):
        """Stop and restore saved selection."""
        self._anim_timer.stop()
        self.selected_dest_indices = set(self._anim_saved_dests)
        self.source_selected = self._anim_saved_source
        self.legendSelectionChanged.emit(
            set(self.selected_dest_indices), self.source_selected)
        self.update_display()
        self._play_btn.setText("▶ Play")
        self._play_btn.setChecked(False)

    def _animation_step(self):
        """Advance to next step."""
        self._anim_current = (self._anim_current + 1) % len(self._anim_steps)
        self._apply_animation_step(self._anim_current)
        # Update timer interval in case slider changed
        self._anim_timer.setInterval(self._speed_slider.value())

    def _apply_animation_step(self, step_idx: int):
        """Show only the rect for this step."""
        kind, dest_idx = self._anim_steps[step_idx]
        if kind == 'source':
            self.source_selected = True
            self.selected_dest_indices = set()
        else:
            self.source_selected = False
            self.selected_dest_indices = {dest_idx}
        self.legendSelectionChanged.emit(
            set(self.selected_dest_indices), self.source_selected)
        self.update_display()

    def resizeEvent(self, event):
        # Position play button and slider inside the legend panel at the bottom
        legend_x = self.width() - LEGEND_WIDTH
        btn_w = LEGEND_WIDTH - LEGEND_PADDING * 2
        self._play_btn.setGeometry(
            legend_x + LEGEND_PADDING,
            self.height() - 60,
            btn_w, 28
        )
        self._speed_slider.setGeometry(
            legend_x + LEGEND_PADDING,
            self.height() - 28,
            btn_w, 22
        )
        self.update_display()
        super().resizeEvent(event)

    def _dest_color(self, dest_idx: int) -> QColor:
        return DEST_PALETTE[dest_idx % len(DEST_PALETTE)]

    def set_selection(self, selected_dest_indices: set, source_selected: bool):
        """Set selection state from outside without emitting signal"""
        self.selected_dest_indices = set(selected_dest_indices)
        self.source_selected = source_selected
        self.update_display()

    def set_texture(self, pixmap: QPixmap):
        self.original_pixmap = pixmap
        self.update_display()

    def add_rectangle(self, x, y, width, height, color: QColor,
                      line_width=2, label="", entry_idx=-1, dest_idx=-1):
        self.rectangles.append((x, y, width, height, color, line_width, label, entry_idx, dest_idx))
        self.update_display()

    def clear_rectangles(self):
        self.rectangles.clear()
        self.update_display()

    def event(self, e:QHelpEvent):
        if e.type() == QEvent.Type.ToolTip:
            help_event: QHelpEvent = e  # already a QHelpEvent, just type-hint it
            pos = help_event.pos()
            if pos.x() >= self._legend_x:
                for idx, (y_top, y_bottom, is_source, dest_idx) in enumerate(self._legend_rows):
                    if y_top <= pos.y() <= y_bottom:
                        tip = self._legend_tooltips[idx] if idx < len(self._legend_tooltips) else ""
                        if tip:
                            QToolTip.showText(help_event.globalPos(), tip, self)
                            return True
            QToolTip.hideText()
            return True
        return super().event(e)

    def mousePressEvent(self, event):
        pos = event.position()

        # --- Legend click: toggle as before ---
        if pos.x() >= self._legend_x:
            for (y_top, y_bottom, is_source, dest_idx) in self._legend_rows:
                if y_top <= pos.y() <= y_bottom:
                    if is_source:
                        self.source_selected = not self.source_selected
                    else:
                        if dest_idx in self.selected_dest_indices:
                            self.selected_dest_indices.discard(dest_idx)
                        else:
                            self.selected_dest_indices.add(dest_idx)
                    self.legendSelectionChanged.emit(
                        set(self.selected_dest_indices), self.source_selected)
                    self.update_display()
                    return

        # --- Texture click: deselect only, one at a time for overlaps ---
        if not self.scaled_pixmap:
            return

        tx = pos.x() - self._texture_offset_x
        ty = pos.y() - self._texture_offset_y

        # Collect all rects under the click that are currently selected
        selected_here = []
        for rect in self.rectangles:
            x, y, w, h, color, line_width, label, entry_idx, dest_idx = rect
            is_source = color == QColor(0, 0, 255, 255)
            sx = int(x * self.scale_factor)
            sy = int(y * self.scale_factor)
            sw = max(1, int(w * self.scale_factor))
            sh = max(1, int(h * self.scale_factor))
            if not (sx <= tx <= sx + sw and sy <= ty <= sy + sh):
                continue
            if is_source and self.source_selected:
                selected_here.append((True, dest_idx))
            elif not is_source and dest_idx in self.selected_dest_indices:
                selected_here.append((False, dest_idx))

        # Deselect only the first selected rect found (source before destinations)
        if selected_here:
            is_source, dest_idx = selected_here[0]
            if is_source:
                self.source_selected = False
            else:
                self.selected_dest_indices.discard(dest_idx)
            self.legendSelectionChanged.emit(
                set(self.selected_dest_indices), self.source_selected)
            self.update_display()

        super().mousePressEvent(event)

    def update_display(self):
        if self.original_pixmap is None or self.original_pixmap.isNull():
            self.setText("No texture loaded")
            return

        widget_size = self.size()
        if widget_size.width() <= 1 or widget_size.height() <= 1:
            widget_size = self.minimumSize()

        tex_area_w = widget_size.width() - LEGEND_WIDTH
        tex_area_h = widget_size.height()

        pix_size = self.original_pixmap.size()
        self.scale_factor = min(tex_area_w / pix_size.width(),
                                tex_area_h / pix_size.height())

        scaled_w = int(pix_size.width() * self.scale_factor)
        scaled_h = int(pix_size.height() * self.scale_factor)
        self.scaled_pixmap = self.original_pixmap.scaled(
            QSize(scaled_w, scaled_h),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        canvas = QPixmap(widget_size.width(), widget_size.height())
        canvas.fill(QColor(42, 42, 42))
        painter = QPainter(canvas)

        self._texture_offset_x = (tex_area_w - scaled_w) // 2
        self._texture_offset_y = (tex_area_h - scaled_h) // 2
        self._legend_x = tex_area_w
        painter.drawPixmap(self._texture_offset_x, self._texture_offset_y, self.scaled_pixmap)

        # --- Build coord maps ---
        # Map (x,y,w,h) → list of (label, is_source) for tooltip generation
        coord_labels: dict = {}
        for rect in self.rectangles:
            x, y, w, h, color, line_width, label, entry_idx, dest_idx = rect
            is_source = color == QColor(0, 0, 255, 255)
            text = label if label else ("Source" if is_source else f"Dest {dest_idx}")
            coord_labels.setdefault((x, y, w, h), []).append(text)

        # Scaled coord groups for overlap color blending
        coord_groups: dict = {}
        for rect in self.rectangles:
            x, y, w, h, color, line_width, label, entry_idx, dest_idx = rect
            is_source = color == QColor(0, 0, 255, 255)
            sx = self._texture_offset_x + int(x * self.scale_factor)
            sy = self._texture_offset_y + int(y * self.scale_factor)
            sw = max(1, int(w * self.scale_factor))
            sh = max(1, int(h * self.scale_factor))
            coord_groups.setdefault((sx, sy, sw, sh), []).append((rect, is_source))

        # --- Draw rectangles ---
        for pass_name in ["dest", "source"]:
            for rect in self.rectangles:
                x, y, w, h, color, line_width, label, entry_idx, dest_idx = rect
                is_source = color == QColor(0, 0, 255, 255)

                if pass_name == "source" and not is_source:
                    continue
                if pass_name == "dest" and is_source:
                    continue
                if is_source and not self.source_selected:
                    continue
                if not is_source and dest_idx not in self.selected_dest_indices:
                    continue

                sx = self._texture_offset_x + int(x * self.scale_factor)
                sy = self._texture_offset_y + int(y * self.scale_factor)
                sw = max(1, int(w * self.scale_factor))
                sh = max(1, int(h * self.scale_factor))

                visible_colors = []
                for (grect, gis_source) in coord_groups[(sx, sy, sw, sh)]:
                    gx, gy, gw, gh, gcolor, gline_width, glabel, gentry_idx, gdest_idx = grect
                    if gis_source and self.source_selected:
                        visible_colors.append(SOURCE_COLOR)
                    elif not gis_source and gdest_idx in self.selected_dest_indices:
                        visible_colors.append(self._dest_color(gdest_idx))

                if not visible_colors:
                    continue

                draw_color = (_blend_colors(visible_colors)
                              if len(visible_colors) > 1
                              else (SOURCE_COLOR if is_source else self._dest_color(dest_idx)))

                pen = QPen(draw_color, line_width + (1 if is_source else 0))
                pen.setStyle(Qt.PenStyle.SolidLine if is_source else Qt.PenStyle.DashLine)
                painter.setPen(pen)
                painter.setBrush(QBrush(Qt.GlobalColor.transparent))
                painter.drawRect(sx, sy, sw, sh)

        # --- Build legend entries ---
        legend_entries = []
        for rect in self.rectangles:
            x, y, w, h, color, line_width, label, entry_idx, dest_idx = rect
            is_source = color == QColor(0, 0, 255, 255)
            draw_color = SOURCE_COLOR if is_source else self._dest_color(dest_idx)
            text = label if label else ("Source" if is_source else f"Dest {dest_idx}")
            overlapping = coord_labels[(x, y, w, h)]
            tooltip = ""
            if len(overlapping) > 1:
                text = f"{text} ⚠"
                tooltip = "Overlapping rectangles at same position:\n" + "\n".join(
                    f"  • {t}" for t in overlapping)
            legend_entries.append((draw_color, text, is_source, dest_idx, tooltip))

        # --- Draw legend panel ---
        self._legend_rows.clear()
        self._legend_tooltips.clear()

        painter.fillRect(self._legend_x, 0, LEGEND_WIDTH, widget_size.height(), QColor(30, 30, 30))
        painter.setPen(QPen(QColor(80, 80, 80), 1))
        painter.drawLine(self._legend_x, 0, self._legend_x, widget_size.height())

        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(QColor(200, 200, 200), 1))
        painter.drawText(QRect(self._legend_x + LEGEND_PADDING, 8,
                               LEGEND_WIDTH - LEGEND_PADDING, 20),
                         Qt.AlignmentFlag.AlignLeft, "Legend")
        font.setBold(False)
        painter.setFont(font)

        row_y = 34
        for (draw_color, text, is_source, dest_idx, tooltip) in legend_entries:
            is_selected = self.source_selected if is_source else (dest_idx in self.selected_dest_indices)

            row_rect = QRect(self._legend_x, row_y, LEGEND_WIDTH, LEGEND_ROW_H)
            if is_selected:
                painter.fillRect(row_rect, QColor(60, 60, 80))
                painter.setPen(QPen(draw_color.lighter(130), 1))
                painter.drawRect(row_rect.adjusted(0, 0, -1, -1))

            swatch_rect = QRect(self._legend_x + LEGEND_PADDING,
                                row_y + (LEGEND_ROW_H - SWATCH_SIZE) // 2,
                                SWATCH_SIZE, SWATCH_SIZE)
            painter.fillRect(swatch_rect, draw_color)
            painter.setPen(QPen(QColor(200, 200, 200), 1))
            painter.drawRect(swatch_rect)

            text_color = QColor(220, 220, 220) if is_selected else QColor(120, 120, 120)
            painter.setPen(QPen(text_color, 1))
            text_rect = QRect(self._legend_x + LEGEND_PADDING + SWATCH_SIZE + 6,
                              row_y,
                              LEGEND_WIDTH - LEGEND_PADDING - SWATCH_SIZE - 10,
                              LEGEND_ROW_H)
            painter.drawText(text_rect,
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                             text)

            self._legend_rows.append((row_y, row_y + LEGEND_ROW_H, is_source, dest_idx))
            self._legend_tooltips.append(tooltip)
            row_y += LEGEND_ROW_H

        # Reserve bottom space for play button — just draw the speed label
        speed_label_rect = QRect(self._legend_x + LEGEND_PADDING,
                                 widget_size.height() - 90,
                                 LEGEND_WIDTH - LEGEND_PADDING, 16)
        small_font = painter.font()
        small_font.setPointSize(max(7, small_font.pointSize() - 1))
        painter.setFont(small_font)
        painter.setPen(QPen(QColor(100, 100, 100), 1))
        painter.drawText(speed_label_rect, Qt.AlignmentFlag.AlignLeft, "Speed ↓  Click to toggle")

        painter.end()
        self.setPixmap(canvas)
