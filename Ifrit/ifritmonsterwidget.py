import os
import pathlib
from PyQt6.QtCore import QSettings, Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QMessageBox, QCheckBox, QProgressDialog, QApplication,
    QListWidget, QSplitter, QFileDialog, QComboBox, QLineEdit, QSpinBox,
    QDoubleSpinBox, QAbstractButton, QPlainTextEdit, QTextEdit, QStackedWidget,
    QDialog, QDialogButtonBox
)
from Common.fileregistry import FileRegistry
from FF8GameData.dat.monsteranalyser import GarbageFileError
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


class IfritFilePane(QWidget):
    """The whole tab editor (3D / Dynamic Texture / Sequence / Camera / Stat / AI / Static
    Texture) for ONE loaded .dat file, backed by its own IfritManager.

    One of these exists per loaded file. Because each pane keeps its own widgets and its own
    manager (enemy + textures) alive, switching files in the shell is a pure show/hide - no tab
    is rebuilt and no data is reloaded once a pane exists. The tabs inside a pane are still built
    lazily the first time each is opened (so a pane the user only glances at doesn't pay for the
    3D GL build), and stay built afterwards."""

    dirty_changed = pyqtSignal()   # emitted when this file first becomes edited-but-unsaved

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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Editor widgets (each bound to THIS pane's manager) ───────────
        self._ai_widget = IfritAIWidget(settings, ifrit_manager, icon_path=icon_path)
        self._seq_widget = IfritSeqWidget(ifrit_manager, icon_path=icon_path)
        self._camera_widget = IfritCameraSeqWidget(ifrit_manager, icon_path=icon_path)
        self._3d_widget = Ifrit3DWidget(ifrit_manager, show_controls=True)
        self._texture_widget = IfritTextureWidget(ifrit_manager)
        self._xlsx_widget = IfritXlsxWidget(ifrit_manager)
        self._stat_widget = IfritStatWidget(ifrit_manager, icon_path=icon_path)
        self._name_widget = IfritMonsterNameWidget(ifrit_manager)
        self._battle_text_widget = IfritBattleTextWidget(ifrit_manager)
        self._dynamic_texture_widget = IfritDynamicTextureWidget(ifrit_manager)

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

        self._connect_3d_edit_signals()
        self._loading = True
        self._apply_visibility()
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
        for btn_name in ('fps60_btn', 'fps60_all_btn', 'import_gltf_btn'):
            btn = getattr(self._3d_widget, btn_name, None)
            if btn is not None:
                btn.clicked.connect(self._on_edit)

    def _connect_dirty_signals(self):
        """(Re)connect edit signals of the currently-built editable controls. Only user-interaction
        signals are used; the 3D widget and camera/texture PREVIEW panels are excluded (their
        controls move on a timer - 3D is wired separately, previews are read-only)."""
        excluded_roots = [self._3d_widget]
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
        # AI / Stat / Name / 3D edit the enemy live, so they carry no commit key.
        if sender is None:
            return None
        if self._is_descendant(sender, self._seq_widget):
            return 'seq'
        if self._is_descendant(sender, self._camera_widget):
            return 'camera'
        if self._is_descendant(sender, self._dynamic_texture_widget):
            return 'dyntex'
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

    # ── Commit / save ─────────────────────────────────────────────────

    def _commit(self):
        """Fold the edited commit-needing widgets into this file's enemy bytes. Only the sections
        actually changed are folded - the Static Texture inject (VincentTim) in particular runs
        only when a texture was edited. Stat/Name/AI/3D edit the enemy live, so nothing to do."""
        et = self.ifrit_manager.enemy.entity_type
        if 'seq' in self._edited and et in _SEQ_SECTION_BY_ENTITY:
            self._seq_widget.save_file()
        if 'camera' in self._edited and et in _CAMERA_SECTION_BY_ENTITY:
            self._camera_widget.save_file()
        if 'dyntex' in self._edited and et in _DYNAMIC_TEXTURE_SECTION_BY_ENTITY:
            self._dynamic_texture_widget.save_file()
        if 'texture' in self._edited and et == EntityType.MONSTER:
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
        self._files = []
        self._active_index = -1

        # Panes (full editors) are memory-heavy (~60 MB RAM + a live 3D GL viewer each), so only a
        # bounded number are kept built at once - an LRU. On a multi-file load they are pre-built
        # up to that cap (behind the progress bar) so clicking any loaded monster is instant; going
        # beyond the cap tears down the least-recently-used clean pane and rebuilds it on demand.
        # The cap is derived from a user RAM budget (spinbox, GB).
        self._ram_budget_gb = self.settings.value("ifrit/ram_budget_gb", defaultValue=1, type=int)
        self._pane_lru = []                # file indices with a built pane, least-recent first

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
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet("color:#888;")
        self._stack.addWidget(self._placeholder)

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
        self._build_session(good)

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

    def _build_session(self, paths):
        """Parse AND texture-extract every path up front (behind the progress bar), then show the
        first one and pre-build the rest in the background up to the RAM cap. Each file gets its
        OWN manager (sharing the one GameData). Replaces any previous session."""
        # Only ask the RAM budget when opening more files than the current cap can keep loaded
        # (8 monsters at the 1 GB default) - a smaller load all fits in the cache, no need to ask.
        if len(paths) > self._pane_cap() and not self._ask_ram_budget(len(paths)):
            return
        progress = QProgressDialog("Loading models and textures...", "Cancel", 0, len(paths), self)
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
                              'name': 'empty'})
                continue
            manager = IfritManager(game_data=self._game_data)
            try:
                # free_animation=True: keep loaded files lean (~0.5 MB anim vs ~30 MB); the file's
                # animation re-expands on its first 3D view and stays expanded after.
                enemy = manager.parse_file(path, free_animation=True)
            except GarbageFileError:
                skipped.append(os.path.basename(path))   # empty/corrupt model data
                continue
            except Exception as e:
                print(f"[load] Could not parse {path}: {e}")
                skipped.append(os.path.basename(path))
                continue
            textures = (None if enemy.entity_type == EntityType.MONSTER_NO_MODEL
                        else manager.extract_textures(enemy, path))
            manager.set_active_enemy(enemy, path, textures=textures)
            name = ""
            try:
                name = enemy.info_stat_data['monster_name'].get_str().strip('\x00')
            except Exception:
                pass
            files.append({'path': path, 'manager': manager, 'pane': None, 'name': name})
        if not files:
            progress.close()
            if skipped:
                QMessageBox.information(self, "No files loaded",
                    "The selected file(s) are empty or unreadable:\n\n" + "\n".join(skipped))
            return
        self._discard_panes()
        self._files = files
        self._active_index = -1
        self._file_dialog_folder = os.path.dirname(files[0]['path'])
        self._populate_file_list()
        # Pre-build the panes up front (up to the cap), INCLUDING the first, so once the first is
        # shown there's no separate "loading the current file" step - it's already built. All the
        # slow work (all tabs + 3D model + animation re-expand per file) happens here behind the
        # progress bar; showing the first file afterwards is then instant.
        self._prebuild_panes(progress)
        self._activate_index(0)               # already built by the pre-build -> instant show
        progress.close()
        if skipped:
            QMessageBox.information(self, "Some files skipped",
                "These files are empty or unreadable and were skipped:\n\n" + "\n".join(skipped))
        self.file_registry.open_file(
            "Ifrit battle model(s)",
            FileRegistry.summarize_paths([f['path'] for f in files], "model"))
        self.file_bindings_changed.emit()

    def _discard_panes(self):
        """Tear down every built pane (when replacing the session)."""
        self._pane_lru = []
        for f in self._files:
            pane = f.get('pane')
            if pane is not None:
                self._stack.removeWidget(pane)
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
        """Show file[index]. Builds its editor pane if needed (evicting the least-recently-used
        one when at the RAM cap), then it's a pure show/hide. show_busy pops a brief "Opening..."
        indicator while a build happens (a cache miss on a user click) - not for cache hits
        (instant) or the load-time popup, which _build_session drives itself."""
        if index < 0 or index >= len(self._files):
            return
        self._active_index = index                 # set before building so it's never evicted
        if show_busy and self._files[index]['pane'] is None:
            f = self._files[index]
            name = f['name'] or os.path.basename(f['path'])
            busy = QProgressDialog(f"Opening {name}...", None, 0, 0, self)   # 0..0 = busy spinner
            busy.setWindowTitle("Opening")
            busy.setWindowModality(Qt.WindowModality.WindowModal)
            busy.setMinimumDuration(0)
            busy.show()
            QApplication.processEvents()
            try:
                self._ensure_pane(index)
            finally:
                busy.close()
        else:
            self._ensure_pane(index)
        f = self._files[index]
        f['pane'].show_saved_tab()
        self._stack.setCurrentWidget(f['pane'])
        self._touch_lru(index)
        self.file_loaded = f['path']
        self._file_list.blockSignals(True)
        self._file_list.setCurrentRow(index)
        self._file_list.blockSignals(False)

    # ── Pane cache (LRU, RAM-bounded) ─────────────────────────────────

    _PANE_RAM_MB = 60                      # measured ~55 MB/full pane, rounded up for headroom

    def _pane_cap(self) -> int:
        """How many built panes to keep alive, from the RAM budget (roughly half of it goes to
        panes, the rest to GameData + the parsed files + OS headroom)."""
        return max(1, int(self._ram_budget_gb * 1024 * 0.5 / self._PANE_RAM_MB))

    def _ensure_pane(self, index: int):
        """Build file[index]'s editor pane if not built, first evicting the LRU pane if at cap."""
        f = self._files[index]
        if f['pane'] is not None:
            return
        self._evict_if_needed(keep=index)
        pane = IfritFilePane(f['manager'], f['path'], self.settings, self.icon_path,
                             weapon_provider=self._weapon_options_for)
        pane.dirty_changed.connect(lambda entry=f: self._on_pane_dirty(entry))
        f['pane'] = pane
        self._stack.addWidget(pane)
        self._pane_lru.append(index)               # newest at the end

    def _weapon_options_for(self, body_path):
        """Weapon-selector options for a character body pane: every WEAPON model loaded in the
        session, the ones for THIS character (same dXc/dXw slot digit) listed first and the rest
        marked '(other char)', plus a 'None' entry. Returns (options, default_index) with the
        default on the character's first weapon, or None if no weapon is loaded (selector stays
        hidden). options entries are (label, manager_or_None)."""
        slot = IfritManager.character_slot_of(body_path)
        if slot is None:
            return None
        weapons = []                                   # (name, manager, matches_this_character)
        for f in self._files:
            if not IfritManager.is_weapon_file(f['path']):
                continue
            if f['manager'].enemy.entity_type != EntityType.WEAPON:
                continue                               # skip reduced/no-model weapon files
            matches = (IfritManager.character_slot_of(f['path']) == slot)
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

    def _touch_lru(self, index: int):
        if index in self._pane_lru:
            self._pane_lru.remove(index)
        self._pane_lru.append(index)               # most-recently-used at the end

    def _evict_if_needed(self, keep: int):
        """Tear down least-recently-used panes while at/over the cap, never the active/kept one or
        a pane with unsaved edits."""
        cap = self._pane_cap()
        while len(self._pane_lru) >= cap:
            victim = next((i for i in self._pane_lru
                           if i != keep and i != self._active_index
                           and self._files[i]['pane'] is not None
                           and not self._files[i]['pane'].dirty), None)
            if victim is None:
                return                              # all remaining are active/dirty: allow over cap
            self._evict_pane(victim)

    def _evict_pane(self, index: int):
        f = self._files[index]
        pane = f['pane']
        if pane is None:
            return
        self._stack.removeWidget(pane)
        pane.deleteLater()
        f['pane'] = None
        if index in self._pane_lru:
            self._pane_lru.remove(index)
        # Reclaim the re-expanded animation (safe: an evicted pane is clean, and re-expansion from
        # the raw bytes is byte-identical - see MonsterAnalyser.ensure_animation_expanded).
        try:
            f['manager'].enemy.free_animation()
        except Exception:
            pass

    # ── Pre-build ─────────────────────────────────────────────────────

    def _prebuild_panes(self, progress):
        """Build every file's editor pane up front, up to the cap, so clicking any loaded monster
        is instant. Done synchronously behind the load progress bar (a background timer is starved
        by the active 3D viewer's playback, so panes never actually pre-built). Cancellable - any
        not built here just build on demand (with an 'Opening...' popup) when first clicked."""
        unbuilt = [i for i in range(len(self._files)) if self._files[i]['pane'] is None]
        room = max(0, self._pane_cap() - len(self._pane_lru))
        # If the RAM budget can hold every opened file (they all fit within the cap), pre-load ALL
        # of them; otherwise fill the cache up to the cap and leave the rest to build on demand.
        to_build = unbuilt if len(unbuilt) <= room else unbuilt[:room]
        if not to_build:
            return
        progress.setRange(0, len(to_build))
        for done, index in enumerate(to_build):
            if progress.wasCanceled():
                break
            progress.setValue(done)
            name = self._files[index]['name'] or os.path.basename(self._files[index]['path'])
            progress.setLabelText(f"Pre-loading editors for instant switching...\n"
                                  f"{name}  ({done + 1}/{len(to_build)})")
            QApplication.processEvents()
            try:
                self._ensure_pane(index)
            except Exception as e:
                print(f"[prebuild] {index} failed: {e}")
        progress.setValue(len(to_build))            # reach max -> dialog dismisses

    def _budget_gb_for(self, num_panes: int) -> int:
        """Smallest whole-GB RAM budget whose cap keeps num_panes editors loaded at once."""
        need_mb = num_panes * self._PANE_RAM_MB / 0.5          # 0.5 = fraction of budget for panes
        return max(1, min(256, -(-int(need_mb) // 1024)))      # ceil to GB, clamp to the spin range

    def _ask_ram_budget(self, num_files: int = 1) -> bool:
        """Ask how much RAM to spend keeping editors loaded (shown when opening more files than the
        current budget can hold). Defaults to a budget that keeps ALL the opened files loaded, so
        accepting it pre-loads them all. Returns False if the user cancels the whole load."""
        fit_all_gb = self._budget_gb_for(num_files)
        dlg = QDialog(self)
        dlg.setWindowTitle("Load files")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(
            f"Opening {num_files} monsters. Editors are pre-loaded so switching between them is\n"
            f"instant; each uses ~{self._PANE_RAM_MB} MB of RAM (plus its 3D model in GPU memory).\n"
            f"About {fit_all_gb} GB keeps ALL {num_files} loaded. A smaller budget keeps the most-recent\n"
            f"ones loaded and rebuilds the rest instantly when you click them."))
        row = QHBoxLayout()
        row.addWidget(QLabel("RAM budget:"))
        spin = QSpinBox()
        spin.setRange(1, 256)
        spin.setSuffix(" GB")
        spin.setValue(max(self._ram_budget_gb, fit_all_gb))   # default to keeping them all loaded
        row.addWidget(spin)
        row.addStretch()
        lay.addLayout(row)
        cap_label = QLabel()
        lay.addWidget(cap_label)
        upd = lambda v: cap_label.setText(
            f"→ up to ~{max(1, int(v * 1024 * 0.5 / self._PANE_RAM_MB))} of {num_files} monsters kept loaded at once.")
        spin.valueChanged.connect(upd)
        upd(spin.value())
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return False
        self._ram_budget_gb = spin.value()
        self.settings.setValue("ifrit/ram_budget_gb", self._ram_budget_gb)
        return True

    def _on_pane_dirty(self, entry):
        if entry in self._files:
            self._refresh_list_item(self._files.index(entry))
            self.file_bindings_changed.emit()

    # ── Saving ────────────────────────────────────────────────────────

    def _save_file(self):
        """Write every changed file back to disk (unedited files are left untouched). Only files
        with a built pane can be dirty - a file never opened was never edited."""
        if not self._files:
            return
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

    # ── Reload (Cronos toggle, after fps batch) ───────────────────────

    def _reload_active(self):
        """Re-parse the active file from disk and rebuild its pane (drops uncommitted edits)."""
        if self._active_index < 0:
            return
        f = self._files[self._active_index]
        manager = f['manager']
        try:
            enemy = manager.parse_file(f['path'])
        except Exception as e:
            print(f"[reload] Could not reparse {f['path']}: {e}")
            return
        textures = (None if enemy.entity_type == EntityType.MONSTER_NO_MODEL
                    else manager.extract_textures(enemy, f['path']))
        manager.set_active_enemy(enemy, f['path'], textures=textures)
        old = f['pane']
        if old is not None:
            self._stack.removeWidget(old)
            old.deleteLater()
        f['pane'] = None
        try:
            f['name'] = enemy.info_stat_data['monster_name'].get_str().strip('\x00')
        except Exception:
            pass
        index = self._active_index
        self._active_index = -1               # force _activate_index to rebuild + show
        self._activate_index(index, show_busy=True)
        self._refresh_list_item(index)

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
