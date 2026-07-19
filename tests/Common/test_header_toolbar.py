"""The shared header: file-management buttons under the selector, a collapsible opened-files
panel (no pop-up), and Import/Save that follow the active tool and Zone's active tab."""
import os
import pathlib
import sys

import pytest
from PyQt6.QtWidgets import QApplication

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture(scope="module")
def main_window(qapp):
    # Building the whole app is heavy (loads every tool), so build it once for the module.
    from ff8ultimateeditorwidget import FF8UltimateEditorWidget
    return FF8UltimateEditorWidget("Resources", "FF8GameData")


def test_left_column_stacks_selector_buttons_and_opened_files(main_window):
    col = main_window._program_option_layout
    assert col.count() == 3  # selector row, file-buttons row, opened-files panel
    btn_row = col.itemAt(1).layout()
    names = [type(btn_row.itemAt(i).widget()).__name__
             for i in range(btn_row.count()) if btn_row.itemAt(i).widget()]
    # Import/Save toolbar and the .fs extract button share the file-management row
    assert "FileToolbarWidget" in names and "FsExtractWidget" in names
    assert type(col.itemAt(2).widget()).__name__ == "OpenedFilesPanel"


def test_opened_files_panel_is_collapsible_and_live(main_window):
    panel = main_window._opened_files_panel
    # isHidden() reflects the collapse toggle regardless of whether the window is shown.
    assert panel.file_list.isHidden() is True            # collapsed by default
    before = len(main_window.file_registry.paths)
    # A name no tool binds to, so nothing tries to load it; the panel still lists it.
    main_window.file_registry.open_file("zzdummy.bin", "some/dir/zzdummy.bin")
    assert f"Opened files ({before + 1})" in panel.header_button.text()  # live count
    panel.header_button.setChecked(True)                 # expand to see them
    assert panel.file_list.isHidden() is False and panel.file_list.count() == before + 1


def test_complementary_button_present_but_disabled_without_companions(main_window):
    tb = main_window._file_toolbar
    main_window.tool_stack.setCurrentWidget(main_window._siren_widget)
    assert tb.import_button.isEnabled()
    assert tb.import_complementary_button.isEnabled() is False  # Siren has no companions


def test_import_and_save_follow_zones_active_tab(main_window):
    tb = main_window._file_toolbar
    zone = main_window._zone_widget
    main_window.tool_stack.setCurrentWidget(zone)

    zone.tabs.setCurrentIndex(0)  # mmag.bin
    assert [b.file_name for b in tb._main_bindings()] == ["mmag.bin"]
    assert sorted(b.file_name for b in tb._complementary_bindings()) == [
        "icon.sp1", "kernel.bin", "mitem.bin", "mngrp.bin", "mwepon.bin"]
    assert tb.import_button.isEnabled() and tb.import_complementary_button.isEnabled()

    zone.tabs.setCurrentIndex(1)  # mmag2.bin -> toolbar follows via file_bindings_changed
    assert [b.file_name for b in tb._main_bindings()] == ["mmag2.bin"]
    assert sorted(b.file_name for b in tb._complementary_bindings()) == ["mngrp.bin"]


def test_ifrit_open_save_are_on_the_shared_toolbar(main_window):
    ifrit = main_window._ifrit_widget
    # Ifrit dropped its own open/save/reload buttons for a binding on the shared toolbar.
    assert not hasattr(ifrit, "_open_btn") and not hasattr(ifrit, "_save_btn")
    tb = main_window._file_toolbar
    main_window.tool_stack.setCurrentWidget(ifrit)
    assert [b.file_name for b in tb._main_bindings()] == ["battle model (.dat)"]
    assert tb.import_button.isEnabled()


def test_reload_button_reloads_every_opened_file(main_window):
    from Common.filebinding import FileBinding
    tb = main_window._file_toolbar
    # The Reload button sits right after Save and acts on the whole registry.
    widgets = [tb.layout().itemAt(i).widget() for i in range(tb.layout().count())]
    assert widgets.index(tb.reload_button) == widgets.index(tb.save_button) + 1

    # A throwaway binding on a name no real tool uses, so no real loader runs on a fake path.
    # (Kept in a local so it is not garbage-collected mid-test, which would drop its signals.)
    reloaded = []
    probe = FileBinding("zzreload.bin", main_window.file_registry, load_callback=reloaded.append)
    assert probe.file_name == "zzreload.bin"

    tb.reload_button.click()                     # nothing of ours open yet -> no reload
    assert reloaded == []

    main_window.file_registry.open_file("zzreload.bin", "some/dir/zzreload.bin")  # first load
    assert reloaded == ["some/dir/zzreload.bin"]
    reloaded.clear()
    assert tb.reload_button.isEnabled()          # something is open now
    tb.reload_button.click()                     # reload -> re-read the same path from disk
    assert reloaded == ["some/dir/zzreload.bin"]


