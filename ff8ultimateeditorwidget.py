import os
import sys
from datetime import datetime

from PyQt6.QtCore import Qt, QSettings, QEvent, QSize, QTimer
from PyQt6.QtGui import QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (QWidget, QMenuBar, QHBoxLayout, QVBoxLayout, QLabel, QFrame,
                             QStackedWidget, QSizePolicy, QApplication, QScrollArea, QMessageBox,
                             QToolButton)

from CCGroup.ccgroup import CCGroupWidget
from Chocoboy.chocoboywidget import ChocoboyWidget
from Cid.cidwidget import CidWidget
from Common.closedfileview import install_closed_file_view
from Common.dirtytracking import install_dirty_tracking, tool_has_unsaved_changes
from Common.fileregistry import FileRegistry
from Common.filetoolbarwidget import FileToolbarWidget
from Common.openedfilespanel import OpenedFilesPanel
from Common.wheelguard import WheelGuard
from ExeLauncher.delinglauncher import DelingLauncher
from ExeLauncher.doomtrainlauncher import DoomtrainLauncher
from ExeLauncher.ff8ultimatelauncher import FF8UltimateLauncher
from ExeLauncher.hynelauncher import HyneLauncher
from ExeLauncher.ifritguilauncher import IfritGuiLauncher
from ExeLauncher.junkshop import JunkshopLauncher
from ExeLauncher.quezacotllauncher import QuezacotlLauncher
from ExeLauncher.sirenlauncher import SirenLauncher
from Ifrit.ifritmonsterwidget import IfritMonsterWidget
from JumboCactuar.jumbocactuarwidget import JumboCactuarWidget
from Julia.juliawidget import JuliaWidget
from Odine.odinewidget import OdineWidget
from Piet.pietwidget import PietWidget
from Shiva.shivawidget import ShivaWidget
from Minimog.minimogwidget import MinimogWidget
from Kadowaki.kadowakiwidget import KadowakiWidget
from Seed.seedwidget import SeedWidget
from Siren.sirenwidget import SirenWidget
from Joker.jokerwidget import JokerWidget
from Junkshop.junkshopwidget import JunkshopWidget
from Alexander.alexanderwidget import AlexanderWidget
from Quezacotl.quezacotlwidget import QuezacotlWidget
from Hyne.hynewidget import HyneWidget
from ShumiTranslator.shumitranslator import ShumiTranslator
from SmallWidget.externaltoolwidget import ExternalToolWidget
from SmallWidget.fsextractwidget import FsExtractWidget
from TonberryShop.tonberryshop import TonberryShop
from ToolUpdate.toolupdatewidget import ToolUpdateWidget
from Zone.zonetabswidget import ZoneTabsWidget
from SolomonRing.solomonringwidget import SolomonRingWidget
from Fujin.fujinwidget import FujinWidget
from Watts.wattswidget import WattsWidget
from Xu.xuwidget import XuWidget


class _ToolHost(QWidget):
    """Holds the tool stack, filling the tool area, without reporting height-for-width.

    QStackedLayout answers height-for-width as the maximum over EVERY tool (hidden ones measured
    at stale widths), and a resizable scroll area stretches a height-for-width widget to that
    height: a word-wrapped label anywhere made the current tool far taller than the window, with
    an empty space to scroll into. The host only ever has the viewport's height; on_hint_changed
    is called whenever the current tool's minimum size may have changed."""

    def __init__(self, stack, on_hint_changed):
        super().__init__()
        self._stack = stack
        self._on_hint_changed = on_hint_changed
        stack.setParent(self)

    def resizeEvent(self, event):
        self._stack.setGeometry(self.rect())
        super().resizeEvent(event)
        self._on_hint_changed()  # a narrower window may now need the horizontal scrollbar

    def minimumSizeHint(self):
        return self._stack.minimumSizeHint()

    def sizeHint(self):
        return self._stack.sizeHint()

    def event(self, event):
        if event.type() == QEvent.Type.LayoutRequest:  # a tool's size hints changed
            self.updateGeometry()
            self._on_hint_changed()
        return super().event(event)


