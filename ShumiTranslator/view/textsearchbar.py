from PyQt6.QtCore import QTimer

from SmallWidget.listsearchbar import SearchBar


class TextSearchBar(SearchBar):
    """The Ctrl+F search of a ShumiTranslator file tab: only the lines the text appears in stay
    shown (in the text as read or as modified, ignoring case; a number also finds that line), and
    a section without any is hidden. Same field, count and shortcuts as the other tools' search.

    mngrp.bin alone has ~2600 lines, so the filter runs once the typing pauses, not on every key."""
    DELAY_MS = 250

    def __init__(self, section_widgets, tab_holder=None, parent=None):
        SearchBar.__init__(self, placeholder="Search the text (Ctrl+F)", parent=parent,
                           tooltip="Show only the lines this text appears in (as read or modified), "
                                   "or a line number")
        self._section_widgets = section_widgets  # the pane's list: filled after this bar is built
        self._tab_holder = tab_holder
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self.DELAY_MS)
        self._timer.timeout.connect(self.search)

    def set_tab_holder(self, tab_holder):
        self._tab_holder = tab_holder

    def _on_text_changed(self):
        self._timer.start()

    def search(self):
        self._timer.stop()
        search_text = self.search_text()
        shown = sum(section_widget.apply_search(search_text) for section_widget in self._section_widgets)
        total = sum(len(section_widget.translation_widget_list) for section_widget in self._section_widgets)
        self.result_label.setText(f"{shown}/{total}" if search_text else "")
        if self._tab_holder is not None:
            self._tab_holder.show_search_counts(bool(search_text))

    def clear_search(self):
        self.search_field.clear()
        self.search()  # at once: Escape shows everything again without waiting for the timer

    def focus_results(self):
        """Enter: run the search now and go to the first line it shows."""
        self.search()
        first = next((line for section_widget in self._section_widgets if not section_widget.isHidden()
                      for line in [section_widget.first_shown_line()] if line is not None), None)
        if first is not None:
            first.focus_editor()
