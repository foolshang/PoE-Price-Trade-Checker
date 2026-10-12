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
    assert tier["Runegraft of Gemcraft"] == "S" and tier["Runegraft of Bellows"] == "S"       # t1 / t2 = S
    assert tier["Vial of Sacrifice"] == "S" and tier["Vial of Summoning"] == "S"
    assert tier["Perfect Warlord"] == "S" and tier["Perfect Hydra"] == "S"
    assert tier["Imperfect Blasphemer"] == "A"                                               # t4 = A
    assert tier["Ancient Wombgift"] == "A" and tier["Lavish Wombgift"] == "A"                # t3 / t4
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
    m.set_row(cat, name, "D")
    hidden = m.build()["text"]
    assert not shown(hidden, name, cls) and lint(hidden, data(game)[1]) == []
    m.set_row(cat, name, "S")
    assert f'"{name}"' in block(m.build()["text"], "# tier S")


def block(text, header):
    i = text.index(header)
    return text[i:text.find("\n\n", i)]


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


def test_fallback_blocks_of_neversink_still_show_unlisted_names_of_the_lists():
    """The class / name-fragment fallbacks are NeverSink's own blocks now (copied as they are)."""
    m = model("poe1")
    text = m.build()["text"]
    assert shown(text, "Zzz Not Yet Listed", "Corpses")
    assert shown(text, "Vial of Zzz Not Yet Listed", "Stackable Currency")
    assert shown(text, "Runegraft of Zzz Not Yet Listed", "Stackable Currency")
    m.set_category("Runegraft", "D")
    off = m.build()["text"]
    assert not shown(off, "Runegraft of Gemcraft", "Stackable Currency")            # a name of the list: hidden first
    assert shown(off, "Runegraft of Zzz Not Yet Listed", "Stackable Currency")      # a new one: NeverSink's fallback


def test_a3_survives_the_embedded_settings():
    m = model("poe1")
    m.set_row("Vial", "Vial of Fate", "D")
    m.set_category("Runegraft", "A")
    text = wl_embed.embed(m.build()["text"], m.cfg(), "poe1")
    again = WlModel.from_config(wl_embed.extract(text)["cfg"], "poe1")
    again.set_data(*data("poe1"))
    assert again.build()["text"] == m.build()["text"]


def test_poe1_class_wide_wombgift_show_comes_after_the_name_blocks_and_before_the_final_hide():
    m = model("poe1")
    text = m.build()["text"]
    assert shown(text, "Growing Wombgift", "Wombgifts")                       # a name no list has: the class rule shows it
    assert shown(text, "Ancient Wombgift", "Wombgifts")
    blocks = text.split("\n\n")
    i = next(k for k, b in enumerate(blocks) if b.startswith("# wombgifts"))
    j = next(k for k, b in enumerate(blocks) if b.startswith("# hide everything else"))
    named = [k for k, b in enumerate(blocks) if '"Ancient Wombgift"' in b and b.splitlines()[0] != "# wombgifts"]
    assert named and max(named) < i < j                                       # after every block that lists names
    assert "SetFontSize" in blocks[i] and 'Class == "Wombgifts"' in blocks[i] and "BaseType" not in blocks[i]
    m.set_row("Wombgift", "Ancient Wombgift", "D")                            # a named wombgift set to D stays hidden
    assert not shown(m.build()["text"], "Ancient Wombgift", "Wombgifts")
    m.set_row("Wombgift", "Ancient Wombgift", "S")
    assert f'"Ancient Wombgift"' in block(m.build()["text"], "# tier S")      # a named one keeps its own (name) block


def test_poe2_has_no_wombgift_rule():
    assert "# wombgifts" not in model("poe2").build()["text"]


UNCUT = ("Uncut Skill Gem", "Uncut Spirit Gem", "Uncut Support Gem")


def _uncut(text, base, level):
    item = {"base": base, "cls": "Uncut Gems", "rarity": "Normal", "stack": 1, "area": 80, "ilvl": 80, "quality": 0,
            "drop": 80, "gem": level}
    return cmp.visible(cmp.parse_blocks(text), item)


@pytest.mark.parametrize("n", [1, 5, 17, 18, 20])
def test_uncut_gem_shows_from_N_up_first_match_for_all_three_types(n):
    cfg = {"whitelist_gem_uncut_poe2": {b: n for b in UNCUT}}
    text = model("poe2", cfg).build()["text"]
    for base in UNCUT:
        for lv in sorted({max(1, n - 1), n, min(20, n + 1), 20}):
            shown_, i = _uncut(text, base, lv)
            if lv >= n:
                assert shown_ and i >= 0, (base, lv, n)
                blk = cmp.parse_blocks(text)[i]
                assert any(c[0] == "GemLevel" for c in blk[1]), (base, lv, n)     # our uncut block, nothing earlier
            else:
                assert not shown_, (base, lv, n)


def test_uncut_levels_16_to_20_per_type_with_the_players_17_17_5():
    cfg = {"whitelist_gem_uncut_poe2": {"Uncut Skill Gem": 17, "Uncut Spirit Gem": 17, "Uncut Support Gem": 5}}
    text = model("poe2", cfg).build()["text"]
    for base, need in zip(UNCUT, (17, 17, 5)):
        for lv in range(16, 21):
            assert _uncut(text, base, lv)[0] is (lv >= need), (base, lv)
    assert '    BaseType "Uncut Skill Gem"' in text and 'BaseType == "Uncut' not in text
    heads = [l for l in text.splitlines() if l.startswith("# uncut gem:")]
    assert [h.split(":")[1].split(" (")[0].strip() for h in heads] == list(UNCUT)       # Skill, Spirit, Support


def test_uncut_gems_reopen_from_the_new_block_form():
    cfg = {"whitelist_gem_uncut_poe2": {"Uncut Skill Gem": 17, "Uncut Spirit Gem": 17, "Uncut Support Gem": 5}}
    m = model("poe2", cfg)
    assert m.build()["text"].count("# uncut gem:") == 3
    assert WlModel.from_config(m.to_config({}), "poe2").gem_uncut == cfg["whitelist_gem_uncut_poe2"]
