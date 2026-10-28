"""Ifrit's "Exe - Limit anim." tab: the battle anim sets of the exe that play on the loaded character
(limit breaks, Blue Magic cast, Shot, Duel, Angelo...), previewed and edited on its own skeleton.

A set comes from the FF8 exe (the shared "FF8 exe" file, opened here as a complementary file or in
any other tool) or from an FFNx effect_NNN.animset file: open one with "Import complementary" and
every effect_*.animset beside it is used. Like FFNx, a valid file wins over the exe. With neither,
the tab is hidden. See FF8GameData/dat/exeanimset.py for the format and FFNx's loader.

Edits stay in memory per set (a '*' marks them) until "Save .animset" (the FFNx file, any size) or
"Save into exe" (only while the set still fits its exe block: a 30 fps set never does)."""
import os

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton,
                             QTabWidget, QVBoxLayout, QWidget)

from Common.filebinding import FileBinding
from FF8GameData.dat import exeanimset
from FF8GameData.monsterdata import EntityType
from Ifrit.Ifrit3D.ifrit3dwidget import Ifrit3DWidget
from Ifrit.IfritAnimSet.animsetview import AnimSetHolder, AnimSetManagerView
from Ifrit.IfritSeq.ifritseqwidget import IfritSeqWidget

TAB_LABEL = "Exe - Limit anim."
ANIM_SET_FILE_NAME = "FFNx anim set (.animset)"   # the registry key of the .animset files
EXE_FILE_NAME = "FF8 exe"
SOURCE_EXE, SOURCE_FILE = "exe", "file"


class AnimSetSource(QObject):
    """Where the sets come from: the FF8 exe and/or a folder of FFNx .animset files, both
    complementary files of the shared registry. `changed` when either is opened or closed."""
    changed = pyqtSignal()

    def __init__(self, file_registry):
        super().__init__()
        self.exe_binding = FileBinding(EXE_FILE_NAME, file_registry, load_callback=lambda _path: self._reset(),
                                       file_filter="*.exe", read_only=True)
        self.exe_binding.file_closed.connect(lambda _path: self._reset())
        self.file_binding = FileBinding(ANIM_SET_FILE_NAME, file_registry, load_callback=lambda _path: self._reset(),
                                        file_filter="effect_*.animset", read_only=True)
        self.file_binding.file_closed.connect(lambda _path: self._reset())
        self._exe_offsets = None   # {AnimSetInfo: offset} of the opened exe, found once

    def bindings(self):
        return [self.exe_binding, self.file_binding]

    def load_opened_files(self):
        for binding in self.bindings():
            binding.load_opened_file()

    def _reset(self):
        self._exe_offsets = None
        self.changed.emit()

    def exe_path(self) -> str:
        return self.exe_binding.current_path if self.exe_binding.is_loaded else ""

    def folder(self) -> str:
        path = self.file_binding.current_path if self.file_binding.is_loaded else ""
        return os.path.dirname(path) if path else ""

    def has_data(self) -> bool:
        return bool(self.exe_path() or self.folder())

    def _offsets(self) -> dict:
        if self._exe_offsets is None:
            self._exe_offsets = {}
            if self.exe_path():
                with open(self.exe_path(), "rb") as file:
                    self._exe_offsets = exeanimset.locate_anim_sets(file.read())
        return self._exe_offsets

    def exe_offset(self, info):
        return self._offsets().get(info)

    def read_exe_set(self, info):
        """The set in the exe's block (as the exe holds it now), or None."""
        offset = self.exe_offset(info)
        if offset is None:
            return None
        with open(self.exe_path(), "rb") as file:
            file.seek(offset)
            block = file.read(info.size)
        size = int.from_bytes(block[4 * (info.section_count + 1):4 * (info.section_count + 2)], "little")
        return exeanimset.AnimSet.parse(block[:size], info)

    def file_path(self, info) -> str:
        folder = self.folder()
        return os.path.join(folder, info.file_name) if folder else ""

    def load(self, info):
        """(AnimSet, source, path, problem): the .animset file when there is a valid one (FFNx's rule),
        else the exe's set. problem: why a file next to the opened one was not used."""
        problem = ""
        path = self.file_path(info)
        if path and os.path.isfile(path):
            try:
                with open(path, "rb") as file:
                    return exeanimset.AnimSet.parse(file.read(), info), SOURCE_FILE, path, ""
            except (OSError, exeanimset.AnimSetError) as error:
                problem = f"{info.file_name} is not used (FFNx would ignore it too): {error}"
        if self.exe_path():
            try:
                anim_set = self.read_exe_set(info)
            except exeanimset.AnimSetError as error:
                anim_set, problem = None, f"the exe's block is not a valid set: {error}"
            if anim_set is not None:
                return anim_set, SOURCE_EXE, self.exe_path(), problem
        return None, "", "", problem or "not in the opened exe, and no .animset file for it"


