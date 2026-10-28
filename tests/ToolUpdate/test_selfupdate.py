"""Tests for the self-update system: ToolDownloader.download_self downloads the tool's own
release zip into the SelfUpdate folder, then the Patcher copies it over the installation."""
import io
import json
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

import Patcher.main as patcher
from ToolUpdate.toolupdate import ToolDownloader

RELEASES_URL = "https://api.github.com/repos/HobbitDur/FF8UltimateEditor/releases"
STABLE_ASSETS_URL = "https://api.github.com/fake/releases/2/assets"
CANARY_ASSETS_URL = "https://api.github.com/fake/releases/1/assets"
GUI_ZIP_URL = "https://fake.download/FF8UltimateEditor-1.10.0.zip"
CLI_ZIP_URL = "https://fake.download/FF8UltimateEditor-cli-1.10.0.zip"
CANARY_GUI_ZIP_URL = "https://fake.download/FF8UltimateEditor-continuous-abc1234.zip"
CANARY_CLI_ZIP_URL = "https://fake.download/FF8UltimateEditor-cli-continuous-abc1234.zip"
CANARY_GHOST_ZIP_URL = "https://fake.download/FF8UltimateEditor-continuous-0000000.zip"
CANARY_LINUX_URL = "https://fake.download/ff8ultimateeditor-linux_x64-continuous-abc1234.tar.gz"
CANARY_CLI_LINUX_URL = "https://fake.download/FF8UltimateEditor-cli-linux_x64-continuous-abc1234.tar.gz"


def make_release_zip(exe_content: bytes = b"new exe") -> bytes:
    """Build an in-memory zip that looks like a FF8UltimateEditor release."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zip_file:
        zip_file.writestr("FF8UltimateEditor.exe", exe_content)
        zip_file.writestr("Resources/hobbitdur.ico", b"icon")
        zip_file.writestr("ToolUpdate/list.json", b"{}")
    return buffer.getvalue()


def make_release_tar_gz(exe_content: bytes = b"new exe") -> bytes:
    """Build an in-memory .tar.gz laid out like the Linux release (tar -C release .)."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar_file:
        for name, content in (("./FF8UltimateEditor", exe_content), ("./Resources/hobbitdur.ico", b"icon")):
            info = tarfile.TarInfo(name)
            info.size = len(content)
            info.mode = 0o755
            tar_file.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


class FakeResponse:
    def __init__(self, json_data=None, content=b""):
        self._json_data = json_data
        self._content = content
        self.status_code = 200
        self.headers = {"content-length": str(len(content))} if content else {}
        self.history = []

    def json(self):
        return self._json_data

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size=4096):
        for i in range(0, len(self._content), chunk_size):
            yield self._content[i:i + chunk_size]


