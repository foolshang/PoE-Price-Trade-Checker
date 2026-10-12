"""Tiers S / A / B / C / D (v0.12.0): S / A / B / C are shown (each with its own look, sound and stack minimum), D is hidden.
NeverSink's own tiers map t1-t2 = S, t3-t4 = A, t5-t6 = B, t7-t8 = C, a Hide block = D (letter ladders by position). A config
from before tier D has C = hidden: it is converted once (wl_tier_format)."""
from __future__ import annotations
import collections

import pytest

from poe_price_trade import filter_gen, filter_style, filter_whitelist as w, wl_embed, wl_session
from poe_price_trade.wl_model import HIDE, WlModel
from tests.test_filter_vocabulary import lint
from tests.test_wl_a3 import shown
from tests.test_wl_phase3b import _generate, data, model
from tools import compare_neversink as cmp

GAMES = ["poe1", "poe2"]


def _block(text, header):
    i = text.index(header)
    j = text.find("\n\n", i)
    return text[i:j if j > 0 else len(text)]


def _names_of_step(base, ty, tag):
    """Names whose first plain block (no StackSize / AreaLevel ... condition) is the (type, tag) step of NeverSink's ladder:
    the starting tier is that step's."""
    lines, blocks = w.scan(base)
    first = {}
    for b in blocks:
        ns = w.exact_names(lines, b)
        conds = w._conds(lines, b)
        if not ns or conds & set(w._SPECIAL_CONDITIONS) or "Continue" in conds:
            continue
        t, g = filter_gen._header_tags(lines, b)
        for n in ns:
            first.setdefault(n, (t, g))
    return sorted(n for n, k in first.items() if k == (ty, tag))


# ---------------------------------------------------------------- the starting tiers

LADDER = [
    ("poe1", "currency", "t1exalted", "S"), ("poe1", "currency", "t2divine", "S"), ("poe1", "currency", "t3annul", "A"),
    ("poe1", "currency", "t4chaos", "A"), ("poe1", "currency", "t5alchemy", "B"), ("poe1", "currency", "t6chrom", "B"),
    ("poe1", "currency", "t7chance", "C"), ("poe1", "currency", "t8trans", "C"),
    ("poe2", "currency", "s", "S"), ("poe2", "currency", "a", "S"), ("poe2", "currency", "b", "A"),
    ("poe2", "currency", "c", "A"), ("poe2", "currency", "d", "B"), ("poe2", "currency", "e", "B"),
]


@pytest.mark.parametrize("game,ty,tag,tier", LADDER)
def test_a_ladder_step_starts_at_its_new_tier(game, ty, tag, tier):
    base = data(game)[1]
    names = _names_of_step(base, ty, tag)
    assert names, (game, ty, tag)
    d = w.default_tiers(base)
    assert all(d[n] == tier for n in names), {n: d[n] for n in names}
    m = model(game)
    assert all(m.default_of(n) == tier for n in names)


@pytest.mark.parametrize("game", GAMES)
def test_a_hide_block_of_neversink_is_tier_d_and_there_is_no_hidden_c(game):
    base = data(game)[1]
    d = w.default_tiers(base)
    lines, blocks = w.scan(base)
    hide_only = [n for b in blocks if b.block_type == "Hide" for n in w.exact_names(lines, b)
                 if not (w._conds(lines, b) & set(w._SPECIAL_CONDITIONS))]
    assert hide_only and all(d.get(n) in ("D", None) or d[n] in "SABC" for n in hide_only)
    assert "D" in d.values() and set(d.values()) <= set(w.ALL_TIERS)
    assert w.HIDE_TIER == "D" and w.TIERS == ("S", "A", "B", "C") and w.ALL_TIERS == ("S", "A", "B", "C", "D")


# ---------------------------------------------------------------- first match

