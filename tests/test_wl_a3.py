"""Whitelist phase 3b A3: Runegraft / Vial / Corpse / Wombgift / Relic name lists, the generic-gem block list,
the fragment fallbacks, and the stack-size defaults checked against a first-match simulation of NeverSink."""
from __future__ import annotations
import pytest

from poe_price_trade import filter_whitelist as w, wl_embed
from poe_price_trade.wl_model import WlModel
from tests.test_filter_vocabulary import lint
from tests.test_wl_phase3b import data, model
from tools import compare_neversink as cmp

NAMED = ("Runegraft", "Vial", "Corpse", "Wombgift", "Relic")


def shown(text, name, cls, rarity="Normal", stack=1):
    item = {"base": name, "cls": cls, "rarity": rarity, "stack": stack, "area": 70, "ilvl": 80, "quality": 0,
            "drop": 80, "gem": 1}
    return cmp.visible(cmp.parse_blocks(text), item)[0]


def test_named_categories_and_starting_tiers():
    m = model("poe1")
    cats = {c for c, _l in m.categories()}
    assert set(NAMED) <= cats
    tier = {r.key: r.tier for c in NAMED for r in m.rows(c)}
    assert tier["Runegraft of Gemcraft"] == "S" and tier["Runegraft of Bellows"] == "A"       # t1 / t2
    assert tier["Vial of Sacrifice"] == "S" and tier["Vial of Summoning"] == "A"
    assert tier["Perfect Warlord"] == "S" and tier["Perfect Hydra"] == "A"
    assert tier["Imperfect Blasphemer"] == "B"                                               # t4
    assert tier["Ancient Wombgift"] == "A" and tier["Lavish Wombgift"] == "B"
    assert tier["Candlestick Relic"] == "B"
    assert "Relic" in {c for c, _l in model("poe2").categories()}


@pytest.mark.parametrize("game,name,cls,cat", [
    ("poe1", "Runegraft of Gemcraft", "Stackable Currency", "Runegraft"),
    ("poe1", "Vial of Sacrifice", "Stackable Currency", "Vial"),
    ("poe1", "Perfect Warlord", "Corpses", "Corpse"),
    ("poe1", "Ancient Wombgift", "Wombgifts", "Wombgift"),
    ("poe1", "Candlestick Relic", "Relics", "Relic"),
    ("poe2", "Coffer Relic", "Relics", "Relic")])
def test_a_named_item_follows_its_tier(game, name, cls, cat):
    m = model(game)
    text = m.build()["text"]
    assert shown(text, name, cls)
    m.set_row(cat, name, "C")
    hidden = m.build()["text"]
    assert not shown(hidden, name, cls) and lint(hidden, data(game)[1]) == []
    m.set_row(cat, name, "S")
    assert f'"{name}"' in block(m.build()["text"], "# tier S")


def block(text, header):
    i = text.index(header)
    return text[i:text.find("\n\n", i)]


def test_category_tier_hides_a_whole_list():
    m = model("poe1")
    m.set_category("Runegraft", "C")
    text = m.build()["text"]
    assert not shown(text, "Runegraft of Gemcraft", "Stackable Currency")
    # a name no list has yet still follows the fragment rule (shown by default, hidden by its own row)
    assert shown(text, "Runegraft of Zzz Not Yet Listed", "Stackable Currency")
    m.set_row("Special", w.BASE_PREFIX + "Runegraft", "C")
    assert not shown(m.build()["text"], "Runegraft of Zzz Not Yet Listed", "Stackable Currency")


def test_whole_class_fallbacks_stay():
    m = model("poe1")
    text = m.build()["text"]
    assert shown(text, "Zzz Not Yet Listed", "Corpses") and shown(text, "Zzz Not Yet Listed Wombgift", "Wombgifts")
    assert shown(text, "Vial of Zzz Not Yet Listed", "Stackable Currency")
    rows = {r.key: r for r in m.rows("Special")}
    assert w.BASE_PREFIX + "Vial of" in rows and "Corpses" in rows
    m.set_category("Special", "C")
    off = m.build()["text"]
    assert not shown(off, "Zzz Not Yet Listed", "Corpses") and not shown(off, "Vial of Zzz Not Yet Listed", "Stackable Currency")


def test_generic_gems_are_listed_block_by_block():
    m = model("poe1")
    rows = m.rows("gear:gems")
    assert len(rows) >= 25 and all(r.label.startswith("Gem") for r in rows)
    assert any("GemLevel" in r.label for r in rows) and any("Quality" in r.label for r in rows)
    assert len({r.key for r in rows}) == len(rows)
    base = data("poe1")[1]
    text = m.build()["text"]
    assert lint(text, base) == []
    gem = lambda t: shown(t, "Fireball", "Skill Gems", stack=1)
    # the whole category hidden: no gem block is written as Show any more
    m.set_category("gear:gems", "C")
    assert "# gear: Gem ทั่วไป" in m.build()["text"]
    assert not gem(m.build()["text"])
    # one block of the category on its own
    key = next(r.key for r in rows if r.label.startswith("Gem  Quality ≥ 20   "))
    m.set_row("gear:gems", key, "S")
    out = m.build()["text"]
    assert "tier S (gems->generic)" in out and lint(out, base) == []
    assert "gear:gems" not in {c for c, _l in model("poe2").categories()}


def test_a3_survives_the_embedded_settings():
    m = model("poe1")
    m.set_row("Vial", "Vial of Fate", "C")
    m.set_category("Runegraft", "A")
    m.set_row("gear:gems", m.rows("gear:gems")[3].key, "C")
    m.set_row("Special", w.BASE_PREFIX + "Vial of", "C")
    text = wl_embed.embed(m.build()["text"], m.cfg(), "poe1")
    again = WlModel.from_config(wl_embed.extract(text)["cfg"], "poe1")
    again.set_data(*data("poe1"))
    assert again.build()["text"] == m.build()["text"]


@pytest.mark.parametrize("game", ["poe1", "poe2"])
def test_untouched_tab_equals_neversink_with_the_new_lists(game):
    res = cmp.compare(game, (1, 2, 3, 6, 20, 40))
    assert res["same"] == res["total"], {k: v[:3] for k, v in res["diffs"].items()}


@pytest.mark.parametrize("game,expected", [("poe1", 96), ("poe2", 0)])
def test_stack_defaults_are_the_names_hidden_alone_but_shown_as_a_stack(game, expected):
    """The definition: first-match NeverSink hides the name at stack 1 and shows it at some bigger stack."""
    hub, base, _extra = data(game)
    ns = cmp.parse_blocks(base)
    cls = cmp.name_classes(base)
    found = set()
    for n in cls:
        probe = lambda st: cmp.visible(ns, {"base": n, "cls": cls[n], "rarity": "Normal", "stack": st, "area": 70,
                                            "ilvl": 80, "quality": 0, "drop": 80, "gem": 1})[0]
        if not probe(1) and any(probe(st) for st in (2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 30, 40, 50, 100)):
            found.add(n)
    defaults = w.stack_info(base)[0]
    assert set(defaults) == found and len(found) == expected
