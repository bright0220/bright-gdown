from .download import download
from bs4 import BeautifulSoup
from builtins import bytes
from itertools import islice
import json
import re
import requests
import sys

if sys.version_info.major < 3:
    from pathlib2 import Path
else:
    from pathlib import Path
client = requests.session()

folders_url = "https://drive.google.com/drive/folders/"
files_url = "https://drive.google.com/uc?id="
folder_type = "application/vnd.google-apps.folder"

string_regex = re.compile(r"'((?:[^'\\]|\\.)*)'")


MAX_NUMBER_FILES = 50


class GoogleDriveFile(object):
    """Represent Google Drive file objects structure.

    Attributes
    ----------
    id: str
        Unique id, used to build the download URL.
    name: str
        Actual name, used as file name.
    type: str
        MIME type, or application/vnd.google-apps.folder if it is a folder
    children: List[GoogleDriveFile]
        If it is a directory, it contains the folder files/directories

    """

    def __init__(self, id, name, type, children=None):
        self.id = id
        self.name = name
        self.type = type
        self.children = children if children is not None else []

    def is_folder(self):
        return self.type == folder_type

    def __repr__(self):
        template = "(id={id}, name={name}, type={type}, children={children})"
        return "GoogleDriveFile" + template.format(
            id=self.id,
            name=self.name,
            type=self.type,
            children=self.children,
        )


def download_and_parse_google_drive_link(
    folder,
    quiet=False,
    use_cookies=True,
    remaining_ok=False,
):
    """Get folder structure of Google Drive folder URL.

    Parameters
    ----------
    url: str
        URL of the Google Drive folder.
        Must be of the format 'https://drive.google.com/drive/folders/{url}'.
    quiet: bool, optional
        Suppress terminal output.
    use_cookies: bool, optional
        Flag to use cookies. Default is True.
    remaining_ok: bool, optional
        Flag that ensures that is ok to let some file to not be downloaded,
        since there is a limitation of how many items gdown can download,
        default is False.

    Returns
    -------
    return_code: bool
        Returns False if the download completed unsuccessfully.
        May be due to invalid URLs, permission errors, rate limits, etc.
    gdrive_file: GoogleDriveFile
        Returns the folder structure of the Google Drive folder.
    """
    return_code = True

    folder_page = client.get(folder)

    if folder_page.status_code != 200:
        return False, None
    folder_soup = BeautifulSoup(folder_page.text, features="html.parser")

    if not use_cookies:
        client.cookies.clear()

    # finds the script tag with window['_DRIVE_ivd']
    encoded_data = None
    for script in folder_soup.select("script"):
        inner_html = script.decode_contents()

        if "_DRIVE_ivd" in inner_html:
            # first js string is _DRIVE_ivd, the second one is the encoded arr
            regex_iter = string_regex.finditer(inner_html)
            # get the second elem in the iter
            try:
                encoded_data = next(islice(regex_iter, 1, None)).group(1)
            except StopIteration:
                raise RuntimeError(
                    "Couldn't find the folder encoded JS string"
                )
            break

    if encoded_data is None:
        raise RuntimeError("Didn't found _DRIVE_ivd script tag")

    # decodes the array and evaluates it as a python array
    decoded = bytes(encoded_data, "utf-8").decode("unicode_escape")
    folder_arr = json.loads(decoded)

    folder_contents = [] if folder_arr[0] is None else folder_arr[0]

    gdrive_file = GoogleDriveFile(
        id=folder[39:],
        name=folder_soup.title.contents[0][:-15],
        type=folder_type,
    )

    id_name_type_iter = ((e[0], e[2], e[3]) for e in folder_contents)

    for child_id, child_name, child_type in id_name_type_iter:
        if child_type != folder_type:
            if not quiet:
                print(
                    "Processing file",
                    child_id,
                    child_name,
                )
            gdrive_file.children.append(
                GoogleDriveFile(
                    id=child_id,
                    name=child_name,
                    type=child_type,
                )
            )
            if not return_code:
                return return_code, None
            continue

        if not quiet:
            print(
                "Retrieving folder",
                child_id,
                child_name,
            )
        return_code, child = download_and_parse_google_drive_link(
            folders_url + child_id,
            use_cookies=use_cookies,
            quiet=quiet,
        )
        if not return_code:
            return return_code, None
        gdrive_file.children.append(child)
    has_at_least_max_files = len(gdrive_file.children) == MAX_NUMBER_FILES
    if not remaining_ok and has_at_least_max_files:
        err_msg = " ".join(
            [
                "The gdrive folder with url: {url}".format(url=folder),
                "has at least {max} files,".format(max=MAX_NUMBER_FILES),
                "gdrive can't download more than this limit,",
                "if you are ok with this,",
                "please run again with --remaining-ok flag.",
            ]
        )
        raise RuntimeError(err_msg)
    return return_code, gdrive_file


