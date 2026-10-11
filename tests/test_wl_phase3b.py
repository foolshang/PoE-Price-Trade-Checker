"""Phase 3b: categories filed by NeverSink's type, stack-size minimums, opacity controls, style round trips
(every field, every place it is used), the settings embedded in the file and opening an old filter."""
from __future__ import annotations
import gzip
import json
import re
import tkinter as tk
from pathlib import Path
from unittest import mock

import pytest

from tests import tkutil
from poe_price_trade import filter_core, filter_service, filter_style, filter_whitelist as w, wl_embed
from poe_price_trade.config import AppConfig
from poe_price_trade.filter_style_editor import StyleEditor
from poe_price_trade.filter_window import FilterGenWindow
from poe_price_trade.wl_model import WlModel
from tests.test_filter_vocabulary import lint

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


def block(text, header):
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


def make_window(root, cfg, game="poe2"):
    win = FilterGenWindow(root, cfg, game, on_generate=lambda *_a: None)
    win.set_wl_data(*data(game))
    return win


def click(top, text):
    """Press the button with this text in a dialog."""
    def walk(wd):
        for c in wd.winfo_children():
            yield c
            yield from walk(c)
    btn = next(b for b in walk(top) if isinstance(b, tk.Button) and b.cget("text") == text)
    btn.invoke()


# ---------------------------------------------------------------------------- A1: categories by NeverSink type

def test_names_only_neversink_tiers_join_the_category_of_their_type():
    m2 = model("poe2")
    cat = {n: c for c in dict(m2.categories()) for n in [r.key for r in m2.rows(c)]
           if not c.startswith("gear:")}
    assert cat["Lesser Charging Rune"] == "Rune" and cat["Alchemy Shard"] == "Currency"
    assert {r.key: r for r in m2.rows("Rune")}["Lesser Charging Rune"].tier == "B"     # no tier of NeverSink's: B
    assert {r.key: r for r in m2.rows("Currency")}["Alchemy Shard"].default == "B"     # shown as "supply", not a ladder step
    m1 = model("poe1")
    cat1 = {r.key: c for c in dict(m1.categories()) for r in m1.rows(c) if not c.startswith("gear:")}
    assert cat1["Alteration Shard"] == "Currency"
    assert cat1["Essence of Desolation"] == "Essence"
    names_in_other = {r.key for r in m1.rows(w.OTHER_CATEGORY)}
    assert "Alteration Shard" not in names_in_other
    assert any("Tattoo" in n for n in names_in_other)       # types no category matches stay in "อื่นๆ"


def test_a_category_tier_reaches_the_names_filed_into_it():
    m = model("poe2")
    m.set_category("Currency", "S")
    rows = {r.key: r for r in m.rows("Currency")}
    assert rows["Alchemy Shard"].tier == "S"
    assert '"Alchemy Shard"' in block(m.build()["text"], "# tier S\n")


# ---------------------------------------------------------------------------- A2: stack-size minimums

def _stack_eval(text, base, stack):
    """first Show/Hide block of `text` an item `base` with `stack` would match (BaseType == and StackSize >=)."""
    cur, chunks = None, []
    for line in text.splitlines():
        if line in ("Show", "Hide"):
            cur = [line]
            chunks.append(cur)
        elif cur is not None and line.strip() and not line.startswith("#"):
            cur.append(line.strip())
    for chunk in chunks:
        ok = True
        for cond in chunk[1:]:
            if cond.startswith("BaseType =="):
                ok = ok and base in re.findall(r'"([^"]*)"', cond)
            elif cond.startswith("StackSize >="):
                ok = ok and stack >= int(cond.split()[-1])
            elif cond.split()[0] in ("Class", "Rarity", "AreaLevel", "ItemLevel", "LinkedSockets"):
                ok = False if cond.split()[0] in ("Class", "AreaLevel") else ok
            elif cond.split()[0] in ("BaseType", "Quality", "GemLevel", "WaystoneTier", "MapTier"):
                ok = False
        if ok:
            return chunk
    return None