def test_accepted_file_names_are_the_concrete_ones(main_window):
    accepted = main_window.file_registry.accepted_file_names()
    # every tool's exact file name is offered to the Open-folder scan...
    assert {"price.bin", "mngrp.bin", "mmag.bin", "kernel.bin", "mitem.bin"} <= accepted
    # ...but wildcard bindings (Ifrit's *.dat) are not, since a scan can't pick one file.
    assert "battle model (.dat)" not in accepted


def test_scan_folder_finds_recognized_files_recursively(tmp_path):
    from Common.filetoolbarwidget import FileToolbarWidget
    (tmp_path / "price.bin").write_bytes(b"x")
    sub = tmp_path / "menu"
    sub.mkdir()
    (sub / "MITEM.BIN").write_bytes(b"x")        # matched case-insensitively
    (sub / "notes.txt").write_bytes(b"x")        # not a name any tool reads -> ignored
    found = FileToolbarWidget.scan_folder(str(tmp_path), {"price.bin", "mitem.bin"})
    assert set(found) == {"price.bin", "mitem.bin"}
    assert found["mitem.bin"].endswith(os.path.join("menu", "MITEM.BIN"))


def test_open_folder_loads_the_files_it_finds(main_window):
    """The end of the Open-folder flow: opening each scanned file loads its tool."""
    from Common.filetoolbarwidget import FileToolbarWidget
    reg = main_window.file_registry
    # Limit to two light tools so the test stays cheap (Siren/price.bin, Kadowaki/mitem.bin).
    found = FileToolbarWidget.scan_folder("extracted_files", {"price.bin", "mitem.bin"})
    assert set(found) == {"price.bin", "mitem.bin"}
    for file_name, path in found.items():
        reg.open_file(file_name, path)
    assert main_window._siren_widget.price_binding.is_loaded
    assert main_window._kadowaki_widget.mitem_binding.is_loaded
    assert main_window._siren_widget.editor_container.isEnabled()


def test_open_folder_hands_the_field_folder_to_the_npc_tab(main_window, monkeypatch):
    """A folder-based tool (CCGroup's NPC card players tab) loads the whole field folder via the
    shared Open-folder button (which calls its load_folder), not a per-file binding."""
    from PyQt6.QtWidgets import QFileDialog
    cc = main_window._ccgroup_widget
    main_window.tool_stack.setCurrentWidget(cc)
    cc.tab_widget.setCurrentIndex(1)  # NPC card players tab
    assert not hasattr(cc.npc_card_game_widget, "_NpcCardGameWidget__folder_button")

    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        lambda *args, **kwargs: "extracted_files/field")
    main_window._file_toolbar._open_folder()   # no named files there -> no summary dialog pops
    assert cc.npc_card_game_widget.manager.nb_players() > 0


def test_shared_save_drives_the_npc_multi_file_save(main_window, monkeypatch):
    """The NPC tab has no per-file binding; the shared Save button saves its many .jsm files
    through save_folder(), and enables once a folder is loaded (can_save_folder)."""
    from PyQt6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)  # no modal dialog
    tb = main_window._file_toolbar
    cc = main_window._ccgroup_widget
    npc = cc.npc_card_game_widget
    main_window.tool_stack.setCurrentWidget(cc)
    cc.tab_widget.setCurrentIndex(1)
    tb._on_tool_changed()
    assert not hasattr(npc, "_NpcCardGameWidget__save_button")  # moved to the shared toolbar

    cc.load_folder("extracted_files/field")
    tb._refresh()
    assert cc.can_save_folder() and tb.save_button.isEnabled()  # players loaded -> Save enabled

    saved = []
    monkeypatch.setattr(npc.manager, "save_all", lambda: (saved.append(1), 2)[1])
    tb._save()                                   # shared Save -> NPC save_folder -> save_all
    assert saved == [1]