class FF8UltimateEditorWidget(QWidget):

    def __init__(self, resources_path='Resources', game_data_path='FF8GameData'):
        QWidget.__init__(self)

        # 1. Basic Window Setup
        if getattr(sys, 'frozen', False):  # Check if running as exe
            self.setup_logging()

        self._base_title = "FF8 ultimate editor"
        self.setWindowTitle(self._base_title)
        self.setWindowIcon(QIcon(os.path.join(resources_path, 'hobbitdur.ico')))

        self.settings = QSettings("HobbitDur", "FF8UltimateEditor")
        # The FF8 files are opened once and shared: a file opened in one tool is used by all
        # the tools working on it, without searching for it again.
        self.file_registry = FileRegistry(settings=self.settings)
        self._main_layout = QVBoxLayout(self)
        self.setLayout(self._main_layout)

        # 2. Define the Tool Options
        self.HOBBIT_OPTION_ITEMS = [
            "Ifrit (3D/Stat/AI/Seq/Texture)",
            "ShumiTranslator(All text editor)",
            "TonberryShop (Shop editor)",
            "CCGroup (Card value editor)",
            "Cid (Draw editor)",
            "SolomonRing (kernel.bin editor)",
            "Kadowaki (Item menu editor)",
            "Minimog (icon.sp1 editor)",
            "Seed (Field model viewer)",
            "Shiva (mngrp.bin editor: refine, SeeD tests, sprites)",
            "Alexander (Battle stage viewer)",
            "Julia (Sound editor)",
            "Siren (price.bin editor)",
            "Junkshop (mwepon.bin editor)",
            "Quezacotl (init.out editor)",
            "Odine (magsort.bin editor)",
            "Joker (sp2 sprite editor)",
            "Piet (mtmag.bin editor)",
            "Zone (mmag.bin / mmag2.bin editor)",
            "Fujin (Battle effect editor)",
            "Watts (r0win.dat victory editor)",
            "Xu (Scan camera editor)",
            "Chocoboy (World map script editor)",
            "JumboCactuar (scene.out encounter editor)",
            "Hyne (.ff8 save editor)"
        ]

        # Category = the game folder a tool's main file lives in (Battle/Field/Menu/Main), or a
        # catch-all for tools that don't map to exactly one folder: Multi (several folders - Cid's
        # exe+wmset, ShumiTranslator's many file types) and Other (no raw game file at all - Hyne's
        # save file lives outside the install). Fujin groups battle-effect resources from the
        # executable and extracted archives. Every entry must be an exact HOBBIT_OPTION_ITEMS string so a typo
        # fails loudly, not silently.
        self.CATEGORY_DEFINITIONS = [
            ("Battle", ["Ifrit (3D/Stat/AI/Seq/Texture)", "Alexander (Battle stage viewer)",
                        "Watts (r0win.dat victory editor)", "Xu (Scan camera editor)",
                        "JumboCactuar (scene.out encounter editor)", "Fujin (Battle effect editor)"]),
            ("Field", ["Seed (Field model viewer)", "CCGroup (Card value editor)"]),
            ("Menu", ["Shiva (mngrp.bin editor: refine, SeeD tests, sprites)", "Siren (price.bin editor)",
                      "Kadowaki (Item menu editor)", "Minimog (icon.sp1 editor)",
                      "Junkshop (mwepon.bin editor)", "Odine (magsort.bin editor)",
                      "Piet (mtmag.bin editor)", "Zone (mmag.bin / mmag2.bin editor)",
                      "TonberryShop (Shop editor)", "Joker (sp2 sprite editor)"]),
            ("World", ["Chocoboy (World map script editor)"]),
            ("Main", ["SolomonRing (kernel.bin editor)", "Quezacotl (init.out editor)",
                      "Julia (Sound editor)"]),
            ("Multi", ["Cid (Draw editor)", "ShumiTranslator(All text editor)"]),
            ("Other", ["Hyne (.ff8 save editor)"]),
        ]
        self.HIDDEN_CATEGORIES = set()  # every category has a tool and is shown in the selector

        # Completeness check: every tool must belong to exactly one category, and every category
        # entry must be a real tool name (HOBBIT_OPTION_ITEMS.index below raises otherwise).
        categorized_indices = {self.HOBBIT_OPTION_ITEMS.index(label)
                               for _category_name, tool_labels in self.CATEGORY_DEFINITIONS
                               for label in tool_labels}
        uncategorized = [label for index, label in enumerate(self.HOBBIT_OPTION_ITEMS)
                         if index not in categorized_indices]
        if uncategorized:
            raise RuntimeError(f"Tool(s) missing from CATEGORY_DEFINITIONS: {uncategorized}")

        # 3. Header: one category menu bar (Battle / Field / Menu / ...) - hover a category to
        # flyout its tools, click one to switch. The current tool is shown next to it (a menu bar
        # has no persistent "selected" display of its own once a menu closes) and checkmarked in
        # its own flyout.
        self._tool_menu_bar = QMenuBar()
        self._tool_menu_bar.setNativeMenuBar(False)  # stay embedded in the window, not the OS bar
        self._current_tool_label = QLabel()
        self._current_tool_label.setStyleSheet("font-weight: bold;")

        self._tool_actions = {}  # absolute HOBBIT_OPTION_ITEMS index -> its QAction (bolded when active)
        for category_name, tool_labels in self.CATEGORY_DEFINITIONS:
            if category_name in self.HIDDEN_CATEGORIES:
                continue
            category_menu = self._tool_menu_bar.addMenu(category_name)
            for label in tool_labels:
                absolute_index = self.HOBBIT_OPTION_ITEMS.index(label)
                action = category_menu.addAction(label)
                action.triggered.connect(lambda _checked=False, i=absolute_index: self._activate_tool(i))
                self._tool_actions[absolute_index] = action

        # Shared action available to every tool: extract a .fs archive recursively. It is file
        # management too, so it sits with the Import/Save buttons rather than the selector.
        self._fs_extract_button = FsExtractWidget(resources_path, game_data_path)
        # The opened files are shown in a collapsible inline panel (not a pop-up any more).
        self._opened_files_panel = OpenedFilesPanel(self.file_registry)

        # Left column: the "Hobbit tools" selector on top; under it the shared file-management
        # buttons (Import / Import complementary / Save + .fs extract); under those the
        # collapsible list of everything currently open.
        self._program_option_selector_row = QHBoxLayout()
        self._program_option_selector_row.addWidget(self._tool_menu_bar)
        self._program_option_selector_row.addWidget(self._current_tool_label)
        self._program_option_selector_row.addStretch(1)

        # The FileToolbarWidget is created below (it needs tool_stack); it is inserted at the
        # front of this row then, before the .fs extract button.
        self._file_buttons_row = QHBoxLayout()
        self._file_buttons_row.addWidget(self._fs_extract_button)
        self._file_buttons_row.addStretch(1)

        self._program_option_layout = QVBoxLayout()
        self._program_option_layout.addLayout(self._program_option_selector_row)
        self._program_option_layout.addLayout(self._file_buttons_row)
        self._program_option_layout.addWidget(self._opened_files_panel)
        # Keep the selector / file buttons / opened-files rows packed at the top; spare height in
        # this column (e.g. when the opened-files list is collapsed) goes here, not between rows.
        self._program_option_layout.addStretch(1)

        # 4. Header: External Tool Buttons
        self._external_program_title = QLabel("External program:")
        self._tool_update_widget = ToolUpdateWidget(self.settings, self.tools_to_update)

        # Initialize External Tool Buttons
        self._self_button = ExternalToolWidget(os.path.join(resources_path, 'hobbitdur.ico'), self._launch_FF8Ultimate, "Launch FF8UltimateEditor", show_checkbox=False)
        self._ifrit_gui_button = ExternalToolWidget(os.path.join(resources_path, 'ifritGui.ico'), self._launch_ifritGui, "Launch original ifrit soft")
        self._Quezacotl_button = ExternalToolWidget(os.path.join(resources_path, 'Quezacotl.ico'), self._launch_Quezacotl, "Launch Quezacotl (init.out editor)")
        self._siren_button = ExternalToolWidget(os.path.join(resources_path, 'siren.ico'), self._launch_siren, "Launch siren (price.bin editor)")
        self._junkshop_button = ExternalToolWidget(os.path.join(resources_path, 'junkshop.ico'), self._launch_junkshop, "Launch junkshop (mweapon.bin editor)")
        self._doomtrain_button = ExternalToolWidget(os.path.join(resources_path, 'doomtrain.ico'), self._launch_doomtrain, "Launch doomtrain (kernel.bin editor)")
        self._deling_button = ExternalToolWidget(os.path.join(resources_path, 'deling.ico'), self._launch_deling, "Launch deling (Archive editor)")
        self._hyne_button = ExternalToolWidget(os.path.join(resources_path, 'hyne.ico'), self._launch_hyne, "Launch hyne (Save editor)")
        self._ffnx_button = ExternalToolWidget(os.path.join(resources_path, 'ffnx.ico'), self._show_ffnx_effects,
                                               "FFNx's effect sources (Fujin's effect part tabs): tick, then Update "
                                               "downloads them and builds Fujin's effect recorder with them")

        # Temporarily hidden (kept in case they get re-enabled later)
        #self._Quezacotl_button.hide()
        #self._siren_button.hide()
        #self._junkshop_button.hide()
        #self._doomtrain_button.hide()

        # External Program Layout Assembly
        self._external_program_layout = QHBoxLayout()
        self._external_program_layout.addWidget(self._tool_update_widget, alignment=Qt.AlignmentFlag.AlignCenter)
        self._external_program_layout.addWidget(self._external_program_title, alignment=Qt.AlignmentFlag.AlignCenter)
        self._external_program_layout.addWidget(self._self_button, alignment=Qt.AlignmentFlag.AlignCenter)
        self._external_program_layout.addWidget(self._ifrit_gui_button, alignment=Qt.AlignmentFlag.AlignCenter)
        self._external_program_layout.addWidget(self._Quezacotl_button, alignment=Qt.AlignmentFlag.AlignCenter)
        self._external_program_layout.addWidget(self._siren_button, alignment=Qt.AlignmentFlag.AlignCenter)
        self._external_program_layout.addWidget(self._junkshop_button, alignment=Qt.AlignmentFlag.AlignCenter)
        self._external_program_layout.addWidget(self._doomtrain_button, alignment=Qt.AlignmentFlag.AlignCenter)
        self._external_program_layout.addWidget(self._hyne_button, alignment=Qt.AlignmentFlag.AlignCenter)
        self._external_program_layout.addWidget(self._deling_button, alignment=Qt.AlignmentFlag.AlignCenter)
        self._external_program_layout.addWidget(self._ffnx_button, alignment=Qt.AlignmentFlag.AlignCenter)
        self._external_program_layout.addStretch(1)

        # Combine Header Layouts
        self._enhance_layout = QHBoxLayout()
        self._enhance_layout.addLayout(self._program_option_layout)
        self._enhance_layout.addLayout(self._external_program_layout)
        self._enhance_layout.addStretch(1)

        self._enhance_container = QWidget()
        self._enhance_container.setLayout(self._enhance_layout)
        # The header is a fixed strip: keep it at its natural height so it never eats the window in
        # full screen (its contents would otherwise float in the vertical middle). All the spare
        # vertical space goes to the tool stack below (see the main layout assembly).
        self._enhance_container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        # Separator Line
        self._enhance_end_separator_line = QFrame()
        self._enhance_end_separator_line.setFrameStyle(QFrame.Shape.HLine | QFrame.Shadow.Sunken)
        self._enhance_end_separator_line.setLineWidth(1)

        # 5. Middle Section: Tool Widgets & QStackedWidget
        self.tool_stack = QStackedWidget()

        # Initialize internal tools
        self._shumi_translator_widget = ShumiTranslator(icon_path=os.path.join(resources_path), game_data_folder=os.path.join(game_data_path), file_registry=self.file_registry)
        self._tonberry_shop_widget = TonberryShop(resource_folder=os.path.join(resources_path), file_registry=self.file_registry,
                                                 game_data_folder=os.path.join(game_data_path))
        self._ccgroup_widget = CCGroupWidget(icon_path=os.path.join(resources_path), game_data_path=os.path.join(game_data_path), settings=self.settings, file_registry=self.file_registry)
        self._cid_widget = CidWidget(icon_path=os.path.join(resources_path), game_data_folder=os.path.join(game_data_path), file_registry=self.file_registry)
        self._solomonring_widget = SolomonRingWidget(game_data_folder=os.path.join(game_data_path), file_registry=self.file_registry,
                                                     settings=self.settings)
        self._ifrit_widget = IfritMonsterWidget( settings=self.settings, icon_path=resources_path, game_data_folder=game_data_path, file_registry=self.file_registry)
        # SolomonRing's damage formulas can use a monster opened in Ifrit
        self._solomonring_widget.set_monster_provider(self._ifrit_widget.battle_setup_monsters)
        self._kadowaki_widget = KadowakiWidget(icon_path=os.path.join(resources_path), game_data_folder=os.path.join(game_data_path), file_registry=self.file_registry)
        self._minimog_widget = MinimogWidget(icon_path=os.path.join(resources_path), game_data_folder=os.path.join(game_data_path), file_registry=self.file_registry)
        self._seed_widget = SeedWidget(icon_path=os.path.join(resources_path), settings=self.settings, file_registry=self.file_registry)
        self._shiva_widget = ShivaWidget(icon_path=os.path.join(resources_path), game_data_folder=os.path.join(game_data_path), file_registry=self.file_registry)
        self._alexander_widget = AlexanderWidget(icon_path=os.path.join(resources_path), settings=self.settings, file_registry=self.file_registry, game_data_folder=os.path.join(game_data_path))
        self._julia_widget = JuliaWidget(icon_path=os.path.join(resources_path), game_data_folder=os.path.join(game_data_path), file_registry=self.file_registry)
        self._siren_widget = SirenWidget(icon_path=os.path.join(resources_path), game_data_folder=os.path.join(game_data_path), file_registry=self.file_registry)
        self._junkshop_widget = JunkshopWidget(icon_path=os.path.join(resources_path), game_data_folder=os.path.join(game_data_path), file_registry=self.file_registry)
        self._quezacotl_widget = QuezacotlWidget(icon_path=os.path.join(resources_path), game_data_folder=os.path.join(game_data_path), file_registry=self.file_registry)
        self._odine_widget = OdineWidget(icon_path=os.path.join(resources_path), game_data_folder=os.path.join(game_data_path), file_registry=self.file_registry)
        self._joker_widget = JokerWidget(icon_path=os.path.join(resources_path), game_data_folder=os.path.join(game_data_path), file_registry=self.file_registry)
        self._piet_widget = PietWidget(icon_path=os.path.join(resources_path), game_data_folder=os.path.join(game_data_path), file_registry=self.file_registry)
        # Zone is now a two-tab tool: mmag.bin (magazines) + mmag2.bin (Chocobo World)
        self._zone_widget = ZoneTabsWidget(icon_path=os.path.join(resources_path), game_data_folder=os.path.join(game_data_path), file_registry=self.file_registry)
        self._fujin_widget = FujinWidget(icon_path=os.path.join(resources_path), game_data_folder=os.path.join(game_data_path), file_registry=self.file_registry)
        self._watts_widget = WattsWidget(icon_path=os.path.join(resources_path), game_data_folder=os.path.join(game_data_path), file_registry=self.file_registry)
        self._xu_widget = XuWidget(icon_path=os.path.join(resources_path), game_data_folder=os.path.join(game_data_path), file_registry=self.file_registry)
        self._chocoboy_widget = ChocoboyWidget(icon_path=os.path.join(resources_path), game_data_folder=os.path.join(game_data_path), file_registry=self.file_registry)
        self._jumbo_cactuar_widget = JumboCactuarWidget(icon_path=os.path.join(resources_path), game_data_folder=os.path.join(game_data_path), file_registry=self.file_registry)
        self._hyne_widget = HyneWidget(icon_path=os.path.join(resources_path), game_data_folder=os.path.join(game_data_path), file_registry=self.file_registry)


        # Add to Stack (MUST match HOBBIT_OPTION_ITEMS order)
        self.tool_stack.addWidget(self._ifrit_widget) # Index 0
        self.tool_stack.addWidget(self._shumi_translator_widget)  # Index 1
        self.tool_stack.addWidget(self._tonberry_shop_widget)  # Index 2
        self.tool_stack.addWidget(self._ccgroup_widget)  # Index 3
        self.tool_stack.addWidget(self._cid_widget)  # Index 4
        self.tool_stack.addWidget(self._solomonring_widget) # Index 5
        self.tool_stack.addWidget(self._kadowaki_widget) # Index 6
        self.tool_stack.addWidget(self._minimog_widget) # Minimog (icon.sp1), keep right after Kadowaki in HOBBIT_OPTION_ITEMS
        self.tool_stack.addWidget(self._seed_widget) # Index 7
        self.tool_stack.addWidget(self._shiva_widget) # Index 8, took the place of Pandemona: its refine editing is a tab of Shiva now
        self.tool_stack.addWidget(self._alexander_widget) # Index 9
        self.tool_stack.addWidget(self._julia_widget) # Index 10
        self.tool_stack.addWidget(self._siren_widget) # Index 11
        self.tool_stack.addWidget(self._junkshop_widget) # Index 12
        self.tool_stack.addWidget(self._quezacotl_widget) # Index 13
        self.tool_stack.addWidget(self._odine_widget) # Index 14
        self.tool_stack.addWidget(self._joker_widget) # Index 16
        self.tool_stack.addWidget(self._piet_widget) # Index 17
        self.tool_stack.addWidget(self._zone_widget) # Index 19
        self.tool_stack.addWidget(self._fujin_widget) # Index 21
        self.tool_stack.addWidget(self._watts_widget) # Watts (r0win.dat)
        self.tool_stack.addWidget(self._xu_widget) # Xu (battle_scan_cameras.bin)
        self.tool_stack.addWidget(self._chocoboy_widget) # Chocoboy (wmsetxx.obj world map scripts)
        self.tool_stack.addWidget(self._jumbo_cactuar_widget) # JumboCactuar (scene.out encounters)
        self.tool_stack.addWidget(self._hyne_widget) # Hyne (.ff8 save editor), keep last in HOBBIT_OPTION_ITEMS
        self._piet_widget.view_in_zone_requested.connect(self._view_mmag_entry_in_zone)

        # Give every binding-based tool an unsaved-changes tracker (tool.dirty_state) so the window
        # title's * reflects real edits. Tools that load through hooks (Ifrit/Alexander/...) already
        # report changes via can_save_folder(), so they don't need one.
        # Removing a fixed-file tool's file from the Opened files panel clears its view. Tools
        # that already drop their own files are left out (ShumiTranslator closes its tabs); the
        # tabbed tools get it per tab, on the page that edits the file, so their other tab stays.
        # Ifrit's only binding is its complementary kernel.bin: its .dat files close on their own.
        own_close = (self._shumi_translator_widget, self._ccgroup_widget, self._zone_widget,
                     self._ifrit_widget, self._fujin_widget)
        for index in range(self.tool_stack.count()):
            tool = self.tool_stack.widget(index)
            if (callable(getattr(tool, "file_bindings", None)) and tool not in own_close
                    and tool.layout() is not None):
                install_closed_file_view(tool)
        install_closed_file_view(self._zone_widget.mmag_widget)
        install_closed_file_view(self._zone_widget.mmag2_widget)
        install_closed_file_view(self._fujin_widget.camera_editor,
                                 [self._fujin_widget.camera_editor.exe_binding])
        install_closed_file_view(self._ccgroup_widget.scroll_widget,
                                 [self._ccgroup_widget.exe_binding])
        for index in range(self.tool_stack.count()):
            tool = self.tool_stack.widget(index)
            # Ifrit tracks its own unsaved edits per file (undo stacks, '*' in its file list).
            if callable(getattr(tool, "file_bindings", None)) and tool is not self._ifrit_widget:
                install_dirty_tracking(tool)

        # QStackedLayout includes hidden pages in its minimum size. Only the active tool
        # should determine the scrollable content's size, rather than the largest editor.
        self._tool_size_policies = {}
        self.tool_stack.currentChanged.connect(self._size_stack_for_current_tool)
        self._size_stack_for_current_tool()

        saved_tool_index = self.settings.value("main/program_option", defaultValue=0, type=int)
        if not 0 <= saved_tool_index < len(self.HOBBIT_OPTION_ITEMS):
            saved_tool_index = 0
        self._activate_tool(saved_tool_index)

        # Shared file toolbar: Import / Import read-only / Save acting on the active tool's
        # declared files (its file_bindings()), so which file is opened/saved follows the
        # current tool and sub-tab from one common set of buttons. It sits under the tool
        # selector, before the opened-files list.
        self._file_toolbar = FileToolbarWidget(self.tool_stack, self.file_registry, resources_path)
        self._file_buttons_row.insertWidget(0, self._file_toolbar)

        # One global Ctrl+S for every tool: it "clicks" the shared Save button, which saves the
        # active tool's file(s) and does nothing when there's nothing to save (the button is
        # disabled). No tool needs its own Save shortcut anymore.
        self._save_shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        self._save_shortcut.activated.connect(self._file_toolbar.save_button.click)

        # One global Ctrl+Z / Ctrl+Shift+Z routed to the active tool's undo()/redo() (a no-op for
        # tools that don't implement them yet). A window-level QShortcut is NOT enough here: a
        # focused spin/text field (QSpinBox, QLineEdit, QTextEdit...) issues a ShortcutOverride for
        # Ctrl+Z to claim it for its own field-undo, so the shortcut only fired when focus was on
        # the bare main window. Instead we filter key presses at the QApplication level - the app
        # filter sees the KeyPress before the focused field does, so it wins regardless of focus.
        QApplication.instance().installEventFilter(self)

        # The mouse wheel scrolls forms instead of changing the combo/spin box under the cursor.
        self._wheel_guard = WheelGuard(self)
        QApplication.instance().installEventFilter(self._wheel_guard)

        # Show a "*" in the window title whenever the active tool has something to save.
        self._file_toolbar.save_state_changed.connect(self._update_title_save_marker)
        self._update_title_save_marker(self._file_toolbar.save_button.isEnabled())

        # 6. The wide header and a tool wider than the window scroll horizontally instead of
        # forcing the window beyond the desktop. Never vertically: every tool fits a 1080p screen,
        # and the tool area's minimum height follows the current tool (_fit_tool_height).
        self._header_scroll = QScrollArea()
        self._header_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._header_scroll.setWidgetResizable(True)
        self._header_scroll.setWidget(self._enhance_container)
        self._header_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self._header_scroll.setMaximumHeight(180)
        self._fit_header_height()
        self._tool_scroll = QScrollArea()
        self._tool_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._tool_scroll.setWidgetResizable(True)
        self._tool_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._tool_host = _ToolHost(self.tool_stack, self._fit_tool_height)
        self._tool_scroll.setWidget(self._tool_host)
        self._fit_tool_height()
        # The separator under the header carries a small button that hides the whole header
        # (tool selector, file buttons, opened files, external programs) to give the tool more
        # room; Ctrl+S and the other window shortcuts keep working while it is hidden.
        self._header_toggle = QToolButton()
        self._header_toggle.setAutoRaise(True)
        self._header_toggle.setStyleSheet("QToolButton{font-size:10px; padding:0 6px;}")
        self._header_toggle.clicked.connect(lambda: self.set_header_hidden(not self._header_scroll.isHidden()))
        separator_row = QHBoxLayout()
        separator_row.setContentsMargins(0, 0, 0, 0)
        separator_row.setSpacing(4)
        separator_row.addWidget(self._header_toggle)
        separator_row.addWidget(self._enhance_end_separator_line, 1)
        # The header's height follows the opened-files list (expanded/collapsed, more or fewer
        # files). Refit once the panel has laid itself out, measuring afresh: the size the header
        # had cached was still the expanded one, which left the strip at its expanded height.
        def refit_header():
            self._enhance_layout.invalidate()
            self._fit_header_height()

        def refit_header_later(*_):
            QTimer.singleShot(0, refit_header)
        self._opened_files_panel.header_button.toggled.connect(refit_header_later)
        self.file_registry.file_changed.connect(refit_header_later)
        self.file_registry.batch_finished.connect(refit_header_later)
        self._main_layout.addWidget(self._header_scroll)
        self._main_layout.addLayout(separator_row)
        self._main_layout.addWidget(self._tool_scroll, 1)
        self.set_header_hidden(False)                    # always shown at start, not remembered

        # 7. Initialize Launchers
        self.ifritGui_launcher = IfritGuiLauncher(os.path.join("ExternalTools", "IfritGui", "Ifrit.exe"), callback=None)
        self.Quezacotl_launcher = QuezacotlLauncher(os.path.join("ExternalTools", "Quezacotl", "Quezacotl.exe"), callback=None)
        self.siren_launcher = SirenLauncher(os.path.join("ExternalTools", "Siren", "Siren.exe"), callback=None)
        self.junkshop_launcher = JunkshopLauncher(os.path.join("ExternalTools", "Junkshop", "Junkshop.exe"), callback=None)
        self.doomtrain_launcher = DoomtrainLauncher(os.path.join("ExternalTools", "Doomtrain", "Doomtrain.exe"), callback=None)
        self.deling_launcher = DelingLauncher(os.path.join("ExternalTools", "Deling", "Deling.exe"), callback=None)
        self.hyne_launcher = HyneLauncher(os.path.join("ExternalTools", "Hyne", "Hyne.exe"), callback=None)
        ff8ultimate_exe_name = "FF8UltimateEditor.exe" if sys.platform == "win32" else "FF8UltimateEditor"
        self.ff8ultimate_launcher = FF8UltimateLauncher(os.path.join("", ff8ultimate_exe_name), callback=None)

        # Final setup for header height and initial state
        self._tool_update_widget.progress.show()
        self._tool_update_widget.progress_current_download.show()
        #self._enhance_container.setFixedHeight(self._enhance_container.sizeHint().height())
        self._tool_update_widget.progress.hide()
        self._tool_update_widget.progress_current_download.hide()

        self._resize_for_screen()

    def _size_stack_for_current_tool(self):
        current = self.tool_stack.currentWidget()
        for index in range(self.tool_stack.count()):
            tool = self.tool_stack.widget(index)
            policy = self._tool_size_policies.setdefault(tool, tool.sizePolicy())
            if tool is current:
                tool.setSizePolicy(policy)
            else:
                tool.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.tool_stack.updateGeometry()
        self._fit_tool_height()

    def _fit_tool_height(self):
        # No vertical scrollbar: the window may not get shorter than the current tool needs
        # (plus the horizontal scrollbar when the tool is wider than the window).
        scroll = getattr(self, "_tool_scroll", None)
        if scroll is None:  # tools switched before the tool area exists
            return
        height = self._tool_host.minimumSizeHint().height()
        if self._tool_host.minimumSizeHint().width() > scroll.viewport().width():
            height += scroll.horizontalScrollBar().sizeHint().height()
        if scroll.minimumHeight() != height:
            scroll.setMinimumHeight(height)

    def _resize_for_screen(self):
        # Client size leaves room for window decorations and a taskbar on a 720p desktop.
        # This is an initial size only: larger monitors can still expand/maximize the window.
        initial = QSize(1200, 640)
        screen = self.screen()
        if screen is not None:
            available = screen.availableGeometry().size() - QSize(40, 80)
            initial = initial.boundedTo(available.expandedTo(QSize(1, 1)))
        self.resize(initial)

    def _fit_header_height(self):
        # Exactly the header's natural height, reserving the horizontal scrollbar's so the header
        # needs no vertical scrolling; a long expanded file list scrolls within the bounded strip.
        # A FIXED height, not only a minimum: expanding the opened-files list raised the minimum,
        # and collapsing it again left the strip that tall.
        height = (self._enhance_container.sizeHint().height()
                  + self._header_scroll.horizontalScrollBar().sizeHint().height())
        if self._header_scroll.height() != min(180, height) or self._header_scroll.minimumHeight() != min(180, height):
            self._header_scroll.setFixedHeight(min(180, height))

    def set_header_hidden(self, hidden: bool):
        """Hide/show the whole header strip (for this session: the tool starts with it shown)."""
        self._header_scroll.setVisible(not hidden)
        self._header_toggle.setText("▾ Show toolbar" if hidden else "▴ Hide toolbar")
        self._header_toggle.setToolTip(
            "Show the tool selector, the file buttons and the opened files again" if hidden else
            "Hide the tool selector, the file buttons and the opened files to give the tool more "
            "room (Ctrl+S still saves)")

    def _launch_ifritGui(self):
        self.ifritGui_launcher.launch()

    def _launch_Quezacotl(self):
        self.Quezacotl_launcher.launch()

    def _launch_junkshop(self):
        self.junkshop_launcher.launch()

    def _launch_siren(self):
        self.siren_launcher.launch()

    def _launch_doomtrain(self):
        self.doomtrain_launcher.launch()

    def _launch_deling(self):
        self.deling_launcher.launch()

    def _launch_hyne(self):
        self.hyne_launcher.launch()

    def _launch_FF8Ultimate(self):
        self.ff8ultimate_launcher.launch()

    def _activate_tool(self, absolute_index):
        """Switch to the tool at HOBBIT_OPTION_ITEMS[absolute_index]: a category flyout's menu
        action, the startup restore of the last-used tool, or a cross-navigation request (Piet's
        "View in Zone"). Bolds it in its category's flyout and updates the current-tool label
        (a menu bar shows nothing once its menu closes, unlike a combo box)."""
        previous_index = getattr(self, "_current_tool_index", None)
        if previous_index in self._tool_actions:
            self._set_action_bold(self._tool_actions[previous_index], False)
        self._current_tool_index = absolute_index
        self._set_action_bold(self._tool_actions[absolute_index], True)
        self._current_tool_label.setText(self.HOBBIT_OPTION_ITEMS[absolute_index])
        self.tool_stack.setCurrentIndex(absolute_index)
        self.settings.setValue("main/program_option", absolute_index)

    @staticmethod
    def _set_action_bold(action, bold):
        font = action.font()
        font.setBold(bold)
        action.setFont(font)

    def unsaved_tool_names(self):
        """The tools (as named in the tool menu) holding edits not written to disk yet."""
        return [self.HOBBIT_OPTION_ITEMS[index] for index in range(self.tool_stack.count())
                if tool_has_unsaved_changes(self.tool_stack.widget(index))]

    def closeEvent(self, event):
        """Closing with unsaved edits asks first: Discard closes and loses them, Cancel keeps the
        window open so they can still be saved."""
        unsaved = self.unsaved_tool_names()
        if unsaved:
            listed = "\n".join(f"  \u2022 {name}" for name in unsaved)
            answer = QMessageBox.warning(
                self, "Unsaved changes",
                f"These tools have unsaved changes:\n{listed}\n\n"
                "Close anyway and discard them?",
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel)
            if answer != QMessageBox.StandardButton.Discard:
                event.ignore()
                return
        super().closeEvent(event)

    def _update_title_save_marker(self, has_unsaved):
        """Prefix the window title with '*' while the active tool has something to save."""
        self.setWindowTitle(f"*{self._base_title}" if has_unsaved else self._base_title)

    def eventFilter(self, obj, event):
        """App-level Ctrl+Z / Ctrl+Shift+Z (and Ctrl+Y) -> active tool undo/redo. Installed on the
        QApplication so it catches the KeyPress before a focused spin/text field can consume it for
        its own field-level undo. Left alone while a modal dialog is up (its fields keep their own
        Ctrl+Z), and only acts when the active tool actually implements the method.

        Text editors (the AI IfritSeq/IfritCode areas, name fields...) get FALL-THROUGH: while the
        focused text field still has its own undo history, Ctrl+Z does that field's native
        keystroke undo; only once its history is exhausted (or focus isn't a text field) does it
        reach the tool's snapshot undo. So typing in the code editor undoes character by character,
        as in any editor, while structural edits still undo at the tool level."""
        if (event.type() == QEvent.Type.LayoutRequest and obj is self._enhance_container
                and hasattr(self, "_header_scroll")):
            self._fit_header_height()
        if event.type() == QEvent.Type.KeyPress and QApplication.activeModalWidget() is None:
            mods = event.modifiers()
            if mods & Qt.KeyboardModifier.ControlModifier:
                key = event.key()
                shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
                redo = key == Qt.Key.Key_Y or (key == Qt.Key.Key_Z and shift)
                method = "redo" if redo else ("undo" if key == Qt.Key.Key_Z else None)
                if method is not None:
                    if self._focused_text_editor_can(redo):
                        return False   # let the focused text field do its own keystroke undo/redo
                    if self._route_to_active_tool(method):
                        return True    # consumed: don't let the focused field also undo
        return super().eventFilter(obj, event)

    @staticmethod
    def _focused_text_editor_can(redo):
        """True if the widget with keyboard focus is a text editor that still has its own undo (or
        redo) available - meaning Ctrl+Z should go to it, not the tool. Covers QLineEdit and
        QTextEdit/QPlainTextEdit (also when focus is on their internal viewport)."""
        from PyQt6.QtWidgets import QLineEdit, QTextEdit, QPlainTextEdit
        w = QApplication.focusWidget()
        editor = w
        while editor is not None and not isinstance(editor, (QLineEdit, QTextEdit, QPlainTextEdit)):
            editor = editor.parentWidget()
        if editor is None or not editor.isEnabled() or editor.isReadOnly():
            return False
        if isinstance(editor, (QTextEdit, QPlainTextEdit)):
            if not editor.isUndoRedoEnabled():
                return False
            doc = editor.document()
            return doc.isRedoAvailable() if redo else doc.isUndoAvailable()
        # QLineEdit
        try:
            return editor.isRedoAvailable() if redo else editor.isUndoAvailable()
        except AttributeError:
            return True   # older Qt: assume the field can handle its own edit undo

    def _route_to_active_tool(self, method_name):
        """Call method_name() on the currently shown tool if it has one (Ctrl+Z/Ctrl+Shift+Z ->
        undo/redo). Returns True if the active tool handled it, False otherwise."""
        tool = self.tool_stack.currentWidget()
        fn = getattr(tool, method_name, None)
        if callable(fn):
            fn()
            return True
        return False

    def _view_mmag_entry_in_zone(self, entry_index):
        """Switch to the Zone tool and select an mmag.bin entry, requested from the Piet tool."""
        zone_index = self.HOBBIT_OPTION_ITEMS.index("Zone (mmag.bin / mmag2.bin editor)")
        self._activate_tool(zone_index)
        # Zone is tabbed now: focus the mmag.bin tab before selecting the entry
        self._zone_widget.tabs.setCurrentWidget(self._zone_widget.mmag_widget)
        self._zone_widget.mmag_widget.select_entry(entry_index)

    def _show_ffnx_effects(self):
        """FFNx's effect sources: what is installed, and how to get them."""
        from Fujin.effectparts import ffnx_sources, recorder_has_ports
        from PyQt6.QtWidgets import QMessageBox
        from Fujin.recorderbuild import recorder_build
        source = ffnx_sources()
        installed = (f"Installed: {source[0]}, {source[1]} (commit {source[2][:10]})." if source else
                     "Not installed: tick the box above this button, then Update.")
        build = recorder_build()
        recorder = ("Fujin's effect recorder is being built with them." if build.building else
                    "Fujin's effect recorder includes them: Fujin shows the part tabs (Choreography)."
                    if recorder_has_ports() else
                    "Fujin's effect recorder does not include them yet" + (f": {build.error}" if build.error else "."))
        QMessageBox.information(self, "FFNx effect sources",
                                "FFNx's battle effects ported to C++ (src/ff8/battle/fx), built into Fujin's effect "
                                "recorder: Fujin's Choreography shows an effect part by part with its parameters "
                                f"(Cure, Potion, Hypnotize).\n\n{installed}\n{recorder}")

    def tools_to_update(self):
        tool_list = []
        if self._ifrit_gui_button.update_selected:
            tool_list.append("IfritGui")
        if self._Quezacotl_button.update_selected:
            tool_list.append("Quezacotl")
        if self._siren_button.update_selected:
            tool_list.append("Siren")
        if self._junkshop_button.update_selected:
            tool_list.append("Junkshop")
        if self._doomtrain_button.update_selected:
            tool_list.append("Doomtrain")
        if self._hyne_button.update_selected:
            tool_list.append("Hyne")
        if self._deling_button.update_selected:
            tool_list.append("Deling")
            tool_list.append("DelingCli")
        tool_list.append("VincentTim")
        if self._ffnx_button.update_selected:
            tool_list.append("FFNxEffects")  # FFNx's effect sources: built into Fujin's effect recorder
        return tool_list

    @staticmethod
    def setup_logging():
        # Create logs directory
        if not os.path.exists('logs'):
            os.makedirs('logs')

        # Log file with timestamp
        log_file = f"logs/FF8UltimateEditor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

        # Redirect stdout and stderr to file
        sys.stdout = open(log_file, 'w')
        sys.stderr = sys.stdout

    def debug_widget_sizes(self):
        print("\n--- WIDGET HEIGHT DEBUGGER ---")
        widgets_to_check = [
            ("Main Window", self),
            ("Header Container", self._enhance_container),
            ("Separator Line", self._enhance_end_separator_line),
            ("Stacked Widget", self.tool_stack),
            ("IfritAI", self._ifritAI_widget),
            ("IfritXlsx", self._ifritxlsx_widget),
            ("IfritTexture", self._ifrittexture_widget),
            ("Ifrit3D", self._ifrit3d_widget),
            ("SolomonRing", self._solomonring_widget),
            # Add any others you suspect here
        ]

        for name, widget in widgets_to_check:
            # sizeHint: What the widget PREFERS to be
            # minimumSize: The absolute limit the widget CANNOT go below
            # frameGeometry: What the widget currently IS in pixels
            hint = widget.sizeHint().height()
            min_h = widget.minimumSize().height()
            actual = widget.frameGeometry().height()

            print(f"{name.ljust(20)} | Actual: {actual}px | Hint: {hint}px | Min: {min_h}px")
        print("------------------------------\n")
