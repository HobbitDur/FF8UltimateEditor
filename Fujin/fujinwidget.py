"""One effect workspace for MAG files, executable cameras and embedded native assets."""
import hashlib
import html
import json
import os
import re
import time
from pathlib import Path

from PyQt6.QtCore import Qt, QSignalBlocker, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon, QFont
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QTabWidget, QPlainTextEdit, QComboBox, QSplitter, QTextBrowser,
    QFileDialog, QMessageBox, QPushButton)
from Common.autoimport import AutoImportSource
from Common.battlesidefiles import BattleSideFiles
from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from FF8GameData.gamedata import GameData
from Fujin.cameraeffectpreview import MODEL_FOLDER_KEY, MODEL_PATTERNS, MODEL_SELECTION_KEY
from Fujin.cameraeffectwidget import CAM_FOLDER_KEY, CAM_SELECTION_KEY, CameraEffectEditorWidget
from Fujin.cameraeffectmanager import cam_file_name, CAM_EXTENSION, CAM_FFNX_FOLDER
from Fujin.effectcatalog import EffectCatalog, filename_effect
from Fujin.effectresourceview import EffectResourceView
from Fujin.nativeresources import NativeResourceStore, apply_effect_hext
from Fujin.magdocumentwidget import MagDocumentWidget
from Fujin.texturepictureview import TexturePictureView, TimTexture, sheet_in_tim, tim_blocks
from FF8GameData.psxgpu.texuse import texture_sheets
from Fujin.effectparts import (PORTS_BUILDING, PORTS_MISSING, PartTab, defaults as schema_defaults, effect_schema,
                               recorder_has_ports)
from Fujin.nativepreview import NativePreviewView, gl_renderer
from Fujin.scriptparts import apply_script_values, edits, is_script_key, script_matches, script_values, with_script_parts
from Fujin.effectdescriptionview import EffectDescriptionView
from Fujin.animsetfiles import AnimSetFiles
from Fujin.effectdataview import EffectDataView
from Fujin import effecttemplates
from Fujin.effectprogram import (DescriptionError, FREE_EFFECTS, PROGRAM_FOLDER, SOURCE, compile_program,
                                 described_effects, description_schema, effect_file_text, load_description, new_effect, program_camera,
                                 program_file_name, read_effect_file, set_program_camera)
from Fujin.recorderbuild import HOST_DLL
from Fujin.recorderbuild import recorder_build
from Fujin.recorderbuildbanner import RecorderBuildBanner
from Fujin.soundpanel import SoundPanel
from Fujin.objectview import MagObjectView
from SmallWidget.listsearchbar import ListSearchBar, SEARCH_TEXT_ROLE

STAGE_FILES_KEY = "Fujin battle stages"
EFFECT_FILE_PATTERNS = ("mag*", "MAG*", "ma8*", "MA8*")
EFFECT_FILES_KEY = "Fujin effect files"                # the game's magic folder
BATTLE_EFFECT_FILES_KEY = "Fujin battle effect files"  # the game's battle folder: no file is in both
ANIM_SET_FOLDER_KEY = "FFNx animation sets"
ANIM_SET_SELECTION_KEY = "FFNx animation set files"   # the .animset files last imported
PROGRAM_FOLDER_KEY = "Fujin effect programs"
PROGRAM_SELECTION_KEY = "Fujin effect program files"   # every effect_NNN.fxprog imported, reopened by Auto-upload
PROGRAM_CAMERA_TIP = ("The camera track this new effect starts when it is cast (not when the cast repeats): a copy of "
                      "the camera of an effect of the game, kept in the effect's program (FujinEffects.dll plays it). "
                      "Characters' spells frame the target from the party's side: Bio's (022) suits a spell on one "
                      "monster. A cinematic's own track (Timing part, Camera) plays too unless it is set to None.")
USERS_SHOWN = 24    # entries listed per kind in the Overview's Used by (effect 0 has hundreds)


