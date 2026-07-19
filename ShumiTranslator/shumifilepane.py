"""One loaded file, one tab: a self-contained ShumiTranslator editor pane.

Each pane owns its own manager and section widgets for a single opened file, so several files
(of the same or different kinds) can be open at once in the shell's QTabWidget - editing/saving
one is independent of the others. The shell (shumitranslator.py) creates one pane per file the
shared header toolbar opens, and routes Save / CSV / compress to whichever tab is active.
"""
import csv
import pathlib

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QLabel, QFileDialog

from FF8GameData.gamedata import GameData, FileType, SectionType, RemasterCardType
from FF8GameData.menu.mngrp.mngrpmanager import MngrpManager
from FF8GameData.menu.mngrp.string.sectionstring import SectionString
from .model.battle.battlemanager import BattleManager
from .model.exe.exemanager import ExeManager
from .model.exe.remasterdatmanager import RemasterDatManager
from .model.field.fieldfsmanager import FieldFsManager
from .model.kernel.kernelmanager import KernelManager
from .model.world.worldfsmanager import WorldFsManager
from .view.sectionwidget import SectionWidget
from .view.tabholderwidget import TabHolderWidget

# The per-kind warning shown at the top of the pane (was a hide/show label in the old single-file
# widget; now each pane carries its own so it is always right for that tab).
_WARNINGS = {
    FileType.KERNEL: (
        "{x0...} are yet unknown text correspondence. Pls don't modify them.<br/>"
        "Value between {} are \"compressed\" data. Pls don't remove bracket around.<br/>"
        "The file as a size max (40456?).<br/>"
        "If you wish to get rid of parenthesis you can uncompress<br/>"
        "But pls compress before saving to avoid size problem."),
    FileType.MNGRP: (
        "{x0...} are yet unknown text correspondence. Pls don't modify them.<br/>"
        "Value between {} are \"compressed\" data. Pls don't remove bracket around.<br/>"),
    FileType.EXE: (
        "/!\\ Only compatible with FFNx (2000 and 2013 version)<br/>"
        "When saving, this tool produce<br/>"
        "msd files that need to be put in the folder direct/exe/<br/>"),
    FileType.DAT: (
        "c0m127 and all files > 143 are garbage so they are ignored even if selected"),
    FileType.FIELD_FS: (
        "This tool use deling (please download with the button after canal), an external tool done my myst6re, to manage all field text (what character says). <br/> Due to this, the tool doesn't offer direct "
        "modification but allows to export and import csv. <br/> "
        "The input is the field.fs file (need the .fi and .fl with same name and in same folder than field.fs)<br/>"
        "It will output a folder containing only the msd files which correspond to the file text.<br/>"
        "For the moment, it only works on Windows.<br/>"
        "<b>/!\\ When saving or uploading csv, there is a lot of work being done, so be patient.</b><br/>"
        "The save put all files in a field folder that can be directly put in the direct folder of FFNx."),
    FileType.WORLD_FS: (
        "This tool use deling (please download with the button after canal), an external tool done my myst6re, to manage all world text (Draw point, aubel,...). <br/> Due to this, the tool doesn't offer direct "
        "modification but allows to export and import csv. <br/> "
        "The input is the world.fs file (need the .fi and .fl with same name and in same folder than world.fs)<br/>"
        "It will output a folder containing only the msd files which correspond to the file text.<br/>"
        "<b>/!\\ When saving or uploading csv, there is a lot of work being done, so be patient.</b><br/>"
        "The save put all files in a world folder that can be directly put in the direct folder of FFNx."),
}