def test_neversink_stack_rules_are_the_starting_minimum_and_tier():
    hub, base, extra = data("poe1")
    defaults, stackable = w.stack_info(base)
    assert {n: defaults[n] for n in ("Orb of Augmentation", "Portal Scroll", "Scroll of Wisdom")} == {
        "Orb of Augmentation": (3, "A"), "Portal Scroll": (3, "A"), "Scroll of Wisdom": (3, "A")}
    # a whole-class rule ("Divination Cards" with StackSize >= 3) gates every card NeverSink hides alone
    assert defaults["Audacity"] == (3, "B") and sum(1 for v in defaults.values() if v == (3, "B")) == 93
    assert len(defaults) == 96 and w.stack_info(data("poe2")[1])[0] == {}
    assert "Chaos Orb" in stackable and "Chaos Orb" not in defaults and "Vaal Regalia" not in stackable
    m = model("poe1")
    row = {r.key: r for r in m.rows("Currency")}["Scroll of Wisdom"]
    assert (row.tier, row.stack, row.stackable, row.stack_set) == ("A", 3, True, False)
    text = m.build()["text"]
    shows = block(text, "# tier A - stack >= 3")
    assert 'BaseType == ' in shows and '"Scroll of Wisdom"' in shows and "StackSize >= 3" in shows
    hide = block(text, "# tier A - smaller stacks hidden")
    assert hide.splitlines()[1] == "Hide" and '"Scroll of Wisdom"' in hide
    # first match: one scroll is hidden, a stack of 3 shows with the A look
    assert _stack_eval(text, "Scroll of Wisdom", 1)[0] == "Hide"
    hit = _stack_eval(text, "Scroll of Wisdom", 3)
    assert hit[0] == "Show" and any(l.startswith("SetFontSize") for l in hit)
    assert _stack_eval(text, "Chaos Orb", 1)[0] == "Show"           # a name without a rule shows every one


def test_tier_minimum_item_minimum_larger_wins_and_unstackable_names_are_skipped():
    m = model("poe1")
    m.set_row("Currency", "Chaos Orb", "B")
    m.set_tier_stack("B", 5)
    rows = {r.key: r for r in m.rows("Currency")}
    assert rows["Chaos Orb"].stack == 5
    m.set_stack(["Chaos Orb"], 10)
    assert {r.key: r for r in m.rows("Currency")}["Chaos Orb"].stack == 10          # the larger one
    m.set_stack(["Chaos Orb"], 1)
    assert {r.key: r for r in m.rows("Currency")}["Chaos Orb"].stack == 5           # 1 = every one, the tier still counts
    text = m.build()["text"]
    assert _stack_eval(text, "Chaos Orb", 4)[0] == "Hide" and _stack_eval(text, "Chaos Orb", 5)[0] == "Show"
    # Scroll of Wisdom: NeverSink says 3, the player says 1 -> every one is shown (B tier minimum is 5 though)
    m.set_row("Currency", "Scroll of Wisdom", "B")
    m.set_stack(["Scroll of Wisdom"], 1)
    assert {r.key: r for r in m.rows("Currency")}["Scroll of Wisdom"].stack == 5
    m.set_tier_stack("B", 1)
    assert {r.key: r for r in m.rows("Currency")}["Scroll of Wisdom"].stack == 1
    assert _stack_eval(m.build()["text"], "Scroll of Wisdom", 1)[0] == "Show"
    # unstackable names never get a StackSize line (a unique base / a Tablet / a lineage gem)
    m2 = model("poe2")
    m2.set_tier_stack("B", 9)
    m2.set_tier_stack("S", 9)
    t = m2.build()["text"]
    assert "StackSize >= 9" in t
    stackable = w.stack_info(data("poe2")[1])[1]
    gated = 0
    for seg in t.split(chr(10) * 2):
        if "StackSize >= 9" in seg and seg.splitlines()[1] == "Show":
            names = re.findall(r'"([^"]*)"', next(l for l in seg.splitlines() if l.strip().startswith("BaseType ==")))
            gated += len(names)
            assert names and all(n in stackable and not n.endswith(" Tablet") for n in names)
    assert gated > 20
    rows2 = m2.rows("LineageGem")
    assert rows2 and all(not r.stackable and r.stack == 1 for r in rows2)


