"""The effect recorder is never in git: run from source, FF8UltimateEditor builds it at startup when
it is missing or older than its source (Fujin.recorderbuild), and the effect preview says so while
it builds or why it could not be built. No real build runs here."""
import os
import sys

import pytest


@pytest.fixture
def folder(tmp_path, monkeypatch):
    from Fujin import recorderbuild
    source, script, exe = tmp_path / "fxrecorder.cpp", tmp_path / "build.bat", tmp_path / "fxrecorder.exe"
    source.write_text("int main() {}")
    script.write_text("@echo off")
    monkeypatch.setattr(recorderbuild, "FOLDER", tmp_path)
    monkeypatch.setattr(recorderbuild, "RECORDER", exe)
    monkeypatch.setattr(recorderbuild, "SOURCES", (source, script))
    monkeypatch.setattr(recorderbuild, "FFNX_EFFECTS", tmp_path / "no-ffnx-sources")
    monkeypatch.setattr(sys, "platform", "win32")
    return source, exe


def test_built_when_missing_or_older_than_its_source(folder, monkeypatch):
    from Fujin.recorderbuild import needs_build
    source, exe = folder
    assert needs_build()                                    # a fresh clone: no exe
    exe.write_bytes(b"MZ")
    os.utime(source, (1000, 1000))
    os.utime(source.with_name("build.bat"), (1000, 1000))
    os.utime(exe, (2000, 2000))
    assert not needs_build()                                # up to date
    os.utime(source, (3000, 3000))
    assert needs_build()                                    # a pull changed its source
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert not needs_build()                                # the release ships its own


def test_preview_waits_for_the_build_and_says_why_it_failed(qapp, folder, monkeypatch):
    from Common.fileregistry import FileRegistry
    from Fujin import nativepreview, recorderbuild
    build = recorderbuild.RecorderBuild()
    monkeypatch.setattr(recorderbuild, "_build", build)
    monkeypatch.setattr(nativepreview, "RECORDER", recorderbuild.RECORDER)
    view = nativepreview.NativePreviewView(FileRegistry())
    build.building = True
    assert any("being built" in need for need in view.missing())
    build._end(recorderbuild.NO_COMPILER, "no Visual Studio C++ build tools found (cl.exe)")
    assert not build.building
    assert any("Visual Studio" in need and "Desktop development with C++" in need for need in view.missing())
    build._end(2, "fxrecorder.cpp(10): error C2065: 'x': undeclared identifier\nbuild fxrecorder.exe exit 2")
    assert any("error C2065" in need for need in view.missing())


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])
