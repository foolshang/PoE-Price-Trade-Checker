"""Settings window (F8). Allows changing game version, league, currency,
opacity, hotkeys, and POESESSID."""
from __future__ import annotations
import logging
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Optional

from .config import AppConfig
from .profiles import PROFILES, GameProfile

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

    def _entry(self, parent, key: str, row, col, width=24, show=""):
        var = tk.StringVar()
        self._vars[key] = var
        e = tk.Entry(parent, textvariable=var, bg=_INPUT_BG, fg=_FG, insertbackground=_FG,
                     relief=tk.FLAT, font=_PANEL_FONT, width=width, show=show)
        e.grid(row=row, column=col, sticky="w", padx=6, pady=3)
        return e

    def _combo(self, parent, key: str, values: list[str], row, col, width=22):
        var = tk.StringVar()
        self._vars[key] = var
        cb = ttk.Combobox(parent, textvariable=var, values=values, width=width,
                          state="readonly", font=_PANEL_FONT)
        cb.grid(row=row, column=col, sticky="w", padx=6, pady=3)
        return cb

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
        self._build_session_tab(self._section(nb, "Trade Auth"))
        self._build_advanced_tab(self._section(nb, "Advanced"))

        # Bottom buttons
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
        gv_cb = self._combo(f, "game_version", ["poe2", "poe1"], 0, 1, width=10)
        gv_cb.bind("<<ComboboxSelected>>", self._on_game_version_changed)

        self._lbl(f, "League:", 1, 0)
        self._league_combo = self._combo(f, "league", [], 1, 1, width=22)

        tk.Button(f, text="Refresh Leagues", command=self._fetch_leagues,
                  bg=_BUTTON_BG, fg=_FG, activebackground=_ACCENT,
                  relief=tk.FLAT, font=_SMALL_FONT).grid(row=1, column=2, padx=4)

        self._lbl(f, "Currency Unit:", 2, 0)
        self._combo(f, "currency_unit", ["divine", "chaos", "exalted"], 2, 1, width=10)

        self._lbl(f, "Overlay Opacity:", 3, 0)
        self._scale(f, "overlay_opacity", 3, 1)

        self._lbl(f, "Price X-offset (px):", 4, 0)
        self._entry(f, "price_offset_px", 4, 1, width=6)

    def _build_hotkeys_tab(self, f: tk.Frame) -> None:
        specs = [
            ("hotkey_scan",     "Scan Prices (Mode A):"),
            ("hotkey_currency", "Cycle Currency:"),
            ("hotkey_trade",    "Check Trade (Mode B):"),
            ("hotkey_settings", "Settings:"),
            ("hotkey_quit",     "Quit:"),
        ]
        for row, (key, label) in enumerate(specs):
            self._lbl(f, label, row, 0)
            self._entry(f, key, row, 1, width=16)

        tk.Label(f, text="Format: F9  or  Ctrl+Alt+Q  etc.",
                 bg=_BG, fg="#888", font=_SMALL_FONT).grid(
            row=len(specs), column=0, columnspan=3, sticky="w", padx=6, pady=(8, 0))

    def _build_session_tab(self, f: tk.Frame) -> None:
        tk.Label(f, text="POESESSID (from pathofexile.com cookies):",
                 bg=_BG, fg=_FG, font=_PANEL_FONT).grid(row=0, column=0, columnspan=2, sticky="w", padx=6, pady=(6, 2))

        var = tk.StringVar()
        self._vars["poesessid"] = var
        self._sess_entry = tk.Entry(f, textvariable=var, bg=_INPUT_BG, fg=_FG, insertbackground=_FG,
                                    relief=tk.FLAT, font=_PANEL_FONT, width=48, show="●")
        self._sess_entry.grid(row=1, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 4))

        def toggle_show():
            current = self._sess_entry.cget("show")
            self._sess_entry.configure(show="" if current else "●")
        tk.Button(f, text="Show/Hide", command=toggle_show,
                  bg=_BUTTON_BG, fg=_FG, activebackground=_ACCENT,
                  relief=tk.FLAT, font=_SMALL_FONT).grid(row=1, column=2, padx=4)

        tk.Button(f, text="Clear Session", command=self._clear_session,
                  bg="#4A1010", fg=_FG, activebackground="#7A2020",
                  relief=tk.FLAT, font=_PANEL_FONT, padx=8, pady=3).grid(
            row=2, column=0, sticky="w", padx=6, pady=8)

        self._session_status = tk.Label(f, text="", bg=_BG, fg="#888", font=_SMALL_FONT)
        self._session_status.grid(row=2, column=1, sticky="w", padx=6)

        tk.Label(f, text="Note: POESESSID is encrypted with Windows DPAPI\n(accessible only on this machine by your user account).",
                 bg=_BG, fg="#666", font=_SMALL_FONT).grid(
            row=3, column=0, columnspan=3, sticky="w", padx=6, pady=(8, 0))

    def _build_advanced_tab(self, f: tk.Frame) -> None:
        self._lbl(f, "Log Level:", 0, 0)
        self._combo(f, "log_level", ["DEBUG", "INFO", "WARNING", "ERROR"], 0, 1, width=10)

        self._lbl(f, "Match Threshold:", 1, 0)
        self._entry(f, "match_threshold", 1, 1, width=6)
        tk.Label(f, text="(0.0–1.0, higher = stricter)", bg=_BG, fg="#888", font=_SMALL_FONT).grid(
            row=1, column=2, sticky="w", padx=4)

    # ------------------------------------------------------------------

    def _load_from_config(self) -> None:
        for key in ("game_version", "league", "currency_unit", "overlay_opacity",
                    "price_offset_px", "hotkey_scan", "hotkey_currency",
                    "hotkey_trade", "hotkey_settings", "hotkey_quit",
                    "log_level", "match_threshold"):
            if key in self._vars:
                self._vars[key].set(self._config.get(key, ""))

        # POESESSID: show placeholder if saved
        if self._config.has_session_id():
            self._vars["poesessid"].set("")
            self._session_status.configure(text="Session saved (leave blank to keep)")

        # Populate league list
        self._refresh_league_list()

    def _refresh_league_list(self) -> None:
        gv = self._vars.get("game_version")
        profile = PROFILES.get(gv.get() if gv else "poe2", PROFILES["poe2"])
        leagues = profile.default_leagues
        self._league_combo.configure(values=leagues)
        current = self._config.get("league", "")
        if current in leagues:
            self._vars["league"].set(current)
        elif leagues:
            self._vars["league"].set(leagues[0])

    def _on_game_version_changed(self, _event=None) -> None:
        self._refresh_league_list()

    def _fetch_leagues(self) -> None:
        if self._on_fetch_leagues:
            gv = self._vars["game_version"].get()
            try:
                leagues = self._on_fetch_leagues(gv)
                if leagues:
                    self._league_combo.configure(values=leagues)
                    self._vars["league"].set(leagues[0])
            except Exception as e:
                messagebox.showerror("Error", f"Could not fetch leagues:\n{e}", parent=self._win)

    def _clear_session(self) -> None:
        if messagebox.askyesno("Clear Session", "Clear saved POESESSID?", parent=self._win):
            self._config.clear_session_id()
            self._vars["poesessid"].set("")
            self._session_status.configure(text="Session cleared")

    def _apply(self) -> None:
        for key in ("game_version", "league", "currency_unit", "hotkey_scan",
                    "hotkey_currency", "hotkey_trade", "hotkey_settings",
                    "hotkey_quit", "log_level"):
            if key in self._vars:
                self._config.set(key, self._vars[key].get())

        try:
            self._config.set("overlay_opacity", float(self._vars["overlay_opacity"].get()))
        except ValueError:
            pass
        try:
            self._config.set("price_offset_px", int(self._vars["price_offset_px"].get()))
        except ValueError:
            pass
        try:
            self._config.set("match_threshold", float(self._vars["match_threshold"].get()))
        except ValueError:
            pass

        # POESESSID: only save if user typed something
        sess = self._vars.get("poesessid", tk.StringVar()).get().strip()
        if sess:
            try:
                self._config.save_session_id(sess)
                log.info("POESESSID saved")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save POESESSID:\n{e}", parent=self._win)

        self._config.save()
        if self._on_apply:
            self._on_apply()
        self._win.destroy()
