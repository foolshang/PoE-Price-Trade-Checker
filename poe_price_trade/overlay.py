"""Transparent click-through overlay window (Mode A price display).
Uses tkinter + ctypes WS_EX_TRANSPARENT so the window passes all mouse events
through to the game beneath it."""
from __future__ import annotations
import ctypes
import ctypes.wintypes
import logging
import tkinter as tk
from tkinter import font as tkfont
from typing import Optional

from .capture import get_screen_size
from .models import ScanResult

log = logging.getLogger(__name__)

_TRANSPARENT_COLOR = "#010101"
_SHADOW_COLOR = "#000000"
_BG_COLOR = "#1A1A1A"

# สี label ตาม PoE Item Rarity (ใช้สีเดียวกับที่โชว์ใน client)
_CATEGORY_COLORS: dict[str, str] = {
    # Unique rarity — orange
    "UniqueWeapon":    "#AF6025",
    "UniqueArmour":    "#AF6025",
    "UniqueAccessory": "#AF6025",
    "UniqueFlask":     "#AF6025",
    "UniqueJewel":     "#AF6025",
    "UniqueMap":       "#AF6025",
    # Gem — teal
    "SkillGem": "#1BA29B",
    "UncutGem": "#1BA29B",
    # Divination Card — normal (white)
    "DivinationCard": "#C8C8C8",
}
_DEFAULT_COLOR = "#AA9E82"  # Currency rarity (tan) — currency/rune/essence/fragment/etc.

_GWL_EXSTYLE = -20
_WS_EX_LAYERED = 0x00080000
_WS_EX_TRANSPARENT = 0x00000020

_FONT_FAMILY = "Segoe UI"
_FONT_SIZE = 10
_FONT_WEIGHT = "bold"


def _set_click_through(hwnd: int) -> None:
    user32 = ctypes.windll.user32
    style = user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, _GWL_EXSTYLE, style | _WS_EX_LAYERED | _WS_EX_TRANSPARENT)


class PriceLabel:
    """A single price tag drawn on the overlay canvas."""
    def __init__(self, canvas: tk.Canvas, x: int, y: int, text: str, offset_px: int,
                 color: str = _DEFAULT_COLOR):
        self._canvas = canvas
        self._ids: list[int] = []
        self._draw(x, y, text, offset_px, color)

    def _draw(self, x: int, y: int, text: str, offset_px: int, color: str) -> None:
        draw_x = x + offset_px
        draw_y = y
        fnt = ((_FONT_FAMILY, _FONT_SIZE, _FONT_WEIGHT))

        # Background rectangle
        test_id = self._canvas.create_text(draw_x, draw_y, text=text, font=fnt, anchor="w")
        bbox = self._canvas.bbox(test_id)
        self._canvas.delete(test_id)
        if bbox:
            pad = 2
            self._ids.append(self._canvas.create_rectangle(
                bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad,
                fill=_BG_COLOR, outline="", stipple=""
            ))

        # Shadow
        self._ids.append(self._canvas.create_text(
            draw_x + 1, draw_y + 1, text=text, fill=_SHADOW_COLOR, font=fnt, anchor="w"
        ))
        # Main text
        self._ids.append(self._canvas.create_text(
            draw_x, draw_y, text=text, fill=color, font=fnt, anchor="w"
        ))

    def delete(self) -> None:
        for cid in self._ids:
            self._canvas.delete(cid)
        self._ids.clear()


class PriceOverlay:
    def __init__(self, root: tk.Tk, offset_px: int = 2, opacity: float = 0.9):
        self._root = root
        self._offset_px = offset_px
        self._opacity = opacity
        self._visible = False
        self._labels: list[PriceLabel] = []
        self._window: Optional[tk.Toplevel] = None
        self._canvas: Optional[tk.Canvas] = None
        self._build()

    def _build(self) -> None:
        win = tk.Toplevel(self._root)
        win.overrideredirect(True)
        win.wm_attributes("-topmost", True)
        win.wm_attributes("-transparentcolor", _TRANSPARENT_COLOR)
        win.configure(bg=_TRANSPARENT_COLOR)
        win.withdraw()

        sw, sh = get_screen_size()   # physical px (DPI-aware)
        win.geometry(f"{sw}x{sh}+0+0")

        canvas = tk.Canvas(win, bg=_TRANSPARENT_COLOR, highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True)

        self._window = win
        self._canvas = canvas

        # Apply click-through after window is mapped
        win.after(100, self._apply_click_through)

    def _apply_click_through(self) -> None:
        if self._window is None:
            return
        self._window.update_idletasks()
        try:
            hwnd = int(self._window.wm_frame(), 16)
            _set_click_through(hwnd)
        except Exception as e:
            log.warning("Click-through setup failed: %s", e)

    # ------------------------------------------------------------------
    # Public API (all called from main thread via root.after_idle)
    # ------------------------------------------------------------------

    def show_prices(self, results: list[ScanResult]) -> None:
        self._clear_labels()
        for r in results:
            if r.price_entry is None:
                continue
            price_text = r.price_entry.format_price()
            color = _CATEGORY_COLORS.get(r.price_entry.category, _DEFAULT_COLOR)
            label = PriceLabel(
                self._canvas, r.bbox_x + r.bbox_w, r.bbox_y,
                price_text, self._offset_px, color=color,
            )
            self._labels.append(label)

        if results:
            self._show()
        else:
            self.hide()

    def toggle(self, results: list[ScanResult]) -> None:
        if self._visible:
            self.hide()
        else:
            self.show_prices(results)

    def hide(self) -> None:
        self._clear_labels()
        if self._window:
            self._window.withdraw()
        self._visible = False

    def _show(self) -> None:
        if self._window:
            self._window.deiconify()
            self._window.lift()
        self._visible = True

    def _clear_labels(self) -> None:
        for lbl in self._labels:
            lbl.delete()
        self._labels.clear()

    def set_opacity(self, opacity: float) -> None:
        self._opacity = max(0.1, min(1.0, opacity))
        if self._window:
            self._window.wm_attributes("-alpha", self._opacity)

    def set_offset(self, px: int) -> None:
        self._offset_px = px

    def destroy(self) -> None:
        if self._window:
            self._window.destroy()
