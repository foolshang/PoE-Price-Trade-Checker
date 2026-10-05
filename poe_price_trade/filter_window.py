"""Filter Generator window — same visual style/helpers as settings.py."""
from __future__ import annotations
import logging
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Callable, Optional

from . import filter_gen, hub_client
from .config import AppConfig
from .neversink_source import LEVELS

log = logging.getLogger(__name__)

_BG = "#1C1C1C"
_FG = "#E8D5A0"
_ACCENT = "#C8A050"
_INPUT_BG = "#2A2A2A"
_BUTTON_BG = "#3A3020"
_PANEL_FONT = ("Segoe UI", 9)
_SMALL_FONT = ("Segoe UI", 8)
_RARITIES = ["Normal", "Magic", "Rare", "Unique"]
_MONO_FONT = ("Consolas", 8)

_STRICTNESS_VALUES = [f"{i} - {lvl}" for i, lvl in enumerate(LEVELS)]


class FilterGenWindow:
    def __init__(self, parent: tk.Misc, config: AppConfig, game_version: str,
                 on_generate: Optional[Callable[[bool], None]] = None,
                 hub_loader: Optional[Callable[[], dict]] = None,
                 *, as_toplevel: bool = True, show_auto_regen: bool = True):
        self._config = config
        self._game_version = game_version
        self._on_generate = on_generate
        self._as_toplevel = as_toplevel
        self._show_auto_regen = show_auto_regen
        self._hub_loader = hub_loader
        self._cat_exclude: dict[str, list[str]] = {}
        self._custom_entries: list[dict] = []   # {"name", "rarities"} = source of truth
        self._refine_win: Optional[tk.Toplevel] = None
        self._rules = filter_gen.load_rules(config.app_dir())

        if as_toplevel:
            self._win = tk.Toplevel(parent)
            self._win.title("PoE Price & Trade Checker — Filter Generator")
            self._win.configure(bg=_BG)
            self._win.resizable(False, False)
            self._win.protocol("WM_DELETE_WINDOW", self._win.destroy)
        else:
            self._win = parent          # build into the frame/root handed in

        self._vars: dict[str, tk.Variable] = {}
        self._build()
        self._load_from_config()

    # ------------------------------------------------------------------

    def _lbl(self, parent, text, row, col, **kw):
        tk.Label(parent, text=text, bg=_BG, fg=_FG, font=_PANEL_FONT, **kw).grid(
            row=row, column=col, sticky="w", padx=6, pady=3)

    def _entry(self, parent, key: str, row, col, width=10):
        var = tk.StringVar()
        self._vars[key] = var
        e = tk.Entry(parent, textvariable=var, bg=_INPUT_BG, fg=_FG, insertbackground=_FG,
                     relief=tk.FLAT, font=_PANEL_FONT, width=width)
        e.grid(row=row, column=col, sticky="w", padx=6, pady=3)
        return e

    def _combo(self, parent, key: str, values: list, row, col, width=18):
        var = tk.StringVar()
        self._vars[key] = var
        cb = ttk.Combobox(parent, textvariable=var, values=values, width=width,
                          state="readonly", font=_PANEL_FONT)
        cb.grid(row=row, column=col, sticky="w", padx=6, pady=3)
        return cb

    def _check(self, parent, key: str, text: str, row, col, columnspan=2):
        var = tk.BooleanVar()
        self._vars[key] = var
        tk.Checkbutton(parent, text=text, variable=var,
                       bg=_BG, fg=_FG, selectcolor="#2A2020", activebackground=_BG,
                       font=_PANEL_FONT).grid(row=row, column=col, columnspan=columnspan,
                                              sticky="w", padx=6, pady=3)
        return var

    def _btn(self, parent, text, cmd, side=None, **grid_kw):
        b = tk.Button(parent, text=text, command=cmd, bg=_BUTTON_BG, fg=_FG,
                     activebackground=_ACCENT, activeforeground="#000",
                     relief=tk.FLAT, font=_PANEL_FONT, padx=8, pady=3, cursor="hand2")
        if side is not None:
            b.pack(side=side, padx=4)
        elif grid_kw:
            b.grid(**grid_kw)
        return b

    def _sound_row(self, parent, key: str, label: str, row: int) -> None:
        self._lbl(parent, label, row, 0)
        var = tk.StringVar()
        self._vars[key] = var
        tk.Entry(parent, textvariable=var, bg=_INPUT_BG, fg=_FG, insertbackground=_FG,
                 relief=tk.FLAT, font=_PANEL_FONT, width=28, state="readonly").grid(
            row=row, column=1, sticky="w", padx=6, pady=3)
        btn_frame = tk.Frame(parent, bg=_BG)
        btn_frame.grid(row=row, column=2, sticky="w")
        self._btn(btn_frame, "Browse…", lambda k=key: self._browse_sound(k), side=tk.LEFT)
        self._btn(btn_frame, "Clear", lambda k=key: self._vars[k].set(""), side=tk.LEFT)

    def _browse_sound(self, key: str) -> None:
        path = filedialog.askopenfilename(
            title="Select alert sound",
            filetypes=[("Sound files", "*.mp3 *.wav"), ("All files", "*.*")])
        if path:
            self._vars[key].set(path)

    # ------------------------------------------------------------------

    def _build(self) -> None:
        f = tk.Frame(self._win, bg=_BG, padx=10, pady=8)
        f.pack(fill=tk.BOTH, expand=True)

        tk.Label(f, text=f"Filter Generator — {self._game_version.upper()}", bg=_BG, fg=_ACCENT,
                 font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=3, pady=(0, 8))

        row = 1
        self._lbl(f, "NeverSink Strictness:", row, 0)
        self._combo(f, "strictness", _STRICTNESS_VALUES, row, 1, width=18)
        row += 1

        self._lbl(f, "Tier thresholds (chaos, fallback):", row, 0)
        row += 1
        tier_frame = tk.Frame(f, bg=_BG)
        tier_frame.grid(row=row, column=0, columnspan=3, sticky="w", padx=6)
        for i, name in enumerate(("S", "A", "B", "C")):
            tk.Label(tier_frame, text=f"{name}:", bg=_BG, fg=_FG, font=_PANEL_FONT).grid(
                row=0, column=i * 2, sticky="w", padx=(0 if i == 0 else 8, 2))
            var = tk.StringVar()
            self._vars[f"tier_{name.lower()}"] = var
            tk.Entry(tier_frame, textvariable=var, bg=_INPUT_BG, fg=_FG, insertbackground=_FG,
                     relief=tk.FLAT, font=_PANEL_FONT, width=8).grid(row=0, column=i * 2 + 1)
        row += 1
        tk.Label(f, text="(used only when Divine Orb's own price is unavailable — normal tiering "
                          "is a % of Divine, edit min_divine_pct in filter_gen_rules.json)",
                 bg=_BG, fg="#666", font=_SMALL_FONT, wraplength=420, justify=tk.LEFT).grid(
            row=row, column=0, columnspan=3, sticky="w", padx=6)
        row += 1

        tk.Label(f, text="Alert sounds (S/A/B — C is always silent):", bg=_BG, fg=_FG,
                 font=_PANEL_FONT).grid(row=row, column=0, columnspan=3, sticky="w", padx=6, pady=(8, 2))
        row += 1
        self._sound_row(f, "sound_s", "Tier S sound:", row); row += 1
        self._sound_row(f, "sound_a", "Tier A sound:", row); row += 1
        self._sound_row(f, "sound_b", "Tier B sound:", row); row += 1

        self._lbl(f, "Game folder override:", row, 0)
        var = tk.StringVar()
        self._vars["game_dir"] = var
        tk.Entry(f, textvariable=var, bg=_INPUT_BG, fg=_FG, insertbackground=_FG,
                 relief=tk.FLAT, font=_PANEL_FONT, width=28).grid(row=row, column=1, sticky="w", padx=6, pady=3)
        self._btn(f, "Browse…", self._browse_game_dir, row=row, column=2)
        row += 1
        tk.Label(f, text="(leave blank to auto-detect Documents\\My Games\\...)", bg=_BG, fg="#666",
                 font=_SMALL_FONT).grid(row=row, column=0, columnspan=3, sticky="w", padx=6)
        row += 1

        tk.Label(f, text="Whitelist mode (show only):", bg=_BG, fg=_FG,
                 font=_PANEL_FONT).grid(row=row, column=0, columnspan=3, sticky="w", padx=6, pady=(8, 2))
        row += 1
        self._check(f, "whitelist_enabled",
                    "โหมดโชว์เฉพาะ (whitelist) — ซ่อนที่เหลือ", row, 0, columnspan=3)
        row += 1
        self._check(f, "whitelist_gold", "Gold", row, 0, columnspan=1)
        gold_row = tk.Frame(f, bg=_BG)
        gold_row.grid(row=row, column=1, columnspan=2, sticky="w")
        tk.Label(gold_row, text="จำนวน ≥", bg=_BG, fg=_FG, font=_PANEL_FONT).grid(row=0, column=0)
        self._entry(gold_row, "whitelist_gold_min", 0, 1, width=6)
        row += 1
        tk.Label(f, text="หมวด (โชว์ทั้งหมวด):", bg=_BG, fg=_FG, font=_SMALL_FONT).grid(
            row=row, column=0, columnspan=3, sticky="w", padx=6)
        row += 1
        cat_frame = tk.Frame(f, bg=_BG)
        cat_frame.grid(row=row, column=0, columnspan=3, sticky="w", padx=6)
        for i, cat in enumerate(filter_gen.WHITELIST_CATEGORIES.get(self._game_version, [])):
            self._check(cat_frame, f"whitelist_cat_{cat}", cat, i // 3, i % 3, columnspan=1)
        n_cats = len(filter_gen.WHITELIST_CATEGORIES.get(self._game_version, []))
        # not a hub category: own key, no refine list (offline "Rarity Unique" block)
        self._check(cat_frame, "whitelist_unique_all", "Unique (ทุกตัว)",
                    n_cats // 3, n_cats % 3, columnspan=1)
        self._btn(cat_frame, "ปรับรายการในหมวด…", self._open_cat_refine,
                  row=(n_cats + 3) // 3, column=0, columnspan=3, sticky="w", pady=(4, 0))
        row += 1
        tk.Label(f, text="ชื่อที่พิมพ์เอง (contains) + เลือก rarity:", bg=_BG, fg=_FG,
                 font=_SMALL_FONT).grid(row=row, column=0, columnspan=3, sticky="w", padx=6, pady=(4, 0))
        row += 1
        custom_frame = tk.Frame(f, bg=_BG)
        custom_frame.grid(row=row, column=0, columnspan=3, sticky="w", padx=6)
        self._custom_var = tk.StringVar()
        entry = tk.Entry(custom_frame, textvariable=self._custom_var, bg=_INPUT_BG, fg=_FG,
                         insertbackground=_FG, relief=tk.FLAT, font=_PANEL_FONT, width=24)
        entry.grid(row=0, column=0, padx=(0, 4))
        entry.bind("<Return>", lambda _e: self._add_custom())
        self._btn(custom_frame, "เพิ่ม", self._add_custom, row=0, column=1)
        self._btn(custom_frame, "ลบที่เลือก", self._remove_custom, row=0, column=2)
        # rarity picker: used by "เพิ่ม" and "ตั้ง rarity ที่เลือก"
        rar_frame = tk.Frame(custom_frame, bg=_BG)
        rar_frame.grid(row=1, column=0, columnspan=3, sticky="w", pady=(3, 0))
        self._cust_rar = {}
        for r in _RARITIES:
            v = tk.BooleanVar(value=(r == "Normal"))   # default = Normal
            self._cust_rar[r] = v
            tk.Checkbutton(rar_frame, text=r, variable=v, bg=_BG, fg=_FG,
                           selectcolor="#2A2020", activebackground=_BG,
                           font=_SMALL_FONT).pack(side=tk.LEFT)
        self._btn(rar_frame, "ตั้ง rarity ที่เลือก", self._set_custom_rarity, side=tk.LEFT)
        self._custom_list = tk.Listbox(custom_frame, bg=_INPUT_BG, fg=_FG, font=_PANEL_FONT,
                                       height=4, width=44, relief=tk.FLAT, selectmode=tk.EXTENDED,
                                       exportselection=False)
        self._custom_list.grid(row=2, column=0, columnspan=3, sticky="w", pady=(3, 0))
        self._custom_list.bind("<<ListboxSelect>>", self._on_custom_select)
        row += 1
        tk.Label(f, text="(เปิดโหมดนี้ = ข้าม filter ปกติ, generate เฉพาะที่เลือก)", bg=_BG, fg="#666",
                 font=_SMALL_FONT).grid(row=row, column=0, columnspan=3, sticky="w", padx=6)
        row += 1

        # ---- Gem filter ----
        tk.Label(f, text="Gem:", bg=_BG, fg=_FG, font=_SMALL_FONT).grid(
            row=row, column=0, columnspan=3, sticky="w", padx=6, pady=(4, 0))
        row += 1
        gem_frame = tk.Frame(f, bg=_BG)
        gem_frame.grid(row=row, column=0, columnspan=3, sticky="w", padx=6)
        self._gem_level_vars = {}        # base_type -> StringVar(level)
        self._gem_enable_vars = {}       # base_type -> BooleanVar
        self._gem_all_names: list[str] = []     # lazy-loaded from hub (poe1 autocomplete)
        uncut = filter_gen.WHITELIST_GEM_UNCUT.get(self._game_version, [])
        if uncut:
            # poe2: one checkbox + minimum level per uncut type
            for i, base in enumerate(uncut):
                ev = tk.BooleanVar()
                self._gem_enable_vars[base] = ev
                tk.Checkbutton(gem_frame, text=base, variable=ev, bg=_BG, fg=_FG,
                               selectcolor="#2A2020", activebackground=_BG,
                               font=_SMALL_FONT).grid(row=i, column=0, sticky="w")
                tk.Label(gem_frame, text="level ≥", bg=_BG, fg=_FG,
                         font=_SMALL_FONT).grid(row=i, column=1, sticky="w", padx=(6, 2))
                lv = tk.StringVar(value="1")
                self._gem_level_vars[base] = lv
                tk.Entry(gem_frame, textvariable=lv, bg=_INPUT_BG, fg=_FG, width=4,
                         insertbackground=_FG, relief=tk.FLAT,
                         font=_PANEL_FONT).grid(row=i, column=2, sticky="w")
        else:
            # poe1: type a gem name + autocomplete + add several
            self._gem_name_var = tk.StringVar()
            ge = tk.Entry(gem_frame, textvariable=self._gem_name_var, bg=_INPUT_BG, fg=_FG,
                          insertbackground=_FG, relief=tk.FLAT, font=_PANEL_FONT, width=24)
            ge.grid(row=0, column=0, padx=(0, 4))
            ge.bind("<KeyRelease>", self._gem_suggest)
            ge.bind("<Return>", lambda _e: self._gem_add())
            self._btn(gem_frame, "เพิ่ม", self._gem_add, row=0, column=1)
            self._btn(gem_frame, "ลบที่เลือก", self._gem_remove, row=0, column=2)
            # suggestions — click = put the name into the entry, double-click = add it to the list
            self._gem_sugg = tk.Listbox(gem_frame, bg=_INPUT_BG, fg=_FG, font=_PANEL_FONT,
                                        height=5, width=36, relief=tk.FLAT, exportselection=False)
            self._gem_sugg.grid(row=1, column=0, columnspan=3, sticky="w", pady=(3, 0))
            self._gem_sugg.bind("<ButtonRelease-1>", self._gem_pick_sugg)        # click once = fill the entry
            self._gem_sugg.bind("<Double-Button-1>", lambda _e: self._gem_add())  # double-click = add to list
            # chosen names
            self._gem_list = tk.Listbox(gem_frame, bg=_INPUT_BG, fg=_FG, font=_PANEL_FONT,
                                        height=4, width=36, relief=tk.FLAT,
                                        selectmode=tk.EXTENDED, exportselection=False)
            self._gem_list.grid(row=2, column=0, columnspan=3, sticky="w", pady=(3, 0))
        row += 1

        if self._show_auto_regen:
            self._lbl(f, "Staleness limit (hours):", row, 0)
            self._entry(f, "staleness_hours", row, 1, width=8)
            row += 1
            self._lbl(f, "Regen cooldown (min):", row, 0)
            self._entry(f, "regen_cooldown_min", row, 1, width=8)
            row += 1
            self._check(f, "auto_regen", "Auto-regenerate when hub prices move tiers", row, 0, columnspan=3)
            row += 1
        else:
            # hidden, but load/save/generate still read these vars -> keep defaults
            self._vars["staleness_hours"] = tk.StringVar(value="24")
            self._vars["regen_cooldown_min"] = tk.StringVar(value="60")
            self._vars["auto_regen"] = tk.BooleanVar(value=False)

        tk.Label(f, text="Status:", bg=_BG, fg=_FG, font=_PANEL_FONT).grid(
            row=row, column=0, sticky="nw", pady=(8, 2))
        log_frame = tk.Frame(f, bg="#111")
        log_frame.grid(row=row, column=1, columnspan=2, sticky="ew", pady=(8, 2))
        self._log_text = tk.Text(log_frame, bg="#111", fg="#AADDAA", font=_MONO_FONT,
                                 width=40, height=6, relief=tk.FLAT, state=tk.DISABLED, wrap=tk.WORD)
        self._log_text.pack(fill=tk.BOTH)
        self._log_text.tag_config("ok", foreground="#88DD88")
        self._log_text.tag_config("err", foreground="#DD6666")
        self._log_text.tag_config("warn", foreground="#DDCC66")
        self._log_text.tag_config("info", foreground="#AACCFF")
        row += 1

        btn_frame = tk.Frame(f, bg=_BG)
        btn_frame.grid(row=row, column=0, columnspan=3, pady=(8, 0))
        self._btn(btn_frame, "Generate Now", self._on_generate_clicked, side=tk.LEFT)
        self._btn(btn_frame, "Refresh NeverSink Base", self._on_refresh_clicked, side=tk.LEFT)
        self._btn(btn_frame, "Save Settings", self._save, side=tk.LEFT)
        if self._as_toplevel:
            self._btn(btn_frame, "Close", self._win.destroy, side=tk.LEFT)

    def _open_cat_refine(self) -> None:
        """Popup: per-category checklist. Checked = shown (default), unchecked =
        excluded; only the exclude lists are stored (self._cat_exclude)."""
        if self._refine_win is not None:
            try:
                if self._refine_win.winfo_exists():
                    self._refine_win.lift()
                    return
            except tk.TclError:
                pass
        cats = [c for c in filter_gen.WHITELIST_CATEGORIES.get(self._game_version, [])
                if self._vars[f"whitelist_cat_{c}"].get()]
        if not cats:
            self.log("ติ๊กหมวดก่อน แล้วค่อยปรับรายการ", "warn")
            return
        if self._hub_loader is None:
            self.log("ต้องต่อ hub เพื่อดูรายการ: ไม่มี hub loader", "warn")
            return
        try:
            hub_data = self._hub_loader()
        except Exception as e:
            self.log(f"ต้องต่อ hub เพื่อดูรายการ: {e}", "warn")
            return

        top = tk.Toplevel(self._win)
        self._refine_win = top
        top.title("ปรับรายการในหมวด")
        top.configure(bg=_BG)
        top.attributes("-topmost", True)

        sel = tk.StringVar(value=cats[0])
        q = tk.StringVar()
        top_row = tk.Frame(top, bg=_BG)
        top_row.pack(fill=tk.X, padx=8, pady=6)
        menu = tk.OptionMenu(top_row, sel, *cats)
        menu.config(bg=_BUTTON_BG, fg=_FG, activebackground=_ACCENT, relief=tk.FLAT,
                    highlightthickness=0, font=_PANEL_FONT)
        menu.pack(side=tk.LEFT)
        tk.Entry(top, textvariable=q, bg=_INPUT_BG, fg=_FG, insertbackground=_FG,
                 relief=tk.FLAT, font=_PANEL_FONT).pack(fill=tk.X, padx=8)

        wrap = tk.Frame(top, bg=_BG)
        wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
        canvas = tk.Canvas(wrap, bg=_BG, highlightthickness=0, width=320, height=340)
        scrollbar = tk.Scrollbar(wrap, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        body = tk.Frame(canvas, bg=_BG)
        canvas.create_window((0, 0), window=body, anchor="nw")

        def on_wheel(event) -> None:
            canvas.yview_scroll(int(-event.delta / 120), "units")
        canvas.bind("<MouseWheel>", on_wheel)
        body.bind("<MouseWheel>", on_wheel)

        item_vars: dict[str, tk.BooleanVar] = {}

        def all_names(cat: str) -> list[str]:
            return sorted(set(filter_gen.names_in_categories(hub_data, [cat])))

        def toggle(nm: str) -> None:
            cat = sel.get()
            ex = set(self._cat_exclude.get(cat, []))
            if item_vars[nm].get():
                ex.discard(nm)
            else:
                ex.add(nm)
            if ex:
                self._cat_exclude[cat] = sorted(ex)
            else:
                self._cat_exclude.pop(cat, None)

        def rebuild(*_a) -> None:
            cat = sel.get()
            excl = set(self._cat_exclude.get(cat, []))
            kw = q.get().strip().lower()
            for w in body.winfo_children():
                w.destroy()
            item_vars.clear()
            for nm in all_names(cat):
                if kw and kw not in nm.lower():
                    continue
                v = tk.BooleanVar(value=(nm not in excl))
                item_vars[nm] = v
                cb = tk.Checkbutton(body, text=nm, variable=v, bg=_BG, fg=_FG,
                                    selectcolor="#2A2020", activebackground=_BG,
                                    font=_PANEL_FONT, anchor="w",
                                    command=lambda n=nm: toggle(n))
                cb.pack(fill=tk.X, anchor="w")
                cb.bind("<MouseWheel>", on_wheel)
            body.update_idletasks()
            canvas.configure(scrollregion=(0, 0, body.winfo_reqwidth(), body.winfo_reqheight()))
            canvas.yview_moveto(0)

        def select_all() -> None:
            self._cat_exclude.pop(sel.get(), None)
            rebuild()

        def select_none() -> None:
            self._cat_exclude[sel.get()] = all_names(sel.get())
            rebuild()

        btn_row = tk.Frame(top, bg=_BG)
        btn_row.pack(pady=(0, 6))
        self._btn(btn_row, "เลือกทั้งหมด", select_all, side=tk.LEFT)
        self._btn(btn_row, "ไม่เลือกเลย", select_none, side=tk.LEFT)
        self._btn(btn_row, "ปิด", top.destroy, side=tk.LEFT)

        sel.trace_add("write", rebuild)
        q.trace_add("write", rebuild)
        rebuild()
        # exposed for headless tests
        top._refine = {"sel": sel, "q": q, "items": item_vars, "toggle": toggle,
                       "select_all": select_all, "select_none": select_none}

    @staticmethod
    def _rarity_tag(rarities) -> str:
        abbr = {"Normal": "N", "Magic": "M", "Rare": "R", "Unique": "U"}
        rs = [r for r in _RARITIES if r in set(rarities)]
        return "/".join(abbr[r] for r in rs) if rs else "N"

    def _render_custom(self) -> None:
        self._custom_list.delete(0, tk.END)
        for e in self._custom_entries:
            self._custom_list.insert(
                tk.END, f"{e['name']}   [{self._rarity_tag(e['rarities'])}]")

    def _current_rarities(self) -> list:
        rs = [r for r in _RARITIES if self._cust_rar[r].get()]
        return rs or ["Normal"]       # never empty

    def _gem_load_names(self) -> None:
        if self._gem_all_names:
            return
        try:
            data = hub_client.get_gems(self._game_version) or {}
            seen, out = set(), []
            for g in data.get("gems", []):
                nm = (g.get("display_name") or "").strip()
                if not nm or nm == "..." or nm.lower() in seen:
                    continue
                seen.add(nm.lower())
                out.append(nm)
            self._gem_all_names = sorted(out)
        except Exception as e:
            self.log(f"⚠ โหลดรายชื่อ gem ไม่ได้ (พิมพ์เองได้): {e}", "warn")
            self._gem_all_names = []

    def _gem_suggest(self, _e=None) -> None:
        self._gem_load_names()
        kw = self._gem_name_var.get().strip().lower()
        self._gem_sugg.delete(0, tk.END)
        if not kw:
            return
        for nm in self._gem_all_names:
            if kw in nm.lower():
                self._gem_sugg.insert(tk.END, nm)
                if self._gem_sugg.size() >= 20:
                    break

    def _gem_pick_sugg(self, _e=None) -> None:
        sel = self._gem_sugg.curselection()
        if sel:
            self._gem_name_var.set(self._gem_sugg.get(sel[0]))

    def _gem_add(self) -> None:
        nm = self._gem_name_var.get().strip()
        if not nm:
            return
        existing = {x.lower() for x in self._gem_list.get(0, tk.END)}
        if nm.lower() not in existing:
            self._gem_list.insert(tk.END, nm)
        self._gem_name_var.set("")
        self._gem_sugg.delete(0, tk.END)

    def _gem_remove(self) -> None:
        for idx in reversed(self._gem_list.curselection()):
            self._gem_list.delete(idx)

    def _add_custom(self) -> None:
        text = self._custom_var.get().strip()
        if not text:
            return
        if any(e["name"].lower() == text.lower() for e in self._custom_entries):
            self._custom_var.set("")
            return
        self._custom_entries.append({"name": text, "rarities": self._current_rarities()})
        self._custom_var.set("")
        self._render_custom()

    def _remove_custom(self) -> None:
        for idx in sorted(self._custom_list.curselection(), reverse=True):
            if 0 <= idx < len(self._custom_entries):
                del self._custom_entries[idx]
        self._render_custom()

    def _on_custom_select(self, _e=None) -> None:
        # selecting a name loads its rarities back into the checkboxes
        sel = self._custom_list.curselection()
        if not sel or sel[0] >= len(self._custom_entries):
            return
        rs = set(self._custom_entries[sel[0]]["rarities"])
        for r in _RARITIES:
            self._cust_rar[r].set(r in rs)

    def _set_custom_rarity(self) -> None:
        # apply the currently ticked rarities to every selected name
        sel = list(self._custom_list.curselection())
        if not sel:
            return
        rs = self._current_rarities()
        for idx in sel:
            if 0 <= idx < len(self._custom_entries):
                self._custom_entries[idx]["rarities"] = list(rs)
        self._render_custom()
        for i in sel:
            self._custom_list.selection_set(i)

    def _browse_game_dir(self) -> None:
        path = filedialog.askdirectory(title="Select the game's filter folder")
        if path:
            self._vars["game_dir"].set(path)

    # ------------------------------------------------------------------

    def log(self, msg: str, tag: str = "info") -> None:
        try:
            widget = self._log_text
            widget.configure(state=tk.NORMAL)
            widget.insert(tk.END, msg + "\n", tag)
            widget.see(tk.END)
            widget.configure(state=tk.DISABLED)
        except Exception:
            pass

    # ------------------------------------------------------------------

    def _load_from_config(self) -> None:
        fg = dict(self._config.get("filter_gen", {}) or {})
        strictness = fg.get(f"strictness_{self._game_version}", 2)
        strictness = strictness if 0 <= strictness < len(_STRICTNESS_VALUES) else 2
        self._vars["strictness"].set(_STRICTNESS_VALUES[strictness])

        tiers_cfg = self._rules.get("tiers", [])
        for t in tiers_cfg:
            key = f"tier_{t['name'].lower()}"
            if key in self._vars:
                self._vars[key].set(str(t.get("min_chaos", "")))

        self._vars["sound_s"].set(fg.get("sound_s", ""))
        self._vars["sound_a"].set(fg.get("sound_a", ""))
        self._vars["sound_b"].set(fg.get("sound_b", ""))
        self._vars["game_dir"].set(fg.get(f"game_dir_{self._game_version}", ""))
        self._vars["staleness_hours"].set(str(fg.get("staleness_hours", 24)))
        self._vars["regen_cooldown_min"].set(str(fg.get("regen_cooldown_min", 60)))
        self._vars["auto_regen"].set(bool(fg.get("auto_regen", True)))
        self._vars["whitelist_enabled"].set(bool(fg.get("whitelist_enabled", False)))
        self._vars["whitelist_gold"].set(bool(fg.get("whitelist_gold", False)))
        self._vars["whitelist_gold_min"].set(str(fg.get("whitelist_gold_min", 0)))
        self._vars["whitelist_unique_all"].set(bool(fg.get("whitelist_unique_all", False)))
        cats = set(fg.get(f"whitelist_cats_{self._game_version}", []))
        for cat in filter_gen.WHITELIST_CATEGORIES.get(self._game_version, []):
            self._vars[f"whitelist_cat_{cat}"].set(cat in cats)
        self._cat_exclude = {
            str(c): list(v) for c, v in
            dict(fg.get(f"whitelist_cat_exclude_{self._game_version}", {}) or {}).items() if v}
        self._custom_entries = []
        for item in fg.get(f"whitelist_custom_{self._game_version}", []):
            if isinstance(item, str):                       # pre-0.8.2 = any rarity (nothing disappears)
                self._custom_entries.append({"name": item, "rarities": list(_RARITIES)})
            elif isinstance(item, dict) and item.get("name"):
                rs = [r for r in _RARITIES if r in set(item.get("rarities") or [])]
                self._custom_entries.append({"name": item["name"], "rarities": rs or ["Normal"]})
        self._render_custom()
        # gem filter
        if filter_gen.WHITELIST_GEM_UNCUT.get(self._game_version):   # poe2
            saved = fg.get(f"whitelist_gem_uncut_{self._game_version}", {}) or {}
            for base, ev in self._gem_enable_vars.items():
                ev.set(base in saved)
                if base in saved:
                    self._gem_level_vars[base].set(str(saved[base]))
        else:                                                        # poe1
            self._gem_list.delete(0, tk.END)
            for nm in fg.get(f"whitelist_gem_names_{self._game_version}", []):
                self._gem_list.insert(tk.END, nm)

    def _save(self) -> dict:
        """Persist all fields (config.json's filter_gen dict + the
        filter_gen_rules.json tier-threshold override) and return the
        resolved settings dict the caller needs to actually generate."""
        fg = dict(self._config.get("filter_gen", {}) or {})

        strictness_str = self._vars["strictness"].get()
        strictness = int(strictness_str.split(" - ")[0]) if strictness_str else 2
        fg[f"strictness_{self._game_version}"] = strictness

        for t in self._rules.get("tiers", []):
            key = f"tier_{t['name'].lower()}"
            try:
                t["min_chaos"] = float(self._vars[key].get())
            except (ValueError, KeyError):
                pass
        filter_gen.save_rules(self._config.app_dir(), self._rules)

        fg["sound_s"] = self._vars["sound_s"].get()
        fg["sound_a"] = self._vars["sound_a"].get()
        fg["sound_b"] = self._vars["sound_b"].get()
        fg[f"game_dir_{self._game_version}"] = self._vars["game_dir"].get()
        try:
            fg["staleness_hours"] = float(self._vars["staleness_hours"].get())
        except ValueError:
            pass
        try:
            fg["regen_cooldown_min"] = float(self._vars["regen_cooldown_min"].get())
        except ValueError:
            pass
        fg["auto_regen"] = bool(self._vars["auto_regen"].get())
        fg["whitelist_enabled"] = bool(self._vars["whitelist_enabled"].get())
        fg["whitelist_gold"] = bool(self._vars["whitelist_gold"].get())
        fg["whitelist_unique_all"] = bool(self._vars["whitelist_unique_all"].get())
        try:
            fg["whitelist_gold_min"] = max(0, int(self._vars["whitelist_gold_min"].get() or 0))
        except ValueError:
            fg["whitelist_gold_min"] = 0
        if filter_gen.WHITELIST_GEM_UNCUT.get(self._game_version):   # poe2
            gem_out = {}
            for base, ev in self._gem_enable_vars.items():
                if ev.get():
                    try:
                        gem_out[base] = max(1, int(self._gem_level_vars[base].get() or 1))
                    except ValueError:
                        gem_out[base] = 1
            fg[f"whitelist_gem_uncut_{self._game_version}"] = gem_out
        else:                                                        # poe1
            fg[f"whitelist_gem_names_{self._game_version}"] = list(self._gem_list.get(0, tk.END))
        fg[f"whitelist_cat_exclude_{self._game_version}"] = {
            c: sorted(v) for c, v in self._cat_exclude.items() if v}
        fg[f"whitelist_cats_{self._game_version}"] = [
            cat for cat in filter_gen.WHITELIST_CATEGORIES.get(self._game_version, [])
            if self._vars[f"whitelist_cat_{cat}"].get()]
        fg[f"whitelist_custom_{self._game_version}"] = [
            {"name": e["name"], "rarities": list(e["rarities"])}
            for e in self._custom_entries]

        self._config.set("filter_gen", fg)
        self._config.save()
        return fg

    def _on_generate_clicked(self) -> None:
        self._save()
        if self._on_generate:
            self._on_generate(False)

    def _on_refresh_clicked(self) -> None:
        self._save()
        if self._on_generate:
            self._on_generate(True)
