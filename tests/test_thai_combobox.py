"""A picked readonly Combobox keeps its text selected and the focus; Tk draws a selected text cluster by cluster, so a Thai
prompt put in it by the program ("ตั้งทั้งกลุ่ม…") fell apart on screen (v0.13.0, group header of the equipment
category). ui_theme.calm clears the selection after a pick and whenever the box gets the focus."""
from __future__ import annotations
import time
import tkinter as tk
from tkinter import ttk

from poe_price_trade import ui_theme
from poe_price_trade.wl_model import EQUIP_CATEGORY
from tests.test_wl_phase3b import cfg, make_window, root       # noqa: F401  (fixtures)


def _settle(root):
    root.update()
    time.sleep(0.05)
    root.update()


def test_a_picked_group_header_box_shows_no_selection_whatever_the_handler_does(root, cfg):
    win = make_window(root, cfg, "poe2")
    p = win._panel
    p.active.set("B"); p._on_tier_picked()
    p.cat_var.set(dict(win._model.categories())[EQUIP_CATEGORY]); p.refresh_list(); root.update()
    for rar in ("Normal", "Magic", "Rare"):                      # what ttk does on a pick: text selected, box focused
        c = p._eq_grp_combos["weapon"][rar]
        c.focus_force()
        p.v_eq_grp["weapon"][rar].set("A")
        c.selection_range(0, "end")
        assert c.selection_present()
        c.event_generate("<<ComboboxSelected>>")
        _settle(root)
        assert not c.selection_present(), rar
        assert p.v_eq_grp["weapon"][rar].get() == "ตั้งทั้งกลุ่ม…"      # the prompt is back
    assert all(not c.selection_present() for g in p._eq_grp_combos.values() for c in g.values())


def test_every_combobox_and_readonly_entry_of_the_windows_is_calm(root, cfg):
    win = make_window(root, cfg, "poe2")
    win._panel.active.set("B"); win._panel._on_tier_picked()
    root.update()
    seen = []

    def walk(w):
        for c in w.winfo_children():
            if isinstance(c, ttk.Combobox) or (isinstance(c, tk.Entry) and str(c.cget("state")) == "readonly"):
                seen.append(c)
            walk(c)
    walk(win._win)
    assert len(seen) > 20                                        # the NeverSink tab, the panel, the style editors
    for c in seen:
        c.focus_force()
        c.selection_range(0, "end")
        c.event_generate("<FocusIn>")
        _settle(root)
        assert not c.selection_present(), str(c)


def test_calm_works_on_a_plain_box_and_does_not_break_the_pick_handlers(root):
    top = tk.Toplevel(root)
    var = tk.StringVar(value="x")
    picked = []
    cb = ui_theme.calm(ttk.Combobox(top, textvariable=var, values=["x", "y"], state="readonly"))
    cb.pack()
    cb.bind("<<ComboboxSelected>>", lambda _e: picked.append(var.get()))
    cb.focus_force()
    var.set("y")
    cb.selection_range(0, "end")
    cb.event_generate("<<ComboboxSelected>>")
    _settle(root)
    assert picked == ["y"] and not cb.selection_present()
    top.destroy()
