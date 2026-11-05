"""Tool update of the external tools: VincentTim (in every Tool update) is only downloaded when
its release asset changed, and FFNx's effect sources (a GitHub archive sent without its size)
show their progress against the size of the previous download."""
import io
import json
import zipfile

import pytest

from ToolUpdate.toolupdate import ToolDownloader

RELEASES_URL = "https://api.github.com/repos/myst6re/vincent-tim/releases"
ASSETS_URL = "https://api.github.com/fake/vincent-tim/releases/1/assets"
ZIP_URL = "https://fake.download/vincent-tim-1.2.1.zip"
FFNX_URL = "https://github.com/HobbitDur/FFNx/archive/refs/heads/Work.zip"


def make_zip(files: dict, comment=b"") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zip_file:
        for name, content in files.items():
            zip_file.writestr(name, content)
        zip_file.comment = comment
    return buffer.getvalue()


class FakeResponse:
    def __init__(self, json_data=None, content=b"", sized=True):
        self._json_data = json_data
        self._content = content
        self.status_code = 200
        self.headers = {"content-length": str(len(content))} if content and sized else {}
        self.history = []

    def json(self):
        return self._json_data

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size=4096):
        for i in range(0, len(self._content), chunk_size):
            yield self._content[i:i + chunk_size]


@pytest.fixture
def github(monkeypatch, tmp_path):
    """An isolated folder and a fake GitHub: responses maps link -> FakeResponse, requested
    lists every link asked for."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ToolUpdate").mkdir()
    (tmp_path / "ToolUpdate" / "list.json").write_text(json.dumps({"ExternalTools": {
        "VincentTim": {"link": "https://github.com/myst6re/vincent-tim", "install_path": "ExternalTools/VincentTim",
                       "only_when_new": True},
        "FFNxEffects": {"link": "https://github.com/HobbitDur/FFNx", "install_path": "ExternalTools/FFNx/fx",
                        "source": {"stable": "branch:Work", "canary": "branch:Work"},
                        "source_folder": "src/ff8/battle/fx", "expected_size": 50000}}}))
    asset = {"id": 95321503, "name": "vincent-tim-1.2.1.zip", "updated_at": "2023-02-12T10:58:38Z",
             "browser_download_url": ZIP_URL}
    responses = {
        RELEASES_URL: FakeResponse(json_data=[{"tag_name": "v1.2.1", "prerelease": False, "assets_url": ASSETS_URL}]),
        ASSETS_URL: FakeResponse(json_data=[asset]),
        ZIP_URL: FakeResponse(content=make_zip({"tim.exe": b"tim"})),
    }
    requested = []

    def fake_get(link, headers={}, stream=False, timeout=None):
        requested.append(link)
        return responses[link]

    monkeypatch.setattr("ToolUpdate.toolupdate.requests.get", fake_get)
    return type("Github", (), {"responses": responses, "requested": requested, "asset": asset})


def test_vincent_tim_is_downloaded_only_when_its_release_changed(github, tmp_path):
    downloader = ToolDownloader()
    assert downloader.update_one_tool("VincentTim") is True
    assert (tmp_path / "ExternalTools" / "VincentTim" / "tim.exe").read_bytes() == b"tim"
    github.requested.clear()
    assert downloader.update_one_tool("VincentTim") is False  # same asset: only the release list is read
    assert ZIP_URL not in github.requested
    github.asset["updated_at"] = "2026-11-05T10:00:00Z"  # a new build of the asset
    assert downloader.update_one_tool("VincentTim") is True
    assert ZIP_URL in github.requested


def test_vincent_tim_is_downloaded_again_when_its_folder_is_missing(github, tmp_path):
    import shutil
    downloader = ToolDownloader()
    downloader.update_one_tool("VincentTim")
    shutil.rmtree(tmp_path / "ExternalTools" / "VincentTim")
    assert downloader.update_one_tool("VincentTim") is True
    assert (tmp_path / "ExternalTools" / "VincentTim" / "tim.exe").is_file()


def test_ffnx_sources_progress_runs_against_the_previous_download_size(github, tmp_path):
    archive = make_zip({"FFNx-Work/src/ff8/battle/fx/mag001_cure.cpp": b"x" * 30000}, comment=b"abc")
    github.responses[FFNX_URL] = FakeResponse(content=archive, sized=False)  # no content-length
    downloader = ToolDownloader()
    progress = []
    downloader.update_one_tool("FFNxEffects", lambda done, total: progress.append((done, total)))
    # the first time against "expected_size", always below full until the download is over
    assert progress[0] == (0, 50000)
    assert all(0 < total and done < total for done, total in progress[:-1])
    assert progress[-1] == (len(archive), len(archive))
    source = (tmp_path / "ExternalTools" / "FFNx" / "fx" / "SOURCE.txt").read_text().splitlines()
    assert source[2] == "abc" and source[4] == str(len(archive))
    progress.clear()
    downloader.update_one_tool("FFNxEffects", lambda done, total: progress.append((done, total)))
    assert progress[0] == (0, len(archive))  # then against the last download's size
