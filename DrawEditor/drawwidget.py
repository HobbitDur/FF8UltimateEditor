from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QTableWidget, QHeaderView, QTableWidgetItem, QCheckBox

from DrawEditor.draw import Draw
from FF8GameData.gamedata import GameData


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
            self.setCellWidget(row, 1, combo)

            # HighYield column - QCheckBox
            high_yield_check = QCheckBox()
            high_yield_check.setStyleSheet("margin-left:50%; margin-right:50%;")
            if draw.high_yield:
                high_yield_check.setChecked(True)
            else:
                high_yield_check.setChecked(False)
            self.setCellWidget(row, 2, high_yield_check)

            # Refill column - QCheckBox
            refill_check = QCheckBox()
            refill_check.setStyleSheet("margin-left:50%; margin-right:50%;")
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