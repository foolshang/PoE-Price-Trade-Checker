"""Jewel / flask / charm categories can be tiered by rarity (Normal / Magic / Rare): written ahead of the category's
own blocks, so rarity beats one block, the whole category and NeverSink; uniques are never touched."""
from __future__ import annotations
import re

import pytest

from poe_price_trade import filter_whitelist as w, wl_embed, wl_import
from poe_price_trade.wl_model import WlModel
from tests.test_filter_vocabulary import lint
from tests.test_wl_phase3b import _generate, cfg, data, make_window, model, root       # noqa: F401  (fixtures)
from tools import compare_neversink as cmp

CASES = [("poe1", "gear:jewel", "Jewels"), ("poe1", "gear:jewel", "Abyss Jewels"), ("poe1", "gear:flask", "Life Flasks"),
         ("poe1", "gear:flask", "Tinctures"), ("poe2", "gear:jewel", "Jewels"), ("poe2", "gear:flask", "Charms"),
         ("poe2", "gear:flask", "Life Flasks")]


def probe(text, cls, rarity, base="Test Base"):
    """(shown, index) of the first block that decides the item."""
    blocks = cmp.parse_blocks(text)
    return cmp.visible(blocks, {"base": base, "cls": cls, "rarity": rarity, "stack": 1, "area": 70, "ilvl": 80,
                                "quality": 0, "drop": 80, "gem": 1})


def titles(text):
    """Title comment of every Show / Hide block, in order (the comment line right above it)."""
    out, last = [], ""
    for l in text.splitlines():
        s = l.strip()
        if s.startswith("#"):
            last = s
        elif s.split(" ")[0] in ("Show", "Hide"):
            out.append(last)
            last = ""
        elif not s:
            last = ""
    return out


def test_the_classes_used_are_the_ones_neversink_s2_uses_in_both_games():
    for game, cats in w.RARITY_CATEGORIES.items():
        base = data(game)[1]
        in_file = set(re.findall(r'"([^"]+)"', "\n".join(l for l in base.split("\n") if l.strip().startswith("Class"))))
        for cat, classes in cats.items():
            assert set(classes) <= in_file, (game, cat)
            assert any(g[0] == cat[len(w.GEAR_PREFIX):] for g in w.GEAR_GROUPS[game])


@pytest.mark.parametrize("game,cat,cls", CASES)
def test_a_rarity_set_to_C_hides_it_and_nothing_else(game, cat, cls):
    m = model(game)
    plain = m.build()["text"]
    m.set_rarity(cat, "Magic", "C")
    text = m.build()["text"]
    assert lint(text, data(game)[1]) == []
    assert probe(text, cls, "Magic")[0] is False
    for rar in ("Normal", "Rare", "Unique"):                      # the other rarities: the same block decides
        (sa, ia), (sb, ib) = probe(plain, cls, rar), probe(text, cls, rar)
        assert sa == sb
        if ia >= 0:
            assert titles(plain)[ia] == titles(text)[ib]
    other = "Rings" if game == "poe1" else "Amulets"
    assert probe(text, other, "Magic")[0] == probe(plain, other, "Magic")[0]


@pytest.mark.parametrize("game,cat,cls", CASES)
def test_a_rarity_set_to_a_tier_uses_that_tiers_style_and_wins_over_a_block_and_the_category(game, cat, cls):
    m = model(game)
    m.set_style_from_editor("B", dict(m.effective_style("B"), size=31))
    m.set_rarity(cat, "Normal", "B")
    m.set_category(cat, "C")                      # clears the rarity (a whole-category tier would lose) ...
    assert m.get_rarity(cat, "Normal") is None
    m.set_rarity(cat, "Normal", "B")              # ... so set it after: rarity beats the category tier
    m.set_row(cat, m.rows(cat)[0].key, "C")       # ... and a block set alone
    text = m.build()["text"]
    shown, i = probe(text, cls, "Normal")
    ts = titles(text)
    assert shown and ts[i].startswith("# rarity:") and "Normal - tier B" in ts[i]
    lines = text.splitlines()
    block = "\n".join(lines[lines.index(ts[i]):]).split("\n\n")[0]
    assert "SetFontSize 31" in block and "Class == " in block and "Rarity Normal" in block
    assert i < [k for k, t in enumerate(ts) if t.startswith("# gear:")][0]      # before every gear block of NeverSink
    assert lint(text, data(game)[1]) == []


