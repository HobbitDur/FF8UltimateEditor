import os
import pathlib
from PyQt6.QtCore import QSettings, Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QMessageBox, QCheckBox, QProgressDialog, QApplication,
    QListWidget, QSplitter, QFileDialog, QComboBox, QLineEdit, QSpinBox,
    QDoubleSpinBox, QAbstractButton, QPlainTextEdit, QTextEdit, QStackedWidget,
    QSizePolicy
)
from Common.fileregistry import FileRegistry
from Common.undo import UndoStack
from FF8GameData.dat.monsteranalyser import GarbageFileError
from FF8GameData.dat.animloopdetector import find_character_weapon_file_list
from Ifrit.IfritAI.ifritaiwidget import IfritAIWidget
from Ifrit.ifritmanager import IfritManager
from Ifrit.fpsbatchdialog import (FpsBatchDialog, FpsBatchReportDialog,
                                  select_battle_model_file_list)
from Ifrit.IfritDynamicTexture.ifritdynamictexturewidget import IfritDynamicTextureWidget
from Ifrit.IfritSeq.ifritseqwidget import IfritSeqWidget
from Ifrit.IfritCameraSeq.ifritcameraseqwidget import IfritCameraSeqWidget, _CAMERA_SECTION_BY_ENTITY
from Ifrit.IfritCameraSeq.camerapreview import CameraPreviewPanel
from Ifrit.IfritDynamicTexture.texturepreviewwidget import TexturePreviewWidget
from FF8GameData.monsterdata import EntityType
from Ifrit.Ifrit3D.ifrit3dwidget import Ifrit3DWidget
from Ifrit.IfritTexture.ifrittexturewidget import IfritTextureWidget
from Ifrit.IfritXlsx.ifritxlsxwidget import IfritXlsxWidget
from Ifrit.IfritStat.ifritstatwidget import IfritStatWidget
from Ifrit.IfritStat.ifritmonsternamewidget import IfritMonsterNameWidget
from Ifrit.IfritBattleText.ifritbattletextwidget import IfritBattleTextWidget

# Which .dat section holds the animation sequence per entity type (character-with-weapon has
# none - its Sequence tab stays disabled). Camera's per-type section is _CAMERA_SECTION_BY_ENTITY.
# Matches MonsterAnalyser.analyse_loaded_data's per-type __analyze_sequence_animation() calls -
# keep in sync with that if a new entity type or section layout is added.
_SEQ_SECTION_BY_ENTITY = {
    EntityType.MONSTER: 5,
    EntityType.WEAPON: 4,
    EntityType.WEAPON_NO_ANIM: 2,       # reduced weapon (Zell/Kiros unarmed): 5 real sections
    EntityType.CHARACTER_NO_WEAPON: 6,  # Edea (d7c016): body carries the seq VM itself
}

# Which .dat section holds dynamic-texture data. Only wired up for monsters today - the wiki
# documents section 4 as a real (eyeblink) dynamic-texture section on character bodies too,
# but MonsterAnalyser doesn't parse it there yet, so the tab stays disabled for everything else
# rather than show an empty/non-functional editor.
_DYNAMIC_TEXTURE_SECTION_BY_ENTITY = {
    EntityType.MONSTER: 4,
}

# Which entity types carry real info_stat + AI/battle_script data (Stat/StatExcel/AI/Battle
# text tabs). MONSTER_NO_MODEL has both despite having no model at all - see
# EntityType.MONSTER_NO_MODEL. Static Texture stays MONSTER-only below: MONSTER_NO_MODEL has
# no texture section either.
_STAT_AI_CAPABLE_ENTITY_TYPES = {EntityType.MONSTER, EntityType.MONSTER_NO_MODEL}

# 3D always starts at section 1, but a reduced weapon (WEAPON_NO_ANIM) has no separate
# skeleton/animation sections - it's geometry-only (section 1), reusing the body's skeleton
# and animation pool. Every other type carries skeleton+geometry+animation as sections 1-3.
# MONSTER_NO_MODEL is deliberately absent - it has no model sections whatsoever, so the tab
# is hidden rather than shown empty.
_3D_SECTIONS_BY_ENTITY = {
    EntityType.MONSTER: "1/2/3",
    EntityType.WEAPON: "1/2/3",
    EntityType.CHARACTER: "1/2/3",
    EntityType.CHARACTER_NO_WEAPON: "1/2/3",
    EntityType.WEAPON_NO_ANIM: "1",
}


def _shrink_stack_to_current(stack, policy_cache):
    """Exclude every non-current page of `stack` (a QTabWidget or QStackedWidget) from its own
    minimumSizeHint. Both report the size of their LARGEST page as their own - even for a page
    that's hidden or has never been shown - so a single wide page permanently floors the whole
    widget's width. That floor then propagates out through whatever container holds it (here, the
    multi-file shell's QSplitter), pinning the file list to a sliver regardless of window size.
    Giving each non-current page an Ignored size policy excludes it from that computation; the
    real policy - captured once per widget in `policy_cache` - is restored when a page becomes
    current again. Used at three levels: a pane's own tabs, its nested Stat/AI sub-tabs, and the
    shell's stack of per-file panes (+ the "no file loaded" placeholder)."""
    current = stack.currentWidget()
    for i in range(stack.count()):
        w = stack.widget(i)
        if w is None:
            continue
        if id(w) not in policy_cache:
            policy_cache[id(w)] = w.sizePolicy()
        if w is current:
            w.setSizePolicy(policy_cache[id(w)])
        else:
            w.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
    stack.updateGeometry()