def test_names_with_different_minimums_get_their_own_blocks_in_order():
    m = model("poe1")
    m.set_tier_stack("B", 2)
    m.set_stack(["Orb of Alchemy"], 7)
    text = m.build()["text"]
    assert "# tier B - stack >= 2" in text and "# tier B - stack >= 7" in text
    seg7 = block(text, "# tier B - stack >= 7")
    assert '"Orb of Alchemy"' in seg7 and seg7.count("StackSize >= 7") == 1
    hide7 = block(text, "# tier B - smaller stacks hidden")
    assert hide7.splitlines()[1] == "Hide"
    for name in ("Orb of Alchemy",):
        assert _stack_eval(text, name, 6)[0] == "Hide" and _stack_eval(text, name, 7)[0] == "Show"
    # the stack config survives a round trip and the file passes the keyword / operator lint
    again = WlModel.from_config(json.loads(json.dumps(m.to_config({}))), "poe1")
    again.set_data(*data("poe1"))
    assert again.build()["text"] == text
    assert lint(text, data("poe1")[1]) == []


def test_reset_row_and_category_clear_the_names_own_minimum():
    m = model("poe1")
    m.set_stack(["Chaos Orb"], 4)
    m.reset_row("Currency", "Chaos Orb")
    assert "Chaos Orb" not in m.item_stack
    m.set_stack(["Chaos Orb"], 4)
    m.reset_category("Currency")
    assert not m.item_stack


# ---------------------------------------------------------------------------- B: block labels

def test_gear_block_labels_read_like_the_condition_summaries():
    m = model("poe1")
    labels = [r.label for c in dict(m.categories()) if c.startswith("gear:") for r in m.rows(c)]
    assert any(l.startswith("Rare แหวน") or "แหวน" in l for l in labels)
    assert any("Rare อาวุธ" in l and "AreaLevel ≤" in l for l in labels)
    assert any("ilvl ≥" in l for l in labels)
    assert not any(l.startswith("   ") or l.strip() == "" for l in labels)
    assert len({r.key for c in dict(m.categories()) if c.startswith("gear:") for r in m.rows(c)}) == len(labels)


# ---------------------------------------------------------------------------- D1: opacity controls

def test_opacity_slider_tick_and_entry_are_one_value(root):
    ed = StyleEditor(root, {"text": [10, 20, 30, 200]})
    assert ed._alpha["text"].get() == "200" and not ed._clear["text"].get()
    ed._clear["text"].set(True); ed._clear_toggled("text")
    assert ed._alpha["text"].get() == "0" and int(ed._slider["text"].get()) == 0
    assert ed.get_style()["text"] == [10, 20, 30, 0]
    ed._clear["text"].set(False); ed._clear_toggled("text")
    assert ed._alpha["text"].get() == "200" and ed.get_style()["text"][3] == 200       # back to what it was
    ed._slider["text"].set(77); ed._alpha_slid("text", 77)
    assert ed._alpha["text"].get() == "77" and not ed._clear["text"].get()
    ed._alpha["text"].set("0"); ed._alpha_typed("text")
    assert ed._clear["text"].get() and int(ed._slider["text"].get()) == 0
    ed._alpha["text"].set("999"); ed._alpha_typed("text")
    assert ed.get_style()["text"][3] == 255                                              # clamped like the engine does
    # all three colours have their own controls
    for key in ("text", "border", "bg"):
        assert key in ed._slider and key in ed._clear
    # untick when it was already transparent on open -> opaque
    ed2 = StyleEditor(root, {"bg": [0, 0, 0, 0]})
    assert ed2._clear["bg"].get()
    ed2._clear["bg"].set(False); ed2._clear_toggled("bg")
    assert ed2.get_style()["bg"] == [0, 0, 0, 255]


def test_the_opacity_hint_is_on_screen(root):
    ed = StyleEditor(root, None)
    texts = []
    def walk(wd):
        for c in wd.winfo_children():
            if isinstance(c, tk.Label):
                texts.append(c.cget("text"))
            walk(c)
    walk(ed)
    assert "ความทึบ (255 = ทึบ, 0 = โปร่งใส)" in texts


def test_transparent_colours_reach_the_file(root, cfg):
    win = make_window(root, cfg)
    p = win._panel
    p._edit_style("G", "Gold")
    top = p._style_dialog
    ed = top._style_editor
    ed._clear["bg"].set(True); ed._clear_toggled("bg")
    ed._slider["text"].set(100); ed._alpha_slid("text", 100)
    click(top, "บันทึก")
    p.v_gold.set(True); p._parts_changed()
    text = win._model.build()["text"]
    seg = block(text, "# gold")
    assert re.search(r"SetBackgroundColor \d+ \d+ \d+ 0\b", seg) and re.search(r"SetTextColor \d+ \d+ \d+ 100\b", seg)


