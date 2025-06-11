from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QTabWidget, QSizePolicy, QStyleOptionTabWidgetFrame, QStackedLayout

from FF8GameData.gamedata import FileType, SectionType
from ShumiTranslator.view.sectiontypetabwidget import SectionTypeTabWidget
from ShumiTranslator.view.sectionwidget import SectionWidget


class TabHolderWidget(QTabWidget):
    def __init__(self, file_type:FileType):
        QTabWidget.__init__(self)
        self._file_type = file_type
        self._page_list = []
        if file_type == FileType.MNGRP:
            self._page_list.append(SectionTypeTabWidget([], section_type=SectionType.MNGRP_STRING))
            self.addTab( self._page_list[-1], "Tkmnmes")
            self._page_list.append(SectionTypeTabWidget([], section_type=SectionType.MNGRP_M00MSG))
            self.addTab(self._page_list[-1], "GF Refining")
            self._page_list.append(SectionTypeTabWidget([], section_type=SectionType.MNGRP_TEXTBOX))
            self.addTab(self._page_list[-1], "Tutorial TextBox")
            self._page_list.append(SectionTypeTabWidget([], section_type=SectionType.FF8_TEXT))
            self.addTab(self._page_list[-1], "Miscellaneous")
        self.setSizePolicy(QSizePolicy.Policy.MinimumExpanding,QSizePolicy.Policy.Maximum)
        self.currentChanged.connect(self.updateGeometry)

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
