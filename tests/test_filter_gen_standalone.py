"""Standalone Filter Generator + the FilterGenWindow flags it relies on (Tk is needed)."""
from __future__ import annotations
import json
import time
import tkinter as tk
import types
from unittest import mock

import pytest

from poe_price_trade import __version__
from poe_price_trade.config import AppConfig
from poe_price_trade.filter_window import FilterGenWindow


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"no display: {e}")
    r.withdraw()
    yield r
    r.destroy()


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    return AppConfig("PoeFilterGen")


def _texts(widget):
    out = []
    for c in widget.winfo_children():
        try:
            out.append(str(c.cget("text")))
        except tk.TclError:
            pass
        out += _texts(c)
    return out


def test_app_config_dir_is_separate_per_name(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert AppConfig().app_dir() == tmp_path / "PoePriceTrade"           # checker default unchanged
    assert AppConfig("PoeFilterGen").app_dir() == tmp_path / "PoeFilterGen"


def test_no_price_threshold_or_auto_regen_rows_any_more(root, cfg):
    w = FilterGenWindow(root, cfg, "poe2")
    texts = _texts(w._win)
    assert not any("threshold" in t.lower() or "Staleness" in t or "Regen" in t or "Auto-regenerate" in t
                   or "Divine" in t for t in texts)
    assert [w._nb.tab(i, "text") for i in (0, 1)] == ["NeverSink", "Whitelist"]       # the two tabs
    assert texts.count("ชื่อ filter:") == 2
    assert any("tier สูงสุด/รอง/กลาง ของ NeverSink" in t for t in texts)
    assert "Close" in texts and isinstance(w._win, tk.Toplevel)
    fg = w._save()
    assert not any(k.startswith("tier_") for k in w._vars)
    assert not any(k in w._vars for k in ("staleness_hours", "regen_cooldown_min", "auto_regen"))


def test_embedded_window_has_no_close_button(root, cfg):
    frame = tk.Frame(root)
    frame.pack()
    w = FilterGenWindow(frame, cfg, "poe2", as_toplevel=False)
    texts = _texts(frame)
    assert "Close" not in texts and "Generate Now" in texts
    w._save()                                                            # no KeyError


def test_old_threshold_and_regen_keys_in_config_are_ignored_and_kept(root, cfg):
    cfg.set("filter_gen", {"auto_regen": True, "staleness_hours": 12.0, "sound_s": ""})
    w = FilterGenWindow(root, cfg, "poe2")
    fg = w._save()
    assert fg["staleness_hours"] == 12.0 and fg["auto_regen"] is True    # not touched, just unused


def test_standalone_toggle_keeps_per_game_values_and_swaps_gem_ui(root, cfg, monkeypatch, tmp_path):
    from poe_price_trade import filter_gen_standalone as sa
    monkeypatch.setattr(sa.tk, "Tk", lambda: root)                       # reuse the test root
    app = sa.FilterGenStandaloneApp()
    assert app._game.get() == "poe2" and "Uncut Skill Gem" in app._fgw._gem_enable_vars
    app._fgw._gem_enable_vars["Uncut Skill Gem"].set(True)
    app._fgw._gem_level_vars["Uncut Skill Gem"].set("16")
    app._game.set("poe1"); app._switch_game()
    assert hasattr(app._fgw, "_gem_name_var") and not app._fgw._gem_enable_vars
    app._fgw._gem_name_var.set("Empower Support"); app._fgw._gem_add()
    app._game.set("poe2"); app._switch_game()
    assert app._fgw._gem_enable_vars["Uncut Skill Gem"].get()
    assert app._fgw._gem_level_vars["Uncut Skill Gem"].get() == "16"
    app._game.set("poe1"); app._switch_game()
    assert list(app._fgw._gem_list.get(0, tk.END)) == ["Empower Support"]
    saved = json.loads((tmp_path / "PoeFilterGen" / "config.json").read_text(encoding="utf-8"))
    assert saved["filter_gen"]["whitelist_gem_uncut_poe2"] == {"Uncut Skill Gem": 16}
    assert saved["filter_gen"]["standalone_game"] == "poe1"
    assert not (tmp_path / "PoePriceTrade").exists()                     # checker dir untouched


def test_standalone_generate_writes_filter_and_logs(root, cfg, monkeypatch, tmp_path):
    from poe_price_trade import filter_gen_standalone as sa
    monkeypatch.setattr(sa.tk, "Tk", lambda: root)
    app = sa.FilterGenStandaloneApp()
    out = tmp_path / "game"
    app._fgw._vars["game_dir"].set(str(out))
    app._fgw._vars["whitelist_gold"].set(True)
    with mock.patch.object(sa.filter_service.hub_client, "get_prices",
                           side_effect=AssertionError("whitelist must not need the hub")):
        app._fgw._on_generate_clicked(False, "whitelist")
        # worker threads reach Tk through after_idle, which needs the real mainloop (as in the app)
        deadline = time.time() + 8

        def poll():
            if "Filter updated" in app._fgw._log_text.get("1.0", tk.END) or time.time() > deadline:
                root.quit()
            else:
                root.after(50, poll)
        root.after(50, poll)
        root.mainloop()
    log_text = app._fgw._log_text.get("1.0", tk.END)
    assert '"Gold"' in (out / "poe-checker-whitelist.filter").read_text(encoding="utf-8")
    assert f"PoE Filter Generator v{__version__}" in log_text and "Filter updated" in log_text