# ---------------------------------------------------------------------------- D2: nothing the player unticks comes back

def _full_style():
    return {"text": [10, 20, 30, 40], "border": [50, 60, 70, 255], "bg": [1, 2, 3, 0], "size": 33,
            "icon": {"size": 2, "color": "Cyan", "shape": "Moon"}, "effect": {"color": "Pink", "temp": True},
            "sound": {"kind": "game", "id": 7, "volume": 120}}


@pytest.mark.parametrize("part", ["text", "border", "bg", "size", "icon", "effect"])
def test_editor_keeps_each_unticked_part_unticked(root, part):
    ed = StyleEditor(root, _full_style())
    box = {"text": ed._on["text"], "border": ed._on["border"], "bg": ed._on["bg"], "size": ed._size_on,
           "icon": ed._icon_on, "effect": ed._eff_on}[part]
    box.set(False); ed._changed()
    got = ed.get_style()
    assert got[part] is None
    others = [k for k in ("text", "border", "bg", "size", "icon", "effect") if k != part]
    assert all(got[k] is not None for k in others)
    again = StyleEditor(root, got).get_style()                       # saved -> closed -> opened again
    assert again == got


def test_editor_round_trips_every_field_value(root):
    colours = [[0, 0, 0, 0], [255, 255, 255, 255], [1, 2, 3, 128]]
    for key in ("text", "border", "bg"):
        for c in colours:
            st = dict(filter_style.normalize_style({}), **{key: c})
            assert StyleEditor(root, StyleEditor(root, st).get_style()).get_style()[key] == c
    for size in (18, 33, 45):
        assert StyleEditor(root, {"size": size}).get_style()["size"] == size
    for isz in (0, 1, 2):
        for color in filter_style.COLORS[:3]:
            for shape in filter_style.SHAPES[:3]:
                icon = {"size": isz, "color": color, "shape": shape}
                assert StyleEditor(root, {"icon": icon}).get_style()["icon"] == icon
    for temp in (True, False):
        eff = {"color": "Blue", "temp": temp}
        assert StyleEditor(root, {"effect": eff}).get_style()["effect"] == eff
    for snd in ({"kind": "none"}, {"kind": "game", "id": 16, "volume": 0}, {"kind": "game", "id": 3, "volume": 300},
                {"kind": "file", "file": "a.mp3", "volume": 55}):
        got = StyleEditor(root, {"sound": snd}).get_style()["sound"]
        assert got["kind"] == snd["kind"] and got["volume"] == snd.get("volume", 300)
        assert StyleEditor(root, {"sound": got}).get_style()["sound"] == got


def test_unticked_parts_of_a_tier_stay_off_and_leave_the_file(root, cfg):
    win = make_window(root, cfg, "poe1")
    p = win._panel
    base = win._model.base_style("S")
    assert base["text"] and base["border"] and base["bg"] and base["size"] and base["icon"] and base["effect"]
    p._edit_style("S", "tier S", show_sound=False)
    top = p._style_dialog
    ed = top._style_editor
    ed._on["text"].set(False); ed._on["border"].set(False); ed._icon_on.set(False); ed._eff_on.set(False)
    ed._changed()
    click(top, "บันทึก")
    assert sorted(win._model.tier_style["S"]["off"]) == ["border", "effect", "icon", "text"]
    # reopen: still unticked (this is what used to jump back to NeverSink's values)
    p._edit_style("S", "tier S", show_sound=False)
    ed2 = p._style_dialog._style_editor
    got = ed2.get_style()
    assert got["text"] is None and got["border"] is None and got["icon"] is None and got["effect"] is None
    assert got["bg"] == base["bg"] and got["size"] == base["size"]
    p._style_dialog.destroy()
    text = win._model.build()["text"]
    seg = block(text, "# tier S\n")
    assert "SetTextColor" not in seg and "SetBorderColor" not in seg and "MinimapIcon" not in seg
    assert "PlayEffect" not in seg
    assert "SetBackgroundColor" in seg and "SetFontSize" in seg and "PlayAlertSound" in seg   # the rest + shared sound
    # and the same through save -> new window -> reopen
    fg = win._save("whitelist")
    m2 = WlModel.from_config(json.loads(json.dumps(fg)), "poe1")
    m2.set_data(*data("poe1"))
    assert m2.effective_style("S") == win._model.effective_style("S")
    assert m2.build()["text"] == text
    # ticking one back on: the value is stored, the off mark goes
    win._model.set_style_from_editor("S", dict(win._model.effective_style("S"),
                                               text=[9, 9, 9, 255]))
    assert "text" not in win._model.tier_style["S"].get("off", [])
    assert "SetTextColor 9 9 9 255" in block(win._model.build()["text"], "# tier S\n")


