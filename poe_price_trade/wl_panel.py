"""Whitelist tab body (Tk): pick a tier first, then style, category and items. All state lives in WlModel;
this file only draws it and forwards clicks. Widgets use the dark theme (ui_theme) - no white boxes."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from . import filter_style, ui_theme
from .filter_style_editor import open_style_dialog
from .wl_model import ALL_CHOICES, RARITIES, TIER_CHOICES, WlModel, tier_label

_BG, _FG, _ACCENT = ui_theme.BG, ui_theme.FG, ui_theme.ACCENT
_INPUT_BG, _BUTTON_BG = ui_theme.INPUT_BG, ui_theme.BUTTON_BG
_FONT = ("Segoe UI", 9)
_SMALL = ("Segoe UI", 8)
# colour of the tier suffix in the list (readable on the dark list background)
TIER_COLORS = {"S": "#FF7A66", "A": "#F2A93B", "B": "#8FD16A", "C": "#8A8A8A", "T": "#4FD8E0"}


class WhitelistPanel(tk.Frame):
    def __init__(self, parent, model: WlModel, *, on_changed: Optional[Callable[[], None]] = None,
                 goto_sound_tab: Optional[Callable[[], None]] = None,
                 get_sounds: Optional[Callable[[], dict]] = None):
        super().__init__(parent, bg=_BG)
        self.model = model
        self._on_changed = on_changed
        self._goto_sound_tab = goto_sound_tab
        self._get_sounds = get_sounds or (lambda: {})
        self._cat_ids: list = []
        self._row_keys: dict = {}          # tree item id -> row key
        self._build()
        self.refresh_all()

    # ------------------------------------------------------------------ small widgets

    def _btn(self, parent, text, cmd, **kw):
        b = tk.Button(parent, text=text, command=cmd, bg=_BUTTON_BG, fg=_FG, activebackground=_ACCENT,
                      activeforeground="#000", disabledforeground="#6a6050", relief=tk.FLAT, font=_FONT,
                      padx=6, pady=2, cursor="hand2", **kw)
        return b

    def _label(self, parent, text, fg=_FG, font=_FONT, **kw):
        return tk.Label(parent, text=text, bg=_BG, fg=fg, font=font, **kw)

    def _entry(self, parent, var, width=8):
        return tk.Entry(parent, textvariable=var, bg=_INPUT_BG, fg=_FG, insertbackground=_FG, relief=tk.FLAT,
                        font=_FONT, width=width, disabledbackground=_BG, disabledforeground="#6a6050")

    def _combo(self, parent, var, values, width=8):
        return ttk.Combobox(parent, textvariable=var, values=values, width=width, state="readonly", font=_FONT)

    def _changed(self) -> None:
        if self._on_changed:
            self._on_changed()

    # ------------------------------------------------------------------ build

    def _build(self) -> None:
        # 1) tier first
        top = tk.Frame(self, bg=_BG)
        top.pack(fill=tk.X, padx=6, pady=(4, 2))
        self._label(top, "1) เลือก tier:").pack(side=tk.LEFT)
        self.active = tk.StringVar(value="")
        self._tier_btns = {}
        for t in TIER_CHOICES:
            b = tk.Radiobutton(top, text=f" {t} ", variable=self.active, value=t, indicatoron=0, width=4,
                               bg=_BUTTON_BG, fg=TIER_COLORS[t], selectcolor="#6a5528", activebackground=_ACCENT,
                               activeforeground="#000", relief=tk.FLAT, font=("Segoe UI", 10, "bold"),
                               command=self._on_tier_picked, cursor="hand2")
            b.pack(side=tk.LEFT, padx=3)
            self._tier_btns[t] = b
        self._hint = self._label(top, "ยังไม่ได้เลือก — ส่วนอื่นยังกดไม่ได้", fg="#C8A050", font=_SMALL)
        self._hint.pack(side=tk.LEFT, padx=8)

        # 2) the tier's style
        st = tk.Frame(self, bg=_BG)
        st.pack(fill=tk.X, padx=6, pady=2)
        self._label(st, "2) สไตล์ของ tier:").pack(side=tk.LEFT)
        self._style_btn = self._btn(st, "แก้สไตล์…", self._edit_tier_style)
        self._style_btn.pack(side=tk.LEFT, padx=6)
        self._preview = tk.Label(st, text="ตัวอย่าง", width=16, font=("Segoe UI", 10, "bold"), bd=0,
                                 highlightthickness=2)
        self._preview.pack(side=tk.LEFT, padx=6)
        # minimum stack size of the tier (only stackable names are affected)
        sk = tk.Frame(self, bg=_BG)
        sk.pack(fill=tk.X, padx=6, pady=2)
        self._label(sk, "   โชว์เมื่อจำนวน ≥").pack(side=tk.LEFT)
        self.v_tier_stack = tk.StringVar(value="1")
        self._tier_stack_entry = self._entry(sk, self.v_tier_stack, 5)
        self._tier_stack_entry.pack(side=tk.LEFT, padx=4)
        self._tier_stack_entry.bind("<KeyRelease>", lambda _e: self._apply_tier_stack())
        self._label(sk, "(1 = โชว์ทุกชิ้น · ใช้กับของที่ stack ได้ · ค่ารายชิ้นที่สูงกว่าชนะ)", fg="#777",
                    font=_SMALL).pack(side=tk.LEFT)

        self._sub = ttk.Notebook(self)
        self._sub.pack(fill=tk.BOTH, expand=True, padx=4, pady=(4, 2))
        items = tk.Frame(self._sub, bg=_BG, padx=4, pady=4)
        parts = tk.Frame(self._sub, bg=_BG, padx=4, pady=4)
        self._sub.add(items, text="3) หมวด / ไอเท็ม")
        self._sub.add(parts, text="ส่วนแยก")
        self._build_items(items)
        self._build_parts(parts)

    def _build_items(self, f) -> None:
        r = tk.Frame(f, bg=_BG)
        r.pack(fill=tk.X)
        self.cat_var = tk.StringVar()
        self._cat_combo = self._combo(r, self.cat_var, [], width=30)
        self._cat_combo.pack(side=tk.LEFT)
        self._cat_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh_list())
        self.query = tk.StringVar()
        self._label(r, " ค้นหา:", font=_SMALL).pack(side=tk.LEFT)
        self._search = self._entry(r, self.query, width=16)
        self._search.pack(side=tk.LEFT, padx=2)
        self.query.trace_add("write", lambda *_a: self.refresh_list())
        self._cat_info = self._label(f, "", fg="#9a9a9a", font=_SMALL, anchor="w")
        self._cat_info.pack(fill=tk.X, pady=(2, 0))

        wrap = tk.Frame(f, bg=_BG)
        wrap.pack(fill=tk.BOTH, expand=True)
        style = ttk.Style(self)
        style.configure("Wl.Treeview", background=_INPUT_BG, fieldbackground=_INPUT_BG, foreground=_FG,
                        rowheight=20, borderwidth=0, font=_FONT)
        style.configure("Wl.Treeview.Heading", background=_BUTTON_BG, foreground=_FG, font=_SMALL, relief="flat")
        style.map("Wl.Treeview", background=[("selected", "#4a3d20")], foreground=[("selected", "#FFFFFF")])
        self.tree = ttk.Treeview(wrap, columns=("name", "tier", "mark"), show="headings", style="Wl.Treeview",
                                 height=11, selectmode="extended")
        self.tree.heading("name", text="ชื่อ (คลิก ☑/☐ = ติ๊ก/เอาออก)")
        self.tree.heading("tier", text="tier")
        self.tree.heading("mark", text="")
        self.tree.column("name", width=400, anchor="w")
        self.tree.column("tier", width=62, anchor="center")
        self.tree.column("mark", width=62, anchor="center")
        sb = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        for t, c in TIER_COLORS.items():
            self.tree.tag_configure(t, foreground=c)
        self.tree.bind("<Button-1>", self._on_click)

        self._warn = self._label(f, "", fg="#E0B060", font=_SMALL, anchor="w", justify=tk.LEFT, wraplength=420)
        self._warn.pack(fill=tk.X)
        b1 = tk.Frame(f, bg=_BG)
        b1.pack(fill=tk.X, pady=(3, 0))
        self._act_btns = []
        for text, cmd in (("ทั้งหมวด → tier นี้", lambda: self._set_cat(self.active.get())),
                          ("ทั้งหมวด → C (ซ่อน)", lambda: self._set_cat("C")),
                          ("ย้ายที่เลือก → tier นี้", self._move_selected)):
            b = self._btn(b1, text, cmd)
            b.pack(side=tk.LEFT, padx=2)
            self._act_btns.append(b)
        b2 = tk.Frame(f, bg=_BG)
        b2.pack(fill=tk.X, pady=(3, 0))
        for text, cmd in (("รีเซ็ตที่เลือกเป็นค่า NeverSink", self._reset_selected),
                          ("รีเซ็ตทั้งหมวด", self._reset_cat)):
            b = self._btn(b2, text, cmd)
            b.pack(side=tk.LEFT, padx=2)
            self._act_btns.append(b)
        b3 = tk.Frame(f, bg=_BG)
        b3.pack(fill=tk.X, pady=(3, 0))
        self._label(b3, "จำนวนขั้นต่ำของที่เลือก ≥").pack(side=tk.LEFT, padx=(2, 0))
        self.v_item_stack = tk.StringVar(value="1")
        self._item_stack_entry = self._entry(b3, self.v_item_stack, 5)
        self._item_stack_entry.pack(side=tk.LEFT, padx=4)
        b = self._btn(b3, "ตั้งที่เลือก", self._set_item_stack)
        b.pack(side=tk.LEFT, padx=2)
        self._act_btns.append(b)
        self._label(b3, "(1 = โชว์ทุกชิ้น)", fg="#777", font=_SMALL).pack(side=tk.LEFT, padx=4)

    def _build_parts(self, f) -> None:
        m = self.model
        # gold
        g = tk.Frame(f, bg=_BG)
        g.pack(fill=tk.X, pady=2)
        self.v_gold = tk.BooleanVar(value=m.gold)
        self._check(g, "Gold", self.v_gold).pack(side=tk.LEFT)
        self._label(g, "จำนวน ≥").pack(side=tk.LEFT, padx=(6, 2))
        self.v_gold_min = tk.StringVar(value=str(m.gold_min))
        self._entry(g, self.v_gold_min, 6).pack(side=tk.LEFT)
        self._btn(g, "สไตล์ Gold…", lambda: self._edit_style("G", "Gold")).pack(side=tk.LEFT, padx=6)
        # map / waystone
        mp = tk.Frame(f, bg=_BG)
        mp.pack(fill=tk.X, pady=2)
        name = "Waystone" if m.game == "poe2" else "Map"
        self.v_map = tk.BooleanVar(value=m.map_on)
        self._check(mp, f"{name} (ต้องผ่านทั้ง 2 เงื่อนไข)", self.v_map).pack(side=tk.LEFT)
        mp2 = tk.Frame(f, bg=_BG)
        mp2.pack(fill=tk.X, pady=(0, 2))
        self._label(mp2, "   tier ≥").pack(side=tk.LEFT)
        self.v_map_tier = tk.StringVar(value=str(m.map_tier))
        self._entry(mp2, self.v_map_tier, 4).pack(side=tk.LEFT, padx=2)
        self._label(mp2, "rarity ≥").pack(side=tk.LEFT, padx=(6, 2))
        self.v_map_rar = tk.StringVar(value=m.map_rarity)
        c = self._combo(mp2, self.v_map_rar, list(RARITIES), 8)
        c.pack(side=tk.LEFT)
        c.bind("<<ComboboxSelected>>", lambda _e: self._parts_changed())
        self._btn(mp2, f"สไตล์ {name}…", lambda: self._edit_style("Map", name)).pack(side=tk.LEFT, padx=6)
        self._label(f, "   (ไม่ติ๊ก = โชว์ตามเกม · poe1: map พิเศษผ่านเสมอ)", fg="#777", font=_SMALL).pack(anchor="w")
        if m.game == "poe2":
            tb = tk.Frame(f, bg=_BG)
            tb.pack(fill=tk.X, pady=2)
            self._label(tb, "Tablet (โชว์เสมอ ยกเว้นตั้ง tier รายชิ้น)").pack(side=tk.LEFT)
            self._btn(tb, "สไตล์ Tablet…", lambda: self._edit_style("Tablet", "Tablet")).pack(side=tk.LEFT, padx=6)
        # gem
        self._gem_frame = tk.Frame(f, bg=_BG)
        self._gem_frame.pack(fill=tk.X, pady=(4, 2))
        self._build_gems(self._gem_frame)
        # typed names
        self._build_custom(f)
        # shared sounds (read only)
        sd = tk.LabelFrame(f, text=" เสียงที่ใช้ (แชร์กับแท็บ NeverSink) ", bg=_BG, fg=_FG, font=_SMALL)
        sd.pack(fill=tk.X, pady=(6, 0))
        self._sound_lbl = self._label(sd, "", fg="#bfae80", font=_SMALL, anchor="w", justify=tk.LEFT, wraplength=410)
        self._sound_lbl.pack(fill=tk.X, padx=4)
        self._btn(sd, "ไปตั้งที่แท็บ NeverSink", self._on_goto_sound).pack(anchor="w", padx=4, pady=3)
        self._parts_widgets = [w for w in f.winfo_children()]

    def _check(self, parent, text, var):
        return tk.Checkbutton(parent, text=text, variable=var, bg=_BG, fg=_FG, selectcolor="#2A2020",
                              activebackground=_BG, font=_FONT, command=self._parts_changed)

    def _build_gems(self, f) -> None:
        m = self.model
        self._label(f, "Gem:").grid(row=0, column=0, sticky="w")
        self.v_gem_tier = tk.StringVar(value=m.gem_tier)
        self._label(f, "tier").grid(row=0, column=1, sticky="e")
        c = self._combo(f, self.v_gem_tier, list(ALL_CHOICES), 3)
        c.grid(row=0, column=2, sticky="w", padx=3)
        c.bind("<<ComboboxSelected>>", lambda _e: self._parts_changed())
        self.v_gem_on = {}
        self.v_gem_lv = {}
        from . import filter_gen
        uncut = filter_gen.WHITELIST_GEM_UNCUT.get(m.game, [])
        for i, base in enumerate(uncut, start=1):
            on = tk.BooleanVar(value=base in m.gem_uncut)
            lv = tk.StringVar(value=str(m.gem_uncut.get(base, 1)))
            self.v_gem_on[base], self.v_gem_lv[base] = on, lv
            tk.Checkbutton(f, text=base, variable=on, bg=_BG, fg=_FG, selectcolor="#2A2020", activebackground=_BG,
                           font=_SMALL, command=self._parts_changed).grid(row=i, column=0, sticky="w")
            self._label(f, "level ≥", font=_SMALL).grid(row=i, column=1, sticky="e")
            self._entry(f, lv, 4).grid(row=i, column=2, sticky="w", padx=3)
        if not uncut:
            self.v_gem_name = tk.StringVar()
            e = self._entry(f, self.v_gem_name, 22)
            e.grid(row=1, column=0, sticky="w")
            e.bind("<Return>", lambda _e: self._gem_add())
            self._btn(f, "เพิ่ม", self._gem_add).grid(row=1, column=1, padx=3)
            self._btn(f, "ลบที่เลือก", self._gem_remove).grid(row=1, column=2)
            self._gem_list = tk.Listbox(f, bg=_INPUT_BG, fg=_FG, font=_SMALL, height=3, width=40, relief=tk.FLAT,
                                        selectmode=tk.EXTENDED, exportselection=False, selectbackground="#4a3d20")
            self._gem_list.grid(row=2, column=0, columnspan=3, sticky="w", pady=2)
            for n in m.gem_names:
                self._gem_list.insert(tk.END, n)

    def _gem_add(self) -> None:
        nm = self.v_gem_name.get().strip()
        if nm and nm.lower() not in {x.lower() for x in self.model.gem_names}:
            self.model.gem_names.append(nm)
            self._gem_list.insert(tk.END, nm)
        self.v_gem_name.set("")
        self._changed()

    def _gem_remove(self) -> None:
        for idx in reversed(self._gem_list.curselection()):
            self._gem_list.delete(idx)
            del self.model.gem_names[idx]
        self._changed()

    def _build_custom(self, f) -> None:
        box = tk.Frame(f, bg=_BG)
        box.pack(fill=tk.X, pady=(4, 2))
        self._label(box, "พิมพ์ชื่อเอง (contains):").grid(row=0, column=0, columnspan=4, sticky="w")
        self.v_custom = tk.StringVar()
        e = self._entry(box, self.v_custom, 20)
        e.grid(row=1, column=0, sticky="w")
        e.bind("<Return>", lambda _e: self._custom_add())
        self.v_custom_tier = tk.StringVar(value="B")
        self._combo(box, self.v_custom_tier, list(ALL_CHOICES), 3).grid(row=1, column=1, padx=3)
        self._btn(box, "เพิ่ม", self._custom_add).grid(row=1, column=2, padx=2)
        self._btn(box, "ลบที่เลือก", self._custom_remove).grid(row=1, column=3)
        rf = tk.Frame(box, bg=_BG)
        rf.grid(row=2, column=0, columnspan=4, sticky="w")
        self.v_custom_rar = {}
        for r in RARITIES:
            v = tk.BooleanVar(value=(r == "Normal"))
            self.v_custom_rar[r] = v
            tk.Checkbutton(rf, text=r, variable=v, bg=_BG, fg=_FG, selectcolor="#2A2020", activebackground=_BG,
                           font=_SMALL).pack(side=tk.LEFT)
        self._custom_list = tk.Listbox(box, bg=_INPUT_BG, fg=_FG, font=_SMALL, height=3, width=48, relief=tk.FLAT,
                                       selectmode=tk.EXTENDED, exportselection=False, selectbackground="#4a3d20")
        self._custom_list.grid(row=3, column=0, columnspan=4, sticky="w", pady=2)
        self._render_custom()

    def _render_custom(self) -> None:
        abbr = {"Normal": "N", "Magic": "M", "Rare": "R", "Unique": "U"}
        self._custom_list.delete(0, tk.END)
        for e in self.model.custom:
            self._custom_list.insert(tk.END, f"{e['name']}   [{'/'.join(abbr[r] for r in e['rarities'])}]  → {e['tier']}")

    def _custom_add(self) -> None:
        nm = self.v_custom.get().strip()
        if not nm or any(e["name"].lower() == nm.lower() for e in self.model.custom):
            self.v_custom.set("")
            return
        rs = [r for r in RARITIES if self.v_custom_rar[r].get()] or ["Normal"]
        self.model.custom.append({"name": nm, "rarities": rs, "tier": self.v_custom_tier.get()})
        self.v_custom.set("")
        self._render_custom()
        self._changed()

    def _custom_remove(self) -> None:
        for idx in sorted(self._custom_list.curselection(), reverse=True):
            if 0 <= idx < len(self.model.custom):
                del self.model.custom[idx]
        self._render_custom()
        self._changed()

    # ------------------------------------------------------------------ parts -> model

    def _parts_changed(self) -> None:
        self.read_parts()
        self._changed()

    def read_parts(self) -> None:
        """Copy the 'ส่วนแยก' widgets into the model (call before saving)."""
        m = self.model
        m.gold = bool(self.v_gold.get())
        try:
            m.gold_min = max(0, int(self.v_gold_min.get() or 0))
        except ValueError:
            m.gold_min = 0
        m.map_on = bool(self.v_map.get())
        try:
            m.map_tier = max(1, min(16, int(self.v_map_tier.get() or 1)))
        except ValueError:
            m.map_tier = 1
        m.map_rarity = self.v_map_rar.get() if self.v_map_rar.get() in RARITIES else "Normal"
        m.gem_tier = self.v_gem_tier.get() if self.v_gem_tier.get() in ALL_CHOICES else "B"
        if self.v_gem_on:
            out = {}
            for base, on in self.v_gem_on.items():
                if on.get():
                    try:
                        out[base] = max(1, int(self.v_gem_lv[base].get() or 1))
                    except ValueError:
                        out[base] = 1
            m.gem_uncut = out

    # ------------------------------------------------------------------ tier / style

    def _controls(self):
        return [self._style_btn, self._cat_combo, self._search, self._tier_stack_entry, self._item_stack_entry,
                *self._act_btns]

    def _on_tier_picked(self) -> None:
        self.refresh_enabled()
        self.refresh_preview()
        t = self.active.get()
        self.v_tier_stack.set(str(self.model.tier_stack.get(t, 1)) if t else "1")

    def _apply_tier_stack(self) -> None:
        t = self.active.get()
        if not t:
            return
        try:
            n = max(1, int(self.v_tier_stack.get() or 1))
        except ValueError:
            n = 1
        self.model.set_tier_stack(t, n)
        self.refresh_list()
        self._changed()

    def _set_item_stack(self) -> None:
        try:
            n = max(1, int(self.v_item_stack.get() or 1))
        except ValueError:
            n = 1
        keys = [r.key for r in self.model.rows(self.current_category()) if r.stackable
                and r.key in set(self.selected_keys())]
        self.model.set_stack(keys, n)
        self.refresh_list()
        self._changed()

    def refresh_enabled(self) -> None:
        on = bool(self.active.get())
        state = tk.NORMAL if on else tk.DISABLED
        for w in self._controls():
            try:
                w.configure(state=("readonly" if (w is self._cat_combo and on) else state))
            except tk.TclError:
                pass
        self.tree.configure(selectmode="extended" if on else "none")
        self._hint.configure(text="" if on else "ยังไม่ได้เลือก — ส่วนอื่นยังกดไม่ได้")

    def refresh_preview(self) -> None:
        t = self.active.get()
        if not t:
            self._preview.configure(text="—", bg=_BG, fg="#777", highlightbackground=_BG)
            return
        s = self.model.effective_style(t)
        bg = _color(s["bg"], "#101010")
        self._preview.configure(text=f"ตัวอย่าง {t}", bg=bg, fg=_color(s["text"], "#C8C8C8"),
                                highlightbackground=_color(s["border"], bg), highlightcolor=_color(s["border"], bg))

    def _edit_tier_style(self) -> None:
        t = self.active.get()
        if t:
            self._edit_style(t, f"tier {t}", show_sound=False)

    def _edit_style(self, label: str, title: str, show_sound: bool = True) -> None:
        def _save(style) -> None:
            if style is None:
                self.model.set_style(label, None)
            else:
                self.model.set_style_from_editor(label, style)
            self.refresh_preview()
            self._changed()
        self._style_dialog = open_style_dialog(
            self.winfo_toplevel(), f"สไตล์ {title} (ติ๊กออก = ใช้ค่า NeverSink)", self.model.effective_style(label),
            _save, clear_text="รีเซ็ตเป็นค่า NeverSink", sample_text=title, show_sound=show_sound)

    # ------------------------------------------------------------------ list

    def load_categories(self) -> None:
        cats = self.model.categories()
        self._cat_ids = [c for c, _l in cats]
        self._cat_combo.configure(values=[l for _c, l in cats])
        if cats and not self.cat_var.get():
            self.cat_var.set(cats[0][1])

    def current_category(self) -> str:
        label = self.cat_var.get()
        for cid, lab in self.model.categories():
            if lab == label:
                return cid
        return self._cat_ids[0] if self._cat_ids else ""

    def refresh_all(self) -> None:
        self.load_categories()
        self.refresh_enabled()
        self.refresh_preview()
        self.refresh_list()
        self.refresh_sounds()

    def refresh_list(self) -> None:
        cat = self.current_category()
        self.tree.delete(*self.tree.get_children())
        self._row_keys = {}
        if not cat:
            return
        if not self.model.loaded:
            self._cat_info.configure(text="กำลังโหลดรายการ… (hub + NeverSink)")
            return
        rows = self.model.rows(cat, self.query.get())
        for r in rows:
            on = r.tier != "C"
            tier_text = tier_label(r.tier) if on else "C"
            if on and r.stack > 1:
                tier_text += f" ≥{r.stack}"
            mark = "● ตั้งเอง" if (r.user_set or r.stack_set) else ""
            iid = self.tree.insert("", tk.END, values=(("☑ " if on else "☐ ") + r.label, tier_text, mark),
                                   tags=(r.tier,))
            self._row_keys[iid] = r.key
        ct = self.model.category_tier(cat)
        info = f"{len(rows)} แถว · ตั้งเองแล้ว {self.model.changed_count(cat)}"
        if ct:
            info += f" · ทั้งหมวด = {ct}"
        self._cat_info.configure(text=info)
        notes = sorted({r.note for r in rows if r.note})
        self._warn.configure(text="\n".join(notes))

    def refresh_sounds(self) -> None:
        s = self._get_sounds() or {}
        names = []
        for k in ("S", "A", "B", "Q"):
            v = s.get(k) or ""
            names.append(f"{k}: " + (v.replace("\\", "/").rsplit("/", 1)[-1] if v else "(เสียงของ NeverSink)"))
        self._sound_lbl.configure(text="   ".join(names))

    def _on_click(self, event) -> Optional[str]:
        if not self.active.get():
            return "break"
        iid = self.tree.identify_row(event.y)
        if not iid or self.tree.identify_region(event.x, event.y) != "cell":
            return None
        if self.tree.identify_column(event.x) == "#1" and event.x < 28 and not (event.state & 0x5):
            self.model.toggle_row(self.current_category(), self._row_keys[iid], self.active.get())
            self.refresh_list()
            self._changed()
            return "break"
        return None

    def selected_keys(self) -> list:
        return [self._row_keys[i] for i in self.tree.selection() if i in self._row_keys]

    def _move_selected(self) -> None:
        t = self.active.get()
        for k in self.selected_keys():
            self.model.set_row(self.current_category(), k, t)
        self.refresh_list()
        self._changed()

    def _reset_selected(self) -> None:
        for k in self.selected_keys():
            self.model.reset_row(self.current_category(), k)
        self.refresh_list()
        self._changed()

    def _set_cat(self, tier: str) -> None:
        if tier:
            self.model.set_category(self.current_category(), tier)
            self.refresh_list()
            self._changed()

    def _reset_cat(self) -> None:
        self.model.reset_category(self.current_category())
        self.refresh_list()
        self._changed()

    def _on_goto_sound(self) -> None:
        if self._goto_sound_tab:
            self._goto_sound_tab()

    # called by the window once hub / NeverSink data arrived
    def data_loaded(self) -> None:
        self.refresh_all()


def _color(rgba, default: str) -> str:
    return "#%02x%02x%02x" % tuple(rgba[:3]) if rgba else default
