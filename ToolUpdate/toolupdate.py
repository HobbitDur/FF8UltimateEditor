import json
import os
import re
import shutil
import types
from zipfile import ZipFile
import requests


class ToolDownloader:
    GITHUB_RELEASE_TAG_PATH = "/releases/tag/"
    GITHUB_RELEASE_PATH = "/releases"
    FOLDER_DOWNLOAD = "ToolDownload"

    def __init__(self):
        with open(os.path.join("ToolUpdate", "list.json")) as f:
            self.json_data =json.load(f)

    def update_all_tools(self, download_update_func: types.MethodType = None, canary=False):
        for tool_name in self.TOOL_LIST:
            self.update_one_tool(tool_name, download_update_func, canary)

    def update_one_tool(self, tool_name: str, download_update_func: types.MethodType = None, canary=False):
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

    def update_self(self, download_update_func: types.MethodType = None, canary=True):
        os.makedirs(self.FOLDER_DOWNLOAD, exist_ok=True)
        dd_url = self.__get_github_url_file(self.json_data['SelfUpdate'], "assets_url", canary)
        json_file = self.__download_file(dd_url, download_update_func, headers={'content-type': 'application/json'})[0].json()
        asset_link = ""
        if len(json_file) == 1:
            asset_link = json_file[0]['browser_download_url']
        dd_file_name = self.__download_file(asset_link, download_update_func, write_file=True)[1]
        self._unzip_tool(dd_file_name, "SelfUpdate")
        shutil.rmtree(self.FOLDER_DOWNLOAD)



    def __download_file(self, link, download_update_func: types.MethodType = None, headers={}, write_file=False, file_name=None, dest_path=FOLDER_DOWNLOAD) -> (
            requests.models.Response, str):
        print("Downloading with link: {}".format(link))
        if write_file:
            stream = True
        else:
            stream = False

        request_return = requests.get(link, headers=headers, stream=stream)

        if not file_name:
            if "Content-Disposition" in request_return.headers.keys():
                file_name = re.findall("filename\*?=['\"]?(?:UTF-\d['\"]*)?([^;\r\n\"']*)['\"]?;?",
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
            current_tag_version = ""
            for el in json_file:
                if el['tag_name'].count('.') >= 1:
                    if not current_tag_version or el['tag_name'] > current_tag_version:
                        current_tag_version = el['tag_name']
                        dd_url = el[json_url]
        return dd_url

    def _unzip_tool(self, dd_file_name: str, tool_folder: str, ignore_first_folder = False):
        # Unzip locally then copy all files, so we don't have problem erasing files while unziping
        if '.zip' in dd_file_name:
            archive = "tempzip"
            os.makedirs(archive, exist_ok=True)
            with ZipFile(os.path.join(self.FOLDER_DOWNLOAD, dd_file_name), 'r') as zip_ref:
                zip_ref.extractall(archive)
        list_dir = os.listdir(archive)
        try:
            index_folder = os.listdir(archive).index(dd_file_name.rsplit('.', 1)[0])
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
        if archive != "":
            shutil.rmtree(archive)