@pytest.mark.parametrize("game", ["poe1", "poe2"])
@pytest.mark.parametrize("label", ["S", "A", "B", "G", "Tablet", "Map"])
def test_every_style_field_of_every_whitelist_style_round_trips_through_the_dialog(root, cfg, game, label):
    if label == "Tablet" and game == "poe1":
        pytest.skip("no tablets in poe1")
    win = make_window(root, cfg, game)
    p = win._panel
    p.v_gold.set(True); p.v_map.set(True); p._parts_changed()
    shared = label in ("S", "A", "B")

    def open_editor():
        p._edit_style(label, label, show_sound=not shared)
        return p._style_dialog

    def assert_matches_file(style):
        win._model.gold, win._model.map_on = True, True
        text = win._model.build()["text"]
        head = {"S": "# tier S\n", "A": "# tier A\n", "B": "# tier B\n", "G": "# gold", "Tablet": "# tablets\n",
                "Map": "# maps" if game == "poe1" else "# waystones"}[label]
        seg = block(text, head)
        lines = {l.split(None, 1)[0]: l.strip() for l in seg.splitlines() if l.startswith("    ")
                 and l.split(None, 1)[0] in filter_style.PART_KEYWORDS["text"] + filter_style.PART_KEYWORDS["border"]
                 + filter_style.PART_KEYWORDS["bg"] + filter_style.PART_KEYWORDS["size"]
                 + filter_style.PART_KEYWORDS["icon"] + filter_style.PART_KEYWORDS["effect"] + ("PlayAlertSound",)}
        want = {l.split(None, 1)[0]: l.strip() for l in filter_style.style_lines(style, indent="")
                if l.split(None, 1)[0] != "CustomAlertSoundOptional"}
        if shared:      # the sound is the shared NeverSink one
            want.pop("PlayAlertSound", None)
            lines.pop("PlayAlertSound", None)
        assert lines == want, (label, lines, want)

    # 1) set every field to a value of our own
    top = open_editor()
    ed = top._style_editor
    ed.set_style(dict(_full_style(), sound=_full_style()["sound"]))
    ed._changed()
    expect = ed.get_style()
    click(top, "บันทึก")
    top = open_editor()
    assert top._style_editor.get_style() == (expect if not shared else dict(expect, sound=top._style_editor.get_style()["sound"]))
    top.destroy()
    assert_matches_file(win._model.effective_style(label))
    # 2) untick every part one by one: each stays off after save / reopen, and is gone from the file
    for part, var in (("text", "_on"), ("border", "_on"), ("bg", "_on"), ("size", "_size_on"), ("icon", "_icon_on"),
                      ("effect", "_eff_on")):
        top = open_editor()
        ed = top._style_editor
        (ed._on[part] if var == "_on" else getattr(ed, var)).set(False)
        ed._changed()
        saved = ed.get_style()
        click(top, "บันทึก")
        top = open_editor()
        reopened = top._style_editor.get_style()
        top.destroy()
        assert reopened[part] is None, (label, part)
        for k in ("text", "border", "bg", "size", "icon", "effect"):
            assert reopened[k] == saved[k], (label, part, k)
        assert_matches_file(win._model.effective_style(label))
    # 3) everything off, and the sound off where this tab owns it
    top = open_editor()
    ed = top._style_editor
    for k in ("text", "border", "bg"):
        ed._on[k].set(False)
    ed._size_on.set(False); ed._icon_on.set(False); ed._eff_on.set(False)
    ed._snd_kind.set("none")
    ed._changed()
    click(top, "บันทึก")
    top = open_editor()
    got = top._style_editor.get_style()
    top.destroy()
    assert all(got[k] is None for k in ("text", "border", "bg", "size", "icon", "effect")), got
    assert got["sound"]["kind"] == "none" or shared
    seg_style = win._model.effective_style(label)
    assert all(seg_style[k] is None for k in ("text", "border", "bg", "size", "icon", "effect"))
    # 4) the whole thing survives the config file
    fg = win._save("whitelist")
    m2 = WlModel.from_config(json.loads(json.dumps(fg)), game)
    m2.set_data(*data(game))
    assert m2.effective_style(label) == win._model.effective_style(label)


