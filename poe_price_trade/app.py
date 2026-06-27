"""Main application: overlay, hotkeys, repository, F4 scan→hover, F5 browser trade."""
from __future__ import annotations
import ctypes
import logging
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

from .capture import get_cursor_pos, get_screen_size, set_dpi_aware
from .clipboard import read_text
from .config import AppConfig
from . import debug
from .hotkeys import HotkeyManager
from .item_parser import parse_item
from .models import ScanResult
from .overlay import PriceOverlay
from .profiles import PROFILES
from .repository import PriceRepository
from .scan import Scanner
from .settings import SettingsWindow
from .trade_url import open_trade
from .mod_db import ModDatabase

log = logging.getLogger(__name__)

_MUTEX_NAME = "PoePriceTrade_SingleInstance"


def _acquire_single_instance_mutex() -> Optional[int]:
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
        debug.setup(self._config.app_dir() / "debug_logs")

        self._root = tk.Tk()
        self._root.title("PoE Price & Trade Checker")
        self._root.configure(bg="#1C1C1C")
        self._root.resizable(False, False)
        self._root.protocol("WM_DELETE_WINDOW", self._quit)

        sw, sh = get_screen_size()
        log.info("Screen: %dx%d", sw, sh)

        self._profile = PROFILES.get(self._config.get("game_version", "poe2"), PROFILES["poe2"])
        self._repo = PriceRepository(self._profile, cache_dir=self._config.app_dir() / "cache")
        self._scanner: Optional[Scanner] = None
        self._mod_db = ModDatabase(self._profile, cache_dir=self._config.app_dir() / "cache")

        self._overlay: Optional[PriceOverlay] = None
        self._hotkeys: Optional[HotkeyManager] = None

        # F4 scan state
        self._scan_results: list[ScanResult] = []
        self._scan_active = False
        self._hover_shown_key = ""
        self._safety_timer = None
        self._motion = None  # MotionWatcher

        self._build_ui()
        self._build_overlay()
        self._start_hotkeys()
        self._start_hover_loop()

        gv = self._config.get("game_version", "poe2").upper()
        league = self._config.get("league", "") or (
            self._profile.default_leagues[0] if self._profile.default_leagues else "Standard"
        )
        debug.event(f"start gv={gv} league={league} screen={sw}x{sh}")
        self._log(f"เริ่มต้น {gv} · league: {league} · จอ {sw}×{sh}", "dim")
        self._log("F4 Scan+Hover  |  F5 Trade browser  |  Esc ล้าง  |  F8 Settings", "dim")

        if self._config.get("auto_league", True):
            self._fetch_leagues_for_current_gv(auto_pick=True)
        else:
            self._load_prices_async()

    # ------------------------------------------------------------------
    # Build UI
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

        # League
        tk.Label(frame, text="League:", bg=BG, fg=FG, font=FONT).grid(
            row=2, column=0, sticky="w", pady=4)
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
        self._league_var.trace_add("write", lambda *_: self._load_prices_async())
        self._league_cb.bind("<Return>", lambda _: self._load_prices_async())

        # Status log
        tk.Label(frame, text="Status:", bg=BG, fg=FG, font=FONT).grid(
            row=3, column=0, sticky="nw", pady=(6, 2))
        log_frame = tk.Frame(frame, bg="#111")
        log_frame.grid(row=3, column=1, sticky="ew", pady=(6, 2))
        frame.columnconfigure(1, weight=1)

        self._log_text = tk.Text(
            log_frame, bg="#111", fg="#AADDAA", font=FONT_MONO,
            width=36, height=6, relief=tk.FLAT,
            state=tk.DISABLED, wrap=tk.WORD,
        )
        self._log_text.pack(fill=tk.BOTH)
        self._log_text.tag_config("ok",   foreground="#88DD88")
        self._log_text.tag_config("err",  foreground="#DD6666")
        self._log_text.tag_config("warn", foreground="#DDCC66")
        self._log_text.tag_config("info", foreground="#AACCFF")
        self._log_text.tag_config("dim",  foreground="#666666")

        # Legend
        legend = "F4 Scan+Hover  |  F5 Trade browser  |  Esc ล้าง  |  F8 Settings  |  Ctrl+Alt+Q Quit"
        tk.Label(frame, text=legend, bg=BG, fg="#666", font=FONT_SMALL, justify=tk.LEFT).grid(
            row=4, column=0, columnspan=2, pady=(4, 0))

        # Buttons
        btn_frame = tk.Frame(frame, bg=BG)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=(8, 0))

        def btn(text, cmd):
            return tk.Button(btn_frame, text=text, command=cmd,
                             bg="#3A3020", fg=FG, activebackground=ACC, activeforeground="#000",
                             relief=tk.FLAT, font=FONT, padx=8, pady=3, cursor="hand2")

        btn("Refresh Prices", self._load_prices_async).pack(side=tk.LEFT, padx=4)
        btn("Refresh Leagues", self._fetch_leagues_for_current_gv).pack(side=tk.LEFT, padx=4)
        btn("Settings (F8)", self._open_settings).pack(side=tk.LEFT, padx=4)

    def _build_overlay(self) -> None:
        self._overlay = PriceOverlay(
            self._root,
            offset_px=self._config.get("price_offset_px", 2),
            opacity=self._config.get("overlay_opacity", 0.9),
        )

    def _start_hotkeys(self) -> None:
        hkm = HotkeyManager(tk_root=self._root)
        hkm.add(self._config.get("hotkey_scan", "F4"),         self._on_f4_scan)
        hkm.add(self._config.get("hotkey_trade", "F5"),        self._on_f5_trade)
        hkm.add(self._config.get("hotkey_settings", "F8"),     self._open_settings)
        hkm.add(self._config.get("hotkey_quit", "Ctrl+Alt+Q"), self._quit)
        clear_key = self._config.get("hotkey_clear", "Esc")
        try:
            hkm.add(clear_key, self._clear_all)
        except Exception:
            log.warning("Could not register clear hotkey: %s", clear_key)
        hkm.start()
        hkm.wait_ready()
        self._hotkeys = hkm
        log.info("Hotkeys registered")

    # ------------------------------------------------------------------
    # F4 scan → hover reveal
    # ------------------------------------------------------------------

    def _on_f4_scan(self) -> None:
        if not self._repo.is_ready():
            self._log("⚠ ราคายังโหลดไม่เสร็จ รอสักครู่…", "warn")
            return
        if self._scanner is None:
            self._scanner = Scanner(self._repo)
        self._clear_all()
        self._log("⟳ scan…", "info")
        t0 = time.time()

        def _run():
            try:
                results = self._scanner.scan(float(self._config.get("match_threshold", 0.8)))
                ms = int((time.time() - t0) * 1000)
                self._root.after_idle(lambda: self._on_scan_done(results, ms))
            except Exception as e:
                log.exception("Scan error")
                self._root.after_idle(lambda err=e: self._log(f"✗ scan: {err}", "err"))

        threading.Thread(target=_run, daemon=True, name="F4Scan").start()

    def _on_scan_done(self, results: list[ScanResult], ms: int) -> None:
        self._scan_results = results
        self._scan_active = bool(results)
        count = len(results)
        names = [r.item_name for r in results]
        debug.event(f"F4 scan: matched={count} took={ms}ms items={names}")
        if count:
            self._log(f"✓ scan {count} รายการ ({ms}ms) — hover เพื่อดูราคา", "ok")
            self._start_safety_timer()
            self._start_motion_watch()
        else:
            self._log("ไม่พบ item — เปิด tooltip ก่อนกด F4", "warn")

    def _start_hover_loop(self) -> None:
        threading.Thread(target=self._hover_loop, daemon=True, name="HoverLoop").start()

    def _hover_loop(self) -> None:
        """ตรวจตำแหน่ง cursor ทุก 80ms — ถ้าอยู่ใน bbox ของ item ไหน โชว์ราคา (ไม่ OCR ซ้ำ)."""
        while True:
            time.sleep(0.08)
            if not self._scan_active:
                continue
            try:
                cx, cy = get_cursor_pos()
            except Exception:
                continue
            hit = None
            for r in self._scan_results:
                if (r.bbox_x <= cx <= r.bbox_x + max(r.bbox_w, 40) and
                        r.bbox_y - 6 <= cy <= r.bbox_y + r.bbox_h + 6):
                    hit = r
                    break
            key = hit.item_name if hit else ""
            if key != self._hover_shown_key:
                self._hover_shown_key = key
                if hit:
                    debug.event(f"hover '{hit.item_name}' @({cx},{cy})")
                    self._root.after_idle(lambda h=hit: self._overlay.show_prices([h]))
                else:
                    self._root.after_idle(self._overlay.hide)

    def _clear_all(self) -> None:
        self._scan_active = False
        self._scan_results = []
        self._hover_shown_key = ""
        if self._overlay:
            self._overlay.hide()
        if self._motion:
            self._motion.stop()
            self._motion = None
        if self._safety_timer:
            try:
                self._root.after_cancel(self._safety_timer)
            except Exception:
                pass
            self._safety_timer = None

    def _start_safety_timer(self) -> None:
        if self._safety_timer:
            try:
                self._root.after_cancel(self._safety_timer)
            except Exception:
                pass
        self._safety_timer = self._root.after(25000, self._clear_all)

    def _start_motion_watch(self) -> None:
        from .motion import MotionWatcher
        if self._motion:
            self._motion.stop()
        self._motion = MotionWatcher(on_motion=lambda: self._root.after_idle(self._on_walk))
        self._motion.start()

    def _on_walk(self) -> None:
        debug.event("auto-clear: motion detected")
        self._clear_all()

    # ------------------------------------------------------------------
    # F5 — open browser trade
    # ------------------------------------------------------------------

    def _simulate_ctrl_c(self) -> None:
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
                time.sleep(0.22)
                text = read_text() or ""
                if "Rarity:" not in text and "Item Class:" not in text:
                    self._root.after_idle(lambda: self._log("⚠ ชี้ที่ item แล้วกด F5", "warn"))
                    return
                item = parse_item(text, self._gv_var.get())
                if not item:
                    self._root.after_idle(lambda: self._log("⚠ อ่าน item ไม่ได้", "warn"))
                    return
                self._mod_db.load()
                url = open_trade(item, self._mod_db, self._league_var.get(), self._profile)
                resolved = sum(1 for m in item.mods if self._mod_db.find_stat_id(m.text))
                debug.event(f"F5 '{item.item_name}' mods={resolved}/{len(item.mods)} url={url[:80]}")
                self._root.after_idle(
                    lambda n=item.item_name: self._log(f"🔎 เปิด trade: {n}", "ok"))
            except Exception as e:
                log.exception("F5 trade error")
                self._root.after_idle(lambda err=e: self._log(f"✗ F5: {err}", "err"))

        threading.Thread(target=_run, daemon=True, name="F5").start()

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
        if self._overlay:
            self._overlay.set_opacity(self._config.get("overlay_opacity", 0.9))
            self._overlay.set_offset(self._config.get("price_offset_px", 2))

    def _on_game_version_changed(self) -> None:
        gv = self._gv_var.get()
        self._config.set("game_version", gv)
        self._profile = PROFILES.get(gv, PROFILES["poe2"])
        self._repo = PriceRepository(self._profile, cache_dir=self._config.app_dir() / "cache")
        self._mod_db = ModDatabase(self._profile, cache_dir=self._config.app_dir() / "cache")
        self._scanner = None
        self._league_cb.configure(values=self._profile.default_leagues)
        self._clear_all()
        if self._config.get("auto_league", True):
            self._fetch_leagues_for_current_gv(auto_pick=True)
        elif self._profile.default_leagues:
            self._league_var.set(self._profile.default_leagues[0])
        else:
            self._load_prices_async()

    def _fetch_leagues_for_gv(self, game_version: str) -> list[str]:
        from .ninja_client import NinjaClient
        profile = PROFILES.get(game_version, PROFILES["poe2"])
        client = NinjaClient(profile)
        return client.fetch_leagues()

    def _fetch_leagues_for_current_gv(self, auto_pick: bool = False) -> None:
        self._log("⟳ ดึงรายชื่อ league…", "info")
        gv = self._gv_var.get()

        def _run():
            try:
                leagues = self._fetch_leagues_for_gv(gv)
                self._root.after_idle(
                    lambda: self._update_league_menu(leagues, auto_pick=auto_pick))
            except Exception as e:
                self._root.after_idle(
                    lambda err=e: self._log(f"✗ ดึง league ไม่ได้: {err}", "err"))

        threading.Thread(target=_run, daemon=True).start()

    def _update_league_menu(self, leagues: list[str], auto_pick: bool = False) -> None:
        if not leagues:
            return
        self._league_cb.configure(values=leagues)
        if auto_pick:
            self._auto_pick_league(leagues)
        else:
            current = self._league_var.get()
            if current not in leagues:
                self._league_var.set(leagues[0])
        self._log(f"✓ พบ {len(leagues)} leagues", "ok")

    def _auto_pick_league(self, leagues: list[str]) -> None:
        pref_hc = self._config.get("prefer_hardcore", False)
        challenge = [l for l in leagues if l not in ("Standard", "Hardcore")]
        def is_hc(name): return "Hardcore" in name or name.upper().startswith("HC")
        pool = [l for l in challenge if is_hc(l) == pref_hc] or challenge or leagues
        picked = pool[0] if pool else (leagues[0] if leagues else "")
        if picked:
            self._league_var.set(picked)
        debug.event(f"auto-league pref_hc={pref_hc} picked={picked}")

    def _load_prices_async(self) -> None:
        league = self._league_var.get() or (
            self._profile.default_leagues[0] if self._profile.default_leagues else "Standard"
        )
        self._config.set("league", league)
        self._log(f"⟳ กำลังโหลดราคา ({league})…", "info")

        def _on_done(snapshot):
            count = len(snapshot.entries) if snapshot else 0
            degraded = self._repo.degraded()
            def _update():
                self._scanner = Scanner(self._repo)
                debug.event(f"ninja loaded entries={count} league={league}")
                if count == 0:
                    self._log(f"⚠ 0 รายการ ({league}) — ลองเปลี่ยนเป็น Standard", "warn")
                else:
                    self._log(f"✓ พร้อม — {count} รายการ ({league})", "ok")
                if degraded:
                    self._log(f"⚠ {len(degraded)} หมวดโหลด 0 — ดู log", "warn")
            self._root.after_idle(_update)

        def _on_error(exc):
            self._root.after_idle(lambda: self._log(f"✗ โหลดราคาไม่สำเร็จ: {exc}", "err"))

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

    def _log(self, msg: str, tag: str = "info") -> None:
        try:
            widget = self._log_text
            widget.configure(state=tk.NORMAL)
            widget.insert(tk.END, msg + "\n", tag)
            widget.see(tk.END)
            widget.configure(state=tk.DISABLED)
        except Exception:
            pass

    def _quit(self) -> None:
        debug.write_summary(self._config.app_dir() / "debug_logs")
        self._clear_all()
        if self._hotkeys:
            self._hotkeys.stop()
        if self._mutex:
            ctypes.windll.kernel32.ReleaseMutex(self._mutex)
            ctypes.windll.kernel32.CloseHandle(self._mutex)
        self._root.destroy()

    def run(self) -> None:
        self._root.mainloop()