class IfritFilePane(QWidget):
    """The whole tab editor (3D / Dynamic Texture / Sequence / Camera / Stat / AI / Static
    Texture) for ONE loaded .dat file, backed by its own IfritManager.

    One of these exists per loaded file. Because each pane keeps its own widgets and its own
    manager (enemy + textures) alive, switching files in the shell is a pure show/hide - no tab
    is rebuilt and no data is reloaded once a pane exists. The tabs inside a pane are still built
    lazily the first time each is opened (so a pane the user only glances at doesn't pay for the
    3D GL build), and stay built afterwards."""

    dirty_changed = pyqtSignal()   # emitted when this file first becomes edited-but-unsaved
    edited = pyqtSignal()          # emitted on EVERY real edit (drives undo snapshots)

    def __init__(self, ifrit_manager: IfritManager, path: str, settings: QSettings,
                 icon_path="Resources", weapon_provider=None):
        super().__init__()
        self.ifrit_manager = ifrit_manager   # its enemy + textures are already set for `path`
        self.path = path
        self.settings = settings
        self.icon_path = icon_path
        # Callback(body_path) -> (options, default_index) or None, listing the weapon models loaded
        # in the session so a character body can show one in its hand (see set_weapon_options).
        self._weapon_provider = weapon_provider
        self.dirty = False
        self._edited = set()              # commit-needing sections the user changed (seq/camera/...)
        self._loading = False             # True while populating widgets: suppresses dirty flagging
        self._dirty_connected = set()     # id()s of widgets already wired for edit detection
        self._loaded_tabs = set()         # tabs already populated (built once, kept)
        self._tab_size_policies = {}      # id(widget) -> its real QSizePolicy (see _shrink_tabs_to_current)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Editor widgets (each bound to THIS pane's manager) ───────────
        self._ai_widget = IfritAIWidget(settings, ifrit_manager, icon_path=icon_path)
        self._seq_widget = IfritSeqWidget(ifrit_manager, icon_path=icon_path)
        # Seq writes straight to the in-memory monster on every edit and self-reports via data_edited
        # (so it is excluded from the generic widget scan in _connect_dirty_signals). The pane just
        # dirties + records an undo step; nothing is deferred to Save for it.
        self._seq_widget.data_edited.connect(self._on_edit)
        self._camera_widget = IfritCameraSeqWidget(ifrit_manager, icon_path=icon_path)
        # Camera also writes the model live and self-reports (same as seq).
        self._camera_widget.data_edited.connect(self._on_edit)
        self._3d_widget = Ifrit3DWidget(ifrit_manager, show_controls=True)
        self._texture_widget = IfritTextureWidget(ifrit_manager)
        self._xlsx_widget = IfritXlsxWidget(ifrit_manager)
        self._stat_widget = IfritStatWidget(ifrit_manager, icon_path=icon_path)
        self._name_widget = IfritMonsterNameWidget(ifrit_manager)
        self._battle_text_widget = IfritBattleTextWidget(ifrit_manager)
        self._dynamic_texture_widget = IfritDynamicTextureWidget(ifrit_manager)
        # Dyntex also mutates the model live and self-reports (same as seq/camera).
        self._dynamic_texture_widget.data_edited.connect(self._on_edit)

        # Name/Stat/StatExcel all edit section 7 -> one "Stat" tab. Battle text edits section 8
        # like AI -> lives under "AI".
        self._stat_container = QTabWidget()
        self._stat_container.addTab(self._name_widget, "Name")
        self._stat_container.addTab(self._stat_widget, "Editor")
        self._stat_container.addTab(self._xlsx_widget, "Excel (xlsx)")
        self._ai_container = QTabWidget()
        self._ai_container.addTab(self._ai_widget, "AI script")
        self._ai_container.addTab(self._battle_text_widget, "Battle text")

        self._tabs = QTabWidget()
        self._tabs.addTab(self._3d_widget, "1/2/3 - 3D")
        self._tabs.addTab(self._dynamic_texture_widget, "4 - Dynamic Texture")
        self._tabs.addTab(self._seq_widget, "5 - Sequence")
        self._tabs.addTab(self._camera_widget, "6 - Camera")
        self._tabs.addTab(self._stat_container, "7 - Stat")
        self._tabs.addTab(self._ai_container, "8 - AI")
        self._tabs.addTab(self._texture_widget, "11 - Static Texture")
        self._tabs.setCurrentIndex(settings.value("ifrit/current_tab", defaultValue=0, type=int))
        self._tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self._tabs)

        # A QTabWidget (via its internal QStackedWidget) reports the size of its LARGEST page as
        # its own minimumSizeHint - even for tabs that are hidden or never shown. With every tab
        # eagerly built (see below) AND some tabs (Stat/AI) themselves nested QTabWidgets, that
        # floor stacks up to 1000+ px, which propagates out through the multi-file shell's
        # QSplitter and pins the file list to a sliver on anything narrower than that. Toggling
        # every non-current page to an Ignored size policy excludes it from that computation, so
        # only the tab actually on screen constrains width - applied to all three tab widgets,
        # re-run on every tab change, one level of nesting (Stat/AI's own sub-tabs) included.
        for tw in (self._tabs, self._stat_container, self._ai_container):
            tw.currentChanged.connect(lambda _idx=None, t=tw: self._shrink_tabs_to_current(t))
            self._shrink_tabs_to_current(tw)

        self._connect_3d_edit_signals()
        self._loading = True
        self._apply_visibility()
        # _apply_visibility can hide the tab that was "current" (e.g. the saved current-tab index
        # is a shared, cross-entity-type preference - it may point at Stat/AI for a file that has
        # neither). Hiding a tab does NOT fire currentChanged, so the initial shrink pass above
        # would leave that now-hidden tab un-ignored, permanently flooring this pane's width on
        # a tab the user can never even see. Re-run once more now that visibility is settled.
        self._shrink_tabs_to_current(self._tabs)
        # Load EVERY tab now, not just the visible one, so moving between this monster's tabs is
        # instant afterwards. The pane is built lazily on the file's first open and kept alive, so
        # this cost is paid once per opened file - "load when opening, clean while using". Hidden
        # tabs (sections this entity type doesn't have) load nothing (gated in _load_tab).
        for index in range(self._tabs.count()):
            self._ensure_tab_loaded(self._tabs.widget(index))
        QTimer.singleShot(0, self._end_loading)

    def _end_loading(self):
        self._loading = False

    def monster_name(self) -> str:
        try:
            return self.ifrit_manager.enemy.info_stat_data['monster_name'].get_str().strip('\x00')
        except Exception:
            return ""

    def show_saved_tab(self):
        """Select the tab the user last had open (shared preference across panes)."""
        idx = self.settings.value("ifrit/current_tab", defaultValue=0, type=int)
        if 0 <= idx < self._tabs.count() and self._tabs.isTabVisible(idx):
            self._tabs.setCurrentIndex(idx)

    # ── Tab visibility / labels ───────────────────────────────────────

    def _apply_visibility(self):
        """Hide the tabs whose section this entity type does not have (gated on the parsed type,
        never a filename heuristic)."""
        et = self.ifrit_manager.enemy.entity_type
        stat_ai = et in _STAT_AI_CAPABLE_ENTITY_TYPES
        for w in (self._stat_container, self._ai_container):
            self._tabs.setTabVisible(self._tabs.indexOf(w), stat_ai)
        self._tabs.setTabVisible(self._tabs.indexOf(self._texture_widget), et == EntityType.MONSTER)
        self._tabs.setTabVisible(self._tabs.indexOf(self._3d_widget), et in _3D_SECTIONS_BY_ENTITY)
        self._tabs.setTabVisible(self._tabs.indexOf(self._seq_widget), et in _SEQ_SECTION_BY_ENTITY)
        self._tabs.setTabVisible(self._tabs.indexOf(self._camera_widget), et in _CAMERA_SECTION_BY_ENTITY)
        self._tabs.setTabVisible(self._tabs.indexOf(self._dynamic_texture_widget),
                                 et in _DYNAMIC_TEXTURE_SECTION_BY_ENTITY)
        self._update_section_tab_labels()

    def _update_section_tab_labels(self):
        et = self.ifrit_manager.enemy.entity_type
        self._tabs.setTabText(self._tabs.indexOf(self._3d_widget),
                              f"{_3D_SECTIONS_BY_ENTITY.get(et, '1/2/3')} - 3D")
        self._tabs.setTabText(self._tabs.indexOf(self._seq_widget),
                              f"{_SEQ_SECTION_BY_ENTITY.get(et, 5)} - Sequence")
        self._tabs.setTabText(self._tabs.indexOf(self._camera_widget),
                              f"{_CAMERA_SECTION_BY_ENTITY.get(et, 6)} - Camera")
        self._tabs.setTabText(self._tabs.indexOf(self._dynamic_texture_widget),
                              f"{_DYNAMIC_TEXTURE_SECTION_BY_ENTITY.get(et, 4)} - Dynamic Texture")

    def _shrink_tabs_to_current(self, tabs: QTabWidget):
        _shrink_stack_to_current(tabs, self._tab_size_policies)

    # ── Lazy tab loading ──────────────────────────────────────────────

    def _on_tab_changed(self, index: int):
        self.settings.setValue("ifrit/current_tab", self._tabs.currentIndex())
        self._ensure_tab_loaded(self._tabs.currentWidget())

    def _load_tab(self, widget):
        et = self.ifrit_manager.enemy.entity_type
        path = self.path
        if widget is self._3d_widget:
            if et in _3D_SECTIONS_BY_ENTITY:
                # Expand the animation + build matrices up front so the 3D tab is fully ready the
                # moment it's shown (rather than on the first paint), keeping the tab switch clean.
                self.ifrit_manager._ensure_matrices()
                self._3d_widget.load_file()
                # A character body can display one of the session's loaded weapons in its hand,
                # played on the same animation (see CompositeCharacterWeaponAnimation).
                if et == EntityType.CHARACTER and self._weapon_provider is not None:
                    result = self._weapon_provider(path)
                    if result is not None:
                        options, default_index = result
                        self._3d_widget.set_weapon_options(options, default_index)
        elif widget is self._texture_widget:
            if et == EntityType.MONSTER:
                self._texture_widget.show_current()   # textures already in the manager
        elif widget is self._seq_widget:
            self._seq_widget.load_file(path)
        elif widget is self._camera_widget:
            self._camera_widget.load_file(path)
        elif widget is self._dynamic_texture_widget:
            if et in _DYNAMIC_TEXTURE_SECTION_BY_ENTITY:
                self._dynamic_texture_widget.load_file(path)
        elif widget is self._stat_container:
            if et in _STAT_AI_CAPABLE_ENTITY_TYPES:
                self._name_widget.load_data()
                self._stat_widget.load_data()
        elif widget is self._ai_container:
            if et in _STAT_AI_CAPABLE_ENTITY_TYPES:
                self._ai_widget.load_file(path)
                self._battle_text_widget.load_data()

    def _ensure_tab_loaded(self, widget):
        if widget is None or widget in self._loaded_tabs:
            return
        self._loaded_tabs.add(widget)
        nested = self._loading
        self._loading = True
        try:
            self._load_tab(widget)
            self._connect_dirty_signals()
        except Exception as e:
            # One tab failing to load (e.g. a file with no/broken textures) must not stop the
            # monster from opening now that every tab loads on open. Log it and let a later click
            # retry that one tab.
            print(f"[pane] tab load failed for {type(widget).__name__}: {e}")
            self._loaded_tabs.discard(widget)
        finally:
            if not nested:
                QTimer.singleShot(0, self._end_loading)

    # ── Dirty tracking ────────────────────────────────────────────────

    def _connect_3d_edit_signals(self):
        bone_editor = getattr(self._3d_widget, 'bone_editor', None)
        if bone_editor is not None:
            for sig_name in ('bone_length_changed', 'bone_parent_changed', 'add_bone_requested',
                             'reset_skeleton_requested', 'animation_rotation_changed',
                             'animation_position_changed', 'animation_scale_changed',
                             'frame_scale_mode_changed'):
                sig = getattr(bone_editor, sig_name, None)
                if sig is not None:
                    sig.connect(self._on_edit)
        # Everything that edits the model bytes through the 3D view but none of the signals above -
        # frame/animation authoring (add/delete/duplicate), fps conversion, direct in-view bone
        # dragging (rotate ring / Ctrl+drag length), and glTF mesh import - fires this one on a
        # real, committed change ONLY (a click that ends in a cancelled dialog never emits it, so
        # cancelling never dirties the file).
        model_edited = getattr(self._3d_widget, 'model_edited', None)
        if model_edited is not None:
            model_edited.connect(self._on_edit)

    def _connect_dirty_signals(self):
        """(Re)connect edit signals of the currently-built editable controls. Only user-interaction
        signals are used; the 3D widget, the seq widget and camera/texture PREVIEW panels are
        excluded - 3D and seq report their own edits (model_edited / data_edited), previews are
        read-only, and all move controls on a timer."""
        excluded_roots = [self._3d_widget, self._seq_widget, self._camera_widget,
                          self._dynamic_texture_widget]
        excluded_roots += self._tabs.findChildren(CameraPreviewPanel)
        excluded_roots += self._tabs.findChildren(TexturePreviewWidget)
        for widget in self._tabs.findChildren(QWidget):
            if id(widget) in self._dirty_connected:
                continue
            if any(self._is_descendant(widget, root) for root in excluded_roots):
                continue
            signal = None
            if isinstance(widget, QLineEdit):
                signal = widget.textEdited
            elif isinstance(widget, QComboBox):
                signal = widget.activated
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                signal = widget.valueChanged               # guarded by _loading
            elif isinstance(widget, QAbstractButton) and widget.isCheckable():
                signal = widget.clicked
            elif isinstance(widget, (QPlainTextEdit, QTextEdit)):
                signal = widget.textChanged                # guarded by _loading
            if signal is not None:
                signal.connect(self._on_edit)
                self._dirty_connected.add(id(widget))

    @staticmethod
    def _is_descendant(widget, root) -> bool:
        node = widget
        while node is not None:
            if node is root:
                return True
            node = node.parent()
        return False

    def _edited_key_for(self, sender):
        # AI / Stat / Name / 3D / Seq / Camera / DynTex edit the enemy live, so no commit key. Only
        # the Static Texture inject is still deferred.
        if sender is None:
            return None
        if self._is_descendant(sender, self._texture_widget):
            return 'texture'
        return None

    def _on_edit(self, *args):
        if self._loading:
            return
        key = self._edited_key_for(self.sender())
        if key is not None:
            self._edited.add(key)
        if not self.dirty:
            self.dirty = True
            self.dirty_changed.emit()
        self.edited.emit()   # every real edit (not just the first) -> drives undo snapshots

    # ── Commit / save ─────────────────────────────────────────────────

    def _commit(self, include_texture=True):
        """Fold the edited commit-needing widgets into this file's enemy bytes. Only the sections
        actually changed are folded. Stat/Name/AI/3D edit the enemy live, so nothing to do for them.

        include_texture=False skips the Static Texture inject (VincentTim - too heavy to run on
        every undo snapshot); the seq/camera/dyntex folds are cheap in-memory serializations, so an
        undo snapshot folds those to capture their widget-held edits before serializing the model."""
        et = self.ifrit_manager.enemy.entity_type
        # Seq/Camera/DynTex/Stat/Name/AI/3D all write the model live - only the Static Texture inject
        # (VincentTim) is still deferred, because it is far too heavy to run on every edit/snapshot.
        if include_texture and 'texture' in self._edited and et == EntityType.MONSTER:
            self._texture_widget.save_file()

    def save(self):
        """Fold pending edits into the enemy and write this file to disk."""
        self._commit()
        self.ifrit_manager.save_file(self.path)
        self.dirty = False
        self._edited = set()