def test_a_sound_switched_off_on_g_tablet_map_stays_off(root, cfg):
    win = make_window(root, cfg, "poe2")
    p = win._panel
    m = win._model
    m.set_style_from_editor("G", dict(m.base_style("G"), sound={"kind": "game", "id": 4, "file": "", "volume": 100}))
    p._edit_style("G", "Gold")
    ed = p._style_dialog._style_editor
    assert ed.get_style()["sound"]["kind"] == "game"
    ed._snd_kind.set("none"); ed._changed()
    click(p._style_dialog, "บันทึก")
    assert m.tier_style.get("G", {}).get("sound", {}).get("kind", "none") == "none"
    p._edit_style("G", "Gold")
    assert p._style_dialog._style_editor.get_style()["sound"]["kind"] == "none"
    p._style_dialog.destroy()
    m.gold = True
    assert "PlayAlertSound" not in block(m.build()["text"], "# gold")


def test_the_reset_button_gives_neversinks_values_back(root, cfg):
    win = make_window(root, cfg, "poe1")
    p = win._panel
    m = win._model
    m.set_style_from_editor("A", dict(m.effective_style("A"), text=None, size=None))
    assert m.tier_style["A"]["off"]
    p._edit_style("A", "tier A", show_sound=False)
    click(p._style_dialog, "รีเซ็ตเป็นค่า NeverSink")
    assert "A" not in m.tier_style
    assert m.effective_style("A") == filter_style.merge_styles(m.base_style("A"), None)


# ---- the quest-items (Q) style of the NeverSink tab

def test_q_style_unticked_parts_and_emptied_style_survive_close_and_reopen(root, cfg):
    win = make_window(root, cfg, "poe1")
    win._open_quest_style()
    top = next(c for c in win._win.winfo_children() if isinstance(c, tk.Toplevel))
    ed = top._style_editor
    ed.set_style(_full_style()); ed._changed()
    want = ed.get_style()
    click(top, "บันทึก")
    assert win._style_q == want
    # untick the only thing the default had (green text) and save an empty style
    win._open_quest_style()
    top = [c for c in win._win.winfo_children() if isinstance(c, tk.Toplevel)][-1]
    ed = top._style_editor
    assert ed.get_style() == want
    ed.set_style(None); ed._changed()
    click(top, "บันทึก")
    fg = win._save("tier")
    assert fg["style_q"] is not None and filter_style.is_empty(fg["style_q"])
    win2 = FilterGenWindow(root, cfg, "poe1", on_generate=lambda *_a: None)
    win2._open_quest_style()
    top2 = [c for c in win2._win.winfo_children() if isinstance(c, tk.Toplevel)][-1]
    assert filter_style.is_empty(top2._style_editor.get_style())          # not the green default again
    # cleared on purpose -> the green suggestion is offered again
    click(top2, "ล้าง (ใช้ของ NeverSink)")
    assert win2._style_q is None
    win2._open_quest_style()
    top3 = [c for c in win2._win.winfo_children() if isinstance(c, tk.Toplevel)][-1]
    assert top3._style_editor.get_style()["text"] == filter_style.default_quest_style()["text"]


def test_every_q_field_reaches_the_tier_file_when_set():
    st = _full_style()
    st["sound"] = {"kind": "game", "id": 7, "volume": 120}
    section = filter_core.build_quest_blocks("poe1", st)
    for part in ("SetFontSize 33", "SetTextColor 10 20 30 40", "SetBorderColor 50 60 70 255",
                 "SetBackgroundColor 1 2 3 0", "PlayAlertSound 7 120", "PlayEffect Pink Temp",
                 "MinimapIcon 2 Cyan Moon"):
        assert part in section
    assert filter_core.build_quest_blocks("poe1", filter_style.normalize_style({})) == ""


# ---------------------------------------------------------------------------- C: settings embedded in the file

