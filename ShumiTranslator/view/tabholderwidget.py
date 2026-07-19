from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (QTabWidget, QSizePolicy, QStyleOptionTabWidgetFrame, QStackedLayout,
                             QScrollArea)

from FF8GameData.gamedata import FileType, SectionType
from ShumiTranslator.view.sectiontypetabwidget import SectionTypeTabWidget
from ShumiTranslator.view.sectionwidget import SectionWidget


class TabHolderWidget(QTabWidget):
    def __init__(self, file_type:FileType):
        QTabWidget.__init__(self)
        self._file_type = file_type
        self._page_list = []
        if file_type == FileType.MNGRP:
            self._add_page(SectionType.MNGRP_STRING, "Tkmnmes")
            self._add_page(SectionType.MNGRP_M00MSG, "GF Refining")
            self._add_page(SectionType.MNGRP_TEXTBOX, "Tutorial TextBox")
            self._add_page(SectionType.FF8_TEXT, "Miscellaneous")
        # Expanding on BOTH axes so the tab holder fills the pane. It used to be Maximum vertically,
        # which was fine only because each sub-page's sizeHint was the full (huge) stacked height;
        # now the pages live in their own scroll areas (small sizeHint), so Maximum would pin the
        # whole thing to a few rows and let the top warning label eat the space instead.
        self.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Expanding)
        self.currentChanged.connect(self.updateGeometry)

    def _add_page(self, section_type, title):
        """Each sub-tab's section list goes inside its OWN scroll area. Without one, showing the
        tab lays out and paints every text box at once (mngrp.bin is thousands of them) and the app
        locks after loading; a scroll area clips painting to the visible rows so it stays snappy.
        _page_list keeps the inner SectionTypeTabWidget (what add_section fills), not the scroll."""
        page = SectionTypeTabWidget([], section_type=section_type)
        self._page_list.append(page)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        self.addTab(scroll, title)

    def add_section(self, section_widget:SectionWidget):
        for i in range(len(self._page_list)):
            if self._page_list[i].get_type() == section_widget.section.type:
                self._page_list[i].add_section_widget(section_widget)
                return
        print(f"Type section not found: {section_widget.section.type}")

    def minimumSizeHint(self):
        return self.sizeHint()

    def sizeHint(self):
        lc = QSize(0, 0)
        rc = QSize(0, 0)
        opt = QStyleOptionTabWidgetFrame()
        self.initStyleOption(opt)
        if self.cornerWidget(Qt.Corner.TopLeftCorner):
            lc = self.cornerWidget(Qt.Corner.TopLeftCorner).sizeHint()
        if self.cornerWidget(Qt.Corner.TopRightCorner):
            rc = self.cornerWidget(Qt.Corner.TopRightCorner).sizeHint()
        layout = self.findChild(QStackedLayout)
        layout_hint = layout.currentWidget().sizeHint()
        tab_hint = self.tabBar().sizeHint()
        if self.tabPosition() in (QTabWidget.TabPosition.North, QTabWidget.TabPosition.South):
            size = QSize(
                max(layout_hint.width(), tab_hint.width() + rc.width() + lc.width()),
                layout_hint.height() + max(rc.height(), max(lc.height(), tab_hint.height()))
            )
        else:
            size = QSize(
                layout_hint.width() + max(rc.width(), max(lc.width(), tab_hint.width())),
                max(layout_hint.height(), tab_hint.height() + rc.height() + lc.height())
            )
        return size