class FujinWidget(QWidget):
    file_bindings_changed = pyqtSignal()

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData", file_registry=None):
        super().__init__()
        self.setProperty("read_only_preview", True)
        self.file_registry = file_registry if file_registry is not None else FileRegistry()
        self.setWindowTitle("Fujin — Battle effects")
        self.setWindowIcon(QIcon(os.path.join(icon_path, "hobbitdur.ico")))
        self.catalog = EffectCatalog()
        self.native = NativeResourceStore(self.catalog.native, game_data_folder)
        self.current_effect = None
        self._refresh_pending = False
        self._exported_signature = ()
        self.effect_params = {}          # effect id -> {key: value} of its parameters not at the game's value
        self.descriptions = {}           # effect id -> its description as edited here (Fujin's changed, or a new effect)
        self._shipped = {}               # effect id -> Fujin's description (or None), read once
        self._owned_cam_exports = {}
        self._saved_note = ""            # what the last Save wrote, shown until the next change
        self._resource_effects = None          # resource key -> effect ids using it (built once)
        self.camera_editor = CameraEffectEditorWidget(GameData(game_data_folder), self.file_registry, embedded=True)
        # kernel.bin (read-only, shared): which spells, items, GFs, enemy attacks... play each effect
        self.effect_users = {}
        self.anim_set_files = AnimSetFiles()     # the .animset files the previews play
        self.kernel_binding = FileBinding("kernel.bin", self.file_registry, load_callback=self._load_kernel,
                                          file_filter="*kernel*.bin", read_only=True)
        self.kernel_binding.file_closed.connect(self._close_kernel)
        self.mag_editor = MagDocumentWidget(icon_path, game_data_folder, self.file_registry)
        self.mag_editor.tabs.setTabVisible(0, False)
        self.mag_editor.tabs.setTabVisible(3, False)
        self.mag_editor.tabs.setCurrentIndex(1)
        self.mag_editor.file_label.hide()
        self.mag_editor.gf_selector.setToolTip("Loaded cinematic scripts for the selected effect")
        self.mag_editor.file_bindings_changed.connect(self._schedule_refresh)
        self.camera_editor.modified_changed.connect(self._camera_changed)
        self.camera_editor.exe_binding.file_opened.connect(self._load_native)
        self.camera_editor.exe_binding.file_closed.connect(self._close_native)

        self.effect_list = QListWidget()
        self.effect_list.setMinimumWidth(260)
        self.effect_list.currentRowChanged.connect(self._selection_changed)
        self.effect_search = ListSearchBar.wrap(self.effect_list,
                                                placeholder="Search: name, user, camera, MAG, unused (Ctrl+F)")
        self.title = QLabel()
        self.title.setStyleSheet("font-size: 15pt; font-weight: bold")
        self.context = QLabel()
        self.context.setWordWrap(True)
        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self._activate_tab)
        self.tabs.currentChanged.connect(self._remember_tab)
        self.overview = QTextBrowser()
        # The effect itself, played by the game's own code in the Camera tab preview's battle
        self.native_preview = NativePreviewView(
            self.file_registry, exe_path=lambda: self.camera_editor.exe_binding.current_path or "",
            effect_files=self._preview_effect_files,
            file_edits=self._preview_file_edits,
            cast_source=self.camera_editor.preview, params=self.effect_parameters, program=self.effect_program,
            camera_track=lambda effect: (self.camera_editor.manager, self.camera_editor.manager.track(effect)),
            effect_users=lambda effect: self.users(self._files_effect(effect)), anim_sets=self._anim_sets)
        # Choreography's part tabs: the effect recorded once more, its C++ port alone (no actors),
        # with the edited parameters; each tab shows its part of that recording (Fujin.effectparts)
        self.lab = NativePreviewView(
            self.file_registry, exe_path=lambda: self.camera_editor.exe_binding.current_path or "",
            effect_files=self._preview_effect_files, file_edits=self._preview_file_edits,
            script_values=self._preview_script_values,
            cast_source=self.camera_editor.preview, params=self.effect_parameters, lab=True, program=self.effect_program,
            camera_track=lambda effect: (self.camera_editor.manager, self.camera_editor.manager.track(effect)), anim_sets=self._anim_sets)
        self.lab.setParent(self)
        self.lab.hide()
        self.native_preview.camera_toggled.connect(self.lab.camera_check.setChecked)   # one Camera box for both
        self.lab.camera_toggled.connect(self.native_preview.camera_check.setChecked)
        self.part_tabs = []
        self._parts_schema = None           # the parameter table the part tabs show
        recorder_build().changed.connect(self._recorder_built)     # FFNx's sources updated: tabs without a restart
        self._params_refresh = QTimer(self)
        self._params_refresh.setSingleShot(True)
        self._params_refresh.setInterval(300)
        self._params_refresh.timeout.connect(self._params_edited)
        self.camera_editor.modified_changed.connect(self.native_preview.camera_changed)   # a keyframe edit records anew
        self.overview_splitter = QSplitter(Qt.Orientation.Vertical)
        self.overview_splitter.addWidget(self.overview)
        self.overview_splitter.addWidget(self.native_preview)
        self.overview_splitter.setStretchFactor(0, 1)
        self.overview_splitter.setStretchFactor(1, 3)
        self.tabs.addTab(self.overview_splitter, "Overview")
        self.camera_sources = QTabWidget()
        self.camera_sources.addTab(self.camera_editor, "Executable track")
        self.mag_camera = EffectResourceView("camera", self.resolve)
        self.mag_camera.sections.camera_preview = self.camera_editor.preview
        self.camera_sources.addTab(self.mag_camera, "MAG track")
        self.native_camera = EffectResourceView("parameters", self.resolve)
        self.camera_sources.addTab(self.native_camera, "Native parameters")
        self.camera_note = QLabel()
        self.camera_note.setWordWrap(True)
        # a new effect's program: the camera track it starts (a copy of an exe effect's), or none
        self.program_camera = QComboBox()
        self.program_camera.setToolTip(PROGRAM_CAMERA_TIP)
        self.program_camera.currentIndexChanged.connect(self._program_camera_chosen)
        self.program_camera_row = QWidget()
        program_camera_layout = QHBoxLayout(self.program_camera_row)
        program_camera_layout.setContentsMargins(0, 0, 0, 0)
        program_camera_layout.addWidget(QLabel("Camera it starts:"))
        program_camera_layout.addWidget(self.program_camera, 1)
        self.program_camera_row.hide()
        camera_page = QWidget()
        camera_layout = QVBoxLayout(camera_page)
        camera_layout.addWidget(self.program_camera_row)
        camera_layout.addWidget(self.camera_note)
        camera_splitter = QSplitter()
        camera_splitter.addWidget(self.camera_sources)
        camera_splitter.addWidget(self.camera_editor.preview)
        camera_splitter.setStretchFactor(0, 1)
        camera_splitter.setStretchFactor(1, 1)
        camera_layout.addWidget(camera_splitter, 1)
        self.tabs.addTab(camera_page, "Camera")

        self.choreography = QTabWidget()
        self.choreography.addTab(self.mag_editor, "MAG script / playback")
        native_page = QWidget()
        native_layout = QVBoxLayout(native_page)
        self.function_selector = QComboBox()
        self.function_selector.currentIndexChanged.connect(self._show_function)
        self.native_code = QPlainTextEdit()
        self.native_code.setReadOnly(True)
        self.native_code.setFont(QFont("Consolas", 10))
        snapshot = self.catalog.snapshot()
        native_layout.addWidget(QLabel(
            "The effect's game code, decompiled from the English exe's research database"
            + (f" (saved {snapshot['idb_saved']})" if snapshot.get("idb_saved") else "")
            + ". Read-only: the exe's code is not edited here."))
        native_layout.addWidget(self.function_selector)
        native_layout.addWidget(self.native_code, 1)
        self.choreography.addTab(native_page, "Native code")
        # the effect's MAG workspace: data its code works on, not decoded yet (only when it has some)
        self.workspace = EffectResourceView("workspace", self.resolve)
        self.workspace_tab = self.choreography.addTab(self.workspace, "Workspace data")
        # the effect's description (its parts, tasks, director): what Save compiles for FujinEffects.dll
        self.description_view = EffectDescriptionView()
        self.description_view.applied.connect(self._description_applied)
        self.description_view.reset_requested.connect(self._description_reset)
        self.choreography.addTab(self.description_view, "Description")
        # a new effect's own data (sequences, sounds, tables...), edited by kind
        self.data_view = EffectDataView(vram=self._data_vram, play_sound=self._play_archive,
                                       camera_tools=self.camera_editor.manager, registry=self.file_registry,
                                       exe=self._exe_bytes)
        self.data_view.changed.connect(self._data_changed)
        self.choreography.addTab(self.data_view, "Data")
        # an effect built part by part: + adds (or removes) a part (Fujin.effecttemplates)
        self.plus_tab = QWidget()
        self.choreography.addTab(self.plus_tab, "+")
        self.choreography.setTabToolTip(self.choreography.indexOf(self.plus_tab),
                                        "Add a part to this effect (right-click a part's tab to remove it)")
        self._choreography_tab = 0
        self.choreography.currentChanged.connect(self._choreography_tab_changed)
        self.choreography.tabBarClicked.connect(self._choreography_tab_clicked)
        self.choreography.tabBar().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.choreography.tabBar().customContextMenuRequested.connect(self._choreography_tab_menu)
        self.choreography.currentChanged.connect(self._activate_tab)
        self.choreography.currentChanged.connect(lambda _index: self._record_parts())
        # Why there is no MAG script, when there is none (the greyed tab says it too)
        self.choreography_note = QLabel()
        self.choreography_note.setWordWrap(True)
        choreography_page = QWidget()
        choreography_layout = QVBoxLayout(choreography_page)
        choreography_layout.setContentsMargins(0, 0, 0, 0)
        choreography_layout.addWidget(self.choreography_note)
        # why there are no part tabs: the effect recorder lacks FFNx's effect sources
        self.parts_note = QLabel()
        self.parts_note.setWordWrap(True)
        self.parts_note.hide()
        choreography_layout.addWidget(self.parts_note)
        choreography_layout.addWidget(self.choreography, 1)
        self.tabs.addTab(choreography_page, "Choreography")
        self.object_view = MagObjectView(self.file_registry)
        self.models = EffectResourceView("models", self.resolve, self.object_view, "3D view")
        self.textures = EffectResourceView("textures", self.resolve, TexturePictureView(self.file_registry), "Textures")
        self.textures.panel.uses_provider = self._texture_uses     # what the effect draws from each TIM
        self._sheets = (None, [])                                    # (recording, its texture sheets)
        self.lab.recording_changed.connect(self.textures.panel.refresh_uses)
        self.native_preview.recording_changed.connect(self.textures.panel.refresh_uses)
        self.sound_panel = SoundPanel(self.file_registry)
        self.sound = EffectResourceView("sound", self.resolve, self.sound_panel, "Sounds and vibration")
        self.tabs.addTab(self.models, "Models / animation")
        self.tabs.addTab(self.textures, "Textures")
        self.tabs.addTab(self.sound, "Sound")
        self.changes = QTextBrowser()
        self.tabs.addTab(self.changes, "Pending changes")
        self.component_views = (self.mag_camera, self.native_camera, self.models, self.textures, self.sound,
                                self.workspace)
        for view in self.component_views:
            view.data_changed.connect(self._resource_changed)
        self.camera_sources.currentChanged.connect(self._activate_tab)
        right = QWidget()
        layout = QVBoxLayout(right)
        layout.setContentsMargins(0, 0, 0, 0)
        # a new effect: from a described one (a copy in a free slot), or in a free slot (empty or a copy);
        # its buttons share the title's line (Fujin is the tallest tool: no row of its own, 1080p budget)
        self.copy_button = QPushButton("New effect from this…")
        self.copy_button.setToolTip("A copy of this effect in a free slot of the game's effect table "
                                    "(224, 225, 346-400): a kernel.bin entry naming that effect id casts it")
        self.copy_button.clicked.connect(lambda: self.new_effect_dialog())
        self.create_button = QPushButton("Create a new effect here")
        self.create_button.setToolTip("An empty effect in this free slot: Choreography's + tab adds its parts")
        self.create_button.clicked.connect(lambda: self.create_effect_here())
        self.copy_here_button = QPushButton("Copy an effect here…")
        self.copy_here_button.setToolTip("A copy of an effect Fujin describes (Cure, Potion, Hypnotize, "
                                         "or a new effect) in this free slot")
        self.copy_here_button.clicked.connect(lambda: self.copy_effect_here())
        title_row = QHBoxLayout()
        title_row.addWidget(self.title)
        title_row.addSpacing(12)
        for button in (self.copy_button, self.create_button, self.copy_here_button):
            title_row.addWidget(button)
        title_row.addStretch(1)
        layout.addLayout(title_row)
        layout.addWidget(self.context)
        self.stage_files = BattleSideFiles(self, self.file_registry, STAGE_FILES_KEY, self.native_preview, patterns=("a0stg*.x",))
        self.build_banner = RecorderBuildBanner()
        layout.addWidget(self.build_banner)
        layout.addWidget(self.tabs, 1)
        splitter = QSplitter()
        splitter.addWidget(self.effect_search.column)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 1100])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)
        self._fill_effects()
        self._update_effect_rows(refresh=False)
        self.effect_list.setCurrentRow(0)
        self.kernel_binding.load_opened_file()
        self.camera_editor.exe_binding.load_opened_file()
        if self.camera_editor.manager.exe_path and not self.native.managers:
            self._load_native(self.camera_editor.manager.exe_path)
        self._exported_signature = self._native_signature()

    def file_bindings(self):
        return ([self.camera_editor.exe_binding, self.camera_editor.preview.sceneout_binding, self.kernel_binding]
                + self.sound_panel.file_bindings() + [self.native_preview.textures_binding]
                + self.mag_editor.file_bindings())

    def import_entries(self):
        return [("FF8 exe (camera tracks and embedded effect assets)", self.camera_editor.open_exe),
                ("Effect files: magic (MAG / MA8, all sections)", self.open_effect_files),
                ("Effect files: battle (MAG / MA8: a summon's streamed parts and textures, more effects)",
                 self.open_battle_effect_files),
                ("Fujin effect patch (.hext)", self.import_hext),
                ("FFNx effect cameras (effect_NNN.bcam files)", self._import_bcam),
                ("FFNx animation sets (effect_NNN.animset files)", self.import_anim_sets)]

    def import_anim_sets(self, paths=None, select=True):
        """effect_NNN.animset files (body animations, sequences, weapon animations): the previews play them instead of the exe's
        sets, as FFNx does in the game. (the effects taken, [(path, why refused)])."""
        if paths is None:
            paths = QFileDialog.getOpenFileNames(self, "Import FFNx animation sets (effect_NNN.animset)",
                                                 self.file_registry.last_folder(ANIM_SET_FOLDER_KEY) or os.getcwd(),
                                                 "FFNx animation set (*.animset)")[0]
        if not paths:
            return [], []
        loaded, refused = self.anim_set_files.load(paths)
        self.file_registry.remember_folder(ANIM_SET_FOLDER_KEY, os.path.dirname(paths[0]))
        gone = {path for path, _reason in refused}
        self.file_registry.remember_files(ANIM_SET_SELECTION_KEY, [path for path in paths if path not in gone])
        if refused:
            QMessageBox.warning(self, "Fujin", f"{len(loaded)} effect(s) loaded, {len(refused)} file(s) refused:\n"
                                + "\n".join(f"{os.path.basename(path)}: {reason}" for path, reason in refused[:10]))
        if loaded and select:
            self.select_effect(loaded[0])
        self.native_preview.refresh_cast()
        self.lab.refresh_cast()
        return loaded, refused

    def _anim_sets(self, effect):
        return self.anim_set_files.bindings(effect, self.camera_editor.exe_binding.current_path)

    def _import_bcam(self, paths=None):
        result = self.camera_editor.import_bcam(paths)
        self._after_bcam_import(result[0])
        return result

    def _after_bcam_import(self, loaded):
        if loaded:
            self.select_effect(loaded[0])
            self.tabs.setCurrentIndex(1)
        self._refresh()

    def complementary_entries(self):
        preview = self.camera_editor.preview
        return [("Camera preview models: characters, weapons and monsters", preview.import_models),
                ("Camera preview encounters: scene.out", preview.import_sceneout),
                ("Effect users: kernel.bin (spells, items, GFs, enemy attacks, limit breaks)", self.import_kernel),
                ("Sound preview: audio.fmt + audio.dat (battle sound archive)", self.sound_panel.import_archive),
                ("Effect preview: a8def.tim (the battle's shared effect textures)",
                 self.native_preview.import_shared_textures),
                ("Effect preview: battle stages a0stg###.x (drawn behind the actors; several, Ctrl+A for all)",
                 self.stage_files.import_stages),
                ("Fujin effects: FujinEffects/effect_NNN.fxprog (parameters, edited descriptions, new effects)",
                 self.import_effects)]

    def auto_import_sources(self):
        preview = self.camera_editor.preview
        return [AutoImportSource.for_binding(self.camera_editor.exe_binding, self.file_registry.last_folder("FF8 exe")),
                AutoImportSource(MODEL_FOLDER_KEY, MODEL_PATTERNS, preview.add_models,
                                 selection_only=True, selection_key=MODEL_SELECTION_KEY),
                AutoImportSource.for_binding(preview.sceneout_binding, self.file_registry.last_folder("scene.out")),
                AutoImportSource.for_binding(self.kernel_binding, self.file_registry.last_folder("kernel.bin")),
                AutoImportSource.for_binding(self.sound_panel.audio_binding, self.file_registry.last_folder("audio.fmt")),
                AutoImportSource.for_binding(self.native_preview.textures_binding,
                                             self.file_registry.last_folder(self.native_preview.textures_binding.file_name)),
                self.stage_files.auto_import_source(),
                AutoImportSource(CAM_FOLDER_KEY, ("effect_*.bcam",), self.camera_editor.reload_bcam,
                                 selection_only=True, selection_key=CAM_SELECTION_KEY),
                AutoImportSource(ANIM_SET_FOLDER_KEY, ("effect_*.animset",), lambda paths: self.import_anim_sets(paths, select=False),
                                 selection_only=True, selection_key=ANIM_SET_SELECTION_KEY),
                AutoImportSource(EFFECT_FILES_KEY, EFFECT_FILE_PATTERNS, self.import_paths, selection_only=True),
                AutoImportSource(BATTLE_EFFECT_FILES_KEY, EFFECT_FILE_PATTERNS, self.import_battle_paths, selection_only=True),
                AutoImportSource(PROGRAM_FOLDER_KEY, ("effect_*.fxprog",), self.import_effects,
                                 selection_only=True, selection_key=PROGRAM_SELECTION_KEY)]

    def auto_import_bindings(self):
        return self.mag_editor.file_bindings()

    def open_effect_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Import effect files: the game's magic folder",
            self.file_registry.last_folder(EFFECT_FILES_KEY), "Effect files (MAG* mag* MA8* ma8*);;All files (*)")
        if paths:
            self.import_paths(paths)

    def open_battle_effect_files(self):
        # first time: where the models were imported from, the same folder
        folder = self.file_registry.last_folder(BATTLE_EFFECT_FILES_KEY) or self.file_registry.last_folder(MODEL_FOLDER_KEY)
        paths, _ = QFileDialog.getOpenFileNames(self, "Import effect files: the game's battle folder",
            folder, "Effect files (MAG* mag* MA8* ma8*);;All files (*)")
        if paths:
            self.import_battle_paths(paths)

    def import_kernel(self):
        path = self.kernel_binding.open_dialog(self, default_dir=self.file_registry.last_folder("kernel.bin"))
        if path:
            self.file_registry.remember_folder("kernel.bin", os.path.dirname(path))

    def _load_kernel(self, path):
        from Fujin.effectusers import read_effect_users
        try:
            self.effect_users = read_effect_users(self.camera_editor.manager.game_data, path)
        except Exception as error:  # noqa: BLE001 - a kernel.bin it cannot read gives no users
            self.effect_users = {}
            QMessageBox.warning(self, "Fujin", f"Cannot read the effect users from {os.path.basename(path)}:\n{error}")
        self._update_effect_rows()

    def _close_kernel(self, *_args):
        self.effect_users = {}
        self._update_effect_rows()

    def users(self, effect):
        """The kernel.bin entries playing an effect ([] without a kernel.bin)."""
        return self.effect_users.get(effect, [])

    def effect_tags(self, effect):
        """What an effect has, in a few words (shown in its tooltip; the search finds them too)."""
        tags = []
        if self.catalog.camera_entry(effect) is not None:
            tags.append("exe camera track")
        if effect in self.catalog.camera["file_camera_effects"]:
            tags.append("MAG camera / cinematic")
        resources = self.catalog.resources(effect)
        if any(resource.source == "File" for resource in resources):
            tags.append("MAG files")
        if any(resource.source == "Executable" for resource in resources):
            tags.append("editable exe values")
        if self.catalog.info(effect).get("free"):
            tags.append("unused slot")
        return tags

    def _update_effect_rows(self, refresh=True):
        """Tooltip and search words of every effect row: full name, tags, users; then the Overview."""
        if not hasattr(self, "_tags"):
            self._tags = {effect: self.effect_tags(effect) for effect in self.catalog.effect_ids()}
        for row in range(self.effect_list.count()):
            item = self.effect_list.item(row)
            effect = item.data(Qt.ItemDataRole.UserRole)
            users, tags = self.users(effect), self._tags.get(effect, [])
            item.setData(SEARCH_TEXT_ROLE, " ".join(tags + [user.name for user in users]))
            lines = [f"{effect:03d} — {self.catalog.name(effect)}"]
            if tags:
                lines.append("Has: " + ", ".join(tags))
            labels = [user.label() for user in users]
            if labels:
                more = f" and {len(labels) - 12} more" if len(labels) > 12 else ""
                lines.append("Used by: " + ", ".join(labels[:12]) + more)
            elif self.effect_users:
                lines.append("No kernel.bin entry plays this effect")
            else:
                lines.append("Used by: open kernel.bin (header's Import complementary)")
            item.setToolTip("\n".join(lines))
        self.effect_search.search()
        if refresh:
            self._refresh_summary()

    def _users_html(self, effect):
        esc = lambda value: html.escape(str(value))
        if not self.effect_users:
            return ("<h3>Used by</h3><p style='color:#c0392b'>Open kernel.bin with the header's Import "
                    "complementary to see which spells, items, GFs, enemy attacks and limit breaks play this effect.</p>")
        users = self.users(effect)
        if not users:
            return ("<h3>Used by</h3><p>No kernel.bin entry plays this effect. It can still be played by the "
                    "game code, a monster's AI or another effect.</p>")
        groups = {}
        for user in users:
            groups.setdefault(user.kind, []).append(user)
        rows = []
        for kind, entries in groups.items():
            names = [f"{esc(u.name)} <span style='color:gray'>({u.entry_id})</span>" for u in entries[:USERS_SHOWN]]
            more = f" and {len(entries) - USERS_SHOWN} more" if len(entries) > USERS_SHOWN else ""
            rows.append(f"<tr><td><b>{esc(kind)}</b></td><td>{', '.join(names)}{more}</td></tr>")
        return ("<h3>Used by</h3><table cellspacing='0' cellpadding='4'>" + "".join(rows) + "</table>"
                "<p style='color:gray'>From the kernel.bin entries whose attack animation is this effect "
                "(in brackets: the entry's index in its kernel section).</p>")

    def import_battle_paths(self, paths):
        self.import_paths(paths, BATTLE_EFFECT_FILES_KEY)

    def import_paths(self, paths, key=EFFECT_FILES_KEY):
        """Open effect files with a progress bar (Cancel stops before the next file). The registry
        batches the opens: views refresh once at the end instead of after every file."""
        from Common.filetoolbarwidget import FileToolbarWidget
        by_name = {b.file_name.lower(): b for b in self.mag_editor.file_bindings()}
        opened = []
        progress = FileToolbarWidget.open_progress(self, len(paths), "Opening effect files")
        try:
            with self.file_registry.batch():
                for index, path in enumerate(paths):
                    if progress.wasCanceled():
                        break
                    name = os.path.basename(path)
                    progress.setLabelText(f"Opening {name} ({index + 1} / {len(paths)})")
                    progress.setValue(index)
                    binding = by_name.get(name.lower())
                    if binding is None:
                        binding = self.mag_editor._add_generic_binding(name)
                        by_name[name.lower()] = binding
                    binding.open_path(str(path))
                    opened.append(str(path))
        finally:
            FileToolbarWidget.close_progress(progress)
        if opened:
            # added to those remembered: Auto-upload reopens every effect imported, each one at a time
            earlier = [path for path in self.file_registry.last_files(key) or [] if os.path.isfile(path)]
            self.file_registry.remember_files(key, earlier + opened)
            self.file_registry.remember_folder(key, os.path.dirname(opened[-1]))
        self._refresh()

    def _load_native(self, path):
        if self.camera_editor.manager.loaded:
            self.native.load(Path(path).read_bytes(), self.camera_editor.manager.language_name)
        else:
            self.native.close()
        if self.current_effect is not None:
            self.camera_editor.select_effect(self.current_effect)
        self._exported_signature = self._native_signature()
        self._refresh()

    def _close_native(self, *_args):
        self.native.close()
        self._exported_signature = self._native_signature()
        self._refresh()

    def resolve(self, resource):
        if resource is None:
            return None
        if resource.source == "Executable":
            return self.native.managers.get(resource.key)
        return next((manager for manager in self.mag_editor.managers.values()
                     if os.path.basename(manager.file_path).lower() == resource.key.lower()), None)

    def _fill_effects(self):
        with QSignalBlocker(self.effect_list):
            self.effect_list.clear()
            for effect in self.catalog.effect_ids():
                item = QListWidgetItem(self._effect_text(effect))
                item.setData(Qt.ItemDataRole.UserRole, effect)
                self.effect_list.addItem(item)

    def effect_name(self, effect):
        """The effect's name: a new effect's own, else the catalog's."""
        description = self.descriptions.get(effect)
        return description["name"] if self.is_new_effect(effect) else self.catalog.name(effect)

    def is_new_effect(self, effect):
        """A new effect made here (a copy in a free slot, or built part by part)."""
        description = self.descriptions.get(effect) or {}
        return "base" in description or "template_parts" in description

    def _effect_text(self, effect, modified=False):
        created = self.camera_editor.manager.camera_kind(effect) == "created"
        new = " (new effect)" if self.is_new_effect(effect) else ""
        return f"{'* ' if modified else ''}{effect:03d} — {self.effect_name(effect)}{new}" + (" (.bcam camera)" if created else "")

    def modified_effects(self):
        """The effects with unsaved changes: a camera track or a native resource changed since the
        last export, or a modified MAG file that the effect uses."""
        exported = dict(self._exported_signature)
        unsaved = {key for key, digest in self._native_signature() if exported.get(key) != digest}
        effects = {int(key.split(":", 1)[1]) for key in unsaved if key.split(":", 1)[0] in ("camera", "params", "desc")}
        dirty = {os.path.basename(m.file_path).lower() for m in self.mag_editor.managers.values() if m.modified}
        dirty |= {key for key in unsaved if key.split(":", 1)[0] not in ("camera", "params", "desc")}
        if dirty and self._resource_effects is None:
            self._resource_effects = {}
            for effect in self.catalog.effect_ids():
                for resource in self.catalog.resources(effect):
                    self._resource_effects.setdefault(resource.key, set()).add(effect)
        for key in dirty:
            family = filename_effect(key)       # an imported file of the effect's mag family
            effects |= self._resource_effects.get(key, {family} if family is not None else set())
        return effects

    def _mark_modified_effects(self):
        modified = self.modified_effects()
        for row in range(self.effect_list.count()):
            item = self.effect_list.item(row)
            effect = item.data(Qt.ItemDataRole.UserRole)
            text = self._effect_text(effect, effect in modified)
            if item.text() != text:
                item.setText(text)

    def select_effect(self, effect):
        for row in range(self.effect_list.count()):
            if self.effect_list.item(row).data(Qt.ItemDataRole.UserRole) == effect:
                self.effect_list.setCurrentRow(row)
                return
        raise ValueError(f"Unknown effect ID: {effect}")

    def _effect_files_folder(self):
        """Where the effect files come from: the folder of an imported MAG file, or the remembered one."""
        for manager in self.mag_editor.managers.values():
            if manager.file_path:
                return os.path.dirname(manager.file_path)
        return self.file_registry.last_folder(EFFECT_FILES_KEY) or ""

    def _effect_file_managers(self, effect):
        """{file name: its imported file} of what an effect reads: its base's files, and a new effect's own
        (named for its id, or as its Files tab says: Bio 349's mag348_b.00)."""
        extra = [os.path.basename(m.file_path) for m in self.mag_editor.managers.values()]
        base = self._files_effect(effect)
        names = [resource.key for resource in self.catalog.resources(base, extra) if resource.source == "File"]
        if base != effect:
            names += [resource.key for resource in self.catalog.resources(effect, extra) if resource.source == "File"]
            values = self.effect_params.get(effect, {})
            names += [values[param["key"]].lower() for param in self.descriptions[effect].get("params", [])
                      if param.get("type") == "file" and values.get(param["key"])]
        managers = {}
        for name in names:
            manager = next((m for m in self.mag_editor.managers.values() if os.path.basename(m.file_path).lower() == name), None)
            if manager is not None:
                managers[name] = manager
        return managers

    def _preview_effect_files(self):
        """The current effect's imported files as Fujin holds them (unsaved edits included): all
        the effect preview's recorder reads of them - never their folder."""
        if self.current_effect is None:
            return {}
        return {name: bytes(manager.data) for name, manager in self._effect_file_managers(self.current_effect).items()}

    def _preview_file_edits(self):
        """Current effect's unsaved file bytes, for preview without saving the imported files."""
        if self.current_effect is None:
            return {}
        return {name: bytes(manager.data) for name, manager in self._effect_file_managers(self.current_effect).items()
                if manager.modified}

    def _selection_changed(self, *_args):
        item = self.effect_list.currentItem()
        if item:
            self.current_effect = item.data(Qt.ItemDataRole.UserRole)
            self.camera_editor.select_effect(self.current_effect)
            self.native_preview.set_effect(self.current_effect, self.effect_name(self.current_effect))
            self.lab.set_effect(self.current_effect, self.effect_name(self.current_effect))
            self._build_part_tabs()
            self._show_description()
            self._refresh()

    def _schedule_refresh(self):
        if hasattr(self, "native_preview"):
            self.native_preview.edits_changed()
        self.file_bindings_changed.emit()
        if not self._refresh_pending:
            self._refresh_pending = True
            QTimer.singleShot(0, self._refresh)

    def _resource_changed(self):
        self.mag_editor._sync_resource_images()
        self._choreography_dirty = True
        self._schedule_refresh()

    def _camera_changed(self):
        if hasattr(self, "changes"):
            if self.current_effect is not None and hasattr(self, "resources"):
                self._refresh_camera()            # a camera created or removed changes the tab
            self._refresh_summary()
            self.file_bindings_changed.emit()

    def _refresh(self, *_args):
        self._refresh_pending = False
        if self.current_effect is None or not hasattr(self, "component_views"):
            return
        effect = self.current_effect
        extra = [os.path.basename(m.file_path) for m in self.mag_editor.managers.values()]
        resources = self.catalog.resources(effect, extra)
        self.resources = resources
        self._set_empty_texts(effect, resources)
        for view in self.component_views:
            view.set_resources(resources)
        self.choreography.setTabVisible(self.workspace_tab, self.workspace.sources.count() > 0)
        self.title.setText(f"{effect:03d} — {self.effect_name(effect)}")
        loaded = sum(self.resolve(r) is not None for r in resources)
        self.context.setText(f"{self.catalog.runtime(effect)} · {loaded} of {len(resources)} files imported"
                             + self._files_to_import(resources)
                             + (" · unsaved changes: see Pending changes" if self.can_save_folder()
                                else f" · {self._saved_note}" if self._saved_note else ""))
        self._sync_script_parts()
        self._refresh_camera()
        self._refresh_choreography()
        self._grey_unused_tabs()
        self._refresh_summary()
        self._activate_tab()

    def _files_to_import(self, resources):
        """Which of the header's Effect files lines brings what is missing: Ifrit's first 2 files are in the magic folder, its 11 others in the battle one."""
        folders = [self.catalog.file_folder(r.name) for r in resources if r.source == "File" and self.resolve(r) is None]
        counts = [f"{folders.count(folder)} from {folder} folder" for folder in ("magic", "battle") if folder in folders]
        return " · header's Import, Effect files: " + ", ".join(counts) if counts else ""

    def _refresh_camera(self):
        effect = self.current_effect
        self._fill_program_camera(effect)
        exe = self.catalog.camera_entry(effect)
        manager = self.camera_editor.manager
        created = manager.camera_kind(effect) == "created"
        creatable = manager.can_create(effect)
        parameters = any(r.kind == "camera_parameter" for r in self.resources)
        self.camera_sources.setTabVisible(0, exe is not None or created or creatable)
        self.camera_sources.setTabVisible(1, (exe is None and not parameters and not (created or creatable))
                                          or self.mag_camera.sources.count() > 0)
        self.camera_sources.setTabVisible(2, parameters)
        mag_tracks = self.mag_camera.sources.count() > 0
        file_camera = effect in self.catalog.camera["file_camera_effects"]
        # No track anywhere: say so instead of showing an empty editor and an empty 3D view
        self.camera_sources.setVisible(exe is not None or parameters or mag_tracks or file_camera or created or creatable)
        if created:
            self.camera_note.setText("<b>Created camera.</b> This effect has no camera in the exe; FFNx plays this one "
                                     "from direct/exe/" + cam_file_name(effect) + " right after the effect starts. Save "
                                     "writes it (Pending changes lists it); Remove this camera deletes it.")
            self.camera_sources.setCurrentIndex(0)
        elif creatable and exe is None:
            self.camera_note.setText("<b>This effect plays no camera track of its own</b> (as for Phoenix Down and Mega "
                                     "Phoenix, the camera of the action stays). It can be given one: Create a camera "
                                     "below makes an FFNx .bcam camera, from another effect's track or a minimal one.")
            self.camera_sources.setCurrentIndex(0)
        elif exe is not None:
            self.camera_note.setText("Camera track stored in the exe. Save writes your changes as a .hext patch; "
                                     "a track that grew is saved as an FFNx .bcam file instead.")
        elif parameters:
            self.camera_note.setText("The game code computes this camera. Six of its numbers can be edited below "
                                     "(opening position, orbit radius and step); Save writes them as a .hext patch. "
                                     "The rest of the camera motion is compiled code.")
            self.camera_sources.setCurrentIndex(2)
        elif mag_tracks:
            self.camera_note.setText("Camera track inside the effect's MAG file. Save writes it back into that file.")
            self.camera_sources.setCurrentIndex(1)
        elif file_camera:
            self.camera_note.setText("This effect's camera comes from its MAG files (a camera track or cinematic camera "
                                     "commands). Import them with the header's Import (Effect files: magic and battle folders) to edit it; camera "
                                     "moves driven by the cinematic script are in Choreography.")
        else:
            self.camera_note.setText("<b>This effect plays no camera track of its own.</b> It never starts the battle "
                                     "camera player, so the camera of the action (or the stage camera) stays while it "
                                     "plays, as for Phoenix Down and Mega Phoenix. Its game code can still move the "
                                     "camera: see Choreography, Native code. " + html.escape(self.catalog.notes(effect)))

    def _fill_program_camera(self, effect):
        """A new effect's camera choice: none, or the camera track of an effect of the exe (its own
        copy in the program), the one it starts now selected."""
        new = self.is_new_effect(effect)
        self.program_camera_row.setVisible(new)
        if not new:
            return
        current = program_camera(self.descriptions[effect])
        with QSignalBlocker(self.program_camera):
            self.program_camera.clear()
            self.program_camera.addItem("None: the battle's view stays", None)
            for track in sorted(self.catalog.camera["tracks"], key=lambda t: t["effect_id"]):
                address = int(track["eng_address"], 16)
                self.program_camera.addItem(f"{track['effect_id']:03d} — {self.catalog.name(track['effect_id'])}'s camera",
                                            (address, int(track["size"], 16)))
            index = next((i for i in range(self.program_camera.count())
                          if (self.program_camera.itemData(i) or (None,))[0] == current), -1)
            if index < 0:   # (a track of its own, from no effect's)
                self.program_camera.addItem(f"Its own track (from 0x{current:X})", (current, 0))
                index = self.program_camera.count() - 1
            self.program_camera.setCurrentIndex(index)

    def _program_camera_chosen(self, index):
        """The new effect starts the chosen camera track (a copy in its program) or none."""
        effect = self.current_effect
        choice = self.program_camera.itemData(index)
        if not self.is_new_effect(effect) or (choice or (None,))[0] == program_camera(self.descriptions[effect]):
            return
        try:
            set_program_camera(self.descriptions[effect], *(choice or (None,)), exe=self._exe_bytes())
        except DescriptionError as error:
            QMessageBox.warning(self, "Camera", str(error))
            self._fill_program_camera(effect)
            return
        self._description_changed()

    def _grey_unused_tabs(self):
        """Grey the tabs with nothing for this effect; the reason is the tab's tooltip (and listed
        in the Overview). A greyed current tab hands over to the Overview."""
        camera = not self.camera_sources.isHidden()
        reasons = {
            1: None if camera or self.is_new_effect(self.current_effect)
            else self.camera_note.text().replace("<b>", "").replace("</b>", ""),
            2: None if (self.choreography.isTabEnabled(0) or self.function_selector.count()
                        or self.workspace.sources.count() or self.part_tabs or self.current_effect in self.descriptions)
            else "No MAG script and no native code snapshot for this effect.",
            3: None if self.models.sources.count() else self.models.empty_text,
            4: None if self.textures.sources.count() else self.textures.empty_text,
            5: None if self.sound.sources.count() else self.sound.empty_text,
        }
        self.greyed_tabs = {}
        wanted = getattr(self, "_wanted_tab", self.tabs.currentIndex())
        self._greying = True    # Qt moves off a tab it disables: not the user's choice
        try:
            for index, reason in reasons.items():
                self.tabs.setTabEnabled(index, reason is None)
                self.tabs.setTabToolTip(index, reason or "")
                if reason is not None:
                    self.greyed_tabs[self.tabs.tabText(index)] = reason or "Nothing for this effect."
            # The tab the user chose comes back as soon as an effect has something for it
            self.tabs.setCurrentIndex(wanted if self.tabs.isTabEnabled(wanted) else 0)
        finally:
            self._greying = False
        self._wanted_tab = wanted

    def _remember_tab(self, index):
        if not getattr(self, "_greying", False):
            self._wanted_tab = index

    def _greyed_tabs_html(self):
        greyed = getattr(self, "greyed_tabs", {})
        if not greyed:
            return ""
        esc = lambda value: html.escape(str(value))
        return ("<h3>Greyed tabs</h3><table cellspacing='0' cellpadding='4'>"
                + "".join(f"<tr><td><b>{esc(name)}</b></td><td>{esc(reason)}</td></tr>" for name, reason in greyed.items())
                + "</table>")

    def _refresh_choreography(self):
        candidates = [(key, m) for key, m in self.mag_editor.managers.items()
                      if m.program is not None and any(self.resolve(r) is m for r in self.resources)]
        if getattr(self, "_choreography_dirty", False) and self.mag_editor.current_gf in {k for k, _m in candidates}:
            self.mag_editor._show_gf(self.mag_editor.current_gf)
        elif self.mag_editor.current_gf not in {k for k, _m in candidates}:
            self.mag_editor._show_gf(candidates[0][0] if candidates else "")
        self._choreography_dirty = False
        with QSignalBlocker(self.mag_editor.gf_selector):
            self.mag_editor.gf_selector.clear()
            for key, manager in candidates:
                self.mag_editor.gf_selector.addItem(os.path.basename(manager.file_path), key)
            self.mag_editor.gf_selector.setCurrentIndex(self.mag_editor.gf_selector.findData(self.mag_editor.current_gf))
        self.choreography.setTabEnabled(0, bool(candidates))
        note = "" if candidates else self._no_script_text(self.current_effect)
        self.choreography.setTabToolTip(0, note)
        self.choreography_note.setText(note)
        self.choreography_note.setVisible(bool(note))
        if not candidates and self.choreography.currentIndex() == 0:
            self.choreography.setCurrentIndex(1)       # off the greyed script tab, never off another
        functions = self.catalog.functions(self.current_effect)
        previous = self.function_selector.currentData()
        with QSignalBlocker(self.function_selector):
            self.function_selector.clear()
            for function in functions:
                self.function_selector.addItem(f"{function['name']} ({function['addr']})", function)
            if previous in functions:
                self.function_selector.setCurrentIndex(functions.index(previous))
        self._show_function()

    def _show_function(self, *_args):
        function = self.function_selector.currentData()
        if not function:
            self.native_code.setPlainText("No native research snapshot for this effect.")
            return
        code = self.catalog.pseudocode(function)
        comment = function.get("comment", "")
        # Hex-Rays prints the function comment above the code itself: add it only when it does not
        shown = comment and comment.splitlines()[0].strip() in code
        header = "/* " + comment.replace("*/", "* /") + " */\n\n" if comment and not shown else ""
        self.native_code.setPlainText(header + code)

    # ------------------------------------------------------------------ empty tabs, said plainly
    def _no_script_text(self, effect):
        if self.catalog.runtime(effect).startswith("MAG cinematic"):
            return ("This effect runs a MAG cinematic script: import its MAG files (header's Import, "
                    "Effect files: magic and battle folders) to read, edit and play it here.")
        return ("No MAG script: this effect is run by the exe's own code (see Native code). Only cinematic "
                "effects, the GF summons and the other MAG-script effects, have a MAG script.")

    def _native_functions(self, effect, pattern):
        """Names of the effect's native functions whose name matches `pattern` (the research names
        say what a function does: MAG_001_CURE_DrawTargetModelWithOverlay)."""
        return [function["name"] for function in self.catalog.functions(effect)
                if re.search(pattern, function.get("name", ""))]

    def _set_empty_texts(self, effect, resources):
        """What each component tab says when the effect has nothing for it: missing imports first,
        then what is known from its files and its native code - never a guess."""
        missing = [r.name for r in resources if r.source == "File" and self.resolve(r) is None]
        if missing:
            text = ("Not imported yet: " + ", ".join(missing[:6]) + (" ..." if len(missing) > 6 else "")
                    + ". Open them with the header's Import (Effect files: magic and battle folders).")
            for view in (self.models, self.textures, self.sound):
                view.empty_text = text
            return
        native = not self.catalog.runtime(effect).startswith("MAG cinematic")
        drawers = self._native_functions(effect, r"(Draw|Render)\w*Model|Model\w*(Draw|Render)") if native else []
        models = "This effect stores no model of its own."
        if drawers:
            models += (" Its game code draws battle models already on screen: "
                       + ", ".join(drawers[:4]) + (" ..." if len(drawers) > 4 else "") + " (Choreography, Native code).")
        elif native:
            models += " Its game code draws its visuals itself (Choreography, Native code)."
        self.models.empty_text = models
        self.textures.empty_text = ("No texture file is known for this effect." if not any(
            r.source in ("File", "Executable") for r in resources) else
            "None of this effect's files holds a texture.")
        players = self._native_functions(effect, r"PlaySE|PlaySound|Sound_") if native else []
        sound = "No sound data in this effect's files."
        if players:
            sound += " Its game code plays sounds in: " + ", ".join(players[:4]) + (" ..." if len(players) > 4 else "") + "."
        self.sound.empty_text = sound

    def _activate_tab(self, *_args):
        if not hasattr(self, "component_views"):
            return
        for view in self.component_views:
            if view.isVisible() and view._pending:
                view.activate()
        if self.tabs.currentIndex() == 1:
            source = None if self.camera_sources.isHidden() else self.camera_sources.currentWidget()
            track = None
            if source is self.camera_editor:
                track = self.camera_editor.manager.track(self.current_effect)
            elif source is self.mag_camera:
                page = self.mag_camera.sections.currentWidget()
                from Fujin.magsectionwidget import MagSectionEditor
                editor = page.findChild(MagSectionEditor) if page else None
                track = getattr(editor, "camera_track", None)
            self.camera_editor.preview.set_track(track)
            # The 3D preview only when there is a camera to play (no empty view beside a note)
            self.camera_editor.preview.setVisible(track is not None or source is self.camera_editor)

    def _refresh_summary(self):
        if self.current_effect is None:
            return
        esc = lambda value: html.escape(str(value))
        effect, info = self.current_effect, self.catalog.info(self.current_effect)
        rows = []
        for resource in getattr(self, "resources", []):
            manager = self.resolve(resource)
            availability = ("Imported (" + manager.document.format + ")" if manager else
                self.native.unavailable.get(resource.key, "Import the exe" if resource.source == "Executable"
                                            else "Not imported: header's Import (Effect files"
                                            + (f": {self.catalog.file_folder(resource.name)} folder)" if self.catalog.file_folder(resource.name) else ")")))
            rows.append("<tr>" + "".join(f"<td>{esc(value)}</td>" for value in (
                resource.name, resource.source, resource.evidence, availability)) + "</tr>")
        aliases = self.catalog.aliases(effect)
        self.overview.setHtml(
            f"<h2>{effect:03d} — {esc(self.catalog.name(effect))}</h2>"
            f"<p><b>How it runs:</b> {esc(self.catalog.runtime(effect))}<br>"
            f"<b>Start function (EN exe):</b> {esc(info.get('logic_name', 'not found'))} {esc(info.get('logic_addr', ''))}<br>"
            f"<b>File loader (EN exe):</b> {esc(info.get('fl_name', 'not found'))} {esc(info.get('fl_addr', ''))}</p>"
            f"<p>{esc(self.catalog.notes(effect))}</p>"
            + self._users_html(effect)
            + self._greyed_tabs_html()
            + (f"<p>Effects {esc(', '.join(str(i) for i in aliases))} run the same game code; each one still has "
               "its own files below.</p>" if aliases else "")
            + ("<p><b>Unused slot:</b> the game's effect table points to no effect here.</p>" if info.get("free") else "")
            + "<h3>Files</h3><table border='1' cellspacing='0' cellpadding='6'><tr><th>File</th><th>Stored in</th>"
              "<th>How it is linked</th><th>Status</th></tr>"
            + "".join(rows) + "</table><p style='color:gray'>How it is linked: <i>Verified runtime resource</i> = "
              "seen in use; <i>Loader reference</i> = named by the effect's file loader; <i>Filename family only</i> = "
              "its name carries the effect's number, a hint, not a proof. A file missing here can still be used. "
              "Files with decoded sections show named fields, the others their bytes; the game code "
              "(Choreography, Native code) is read-only.</p>")
        pending = []
        for manager in self.mag_editor.managers.values():
            if manager.modified:
                pending.append(f"<li>File: {esc(manager.file_path)} ({len(manager.data):,} bytes; original section sizes)</li>")
        for track in self.camera_editor.manager.modified_tracks():
            destination = "effects_" + self.camera_editor.manager.language_name + ".hext" if track.fits_exe else CAM_FFNX_FOLDER + "/" + cam_file_name(track.effect_id)
            pending.append(f"<li>Camera {track.effect_id}{' (created)' if track.created else ''}: {esc(destination)}</li>")
        for key, manager in self.native.managers.items():
            if manager.modified:
                pending.append(f"<li>{esc(key)}: effects_EN.hext (native data)</li>")
        exported = dict(self._exported_signature)
        for effect in self._changed_effects():
            if any(exported.get(key) != digest for key, digest in self._native_signature()
                   if key in (f"desc:{effect}", f"params:{effect}")):
                pending.append(f"<li>Effect {effect} ({esc(self.effect_name(effect))}): {PROGRAM_FOLDER}/"
                               f"{program_file_name(effect)}, run in the game by {HOST_DLL.name}</li>")
        unsaved = self.can_save_folder()
        self.changes.setHtml(f"<h2>{'Unsaved changes' if unsaved else 'All changes saved'}</h2>"
            "<p>Save (header toolbar or Ctrl+S) writes MAG edits into the imported files. Exe edits (camera tracks, "
            "native values) go to a folder you choose: one .hext patch holding every change made to the loaded exe, "
            "and an FFNx .bcam file for each camera track that grew. The exe itself is never modified.</p>"
            + ("<p><b>What Save writes:</b></p><ul>" + "".join(pending) + "</ul>" if pending
               else "<p>Nothing is changed.</p>"))
        state = getattr(self, "dirty_state", None)
        if state is not None:
            (state.mark if unsaved else state.clear)()
        self._mark_modified_effects()

    def _native_signature(self):
        result = [(f"camera:{effect}", hashlib.sha256(t.to_bytes()).digest())
                  for effect, t in sorted(self.camera_editor.manager.tracks.items())]
        result += [(key, hashlib.sha256(m.data).digest()) for key, m in sorted(self.native.managers.items())]
        result += [(f"params:{effect}", tuple(sorted(values.items()))) for effect, values in sorted(self.effect_params.items())]
        result += [(f"desc:{effect}", json.dumps(description, sort_keys=True)) for effect, description in sorted(self.descriptions.items())]
        return tuple(result)

    # ------------------------------------------------------------------ effect descriptions (Description tab)
    def shipped_description(self, effect):
        if effect not in self._shipped:
            self._shipped[effect] = load_description(effect)
        return self._shipped[effect]

    def description(self, effect):
        """The effect's description as Fujin holds it (edited, new or Fujin's), or None."""
        return self.descriptions.get(effect) or self.shipped_description(effect)

    def _changed_effects(self):
        """The effects Save writes a file of: described, with edited parameters, an edited description
        or new."""
        return [effect for effect in sorted(set(self.descriptions) | set(self.effect_params))
                if self.description(effect) is not None and (effect in self.descriptions or self.effect_params.get(effect))]

    def _files_effect(self, effect):
        """The effect whose files an effect reads: a new effect's base."""
        return self.descriptions.get(effect, {}).get("base", effect)

    def _schema(self, effect):
        """The parameter table of an effect's part tabs: its description's when edited here, else the
        recorder's (FFNx's port)."""
        if effect is None:
            return None
        schema = description_schema(self.descriptions[effect]) if effect in self.descriptions else effect_schema(effect)
        return with_script_parts(schema, self.description(effect))

    def _script_manager(self, effect):
        """(an effect's script parts, the imported file they edit): None for the file when it is not imported or
        not laid out as they say."""
        script = (self.description(effect) or {}).get("script")
        if not script:
            return None, None
        name = self.effect_params.get(effect, {}).get(script["param"]) or script["file"]
        manager = next((m for m in self.mag_editor.managers.values() if os.path.basename(m.file_path).lower() == name.lower()), None)
        return script, manager if manager is not None and script_matches(script, manager.data) else None

    def _part_values(self, effect):
        """The values a part tab shows: an effect's parameters, its script's as its file holds them."""
        script, manager = self._script_manager(effect)
        return {**self.effect_params.get(effect, {}), **(script_values(script, manager.data) if manager else {})}

    def _sync_script_parts(self):
        """The script parts' tabs as the file is (an undo, a Script tab edit, the file imported or closed)."""
        script, manager = self._script_manager(self.current_effect)
        if not script:
            return
        values = self._part_values(self.current_effect)
        for tab in self.part_tabs:
            if any(is_script_key(field["key"]) for field in tab.fields):
                tab.set_values(values)
                tab.set_fields_enabled(manager is not None)

    def _script_changed(self, key, value):
        """A script part's value: written in the effect's file, as an edit of it (Save writes the file)."""
        script, manager = self._script_manager(self.current_effect)
        if manager is None:
            return
        field = next(field for field in script["fields"] if field["key"] == key)
        # at once, one undo step: a choice's places go together
        places = edits(field, value, manager.data)
        start, end = min(at for at, _raw in places), max(at + len(raw) for at, raw in places)
        changed = bytearray(manager.data[start:end])
        for at, raw in places:
            changed[at - start:at - start + len(raw)] = raw
        if manager.patch_bytes(start, changed):
            self.mag_editor._section_edited()
            self._params_refresh.start()

    def _preview_script_values(self, files, values):
        """The effect's files with these script values (a part tab's compare): the recordings' only."""
        script, manager = self._script_manager(self.current_effect)
        if manager is None:
            return files
        name = os.path.basename(manager.file_path)
        return {**files, name: apply_script_values(script, files.get(name, bytes(manager.data)), values)}

    def effect_program(self, effect):
        """The program an effect's previews run (one whose description is edited here, or a new
        effect), with its edited parameters; None: its exe code or FFNx's port."""
        if effect not in self.descriptions:
            return None
        try:
            return compile_program(self.descriptions[effect], self.effect_params.get(effect))
        except (DescriptionError, KeyError, TypeError, ValueError):
            return None

    def _show_description(self):
        effect = self.current_effect
        kind = "new" if self.is_new_effect(effect) else "edited" if effect in self.descriptions else "shipped"
        self.description_view.show_description(effect, self.description(effect) if effect is not None else None, kind)
        self.data_view.show_data(self.description(effect) if effect is not None else None)
        built = "template_parts" in self.descriptions.get(effect, {})
        self.choreography.setTabVisible(self.choreography.indexOf(self.plus_tab), built)
        info = self.catalog.info(effect) if effect is not None else {}
        free_slot = bool(info.get("free")) and effect not in self.descriptions
        self.create_button.setVisible(free_slot)
        self.copy_here_button.setVisible(free_slot)
        self.copy_button.setVisible(effect is not None and self.description(effect) is not None)

    # ------------------------------------------------------------------ an effect built part by part (+ tab)
    def create_effect_here(self, name=None):
        """An empty effect in the shown free slot; Choreography opens on its + tab. Its id, or None."""
        effect = self.current_effect
        if effect is None or not self.catalog.info(effect).get("free") or effect in self.descriptions:
            return None
        if name is None:
            from PyQt6.QtWidgets import QInputDialog
            name, ok = QInputDialog.getText(self, "New effect", f"Name of effect {effect}:", text="New effect")
            if not ok or not name.strip():
                return None
        self.descriptions[effect] = effecttemplates.empty_effect(effect, name.strip())
        self._update_effect_rows(refresh=False)
        self._description_changed()
        self.tabs.setCurrentIndex(2)
        return effect

    def _exe_bytes(self):
        path = self.camera_editor.exe_binding.current_path
        try:
            return Path(path).read_bytes() if path else None
        except OSError:
            return None

    def effect_parts(self, effect=None):
        """The parts of an effect built part by part ([] for none yet), or None for another effect."""
        description = self.descriptions.get(self.current_effect if effect is None else effect, {})
        return list(description["template_parts"]) if "template_parts" in description else None

    def _rebuild(self, parts):
        effect = self.current_effect
        old = self.descriptions[effect]
        self.descriptions[effect] = effecttemplates.build_effect(effect, old["name"], parts, self._exe_bytes(), keep=old)
        # parameters the effect no longer has: their edited values go
        keys = {param["key"] for param in self.descriptions[effect]["params"]}
        if effect in self.effect_params:
            self.effect_params[effect] = {k: v for k, v in self.effect_params[effect].items() if k in keys}
        self._description_changed()

    def add_part(self, key):
        """The part `key` (Fujin.effecttemplates) added to the shown effect, with the parts it needs
        that it has not yet; its tab shown."""
        parts = self.effect_parts()
        added = effecttemplates.with_needs(parts, key) if parts is not None else []
        if not added:
            return False
        self._rebuild(parts + added)
        part = effecttemplates.TEMPLATES[key][4]
        tab = next((tab for tab in self.part_tabs if tab.part["key"] == part), None)
        self.choreography.setCurrentWidget(tab or self.description_view)
        return True

    def remove_part(self, key, confirm=True):
        """The part `key` and the parts that need it removed from the shown effect."""
        parts = self.effect_parts()
        if parts is None or key not in parts:
            return False
        gone = effecttemplates.dependents(parts, key)
        if confirm and len(gone) > 1:
            names = ", ".join(effecttemplates.title(k) for k in gone)
            if QMessageBox.question(self, "Fujin", f"Remove {names}? The others need {effecttemplates.title(key)}.") \
                    != QMessageBox.StandardButton.Yes:
                return False
        self._rebuild([k for k in parts if k not in gone])
        return True

    def _choreography_tab_changed(self, index):
        """The + tab is never the tab shown (Qt moves onto it when tabs go): back to the one before."""
        if self.choreography.widget(index) is not self.plus_tab:
            self._choreography_tab = index
            return
        back = self._choreography_tab if self._choreography_tab != index else 0
        with QSignalBlocker(self.choreography):
            self.choreography.setCurrentIndex(back if back < self.choreography.count() else 0)

    def _choreography_tab_clicked(self, index):
        """The + tab clicked: its menu."""
        if self.choreography.widget(index) is not self.plus_tab:
            return
        menu = self.parts_menu()
        if menu is not None:
            bar = self.choreography.tabBar()
            menu.exec(bar.mapToGlobal(bar.tabRect(index).bottomLeft()))

    def parts_menu(self):
        """The + tab's menu: the parts of the effect's kind, named as their tabs, by group - the ones
        it has ticked, the others added with the parts they need. An effect with no part yet: one
        submenu per kind (Cure's, Hypnotize's), its first part choosing it."""
        from PyQt6.QtWidgets import QMenu
        parts = self.effect_parts()
        if parts is None:
            return None
        menu = QMenu(self)
        kind = effecttemplates.family(parts)
        if kind is None:
            for kind, label in effecttemplates.FAMILIES.items():
                self._fill_parts_menu(menu.addMenu(label), parts, kind)
        else:
            self._menu_header(menu, effecttemplates.FAMILIES[kind])
            self._fill_parts_menu(menu, parts, kind)
        return menu

    @staticmethod
    def _menu_header(menu, text):
        """A section's title, shown in every style (Windows' menus draw addSection as a line only)."""
        if menu.actions():
            menu.addSeparator()
        header = menu.addAction(text)
        font = header.font()
        font.setBold(True)
        header.setFont(font)
        header.setEnabled(False)

    def _fill_parts_menu(self, menu, parts, kind):
        for group in effecttemplates.GROUPS:
            keys = [k for k, t in effecttemplates.TEMPLATES.items() if t[1] == group and t[2] == kind]
            if not keys:
                continue
            self._menu_header(menu, group)
            for key in keys:
                added = effecttemplates.with_needs(parts, key)
                others = [effecttemplates.title(k) for k in added if k != key]
                text = effecttemplates.title(key) + (f" (with {', '.join(others)})" if others else "")
                action = menu.addAction(f"{text}\t{effecttemplates.hint(key)}")
                action.setToolTip(effecttemplates.TEMPLATES[key][8])
                action.setStatusTip(effecttemplates.TEMPLATES[key][8])
                if key in parts:
                    action.setCheckable(True)
                    action.setChecked(True)
                    action.setEnabled(False)
                else:
                    action.triggered.connect(lambda _checked=False, k=key: self.add_part(k))
        menu.setToolTipsVisible(True)

    def part_template(self, tab):
        """The part (Fujin.effecttemplates key) a part tab of an effect built part by part shows, or None."""
        parts = self.effect_parts()
        if parts is None or tab not in self.part_tabs:
            return None
        return next((key for key in parts if effecttemplates.TEMPLATES[key][4] == tab.part["key"]), None)

    def part_tab_menu(self, index):
        """A part tab's right-click menu: Remove (with the parts that need it), or None."""
        from PyQt6.QtWidgets import QMenu
        key = self.part_template(self.choreography.widget(index))
        if key is None:
            return None
        menu = QMenu(self)
        parts = self.effect_parts()
        others = [effecttemplates.title(k) for k in effecttemplates.dependents(parts, key) if k != key]
        text = f"Remove {effecttemplates.title(key)}" + (f" (and {', '.join(others)})" if others else "")
        menu.addAction(text).triggered.connect(lambda _checked=False: self.remove_part(key))
        return menu

    def _choreography_tab_menu(self, pos):
        bar = self.choreography.tabBar()
        menu = self.part_tab_menu(bar.tabAt(pos))
        if menu is not None:
            menu.exec(bar.mapToGlobal(pos))

    def _data_changed(self, key, entry):
        """An entry of the Data tab applied: the effect's description takes it."""
        self.descriptions[self.current_effect]["data"][key] = entry
        self._description_changed()

    def _data_vram(self):
        """The video memory the Data tab draws sequence frames from: the last recording's, or None."""
        recording = self.lab.recording or self.native_preview.recording
        return recording.vram_at(len(recording.ticks) - 1) if recording is not None and recording.ticks else None

    def _play_archive(self, archive):
        if self.sound_panel._can_play(archive):
            self.sound_panel.play(archive)

    def _description_applied(self, description):
        effect = self.current_effect
        if "base" not in description and description == self.shipped_description(effect):
            self.descriptions.pop(effect, None)          # back to Fujin's own
        else:
            self.descriptions[effect] = description
        self._description_changed()

    def _description_reset(self):
        effect = self.current_effect
        new = self.is_new_effect(effect)
        self.descriptions.pop(effect, None)
        if new:
            self.effect_params.pop(effect, None)
        self._description_changed()

    def _description_changed(self):
        self._mark_modified_effects()
        self._update_effect_rows(refresh=False)
        self.native_preview.set_effect(self.current_effect, self.effect_name(self.current_effect))
        self._build_part_tabs()
        self._show_description()
        self._params_edited()

    def copy_effect_here(self, source_effect=None, name=None):
        """A copy of a described effect (asked for when not given) in the shown free slot. Its id, or None."""
        from PyQt6.QtWidgets import QInputDialog
        effect = self.current_effect
        if effect is None or not self.catalog.info(effect).get("free") or effect in self.descriptions:
            return None
        if source_effect is None:
            sources = sorted(set(described_effects()) | {e for e in self.descriptions if e != effect})
            labels = [f"{e} — {self.effect_name(e)}" for e in sources]
            choice, ok = QInputDialog.getItem(self, "Copy an effect here", f"Effect copied into {effect}:", labels, 0, False)
            if not ok:
                return None
            source_effect = sources[labels.index(choice)]
        return self.new_effect_dialog(effect, name, source_effect)

    def new_effect_dialog(self, effect_id=None, name=None, source_effect=None):
        """A copy of the description of `source_effect` (default: the shown effect) as a new effect in
        a free slot (asked for when not given); the new effect is selected. Its id, or None."""
        from PyQt6.QtWidgets import QInputDialog
        if source_effect is None:
            source_effect = self.current_effect
        source = self.description(source_effect)
        if source is None:
            return None
        free = [e for e in FREE_EFFECTS if e not in self.descriptions]
        if not free:
            QMessageBox.information(self, "Fujin", "Every free slot of the effect table holds a new effect already.")
            return None
        if effect_id is None:
            choice, ok = QInputDialog.getItem(self, "New effect", "Effect id (a free slot of the game's effect table):",
                                              [str(e) for e in free], 0, False)
            if not ok:
                return None
            effect_id = int(choice)
        if name is None:
            name, ok = QInputDialog.getText(self, "New effect", "Name:", text=f"New {source['name']}")
            if not ok or not name.strip():
                return None
        if effect_id not in free:
            raise ValueError(f"effect {effect_id} is not a free slot")
        # with the exe open, its data (sequences, sounds, layouts, camera...) is copied into the effect
        exe_path = self.camera_editor.exe_binding.current_path
        try:
            exe = Path(exe_path).read_bytes() if exe_path else None
        except OSError:
            exe = None
        self.descriptions[effect_id] = new_effect(source, effect_id, name.strip(), exe)
        if self.effect_params.get(source_effect):
            self.effect_params[effect_id] = dict(self.effect_params[source_effect])
        if effect_id == self.current_effect:          # a copy into the free slot shown
            self._description_changed()
        else:
            self._update_effect_rows(refresh=False)
            self._mark_modified_effects()
            self.select_effect(effect_id)
        self.tabs.setCurrentIndex(2)
        self.choreography.setCurrentWidget(self.description_view)
        return effect_id

    def import_effects(self, paths=None):
        """Header Import complementary: Fujin's effect files (FujinEffects/effect_NNN.fxprog, what Save
        writes): each effect's parameters and, for an edited one or a new one, its description."""
        if paths is None:
            folder = self.file_registry.last_folder(PROGRAM_FOLDER_KEY) or os.path.join(
                self.file_registry.last_folder("Fujin effect export") or os.getcwd(), PROGRAM_FOLDER)
            paths = QFileDialog.getOpenFileNames(self, "Import Fujin effects (FujinEffects/effect_NNN.fxprog)",
                                                 folder, "Fujin effects (*.fxprog)")[0]
        clean = self._native_signature() == self._exported_signature
        loaded, read = [], []
        for path in paths:
            try:
                with open(path, encoding="ascii") as file:
                    effect, description, values = read_effect_file(file.read())
            except (OSError, ValueError, KeyError, TypeError, UnicodeDecodeError) as error:
                QMessageBox.warning(self, "Fujin", f"Cannot read {os.path.basename(path)}: {error}")
                continue
            if description is not None:
                self.descriptions[effect] = description
            else:
                self.descriptions.pop(effect, None)
            self.effect_params[effect] = values
            loaded.append(effect)
            read.append(str(path))
        if read:
            # added to those remembered (one effect per file, imported one at a time): Auto-upload reopens them all
            earlier = [path for path in self.file_registry.last_files(PROGRAM_SELECTION_KEY) or [] if os.path.isfile(path)]
            self.file_registry.remember_files(PROGRAM_SELECTION_KEY, earlier + read)
            self.file_registry.remember_folder(PROGRAM_FOLDER_KEY, os.path.dirname(read[-1]))
        if loaded and clean:
            self._exported_signature = self._native_signature()     # what the files hold: nothing to save
        if loaded:
            self._update_effect_rows(refresh=False)
            self._mark_modified_effects()
            if self.current_effect in loaded:
                self._description_changed()
        return loaded

    # ------------------------------------------------------------------ effect parameters (part tabs)
    def effect_parameters(self, effect_id):
        """{key: value} of an effect's parameters not at the game's value (FFNx fx_params.h)."""
        return dict(self.effect_params.get(effect_id, {}))

    def _build_part_tabs(self):
        """Choreography's part tabs for the selected effect: one per part of its C++ port's
        parameter table (none when FFNx has no port with parameters for it). The part tab shown
        stays shown when the new tabs have one of the same key."""
        shown = self.choreography.currentWidget()
        shown_key = shown.part["key"] if shown in self.part_tabs else None
        for tab in self.part_tabs:
            self.choreography.removeTab(self.choreography.indexOf(tab))
            tab.deleteLater()
        self.part_tabs = []
        effect = self.current_effect
        schema = self._parts_schema = self._schema(effect)
        self._show_parts_note()
        if schema is None:
            return
        drawing = frozenset(part["id"] for part in schema["parts"] if part["id"])
        names = {0: "The target"} | {part["id"]: part["title"] for part in schema["parts"] if part["id"]}
        # what its code reads at a fixed place of the exe: under the part that previews the whole effect
        whole = next((part for part in schema["parts"] if not part["id"]), next(iter(schema["parts"]), None))
        fixed = (self.description(effect) or {}).get("not_editable", [])
        for part in schema["parts"]:
            fields = [field for field in schema["fields"] if field["part"] == part["key"]]
            # Cure's ring spawns the other parts: their windows count its ticks
            ring = next((p for p in schema["parts"] if p["key"] == "ring"), None)
            spawner = (ring["id"], ring["title"]) if ring and part is not ring and part["id"] else None
            tab = PartTab(part, fields, self._part_values(effect), self.lab, gl_renderer, drawing, self._locate_texture, names,
                          schema.get("groups", []), self.sound_panel, spawner, fixed if part is whole else ())
            tab.value_changed.connect(self._param_changed)
            tab.preview.reference_toggled.connect(self._part_reference)
            self.part_tabs.append(tab)
            index = self.choreography.insertTab(self.choreography.indexOf(self.plus_tab), tab, part["title"])
            self.choreography.setTabToolTip(index, part["doc"])
            if part["key"] == shown_key:
                self.choreography.setCurrentWidget(tab)
        self._sync_script_parts()

    def _recorder_built(self):
        """The recorder's build started or ended (the updater brought FFNx's effect sources): the
        part tabs of the new recorder, kept as they are when its parameter table did not change."""
        if recorder_build().building:
            self._show_parts_note()
            return
        if self.current_effect is not None and self._schema(self.current_effect) != self._parts_schema:
            self._build_part_tabs()
        else:
            self._show_parts_note()
        # the old recorder's recording goes: the tab shown records again with the new one
        self.lab.params_changed()
        self._record_parts()

    def _show_parts_note(self):
        """Why there are no part tabs: the recorder is being built, or lacks FFNx's effect sources."""
        building = recorder_build().building
        self.parts_note.setText("" if self._parts_schema is not None else
                                PORTS_BUILDING if building else "" if recorder_has_ports() else PORTS_MISSING)
        self.parts_note.setVisible(bool(self.parts_note.text()))

    def _locate_texture(self, sheet, pieces, label):
        """(file name, show) of the effect's TIM a part tab's image is loaded from (Textures tab's
        sources), show() opening it there with the pieces outlined; None when none loads it."""
        for source in range(self.textures.sources.count()):
            manager = self.resolve(self.textures.sources.itemData(source))
            if manager is None or manager.document.format != "PlayStation TIM":
                continue
            for index, (offset, _section) in enumerate(tim_blocks(manager)):
                found = sheet_in_tim(TimTexture(manager, offset), sheet.x, sheet.y, sheet.depth, sheet.clut_xy,
                                     pieces)
                if found:
                    name = os.path.basename(manager.file_path) + (f" (TIM{index})" if index else "")

                    def show(source=source, index=index, found=found):
                        self.textures.sources.setCurrentIndex(source)
                        self.tabs.setCurrentWidget(self.textures)
                        self.textures.activate()
                        self.textures.display.setCurrentIndex(0)
                        self.textures.panel.outline(index, found[0], found[1], label)
                    return name, show
        return None

    def _texture_uses(self, manager):
        """({TIM index: (rects, palette rows)}, note) of what the effect's recording draws from the
        TIMs of `manager` (a part tab's recording, else the Overview's), None without one."""
        recording = self.lab.recording or self.native_preview.recording
        if recording is None or not recording.ticks or manager is None:
            return None
        if self._sheets[0] is not recording:
            parts = {part for tick in recording.ticks for part in tick.parts} - {0}
            self._sheets = (recording, texture_sheets(recording, parts or None))
        uses = {}
        for index, (offset, _section) in enumerate(tim_blocks(manager)):
            texture = TimTexture(manager, offset)
            rects, rows = set(), set()
            for sheet in self._sheets[1]:
                found = sheet_in_tim(texture, sheet.x, sheet.y, sheet.depth, sheet.clut_xy, sheet.all_pieces())
                if found:
                    rows.add(found[0])
                    rects.update(found[1])
            uses[index] = (sorted(rects), rows)
        source = "a part tab's recording" if recording is self.lab.recording else "the Overview's recording"
        return uses, f"From {source}: dimmed what the effect never draws from, outlined the pieces it does"

    def _part_reference(self, on):
        """A part preview's Target box: the same for every part tab."""
        for tab in self.part_tabs:
            tab.preview.set_reference(on)

    def _param_changed(self, key, value):
        if is_script_key(key):
            return self._script_changed(key, value)
        effect = self.current_effect
        schema = self._schema(effect)
        if schema is None:
            return
        values = self.effect_params.setdefault(effect, {})
        if value == schema_defaults(schema).get(key):
            values.pop(key, None)
        else:
            values[key] = value
        self._params_refresh.start()

    def _params_edited(self):
        """Parameters edited (coalesced): both previews record with them, Save writes them."""
        self.lab.params_changed()
        self.native_preview.params_changed()
        self._refresh()

    def _record_parts(self):
        """A part tab shown: record the effect for them if it is not yet."""
        if (self.choreography.currentWidget() in self.part_tabs and self.lab.recording is None
                and self.lab._process is None):
            self.lab.record()
            self.choreography.currentWidget().preview.refresh()

    def can_save_folder(self):
        return self.mag_editor.can_save_folder() or self._native_signature() != self._exported_signature

    def has_unsaved_changes(self):
        return self.can_save_folder()   # a modified mag file or an unexported native preview

    def undo(self):
        return self._history(False)

    def redo(self):
        return self._history(True)

    def _history(self, redo):
        for view in self.component_views:
            if view.isVisible():
                manager = self.resolve(view.sources.currentData())
                if manager and (manager.redo() if redo else manager.undo()):
                    self._resource_changed()
                    return True
        if self.tabs.currentIndex() == 2:
            result = self.mag_editor.redo() if redo else self.mag_editor.undo()
            self._schedule_refresh()
            return result
        return False

    def save_files(self, output_dir=None):
        native_dirty = self._native_signature() != self._exported_signature
        written = [m.file_path for m in self.mag_editor.managers.values() if m.modified]
        outputs, stale = {}, []
        if native_dirty:
            if output_dir is None:
                output_dir = QFileDialog.getExistingDirectory(self, "Export effect patch and resized camera files",
                    self.file_registry.last_folder("Fujin effect export") or os.getcwd())
            if not output_dir:
                return False
            folder = Path(output_dir).resolve()
            try:
                text = self.camera_editor.manager.hext_text().replace("#Fujin camera effect patch", "#Fujin battle effect patch", 1)
                text += "\n" + "\n".join(self.native.hext_lines())
                outputs[folder / f"effects_{self.camera_editor.manager.language_name}.hext"] = text.encode("utf-8")
                for track in self.camera_editor.manager.resized_tracks():
                    outputs[folder / CAM_FFNX_FOLDER / cam_file_name(track.effect_id)] = self.camera_editor.manager.cam_bytes(track)
                # one file per changed effect (edited parameters, edited description, new effect): its
                # program, run in the game by FujinEffects.dll, and what Fujin reopens it from
                programs = 0
                for effect in self._changed_effects():
                    try:
                        text = effect_file_text(self.description(effect), self.effect_params.get(effect),
                                                edited=effect in self.descriptions)
                    except DescriptionError as error:
                        raise ValueError(f"Effect {effect}'s description: {error}") from None
                    outputs[folder / PROGRAM_FOLDER / program_file_name(effect)] = text.encode("ascii")
                    programs += 1
                # an effect file of an earlier Save whose effect is back to the game's: gone
                for path in sorted((folder / PROGRAM_FOLDER).glob("effect_*.fxprog")):
                    if path not in outputs and SOURCE.encode("ascii") in path.read_bytes():
                        stale.append(path)
                if programs and HOST_DLL.is_file():
                    outputs[folder / HOST_DLL.name] = HOST_DLL.read_bytes()
                for path, digest in self._owned_cam_exports.items():
                    if path not in outputs and path.is_relative_to(folder):
                        if path.exists() and hashlib.sha256(path.read_bytes()).digest() != digest:
                            raise ValueError(f"Previously exported camera was modified outside Fujin: {path}")
                        stale.append(path)
            except (ValueError, OSError) as error:
                QMessageBox.warning(self, "Fujin", str(error))
                return False
        try:
            from PyQt6.QtCore import QSaveFile, QIODevice
            for path, data in outputs.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                file = QSaveFile(str(path))
                if not file.open(QIODevice.OpenModeFlag.WriteOnly) or file.write(data) != len(data) or not file.commit():
                    raise OSError(f"Could not write {path}: {file.errorString()}")
            for path in stale:
                path.unlink(missing_ok=True)
            if self.mag_editor.save_files() is False:
                return False
        except OSError as error:
            QMessageBox.warning(self, "Fujin", f"Save did not complete: {error}")
            return False
        if native_dirty:
            self.file_registry.remember_folder("Fujin effect export", str(output_dir))
            self._exported_signature = self._native_signature()
            for path in stale:
                self._owned_cam_exports.pop(path, None)
            self._owned_cam_exports.update({p: hashlib.sha256(data).digest() for p, data in outputs.items() if p.suffix == CAM_EXTENSION})
        written += [str(path) for path in outputs]
        self._saved_note = (f"saved {', '.join(os.path.basename(p) for p in written)} at {time.strftime('%H:%M')}"
                            if written else "nothing to save")
        self.context.setToolTip("Written by the last Save:\n" + "\n".join(written) if written else "")
        self._refresh()
        return True

    def import_hext(self, path=None):
        if not self.camera_editor.manager.loaded:
            QMessageBox.information(self, "Fujin", "Import the FF8 exe before applying an effect patch.")
            return False
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "Import Fujin effect patch", "", "Hext (*.hext)")
        if not path:
            return False
        try:
            apply_effect_hext(Path(path).read_text(encoding="utf-8"), self.camera_editor.manager, self.native)
        except (OSError, ValueError, IndexError) as error:
            QMessageBox.warning(self, "Fujin", f"Patch was not applied: {error}")
            return False
        self.camera_editor._after_tracks_changed()
        self._refresh()
        return True
