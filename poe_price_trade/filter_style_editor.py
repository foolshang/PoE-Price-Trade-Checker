"""Tk widget that edits one item style (see filter_style) - used for Q now, and for every other
styled thing (Gold, Tablet, Map, S / A / B) in the whitelist tab later."""
from __future__ import annotations
import tkinter as tk
from tkinter import colorchooser, filedialog, ttk
from typing import Callable, Optional

from . import filter_style, ui_theme

_BG = "#1C1C1C"
_FG = "#E8D5A0"
_ACCENT = "#C8A050"
_INPUT_BG = "#2A2A2A"
_BUTTON_BG = "#3A3020"
_FONT = ("Segoe UI", 9)
_SMALL = ("Segoe UI", 8)


def _hex(rgba) -> str:
    return "#%02x%02x%02x" % tuple(rgba[:3])


class StyleEditor(tk.Frame):
    """get_style() / set_style() work on filter_style dicts; on_change() fires after every edit."""

    def __init__(self, parent, style=None, on_change: Optional[Callable[[], None]] = None,
                 allow_file_sound: bool = True, sample_text: str = "Quest Item", show_sound: bool = True,
                 compact: bool = False):
        super().__init__(parent, bg=_BG)
        ui_theme.apply(self)
        self._on_change = on_change
        self._allow_file = allow_file_sound
        self._show_sound = show_sound        # False: no sound part (kept for callers that set it elsewhere)
        self._compact = compact              # inline use: the sound on one row, a one-line sample
        self._sample = sample_text
        self._color: dict = {"text": [255, 255, 255, 255], "border": [255, 255, 255, 255], "bg": [0, 0, 0, 255]}
        self._on: dict = {}
        self._alpha: dict = {}              # key -> StringVar (0..255), the one value the entry / slider / tick share
        self._alpha_prev: dict = {}         # key -> the opacity to come back to when "โปร่งใส" is unticked
        self._clear: dict = {}              # key -> BooleanVar of the "โปร่งใส" tick
        self._slider: dict = {}
        self._swatch: dict = {}
        self._syncing = False
        self._build()
        self.set_style(style)

    # -- building ---------------------------------------------------------

    def _check(self, parent, text, var, command=None):
        return tk.Checkbutton(parent, text=text, variable=var, bg=_BG, fg=_FG, selectcolor="#2A2020",
                              activebackground=_BG, font=_FONT, command=command or self._changed)

    def _combo(self, parent, values, var, width=10):
        cb = ui_theme.calm(ttk.Combobox(parent, textvariable=var, values=values, width=width, state="readonly",
                                        font=_FONT))
        cb.bind("<<ComboboxSelected>>", lambda _e: self._changed(), add="+")
        return cb

    def _build(self) -> None:
        r = 0
        tk.Label(self, text="ความทึบ (255 = ทึบ, 0 = โปร่งใส)", bg=_BG, fg="#A89868", font=_SMALL).grid(
            row=r, column=2, columnspan=3, sticky="w", padx=(8, 0))
        r += 1
        for key, label in (("text", "สีตัวอักษร"), ("border", "สีกรอบ"), ("bg", "สีพื้น")):
            on = tk.BooleanVar()
            self._on[key] = on
            self._check(self, label, on).grid(row=r, column=0, sticky="w", padx=4, pady=2)
            sw = tk.Button(self, width=6, relief=tk.FLAT, command=lambda k=key: self._pick(k), cursor="hand2")
            sw.grid(row=r, column=1, padx=4)
            self._swatch[key] = sw
            a = tk.StringVar(value="255")
            self._alpha[key] = a
            self._alpha_prev[key] = 255
            e = tk.Entry(self, textvariable=a, width=4, bg=_INPUT_BG, fg=_FG, insertbackground=_FG, relief=tk.FLAT,
                         font=_FONT)
            e.grid(row=r, column=2, padx=(8, 2))
            e.bind("<KeyRelease>", lambda _e, k=key: self._alpha_typed(k))
            sc = tk.Scale(self, from_=0, to=255, orient=tk.HORIZONTAL, showvalue=False, length=110, width=10,
                          bg=_BG, fg=_FG, troughcolor=_INPUT_BG, highlightthickness=0, bd=0,
                          activebackground=_ACCENT, command=lambda v, k=key: self._alpha_slid(k, v))
            sc.grid(row=r, column=3, padx=2)
            self._slider[key] = sc
            clear = tk.BooleanVar()
            self._clear[key] = clear
            self._check(self, "โปร่งใส", clear, command=lambda k=key: self._clear_toggled(k)).grid(
                row=r, column=4, sticky="w", padx=(2, 4))
            r += 1

        self._size_on = tk.BooleanVar()
        self._size = tk.StringVar(value="40")
        self._check(self, "ขนาดตัวอักษร", self._size_on).grid(row=r, column=0, sticky="w", padx=4, pady=2)
        se = tk.Entry(self, textvariable=self._size, width=4, bg=_INPUT_BG, fg=_FG, insertbackground=_FG,
                      relief=tk.FLAT, font=_FONT)
        se.grid(row=r, column=1, sticky="w", padx=4)
        se.bind("<KeyRelease>", lambda _e: self._changed())
        tk.Label(self, text=f"({filter_style.FONT_MIN}-{filter_style.FONT_MAX})", bg=_BG, fg="#666",
                 font=_SMALL).grid(row=r, column=2, sticky="w")
        r += 1

        self._icon_on = tk.BooleanVar()
        self._icon_size = tk.StringVar(value="1")
        self._icon_color = tk.StringVar(value="Red")
        self._icon_shape = tk.StringVar(value="Star")
        self._check(self, "ไอคอนบนมินิแมป", self._icon_on).grid(row=r, column=0, sticky="w", padx=4, pady=2)
        box = tk.Frame(self, bg=_BG)
        box.grid(row=r, column=1, columnspan=3, sticky="w")
        self._combo(box, ["0", "1", "2"], self._icon_size, 3).pack(side=tk.LEFT, padx=2)
        self._combo(box, filter_style.COLORS, self._icon_color, 8).pack(side=tk.LEFT, padx=2)
        self._combo(box, filter_style.SHAPES, self._icon_shape, 14).pack(side=tk.LEFT, padx=2)
        r += 1

        self._eff_on = tk.BooleanVar()
        self._eff_color = tk.StringVar(value="Red")
        self._eff_temp = tk.BooleanVar()
        self._check(self, "แสงบีม (PlayEffect)", self._eff_on).grid(row=r, column=0, sticky="w", padx=4, pady=2)
        box = tk.Frame(self, bg=_BG)
        box.grid(row=r, column=1, columnspan=3, sticky="w")
        self._combo(box, filter_style.COLORS, self._eff_color, 8).pack(side=tk.LEFT, padx=2)
        self._check(box, "Temp (หายเมื่อเก็บ)", self._eff_temp).pack(side=tk.LEFT, padx=6)
        r += 1

        self._snd_kind = tk.StringVar(value="none")
        self._snd_id = tk.StringVar(value="1")
        self._snd_file = tk.StringVar(value="")
        self._snd_vol = tk.StringVar(value=str(filter_style.DEFAULT_VOLUME))
        snd_label = tk.Label(self, text="เสียง", bg=_BG, fg=_FG, font=_FONT)
        snd_label.grid(row=r, column=0, sticky="nw", padx=4, pady=2)
        box = tk.Frame(self, bg=_BG)
        box.grid(row=r, column=1, columnspan=3, sticky="w")
        if not self._show_sound:
            snd_label.grid_remove()
            box.grid_remove()
        rb = lambda text, val: tk.Radiobutton(box, text=text, variable=self._snd_kind, value=val, bg=_BG, fg=_FG,
                                              selectcolor="#2A2020", activebackground=_BG, font=_FONT,
                                              command=self._changed)
        if self._compact:                    # one row: none | game [id] | file [path] [Browse] | volume
            rb("ไม่มี", "none").grid(row=0, column=0, sticky="w")
            rb("เสียงเกม", "game").grid(row=0, column=1, sticky="w")
            self._combo(box, [str(i) for i in filter_style.SOUND_IDS], self._snd_id, 3).grid(row=0, column=2, padx=2)
            fcol = 3
            if self._allow_file:
                rb("ไฟล์", "file").grid(row=0, column=3, sticky="w")
                ui_theme.calm(tk.Entry(box, textvariable=self._snd_file, width=16, state="readonly", bg=_INPUT_BG, fg=_FG,
                         readonlybackground=_INPUT_BG, disabledforeground=_FG,
                         relief=tk.FLAT, font=_FONT)).grid(row=0, column=4, padx=2)
                tk.Button(box, text="Browse…", command=self._browse, bg=_BUTTON_BG, fg=_FG, relief=tk.FLAT, font=_FONT,
                          cursor="hand2").grid(row=0, column=5)
                fcol = 6
            tk.Label(box, text="volume", bg=_BG, fg=_FG, font=_SMALL).grid(row=0, column=fcol, padx=(8, 2))
            ve = tk.Entry(box, textvariable=self._snd_vol, width=5, bg=_INPUT_BG, fg=_FG, insertbackground=_FG,
                          relief=tk.FLAT, font=_FONT)
            ve.grid(row=0, column=fcol + 1, sticky="w")
            ve.bind("<KeyRelease>", lambda _e: self._changed())
        else:
            rb("ไม่มี", "none").grid(row=0, column=0, sticky="w")
            rb("เสียงเกม", "game").grid(row=1, column=0, sticky="w")
            self._combo(box, [str(i) for i in filter_style.SOUND_IDS], self._snd_id, 4).grid(row=1, column=1, padx=4)
            if self._allow_file:
                rb("ไฟล์เสียง", "file").grid(row=2, column=0, sticky="w")
                ui_theme.calm(tk.Entry(box, textvariable=self._snd_file, width=26, state="readonly", bg=_INPUT_BG, fg=_FG,
                         readonlybackground=_INPUT_BG, disabledforeground=_FG,
                         relief=tk.FLAT, font=_FONT)).grid(row=2, column=1, columnspan=2, padx=4, sticky="w")
                tk.Button(box, text="Browse…", command=self._browse, bg=_BUTTON_BG, fg=_FG, relief=tk.FLAT, font=_FONT,
                          cursor="hand2").grid(row=2, column=3)
            tk.Label(box, text="volume", bg=_BG, fg=_FG, font=_SMALL).grid(row=3, column=0, sticky="e")
            ve = tk.Entry(box, textvariable=self._snd_vol, width=5, bg=_INPUT_BG, fg=_FG, insertbackground=_FG,
                          relief=tk.FLAT, font=_FONT)
            ve.grid(row=3, column=1, sticky="w", padx=4)
            ve.bind("<KeyRelease>", lambda _e: self._changed())
        r += 1

        self._preview = tk.Label(self, text=self._sample, width=26, height=1 if self._compact else 2,
                                 font=("Segoe UI", 12, "bold"), bd=0, highlightthickness=3)
        self._preview.grid(row=r, column=0, columnspan=4, pady=(4, 2) if self._compact else (8, 4))

    # -- events -----------------------------------------------------------

    def _pick(self, key: str) -> None:
        rgb, _hexs = colorchooser.askcolor(color=_hex(self._color[key]), parent=self, title="เลือกสี")
        if rgb:
            self._color[key] = [int(rgb[0]), int(rgb[1]), int(rgb[2]), self._color[key][3]]
            self._on[key].set(True)
            self._changed()

    def _browse(self) -> None:
        path = filedialog.askopenfilename(
            parent=self, title="เลือกไฟล์เสียง",
            filetypes=[("Sound files", "*.mp3 *.wav *.ogg"), ("All files", "*.*")])
        if path:
            self._snd_file.set(path)
            self._snd_kind.set("file")
            self._changed()

    # -- opacity: entry, slider and the "โปร่งใส" tick are three views of one value ---

    def _set_alpha(self, key: str, value: int, from_slider: bool = False) -> None:
        value = max(0, min(255, int(value)))
        self._syncing = True
        try:
            self._alpha[key].set(str(value))
            if not from_slider:
                self._slider[key].set(value)
            self._clear[key].set(value == 0)
        finally:
            self._syncing = False
        if value > 0:
            self._alpha_prev[key] = value

    def _alpha_typed(self, key: str) -> None:
        text = self._alpha[key].get().strip()
        if text.isdigit():
            v = max(0, min(255, int(text)))
            self._syncing = True
            try:
                self._slider[key].set(v)
                self._clear[key].set(v == 0)
            finally:
                self._syncing = False
            if v > 0:
                self._alpha_prev[key] = v
        self._changed()

    def _alpha_slid(self, key: str, value) -> None:
        if self._syncing:
            return
        self._set_alpha(key, int(float(value)), from_slider=True)
        self._changed()

    def _clear_toggled(self, key: str) -> None:
        if self._clear[key].get():
            self._set_alpha(key, 0)
        else:
            self._set_alpha(key, self._alpha_prev.get(key) or 255)
        self._changed()

    def _changed(self) -> None:
        self._refresh_preview()
        if self._on_change:
            self._on_change()

    def _refresh_preview(self) -> None:
        for key, sw in self._swatch.items():
            c = self._color[key]
            sw.configure(bg=_hex(c), activebackground=_hex(c), state=tk.NORMAL)
        s = self.get_style()
        bg = _hex(s["bg"]) if s["bg"] else "#101010"
        fg = _hex(s["text"]) if s["text"] else "#C8C8C8"
        border = _hex(s["border"]) if s["border"] else bg
        size = s["size"] or 32
        self._preview.configure(bg=bg, fg=fg, highlightbackground=border, highlightcolor=border,
                                font=("Segoe UI", max(8, int(size * 0.4)), "bold"))

    # -- data -------------------------------------------------------------

    def get_style(self) -> dict:
        raw: dict = {}
        for key in ("text", "border", "bg"):
            if self._on[key].get():
                a = self._alpha[key].get().strip()
                rgb = self._color[key][:3]
                raw[key] = rgb + [int(a) if a.isdigit() else 255]
        if self._size_on.get():
            raw["size"] = self._size.get().strip() or None
        if self._icon_on.get():
            raw["icon"] = {"size": self._icon_size.get(), "color": self._icon_color.get(),
                           "shape": self._icon_shape.get()}
        if self._eff_on.get():
            raw["effect"] = {"color": self._eff_color.get(), "temp": self._eff_temp.get()}
        raw["sound"] = {"kind": self._snd_kind.get(), "id": self._snd_id.get(), "file": self._snd_file.get(),
                        "volume": self._snd_vol.get()}
        return filter_style.normalize_style(raw)

    def set_style(self, style) -> None:
        s = filter_style.normalize_style(style)
        for key in ("text", "border", "bg"):
            if s[key]:
                self._color[key] = list(s[key])
            self._on[key].set(bool(s[key]))
            self._set_alpha(key, self._color[key][3])
        self._size_on.set(s["size"] is not None)
        if s["size"] is not None:
            self._size.set(str(s["size"]))
        self._icon_on.set(bool(s["icon"]))
        if s["icon"]:
            self._icon_size.set(str(s["icon"]["size"]))
            self._icon_color.set(s["icon"]["color"])
            self._icon_shape.set(s["icon"]["shape"])
        self._eff_on.set(bool(s["effect"]))
        if s["effect"]:
            self._eff_color.set(s["effect"]["color"])
            self._eff_temp.set(s["effect"]["temp"])
        snd = s["sound"]
        self._snd_kind.set(snd["kind"] if (snd["kind"] != "file" or self._allow_file) else "none")
        self._snd_id.set(str(snd["id"]))
        self._snd_file.set(snd["file"])
        self._snd_vol.set(str(snd["volume"]))
        self._refresh_preview()


