"""Application settings — persisted as JSON in %LOCALAPPDATA%\\PoePriceTrade\\config.json.
POESESSID is stored separately with Windows DPAPI (ctypes, no extra deps)."""
from __future__ import annotations
import ctypes
import ctypes.wintypes
import json
import logging
import os
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_APP_DIR_NAME = "PoePriceTrade"
_CONFIG_FILE = "config.json"
_SESSION_FILE = "session.dpapi"

_DEFAULTS: dict = {
    "game_version": "poe2",
    "league": "",
    "currency_unit": "divine",
    "overlay_opacity": 0.85,
    "price_offset_px": 2,
    "hotkey_scan": "F9",
    "hotkey_currency": "F6",
    "hotkey_trade": "F5",
    "hotkey_settings": "F8",
    "hotkey_quit": "Ctrl+Alt+Q",
    "match_threshold": 0.80,
    "log_level": "INFO",
}


# ---------------------------------------------------------------------------
# DPAPI helpers
# ---------------------------------------------------------------------------

class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi_encrypt(plaintext: str) -> bytes:
    data = plaintext.encode("utf-8")
    inp = _DataBlob(len(data), ctypes.cast(ctypes.c_char_p(data), ctypes.POINTER(ctypes.c_ubyte)))
    out = _DataBlob()
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(inp), None, None, None, None, 0, ctypes.byref(out)
    )
    if not ok:
        raise RuntimeError(f"DPAPI encrypt error: {ctypes.GetLastError()}")
    result = bytes(ctypes.string_at(out.pbData, out.cbData))
    ctypes.windll.kernel32.LocalFree(out.pbData)
    return result


def _dpapi_decrypt(ciphertext: bytes) -> str:
    inp = _DataBlob(len(ciphertext), ctypes.cast(ctypes.c_char_p(ciphertext), ctypes.POINTER(ctypes.c_ubyte)))
    out = _DataBlob()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(inp), None, None, None, None, 0, ctypes.byref(out)
    )
    if not ok:
        raise RuntimeError(f"DPAPI decrypt error: {ctypes.GetLastError()}")
    result = ctypes.string_at(out.pbData, out.cbData).decode("utf-8")
    ctypes.windll.kernel32.LocalFree(out.pbData)
    return result


# ---------------------------------------------------------------------------
# AppConfig
# ---------------------------------------------------------------------------

class AppConfig:
    def __init__(self):
        self._data: dict = dict(_DEFAULTS)
        self._dir: Path = self._resolve_dir()
        self.load()

    @staticmethod
    def _resolve_dir() -> Path:
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        p = Path(base) / _APP_DIR_NAME
        p.mkdir(parents=True, exist_ok=True)
        return p

    def app_dir(self) -> Path:
        return self._dir

    def load(self) -> None:
        path = self._dir / _CONFIG_FILE
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    saved = json.load(f)
                # Merge: only accept known keys
                for k in _DEFAULTS:
                    if k in saved:
                        self._data[k] = saved[k]
            except Exception as e:
                log.warning("Config load failed: %s", e)

    def save(self) -> None:
        path = self._dir / _CONFIG_FILE
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.warning("Config save failed: %s", e)

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value) -> None:
        self._data[key] = value

    # ------------------------------------------------------------------
    # POESESSID (DPAPI-protected)
    # ------------------------------------------------------------------

    def save_session_id(self, session_id: str) -> None:
        if not session_id:
            self._clear_session_file()
            return
        try:
            encrypted = _dpapi_encrypt(session_id)
            path = self._dir / _SESSION_FILE
            with open(path, "wb") as f:
                f.write(encrypted)
            log.debug("POESESSID saved (encrypted)")
        except Exception as e:
            log.error("Failed to save POESESSID: %s", e)
            raise

    def load_session_id(self) -> Optional[str]:
        path = self._dir / _SESSION_FILE
        if not path.exists():
            return None
        try:
            with open(path, "rb") as f:
                ciphertext = f.read()
            return _dpapi_decrypt(ciphertext)
        except Exception as e:
            log.warning("Failed to load POESESSID: %s", e)
            return None

    def clear_session_id(self) -> None:
        self._clear_session_file()
        log.info("POESESSID cleared")

    def _clear_session_file(self) -> None:
        path = self._dir / _SESSION_FILE
        if path.exists():
            path.unlink()

    def has_session_id(self) -> bool:
        return (self._dir / _SESSION_FILE).exists()
