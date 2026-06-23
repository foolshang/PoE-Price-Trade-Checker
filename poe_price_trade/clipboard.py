"""Read text from Windows clipboard (ctypes, no deps)."""
from __future__ import annotations
import ctypes
import ctypes.wintypes
import logging
from typing import Optional

log = logging.getLogger(__name__)

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


def read_text() -> Optional[str]:
    """Return clipboard text content, or None if clipboard is empty/non-text."""
    try:
        if not ctypes.windll.user32.OpenClipboard(None):
            return None
        try:
            handle = ctypes.windll.user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return None
            ptr = ctypes.windll.kernel32.GlobalLock(handle)
            if not ptr:
                return None
            try:
                text = ctypes.wstring_at(ptr)
                return text
            finally:
                ctypes.windll.kernel32.GlobalUnlock(handle)
        finally:
            ctypes.windll.user32.CloseClipboard()
    except Exception as e:
        log.warning("Clipboard read error: %s", e)
        return None


def write_text(text: str) -> bool:
    """Write text to Windows clipboard. Returns True on success."""
    try:
        encoded = (text + "\0").encode("utf-16-le")
        size = len(encoded)
        h_mem = ctypes.windll.kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
        if not h_mem:
            return False
        ptr = ctypes.windll.kernel32.GlobalLock(h_mem)
        if not ptr:
            ctypes.windll.kernel32.GlobalFree(h_mem)
            return False
        ctypes.memmove(ptr, encoded, size)
        ctypes.windll.kernel32.GlobalUnlock(h_mem)

        if not ctypes.windll.user32.OpenClipboard(None):
            ctypes.windll.kernel32.GlobalFree(h_mem)
            return False
        try:
            ctypes.windll.user32.EmptyClipboard()
            ctypes.windll.user32.SetClipboardData(CF_UNICODETEXT, h_mem)
            return True
        finally:
            ctypes.windll.user32.CloseClipboard()
    except Exception as e:
        log.warning("Clipboard write error: %s", e)
        return False