class IfritMonsterWidget(QWidget):
    """Multi-file battle-model editor: holds several .dat files, each in its own IfritFilePane
    (a full editor with its own manager). Switching files is show/hide of pre-built panes.

    Like Alexander (battle stages), a model .dat has no fixed FF8 name and many open at once, so
    this tool has no per-file FileBinding: the shared header toolbar's Import routes to
    open_files(), Save to save_folder()/can_save_folder(), file_bindings_changed refreshes those
    buttons, and the loaded set is published to the Opened-files panel as one summary entry."""

    file_bindings_changed = pyqtSignal()

    def __init__(self, settings: QSettings, icon_path="Resources", game_data_folder="FF8GameData",
                 file_registry=None):
        super().__init__()
        if file_registry is None:  # Used alone, it shares its files with nobody
            file_registry = FileRegistry()
        self.file_registry = file_registry
        # The shared-toolbar Reload button (registry.reload_all) fans out via reload_requested.
        # Ifrit is an Alexander-pattern tool with no per-file FileBinding, so it subscribes to the
        # signal directly instead of through a binding (otherwise Reload is a no-op for it).
        self.file_registry.reload_requested.connect(self._reload_from_disk)
        self.settings = settings
        self.icon_path = icon_path
        self.file_loaded = ""
        self._file_dialog_folder = ""

        # One manager owns the shared GameData (loaded once, ~0.5s) and the Cronos AI-data
        # selection. Every file's own IfritManager reuses this GameData object, so opening N
        # files pays that cost once, not N times.
        self._shared_manager = IfritManager(game_data_folder)
        self._game_data = self._shared_manager.game_data

        # One dict per loaded file: {'path', 'manager', 'pane' (None until built), 'name'}.
        # Opening files only parses each one LEAN (structure + name for the list, no textures, no
        # expanded animation, no editor widgets). Exactly ONE file is ever "fully loaded" at a time:
        # clicking a file in the list builds its whole editor (textures + expanded animation + all
        # tabs + the 3D GL viewer) and tears the previous one down. Simple and light - no preload,
        # no LRU, no RAM budget, and never more than one heavy 3D viewer alive.
        self._files = []
        self._active_index = -1
        self._stack_size_policies = {}     # id(widget) -> real QSizePolicy, see _shrink_stack_to_current

        # ── Undo/redo (snapshot based, one stack per open file - see Common/undo.py) ──
        # Every edit fires the pane's `edited` signal; a short debounce collapses a burst (typing,
        # dragging) into ONE undo step, then a snapshot of the file's saved bytes is recorded.
        self._undo_debounce = QTimer(self)
        self._undo_debounce.setSingleShot(True)
        self._undo_debounce.setInterval(500)
        self._undo_debounce.timeout.connect(self._commit_active_undo)
        self._restoring_undo = False       # guard: applying an undo must not record a new edit
        # NOTE: no QShortcut here. Ctrl+Z/Ctrl+Shift+Z are bound ONCE at the main window (like
        # Ctrl+S) and routed to the active tool's undo()/redo() - a window-level shortcut fires
        # regardless of which child has focus and takes precedence over a focused spin/text field's
        # own field-level undo, which a sub-widget shortcut does not.

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Toolbar ──────────────────────────────────────────────────
        toolbar = QWidget()
        tl = QHBoxLayout(toolbar)
        tl.setContentsMargins(6, 4, 6, 4)
        tl.setSpacing(4)

        self._cronos_checkbox = QCheckBox("Cronos")
        self._cronos_checkbox.setToolTip("Load AI data with cronos configuration")
        self._cronos_checkbox.setChecked(self.settings.value("ifrit/cronos_checkbox", defaultValue=False, type=bool))
        self._cronos_checkbox.stateChanged.connect(self._on_cronos_toggled)

        self._fps_batch_btn = QPushButton("Files to 30/60 FPS...")
        self._fps_batch_btn.setToolTip("Convert the animations of several .dat files at once to\n"
                                       "30 or 60 fps, without opening them one by one.")
        self._fps_batch_btn.clicked.connect(self._convert_files_to_fps)

        # Import / Save both run from the shared header toolbar (open_files / save_folder /
        # can_save_folder below), the same wiring Alexander uses. Ctrl+S also saves. The loaded
        # file's name/monster is shown in the left side list, so no label is needed here.
        for w in [self._cronos_checkbox, self._fps_batch_btn]:
            tl.addWidget(w)
        tl.addStretch()

        # ── Stack of per-file panes + placeholder ────────────────────
        self._stack = QStackedWidget()
        self._placeholder = QLabel("No file loaded — use Import to open one or more battle model "
                                   "(.dat) files.")
        self._placeholder.setWordWrap(True)   # else its own minimumSizeHint is its full unwrapped
                                              # single-line width - see _shrink_stack_to_current
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet("color:#888;")
        self._stack.addWidget(self._placeholder)
        # Like a pane's own tabs, this stack reports the size of its LARGEST page (the pane or the
        # placeholder) as its own minimumSizeHint - even the one not currently shown - which would
        # floor the file list's max width. Keep only the active page counted; re-applied whenever
        # the active page changes AND whenever a new pane is added (in _build_pane - adding a widget
        # doesn't fire currentChanged by itself).
        self._stack.currentChanged.connect(
            lambda _idx=None: _shrink_stack_to_current(self._stack, self._stack_size_policies))
        _shrink_stack_to_current(self._stack, self._stack_size_policies)

        # ── Loaded-files side list ───────────────────────────────────
        self._file_list = QListWidget()
        self._file_list.setToolTip("Files loaded in memory. Click one to edit it; a leading * "
                                   "marks a file with unsaved changes.")
        self._file_list.currentRowChanged.connect(self._on_file_list_changed)
        left_panel = QWidget()
        lp = QVBoxLayout(left_panel)
        lp.setContentsMargins(4, 4, 0, 4)
        lp.setSpacing(2)
        lp.addWidget(QLabel("Loaded files"))
        lp.addWidget(self._file_list, 1)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(left_panel)
        self._splitter.addWidget(self._stack)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([220, 900])

        root.addWidget(toolbar)
        root.addWidget(self._splitter, 1)

        # Ctrl+S is a single global shortcut on the main window (FF8UltimateEditorWidget) that saves
        # the active tool through the shared toolbar - no per-tool shortcut, to avoid an ambiguous
        # Ctrl+S when Ifrit has focus.

        # Load Cronos AI data once at startup (no file to reload yet).
        self._apply_cronos_ai_data(self._cronos_checkbox.isChecked())

    # ── Shared header toolbar hooks (Alexander pattern) ───────────────

    def open_files(self):
        """Open one or more model .dat files at once (shared header Import routes here). Non-model
        files (b0wave.dat, r0win.dat...) are rejected on the name."""
        key = "battle model (.dat)"  # per file type: re-open where models were last found (persisted)
        folder = (self.file_registry.last_folder(key) or self._file_dialog_folder
                  or (os.path.dirname(self.file_loaded) if self.file_loaded else os.getcwd()))
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Open battle model files", folder,
            f"{IfritManager.BATTLE_MODEL_FILE_FILTER};;All .dat (*.dat)")
        if not paths:
            return
        self.file_registry.remember_folder(key, os.path.dirname(paths[0]))
        good = [p for p in paths if IfritManager.is_openable_model_file(p)]
        skipped = [os.path.basename(p) for p in paths if not IfritManager.is_openable_model_file(p)]
        if skipped:
            QMessageBox.information(
                self, "Some files skipped",
                "These are known non-model battle files (magic effects, wave/victory) and were "
                "skipped:\n\n" + "\n".join(skipped))
        if not good:
            return
        # Add to the current session rather than replacing it: opening more models keeps the
        # ones already open (and their unsaved edits) and appends the new ones to the list.
        self._append_to_session(good)

    def save_folder(self):
        """Write every changed file back to disk - the shared header Save button routes here."""
        self._save_file()

    def can_save_folder(self) -> bool:
        return any(f['pane'] is not None and f['pane'].dirty for f in self._files)

    # ── Loading ───────────────────────────────────────────────────────

    def load_file(self, path):
        """Load a single .dat (replaces the session with just it)."""
        if path:
            self._file_dialog_folder = os.path.dirname(path)
            self._build_session([path])

    def _read_file_entries(self, paths):
        """Lean-parse each .dat into a session entry (structure + name for the list only - no
        textures, no expanded animation, no editor widgets). The heavy work (textures + animation
        + all tabs + 3D viewer) is done per file when it's clicked, one at a time (_activate_index).
        Each file gets its OWN manager sharing the one GameData. Shows a cancelable progress dialog.
        Returns (files, skipped): the entries and the basenames of the empty/unreadable ones.
        Shared by _build_session (replace) and _append_to_session (add)."""
        progress = QProgressDialog("Reading files...", "Cancel", 0, len(paths), self)
        progress.setWindowTitle("Load files")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)        # show at once and stay up (a load is always >0.3s),
        progress.setAutoClose(False)          # rather than flashing/vanishing; we close it by hand
        progress.setAutoReset(False)          # (so reaching a phase's max doesn't dismiss it early)
        progress.setValue(0)
        QApplication.processEvents()
        files = []
        skipped = []                          # empty / unreadable placeholder .dat
        for index, path in enumerate(paths):
            progress.setValue(index)
            progress.setLabelText(f"{os.path.basename(path)}  ({index + 1}/{len(paths)})")
            QApplication.processEvents()
            if progress.wasCanceled():
                break
            # Some battle .dat are empty placeholders (e.g. Squall's unused weapon slot d0w007.dat
            # is 0 bytes). Rather than skip them, open them as a blank model of the kind the
            # filename implies (an empty weapon/character/monster): all the type's tabs are there,
            # just showing nothing, so the slot can be filled in and saved. Only a filename we
            # can't classify falls through to being skipped.
            if os.path.getsize(path) == 0:
                manager = IfritManager(game_data=self._game_data)
                enemy = manager.create_blank_enemy(path)
                if enemy is None:
                    skipped.append(os.path.basename(path))
                    continue
                manager.set_active_enemy(enemy, path, textures=([], True))
                files.append({'path': path, 'manager': manager, 'pane': None,
                              'name': 'empty', 'blank': True})
                continue
            manager = IfritManager(game_data=self._game_data)
            try:
                # free_animation=True: keep the loaded file lean (~0.5 MB anim vs ~30 MB); the
                # animation re-expands when the file is clicked and its pane is built.
                enemy = manager.parse_file(path, free_animation=True)
            except GarbageFileError:
                skipped.append(os.path.basename(path))   # empty/corrupt model data
                continue
            except Exception as e:
                print(f"[load] Could not parse {path}: {e}")
                skipped.append(os.path.basename(path))
                continue
            # Bind the parsed enemy to its manager cheaply (compiler + empty textures, NO VincentTim
            # extraction). Textures are extracted later, only when this file is the one being shown.
            manager.set_active_enemy(enemy, path, textures=([], True))
            name = ""
            try:
                name = enemy.info_stat_data['monster_name'].get_str().strip('\x00')
            except Exception:
                pass
            files.append({'path': path, 'manager': manager, 'pane': None, 'name': name})
        progress.close()
        return files, skipped

    def _build_session(self, paths):
        """Open a set of files, REPLACING any previous session, and show the first one.
        (Adding to an existing session instead is _append_to_session.)"""
        files, skipped = self._read_file_entries(paths)
        if not files:
            if skipped:
                QMessageBox.information(self, "No files loaded",
                    "The selected file(s) are empty or unreadable:\n\n" + "\n".join(skipped))
            return
        self._discard_panes()
        self._files = files
        self._active_index = -1
        self._file_dialog_folder = os.path.dirname(files[0]['path'])
        self._populate_file_list()
        self._activate_index(0, show_busy=True)   # fully load + show the first file
        if skipped:
            QMessageBox.information(self, "Some files skipped",
                "These files are empty or unreadable and were skipped:\n\n" + "\n".join(skipped))
        self.file_registry.open_file(
            "Ifrit battle model(s)",
            FileRegistry.summarize_paths([f['path'] for f in files], "model"))
        self.file_bindings_changed.emit()

    def _append_to_session(self, paths):
        """Add files to the current session WITHOUT replacing it: the file that is open stays
        open, the new ones are appended to the list. Files already in the session are skipped
        (no duplicate entries). Falls back to a fresh session when nothing is open yet."""
        if not self._files:
            self._build_session(paths)
            return
        loaded = {os.path.normcase(os.path.abspath(f['path'])) for f in self._files}
        already = [os.path.basename(p) for p in paths
                   if os.path.normcase(os.path.abspath(p)) in loaded]
        new_paths = [p for p in paths
                     if os.path.normcase(os.path.abspath(p)) not in loaded]
        if not new_paths:
            if already:
                QMessageBox.information(self, "Already open",
                    "The selected file(s) are already in the session:\n\n" + "\n".join(already))
            return
        files, skipped = self._read_file_entries(new_paths)
        if not files:
            if skipped:
                QMessageBox.information(self, "No files added",
                    "The selected file(s) are empty or unreadable:\n\n" + "\n".join(skipped))
            return
        first_new = len(self._files)
        self._files.extend(files)                       # keep _active_index / current pane as-is
        for i in range(first_new, len(self._files)):
            self._file_list.addItem(self._list_label(i))
        self._file_dialog_folder = os.path.dirname(files[0]['path'])
        self.file_registry.open_file(
            "Ifrit battle model(s)",
            FileRegistry.summarize_paths([f['path'] for f in self._files], "model"))
        self.file_bindings_changed.emit()
        notes = []
        if already:
            notes.append("Already open (skipped):\n" + "\n".join(already))
        if skipped:
            notes.append("Empty or unreadable (skipped):\n" + "\n".join(skipped))
        if notes:
            QMessageBox.information(self, "Some files skipped", "\n\n".join(notes))


    def _discard_panes(self):
        """Tear down the built pane (when replacing the session)."""
        for f in self._files:
            pane = f.get('pane')
            if pane is not None:
                self._stack.removeWidget(pane)
                self._stack_size_policies.pop(id(pane), None)   # avoid a stale entry if id() is reused
                pane.deleteLater()
        self._files = []

    def _populate_file_list(self):
        self._file_list.blockSignals(True)
        self._file_list.clear()
        for index in range(len(self._files)):
            self._file_list.addItem(self._list_label(index))
        self._file_list.blockSignals(False)

    def _list_label(self, index) -> str:
        f = self._files[index]
        name = pathlib.Path(f['path']).name
        if f['name']:
            name = f"{name}  ({f['name']})"
        dirty = f['pane'] is not None and f['pane'].dirty
        return ("* " if dirty else "   ") + name

    def _refresh_list_item(self, index):
        item = self._file_list.item(index)
        if item is not None:
            item.setText(self._list_label(index))

    # ── Switching ─────────────────────────────────────────────────────

    def _on_file_list_changed(self, row: int):
        if row < 0 or row >= len(self._files) or row == self._active_index:
            return
        self._activate_index(row, show_busy=True)   # show "Opening..." if this file isn't built yet

    def _activate_index(self, index: int, show_busy: bool = False):
        """Fully load and show file[index]. Exactly one file is loaded at a time: this builds the
        clicked file's whole editor (textures + expanded animation + all tabs + the 3D viewer) and
        tears the previously-shown one down (freeing its 3D GL context + animation). If the file
        being left has unsaved edits, the user is asked to save / discard / cancel first. show_busy
        pops a brief "Opening..." indicator while the (always non-trivial) build runs."""
        if index < 0 or index >= len(self._files):
            return
        if index == self._active_index and self._files[index]['pane'] is not None:
            return                                     # already the shown file
        self._flush_pending_undo()                     # snapshot pending edits of the file being left
        if not self._confirm_leave_current():          # unsaved-edits guard -> keep list on current
            self._file_list.blockSignals(True)
            self._file_list.setCurrentRow(self._active_index)
            self._file_list.blockSignals(False)
            return
        self._destroy_current_pane()                   # only ever one pane alive
        self._active_index = index
        f = self._files[index]
        if show_busy:
            name = f['name'] or os.path.basename(f['path'])
            busy = QProgressDialog(f"Opening {name}...", None, 0, 0, self)   # 0..0 = busy spinner
            busy.setWindowTitle("Opening")
            busy.setWindowModality(Qt.WindowModality.WindowModal)
            busy.setMinimumDuration(0)
            busy.show()
            QApplication.processEvents()
            try:
                self._build_pane(index)
            finally:
                busy.close()
        else:
            self._build_pane(index)
        f['pane'].show_saved_tab()
        self._stack.setCurrentWidget(f['pane'])
        self.file_loaded = f['path']
        self._file_list.blockSignals(True)
        self._file_list.setCurrentRow(index)
        self._file_list.blockSignals(False)

    def _confirm_leave_current(self) -> bool:
        """Before switching away from (or reloading) the shown file, guard its unsaved edits.
        Returns True to proceed (edits saved or discarded), False to abort the switch."""
        if not (0 <= self._active_index < len(self._files)):
            return True
        f = self._files[self._active_index]
        pane = f['pane']
        if pane is None or not pane.dirty:
            return True
        name = f['name'] or os.path.basename(f['path'])
        resp = QMessageBox.question(
            self, "Unsaved changes",
            f"{name} has unsaved changes.\nSave them before switching?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save)
        if resp == QMessageBox.StandardButton.Cancel:
            return False
        if resp == QMessageBox.StandardButton.Save:
            try:
                pane.save()
                self._refresh_list_item(self._active_index)
                self.file_bindings_changed.emit()
            except Exception as e:
                QMessageBox.warning(self, "Save failed", f"Could not save {name}:\n{e}")
                return False
        return True

    def _destroy_current_pane(self):
        """Tear down whichever single pane is currently built - freeing its 3D viewer + GL context
        and reclaiming its ~30 MB expanded animation. No-op if none is built."""
        for f in self._files:
            pane = f.get('pane')
            if pane is None:
                continue
            self._stack.removeWidget(pane)
            self._stack_size_policies.pop(id(pane), None)   # avoid a stale entry if id() is reused
            pane.deleteLater()
            f['pane'] = None
            try:
                f['manager'].enemy.free_animation()         # drop the expanded animation
            except Exception:
                pass

    def _build_pane(self, index: int):
        """Fully load file[index]: extract its textures (VincentTim), expand its animation, and
        build its editor pane (all tabs + the 3D viewer). This is the one heavy step, paid only
        for the file the user actually opens."""
        f = self._files[index]
        manager = f['manager']
        enemy = manager.enemy
        # Real textures now - skipped at open time to keep loading light. Blank placeholder files
        # (0-byte slots) have nothing to extract; they keep their empty texture set.
        if not f.get('blank') and enemy.entity_type != EntityType.MONSTER_NO_MODEL:
            try:
                textures = manager.extract_textures(enemy, f['path'])
                manager.set_active_enemy(enemy, f['path'], textures=textures)
            except Exception as e:
                print(f"[texture] {f['path']}: {e}")
        # Expand the animation before the pane's 3D view poses it (bone matrices must be ready,
        # incl. for a character's weapon overlay which reads the body's matrices).
        try:
            enemy.ensure_animation_expanded()
        except Exception:
            pass
        pane = IfritFilePane(manager, f['path'], self.settings, self.icon_path,
                             weapon_provider=self._weapon_options_for)
        pane.dirty_changed.connect(lambda entry=f: self._on_pane_dirty(entry))
        pane.edited.connect(self._on_active_edited)          # every edit -> (debounced) undo snapshot
        f['pane'] = pane
        self._ensure_undo_stack(f)   # baseline = the just-loaded (== on-disk) model; kept across rebuilds
        self._stack.addWidget(pane)
        # Adding a widget doesn't make it current (no currentChanged fires), so keep the stack's
        # min-size floored to the shown page (see _shrink_stack_to_current).
        _shrink_stack_to_current(self._stack, self._stack_size_policies)

    def _autoload_character_weapons(self, body_path):
        """Bring a character's weapon .dat files into the session automatically.

        A character body only shows a weapon in its hand if that weapon model is loaded (see
        _weapon_options_for). So when a character's 3D view opens, lean-load the weapon files
        that sit next to it on disk (d0c000.dat -> d0w*.dat) but aren't in the session yet -
        the user no longer has to hunt down and open the weapon file separately for it to
        appear. Empty (0-byte) weapon slots and already-loaded files are skipped. Loaded
        weapons also show up in the file list, switchable/editable like any other. Textures
        are NOT extracted here - that is done by _ensure_weapon_textures when the weapon is
        actually offered, so it also covers weapons that were already in the session (e.g.
        loaded with the character from a folder) but never opened. Returns True if any file
        was added."""
        loaded = {os.path.normcase(os.path.abspath(f['path'])) for f in self._files}
        added = False
        for weapon_path in find_character_weapon_file_list(body_path):
            path = str(weapon_path)
            if os.path.normcase(os.path.abspath(path)) in loaded:
                continue
            if os.path.getsize(path) == 0:
                continue                               # empty weapon slot - nothing to overlay
            manager = IfritManager(game_data=self._game_data)
            try:
                # Lean parse (like _build_session); the animation re-expands on demand when the
                # weapon is posed as an overlay (Ifrit3DWidget._set_weapon_manager -> _ensure_matrices).
                enemy = manager.parse_file(path, free_animation=True)
            except Exception as e:
                print(f"[weapon autoload] {path}: {e}")
                continue
            manager.set_active_enemy(enemy, path, textures=([], True))   # bind (compiler); textures later
            self._files.append({'path': path, 'manager': manager, 'pane': None, 'name': ''})
            self._file_list.addItem(self._list_label(len(self._files) - 1))
            added = True
        if added:
            self.file_bindings_changed.emit()
        return added

    def _ensure_weapon_textures(self, f):
        """Extract a weapon file's textures if they aren't loaded yet, so its overlay renders
        textured instead of merging in invisibly. A weapon loaded but never opened has empty
        textures (they're extracted only when its own pane is built) - THAT is the 'I have to
        click the weapon once, then go back to the character, to see it' symptom: the overlay
        needs the weapon's textures, and nothing had extracted them. Idempotent: a weapon whose
        textures are already loaded (opened before, or extracted here earlier) is skipped, so
        this costs one extraction per weapon per session."""
        manager = f['manager']
        if f.get('blank') or manager.texture_data:
            return
        try:
            textures = manager.extract_textures(manager.enemy, f['path'])
            manager.set_active_enemy(manager.enemy, f['path'], textures=textures)
        except Exception as e:
            print(f"[weapon texture] {f['path']}: {e}")

    def _weapon_options_for(self, body_path):
        """Weapon-selector options for a character body pane: every WEAPON model loaded in the
        session, the ones for THIS character (same dXc/dXw slot digit) listed first and the rest
        marked '(other char)', plus a 'None' entry. Returns (options, default_index) with the
        default on the character's first weapon, or None if no weapon is loaded (selector stays
        hidden). options entries are (label, manager_or_None)."""
        slot = IfritManager.character_slot_of(body_path)
        if slot is None:
            return None
        # Pull this character's weapon files in from disk first, so a character always opens
        # with its weapon available even when the weapon file wasn't loaded by hand.
        self._autoload_character_weapons(body_path)
        weapons = []                                   # (name, manager, matches_this_character)
        for f in self._files:
            if not IfritManager.is_weapon_file(f['path']):
                continue
            # WEAPON = full model with its own skeleton/animation; WEAPON_NO_ANIM = the reduced
            # form (Zell's gloves, Kiros's katals) whose mesh is skinned to the BODY's bones and
            # posed by the body's animation (see Ifrit3DWidget._current_weapon_verts).
            if f['manager'].enemy.entity_type not in (EntityType.WEAPON, EntityType.WEAPON_NO_ANIM):
                continue
            matches = (IfritManager.character_slot_of(f['path']) == slot)
            if matches:
                # This character's own weapons can be overlaid (default + switching), so make sure
                # they're textured. Other characters' weapons stay lazy (extracted if opened) - they
                # are only an occasional cross-dress pick and keeping them lazy bounds the cost to
                # this one character's handful of weapons.
                self._ensure_weapon_textures(f)
            weapons.append((os.path.basename(f['path']), f['manager'], matches))
        if not weapons:
            return None
        weapons.sort(key=lambda w: (not w[2], w[0]))   # this character's weapons first, then a-z
        options = [("None (body only)", None)]
        default_index = 0
        for i, (name, manager, matches) in enumerate(weapons):
            options.append((name if matches else f"{name} (other char)", manager))
            if matches and default_index == 0:
                default_index = i + 1                  # +1 for the leading "None" entry
        return options, default_index

    def _on_pane_dirty(self, entry):
        if entry in self._files:
            self._refresh_list_item(self._files.index(entry))
            self.file_bindings_changed.emit()

    # ── Undo / redo (snapshot based, one stack per file) ──────────────
    def _ensure_undo_stack(self, f):
        """Create this file's undo stack once, its baseline captured from the current (just-loaded,
        so == on-disk) model. Kept in the file entry so it survives pane rebuilds (an undo rebuilds
        the pane). Blank placeholder files carry no stack."""
        if f.get('undo') is None and not f.get('blank'):
            f['undo'] = UndoStack(capture=lambda ff=f: self._undo_capture(ff),
                                  restore=lambda snap, ff=f: self._undo_restore(ff, snap))

    def _undo_capture(self, f):
        """Snapshot = the file's serialized .dat bytes (the exact save encoding, a few tens of KB -
        far smaller than the ~30 MB expanded animation, so keeping many is cheap).

        Every editor now writes the model live except the Static Texture inject (VincentTim, too
        heavy per snapshot), so the fold is a cheap no-op here today; kept (skipping texture) so a
        future deferred section is captured automatically."""
        pane = f.get('pane')
        if pane is not None:
            pane._commit(include_texture=False)
        return bytes(f['manager'].enemy.get_bytes(self._game_data))

    def _undo_restore(self, f, snapshot):
        """Re-parse a snapshot back into the file's model and rebuild its pane so every tab shows
        the restored state. Re-parsing via a scratch file reuses the whole, proven load path."""
        self._restoring_undo = True
        try:
            manager = f['manager']
            scratch = manager.temp_path / "_undo_restore.dat"
            scratch.parent.mkdir(parents=True, exist_ok=True)
            with open(scratch, "wb") as fh:
                fh.write(snapshot)
            try:
                enemy = manager.parse_file(str(scratch), free_animation=True)
            finally:
                try:
                    os.remove(scratch)
                except OSError:
                    pass
            manager.set_active_enemy(
                enemy, f['path'],
                textures=(list(manager.texture_data), manager.texture_black_is_transparent))
            index = self._files.index(f)
            if index == self._active_index:      # rebuild the shown pane from the restored model
                self._destroy_current_pane()
                self._active_index = -1
                self._activate_index(index, show_busy=False)
            pane = f.get('pane')
            if pane is not None:                 # dirty follows whether we're back at the saved state
                pane.dirty = f['undo'].is_dirty()
            self._refresh_list_item(index)
            self.file_bindings_changed.emit()
        finally:
            self._restoring_undo = False

    def _on_active_edited(self):
        """A real edit happened in the shown pane: (re)start the debounce so a burst collapses to
        one undo step. Ignored while an undo restore is repopulating (that must not record edits)."""
        if not self._restoring_undo:
            self._undo_debounce.start()

    def _commit_active_undo(self):
        """Fold the pending edits of the active file into one undo step (fired by the debounce, and
        flushed before a file switch / an undo so nothing is lost or mis-attributed)."""
        if self._restoring_undo or not (0 <= self._active_index < len(self._files)):
            return
        stack = self._files[self._active_index].get('undo')
        if stack is not None:
            stack.commit()

    def _flush_pending_undo(self):
        """Commit any not-yet-snapshotted edits now (before switching away from the file)."""
        if self._undo_debounce.isActive():
            self._undo_debounce.stop()
            self._commit_active_undo()

    def undo(self):
        """Public entry point (main-window Ctrl+Z routes here for the active tool)."""
        if not (0 <= self._active_index < len(self._files)):
            return
        stack = self._files[self._active_index].get('undo')
        if stack is None:
            return
        self._flush_pending_undo()   # make a pending (un-snapshotted) edit undoable first
        stack.undo()

    def redo(self):
        """Public entry point (main-window Ctrl+Shift+Z routes here for the active tool)."""
        if not (0 <= self._active_index < len(self._files)):
            return
        stack = self._files[self._active_index].get('undo')
        if stack is not None:
            stack.redo()

    # ── Saving ────────────────────────────────────────────────────────

    def _save_file(self):
        """Write every changed file back to disk (unedited files are left untouched). Only files
        with a built pane can be dirty - a file never opened was never edited."""
        if not self._files:
            return
        self._flush_pending_undo()
        saved = 0
        for index, f in enumerate(self._files):
            pane = f['pane']
            if pane is None or not pane.dirty:
                continue
            try:
                pane.save()
            except Exception as e:
                QMessageBox.warning(self, "Save failed",
                                    f"Could not save {os.path.basename(f['path'])}:\n{e}")
                continue
            if f.get('undo') is not None:
                f['undo'].mark_saved()   # the current state is now on disk -> undo back to it = clean
            self._refresh_list_item(index)
            saved += 1
        if saved:
            self.file_bindings_changed.emit()

    # ── Cronos ────────────────────────────────────────────────────────

    def _apply_cronos_ai_data(self, checked):
        self._game_data.load_ai_data("ai_cronos.json" if checked else "ai_vanilla.json")

    def _on_cronos_toggled(self, state):
        """Cronos changes how AI is decompiled - reload the active file so it re-decompiles with
        the new tables (other files re-decompile when next reloaded)."""
        self._apply_cronos_ai_data(self._cronos_checkbox.isChecked())
        self.settings.setValue("ifrit/cronos_checkbox", state)
        self._reload_active()

    # ── Reload from disk (shared toolbar button) ──────────────────────

    def _reload_from_disk(self):
        """Shared-toolbar Reload (registry.reload_all): re-read EVERY loaded file from disk and
        rebuild. Ifrit has no per-file FileBinding, so it handles the registry signal itself.
        Drops uncommitted edits - that is what 'reload from disk' means."""
        if not self._files:
            return
        keep = self._active_index if 0 <= self._active_index < len(self._files) else 0
        progress = QProgressDialog("Reloading files from disk...", None, 0, len(self._files), self)
        progress.setWindowTitle("Reload")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setValue(0)
        QApplication.processEvents()
        self._destroy_current_pane()           # drop the shown pane; it rebuilds from fresh data
        for i, f in enumerate(self._files):
            progress.setValue(i)
            progress.setLabelText(f"{os.path.basename(f['path'])}  ({i + 1}/{len(self._files)})")
            QApplication.processEvents()
            try:
                if os.path.getsize(f['path']) == 0:       # 0-byte placeholder -> re-open as blank
                    enemy = f['manager'].create_blank_enemy(f['path'])
                    if enemy is None:
                        continue
                    f['manager'].set_active_enemy(enemy, f['path'], textures=([], True))
                    f['name'] = 'empty'
                    continue
                # Lean re-parse (name for the list); textures + animation re-load when shown.
                enemy = f['manager'].parse_file(f['path'], free_animation=True)
                f['manager'].set_active_enemy(enemy, f['path'], textures=([], True))
            except Exception as e:
                print(f"[reload] Could not reparse {f['path']}: {e}")
                continue
            try:
                f['name'] = enemy.info_stat_data['monster_name'].get_str().strip('\x00')
            except Exception:
                f['name'] = ""
        self._active_index = -1
        self._populate_file_list()
        progress.close()
        self._activate_index(keep, show_busy=True)
        # Reload rebuilds every pane fresh (dirty=False). The file list is refreshed above, but the
        # shared toolbar's Save state / window-title '*' only re-evaluate on file_bindings_changed -
        # emit it so the '*' clears instead of lingering from before the reload.
        self.file_bindings_changed.emit()

    # ── Reload (Cronos toggle, after fps batch) ───────────────────────

    def _reload_active(self):
        """Re-parse the active file from disk and rebuild its pane (drops uncommitted edits)."""
        if self._active_index < 0:
            return
        index = self._active_index
        f = self._files[index]
        manager = f['manager']
        try:
            enemy = manager.parse_file(f['path'], free_animation=True)
        except Exception as e:
            print(f"[reload] Could not reparse {f['path']}: {e}")
            return
        # Lean bind now; textures + animation reload when _build_pane runs below.
        manager.set_active_enemy(enemy, f['path'], textures=([], True))
        try:
            f['name'] = enemy.info_stat_data['monster_name'].get_str().strip('\x00')
        except Exception:
            pass
        self._destroy_current_pane()
        self._active_index = -1               # force _activate_index to rebuild + show
        self._activate_index(index, show_busy=True)
        self._refresh_list_item(index)
        self.file_bindings_changed.emit()     # rebuilt pane is clean -> refresh toolbar Save / title '*'

    # ── FPS batch ─────────────────────────────────────────────────────

    def _convert_files_to_fps(self):
        """Convert the animations of several .dat files to 30 or 60 fps in one go."""
        folder = self._file_dialog_folder or (os.path.dirname(self.file_loaded)
                                              if self.file_loaded else os.getcwd())
        file_list = select_battle_model_file_list(
            self, folder, IfritManager.BATTLE_MODEL_FILE_FILTER,
            IfritManager.is_battle_model_file, IfritManager.get_file_family_list)
        if not file_list:
            return
        dialog = FpsBatchDialog(self, file_list)
        if dialog.exec() != FpsBatchDialog.DialogCode.Accepted:
            return
        file_list = dialog.get_file_list()
        target_fps = dialog.get_target_fps()
        split_when_too_long = dialog.get_split_when_too_long()

        progress = QProgressDialog(f"Converting to {target_fps} fps...", "Cancel",
                                   0, len(file_list), self)
        progress.setWindowTitle(f"Convert files to {target_fps} FPS")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)

        def on_progress(index, file_name):
            progress.setValue(index)
            progress.setLabelText(f"{file_name}  ({index + 1}/{len(file_list)})")
            QApplication.processEvents()
            return not progress.wasCanceled()

        try:
            report_list = self._shared_manager.convert_file_list_to_fps(
                file_list, target_fps, split_when_too_long, progress_callback=on_progress)
        finally:
            progress.setValue(len(file_list))

        FpsBatchReportDialog(self, report_list, target_fps).exec()
        # The active file may be one of the converted ones - reload it from disk if so.
        if self.file_loaded and any(os.path.normcase(f) == os.path.normcase(self.file_loaded)
                                    for f in file_list):
            self._reload_active()

    def _show_info(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("Ifrit Monster Tools")
        msg.setText("Combined 3D / Stat / AI / Seq / Texture monster editor.\nDone by Hobbitdur.")
        msg.exec()
