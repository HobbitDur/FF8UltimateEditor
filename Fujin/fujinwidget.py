"""One effect workspace for MAG files, executable cameras and embedded native assets."""
import hashlib
import html
import os
import re
import time
from pathlib import Path

from PyQt6.QtCore import Qt, QSignalBlocker, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon, QFont
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QTabWidget, QPlainTextEdit, QComboBox, QSplitter, QTextBrowser,
    QCheckBox, QFileDialog, QMessageBox)
from Common.autoimport import AutoImportSource
from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from FF8GameData.gamedata import GameData
from Fujin.cameraeffectpreview import MODEL_FOLDER_KEY, MODEL_PATTERNS, MODEL_SELECTION_KEY
from Fujin.cameraeffectwidget import CameraEffectEditorWidget
from Fujin.cameraeffectmanager import cam_file_name, CAM_EXTENSION, CAM_FFNX_FOLDER
from Fujin.effectcatalog import EffectCatalog, EffectResource, filename_effect
from Fujin.effectresourceview import EffectResourceView
from Fujin.nativeresources import NativeResourceStore, apply_effect_hext
from Fujin.magdocumentwidget import MagDocumentWidget
from Fujin.texturepictureview import TexturePictureView
from Fujin.soundpanel import SoundPanel
from Fujin.objectview import MagObjectView
from SmallWidget.listsearchbar import ListSearchBar, SEARCH_TEXT_ROLE

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
        self._owned_cam_exports = {}
        self._saved_note = ""            # what the last Save wrote, shown until the next change
        self._resource_effects = None          # resource key -> effect ids using it (built once)
        self.camera_editor = CameraEffectEditorWidget(GameData(game_data_folder), self.file_registry, embedded=True)
        # kernel.bin (read-only, shared): which spells, items, GFs, enemy attacks... play each effect
        self.effect_users = {}
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
        self.tabs.addTab(self.overview, "Overview")
        self.camera_sources = QTabWidget()
        self.camera_sources.addTab(self.camera_editor, "Executable track")
        self.mag_camera = EffectResourceView("camera", self.resolve)
        self.mag_camera.sections.camera_preview = self.camera_editor.preview
        self.camera_sources.addTab(self.mag_camera, "MAG track")
        self.native_camera = EffectResourceView("parameters", self.resolve)
        self.camera_sources.addTab(self.native_camera, "Native parameters")
        self.camera_note = QLabel()
        self.camera_note.setWordWrap(True)
        camera_page = QWidget()
        camera_layout = QVBoxLayout(camera_page)
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
        # Why there is no MAG script, when there is none (the greyed tab says it too)
        self.choreography_note = QLabel()
        self.choreography_note.setWordWrap(True)
        choreography_page = QWidget()
        choreography_layout = QVBoxLayout(choreography_page)
        choreography_layout.setContentsMargins(0, 0, 0, 0)
        choreography_layout.addWidget(self.choreography_note)
        choreography_layout.addWidget(self.choreography, 1)
        self.tabs.addTab(choreography_page, "Choreography")
        self.object_view = MagObjectView()
        self.models = EffectResourceView("models", self.resolve, self.object_view, "3D view")
        self.textures = EffectResourceView("textures", self.resolve, TexturePictureView(self.file_registry), "Textures")
        self.sound_panel = SoundPanel(self.file_registry)
        self.sound = EffectResourceView("sound", self.resolve, self.sound_panel, "Sounds and vibration")
        self.tabs.addTab(self.models, "Models / animation")
        self.tabs.addTab(self.textures, "Textures")
        self.tabs.addTab(self.sound, "Sound")
        files_page = QWidget()
        files_layout = QVBoxLayout(files_page)
        self.all_files = QCheckBox("Browse all imported files (including files without an effect association)")
        self.all_files.toggled.connect(self._refresh)
        self.files = EffectResourceView("files", self.resolve)
        files_layout.addWidget(self.all_files)
        files_layout.addWidget(self.files, 1)
        self.tabs.addTab(files_page, "Files / sections")
        self.changes = QTextBrowser()
        self.tabs.addTab(self.changes, "Pending changes")
        self.component_views = (self.mag_camera, self.native_camera, self.models, self.textures, self.sound, self.files)
        for view in self.component_views:
            view.data_changed.connect(self._resource_changed)
        self.camera_sources.currentChanged.connect(self._activate_tab)
        right = QWidget()
        layout = QVBoxLayout(right)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.title)
        layout.addWidget(self.context)
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
                + self.sound_panel.file_bindings() + self.mag_editor.file_bindings())

    def import_entries(self):
        return [("FF8 exe (camera tracks and embedded effect assets)", self.camera_editor.open_exe),
                ("Effect files (MAG / MA8, all sections)", self.open_effect_files),
                ("Fujin effect patch (.hext)", self.import_hext)]

    def complementary_entries(self):
        preview = self.camera_editor.preview
        return [("Camera preview models: characters, weapons and monsters", preview.import_models),
                ("Camera preview encounters: scene.out", preview.import_sceneout),
                ("Effect users: kernel.bin (spells, items, GFs, enemy attacks, limit breaks)", self.import_kernel),
                ("Sound preview: audio.fmt + audio.dat (battle sound archive)", self.sound_panel.import_archive)]

    def auto_import_sources(self):
        preview = self.camera_editor.preview
        return [AutoImportSource.for_binding(self.camera_editor.exe_binding, self.file_registry.last_folder("FF8 exe")),
                AutoImportSource(MODEL_FOLDER_KEY, MODEL_PATTERNS, preview.add_models,
                                 selection_only=True, selection_key=MODEL_SELECTION_KEY),
                AutoImportSource.for_binding(preview.sceneout_binding, self.file_registry.last_folder("scene.out")),
                AutoImportSource.for_binding(self.kernel_binding, self.file_registry.last_folder("kernel.bin")),
                AutoImportSource.for_binding(self.sound_panel.audio_binding, self.file_registry.last_folder("audio.fmt")),
                AutoImportSource("Fujin effect files", ("mag*", "MAG*", "ma8*", "MA8*"),
                                 self.import_paths, selection_only=True)]

    def auto_import_bindings(self):
        return self.mag_editor.file_bindings()

    def open_effect_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Import effect files",
            self.file_registry.last_folder("Fujin effect files"), "Effect files (MAG* mag* MA8* ma8*);;All files (*)")
        if paths:
            self.import_paths(paths)

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

    def load_folder(self, folder):
        self.mag_editor.load_folder(folder)

    def import_paths(self, paths):
        """Open effect files with a progress bar (Cancel stops before the next file). The registry
        batches the opens: views refresh once at the end instead of after every file."""
        from Common.filetoolbarwidget import FileToolbarWidget
        by_name = {b.file_name.lower(): b for b in self.mag_editor.file_bindings()}
        opened = []
        progress = FileToolbarWidget.open_progress(self, len(paths), "Opening effect files")
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
            progress.setValue(len(paths))
        self.file_registry.remember_files("Fujin effect files", opened)
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

    def _effect_text(self, effect, modified=False):
        return f"{'* ' if modified else ''}{effect:03d} — {self.catalog.name(effect)}"

    def modified_effects(self):
        """The effects with unsaved changes: a camera track or a native resource changed since the
        last export, or a modified MAG file that the effect uses."""
        exported = dict(self._exported_signature)
        unsaved = {key for key, digest in self._native_signature() if exported.get(key) != digest}
        effects = {int(key.split(":", 1)[1]) for key in unsaved if key.startswith("camera:")}
        dirty = {os.path.basename(m.file_path).lower() for m in self.mag_editor.managers.values() if m.modified}
        dirty |= {key for key in unsaved if not key.startswith("camera:")}
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

    def _selection_changed(self, *_args):
        item = self.effect_list.currentItem()
        if item:
            self.current_effect = item.data(Qt.ItemDataRole.UserRole)
            self.camera_editor.select_effect(self.current_effect)
            self._refresh()

    def _schedule_refresh(self):
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
            selected = resources
            if view is self.files and self.all_files.isChecked():
                selected = list(resources)
                keys = {r.key for r in selected}
                for manager in self.mag_editor.managers.values():
                    name = os.path.basename(manager.file_path)
                    if name.lower() not in keys:
                        selected.append(EffectResource(name.lower(), name, "File", "Imported file; association unresolved"))
            view.set_resources(selected)
        self.title.setText(f"{effect:03d} — {self.catalog.name(effect)}")
        loaded = sum(self.resolve(r) is not None for r in resources)
        self.context.setText(f"{self.catalog.runtime(effect)} · {loaded} of {len(resources)} files imported"
                             + (" · unsaved changes: see Pending changes" if self.can_save_folder()
                                else f" · {self._saved_note}" if self._saved_note else ""))
        self._refresh_camera()
        self._refresh_choreography()
        self._grey_unused_tabs()
        self._refresh_summary()
        self._activate_tab()

    def _refresh_camera(self):
        effect = self.current_effect
        exe = self.catalog.camera_entry(effect)
        parameters = any(r.kind == "camera_parameter" for r in self.resources)
        self.camera_sources.setTabVisible(0, exe is not None)
        self.camera_sources.setTabVisible(1, (exe is None and not parameters) or self.mag_camera.sources.count() > 0)
        self.camera_sources.setTabVisible(2, parameters)
        mag_tracks = self.mag_camera.sources.count() > 0
        file_camera = effect in self.catalog.camera["file_camera_effects"]
        # No track anywhere: say so instead of showing an empty editor and an empty 3D view
        self.camera_sources.setVisible(exe is not None or parameters or mag_tracks or file_camera)
        if exe is not None:
            self.camera_note.setText("Camera track stored in the exe. Save writes your changes as a .hext patch; "
                                     "a track that grew is saved as an FFNx .bcam file instead.")
        elif parameters:
            self.camera_note.setText("The game code computes this camera. Six of its numbers can be edited below "
                                     "(opening position, orbit radius and step); Save writes them as a .hext patch. "
                                     "The rest of the camera motion is compiled code.")
            self.camera_sources.setCurrentIndex(2)
        elif mag_tracks:
            self.camera_note.setText("Camera track inside the effect's MAG file. Save writes it back into that file "
                                     "(the same bytes as in Files / sections).")
            self.camera_sources.setCurrentIndex(1)
        elif file_camera:
            self.camera_note.setText("This effect's camera comes from its MAG files (a camera track or cinematic camera "
                                     "commands). Import them with the header's Import (Effect files) to edit it; camera "
                                     "moves driven by the cinematic script are in Choreography.")
        else:
            self.camera_note.setText("<b>This effect plays no camera track of its own.</b> It never starts the battle "
                                     "camera player, so the camera of the action (or the stage camera) stays while it "
                                     "plays, as for Phoenix Down and Mega Phoenix. Its game code can still move the "
                                     "camera: see Choreography, Native code. " + html.escape(self.catalog.notes(effect)))

    def _grey_unused_tabs(self):
        """Grey the tabs with nothing for this effect; the reason is the tab's tooltip (and listed
        in the Overview). A greyed current tab hands over to the Overview."""
        camera = not self.camera_sources.isHidden()
        reasons = {
            1: None if camera else self.camera_note.text().replace("<b>", "").replace("</b>", ""),
            2: None if (self.choreography.isTabEnabled(0) or self.function_selector.count())
            else "No MAG script and no native code snapshot for this effect.",
            3: None if self.models.sources.count() else self.models.empty_text,
            4: None if self.textures.sources.count() else self.textures.empty_text,
            5: None if self.sound.sources.count() else self.sound.empty_text,
            6: self._files_unused(),
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

    def _files_unused(self):
        """Why Files / sections has nothing to add, or None. It shows the sections of MAG files
        (and of imported files with no effect association); a TIM is all in Textures."""
        managers = list(self.mag_editor.managers.values())
        if any(m.document.format != "PlayStation TIM" for m in managers):
            return None
        if not managers:
            return "No effect file is imported (the Overview lists this effect's files)."
        return "Only TIM files are imported, and Textures shows and edits everything they hold."

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
        if not candidates:
            self.choreography.setCurrentIndex(1)
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
                    "Effect files) to read, edit and play it here.")
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
                    + ". Open them with the header's Import (Effect files).")
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
                                            else "Not imported: header's Import (Effect files)"))
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
            pending.append(f"<li>Camera {track.effect_id}: {esc(destination)}</li>")
        for key, manager in self.native.managers.items():
            if manager.modified:
                pending.append(f"<li>{esc(key)}: effects_EN.hext (native data)</li>")
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
        return tuple(result)

    def can_save_folder(self):
        return self.mag_editor.can_save_folder() or self._native_signature() != self._exported_signature

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