def get_directory_structure(gdrive_file, previous_path):
    """Converts a Google Drive folder structure into a local directory list.

    Parameters
    ----------
    gdrive_file: GoogleDriveFile
        Google Drive folder structure.
    previous_path: pathlib.Path
        Path containing the parent's file path.

    Returns
    -------
    directory_structure: list
        List containing a tuple of the files' ID and file path.
    """
    directory_structure = []
    for file in gdrive_file.children:
        if file.is_folder():
            directory_structure.append((None, previous_path / file.name))
            for i in get_directory_structure(file, previous_path / file.name):
                directory_structure.append(i)
        elif not file.children:
            directory_structure.append((file.id, previous_path / file.name))
    return directory_structure


def download_folder(
    folder,
    output=None,
    quiet=False,
    proxy=None,
    speed=None,
    use_cookies=True,
    remaining_ok=False,
):
    """Downloads entire folder from URL.

    Parameters
    ----------
    url: str
        URL of the Google Drive folder.
        Must be of the format 'https://drive.google.com/drive/folders/{url}'.
    output: str, optional
        String containing the path of the output folder.
        Defaults to current working directory.
    quiet: bool, optional
        Suppress terminal output.
    proxy: str, optional
        Proxy.
    speed: float, optional
        Download byte size per second (e.g., 256KB/s = 256 * 1024).
    use_cookies: bool, optional
        Flag to use cookies. Default is True.

    Returns
    -------
    return_code: bool
        Returns False if the download completed unsuccessfully.
        May be due to invalid URLs, permission errors, rate limits, etc.

    Example
    -------
    gdown.download_folder(
        "https://drive.google.com/drive/folders/" +
        "1ZXEhzbLRLU1giKKRJkjm8N04cO_JoYE2",
        use_cookies=True
    )
    """
    if not quiet:
        print("Retrieving folder list")
    return_code, gdrive_file = download_and_parse_google_drive_link(
        folder,
        quiet=quiet,
        use_cookies=False,
        remaining_ok=remaining_ok,
    )

    if not return_code:
        return return_code
    if not quiet:
        print("Retrieving folder list completed")
        print("Building directory structure")
    if output is None:
        output = Path.cwd()
    else:
        output = Path(output)
    root_folder = output / gdrive_file.name
    directory_structure = get_directory_structure(gdrive_file, root_folder)
    root_folder.mkdir(parents=True, exist_ok=True)

    if not quiet:
        print("Building directory structure completed")
    for file_id, file_path in directory_structure:
        if file_id is None:  # folder
            file_path.mkdir(parents=True, exist_ok=True)
            continue

        return_code = download(
            files_url + file_id,
            output=str(file_path),
            quiet=quiet,
            proxy=proxy,
            speed=speed,
            use_cookies=use_cookies,
        )

        if not return_code:
            if not quiet:
                print("Download ended unsuccessfully")
            return return_code
    if return_code and not quiet:
        print("Download completed")
    return return_code
