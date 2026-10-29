"""Bring-your-own-project inputs for the API: an uploaded ZIP, or a shallow clone of a public repository.

Everything lands in a private temp directory that is deleted when the run ends. Extraction is
defensive: size and file-count limits, no paths outside the target directory, no symlinks.
"""

import os
import re
import shutil
import stat
import subprocess
import tempfile
import zipfile
from pathlib import Path

MAX_ZIP_BYTES = 50_000_000
MAX_UNZIPPED_BYTES = 200_000_000
MAX_FILES = 5000
MAX_ATTACHMENT_BYTES = 5_000_000
REPO_URL = re.compile(r"https://(github\.com|gitlab\.com|bitbucket\.org)/[\w.-]+/[\w.-]+?(\.git)?/?")
SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")


class UploadError(ValueError):
    """The input can't be used; the message is safe to show to the user."""


def workdir() -> Path:
    return Path(tempfile.mkdtemp(prefix="tracepilot-upload-"))


def extract_zip(data: bytes, dest: Path) -> Path:
    """Unpack a project ZIP into dest and return the project root (a single top-level folder is unwrapped)."""
    if len(data) > MAX_ZIP_BYTES:
        raise UploadError(f"the ZIP is larger than {MAX_ZIP_BYTES // 1_000_000} MB")
    zip_path = dest.parent / "upload.zip"
    zip_path.write_bytes(data)
    try:
        archive = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        raise UploadError("the upload is not a valid ZIP file") from exc
    with archive:
        members = archive.infolist()
        if len(members) > MAX_FILES:
            raise UploadError(f"the ZIP has more than {MAX_FILES} entries; upload the service's own folder")
        if sum(m.file_size for m in members) > MAX_UNZIPPED_BYTES:
            raise UploadError(f"the ZIP unpacks to more than {MAX_UNZIPPED_BYTES // 1_000_000} MB")
        root = dest.resolve()
        for m in members:
            target = (dest / m.filename).resolve()
            if not target.is_relative_to(root):
                raise UploadError(f"unsafe path in the ZIP: {m.filename}")
            if stat.S_ISLNK(m.external_attr >> 16):
                raise UploadError(f"symbolic links are not allowed: {m.filename}")
        archive.extractall(dest)
    zip_path.unlink()
    entries = [p for p in dest.iterdir() if not p.name.startswith((".", "__MACOSX"))]
    return entries[0] if len(entries) == 1 and entries[0].is_dir() else dest


def clone_repo(url: str, dest: Path) -> Path:
    """Shallow-clone a public repository over HTTPS. Only well-known hosts; no credentials, no prompts."""
    url = url.strip()
    if not REPO_URL.fullmatch(url):
        raise UploadError("use a public https:// URL on github.com, gitlab.com or bitbucket.org")
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "echo"}
    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", "--single-branch", url, str(dest)],
            capture_output=True, text=True, timeout=180, env=env,
        )  # fmt: skip
    except subprocess.TimeoutExpired as exc:
        raise UploadError("cloning took longer than 3 minutes") from exc
    if result.returncode != 0:
        raise UploadError("could not clone the repository (is it public?)")
    shutil.rmtree(dest / ".git", ignore_errors=True)
    if sum(1 for _ in dest.rglob("*")) > MAX_FILES * 4:
        raise UploadError("the repository is too large; point TracePilot at a single service")
    return dest


def save_attachment(name: str, data: bytes, folder: Path, allowed: set[str]) -> Path:
    """Store an uploaded log or screenshot under a sanitised name."""
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise UploadError(f"{name} is larger than {MAX_ATTACHMENT_BYTES // 1_000_000} MB")
    clean = SAFE_NAME.sub("_", Path(name).name)[:80] or "file"
    if Path(clean).suffix.lower() not in allowed:
        raise UploadError(f"{name}: expected one of {', '.join(sorted(allowed))}")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / clean
    path.write_bytes(data)
    return path