def test_cid_drives_two_inputs_and_shares_the_exe(main_window, monkeypatch):
    """Cid's FF8 exe + wmset both run from the shared toolbar (two main bindings); Save is its
    multi-file save; and the exe key is shared with CCGroup, so opening it feeds both tools."""
    from PyQt6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)
    tb = main_window._file_toolbar
    cid = main_window._cid_widget
    cc = main_window._ccgroup_widget
    main_window.tool_stack.setCurrentWidget(cid)
    tb._on_tool_changed()
    assert [b.file_name for b in tb._main_bindings()] == ["FF8 exe", "wmsetxx.obj"]
    assert not hasattr(cid, "_exe_button") and not hasattr(cid, "_save_button")
    assert tb.save_button.isEnabled() is False   # nothing loaded yet

    # Opening the exe feeds Cid (draw table) AND CCGroup (card values) via the shared "FF8 exe" key.
    main_window.file_registry.open_file("FF8 exe", "extracted_files/FF8_EN.exe")
    assert cid.exe_loaded
    assert cc.file_loaded.endswith("FF8_EN.exe")
    assert tb.save_button.isEnabled()            # can_save_folder is now true

    saved = []
    monkeypatch.setattr(cid, "_save", lambda: saved.append(1))
    tb._save()                                   # shared Save -> Cid save_folder -> _save
    assert saved == [1]


def test_compress_buttons_show_only_for_text_tools(main_window):
    tb = main_window._file_toolbar
    sr = main_window._solomonring_widget
    assert not hasattr(sr, "reload_button")           # its own reload button is gone
    main_window.tool_stack.setCurrentWidget(sr)
    tb._on_tool_changed()
    # visibleTo(parent) reflects the show/hide state even though the window isn't shown
    assert tb.compress_button.isVisibleTo(tb) and tb.uncompress_button.isVisibleTo(tb)

    main_window.tool_stack.setCurrentWidget(main_window._siren_widget)
    tb._on_tool_changed()
    assert not tb.compress_button.isVisibleTo(tb)      # Siren has no compressible text
    assert not tb.uncompress_button.isVisibleTo(tb)


def test_minimog_main_and_complementary_bindings_share_with_zone(main_window):
    """icon.sp1 (edited in Minimog, read-only companion in Zone) and icon.TEX (Minimog's own
    preview companion) both run from the shared toolbar; opening icon.sp1 also auto-loads a
    icon.TEX beside it and is picked up read-only by Zone."""
    tb = main_window._file_toolbar
    mm = main_window._minimog_widget
    main_window.tool_stack.setCurrentWidget(mm)
    tb._on_tool_changed()
    assert [b.file_name for b in tb._main_bindings()] == ["icon.sp1"]
    assert [b.file_name for b in tb._complementary_bindings()] == ["icon.TEX"]
    assert not hasattr(mm, "file_bar") and not hasattr(mm, "tex_button")

    main_window.file_registry.open_file("icon.sp1", "extracted_files/menu/icon.sp1")
    assert mm.editor_container.isEnabled()
    assert mm.tex_file is not None                 # icon.TEX auto-loaded from the same folder
    assert tb.save_button.isEnabled()

    zone = main_window._zone_widget.mmag_widget
    assert zone.companion_bindings["icon.sp1"].is_loaded  # Zone picked up the shared icon.sp1


