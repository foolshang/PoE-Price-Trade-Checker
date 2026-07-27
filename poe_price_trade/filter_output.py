"""Economy Filter Generator — filesystem side: Documents/My Games resolution,
writing the merged .filter, sound-file copy, auto-regen state."""
from __future__ import annotations
import ctypes
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_FILTER_NAME = "poe-checker.filter"


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


def write_filter(dir_: Path, generated_section: str, base_text: Optional[str]) -> Path:
    """generated_section (hub-tiered rules, may be "") + base_text (NeverSink,
    may be None) -> dir_/poe-checker.filter, overwritten unconditionally.
    Raises ValueError if both sources are empty — per the failure-mode table
    ("ทั้งคู่ไม่มี -> ไม่เขียนทับไฟล์เดิม"), the caller must not touch the
    existing file in that case, and this is the last line of defense against
    silently truncating it."""
    if not generated_section.strip() and not base_text:
        raise ValueError("nothing to write — both hub and base filter sources unavailable")
    dir_.mkdir(parents=True, exist_ok=True)
    body = generated_section
    if base_text:
        body += "\n# ===== base filter below =====\n" + base_text
    path = dir_ / _FILTER_NAME
    path.write_text(body, encoding="utf-8")
    return path


def copy_sounds(dir_: Path, sound_map: dict) -> dict:
    """sound_map: {"S"/"A"/"B": source_path_or_None}. Copies each assigned
    tier's sound to dir_/poe-checker-{tier}{ext} — fixed tier-prefixed names
    (not the original filename) so two tiers picking differently-named files
    never collide, and filter_gen's CustomAlertSound lines can reference a
    deterministic name. Returns {tier: written_filename} for tiers actually
    copied."""
    dir_.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}
    for tier, src in (sound_map or {}).items():
        if not src:
            continue
        src_path = Path(src)
        if not src_path.exists():
            log.warning("Filter sound for tier %s not found: %s", tier, src_path)
            continue
        dest_name = f"poe-checker-{tier}{src_path.suffix}"
        try:
            shutil.copyfile(src_path, dir_ / dest_name)
            written[tier] = dest_name
        except Exception as e:
            log.warning("Filter sound copy failed (tier %s): %s", tier, e)
    return written


def _state_path(config_dir: Path, game: str) -> Path:
    return config_dir / f"filter_state_{game}.json"


def load_state(config_dir: Path, game: str) -> dict:
    try:
        return json.loads(_state_path(config_dir, game).read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(config_dir: Path, game: str, **fields) -> None:
    state = load_state(config_dir, game)
    state.update(fields)
    try:
        _state_path(config_dir, game).write_text(json.dumps(state), encoding="utf-8")
    except Exception as e:
        log.warning("filter_state save failed (%s): %s", game, e)
