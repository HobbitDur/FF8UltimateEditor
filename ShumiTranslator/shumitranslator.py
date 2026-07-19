import os
import pathlib
from fnmatch import fnmatch

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QVBoxLayout, QWidget, QPushButton, QFileDialog, QHBoxLayout, \
    QMessageBox, QCheckBox, QTabWidget, QStackedWidget, QProgressDialog, QApplication

from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from FF8GameData.gamedata import GameData, FileType
from .shumifilepane import ShumiFilePane
from .view.translatorwidget import TranslatorWidget


class ShumiTranslator(QWidget):
    """All-text editor for seven FF8 file kinds (kernel.bin, namedic.bin, mngrp.bin, the FF8 exe,
    the remaster's card-name .dat, field.fs, world.fs) plus c0mxx.dat battle text. Import is a
    single multi-select dialog: its filter preselects every one of those names, you pick as many
    files as you like at once, and each opens its own closable tab (a ShumiFilePane with its own
    manager), its kind detected from its name. Several c0mxx.dat collapse into one battle-text tab.
    Save / CSV / compress act on whichever tab is active.

    kernel.bin and the FF8 exe share their registry key with SolomonRing/Cid/CCGroup (same file);
    mngrp.bin shares its key with Shiva/Zone/Moomba/Minimog, so importing one here publishes it to
    them too. A file opened in another tool is NOT auto-mirrored into a tab here, though: these
    editors are heavy (mngrp.bin is ~2600 text boxes), so a pane is built only when the file is
    opened through this tool - see _is_active_tool. Import it here when you want to edit it here.
    """

    CSV_FOLDER = "csv"
    file_bindings_changed = pyqtSignal()  # active tab / tab set changed -> header Save re-checks

    def __init__(self, icon_path='Resources', game_data_folder="FF8GameData", file_registry=None):
        QWidget.__init__(self)

        if file_registry is None:  # Used alone, it shares its files with nobody
            file_registry = FileRegistry()
        self.file_registry = file_registry

        self.game_data = GameData(game_data_folder)
        self.game_data.load_kernel_data()
        self.game_data.load_mngrp_data()
        self.game_data.load_item_data()
        self.game_data.load_magic_data()
        self.game_data.load_card_data()
        self.game_data.load_stat_data()
        self.game_data.load_ai_data()
        self.game_data.load_monster_data()
        self.game_data.load_status_data()
        self.game_data.load_gforce_data()
        self.game_data.load_attack_animation_data()
        self.game_data.load_enemy_abilities_data()
        self.__shumi_icon = QIcon(os.path.join(icon_path, 'icon.ico'))

        # Local toolbar: everything that ISN'T file open/save (which lives in the shared header).
        # CSV import/export, kernel compress/uncompress (only kernel supports it), the info button,
        # the JP encoding toggle and the Translator helper. All act on the active tab.
        self.csv_save_dialog = QFileDialog()
        self.csv_save_button = self.__icon_button(icon_path, 'csv_save.png', "Save to csv", self.__save_csv)
        self.csv_upload_button = self.__icon_button(icon_path, 'csv_upload.png', "Upload csv", self.__open_csv)
        self.compress_button = self.__icon_button(icon_path, 'compress.png', "Compress data", self.__compress_data)
        self.uncompress_button = self.__icon_button(icon_path, 'uncompress.png', "Uncompress data", self.__uncompress_data)
        self.info_button = self.__icon_button(icon_path, 'info.png', "Show toolmaker info", self.__show_info)

        # Japanese encoding toggle: flips the shared GameData codec to the 4-table JP font
        # (2-byte lead bytes 0x19/0x1a/0x1b). Disabled if sysfnt_jp.txt is missing.
        self.jp_checkbox = QCheckBox("日本語 (JP)")
        self.jp_checkbox.setToolTip("Encode/decode text with the Japanese 4-table font (JP version).")
        self.jp_checkbox.setEnabled(bool(self.game_data.jp_tables))
        self.jp_checkbox.toggled.connect(self.__jp_encoding_toggled)

        # The Translator helper (copy/paste, no file needed) was one exclusive combo entry; it is
        # now an independent toggle, shown above the file tabs alongside whatever is open.
        self.translator_toggle_button = QPushButton("Translator")
        self.translator_toggle_button.setCheckable(True)
        self.translator_toggle_button.setToolTip("Copy/paste translation helper (no file needed)")
        self.translator_toggle_button.toggled.connect(self.__translator_toggled)

        self.layout_top = QHBoxLayout()
        for widget in (self.csv_save_button, self.csv_upload_button, self.compress_button,
                       self.uncompress_button, self.info_button, self.translator_toggle_button,
                       self.jp_checkbox):
            self.layout_top.addWidget(widget)
        self.layout_top.addStretch(1)

        # Copy/paste translator (no file to load), shown/hidden by its toggle.
        self.translator_widget = TranslatorWidget(self.game_data)
        self.translator_widget.hide()

        # One closable tab per opened file.
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.tabCloseRequested.connect(self.__close_tab)
        self.tab_widget.currentChanged.connect(self.__tab_changed)

        self.window_layout = QVBoxLayout()
        self.setLayout(self.window_layout)
        self.window_layout.addLayout(self.layout_top)
        self.window_layout.addWidget(self.translator_widget)
        self.window_layout.addWidget(self.tab_widget, 1)

        # Every FF8 text file this tool reads, as FileBindings. They are NOT offered one-by-one in
        # the header - Import is a single multi-select dialog (see open_files). They exist so that
        # importing one still publishes it to the registry for the other tools that share it
        # (kernel.bin/FF8 exe with SolomonRing/Cid, mngrp.bin with Shiva/Zone...), and so each is
        # found by the global Open-folder scan. None has a save_callback: Save is centralized
        # (save_folder) on the active tab. c0m*.dat has no binding (no fixed name; several files
        # collapse into one battle-text tab).
        self.kernel_binding = FileBinding("kernel.bin", file_registry,
                                          load_callback=self._load_kernel, file_filter="*kernel*.bin")
        self.namedic_binding = FileBinding("namedic.bin", file_registry,
                                           load_callback=self._load_namedic, file_filter="*namedic*.bin")
        self.mngrp_binding = FileBinding("mngrp.bin", file_registry,
                                         load_callback=self._load_mngrp, file_filter="mngrp.bin")
        self.exe_binding = FileBinding("FF8 exe", file_registry,
                                       load_callback=self._load_exe, file_filter="*.exe")
        self.remaster_binding = FileBinding("remaster card names (.dat)", file_registry,
                                            load_callback=self._load_remaster,
                                            file_filter="off_cards_names*.dat")
        self.field_fs_binding = FileBinding("field.fs", file_registry,
                                            load_callback=self._load_field_fs, file_filter="field*.fs")
        self.world_fs_binding = FileBinding("world.fs", file_registry,
                                            load_callback=self._load_world_fs, file_filter="world*.fs")
        self._bindings = [self.kernel_binding, self.namedic_binding, self.mngrp_binding,
                          self.exe_binding, self.remaster_binding, self.field_fs_binding,
                          self.world_fs_binding]

        self.__tab_changed()  # start with everything disabled (no tab yet)
        for binding in self._bindings:
            binding.load_opened_file()  # a file already open elsewhere is picked up if we're active

    def __icon_button(self, icon_path, icon_name, tooltip, slot):
        button = QPushButton()
        button.setIcon(QIcon(os.path.join(icon_path, icon_name)))
        button.setIconSize(QSize(30, 30))
        button.setFixedSize(40, 40)
        button.setToolTip(tooltip)
        button.setEnabled(False)
        button.clicked.connect(slot)
        return button

    # ── Shared header toolbar hooks ──────────────────────────────────────
    # No file_bindings(): the header shows a SINGLE Import for this tool (the bindings publish to
    # the registry but are not offered one-by-one), and Import calls open_files() below.
    open_files_label = "Open FF8 text file(s)"

    def open_files(self):
        """The whole tool's Import: one multi-select dialog whose filter preselects every FF8 text
        file ShumiTranslator reads, opening one tab per file picked. Several c0mxx.dat collapse into
        a single battle-text tab; every other file gets its own tab, its kind detected by name."""
        patterns = [binding.file_filter for binding in self._bindings] + ["c0m*.dat"]
        name_filter = "FF8 text files (" + " ".join(patterns) + ");;All files (*)"
        paths = QFileDialog.getOpenFileNames(
            parent=self, caption="Open FF8 text files (several at once is fine)",
            filter=name_filter)[0]
        if not paths:
            return
        c0m_paths, unknown = [], []
        for path in paths:
            name = os.path.basename(path)
            binding = self.__binding_for(name)
            if binding is not None:
                binding.open_path(path)  # publishes to the registry AND builds its tab (we're active)
            elif fnmatch(name.lower(), "c0m*.dat"):
                c0m_paths.append(path)
            else:
                unknown.append(name)
        self.__open_c0m_set(c0m_paths)
        if unknown:
            QMessageBox.warning(self, "ShumiTranslator - unrecognised files",
                                "Skipped, ShumiTranslator doesn't read these:<br>" + "<br>".join(unknown))

    def __binding_for(self, name):
        """The FileBinding whose file filter matches this file name, or None (e.g. a c0mxx.dat)."""
        for binding in self._bindings:
            if fnmatch(name.lower(), binding.file_filter.lower()):
                return binding
        return None

    def __open_c0m_set(self, c0m_paths):
        """All the c0mxx.dat picked in one Import go into a single battle-text tab (dropping the
        garbage files), with one summary entry in the registry - like Alexander's stages."""
        valid_paths = []
        for path in c0m_paths:
            stem = pathlib.Path(path).name.split('.')[0].split('m')[1]
            if int(stem) < 144 and int(stem) != 127:  # not garbage data (c0m127 / >143)
                valid_paths.append(path)
        if not valid_paths:
            return
        self.__add_pane(FileType.DAT, valid_paths)
        self.file_registry.open_file("ShumiTranslator battle text (c0mxx.dat)",
                                     FileRegistry.summarize_paths(valid_paths, "file"))

    def save_folder(self):
        """Save the active tab's file (the shared header Save button calls this)."""
        pane = self.__active_pane()
        if pane is None:
            return
        try:
            message = pane.save(self)
        except Exception as error:  # noqa: BLE001 - surface any manager save failure to the user
            QMessageBox.critical(self, "ShumiTranslator", f"Could not save:\n{error}")
            return
        if message is not None:
            box = QMessageBox()
            box.setText(message)
            box.setIcon(QMessageBox.Icon.Information)
            box.setWindowTitle("ShumiTranslator - Data saved")
            box.setWindowIcon(self.__shumi_icon)
            box.exec()

    def can_save_folder(self):
        """The shared Save button is enabled whenever a file tab is open."""
        return self.__active_pane() is not None

    # ── Per-kind load callbacks (each opens a tab) ───────────────────────
    def _load_kernel(self, file_name):
        self.__add_pane(FileType.KERNEL, file_name)

    def _load_namedic(self, file_name):
        self.__add_pane(FileType.NAMEDIC, file_name)

    def _load_mngrp(self, file_name):
        """mngrp.bin needs mngrphd.bin (its section offset/size table) beside it, like every other
        tool that reads mngrp.bin - auto-found next to it rather than via a second dialog."""
        mngrphd_path = os.path.join(os.path.dirname(file_name), "mngrphd.bin")
        if not os.path.exists(mngrphd_path):
            QMessageBox.warning(self, "ShumiTranslator - mngrphd.bin not found",
                                f"mngrphd.bin is needed to locate the sections of mngrp.bin, it is "
                                f"not next to it:\n{mngrphd_path}")
            return
        self.__add_pane(FileType.MNGRP, file_name, mngrphd_path)

    def _load_exe(self, file_name):
        self.__add_pane(FileType.EXE, file_name)

    def _load_remaster(self, file_name):
        self.__add_pane(FileType.REMASTER_DAT, file_name)

    def _load_field_fs(self, file_name):
        self.__add_pane(FileType.FIELD_FS, file_name)

    def _load_world_fs(self, file_name):
        self.__add_pane(FileType.WORLD_FS, file_name)

    # ── Tab management ───────────────────────────────────────────────────
    def _is_active_tool(self):
        """True when this tool is the one currently selected in the main tool stack.

        A ShumiFilePane is a heavy editor (mngrp.bin alone is ~2600 text boxes). Building one is
        only worth it when the user opens the file *through this tool* - i.e. while looking at it.
        A file opened in another tool (Shiva editing mngrp.bin, SolomonRing the kernel...) still
        shares its path through the registry, but we must NOT eagerly rebuild that whole editor
        here in the background: it would freeze the app during an unrelated action and again when
        switching in. When the user does come here and wants it, one Import rebuilds it on demand.
        Used standalone (no tool stack around it), there is nothing to gate on, so always True."""
        child, parent = self, self.parentWidget()
        while parent is not None:
            if isinstance(parent, QStackedWidget):
                return parent.currentWidget() is child
            child, parent = parent, parent.parentWidget()
        return True

    def __add_pane(self, file_type, file_loaded, mngrphd_path=""):
        if not self._is_active_tool():
            return  # a background open in another tool: don't build a heavy pane behind the scenes
        # Same file already open -> focus its tab rather than opening a duplicate.
        for index in range(self.tab_widget.count()):
            pane = self.tab_widget.widget(index)
            if pane.file_type == file_type and pane.file_loaded == file_loaded:
                self.tab_widget.setCurrentIndex(index)
                return
        # These editors are heavy (mngrp.bin builds ~2600 text boxes): show a modal loading bar,
        # driven by the pane as it builds each section, so the wait is visible instead of a freeze.
        progress = self.__loading_dialog(file_type, file_loaded)
        try:
            pane = ShumiFilePane(self.game_data, file_type, file_loaded, mngrphd_path,
                                 progress=self.__report_progress(progress))
        except Exception as error:  # noqa: BLE001 - a bad/unsupported file must not kill the tool
            progress.close()
            QMessageBox.critical(self, "ShumiTranslator", f"Could not load this file:\n{error}")
            return
        progress.close()
        index = self.tab_widget.addTab(pane, pane.display_name)
        self.tab_widget.setTabToolTip(index, pane.display_name)
        self.tab_widget.setCurrentWidget(pane)
        self.file_bindings_changed.emit()  # header Save can now act

    def __loading_dialog(self, file_type, file_loaded):
        """A modal, cancel-less progress dialog for building a pane (a half-built editor is useless,
        so there is nothing to cancel to). Determinate once the pane reports its section count."""
        if file_type == FileType.DAT:
            name = (pathlib.Path(file_loaded[0]).name if len(file_loaded) == 1
                    else f"{len(file_loaded)} c0mxx.dat")
        else:
            name = pathlib.Path(file_loaded).name
        progress = QProgressDialog(f"Loading {name}…", None, 0, 0, self)
        progress.setWindowTitle("ShumiTranslator")
        progress.setWindowIcon(self.__shumi_icon)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setCancelButton(None)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        QApplication.processEvents()  # make it appear before the heavy build starts
        return progress

    @staticmethod
    def __report_progress(progress):
        def report(done, total):
            progress.setMaximum(total)  # total 0 -> a busy bar (fs unpack, no sections to count)
            progress.setValue(done)
            QApplication.processEvents()  # let the bar repaint between sections
        return report

    def __close_tab(self, index):
        pane = self.tab_widget.widget(index)
        self.tab_widget.removeTab(index)
        pane.deleteLater()
        self.file_bindings_changed.emit()

    def __active_pane(self) -> ShumiFilePane:
        return self.tab_widget.currentWidget()

    def __tab_changed(self, _index=None):
        pane = self.__active_pane()
        has_pane = pane is not None
        self.csv_save_button.setEnabled(has_pane)
        self.csv_upload_button.setEnabled(has_pane)
        supports_compress = has_pane and pane.supports_compress
        for button in (self.compress_button, self.uncompress_button):
            button.setVisible(supports_compress)
            button.setEnabled(supports_compress)

    # ── Local toolbar actions (act on the active tab) ────────────────────
    def __compress_data(self):
        pane = self.__active_pane()
        if pane is not None and pane.supports_compress:
            pane.compress()

    def __uncompress_data(self):
        pane = self.__active_pane()
        if pane is not None and pane.supports_compress:
            pane.uncompress()

    def __translator_toggled(self, checked):
        self.translator_widget.setVisible(checked)

    def __save_csv(self):
        pane = self.__active_pane()
        if pane is None:
            return
        os.makedirs(self.CSV_FOLDER, exist_ok=True)
        default_file_name = os.path.join(self.CSV_FOLDER, pane.csv_default_name())
        file_to_save = self.csv_save_dialog.getSaveFileName(
            parent=self, caption="Find csv file", filter="*.csv", directory=default_file_name)[0]
        if file_to_save:
            pane.save_csv(file_to_save)

    def __open_csv(self):
        pane = self.__active_pane()
        if pane is None:
            return
        csv_to_load = self.csv_save_dialog.getOpenFileName(
            parent=self, caption="Find csv file (in UTF8 format only)", filter="*.csv")[0]
        if not csv_to_load:
            return
        try:
            was_fs = pane.open_csv(csv_to_load)
        except UnicodeDecodeError:
            QMessageBox.critical(self, "ShumiTranslator - Wrong CSV encoding",
                                 "Wrong <b>encoding</b>, please use <b>UTF8</b> formating only.<br>"
                                 "In excel, you can go to the \"Data tab\", \"Import text file\" and "
                                 "choose UTF8 encoding")
            return
        if was_fs:
            QMessageBox.information(self, "ShumiTranslator - Data saved",
                                   "Csv uploaded to the fs file ! (Thanks for your patience)")

    def __jp_encoding_toggled(self, checked):
        self.game_data.jp_encoding = checked
        # Re-decode every open single-file tab with the new encoding (rebuild each pane in place;
        # the multi-file DAT set is left as-is, it just applies on next load/save).
        for index in range(self.tab_widget.count()):
            pane = self.tab_widget.widget(index)
            if pane.file_type == FileType.DAT:
                continue
            was_current = self.tab_widget.currentIndex() == index
            progress = self.__loading_dialog(pane.file_type, pane.file_loaded)
            rebuilt = ShumiFilePane(self.game_data, pane.file_type, pane.file_loaded,
                                    pane.file_mngrphd_loaded, progress=self.__report_progress(progress))
            progress.close()
            self.tab_widget.removeTab(index)
            pane.deleteLater()
            self.tab_widget.insertTab(index, rebuilt, rebuilt.display_name)
            self.tab_widget.setTabToolTip(index, rebuilt.display_name)
            if was_current:
                self.tab_widget.setCurrentIndex(index)

    def __show_info(self):
        message_box = QMessageBox()
        message_box.setText(f"Tool done by <b>Hobbitdur</b>.<br/>"
                            f"You can support me on <a href='https://www.patreon.com/HobbitMods'>Patreon</a>.<br/>"
                            f"Special thanks to :<br/>"
                            f"&nbsp;&nbsp;-<b>Riccardo</b> for beta testing.<br/>"
                            f"&nbsp;&nbsp;-<b>myst6re</b> for all the retro-engineering.")
        message_box.setIcon(QMessageBox.Icon.Information)
        message_box.setWindowIcon(self.__shumi_icon)
        message_box.setWindowTitle("ShumiTranslator - Info")
        message_box.exec()
