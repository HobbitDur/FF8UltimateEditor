import os
import pathlib
from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QMessageBox, QCheckBox, QProgressDialog, QApplication
)
from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from Ifrit.IfritAI.ifritaiwidget import IfritAIWidget
from Ifrit.ifritmanager import IfritManager
from Ifrit.fpsbatchdialog import (FpsBatchDialog, FpsBatchReportDialog,
                                  select_battle_model_file_list)
from Ifrit.IfritDynamicTexture.ifritdynamictexturewidget import IfritDynamicTextureWidget
from Ifrit.IfritSeq.ifritseqwidget import IfritSeqWidget
from Ifrit.IfritCameraSeq.ifritcameraseqwidget import IfritCameraSeqWidget, _CAMERA_SECTION_BY_ENTITY
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


class IfritMonsterWidget(QWidget):
    """IfritAI + IfritSeq + Ifrit3D with a single shared file toolbar."""

    def __init__(self, settings:QSettings, icon_path="Resources", game_data_folder="FF8GameData",
                 file_registry=None):
        super().__init__()
        if file_registry is None:  # Used alone, it shares its files with nobody
            file_registry = FileRegistry()
        self.settings = settings
        self.icon_path = icon_path
        self.file_loaded = ""
        self._file_dialog_folder = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Shared toolbar ───────────────────────────────────────────
        toolbar = QWidget()
        tl = QHBoxLayout(toolbar)
        tl.setContentsMargins(6, 4, 6, 4)
        tl.setSpacing(4)

        # The .dat this tool edits, driven by the shared header toolbar (Import / Save / Reload).
        # Its name varies (c0m*.dat, d?c???.dat...), so the binding keys it generically and the
        # open dialog just filters on *.dat.
        self.dat_binding = FileBinding("battle model (.dat)", file_registry,
                                       load_callback=self.load_file, save_callback=self._save_file,
                                       file_filter="*.dat")

        # Add Cronos checkbox
        self._cronos_checkbox = QCheckBox("Cronos")
        self._cronos_checkbox.setToolTip("Load AI data with cronos configuration")
        self._cronos_checkbox.setChecked(self.settings.value("ifrit/cronos_checkbox", defaultValue=False, type=bool))
        self._cronos_checkbox.stateChanged.connect(self._on_cronos_toggled)

        self._monster_label = QLabel("No file loaded")

        self._fps_batch_btn = QPushButton("Files to 30/60 FPS...")
        self._fps_batch_btn.setToolTip("Convert the animations of several .dat files at once to\n"
                                       "30 or 60 fps, without opening them one by one.")
        self._fps_batch_btn.clicked.connect(self._convert_files_to_fps)

        for w in [self._cronos_checkbox, self._fps_batch_btn, self._monster_label]:
            tl.addWidget(w)
        tl.addStretch()

        self.ifrit_manager = IfritManager(game_data_folder)
        # ── Sub-widgets ──────────────────────────────────────────────
        # AI: keeps its own sub-toolbar (expert, section, color…) minus file buttons
        self._ai_widget = IfritAIWidget(settings, self.ifrit_manager, icon_path=icon_path)

        # Seq: keeps xml import/export sub-toolbar minus file buttons
        self._seq_widget = IfritSeqWidget(self.ifrit_manager, icon_path=icon_path)

        # Camera: monster section 6 (camera animation collection / keyframes)
        self._camera_widget = IfritCameraSeqWidget(self.ifrit_manager, icon_path=icon_path)

        # 3D: keeps its own sub-toolbar (mesh/wire/play/frame…)
        self._3d_widget = Ifrit3DWidget(self.ifrit_manager, show_controls=True)

        self._texture_widget = IfritTextureWidget(self.ifrit_manager)
        self._xlsx_widget = IfritXlsxWidget(self.ifrit_manager)
        self._stat_widget = IfritStatWidget(self.ifrit_manager, icon_path=icon_path)
        self._name_widget = IfritMonsterNameWidget(self.ifrit_manager)
        self._battle_text_widget = IfritBattleTextWidget(self.ifrit_manager)

        # This need to be loaded after the texture widget
        self._dynamic_texture_widget = IfritDynamicTextureWidget(self.ifrit_manager)

        # Name, Stat and StatExcel all edit section 7 (name used to be duplicated into the
        # AI tab's Battle text sub-tab too), so they live together under one "Stat" tab.
        self._stat_container = QTabWidget()
        self._stat_container.addTab(self._name_widget, "Name")
        self._stat_container.addTab(self._stat_widget, "Editor")
        self._stat_container.addTab(self._xlsx_widget, "Excel (xlsx)")

        # Battle text edits section 8 (battle_script_data['battle_text']), the same section
        # as AI - only the monster name it also shows is section 7. It lives under "AI" as a
        # sub-tab rather than as its own top-level entry.
        self._ai_container = QTabWidget()
        self._ai_container.addTab(self._ai_widget, "AI script")
        self._ai_container.addTab(self._battle_text_widget, "Battle text")

        # ── Tabs ─────────────────────────────────────────────────────
        # Ordered to match the .dat section layout, with each tab's section number in its
        # label (monster numbering). Sequence and Camera sit at different sections depending
        # on the file type, so their number is refreshed per loaded file (see
        # _update_section_tab_labels); the rest are monster-only or section-stable.
        self._tabs = QTabWidget()
        self._tabs.addTab(self._3d_widget, "1/2/3 - 3D")
        self._tabs.addTab(self._dynamic_texture_widget, "4 - Dynamic Texture")
        self._tabs.addTab(self._seq_widget, "5 - Sequence")
        self._tabs.addTab(self._camera_widget, "6 - Camera")
        self._tabs.addTab(self._stat_container, "7 - Stat")
        self._tabs.addTab(self._ai_container, "8 - AI")
        self._tabs.addTab(self._texture_widget, "11 - Static Texture")
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._tabs.setCurrentIndex(self.settings.value("ifrit/current_tab", defaultValue=0, type=int))

        root.addWidget(toolbar)
        root.addWidget(self._tabs, 1)

        # Ctrl+S = the Save toolbar button, from anywhere inside this tool
        self._save_shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        self._save_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._save_shortcut.activated.connect(self._on_save_shortcut)

        self._on_tab_changed(0)
        self._on_cronos_toggled( self._cronos_checkbox.isChecked())
        self.dat_binding.load_opened_file()  # another tool instance may have opened one already

    def file_bindings(self):
        """The file the shared header toolbar drives for this tool (the loaded .dat)."""
        return [self.dat_binding]

    # ── Tab switching ─────────────────────────────────────────────────

    def _on_tab_changed(self, index: int):
        self.settings.setValue("ifrit/current_tab", self._tabs.currentIndex())

    # ── Cronos checkbox handler ───────────────────────────────────────

    def _on_cronos_toggled(self, state):
        """Handle Cronos checkbox state changes"""
        if state:  # Checked
            self.ifrit_manager.game_data.load_ai_data("ai_cronos.json")
        else:  # Unchecked
            self.ifrit_manager.game_data.load_ai_data("ai_vanilla.json")
        self.settings.setValue("ifrit/cronos_checkbox", state)
        # Call reload function to refresh the display
        self._reload_file()


    # ── File operations ───────────────────────────────────────────────

    def load_file(self, path):
        """Load a .dat file (path from the shared header toolbar), then show only the tabs the
        loaded entity type actually has."""
        if path:
            self._file_dialog_folder = os.path.dirname(path)
            self._load_all(path)
            entity_type = self.ifrit_manager.enemy.entity_type
            # Stat/StatExcel/AI/Battle text only have real, parsed data for entity types in
            # _STAT_AI_CAPABLE_ENTITY_TYPES (see MonsterAnalyser.analyse_loaded_data -
            # character/weapon files never populate info_stat_data or battle_script_data).
            # _stat_container wraps Stat + StatExcel (both section 7-equivalent); _ai_container
            # wraps AI + Battle text (both section 8-equivalent). Gate the containers, not the
            # inner widgets - they are no longer direct children of the top-level tabs.
            # Tabs that don't apply to the loaded entity type are hidden outright (setTabVisible),
            # not just disabled - a merely-greyed-out Stat tab on a weapon file still invites a
            # click; hiding makes "this file has no such section" unambiguous.
            stat_ai_visible = entity_type in _STAT_AI_CAPABLE_ENTITY_TYPES
            for widget in (self._stat_container, self._ai_container):
                self._tabs.setTabVisible(self._tabs.indexOf(widget), stat_ai_visible)
            # Static Texture is MONSTER-only: MONSTER_NO_MODEL has no texture section either.
            self._tabs.setTabVisible(self._tabs.indexOf(self._texture_widget),
                                      entity_type == EntityType.MONSTER)
            # 3D, Sequence, Camera and Dynamic Texture each sit at a different section (or are
            # absent) per entity type - gate every one of them on the actually-loaded entity
            # type rather than a filename heuristic. A filename heuristic misclassifies e.g.
            # Edea (d7c016.dat, CHARACTER_NO_WEAPON): her third filename character is 'c' like
            # an armed character, but her body carries a real, parsed Sequence section (S6).
            self._tabs.setTabVisible(self._tabs.indexOf(self._3d_widget),
                                      entity_type in _3D_SECTIONS_BY_ENTITY)
            self._tabs.setTabVisible(self._tabs.indexOf(self._seq_widget),
                                      entity_type in _SEQ_SECTION_BY_ENTITY)
            self._tabs.setTabVisible(self._tabs.indexOf(self._camera_widget),
                                      entity_type in _CAMERA_SECTION_BY_ENTITY)
            self._tabs.setTabVisible(self._tabs.indexOf(self._dynamic_texture_widget),
                                      entity_type in _DYNAMIC_TEXTURE_SECTION_BY_ENTITY)
            self._update_section_tab_labels()

    def _update_section_tab_labels(self):
        """Refresh the 3D/Sequence/Camera/Dynamic Texture tab numbers for the loaded file: each
        sits at a different .dat section (or is absent) depending on the entity type - see
        _3D_SECTIONS_BY_ENTITY / _SEQ_SECTION_BY_ENTITY / _CAMERA_SECTION_BY_ENTITY /
        _DYNAMIC_TEXTURE_SECTION_BY_ENTITY. A tab that doesn't apply to this entity type keeps
        the monster default so a disabled tab still reads sensibly. Stat/AI/Static Texture are
        not included here: they are monster-exclusive concepts (info-stat, battle AI script,
        static texture bank) with no equivalent section, by any number, on weapon/character
        files, so their fixed S7/S8/S11 labels only apply when the tab is actually enabled."""
        entity_type = self.ifrit_manager.enemy.entity_type
        threeD_section = _3D_SECTIONS_BY_ENTITY.get(entity_type, "1/2/3")
        seq_section = _SEQ_SECTION_BY_ENTITY.get(entity_type, 5)
        camera_section = _CAMERA_SECTION_BY_ENTITY.get(entity_type, 6)
        dyntex_section = _DYNAMIC_TEXTURE_SECTION_BY_ENTITY.get(entity_type, 4)
        self._tabs.setTabText(self._tabs.indexOf(self._3d_widget), f"{threeD_section} - 3D")
        self._tabs.setTabText(self._tabs.indexOf(self._seq_widget), f"{seq_section} - Sequence")
        self._tabs.setTabText(self._tabs.indexOf(self._camera_widget), f"{camera_section} - Camera")
        self._tabs.setTabText(self._tabs.indexOf(self._dynamic_texture_widget), f"{dyntex_section} - Dynamic Texture")

    def _convert_files_to_fps(self):
        """Convert the animations of several .dat files to 30 or 60 fps in one go."""
        folder = self._file_dialog_folder or os.path.dirname(self.file_loaded)
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
            report_list = self.ifrit_manager.convert_file_list_to_fps(
                file_list, target_fps, split_when_too_long, progress_callback=on_progress)
        finally:
            progress.setValue(len(file_list))

        FpsBatchReportDialog(self, report_list, target_fps).exec()
        # The loaded file may be one of the converted ones
        if self.file_loaded and any(os.path.normcase(f) == os.path.normcase(self.file_loaded)
                                    for f in file_list):
            self._reload_file()

    def _load_all(self, path: str):
        self.file_loaded = path
        self.ifrit_manager.init_from_file(path)
        entity_type = self.ifrit_manager.enemy.entity_type
        self._ai_widget.load_file(path)
        self._seq_widget.load_file(path)
        self._camera_widget.load_file(path)
        # 3D/Static Texture assume real geometry/texture data exists (e.g. numpy .min() on an
        # empty vertex array raises ValueError) - only load them for entity types that actually
        # have that data, matching the hidden-tab set in load_file. MONSTER_NO_MODEL (no model
        # sections at all) is the case this guards against; every other type already has real
        # geometry so this was never an issue for them.
        if entity_type in _3D_SECTIONS_BY_ENTITY:
            self._3d_widget.load_file()
        if entity_type == EntityType.MONSTER:
            self._texture_widget.load_file(path)
        # Name/Stat/Battle-text read info_stat_data/battle_script_data, only populated for
        # _STAT_AI_CAPABLE_ENTITY_TYPES (see MonsterAnalyser.analyse_loaded_data). On other
        # types that data is absent and their load_data() would crash (it assumes a monster).
        # Those tabs are hidden for such files anyway, so skip their data load.
        if entity_type in _STAT_AI_CAPABLE_ENTITY_TYPES:
            self._name_widget.load_data()
            self._stat_widget.load_data()
            self._battle_text_widget.load_data()
        if entity_type in _DYNAMIC_TEXTURE_SECTION_BY_ENTITY:
            self._dynamic_texture_widget.load_file(path) # need to be after texture
        try:
            name = self._ai_widget.ifrit_manager.enemy.info_stat_data['monster_name'].get_str().strip('\x00')
            self._monster_label.setText(f"{name}  [{pathlib.Path(path).name}]")
        except Exception:
            self._monster_label.setText(pathlib.Path(path).name)

    def _on_save_shortcut(self):
        if self.file_loaded:
            self._save_file()

    def _save_file(self):
        self._ai_widget.save_file()
        self._seq_widget.save_file()
        self._camera_widget.save_file()
        self._texture_widget.save_file()
        self._dynamic_texture_widget.save_file()
        self.ifrit_manager.save_file(self.file_loaded)

    def _reload_file(self):
        if self.file_loaded:
            self._load_all(self.file_loaded)

    def _show_info(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("Ifrit Monster Tools")
        msg.setText("Combined 3D / Stat / AI / Seq / Texture monster editor.\nDone by Hobbitdur.")
        msg.exec()