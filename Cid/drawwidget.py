from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QComboBox, QTableWidget, QHeaderView, QTableWidgetItem, QCheckBox, QWidget, QHBoxLayout, QSpinBox

from Cid.draw import Draw
from FF8GameData.gamedata import GameData


class CenteredCheckBox(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.checkbox = QCheckBox()
        layout = QHBoxLayout(self)
        layout.addWidget(self.checkbox)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(0, 0, 0, 0)

    def isChecked(self):
        return self.checkbox.isChecked()

    def setChecked(self, state):
        self.checkbox.setChecked(state)


class DrawWidget(QTableWidget):

    COLUMNS = ["Draw ID", "Magic", "HighYield", "Refill", "X", "Y", "Sub ID", "Default Location"]
    COL_X, COL_Y, COL_SUB = 4, 5, 6

    # Emits the draw-list index of the selected row (-1 when none is selected).
    selection_changed = pyqtSignal(int)
    # Emitted whenever an X/Y position changes (so the map can refresh).
    position_changed = pyqtSignal()

    def __init__(self, game_data: GameData, draw_list: [Draw] = (), parent=None):
        super().__init__(0, len(self.COLUMNS), parent)
        self._draw = list(draw_list)
        self.game_data = game_data
        self._loading = False
        self.setup_table()
        self.currentCellChanged.connect(self._on_current_cell_changed)

    def set_draw(self, draw_list: [Draw]):
        self._draw = list(draw_list)
        self._populate_table()

    def get_draw(self) -> [Draw]:
        return self._draw

    def setup_table(self):
        self.setHorizontalHeaderLabels(self.COLUMNS)
        for column in range(len(self.COLUMNS)):
            self.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
        self.verticalHeader().setVisible(False)
        self._populate_table()

    def _populate_table(self):
        self._loading = True
        self.setEnabled(False)
        self.setRowCount(len(self._draw))
        magic_options = [x['name'] for x in self.game_data.magic_data_json['magic']]

        for row, draw in enumerate(self._draw):
            id_item = QTableWidgetItem(f"{draw.get_id()}")
            id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setItem(row, 0, id_item)

            combo = QComboBox()
            combo.addItems(magic_options)
            combo.setCurrentIndex(draw.magic_index)
            combo.currentIndexChanged.connect(lambda state, r=row: self._magic_changed(state, r))
            self.setCellWidget(row, 1, combo)

            high_yield_check = CenteredCheckBox()
            high_yield_check.setChecked(draw.high_yield)
            high_yield_check.checkbox.stateChanged.connect(lambda state, r=row: self._high_yield_changed(state, r))
            self.setCellWidget(row, 2, high_yield_check)

            refill_check = CenteredCheckBox()
            refill_check.setChecked(draw.refill)
            refill_check.checkbox.stateChanged.connect(lambda state, r=row: self._refill_changed(state, r))
            self.setCellWidget(row, 3, refill_check)

            # Position columns - only world draw points have a wmset position.
            is_world = draw.is_world()
            self.setCellWidget(row, self.COL_X, self._make_byte_spinbox(draw.x, row, self._x_changed, is_world))
            self.setCellWidget(row, self.COL_Y, self._make_byte_spinbox(draw.y, row, self._y_changed, is_world))
            self.setCellWidget(row, self.COL_SUB, self._make_byte_spinbox(draw.sub_id, row, self._sub_id_changed, is_world))

            location_item = QTableWidgetItem(f"{draw.get_location()}")
            location_item.setFlags(location_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            location_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft)
            self.setItem(row, 7, location_item)
        self.setEnabled(True)
        self._loading = False

    @staticmethod
    def _make_byte_spinbox(value, row, callback, enabled):
        spin = QSpinBox()
        spin.setRange(0, 255)
        spin.setValue(value)
        spin.setEnabled(enabled)
        if not enabled:
            spin.setToolTip("Field draw points have no world-map position")
        spin.valueChanged.connect(lambda new_value, r=row: callback(new_value, r))
        return spin

    def set_row_position(self, row, x, y):
        """Apply a map-picked position to a row's model and spinboxes."""
        draw = self._draw[row]
        draw.x, draw.y = x, y
        for column, value in ((self.COL_X, x), (self.COL_Y, y)):
            spin = self.cellWidget(row, column)
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
        self.position_changed.emit()

    def _on_current_cell_changed(self, current_row, *_):
        if current_row < 0 or current_row >= len(self._draw):
            self.selection_changed.emit(-1)
        else:
            self.selection_changed.emit(current_row)

    def _magic_changed(self, index, row):
        self._draw[row].magic_index = index

    def _high_yield_changed(self, state, row):
        self._draw[row].high_yield = (state == Qt.CheckState.Checked.value)

    def _refill_changed(self, state, row):
        self._draw[row].refill = (state == Qt.CheckState.Checked.value)

    def _x_changed(self, value, row):
        self._draw[row].x = value
        if not self._loading:
            self.position_changed.emit()

    def _y_changed(self, value, row):
        self._draw[row].y = value
        if not self._loading:
            self.position_changed.emit()

    def _sub_id_changed(self, value, row):
        self._draw[row].sub_id = value
