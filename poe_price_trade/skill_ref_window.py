"""Skill Mod Reference window — UI for the new F4 mode (config.f4_mode ==
"skill_ref", default off, see app.py's _on_f4_scan). Style mirrors
mod_picker.py's ModPickerWindow (same Toplevel/color/font conventions) so it
looks consistent with the rest of the app. Data comes from SkillRefDB
(skill_ref.py), hub-only as of the v2 rewrite (2026-09-22) — see that
module's docstring for the real schema (per-skill mod files keyed by
(skill_type, skill), level-bracket toggle, real per-bracket population)."""
from __future__ import annotations
import tkinter as tk
from typing import Callable, Optional

from .skill_ref import SkillRefDB, Skill

_BG, _FG, _ACC = "#1C1C1C", "#E8D5A0", "#C8A050"
_DIM = "#777777"
_WARN = "#D08030"
_ENTRY_BG = "#2A2A2A"
_FONT = ("Segoe UI", 9)
_FONT_SMALL = ("Segoe UI", 8)
_FONT_BOLD = ("Segoe UI", 10, "bold")
_MAX_SUGGESTIONS = 8
# Local UI-only threshold for flagging a thin sample bracket — not from the
# hub. Anything below this still gets shown (the hub already published it),
# just with an honest "ข้อมูลน้อย" caption next to the population count.
_THIN_POPULATION = 50
# Max height of the scrollable mod/passive body before a scrollbar appears.
_MAX_BODY_H = 380


def _fmt_num(v: float) -> str:
    return f"{v:.0f}" if v == int(v) else f"{v:.1f}"


def _bracket_sort_key(bracket: str) -> int:
    try:
        return int(bracket.split("-", 1)[0])
    except Exception:
        return 0


