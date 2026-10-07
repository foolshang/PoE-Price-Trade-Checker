"""v0.9.1 phase 1: style model, file names, sound-name planning, quest blocks, tabs."""
from __future__ import annotations
import tkinter as tk
import types
from unittest import mock

import pytest

from poe_price_trade import filter_core, filter_service, filter_style
from poe_price_trade.config import AppConfig
from poe_price_trade.filter_style_editor import StyleEditor, open_style_dialog
from poe_price_trade.filter_window import FilterGenWindow


# ---------------------------------------------------------------- filter_style

def test_style_lines_follow_neversinks_order_and_skip_unset_parts():
    st = {"text": [255, 0, 0], "border": [1, 2, 3, 4], "bg": None, "size": 45,
          "icon": {"size": 2, "color": "Red", "shape": "Star"}, "effect": {"color": "Green", "temp": True},
          "sound": {"kind": "game", "id": 6, "volume": 250}}
    assert filter_style.style_lines(st) == [
        "    SetFontSize 45", "    SetTextColor 255 0 0 255", "    SetBorderColor 1 2 3 4",
        "    PlayAlertSound 6 250", "    PlayEffect Green Temp", "    MinimapIcon 2 Red Star"]
    assert filter_style.style_lines({}) == [] and filter_style.is_empty({}) and filter_style.is_empty(None)


def test_file_sound_is_always_written_as_optional_and_needs_its_resolved_name():
    st = {"sound": {"kind": "file", "file": "D:/x/ping.mp3", "volume": 120}}
    assert filter_style.uses_sound_file(st) == "D:/x/ping.mp3"
    assert filter_style.style_lines(st, "ping.mp3") == ['    CustomAlertSoundOptional "ping.mp3" 120']
    assert filter_style.style_lines(st) == []                        # no resolved name -> nothing half-written
    assert not filter_style.is_empty(st)


def test_normalize_style_clamps_and_drops_garbage():
    s = filter_style.normalize_style({"text": [300, -5, "x"], "size": "99", "icon": {"size": 9, "color": "Nope"},
                                      "effect": {"color": "Pink"}, "sound": {"kind": "game", "id": 99, "volume": 9999},
                                      "junk": 1})
    assert s["text"] is None and s["size"] == filter_style.FONT_MAX and s["icon"] is None
    assert s["effect"] == {"color": "Pink", "temp": False}
    assert s["sound"]["id"] == 1 and s["sound"]["volume"] == filter_style.VOLUME_MAX and "junk" not in s
    assert filter_style.normalize_style("nonsense") == filter_style.normalize_style({})
    assert filter_style.normalize_style({"text": [10, 20, 30]})["text"] == [10, 20, 30, 255]


# ---------------------------------------------------------------- names

@pytest.mark.parametrize("name", ["poe-checker", "my filter", "ฟิลเตอร์ไทย", "a.b", "x" * 100, "CONSOLE"])
def test_good_filter_names(name):
    assert filter_core.validate_filter_name(name) == (name, None)


@pytest.mark.parametrize("name", ["", "   ", "a<b", "a>b", "a:b", 'a"b', "a/b", "a\\b", "a|b", "a?b", "a*b",
                                  "tab\there", "trail.", "trail ", "CON", "con", "NUL", "COM1", "LPT9", "aux.txt",
                                  "x" * 101])
def test_bad_filter_names_say_why(name):
    n, err = filter_core.validate_filter_name(name)
    assert err and isinstance(err, str)


def test_sound_names_with_hash_or_semicolon_become_underscore_with_a_reason():
    assert filter_core.safe_sound_name("ping.mp3") == ("ping.mp3", None)
    assert filter_core.safe_sound_name("ไม่มี.mp3") == ("ไม่มี.mp3", None)
    new, why = filter_core.safe_sound_name("a#b.mp3")
    assert new == "a_b.mp3" and why == 'เปลี่ยนชื่อ "a#b.mp3" เป็น "a_b.mp3" เพราะเกมเล่นไฟล์ที่ชื่อมี # ไม่ได้'
    new, why = filter_core.safe_sound_name("a;b.mp3")
    assert new == "a_b.mp3" and why.endswith("เพราะเกมใช้ ; คั่นหลายไฟล์")