@pytest.fixture
def fake_github(monkeypatch, tmp_path):
    """Run in an isolated folder with a fake GitHub API answering all requests.get calls.
    Returns the list of requested links so tests can assert which URLs were hit.
    Runs as on Windows (the Windows .zip is the build picked), whatever the test machine is."""
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.chdir(tmp_path)
    tool_update_dir = tmp_path / "ToolUpdate"
    tool_update_dir.mkdir()
    (tool_update_dir / "list.json").write_text(json.dumps({
        "ExternalTools": {},
        "SelfUpdate": {"link": "https://github.com/HobbitDur/FF8UltimateEditor"}
    }))

    releases = [
        {  # Canary build, newest first like the real GitHub API
            "tag_name": "continuous",
            "prerelease": True,
            "assets_url": CANARY_ASSETS_URL,
        },
        {  # An old release with a higher string-sort but lower version, to check version parsing
            "tag_name": "1.2.0",
            "prerelease": False,
            "assets_url": "https://api.github.com/fake/releases/0/assets",
        },
        {  # The latest stable release
            "tag_name": "1.10.0",
            "prerelease": False,
            "assets_url": STABLE_ASSETS_URL,
        },
    ]
    responses = {
        RELEASES_URL: FakeResponse(json_data=releases),
        STABLE_ASSETS_URL: FakeResponse(json_data=[
            {"name": "FF8UltimateEditor-cli-1.10.0.zip", "browser_download_url": CLI_ZIP_URL},
            {"name": "FF8UltimateEditor-1.10.0.zip", "browser_download_url": GUI_ZIP_URL},
        ]),
        CANARY_ASSETS_URL: FakeResponse(json_data=[  # Sorted by name, like the real assets list
            {"name": "FF8UltimateEditor-cli-continuous-abc1234.zip", "browser_download_url": CANARY_CLI_ZIP_URL},
            {  # An upload that never finished: listed, but a 404 when downloaded
                "name": "FF8UltimateEditor-continuous-0000000.zip", "state": "starter",
                "browser_download_url": CANARY_GHOST_ZIP_URL,
            },
            {"name": "FF8UltimateEditor-continuous-abc1234.zip", "browser_download_url": CANARY_GUI_ZIP_URL},
            {"name": "ff8ultimateeditor-linux_x64-continuous-abc1234.tar.gz", "browser_download_url": CANARY_LINUX_URL},
            {"name": "FF8UltimateEditor-cli-linux_x64-continuous-abc1234.tar.gz", "browser_download_url": CANARY_CLI_LINUX_URL},
        ]),
        GUI_ZIP_URL: FakeResponse(content=make_release_zip(b"stable exe")),
        CANARY_GUI_ZIP_URL: FakeResponse(content=make_release_zip(b"canary exe")),
        CANARY_LINUX_URL: FakeResponse(content=make_release_tar_gz(b"canary linux exe")),
    }

    requested_links = []

    def fake_get(link, headers={}, stream=False, timeout=None):
        assert timeout, "every request needs a timeout, or a dead connection hangs the update"
        requested_links.append(link)
        if link not in responses:
            raise AssertionError(f"Unexpected download link requested: '{link}'")
        return responses[link]

    monkeypatch.setattr("ToolUpdate.toolupdate.requests.get", fake_get)
    return requested_links


def test_download_self_stable_extracts_gui_release_to_selfupdate(fake_github, tmp_path):
    ToolDownloader().download_self(canary=False)

    assert (tmp_path / "SelfUpdate" / "FF8UltimateEditor.exe").read_bytes() == b"stable exe"
    assert (tmp_path / "SelfUpdate" / "Resources" / "hobbitdur.ico").exists()
    assert CLI_ZIP_URL not in fake_github  # The CLI zip must not be the one installed


def test_download_self_stable_picks_highest_version_not_string_order(fake_github):
    ToolDownloader().download_self(canary=False)

    # 1.10.0 > 1.2.0 even though "1.2.0" sorts after "1.10.0" as a string
    assert STABLE_ASSETS_URL in fake_github


def test_download_self_canary_picks_prerelease(fake_github, tmp_path):
    ToolDownloader().download_self(canary=True)

    assert CANARY_ASSETS_URL in fake_github
    assert (tmp_path / "SelfUpdate" / "FF8UltimateEditor.exe").read_bytes() == b"canary exe"


