"""Standalone PoE1 & PoE2 Filter Generator.

Reuses filter_service.generate_filter + FilterGenWindow. No checker, no
auto-regen, no hotkeys/tray — just the generator window with a game toggle."""
from __future__ import annotations
import logging
import os
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import __version__, filter_service, hub_client
from .config import AppConfig
from .filter_window import FilterGenWindow, _BG, _FG, _PANEL_FONT

_APP_DIR_NAME = "PoeFilterGen"     # config dir separate from the checker's PoePriceTrade


def _icon_path() -> Optional[Path]:
    """poe_price_trade/assets/icon.ico — a PyInstaller onefile bundle keeps
    `datas` under their source-relative path (poe_price_trade/assets/...), so
    the frozen lookup has the package prefix a plain source run doesn't."""
    here = Path(__file__).resolve().parent / "assets" / "icon.ico"
    if getattr(sys, "frozen", False):
        frozen = Path(getattr(sys, "_MEIPASS", "")) / "poe_price_trade" / "assets" / "icon.ico"
        return frozen if frozen.exists() else (here if here.exists() else None)
    return here if here.exists() else None


class FilterGenStandaloneApp:
    def __init__(self):
        try:
            from .capture import set_dpi_aware
            set_dpi_aware()
        except Exception:
            pass
        self._root = tk.Tk()
        self._root.title(f"PoE1 & PoE2 Filter Generator v{__version__}")
        self._root.configure(bg=_BG)
        self._root.resizable(False, False)
        self._config = AppConfig(_APP_DIR_NAME)      # separate from the checker
        icon = _icon_path()
        if icon:
            try:
                self._root.iconbitmap(str(icon))
            except Exception:
                icon = None

        fg = dict(self._config.get("filter_gen", {}) or {})
        start = fg.get("standalone_game")
        self._game = tk.StringVar(value=start if start in ("poe1", "poe2") else "poe2")
        top = tk.Frame(self._root, bg=_BG)
        top.pack(fill=tk.X, padx=8, pady=(8, 2))
        tk.Label(top, text="เกม:", bg=_BG, fg=_FG, font=_PANEL_FONT).pack(side=tk.LEFT)
        for g, lbl in (("poe1", "PoE1"), ("poe2", "PoE2")):
            tk.Radiobutton(top, text=lbl, variable=self._game, value=g,
                           command=self._switch_game, bg=_BG, fg=_FG,
                           selectcolor="#2A2020", activebackground=_BG,
                           font=_PANEL_FONT).pack(side=tk.LEFT, padx=4)

        self._body = tk.Frame(self._root, bg=_BG)
        self._body.pack(fill=tk.BOTH, expand=True)
        self._fgw: Optional[FilterGenWindow] = None
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_game()
        # version marker (visible proof of which build is running) + where config lives
        self._fgw.log(f"PoE Filter Generator v{__version__} — config: {self._config.app_dir()}", "info")
        self._write_run_marker(icon)

    def _write_run_marker(self, icon: Optional[Path]) -> None:
        try:
            (self._config.app_dir() / "last_run.txt").write_text(
                f"v{__version__}\n{datetime.now().isoformat()}\n"
                f"frozen={bool(getattr(sys, 'frozen', False))}\nicon={icon}\n", encoding="utf-8")
        except Exception:
            pass

    def _league_path(self, gv: str) -> str:
        return f"{gv}/prices/latest.json"        # main league only (dropdown can come later)

    def _build_game(self) -> None:
        gv = self._game.get()
        self._fgw = FilterGenWindow(
            self._body, self._config, gv,
            on_generate=self._on_generate,
            hub_loader=lambda: hub_client.get_prices(self._league_path(gv)),
            as_toplevel=False, show_auto_regen=False)

    def _remember_game(self) -> None:
        fg = dict(self._config.get("filter_gen", {}) or {})
        fg["standalone_game"] = self._game.get()
        self._config.set("filter_gen", fg)
        self._config.save()

    def _switch_game(self) -> None:
        if self._fgw:
            try:
                self._fgw._save()          # persist the current game before switching
            except Exception:
                pass
        self._remember_game()
        for w in self._body.winfo_children():
            w.destroy()
        self._build_game()

    def _on_close(self) -> None:
        if self._fgw:
            try:
                self._fgw._save()
            except Exception:
                pass
        self._remember_game()
        self._root.destroy()

    def _on_generate(self, refresh: bool) -> None:
        # FilterGenWindow._on_generate_clicked already called _save() -> config is fresh
        gv = self._game.get()
        cfg = self._config
        fgw = self._fgw
        path = self._league_path(gv)

        def log(msg, tag="info"):
            self._root.after_idle(lambda m=msg, t=tag: fgw.log(m, t))

        def worker():
            try:
                filter_service.generate_filter(cfg, gv, path, force_base=refresh,
                                               league="", log=log)
            except Exception as e:
                self._root.after_idle(lambda err=e: fgw.log(f"✗ generate ล้มเหลว: {err}", "err"))

        threading.Thread(target=worker, daemon=True, name="StandaloneGen").start()

    def run(self) -> None:
        self._root.mainloop()


def _setup_logging() -> None:
    """A windowed exe has no console: if logging falls through to its
    lastResort handler it writes to a stderr whose fd is unusable ([Errno 9]).
    Give the root logger a real FileHandler (no StreamHandler — useless without
    a console) and park the dead std streams on devnull as insurance."""
    try:
        log_dir = Path(os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))) / _APP_DIR_NAME
        log_dir.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            handlers=[logging.FileHandler(log_dir / "log.txt", mode="w", encoding="utf-8")])
    except Exception:
        logging.getLogger().addHandler(logging.NullHandler())
    try:
        sys.stdout = sys.stderr = open(os.devnull, "w", encoding="utf-8")
    except Exception:
        pass
    logging.getLogger(__name__).info("PoE Filter Generator v%s started (frozen=%s)",
                                     __version__, bool(getattr(sys, "frozen", False)))


def main() -> None:
    _setup_logging()
    FilterGenStandaloneApp().run()

if __name__ == "__main__":
    main()