def open_style_dialog(parent, title: str, style, on_save: Callable[[Optional[dict]], None], *,
                      allow_file_sound: bool = True, clear_text: str = "ล้าง (ใช้ค่าเดิม)",
                      sample_text: str = "Item", show_sound: bool = True) -> tk.Toplevel:
    """Modal-ish popup around StyleEditor. on_save gets the normalized style, or None for "clear"."""
    top = tk.Toplevel(parent)
    top.title(title)
    top.configure(bg=_BG)
    top.transient(parent)
    ed = StyleEditor(top, style, allow_file_sound=allow_file_sound, sample_text=sample_text, show_sound=show_sound)
    ed.pack(padx=10, pady=10)
    row = tk.Frame(top, bg=_BG)
    row.pack(pady=(0, 10))

    def _done(value) -> None:
        on_save(value)
        top.destroy()

    for text, cmd in (("บันทึก", lambda: _done(ed.get_style())), (clear_text, lambda: _done(None)),
                      ("ยกเลิก", top.destroy)):
        tk.Button(row, text=text, command=cmd, bg=_BUTTON_BG, fg=_FG, activebackground=_ACCENT,
                  activeforeground="#000", relief=tk.FLAT, font=_FONT, padx=8, pady=3,
                  cursor="hand2").pack(side=tk.LEFT, padx=4)
    top._style_editor = ed          # for tests
    return top
