"""Tests for the self-update system: ToolDownloader.download_self downloads the tool's own
release zip into the SelfUpdate folder, then the Patcher copies it over the installation."""
import io
import json
import subprocess
import sys
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


def make_release_zip(exe_content: bytes = b"new exe") -> bytes:
    """Build an in-memory zip that looks like a FF8UltimateEditor release."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zip_file:
        zip_file.writestr("FF8UltimateEditor.exe", exe_content)
        zip_file.writestr("Resources/hobbitdur.ico", b"icon")
        zip_file.writestr("ToolUpdate/list.json", b"{}")
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

    def iter_content(self, chunk_size=4096):
        for i in range(0, len(self._content), chunk_size):
            yield self._content[i:i + chunk_size]


@pytest.fixture
def fake_github(monkeypatch, tmp_path):
    """Run in an isolated folder with a fake GitHub API answering all requests.get calls.
    Returns the list of requested links so tests can assert which URLs were hit."""
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
        CANARY_ASSETS_URL: FakeResponse(json_data=[
            {"name": "FF8UltimateEditor-cli-continuous-abc1234.zip", "browser_download_url": CANARY_CLI_ZIP_URL},
            {"name": "FF8UltimateEditor-continuous-abc1234.zip", "browser_download_url": CANARY_GUI_ZIP_URL},
        ]),
        GUI_ZIP_URL: FakeResponse(content=make_release_zip(b"stable exe")),
        CANARY_GUI_ZIP_URL: FakeResponse(content=make_release_zip(b"canary exe")),
    }

    requested_links = []

    def fake_get(link, headers={}, stream=False):
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

    monkeypatch.setattr(patcher, "wait_for_exit", lambda exe_name, timeout=30: True)
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

    monkeypatch.setattr(patcher, "wait_for_exit", lambda exe_name, timeout=30: False)
    monkeypatch.setattr("builtins.input", lambda *args: "")
    launched = []
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kwargs: launched.append(cmd))

    patcher.main()

    # Nothing copied, nothing launched: update aborted while the tool is running
    assert not (tmp_path / "FF8UltimateEditor.exe").exists()
    assert self_update.exists()
    assert launched == []
