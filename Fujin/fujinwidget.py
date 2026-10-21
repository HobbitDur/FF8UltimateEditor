"""One effect workspace for MAG files, executable cameras and embedded native assets."""
import hashlib
import html
import os
from pathlib import Path

from PyQt6.QtCore import Qt, QSignalBlocker, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon, QFont
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QTabWidget, QPlainTextEdit, QComboBox, QSplitter, QTextBrowser,
    QCheckBox, QFileDialog, QMessageBox)
from Common.autoimport import AutoImportSource
from Common.fileregistry import FileRegistry
from FF8GameData.gamedata import GameData
from Fujin.cameraeffectpreview import MODEL_FOLDER_KEY, MODEL_PATTERNS, MODEL_SELECTION_KEY
from Fujin.cameraeffectwidget import CameraEffectEditorWidget
from Fujin.cameraeffectmanager import cam_file_name, CAM_EXTENSION, CAM_FFNX_FOLDER
from Fujin.effectcatalog import EffectCatalog, EffectResource, filename_effect
from Fujin.effectresourceview import EffectResourceView
from Fujin.nativeresources import NativeResourceStore, apply_effect_hext
from Fujin.magdocumentwidget import MagDocumentWidget
from SmallWidget.listsearchbar import ListSearchBar


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
        self._resource_effects = None          # resource key -> effect ids using it (built once)
        self.camera_editor = CameraEffectEditorWidget(GameData(game_data_folder), self.file_registry, embedded=True)
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
        self.effect_list.setMinimumWidth(225)
        self.effect_list.currentRowChanged.connect(self._selection_changed)
        self.effect_search = ListSearchBar.wrap(self.effect_list)
        self.title = QLabel()
        self.title.setStyleSheet("font-size: 15pt; font-weight: bold")
        self.context = QLabel()
        self.context.setWordWrap(True)
        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self._activate_tab)
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
        native_layout.addWidget(QLabel("English IDA research snapshot — compiled choreography is read-only."))
        native_layout.addWidget(self.function_selector)
        native_layout.addWidget(self.native_code, 1)
        self.choreography.addTab(native_page, "Native code")
        self.tabs.addTab(self.choreography, "Choreography")
        self.models = EffectResourceView("models", self.resolve)
        self.textures = EffectResourceView("textures", self.resolve)
        self.sound = EffectResourceView("sound", self.resolve)
        self.tabs.addTab(self.models, "Models / animation")
        self.tabs.addTab(self.textures, "Textures / palettes")
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
        self.effect_list.setCurrentRow(0)
        self.camera_editor.exe_binding.load_opened_file()
        if self.camera_editor.manager.exe_path and not self.native.managers:
            self._load_native(self.camera_editor.manager.exe_path)
        self._exported_signature = self._native_signature()

    def file_bindings(self):
        return [self.camera_editor.exe_binding, self.camera_editor.preview.sceneout_binding] + self.mag_editor.file_bindings()

    def import_entries(self):
        return [("FF8 exe (camera tracks and embedded effect assets)", self.camera_editor.open_exe),
                ("Effect files (MAG / MA8, all sections)", self.open_effect_files),
                ("Fujin effect patch (.hext)", self.import_hext)]

    def complementary_entries(self):
        preview = self.camera_editor.preview
        return [("Camera preview models: characters, weapons and monsters", preview.import_models),
                ("Camera preview encounters: scene.out", preview.import_sceneout)]

    def auto_import_sources(self):
        preview = self.camera_editor.preview
        return [AutoImportSource.for_binding(self.camera_editor.exe_binding, self.file_registry.last_folder("FF8 exe")),
                AutoImportSource(MODEL_FOLDER_KEY, MODEL_PATTERNS, preview.add_models,
                                 selection_only=True, selection_key=MODEL_SELECTION_KEY),
                AutoImportSource.for_binding(preview.sceneout_binding, self.file_registry.last_folder("scene.out")),
                AutoImportSource("Fujin effect files", ("mag*", "MAG*", "ma8*", "MA8*"),
                                 self.import_paths, selection_only=True)]

    def auto_import_bindings(self):
        return self.mag_editor.file_bindings()

    def open_effect_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Import effect files",
            self.file_registry.last_folder("Fujin effect files"), "Effect files (MAG* mag* MA8* ma8*);;All files (*)")
        if paths:
            self.import_paths(paths)

    def load_folder(self, folder):
        self.mag_editor.load_folder(folder)

    def import_paths(self, paths):
        by_name = {b.file_name.lower(): b for b in self.mag_editor.file_bindings()}
        for path in paths:
            name = os.path.basename(path)
            binding = by_name.get(name.lower())
            if binding is None:
                binding = self.mag_editor._add_generic_binding(name)
                by_name[name.lower()] = binding
            binding.open_path(str(path))
        self.file_registry.remember_files("Fujin effect files", [str(p) for p in paths])
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
        self.context.setText(f"{self.catalog.runtime(effect)} · {loaded} / {len(resources)} resources imported. "
                             "Views share editable bytes. Save destinations appear in Pending changes.")
        self._refresh_camera()
        self._refresh_choreography()
        self._refresh_summary()
        self._activate_tab()

    def _refresh_camera(self):
        effect = self.current_effect
        exe = self.catalog.camera_entry(effect)
        parameters = any(r.kind == "camera_parameter" for r in self.resources)
        self.camera_sources.setTabVisible(0, exe is not None)
        self.camera_sources.setTabVisible(1, (exe is None and not parameters) or self.mag_camera.sources.count() > 0)
        self.camera_sources.setTabVisible(2, parameters)
        if exe is not None:
            self.camera_note.setText("Executable track. Keyframes and script export as Hext; resized tracks export as FFNx .bcam files.")
        elif parameters:
            self.camera_note.setText("Procedural camera. Six verified native constants expose Carbuncle's orbit and opening position. "
                                    "Import the English exe to edit them; Save exports Hext. Other camera logic remains compiled code.")
            self.camera_sources.setCurrentIndex(2)
        elif self.mag_camera.sources.count():
            self.camera_note.setText("Embedded MAG camera track. Edits share the section in Files / sections and save into its MAG file.")
            self.camera_sources.setCurrentIndex(1)
        elif effect in self.catalog.camera["file_camera_effects"]:
            self.camera_note.setText("This effect can use cinematic camera commands or a MAG track. Import its files to locate embedded tracks. "
                                    "Bone-driven camera motion is edited in Choreography.")
        else:
            self.camera_note.setText("No static track is cataloged. Camera motion can be procedural or inherited from the action. "
                                    "Inspect Native code in Choreography; absence of a track does not mean a stationary camera. "
                                    + self.catalog.notes(effect))

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
        self.native_code.setPlainText(function.get("pseudocode", "No decompiled source available.") if function
                                      else "No native research snapshot for this effect.")

    def _activate_tab(self, *_args):
        if not hasattr(self, "component_views"):
            return
        for view in self.component_views:
            if view.isVisible() and view._pending:
                view.activate()
        if self.tabs.currentIndex() == 1:
            source = self.camera_sources.currentWidget()
            self.camera_editor.preview.setVisible(source is self.camera_editor or source is self.mag_camera)
            if source is self.camera_editor:
                self.camera_editor.preview.set_track(self.camera_editor.manager.track(self.current_effect))
            elif source is self.mag_camera:
                page = self.mag_camera.sections.currentWidget()
                from Fujin.magsectionwidget import MagSectionEditor
                editor = page.findChild(MagSectionEditor) if page else None
                self.camera_editor.preview.set_track(getattr(editor, "camera_track", None))
            else:
                self.camera_editor.preview.set_track(None)

    def _refresh_summary(self):
        if self.current_effect is None:
            return
        esc = lambda value: html.escape(str(value))
        effect, info = self.current_effect, self.catalog.info(self.current_effect)
        rows = []
        for resource in getattr(self, "resources", []):
            manager = self.resolve(resource)
            availability = ("Loaded: " + manager.document.format if manager else
                self.native.unavailable.get(resource.key, "Import executable" if resource.source == "Executable" else "Not imported"))
            rows.append("<tr>" + "".join(f"<td>{esc(value)}</td>" for value in (
                resource.name, resource.source, resource.evidence, availability)) + "</tr>")
        aliases = self.catalog.aliases(effect)
        self.overview.setHtml(
            f"<h2>{effect:03d} — {esc(self.catalog.name(effect))}</h2>"
            f"<p><b>Runtime:</b> {esc(self.catalog.runtime(effect))}<br>"
            f"<b>Initializer (EN):</b> {esc(info.get('logic_name', 'Unresolved'))} {esc(info.get('logic_addr', ''))}<br>"
            f"<b>Loader (EN):</b> {esc(info.get('fl_name', 'Unresolved'))} {esc(info.get('fl_addr', ''))}</p>"
            f"<p>{esc(self.catalog.notes(effect))}</p>"
            + (f"<p>Same initializer: {esc(', '.join(str(i) for i in aliases))}. Resource ownership is listed separately.</p>" if aliases else "")
            + ("<p>This slot is unused in the audited dispatch table.</p>" if info.get("free") else "")
            + "<table border='1' cellspacing='0' cellpadding='6'><tr><th>Resource</th><th>Source</th><th>Evidence</th><th>Availability</th></tr>"
            + "".join(rows) + "</table><p>Filename-family matches are discovery hints. Loader string extraction is partial; "
              "missing references do not prove an effect is unused. Decoded sections expose named fields; "
              "other sections retain bounded byte editing. Native choreography remains read-only.</p>")
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
            "<p>MAG edits write to imported files. Executable edits export together into a selected folder. "
            "Patches contain cumulative differences from the loaded executable; the executable itself is unchanged.</p>"
            + ("<ul>" + "".join(pending) + "</ul>" if pending else "<p>No modified resources.</p>"))
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
