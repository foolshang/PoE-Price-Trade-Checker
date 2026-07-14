"""F5 popup: โชว์ mod ของ item ให้ติ๊กเลือก + ใส่ min/max เอง ก่อนเปิดหน้า trade.

แบบ "เบา" สไตล์ awakened-poe-trade: เลือก mod → กดค้นหา → เปิด browser
(ไม่แสดงผลราคาในหน้าต่าง). แก้ปัญหา desecrated ที่ราก — ผู้ใช้ไม่ติ๊ก mod
ที่ทำ query พังได้เอง."""
from __future__ import annotations
import tkinter as tk
from typing import Callable, Optional

from .capture import get_cursor_pos
from .models import ModValue, ParsedItem

_BG, _FG, _ACC = "#1C1C1C", "#E8D5A0", "#C8A050"
_DIM = "#777777"
_ENTRY_BG = "#2A2A2A"
_FONT = ("Segoe UI", 9)
_FONT_SMALL = ("Segoe UI", 8)
_FONT_BOLD = ("Segoe UI", 10, "bold")

# type ที่ติ๊กมาให้ตั้งแต่แรก — เหมือน search ในเกม (implicit + explicit, ไม่เอา desecrated)
_DEFAULT_CHECKED = {"explicit", "implicit"}
_MIN_PCT = 0.8          # default ช่อง min = value × 0.8
_MAX_TEXT = 56          # ตัดข้อความ mod ยาวเกิน

_TYPE_TAG = {
    "implicit":   "[imp] ",
    "desecrated": "[des] ",
    "rune":       "[rune] ",
    "enchant":    "[ench] ",
    "fractured":  "[frac] ",
}


