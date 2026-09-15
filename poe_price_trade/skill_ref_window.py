"""Skill Mod Reference window — UI for the new F4 mode (config.f4_mode ==
"skill_ref", default off, see app.py's _on_f4_scan). Style mirrors
mod_picker.py's ModPickerWindow (same Toplevel/color/font conventions) so it
looks consistent with the rest of the app. Data comes from SkillRefDB
(skill_ref.py) — mock only right now, no network calls."""
from __future__ import annotations
import tkinter as tk
from typing import Callable, Optional

from .skill_ref import SkillRefDB

_BG, _FG, _ACC = "#1C1C1C", "#E8D5A0", "#C8A050"
_DIM = "#777777"
_ENTRY_BG = "#2A2A2A"
_FONT = ("Segoe UI", 9)
_FONT_SMALL = ("Segoe UI", 8)
_FONT_BOLD = ("Segoe UI", 10, "bold")
_MAX_SUGGESTIONS = 8


class SkillRefWindow:
    def __init__(self, parent: tk.Misc, db: SkillRefDB, on_close: Optional[Callable[[], None]] = None):
        self._db = db
        self._on_close = on_close
        self._suggest_names: list[str] = []

        win = tk.Toplevel(parent)
        self._win = win
        win.withdraw()                      # ซ่อนก่อน จัดตำแหน่งเสร็จค่อยโชว์ (กันกระพริบ)
        win.title("Skill Mod Reference")
        win.configure(bg=_BG)
        win.attributes("-topmost", True)
        win.resizable(False, False)

        tk.Label(win, text="Skill Mod Reference", bg=_BG, fg=_ACC, font=_FONT_BOLD).pack(
            anchor="w", padx=12, pady=(10, 4))

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
        self._suggest_list.pack(fill=tk.X, padx=12, pady=(2, 0))
        self._suggest_list.pack_forget()    # ซ่อนจนกว่าจะมี suggestion

        self._skill_var.trace_add("write", lambda *_a: self._on_type())
        self._suggest_list.bind("<<ListboxSelect>>", self._on_suggest_select)
        entry.bind("<Down>", self._focus_suggestions)
        entry.bind("<Return>", self._on_type_enter)

        self._table_label = tk.Label(win, text="พิมพ์ชื่อสกิลแล้วเลือกจาก dropdown",
                                      bg=_BG, fg=_DIM, font=_FONT_SMALL, justify=tk.LEFT)
        self._table_label.pack(anchor="w", padx=12, pady=(8, 2))

        self._table_frame = tk.Frame(win, bg=_BG)
        self._table_frame.pack(fill=tk.BOTH, padx=12)

        # Passive section — เฟส 2, รอ hub (skill_ref.py's passives_for_skill() stub)
        tk.Label(win, text="Passive", bg=_BG, fg=_ACC, font=_FONT_BOLD).pack(
            anchor="w", padx=12, pady=(10, 0))
        tk.Label(win, text="รอข้อมูลจาก hub", bg=_BG, fg=_DIM, font=_FONT_SMALL).pack(
            anchor="w", padx=12, pady=(0, 8))

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
            return
        matches = self._db.search_skills(prefix)[:_MAX_SUGGESTIONS]
        if not matches:
            self._suggest_list.pack_forget()
            return
        for m in matches:
            self._suggest_list.insert(tk.END, f"{m.name}  ({m.archetype})")
        self._suggest_names = [m.name for m in matches]
        self._suggest_list.config(height=len(matches))
        self._suggest_list.pack(fill=tk.X, padx=12, pady=(2, 0))

    def _on_type_enter(self, *_ignored) -> None:
        matches = self._db.search_skills(self._skill_var.get())
        if matches:
            self._select_skill(matches[0].name)

    def _focus_suggestions(self, *_ignored) -> str:
        if self._suggest_list.winfo_ismapped() and self._suggest_list.size():
            self._suggest_list.focus_set()
            self._suggest_list.selection_set(0)
        return "break"

    def _on_suggest_select(self, *_ignored) -> None:
        sel = self._suggest_list.curselection()
        if not sel:
            return
        self._select_skill(self._suggest_names[sel[0]])

    def _select_skill(self, name: str) -> None:
        self._skill_var.set(name)
        self._suggest_list.pack_forget()
        self._render_mods(name)

    # ------------------------------------------------------------------
    # Mod table
    # ------------------------------------------------------------------

    def _render_mods(self, name: str) -> None:
        for w in self._table_frame.winfo_children():
            w.destroy()
        mods_by_slot = self._db.mods_for_skill(name)
        if not mods_by_slot:
            self._table_label.config(text=f"ไม่พบข้อมูล mod สำหรับ {name}")
            return
        self._table_label.config(text="Mod แนะนำต่อ slot:")
        for slot in sorted(mods_by_slot.keys()):
            slot_row = tk.Frame(self._table_frame, bg=_BG)
            slot_row.pack(fill=tk.X, pady=(6, 0))
            tk.Label(slot_row, text=slot.capitalize(), bg=_BG, fg=_ACC, font=_FONT_BOLD).pack(anchor="w")
            for mod in mods_by_slot[slot]:
                row = tk.Frame(self._table_frame, bg=_BG)
                row.pack(fill=tk.X)
                tk.Label(row, text=mod.text, bg=_BG, fg=_FG, font=_FONT, anchor="w",
                         width=40, justify=tk.LEFT).pack(side=tk.LEFT)
                tk.Label(row, text=f"{mod.usage_pct:.0f}%", bg=_BG, fg=_DIM, font=_FONT_SMALL,
                         width=6, anchor="e").pack(side=tk.RIGHT)

    # ------------------------------------------------------------------

    def close(self) -> None:
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
