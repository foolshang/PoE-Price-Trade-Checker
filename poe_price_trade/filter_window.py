"""Filter Generator window — same visual style/helpers as settings.py."""
from __future__ import annotations
import logging
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Callable, Optional

from . import filter_gen
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
_MONO_FONT = ("Consolas", 8)

_STRICTNESS_VALUES = [f"{i} - {lvl}" for i, lvl in enumerate(LEVELS)]


class FilterGenWindow:
    def __init__(self, parent: tk.Misc, config: AppConfig, game_version: str,
                 on_generate: Optional[Callable[[bool], None]] = None):
        self._config = config
        self._game_version = game_version
        self._on_generate = on_generate
        self._rules = filter_gen.load_rules(config.app_dir())

        self._win = tk.Toplevel(parent)
        self._win.title("PoE Price & Trade Checker — Filter Generator")
        self._win.configure(bg=_BG)
        self._win.resizable(False, False)
        self._win.protocol("WM_DELETE_WINDOW", self._win.destroy)

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
        cur_frame = tk.Frame(f, bg=_BG)
        cur_frame.grid(row=row, column=0, columnspan=3, sticky="w", padx=6)
        for i, (label, _bts) in enumerate(filter_gen.WHITELIST_CURRENCIES.get(self._game_version, [])):
            self._check(cur_frame, f"whitelist_cur_{label}", label, i // 3, i % 3, columnspan=1)
        row += 1
        self._check(f, "whitelist_gold", "Gold", row, 0, columnspan=3)
        row += 1
        tk.Label(f, text="หมวด (โชว์ทั้งหมวด):", bg=_BG, fg=_FG, font=_SMALL_FONT).grid(
            row=row, column=0, columnspan=3, sticky="w", padx=6)
        row += 1
        cat_frame = tk.Frame(f, bg=_BG)
        cat_frame.grid(row=row, column=0, columnspan=3, sticky="w", padx=6)
        for i, cat in enumerate(filter_gen.WHITELIST_CATEGORIES.get(self._game_version, [])):
            self._check(cat_frame, f"whitelist_cat_{cat}", cat, i // 3, i % 3, columnspan=1)
        row += 1
        min_frame = tk.Frame(f, bg=_BG)
        min_frame.grid(row=row, column=0, columnspan=3, sticky="w")
        self._check(min_frame, "whitelist_min_enabled", "ของขาย ≥", 0, 0, columnspan=1)
        self._entry(min_frame, "whitelist_min_value", 0, 1, width=6)
        self._combo(min_frame, "whitelist_min_unit", ["div", "ex"], 0, 2, width=5)
        row += 1
        self._check(f, "whitelist_unique_enabled",
                    "รวม unique ที่ขายถึงเกณฑ์ด้วย (โชว์ตาม base)", row, 0, columnspan=3)
        row += 1
        tk.Label(f, text="ชื่อที่พิมพ์เอง (contains, ทุก rarity):", bg=_BG, fg=_FG,
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
        self._custom_list = tk.Listbox(custom_frame, bg=_INPUT_BG, fg=_FG, font=_PANEL_FONT,
                                       height=4, width=36, relief=tk.FLAT, selectmode=tk.EXTENDED,
                                       exportselection=False)
        self._custom_list.grid(row=1, column=0, columnspan=3, sticky="w", pady=(3, 0))
        row += 1
        tk.Label(f, text="(เปิดโหมดนี้ = ข้าม filter ปกติ | unique โชว์ทุกตัวบน base ที่มีของแพง)", bg=_BG, fg="#666",
                 font=_SMALL_FONT).grid(row=row, column=0, columnspan=3, sticky="w", padx=6)
        row += 1

        self._lbl(f, "Staleness limit (hours):", row, 0)
        self._entry(f, "staleness_hours", row, 1, width=8)
        row += 1
        self._lbl(f, "Regen cooldown (min):", row, 0)
        self._entry(f, "regen_cooldown_min", row, 1, width=8)
        row += 1
        self._check(f, "auto_regen", "Auto-regenerate when hub prices move tiers", row, 0, columnspan=3)
        row += 1

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
        self._btn(btn_frame, "Close", self._win.destroy, side=tk.LEFT)

    def _add_custom(self) -> None:
        text = self._custom_var.get().strip()
        if not text:
            return
        existing = {t.lower() for t in self._custom_list.get(0, tk.END)}
        if text.lower() not in existing:
            self._custom_list.insert(tk.END, text)
        self._custom_var.set("")

    def _remove_custom(self) -> None:
        for idx in reversed(self._custom_list.curselection()):
            self._custom_list.delete(idx)

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
        self._vars["whitelist_min_enabled"].set(bool(fg.get("whitelist_min_enabled", False)))
        self._vars["whitelist_min_value"].set(str(fg.get("whitelist_min_value", "1")))
        self._vars["whitelist_min_unit"].set(fg.get("whitelist_min_unit", "div"))
        self._vars["whitelist_unique_enabled"].set(bool(fg.get("whitelist_unique_enabled", False)))
        selected = set(fg.get(f"whitelist_selected_{self._game_version}", []))
        # pre-0.8.0 configs stored Gold as a currency label
        self._vars["whitelist_gold"].set(bool(fg.get("whitelist_gold", "Gold" in selected)))
        cats = set(fg.get(f"whitelist_cats_{self._game_version}", []))
        for cat in filter_gen.WHITELIST_CATEGORIES.get(self._game_version, []):
            self._vars[f"whitelist_cat_{cat}"].set(cat in cats)
        self._custom_list.delete(0, tk.END)
        for name in fg.get(f"whitelist_custom_{self._game_version}", []):
            self._custom_list.insert(tk.END, name)
        for label, _bts in filter_gen.WHITELIST_CURRENCIES.get(self._game_version, []):
            self._vars[f"whitelist_cur_{label}"].set(label in selected)

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
        fg["whitelist_min_enabled"] = bool(self._vars["whitelist_min_enabled"].get())
        fg["whitelist_min_value"] = self._vars["whitelist_min_value"].get().strip() or "1"
        fg["whitelist_min_unit"] = self._vars["whitelist_min_unit"].get() or "div"
        fg["whitelist_unique_enabled"] = bool(self._vars["whitelist_unique_enabled"].get())
        fg["whitelist_gold"] = bool(self._vars["whitelist_gold"].get())
        fg[f"whitelist_cats_{self._game_version}"] = [
            cat for cat in filter_gen.WHITELIST_CATEGORIES.get(self._game_version, [])
            if self._vars[f"whitelist_cat_{cat}"].get()]
        fg[f"whitelist_custom_{self._game_version}"] = list(self._custom_list.get(0, tk.END))
        fg[f"whitelist_selected_{self._game_version}"] = [
            label for label, _bts in filter_gen.WHITELIST_CURRENCIES.get(self._game_version, [])
            if self._vars[f"whitelist_cur_{label}"].get()]

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