class ModPickerWindow:
    """หน้าต่างเลือก mod. rows = [(ModValue, stat_id|None), ...] (resolve id มาแล้ว)."""

    def __init__(self, parent: tk.Misc, item: ParsedItem,
                 rows: list[tuple[ModValue, Optional[str]]],
                 on_search: Callable[[list[dict]], None],
                 annos: Optional[dict] = None, summary: str = "",
                 badge_colors: Optional[list[Optional[str]]] = None,
                 badge_style: str = "dot"):
        self._on_search = on_search
        self._rows: list[dict] = []
        self._annos = annos or {}
        self._badge_colors = badge_colors or [None] * len(rows)
        self._badge_style = badge_style if badge_style in ("dot", "text", "frame") else "dot"

        win = tk.Toplevel(parent)
        self._win = win
        win.withdraw()                      # ซ่อนก่อน จัดตำแหน่งเสร็จค่อยโชว์ (กันกระพริบ)
        win.title("เลือก mod")
        win.configure(bg=_BG)
        win.attributes("-topmost", True)
        win.resizable(False, False)

        head = item.item_name or item.base_type or "?"
        tk.Label(win, text=head, bg=_BG, fg=_ACC, font=_FONT_BOLD).pack(
            anchor="w", padx=12, pady=(10, 0))
        sub = item.rarity + (f"  ·  {item.base_type}"
                             if item.base_type and item.base_type != head else "")
        tk.Label(win, text=sub, bg=_BG, fg=_DIM, font=_FONT_SMALL).pack(
            anchor="w", padx=12, pady=(0, 2))
        if summary:
            tk.Label(win, text=summary, bg=_BG, fg="#7FBF7F", font=_FONT_SMALL).pack(
                anchor="w", padx=12, pady=(0, 6))

        body = tk.Frame(win, bg=_BG)
        body.pack(fill=tk.BOTH, expand=True, padx=10)

        for i, (mod, sid) in enumerate(rows):
            badge = self._badge_colors[i] if i < len(self._badge_colors) else None
            self._add_row(body, mod, sid, badge)

        # ปุ่มเลือกทั้งหมด / ไม่เลือกเลย
        sel = tk.Frame(win, bg=_BG)
        sel.pack(fill=tk.X, padx=12, pady=(4, 0))
        for text, val in (("เลือกทั้งหมด", True), ("ไม่เลือกเลย", False)):
            tk.Button(sel, text=text, command=lambda v=val: self._set_all(v),
                      bg=_BG, fg=_DIM, activebackground=_BG, activeforeground=_FG,
                      relief=tk.FLAT, font=_FONT_SMALL, cursor="hand2",
                      padx=2, pady=0, bd=0).pack(side=tk.LEFT, padx=(0, 8))

        btns = tk.Frame(win, bg=_BG)
        btns.pack(fill=tk.X, padx=10, pady=(6, 10))
        tk.Button(btns, text="🔎 ค้นหา  (Enter)", command=self._do_search,
                  bg="#3A3020", fg=_FG, activebackground=_ACC, activeforeground="#000",
                  relief=tk.FLAT, font=_FONT, padx=10, pady=4, cursor="hand2"
                  ).pack(side=tk.LEFT)
        tk.Button(btns, text="ยกเลิก  (Esc)", command=self._close,
                  bg="#2A2A2A", fg=_DIM, activebackground="#444", activeforeground=_FG,
                  relief=tk.FLAT, font=_FONT, padx=10, pady=4, cursor="hand2"
                  ).pack(side=tk.RIGHT)

        win.bind("<Return>", self._do_search)
        win.bind("<Escape>", lambda _e: self._close())
        win.protocol("WM_DELETE_WINDOW", self._close)

        self._place_near_cursor()
        win.deiconify()
        win.lift()
        win.focus_force()

    # ------------------------------------------------------------------

    def _add_row(self, parent: tk.Frame, mod: ModValue, sid: Optional[str],
                 pop_color: Optional[str] = None) -> None:
        """pop_color = mod-badge color (red/gold/None) from ModBadgeDB, rendered per
        self._badge_style: "dot" prepends a colored ● (rest of the line unchanged),
        "text" tints the whole line's fg, "frame" outlines the row."""
        mtype = getattr(mod, "mod_type", "explicit") or "explicit"
        tag = _TYPE_TAG.get(mtype, "")
        anno = self._annos.get(getattr(mod, "group", -1)) or {}
        tier_badge = ""
        if anno.get("tier"):
            tot = anno.get("total", 0)
            tier_badge = f"[T{anno['tier']}/{tot}] " if tot else f"[T{anno['tier']}] "
        money = "💰 " if anno.get("money") else ""
        text = money + tier_badge + tag + mod.text
        if len(text) > _MAX_TEXT:
            text = text[:_MAX_TEXT - 1] + "…"

        row = tk.Frame(parent, bg=_BG)
        if pop_color and self._badge_style == "frame":
            row.configure(highlightthickness=1, highlightbackground=pop_color,
                          highlightcolor=pop_color)
        row.pack(fill=tk.X, pady=1)

        if self._badge_style == "dot":
            tk.Label(row, text="●", bg=_BG, fg=(pop_color or _BG),
                     font=_FONT, width=2).pack(side=tk.LEFT)

        var = tk.BooleanVar(value=bool(sid) and mtype in _DEFAULT_CHECKED)
        state = tk.NORMAL if sid else tk.DISABLED
        if pop_color and self._badge_style == "text":
            fg = pop_color
        else:
            fg = (_ACC if anno.get("money") else _FG) if sid else _DIM
        cb = tk.Checkbutton(row, text=text if sid else text + "  (ไม่พบ id)",
                            variable=var, state=state,
                            bg=_BG, fg=fg, selectcolor="#2A2020",
                            activebackground=_BG, activeforeground=fg,
                            font=_FONT, anchor="w")
        cb.pack(side=tk.LEFT, fill=tk.X, expand=True)

        def entry():
            e = tk.Entry(row, width=6, bg=_ENTRY_BG, fg=_FG, insertbackground=_FG,
                         relief=tk.FLAT, font=_FONT, justify=tk.CENTER,
                         state=tk.NORMAL if sid else tk.DISABLED,
                         disabledbackground=_BG)
            e.pack(side=tk.RIGHT, padx=2)
            return e

        max_e = entry()     # ขวาสุด = max
        min_e = entry()     # ถัดมา = min
        if sid and mod.value is not None:
            min_e.insert(0, f"{round(mod.value * _MIN_PCT, 2):g}")

        self._rows.append({"var": var, "sid": sid, "min": min_e, "max": max_e})

    def _set_all(self, value: bool) -> None:
        for r in self._rows:
            if r["sid"]:
                r["var"].set(value)

    def _do_search(self, *_ignored) -> None:
        filters: list[dict] = []
        for r in self._rows:
            if not r["sid"] or not r["var"].get():
                continue
            f: dict = {"id": r["sid"], "disabled": False}
            val: dict = {}
            for key, widget in (("min", r["min"]), ("max", r["max"])):
                raw = widget.get().strip()
                if not raw:
                    continue
                try:
                    val[key] = float(raw)
                except ValueError:
                    pass                    # พิมพ์ไม่ใช่เลข → ข้ามช่องนั้น
            if val:
                f["value"] = val
            filters.append(f)
        self._close()
        self._on_search(filters)            # list ว่างได้ — trade_url จะไม่ใส่ stats เอง

    def _close(self) -> None:
        try:
            self._win.destroy()
        except Exception:
            pass

    def _place_near_cursor(self) -> None:
        win = self._win
        try:
            cx, cy = get_cursor_pos()
        except Exception:
            cx, cy = 200, 200
        win.update_idletasks()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        x = min(max(cx + 16, 0), max(sw - w - 8, 0))
        y = min(max(cy - h // 2, 0), max(sh - h - 8, 0))
        win.geometry(f"+{x}+{y}")