@pytest.mark.parametrize("game", GAMES)
def test_c_shows_with_its_own_style_between_b_and_the_hidden_names_and_d_hides(game):
    m = model(game)
    cur = "Divine Orb" if game == "poe1" else "Chaos Orb"
    cat = "Currency"
    m.set_row(cat, cur, "C")
    m.set_row(cat, "Orb of Augmentation" if game == "poe1" else "Orb of Transmutation", "D")
    text = m.build()["text"]
    cls = "Stackable Currency"
    assert shown(text, cur, cls)
    tc = _block(text, "# tier C\n")
    assert f'"{cur}"' in tc and "Show" in tc
    for line in w.default_tier_lines(m.base_text)["C"]:
        assert line.strip() in tc, line                                  # the faded preset look of C
    assert text.index("# tier C\n") > text.index("# tier B\n") if "# tier B\n" in text else True
    hid = "Orb of Augmentation" if game == "poe1" else "Orb of Transmutation"
    assert not shown(text, hid, cls)
    assert "# tier D (hidden" in text and text.index("# tier C\n") < text.index("# tier D (hidden")
    assert "tier C (hidden" not in text
    assert lint(text, m.base_text) == []


def test_the_style_and_the_sound_of_c_are_its_own():
    base = data("poe1")[1]
    hub = data("poe1")[0]
    cfg = {"wl_item_tier_poe1": {"Chaos Orb": "C"}, "wl_tier_format": 2,
           "wl_tier_style": {"C": {"size": 30, "text": [1, 2, 3, 255], "sound": {"kind": "file", "file": "ping-c.mp3"}}}}
    assert w.sound_requests(cfg)["C"] == "ping-c.mp3"
    res = w.build_whitelist_filter("poe1", cfg, base, hub, "", {"C": "ping-c.mp3"}, None)
    tc = _block(res["text"], "# tier C\n")
    assert "SetFontSize 30" in tc and "SetTextColor 1 2 3 255" in tc
    assert 'CustomAlertSoundOptional "ping-c.mp3" 300' in tc
    # the NeverSink tab's numbered sounds are that tab's alone: nothing of them in the whitelist's own look
    out, done = filter_gen.apply_numbered_sounds(
        'Show # $type->currency $tier->t1\n\tBaseType == "Divine Orb"\n\tPlayAlertSound 6 300\n', {"2": "x.mp3"})
    assert done == {} and "CustomAlertSoundOptional" not in out


def test_c_has_its_own_stack_minimum():
    m = model("poe1")
    m.set_row("Currency", "Chaos Orb", "C")
    m.set_tier_stack("C", 5)
    text = m.build()["text"]
    assert "# tier C - stack >= 5" in text and "# tier C - smaller stacks hidden" in text
    assert m.tier_stack == {"C": 5}
    assert m.to_config({})["wl_tier_stack"] == {"C": 5}


@pytest.mark.parametrize("game", GAMES)
def test_a_whole_category_and_typed_names_and_gems_follow_c_and_d(game):
    m = model(game)
    m.set_category("Currency", "C")
    assert all(r.tier == "C" for r in m.rows("Currency"))
    m.set_category("Currency", "D")
    assert all(r.tier == "D" for r in m.rows("Currency")) and m.category_tier("Currency") == "D"
    m.custom = [{"name": "Rakiata", "rarities": ["Rare"], "tier": "C"}, {"name": "Hidden", "rarities": ["Rare"], "tier": "D"}]
    text = m.build()["text"]
    seg = _block(text, "# typed names")
    assert 'BaseType "Rakiata"' in text and 'BaseType "Hidden"' not in text and "tier C" in seg
    m.gem_tier = "C"
    assert m.cfg()["whitelist_gem_tier"] == "C"


@pytest.mark.parametrize("game", GAMES)
def test_equipment_and_flask_rows_c_shows_and_d_hides(game):
    m = model(game)
    rid = "Flask"
    m.set_flask_rarity(rid, "Magic", "C")
    m.set_flask_rarity(rid, "Normal", "D")
    cls = "Life Flasks"
    text = m.build()["text"]
    assert shown(text, "Some Flask", cls, rarity="Magic") and not shown(text, "Some Flask", cls, rarity="Normal")
    assert "# rarity: Flask - Magic - tier C" in text and "# rarity: Flask - Normal - tier D" in text
    m.set_equip_rarity("Boots", "Rare", "C")
    m.set_equip_rarity("Boots", "Magic", "D")
    text = m.build()["text"]
    assert shown(text, "Some Boots", "Boots", rarity="Rare") and not shown(text, "Some Boots", "Boots", rarity="Magic")
    assert "# equipment: Boots - Rare - tier C" in text and "# equipment: Boots - Magic - tier D" in text
    assert w.default_tier_lines(m.base_text)["C"][0].strip() in _block(text, "# equipment: Boots - Rare - tier C")


