from PyQt6.QtWidgets import QWidget, QVBoxLayout

from Joker.jokermanager import Sp2File
from Joker.sp2editorwidget import Sp2EditorWidget


class ShivaSpriteWidget(QWidget):
    """The magazine picture sprites of mngrp.bin: the SP2 quad-list table of section 4.

    Same table format as a .sp2 file, so it reuses Joker's editor and Sp2File. Only this
    section is read and written back, the rest of mngrp.bin belongs to the other tabs.
    """

    MNGRP_SP2_SECTION_ID = 4

    def __init__(self):
        QWidget.__init__(self)
        self.sp2 = None

        self.sp2_editor = Sp2EditorWidget()

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.sp2_editor)
        self.setLayout(main_layout)

    def owned_section_ids(self, manager):
        """The mngrp sections this tab edits, kept out of Shiva's raw-preserve pass."""
        return {self.MNGRP_SP2_SECTION_ID}

    def load_from_mngrp(self, manager):
        section = manager.mngrp.get_section_by_id(self.MNGRP_SP2_SECTION_ID)
        self.sp2 = Sp2File.from_bytes(bytes(section.get_data_hex()))
        self.sp2_editor.set_sp2(self.sp2)

    def save_to_mngrp(self, manager):
        if not self.sp2:
            return
        manager.mngrp.set_section_by_id_and_bytearray(self.MNGRP_SP2_SECTION_ID,
                                                      bytearray(self.sp2.to_bytes()))
