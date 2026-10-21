from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget


# Item data role holding more text a row matches, beyond its label (Fujin: the spells, items...
# that play an effect, so searching "Potion" finds its effect)
SEARCH_TEXT_ROLE = Qt.ItemDataRole.UserRole + 50


class ListSearchBar(QWidget):
    """A Ctrl+F search bar filtering the QListWidget it is attached to.

    Put it right above the list it searches:

        self.item_search = ListSearchBar(self.item_list)
        left_layout.addWidget(self.item_search)
        left_layout.addWidget(self.item_list)

    or let it build the column for a list that is added straight to a layout:

        main_editor_layout.addWidget(ListSearchBar.wrap(self.item_list))

    Rows are hidden, never removed, so a row index still means what it meant to the tool
    (most tools map the current row onto their own entry list). Shortcuts: Ctrl+F focuses
    the search, Enter goes to the list to browse the matches, Escape clears the search."""

    def __init__(self, list_widget, match_index=False, placeholder="Search (Ctrl+F)", parent=None):
        QWidget.__init__(self, parent)
        self.list_widget = list_widget
        self.match_index = match_index  # A search that is only digits also matches the row number
        self.column = None  # Set by wrap() when it builds the search bar + list column
        self._has_hidden_rows = False  # Lets a refill of an unfiltered list skip the whole scan
        self._updating_selection = False

        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText(placeholder)
        self.search_field.setClearButtonEnabled(True)
        self.search_field.setToolTip("Filter the list" + (" by text or by index" if match_index else "") +
                                     ".\nCtrl+F: focus the search  -  Enter: go to the list  -  Esc: clear")
        self.search_field.textChanged.connect(self.search)
        self.search_field.returnPressed.connect(self.focus_list)

        self.result_label = QLabel("")
        self.result_label.setStyleSheet("color: gray;")

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.search_field)
        layout.addWidget(self.result_label)
        self.setLayout(layout)

        self.search_shortcut = QShortcut(QKeySequence.StandardKey.Find, self)
        self.search_shortcut.activated.connect(self.focus_search_field)
        self.clear_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self.search_field)
        self.clear_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        self.clear_shortcut.activated.connect(self.clear_search)

        # The tool refills its list on import: filter the new rows and keep the selection visible
        self.list_widget.model().rowsInserted.connect(self.search)
        self.list_widget.currentRowChanged.connect(self._on_current_row_changed)

    @classmethod
    def wrap(cls, list_widget, match_index=False, placeholder="Search (Ctrl+F)"):
        """Build a search bar plus the column stacking it above `list_widget`, and return the bar.

        For lists that are added straight to a layout, so the caller only swaps
        `layout.addWidget(self.item_list)` for `layout.addWidget(self.item_search.column)`."""
        search_bar = cls(list_widget, match_index=match_index, placeholder=placeholder)

        column = QWidget()
        column_layout = QVBoxLayout()
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.addWidget(search_bar)
        column_layout.addWidget(list_widget)
        column.setLayout(column_layout)
        # A fixed width set on the list is meant for the whole column
        if list_widget.minimumWidth() == list_widget.maximumWidth():
            column.setFixedWidth(list_widget.maximumWidth())
        search_bar.column = column
        return search_bar

    def search(self):
        """Hide every row that doesn't match the search."""
        search_text = self.search_field.text().strip().lower()
        row_count = self.list_widget.count()
        if not search_text and not self._has_hidden_rows:
            self.result_label.setText("")  # Nothing to filter, a tool refilling its list lands here
            return
        self._has_hidden_rows = bool(search_text)
        match_count = 0
        for row in range(row_count):
            item = self.list_widget.item(row)
            matched = not search_text or self._matches(row, item, search_text)
            item.setHidden(not matched)
            match_count += matched

        self.result_label.setText("" if not search_text else f"{match_count}/{row_count}")
        self._keep_selection_visible()

    def clear_search(self):
        """Escape in the search field: drop the filter and go back to the list."""
        self.search_field.clear()
        self.list_widget.setFocus()

    def focus_search_field(self):
        """Ctrl+F: put the caret in the search field, ready to type over the current search."""
        self.search_field.setFocus()
        self.search_field.selectAll()

    def focus_list(self):
        """Enter in the search field: go to the list so the arrow keys browse the matches."""
        if self.list_widget.currentRow() < 0:
            self.select_first_match()
        else:
            self._keep_selection_visible()
        self.list_widget.setFocus()

    def select_first_match(self):
        """Select the first row the search matches (the first row when nothing is searched).

        Tools that repopulate their list call this instead of setCurrentRow(0), so an import
        done while a search is typed in lands on a row the user can actually see."""
        first_visible = self._first_visible_row()
        if first_visible >= 0:
            self.list_widget.setCurrentRow(first_visible)

    def _matches(self, row, item, search_text):
        if search_text in item.text().lower():
            return True
        extra = item.data(SEARCH_TEXT_ROLE)   # more words a row is found by (not shown in it)
        if extra and search_text in str(extra).lower():
            return True
        return self.match_index and search_text == str(row)

    def _keep_selection_visible(self):
        """Move a selection the filter just hid onto a visible row, else the tool would edit an
        entry the user can't see. An empty selection is left alone: the list is being refilled
        and its tool decides what to select."""
        if self._updating_selection:
            return
        if self.list_widget.selectionMode() != QListWidget.SelectionMode.SingleSelection:
            return  # A multi-selection list (spell pools and the like): never drop what is selected
        current_row = self.list_widget.currentRow()
        if current_row < 0 or not self.list_widget.item(current_row).isHidden():
            return
        first_visible = self._first_visible_row()
        if first_visible < 0:  # Nothing matches, leave the tool on the entry it was editing
            return
        self._updating_selection = True
        self.list_widget.setCurrentRow(first_visible)
        self._updating_selection = False

    def _on_current_row_changed(self):
        if self.search_field.text().strip():  # A row can be selected while hidden by a filter
            self._keep_selection_visible()

    def _first_visible_row(self):
        for row in range(self.list_widget.count()):
            if not self.list_widget.item(row).isHidden():
                return row
        return -1
