import os
import pathlib
from fnmatch import fnmatch

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QVBoxLayout, QWidget, QPushButton, QFileDialog, QHBoxLayout, \
    QMessageBox, QComboBox, QLabel, QTabWidget, QStackedWidget, QProgressDialog, QApplication

from Common.filebinding import FileBinding
from Common.autoimport import AutoImportSource
from Common.dirtytracking import DirtyState
from Common.fileregistry import FileRegistry
from FF8GameData.gamedata import GameData, FileType
from .shumifilepane import ShumiFilePane
from FF8GameData.font.hiresfont import HiresFont
from .view.fontpane import FontPane
from .view.translatorwidget import TranslatorWidget


class ShumiTranslator(QWidget):
    """All-text editor for eight FF8 file kinds (kernel.bin, namedic.bin, mngrp.bin, mwepon.msg, the
    FF8 exe, the remaster's card-name .dat, field.fs, world.fs) plus c0mxx.dat battle text, and the font
    (.tdw). The header's Import lists each kind; each file opens its own closable tab (a
    ShumiFilePane with its own manager). Several c0mxx.dat, picked together, collapse into one
    battle-text tab. The font is a secondary file, under Import complementary: it opens a font tab
    (FontPane). Save / CSV / compress act on whichever tab is active.

    kernel.bin and the FF8 exe share their registry key with SolomonRing/Cid/CCGroup (same file);
    mngrp.bin shares its key with Shiva/Zone/Moomba/Minimog, so importing one here publishes it to
    them too. A file opened in another tool is NOT auto-mirrored into a tab here, though: these
    editors are heavy (mngrp.bin is ~2600 text boxes), so a pane is built only when the file is
    opened through this tool - see _is_active_tool. Import it here when you want to edit it here.
    """

    CSV_FOLDER = "csv"
    file_bindings_changed = pyqtSignal()  # active tab / tab set changed -> header Save re-checks

    # The one summary entry the battle-text tab's c0mxx.dat set has in the Opened files panel.
    C0M_REGISTRY_NAME = "ShumiTranslator battle text (c0mxx.dat)"

    def __init__(self, icon_path='Resources', game_data_folder="FF8GameData", file_registry=None):
        QWidget.__init__(self)

        if file_registry is None:  # Used alone, it shares its files with nobody
            file_registry = FileRegistry()
        self.file_registry = file_registry
        file_registry.file_closed.connect(self.__on_registry_file_closed)

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

        # Character table: which character each code is, for every tab (GameData.CHARACTER_TABLES:
        # Latin, Japanese with its 2-byte kanji codes, Vietnamese; or a file of your own, "Custom
        # file...", opened again each session). The files don't say which one they use, so it is chosen
        # here; a built-in one is remembered.
        self.table_box = QComboBox()
        for key, (name, _file, _japanese) in GameData.CHARACTER_TABLES.items():
            self.table_box.addItem(name, key)
        self.table_box.addItem("Custom file...", self.PICK_TABLE)
        self.table_box.setToolTip("Character table the texts are read and written with: which character each "
                                  "code of the game's font is. Changing it re-reads the open files.")
        self.table_box.setProperty("read_only_preview", True)  # choosing it is not an edit of a file
        saved = self.__settings_value(self.TABLE_SETTING)  # the last built-in table chosen (not a custom file)
        if saved in GameData.CHARACTER_TABLES and saved != "latin":
            self.game_data.set_character_table(saved)
        self.__show_table()
        self.table_box.currentIndexChanged.connect(self.__character_table_changed)
        table_label = QLabel("Characters:")

        # The Translator helper (copy/paste, no file needed) was one exclusive combo entry; it is
        # now an independent toggle, shown above the file tabs alongside whatever is open.
        self.translator_toggle_button = QPushButton("Translator")
        self.translator_toggle_button.setCheckable(True)
        self.translator_toggle_button.setToolTip("Copy/paste translation helper (no file needed)")
        self.translator_toggle_button.toggled.connect(self.__translator_toggled)

        self.layout_top = QHBoxLayout()
        for widget in (self.csv_save_button, self.csv_upload_button, self.compress_button,
                       self.uncompress_button, self.info_button, self.translator_toggle_button,
                       table_label, self.table_box):
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

        # Every FF8 text file this tool reads, as FileBindings: the header's Import lists them one by
        # one (plus the c0mxx.dat multi-select, see open_files), and a file opened here is shared
        # through the registry with the other tools reading it (kernel.bin/FF8 exe with
        # SolomonRing/Cid, mngrp.bin with Shiva/Zone...). None has a save_callback: Save is
        # centralized (save_folder) on the active tab. c0m*.dat has no binding (no fixed name;
        # several files collapse into one battle-text tab).
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
        # mwepon.msg, the Junk Shop text per upgrade: read with the mwepon.bin beside it (its offsets)
        self.mwepon_msg_binding = FileBinding("mwepon.msg", file_registry,
                                              load_callback=self._load_mwepon_msg, file_filter="mwepon*.msg")
        self.field_fs_binding = FileBinding("field.fs", file_registry,
                                            load_callback=self._load_field_fs, file_filter="field*.fs")
        self.world_fs_binding = FileBinding("world.fs", file_registry,
                                            load_callback=self._load_world_fs, file_filter="world*.fs")
        # A font (main/sysfnt.tdw, or a field's .tdw) opens a font tab instead of a text tab. It is
        # a secondary file of this tool: offered by Import complementary, not Import.
        self.font_binding = FileBinding("font (.tdw)", file_registry, load_callback=self._load_font,
                                        file_filter="*.tdw", complementary=True)
        # The font tab's own side files: the textures the PC game draws text with (low and high
        # resolution). They attach to the font tab shown (see FontPane).
        self.font_texture_binding = FileBinding("font texture, low res (menu/sysfnt.TEX)", file_registry,
                                                load_callback=self._load_font_texture,
                                                file_filter="sysfnt*.tex", complementary=True)
        self.font_hires_binding = FileBinding("font textures, high res (menu/hires/sysfld00.TEX...)",
                                              file_registry, load_callback=self._load_font_hires,
                                              file_filter="sysfld0*.tex sysevn0*.tex sysodd0*.tex",
                                              complementary=True)
        self._bindings = [self.kernel_binding, self.namedic_binding, self.mngrp_binding,
                          self.mwepon_msg_binding, self.exe_binding, self.remaster_binding, self.field_fs_binding,
                          self.world_fs_binding, self.font_binding, self.font_texture_binding,
                          self.font_hires_binding]

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
    # Import lists every text file kind (file_bindings) plus the c0mxx.dat multi-select
    # (open_files); Import complementary offers the font.
    open_files_label = "c0mxx.dat (battle text)"

    def file_bindings(self):
        return list(self._bindings)

    def complementary_entries(self):
        """Import complementary: the font and its textures. The hi-res textures are several files
        (sysfld00 + 01, or sysevn/sysodd 00-03), picked all at once."""
        return [(self.font_binding.file_name, lambda: self.font_binding.open_remembered(self)),
                (self.font_texture_binding.file_name, lambda: self.font_texture_binding.open_remembered(self)),
                ("font textures, high res (menu/hires: select all of them)", self.open_hires_textures)]

    def open_hires_textures(self, paths=None):
        """Pick every hi-res font texture at once (a tile missing from the pick is taken from the same
        folder), then attach them to the font tab."""
        binding = self.font_hires_binding
        if paths is None:
            paths = QFileDialog.getOpenFileNames(
                self, "High resolution font textures (select all of them)",
                self.file_registry.last_folder(binding.file_name),
                "Hi-res font textures (" + binding.file_filter + ");;All files (*)")[0]
        if not paths:
            return
        textures = [path for path in paths if HiresFont.is_hires_font(path)]
        if not textures:
            QMessageBox.warning(self, "ShumiTranslator", "None of these files is a hi-res font texture "
                                "(sysfld00/01.TEX, or sysevn00-03 and sysodd00-03.TEX).")
            return
        self.file_registry.remember_folder(binding.file_name, os.path.dirname(textures[0]))
        binding.open_path(textures[0])  # loads them all (see HiresFont.from_path) into the font tab

    def auto_import_sources(self):
        """The c0mxx.dat set; the header adds one source per file binding itself."""
        return [AutoImportSource("ShumiTranslator battle text", ("c0m[0-9][0-9][0-9].dat",),
                                 self.open_files, selection_only=True)]

    def open_files(self, paths=None):
        """Open several files at once, one tab each, the kind of each detected by its name; several
        c0mxx.dat collapse into a single battle-text tab. Without paths (the header's c0mxx.dat
        entry), asks for the c0mxx.dat files."""
        key = "ShumiTranslator text files"
        if paths is None:
            paths = QFileDialog.getOpenFileNames(
                parent=self, caption="Open c0mxx.dat battle texts (several at once is fine)",
                filter="Battle texts (c0m*.dat);;All files (*)", directory=self.file_registry.last_folder(key))[0]
        if not paths:
            return
        self.file_registry.remember_folder(key, os.path.dirname(paths[0]))
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
        if c0m_paths:
            self.file_registry.remember_files("ShumiTranslator battle text", c0m_paths)
        if unknown:
            QMessageBox.warning(self, "ShumiTranslator - unrecognised files",
                                "Skipped, ShumiTranslator doesn't read these:<br>" + "<br>".join(unknown))

    def __binding_for(self, name):
        """The FileBinding whose file filter matches this file name, or None (e.g. a c0mxx.dat)."""
        for binding in self._bindings:
            if any(fnmatch(name.lower(), pattern) for pattern in binding.file_filter.lower().split()):
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
        self.file_registry.open_file(self.C0M_REGISTRY_NAME,
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
        pane.dirty_state.clear()
        if getattr(pane, "unsaved_after_save", lambda: False)():
            pane.dirty_state.mark()  # e.g. the font tab's changed characters, no .txt chosen for them
        if message is not None:
            box = QMessageBox()
            box.setText(message)
            box.setIcon(QMessageBox.Icon.Information)
            box.setWindowTitle("ShumiTranslator - Data saved")
            box.setWindowIcon(self.__shumi_icon)
            box.exec()

    def undo(self):
        """Ctrl+Z, routed here by the main window: the tab shown undoes, if it has an undo (the font tab;
        a text field keeps its own Ctrl+Z)."""
        pane = self.__active_pane()
        return bool(pane is not None and callable(getattr(pane, "undo", None)) and pane.undo())

    def redo(self):
        pane = self.__active_pane()
        return bool(pane is not None and callable(getattr(pane, "redo", None)) and pane.redo())

    def can_save_folder(self):
        """The shared Save button is enabled whenever a file tab is open."""
        return self.__active_pane() is not None

    def has_unsaved_changes(self):
        """Whether any tab holds edits not saved yet (each tab tracks its own, see __track_edits)."""
        return any(self.tab_widget.widget(index).dirty_state.dirty
                   for index in range(self.tab_widget.count()))

    def __track_edits(self, pane):
        """Give a tab its own unsaved-edits tracker, set up once the pane is fully built so its
        loading never counts: an edit in its text boxes marks it, its successful Save clears it."""
        pane.dirty_state = DirtyState(pane)
        pane.dirty_state.track(pane)
        pane.dirty_state.changed.connect(lambda _dirty: self.file_bindings_changed.emit())

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

    def _load_mwepon_msg(self, file_name):
        """mwepon.msg needs mwepon.bin beside it: its upgrade records say where each text starts, and
        Save moves those offsets with the texts."""
        bin_path = os.path.join(os.path.dirname(file_name), "mwepon.bin")
        if not os.path.exists(bin_path):
            QMessageBox.warning(self, "ShumiTranslator - mwepon.bin not found",
                                f"mwepon.bin says where each text of mwepon.msg starts, it is not next to "
                                f"it:\n{bin_path}")
            return
        self.__add_pane(FileType.MWEPON_MSG, file_name, bin_path)

    def _load_exe(self, file_name):
        self.__add_pane(FileType.EXE, file_name)

    def _load_remaster(self, file_name):
        self.__add_pane(FileType.REMASTER_DAT, file_name)

    def _load_field_fs(self, file_name):
        self.__add_pane(FileType.FIELD_FS, file_name)

    def _load_world_fs(self, file_name):
        self.__add_pane(FileType.WORLD_FS, file_name)

    def _load_font(self, file_name):
        self.__add_pane(FileType.FONT, file_name)

    def _load_font_texture(self, file_name):
        self.__attach_to_font(file_name, "attach_texture")

    def _load_font_hires(self, file_name):
        self.__attach_to_font(file_name, "attach_hires")

    def __attach_to_font(self, file_name, method):
        """A font side file goes to the font tab shown (or the only one open)."""
        if not self._is_active_tool():
            return
        pane = self.__active_pane()
        if pane is None or pane.file_type != FileType.FONT:
            fonts = [self.tab_widget.widget(i) for i in range(self.tab_widget.count())
                     if self.tab_widget.widget(i).file_type == FileType.FONT]
            pane = fonts[0] if len(fonts) == 1 else None
        if pane is None:
            QMessageBox.warning(self, "ShumiTranslator", "Open the font (.tdw) first, and show its tab: "
                                f"{os.path.basename(file_name)} completes it.")
            return
        try:
            getattr(pane, method)(file_name)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "ShumiTranslator", f"Could not use {os.path.basename(file_name)}:\n{error}")
            return
        self.tab_widget.setCurrentWidget(pane)

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
        # Same file already open (imported again, or the header's Reload) -> no duplicate: its tab
        # is read again from disk, unless it holds unsaved edits, then it is only shown.
        replaced = None
        for index in range(self.tab_widget.count()):
            pane = self.tab_widget.widget(index)
            if pane.file_type == file_type and pane.file_loaded == file_loaded:
                self.tab_widget.setCurrentIndex(index)
                if pane.dirty_state.dirty:
                    return
                replaced = index
                break
        # These editors are heavy (mngrp.bin builds ~2600 text boxes): show a modal loading bar,
        # driven by the pane as it builds each section, so the wait is visible instead of a freeze.
        progress = self.__loading_dialog(file_type, file_loaded)
        try:
            if file_type == FileType.FONT:
                pane = FontPane(self.game_data, file_loaded)
            else:
                pane = ShumiFilePane(self.game_data, file_type, file_loaded, mngrphd_path,
                                     progress=self.__report_progress(progress))
        except Exception as error:  # noqa: BLE001 - a bad/unsupported file must not kill the tool
            progress.close()
            QMessageBox.critical(self, "ShumiTranslator", f"Could not load this file:\n{error}")
            return
        progress.close()
        self.__track_edits(pane)
        if replaced is None:
            index = self.tab_widget.addTab(pane, pane.display_name)
        else:
            old = self.tab_widget.widget(replaced)
            self.tab_widget.removeTab(replaced)
            old.deleteLater()
            index = self.tab_widget.insertTab(replaced, pane, pane.display_name)
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
        # Start determinate at 0/100 (an empty bar), not 0/0 - a 0/0 dialog shows the busy "blue
        # marquee" that looks stuck while the first file parses. The pane's first _begin_progress
        # replaces 100 with the real step count almost immediately.
        progress = QProgressDialog(f"Loading {name}…", None, 0, 100, self)
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

    def __on_registry_file_closed(self, file_name, file_path):
        """A file was removed from the Opened files panel: close the tab(s) showing it - the
        battle-text tab for the c0mxx.dat set, else the tab of that exact path."""
        for index in reversed(range(self.tab_widget.count())):
            pane = self.tab_widget.widget(index)
            if file_name == self.C0M_REGISTRY_NAME:
                closing = pane.file_type == FileType.DAT
            else:
                closing = pane.file_type != FileType.DAT and pane.file_loaded == file_path
            if closing:
                self.__close_tab(index)

    def __active_pane(self) -> ShumiFilePane:
        return self.tab_widget.currentWidget()

    def __tab_changed(self, _index=None):
        pane = self.__active_pane()
        has_pane = pane is not None
        has_csv = has_pane and getattr(pane, "supports_csv", True)  # a font tab has no texts
        self.csv_save_button.setEnabled(has_csv)
        self.csv_upload_button.setEnabled(has_csv)
        supports_compress = has_pane and pane.supports_compress
        for button in (self.compress_button, self.uncompress_button):
            button.setVisible(supports_compress)
            button.setEnabled(supports_compress)

    # ── Local toolbar actions (act on the active tab) ────────────────────
    def __compress_data(self):
        pane = self.__active_pane()
        if pane is not None and pane.supports_compress:
            pane.compress()
            pane.dirty_state.mark()

    def __uncompress_data(self):
        pane = self.__active_pane()
        if pane is not None and pane.supports_compress:
            pane.uncompress()
            pane.dirty_state.mark()

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
        if was_fs:  # written straight into the .fs archive
            QMessageBox.information(self, "ShumiTranslator - Data saved",
                                   "Csv uploaded to the fs file ! (Thanks for your patience)")
        else:       # the texts are in the tab, not saved yet
            pane.dirty_state.mark()

    # ── Character table ──────────────────────────────────────────────────
    TABLE_SETTING = "ShumiTranslator/character_table"

    def __settings_value(self, key):
        settings = getattr(self.file_registry, "settings", None)
        return settings.value(key) if settings is not None else None

    PICK_TABLE = "pick"     # the "Custom file..." line: asks for the file
    CUSTOM = "custom:"      # a custom file's line: CUSTOM + its path

    def __current_choice(self):
        if self.game_data.character_table == "custom":
            return self.CUSTOM + self.game_data.character_table_path
        return self.game_data.character_table

    def __use_table(self, choice):
        if choice.startswith(self.CUSTOM):
            self.game_data.set_custom_character_table(choice[len(self.CUSTOM):])
        else:
            self.game_data.set_character_table(choice)

    def __show_table(self):
        """Select the line of the table in use; a custom file gets its own line, before "Custom file..."."""
        choice = self.__current_choice()
        self.table_box.blockSignals(True)
        for index in reversed(range(self.table_box.count())):
            if str(self.table_box.itemData(index)).startswith(self.CUSTOM):
                self.table_box.removeItem(index)
        if choice.startswith(self.CUSTOM):
            index = self.table_box.findData(self.PICK_TABLE)
            self.table_box.insertItem(index, f"Custom: {self.game_data.character_table_name}", choice)
            self.table_box.setItemData(index, choice[len(self.CUSTOM):], Qt.ItemDataRole.ToolTipRole)
        self.table_box.setCurrentIndex(self.table_box.findData(choice))
        self.table_box.blockSignals(False)

    def __character_table_changed(self, _index):
        choice = self.table_box.currentData()
        if choice == self.PICK_TABLE:
            folder = os.path.dirname(self.game_data.character_table_path)
            path = QFileDialog.getOpenFileName(
                self, "Character table file", folder,
                "Character table (*.txt);;All files (*)")[0]
            if not path:
                self.__show_table()
                return
            choice = self.CUSTOM + path
        if choice == self.__current_choice():
            self.__show_table()
            return
        lost = [self.tab_widget.tabText(i) for i in range(self.tab_widget.count())
                if self.tab_widget.widget(i).file_type != FileType.FONT and self.tab_widget.widget(i).dirty_state.dirty]
        if self.game_data.character_table_modified:
            lost.append(f"the edited {self.game_data.character_table_name} character table")
        if lost and QMessageBox.question(
                self, "ShumiTranslator - Character table",
                "Changing the character table reads the open files again. Not saved, these edits will be "
                "lost:<br>" + "<br>".join(lost) + "<br><br>Change it anyway?") != QMessageBox.StandardButton.Yes:
            self.__show_table()
            return
        previous = self.__current_choice()
        try:
            self.__use_table(choice)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "ShumiTranslator - Character table", f"Could not use this file:<br>{error}")
            self.__use_table(previous)
            self.__show_table()
            return
        self.__show_table()
        settings = getattr(self.file_registry, "settings", None)
        if settings is not None and not choice.startswith(self.CUSTOM):  # a custom file is opened each time
            settings.setValue(self.TABLE_SETTING, choice)
        self.__reread_tabs()

    def __reread_tabs(self):
        """Every tab with texts is built again with the character table in use: no tab keeps the old one."""
        for index in range(self.tab_widget.count()):
            pane = self.tab_widget.widget(index)
            if pane.file_type == FileType.FONT:  # its glyphs don't depend on it; it shows the new characters
                pane.character_table_changed()
                continue
            was_current = self.tab_widget.currentIndex() == index
            progress = self.__loading_dialog(pane.file_type, pane.file_loaded)
            rebuilt = ShumiFilePane(self.game_data, pane.file_type, pane.file_loaded,
                                    pane.file_mngrphd_loaded, progress=self.__report_progress(progress))
            progress.close()
            self.__track_edits(rebuilt)
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