def _generate(cfg_dict, game, tmp_path, name="wl-test"):
    hub, base, extra = data(game)
    fg = dict(cfg_dict, whitelist_enabled=True, wl_v2=True, **{f"game_dir_{game}": str(tmp_path / "game"),
                                                               "filter_name_whitelist": name})
    cfg_obj = type("C", (), {"get": lambda self, k, d=None: dict(fg) if k == "filter_gen" else d,
                             "app_dir": lambda self: tmp_path / "app"})()
    with mock.patch.object(filter_service.neversink_source, "fetch_base_filter", return_value=(base, "t")), \
         mock.patch.object(filter_service.hub_client, "get_prices", return_value=hub), \
         mock.patch.object(filter_service.trade_names, "get_names", return_value=extra):
        return filter_service.generate_filter(cfg_obj, game, "p", mode="whitelist")


def test_embedded_settings_round_trip_and_stay_valid_filter_comments(tmp_path):
    m = model("poe2")
    m.set_row("Currency", "Chaos Orb", "S"); m.set_category(w.gear_cat("story"), "C"); m.set_tier_stack("B", 4)
    m.set_style_from_editor("A", dict(m.effective_style("A"), text=None))
    m.gold, m.gold_min = True, 12
    m.custom = [{"name": "ไทย", "rarities": ["Rare"], "tier": "A"}]          # non-ASCII must survive as ASCII
    res = _generate(m.to_config({}), "poe2", tmp_path)
    text = res["path"].read_text(encoding="utf-8")
    marks = [l for l in text.splitlines() if l.startswith(wl_embed.MARK)]
    assert marks and all(l.isascii() and len(l) < 200 for l in marks)
    assert all(l.startswith("#") for l in text.splitlines() if "poe-checker-config" in l)
    data_ = wl_embed.extract(text)
    assert data_["game"] == "poe2" and data_["cfg"]["wl_tier_stack"] == {"B": 4}
    back = WlModel.from_config(data_["cfg"], "poe2")
    assert back.to_config({}) == m.to_config({})
    assert wl_embed.classify(text) == "ok"
    assert lint(text, data("poe2")[1]) == []                                  # comment lines pass the lint too
    # regenerating from the embedded settings gives the same file
    back.set_data(*data("poe2"))
    res2 = _generate(back.to_config({}), "poe2", tmp_path, name="wl-test2")
    strip = lambda t: "\n".join(l for l in t.splitlines() if not l.startswith(wl_embed.MARK))
    assert strip(res2["path"].read_text(encoding="utf-8")) == strip(text)


def test_classify_tells_the_kinds_of_file_apart(tmp_path):
    ok = _generate({}, "poe1", tmp_path)["path"].read_text(encoding="utf-8")
    assert wl_embed.classify(ok) == "ok"
    old = "\n".join(l for l in ok.splitlines() if not l.startswith(wl_embed.MARK))
    assert wl_embed.classify(old) == "no_config"                              # a v0.10.0 file: header, no settings
    assert wl_embed.classify(filter_core.TIER_HEADER + "Show\n") == "tier"
    assert wl_embed.classify("Show\n    Class \"Gems\"\n") == "foreign"
    broken = old + "\n" + wl_embed.MARK + " !!!notbase64!!!\n"
    assert wl_embed.extract(broken) is None and wl_embed.classify(broken) == "no_config"


def test_open_filter_loads_the_settings_the_name_and_overwrites_after_asking(root, cfg, tmp_path):
    win = make_window(root, cfg, "poe1")
    p = win._panel
    p.model.set_row("Currency", "Chaos Orb", "S")
    p.model.set_tier_stack("A", 3)
    p.v_gold.set(True); p.v_gold_min.set("21")
    win._vars["game_dir"].set(str(tmp_path / "game"))
    win._vars["filter_name_whitelist"].set("my-first")
    fg = win._save("whitelist")
    res = _generate(fg, "poe1", tmp_path, name="my-first")
    path = res["path"]
    original = path.read_text(encoding="utf-8")
    # a fresh window (default settings) opens the file
    cfg2 = AppConfig("PoeFilterGen2")
    win2 = make_window(root, cfg2, "poe1")
    assert win2._model.item_tier == {}
    assert win2.open_filter(path) is True
    assert win2._model.item_tier == {"Chaos Orb": "S"} and win2._model.tier_stack == {"A": 3}
    assert win2._model.gold and win2._model.gold_min == 21
    assert win2._vars["filter_name_whitelist"].get() == "my-first"
    assert win2._panel.model is win2._model and win2._model.loaded                # the panel shows the opened settings
    assert win2._panel.v_gold_min.get() == "21" and win2._panel.v_gold.get()
    assert win2._vars["game_dir"].get() == str(path.parent)
    # change something; Generate asks first
    win2._model.set_row("Currency", "Chaos Orb", "B")
    called = []
    win2._on_generate = lambda force, mode: called.append((force, mode))
    with mock.patch("poe_price_trade.filter_window.messagebox.askyesno", return_value=False) as ask:
        win2._on_generate_clicked(False, "whitelist")
    assert ask.called and called == [] and path.read_text(encoding="utf-8") == original
    with mock.patch("poe_price_trade.filter_window.messagebox.askyesno", return_value=True) as ask:
        win2._on_generate_clicked(False, "whitelist")
    assert ask.called and called == [(False, "whitelist")]
    # asked once per open: a second Generate goes straight through
    with mock.patch("poe_price_trade.filter_window.messagebox.askyesno") as ask:
        win2._on_generate_clicked(False, "whitelist")
    assert not ask.called and len(called) == 2


