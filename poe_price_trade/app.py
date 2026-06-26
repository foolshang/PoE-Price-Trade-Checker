"""Main application: ties together overlay, hotkeys, repository, scan, and trade."""
from __future__ import annotations
import ctypes
import logging
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

from .capture import get_cursor_pos, get_dpi_scale, get_screen_size, set_dpi_aware
from .clipboard import read_text
from .config import AppConfig
from .hotkeys import HotkeyManager
from .item_parser import parse_item
from .models import PriceEntry, ScanResult, TradeListing
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

_MUTEX_NAME = "PoePriceTrade_SingleInstance"


def _acquire_single_instance_mutex() -> Optional[int]:
    """Create a named mutex. Returns handle if this is the first instance, else None."""
    h = ctypes.windll.kernel32.CreateMutexW(None, True, _MUTEX_NAME)
    if ctypes.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        ctypes.windll.kernel32.CloseHandle(h)
        return None
    return h


class App:
    def __init__(self):
        set_dpi_aware()
        self._mutex = _acquire_single_instance_mutex()
        if self._mutex is None:
            import tkinter as _tk
            _r = _tk.Tk()
            _r.withdraw()
            messagebox.showwarning("Already Running",
                                   "PoE Price & Trade Checker is already running.\n"
                                   "Check the taskbar or system tray.")
            _r.destroy()
            raise SystemExit(0)
        self._config = AppConfig()
        self._setup_logging()

        self._root = tk.Tk()
        self._root.title("PoE Price & Trade Checker")
        self._root.configure(bg="#1C1C1C")
        self._root.resizable(False, False)
        self._root.protocol("WM_DELETE_WINDOW", self._quit)

        self._dpi_scale = get_dpi_scale()
        sw, sh = get_screen_size()
        log.info("Screen: %dx%d  DPI scale: %.2f", sw, sh, self._dpi_scale)

        self._profile = PROFILES.get(self._config.get("game_version", "poe2"), PROFILES["poe2"])
        self._repo = PriceRepository(self._profile, cache_dir=self._config.app_dir() / "cache")
        self._scanner: Optional[Scanner] = None
        self._last_scan_results: list[ScanResult] = []

        self._trade_client = TradeClient(self._profile, self._config.load_session_id())
        self._mod_db = ModDatabase(self._profile, cache_dir=self._config.app_dir() / "cache")

        self._overlay: Optional[PriceOverlay] = None
        self._trade_panel: Optional[TradePanel] = None
        self._hotkeys: Optional[HotkeyManager] = None

        self._last_clipboard_hash: int = 0
        self._last_auto_item: str = ""
        self._hover_gen: int = 0          # increments on every mouse move to cancel stale scans
        self._hover_ctrl_c_ts: float = 0.0  # timestamp of last hover-triggered Ctrl+C

        self._build_ui()
        self._build_overlay()
        self._build_trade_panel()
        self._start_hotkeys()
        self._start_clipboard_monitor()
        self._start_hover_watcher()

        gv = self._config.get("game_version", "poe2").upper()
        league = self._config.get("league", "") or (self._profile.default_leagues[0] if self._profile.default_leagues else "Standard")
        sw, sh = get_screen_size()
        self._log(f"เริ่มต้น {gv} · league: {league} · จอ {sw}×{sh} DPI×{self._dpi_scale:.2f}", "dim")
        self._log("Ctrl+C บน item = ราคา (poe.ninja→trade)  |  F5 = Trade panel  |  F8 = Settings", "dim")

        self._load_prices_async()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        BG, FG, ACC = "#1C1C1C", "#E8D5A0", "#C8A050"
        FONT = ("Segoe UI", 9)
        FONT_SMALL = ("Segoe UI", 8)
        FONT_MONO = ("Consolas", 8)

        frame = tk.Frame(self._root, bg=BG, padx=12, pady=8)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(frame, text="PoE Price & Trade Checker", bg=BG, fg=ACC,
                 font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=2, pady=(0, 6))

        # Game version
        self._gv_var = tk.StringVar(value=self._config.get("game_version", "poe2"))
        gv_frame = tk.Frame(frame, bg=BG)
        gv_frame.grid(row=1, column=0, columnspan=2, sticky="w")
        for gv, label in (("poe1", "PoE 1"), ("poe2", "PoE 2")):
            tk.Radiobutton(gv_frame, text=label, variable=self._gv_var, value=gv,
                           bg=BG, fg=FG, selectcolor="#2A2020", activebackground=BG,
                           command=self._on_game_version_changed, font=FONT).pack(side=tk.LEFT, padx=4)

        # League — Combobox พิมพ์เองได้ หรือเลือกจาก dropdown
        tk.Label(frame, text="League:", bg=BG, fg=FG, font=FONT).grid(row=2, column=0, sticky="w", pady=4)
        saved_league = self._config.get("league", "") or (
            self._profile.default_leagues[0] if self._profile.default_leagues else "Standard"
        )
        self._league_var = tk.StringVar(value=saved_league)
        style = ttk.Style()
        style.configure("League.TCombobox", fieldbackground="#2A2A2A", background="#2A2A2A",
                        foreground=FG, selectbackground="#3A3020")
        self._league_cb = ttk.Combobox(frame, textvariable=self._league_var,
                                       values=self._profile.default_leagues,
                                       width=20, font=FONT, style="League.TCombobox")
        self._league_cb.grid(row=2, column=1, sticky="w")
        # เปลี่ยน league → โหลดราคาใหม่ทันที (ทั้ง dropdown และพิมพ์)
        self._league_var.trace_add("write", lambda *_: self._load_prices_async())
        self._league_cb.bind("<Return>", lambda _: self._load_prices_async())

        # Status log — แสดงขั้นตอนการทำงานแบบ real-time
        tk.Label(frame, text="Status:", bg=BG, fg=FG, font=FONT).grid(
            row=3, column=0, sticky="nw", pady=(6, 2))

        log_frame = tk.Frame(frame, bg="#111")
        log_frame.grid(row=3, column=1, sticky="ew", pady=(6, 2))
        frame.columnconfigure(1, weight=1)

        self._log_text = tk.Text(
            log_frame, bg="#111", fg="#AADDAA", font=FONT_MONO,
            width=36, height=6, relief=tk.FLAT,
            state=tk.DISABLED, wrap=tk.WORD,
            insertbackground=FG,
        )
        self._log_text.pack(fill=tk.BOTH)
        self._log_text.tag_config("ok",    foreground="#88DD88")
        self._log_text.tag_config("err",   foreground="#DD6666")
        self._log_text.tag_config("warn",  foreground="#DDCC66")
        self._log_text.tag_config("info",  foreground="#AACCFF")
        self._log_text.tag_config("dim",   foreground="#666666")

        # Hover mode toggle
        self._hover_var = tk.BooleanVar(value=self._config.get("hover_mode", True))
        hover_row = tk.Frame(frame, bg=BG)
        hover_row.grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 0))
        tk.Checkbutton(
            hover_row, text="Hover mode (เมาส์นิ่ง 0.4s → ราคาจาก poe.ninja/trade)",
            variable=self._hover_var,
            bg=BG, fg=FG, selectcolor="#2A2020", activebackground=BG,
            font=FONT,
            command=self._on_hover_toggle,
        ).pack(side=tk.LEFT)

        # Hotkey legend
        legend = "F9 Scan  |  F5 Trade (ชี้ item)  |  F8 Settings  |  Ctrl+Alt+Q Quit"
        tk.Label(frame, text=legend, bg=BG, fg="#666", font=FONT_SMALL, justify=tk.LEFT).grid(
            row=5, column=0, columnspan=2, pady=(4, 0))

        # Buttons
        btn_frame = tk.Frame(frame, bg=BG)
        btn_frame.grid(row=6, column=0, columnspan=2, pady=(8, 0))

        def btn(text, cmd):
            b = tk.Button(btn_frame, text=text, command=cmd,
                          bg="#3A3020", fg=FG, activebackground=ACC, activeforeground="#000",
                          relief=tk.FLAT, font=FONT, padx=8, pady=3, cursor="hand2")
            return b

        btn("Refresh Prices", self._load_prices_async).pack(side=tk.LEFT, padx=4)
        btn("Refresh Leagues", self._fetch_leagues_for_current_gv).pack(side=tk.LEFT, padx=4)
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
            self._log("⚠ ราคายังโหลดไม่เสร็จ รอสักครู่…", "warn")
            return
        if self._scanner is None:
            self._scanner = Scanner(self._repo, dpi_scale=self._dpi_scale)
        if self._overlay and self._overlay._visible:
            self._overlay.hide()
            self._last_scan_results = []
            self._log("ซ่อน overlay แล้ว", "dim")
            return

        self._log("⟳ กำลัง scan หน้าจอ…", "info")
        threshold = float(self._config.get("match_threshold", 0.80))

        def _run():
            try:
                results = self._scanner.scan(threshold)
                self._root.after_idle(lambda: self._show_scan_results(results))
            except Exception as e:
                log.exception("Scan error")
                self._root.after_idle(lambda err=e: self._log(f"✗ Scan error: {err}", "err"))

        threading.Thread(target=_run, daemon=True).start()

    def _show_scan_results(self, results: list[ScanResult]) -> None:
        self._last_scan_results = results
        self._overlay.show_prices(results)
        count = len(results)
        if count:
            names = ", ".join(r.item_name for r in results[:3])
            extra = f" (+{count-3} อื่น)" if count > 3 else ""
            self._log(f"✓ พบ {count} รายการ: {names}{extra}", "ok")
        else:
            self._log("ไม่พบ item ที่ตรงกัน — ลองเปิด tooltip แล้วกด F9", "warn")

    def _simulate_ctrl_c(self) -> None:
        """Simulate Ctrl+C so PoE copies the hovered item to clipboard."""
        VK_CONTROL, VK_C, KEYUP = 0x11, 0x43, 0x0002
        ke = ctypes.windll.user32.keybd_event
        ke(VK_CONTROL, 0, 0, 0)
        ke(VK_C, 0, 0, 0)
        ke(VK_C, 0, KEYUP, 0)
        ke(VK_CONTROL, 0, KEYUP, 0)

    def _on_f5_trade(self) -> None:
        def _run():
            try:
                self._simulate_ctrl_c()
                time.sleep(0.25)

                text = read_text()
                if not text or ("Rarity:" not in text and "Item Class:" not in text):
                    self._root.after_idle(lambda: self._log("⚠ ชี้ที่ item แล้วกด F5 (ไม่พบข้อมูล item)", "warn"))
                    return

                game_version = self._gv_var.get()
                item = parse_item(text, game_version)
                if item is None:
                    self._root.after_idle(lambda: self._log("⚠ ไม่ใช่ข้อความ item ของ PoE", "warn"))
                    return

                league = self._league_var.get()
                self._root.after_idle(lambda n=item.item_name: self._log(f"⟳ ค้นหา: {n}…", "info"))

                sid = self._config.load_session_id()
                self._trade_client.update_session(sid)
                query = build_query(item, [], league)
                listings = self._trade_client.search_and_fetch(query, league)
                self._root.after_idle(lambda l=listings, i=item: self._show_trade_results(l, i))
            except SessionExpiredError:
                self._root.after_idle(lambda: self._on_session_expired())
            except Exception as e:
                log.exception("Trade lookup error")
                self._root.after_idle(lambda err=e: self._log(f"✗ Trade error: {err}", "err"))

        threading.Thread(target=_run, daemon=True, name="F5Trade").start()

    def _show_trade_results(self, listings: list[TradeListing], item) -> None:
        self._log(f"✓ Trade: {len(listings)} listings — {item.item_name}", "ok")
        if self._trade_panel:
            self._trade_panel.show(listings, item, league=self._league_var.get())

    def _on_trade_refresh(self) -> None:
        text = read_text()
        if text:
            self._on_f5_trade()

    def _on_session_expired(self) -> None:
        self._log("✗ Session หมดอายุ — ใส่ POESESSID ใหม่ใน Settings (F8)", "err")
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
            self._on_game_version_changed()  # handles league + reload via trace
        if self._overlay:
            self._overlay.set_opacity(self._config.get("overlay_opacity", 0.9))
            self._overlay.set_offset(self._config.get("price_offset_px", 2))

    def _on_game_version_changed(self) -> None:
        gv = self._gv_var.get()
        self._config.set("game_version", gv)
        self._profile = PROFILES.get(gv, PROFILES["poe2"])
        self._repo = PriceRepository(self._profile, cache_dir=self._config.app_dir() / "cache")
        self._scanner = None
        self._league_cb.configure(values=self._profile.default_leagues)
        if self._profile.default_leagues:
            self._league_var.set(self._profile.default_leagues[0])  # trace fires → _load_prices_async
        else:
            self._load_prices_async()

    def _fetch_leagues_for_gv(self, game_version: str) -> list[str]:
        from .ninja_client import NinjaClient
        profile = PROFILES.get(game_version, PROFILES["poe2"])
        client = NinjaClient(profile)
        return client.fetch_leagues()

    def _fetch_leagues_for_current_gv(self) -> None:
        self._log("⟳ ดึงรายชื่อ league…", "info")
        gv = self._gv_var.get()

        def _run():
            try:
                leagues = self._fetch_leagues_for_gv(gv)
                self._root.after_idle(lambda: self._update_league_menu(leagues))
            except Exception as e:
                self._root.after_idle(lambda err=e: self._log(f"✗ ดึง league ไม่ได้: {err}", "err"))

        threading.Thread(target=_run, daemon=True).start()

    def _update_league_menu(self, leagues: list[str]) -> None:
        if not leagues:
            return
        self._league_cb.configure(values=leagues)
        current = self._league_var.get()
        if current not in leagues:
            self._league_var.set(leagues[0])  # trace fires → reload
        self._log(f"✓ พบ {len(leagues)} leagues", "ok")

    def _load_prices_async(self) -> None:
        league = self._league_var.get() or (
            self._profile.default_leagues[0] if self._profile.default_leagues else "Standard"
        )
        self._config.set("league", league)
        self._log(f"⟳ กำลังโหลดราคา ({league})…", "info")

        def _on_done(snapshot):
            count = len(snapshot.entries) if snapshot else 0
            def _update():
                self._scanner = Scanner(self._repo, dpi_scale=self._dpi_scale)
                if count == 0:
                    self._log(f"⚠ 0 รายการ ({league}) — league อาจหมดแล้ว ลองเปลี่ยนเป็น Standard", "warn")
                else:
                    self._log(f"✓ พร้อม — {count} รายการ ({league})", "ok")
            self._root.after_idle(_update)

        def _on_error(exc):
            self._root.after_idle(lambda: self._log(f"✗ โหลดราคาไม่สำเร็จ: {exc}", "err"))

        self._repo.load_async(league, on_done=_on_done, on_error=_on_error)

    # ------------------------------------------------------------------
    # Hover mode — mouse still 400ms → auto scan region → show price
    # ------------------------------------------------------------------

    def _on_hover_toggle(self) -> None:
        enabled = self._hover_var.get()
        self._config.set("hover_mode", enabled)
        state = "เปิด" if enabled else "ปิด"
        self._log(f"Hover mode: {state}", "dim")
        if not enabled and self._overlay:
            self._overlay.hide()

    def _start_hover_watcher(self) -> None:
        threading.Thread(target=self._hover_loop, daemon=True, name="HoverWatcher").start()

    def _hover_loop(self) -> None:
        last_x, last_y = -9999, -9999
        still_since: float = 0.0
        triggered_gen: int = -1
        STILL_DELAY = 0.4   # seconds before triggering scan
        MOVE_THRESH = 8     # pixels of movement to reset timer

        while True:
            time.sleep(0.1)
            try:
                cx, cy = get_cursor_pos()
            except Exception:
                continue

            moved = abs(cx - last_x) > MOVE_THRESH or abs(cy - last_y) > MOVE_THRESH
            if moved:
                last_x, last_y = cx, cy
                still_since = time.time()
                self._hover_gen += 1
                self._last_auto_item = ""  # reset so re-hovering same item shows price again
                # Hide overlay on mouse move (if hover mode is on)
                if self._hover_var.get() and self._overlay and self._overlay._visible:
                    self._root.after_idle(self._overlay.hide)
            else:
                elapsed = time.time() - still_since
                cur_gen = self._hover_gen
                if elapsed >= STILL_DELAY and triggered_gen != cur_gen:
                    triggered_gen = cur_gen
                    if self._hover_var.get():
                        self._trigger_hover_price(cx, cy, cur_gen)

    def _trigger_hover_price(self, cx: int, cy: int, gen: int) -> None:
        """Simulate Ctrl+C, read clipboard, check poe.ninja then trade API; gen-guarded."""
        def _run():
            try:
                # Mark hover-triggered Ctrl+C so clipboard monitor skips this change
                self._hover_ctrl_c_ts = time.time()
                self._simulate_ctrl_c()
                time.sleep(0.22)

                if self._hover_gen != gen:
                    return

                text = read_text() or ""
                if "Rarity:" not in text and "Item Class:" not in text:
                    return

                gv = self._gv_var.get()
                item = parse_item(text, gv)
                if item is None:
                    return

                # 1. poe.ninja lookup (instant, ~500 currency/consumable items)
                if self._repo.is_ready():
                    entry = self._repo.lookup(item.item_name, 0.85)
                    if entry:
                        if self._hover_gen == gen:
                            p = entry.format_price()
                            def _show_ninja(e=entry, ps=p, n=item.item_name):
                                self._log(f"💰 {n}: {ps}", "ok")
                                self._show_price_at_cursor(e)
                            self._root.after_idle(_show_ninja)
                        return

                # 2. PoE trade API fallback (covers all items incl. uniques, gems, etc.)
                sid = self._config.load_session_id()
                if not sid:
                    return

                league = self._league_var.get()
                self._trade_client.update_session(sid)
                query = build_query(item, [], league)
                q_id, result_ids = self._trade_client.search(query, league)
                if not result_ids or self._hover_gen != gen:
                    return

                listings = self._trade_client.fetch(result_ids[:5], q_id)
                if not listings or self._hover_gen != gen:
                    return

                cheapest = min(listings, key=lambda l: l.price_amount)
                entry = self._make_price_entry_from_listing(item.item_name, cheapest)
                p = entry.format_price()

                def _show_trade(e=entry, ps=p, n=item.item_name):
                    self._log(f"💰 {n} (trade): {ps}", "ok")
                    self._show_price_at_cursor(e)
                self._root.after_idle(_show_trade)
            except Exception as e:
                log.debug("Hover price error: %s", e)

        threading.Thread(target=_run, daemon=True, name=f"HoverPrice-{gen}").start()

    # ------------------------------------------------------------------
    # Clipboard auto-detect (Ctrl+C on item → show price immediately)
    # ------------------------------------------------------------------

    def _start_clipboard_monitor(self) -> None:
        def _loop():
            while True:
                time.sleep(0.35)
                try:
                    text = read_text() or ""
                    h = hash(text)
                    if h != self._last_clipboard_hash:
                        self._last_clipboard_hash = h
                        # Skip if hover mode just triggered a Ctrl+C — hover handler processes it
                        if time.time() - self._hover_ctrl_c_ts < 0.8:
                            continue
                        if "Rarity:" in text and "--------" in text:
                            self._root.after_idle(lambda t=text: self._on_clipboard_item(t))
                except Exception:
                    pass
        threading.Thread(target=_loop, daemon=True, name="ClipboardMonitor").start()

    def _on_clipboard_item(self, text: str) -> None:
        gv = self._gv_var.get()
        item = parse_item(text, gv)
        if item is None:
            return
        if item.item_name == self._last_auto_item:
            return  # same item, skip
        self._last_auto_item = item.item_name

        if not self._repo.is_ready():
            self._log(f"? {item.item_name}: ราคายังโหลดไม่เสร็จ", "dim")
            return

        entry = self._repo.lookup(item.item_name, 0.85)
        if entry:
            price_str = entry.format_price()
            self._log(f"💰 {item.item_name}: {price_str}", "ok")
            self._show_price_at_cursor(entry)
        else:
            # ไม่พบใน poe.ninja → ค้นหา trade API โดยตรง (cover unique items, gems, etc.)
            self._log(f"⟳ {item.item_name}: ไม่พบใน poe.ninja — ค้นใน trade…", "info")
            self._quick_trade_lookup_async(item)

    def _quick_trade_lookup_async(self, item) -> None:
        """Look up item price via PoE trade API; used as fallback when poe.ninja has no data."""
        league = self._league_var.get()

        def _run():
            try:
                sid = self._config.load_session_id()
                if not sid:
                    self._root.after_idle(lambda: self._log(
                        f"? {item.item_name}: ไม่พบใน poe.ninja "
                        "(ตั้ง POESESSID ใน Settings เพื่อค้น trade)", "dim"))
                    return
                self._trade_client.update_session(sid)
                query = build_query(item, [], league)
                q_id, result_ids = self._trade_client.search(query, league)
                if not result_ids:
                    self._root.after_idle(lambda: self._log(
                        f"? {item.item_name}: ไม่พบ listing ใน trade", "dim"))
                    return
                listings = self._trade_client.fetch(result_ids[:5], q_id)
                if not listings:
                    return
                cheapest = min(listings, key=lambda l: l.price_amount)
                entry = self._make_price_entry_from_listing(item.item_name, cheapest)
                p = entry.format_price()

                def _show(e=entry, ps=p, n=item.item_name):
                    self._log(f"💰 {n} (trade): {ps}", "ok")
                    self._show_price_at_cursor(e)
                self._root.after_idle(_show)
            except SessionExpiredError:
                self._root.after_idle(self._on_session_expired)
            except Exception as e:
                log.debug("Quick trade error: %s", e)

        threading.Thread(target=_run, daemon=True, name="QuickTrade").start()

    def _make_price_entry_from_listing(self, item_name: str, listing: TradeListing) -> PriceEntry:
        """Convert cheapest TradeListing → PriceEntry for overlay display."""
        gv = self._gv_var.get()
        currency = listing.price_currency.lower()
        amount = listing.price_amount

        # Try to get real chaos-per-divine from cached poe.ninja data
        chaos_per_div = 0.0
        if self._repo.is_ready():
            div_entry = self._repo.lookup("Divine Orb", 1.0)
            if div_entry and div_entry.chaos_value > 0:
                chaos_per_div = div_entry.chaos_value
        if chaos_per_div <= 0:
            chaos_per_div = 400.0  # PoE2 rough estimate

        if currency in ("divine", "div"):
            divine_v = amount
            chaos_v = amount * chaos_per_div
        elif currency == "chaos":
            chaos_v = amount
            divine_v = amount / chaos_per_div
        else:
            chaos_v = amount
            divine_v = 0.0

        return PriceEntry(
            item_name=item_name,
            normalized_name=item_name.lower(),
            chaos_value=chaos_v,
            divine_value=divine_v,
            listing_count=1,
            game_version=gv,
            category="Trade",
        )

    def _show_price_at_cursor(self, entry) -> None:
        """แสดง price label ใกล้ cursor position ปัจจุบัน"""
        class _POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
        pt = _POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        cx = int(pt.x / self._dpi_scale)
        cy = int(pt.y / self._dpi_scale)

        result = ScanResult(
            item_name=entry.item_name,
            price_entry=entry,
            bbox_x=cx,
            bbox_y=cy,
            bbox_w=0,
            bbox_h=0,
            confidence=1.0,
        )
        self._overlay.show_prices([result])
        # ซ่อนอัตโนมัติหลัง 6 วินาที
        self._root.after(6000, self._overlay.hide)

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

    def _log(self, msg: str, tag: str = "info") -> None:
        """Append a line to the status log text widget (main thread only)."""
        try:
            widget = self._log_text
            widget.configure(state=tk.NORMAL)
            widget.insert(tk.END, msg + "\n", tag)
            widget.see(tk.END)
            widget.configure(state=tk.DISABLED)
        except Exception:
            pass

    def _set_status(self, msg: str) -> None:
        self._log(msg)

    def _quit(self) -> None:
        if self._hotkeys:
            self._hotkeys.stop()
        if self._mutex:
            ctypes.windll.kernel32.ReleaseMutex(self._mutex)
            ctypes.windll.kernel32.CloseHandle(self._mutex)
        self._root.destroy()

    def run(self) -> None:
        self._root.mainloop()
