"""Trade result panel (Mode B). A regular (non-transparent) tkinter window
that shows a sortable list of TradeListing, with Open-in-Browser and Copy-Whisper buttons."""
from __future__ import annotations
import logging
import tkinter as tk
from tkinter import ttk
import webbrowser
from typing import Optional

from .clipboard import write_text
from .models import TradeListing, ParsedItem
from .profiles import GameProfile

log = logging.getLogger(__name__)

_BG = "#1C1C1C"
_FG = "#E8D5A0"
_ACCENT = "#C8A050"
_ROW_BG = "#232323"
_ROW_BG_ALT = "#1A1A1A"
_SEL_BG = "#3A3020"
_BUTTON_BG = "#3A3020"
_PANEL_FONT = ("Segoe UI", 9)
_HEADER_FONT = ("Segoe UI", 9, "bold")


def _currency_symbol(currency: str) -> str:
    return {"divine": "div", "chaos": "c", "exalted": "ex"}.get(currency, currency)


class TradePanel:
    def __init__(self, parent: tk.Misc, profile: GameProfile):
        self._profile = profile
        self._listings: list[TradeListing] = []
        self._item: Optional[ParsedItem] = None
        self._query_id: str = ""
        self._league: str = ""

        self._win = tk.Toplevel(parent)
        self._win.title("PoE Trade Results")
        self._win.configure(bg=_BG)
        self._win.resizable(True, True)
        self._win.geometry("700x420")
        self._win.wm_attributes("-topmost", True)
        self._win.protocol("WM_DELETE_WINDOW", self.hide)

        self._build_ui()
        self._win.withdraw()

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        style = ttk.Style(self._win)
        style.theme_use("clam")
        style.configure("Dark.TFrame", background=_BG)
        style.configure("Dark.TLabel", background=_BG, foreground=_FG, font=_PANEL_FONT)
        style.configure("Header.TLabel", background=_BG, foreground=_ACCENT, font=_HEADER_FONT)
        style.configure("Dark.Treeview", background=_ROW_BG, foreground=_FG,
                        fieldbackground=_ROW_BG, font=_PANEL_FONT, rowheight=22)
        style.configure("Dark.Treeview.Heading", background=_BG, foreground=_ACCENT, font=_HEADER_FONT)
        style.map("Dark.Treeview", background=[("selected", _SEL_BG)])

        # Info bar
        info_frame = ttk.Frame(self._win, style="Dark.TFrame", padding=(8, 4))
        info_frame.pack(fill=tk.X)
        self._info_label = ttk.Label(info_frame, text="", style="Header.TLabel")
        self._info_label.pack(side=tk.LEFT)
        self._status_label = ttk.Label(info_frame, text="", style="Dark.TLabel")
        self._status_label.pack(side=tk.RIGHT)

        # Tree
        tree_frame = ttk.Frame(self._win, style="Dark.TFrame")
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))

        cols = ("price", "seller", "ilvl", "mods")
        self._tree = ttk.Treeview(
            tree_frame, columns=cols, show="headings",
            style="Dark.Treeview", selectmode="browse"
        )
        self._tree.heading("price",  text="Price",   command=lambda: self._sort("price"))
        self._tree.heading("seller", text="Seller",  command=lambda: self._sort("seller"))
        self._tree.heading("ilvl",   text="iLvl",    command=lambda: self._sort("ilvl"))
        self._tree.heading("mods",   text="Mods")
        self._tree.column("price",  width=100, anchor="center")
        self._tree.column("seller", width=140)
        self._tree.column("ilvl",   width=50,  anchor="center")
        self._tree.column("mods",   width=380)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.pack(fill=tk.BOTH, expand=True)

        self._tree.tag_configure("even", background=_ROW_BG)
        self._tree.tag_configure("odd", background=_ROW_BG_ALT)

        # Button bar
        btn_frame = ttk.Frame(self._win, style="Dark.TFrame", padding=(4, 4))
        btn_frame.pack(fill=tk.X)

        def btn(text, cmd):
            b = tk.Button(btn_frame, text=text, command=cmd,
                          bg=_BUTTON_BG, fg=_FG, activebackground=_SEL_BG,
                          activeforeground=_ACCENT, relief=tk.FLAT,
                          font=_PANEL_FONT, padx=8, pady=3, cursor="hand2")
            b.pack(side=tk.LEFT, padx=(0, 6))
            return b

        btn("Open in Browser", self._open_browser)
        self._whisper_btn = btn("Copy Whisper", self._copy_whisper)
        btn("Refresh", self._on_refresh)

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def show(self, listings: list[TradeListing], item: Optional[ParsedItem],
             query_id: str = "", league: str = "") -> None:
        self._listings = sorted(listings, key=lambda l: l.price_amount)
        self._item = item
        self._query_id = query_id
        self._league = league
        self._populate()
        self._win.deiconify()
        self._win.lift()

    def hide(self) -> None:
        self._win.withdraw()

    def set_refresh_callback(self, callback) -> None:
        self._on_refresh_cb = callback

    def _populate(self) -> None:
        self._tree.delete(*self._tree.get_children())
        if self._item:
            self._info_label.configure(text=f"{self._item.item_name} ({self._item.base_type})")
        self._status_label.configure(text=f"{len(self._listings)} listings")

        for i, lst in enumerate(self._listings):
            price_str = f"{lst.price_amount:.1f} {_currency_symbol(lst.price_currency)}"
            mods_str = " | ".join(lst.mods[:3])
            if len(lst.mods) > 3:
                mods_str += f" +{len(lst.mods)-3} more"
            tag = "even" if i % 2 == 0 else "odd"
            self._tree.insert("", tk.END, iid=str(i), values=(
                price_str, lst.seller, lst.item_level or "", mods_str
            ), tags=(tag,))

    def _get_selected_listing(self) -> Optional[TradeListing]:
        sel = self._tree.selection()
        if not sel:
            return None
        idx = int(sel[0])
        return self._listings[idx] if 0 <= idx < len(self._listings) else None

    def _open_browser(self) -> None:
        if not self._query_id or not self._league:
            return
        gv = self._profile.game_version
        path = "trade2" if gv == "poe2" else "trade"
        url = f"https://www.pathofexile.com/{path}/search/{self._league}/{self._query_id}"
        webbrowser.open(url)

    def _copy_whisper(self) -> None:
        listing = self._get_selected_listing()
        if listing and listing.whisper:
            write_text(listing.whisper)
            self._status_label.configure(text="Whisper copied!")
        else:
            self._status_label.configure(text="Select a listing first")

    def _on_refresh(self) -> None:
        if hasattr(self, "_on_refresh_cb") and self._on_refresh_cb:
            self._on_refresh_cb()

    def _sort(self, col: str) -> None:
        if col == "price":
            self._listings.sort(key=lambda l: l.price_amount)
        elif col == "seller":
            self._listings.sort(key=lambda l: l.seller.lower())
        elif col == "ilvl":
            self._listings.sort(key=lambda l: l.item_level, reverse=True)
        self._populate()

    def destroy(self) -> None:
        self._win.destroy()
