"""Font tab: view and edit an FF8 font file (.tdw), as Deling's font manager does.

Opening ``main/sysfnt.tdw`` (the game font) or a field's ``.tdw`` (its additional glyphs) gives one
of these tabs. Like Deling's font editor (TdwWidget2 and its grid / letter / palette widgets, by
myst6re, GPL-3.0) it shows each table as a 16x14 grid; clicking a glyph opens it zoomed, where you
paint its pixels with the colour levels below it and drag its red width line. Its character (what
ShumiTranslator writes for that code) and width are edited under it.

The tab shows the .tdw; the textures the PC game draws (low and high resolution) and a character
table (.txt) are attached with the header's Import complementary, and the header's Save writes all of
them (see FontPane).
"""
import os
import pathlib

from PIL import Image
from PyQt6.QtCore import QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QKeySequence, QPainter, QPen
from PyQt6.QtWidgets import (QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                             QSpinBox, QVBoxLayout, QWidget)

from Common.undo import UndoStack

from FF8GameData.font.hiresfont import HiresFont
from FF8GameData.font.lowresfont import LowresFont
from FF8GameData.font.tdwfile import COLORS, LETTER_SIZE, MAX_WIDTH, TABLE_SIZE, WHITE, TdwFile
from FF8GameData.gamedata import FileType

GRID_COLUMNS = 16
GRID_ROWS = TABLE_SIZE // GRID_COLUMNS
GRID_ZOOM = 2
GRID_CELL = LETTER_SIZE * GRID_ZOOM + 4  # glyph + 1 px border + 1 px padding each side
PIXEL_SIZE = 20
HIRES_CELL = 24
HIRES_PIXEL_SIZE = 10


def _qimage(image):
    """A QImage that owns its pixels: one made over a Python buffer (or PIL's ImageQt) shows garbage or
    nothing once that buffer is freed, and FontGrid keeps its images. copy() runs while `data` lives."""
    image = image.convert("RGBA")
    data = image.tobytes("raw", "RGBA")
    return QImage(data, image.width, image.height, 4 * image.width, QImage.Format.Format_RGBA8888).copy()


def _qcolor(rgba):
    return QColor(*rgba)


def _navigation(widget):
    """Choosing what to look at is not an edit of the file (see Common.dirtytracking)."""
    widget.setProperty("read_only_preview", True)
    return widget