# ---------------------------------------------------------------- old configs: C was the hidden tier

OLD = {
    "wl_item_tier_poe1": {"Chaos Orb": "C", "Divine Orb": "S"},
    "wl_cat_tier_poe1": {"Scarab": "C", "Currency": "A"},
    "wl_unique_tier_poe1": {"Headhunter": "C", "Mageblood": "B"},
    "wl_block_tier_poe1": {"x|t1|1": "C"},
    "wl_rarity_rows_poe1": {"Flask": {"custom": True, "tiers": {"Normal": "C", "Magic": "A"}}},
    "wl_equip_rows_poe1": {"Boots": {"custom": True, "tiers": {"Normal": "B", "Magic": "C", "Rare": "S"}}},
    "whitelist_gem_tier": "C",
    "whitelist_custom_poe1": [{"name": "Coral", "rarities": ["Rare"], "tier": "C"}, {"name": "Ring", "rarities": ["Rare"], "tier": "A"}],
}


def test_an_old_config_has_its_c_turned_into_d_once_with_a_count_and_s_a_b_are_kept():
    m = WlModel.from_config(OLD, "poe1")
    assert m.item_tier == {"Chaos Orb": "D", "Divine Orb": "S"}
    assert m.cat_tier == {"Scarab": "D", "Currency": "A"}
    assert m.unique_tier == {"Headhunter": "D", "Mageblood": "B"}
    assert m.block_tier == {"x|t1|1": "D"}
    assert m.rarity_rows["Flask"]["tiers"] == {"Normal": "D", "Magic": "A"}
    assert m.equip_rows["Boots"]["tiers"] == {"Normal": "B", "Magic": "D", "Rare": "S"}
    assert m.gem_tier == "D"
    assert [(e["name"], e["tier"]) for e in m.custom] == [("Coral", "D"), ("Ring", "A")]
    notes = m.take_notes()
    assert len(notes) == 1 and "8 ค่า" in notes[0] and "D" in notes[0] and "C" in notes[0]
    saved = m.to_config({})
    assert saved["wl_tier_format"] == w.TIER_FORMAT
    again = WlModel.from_config(saved, "poe1")                 # saved once: nothing is converted twice, no note
    assert again.take_notes() == [] and again.item_tier == m.item_tier and again.gem_tier == "D"


def test_a_config_of_the_new_format_keeps_its_c():
    cfg = {"wl_tier_format": 2, "wl_item_tier_poe2": {"Chaos Orb": "C", "Divine Orb": "D"},
           "wl_equip_rows_poe2": {"Boots": {"custom": True, "tiers": {"Normal": "B", "Rare": "C", "Magic": "D"}}},
           "whitelist_gem_tier": "C"}
    m = WlModel.from_config(cfg, "poe2")
    assert m.item_tier == {"Chaos Orb": "C", "Divine Orb": "D"} and m.gem_tier == "C"
    assert m.equip_rows["Boots"]["tiers"]["Rare"] == "C" and m.take_notes() == []
    assert m.to_config({})["wl_item_tier_poe2"] == {"Chaos Orb": "C", "Divine Orb": "D"}


def test_an_empty_or_s_a_b_only_old_config_says_nothing():
    for cfg in ({}, {"wl_item_tier_poe1": {"Chaos Orb": "A"}, "wl_cat_tier_poe1": {"Currency": "S"}}):
        m = WlModel.from_config(cfg, "poe1")
        assert m.take_notes() == []
        assert m.to_config({})["wl_tier_format"] == 2


def test_the_hidden_default_of_a_legacy_whitelist_conversion_is_d():
    fg = {"whitelist_cats_poe1": ["Currency"], "whitelist_unique_all": False}
    upd, notes = WlModel.convert_legacy(fg, "poe1")
    assert upd["wl_tier_format"] == 2 and notes
    assert set(upd["wl_cat_tier_poe1"].values()) == {"D"} and upd["wl_cat_tier_poe1"]["Unique"] == "D"