def test_seed_drives_two_view_inputs_and_a_main_chr_folder(main_window, monkeypatch):
    """Seed has two main bindings (chara.one, edited/saved; a standalone .mch, view-only) and a
    third input - the main_chr folder - set through the shared Open-folder button's load_folder
    hook, the same mechanism CCGroup's NPC tab uses."""
    from PyQt6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    tb = main_window._file_toolbar
    seed = main_window._seed_widget
    main_window.tool_stack.setCurrentWidget(seed)
    tb._on_tool_changed()
    assert [b.file_name for b in tb._main_bindings()] == \
        ["chara.one", "field character model (.mch)"]
    assert not hasattr(seed, "open_one_btn") and not hasattr(seed, "save_one_btn")
    assert not hasattr(seed, "file_label")             # the "No file loaded" label is gone
    assert tb.save_button.isEnabled() is False

    # Avoid the real GL viewer path (Ifrit3DWidget.load_file only needs a live 3D backend); only
    # the binding + model-list wiring is under test here. Guarded: another test sharing this
    # module-scoped main_window may have disconnected it already.
    try:
        seed.model_list.currentRowChanged.disconnect(seed._on_model_selected)
    except TypeError:
        pass
    main_window.file_registry.open_file(
        "chara.one", "extracted_files/field/mapdata/bc/bccent12/chara.one")
    assert seed.model_list.count() > 0
    assert seed.seed_manager.main_chr_folder is not None   # auto-detected from the chara.one path
    assert tb.save_button.isEnabled()

    # The shared Open-folder button's load_folder hook overrides the main_chr folder.
    import os
    alt_folder = os.path.abspath("extracted_files/field/model/main_chr")
    seed.seed_manager.main_chr_folder = None
    folder_loader = getattr(tb.tool_stack.currentWidget(), "load_folder", None)
    assert callable(folder_loader)
    folder_loader(alt_folder)
    assert str(seed.seed_manager.main_chr_folder) == alt_folder

    # Save writes straight back to the loaded chara.one path (no Save-As dialog).
    saved = []
    monkeypatch.setattr(seed.seed_manager, "save_chara_one", lambda dest: saved.append(dest) or [])
    monkeypatch.setattr(seed.seed_manager, "modified_entry_names", lambda: ["dummy"])
    tb._save()
    assert saved == [seed.seed_manager.chara_one_path]


def test_compress_buttons_route_to_the_active_tool(main_window, monkeypatch):
    tb = main_window._file_toolbar
    sr = main_window._solomonring_widget
    main_window.tool_stack.setCurrentWidget(sr)
    tb._on_tool_changed()
    calls = []
    monkeypatch.setattr(sr, "compress_text", lambda: calls.append("c"))
    monkeypatch.setattr(sr, "uncompress_text", lambda: calls.append("u"))
    tb._compress()
    tb._uncompress()
    assert calls == ["c", "u"]


def test_alexander_open_files_hook_and_auto_save_enable(main_window, monkeypatch):
    """Alexander has no FileBinding at all (a0stgXXX.x has no fixed name, and several are opened
    into a list at once): Import calls its open_files() hook, and Save enables itself via
    file_bindings_changed once a stage is loaded, without the user touching the header again."""
    from PyQt6.QtWidgets import QFileDialog, QMessageBox
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    tb = main_window._file_toolbar
    alexander = main_window._alexander_widget
    main_window.tool_stack.setCurrentWidget(alexander)
    tb._on_tool_changed()

    assert tb._main_bindings() == [] and tb._complementary_bindings() == []
    assert tb.import_button.isEnabled() is True     # enabled via open_files(), no bindings needed
    assert not hasattr(alexander, "open_x_btn") and not hasattr(alexander, "save_btn")
    assert tb.save_button.isEnabled() is False       # nothing loaded yet

    # Ifrit3DWidget.load_file() (real GL viewer) hangs headless, same as Seed's - stub it out so
    # only the open_files()/manager/save_folder() logic under test actually runs.
    monkeypatch.setattr(alexander.viewer_3d, "load_file", lambda: None)
    monkeypatch.setattr(alexander, "_frame_stage", lambda: None)

    stage_path = str(PROJECT_ROOT / "extracted_files" / "battle" / "a0stg000.x")
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([stage_path], ""))
    tb.import_button.click()  # -> Alexander.open_files()
    assert alexander.stage_list.count() == 1
    assert alexander.manager.can_save is True
    assert tb.save_button.isEnabled() is True        # auto-enabled via file_bindings_changed
    assert alexander.manager.current_stage_path == stage_path

    # Save writes straight back to the loaded stage's own path - no Save-As dialog - since it
    # is now known (current_stage_path), matching every other converted tool's direct-write Save.
    saved = []
    dialog_called = []
    monkeypatch.setattr(alexander.manager, "save", lambda path: saved.append(path) or "ok")
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        lambda *a, **k: (dialog_called.append(1), ("", ""))[1])
    tb.save_button.click()  # -> Alexander.save_folder()
    assert saved == [stage_path]
    assert dialog_called == [], "a known stage path must not prompt a Save-As dialog"


