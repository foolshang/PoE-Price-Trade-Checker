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
from .clipboard import read_text, write_text
from .config import AppConfig
from . import debug, hub_client, __version__
from .hotkeys import HotkeyManager
from .item_parser import parse_item
from .models import Rarity, ScanResult
from .overlay import PriceOverlay
from .profiles import PROFILES
from .repository import PriceRepository
from .scan import Scanner
from .settings import SettingsWindow
from .trade_url import open_trade
from .mod_db import ModDatabase
from . import mod_badge
from .mod_badge import ModBadgeDB

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
        self._root.report_callback_exception = self._on_tk_callback_exception
        self._root.title(f"PoE Price & Trade Checker  v{__version__}")
        self._root.configure(bg="#1C1C1C")
        self._root.resizable(False, False)
        self._root.protocol("WM_DELETE_WINDOW", self._quit)

        sw, sh = get_screen_size()
        log.info("Screen: %dx%d", sw, sh)

        self._profile = PROFILES.get(self._config.get("game_version", "poe2"), PROFILES["poe2"])
        self._repo = PriceRepository(self._profile, cache_dir=self._config.app_dir() / "cache")
        self._league_paths: dict[str, str] = {}   # league name -> hub file path
        self._scanner: Optional[Scanner] = None
        self._mod_db = ModDatabase(self._profile, cache_dir=self._config.app_dir() / "cache")
        # Shared across both games (unlike _repo/_mod_db which are per-profile) --
        # load(game) re-indexes in place, so switching game_version doesn't need
        # a new instance, just passing the current game to load() each time.
        self._mod_badge = ModBadgeDB(cache_dir=self._config.app_dir() / "cache",
                                     config_dir=self._config.app_dir())

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
        self._log(f"v{__version__} · {gv} · league: {league} · จอ {sw}×{sh}", "dim")
        self._log("F4 Scan+Hover  |  F5 Trade browser  |  F8 Settings", "dim")

        self._fetch_leagues_for_current_gv(auto_pick=self._config.get("auto_league", True))

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
        legend = "F4 Scan+Hover  |  F5 Trade browser  |  F8 Settings  |  Ctrl+Alt+Q Quit"
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
        self._scan_active = True          # เปิด hover mode เสมอ (แม้ static เจอ 0)
        count = len(results)
        names = [r.item_name for r in results]
        debug.event(f"F4 scan: matched={count} took={ms}ms items={names}")
        self._start_safety_timer()
        self._start_motion_watch()
        if count:
            self._log(f"✓ scan {count} รายการ ({ms}ms) — hover ดูราคา (ชี้ทีละชิ้นก็ได้)", "ok")
        else:
            self._log("hover mode: ชี้ item ให้ tooltip เด้ง แล้วดูราคา", "ok")

    def _start_hover_loop(self) -> None:
        threading.Thread(target=self._hover_loop, daemon=True, name="HoverLoop").start()

    def _hover_loop(self) -> None:
        """hover: static bbox ก่อน (ของตกพื้น/label) → ถ้าไม่โดน OCR รอบ cursor (tooltip)."""
        last_pos = (-999, -999)
        settle_pos = None
        settle_since = 0.0
        ocr_done_pos = None          # ตำแหน่งที่ OCR ไปแล้ว (กัน OCR ซ้ำที่เดิม)
        while True:
            time.sleep(0.08)
            if not self._scan_active:
                continue
            try:
                cx, cy = get_cursor_pos()
            except Exception:
                continue

            # ── 1) static bbox จาก full-screen scan (ของตกพื้น / label) ──
            hit = None
            for r in self._scan_results:
                if (r.bbox_x <= cx <= r.bbox_x + max(r.bbox_w, 40) and
                        r.bbox_y - 6 <= cy <= r.bbox_y + r.bbox_h + 6):
                    hit = r
                    break
            if hit:
                if hit.item_name != self._hover_shown_key:
                    self._hover_shown_key = hit.item_name
                    debug.event(f"hover '{hit.item_name}' @({cx},{cy})")
                    self._root.after_idle(lambda h=hit: self._show_hover_result(h))
                continue

            # ── 2) hover-OCR (inventory / stash — tooltip เด้งตอน hover) ──
            moved = abs(cx - last_pos[0]) > 8 or abs(cy - last_pos[1]) > 8
            last_pos = (cx, cy)
            if moved:
                # cursor ขยับ → รีเซ็ต + ซ่อนราคาที่โชว์อยู่
                settle_pos = (cx, cy)
                settle_since = time.time()
                if self._hover_shown_key:
                    self._hover_shown_key = ""
                    self._root.after_idle(self._overlay.hide)
                continue

            # cursor นิ่ง — นิ่งครบ 0.22s และยังไม่ OCR จุดนี้ → OCR รอบ cursor
            if settle_pos and ocr_done_pos != settle_pos and (time.time() - settle_since) > 0.22:
                ocr_done_pos = settle_pos

                if not self._repo.is_ready() or self._repo.entry_count() == 0:
                    # กันอาการ "พังเงียบ": ราคายังไม่พร้อม/league ว่าง → บอกตรงๆ
                    # แทนที่จะปล่อยให้ tooltip ไม่ขึ้นโดยไม่มีเหตุผลให้เห็น
                    if self._hover_shown_key != "~notready":
                        self._hover_shown_key = "~notready"
                        debug.event(f"hover-ocr skipped: repo not ready "
                                    f"(is_ready={self._repo.is_ready()} "
                                    f"entries={self._repo.entry_count()}) @({cx},{cy})")
                        self._root.after_idle(lambda cx=cx, cy=cy: self._overlay.show_message(
                            "⚠ ราคายังไม่พร้อม", cx, cy))
                    continue

                try:
                    res = self._scanner.scan_region(
                        cx, cy, float(self._config.get("match_threshold", 0.8)))
                except Exception:
                    log.exception("hover-ocr scan_region error")
                    res = []
                if res:
                    r = res[0]
                    self._hover_shown_key = "~ocr:" + r.item_name
                    debug.event(f"hover-ocr '{r.item_name}' @({cx},{cy}) "
                                f"price={r.price_entry.format_price() if r.price_entry else None}")
                    self._root.after_idle(lambda rr=r: self._show_hover_result(rr))

    def _on_tk_callback_exception(self, exc, val, tb) -> None:
        """Default Tk behavior prints to stderr — a windowed (console=False) build has
        no stderr for the user to see, so any exception raised inside an after_idle/
        hotkey callback would otherwise vanish with zero trace. Route it into the same
        log/debug files everything else uses instead."""
        log.error("Unhandled Tk callback exception", exc_info=(exc, val, tb))
        debug.event(f"TK CALLBACK EXCEPTION: {exc.__name__}: {val}")

    def _show_hover_result(self, r: ScanResult) -> None:
        """Wrap overlay.show_prices with a try/except: this runs via after_idle on the
        Tk mainloop, and a windowed (console=False) build has nowhere for an unhandled
        exception there to go — it would otherwise vanish silently instead of just the
        tooltip failing to appear."""
        try:
            self._overlay.show_prices([r])
        except Exception:
            log.exception("show_prices failed")
            debug.event(f"show_prices FAILED for '{r.item_name}'")

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
                import time as _t
                write_text("")                       # ① reset ต้น — กันอ่านค่าเก่า
                self._simulate_ctrl_c()
                text = ""
                for _ in range(24):                  # poll รอจนเกมเขียน item ใหม่ (~1.2s)
                    _t.sleep(0.05)
                    cur = read_text() or ""
                    if "Item Class:" in cur or "Rarity:" in cur:
                        text = cur
                        break
                if not text:
                    self._root.after_idle(lambda: self._log("⚠ ชี้ที่ item แล้วกด F5 อีกครั้ง", "warn"))
                    return
                debug.raw_item(text)
                item = parse_item(text, self._gv_var.get())
                if not item:
                    self._root.after_idle(lambda: self._log("⚠ อ่าน item ไม่ได้", "warn"))
                    return
                # magic ส่องแล้ว: ชื่อบรรทัดเดียวรวม affix name (Legend's ... of Grounding)
                # → หา base จริงจาก meta | ไม่เจอ → ตัด type ทิ้ง (กัน "search invalid")
                if item.rarity == Rarity.MAGIC and item.identified:
                    fixed = self._get_meta_db().resolve_base(item.base_type)
                    if fixed:
                        if fixed != item.base_type:
                            debug.event(f"F5 magic base: '{item.base_type}' → '{fixed}'")
                        item.base_type = fixed
                    else:
                        debug.event(f"F5 magic base unresolved: '{item.base_type}' → ไม่ใส่ type")
                        item.base_type = ""
                if not item.mods_have_headers:
                    # clipboard ไม่มี { ... Modifier } header เลย (เช่น client PoE1 บางตัว) —
                    # prefix_count/suffix_count/affix จาก parser เป็นค่าว่างหมด ต้องเติมจาก
                    # RePoE family data แทน (ดู MetaDB.infer_affixes docstring)
                    self._get_meta_db().infer_affixes(item)
                    debug.event(f"F5 no mod headers — inferred P={item.prefix_count} S={item.suffix_count}")
                self._mod_db.load()
                self._mod_badge.load(self._profile.game_version)
                use_picker = (bool(self._config.get("f5_mod_picker", True))
                              and item.identified
                              and item.rarity in (Rarity.RARE, Rarity.MAGIC)
                              and item.mods)
                if use_picker:
                    # resolve stat id ใน thread นี้ (fuzzy อาจช้า) แล้วเปิด popup บน main thread
                    rows = [(m, self._mod_db.find_stat_id(m.text, getattr(m, "mod_type", None)))
                            for m in item.mods]
                    annos: dict = {}
                    summary = ""
                    try:
                        from .meta_db import MetaDB
                        annos = self._get_meta_db().annotate(item)
                        cap = mod_badge.affix_cap(item.item_class, self._profile.game_version)
                        summary = MetaDB.summary(item, annos, prefix_cap=cap, suffix_cap=cap)
                    except Exception:
                        log.exception("meta annotate error")

                    badge_colors, roll_arrows = self._compute_mod_extras(item, rows, annos)
                    affixes = [m.affix for m, _ in rows]

                    write_text("")                   # ② reset ท้าย
                    debug.event(f"F5 picker '{item.item_name}' rarity={item.rarity} "
                                f"mods={len(rows)} resolved={sum(1 for _, s in rows if s)} "
                                f"money={sum(1 for a in annos.values() if a.get('money'))} "
                                f"badges={sum(1 for c in badge_colors if c)} "
                                f"arrows={sum(1 for a in roll_arrows if a)}")
                    self._root.after_idle(lambda it=item, r=rows, a=annos, s=summary, bc=badge_colors,
                                                  ra=roll_arrows, af=affixes:
                                          self._open_mod_picker(it, r, a, s, bc, ra, af))
                    return
                url = open_trade(item, self._mod_db, self._league_var.get(), self._profile)
                write_text("")                       # ② reset ท้าย — เก็บกวาดหลังเปิด browser
                resolved = sum(1 for m in item.mods if self._mod_db.find_stat_id(m.text))
                debug.event(f"F5 '{item.item_name}' rarity={item.rarity} id={item.identified} "
                            f"base='{item.base_type}' mods={resolved}/{len(item.mods)} url={url[:80]}")
                self._root.after_idle(
                    lambda n=item.item_name: self._log(f"🔎 เปิด trade: {n}", "ok"))
            except Exception as e:
                log.exception("F5 trade error")
                self._root.after_idle(lambda err=e: self._log(f"✗ F5: {err}", "err"))

        threading.Thread(target=_run, daemon=True, name="F5").start()

    def _get_meta_db(self):
        """MetaDB แบบ lazy — สร้างใหม่เฉพาะตอนสลับเกม (mod_meta_{game}.json
        คนละไฟล์ ผูกกับ game_version) ไม่งั้นใช้ตัวเดิมซ้ำทุก F5."""
        from .meta_db import MetaDB
        gv = self._profile.game_version
        if getattr(self, "_meta_db", None) is None or getattr(self, "_meta_db_gv", None) != gv:
            self._meta_db = MetaDB(self._config.app_dir(), gv)
            self._meta_db_gv = gv
        return self._meta_db

    def _compute_mod_extras(self, item, rows, annos) -> tuple:
        """(badge_colors, roll_arrows) — both index-aligned with `rows`, all-None
        if out of scope. Independent of the trade-query stat_id in `rows` itself —
        never touches it, so F5's trade-search behavior is unaffected either way.

        badge_colors: red > gold > green > None (see ModBadgeDB.tag_color).
        roll_arrows: "▲"/"▼"/None — T1 (maxed) never gets one; below T1 compares
        the roll against the RePoE tier range when tier is known, or the hub
        meta's observed value_min/value_max when it isn't."""
        n = len(rows)
        badge_colors: list = [None] * n
        roll_arrows: list = [None] * n
        if item.rarity != Rarity.RARE:
            return badge_colors, roll_arrows

        meta_db = self._get_meta_db()
        slot = mod_badge.slot_for_item(item.item_class, item.base_type)
        archetype = self._config.get("mod_badge_archetype", "all")
        badge_ready = bool(slot) and self._mod_badge.available()

        for i, (m, _sid) in enumerate(rows):
            values = getattr(m, "values", ()) or ((m.value,) if m.value is not None else ())
            bsid = (self._mod_badge.resolve_stat_id(m.text, getattr(m, "mod_type", None), self._mod_db)
                    if badge_ready else None)
            if bsid:
                badge_colors[i] = self._mod_badge.tag_color(bsid, slot, archetype, meta_db)

            anno = annos.get(getattr(m, "group", -1)) or {}
            tier = anno.get("tier", 0)
            if tier == 1 or not values:
                continue   # maxed already (nothing more to add), or no roll number to compare
            if tier:
                rng = meta_db.tier_range(item.base_type, m.text, tier)
                roll_arrows[i] = mod_badge.tier_roll_arrow(values, rng, self._mod_badge.rule("roll_pct", 0.25))
            elif bsid:
                roll_arrows[i] = self._mod_badge.roll_indicator_fallback(bsid, slot, archetype, values)

        return badge_colors, roll_arrows

    def _open_mod_picker(self, item, rows, annos=None, summary="", badge_colors=None,
                         roll_arrows=None, affixes=None) -> None:
        """เปิด popup เลือก mod (ต้องเรียกบน main thread เท่านั้น)."""
        from .mod_picker import ModPickerWindow

        def _on_search(stat_filters: list) -> None:
            def _go():
                try:
                    url = open_trade(item, self._mod_db, self._league_var.get(),
                                     self._profile, custom_stats=stat_filters)
                    debug.event(f"F5 picker search '{item.item_name}' "
                                f"filters={len(stat_filters)} url={url[:80]}")
                    self._root.after_idle(
                        lambda n=item.item_name: self._log(f"🔎 เปิด trade: {n}", "ok"))
                except Exception as e:
                    log.exception("mod picker search error")
                    self._root.after_idle(lambda err=e: self._log(f"✗ F5: {err}", "err"))
            threading.Thread(target=_go, daemon=True, name="F5PickerSearch").start()

        self._log(f"🧩 เลือก mod: {item.item_name}", "info")
        ModPickerWindow(self._root, item, rows, on_search=_on_search,
                        annos=annos, summary=summary, badge_colors=badge_colors,
                        roll_arrows=roll_arrows, affixes=affixes)

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
        self._league_paths = {}
        self._scanner = None
        self._league_cb.configure(values=self._profile.default_leagues)
        self._clear_all()
        self._fetch_leagues_for_current_gv(auto_pick=self._config.get("auto_league", True))

    def _fetch_leagues_for_gv(self, game_version: str) -> dict:
        """{"main": {league, path}, "hardcore": {league, path}|None, "events": [...]}
        — routing table read from the hub's index.json (hub_client.get_league_files)."""
        return hub_client.get_league_files(game_version)

    def _fetch_leagues_for_current_gv(self, auto_pick: bool = False) -> None:
        self._log("⟳ ดึงรายชื่อ league จาก hub…", "info")
        gv = self._gv_var.get()

        def _run():
            try:
                league_files = self._fetch_leagues_for_gv(gv)
                self._root.after_idle(
                    lambda: self._update_league_menu(league_files, auto_pick=auto_pick))
            except Exception as e:
                self._root.after_idle(
                    lambda err=e: self._log(f"✗ ดึง league ไม่ได้: {err}", "err"))
                # hub ล่ม/ต่อไม่ได้ — ยังลองโหลดจาก disk cache เดิม (ถ้ามี) แทนที่จะค้างว่างเปล่า
                self._root.after_idle(self._load_prices_async)

        threading.Thread(target=_run, daemon=True).start()

    def _update_league_menu(self, league_files: dict, auto_pick: bool = False) -> None:
        main = league_files.get("main") or {}
        hardcore = league_files.get("hardcore")
        events = league_files.get("events") or []

        if not main.get("league"):
            self._log("✗ hub ไม่มีข้อมูลลีกสำหรับเกมนี้ — ลองโหลดจาก disk cache เดิม", "err")
            self._load_prices_async()
            return

        self._league_paths = {main["league"]: main["path"]}
        if hardcore:
            self._league_paths[hardcore["league"]] = hardcore["path"]
        for e in events:
            self._league_paths[e["league"]] = e["path"]

        leagues = list(self._league_paths.keys())
        self._league_cb.configure(values=leagues)

        if auto_pick:
            picked = self._pick_league(main, hardcore)
        else:
            current = self._league_var.get()
            picked = current if current in leagues else main["league"]

        self._league_var.set(picked)   # เปลี่ยนหรือไม่เปลี่ยนก็ fire trace → _load_prices_async เสมอ
        self._log(f"✓ พบ {len(leagues)} leagues", "ok")

    def _pick_league(self, main: dict, hardcore: Optional[dict]) -> str:
        pref_hc = self._config.get("prefer_hardcore", False)
        if pref_hc:
            if hardcore:
                debug.event(f"auto-league pref_hc=True picked={hardcore['league']}")
                return hardcore["league"]
            self._log("⚠ ไม่มี Hardcore league ให้ใช้ตอนนี้ — ใช้ main league แทน", "warn")
        debug.event(f"auto-league pref_hc={pref_hc} picked={main['league']}")
        return main["league"]

    def _load_prices_async(self) -> None:
        league = self._league_var.get() or (
            self._profile.default_leagues[0] if self._profile.default_leagues else ""
        )
        if not league:
            return
        path = self._league_paths.get(league) or f"{self._profile.game_version}/prices/latest.json"
        self._config.set("league", league)
        self._log(f"⟳ กำลังโหลดราคา ({league})…", "info")

        def _on_done(snapshot):
            count = len(snapshot.entries) if snapshot else 0
            degraded = self._repo.degraded()
            def _update():
                self._scanner = Scanner(self._repo)
                debug.event(f"hub loaded entries={count} league={league}")
                if count == 0:
                    self._log(f"⚠ 0 รายการ ({league}) — ลอง Refresh Prices", "warn")
                else:
                    self._log(f"✓ พร้อม — {count} รายการ ({league})", "ok")
                if degraded:
                    self._log(f"⚠ {len(degraded)} หมวดโหลด 0 — ดู log", "warn")
            self._root.after_idle(_update)

        def _on_error(exc):
            self._root.after_idle(lambda: self._log(f"✗ โหลดราคาไม่สำเร็จ: {exc}", "err"))

        self._repo.load_async(league, path, on_done=_on_done, on_error=_on_error)

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
