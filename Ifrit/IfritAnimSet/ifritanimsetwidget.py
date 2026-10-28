"""Ifrit's "Exe - Limit anim." tab: the battle anim sets of the exe that play on the loaded character
(limit breaks, Blue Magic cast, Shot, Duel, Angelo...), previewed and edited on its own skeleton.

A set comes from the FF8 exe (the shared "FF8 exe" file, opened here as a complementary file or in
any other tool) or from an FFNx effect_NNN.animset file: open one with "Import complementary" and
every effect_*.animset beside it is used. Like FFNx, a valid file wins over the exe. With neither,
the tab is hidden. See FF8GameData/dat/exeanimset.py for the format and FFNx's loader.

A set holds the body animations, the sequences and (most sets) the weapon animations: the engine
plays the weapon animation of the same id as the body one, in lockstep (Battle_QueueAnimation,
FF8_EN.exe 0x509520). The tab of a character BODY file (dXc) edits the body animations and the
sequences, the tab of a character WEAPON file (dXw) the weapon animations, and both edit the SAME
set: the open sets live in the shared AnimSetSource (one AnimSetDocument per set, whichever file
opened it), so the 30 fps conversion and both saves always carry the body and the weapon together.

Edits stay in memory per set (a '*' marks them, and the tool counts as unsaved) until "Save
.animset" (the FFNx file, any size) or "Save into exe" (only while the set still fits its exe block:
a 30 fps set never does)."""
import os

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit,
                             QPushButton, QTabWidget, QVBoxLayout, QWidget)

from Common.filebinding import FileBinding
from FF8GameData.dat import exeanimset
from FF8GameData.monsterdata import EntityType
from Ifrit.Ifrit3D.ifrit3dwidget import Ifrit3DWidget
from Ifrit.IfritAnimSet.animsetview import AnimSetHolder, AnimSetManagerView

TAB_LABEL = "Exe - Limit anim."
ANIM_SET_FILE_NAME = "FFNx anim set (.animset)"   # the registry key of the .animset files
EXE_FILE_NAME = "FF8 exe"
SOURCE_EXE, SOURCE_FILE = "exe", "file"
BODY, WEAPON = 'body', 'weapon'
# The tab is shown greyed, with this tooltip, on a file that has sets while no source is open.
NO_SOURCE_TOOLTIP = ("Open FF8_EN.exe (the FF8 exe) or an FFNx effect_NNN.animset file (Import complementary)\n"
                     "to see and edit the anim sets this character plays (limit breaks, Blue Magic...).")


def pool_of(enemy) -> str:
    """The pool of a set a model plays: a weapon (with its own animations) the weapon animations,
    anything else the body ones."""
    return WEAPON if getattr(enemy, 'entity_type', None) == EntityType.WEAPON else BODY


def model_set_infos(enemy, path="") -> list:
    """The sets that can play on this model, whatever source is open: a character body's sets, or
    for a character weapon the ones with weapon animations made for its skeleton. [] for anything
    else (monsters, reduced weapons, a character without sets)."""
    entity_type = getattr(enemy, 'entity_type', None)
    pool = pool_of(enemy)
    allowed = (EntityType.WEAPON,) if pool == WEAPON else (EntityType.CHARACTER, EntityType.CHARACTER_NO_WEAPON)
    if entity_type not in allowed:
        return []
    character = exeanimset.character_of_model_file(path or getattr(enemy, 'origin_path', "") or "")
    infos = exeanimset.sets_of_character(character) if character else []
    if pool == WEAPON:
        monster = getattr(enemy, 'monster', enemy)
        bone_data = getattr(monster, 'bone_data', None)
        nb_bone = len(bone_data.bones) if bone_data is not None else 0
        infos = [info for info in infos if info.weapon_bones and info.weapon_bones == nb_bone]
    return infos


class OpenAnimSet:
    """One set opened for editing: its document, where it was read from (or last saved to), and
    whether it holds edits not saved yet."""
    __slots__ = ('document', 'kind', 'path', 'modified')

    def __init__(self, document, kind, path):
        self.document = document
        self.kind = kind
        self.path = path
        self.modified = False