def test_alexander_save_falls_back_to_a_dialog_without_a_known_stage_path(main_window, monkeypatch):
    """The one case Save can't write back directly: no stage was loaded this session with a known
    path (e.g. only a .glb was imported), so there is no "corresponding .x file" to write to."""
    from PyQt6.QtWidgets import QFileDialog, QMessageBox
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    alexander = main_window._alexander_widget

    # Load a real stage (can_save is a read-only property, so this is how it becomes True)...
    stage_path = str(PROJECT_ROOT / "extracted_files" / "battle" / "a0stg000.x")
    alexander.manager.load_stage_file(stage_path)
    assert alexander.manager.can_save is True
    # ...then simulate the post-.glb-import state: the known path is gone, the template stays.
    alexander.manager.current_stage_path = None

    saved = []
    dialog_called = []
    monkeypatch.setattr(alexander.manager, "save", lambda path: saved.append(path) or "ok")

    def fake_dialog(*_a, **_k):
        dialog_called.append(1)
        return ("picked.x", "")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", fake_dialog)

    alexander.save_folder()
    assert dialog_called == [1]
    assert saved == ["picked.x"]


def test_hook_based_tools_register_a_summary_entry_in_opened_files(main_window, monkeypatch):
    """Alexander/Seed/CCGroup's NPC tab load files through a hook (open_files/load_folder), not a
    FileBinding, so nothing put them in the registry before - they were invisible in the Opened
    files panel. Each now registers one summary entry (not one per file - could be dozens)."""
    from PyQt6.QtWidgets import QFileDialog, QMessageBox
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)
    tb = main_window._file_toolbar
    registry = main_window.file_registry

    # Alexander: several stages at once -> one entry, listing names only when there are few.
    alexander = main_window._alexander_widget
    main_window.tool_stack.setCurrentWidget(alexander)
    tb._on_tool_changed()
    monkeypatch.setattr(alexander.viewer_3d, "load_file", lambda: None)
    monkeypatch.setattr(alexander, "_frame_stage", lambda: None)
    stage_paths = [str(PROJECT_ROOT / "extracted_files" / "battle" / f"a0stg{i:03d}.x")
                  for i in range(8)]
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: (stage_paths, ""))
    tb.import_button.click()
    assert registry.paths["Alexander battle stage(s)"].startswith("8 stages in")  # collapsed
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: (stage_paths[:2], ""))
    tb.import_button.click()
    assert registry.paths["Alexander battle stage(s)"] == "2 stages: a0stg000.x, a0stg001.x"

    # Seed: the main_chr folder appears even via auto-detection (the common path), not only when
    # the user manually overrides it with the Open-folder button.
    seed = main_window._seed_widget
    main_window.tool_stack.setCurrentWidget(seed)
    tb._on_tool_changed()
    try:  # avoid the GL viewer hang; an earlier test in this module may have disconnected it already
        seed.model_list.currentRowChanged.disconnect(seed._on_model_selected)
    except TypeError:
        pass
    registry.open_file("chara.one", str(PROJECT_ROOT / "extracted_files" / "field" / "mapdata" /
                                        "bc" / "bccent12" / "chara.one"))
    assert "main_chr" in registry.paths["Seed main_chr folder"]

    # CCGroup NPC tab: 170 .jsm scripts -> one entry, not 170.
    cc = main_window._ccgroup_widget
    main_window.tool_stack.setCurrentWidget(cc)
    tb._on_tool_changed()
    cc.tab_widget.setCurrentIndex(1)
    cc.load_folder(str(PROJECT_ROOT / "extracted_files" / "field"))
    assert "scripts in" in registry.paths["CCGroup NPC scripts"]

    # The panel itself reflects every one of these summary entries.
    panel = main_window._opened_files_panel
    panel._refresh()
    for key in ("Alexander battle stage(s)", "Seed main_chr folder", "CCGroup NPC scripts"):
        assert any(key in panel.file_list.item(i).text() for i in range(panel.file_list.count()))


