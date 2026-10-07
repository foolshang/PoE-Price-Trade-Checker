"""Dark ttk theme shared by every window (checker, filter generator, standalone exe, settings).

The default Windows ttk theme ignores fieldbackground / foreground for Combobox and paints readonly
Entry widgets white, so gold text (#E8D5A0) ended up on white and was unreadable. `clam` honours the
colours; everything the windows used from the default theme (Notebook) is restyled here to match.
"""
from __future__ import annotations
from tkinter import ttk

BG = "#1C1C1C"
FG = "#E8D5A0"
ACCENT = "#C8A050"
INPUT_BG = "#2A2A2A"
BUTTON_BG = "#3A3020"


def apply(widget) -> None:
    """Idempotent; safe to call from every window's constructor. Never raises."""
    try:
        style = ttk.Style(widget)
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=INPUT_BG, background=BUTTON_BG, foreground=FG,
                        arrowcolor=FG, bordercolor=BUTTON_BG, lightcolor=INPUT_BG, darkcolor=INPUT_BG,
                        selectbackground=BUTTON_BG, selectforeground=FG, insertcolor=FG)
        style.map("TCombobox",
                  fieldbackground=[("readonly", INPUT_BG), ("disabled", BG)],
                  foreground=[("readonly", FG), ("disabled", "#777")],
                  background=[("readonly", BUTTON_BG), ("active", BUTTON_BG)],
                  selectbackground=[("readonly", BUTTON_BG)], selectforeground=[("readonly", FG)])
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=BUTTON_BG, foreground=FG, padding=(14, 4), borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", ACCENT), ("active", INPUT_BG)],
                  foreground=[("selected", "#000")])
        widget.option_add("*TCombobox*Listbox.background", INPUT_BG)
        widget.option_add("*TCombobox*Listbox.foreground", FG)
        widget.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        widget.option_add("*TCombobox*Listbox.selectForeground", "#000")
    except Exception:
        pass