@pytest.mark.parametrize("game,cat,cls", CASES)
def test_default_is_by_neversink_and_the_text_is_unchanged(game, cat, cls):
    m = model(game)
    assert all(m.get_rarity(cat, r) is None for r in w.RARITY_CHOICES)
    assert "# rarity:" not in m.build()["text"]
    m.set_rarity(cat, "Rare", "A")
    m.set_rarity(cat, "Rare", None)               # back to NeverSink's blocks
    assert m.rarity_tier == {} and "# rarity:" not in m.build()["text"]
    assert not m.has_rarity("Currency") and not m.has_rarity("gear:rare_ilvl")


def test_unique_jewels_still_follow_the_unique_category():
    m = model("poe1")
    m.set_rarity("gear:jewel", "Magic", "C")
    m.set_rarity("gear:jewel", "Rare", "C")
    text = m.build()["text"]
    base = next(b for _n, b in m._entries if b.endswith("Jewel"))
    shown, i = probe(text, "Jewels", "Unique", base)
    assert shown and titles(text)[i].startswith("# uniques")
    assert all("Rarity Unique" not in b for b in text.split("\n\n") if b.startswith("# rarity:"))


def test_rarity_survives_embedded_settings_open_and_the_saved_config(root, cfg, tmp_path):
    m = model("poe2")
    m.set_rarity("gear:jewel", "Magic", "C")
    m.set_rarity("gear:flask", "Normal", "B")
    fg = m.to_config({})
    assert fg["wl_rarity_tier_poe2"] == {"gear:jewel": {"Magic": "C"}, "gear:flask": {"Normal": "B"}}
    path = _generate(fg, "poe2", tmp_path, name="rar")["path"]
    text = path.read_text(encoding="utf-8")
    assert wl_embed.extract(text)["cfg"]["wl_rarity_tier_poe2"] == fg["wl_rarity_tier_poe2"]
    win = make_window(root, cfg, "poe2")
    assert win.open_filter(path) is True
    assert win._model.get_rarity("gear:jewel", "Magic") == "C" and win._model.get_rarity("gear:flask", "Normal") == "B"
    def body(t):                                  # the file without its settings lines and the always-written quest blocks
        t = t.split("# settings of this filter")[0]
        if "# quest items" not in t:
            return t.rstrip()
        i = t.index("# quest items")
        nxt = re.search(r"\n# (?!quest items)", t[i:]).start() + i + 1
        return (t[:i] + t[nxt:]).rstrip()
    assert body(win._model.build()["text"]) == body(text)
    assert win._save("whitelist")["wl_rarity_tier_poe2"] == fg["wl_rarity_tier_poe2"]
    junk = dict(fg, wl_rarity_tier_poe2={"gear:jewel": {"Unique": "C", "Magic": "Z"}, "Currency": {"Magic": "C"}})
    assert WlModel.from_config(junk, "poe2").rarity_tier == {}


def test_an_old_file_opens_without_rarity_settings():
    cur = model("poe2")
    cur.set_rarity("gear:jewel", "Magic", "C")                      # remembered, but an old file knows nothing of it
    from tests.test_wl_import import old_text
    assert wl_import.read(old_text("v2_poe2_bus"), "poe2", cur)["model"].rarity_tier == {}


def test_the_whole_category_buttons_clear_the_rarity():
    m = model("poe1")
    m.set_rarity("gear:flask", "Magic", "C")
    m.reset_category("gear:flask")
    assert m.rarity_tier == {}
    m.set_rarity("gear:jewel", "Rare", "A")
    assert m.changed_count("gear:jewel") == 1


def test_the_panel_shows_the_rarity_box_only_for_those_categories_and_applies_picks(root, cfg):
    win = make_window(root, cfg, "poe1")
    p = win._panel
    labels = dict(win._model.categories())
    p.cat_var.set(labels["gear:jewel"]); p.refresh_list(); root.update()
    assert bool(p._rar_box.winfo_manager()) and p.v_rar["Magic"].get() == "ตาม NeverSink"
    p.v_rar["Magic"].set("C"); p._rarity_picked("Magic")
    assert win._model.get_rarity("gear:jewel", "Magic") == "C"
    assert p._rar_warn.cget("text") == "ตั้ง C = ซ่อนทุกชิ้นของ rarity นั้น รวมตัวที่ mod ดีในหมวดอื่นด้วย"
    p.cat_var.set(labels["Currency"]); p.refresh_list(); root.update()
    assert not bool(p._rar_box.winfo_manager())
    p.cat_var.set(labels["gear:jewel"]); p.refresh_list()
    assert p.v_rar["Magic"].get() == "C"                                 # remembered when coming back