class IfritAnimSetWidget(QWidget):
    """The anim sets of the loaded character body: a set picker, the set's animations in Ifrit's 3D
    view (body + the character's weapon) and its sequences in Ifrit's sequence editor."""
    set_edited = pyqtSignal()    # an edit of a set (not of the .dat)
    body_edited = pyqtSignal()   # a skeleton edit made through this view: it changes the .dat

    def __init__(self, ifrit_manager, source: AnimSetSource, weapon_provider=None, icon_path="Resources",
                 file_registry=None):
        super().__init__()
        self.ifrit_manager = ifrit_manager
        self.source = source
        self.file_registry = file_registry
        self._weapon_provider = weapon_provider
        self.path = ""
        self.holder = AnimSetHolder()
        self.body_view = AnimSetManagerView(ifrit_manager, self.holder, 'body')
        self._documents = {}       # AnimSetInfo -> AnimSetDocument (edits kept while switching sets)
        self._origins = {}         # AnimSetInfo -> (source, path)
        self._modified = set()     # AnimSetInfo edited since loaded or saved
        self._infos = []

        self.set_selector = QComboBox()
        self.set_selector.setToolTip("The sets this character plays in battle (limit breaks, Blue Magic...).\n"
                                     "* = edited, not saved yet.")
        self.set_selector.currentIndexChanged.connect(self._show_selected)
        self.source_label = QLabel()
        self.source_label.setWordWrap(True)
        self.convert_button = QPushButton("To 30 fps")
        self.convert_button.setToolTip("Convert this set for FFNx True30FPS: every animation gets 2n frames\n"
                                       "(body and weapon together), the sequences are rewritten for a VM at\n"
                                       "30 Hz, an animation over 255 frames is split. Convert once.")
        self.convert_button.clicked.connect(lambda: self.convert_to_30fps())
        self.save_file_button = QPushButton("Save .animset…")
        self.save_file_button.setToolTip("Write this set as FFNx's effect_NNN.animset (any size, any exe\n"
                                         "language; the game folder's direct/exe/).")
        self.save_file_button.clicked.connect(lambda: self.save_file())
        self.save_exe_button = QPushButton("Save into exe")
        self.save_exe_button.setToolTip("Write this set back into its block of the opened exe. Only a set that\n"
                                        "still fits the vanilla block can: else save it as an .animset file.")
        self.save_exe_button.clicked.connect(lambda: self.save_into_exe())
        top = QHBoxLayout()
        top.addWidget(QLabel("Set:"))
        top.addWidget(self.set_selector, 1)
        top.addWidget(self.convert_button)
        top.addWidget(self.save_file_button)
        top.addWidget(self.save_exe_button)

        self.view_3d = Ifrit3DWidget(self.body_view, show_controls=True)
        self.view_3d.set_single_animation_block()   # the set's own list: no add/remove, no fps action
        self.seq_widget = IfritSeqWidget(self.body_view, icon_path=icon_path, file_registry=file_registry)
        self.seq_widget.data_edited.connect(self._on_set_edit)
        self.view_3d.model_edited.connect(self._on_set_edit)
        bone_editor = getattr(self.view_3d, 'bone_editor', None)
        if bone_editor is not None:
            for name in ('animation_rotation_changed', 'animation_position_changed', 'animation_scale_changed',
                         'frame_scale_mode_changed'):
                signal = getattr(bone_editor, name, None)
                if signal is not None:
                    signal.connect(self._on_set_edit)
            for name in ('bone_length_changed', 'bone_parent_changed', 'add_bone_requested',
                         'reset_skeleton_requested'):
                signal = getattr(bone_editor, name, None)
                if signal is not None:
                    signal.connect(self.body_edited.emit)
        self.inner_tabs = QTabWidget()
        self.inner_tabs.addTab(self.view_3d, "Animations")
        self.inner_tabs.addTab(self.seq_widget, "Sequences")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(top)
        layout.addWidget(self.source_label)
        layout.addWidget(self.inner_tabs, 1)
        self._update_buttons()

    # ------------------------------------------------------------------ what is shown
    def character(self):
        """The character of the loaded body file, None for anything else (weapons, monsters)."""
        enemy = self.ifrit_manager.enemy
        if getattr(enemy, 'entity_type', None) not in (EntityType.CHARACTER, EntityType.CHARACTER_NO_WEAPON):
            return None
        return exeanimset.character_of_model_file(self.path or getattr(enemy, 'origin_path', "") or "")

    def set_infos(self) -> list:
        character = self.character()
        return exeanimset.sets_of_character(character) if character else []

    def has_sets(self) -> bool:
        """The tab is shown: a character body with sets, and the exe or an .animset folder open."""
        return bool(self.set_infos()) and self.source.has_data()

    def is_modified(self) -> bool:
        return bool(self._modified)

    def load(self, path):
        """(Re)fill the set list for the body file `path` (sources may have changed)."""
        self.path = path
        current = self._current_info()
        self._infos = self.set_infos() if self.source.has_data() else []
        # sets edited here keep their edits; the others are read again (a file may have appeared)
        for info in list(self._documents):
            if info not in self._modified:
                del self._documents[info]
                self._origins.pop(info, None)
        self.set_selector.blockSignals(True)
        self.set_selector.clear()
        for info in self._infos:
            self.set_selector.addItem(self._label(info))
        index = self._infos.index(current) if current in self._infos else 0
        self.set_selector.setCurrentIndex(index if self._infos else -1)
        self.set_selector.blockSignals(False)
        self._show_selected()

    def _label(self, info) -> str:
        star = " *" if info in self._modified else ""
        origin = self._origins.get(info)
        kind = "" if origin is None else f"  [{origin[0]}]"
        return f"{info.effect_id:03d} {info.effect_name}{kind}{star}"

    def _refresh_labels(self):
        for row, info in enumerate(self._infos):
            self.set_selector.setItemText(row, self._label(info))

    def _current_info(self):
        row = self.set_selector.currentIndex()
        return self._infos[row] if 0 <= row < len(self._infos) else None

    def _bone_sections(self, info):
        """(body BoneSection or None, weapon BoneSection or None, weapon options, problem)."""
        monster = getattr(self.ifrit_manager.enemy, 'monster', self.ifrit_manager.enemy)
        bone_data = getattr(monster, 'bone_data', None)
        problem = ""
        body = bone_data if bone_data is not None and len(bone_data.bones) == info.body_bones else None
        if body is None:
            problem = (f"this model has {len(bone_data.bones) if bone_data else 0} bones, the set's "
                       f"animations {info.body_bones}: no preview")
        options, default_index, weapon = [], 0, None
        result = self._weapon_provider(self.path) if self._weapon_provider is not None else None
        if result is not None:
            raw_options, default_index = result
            for label, manager in raw_options:
                if manager is not None and manager.enemy.entity_type == EntityType.WEAPON:
                    if info.weapon_bones and len(manager.enemy.bone_data.bones) == info.weapon_bones:
                        if weapon is None:
                            weapon = manager.enemy.bone_data
                        options.append((label, AnimSetManagerView(manager, self.holder, 'weapon')))
                    continue
                options.append((label, manager))   # body only, or a reduced weapon posed by the body
        return body, weapon, (options, default_index), problem

    def _show_selected(self, _index=None):
        info = self._current_info()
        problem = ""
        document = None
        options = ([], 0)
        if info is not None:
            body, weapon, options, problem = self._bone_sections(info)
            document = self._documents.get(info)
            if document is None and body is not None:
                anim_set, kind, path, load_problem = self.source.load(info)
                problem = problem or load_problem
                if anim_set is not None:
                    try:
                        document = exeanimset.AnimSetDocument(anim_set, body, weapon)
                    except Exception as error:   # a set that does not decode on this skeleton
                        problem = f"cannot be decoded on this model: {error}"
                    else:
                        self._documents[info] = document
                        self._origins[info] = (kind, path)
                        self._refresh_labels()
        self.holder.document = document
        self.source_label.setText(self._describe(info, problem))
        if document is not None:
            self.view_3d.load_file()
            self.view_3d.set_weapon_options(*options)
            self.seq_widget.load_file(self.path)
        self._update_buttons()

    def _describe(self, info, problem) -> str:
        if info is None:
            return "No anim set for this model (open the FF8 exe or an FFNx effect_NNN.animset file)."
        origin = self._origins.get(info)
        where = ""
        if origin is not None:
            where = (f"From {os.path.basename(origin[1])}" if origin[0] == SOURCE_FILE
                     else f"From the exe ({os.path.basename(origin[1])})")
            where += f" - FFNx file: {info.file_name}, exe block: {info.size} bytes."
        text = " ".join(part for part in (where, problem) if part)
        return f"<span style='color:#c77800'>{text}</span>" if problem else text

    def _update_buttons(self):
        info = self._current_info()
        has_document = info is not None and info in self._documents
        self.convert_button.setEnabled(has_document)
        self.save_file_button.setEnabled(has_document)
        self.save_exe_button.setEnabled(has_document and bool(self.source.exe_path()))

    def _on_set_edit(self):
        info = self._current_info()
        if info is None or info not in self._documents:
            return
        if info not in self._modified:
            self._modified.add(info)
            self._refresh_labels()
        self.set_edited.emit()

    # ------------------------------------------------------------------ actions
    def _current_set(self):
        info = self._current_info()
        document = self._documents.get(info) if info is not None else None
        if document is None:
            return None, None
        if info not in self._modified:
            return info, document.original   # unedited: the bytes as they were read
        return info, document.to_anim_set()

    def convert_to_30fps(self, confirm=True) -> dict:
        title = "Anim set to 30 fps"
        info, anim_set = self._current_set()
        if anim_set is None:
            return {}
        if confirm and QMessageBox.question(
                self, title, f"Convert {info.label} for FFNx True30FPS? Convert a vanilla set only once: "
                "converting twice doubles again.") != QMessageBox.StandardButton.Yes:
            return {}
        try:
            converted, report = exeanimset.convert_to_real30(self.ifrit_manager.game_data, anim_set)
            body, weapon, _options, _problem = self._bone_sections(info)
            document = exeanimset.AnimSetDocument(converted, body, weapon)
        except exeanimset.AnimSetError as error:
            QMessageBox.warning(self, title, f"Not converted:\n{error}")
            return {}
        self._documents[info] = document
        self._modified.add(info)
        self._refresh_labels()
        self._show_selected()
        self.set_edited.emit()
        if confirm:
            split = "".join(f"\nanimation {anim_id} ({nb} frames) split in {parts}"
                            for anim_id, nb, parts, _ids in report['split_list'])
            QMessageBox.information(self, title, f"{report['nb_converted']} animation(s) converted, "
                                    f"{len(converted.to_bytes())} bytes (exe block: {info.size}).{split}\n"
                                    "Save it with Save .animset… (it no longer fits the exe).")
        return report

    def save_file(self, folder=None) -> str:
        """Write the shown set as effect_NNN.animset: into the opened .animset folder, else `folder`
        (asked). Returns the path written, or ""."""
        title = "Save .animset"
        info, anim_set = self._current_set()
        if anim_set is None:
            return ""
        try:
            data = anim_set.to_bytes()     # built and checked before anything is written
        except exeanimset.AnimSetError as error:
            QMessageBox.warning(self, title, f"Not saved:\n{error}")
            return ""
        folder = folder or self.source.folder()
        if not folder:
            start = (self.file_registry.last_folder(ANIM_SET_FILE_NAME) if self.file_registry else "") or os.getcwd()
            folder = QFileDialog.getExistingDirectory(self, "Folder for the .animset file (FFNx: the game "
                                                      "folder's direct/exe/)", start)
        if not folder:
            return ""
        path = os.path.join(folder, info.file_name)
        with open(path, "wb") as file:
            file.write(data)
        if self.file_registry is not None:
            self.file_registry.remember_folder(ANIM_SET_FILE_NAME, folder)
        self._saved(info, SOURCE_FILE, path)
        return path

    def save_into_exe(self, confirm=True) -> bool:
        title = "Save into exe"
        info, anim_set = self._current_set()
        exe_path = self.source.exe_path()
        if anim_set is None or not exe_path:
            return False
        offset = self.source.exe_offset(info)
        if offset is None:
            QMessageBox.warning(self, title, f"{info.label} was not found in {os.path.basename(exe_path)} "
                                f"(changed by something else?). Save it as {info.file_name} for FFNx instead.")
            return False
        try:
            data = anim_set.to_bytes()
            with open(exe_path, "rb") as file:
                exe = bytearray(file.read())
            exeanimset.patch_exe(exe, info, data, offset)   # refused when it does not fit: nothing written
        except (OSError, exeanimset.AnimSetError) as error:
            QMessageBox.warning(self, title, f"Not saved into the exe:\n{error}")
            return False
        if confirm and QMessageBox.question(
                self, title, f"Write {info.label} ({len(data)} of {info.size} bytes) into "
                f"{exe_path}?") != QMessageBox.StandardButton.Yes:
            return False
        with open(exe_path, "wb") as file:
            file.write(exe)
        self._saved(info, SOURCE_EXE, exe_path)
        return True

    def _saved(self, info, kind, path):
        self._modified.discard(info)
        document = self._documents.get(info)
        if document is not None:
            document.original = document.to_anim_set()
        self._origins[info] = (kind, path)
        self._refresh_labels()
        self.source_label.setText(self._describe(info, ""))
        self._update_buttons()
