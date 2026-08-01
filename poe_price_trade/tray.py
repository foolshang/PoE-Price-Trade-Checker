"""System tray icon (pystray) — Discord-style minimize-to-tray, right-click
menu, best-effort balloon notification, and a "pending reload" badge.

All 4 constructor callbacks run on pystray's own background thread, never
the Tk thread — callers must wrap them in `root.after_idle(...)` themselves
(same cross-thread-into-Tk pattern used everywhere else in this codebase,
e.g. app.py's `_on_f4_scan`/`_load_prices_async`).

`start()` can fail (missing icon asset, no shell available, backend
unavailable, ...) — callers MUST check its return value and fall back to
plain-window behavior rather than assuming a tray icon exists. See
app.py's `self._tray_ok`.
"""
from __future__ import annotations
import logging
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

from PIL import Image, ImageDraw
import pystray

log = logging.getLogger(__name__)

_SETUP_TIMEOUT_S = 2.0
_BADGE_COLOR = (220, 60, 60, 255)


def _asset_path(name: str) -> Path:
    # PyInstaller's onefile datas= preserves the source-relative directory
    # ("poe_price_trade/assets/...") under _MEIPASS, unlike a source run
    # where this file already lives inside poe_price_trade/.
    base = Path(sys._MEIPASS) / "poe_price_trade" if getattr(sys, "frozen", False) \
        else Path(__file__).resolve().parent
    return base / "assets" / name


def _make_pending_image(base: Image.Image) -> Image.Image:
    img = base.copy()
    d = ImageDraw.Draw(img)
    w, h = img.size
    r = w * 0.22
    cx, cy = w - r * 0.9, h * 0.9
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=_BADGE_COLOR, outline=(20, 20, 20, 255), width=3)
    return img


class TrayIcon:
    def __init__(self, on_show: Callable[[], None], on_generate_now: Callable[[], None],
                 on_open_settings: Callable[[], None], on_quit: Callable[[], None]):
        self._on_show = on_show
        self._on_generate_now = on_generate_now
        self._on_open_settings = on_open_settings
        self._on_quit = on_quit
        self._icon: Optional[pystray.Icon] = None
        self._thread: Optional[threading.Thread] = None
        self._normal_image: Optional[Image.Image] = None
        self._pending_image: Optional[Image.Image] = None

    # ------------------------------------------------------------------

    def start(self) -> bool:
        """Builds and shows the tray icon, blocking (briefly) until it's
        confirmed ready or the setup timeout elapses. Returns False on any
        failure — never raises."""
        try:
            self._normal_image = Image.open(_asset_path("icon.ico"))
            self._pending_image = _make_pending_image(self._normal_image)
            menu = pystray.Menu(
                pystray.MenuItem("Show", lambda: self._on_show(), default=True),
                pystray.MenuItem("Generate Now", lambda: self._on_generate_now()),
                pystray.MenuItem("Settings", lambda: self._on_open_settings()),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", lambda: self._on_quit()),
            )
            self._icon = pystray.Icon("PoePriceTrade", self._normal_image,
                                      "PoE Price & Trade Checker", menu)
        except Exception as e:
            log.warning("Tray icon build failed: %s", e)
            self._icon = None
            return False

        ready = threading.Event()

        def _setup(icon: pystray.Icon) -> None:
            try:
                icon.visible = True
            finally:
                ready.set()

        def _run() -> None:
            try:
                self._icon.run(setup=_setup)
            except Exception as e:
                log.warning("Tray icon loop stopped unexpectedly: %s", e)

        self._thread = threading.Thread(target=_run, daemon=True, name="TrayIcon")
        self._thread.start()

        if not ready.wait(_SETUP_TIMEOUT_S):
            log.warning("Tray icon setup timed out after %.1fs", _SETUP_TIMEOUT_S)
            self.stop()
            return False
        return True

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception as e:
                log.warning("Tray icon stop failed: %s", e)
        if self._thread is not None:
            self._thread.join(timeout=_SETUP_TIMEOUT_S)

    # ------------------------------------------------------------------

    def set_pending(self, pending: bool) -> None:
        if self._icon is None:
            return
        try:
            self._icon.icon = self._pending_image if pending else self._normal_image
        except Exception as e:
            log.warning("Tray icon badge update failed: %s", e)

    def notify(self, title: str, message: str) -> None:
        """Best-effort balloon — known unreliable while a fullscreen game
        has focus (Windows suppresses it under Focus Assist), so this is a
        secondary channel only. Never raises."""
        if self._icon is None or not pystray.Icon.HAS_NOTIFICATION:
            return
        try:
            self._icon.notify(message, title)
        except Exception as e:
            log.warning("Tray notify failed: %s", e)