def test_download_self_canary_skips_unfinished_upload(fake_github, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    ToolDownloader().download_self(canary=True)

    assert CANARY_GHOST_ZIP_URL not in fake_github
    assert CANARY_LINUX_URL not in fake_github
    assert (tmp_path / "SelfUpdate" / "FF8UltimateEditor.exe").read_bytes() == b"canary exe"


def test_download_self_canary_on_linux_extracts_tar_gz(fake_github, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    ToolDownloader().download_self(canary=True)

    assert CANARY_GUI_ZIP_URL not in fake_github
    assert (tmp_path / "SelfUpdate" / "FF8UltimateEditor").read_bytes() == b"canary linux exe"
    assert (tmp_path / "SelfUpdate" / "Resources" / "hobbitdur.ico").exists()


def test_download_self_without_build_for_platform_fails_and_cleans(fake_github, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")  # The stable release has no Linux build
    with pytest.raises(RuntimeError, match="Linux"):
        ToolDownloader().download_self(canary=False)

    assert not (tmp_path / "SelfUpdate").exists()
    assert not (tmp_path / ToolDownloader.FOLDER_DOWNLOAD).exists()


def test_installer_reports_failure_instead_of_hanging():
    from ToolUpdate.toolupdatewidget import Installer

    class BrokenDownloader:
        def download_self(self, *args, **kwargs):
            raise ConnectionError("no network")

    installer = Installer()
    failed, completed = [], []
    installer.failed.connect(lambda tool, error: failed.append((tool, error)))
    installer.completed.connect(completed.append)
    installer.install(BrokenDownloader(), False, ["Self"])

    assert failed == [("Self", "ConnectionError: no network")]
    assert completed == []


def test_download_self_cleans_temporary_folders(fake_github, tmp_path):
    ToolDownloader().download_self(canary=False)

    assert not (tmp_path / ToolDownloader.FOLDER_DOWNLOAD).exists()
    assert not (tmp_path / "tempzip").exists()


def test_patcher_applies_selfupdate_and_restarts(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    # The patcher names the executables after the platform it runs on
    tool_exe = "FF8UltimateEditor.exe" if sys.platform == "win32" else "FF8UltimateEditor"
    patcher_exe = "Patcher.exe" if sys.platform == "win32" else "Patcher"
    # Simulate an installation with an old exe and a downloaded SelfUpdate folder
    (tmp_path / tool_exe).write_bytes(b"old exe")
    self_update = tmp_path / "SelfUpdate"
    (self_update / "Resources").mkdir(parents=True)
    (self_update / tool_exe).write_bytes(b"new exe")
    (self_update / patcher_exe).write_bytes(b"patcher from release")
    (self_update / "Resources" / "hobbitdur.ico").write_bytes(b"icon")

    monkeypatch.setattr(patcher, "wait_for_exit", lambda exe_path, timeout=60: True)
    launched = []
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kwargs: launched.append(cmd))

    patcher.main()

    # New files applied, but the running patcher is never overwritten
    assert (tmp_path / tool_exe).read_bytes() == b"new exe"
    assert (tmp_path / "Resources" / "hobbitdur.ico").exists()
    assert not (tmp_path / patcher_exe).exists()
    # Temporary folder cleaned and tool restarted
    assert not self_update.exists()
    assert launched and tool_exe in str(launched[0][0])


def test_patcher_aborts_if_tool_still_running(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    self_update = tmp_path / "SelfUpdate"
    self_update.mkdir()
    (self_update / "FF8UltimateEditor.exe").write_bytes(b"new exe")

    monkeypatch.setattr(patcher, "wait_for_exit", lambda exe_path, timeout=60: False)
    told = []
    monkeypatch.setattr(patcher, "notify", lambda text, error=True: told.append(text))
    launched = []
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kwargs: launched.append(cmd))

    patcher.main()
    assert told and "still running" in told[0]       # a message box: the Patcher has no console

    # Nothing copied, nothing launched: update aborted while the tool is running
    assert not (tmp_path / "FF8UltimateEditor.exe").exists()
    assert self_update.exists()
    assert launched == []


def test_patcher_reports_a_blocked_restart_without_crashing(monkeypatch, tmp_path):
    """Windows' application control can refuse to start the new build (WinError 4551). The update
    is already copied: the Patcher says so and where the exe is, instead of calling input() -
    which, without a console, crashed it with "lost sys.stdin"."""
    monkeypatch.chdir(tmp_path)
    tool_exe = "FF8UltimateEditor.exe" if sys.platform == "win32" else "FF8UltimateEditor"
    (tmp_path / "SelfUpdate").mkdir()
    (tmp_path / "SelfUpdate" / tool_exe).write_bytes(b"new exe")
    monkeypatch.setattr(patcher, "wait_for_exit", lambda exe_path, timeout=60: True)
    monkeypatch.setattr("builtins.input", lambda *args: (_ for _ in ()).throw(RuntimeError("lost sys.stdin")))

    def blocked(cmd, **kwargs):
        raise OSError(22, "An Application Control policy has blocked this file", None, 4551)
    monkeypatch.setattr(subprocess, "Popen", blocked)
    told = []
    monkeypatch.setattr(patcher, "notify", lambda text, error=True: told.append(text))

    patcher.main()

    assert (tmp_path / tool_exe).read_bytes() == b"new exe"
    assert len(told) == 1 and "update is installed" in told[0] and str(tmp_path / tool_exe) in told[0]
    assert not (tmp_path / "SelfUpdate").exists()


def _fake_processes(monkeypatch, *processes):
    """psutil.process_iter(attrs) as the Patcher sees it: a process that could not be read has
    None for that attribute, one that ended while being listed is not there at all."""
    from types import SimpleNamespace
    listed = [SimpleNamespace(info={"name": name, "exe": exe}) for name, exe in processes]
    monkeypatch.setattr(patcher.psutil, "process_iter", lambda attrs=None: iter(listed))


def test_patcher_waits_only_for_its_own_installation(monkeypatch, tmp_path):
    """Another copy of the tool open in another folder does not lock this installation: waiting
    for every process of that name made the Patcher give up after its timeout, copy nothing and
    leave SelfUpdate full."""
    exe = tmp_path / "install" / "FF8UltimateEditor.exe"
    other = tmp_path / "Downloads" / "FF8UltimateEditor-v4.2.0" / "FF8UltimateEditor.exe"
    _fake_processes(monkeypatch, ("FF8UltimateEditor.exe", str(other)))
    assert not patcher.is_running(exe)

    _fake_processes(monkeypatch, ("FF8UltimateEditor.exe", str(other)), ("FF8UltimateEditor.exe", str(exe)))
    assert patcher.is_running(exe)


def test_patcher_counts_an_unreadable_process_of_that_name(monkeypatch, tmp_path):
    exe = tmp_path / "FF8UltimateEditor.exe"
    _fake_processes(monkeypatch, ("FF8UltimateEditor.exe", None), ("explorer.exe", None))
    assert patcher.is_running(exe)

    _fake_processes(monkeypatch, ("explorer.exe", None))
    assert not patcher.is_running(exe)


def test_patcher_waits_for_the_exe_next_to_it(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    tool_exe = "FF8UltimateEditor.exe" if sys.platform == "win32" else "FF8UltimateEditor"
    (tmp_path / "SelfUpdate").mkdir()
    (tmp_path / "SelfUpdate" / tool_exe).write_bytes(b"new exe")
    waited = []
    monkeypatch.setattr(patcher, "wait_for_exit", lambda exe_path, timeout=60: waited.append(exe_path) or True)
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kwargs: None)

    patcher.main()

    assert [path.resolve() for path in waited] == [tmp_path / tool_exe]
    assert (tmp_path / tool_exe).read_bytes() == b"new exe"


def test_self_update_puts_the_downloaded_patcher_in_place(monkeypatch, tmp_path):
    """The Patcher skips itself when copying, so the editor installs the new Patcher before
    launching it: Patcher fixes reach the users."""
    from types import SimpleNamespace
    from ToolUpdate import toolupdatewidget
    monkeypatch.chdir(tmp_path)
    name = "Patcher.exe" if sys.platform == "win32" else "Patcher"
    (tmp_path / "Patcher").mkdir()
    (tmp_path / "Patcher" / name).write_bytes(b"old patcher")
    (tmp_path / "SelfUpdate" / "Patcher").mkdir(parents=True)
    (tmp_path / "SelfUpdate" / "Patcher" / name).write_bytes(b"new patcher")
    monkeypatch.setattr(toolupdatewidget.QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(toolupdatewidget.QApplication, "quit", lambda *a: None)
    launched = []
    monkeypatch.setattr(toolupdatewidget.subprocess, "Popen", lambda cmd, **kwargs: launched.append(
        (tmp_path / "Patcher" / name).read_bytes()))
    host = SimpleNamespace(window=lambda: SimpleNamespace(close=lambda: True))

    toolupdatewidget.ToolUpdateWidget.start_self_update_process(host)

    assert launched == [b"new patcher"]