@pytest.mark.parametrize("game", GAMES)
def test_an_old_embedded_file_opens_converted_and_a_new_one_keeps_c(tmp_path, game):
    hub_base_extra = data(game)
    cur = WlModel(game)
    cur.set_data(*hub_base_extra)
    # a file of the build before tier D: its settings have no wl_tier_format and C = hidden
    old = model(game)
    old.set_row("Currency", "Chaos Orb", "D")
    fg = old.to_config({})
    fg.pop("wl_tier_format")
    fg[f"wl_item_tier_{game}"] = {"Chaos Orb": "C"}
    old_path = _generate(fg, game, tmp_path, name="old")["path"]
    res = wl_session.open_text(old_path.read_text(encoding="utf-8"), "old.filter", game, cur, hub_base_extra)
    assert res.ok and res.model.item_tier == {"Chaos Orb": "D"}
    assert any("ถูกแปลงเป็น D" in text for _t, text in res.messages)
    # saved + generated again: the file records the new format and C stays C
    new_path = _generate(res.model.to_config({}) | {f"wl_item_tier_{game}": {"Chaos Orb": "C"}}, game, tmp_path, name="new")["path"]
    emb = wl_embed.extract(new_path.read_text(encoding="utf-8"))
    assert emb["cfg"]["wl_tier_format"] == 2
    res = wl_session.open_text(new_path.read_text(encoding="utf-8"), "new.filter", game, cur, hub_base_extra)
    assert res.ok and res.model.item_tier == {"Chaos Orb": "C"}
    assert not any("ถูกแปลงเป็น D" in text for _t, text in res.messages)


def test_the_cut_off_style_labels_and_buttons_know_c():
    from poe_price_trade import wl_model
    assert wl_model.STYLE_LABELS[:4] == ("S", "A", "B", "C")
    assert wl_model.TIER_CHOICES == ("S", "A", "B", "C") and wl_model.ALL_CHOICES[-1] == "D" and HIDE == "D"
    m = model("poe1")
    st = m.effective_style("C")
    assert st["size"] == filter_style.DEFAULT_STYLES["C"]["size"]
    m.set_style("C", {"size": 31})
    assert m.cfg()["wl_tier_style"]["C"]["size"] == 31


def test_toggle_unticks_into_d_and_ticks_back_into_the_active_tier():
    m = model("poe1")
    m.toggle_row("Currency", "Chaos Orb", "C")
    assert next(r for r in m.rows("Currency") if r.key == "Chaos Orb").tier == "D"
    m.toggle_row("Currency", "Chaos Orb", "C")
    assert next(r for r in m.rows("Currency") if r.key == "Chaos Orb").tier == "C"


# ---------------------------------------------------------------- the desktop panel

from tests.test_wl_phase3b import cfg, make_window, root      # noqa: E402,F401  (fixtures)


def test_the_panel_has_four_tier_buttons_a_d_button_and_c_style(root, cfg):
    win = make_window(root, cfg, "poe1")
    p = win._panel
    assert list(p._tier_btns) == ["S", "A", "B", "C"]
    p.active.set("C"); p._on_tier_picked(); root.update()
    assert str(p._tier_reset.cget("state")) == "normal"
    assert p._tier_editor.get_style()["size"] == filter_style.DEFAULT_STYLES["C"]["size"]      # C's own (faded) look
    texts = [b.cget("text") for b in p._act_btns]
    assert "ทั้งหมวด → D (ซ่อน)" in texts and not any("→ C" in t for t in texts)
    p.cat_var.set("Currency"); p.refresh_list()
    key = next(iter(p._row_keys.values()))
    p.model.set_row("Currency", key, "C")
    p.refresh_list()
    assert any(p.tree.item(i, "values")[1] == "C" and p.tree.item(i, "values")[0].startswith("☑") for i in p.tree.get_children())
    p.model.set_row("Currency", key, "D")
    p.refresh_list()
    assert any(p.tree.item(i, "values")[1] == "D" and p.tree.item(i, "values")[0].startswith("☐") for i in p.tree.get_children())
