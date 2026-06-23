"""Main application: ties together overlay, hotkeys, repository, scan, and trade."""
from __future__ import annotations
import logging
import threading
import tkinter as tk
from tkinter import messagebox
from typing import Optional

from .capture import get_dpi_scale, set_dpi_aware
from .clipboard import read_text
from .config import AppConfig
from .hotkeys import HotkeyManager
from .item_parser import parse_item
from .models import ScanResult, TradeListing
from .overlay import PriceOverlay
from .profiles import PROFILES
from .repository import PriceRepository
from .scan import Scanner
from .settings import SettingsWindow
from .trade_client import SessionExpiredError, TradeClient
from .trade_panel import TradePanel
from .trade_search import build_query
from .mod_db import ModDatabase

log = logging.getLogger(__name__)

_STATUS_READY = "✓ Ready — {count} prices"
_STATUS_LOADING = "⟳ Loading prices…"
_STATUS_ERROR = "✗ Error: {msg}"


class App:
    def __init__(self):
        set_dpi_aware()
        self._config = AppConfig()
        self._setup_logging()

        self._root = tk.Tk()
        self._root.title("PoE Price & Trade Checker")
        self._root.configure(bg="#1C1C1C")
        self._root.resizable(False, False)
        self._root.protocol("WM_DELETE_WINDOW", self._quit)

        self._dpi_scale = get_dpi_scale()
        log.debug("DPI scale: %.2f", self._dpi_scale)

        self._profile = PROFILES.get(self._config.get("game_version", "poe2"), PROFILES["poe2"])
        self._repo = PriceRepository(self._profile, cache_dir=self._config.app_dir() / "cache")
        self._scanner: Optional[Scanner] = None
        self._last_scan_results: list[ScanResult] = []

        self._trade_client = TradeClient(self._profile, self._config.load_session_id())
        self._mod_db = ModDatabase(self._profile, cache_dir=self._config.app_dir() / "cache")

        self._overlay: Optional[PriceOverlay] = None
        self._trade_panel: Optional[TradePanel] = None
        self._hotkeys: Optional[HotkeyManager] = None

        self._build_ui()
        self._build_overlay()
        self._build_trade_panel()
        self._start_hotkeys()
        self._load_prices_async()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        BG, FG, ACC = "#1C1C1C", "#E8D5A0", "#C8A050"
        FONT = ("Segoe UI", 9)
        FONT_BOLD = ("Segoe UI", 9, "bold")
        FONT_SMALL = ("Segoe UI", 8)

        frame = tk.Frame(self._root, bg=BG, padx=12, pady=8)
        frame.pack()

        tk.Label(frame, text="PoE Price & Trade Checker", bg=BG, fg=ACC, font=("Segoe UI", 11, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(0, 6))

        self._gv_var = tk.StringVar(value=self._config.get("game_version", "poe2"))
        gv_frame = tk.Frame(frame, bg=BG)
        gv_frame.grid(row=1, column=0, columnspan=2, sticky="w")
        for gv, label in (("poe1", "PoE 1"), ("poe2", "PoE 2")):
            tk.Radiobutton(gv_frame, text=label, variable=self._gv_var, value=gv,
                           bg=BG, fg=FG, selectcolor="#2A2020", activebackground=BG,
                           command=self._on_game_version_changed, font=FONT).pack(side=tk.LEFT, padx=4)

        tk.Label(frame, text="League:", bg=BG, fg=FG, font=FONT).grid(row=2, column=0, sticky="w", pady=4)
        self._league_var = tk.StringVar(value=self._config.get("league", ""))
        self._league_cb = tk.OptionMenu(frame, self._league_var, *self._profile.default_leagues)
        self._league_cb.configure(bg="#2A2A2A", fg=FG, activebackground="#3A3020",
                                  activeforeground=ACC, relief=tk.FLAT, font=FONT, width=18)
        self._league_cb["menu"].configure(bg="#2A2A2A", fg=FG)
        self._league_cb.grid(row=2, column=1, sticky="w")

        tk.Label(frame, text="Currency:", bg=BG, fg=FG, font=FONT).grid(row=3, column=0, sticky="w", pady=4)
        self._currency_var = tk.StringVar(value=self._config.get("currency_unit", "divine"))
        currency_frame = tk.Frame(frame, bg=BG)
        currency_frame.grid(row=3, column=1, sticky="w")
        for cu in ("divine", "chaos", "exalted"):
            tk.Radiobutton(currency_frame, text=cu, variable=self._currency_var, value=cu,
                           bg=BG, fg=FG, selectcolor="#2A2020", activebackground=BG,
                           font=FONT).pack(side=tk.LEFT, padx=2)

        # Status bar
        self._status_var = tk.StringVar(value="Initializing…")
        tk.Label(frame, textvariable=self._status_var, bg=BG, fg="#888", font=FONT_SMALL,
                 width=38, anchor="w").grid(row=4, column=0, columnspan=2, pady=(8, 2))

        # Hotkey legend
        legend = (
            "F9 Scan prices   F6 Cycle currency\n"
            "F5 Check mod (Ctrl+C first)   F8 Settings\n"
            "Ctrl+Alt+Q Quit"
        )
        tk.Label(frame, text=legend, bg=BG, fg="#666", font=FONT_SMALL, justify=tk.LEFT).grid(
            row=5, column=0, columnspan=2, pady=(4, 0))

        # Manual refresh — btn_frame ใช้ pack ภายใน, ไม่ conflict กับ grid ของ frame หลัก
        btn_frame = tk.Frame(frame, bg=BG)
        btn_frame.grid(row=6, column=0, columnspan=2, pady=(8, 0))

        def btn(text, cmd):
            b = tk.Button(btn_frame, text=text, command=cmd,
                          bg="#3A3020", fg=FG, activebackground=ACC, activeforeground="#000",
                          relief=tk.FLAT, font=FONT, padx=8, pady=3, cursor="hand2")
            return b

        btn("Refresh Prices", self._load_prices_async).pack(side=tk.LEFT, padx=4)
        btn("Settings (F8)", self._open_settings).pack(side=tk.LEFT, padx=4)

    def _build_overlay(self) -> None:
        self._overlay = PriceOverlay(
            self._root,
            offset_px=self._config.get("price_offset_px", 2),
            opacity=self._config.get("overlay_opacity", 0.9),
        )

    def _build_trade_panel(self) -> None:
        self._trade_panel = TradePanel(self._root, self._profile)
        self._trade_panel.set_refresh_callback(self._on_trade_refresh)

    def _start_hotkeys(self) -> None:
        hkm = HotkeyManager(tk_root=self._root)
        hkm.add(self._config.get("hotkey_scan", "F9"),      self._on_f9_scan)
        hkm.add(self._config.get("hotkey_currency", "F6"),  self._on_f6_currency)
        hkm.add(self._config.get("hotkey_trade", "F5"),     self._on_f5_trade)
        hkm.add(self._config.get("hotkey_settings", "F8"),  self._open_settings)
        hkm.add(self._config.get("hotkey_quit", "Ctrl+Alt+Q"), self._quit)
        hkm.start()
        hkm.wait_ready()
        self._hotkeys = hkm
        log.info("Hotkeys registered")

    # ------------------------------------------------------------------
    # Hotkey handlers (called from main thread via after_idle)
    # ------------------------------------------------------------------

    def _on_f9_scan(self) -> None:
        if not self._repo.is_ready():
            self._set_status("Prices not loaded yet")
            return
        if self._scanner is None:
            self._scanner = Scanner(self._repo, dpi_scale=self._dpi_scale)
        if self._overlay and self._overlay._visible:
            self._overlay.hide()
            self._last_scan_results = []
            return

        self._set_status("Scanning…")
        threshold = float(self._config.get("match_threshold", 0.80))

        def _run():
            try:
                results = self._scanner.scan(threshold)
                self._root.after_idle(lambda: self._show_scan_results(results))
            except Exception as e:
                log.exception("Scan error")
                self._root.after_idle(lambda: self._set_status(f"Scan error: {e}"))

        threading.Thread(target=_run, daemon=True).start()

    def _show_scan_results(self, results: list[ScanResult]) -> None:
        self._last_scan_results = results
        currency = self._currency_var.get()
        divine_rate = self._repo.divine_chaos_rate()
        self._overlay.show_prices(results, currency, divine_rate)
        count = len(results)
        self._set_status(f"Found {count} price{'s' if count != 1 else ''}")

    def _on_f6_currency(self) -> None:
        order = ["divine", "chaos", "exalted"]
        cur = self._currency_var.get()
        nxt = order[(order.index(cur) + 1) % len(order)] if cur in order else "divine"
        self._currency_var.set(nxt)
        self._config.set("currency_unit", nxt)
        if self._last_scan_results:
            self._show_scan_results(self._last_scan_results)

    def _on_f5_trade(self) -> None:
        text = read_text()
        if not text:
            self._set_status("Clipboard empty — Ctrl+C an item first")
            return

        game_version = self._gv_var.get()
        item = parse_item(text, game_version)
        if item is None:
            self._set_status("Clipboard doesn't look like a PoE item")
            return

        league = self._league_var.get()
        self._set_status(f"Looking up: {item.item_name}…")

        def _run():
            try:
                sid = self._config.load_session_id()
                self._trade_client.update_session(sid)
                # Build query with all mods, no filtering (show all listings)
                query = build_query(item, [], league)
                listings = self._trade_client.search_and_fetch(query, league)
                self._root.after_idle(lambda: self._show_trade_results(listings, item))
            except SessionExpiredError:
                self._root.after_idle(lambda: self._on_session_expired())
            except Exception as e:
                log.exception("Trade lookup error")
                self._root.after_idle(lambda: self._set_status(f"Trade error: {e}"))

        threading.Thread(target=_run, daemon=True).start()

    def _show_trade_results(self, listings: list[TradeListing], item) -> None:
        self._set_status(f"Trade: {len(listings)} listings for {item.item_name}")
        if self._trade_panel:
            self._trade_panel.show(listings, item, league=self._league_var.get())

    def _on_trade_refresh(self) -> None:
        text = read_text()
        if text:
            self._on_f5_trade()

    def _on_session_expired(self) -> None:
        self._set_status("Session expired — enter new POESESSID in Settings (F8)")
        messagebox.showwarning(
            "Session Expired",
            "POESESSID is invalid or expired.\nOpen Settings (F8) and enter a new one.",
            parent=self._root,
        )

    # ------------------------------------------------------------------
    # Settings & price loading
    # ------------------------------------------------------------------

    def _open_settings(self) -> None:
        SettingsWindow(
            self._root, self._config,
            on_apply=self._on_settings_applied,
            on_fetch_leagues=self._fetch_leagues_for_gv,
        )

    def _on_settings_applied(self) -> None:
        new_gv = self._config.get("game_version", "poe2")
        if new_gv != self._gv_var.get():
            self._gv_var.set(new_gv)
            self._on_game_version_changed()
        self._currency_var.set(self._config.get("currency_unit", "divine"))
        if self._overlay:
            self._overlay.set_opacity(self._config.get("overlay_opacity", 0.9))
            self._overlay.set_offset(self._config.get("price_offset_px", 2))
        self._load_prices_async()

    def _on_game_version_changed(self) -> None:
        gv = self._gv_var.get()
        self._config.set("game_version", gv)
        self._profile = PROFILES.get(gv, PROFILES["poe2"])
        self._repo = PriceRepository(self._profile, cache_dir=self._config.app_dir() / "cache")
        self._scanner = None
        menu = self._league_cb["menu"]
        menu.delete(0, tk.END)
        for league in self._profile.default_leagues:
            menu.add_command(label=league, command=lambda l=league: self._league_var.set(l))
        if self._profile.default_leagues:
            self._league_var.set(self._profile.default_leagues[0])
        self._load_prices_async()

    def _fetch_leagues_for_gv(self, game_version: str) -> list[str]:
        from .ninja_client import NinjaClient
        profile = PROFILES.get(game_version, PROFILES["poe2"])
        client = NinjaClient(profile)
        return client.fetch_leagues()

    def _load_prices_async(self) -> None:
        league = self._league_var.get()
        if not league:
            league = self._profile.default_leagues[0] if self._profile.default_leagues else "Standard"
            self._league_var.set(league)
        self._set_status(_STATUS_LOADING)

        def _on_done(snapshot):
            count = len(snapshot.entries) if snapshot else 0
            self._root.after_idle(lambda: self._set_status(_STATUS_READY.format(count=count)))
            self._scanner = Scanner(self._repo, dpi_scale=self._dpi_scale)

        def _on_error(exc):
            self._root.after_idle(lambda: self._set_status(_STATUS_ERROR.format(msg=str(exc)[:60])))

        self._repo.load_async(league, on_done=_on_done, on_error=_on_error)

    # ------------------------------------------------------------------

    def _setup_logging(self) -> None:
        level_str = self._config.get("log_level", "INFO")
        level = getattr(logging, level_str, logging.INFO)
        log_path = self._config.app_dir() / "log.txt"
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            handlers=[
                logging.FileHandler(log_path, mode="w", encoding="utf-8"),
                logging.StreamHandler(),
            ],
        )

    def _set_status(self, msg: str) -> None:
        self._status_var.set(msg[:70])

    def _quit(self) -> None:
        if self._hotkeys:
            self._hotkeys.stop()
        self._root.destroy()

    def run(self) -> None:
        self._root.mainloop()