def test_open_filter_refuses_files_it_cannot_edit_and_says_why(root, cfg, tmp_path):
    win = make_window(root, cfg, "poe1")
    good = _generate({}, "poe1", tmp_path, name="good")["path"].read_text(encoding="utf-8")
    cases = {
        "foreign.filter": ("Show\n    Class \"Gems\"\n", "ไม่ได้สร้างจากแท็บ Whitelist"),
        "tier.filter": (filter_core.TIER_HEADER + "Show\n", "แท็บ NeverSink"),
    }
    for fname, (body, msg) in cases.items():
        f = tmp_path / fname
        f.write_text(body, encoding="utf-8")
        before = win._log_text.get("1.0", tk.END)
        assert win.open_filter(f) is False
        assert msg in win._log_text.get("1.0", tk.END)[len(before) - 1:]
        assert win._opened_path is None and win._model.item_tier == {}
    other = _generate({}, "poe2", tmp_path, name="other")["path"]
    assert win.open_filter(other) is False and "POE2" in win._log_text.get("1.0", tk.END)
    assert win.open_filter(tmp_path / "missing.filter") is False


def test_opening_a_file_from_another_folder_writes_back_there(root, cfg, tmp_path):
    other = tmp_path / "elsewhere"
    res = _generate({}, "poe1", tmp_path, name="moved")
    other.mkdir()
    f = other / "moved.filter"
    f.write_text(res["path"].read_text(encoding="utf-8"), encoding="utf-8")
    win = make_window(root, cfg, "poe1")
    win._vars["game_dir"].set(str(tmp_path / "game"))
    assert win.open_filter(f)
    assert win._vars["game_dir"].get() == str(other.resolve())
    called = []
    win._on_generate = lambda force, mode: called.append(mode)
    with mock.patch("poe_price_trade.filter_window.messagebox.askyesno", return_value=True) as ask:
        win._on_generate_clicked(False, "whitelist")
    assert ask.called and called == ["whitelist"]
    assert str(ask.call_args[0][1]).count("moved.filter") == 1 and "elsewhere" in str(ask.call_args[0][1])


def test_renaming_after_opening_does_not_ask_and_clears_the_link(root, cfg, tmp_path):
    path = _generate({}, "poe1", tmp_path, name="first")["path"]
    win = make_window(root, cfg, "poe1")
    assert win.open_filter(path)
    win._vars["filter_name_whitelist"].set("second")
    called = []
    win._on_generate = lambda force, mode: called.append(mode)
    with mock.patch("poe_price_trade.filter_window.messagebox.askyesno") as ask:
        win._on_generate_clicked(False, "whitelist")
    assert not ask.called and called == ["whitelist"] and win._opened_path is None


# ---------------------------------------------------------------------------- compared with NeverSink strictness 2

@pytest.mark.parametrize("game", ["poe1", "poe2"])
def test_untouched_whitelist_answers_like_neversink_s2_for_every_name_and_stack(game):
    import importlib.util
    spec = importlib.util.spec_from_file_location("compare_neversink", Path(__file__).parent.parent / "tools" / "compare_neversink.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    res = mod.compare(game, stacks=(1, 2, 3, 5, 20, 100))
    assert res["total"] > 1500
    assert res["same"] == res["total"], {k: sorted({n for n, _s in v})[:5] for k, v in res["diffs"].items()}