def test_joker_sp2_open_and_direct_save(main_window, tmp_path):
    """Joker edits whichever .sp2 is picked (face.sp2 or cardanm.sp2, no fixed FF8 name) - a
    single-select wildcard binding, same shape as Ifrit's *.dat. Save writes straight back to the
    loaded path, no dialog, matching every other converted tool."""
    import shutil
    tb = main_window._file_toolbar
    joker = main_window._joker_widget
    main_window.tool_stack.setCurrentWidget(joker)
    tb._on_tool_changed()

    assert not hasattr(joker, "load_button") and not hasattr(joker, "save_button")
    assert [b.file_name for b in tb._main_bindings()] == ["sprite sheet (.sp2)"]
    assert tb.import_button.isEnabled() is True
    assert tb.save_button.isEnabled() is False   # nothing loaded yet

    # Work on a copy: Save writes straight back to the loaded path, so the real fixture in
    # extracted_files must never be the one actually opened here.
    face_source = PROJECT_ROOT / "extracted_files" / "menu" / "face.sp2"
    face_copy = str(shutil.copy(face_source, tmp_path / "face.sp2"))
    main_window.file_registry.open_file("sprite sheet (.sp2)", face_copy)
    assert joker.manager.file_path == face_copy
    assert joker.manager.sp2 is not None
    assert tb.save_button.isEnabled() is True

    original_bytes = face_source.read_bytes()
    tb.save_button.click()  # writes straight back to face_copy, no Save-As dialog
    assert open(face_copy, "rb").read() == original_bytes  # unedited -> byte-exact rewrite

    # A second real .sp2 shares the same generic binding key.
    cardanm_copy = str(shutil.copy(
        PROJECT_ROOT / "extracted_files" / "menu" / "cardanm.sp2", tmp_path / "cardanm.sp2"))
    main_window.file_registry.open_file("sprite sheet (.sp2)", cardanm_copy)
    assert joker.manager.file_path == cardanm_copy


def test_julia_audio_fmt_open_and_direct_save(main_window, monkeypatch, tmp_path):
    """Julia edits audio.fmt (+ audio.dat from the same folder), a fixed FF8 name - a plain
    FileBinding, no hooks needed. Save writes straight back to the loaded path (JuliaManager.save
    always fully rebuilds/repacks, so it is never byte-identical even unedited - verified instead
    by reloading and checking the sound count round-trips)."""
    import shutil
    from PyQt6.QtWidgets import QMessageBox
    tb = main_window._file_toolbar
    julia = main_window._julia_widget
    main_window.tool_stack.setCurrentWidget(julia)
    tb._on_tool_changed()

    assert not hasattr(julia, "load_button") and not hasattr(julia, "save_button")
    assert [b.file_name for b in tb._main_bindings()] == ["audio.fmt"]
    assert tb.import_button.isEnabled() is True
    assert tb.save_button.isEnabled() is False   # nothing loaded yet

    # Work on copies: Save writes straight back to the loaded path.
    fmt_copy = shutil.copy(PROJECT_ROOT / "extracted_files" / "Sound" / "audio.fmt", tmp_path)
    shutil.copy(PROJECT_ROOT / "extracted_files" / "Sound" / "audio.dat", tmp_path)
    main_window.file_registry.open_file("audio.fmt", fmt_copy)
    assert julia.manager.fmt_path == fmt_copy
    nb_sounds = len(julia.manager.sounds)
    assert nb_sounds > 0
    assert tb.save_button.isEnabled() is True

    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Yes)
    tb.save_button.click()  # writes straight to fmt_copy/audio.dat, no Save-As dialog
    assert julia.manager.fmt_path == fmt_copy   # unchanged - no dialog took over

    from Julia.juliamanager import JuliaManager
    reloaded = JuliaManager(julia.game_data)
    reloaded.load(fmt_copy)
    assert len(reloaded.sounds) == nb_sounds


