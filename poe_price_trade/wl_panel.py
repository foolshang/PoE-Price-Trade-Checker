"""Whitelist tab body (Tk): pick a tier first, then its style (inline - no pop-up), then the sub tabs: items /
categories, Gold, Map / Waystone, Tablet (poe2), Gem, typed names. Gold / Map / Tablet / Gem each show their own style
editor (colours, opacity, size, icon, beam, sound) in their sub tab. All state lives in WlModel; this file only draws it
and forwards clicks. Widgets use the dark theme (ui_theme) - no white boxes."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from . import filter_style, filter_whitelist as w, ui_theme
from .filter_style_editor import StyleEditor
from .wl_model import ALL_CHOICES, EQUIP_CATEGORY, FLASK_CATEGORY, RARITIES, TIER_CHOICES, WlModel, tier_label

_BG, _FG, _ACCENT = ui_theme.BG, ui_theme.FG, ui_theme.ACCENT
_INPUT_BG, _BUTTON_BG = ui_theme.INPUT_BG, ui_theme.BUTTON_BG
TIER_BOX_WIDTH = 5                       # the S / A / B / C boxes of a row: one width for Normal / Magic / Rare
GROUP_BOX_WIDTH = 13                     # ... and the three at a group header (the prompt + "ค่าเริ่มต้น" must fit)
RARITY_WARNING = "ตั้ง D = ซ่อนทุกชิ้นของ rarity นั้น รวมตัวที่ mod ดีในหมวดอื่นด้วย"
EQUIP_HINT = ("ค่าเริ่มต้น = block ของ NeverSink · ตั้งค่าเอง = ทุก rarity เป็น S/A/B/C/D (เริ่มที่ B) ชนะทุกชิ้นของ class+rarity นั้น "
              "รวมของดีที่ NeverSink จัดไว้ · D = ซ่อนทั้งหมด · Unique ตั้งที่หมวด Unique · Flask/Charm/Tincture มีหมวดของตัวเอง")
EQUIP_GROUP_AUTO = "ตั้งทั้งกลุ่ม…"
EQUIP_GROUP_DEFAULT = "ค่าเริ่มต้น"      # every row of the group back to NeverSink
_FONT = ("Segoe UI", 9)
_SMALL = ("Segoe UI", 8)
# colour of the tier suffix in the list (readable on the dark list background)
TIER_COLORS = {"S": "#FF7A66", "A": "#F2A93B", "B": "#8FD16A", "C": "#6FB1C2", "D": "#8A8A8A", "T": "#4FD8E0"}


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
        return ui_theme.calm(ttk.Combobox(parent, textvariable=var, values=values, width=width, state="readonly",
                                          font=_FONT))

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

        # 2) the tier's style, right here (colours, opacity, size, icon, beam, sound) - the sound is this tab's own
        st = tk.Frame(self, bg=_BG)
        st.pack(fill=tk.X, padx=6, pady=2)
        self._label(st, "2) สไตล์ของ tier:").grid(row=0, column=0, sticky="nw")
        self._tier_editor = StyleEditor(st, None, sample_text="ตัวอย่าง", on_change=self._tier_style_changed, compact=True)
        self._tier_editor.grid(row=0, column=1, sticky="w", padx=6)
        side = tk.Frame(st, bg=_BG)
        side.grid(row=0, column=2, sticky="nw", padx=6)
        self._tier_reset = self._btn(side, "รีเซ็ตเป็นค่า NeverSink", self._reset_tier_style)
        self._tier_reset.pack(anchor="w", pady=(2, 8))
        # minimum stack size of the tier (only stackable names are affected)
        self._label(side, "โชว์เมื่อจำนวน ≥").pack(anchor="w")
        self.v_tier_stack = tk.StringVar(value="1")
        self._tier_stack_entry = self._entry(side, self.v_tier_stack, 5)
        self._tier_stack_entry.pack(anchor="w", pady=2)
        self._tier_stack_entry.bind("<KeyRelease>", lambda _e: self._apply_tier_stack())
        self._label(side, "(1 = โชว์ทุกชิ้น · ใช้กับของที่\nstack ได้ · ค่ารายชิ้นที่สูงกว่าชนะ)", fg="#777",
                    font=_SMALL, justify=tk.LEFT).pack(anchor="w")

        self._sub = ttk.Notebook(self)
        self._sub.pack(fill=tk.BOTH, expand=True, padx=4, pady=(4, 2))
        self._sub_frames = {}
        names = [("items", "3) หมวด / ไอเท็ม"), ("gold", "Gold"), ("map", "Waystone" if self.model.game == "poe2" else "Map")]
        if self.model.game == "poe2":
            names.append(("tablet", "Tablet"))
        names += [("gem", "Gem"), ("custom", "พิมพ์เอง")]
        for key, text in names:
            fr = tk.Frame(self._sub, bg=_BG, padx=4, pady=4)
            self._sub.add(fr, text=text)
            self._sub_frames[key] = fr
        self._style_eds: dict = {}
        self._build_items(self._sub_frames["items"])
        self._build_parts()

    def _build_items(self, f) -> None:
        r = tk.Frame(f, bg=_BG)
        r.pack(fill=tk.X)
        self.cat_var = tk.StringVar()
        self._cat_combo = self._combo(r, self.cat_var, [], width=30)
        self._cat_combo.pack(side=tk.LEFT)
        self._cat_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh_list(), add="+")
        self.query = tk.StringVar()
        self._label(r, " ค้นหา:", font=_SMALL).pack(side=tk.LEFT)
        self._search = self._entry(r, self.query, width=16)
        self._search.pack(side=tk.LEFT, padx=2)
        self.query.trace_add("write", lambda *_a: self.refresh_list())
        self._cat_info = self._label(f, "", fg="#9a9a9a", font=_SMALL, anchor="w")
        self._cat_info.pack(fill=tk.X, pady=(2, 0))

        # the "Flask / Charm" category has no list: one box per row (Flask, Charm) - default = NeverSink's blocks, or
        # "set myself" = Normal / Magic each S / A / B / C / D (start at B)
        self._flask_box = tk.Frame(f, bg=_BG)
        self.v_flask_mode, self.v_flask_rar, self._flask_custom_frames = {}, {}, {}
        for fr in self.model.flask_rows():
            rid = fr["id"]
            box = tk.Frame(self._flask_box, bg=_BG, highlightthickness=1, highlightbackground="#3a3a3a")
            box.pack(fill=tk.X, pady=3, padx=1)
            self._label(box, fr["label"], fg="#c9b37a", font=("Segoe UI", 9, "bold"), anchor="w").pack(fill=tk.X, padx=6, pady=(3, 0))
            self.v_flask_mode[rid] = tk.StringVar(value="default")
            for val, text in (("default", "ค่าเริ่มต้น (block ของ NeverSink ทั้งหมดของแถวนี้)"), ("custom", "ตั้งค่าเอง")):
                tk.Radiobutton(box, text=text, variable=self.v_flask_mode[rid], value=val, bg=_BG, fg=_FG, selectcolor="#2A2020",
                               activebackground=_BG, activeforeground=_FG, font=_FONT, anchor="w",
                               command=lambda r=rid: self._flask_mode(r)).pack(fill=tk.X, padx=14)
            cf = tk.Frame(box, bg=_BG)
            self._flask_custom_frames[rid] = cf
            line = tk.Frame(cf, bg=_BG)
            line.pack(fill=tk.X, padx=14)
            self.v_flask_rar[rid] = {}
            for rar in w.RARITY_CHOICES:
                self._label(line, rar).pack(side=tk.LEFT, padx=(0, 2))
                self.v_flask_rar[rid][rar] = tk.StringVar(value="B")
                c = self._combo(line, self.v_flask_rar[rid][rar], list(ALL_CHOICES), width=TIER_BOX_WIDTH)
                c.pack(side=tk.LEFT, padx=(0, 8))
                c.bind("<<ComboboxSelected>>", lambda _e, r=rid, q=rar: self._flask_rarity(r, q), add="+")
            self._label(cf, RARITY_WARNING, fg="#d9a441", font=_SMALL, anchor="w").pack(fill=tk.X, padx=14, pady=(0, 3))
        self._label(self._flask_box, "Unique ตั้งที่หมวด Unique · แถวที่เป็น \"ค่าเริ่มต้น\" ใช้ block ของ NeverSink ตามเดิม",
                    fg="#777", font=_SMALL, anchor="w").pack(fill=tk.X)
        self._build_equip(f)
        # everything of the item list lives in one frame so the Flask / Charm page can replace it
        self._list_box = tk.Frame(f, bg=_BG)
        self._list_box.pack(fill=tk.BOTH, expand=True)
        lb = self._list_box
        wrap = tk.Frame(lb, bg=_BG)
        wrap.pack(fill=tk.BOTH, expand=True)
        style = ttk.Style(self)
        style.configure("Wl.Treeview", background=_INPUT_BG, fieldbackground=_INPUT_BG, foreground=_FG,
                        rowheight=20, borderwidth=0, font=_FONT)
        style.configure("Wl.Treeview.Heading", background=_BUTTON_BG, foreground=_FG, font=_SMALL, relief="flat")
        style.map("Wl.Treeview", background=[("selected", "#4a3d20")], foreground=[("selected", "#FFFFFF")])
        self.tree = ttk.Treeview(wrap, columns=("name", "tier", "mark"), show="headings", style="Wl.Treeview",
                                 height=6, selectmode="extended")
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

        self._warn = self._label(lb, "", fg="#E0B060", font=_SMALL, anchor="w", justify=tk.LEFT, wraplength=420)
        self._warn.pack(fill=tk.X)
        b1 = tk.Frame(lb, bg=_BG)
        b1.pack(fill=tk.X, pady=(3, 0))
        self._act_btns = []
        for text, cmd in (("ทั้งหมวด → tier นี้", lambda: self._set_cat(self.active.get())),
                          ("ทั้งหมวด → D (ซ่อน)", lambda: self._set_cat("D")),
                          ("ย้ายที่เลือก → tier นี้", self._move_selected)):
            b = self._btn(b1, text, cmd)
            b.pack(side=tk.LEFT, padx=2)
            self._act_btns.append(b)
        b2 = tk.Frame(lb, bg=_BG)
        b2.pack(fill=tk.X, pady=(3, 0))
        for text, cmd in (("รีเซ็ตที่เลือกเป็นค่า NeverSink", self._reset_selected),
                          ("รีเซ็ตทั้งหมวด", self._reset_cat)):
            b = self._btn(b2, text, cmd)
            b.pack(side=tk.LEFT, padx=2)
            self._act_btns.append(b)
        b3 = tk.Frame(lb, bg=_BG)
        b3.pack(fill=tk.X, pady=(3, 0))
        self._label(b3, "จำนวนขั้นต่ำของที่เลือก ≥").pack(side=tk.LEFT, padx=(2, 0))
        self.v_item_stack = tk.StringVar(value="1")
        self._item_stack_entry = self._entry(b3, self.v_item_stack, 5)
        self._item_stack_entry.pack(side=tk.LEFT, padx=4)
        b = self._btn(b3, "ตั้งที่เลือก", self._set_item_stack)
        b.pack(side=tk.LEFT, padx=2)
        self._act_btns.append(b)
        self._label(b3, "(1 = โชว์ทุกชิ้น)", fg="#777", font=_SMALL).pack(side=tk.LEFT, padx=4)

    def _style_editor(self, parent, label: str, sample: str) -> StyleEditor:
        """An inline style editor for one label (G / Map / Tablet / Gem): every edit goes to the model at once."""
        box = tk.Frame(parent, bg=_BG)
        box.pack(anchor="w", pady=(6, 2))
        ed = StyleEditor(box, self.model.effective_style(label), sample_text=sample,
                         on_change=lambda: self._part_style_changed(label), compact=True)
        ed.grid(row=0, column=0, sticky="w")
        self._btn(box, "รีเซ็ตเป็นค่า NeverSink", lambda: self._reset_part_style(label)).grid(
            row=0, column=1, sticky="nw", padx=8, pady=2)
        self._style_eds[label] = ed
        return ed

    def _part_style_changed(self, label: str) -> None:
        self.model.set_style_from_editor(label, self._style_eds[label].get_style())
        self._changed()

    def _reset_part_style(self, label: str) -> None:
        self.model.set_style(label, None)
        self._style_eds[label].set_style(self.model.effective_style(label))
        self._changed()

    def _build_parts(self) -> None:
        m = self.model
        F = self._sub_frames
        # gold
        g = tk.Frame(F["gold"], bg=_BG)
        g.pack(fill=tk.X, pady=2)
        self.v_gold = tk.BooleanVar(value=m.gold)
        self._check(g, "Gold", self.v_gold).pack(side=tk.LEFT)
        self._label(g, "จำนวน ≥").pack(side=tk.LEFT, padx=(6, 2))
        self.v_gold_min = tk.StringVar(value=str(m.gold_min))
        e = self._entry(g, self.v_gold_min, 6)
        e.pack(side=tk.LEFT)
        e.bind("<KeyRelease>", lambda _e: self._parts_changed())
        self._label(F["gold"], "(ไม่ติ๊ก = โชว์ตามเกม)", fg="#777", font=_SMALL).pack(anchor="w")
        self._style_editor(F["gold"], "G", "Gold")
        # map / waystone
        name = "Waystone" if m.game == "poe2" else "Map"
        mp = tk.Frame(F["map"], bg=_BG)
        mp.pack(fill=tk.X, pady=2)
        self.v_map = tk.BooleanVar(value=m.map_on)
        self._check(mp, f"{name} (ต้องผ่านทั้ง 2 เงื่อนไข)", self.v_map).pack(side=tk.LEFT)
        mp2 = tk.Frame(F["map"], bg=_BG)
        mp2.pack(fill=tk.X, pady=(0, 2))
        self._label(mp2, "   tier ≥").pack(side=tk.LEFT)
        self.v_map_tier = tk.StringVar(value=str(m.map_tier))
        e = self._entry(mp2, self.v_map_tier, 4)
        e.pack(side=tk.LEFT, padx=2)
        e.bind("<KeyRelease>", lambda _e: self._parts_changed())
        self._label(mp2, "rarity ≥").pack(side=tk.LEFT, padx=(6, 2))
        self.v_map_rar = tk.StringVar(value=m.map_rarity)
        c = self._combo(mp2, self.v_map_rar, list(RARITIES), 8)
        c.pack(side=tk.LEFT)
        c.bind("<<ComboboxSelected>>", lambda _e: self._parts_changed(), add="+")
        self._label(F["map"], "   (ไม่ติ๊ก = โชว์ตามเกม · poe1: map พิเศษผ่านเสมอ)", fg="#777", font=_SMALL).pack(anchor="w")
        self._style_editor(F["map"], "Map", name)
        # tablet (poe2)
        if m.game == "poe2":
            self._label(F["tablet"], "Tablet โชว์เสมอ ยกเว้นตั้ง tier รายชิ้น (หมวด Tablet ที่แท็บ 3)", fg="#777",
                        font=_SMALL).pack(anchor="w")
            self._style_editor(F["tablet"], "Tablet", "Tablet")
        # gem
        self._gem_frame = tk.Frame(F["gem"], bg=_BG)
        self._gem_frame.pack(fill=tk.X, pady=(2, 2))
        self._build_gems(self._gem_frame)
        self._label(F["gem"], "สไตล์ของ Gem = สไตล์ของ tier ที่เลือกข้างบน (แก้ตรงนี้ = เปลี่ยนเฉพาะ Gem)", fg="#777",
                    font=_SMALL).pack(anchor="w")
        self._style_editor(F["gem"], "Gem", "Gem")
        # typed names
        self._build_custom(F["custom"])

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
        c.bind("<<ComboboxSelected>>", lambda _e: self._parts_changed(), add="+")
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
        if "Gem" in self._style_eds:                       # the Gem look follows the tier picked for the gems
            self._style_eds["Gem"].set_style(self.model.effective_style("Gem"))
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
        return [self._tier_reset, self._cat_combo, self._search, self._tier_stack_entry, self._item_stack_entry,
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
        """The tier editor shows the picked tier's effective look (its own preview is the sample)."""
        t = self.active.get()
        if t:
            self._tier_editor.set_style(self.model.effective_style(t))

    def _tier_style_changed(self) -> None:
        t = self.active.get()
        if t:
            self.model.set_style_from_editor(t, self._tier_editor.get_style())
            self._changed()

    def _reset_tier_style(self) -> None:
        t = self.active.get()
        if t:
            self.model.set_style(t, None)
            self.refresh_preview()
            self._changed()

    def refresh_styles(self) -> None:
        """Show the model's looks again (the lists / NeverSink arrived, or a file was opened)."""
        self.refresh_preview()
        for label, ed in self._style_eds.items():
            ed.set_style(self.model.effective_style(label))

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
        self.refresh_styles()
        self.refresh_list()

    def _build_equip(self, f) -> None:
        """"อุปกรณ์ตาม class": one sub tab per group (weapon / armour / jewellery / other; a group with no class in this game
        has no tab). Each tab has the "set the whole group" boxes (Normal / Magic / Rare) on top and one row per class below
        it - default = NeverSink's blocks, or "set myself" = Normal / Magic / Rare each S / A / B / C / D. What D means is
        said once, above the tabs. Each tab scrolls (many rows)."""
        self._equip_box = tk.Frame(f, bg=_BG)
        self._label(self._equip_box, EQUIP_HINT, fg="#777", font=_SMALL, anchor="w", wraplength=760,
                    justify=tk.LEFT).pack(fill=tk.X)
        self._equip_nb = ttk.Notebook(self._equip_box)
        self._equip_nb.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self.v_eq_mode, self.v_eq_rar, self._eq_combos, self.v_eq_grp = {}, {}, {}, {}
        self._eq_grp_combos: dict = {}
        self._equip_canvases: dict = {}
        self._equip_canvas = None
        for g in self.model.equip_groups():
            if not g["classes"]:
                continue
            tab = tk.Frame(self._equip_nb, bg=_BG, padx=2, pady=4)
            self._equip_nb.add(tab, text=g["label"])
            wrap = tk.Frame(tab, bg=_BG)
            wrap.pack(fill=tk.BOTH, expand=True)
            canvas = tk.Canvas(wrap, bg=_BG, highlightthickness=0, height=250)
            sb = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=canvas.yview)
            inner = tk.Frame(canvas, bg=_BG)
            win = canvas.create_window((0, 0), window=inner, anchor="nw")
            inner.bind("<Configure>", lambda _e, c=canvas: c.configure(scrollregion=c.bbox("all")))
            canvas.bind("<Configure>", lambda e, c=canvas, w_=win: c.itemconfigure(w_, width=e.width))
            canvas.configure(yscrollcommand=sb.set)
            sb.pack(side=tk.RIGHT, fill=tk.Y)
            canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            wheel = lambda e, c=canvas: c.yview_scroll(-1 if e.delta > 0 else 1, "units")
            canvas.bind("<Enter>", lambda _e, c=canvas, fn=wheel: c.bind_all("<MouseWheel>", fn))
            canvas.bind("<Leave>", lambda _e, c=canvas: c.unbind_all("<MouseWheel>"))
            self._equip_canvases[g["id"]] = canvas
            self._equip_canvas = self._equip_canvas or canvas
            head = tk.Frame(inner, bg=_BG)
            head.pack(fill=tk.X, pady=(4, 4))
            self._label(head, "ตั้งทั้งกลุ่ม", fg="#c9b37a", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT, padx=(2, 10))
            self.v_eq_grp[g["id"]] = {}
            for rar in w.EQUIP_CHOICES:
                self._label(head, rar, font=_SMALL).pack(side=tk.LEFT, padx=(0, 2))
                var = tk.StringVar(value=EQUIP_GROUP_AUTO)
                self.v_eq_grp[g["id"]][rar] = var
                c = self._combo(head, var, [EQUIP_GROUP_AUTO, EQUIP_GROUP_DEFAULT] + list(ALL_CHOICES), width=GROUP_BOX_WIDTH)
                c.pack(side=tk.LEFT, padx=(0, 8))
                self._eq_grp_combos.setdefault(g["id"], {})[rar] = c
                c.bind("<<ComboboxSelected>>", lambda _e, gid=g["id"], r=rar: self._equip_group(gid, r), add="+")
            for fr in g["classes"]:
                cid = fr["id"]
                line = tk.Frame(inner, bg=_BG)
                line.pack(fill=tk.X, padx=6)
                self._label(line, fr["label"], width=25, anchor="w").pack(side=tk.LEFT)
                self.v_eq_mode[cid] = tk.StringVar(value="default")
                for val, text in (("default", "ค่าเริ่มต้น"), ("custom", "ตั้งค่าเอง")):
                    tk.Radiobutton(line, text=text, variable=self.v_eq_mode[cid], value=val, bg=_BG, fg=_FG, selectcolor="#2A2020",
                                   activebackground=_BG, activeforeground=_FG, font=_FONT,
                                   command=lambda c=cid: self._equip_mode(c)).pack(side=tk.LEFT, padx=(0, 6))
                self.v_eq_rar[cid], self._eq_combos[cid] = {}, []
                for rar in w.EQUIP_CHOICES:
                    self._label(line, rar, font=_SMALL).pack(side=tk.LEFT, padx=(4, 2))
                    var = tk.StringVar(value="B")
                    self.v_eq_rar[cid][rar] = var
                    c = self._combo(line, var, list(ALL_CHOICES), width=TIER_BOX_WIDTH)
                    c.pack(side=tk.LEFT)
                    c.bind("<<ComboboxSelected>>", lambda _e, cc=cid, r=rar: self._equip_rarity(cc, r), add="+")
                    self._eq_combos[cid].append(c)

    def _refresh_equip(self) -> None:
        for g in self.model.equip_groups():
            for fr in g["classes"]:
                cid = fr["id"]
                if cid not in self.v_eq_mode:
                    continue
                self.v_eq_mode[cid].set("custom" if fr["custom"] else "default")
                for rar, var in self.v_eq_rar[cid].items():
                    var.set(fr["tiers"].get(rar) or "B")
                for c in self._eq_combos[cid]:
                    c.configure(state="readonly" if fr["custom"] else "disabled")
            for var in self.v_eq_grp.get(g["id"], {}).values():
                var.set(EQUIP_GROUP_AUTO)
            for c in self._eq_grp_combos.get(g["id"], {}).values():       # the prompt is shown, never highlighted
                c.selection_clear()

    def _equip_mode(self, cid: str) -> None:
        self.model.set_equip_custom(cid, self.v_eq_mode[cid].get() == "custom")
        self.refresh_list()
        self._changed()

    def _equip_rarity(self, cid: str, rar: str) -> None:
        val = self.v_eq_rar[cid][rar].get()
        self.model.set_equip_rarity(cid, rar, val if val in ALL_CHOICES else None)
        self.refresh_list()
        self._changed()

    def _equip_group(self, gid: str, rar: str) -> None:
        val = self.v_eq_grp[gid][rar].get()
        if val == EQUIP_GROUP_AUTO:
            return
        self.model.set_equip_group(gid, rar, val if val in ALL_CHOICES else None)      # "ค่าเริ่มต้น" = None = every row default
        self.refresh_list()
        self._changed()

    def refresh_list(self) -> None:
        cat = self.current_category()
        self.tree.delete(*self.tree.get_children())
        self._row_keys = {}
        if not cat:
            return
        if not self.model.loaded:
            self._cat_info.configure(text="กำลังโหลดรายการ… (hub + NeverSink)")
            return
        if cat == EQUIP_CATEGORY:                       # no list: classes by group, each with its own controls
            self._list_box.pack_forget()
            self._flask_box.pack_forget()
            if not self._equip_box.winfo_manager():
                self._equip_box.pack(fill=tk.BOTH, expand=True, pady=(4, 2))
            self._refresh_equip()
            n = self.model.changed_count(cat)
            self._cat_info.configure(text="ตั้งค่าเองแล้ว " + (f"{n} class" if n else "ไม่มี — ใช้ NeverSink ทั้งหมด"))
            self._warn.configure(text="")
            return
        self._equip_box.pack_forget()
        if cat == FLASK_CATEGORY:                       # no list: the two rows (Flask, Charm) with their own controls
            self._list_box.pack_forget()
            if not self._flask_box.winfo_manager():
                self._flask_box.pack(fill=tk.X, pady=(4, 2))
            self._refresh_flask()
            n = self.model.changed_count(cat)
            self._cat_info.configure(text="ตั้งค่าเองแล้ว " + (f"{n} แถว" if n else "ไม่มี — ใช้ NeverSink ทั้งหมด"))
            self._warn.configure(text="")
            return
        self._flask_box.pack_forget()
        if not self._list_box.winfo_manager():
            self._list_box.pack(fill=tk.BOTH, expand=True)
        rows = self.model.rows(cat, self.query.get())
        for r in rows:
            on = r.tier != w.HIDE_TIER
            tier_text = tier_label(r.tier) if on else w.HIDE_TIER
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

    def _refresh_flask(self) -> None:
        for fr in self.model.flask_rows():
            rid = fr["id"]
            self.v_flask_mode[rid].set("custom" if fr["custom"] else "default")
            for rar, var in self.v_flask_rar[rid].items():
                var.set(fr["tiers"].get(rar) or "B")
            cf = self._flask_custom_frames[rid]
            if fr["custom"]:
                if not cf.winfo_manager():
                    cf.pack(fill=tk.X)
            else:
                cf.pack_forget()

    def _flask_mode(self, rid: str) -> None:
        self.model.set_flask_custom(rid, self.v_flask_mode[rid].get() == "custom")
        self.refresh_list()
        self._changed()

    def _flask_rarity(self, rid: str, rar: str) -> None:
        val = self.v_flask_rar[rid][rar].get()
        self.model.set_flask_rarity(rid, rar, val if val in ALL_CHOICES else None)
        self.refresh_list()
        self._changed()

    def refresh_sounds(self) -> None:
        """(kept for callers: this tab's sounds are in its style editors; only Q is shared and set elsewhere)"""

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

    # called by the window once hub / NeverSink data arrived
    def data_loaded(self) -> None:
        self.refresh_all()


def _color(rgba, default: str) -> str:
    return "#%02x%02x%02x" % tuple(rgba[:3]) if rgba else default
