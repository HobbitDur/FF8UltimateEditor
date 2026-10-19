import os

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTabWidget

from Common.autoimport import AutoImportSource
from Common.fileregistry import FileRegistry
from FF8GameData.gamedata import GameData
from Fujin.cameraeffectpreview import MODEL_FOLDER_KEY, MODEL_PATTERNS, MODEL_SELECTION_KEY
from Fujin.cameraeffectwidget import CameraEffectEditorWidget
from Fujin.magicexplorerwidget import MagicExplorerWidget


class FujinWidget(QWidget):
    """Fujin: the effect explorer. One tab per view of the spell/attack effects:
    - Magic explorer: what each effect_id is (handlers, files, decompiled logic, textures);
    - Camera effect editor: each effect's camera track inside the FF8 exe, saved as a .hext."""

    MAGIC_TAB = "Magic explorer"
    CAMERA_TAB = "Camera effect editor"

    def __init__(self, icon_path="Resources", game_data_folder="FF8GameData", file_registry=None):
        QWidget.__init__(self)
        self.file_registry = file_registry if file_registry is not None else FileRegistry()
        self.setWindowTitle("Fujin")
        self.setWindowIcon(QIcon(os.path.join(icon_path, 'hobbitdur.ico')))

        self.magic_explorer = MagicExplorerWidget(icon_path=icon_path, game_data_folder=game_data_folder,
                                                  file_registry=self.file_registry)
        self.camera_editor = CameraEffectEditorWidget(GameData(game_data_folder), self.file_registry)
        self.camera_editor.modified_changed.connect(self._sync_dirty_marker)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.magic_explorer, self.MAGIC_TAB)
        self.tabs.addTab(self.camera_editor, self.CAMERA_TAB)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)
        self.setLayout(layout)

    # --- shared header toolbar hooks ----------------------------------------------------
    def file_bindings(self):
        return [self.camera_editor.exe_binding, self.camera_editor.preview.sceneout_binding]

    def import_entries(self):
        return [("FF8 exe (effect camera tracks)", self.camera_editor.open_exe),
                ("Camera patch: .hext saved by the Camera effect editor", self.camera_editor.import_hext),
                ("Magic files (from a de-archived magic.fs)", self.magic_explorer.import_files)]

    def complementary_entries(self):
        """The header Import read-only menu: the preview's caster/target, never edited here."""
        preview = self.camera_editor.preview
        return [("Camera preview models: characters d?c###.dat, their weapons d?w###.dat, monsters "
                 "c0m###.dat (several at once)", preview.import_models),
                ("Camera preview encounters: scene.out", preview.import_sceneout)]

    def save_folder(self):
        """Save writes the camera .hext (the exe itself is never written)."""
        self.camera_editor.save_hext()

    def can_save_folder(self):
        return self.camera_editor.has_changes()

    def auto_import_sources(self):
        exe_folder = self.file_registry.last_folder("FF8 exe")
        return ([AutoImportSource.for_binding(self.camera_editor.exe_binding, exe_folder),
                 AutoImportSource(MODEL_FOLDER_KEY, MODEL_PATTERNS, self.camera_editor.preview.add_models,
                                  selection_only=True, selection_key=MODEL_SELECTION_KEY),
                 AutoImportSource.for_binding(self.camera_editor.preview.sceneout_binding,
                                              self.file_registry.last_folder("scene.out"))]
                + self.magic_explorer.auto_import_sources())

    def _sync_dirty_marker(self):
        state = getattr(self, "dirty_state", None)
        if state is not None:
            (state.mark if self.camera_editor.has_changes() else state.clear)()
