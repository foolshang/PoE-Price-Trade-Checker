"""Settings window (F8)."""
from __future__ import annotations
import logging
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from .config import AppConfig

log = logging.getLogger(__name__)

_BG = "#1C1C1C"
_FG = "#E8D5A0"
_ACCENT = "#C8A050"
_INPUT_BG = "#2A2A2A"
_BUTTON_BG = "#3A3020"
_PANEL_FONT = ("Segoe UI", 9)
_HEADER_FONT = ("Segoe UI", 10, "bold")
_SMALL_FONT = ("Segoe UI", 8)


class SettingsWindow:
    def __init__(self, parent: tk.Misc, config: AppConfig,
                 on_apply: Optional[Callable[[], None]] = None,
                 on_fetch_leagues: Optional[Callable[[str], list[str]]] = None):
        self._config = config
        self._on_apply = on_apply
        self._on_fetch_leagues = on_fetch_leagues

        self._win = tk.Toplevel(parent)
        self._win.title("PoE Price & Trade Checker — Settings")
        self._win.configure(bg=_BG)
        self._win.resizable(False, False)
        self._win.grab_set()
        self._win.protocol("WM_DELETE_WINDOW", self._win.destroy)

        self._vars: dict[str, tk.Variable] = {}
        self._build()
        self._load_from_config()

    # ------------------------------------------------------------------

    def _lbl(self, parent, text, row, col, **kw):
        tk.Label(parent, text=text, bg=_BG, fg=_FG, font=_PANEL_FONT, **kw).grid(
            row=row, column=col, sticky="w", padx=6, pady=3)

    def _entry(self, parent, key: str, row, col, width=24):
        var = tk.StringVar()
        self._vars[key] = var
        e = tk.Entry(parent, textvariable=var, bg=_INPUT_BG, fg=_FG, insertbackground=_FG,
                     relief=tk.FLAT, font=_PANEL_FONT, width=width)
        e.grid(row=row, column=col, sticky="w", padx=6, pady=3)
        return e

    def _combo(self, parent, key: str, values: list[str], row, col, width=22):
        var = tk.StringVar()
        self._vars[key] = var
        cb = ttk.Combobox(parent, textvariable=var, values=values, width=width,
                          state="readonly", font=_PANEL_FONT)
        cb.grid(row=row, column=col, sticky="w", padx=6, pady=3)
        return cb

    def _check(self, parent, key: str, text: str, row, col):
        var = tk.BooleanVar()
        self._vars[key] = var
        tk.Checkbutton(parent, text=text, variable=var,
                       bg=_BG, fg=_FG, selectcolor="#2A2020", activebackground=_BG,
                       font=_PANEL_FONT).grid(row=row, column=col, sticky="w", padx=6, pady=3)
        return var

    def _scale(self, parent, key: str, row, col, from_=0.1, to=1.0, resolution=0.05):
        var = tk.DoubleVar()
        self._vars[key] = var
        sc = tk.Scale(parent, variable=var, from_=from_, to=to, resolution=resolution,
                      orient=tk.HORIZONTAL, bg=_BG, fg=_FG, activebackground=_ACCENT,
                      troughcolor=_INPUT_BG, highlightthickness=0, length=160)
        sc.grid(row=row, column=col, sticky="w", padx=6, pady=3)
        return sc

    def _section(self, notebook, title):
        frame = tk.Frame(notebook, bg=_BG, padx=8, pady=8)
        notebook.add(frame, text=title)
        return frame

    # ------------------------------------------------------------------

    def _build(self) -> None:
        nb = ttk.Notebook(self._win)
        nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self._build_game_tab(self._section(nb, "Game"))
        self._build_hotkeys_tab(self._section(nb, "Hotkeys"))
        self._build_advanced_tab(self._section(nb, "Advanced"))

        btn_frame = tk.Frame(self._win, bg=_BG)
        btn_frame.pack(fill=tk.X, padx=8, pady=(0, 8))

        def btn(text, cmd, side=tk.RIGHT):
            b = tk.Button(btn_frame, text=text, command=cmd, bg=_BUTTON_BG, fg=_FG,
                          activebackground=_ACCENT, activeforeground="#000",
                          relief=tk.FLAT, font=_PANEL_FONT, padx=10, pady=4)
            b.pack(side=side, padx=4)
            return b

        btn("Apply & Close", self._apply)
        btn("Cancel", self._win.destroy)

    def _build_game_tab(self, f: tk.Frame) -> None:
        self._lbl(f, "Game Version:", 0, 0)
        self._combo(f, "game_version", ["poe2", "poe1"], 0, 1, width=10)

        self._check(f, "auto_league", "Auto-detect league on startup", 1, 0)
        self._check(f, "prefer_hardcore", "Prefer Hardcore league (HC)", 2, 0)

        tk.Label(f, text="(League is selected in the main window)", bg=_BG, fg="#666",
                 font=_SMALL_FONT).grid(row=3, column=0, columnspan=3, sticky="w", padx=6, pady=2)

        self._lbl(f, "Overlay Opacity:", 4, 0)
        self._scale(f, "overlay_opacity", 4, 1)

        self._lbl(f, "Price X-offset (px):", 5, 0)
        self._entry(f, "price_offset_px", 5, 1, width=6)

    def _build_hotkeys_tab(self, f: tk.Frame) -> None:
        specs = [
            ("hotkey_scan",     "Scan Prices (F4):"),
            ("hotkey_trade",    "Trade Browser (F5):"),
            ("hotkey_clear",    "Clear Overlay (Esc):"),
            ("hotkey_settings", "Settings:"),
            ("hotkey_quit",     "Quit:"),
        ]
        for row, (key, label) in enumerate(specs):
            self._lbl(f, label, row, 0)
            self._entry(f, key, row, 1, width=16)

        tk.Label(f, text="Format: F4  or  Ctrl+Alt+Q  etc.",
                 bg=_BG, fg="#888", font=_SMALL_FONT).grid(
            row=len(specs), column=0, columnspan=3, sticky="w", padx=6, pady=(8, 0))

    def _build_advanced_tab(self, f: tk.Frame) -> None:
        self._lbl(f, "Log Level:", 0, 0)
        self._combo(f, "log_level", ["DEBUG", "INFO", "WARNING", "ERROR"], 0, 1, width=10)

        self._lbl(f, "Match Threshold:", 1, 0)
        self._entry(f, "match_threshold", 1, 1, width=6)
        tk.Label(f, text="(0.0–1.0, higher = stricter)", bg=_BG, fg="#888",
                 font=_SMALL_FONT).grid(row=1, column=2, sticky="w", padx=4)

    # ------------------------------------------------------------------

    def _load_from_config(self) -> None:
        str_keys = ("game_version", "hotkey_scan", "hotkey_trade", "hotkey_clear",
                    "hotkey_settings", "hotkey_quit", "log_level", "match_threshold",
                    "price_offset_px")
        for key in str_keys:
            if key in self._vars:
                self._vars[key].set(self._config.get(key, ""))
        if "overlay_opacity" in self._vars:
            self._vars["overlay_opacity"].set(self._config.get("overlay_opacity", 0.85))
        if "auto_league" in self._vars:
            self._vars["auto_league"].set(bool(self._config.get("auto_league", True)))
        if "prefer_hardcore" in self._vars:
            self._vars["prefer_hardcore"].set(bool(self._config.get("prefer_hardcore", False)))

    def _apply(self) -> None:
        for key in ("game_version", "hotkey_scan", "hotkey_trade", "hotkey_clear",
                    "hotkey_settings", "hotkey_quit", "log_level"):
            if key in self._vars:
                self._config.set(key, self._vars[key].get())

        if "auto_league" in self._vars:
            self._config.set("auto_league", bool(self._vars["auto_league"].get()))
        if "prefer_hardcore" in self._vars:
            self._config.set("prefer_hardcore", bool(self._vars["prefer_hardcore"].get()))

        try:
            self._config.set("overlay_opacity", float(self._vars["overlay_opacity"].get()))
        except (ValueError, KeyError):
            pass
        try:
            self._config.set("price_offset_px", int(self._vars["price_offset_px"].get()))
        except (ValueError, KeyError):
            pass
        try:
            self._config.set("match_threshold", float(self._vars["match_threshold"].get()))
        except (ValueError, KeyError):
            pass

        self._config.save()
        if self._on_apply:
            self._on_apply()
        self._win.destroy()
