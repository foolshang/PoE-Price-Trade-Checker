"""Whitelist tab (phase 3): model, config round trip, UI -> config -> generated file, legacy config."""
from __future__ import annotations
import gzip
import json
import re
import tkinter as tk
from pathlib import Path
from unittest import mock

import pytest

from tests import tkutil
from poe_price_trade import filter_service, filter_whitelist as w
from poe_price_trade.config import AppConfig
from poe_price_trade.filter_window import FilterGenWindow
from poe_price_trade.wl_model import UNIQUE, WlModel

GEAR_STORY = w.gear_cat("story")
GEAR_LINKS = w.gear_cat("links")
GEAR_JEWEL = w.gear_cat("jewel")

SAMPLE = Path(__file__).parent / "sample_data"


def _snap(name):
    with gzip.open(SAMPLE / name, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def data(game):
    base = (SAMPLE / f"neversink_{game}_s2.filter").read_text(encoding="utf-8")
    hub = {"currency": [], "items": _snap(f"hub_{game}.json.gz")["items"]}
    return hub, base, set(_snap(f"trade_names_{game}.json.gz"))


def model(game, fg=None):
    m = WlModel.from_config(fg or {}, game)
    m.set_data(*data(game))
    return m


def text_of(m, **kw):
    return m.build(**kw)["text"]


def block(text, header):
    """The block that starts at the comment line `header`."""
    i = text.index(header)
    j = text.find("\n\n", i)
    return text[i:j if j > 0 else len(text)]


@pytest.fixture
def root():
    try:
        r = tkutil.new_root()
    except tk.TclError as e:
        pytest.skip(f"no display: {e}")
    r.withdraw()
    yield r
    r.destroy()


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    return AppConfig("PoeFilterGen")


# ---------------------------------------------------------------------------- model

@pytest.mark.parametrize("game", ["poe1", "poe2"])
def test_untouched_model_generates_exactly_the_wl_v2_defaults(game):
    hub, base, extra = data(game)
    default = w.build_whitelist_filter(game, {}, base, hub, "", None, extra)["text"]
    m = model(game)
    assert text_of(m) == default
    # and through the config round trip
    again = WlModel.from_config(m.to_config({}), game)
    again.set_data(hub, base, extra)
    assert text_of(again) == default


def test_item_beats_category_beats_default_in_rows_and_in_the_file():
    m = model("poe1")
    start = {r.key: r for r in m.rows("Currency")}
    assert start["Chaos Orb"].default == start["Chaos Orb"].tier and not start["Chaos Orb"].user_set
    m.set_category("Currency", "D")
    assert all(r.tier == "D" for r in m.rows("Currency")) and m.category_tier("Currency") == "D"
    m.set_row("Currency", "Chaos Orb", "S")
    rows = {r.key: r for r in m.rows("Currency")}
    assert rows["Chaos Orb"].tier == "S" and rows["Chaos Orb"].user_set and rows["Divine Orb"].tier == "D"
    text = text_of(m)
    assert '"Chaos Orb"' in block(text, "# tier S\n") and '"Divine Orb"' not in text.split("# hide everything")[0].split("# tier D")[0]
    m.reset_row("Currency", "Chaos Orb")
    assert {r.key: r for r in m.rows("Currency")}["Chaos Orb"].tier == "D"      # back to the category tier
    m.reset_category("Currency")
    assert [r.tier for r in m.rows("Currency")] == [start[r.key].tier for r in m.rows("Currency")]
    assert m.changed_count("Currency") == 0


def test_whole_category_clears_item_overrides_so_it_is_not_lost():
    m = model("poe1")
    m.set_row("Scarab", "Abyss Scarab", "S")
    m.set_category("Scarab", "A")
    assert all(r.tier == "A" and not r.user_set for r in m.rows("Scarab"))


def test_toggle_is_into_the_active_tier_or_d():
    m = model("poe1")
    m.toggle_row("Currency", "Chaos Orb", "S")          # shown -> hidden
    assert {r.key: r for r in m.rows("Currency")}["Chaos Orb"].tier == "D"
    m.toggle_row("Currency", "Chaos Orb", "S")          # hidden -> the active tier
    assert {r.key: r for r in m.rows("Currency")}["Chaos Orb"].tier == "S"


def test_search_filters_rows():
    m = model("poe1")
    assert {r.key for r in m.rows("Currency", "chaos")} <= {r.key for r in m.rows("Currency")}
    assert all("chaos" in r.label.lower() for r in m.rows("Currency", "CHAOS")) and m.rows("Currency", "chaos")


def test_tablets_are_listed_with_tablet_default_and_follow_their_tier():
    m = model("poe2")
    rows = {r.key: r for r in m.rows("Tablet")}
    assert rows and all(r.tier == w.TABLET_DEFAULT and not r.user_set for r in rows.values())
    assert "Ritual Tablet" not in {r.key for r in m.rows("Fragment")}          # listed once, under Tablet
    m.set_row("Tablet", "Ritual Tablet", "S")
    m.set_row("Tablet", "Abyss Tablet", "D")
    text = text_of(m)
    assert 'BaseType == "Ritual Tablet"' in block(text, "# tablets - tier S")
    assert "Hide" in block(text, "# tablets - tier D") and 'BaseType == "Abyss Tablet"' in block(text, "# tablets - tier D")
    assert 'Class "Tablet"' in block(text, "# tablets\n")


def test_unique_rows_show_name_and_base_and_warn_on_a_shared_base():
    m = model("poe1")
    rows = m.rows(UNIQUE)
    assert rows and all(re.match(r".+ \(.+\)$", r.label) for r in rows)
    shared = {}
    for name, base in m._entries:
        shared.setdefault(base, []).append(name)
    base, names = next((b, n) for b, n in shared.items() if len(n) > 1)
    assert not m.unique_conflicts()
    m.set_row(UNIQUE, names[0], "D")
    assert any(b == base for b, _t in m.unique_conflicts())
    warned = [r for r in m.rows(UNIQUE) if r.label.endswith(f"({base})")]
    assert warned and all(r.note.startswith("⚠") for r in warned)
    # the higher tier wins on the shared base
    assert {r.key: r for r in m.rows(UNIQUE)}[names[0]].tier == "D"
    text = text_of(m)
    assert f'"{base}"' in text


def test_style_edit_keeps_only_the_differences_and_each_style_keeps_its_own_sound():
    m = model("poe1")
    base = m.base_style("S")
    assert base["sound"]["kind"] == "game" and base["size"]                    # NeverSink's own S look
    edited = dict(base, text=[1, 2, 3, 255], sound={"kind": "file", "id": 1, "file": "x.mp3", "volume": 300})
    m.set_style_from_editor("S", edited)
    assert m.tier_style["S"]["text"] == [1, 2, 3, 255] and m.tier_style["S"]["sound"]["file"] == "x.mp3"   # the tier's own sound
    assert m.tier_style["S"]["size"] is None                                    # untouched part follows NeverSink
    lines = block(text_of(m), "# tier S\n")
    assert "SetTextColor 1 2 3 255" in lines and "PlayAlertSound 6" in lines and "SetFontSize 45" in lines
    assert 'CustomAlertSoundOptional "x.mp3"' in block(text_of(m, sound_names={"S": "x.mp3"}), "# tier S\n")
    m.set_style_from_editor("G", dict(m.base_style("G"), sound={"kind": "file", "id": 1, "file": "g.mp3", "volume": 200}))
    assert m.tier_style["G"]["sound"]["file"] == "g.mp3"                       # G / Tablet / Map keep theirs
    m.set_style("S", None)
    assert "S" not in m.tier_style


# ---------------------------------------------------------------------------- legacy config

def test_legacy_config_is_converted_once_and_nothing_is_deleted():
    old = {"whitelist_cats_poe1": ["Currency", "Scarab"], "whitelist_cat_exclude_poe1": {"Currency": ["Chaos Orb"]},
           "whitelist_unique_all": False, "whitelist_gold": True}
    updates, notes = WlModel.convert_legacy(old, "poe1")
    assert notes and updates["wl_converted_poe1"] is True
    ct = updates["wl_cat_tier_poe1"]
    assert ct["Fragment"] == "D" and "Currency" not in ct and "Scarab" not in ct       # unticked categories hidden
    assert ct[UNIQUE] == "D" and ct[w.OTHER_CATEGORY] == "D" and not any(k.startswith("gear:") for k in ct)
    assert updates["wl_item_tier_poe1"] == {"Chaos Orb": "D"}
    merged = {**old, **updates}
    assert merged["whitelist_cats_poe1"] == old["whitelist_cats_poe1"]                 # old keys untouched
    assert WlModel.convert_legacy(merged, "poe1") == ({}, [])                          # only once
    m = WlModel.from_config(merged, "poe1")
    m.set_data(*data("poe1"))
    tiers = {r.key: r.tier for r in m.rows("Currency")}
    assert tiers["Chaos Orb"] == "D" and tiers["Divine Orb"] != "D"
    assert all(r.tier == "D" for r in m.rows("Fragment"))


def test_legacy_unique_all_and_fragment_keep_tablets_and_uniques():
    old = {"whitelist_cats_poe2": ["Fragment"], "whitelist_unique_all": True}
    updates, _n = WlModel.convert_legacy(old, "poe2")
    assert UNIQUE not in updates["wl_cat_tier_poe2"] and "Tablet" not in updates["wl_cat_tier_poe2"]
    old = {"whitelist_cats_poe2": ["Currency"]}
    assert WlModel.convert_legacy(old, "poe2")[0]["wl_cat_tier_poe2"]["Tablet"] == "D"
    assert WlModel.convert_legacy({}, "poe1") == ({}, [])                                # a fresh config: nothing
    assert WlModel.convert_legacy({"wl_cat_tier_poe1": {}, "whitelist_cats_poe1": []}, "poe1")[1] == []


# ---------------------------------------------------------------------------- the window

def make_window(root, cfg, game="poe2"):
    win = FilterGenWindow(root, cfg, game, on_generate=lambda *_a: None)
    win.set_wl_data(*data(game))
    return win


def test_nothing_is_clickable_until_a_tier_is_chosen(root, cfg):
    win = make_window(root, cfg)
    p = win._panel
    assert p.active.get() == ""
    for widget in (p._tier_reset, *p._act_btns):
        assert str(widget.cget("state")) == "disabled"
    assert str(p._search.cget("state")) == "disabled"
    p.active.set("S"); p._on_tier_picked()
    for widget in (p._tier_reset, *p._act_btns):
        assert str(widget.cget("state")) == "normal"


def test_clicking_a_row_toggles_and_the_list_shows_the_tier_suffix(root, cfg):
    win = make_window(root, cfg)
    p = win._panel
    p.active.set("S"); p._on_tier_picked()
    p.cat_var.set("Currency"); p.refresh_list()
    iid = next(i for i, k in p._row_keys.items() if k == "Chaos Orb")
    before = p.tree.item(iid, "values")
    assert before[0].startswith("☑") and before[1] in ("S", "A", "B")
    p.model.toggle_row("Currency", "Chaos Orb", "S"); p.refresh_list()
    iid = next(i for i, k in p._row_keys.items() if k == "Chaos Orb")
    after = p.tree.item(iid, "values")
    assert after[0].startswith("☐") and after[1] == "D" and "ตั้งเอง" in after[2]
    p.cat_var.set("Tablet"); p.refresh_list()
    vals = [p.tree.item(i, "values") for i in p.tree.get_children()]
    assert vals and all(v[1] == "Tablet" for v in vals)


def test_buttons_move_reset_and_whole_category(root, cfg):
    win = make_window(root, cfg, "poe1")
    p = win._panel
    p.active.set("A"); p._on_tier_picked()
    p.cat_var.set("Scarab"); p.refresh_list()
    first, second = list(p._row_keys)[:2]
    k1, k2 = p._row_keys[first], p._row_keys[second]
    p.tree.selection_set(first, second)
    p._move_selected()
    assert {p.model.item_tier[k] for k in (k1, k2)} == {"A"}
    p.tree.selection_set(next(i for i, k in p._row_keys.items() if k == k1)); p._reset_selected()
    assert k1 not in p.model.item_tier and k2 in p.model.item_tier
    p._set_cat("D")
    assert p.model.category_tier("Scarab") == "D" and not p.model.item_tier
    p._reset_cat()
    assert p.model.category_tier("Scarab") is None


def test_window_save_writes_wl_v2_and_generate_gives_the_chosen_file(root, cfg, tmp_path):
    win = make_window(root, cfg)
    p = win._panel
    p.model.set_row("Currency", "Chaos Orb", "S")
    p.model.set_category("Rune", "D")
    p.model.set_row("Tablet", "Ritual Tablet", "A")
    p.v_gold.set(True); p.v_gold_min.set("77")
    p.v_map.set(True); p.v_map_tier.set("11"); p.v_map_rar.set("Rare")
    p.v_gem_on["Uncut Skill Gem"].set(True); p.v_gem_lv["Uncut Skill Gem"].set("13")
    win._vars["game_dir"].set(str(tmp_path / "game"))
    fg = win._save("whitelist")
    assert fg["wl_v2"] is True and fg["whitelist_enabled"] is True
    assert fg["wl_item_tier_poe2"]["Chaos Orb"] == "S" and fg["wl_cat_tier_poe2"]["Rune"] == "D"
    assert fg["whitelist_gold_min"] == 77 and fg["wl_map_tier_min"] == 11 and fg["whitelist_gem_uncut_poe2"] == {"Uncut Skill Gem": 13}
    hub, base, extra = data("poe2")
    cfg_obj = type("D", (), {"get": lambda self, k, d=None: dict(fg) if k == "filter_gen" else d,
                             "app_dir": lambda self: tmp_path / "app"})()
    with mock.patch.object(filter_service.neversink_source, "fetch_base_filter", return_value=(base, "t")), \
         mock.patch.object(filter_service.hub_client, "get_prices", return_value=hub), \
         mock.patch.object(filter_service.trade_names, "get_names", return_value=extra):
        res = filter_service.generate_filter(cfg_obj, "poe2", "p", mode="whitelist")
    out = res["path"].read_text(encoding="utf-8")
    assert 'BaseType == "Chaos Orb"' in block(out, "# tier S\n") or '"Chaos Orb"' in block(out, "# tier S\n")
    assert "StackSize >= 77" in block(out, "# gold") and "WaystoneTier >= 11" in block(out, "# waystones")
    assert "GemLevel >= 13" in block(out, "# uncut gem")
    assert 'BaseType == "Ritual Tablet"' in block(out, "# tablets - tier A")
    assert all("Hide" == s.splitlines()[1] for s in out.split("\n\n") if s.startswith("# gear: เนื้อเรื่อง"))
    assert not res["path"].name.startswith("poe-checker.")


def test_window_with_a_legacy_config_converts_once_and_logs_it(root, cfg):
    cfg.set("filter_gen", {"whitelist_cats_poe2": ["Currency"], "whitelist_unique_all": True})
    win = FilterGenWindow(root, cfg, "poe2", on_generate=lambda *_a: None)
    log = win._log_text.get("1.0", tk.END)
    assert "แปลง whitelist เดิม" in log
    saved = cfg.get("filter_gen")
    assert saved["wl_converted_poe2"] is True and saved["whitelist_cats_poe2"] == ["Currency"]   # old key kept
    assert saved["wl_cat_tier_poe2"]["Fragment"] == "D"
    win2 = FilterGenWindow(root, cfg, "poe2", on_generate=lambda *_a: None)
    assert "แปลง whitelist เดิม" not in win2._log_text.get("1.0", tk.END)


def test_the_tabs_do_not_share_sounds_each_tier_has_its_own_in_its_style_editor(root, cfg):
    win = make_window(root, cfg)
    win._vars["sound_1"].set("D:/snd/ragnarok.mp3")                 # the NeverSink tab's sound 1
    p = win._panel
    p.active.set("S"); p._on_tier_picked()
    assert p._tier_editor.get_style()["sound"]["kind"] != "file"     # the Whitelist tab does not see it
    p._tier_editor._snd_file.set("D:/snd/mine.mp3"); p._tier_editor._snd_kind.set("file"); p._tier_editor._changed()
    assert win._model.tier_style["S"]["sound"]["file"] == "D:/snd/mine.mp3"
    saved = win._save("whitelist")
    assert saved["sound_1"] == "D:/snd/ragnarok.mp3" and saved["wl_tier_style"]["S"]["sound"]["file"] == "D:/snd/mine.mp3"
    assert "sound_s" not in saved and saved["sound_format"] == 2


def test_gold_map_gem_and_typed_names_reach_the_file():
    m = model("poe2")
    m.gold, m.gold_min = True, 250
    m.map_on, m.map_tier, m.map_rarity = True, 9, "Rare"
    m.gem_uncut = {"Uncut Skill Gem": 14}
    m.gem_tier = "A"
    m.custom = [{"name": "Heavy Belt", "rarities": ["Magic", "Rare"], "tier": "S"}]
    t = text_of(m)
    assert "StackSize >= 250" in block(t, "# gold")
    seg = block(t, "# waystones")
    assert "WaystoneTier >= 9" in seg and "Rarity >= Rare" in seg
    assert "GemLevel >= 14" in block(t, "# uncut gem")
    seg = block(t, "# typed names")
    assert 'BaseType "Heavy Belt"' in seg and "Rarity Magic Rare" in seg


def test_config_round_trip_keeps_every_setting():
    m = model("poe2")
    m.set_row("Currency", "Chaos Orb", "S"); m.set_category("Rune", "D")
    m.set_flask_custom("Flask", True); m.set_flask_rarity("Flask", "Magic", "D"); m.set_flask_rarity("Charm", "Normal", "B")
    m.set_tier_stack("B", 3); m.set_stack(["Chaos Orb"], 5)
    m.set_row(UNIQUE, "Ab Aeterno", "S")
    m.gold, m.gold_min, m.map_on, m.map_tier, m.map_rarity = True, 5, True, 12, "Magic"
    m.gem_uncut, m.gem_tier = {"Uncut Spirit Gem": 3}, "S"
    m.custom = [{"name": "belt", "rarities": ["Rare"], "tier": "A"}]
    m.set_style("Tablet", {"text": [9, 9, 9, 255]})
    fg = m.to_config({"keep": 1})
    back = WlModel.from_config(json.loads(json.dumps(fg)), "poe2")
    assert back.to_config({}) == m.to_config({}) and fg["keep"] == 1 and fg["wl_v2"] is True