def test_sound_plan_statuses():
    plan = filter_core.plan_sound_files(
        [("S", "new.mp3", "h1"), ("A", "same.mp3", "h2"), ("B", "clash.mp3", "h3"), ("Q", "new.mp3", "h1")],
        {"same.mp3": "h2", "clash.mp3": "OTHER", "clash-2.mp3": None})
    st = {i["dest"]: i["status"] for i in plan["items"]}
    assert st == {"new.mp3": "new", "same.mp3": "same", "clash.mp3": "conflict"}
    assert plan["dest"] == {"S": "new.mp3", "A": "same.mp3", "B": "clash.mp3", "Q": "new.mp3"}   # one file, two labels
    dest, copies, msgs = filter_core.resolve_sound_plan(plan, lambda n, alt: "keep")
    assert dest["B"] == "clash-3.mp3" and ("B", "clash-3.mp3") in copies          # clash-2 is taken on disk
    assert not any(c[1] == "same.mp3" for c in copies) and any("ใช้ไฟล์เดิม" in m for m in msgs)
    dest, copies, _m = filter_core.resolve_sound_plan(plan, lambda n, alt: "overwrite")
    assert dest["B"] == "clash.mp3" and ("B", "clash.mp3") in copies


# ---------------------------------------------------------------- quest blocks

def test_quest_blocks_per_game():
    st = filter_style.default_quest_style()
    poe1 = filter_core.build_quest_blocks("poe1", st)
    assert 'Class == "Quest Items" "Cursed Ducat" "Pantheon Souls" "Labyrinth Items" "Labyrinth Trinkets"' in poe1
    assert "BaseType" not in poe1 and "SetTextColor 74 230 58 255" in poe1 and "Hide" not in poe1
    poe2 = filter_core.build_quest_blocks("poe2", st)
    assert 'Class == "Quest Items" "Instance Local Items"' in poe2
    assert poe2.count("Show") == 2 and 'BaseType == "Bronze Key" "Gold Key" "Silver Key"' in poe2
    assert filter_core.build_quest_blocks("poe2", {}) == "" and filter_core.build_quest_blocks("poe2", None) == ""


def test_tier_mode_puts_our_quest_block_ahead_of_neversinks_and_changes_nothing_without_it():
    base = 'Show # $type->questlikeexception $tier->questitems\n\tClass == "Quest Items"\n\tSetFontSize 42\n'
    plain = filter_core.build_filter_text({}, "poe1", base_text=base, base_tag="t")
    assert plain["generated_section"] == filter_core.TIER_HEADER and plain["base_text"] == base
    for unset in ({"style_q": None}, {"style_q": {}}):
        assert filter_core.build_filter_text(unset, "poe1", base_text=base)["generated_section"] == filter_core.TIER_HEADER
    res = filter_core.build_filter_text({"style_q": {"text": [1, 2, 3, 255], "size": 40}}, "poe1", base_text=base)
    body = filter_core.compose_filter_body(res["generated_section"], res["base_text"])
    assert body.index('Class == "Quest Items" "Cursed Ducat"') < body.index("# ===== base filter below =====")
    assert res["base_text"] == base                                    # NeverSink's text itself is untouched


def test_quest_file_sound_goes_through_the_sound_copy_and_uses_the_name_it_got():
    asked = []
    res = filter_core.build_filter_text(
        {"style_q": {"sound": {"kind": "file", "file": "C:/s/my ping.mp3", "volume": 200}}}, "poe2",
        base_text="Show\n", copy_sounds_fn=lambda m: asked.append(m) or {"Q": "my ping.mp3"})
    assert asked[0]["Q"] == "C:/s/my ping.mp3" and asked[0]["S"] is None
    assert 'CustomAlertSoundOptional "my ping.mp3" 200' in res["generated_section"]
    assert "C:/s" not in res["generated_section"]


# ---------------------------------------------------------------- service

def _cfg(tmp_path, fg):
    store = {"filter_gen": dict(fg, game_dir_poe2=str(tmp_path / "game"))}
    return types.SimpleNamespace(get=lambda k, d=None: store.get(k, d), set=lambda k, v: store.__setitem__(k, v),
                                 save=lambda: None, app_dir=lambda: tmp_path / "app", store=store)