class FontGrid(QWidget):
    """One table's 224 glyphs, 16 per row (the hi-res ones when they are attached). Click or arrow
    keys pick a glyph."""

    letter_clicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tdw = None      # the glyph count, and the 12 px picture when no texture is attached
        self.lowres = None   # the 12 px textures, when attached
        self.hires = None
        self.table = 0
        self.color = WHITE
        self.letter = 0
        self._images = {}  # (glyph, colour) -> QImage: drawing 224 glyphs from the textures is slow
        self.setFixedSize(GRID_COLUMNS * GRID_CELL + 1, GRID_ROWS * GRID_CELL + 1)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def invalidate(self, glyph=None):
        """Draw that glyph (or all of them) again from its pixels: after an edit or a new texture."""
        if glyph is None:
            self._images.clear()
        else:
            for key in [key for key in self._images if key[0] == glyph]:
                del self._images[key]
        self.update()

    def _image(self, glyph):
        key = (glyph, self.color)
        if key not in self._images:
            if self.hires is not None and self.hires.has_letter(glyph):
                image = self.hires.letter_image(glyph, self.color)  # 24 px: the cell's size
            else:
                low = self.lowres if self.lowres is not None and self.lowres.has_letter(glyph) else self.tdw
                image = low.letter_image(glyph, self.color).resize(
                    (LETTER_SIZE * GRID_ZOOM, LETTER_SIZE * GRID_ZOOM), Image.Resampling.NEAREST)
            self._images[key] = _qimage(image)
        return self._images[key]

    def cell_rect(self, letter):
        return QRect((letter % GRID_COLUMNS) * GRID_CELL, (letter // GRID_COLUMNS) * GRID_CELL, GRID_CELL, GRID_CELL)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        painter.setPen(QColor(90, 90, 90))
        for i in range(GRID_COLUMNS + 1):
            painter.drawLine(i * GRID_CELL, 0, i * GRID_CELL, self.height())
        for i in range(GRID_ROWS + 1):
            painter.drawLine(0, i * GRID_CELL, self.width(), i * GRID_CELL)
        if self.tdw is not None:
            for letter in range(self.tdw.char_count(self.table)):
                glyph = self.tdw.glyph_id(self.table, letter)
                painter.drawImage(self.cell_rect(letter).topLeft() + QPoint(2, 2), self._image(glyph))
        painter.setPen(QPen(QColor(255, 60, 60) if self.hasFocus() else QColor(255, 140, 140), 2))
        painter.drawRect(self.cell_rect(self.letter).adjusted(1, 1, -1, -1))

    def set_letter(self, letter):
        if self.tdw is not None and 0 <= letter < self.tdw.char_count(self.table):
            self.letter = letter
            self.update()
            self.letter_clicked.emit(letter)

    def mousePressEvent(self, event):
        position = event.position().toPoint()
        self.set_letter((position.y() // GRID_CELL) * GRID_COLUMNS + position.x() // GRID_CELL)
        self.setFocus()

    def keyPressEvent(self, event):
        step = {Qt.Key.Key_Left: -1, Qt.Key.Key_Right: 1,
                Qt.Key.Key_Up: -GRID_COLUMNS, Qt.Key.Key_Down: GRID_COLUMNS}.get(event.key())
        if step is None:
            super().keyPressEvent(event)
        else:
            self.set_letter(self.letter + step)


class LetterEditor(QWidget):
    """The selected glyph, zoomed: the 12 px one (low-res textures) or the 24 px one (hi-res textures).
    Left click / drag paints the chosen level, right click picks the level of a pixel. The red line is
    the glyph's width (from the tdw, doubled at 24 px), dragged left or right to change it. With
    read_only_pixels (the tdw's own picture shown while no texture is attached), only the width moves."""

    pixels_edited = pyqtSignal()
    width_edited = pyqtSignal(int)
    level_picked = pyqtSignal(int)
    edit_finished = pyqtSignal()   # the mouse is released after painting or moving the width: one undo step

    def __init__(self, size=LETTER_SIZE, pixel_size=PIXEL_SIZE, parent=None):
        super().__init__(parent)
        self.source = None    # LowresFont, HiresFont or TdwFile: letter_image / has_letter / level / set_level
        self.tdw = None       # where the width is
        self.read_only_pixels = False
        self.size = size
        self.pixel_size = pixel_size
        self.width_scale = size // LETTER_SIZE
        self.glyph = 0
        self.table = 0
        self.letter = 0
        self.color = WHITE
        self.level = 1
        self.read_only_width = False
        self._dragging_width = False
        self._painting = False
        self._edited = False
        self.setFixedSize((MAX_WIDTH + 1) * self.width_scale * pixel_size, size * pixel_size)
        self.setMouseTracking(True)

    def show_letter(self, source, tdw, table, letter, color):
        self.source, self.tdw, self.table, self.letter, self.color = source, tdw, table, letter, color
        self.glyph = tdw.glyph_id(table, letter)
        self.update()

    def _width_x(self):
        return self.tdw.char_width(self.table, self.letter) * self.width_scale * self.pixel_size

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        if self.source is None:
            return
        side = self.size * self.pixel_size
        image = self.source.letter_image(self.glyph, self.color).resize((side, side), Image.Resampling.NEAREST)
        painter.drawImage(0, 0, _qimage(image))
        painter.setPen(QColor(60, 60, 60))
        for i in range(1, self.size + 1):
            painter.drawLine(i * self.pixel_size, 0, i * self.pixel_size, side)
            painter.drawLine(0, i * self.pixel_size, side, i * self.pixel_size)
        painter.setPen(QPen(QColor(255, 0, 0), 2))
        painter.drawLine(self._width_x(), 0, self._width_x(), self.height())

    def _near_width_line(self, x):
        return not self.read_only_width and abs(x - self._width_x()) <= 3

    def _pixel(self, position):
        x, y = position.x() // self.pixel_size, position.y() // self.pixel_size
        if 0 <= x < self.size and 0 <= y < self.size and self.source.has_letter(self.glyph):
            return x, y
        return None

    def _paint_at(self, position):
        pixel = None if self.read_only_pixels else self._pixel(position)
        if pixel is not None and self.source.level(self.glyph, *pixel) != self.level:
            self.source.set_level(self.glyph, *pixel, self.level)
            self._edited = True
            self.update()
            self.pixels_edited.emit()

    def mousePressEvent(self, event):
        if self.source is None:
            return
        position = event.position().toPoint()
        if event.button() == Qt.MouseButton.RightButton:
            pixel = self._pixel(position)
            if pixel is not None:
                self.level_picked.emit(self.source.level(self.glyph, *pixel))
        elif self._near_width_line(position.x()):
            self._dragging_width = True
        else:
            self._painting = True
            self._paint_at(position)

    def mouseMoveEvent(self, event):
        if self.source is None:
            return
        position = event.position().toPoint()
        if self._dragging_width:
            width = max(0, min(MAX_WIDTH, round(position.x() / (self.pixel_size * self.width_scale))))
            if width != self.tdw.char_width(self.table, self.letter):
                self._edited = True
                self.width_edited.emit(width)
        elif self._painting:
            self._paint_at(position)
        else:
            self.setCursor(Qt.CursorShape.SplitHCursor if self._near_width_line(position.x())
                           else Qt.CursorShape.PointingHandCursor if position.x() < self.size * self.pixel_size
                           else Qt.CursorShape.ArrowCursor)

    @property
    def dragging(self):
        return self._dragging_width or self._painting

    def mouseReleaseEvent(self, _event):
        self._dragging_width = self._painting = False
        if self._edited:
            self._edited = False
            self.edit_finished.emit()


class _TabUndoLineEdit(QLineEdit):
    """A line edit without an undo of its own: Ctrl+Z / Ctrl+Y go to the font tab's undo, which covers
    the pixels, the widths and the characters together (the main window asks isUndoAvailable whether a
    focused field undoes by itself)."""

    def isUndoAvailable(self):
        return False

    def isRedoAvailable(self):
        return False

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Undo) or event.matches(QKeySequence.StandardKey.Redo):
            event.ignore()
            return
        super().keyPressEvent(event)


def _self_marked(widget):
    """A field whose edits the font tab marks unsaved itself (undo aware), not the generic tracker."""
    widget.setProperty("read_only_preview", True)
    return widget


class LevelPalette(QWidget):
    """The levels a glyph pixel can take, as their colours: 4 (Japanese), 16 (Latin 12 px) or a sample
    of the 255 shades of the Latin hi-res font. A level picked from a pixel that is not in the list
    shows as one more swatch at the end."""

    level_chosen = pyqtSignal(int)
    CELL = 22

    def __init__(self, parent=None):
        super().__init__(parent)
        self.values, self.colors = [], []
        self._base = 0
        self.index = 1
        self.setFixedHeight(self.CELL + 4)

    @property
    def level(self):
        return self.values[self.index] if self.values else 0

    def set_levels(self, values, colors):
        current = self.level if self.values else None  # the first time: the first visible level
        self.values, self.colors = list(values), list(colors)
        self._base = len(self.values)
        self.index = self.values.index(current) if current in self.values else min(1, len(self.values) - 1)
        self._resize()

    def select_value(self, value, color):
        if value not in self.values[:self._base]:
            del self.values[self._base:], self.colors[self._base:]
            self.values.append(value)
            self.colors.append(color)
        self.index = self.values.index(value)
        self._resize()
        self.level_chosen.emit(value)

    def _resize(self):
        self.setFixedWidth(len(self.values) * (self.CELL + 2) + 2)
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        for i, rgba in enumerate(self.colors):
            x = 2 + i * (self.CELL + 2)
            if i == self.index:
                painter.fillRect(x - 2, 0, self.CELL + 4, self.CELL + 4, QColor(255, 0, 0))
            painter.fillRect(x, 2, self.CELL, self.CELL, _qcolor(rgba[:3] + (255,)) if rgba[3] else QColor(0, 0, 0))
            if not rgba[3]:  # transparent level: show it as such
                painter.setPen(QColor(120, 120, 120))
                painter.drawLine(x, 2 + self.CELL, x + self.CELL, 2)

    def mousePressEvent(self, event):
        index = int(event.position().x()) // (self.CELL + 2)
        if 0 <= index < len(self.values):
            self.index = index
            self.update()
            self.level_chosen.emit(self.values[index])


class FontPane(QWidget):
    """One opened .tdw, one tab (same interface as ShumiFilePane for the ShumiTranslator shell).

    The .tdw is the glyph widths: the one thing the PC game reads from it. The glyph pictures the PC
    game draws are textures, attached with the header's Import complementary while the tab is shown:

    - low resolution (12 px), menu/sysfnt.TEX (Japanese: also sysfnt_even/_odd.TEX): edited in the 12 px
      zoom (attach_texture). Until one is attached, that zoom shows the tdw's own picture (from the
      PlayStation version, the same glyphs) read-only. On Save the glyphs edited in the texture are also
      copied into the tdw's picture, so tools showing it (Deling) agree.
    - high resolution (24 px), menu/hires/sysfld00+01 (Japanese: sysevn00-03 + sysodd00-03): edited in
      the 24 px zoom (attach_hires).
    - the characters: the Text field edits the character table chosen in ShumiTranslator (Latin,
      Japanese, Vietnamese, or a custom .txt), in memory: a changed character is used by the text tabs at
      once. It is an unsaved change: Save asks where to write the table (.txt), which the Characters list
      loads again later ("Custom file..."). The table's own file is never written over unasked.
    """

    supports_compress = False
    supports_csv = False

    def __init__(self, game_data, file_loaded, parent=None):
        super().__init__(parent)
        self.game_data = game_data
        self.file_type = FileType.FONT
        self.file_loaded = file_loaded
        self.file_mngrphd_loaded = ""
        self.tdw = TdwFile.read(file_loaded)
        # A field's .tdw holds the glyphs of its {JpNNN} codes (0x1c NN): no character to name, and
        # Deling leaves their widths alone too.
        self.additional = not pathlib.Path(file_loaded).name.lower().startswith("sysfnt")
        self.lowres = LowresFont(self.japanese)
        self._edited_low = set()  # glyphs painted in the low-res texture: copied into the tdw's picture on Save
        self.hires = None

        self.grid = FontGrid()
        self.grid.tdw = self.tdw
        self.editor = LetterEditor()
        self.editor.read_only_width = self.additional
        self.editor.read_only_pixels = True  # until a low-res texture is attached
        self.levels = LevelPalette()
        self.hires_editor = LetterEditor(size=HIRES_CELL, pixel_size=HIRES_PIXEL_SIZE)
        self.hires_editor.read_only_width = self.additional
        self.hires_levels = LevelPalette()
        self.hires_box = QWidget()
        hires_layout = QVBoxLayout(self.hires_box)
        hires_layout.setContentsMargins(0, 0, 0, 0)
        hires_layout.addWidget(QLabel("<b>High resolution</b> (24 px)"))
        hires_layout.addWidget(self.hires_editor)
        hires_layout.addWidget(self.hires_levels)
        hires_layout.addStretch(1)
        self.hires_box.hide()

        self.color_box = _navigation(QComboBox())
        self.color_box.addItems(COLORS)
        self.color_box.setCurrentIndex(WHITE)
        self.color_box.setToolTip("Text colour the glyphs are shown in")
        self.table_box = _navigation(QComboBox())
        self.table_box.addItems([f"Table {i + 1}" + (f" (lead byte {0x18 + i:02x})" if i else "")
                                 for i in range(self.tdw.table_count)])
        self.table_box.setEnabled(self.tdw.table_count > 1)

        self.code_label = QLabel()
        self.text_edit = _self_marked(_TabUndoLineEdit())  # edits the character table
        self.text_edit.setReadOnly(self.additional)
        self.text_edit.setToolTip("The character ShumiTranslator reads and writes for this code")
        self.width_spin = _self_marked(QSpinBox())
        self.width_spin.setLineEdit(_TabUndoLineEdit())
        self.width_spin.setRange(0, MAX_WIDTH)
        self.width_spin.setReadOnly(self.additional)
        self.width_spin.setToolTip("Glyph width in pixels (12 px scale, doubled in high resolution): "
                                   "how far the next character starts")
        info = QLabel("Click a glyph, paint it with the levels under it (right click a pixel to pick its "
                      "level), drag its red line to change its width. Ctrl+Z / Ctrl+Y undo and redo.")
        info.setWordWrap(True)
        self.files_label = QLabel()
        self.files_label.setWordWrap(True)
        self.files_label.setTextFormat(Qt.TextFormat.RichText)

        left = QVBoxLayout()
        left.addWidget(self.grid)
        selectors = QHBoxLayout()
        selectors.addWidget(self.color_box)
        selectors.addWidget(self.table_box)
        selectors.addStretch(1)
        left.addLayout(selectors)
        left.addStretch(1)

        low_box = QVBoxLayout()
        low_box.addWidget(QLabel("<b>Low resolution</b> (12 px)"))
        low_box.addWidget(self.editor)
        low_box.addWidget(self.levels)
        low_box.addStretch(1)
        editors = QHBoxLayout()
        editors.addLayout(low_box)
        editors.addWidget(self.hires_box)
        editors.addStretch(1)

        fields = QGridLayout()
        fields.addWidget(QLabel("Code:"), 0, 0)
        fields.addWidget(self.code_label, 0, 1, 1, 3)
        fields.addWidget(QLabel("Text:"), 1, 0)
        fields.addWidget(self.text_edit, 1, 1)
        fields.addWidget(QLabel("Width:"), 1, 2)
        fields.addWidget(self.width_spin, 1, 3)
        fields.setColumnStretch(4, 1)

        right = QVBoxLayout()
        right.addLayout(editors)
        right.addLayout(fields)
        right.addStretch(1)

        body = QHBoxLayout()
        body.addLayout(left)
        body.addLayout(right, 1)
        outer = QVBoxLayout(self)
        outer.addWidget(self.files_label)
        outer.addWidget(info)
        outer.addLayout(body, 1)

        self.grid.letter_clicked.connect(self.select_letter)
        self.color_box.currentIndexChanged.connect(self.__set_color)
        self.table_box.currentIndexChanged.connect(self.__set_table)
        for editor, levels in ((self.editor, self.levels), (self.hires_editor, self.hires_levels)):
            levels.level_chosen.connect(lambda value, e=editor: setattr(e, "level", value))
            editor.level_picked.connect(lambda value, e=editor, l=levels: l.select_value(
                value, e.source.level_color(self.color, e.glyph, value)))
            editor.pixels_edited.connect(self.__pixels_edited)
            editor.width_edited.connect(self.width_spin.setValue)
            editor.edit_finished.connect(self.__commit)
        self.editor.pixels_edited.connect(lambda: self._edited_low.add(self.editor.glyph))
        self.width_spin.valueChanged.connect(self.__width_changed)
        self.text_edit.textEdited.connect(self.__text_edited)
        self.select_letter(0)
        self.__update_files_label()
        self.__new_history()

    # -- shell interface ---------------------------------------------------------------------------
    @property
    def display_name(self):
        return pathlib.Path(self.file_loaded).name

    @property
    def japanese(self):
        return self.tdw.optimized

    def save(self, parent=None):
        """Write the .tdw (widths, plus the glyphs edited in the low-res texture into its own picture),
        the attached textures and, when characters were changed, the character table to a .txt asked for
        (cancelling that leaves the characters unsaved: unsaved_after_save)."""
        written = [self.display_name]
        for glyph in sorted(self._edited_low):
            if self.tdw.has_letter(glyph) and self.lowres.has_letter(glyph):
                self.tdw.set_levels(glyph, self.lowres.levels(glyph))
        self._edited_low.clear()
        self.tdw.write(self.file_loaded)
        if self.lowres.textures:
            self.lowres.write()
            written.extend(pathlib.Path(path).name for path in self.lowres.paths)
        if self.hires is not None:
            self.hires.write()
            written.extend(pathlib.Path(path).name for path in self.hires.paths)
        if self.game_data.character_table_modified:
            path = QFileDialog.getSaveFileName(
                parent or self, "Characters were changed: where to save the character table (.txt)?",
                self.__table_save_path(), "Character table (*.txt)")[0]
            if path:
                self.game_data.export_character_table(path)
                self.game_data.character_table_modified = False
                self._table_saved_to = path
                written.append(pathlib.Path(path).name)
        saved = self.__capture()
        if self.game_data.character_table_modified:
            saved["table"] = self._saved["table"]  # no .txt chosen: the characters stay unsaved
        self._saved = saved
        self.__update_files_label()
        message = "Saved: " + ", ".join(f"<b>{name}</b>" for name in written)
        if self.game_data.character_table_modified:
            message += "<br>The changed characters are <b>not saved</b> (no .txt chosen)."
        return message

    def unsaved_after_save(self):
        """Whether a Save left something unsaved: the changed characters, when no .txt was chosen."""
        return self.game_data.character_table_modified

    def __table_save_path(self):
        """Where the character table is offered to be saved: where it was saved last, the custom file in
        use, or a new file next to the font (never over a built-in table by default)."""
        if getattr(self, "_table_saved_to", ""):
            return self._table_saved_to
        if self.game_data.character_table == "custom":
            return self.game_data.character_table_path
        return os.path.join(os.path.dirname(self.file_loaded),
                            "sysfnt_jp_custom.txt" if self.game_data.jp_encoding else "sysfnt_custom.txt")

    def csv_default_name(self):
        return pathlib.Path(self.file_loaded).stem + ".csv"

    def _mark_dirty(self):
        dirty_state = getattr(self, "dirty_state", None)
        if dirty_state is not None:
            dirty_state.mark()

    # -- complementary files -----------------------------------------------------------------------
    def attach_texture(self, path):
        """A low-resolution font texture (menu/sysfnt.TEX, or Japanese sysfnt_even/_odd.TEX, which come
        as a pair): the 12 px glyphs the PC game draws, edited in the 12 px zoom from now on."""
        self.lowres.attach(path)
        self.grid.lowres = self.lowres
        self.grid.invalidate()
        self.editor.read_only_pixels = False
        self.select_letter(self.grid.letter)
        self.__update_files_label()
        self.__new_history()

    def attach_hires(self, path):
        """The high-resolution font textures (any one of them: the others are found next to it)."""
        hires = HiresFont.from_path(path)
        if hires.japanese != self.japanese:
            raise ValueError("these hi-res textures are " + ("Japanese" if hires.japanese else "Latin")
                             + ", this font is not")
        self.hires = hires
        self.grid.hires = hires
        self.grid.invalidate()
        self.hires_box.show()
        self.select_letter(self.grid.letter)
        self.__update_files_label()
        self.__new_history()

    def character_table_changed(self):
        """Another character table was chosen in ShumiTranslator: show its characters."""
        self.select_letter(self.grid.letter)
        self.__update_files_label()
        self.__new_history()

    def __update_files_label(self):
        lines = [f"<b>{self.display_name}</b>: the glyph widths."]
        if self.lowres.textures:
            names = ", ".join(pathlib.Path(path).name for path in self.lowres.paths)
            lines.append(f"Low resolution glyphs (12 px): <b>{names}</b>.")
        else:
            lines.append("Low resolution glyphs (12 px, <b>menu/sysfnt.TEX</b>): not loaded, the 12 px zoom shows "
                         "the tdw's own picture, read-only.")
        if self.hires is not None:
            names = ", ".join(pathlib.Path(path).name for path in self.hires.paths)
            lines.append(f"High resolution glyphs (24 px, what FF8 Steam shows): <b>{names}</b>.")
        else:
            lines.append("High resolution glyphs (24 px, <b>menu/hires/"
                         + ("sysevn/sysodd" if self.japanese else "sysfld00/01")
                         + "</b>, what FF8 Steam shows): not loaded.")
        if self.additional:
            lines.append("Field font: its glyphs are the {JpNNN} codes of that field, no character table.")
        else:
            name = self.game_data.character_table_name
            file_name = os.path.basename(self.game_data.character_table_path)
            japanese = self.game_data.jp_encoding
            edited = " (changed here)" if self.game_data.character_table_modified else ""
            lines.append(f"Characters: the <b>{name}</b> table ({file_name}){edited}, chosen in the bar above. A "
                         "character you change is used by the text tabs at once; Save asks where to write the "
                         "table (.txt).")
            if japanese != self.japanese:
                lines.append("<b>This font is " + ("Japanese" if self.japanese else "not Japanese")
                             + f", the {name} table is " + ("" if japanese else "not ") + "Japanese:</b> choose "
                             "the matching table to see the right characters.")
        lines.append("Add the missing files with <i>Import complementary</i>.")
        self.files_label.setText("<br>".join(lines))

    # -- selection ---------------------------------------------------------------------------------
    @property
    def table(self):
        return max(0, self.table_box.currentIndex())

    @property
    def color(self):
        return self.color_box.currentIndex()

    def code_of(self, letter):
        if self.additional:
            return bytes([0x1c, 0x20 + letter])
        return bytes([0x18 + self.table, 0x20 + letter]) if self.table else bytes([0x20 + letter])

    @property
    def low_source(self):
        """The 12 px glyphs shown: the low-res texture once attached (and holding that glyph), else the
        tdw's own picture."""
        glyph = self.editor.glyph
        return self.lowres if self.lowres.textures and self.lowres.has_letter(glyph) else self.tdw

    def select_letter(self, letter):
        letter = max(0, min(letter, self.tdw.char_count(self.table) - 1))
        self.grid.letter = letter
        self.grid.update()
        self.editor.glyph = self.tdw.glyph_id(self.table, letter)
        low = self.low_source
        self.editor.show_letter(low, self.tdw, self.table, letter, self.color)
        self.editor.read_only_pixels = low is self.tdw
        glyph = self.editor.glyph
        self.levels.set_levels(low.level_values, [low.level_color(self.color, glyph, v) for v in low.level_values])
        self.editor.level = self.levels.level
        if self.hires is not None:
            self.hires_editor.show_letter(self.hires, self.tdw, self.table, letter, self.color)
            self.hires_levels.set_levels(self.hires.level_values, self.hires.level_colors(self.color, glyph))
            self.hires_editor.level = self.hires_levels.level
        self.code_label.setText(self.code_of(letter).hex(" ")
                                + ("" if low.has_letter(glyph) else "  (no 12 px image for it)"))
        text = f"{{Jp{letter:03d}}}" if self.additional else self.game_data.table_char(self.table, letter)
        self.text_edit.setText(text)
        self.text_edit.setReadOnly(self.additional or (self.table > 0 and not self.game_data.jp_encoding))
        self.width_spin.blockSignals(True)
        self.width_spin.setValue(self.tdw.char_width(self.table, letter))
        self.width_spin.blockSignals(False)

    def __set_color(self, _index):
        self.grid.color = self.color
        self.select_letter(self.grid.letter)

    def __set_table(self, _index):
        self.grid.table = self.table
        self.select_letter(0)

    # -- edits and undo ----------------------------------------------------------------------------
    def __capture(self):
        """Everything this tab edits: the widths, the characters, the pixels of each attached texture."""
        state = {"widths": self.tdw.width_data}
        if not self.additional:
            state["table"] = self.game_data.character_table_values()
        for path, tex, _kind in self.lowres.textures:
            state["low", path] = bytes(tex.pixels)
        if self.hires is not None:
            for tiles in self.hires.pages.values():
                for path, tex in tiles:
                    state["high", path] = bytes(tex.pixels)
        return state

    def __restore(self, state, tag=None):
        self.tdw.width_data = state["widths"]
        if "table" in state:
            self.game_data.set_character_table_values(state["table"], self.game_data.character_table_modified)
        for path, tex, _kind in self.lowres.textures:
            tex.pixels[:] = state["low", path]
        if self.hires is not None:
            for tiles in self.hires.pages.values():
                for path, tex in tiles:
                    tex.pixels[:] = state["high", path]
        self.grid.invalidate()
        if tag is not None and tag[0] != self.table:
            self.table_box.setCurrentIndex(tag[0])
        self.select_letter(self.grid.letter if tag is None else tag[1])  # where the undone edit was
        self.__sync_unsaved()

    def __new_history(self):
        """Start the undo history from what the tab holds now (a file was attached, another character
        table chosen: older steps don't describe it). The * still compares with what is on disk."""
        state = self.__capture()
        saved = dict(getattr(self, "_saved", state))
        for key, value in state.items():
            if key not in saved or (key == "table" and not self.game_data.character_table_modified):
                saved[key] = value  # just read from its file
        self._saved = saved
        self._undo = UndoStack(self.__capture, self.__restore)

    def __commit(self):
        if self.editor.dragging or self.hires_editor.dragging:
            return  # the step is taken when the mouse is released
        self._undo.commit((self.table, self.grid.letter))
        self.__sync_unsaved()

    def __sync_unsaved(self):
        """The * and "changed characters" follow what differs from the saved files, so undoing back to
        them clears it."""
        state = self.__capture()
        if not self.additional:
            modified = state["table"] != self._saved["table"]
            if modified != self.game_data.character_table_modified:
                self.game_data.character_table_modified = modified
                self.__update_files_label()
        if state == self._saved:
            self._edited_low.clear()
        dirty_state = getattr(self, "dirty_state", None)
        if dirty_state is not None:
            if state == self._saved:
                dirty_state.clear()
            else:
                dirty_state.mark()

    def undo(self):
        """Ctrl+Z (the main window routes it to ShumiTranslator, which hands it to the tab shown)."""
        return self._undo.undo()

    def redo(self):
        return self._undo.redo()

    def __pixels_edited(self):
        self.grid.invalidate(self.editor.glyph)
        self._mark_dirty()  # the undo step is taken on release (edit_finished)

    def __width_changed(self, width):
        if self.additional or width == self.tdw.char_width(self.table, self.grid.letter):
            return
        self.tdw.set_char_width(self.table, self.grid.letter, width)
        self.editor.update()
        self.hires_editor.update()
        self.__commit()

    def __text_edited(self, text):
        modified = self.game_data.character_table_modified
        self.game_data.set_table_char(self.table, self.grid.letter, text)
        self.game_data.character_table_modified = modified  # __sync_unsaved compares with the saved table
        self.__commit()  # unsaved: Save asks where to write the .txt
