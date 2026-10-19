"""Auto-upload discovers only the active tool's inputs in remembered locations."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import QSettings, pyqtSignal
from PyQt6.QtWidgets import QStackedWidget, QWidget, QMessageBox

from Common.autoimport import AutoImportSource
from Common.filebinding import FileBinding
from Common.fileregistry import FileRegistry
from Common.filetoolbarwidget import FileToolbarWidget


def touch(folder, name):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(b"test")
    return str(path)


class Tool(QWidget):
    file_bindings_changed = pyqtSignal()

    def __init__(self, bindings=()):
        super().__init__()
        self.bindings = bindings

    def file_bindings(self):
        return self.bindings


def toolbar(registry, *tools):
    stack = QStackedWidget()
    for tool in tools:
        stack.addWidget(tool)
    bar = FileToolbarWidget(stack, registry)
    return bar, stack


def test_main_and_secondary_use_their_own_folders_and_follow_current_tab(tmp_path):
    registry = FileRegistry()
    loaded = []
    main = FileBinding("main.bin", registry, load_callback=lambda p: loaded.append(("main", p)))
    side = FileBinding("side.bin", registry, read_only=True,
                       load_callback=lambda p: loaded.append(("side", p)))
    other = FileBinding("other.bin", registry, load_callback=lambda p: loaded.append(("other", p)))
    paths = [touch(tmp_path / name, f"{name}.bin") for name in ("main", "side", "other")]
    for binding, path in zip((main, side, other), paths):
        registry.remember_folder(binding.file_name, str(Path(path).parent))
    active = Tool([main, side])
    bar, stack = toolbar(registry, active, Tool([other]))
    assert bar.auto_upload_button.isEnabled()
    assert not bar.auto_upload_button.icon().isNull()
    assert bar.auto_upload_button.accessibleName() == "Auto-upload"
    bar.auto_upload_button.click()
    assert loaded == [("main", paths[0]), ("side", paths[1])]
    assert "other.bin" not in registry.paths

    # Inner tabs declare a different binding set without changing the outer tool.
    active.bindings = [other]
    active.file_bindings_changed.emit()
    bar.auto_upload_button.click()
    assert loaded[-1] == ("other", paths[2])
    stack.setCurrentIndex(1)
    assert bar.auto_upload_button.isEnabled()


def test_unknown_tool_disables_auto_upload():
    bar, stack = toolbar(FileRegistry(), QWidget())
    assert not bar.auto_upload_button.isEnabled()


def test_no_saved_folder_does_not_search_cwd(tmp_path, monkeypatch):
    touch(tmp_path, "main.bin")
    monkeypatch.chdir(tmp_path)
    registry = FileRegistry()
    binding = FileBinding("main.bin", registry)
    bar, stack = toolbar(registry, Tool([binding]))
    message = Mock()
    monkeypatch.setattr(QMessageBox, "information", message)
    bar.auto_upload_button.click()
    message.assert_called_once()
    assert registry.paths == {}


def test_missing_input_does_not_block_existing_input(tmp_path):
    registry = FileRegistry()
    main = FileBinding("main.bin", registry)
    missing = FileBinding("missing.bin", registry, read_only=True)
    path = touch(tmp_path, "main.bin")
    registry.remember_folder("main.bin", str(tmp_path))
    registry.remember_folder("missing.bin", str(tmp_path / "deleted"))
    bar, stack = toolbar(registry, Tool([main, missing]))
    bar.auto_upload_button.click()
    assert registry.paths == {"main.bin": path}


def test_case_insensitive_exact_name_wins_over_broad_filter(tmp_path):
    registry = FileRegistry()
    path = touch(tmp_path, "ICON.TEX")
    touch(tmp_path, "other.tex")
    binding = FileBinding("icon.TEX", registry, file_filter="*.TEX *.tex")
    registry.remember_folder(binding.file_name, str(tmp_path))
    assert AutoImportSource.for_binding(binding).find_paths(registry) == [path]


@pytest.mark.parametrize("file_filter", ["*.exe;;All files (*)", "Executable (*.exe);;All files (*)"])
def test_wildcards_use_last_selected_file_across_sessions(tmp_path, file_filter):
    ini = str(tmp_path / "settings.ini")
    registry = FileRegistry(QSettings(ini, QSettings.Format.IniFormat))
    binding = FileBinding("FF8 exe", registry, file_filter=file_filter)
    first = touch(tmp_path, "FF8_EN.exe")
    touch(tmp_path, "FF8_FR.exe")
    registry.open_file(binding.file_name, first)
    registry.settings.sync()
    reopened = FileRegistry(QSettings(ini, QSettings.Format.IniFormat))
    assert AutoImportSource.for_binding(binding).find_paths(reopened) == [first]
    assert reopened.last_folder("FF8 exe") == str(tmp_path)


def test_ambiguous_wildcard_is_reported_and_other_inputs_still_load(tmp_path, monkeypatch):
    registry = FileRegistry()
    exe = FileBinding("FF8 exe", registry, file_filter="*.exe")
    main = FileBinding("main.bin", registry)
    touch(tmp_path, "FF8_EN.exe")
    touch(tmp_path, "FF8_FR.exe")
    path = touch(tmp_path, "main.bin")
    for binding in (exe, main):
        registry.remember_folder(binding.file_name, str(tmp_path))
    bar, stack = toolbar(registry, Tool([exe, main]))
    warning = Mock()
    monkeypatch.setattr(QMessageBox, "warning", warning)
    bar.auto_upload_button.click()
    assert registry.paths == {"main.bin": path}
    assert "Several matching files" in warning.call_args.args[2]


def test_custom_multifile_import_loads_all_matches_once(tmp_path):
    registry = FileRegistry()
    paths = [touch(tmp_path, name) for name in ("c0m000.dat", "C0M001.DAT")]
    touch(tmp_path, "audio.dat")
    touch(tmp_path / "subfolder", "c0m002.dat")
    loader = Mock()
    tool = Tool()
    tool.auto_import_sources = lambda: [AutoImportSource("models", ("c0m*.dat",), loader)]
    registry.remember_folder("models", str(tmp_path))
    bar, stack = toolbar(registry, tool)
    bar.auto_upload_button.click()
    loader.assert_called_once_with(paths)


def test_loader_failure_does_not_block_other_inputs(tmp_path, monkeypatch):
    registry = FileRegistry()
    path = touch(tmp_path, "main.bin")
    registry.remember_folder("files", str(tmp_path))
    good = Mock()
    tool = Tool()
    tool.auto_import_sources = lambda: [
        AutoImportSource("files", ("*.bin",), Mock(side_effect=ValueError("bad data"))),
        AutoImportSource("files", ("*.bin",), good)]
    bar, stack = toolbar(registry, tool)
    warning = Mock()
    monkeypatch.setattr(QMessageBox, "warning", warning)
    bar.auto_upload_button.click()
    good.assert_called_once_with([path])
    assert "bad data" in warning.call_args.args[2]


def test_recursive_folder_source_only_runs_for_expected_contents(tmp_path):
    registry = FileRegistry()
    touch(tmp_path / "room", "field.jsm")
    touch(tmp_path, "other.bin")
    loader = Mock()
    tool = Tool()
    tool.auto_import_sources = lambda: [AutoImportSource(
        "field", ("*.jsm",), loader, folder=str(tmp_path), recursive=True)]
    bar, stack = toolbar(registry, tool)
    bar.auto_upload_button.click()
    loader.assert_called_once_with([str(tmp_path / "room" / "field.jsm")])


def test_julia_resolves_archive_pair_in_separate_folders(tmp_path):
    from Julia.juliawidget import JuliaWidget
    registry = FileRegistry()
    fmt = touch(tmp_path / "fmt", "audio.fmt")
    dat = touch(tmp_path / "dat", "audio.dat")
    for name, path in (("audio.fmt", fmt), ("audio.dat", dat)):
        registry.remember_folder(name, str(Path(path).parent))
    tool = SimpleNamespace(audio_binding=FileBinding("audio.fmt", registry),
                           dat_binding=FileBinding("audio.dat", registry), load_archive=Mock())
    JuliaWidget._auto_import_archive(tool, [fmt])
    tool.load_archive.assert_called_once_with(fmt, dat)


def test_legacy_whole_tool_folder_is_used_for_bindings(tmp_path):
    registry = FileRegistry()
    binding = FileBinding("MAG200_B.00", registry)
    path = touch(tmp_path, binding.file_name)
    tool = Tool([binding])
    tool.import_files = Mock()
    registry.remember_folder(type(tool).__name__, str(tmp_path))
    bar, stack = toolbar(registry, tool)
    bar.auto_upload_button.click()
    assert registry.get_path(binding.file_name) == path


@pytest.fixture(scope="module")
def main_window():
    from ff8ultimateeditorwidget import FF8UltimateEditorWidget
    return FF8UltimateEditorWidget("Resources", "FF8GameData")


def test_all_tools_with_imports_have_auto_upload(main_window):
    bar = main_window._file_toolbar
    stack = main_window.tool_stack
    for index in range(stack.count()):
        stack.setCurrentIndex(index)
        if bar.import_button.isEnabled() or bar.import_complementary_button.isEnabled():
            assert bar.auto_upload_button.isEnabled(), type(stack.currentWidget()).__name__


def test_xu_auto_upload_sources_include_reference_and_all_preview_inputs(main_window):
    xu = main_window._xu_widget
    main_window.tool_stack.setCurrentWidget(xu)
    sources = main_window._file_toolbar._auto_import_sources()
    keys = [source.key for source in sources]
    assert keys[0] == "FF8 exe"
    assert keys[1] == xu.binding.file_name
    assert {binding.file_name for binding in xu.file_bindings()} <= set(keys)
    assert "battle model (.dat)" in keys


@pytest.mark.parametrize("widget_name,method,filename,key", [
    ("_ifrit_widget", "open_files", "c0m000.dat", "battle model (.dat)"),
    ("_alexander_widget", "open_files", "a0stg000.x", "Alexander battle stages"),
    ("_shumi_translator_widget", "open_files", "c0m000.dat", "ShumiTranslator battle text"),
    ("_xu_widget", "add_models", "d0c000.dat", "battle model (.dat)"),
    ("_fujin_widget", "import_files", "mag001.tim", "FujinWidget"),
])
def test_custom_imports_use_the_existing_loader(main_window, tmp_path, monkeypatch,
                                              widget_name, method, filename, key):
    tool = getattr(main_window, widget_name)
    if widget_name == "_alexander_widget":
        key = tool.REGISTRY_NAME
    registry = main_window.file_registry
    registry.remember_folder(key, str(tmp_path))
    path = touch(tmp_path, filename)
    loader = Mock()
    monkeypatch.setattr(tool, method, loader)
    main_window.tool_stack.setCurrentWidget(tool)
    sources = main_window._file_toolbar._auto_import_sources()
    source = next(source for source in sources if source.key == key)
    registry.remember_files(source.selection_key or key, [path])
    paths = source.find_paths(registry)
    assert paths == [path]
    source.loader(paths)
    loader.assert_called_once_with([path])


def test_exact_multifile_selection_survives_restart_without_scanning_folder(tmp_path, monkeypatch):
    ini = str(tmp_path / "settings.ini")
    registry = FileRegistry(QSettings(ini, QSettings.Format.IniFormat))
    selected = [touch(tmp_path / "one", "c0m003.dat"), touch(tmp_path / "two", "c0m001.dat")]
    touch(tmp_path / "one", "c0m004.dat")
    registry.remember_files("Ifrit battle models", selected)
    registry.settings.sync()
    reopened = FileRegistry(QSettings(ini, QSettings.Format.IniFormat))
    source = AutoImportSource("battle model (.dat)", ("*.dat",), Mock(),
                              selection_only=True, selection_key="Ifrit battle models")
    monkeypatch.setattr("Common.autoimport.os.scandir", Mock(side_effect=AssertionError("no scan")))
    assert source.find_paths(reopened) == selected
    copy = reopened.last_files("Ifrit battle models")
    copy.clear()
    assert reopened.last_files("Ifrit battle models") == selected


def test_model_import_with_only_legacy_folder_does_not_load_all_models(tmp_path):
    registry = FileRegistry()
    touch(tmp_path, "c0m000.dat")
    touch(tmp_path, "c0m001.dat")
    registry.remember_folder("battle model (.dat)", str(tmp_path))
    source = AutoImportSource("battle model (.dat)", ("*.dat",), Mock(),
                              selection_only=True, selection_key="Ifrit battle models")
    assert source.find_paths(registry) == []


def test_missing_selected_files_do_not_expand_selection(tmp_path):
    registry = FileRegistry()
    surviving = touch(tmp_path, "c0m000.dat")
    missing = touch(tmp_path, "c0m001.dat")
    touch(tmp_path, "c0m002.dat")
    registry.remember_files("models", [surviving, missing])
    Path(missing).unlink()
    source = AutoImportSource("models", ("*.dat",), Mock(), selection_only=True)
    assert source.find_paths(registry) == [surviving]
    Path(surviving).unlink()
    assert source.find_paths(registry) == []


def test_last_selected_variant_is_preferred_to_canonical_file(tmp_path):
    registry = FileRegistry()
    touch(tmp_path, "kernel.bin")
    selected = touch(tmp_path, "custom_kernel.bin")
    binding = FileBinding("kernel.bin", registry, file_filter="*kernel*.bin")
    registry.open_file("kernel.bin", selected)
    assert AutoImportSource.for_binding(binding).find_paths(registry) == [selected]


def test_ifrit_manual_import_saves_only_its_last_pick(main_window, tmp_path, monkeypatch):
    tool = main_window._ifrit_widget
    registry = main_window.file_registry
    paths = [touch(tmp_path, name) for name in ("c0m000.dat", "c0m001.dat", "c0m002.dat")]
    loader = Mock()
    monkeypatch.setattr(tool, "_append_to_session", loader)
    tool.open_files(paths[:2])
    assert registry.last_files("Ifrit battle models") == paths[:2]
    tool.open_files(paths[2:])
    assert registry.last_files("Ifrit battle models") == paths[2:]
    # Xu shares the model directory, but keeps a separate selected set.
    registry.remember_files("Xu battle models", paths[:1])
    assert tool.auto_import_sources()[0].find_paths(registry) == paths[2:]


def test_cancelled_import_does_not_clear_previous_selection(tmp_path):
    registry = FileRegistry()
    selected = touch(tmp_path, "c0m000.dat")
    registry.remember_files("models", [selected, selected])
    registry.remember_files("models", [])
    assert registry.last_files("models") == [selected]
