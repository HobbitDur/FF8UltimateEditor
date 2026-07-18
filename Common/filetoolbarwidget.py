import os

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QWidget, QPushButton, QHBoxLayout, QFileDialog, QMessageBox

from Common.fileregistry import FileRegistry


class FileToolbarWidget(QWidget):
    """The shared Import / Import complementary / Save buttons, one common set of file controls.

    They act on whichever tool - and sub-tab - is showing: at click time the active tool is
    asked for its FileBinding list, so which file gets opened or saved depends on the current
    tool/sub-tab. A tool joins in by implementing ``file_bindings(self) -> list[FileBinding]``;
    a tool that does not is simply inert here (the buttons grey out for it). A tool whose files
    change with an inner tab exposes a ``file_bindings_changed`` signal, which refreshes this bar.

    - Import: opens the file(s) the active tool edits (its writable "main" bindings).
    - Import complementary: opens the read-only file(s) it only reads to feed its preview (shared,
      each edited in another tool). Several at once when the tool has several (e.g. Zone reads
      five); disabled when the active tool has none.
    - Save: writes the active tool's main file(s) back.
    """

    def __init__(self, tool_stack, registry: FileRegistry, icon_path="Resources"):
        QWidget.__init__(self)
        self.tool_stack = tool_stack
        self.registry = registry
        self._current_tool = None

        self.import_button = self._icon_button(
            icon_path, 'import_main.svg',
            "Import the file this tool edits (opened for every tool using it too)")
        self.import_button.clicked.connect(self._import_main)

        self.import_complementary_button = self._icon_button(
            icon_path, 'import_complementary.svg',
            "Import the complementary file(s) this tool only reads to feed its preview "
            "(each edited in another tool, shared read-only with every tool using it)")
        self.import_complementary_button.clicked.connect(self._import_complementary)

        self.save_button = self._icon_button(
            icon_path, 'save.svg',
            "Save the file this tool edits (irreversible)")
        self.save_button.clicked.connect(self._save)

        self.reload_button = self._icon_button(
            icon_path, 'reload_files.svg',
            "Reload every opened file from disk (re-read them all after an external change)")
        self.reload_button.clicked.connect(self.registry.reload_all)

        self.open_folder_button = self._icon_button(
            icon_path, 'open_folder.svg',
            "Open a folder: every file a tool can read, found anywhere inside it, is opened at once "
            "(pick the 'field' folder to load the .jsm/.sym card players)")
        self.open_folder_button.clicked.connect(self._open_folder)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.import_button)
        layout.addWidget(self.import_complementary_button)
        layout.addWidget(self.save_button)
        layout.addWidget(self.reload_button)
        layout.addWidget(self.open_folder_button)
        self.setLayout(layout)

        self.tool_stack.currentChanged.connect(self._on_tool_changed)
        registry.file_changed.connect(self._on_registry_changed)
        self._on_tool_changed()

    @staticmethod
    def _icon_button(icon_path, icon_name, tooltip):
        button = QPushButton()
        button.setIcon(QIcon(os.path.join(icon_path, icon_name)))
        button.setIconSize(QSize(30, 30))
        button.setFixedSize(40, 40)
        button.setToolTip(tooltip)
        return button

    # -- the active tool's bindings -------------------------------------------------
    def _bindings(self):
        widget = self.tool_stack.currentWidget()
        getter = getattr(widget, "file_bindings", None)
        return list(getter()) if callable(getter) else []

    def _main_bindings(self):
        return [binding for binding in self._bindings() if not binding.read_only]

    def _complementary_bindings(self):
        return [binding for binding in self._bindings() if binding.read_only]

    # -- actions --------------------------------------------------------------------
    def _import_main(self):
        bindings = self._main_bindings()
        if len(bindings) == 1:
            bindings[0].open_dialog(self)
        elif bindings:
            self._open_several(bindings, "Import the files this tool edits")

    def _import_complementary(self):
        bindings = self._complementary_bindings()
        if len(bindings) == 1:
            bindings[0].open_dialog(self)
        elif bindings:
            self._open_several(bindings, "Open the complementary files (several at once is fine)")

    def _open_several(self, bindings, caption):
        """One multi-select dialog for several files, routing each pick to its binding by name."""
        names = [binding.file_name for binding in bindings]
        file_paths = QFileDialog.getOpenFileNames(
            self, caption, filter=f"Files this tool uses ({' '.join(names)})",
            directory=os.getcwd())[0]
        by_name = {binding.file_name.lower(): binding for binding in bindings}
        for path in file_paths:
            binding = by_name.get(os.path.basename(path).lower())
            if binding is not None:
                binding.open_path(path)

    def _save(self):
        for binding in self._main_bindings():
            binding.save()          # the tool's single-file bindings
        saver = getattr(self.tool_stack.currentWidget(), "save_folder", None)
        if callable(saver):
            saver()                 # ...and its multi-file / folder save, if it has one

    def _can_save_folder(self):
        """Whether the active tool has a multi-file (folder) save with something to write."""
        predicate = getattr(self.tool_stack.currentWidget(), "can_save_folder", None)
        return bool(predicate()) if callable(predicate) else False

    def _open_folder(self):
        """Pick a folder and open every file a tool can read that is found in it or its subfolders.

        A folder-based tool (e.g. the NPC card players tab, which reads a whole 'field' folder of
        .jsm/.sym scripts) is handed the folder through its load_folder(folder) method and reports
        its own result."""
        folder = QFileDialog.getExistingDirectory(
            self, "Open a folder — its files are loaded into the tools "
                  "(pick the 'field' folder for the .jsm/.sym card players)")
        if not folder:
            return
        found = self.scan_folder(folder, self.registry.accepted_file_names())
        opened, problems = [], []
        for file_name, path in found.items():
            try:
                self.registry.open_file(file_name, path)  # -> every tool bound to it loads it
                opened.append(file_name)
            except Exception as error:  # a matching name but unreadable content: keep going
                problems.append(f"{file_name}: {error}")

        # Folder-based tools load the whole folder themselves and show their own result.
        folder_loader = getattr(self.tool_stack.currentWidget(), "load_folder", None)
        loaded_folder = callable(folder_loader)
        if loaded_folder:
            folder_loader(folder)
            self._refresh()  # a folder-based tool may now have something to Save
        # Only pop the generic summary when the active tool won't report the outcome itself.
        if opened or problems or not loaded_folder:
            self._report_open_folder(folder, opened, problems)

    @staticmethod
    def scan_folder(folder, accepted_names):
        """Walk folder and its subfolders; return {file_name: first path found} for every accepted
        FF8 file name present (matched case-insensitively)."""
        wanted = {name.lower(): name for name in accepted_names}
        found = {}
        for root, _dirs, files in os.walk(folder):
            for file in files:
                name = wanted.get(file.lower())
                if name and name not in found:
                    found[name] = os.path.join(root, file)
        return found

    def _report_open_folder(self, folder, opened, problems):
        lines = [f"Opened {len(opened)} file(s) from:\n{folder}"]
        if opened:
            lines.append("\n" + "\n".join(f"  • {name}" for name in sorted(opened)))
        else:
            lines.append("\nNo file a tool can read was found here or in its subfolders.")
        if problems:
            lines.append("\nCould not open:\n" + "\n".join(f"  • {p}" for p in problems))
        QMessageBox.information(self, "Open folder", "\n".join(lines))

    # -- enabled/visible state ------------------------------------------------------
    def _on_tool_changed(self, _index=None):
        """Re-hook the active tool's optional file_bindings_changed signal, then refresh.

        A tool whose bindings depend on an inner tab (e.g. Zone) emits that signal so the bar
        follows the tab without the outer tool stack changing."""
        new_tool = self.tool_stack.currentWidget()
        if new_tool is not self._current_tool:
            self._reconnect_bindings_changed(self._current_tool, new_tool)
            self._current_tool = new_tool
        self._refresh()

    def _reconnect_bindings_changed(self, old_tool, new_tool):
        old_signal = getattr(old_tool, "file_bindings_changed", None)
        if old_signal is not None:
            try:
                old_signal.disconnect(self._refresh)
            except TypeError:
                pass
        new_signal = getattr(new_tool, "file_bindings_changed", None)
        if new_signal is not None:
            new_signal.connect(self._refresh)

    def _on_registry_changed(self, _file_name):
        self._refresh()  # a file just loaded/opened somewhere: Save may now have something to do

    def _refresh(self):
        main_bindings = self._main_bindings()
        complementary_bindings = self._complementary_bindings()
        self.import_button.setEnabled(bool(main_bindings))
        self.import_complementary_button.setEnabled(bool(complementary_bindings))
        # Save covers the tool's single-file bindings AND any multi-file (folder) save it has.
        self.save_button.setEnabled(
            any(binding.is_loaded for binding in main_bindings) or self._can_save_folder())
        # Reload acts on every opened file across all tools, not just the active one.
        self.reload_button.setEnabled(bool(self.registry.paths))