class AnimSetSource(QObject):
    """Where the sets come from: the FF8 exe and/or a folder of FFNx .animset files, both
    complementary files of the shared registry. `changed` when either is opened or closed.

    It also holds the sets opened for editing (OpenAnimSet, one per set): the body tab and the
    weapon tab of a character, whichever file is shown, edit the same document, and edits survive
    switching files. Opening or closing a source drops the unedited ones (read again on use);
    edited ones are kept until saved. `documents_changed` when a set becomes edited or saved."""
    changed = pyqtSignal()
    documents_changed = pyqtSignal()

    def __init__(self, file_registry):
        super().__init__()
        self.exe_binding = FileBinding(EXE_FILE_NAME, file_registry, load_callback=lambda _path: self._reset(),
                                       file_filter="*.exe", read_only=True)
        self.exe_binding.file_closed.connect(lambda _path: self._reset())
        self.file_binding = FileBinding(ANIM_SET_FILE_NAME, file_registry, load_callback=lambda _path: self._reset(),
                                        file_filter="effect_*.animset", read_only=True)
        self.file_binding.file_closed.connect(lambda _path: self._reset())
        self._exe_offsets = None   # {AnimSetInfo: offset} of the opened exe, found once
        self._open = {}            # AnimSetInfo -> OpenAnimSet

    def bindings(self):
        return [self.exe_binding, self.file_binding]

    def load_opened_files(self):
        for binding in self.bindings():
            binding.load_opened_file()

    def _reset(self):
        self._exe_offsets = None
        for info in [info for info, entry in self._open.items() if not entry.modified]:
            del self._open[info]   # read again on use (a file may have appeared or gone)
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

    # ------------------------------------------------------------------ the sets opened for editing
    def entry(self, info):
        """The OpenAnimSet of `info` when it is opened, else None (nothing is read)."""
        return self._open.get(info)

    def open_set(self, info):
        """(OpenAnimSet or None, problem): the set opened for editing, read on first use."""
        entry = self._open.get(info)
        if entry is not None:
            return entry, ""
        anim_set, kind, path, problem = self.load(info)
        if anim_set is None:
            return None, problem
        try:
            document = exeanimset.AnimSetDocument(anim_set)
        except Exception as error:   # noqa: BLE001 - a set that does not decode must not break the tab
            return None, f"cannot be decoded: {error}"
        entry = OpenAnimSet(document, kind, path)
        self._open[info] = entry
        return entry, problem

    def is_modified(self, info) -> bool:
        entry = self._open.get(info)
        return entry is not None and entry.modified

    def has_modified(self) -> bool:
        return any(entry.modified for entry in self._open.values())

    def modified_infos(self) -> list:
        return [info for info, entry in self._open.items() if entry.modified]

    def mark_modified(self, info):
        entry = self._open.get(info)
        if entry is not None and not entry.modified:
            entry.modified = True
            self.documents_changed.emit()

    def replace_document(self, info, document):
        """A new document for an opened set (the 30 fps conversion): an edit of the set."""
        entry = self._open.get(info)
        if entry is None:
            return
        entry.document = document
        entry.modified = True
        self.documents_changed.emit()

    def current_set(self, info):
        """The AnimSet to write for an opened set (built from its document when edited, the bytes as
        read otherwise), or None. AnimSetError when the edits do not make a valid set."""
        entry = self._open.get(info)
        if entry is None:
            return None
        return entry.document.to_anim_set() if entry.modified else entry.document.original

    def saved(self, info, kind, path):
        entry = self._open.get(info)
        if entry is None:
            return
        if entry.modified:
            entry.document.original = entry.document.to_anim_set()
        entry.modified = False
        entry.kind, entry.path = kind, path
        self.documents_changed.emit()