def test_shumitranslator_opens_a_tab_per_file(main_window, monkeypatch, tmp_path):
    """ShumiTranslator's seven fixed-name kinds (kernel.bin, namedic.bin, mngrp.bin, FF8 exe,
    remaster .dat, field.fs, world.fs) plus the c0mxx.dat multi-select are eight *independent*
    Import-menu entries - not one combined "N files loaded" line like Alexander. Each opened file
    gets its own closable tab (a ShumiFilePane with its own manager); Save/CSV/compress act on the
    active tab. kernel.bin shares its registry key with SolomonRing (opening it feeds both)."""
    import shutil
    from PyQt6.QtWidgets import QFileDialog, QMessageBox
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: None)  # save_folder's success pop-up
    tb = main_window._file_toolbar
    shumi = main_window._shumi_translator_widget
    main_window.tool_stack.setCurrentWidget(shumi)
    tb._on_tool_changed()

    # The module-scoped app is shared: an earlier test (Cid) opens the "FF8 exe" key, which this
    # tool also binds to, so a tab may already be open and that binding reads as loaded. Return the
    # tool to a pristine state: close its tabs and clear the bindings' loaded marks.
    while shumi.tab_widget.count():
        shumi.tab_widget.tabCloseRequested.emit(0)
    for binding in shumi._bindings:
        binding._loaded_path = ""
    tb._refresh()

    # Its own open/save widgets are gone; the header drives everything.
    assert not hasattr(shumi, "file_dialog_button") and not hasattr(shumi, "save_button")
    # ONE Import entry: a single multi-select dialog for every kind, not one entry per file kind.
    assert [label for label, _ in tb._import_entries()] == ["Open FF8 text file(s)"]
    assert tb.import_button.isEnabled() and tb.save_button.isEnabled() is False  # no tab yet

    # Open kernel.bin (on a copy - Save writes straight back) -> its own tab, compress shown.
    kernel_copy = str(shutil.copy(PROJECT_ROOT / "extracted_files" / "main" / "kernel.bin", tmp_path))
    main_window.file_registry.open_file("kernel.bin", kernel_copy)
    assert shumi.tab_widget.count() == 1
    pane = shumi.tab_widget.widget(0)
    assert pane.file_type.name == "KERNEL" and pane.file_loaded == kernel_copy
    assert shumi.tab_widget.tabText(0) == "kernel.bin"
    assert tb.save_button.isEnabled()                     # a tab is open -> can_save_folder
    assert not shumi.compress_button.isHidden()           # kernel supports compress
    assert main_window._solomonring_widget.kernel_binding.current_path == kernel_copy  # shared key

    # Open namedic.bin -> a SECOND tab; the kernel tab stays open and independent.
    namedic_copy = str(shutil.copy(PROJECT_ROOT / "extracted_files" / "main" / "namedic.bin", tmp_path))
    main_window.file_registry.open_file("namedic.bin", namedic_copy)
    assert shumi.tab_widget.count() == 2
    assert shumi.tab_widget.currentWidget().file_type.name == "NAMEDIC"
    assert shumi.tab_widget.widget(0).file_type.name == "KERNEL"   # kernel tab untouched
    assert shumi.compress_button.isHidden()               # namedic has no compressible text
    shumi.tab_widget.setCurrentIndex(0)                   # back to kernel
    assert not shumi.compress_button.isHidden()           # per-tab toolbar follows the active kind

    # c0mxx.dat multi-select -> one tab + ONE summary registry entry (not one per file).
    c0m_paths = [str(PROJECT_ROOT / "extracted_files" / "battle" / f"c0m{i:03d}.dat") for i in range(3)]
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: (c0m_paths, ""))
    shumi.open_files()
    assert shumi.tab_widget.count() == 3
    dat_pane = shumi.tab_widget.currentWidget()
    assert dat_pane.file_type.name == "DAT" and dat_pane.file_loaded == c0m_paths
    assert "3 c0mxx.dat" in shumi.tab_widget.tabText(2)
    assert "ShumiTranslator battle text (c0mxx.dat)" in main_window.file_registry.paths
    # kernel/namedic keep their OWN registry entries - the kinds are independent, not collapsed.
    assert "kernel.bin" in main_window.file_registry.paths
    assert "namedic.bin" in main_window.file_registry.paths

    # Re-opening the same kernel path focuses the existing tab, never a duplicate.
    shumi.kernel_binding._loaded_path = ""
    main_window.file_registry.paths.pop("kernel.bin")
    main_window.file_registry.open_file("kernel.bin", kernel_copy)
    assert shumi.tab_widget.count() == 3

    # Save acts on the active tab - the kernel one writes straight back to its own path.
    # KernelManager fully repacks on save (never byte-identical, like Julia's audio.fmt), so verify
    # functionally: reloading the written file yields the same number of text sections.
    from ShumiTranslator.model.kernel.kernelmanager import KernelManager
    kernel_pane = shumi.tab_widget.widget(0)
    nb_sections = len(kernel_pane.manager.section_list)
    shumi.tab_widget.setCurrentWidget(kernel_pane)
    tb.save_button.click()                                # writes straight back to kernel_copy
    reloaded = KernelManager(game_data=shumi.game_data)
    reloaded.load_file(kernel_copy)
    assert len(reloaded.section_list) == nb_sections     # round-trips

    # Closing a tab drops just that one.
    shumi.tab_widget.tabCloseRequested.emit(2)
    assert shumi.tab_widget.count() == 2


