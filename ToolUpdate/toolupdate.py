import json
import os
import re
import shutil
import sys
import tarfile
import types
from zipfile import ZipFile
import requests
from packaging import version

class ToolDownloader:
    GITHUB_RELEASE_TAG_PATH = "/releases/tag/"
    GITHUB_RELEASE_PATH = "/releases"
    FOLDER_DOWNLOAD = "ToolDownload"
    TIMEOUT = 30  # Seconds without an answer before a request fails, instead of hanging forever

    def __init__(self):
        with open(os.path.join("ToolUpdate", "list.json")) as f:
            self.json_data =json.load(f)

    def update_all_tools(self, download_update_func: types.MethodType = None, canary=False):
        for tool_name in self.TOOL_LIST:
            self.update_one_tool(tool_name, download_update_func, canary)

    def update_one_tool(self, tool_name: str, download_update_func: types.MethodType = None, canary=False):
        if "source" in self.json_data['ExternalTools'][tool_name]:
            return self.update_source_tool(tool_name, download_update_func, canary)
        os.makedirs(self.FOLDER_DOWNLOAD, exist_ok=True)
        dd_url = self.__get_github_url_file(self.json_data['ExternalTools'][tool_name], "assets_url", canary)
        json_file = self.__download_file(dd_url, download_update_func, headers={'content-type': 'application/json'})[0].json()
        asset_link = ""
        if len(json_file) == 1: # If only 1 asset available
            asset_link = json_file[0]['browser_download_url']
        else:
            for i, json_asset in enumerate(json_file):
                for asset_name in self.json_data['ExternalTools'][tool_name]["asset_name"]:
                    if asset_name == json_asset['name']:
                        asset_link = json_file[i]['browser_download_url']
                        break
                if asset_link != "":
                    break
        if asset_link == "":
            asset_link = json_file[0]['browser_download_url']
        dd_file_name = self.__download_file(asset_link, download_update_func, write_file=True)[1]
        if "install_path" in self.json_data["ExternalTools"][tool_name]:
            install_path = self.json_data["ExternalTools"][tool_name]["install_path"]
        else:
            install_path = tool_name

        if "ignore_first_folder" in self.json_data["ExternalTools"][tool_name]:
            ignore_first_folder = self.json_data["ExternalTools"][tool_name]["ignore_first_folder"]
        else:
            ignore_first_folder = False
        self._unzip_tool(dd_file_name, install_path, ignore_first_folder)
        shutil.rmtree(self.FOLDER_DOWNLOAD)

    def update_source_tool(self, tool_name: str, download_update_func: types.MethodType = None, canary=False):
        """A tool taken as source code, not a release asset: one folder of a GitHub repository
        ("source_folder") at the channel's "source" - "branch:<name>" (that branch's latest
        commit) or "release" (the source of the latest release, or pre-release for canary) - into
        "install_path", replacing what was there; SOURCE.txt says where it came from. FFNx's
        effect sources (FFNxEffects): built into Fujin's effect recorder (Tools/fxrecorder)."""
        entry = self.json_data['ExternalTools'][tool_name]
        source = entry["source"]["canary" if canary else "stable"]
        if source.startswith("branch:"):
            ref = source.split(":", 1)[1]
            link = f"{entry['link']}/archive/refs/heads/{ref}.zip"
        else:
            ref = "release"
            link = self.__get_github_url_file(entry, "zipball_url", canary)
        os.makedirs(self.FOLDER_DOWNLOAD, exist_ok=True)
        try:
            file_name = self.__download_file(link, download_update_func, write_file=True, file_name=f"{tool_name}.zip")[1]
            install_path, folder = entry["install_path"], entry["source_folder"].strip("/") + "/"
            with ZipFile(os.path.join(self.FOLDER_DOWNLOAD, file_name)) as archive:
                members = [name for name in archive.namelist() if name.split("/", 1)[-1].startswith(folder)
                           and not name.endswith("/")]
                if not members:
                    raise ValueError(f"{folder} is not in {link}")
                shutil.rmtree(install_path, ignore_errors=True)
                os.makedirs(install_path, exist_ok=True)
                for name in members:
                    relative = name.split("/", 1)[-1][len(folder):]
                    target = os.path.join(install_path, *relative.split("/"))
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with archive.open(name) as source_file, open(target, "wb") as out:
                        shutil.copyfileobj(source_file, out)
                commit = archive.comment.decode("ascii", "replace").strip()     # GitHub: the commit
            with open(os.path.join(install_path, "SOURCE.txt"), "w", encoding="utf-8") as info:
                info.write(f"{entry['link']}\n{ref}\n{commit}\n{folder}\n")
        finally:
            shutil.rmtree(self.FOLDER_DOWNLOAD, ignore_errors=True)

    def download_self(self, download_update_func: types.MethodType = None, canary=True):
        os.makedirs(self.FOLDER_DOWNLOAD, exist_ok=True)
        try:
            dd_url = self.__get_github_url_file(self.json_data['SelfUpdate'], "assets_url", canary)
            json_file = self.__download_file(dd_url, download_update_func, headers={'content-type': 'application/json'})[0].json()
            asset_link = self._self_asset_link(json_file)
            dd_file_name = self.__download_file(asset_link, download_update_func, write_file=True)[1]
            self._unzip_tool(dd_file_name, "SelfUpdate")
        finally:
            shutil.rmtree(self.FOLDER_DOWNLOAD, ignore_errors=True)

    @staticmethod
    def _self_asset_link(assets: list) -> str:
        """The GUI build for this platform among a release's assets. A release holds the GUI and
        the CLI, each as a Windows .zip and a Linux .tar.gz. The assets list also holds uploads
        that never finished (state "starter", 404 when downloaded), which the release page hides:
        only "uploaded" assets count."""
        linux = sys.platform != "win32"
        for asset in assets:
            if asset.get('state', 'uploaded') != 'uploaded':
                continue
            name = asset['name'].lower()
            if name.startswith("ff8ultimateeditor") and "cli" not in name and ("linux" in name) == linux:
                return asset['browser_download_url']
        raise RuntimeError("This release has no FF8UltimateEditor build for " + ("Linux" if linux else "Windows"))


    def __download_file(self, link, download_update_func: types.MethodType = None, headers={}, write_file=False, file_name=None, dest_path=FOLDER_DOWNLOAD) -> (
            requests.models.Response, str):
        print("Downloading with link: {}".format(link))
        if write_file:
            stream = True
        else:
            stream = False

        request_return = requests.get(link, headers=headers, stream=stream, timeout=self.TIMEOUT)
        request_return.raise_for_status()  # An error page (rate limit, missing asset) is not the file

        if not file_name:
            if "Content-Disposition" in request_return.headers.keys():
                file_name = re.findall(r"filename\*?=['\"]?(?:UTF-\d['\"]*)?([^;\r\n\"']*)['\"]?;?",
                                       request_return.headers["Content-Disposition"])[0]
            elif "download" in request_return.headers.keys():
                file_name = request_return.headers["download"]
            elif len(request_return.history) > 0 and request_return.history[0].headers[
                'Location']:  # Means there is a redirection, so taking the name from the first location
                file_name = request_return.history[0].headers['Location'].split('/')[-1]
                file_name = file_name.replace('+', ' ')
            else:
                file_name = link.split("/")[-1]

        if write_file:
            total_length = request_return.headers.get('content-length')
            if total_length is None:  # no content length header
                total_length = -1
            else:
                total_length = int(total_length)
            dl = 0
            if download_update_func:
                download_update_func(dl, total_length)
            full_data = bytearray()
            for data in request_return.iter_content(chunk_size=4096):
                dl += len(data)
                full_data.extend(data)
                if download_update_func:
                    download_update_func(dl, total_length)
            with open(os.path.join(dest_path, file_name), "wb") as file:
                file.write(full_data)

        if request_return.status_code == 200:
            print("Successfully downloaded {}".format(link))
        else:
            print("Fail to download {}".format(link))

        return request_return, file_name

    def __get_github_link(self, original_link: str):
        github_link = original_link + self.GITHUB_RELEASE_PATH
        github_link = github_link.replace('github.com', 'api.github.com/repos')
        return github_link

    def __get_github_url_file(self, json_data, json_url="assets_url", canary=False):
        json_link = self.__get_github_link(json_data['link'])
        json_file = self.__download_file(json_link, headers={'content-type': 'application/json'})[0]
        json_file = json_file.json()
        dd_url = ""
        if canary:
            for el in json_file:
                if el['prerelease']:
                    dd_url = el[json_url]
                    break
        if not dd_url:  # No pre-release found, taking latest
            current_tag_version = None
            for el in json_file:
                tag = el['tag_name']
                if tag.count('.') >= 1:
                    try:
                        # Parse the version properly
                        parsed_version = version.parse(tag)

                        if not current_tag_version or parsed_version > version.parse(current_tag_version):
                            current_tag_version = tag  # Store the original tag name
                            dd_url = el[json_url]  # Replace with your actual URL key
                    except:
                        # Skip if version parsing fails
                        continue
        return dd_url

    def _unzip_tool(self, dd_file_name: str, tool_folder: str, ignore_first_folder = False):
        # Unzip locally then copy all files, so we don't have problem erasing files while unziping
        archive = "tempzip"
        archive_path = os.path.join(self.FOLDER_DOWNLOAD, dd_file_name)
        lower_name = dd_file_name.lower()
        if lower_name.endswith('.zip'):
            archive_stem = dd_file_name[:-len('.zip')]
        elif lower_name.endswith('.tar.gz'):  # The Linux builds
            archive_stem = dd_file_name[:-len('.tar.gz')]
        else:
            raise ValueError(f"Cannot extract {dd_file_name}: only .zip and .tar.gz archives are supported")
        os.makedirs(archive, exist_ok=True)
        try:
            if lower_name.endswith('.zip'):
                with ZipFile(archive_path, 'r') as zip_ref:
                    zip_ref.extractall(archive)
            else:
                with tarfile.open(archive_path, 'r:gz') as tar_ref:
                    tar_ref.extractall(archive, filter='data')
            list_dir = os.listdir(archive)
            try:
                index_folder = list_dir.index(archive_stem)
            except ValueError:
                index_folder = -1
            if index_folder >= 0:  # If the extract contain the folder name itself
                archive_to_copy = os.path.join(archive, list_dir[index_folder])
            elif ignore_first_folder:
                archive_to_copy = os.path.join(archive, list_dir[0])
            else:
                archive_to_copy = archive
            futur_path = tool_folder

            if archive_to_copy and futur_path:
                shutil.copytree(archive_to_copy, futur_path, dirs_exist_ok=True,
                                copy_function=shutil.copy)  # shutil.copy to make it works on linux proton
        finally:
            shutil.rmtree(archive, ignore_errors=True)