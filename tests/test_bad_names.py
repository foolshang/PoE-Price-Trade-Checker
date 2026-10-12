"""Names that are known to be no item name ([DNT], INCOMPLETE, (Tier N), ...) are never written into a filter and are
reported; real names are never caught."""
from __future__ import annotations
import copy

import pytest

from poe_price_trade import filter_core, filter_whitelist as w
from poe_price_trade.wl_model import WlModel
from tests.test_wl_phase3b import data, model

BAD = ["[DNT] Not Shown To Players", "[DNT] Incursion Gemcutter's Prism (not visible to players)", "INCOMPLETE",
       "Prism (not visible to players)", "60634", "Blood Stasis ",
       " Leading", "NonEleBowRangerPhysNoble", "ChaosMinionWitchChaosHitNoble"]
# names that look odd but are real: parentheses, apostrophes, digits inside, a single word, non-ASCII
GOOD = ["Chaos Orb", "Orb of Alchemy", "Thaumaturgic Flux (Level 4)", "Thaumaturgic Flux (Level 20)", "Map (Tier 12)",
        "Map (Tier 14)", "Map (Tier 16)", "Waystone (Tier 15)", "Maelström Staff", "Mórrigan's Insight", "Ring",
        "Gold", "Leatherbound Hood", "Time-Lost Diamond", "Divine Orb", "Uncut Skill Gem", "Atziri's Splendour"]


@pytest.mark.parametrize("name", BAD)
def test_known_bad_names_are_caught(name):
    assert w.bad_name(name)


@pytest.mark.parametrize("name", GOOD)
def test_real_looking_names_are_not_caught(name):
    assert not w.bad_name(name)


@pytest.mark.parametrize("game", ["poe1", "poe2"])
def test_no_real_name_of_the_program_is_caught(game):
    """Every name NeverSink lists, every name of the whitelist universe and every unique base of the hub snapshot:
    none matches (the "Map (Tier N)" / "(Level N)" names that games and NeverSink accept are not patterns)."""
    hub, base, _extra = data(game)
    names = set(w.known_names(base)) | set(w.universe(game, hub, base)) | {b for _n, b in w.unique_entries(hub)}
    hits = sorted(n for n in names if w.bad_name(n))
    assert hits == [], hits
    assert len(names) > 1500


@pytest.mark.parametrize("game", ["poe1", "poe2"])
def test_bad_names_are_left_out_reported_and_change_nothing_else(game):
    hub, base, extra = data(game)
    plain = model(game).build()
    dirty_hub = copy.deepcopy(hub)
    cat = "Currency"
    dirty_hub["items"] += [{"category": cat, "name": "[DNT] Test Currency", "base": ""},
                           {"category": cat, "name": "INCOMPLETE", "base": ""},
                           {"category": "UniqueAccessory", "name": "Bad Unique", "base": "[DNT] Test Base"}]
    junk = {"[DNT] Test Currency", "INCOMPLETE", "[DNT] Test Base", "60634"}
    m = WlModel(game)
    m.set_data(dirty_hub, base, set(extra) | junk)                         # even confirmed by the names list: still left out
    res = m.build()
    assert res["text"] == plain["text"]                                    # nothing real changed, nothing bad written
    reported = {n for n, _w in res["bad_names"]}
    assert {"[DNT] Test Currency", "INCOMPLETE"} <= reported
    for bad in ("[DNT] Test Currency", "INCOMPLETE", "Bad Unique"):
        assert f'"{bad}"' not in res["text"]
    assert '"[DNT] Test Base"' not in res["text"]


def test_the_status_says_which_names_were_left_out():
    hub, base, extra = data("poe2")
    hub = copy.deepcopy(hub)
    hub["items"].append({"category": "Currency", "name": "[DNT] Test Currency", "base": ""})
    logs = []
    fg = {"whitelist_enabled": True, "wl_v2": True}
    res = filter_core.build_filter_text(fg, "poe2", hub_data=hub, base_text=base, extra_names=set(extra) | {"[DNT] Test Currency"},
                                        log=lambda m, t="info": logs.append((t, m)))
    assert res["bad_names"] == [("[DNT] Test Currency", "item")]
    assert any(t == "warn" and "ชื่อที่รู้ว่าไม่ใช่ชื่อไอเท็ม" in m and "[DNT] Test Currency" in m for t, m in logs), logs


def test_map_tier_and_thaumaturgic_flux_names_are_written_like_before():
    """The game loaded whitelists with "Map (Tier 14/16)" (poe1 unique-map bases) and "Thaumaturgic Flux (Level N)"
    (poe2), and NeverSink's own filter lists them: they must pass the filter and reach the file."""
    hub, base, extra = data("poe1")
    hub = copy.deepcopy(hub)
    hub["items"] += [{"category": "UniqueMap", "name": "Cortex", "base": "Map (Tier 14)"},
                     {"category": "UniqueMap", "name": "Hallowed Ground", "base": "Map (Tier 16)"},
                     {"category": "UniqueMap", "name": "Mao Kun", "base": "Map (Tier 7)"}]       # nobody confirms Tier 7
    m = WlModel("poe1")
    m.set_data(hub, base, set(extra) | {"Map (Tier 14)", "Map (Tier 16)"})
    res = m.build()
    assert not res["bad_names"]
    assert '"Map (Tier 14)"' in res["text"] and '"Map (Tier 16)"' in res["text"]
    assert "Map (Tier 7)" in {n for n, _w in res["skipped"]} and '"Map (Tier 7)"' not in res["text"]
    # poe2: the 20 levels of Thaumaturgic Flux are shown by the default build
    p2 = model("poe2").build()
    assert not p2["bad_names"] and p2["text"].count("Thaumaturgic Flux (Level") >= 20
