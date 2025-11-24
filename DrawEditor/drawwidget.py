from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QTableWidget, QHeaderView, QTableWidgetItem, QCheckBox, QWidget, QHBoxLayout

from DrawEditor.draw import Draw
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

    def __init__(self, game_data:GameData, draw_list: [Draw]=(), parent=None):
        super().__init__(256, 5, parent)
        self._draw = draw_list
        self.game_data = game_data

        self.setup_table()

    def set_draw(self, draw_list: [Draw]):
        self._draw = draw_list
        self._populate_table()

    def get_draw(self) -> [Draw]:
        return self._draw



    def setup_table(self):
        # Create table with 256 rows and 4 columns

        self.setHorizontalHeaderLabels(["Draw ID", "Magic", "HighYield", "Refill", "Default Location"])

        # Set column widths
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.verticalHeader().setVisible(False)
        # Populate the table
        self._populate_table()


    def _populate_table(self):
        self.setEnabled(False)
        magic_options = [x['name'] for x in self.game_data.magic_data_json['magic']]

        for row, draw in enumerate(self._draw):
            # ID column - QLabel equivalent
            id_item = QTableWidgetItem(f"{draw.get_id()}")
            id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)  # Read-only
            id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setItem(row, 0, id_item)

            # Magic column - QComboBox
            combo = QComboBox()
            combo.addItems(magic_options)
            combo.setCurrentIndex(draw.magic_index)
            combo.currentIndexChanged.connect(lambda state, r=row: self._magic_changed(state, r))
            self.setCellWidget(row, 1, combo)

            # HighYield column - QCheckBox

            high_yield_check = CenteredCheckBox()
            high_yield_check.checkbox.stateChanged.connect( lambda state, r=row: self._high_yield_changed(state, r))
            if draw.high_yield:
                high_yield_check.setChecked(True)
            else:
                high_yield_check.setChecked(False)
            self.setCellWidget(row, 2, high_yield_check)

            refill_check = CenteredCheckBox()
            refill_check.checkbox.stateChanged.connect(lambda state, r=row: self._refill_changed(state, r))
            if draw.refill:
                refill_check.setChecked(True)
            else:
                refill_check.setChecked(False)
            self.setCellWidget(row, 3, refill_check)

            # Location column - QLabel equivalent
            location_item = QTableWidgetItem(f"{draw.get_location()}")
            location_item.setFlags(location_item.flags() & ~Qt.ItemFlag.ItemIsEditable)  # Read-only
            location_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft)
            self.setItem(row, 4, location_item)
        self.setEnabled(True)


    def _magic_changed(self, index, row):
        self._draw[row].magic_index = index
        #print(f"Row {row}: magic_index = {index}")

    def _high_yield_changed(self, state, row):
        is_checked = (state == Qt.CheckState.Checked.value)
        self._draw[row].high_yield = is_checked
        #print(f"Row {row}: high_yield = {is_checked}")

    def _refill_changed(self, state, row):
        is_checked = (state == Qt.CheckState.Checked.value)
        self._draw[row].refill = is_checked
        #print(f"Row {row}: refill = {is_checked}")