class IfritAnimSetWidget(QWidget):
    """The anim sets of the loaded character file. On a BODY file: a set picker, the set's body
    animations in Ifrit's 3D view (with the character's weapon) and its sequences in Ifrit's sequence
    editor. On a WEAPON file: the sets with weapon animations for this weapon's skeleton, those
    animations in the 3D view on the weapon, and the body's sequences read-only."""
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
        # The pool this file plays: a weapon file the set's weapon animations, anything else the body's.
        self.pool = pool_of(ifrit_manager.enemy)
        self.holder = AnimSetHolder()
        self.set_view = AnimSetManagerView(ifrit_manager, self.holder, self.pool)
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
        self.save_file_button.setToolTip("Write this set (body, sequences and weapon) as FFNx's\n"
                                         "effect_NNN.animset (any size, any exe language; the game folder's\n"
                                         "direct/exe/).")
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

        self.view_3d = Ifrit3DWidget(self.set_view, show_controls=True)
        self.view_3d.set_single_animation_block()   # the set's own list: no add/remove, no fps action
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
        self.seq_widget = None
        self.seq_text = None
        if self.pool == BODY:
            from Ifrit.IfritSeq.ifritseqwidget import IfritSeqWidget
            self.seq_widget = IfritSeqWidget(self.set_view, icon_path=icon_path, file_registry=file_registry)
            self.seq_widget.data_edited.connect(self._on_set_edit)
            self.inner_tabs.addTab(self.seq_widget, "Sequences")
        else:
            # The sequences belong to the body: shown here for reference, edited in the body's tab.
            self.seq_text = QPlainTextEdit()
            self.seq_text.setReadOnly(True)
            self.seq_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
            self.inner_tabs.addTab(self.seq_text, "Sequences (body, read-only)")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(top)
        layout.addWidget(self.source_label)
        layout.addWidget(self.inner_tabs, 1)
        self._update_buttons()

    # ------------------------------------------------------------------ what is shown
    def _bone_data(self):
        monster = getattr(self.ifrit_manager.enemy, 'monster', self.ifrit_manager.enemy)
        return getattr(monster, 'bone_data', None)

    def set_infos(self) -> list:
        """The sets of the loaded file (model_set_infos), whatever source is open."""
        return model_set_infos(self.ifrit_manager.enemy, self.path)

    def can_have_sets(self) -> bool:
        """The tab applies to this file (shown; greyed until a source is open)."""
        return bool(self.set_infos())

    def has_sets(self) -> bool:
        """The tab is usable: a character file with sets, and the exe or an .animset folder open."""
        return self.can_have_sets() and self.source.has_data()

    def is_modified(self) -> bool:
        """A set of this tab holds unsaved edits (made here or in the other file's tab)."""
        return any(self.source.is_modified(info) for info in self._infos)

    def load(self, path):
        """(Re)fill the set list for the file `path` (sources may have changed)."""
        self.path = path
        current = self._current_info()
        self._infos = self.set_infos() if self.source.has_data() else []
        self.set_selector.blockSignals(True)
        self.set_selector.clear()
        for info in self._infos:
            self.set_selector.addItem(self._label(info))
        index = self._infos.index(current) if current in self._infos else 0
        self.set_selector.setCurrentIndex(index if self._infos else -1)
        self.set_selector.blockSignals(False)
        self._show_selected()

    def _label(self, info) -> str:
        entry = self.source.entry(info)
        star = " *" if entry is not None and entry.modified else ""
        kind = "" if entry is None else f"  [{entry.kind}]"
        return f"{info.effect_id:03d} {info.effect_name}{kind}{star}"

    def _refresh_labels(self):
        for row, info in enumerate(self._infos):
            self.set_selector.setItemText(row, self._label(info))

    def _current_info(self):
        row = self.set_selector.currentIndex()
        return self._infos[row] if 0 <= row < len(self._infos) else None

    def _bone_sections(self, info):
        """(own BoneSection or None, weapon BoneSection or None, weapon options, problem). own: this
        file's skeleton when it is the one of the set's pool; weapon: (body tab) the skeleton of the
        weapon shown with the body."""
        bone_data = self._bone_data()
        nb_bone = len(bone_data.bones) if bone_data is not None else 0
        wanted = info.weapon_bones if self.pool == WEAPON else info.body_bones
        own = bone_data if bone_data is not None and nb_bone == wanted else None
        problem = "" if own is not None else (f"this model has {nb_bone} bones, the set's animations "
                                              f"{wanted}: no preview")
        options, default_index, weapon = [], 0, None
        if self.pool == WEAPON:
            return own, None, (options, default_index), problem
        result = self._weapon_provider(self.path) if self._weapon_provider is not None else None
        if result is not None:
            raw_options, default_index = result
            for label, manager in raw_options:
                if manager is not None and manager.enemy.entity_type == EntityType.WEAPON:
                    if info.weapon_bones and len(manager.enemy.bone_data.bones) == info.weapon_bones:
                        if weapon is None:
                            weapon = manager.enemy.bone_data
                        options.append((label, AnimSetManagerView(manager, self.holder, WEAPON)))
                    continue
                options.append((label, manager))   # body only, or a reduced weapon posed by the body
        return own, weapon, (options, default_index), problem

    def _show_selected(self, _index=None):
        info = self._current_info()
        problem = ""
        document = None
        options = ([], 0)
        if info is not None:
            own, weapon, options, problem = self._bone_sections(info)
            if own is not None:
                entry, load_problem = self.source.open_set(info)
                problem = problem or load_problem
                if entry is not None:
                    document = entry.document
                    document.bind_skeleton(self.pool, own)
                    if weapon is not None:
                        document.bind_skeleton(WEAPON, weapon)
                    self._refresh_labels()
        self.holder.document = document
        self.source_label.setText(self._describe(info, problem))
        if document is not None:
            self.view_3d.load_file()
            self.view_3d.set_weapon_options(*options)
            if self.seq_widget is not None:
                self.seq_widget.load_file(self.path)
            else:
                self.seq_text.setPlainText(self._sequence_text(document))
        elif self.seq_text is not None:
            self.seq_text.clear()
        self._update_buttons()

    def _sequence_text(self, document) -> str:
        from FF8GameData.dat.sequencecodec import sequence_to_code
        parts = []
        for item in document.seq_animation_data['seq_animation_data']:
            try:
                code = sequence_to_code(self.ifrit_manager.game_data, bytes(item['data']))
            except Exception as error:   # noqa: BLE001 - shown, not edited: never break the tab
                code = f"(not decoded: {error}) " + bytes(item['data']).hex(" ")
            parts.append(f"# Sequence {item['id']}\n{code}")
        return "\n\n".join(parts)

    def _describe(self, info, problem) -> str:
        if info is None:
            return "No anim set for this model (open the FF8 exe or an FFNx effect_NNN.animset file)."
        entry = self.source.entry(info)
        where = ""
        if entry is not None:
            where = (f"From {os.path.basename(entry.path)}" if entry.kind == SOURCE_FILE
                     else f"From the exe ({os.path.basename(entry.path)})")
            where += f" - FFNx file: {info.file_name}, exe block: {info.size} bytes."
            if self.pool == WEAPON:
                where += (" Weapon animation N plays with body animation N (started by the body's "
                          "sequences): the body's tab edits the same set.")
        text = " ".join(part for part in (where, problem) if part)
        return f"<span style='color:#c77800'>{text}</span>" if problem else text

    def _update_buttons(self):
        info = self._current_info()
        has_document = info is not None and self.holder.document is not None
        self.convert_button.setEnabled(has_document)
        self.save_file_button.setEnabled(has_document)
        self.save_exe_button.setEnabled(has_document and bool(self.source.exe_path()))

    def _on_set_edit(self):
        info = self._current_info()
        if info is None or self.source.entry(info) is None:
            return
        if not self.source.is_modified(info):
            self.source.mark_modified(info)
            self._refresh_labels()
        self.set_edited.emit()

    # ------------------------------------------------------------------ actions
    def _current_set(self):
        info = self._current_info()
        if info is None or self.source.entry(info) is None:
            return None, None
        return info, self.source.current_set(info)

    def convert_to_30fps(self, confirm=True) -> dict:
        """Convert the shown set, body and weapon animations together (never one pool alone: the
        weapon must keep the body's frame counts), whichever file's tab asks."""
        title = "Anim set to 30 fps"
        info = self._current_info()
        if info is None or self.source.entry(info) is None:
            return {}
        if confirm and QMessageBox.question(
                self, title, f"Convert {info.label} for FFNx True30FPS? The body and the weapon animations "
                "of the set are converted together. Convert a vanilla set only once: converting twice "
                "doubles again.") != QMessageBox.StandardButton.Yes:
            return {}
        try:
            anim_set = self.source.current_set(info)
            converted, report = exeanimset.convert_to_real30(self.ifrit_manager.game_data, anim_set)
            document = exeanimset.AnimSetDocument(converted)
        except exeanimset.AnimSetError as error:
            QMessageBox.warning(self, title, f"Not converted:\n{error}")
            return {}
        self.source.replace_document(info, document)
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
        try:
            info, anim_set = self._current_set()
            if anim_set is None:
                return ""
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
        exe_path = self.source.exe_path()
        try:
            info, anim_set = self._current_set()
            if anim_set is None or not exe_path:
                return False
            offset = self.source.exe_offset(info)
            if offset is None:
                QMessageBox.warning(self, title, f"{info.label} was not found in {os.path.basename(exe_path)} "
                                    f"(changed by something else?). Save it as {info.file_name} for FFNx instead.")
                return False
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
        self.source.saved(info, kind, path)
        self._refresh_labels()
        self.source_label.setText(self._describe(info, ""))
        self._update_buttons()