def test_shumitranslator_does_not_build_a_pane_for_a_background_open(main_window):
    """The freeze fix: a ShumiFilePane is heavy (mngrp.bin ~2600 text boxes). A file opened in
    ANOTHER tool (Shiva editing mngrp.bin, SolomonRing the kernel) shares its path through the
    registry but must NOT eagerly build that whole editor here in the background - that froze the
    app. A pane is built only when the file is opened while ShumiTranslator is the active tool."""
    shumi = main_window._shumi_translator_widget
    # Pristine tab set (an earlier test leaves tabs / loaded bindings on the shared window).
    main_window.tool_stack.setCurrentWidget(shumi)
    main_window._file_toolbar._on_tool_changed()
    while shumi.tab_widget.count():
        shumi.tab_widget.tabCloseRequested.emit(0)
    for binding in shumi._bindings:
        binding._loaded_path = ""

    namedic = str(PROJECT_ROOT / "extracted_files" / "main" / "namedic.bin")  # stands in for mngrp.bin

    # Another tool is the active one, and it opens namedic.bin.
    main_window.tool_stack.setCurrentWidget(main_window._siren_widget)
    assert shumi._is_active_tool() is False
    before = shumi.tab_widget.count()
    main_window.file_registry.open_file("namedic.bin", namedic)
    assert shumi.tab_widget.count() == before  # background open -> no pane built here

    # Now the user comes to ShumiTranslator and imports it -> the pane is built on demand.
    main_window.tool_stack.setCurrentWidget(shumi)
    assert shumi._is_active_tool() is True
    shumi.namedic_binding.open_path(namedic)  # what the header Import does
    assert shumi.tab_widget.count() == before + 1
    assert shumi.tab_widget.currentWidget().file_type.name == "NAMEDIC"


def test_shumitranslator_single_multiselect_import_opens_a_tab_each(main_window, monkeypatch):
    """One Import = one multi-select dialog covering every kind. Picking kernel.bin + namedic.bin +
    two c0mxx.dat in a single go opens a kernel tab, a namedic tab and ONE battle-text tab (the c0m
    set collapses), each kind detected from its name - not eight separate menu entries."""
    from PyQt6.QtWidgets import QFileDialog, QMessageBox
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    tb = main_window._file_toolbar
    shumi = main_window._shumi_translator_widget
    main_window.tool_stack.setCurrentWidget(shumi)
    tb._on_tool_changed()
    while shumi.tab_widget.count():
        shumi.tab_widget.tabCloseRequested.emit(0)
    for binding in shumi._bindings:
        binding._loaded_path = ""

    # The dialog's filter preselects every name this tool reads (so they show up ready to pick).
    picks = [str(PROJECT_ROOT / "extracted_files" / "main" / "kernel.bin"),
             str(PROJECT_ROOT / "extracted_files" / "main" / "namedic.bin"),
             str(PROJECT_ROOT / "extracted_files" / "battle" / "c0m000.dat"),
             str(PROJECT_ROOT / "extracted_files" / "battle" / "c0m001.dat")]
    captured = {}

    def fake_dialog(parent, caption, filter="", **kwargs):
        captured["filter"] = filter
        return (picks, "")
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", staticmethod(fake_dialog))

    tb.import_button.click()  # the single Import -> open_files (one dialog, several files)

    # The filter lists every accepted name so they are preselected in the dialog.
    for pattern in ("*kernel*.bin", "mngrp.bin", "*.exe", "field*.fs", "c0m*.dat"):
        assert pattern in captured["filter"]

    kinds = sorted(shumi.tab_widget.widget(i).file_type.name
                   for i in range(shumi.tab_widget.count()))
    assert kinds == ["DAT", "KERNEL", "NAMEDIC"]  # 3 tabs: the two c0m collapsed into one DAT
    # the fixed-name picks were published to the registry (shared with SolomonRing/Cid/...)
    assert main_window.file_registry.get_path("kernel.bin").endswith("kernel.bin")
    assert main_window.file_registry.get_path("namedic.bin").endswith("namedic.bin")
    assert "ShumiTranslator battle text (c0mxx.dat)" in main_window.file_registry.paths