class SkillRefWindow:
    def __init__(self, parent: tk.Misc, db: SkillRefDB, on_close: Optional[Callable[[], None]] = None):
        self._db = db
        self._on_close = on_close
        self._suggest_skills: list[Skill] = []
        self._current_skill: Optional[Skill] = None
        self._mods_by_bracket: dict[str, dict[str, list]] = {}
        self._passives_by_bracket: dict[str, list] = {}
        self._current_bracket: Optional[str] = None
        self._mods_by_slot: dict[str, list] = {}
        self._bracket_buttons: dict[str, tk.Label] = {}
        self._tab_buttons: dict[str, tk.Label] = {}

        win = tk.Toplevel(parent)
        self._win = win
        win.withdraw()                      # ซ่อนก่อน จัดตำแหน่งเสร็จค่อยโชว์ (กันกระพริบ)
        win.title("Skill Mod Reference")
        win.configure(bg=_BG)
        win.attributes("-topmost", True)
        win.resizable(False, False)

        tk.Label(win, text="Skill Mod Reference", bg=_BG, fg=_ACC, font=_FONT_BOLD).pack(
            anchor="w", padx=12, pady=(10, 4))

        if not db.available():
            tk.Label(win, text="⚠ โหลดข้อมูลจาก hub ไม่สำเร็จ — ลองปิดแล้วเปิดใหม่",
                     bg=_BG, fg=_WARN, font=_FONT_SMALL).pack(anchor="w", padx=12, pady=(0, 4))

        search = tk.Frame(win, bg=_BG)
        search.pack(fill=tk.X, padx=12)
        tk.Label(search, text="Skill:", bg=_BG, fg=_FG, font=_FONT).pack(side=tk.LEFT)
        self._skill_var = tk.StringVar()
        entry = tk.Entry(search, textvariable=self._skill_var, bg=_ENTRY_BG, fg=_FG,
                          insertbackground=_FG, relief=tk.FLAT, font=_FONT, width=28)
        entry.pack(side=tk.LEFT, padx=(6, 0), fill=tk.X, expand=True)

        self._suggest_list = tk.Listbox(
            win, bg=_ENTRY_BG, fg=_FG, font=_FONT, relief=tk.FLAT, height=0,
            selectbackground="#3A3020", activestyle="none", highlightthickness=0,
        )
        self._search_row = search
        self._suggest_list.pack(fill=tk.X, padx=12, pady=(2, 0), after=search)
        self._suggest_list.pack_forget()    # ซ่อนจนกว่าจะมี suggestion

        self._skill_var.trace_add("write", lambda *_a: self._on_type())
        self._suggest_list.bind("<<ListboxSelect>>", self._on_suggest_select)
        entry.bind("<Down>", self._focus_suggestions)
        entry.bind("<Return>", self._on_type_enter)

        self._bracket_frame = tk.Frame(win, bg=_BG)
        self._bracket_frame.pack(fill=tk.X, padx=12, pady=(8, 0))

        self._population_label = tk.Label(win, text="", bg=_BG, fg=_DIM, font=_FONT_SMALL)
        self._population_label.pack(anchor="w", padx=12, pady=(2, 0))

        body_wrap = tk.Frame(win, bg=_BG)
        body_wrap.pack(fill=tk.BOTH, expand=True, padx=(12, 0))
        self._canvas = tk.Canvas(body_wrap, bg=_BG, highlightthickness=0, height=1)
        self._scrollbar = tk.Scrollbar(body_wrap, orient=tk.VERTICAL, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        body = tk.Frame(self._canvas, bg=_BG)
        self._body = body
        self._canvas.create_window((0, 0), window=body, anchor="nw")
        win.bind_all("<MouseWheel>", self._on_mousewheel)

        self._table_label = tk.Label(body, text="พิมพ์ชื่อสกิลแล้วเลือกจาก dropdown",
                                      bg=_BG, fg=_DIM, font=_FONT_SMALL, justify=tk.LEFT)
        self._table_label.pack(anchor="w", pady=(6, 2))

        self._table_frame = tk.Frame(body, bg=_BG)
        self._table_frame.pack(fill=tk.BOTH, padx=(0, 12))

        tk.Label(body, text="Passive", bg=_BG, fg=_ACC, font=_FONT_BOLD).pack(
            anchor="w", pady=(10, 0))
        self._passive_frame = tk.Frame(body, bg=_BG)
        self._passive_frame.pack(fill=tk.X, padx=(0, 12), pady=(0, 8))

        btns = tk.Frame(win, bg=_BG)
        btns.pack(fill=tk.X, padx=10, pady=(4, 10))
        tk.Button(btns, text="ปิด  (Esc)", command=self.close,
                  bg="#2A2A2A", fg=_DIM, activebackground="#444", activeforeground=_FG,
                  relief=tk.FLAT, font=_FONT, padx=10, pady=4, cursor="hand2"
                  ).pack(side=tk.RIGHT)

        win.bind("<Escape>", lambda _e: self.close())
        win.protocol("WM_DELETE_WINDOW", self.close)

        self._place_center(parent)
        win.deiconify()
        win.lift()
        win.focus_force()
        entry.focus_set()

    # ------------------------------------------------------------------
    # Autocomplete
    # ------------------------------------------------------------------

    def _on_type(self) -> None:
        prefix = self._skill_var.get()
        self._suggest_list.delete(0, tk.END)
        if not prefix.strip():
            self._suggest_list.pack_forget()
            self._resize_to_content()
            return
        matches = self._db.search_skills(prefix)[:_MAX_SUGGESTIONS]
        if not matches:
            self._suggest_list.pack_forget()
            self._resize_to_content()
            return
        for m in matches:
            self._suggest_list.insert(tk.END, f"{m.skill}  [{m.skill_type}]")
        self._suggest_skills = matches
        self._suggest_list.config(height=len(matches))
        self._suggest_list.pack(fill=tk.X, padx=12, pady=(2, 0), after=self._search_row)
        self._resize_to_content()

    def _on_type_enter(self, *_ignored) -> None:
        typed = self._skill_var.get().strip()
        matches = self._db.search_skills(typed)
        if matches:
            self._select_skill(matches[0])
        elif typed:
            self._show_no_match(typed)

    def _focus_suggestions(self, *_ignored) -> str:
        if self._suggest_list.winfo_ismapped() and self._suggest_list.size():
            self._suggest_list.focus_set()
            self._suggest_list.selection_set(0)
        return "break"

    def _on_suggest_select(self, *_ignored) -> None:
        sel = self._suggest_list.curselection()
        if not sel:
            return
        self._select_skill(self._suggest_skills[sel[0]])

    def _show_no_match(self, typed: str) -> None:
        """Typed text matches nothing in the autocomplete list at all."""
        self._suggest_list.pack_forget()
        self._current_skill = None
        for w in self._bracket_frame.winfo_children():
            w.destroy()
        self._population_label.config(text="")
        for w in self._table_frame.winfo_children():
            w.destroy()
        self._table_label.config(text=f"ไม่พบสกิลชื่อ \"{typed}\" — ลองพิมพ์ใหม่หรือเลือกจาก dropdown")
        for w in self._passive_frame.winfo_children():
            w.destroy()
        self._resize_to_content()

    def _resize_to_content(self) -> None:
        """Toplevel is resizable(False, False) (fixed-by-user, not fixed-forever) —
        content added after the initial pack (mod table, passive rows, the
        no-data message) can be wider/taller than the window's original geometry,
        so without this, long text — the Thai population caption in particular —
        clips silently at the old edge instead of growing the window (caught
        visually testing v0.7.6 against real hub data, 2026-09-21)."""
        win = self._win
        body = self._body
        body.update_idletasks()
        body_h = body.winfo_reqheight()
        self._canvas.config(width=body.winfo_reqwidth(), height=min(body_h, _MAX_BODY_H))
        self._canvas.configure(scrollregion=(0, 0, body.winfo_reqwidth(), body_h))
        self._canvas.yview_moveto(0)
        if body_h > _MAX_BODY_H:
            self._scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        else:
            self._scrollbar.pack_forget()
        win.geometry("")   # drop the previous explicit size first — once geometry()
        win.update_idletasks()   # has been set once, reqwidth/reqheight stop tracking
        win.geometry(f"{win.winfo_reqwidth()}x{win.winfo_reqheight()}")  # natural content size otherwise

    # ------------------------------------------------------------------
    # Skill selection → bracket toggle
    # ------------------------------------------------------------------

    def _select_skill(self, skill: Skill) -> None:
        self._skill_var.set(skill.skill)
        self._suggest_list.pack_forget()
        self._current_skill = skill

        self._mods_by_bracket = self._db.mods_for_skill(skill.skill_type, skill.skill)
        self._passives_by_bracket = self._db.passives_for_skill(skill.skill_type, skill.skill)
        brackets = sorted(
            set(self._mods_by_bracket) | set(self._passives_by_bracket) | set(skill.populations),
            key=_bracket_sort_key,
        )

        for w in self._bracket_frame.winfo_children():
            w.destroy()
        self._bracket_buttons = {}

        if not brackets:
            self._population_label.config(text="")
            for w in self._table_frame.winfo_children():
                w.destroy()
            self._table_label.config(
                text=f"ไม่พบข้อมูล mod/passive สำหรับ {skill.skill} (อาจโหลดจาก hub ไม่สำเร็จ)")
            for w in self._passive_frame.winfo_children():
                w.destroy()
            self._resize_to_content()
            return

        for bracket in brackets:
            btn = tk.Label(self._bracket_frame, text=bracket, bg=_ENTRY_BG, fg=_FG,
                           font=_FONT, padx=10, pady=3, cursor="hand2")
            btn.pack(side=tk.LEFT, padx=(0, 4))
            btn.bind("<Button-1>", lambda _e, b=bracket: self._select_bracket(b))
            self._bracket_buttons[bracket] = btn

        default_bracket = "90-100" if "90-100" in brackets else brackets[-1]
        self._select_bracket(default_bracket)

    def _select_bracket(self, bracket: str) -> None:
        self._current_bracket = bracket
        for b, btn in self._bracket_buttons.items():
            active = b == bracket
            btn.config(bg=_ACC if active else _ENTRY_BG, fg=_BG if active else _FG)

        skill = self._current_skill
        population = skill.populations.get(bracket) if skill else None
        if population is None:
            self._population_label.config(text=f"ฐาน: {bracket} = ไม่ทราบจำนวน", fg=_DIM)
        else:
            thin = population < _THIN_POPULATION
            text = f"ฐาน: {bracket} = {population} คน"
            if thin:
                text += "  (ข้อมูลน้อย)"
            self._population_label.config(text=text, fg=(_WARN if thin else _DIM))

        self._render_mods(bracket)
        self._render_passives(bracket)
        self._resize_to_content()

    # ------------------------------------------------------------------
    # Mod table
    # ------------------------------------------------------------------

    def _render_mods(self, bracket: str) -> None:
        for w in self._table_frame.winfo_children():
            w.destroy()
        self._tab_buttons = {}
        mods_by_slot = self._mods_by_bracket.get(bracket, {})
        if not mods_by_slot:
            self._table_label.config(text=f"ไม่มีข้อมูล mod สำหรับ bracket {bracket}")
            return
        self._table_label.config(text="Mod แนะนำต่อ slot:")
        self._mods_by_slot = mods_by_slot
        slots = sorted(mods_by_slot.keys())

        # Plain tk tab bar, not ttk.Notebook — on Windows, ttk's native theme
        # ("vista") ignores style.configure()'d background/foreground for the
        # notebook pane, so it rendered with the OS's native light background
        # regardless of our dark theme, making the gold mod text unreadable
        # against it (real user report testing v0.7.6, 2026-09-21). Plain tk
        # widgets give full color control like the rest of this window.
        tab_bar = tk.Frame(self._table_frame, bg=_BG)
        tab_bar.pack(fill=tk.X)
        for slot in slots:
            btn = tk.Label(tab_bar, text=slot.capitalize(), bg=_ENTRY_BG, fg=_FG,
                           font=_FONT, padx=8, pady=3, cursor="hand2")
            btn.pack(side=tk.LEFT, padx=(0, 2))
            btn.bind("<Button-1>", lambda _e, s=slot: self._select_mod_tab(s))
            self._tab_buttons[slot] = btn

        self._mod_content = tk.Frame(self._table_frame, bg=_BG, pady=4)
        self._mod_content.pack(fill=tk.BOTH, expand=True)
        self._select_mod_tab(slots[0])

    def _select_mod_tab(self, slot: str) -> None:
        for s, btn in self._tab_buttons.items():
            active = s == slot
            btn.config(bg=_ACC if active else _ENTRY_BG, fg=_BG if active else _FG)
        for w in self._mod_content.winfo_children():
            w.destroy()
        for mod in self._mods_by_slot.get(slot, []):
            row = tk.Frame(self._mod_content, bg=_BG)
            row.pack(fill=tk.X)
            tk.Label(row, text=mod.text, bg=_BG, fg=_FG, font=_FONT, anchor="w",
                     width=40, justify=tk.LEFT).pack(side=tk.LEFT)
            range_text = ""
            if mod.value_min is not None and mod.value_max is not None:
                range_text = f"{_fmt_num(mod.value_min)}–{_fmt_num(mod.value_max)}"
            tk.Label(row, text=range_text, bg=_BG, fg=_DIM, font=_FONT_SMALL,
                     width=12, anchor="e").pack(side=tk.RIGHT)
            tk.Label(row, text=f"{mod.usage_pct:.0f}%", bg=_BG, fg=_DIM, font=_FONT_SMALL,
                     width=6, anchor="e").pack(side=tk.RIGHT)
        self._resize_to_content()

    # ------------------------------------------------------------------
    # Passive section
    # ------------------------------------------------------------------

    def _render_passives(self, bracket: str) -> None:
        for w in self._passive_frame.winfo_children():
            w.destroy()
        rows = self._passives_by_bracket.get(bracket, [])
        if not rows:
            tk.Label(self._passive_frame, text="ไม่มีข้อมูล passive สำหรับ bracket นี้",
                     bg=_BG, fg=_DIM, font=_FONT_SMALL).pack(anchor="w")
            return
        for r in rows:
            row = tk.Frame(self._passive_frame, bg=_BG)
            row.pack(fill=tk.X)
            tk.Label(row, text=r.keypassive, bg=_BG, fg=_FG, font=_FONT, anchor="w",
                     width=40, justify=tk.LEFT).pack(side=tk.LEFT)
            tk.Label(row, text=f"{r.usage_pct:.0f}%", bg=_BG, fg=_DIM, font=_FONT_SMALL,
                     width=6, anchor="e").pack(side=tk.RIGHT)

    # ------------------------------------------------------------------

    def _on_mousewheel(self, event) -> None:
        if self._scrollbar.winfo_ismapped():
            self._canvas.yview_scroll(int(-event.delta / 120), "units")

    def close(self) -> None:
        try:
            self._win.unbind_all("<MouseWheel>")
        except Exception:
            pass
        try:
            self._win.destroy()
        except Exception:
            pass
        if self._on_close:
            self._on_close()

    def _place_center(self, parent: tk.Misc) -> None:
        win = self._win
        win.update_idletasks()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        try:
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
            x = px + max((pw - w) // 2, 0)
            y = py + max((ph - h) // 2, 0)
        except Exception:
            x, y = 200, 200
        win.geometry(f"+{x}+{y}")
