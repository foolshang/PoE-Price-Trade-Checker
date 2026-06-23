"""Global hotkey manager using RegisterHotKey (ctypes).
All hotkeys are registered in a dedicated background thread that owns the message queue.
Callbacks are scheduled onto the main tkinter thread via root.after_idle()."""
from __future__ import annotations
import ctypes
import ctypes.wintypes
import logging
import threading
from typing import Callable, Optional

log = logging.getLogger(__name__)

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

MOD_NONE = 0x0000
MOD_ALT = 0x0001
MOD_CTRL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

# Virtual key codes
VK = {
    "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73,
    "F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77,
    "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
}


def _parse_hotkey(spec: str) -> tuple[int, int]:
    """Parse 'Ctrl+Alt+Q' → (MOD_CTRL | MOD_ALT, ord('Q'))."""
    parts = [p.strip() for p in spec.split("+")]
    mods = MOD_NONE
    key = ""
    for p in parts:
        pl = p.lower()
        if pl in ("ctrl", "control"):
            mods |= MOD_CTRL
        elif pl in ("alt",):
            mods |= MOD_ALT
        elif pl in ("shift",):
            mods |= MOD_SHIFT
        elif pl in ("win",):
            mods |= MOD_WIN
        else:
            key = p
    if not key:
        raise ValueError(f"No key in hotkey spec: {spec!r}")
    if key.upper() in VK:
        vk = VK[key.upper()]
    elif len(key) == 1:
        vk = ctypes.windll.user32.VkKeyScanW(ord(key)) & 0xFF
    else:
        raise ValueError(f"Unknown key: {key!r} in {spec!r}")
    return mods, vk


class HotkeyManager(threading.Thread):
    """Background thread: registers hotkeys, pumps WM_HOTKEY, dispatches callbacks."""

    def __init__(self, tk_root=None):
        super().__init__(daemon=True, name="HotkeyThread")
        self._tk_root = tk_root
        self._pending: list[tuple[int, int, int, Callable]] = []
        self._next_id = 1
        self._thread_id: Optional[int] = None
        self._ready = threading.Event()

    def add(self, spec: str, callback: Callable) -> int:
        """Queue a hotkey registration. Must be called before start()."""
        mods, vk = _parse_hotkey(spec)
        hid = self._next_id
        self._next_id += 1
        self._pending.append((hid, mods, vk, callback))
        return hid

    def run(self) -> None:
        user32 = ctypes.windll.user32
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()

        # Force thread message queue creation
        msg = ctypes.wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)

        handlers: dict[int, Callable] = {}
        for hid, mods, vk, cb in self._pending:
            if user32.RegisterHotKey(None, hid, mods, vk):
                handlers[hid] = cb
                log.debug("Registered hotkey id=%d mods=0x%x vk=0x%x", hid, mods, vk)
            else:
                err = ctypes.GetLastError()
                log.warning("RegisterHotKey failed id=%d err=%d (key may be in use)", hid, err)

        self._ready.set()

        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY:
                cb = handlers.get(msg.wParam)
                if cb:
                    self._dispatch(cb)

        # Cleanup
        for hid in handlers:
            user32.UnregisterHotKey(None, hid)

    def _dispatch(self, callback: Callable) -> None:
        if self._tk_root is not None:
            try:
                self._tk_root.after_idle(callback)
            except Exception as e:
                log.warning("after_idle dispatch failed: %s", e)
        else:
            try:
                callback()
            except Exception as e:
                log.warning("Hotkey callback error: %s", e)

    def stop(self) -> None:
        if self._thread_id is not None:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)

    def wait_ready(self, timeout: float = 2.0) -> bool:
        return self._ready.wait(timeout)
