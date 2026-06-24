"""Read text from Windows clipboard (ctypes, no deps)."""
from __future__ import annotations
import ctypes
import ctypes.wintypes
import logging
from typing import Optional

log = logging.getLogger(__name__)

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

# 64-bit Windows: all HGLOBAL / pointer args must be c_void_p or they overflow
_k32 = ctypes.windll.kernel32
_u32 = ctypes.windll.user32
_VP  = ctypes.c_void_p

_k32.GlobalAlloc.restype   = _VP
_k32.GlobalAlloc.argtypes  = [ctypes.c_uint, ctypes.c_size_t]
_k32.GlobalLock.restype    = _VP
_k32.GlobalLock.argtypes   = [_VP]
_k32.GlobalUnlock.restype  = ctypes.c_bool
_k32.GlobalUnlock.argtypes = [_VP]
_k32.GlobalFree.restype    = _VP
_k32.GlobalFree.argtypes   = [_VP]
_u32.GetClipboardData.restype  = _VP
_u32.GetClipboardData.argtypes = [ctypes.c_uint]
_u32.SetClipboardData.restype  = _VP
_u32.SetClipboardData.argtypes = [ctypes.c_uint, _VP]


def read_text() -> Optional[str]:
    """Return clipboard text content, or None if clipboard is empty/non-text."""
    try:
        if not _u32.OpenClipboard(None):
            return None
        try:
            handle = _u32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return None
            ptr = _k32.GlobalLock(handle)
            if not ptr:
                return None
            try:
                return ctypes.wstring_at(ptr)
            finally:
                _k32.GlobalUnlock(handle)
        finally:
            _u32.CloseClipboard()
    except Exception as e:
        log.warning("Clipboard read error: %s", e)
        return None


def write_text(text: str) -> bool:
    """Write text to Windows clipboard. Returns True on success."""
    try:
        encoded = (text + "\0").encode("utf-16-le")
        h_mem = _k32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
        if not h_mem:
            return False
        ptr = _k32.GlobalLock(h_mem)
        if not ptr:
            _k32.GlobalFree(h_mem)
            return False
        ctypes.memmove(ptr, encoded, len(encoded))
        _k32.GlobalUnlock(h_mem)

        if not _u32.OpenClipboard(None):
            _k32.GlobalFree(h_mem)
            return False
        try:
            _u32.EmptyClipboard()
            _u32.SetClipboardData(CF_UNICODETEXT, h_mem)
            return True
        finally:
            _u32.CloseClipboard()
    except Exception as e:
        log.warning("Clipboard write error: %s", e)
        return False