class ShumiFilePane(QWidget):
    """The editor for ONE opened file (one tab). Builds its own manager + section widgets."""

    def __init__(self, game_data, file_type, file_loaded, mngrphd_path="", progress=None):
        super().__init__()
        self.game_data = game_data
        self.file_type = file_type
        self.file_loaded = file_loaded          # str, or list[str] for a c0mxx.dat (DAT) set
        self.file_mngrphd_loaded = mngrphd_path
        self.section_widget_list = []
        self.manager = None
        # Optional loading reporter: callable(done, total), driven as the section text boxes are
        # built (mngrp.bin alone is ~2600 of them), so the shell can show a loading bar. None = off.
        self._progress = progress
        self._progress_done = 0
        self._progress_total = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        warning = _WARNINGS.get(file_type)
        if warning:
            warning_label = QLabel(warning)
            warning_label.setWordWrap(True)
            outer.addWidget(warning_label)

        # Section widgets are stacked in this container; a scroll area wraps it (except mngrp,
        # which uses its own TabHolderWidget, and the fs kinds, which have no editable sections).
        self._lines_container = QWidget()
        self._lines_layout = QVBoxLayout(self._lines_container)
        self._lines_layout.setContentsMargins(0, 0, 0, 0)

        builder = {
            FileType.KERNEL: self._build_kernel,
            FileType.NAMEDIC: self._build_namedic,
            FileType.MNGRP: self._build_mngrp,
            FileType.EXE: self._build_exe,
            FileType.DAT: self._build_dat,
            FileType.REMASTER_DAT: self._build_remaster,
            FileType.FIELD_FS: self._build_fs,
            FileType.WORLD_FS: self._build_fs,
        }[file_type]
        builder(outer)

    # -- display -------------------------------------------------------------
    @property
    def display_name(self):
        if self.file_type == FileType.DAT:
            return (pathlib.Path(self.file_loaded[0]).name if len(self.file_loaded) == 1
                    else f"{len(self.file_loaded)} c0mxx.dat")
        return pathlib.Path(self.file_loaded).name

    def _add_scroll(self, outer):
        self._lines_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._lines_container)
        outer.addWidget(scroll, 1)

    # -- loading progress ----------------------------------------------------
    def _begin_progress(self, total):
        """Declare how many section text boxes are about to be built, so the bar is determinate."""
        self._progress_total = total
        self._progress_done = 0
        if self._progress:
            self._progress(0, total)

    def _tick(self):
        """One more section built - advance the bar (and let it repaint, in the shell)."""
        self._progress_done += 1
        if self._progress:
            self._progress(self._progress_done, self._progress_total)

    # -- per-kind builders ---------------------------------------------------
    def _build_kernel(self, outer):
        self.manager = KernelManager(game_data=self.game_data)
        self.manager.load_file(self.file_loaded)
        text_sections = [s for s in self.manager.section_list if s.type == SectionType.FF8_TEXT]
        self._begin_progress(len(text_sections))
        first_section_line_index = 2  # Start at 2 as in the CSV
        for section in text_sections:
            self._add_section(SectionWidget(section, first_section_line_index))
            first_section_line_index += len(section.section_data_linked.get_all_offset())
        self._add_scroll(outer)

    def _build_namedic(self, outer):
        self.manager = SectionString(game_data=self.game_data)
        self.manager.load_file(self.file_loaded)
        self._begin_progress(1)
        self._add_section(SectionWidget(self.manager.get_text_section(), 2))  # only one section
        self._add_scroll(outer)

    def _build_mngrp(self, outer):
        self.manager = MngrpManager(game_data=self.game_data)
        self.manager.load_file(self.file_mngrphd_loaded, self.file_loaded)
        tab_holder = TabHolderWidget(FileType.MNGRP)
        wanted = (SectionType.TKMNMES, SectionType.MNGRP_STRING, SectionType.FF8_TEXT,
                  SectionType.MNGRP_TEXTBOX, SectionType.MNGRP_M00MSG)
        sections = self.manager.mngrp.get_section_list()
        # Count the section widgets first (a TKMNMES expands to several) so the bar is determinate -
        # this is the heaviest pane, ~2600 text boxes over dozens of sections.
        total = sum(section.get_nb_text_section() if section.type == SectionType.TKMNMES
                    else 1 for section in sections if section.type in wanted)
        self._begin_progress(total)
        first_section_line_index = 2
        for section in sections:
            if section.type == SectionType.MNGRP_STRING:
                self.section_widget_list.append(SectionWidget(section.get_text_section(), first_section_line_index))
                first_section_line_index += len(section.get_text_list())
                self._tick()
            elif section.type == SectionType.FF8_TEXT or section.type == SectionType.MNGRP_M00MSG:
                self.section_widget_list.append(SectionWidget(section, first_section_line_index))
                first_section_line_index += len(section.get_text_list())
                self._tick()
            elif section.type == SectionType.TKMNMES:
                for i in range(section.get_nb_text_section()):
                    self.section_widget_list.append(SectionWidget(section.get_text_section_by_id(i), first_section_line_index))
                    first_section_line_index += len(section.get_text_section_by_id(i).get_text_list())
                    self._tick()
            elif section.type == SectionType.MNGRP_TEXTBOX:
                self.section_widget_list.append(SectionWidget(section, first_section_line_index))
                first_section_line_index += len(section.get_text_list())
                self._tick()
        for section_widget in self.section_widget_list:
            tab_holder.add_section(section_widget)
        outer.addWidget(tab_holder, 1)

    def _build_exe(self, outer):
        self.manager = ExeManager(game_data=self.game_data)
        self.manager.load_file(self.file_loaded)
        exe_section = self.manager.get_exe_section()
        self._begin_progress(4)
        first_section_line_index = 2
        for getter in (exe_section.get_section_draw_text, exe_section.get_section_card_misc_text,
                       exe_section.get_section_card_name, exe_section.get_section_scan_text):
            text_section = getter().get_text_section()
            self._add_section(SectionWidget(text_section, first_section_line_index))
            first_section_line_index += len(text_section.get_text_list())
        self._add_scroll(outer)

    def _build_dat(self, outer):
        self.manager = BattleManager(game_data=self.game_data)
        self.manager.reset()
        for path in self.file_loaded:
            self.manager.add_file(path)
        sections = self.manager.get_section_list()
        self._begin_progress(len(sections))
        first_section_line_index = 2
        for section in sections:
            self._add_section(SectionWidget(section, first_section_line_index))
            first_section_line_index += len(section.get_text_list())
        self._add_scroll(outer)

    def _build_remaster(self, outer):
        self.manager = RemasterDatManager(game_data=self.game_data)
        name = pathlib.Path(self.file_loaded).name
        if "off_cards_names" in name and "2" not in name:
            type_to_load = RemasterCardType.CARD_NAME
        elif "off_cards_names" in name and "2" in name:
            type_to_load = RemasterCardType.CARD_NAME2
        else:
            print(f"Unexpected file name: {name}")
            type_to_load = RemasterCardType.CARD_NAME
        self.manager.load_file(self.file_loaded, type_to_load)
        self._begin_progress(1)
        self._add_section(SectionWidget(self.manager.get_section().get_text_section(), 2))
        self._add_scroll(outer)

    def _build_fs(self, outer):
        self._begin_progress(1)  # no section widgets, just the (slow) unpack - show a busy bar
        manager_type = FieldFsManager if self.file_type == FileType.FIELD_FS else WorldFsManager
        self.manager = manager_type(game_data=self.game_data)
        self.manager.load_file(self.file_loaded)
        self._tick()
        outer.addStretch(1)  # fs kinds have no editable sections, only export/import CSV

    def _add_section(self, section_widget):
        self.section_widget_list.append(section_widget)
        self._lines_layout.addWidget(section_widget)
        self._tick()

    # -- save ----------------------------------------------------------------
    def save(self, parent):
        """Save this pane's file. Returns a human message on success, or None if cancelled.
        Some kinds write straight back to a file; others need an output folder."""
        if self.file_type == FileType.KERNEL:
            self.manager.save_file(self.file_loaded)
            return f"Data saved to file <b>{pathlib.Path(self.file_loaded).name}</b>"
        if self.file_type == FileType.NAMEDIC:
            self.manager.save_file(self.file_loaded)
            return f"Data saved to file <b>{pathlib.Path(self.file_loaded).name}</b>"
        if self.file_type == FileType.MNGRP:
            self.manager.save_file(self.file_loaded, self.file_mngrphd_loaded)
            return f"Data saved to file <b>{pathlib.Path(self.file_loaded).name}</b>"
        if self.file_type == FileType.REMASTER_DAT:
            self.manager.save_file(self.file_loaded)
            return f"Data saved to file <b>{pathlib.Path(self.file_loaded).name}</b>"
        if self.file_type == FileType.DAT:
            self.manager.save_all_file()  # rewrites the c0m files in place
            if len(self.file_loaded) == 1:
                return f"Data saved to file <b>{pathlib.Path(self.file_loaded[0]).name}</b>"
            return "Data saved to file <b>c0mxx.dat</b>"
        if self.file_type == FileType.EXE:
            folder = QFileDialog.getExistingDirectory(parent, "Save msd file")
            if not folder:
                return None
            self.manager.save_file(folder)
            return f"Msd files saved to folder <b>{pathlib.Path(folder).name}</b>"
        if self.file_type == FileType.FIELD_FS:
            folder = QFileDialog.getExistingDirectory(parent, "Save field fs unpacked")
            if not folder:
                return None
            self.manager.save_file(folder)
            return f"Msd files saved to folder <b>{pathlib.Path(folder).name}</b>"
        if self.file_type == FileType.WORLD_FS:
            folder = QFileDialog.getExistingDirectory(parent, "Save world fs unpacked")
            if not folder:
                return None
            self.manager.save_file(folder)
            return f"wmsetxx.obj file saved to folder <b>{pathlib.Path(folder).name}</b>"
        return None

    # -- compress (kernel only) ---------------------------------------------
    @property
    def supports_compress(self):
        return self.file_type == FileType.KERNEL

    def compress(self):
        # Each section is told which of its offsets can be compressed (0=None,1=First,2=Second,3=Both).
        for section_widget in self.section_widget_list:
            compressibility_factor = [x["compressibility_factor"]
                                      for x in self.game_data.kernel_data_json["sections"]
                                      if x["id"] == section_widget.section.id][0]
            section_widget.compress_str(compressibility_factor)

    def uncompress(self):
        for section_widget in self.section_widget_list:
            section_widget.uncompress_str()

    # -- CSV -----------------------------------------------------------------
    @property
    def is_fs(self):
        return self.file_type in (FileType.FIELD_FS, FileType.WORLD_FS)

    def csv_default_name(self):
        if self.file_type == FileType.DAT:
            base = pathlib.Path(self.file_loaded[0]).name if len(self.file_loaded) == 1 else "c0mxx.dat"
        else:
            base = pathlib.Path(self.file_loaded).name
        return base.split('.')[0] + '.csv'

    def save_csv(self, file_to_save):
        if self.file_type == FileType.FIELD_FS:
            self.manager.save_csv(file_to_save)
        elif self.file_type == FileType.WORLD_FS:
            self.manager.save_csv(file_to_save)
        else:
            with open(file_to_save, 'w', newline='', encoding="utf-8") as csv_file:
                csv_writer = csv.writer(csv_file, delimiter=GameData.find_delimiter_from_csv_file(file_to_save),
                                        quotechar='§', quoting=csv.QUOTE_MINIMAL)
                csv_writer.writerow(['Section data name', 'Section Widget id', 'Text Sub id', 'Text'])
                for section_widget_id, section_widget in enumerate(self.section_widget_list):
                    for ff8_widget_id, ff8_text in enumerate(section_widget.section.get_text_list()):
                        csv_writer.writerow([section_widget.section.name, section_widget_id, ff8_widget_id,
                                             ff8_text.get_str().replace('\n', '\\n')])

    def open_csv(self, csv_to_load):
        """Import a CSV into this pane. Returns True for the fs kinds (which show a 'be patient'
        popup handled by the caller), False otherwise."""
        if self.file_type == FileType.FIELD_FS:
            self.manager.load_csv(csv_to_load=csv_to_load)
            return True
        if self.file_type == FileType.WORLD_FS:
            self.manager.load_csv(csv_to_load=csv_to_load)
            return True
        with open(csv_to_load, newline='', encoding="utf-8") as csv_file:
            csv_data = csv.reader(csv_file, delimiter=GameData.find_delimiter_from_csv_file(csv_to_load),
                                  quotechar='§')
            for row_index, row in enumerate(csv_data):
                if row_index == 0:  # Ignoring title row
                    continue
                section_widget_id = int(row[1])
                text_sub_id = int(row[2])
                text_loaded = row[3]
                if text_loaded == "":
                    continue
                text_loaded = text_loaded.replace('`', "'")  # common user mistake
                self.section_widget_list[section_widget_id].set_text_from_id(text_sub_id, text_loaded)
        return False