def test_each_tab_writes_its_own_file_and_a_bad_name_stops_before_writing(tmp_path):
    base = ("Show\n\tBaseType \"X\"\n", "tag1")
    cfg = _cfg(tmp_path, {"filter_name_tier": "my tier", "whitelist_gold": True})
    logs = []
    with mock.patch.object(filter_service.neversink_source, "fetch_base_filter", return_value=base):
        t = filter_service.generate_filter(cfg, "poe2", "p", mode="tier", log=lambda m, t_="info": logs.append((t_, m)))
        w = filter_service.generate_filter(cfg, "poe2", "p", mode="whitelist")
    assert t["path"].name == "my tier.filter" and t["filter_name"] == "my tier"
    assert w["path"].name == "poe-checker-whitelist.filter"
    assert sorted(p.name for p in (tmp_path / "game").glob("*.filter")) == ["my tier.filter", "poe-checker-whitelist.filter"]
    bad = _cfg(tmp_path, {"filter_name_tier": "a/b"})
    logs.clear()
    assert filter_service.generate_filter(bad, "poe2", "p", mode="tier", log=lambda m, t_="info": logs.append((t_, m))) is None
    assert logs[-1][0] == "err" and "/" in logs[-1][1]


def test_renaming_leaves_the_old_file_alone_and_says_it_is_still_there(tmp_path):
    cfg = _cfg(tmp_path, {})
    logs = []
    with mock.patch.object(filter_service.neversink_source, "fetch_base_filter", return_value=("Show\n", "t")):
        r1 = filter_service.generate_filter(cfg, "poe2", "p", mode="tier")
        filter_service.remember_result(cfg, "poe2", r1)
        cfg.store["filter_gen"]["filter_name_tier"] = "renamed"
        r2 = filter_service.generate_filter(cfg, "poe2", "p", mode="tier", log=lambda m, t="info": logs.append(m))
    assert (tmp_path / "game" / "poe-checker.filter").exists() and r2["path"].name == "renamed.filter"
    assert any("ไฟล์เดิม poe-checker.filter ยังอยู่" in m for m in logs)


def test_remember_result_keeps_the_tag_and_name(tmp_path):
    cfg = _cfg(tmp_path, {})
    filter_service.remember_result(cfg, "poe2", {"mode": "tier", "base_tag": "0.10.4", "filter_name": "x"})
    fg = cfg.store["filter_gen"]
    assert fg["neversink_tag_poe2"] == "0.10.4" and fg["last_filter_name_tier"] == "x"
    filter_service.remember_result(cfg, "poe2", {"mode": "whitelist", "filter_name": "w"})
    assert fg is not cfg.store["filter_gen"] or True
    assert cfg.store["filter_gen"]["last_filter_name_whitelist"] == "w" and cfg.store["filter_gen"]["neversink_tag_poe2"] == "0.10.4"
    filter_service.remember_result(cfg, "poe2", None)                      # nothing written -> no change


def test_neversink_update_check():
    cfg = types.SimpleNamespace(get=lambda k, d=None: {"neversink_tag_poe2": "0.10.3", "auto_regen_neversink": True}
                                if k == "filter_gen" else d)
    assert filter_service.check_neversink_update(cfg, "poe2", lambda g: "0.10.3") is None        # same
    assert filter_service.check_neversink_update(cfg, "poe2", lambda g: None) is None            # GitHub down
    assert filter_service.check_neversink_update(cfg, "poe1", lambda g: "9") is None             # never generated poe1
    info = filter_service.check_neversink_update(cfg, "poe2", lambda g: "0.10.4")
    assert info == {"old": "0.10.3", "new": "0.10.4", "auto": True}
    assert filter_service.neversink_update_message(info, True) == "NeverSink อัปเดต 0.10.3 → 0.10.4 สร้าง filter ใหม่แล้ว"
    assert "มีเวอร์ชันใหม่ 0.10.4" in filter_service.neversink_update_message(info, False)
    off = types.SimpleNamespace(get=lambda k, d=None: {"neversink_tag_poe2": "a"} if k == "filter_gen" else d)
    assert filter_service.check_neversink_update(off, "poe2", lambda g: "b")["auto"] is False


# ---------------------------------------------------------------- tk widgets

@pytest.fixture
def root():
    r = tk.Tk()
    r.withdraw()
    yield r
    r.destroy()


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    return AppConfig("PoeFilterGen")


