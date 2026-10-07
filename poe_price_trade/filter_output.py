"""Economy Filter Generator — filesystem side: Documents/My Games resolution,
writing the merged .filter, sound-file copy."""
from __future__ import annotations
import ctypes
import hashlib
import logging
import os
import shutil
from pathlib import Path
from typing import Optional

from . import filter_core

log = logging.getLogger(__name__)

class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


_FOLDERID_DOCUMENTS = _GUID(
    0xFDD39AD0, 0x238F, 0x46AF,
    (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7),
)


def documents_dir() -> Path:
    """Real Documents folder via SHGetKnownFolderPath (handles OneDrive
    redirection correctly, unlike guessing `~/Documents`) — same low-level
    ctypes-Windows-API style as config.py's DPAPI helpers. Falls back to
    %USERPROFILE%\\Documents if the API call fails for any reason."""
    try:
        path_ptr = ctypes.c_wchar_p()
        hresult = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(_FOLDERID_DOCUMENTS), 0, None, ctypes.byref(path_ptr))
        if hresult == 0 and path_ptr.value:
            path = Path(path_ptr.value)
            ctypes.windll.ole32.CoTaskMemFree(path_ptr)
            return path
    except Exception as e:
        log.warning("SHGetKnownFolderPath failed: %s", e)
    return Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Documents"


def game_filter_dir(game: str, override: str = "") -> Path:
    if override:
        return Path(override)
    sub = "Path of Exile 2" if game == "poe2" else "Path of Exile"
    return documents_dir() / "My Games" / sub


def filter_path(dir_: Path, name: str = filter_core.DEFAULT_TIER_NAME) -> Path:
    return dir_ / f"{name}.filter"


def write_filter(dir_: Path, generated_section: str, base_text: Optional[str],
                 name: str = filter_core.DEFAULT_TIER_NAME) -> Path:
    """generated_section (our blocks, may be "") + base_text (NeverSink, may be None) ->
    dir_/<name>.filter, overwritten unconditionally. Raises ValueError if the name is not
    usable, or if both sources are empty - the caller must not touch the existing file in that
    case, and this is the last line of defense against silently truncating it."""
    _clean, err = filter_core.validate_filter_name(name)
    if err:
        raise ValueError(err)
    body = filter_core.compose_filter_body(generated_section, base_text)
    dir_.mkdir(parents=True, exist_ok=True)
    path = filter_path(dir_, name)
    path.write_text(body, encoding="utf-8")
    return path


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_sounds(dir_: Path, sound_map: dict, decide=None, notify=None) -> dict:
    """sound_map: {label: source file or None} (labels: S/A/B and Q). Copies each chosen sound
    into the filter folder under its ORIGINAL file name (a "#" or ";" in it becomes "_", see
    filter_core.safe_sound_name) and returns {label: name written}.

    Nothing already in the folder is touched silently: same name + same content = reuse it (no
    copy); same name + different content = decide(name, new_name) -> "overwrite" | "keep"
    (default keep: the new file gets new_name); one file used by several labels is copied once.
    notify(text) gets every message the user should see."""
    notify = notify or (lambda text: None)
    requests, srcs = [], {}
    for label, src in (sound_map or {}).items():
        if not src:
            continue
        sp = Path(src)
        if not sp.is_file():
            log.warning("Filter sound for %s not found: %s", label, sp)
            notify(f'⚠ ไม่พบไฟล์เสียง "{src}" (ข้าม)')
            continue
        requests.append((label, sp.name, file_sha256(sp)))
        srcs[label] = sp
    if not requests:
        return {}
    existing: dict = {}
    if dir_.is_dir():
        wanted = {filter_core.safe_sound_name(n)[0] for _l, n, _h in requests}
        for entry in dir_.iterdir():
            if entry.is_file():
                existing[entry.name] = file_sha256(entry) if entry.name in wanted else None
    plan = filter_core.plan_sound_files(requests, existing)
    dest, copies, msgs = filter_core.resolve_sound_plan(plan, decide)
    for m in msgs:
        notify(m)
    dir_.mkdir(parents=True, exist_ok=True)
    done = set()
    for label, final in copies:
        try:
            shutil.copyfile(srcs[label], dir_ / final)
            done.add(final)
        except Exception as e:
            log.warning("Filter sound copy failed (%s): %s", label, e)
            notify(f'⚠ ก๊อปไฟล์เสียง "{final}" ไม่ได้: {e}')
    reused = {it["dest"] for it in plan["items"] if it["status"] == "same"}
    return {lab: d for lab, d in dest.items() if d in done or d in reused}