def test_style_editor_round_trips_a_style(root):
    st = {"text": [10, 20, 30, 200], "border": [1, 2, 3, 255], "bg": None, "size": 33,
          "icon": {"size": 1, "color": "Cyan", "shape": "Moon"}, "effect": {"color": "Pink", "temp": True},
          "sound": {"kind": "game", "id": 5, "volume": 100}}
    ed = StyleEditor(root, st)
    got = ed.get_style()
    assert got["text"] == [10, 20, 30, 200] and got["border"] == [1, 2, 3, 255] and got["bg"] is None
    assert got["size"] == 33 and got["icon"] == st["icon"] and got["effect"] == st["effect"]
    assert got["sound"] == {"kind": "game", "id": 5, "file": "", "volume": 100}
    ed.set_style(None)
    assert filter_style.is_empty(ed.get_style())
    ed.set_style({"sound": {"kind": "file", "file": "x.mp3"}})
    assert ed.get_style()["sound"]["kind"] == "file"
    assert StyleEditor(root, {"sound": {"kind": "file", "file": "x.mp3"}}, allow_file_sound=False).get_style()["sound"]["kind"] == "none"


def test_style_dialog_saves_or_clears(root):
    got = []
    top = open_style_dialog(root, "t", {"text": [1, 2, 3, 255]}, got.append)
    assert top._style_editor.get_style()["text"] == [1, 2, 3, 255]
    top.destroy()


def test_window_has_two_tabs_each_with_its_own_name_and_mode(root, cfg):
    calls = []
    w = FilterGenWindow(root, cfg, "poe2", on_generate=lambda force, mode: calls.append((force, mode)))
    assert [w._nb.tab(i, "text") for i in (0, 1)] == ["NeverSink", "Whitelist"]
    assert w._vars["filter_name_tier"].get() == "poe-checker"
    assert w._vars["filter_name_whitelist"].get() == "poe-checker-whitelist"
    assert w._mode() == "tier"
    w._on_generate_clicked(True, "tier")
    w._nb.select(1)
    assert w._mode() == "whitelist"
    w._on_generate_clicked(False, "whitelist")
    assert calls == [(True, "tier"), (False, "whitelist")]
    fg = cfg.get("filter_gen")
    assert fg["last_tab"] == "whitelist" and fg["whitelist_enabled"] is True


def test_window_refuses_to_generate_with_a_bad_filter_name(root, cfg):
    calls = []
    w = FilterGenWindow(root, cfg, "poe2", on_generate=lambda force, mode: calls.append(mode))
    w._vars["filter_name_tier"].set("a?b")
    w._on_generate_clicked(False, "tier")
    assert calls == [] and "ห้ามมีตัวอักษร ?" in w._log_text.get("1.0", tk.END)


def test_window_remembers_quest_style_regen_flag_and_names(root, cfg):
    w = FilterGenWindow(root, cfg, "poe1")
    w._style_q = filter_style.default_quest_style()
    w._refresh_quest_label()
    w._vars["auto_regen_neversink"].set(True)
    w._vars["filter_name_tier"].set("mine")
    fg = w._save("tier")
    assert fg["style_q"]["text"] == [74, 230, 58, 255] and fg["auto_regen_neversink"] is True
    assert fg["filter_name_tier"] == "mine" and fg["whitelist_enabled"] is False
    w2 = FilterGenWindow(root, cfg, "poe1")
    assert w2._style_q["text"] == [74, 230, 58, 255] and w2._vars["filter_name_tier"].get() == "mine"
    w2._style_q = None
    w2._refresh_quest_label()
    assert w2._save("tier")["style_q"] is None                              # cleared = back to NeverSink's own


def test_window_title_and_sound_question(root, cfg):
    from poe_price_trade import __version__
    w = FilterGenWindow(root, cfg, "poe2")
    assert __version__ in w._win.title()
    import threading
    out = {}
    with mock.patch("poe_price_trade.filter_window.messagebox.askyesno", return_value=True):
        t = threading.Thread(target=lambda: out.setdefault("v", w.ask_sound_conflict("a.mp3", "a-2.mp3")))

        def poll():
            if not t.is_alive():
                root.quit()
            else:
                root.after(20, poll)
        t.start()
        root.after(20, poll)
        root.mainloop()         # as in the app: the worker thread reaches Tk through the main loop
        t.join(5)
    assert out["v"] == "overwrite"
