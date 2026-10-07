"""Whitelist engine (filter_whitelist): defaults from NeverSink strictness 2, tier resolution, block order."""
import re
from pathlib import Path

import pytest

from poe_price_trade import filter_core, filter_whitelist as w

SAMPLE = Path(__file__).parent / "sample_data"
POE1 = (SAMPLE / "neversink_poe1_s2.filter").read_text(encoding="utf-8")
POE2 = (SAMPLE / "neversink_poe2_s2.filter").read_text(encoding="utf-8")

MINI = """\
Show # $type->currency $tier->t1
	BaseType == "Divine Orb" "Mirror of Kalandra"
	SetFontSize 45
	SetTextColor 255 0 0 255
	PlayAlertSound 6 300

Show # $type->currency $tier->t2
	BaseType == "Chaos Orb" "Divine Orb"
	SetFontSize 40

Show # $type->currency $tier->t4
	BaseType == "Orb of Alchemy"
	SetFontSize 36

Show # $type->currency $tier->t1
	StackSize >= 20
	BaseType == "Scroll of Wisdom"
	SetFontSize 45

Hide # $type->currency $tier->t6
	BaseType == "Scroll of Wisdom" "Orb of Transmutation"

Show # $type->uniques $tier->t1
	Rarity Unique
	BaseType == "Vaal Regalia"

Show # $type->uniques $tier->t3
	Rarity Unique
	BaseType == "Vaal Regalia" "Sapphire Ring"
"""


def hub(*entries):
    return {"currency": [], "items": [{"name": n, "category": c, **({"base": b} if b else {})}
                                      for n, c, b in entries]}


HUB = hub(("Divine Orb", "Currency", None), ("Chaos Orb", "Currency", None), ("Orb of Alchemy", "Currency", None),
          ("Scroll of Wisdom", "Currency", None), ("Brand New Orb", "Currency", None),
          ("Essence of Hatred", "Essence", None),
          ("Kaom's Heart", "UniqueArmour", "Vaal Regalia"), ("Other Regalia", "UniqueArmour", "Vaal Regalia"),
          ("Ring X", "UniqueAccessory", "Sapphire Ring"))


@pytest.mark.parametrize("tag,tier", [("t1", "S"), ("s", "S"), ("t2", "A"), ("t3", "A"), ("a", "A"), ("b", "A"),
                                      ("t4", "B"), ("t8", "B"), ("c", "B"), ("e", "B"), ("t9", None),
                                      ("exhide", None), (None, None)])
def test_tier_of_step(tag, tier):
    assert w.tier_of_step(tag) == tier


def test_default_tiers_first_match_skips_special_blocks():
    d = w.default_tiers(MINI)
    assert d["Divine Orb"] == "S"                 # t1 comes before the t2 that also lists it
    assert d["Chaos Orb"] == "A"
    assert d["Orb of Alchemy"] == "B"
    assert d["Orb of Transmutation"] == "C"        # Hide block
    assert d["Scroll of Wisdom"] == "C"            # the StackSize t1 block is skipped, Hide wins


def test_hub_only_name_defaults_to_b():
    names = w.universe("poe1", HUB, MINI)
    tiers = w.resolve_tiers("poe1", {}, names, w.default_tiers(MINI))
    assert tiers["Brand New Orb"] == "B"
    assert tiers["Divine Orb"] == "S"


def test_precedence_item_over_category_over_default():
    names = w.universe("poe1", HUB, MINI)
    d = w.default_tiers(MINI)
    cfg = {"wl_cat_tier_poe1": {"Currency": "C"}, "wl_item_tier_poe1": {"Chaos Orb": "S"}}
    t = w.resolve_tiers("poe1", cfg, names, d)
    assert t["Chaos Orb"] == "S" and t["Divine Orb"] == "C" and t["Essence of Hatred"] == "B"


def test_unique_base_default_is_highest_and_conflict_reported():
    bd = w.unique_base_defaults(MINI)
    assert bd == {"Vaal Regalia": "S", "Sapphire Ring": "A"}
    ents = w.unique_entries(HUB)
    bt, conf = w.resolve_unique_tiers("poe1", {}, ents, bd)
    assert bt == {"Vaal Regalia": "S", "Sapphire Ring": "A"} and conf == []
    bt, conf = w.resolve_unique_tiers("poe1", {"wl_unique_tier_poe1": {"Other Regalia": "B"}}, ents, bd)
    assert bt["Vaal Regalia"] == "S"               # higher tier wins on the shared base
    assert conf == [("Vaal Regalia", {"Kaom's Heart": "S", "Other Regalia": "B"})]
    bt, _ = w.resolve_unique_tiers("poe1", {"wl_unique_tier_poe1": {"Kaom's Heart": "B", "Other Regalia": "A"}}, ents, bd)
    assert bt["Vaal Regalia"] == "A"


def _blocks(text):
    out, cur = [], None
    for line in text.split("\n"):
        if line in ("Show", "Hide"):
            cur = {"type": line, "lines": [], "comment": ""}
            out.append(cur)
        elif cur is not None and line.strip():
            cur["lines"].append(line.strip())
        elif line.startswith("#") and (cur is None or not cur["lines"]):
            pass
    return out


EXTRA = {"Brand New Orb", "Essence of Hatred"}      # real names the MINI base does not list (trade data)


def build(game="poe1", cfg=None, base=MINI, hubd=HUB, quest="", sounds=None, extra=EXTRA):
    return w.build_whitelist_filter(game, cfg or {}, base, hubd, quest, sounds, extra)


def test_file_ends_with_hide_and_shows_only_selection():
    res = build()
    blocks = _blocks(res["text"])
    assert blocks[-1] == {"type": "Hide", "lines": [], "comment": ""}
    shown = set()
    for b in blocks[:-1]:
        if b["type"] == "Hide":
            continue
        for l in b["lines"]:
            if l.startswith("BaseType =="):
                shown |= set(re.findall(r'"([^"]*)"', l))
    # Scroll of Wisdom (C) and Transmutation are not shown; others are
    assert "Scroll of Wisdom" not in shown and "Orb of Transmutation" not in shown
    assert {"Divine Orb", "Chaos Orb", "Orb of Alchemy", "Brand New Orb", "Essence of Hatred"} <= shown
    assert shown <= {"Divine Orb", "Chaos Orb", "Orb of Alchemy", "Brand New Orb", "Essence of Hatred",
                     "Mirror of Kalandra", "Vaal Regalia", "Sapphire Ring", "Gold"}


def test_one_block_per_tier_in_order():
    text = build()["text"]
    assert text.index("# tier S") < text.index("# uniques - tier S") < text.index("# tier A") < text.index("# tier B")
    assert text.count("\n# tier S\n") == 1


def test_quest_block_first_and_never_hidden():
    q = filter_core.build_quest_blocks("poe1", {"text": [1, 2, 3, 255]})
    text = build(quest=q)["text"]
    assert text.index("quest items") < text.index("# uniques")
    assert 'Class == "Quest Items"' in text


def test_unique_block_before_tablet_and_tablet_excludes_unique():
    text = build("poe2")["text"]
    assert text.index("# uniques") < text.index("# tablets")
    i = text.index("# tablets")
    seg = text[i:text.index("\n\n", i)]
    assert 'Class == "Tablet"' in seg and "Rarity < Unique" in seg
    assert "tablets" not in build("poe1")["text"]


def test_unique_block_uses_base_and_rarity():
    text = build()["text"]
    seg = text[text.index("# uniques - tier S"):]
    seg = seg[:seg.index("\n\n")]
    assert "Rarity Unique" in seg and 'BaseType == "Vaal Regalia"' in seg
    assert "Kaom's Heart" not in text                # a filter cannot match unique names


def test_gold_both_ways():
    plain = build(cfg={})["text"]
    g = plain[plain.index("# gold"):]
    g = g[:g.index("\n\n")]
    assert 'BaseType == "Gold"' in g and "SetFontSize" not in g and "StackSize" not in g
    styled = build(cfg={"whitelist_gold": True, "whitelist_gold_min": 500})["text"]
    g = styled[styled.index("# gold"):]
    g = g[:g.index("\n\n")]
    assert "StackSize >= 500" in g and "SetFontSize" in g


def test_waystone_and_map_and_or_special_and_unticked():
    off = build("poe2")["text"]
    seg = off[off.index("# waystones"):]
    seg = seg[:seg.index("\n\n")]
    assert "WaystoneTier" not in seg and "SetFontSize" not in seg
    on = build("poe2", {"wl_map_on": True, "wl_map_tier_min": 8, "wl_map_rarity_min": "Rare"})["text"]
    seg = on[on.index("# waystones"):]
    seg = seg[:seg.index("\n\n")]
    assert "WaystoneTier >= 8" in seg and "Rarity >= Rare" in seg and "SetFontSize" in seg    # both required
    p1 = build("poe1", {"wl_map_on": True, "wl_map_tier_min": 12, "wl_map_rarity_min": "Magic"}, base=POE1)["text"]
    assert "MapTier >= 12" in p1 and "Rarity >= Magic" in p1
    for special in ("Rarity Unique", "BlightedMap True", "HasInfluence", "BaseType == \"Valdo Map\""):
        assert special in p1
    # each special block carries the map style
    assert p1.count('Class == "Maps"') >= 6


def test_map_tier_clamped():
    t = build("poe1", {"wl_map_on": True, "wl_map_tier_min": 99})["text"]
    assert "MapTier >= 16" in t


def test_gems_and_typed_names():
    cfg = {"whitelist_gem_uncut_poe2": {"Uncut Skill Gem": 18}, "whitelist_gem_tier": "A",
           "whitelist_custom_poe2": [{"name": "Rakiata", "rarities": ["Magic"], "tier": "S"},
                                     {"name": "Hidden", "rarities": ["Rare"], "tier": "C"}]}
    text = build("poe2", cfg)["text"]
    assert 'BaseType == "Uncut Skill Gem"' in text and "GemLevel >= 18" in text
    seg = text[text.index("# typed names"):]
    seg = seg[:seg.index("\n\n")]
    assert 'BaseType "Rakiata"' in seg and "Rarity Magic" in seg and "==" not in seg.split("BaseType")[1].split("\n")[0]
    assert "Hidden" not in text


def test_sound_per_tier_game_and_file():
    cfg = {"wl_tier_style": {"S": {"sound": {"kind": "file", "file": "a.mp3", "volume": 200}},
                             "A": {"sound": {"kind": "game", "id": 5, "volume": 100}},
                             "G": {"sound": {"kind": "file", "file": "g.ogg"}}}}
    assert w.sound_requests(cfg) == {"S": "a.mp3", "A": None, "B": None, "G": "g.ogg", "Tablet": None, "Map": None}
    text = build(cfg=cfg, sounds={"S": "a.mp3"})["text"]
    seg = text[text.index("# tier S\n"):]
    seg = seg[:seg.index("\n\n")]
    assert 'CustomAlertSoundOptional "a.mp3" 200' in seg
    seg = text[text.index("# tier A\n"):]
    seg = seg[:seg.index("\n\n")]
    assert "PlayAlertSound 5 100" in seg


def test_tier_default_look_copies_neversink_steps():
    lines = w.default_tier_lines(MINI)
    assert "    PlayAlertSound 6 300" in lines["S"] and "    SetFontSize 40" in lines["A"]


@pytest.mark.parametrize("game,base", [("poe1", POE1), ("poe2", POE2)], ids=["poe1", "poe2"])
def test_real_base_filters(game, base):
    d = w.default_tiers(base)
    assert {"S", "A", "B", "C"} <= set(d.values())
    res = build(game, base=base, hubd=hub(("Divine Orb", "Currency", None)), extra=None)
    assert res["tiers"]["Divine Orb"] == "S"
    assert res["text"].rstrip().endswith("Hide")


def test_core_wiring_v2():
    cfg = {"whitelist_enabled": True, "wl_v2": True}
    assert filter_core.plan_fetch(cfg, "poe1") == {"mode": "whitelist", "hub": True, "neversink": True}
    assert filter_core.build_filter_text(cfg, "poe1", hub_data=HUB, base_text=None) is None
    res = filter_core.build_filter_text(cfg, "poe1", hub_data=HUB, base_text=MINI)
    assert res["mode"] == "whitelist" and res["base_text"] is None and res["count"] > 0
    # legacy config keeps the old engine
    assert filter_core.plan_fetch({"whitelist_enabled": True}, "poe1")["neversink"] is False


def test_default_sound_kept_when_user_style_has_no_sound():
    cfg = {"wl_tier_style": {"S": {"text": [1, 2, 3, 255]}}}
    text = build(cfg=cfg)["text"]
    seg = text[text.index("# tier S\n"):]
    seg = seg[:seg.index("\n\n")]
    assert "SetTextColor 1 2 3 255" in seg and "PlayAlertSound 6 300" in seg and "SetFontSize 45" in seg


def test_user_file_sound_added_next_to_default_fallback_and_game_sound_replaces():
    cfg = {"wl_tier_style": {"S": {"sound": {"kind": "file", "file": "a.mp3", "volume": 200}},
                             "A": {"sound": {"kind": "game", "id": 9, "volume": 100}}}}
    text = build(cfg=cfg, sounds={"S": "a.mp3"})["text"]
    seg = text[text.index("# tier S\n"):]
    seg = seg[:seg.index("\n\n")]
    assert "PlayAlertSound 6 300" in seg and 'CustomAlertSoundOptional "a.mp3" 200' in seg
    seg = text[text.index("# tier A\n"):]
    seg = seg[:seg.index("\n\n")]
    assert "PlayAlertSound 9 100" in seg and "PlayAlertSound 1" not in seg


def test_special_classes_list_and_hidden_names_precede_them():
    assert {"Blueprints", "Contracts", "Heist Targets", "Corpses", "Wombgifts", "Chart", "Pieces"} <= set(w.SPECIAL_CLASSES["poe1"])
    assert "Map Fragments" not in w.SPECIAL_CLASSES["poe1"] and "Incubators" not in w.SPECIAL_CLASSES["poe2"]
    text = build()["text"]
    assert text.index("# tier C") < text.index("special classes")
    seg = text[text.index("# tier C"):]
    seg = seg[:seg.index("\n\n")]
    assert "Orb of Transmutation" in seg and seg.splitlines()[1] == "Hide"


def test_substring_basetype_lines_are_not_names():
    base = MINI + """
Show # $type->currency $tier->t3
	BaseType "Ducat"
	SetFontSize 40
"""
    assert "Ducat" not in w.default_tiers(base) and "Ducat" not in w.known_names(base)
    assert "Ducat" not in build(base=base)["text"]


def test_unknown_names_are_skipped_and_reported():
    h = hub(*[(n, c, b) for n, c, b in [("Divine Orb", "Currency", None), ("Fake Orb", "Currency", None),
                                        ("Ring Z", "UniqueAccessory", "Fake Ring")]])
    cfg = {"whitelist_gem_names_poe1": ["Fake Gem"], "whitelist_gem_uncut_poe2": {}}
    res = build(cfg=cfg, hubd=h, extra=None)
    assert "Fake" not in res["text"]
    assert {n for n, _ in res["skipped"]} == {"Fake Orb", "Fake Ring", "Fake Gem"}
    res = build(cfg=cfg, hubd=h, extra={"Fake Orb"})
    assert "Fake Orb" in res["text"] and {n for n, _ in res["skipped"]} == {"Fake Ring", "Fake Gem"}


def _snapshot(name):
    import gzip
    import json
    with gzip.open(SAMPLE / name, "rt", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.mark.parametrize("game,base", [("poe1", POE1), ("poe2", POE2)], ids=["poe1", "poe2"])
def test_everything_on_with_real_hub_writes_only_real_names(game, base):
    """Real hub payload + real NeverSink base, every feature on: each name in a `BaseType ==` line is a
    name NeverSink uses or GGG's item list has (the game rejects the whole filter on any other)."""
    hubd = {"currency": [], "items": _snapshot(f"hub_{game}.json.gz")["items"]}
    trade = set(_snapshot(f"trade_names_{game}.json.gz"))
    cfg = {"whitelist_gold": True, "whitelist_gold_min": 100, "wl_map_on": True, "wl_map_tier_min": 10,
           "wl_map_rarity_min": "Magic", f"whitelist_custom_{game}": [{"name": "x", "rarities": ["Rare"], "tier": "B"}]}
    if game == "poe2":
        cfg["whitelist_gem_uncut_poe2"] = {"Uncut Skill Gem": 10, "Uncut Spirit Gem": 5, "Uncut Support Gem": 3}
    res = w.build_whitelist_filter(game, cfg, base, hubd, "", None, trade)
    valid = w.known_names(base) | trade | {"Gold"} | set(w.filter_gen.WHITELIST_GEM_UNCUT[game])
    written = set()
    for line in res["text"].splitlines():
        m = w._EXACT_LINE.match(line)
        if m:
            written |= set(re.findall(r'"([^"]*)"', m.group(1)))
    assert written and not (written - valid), sorted(written - valid)[:10]
    assert "Ducat" not in written and "Catalyst" not in written
    # the only hub "bases" that are not names: poe1 unique maps ("Map (Tier 10)"; the Map block's own
    # `Rarity Unique` line already shows them)
    assert all(n.startswith("Map (Tier") for n, _ in res["skipped"]), res["skipped"][:10]
    # without GGG's list only NeverSink-backed names are written, and the rest is reported, not written
    res2 = w.build_whitelist_filter(game, cfg, base, hubd, "", None, None)
    written2 = set()
    for line in res2["text"].splitlines():
        m = w._EXACT_LINE.match(line)
        if m:
            written2 |= set(re.findall(r'"([^"]*)"', m.group(1)))
    assert written2 <= w.known_names(base) | {"Gold"} | set(w.filter_gen.WHITELIST_GEM_UNCUT[game])


def test_tier_sound_is_shared_between_both_tabs():
    cfg = {"sound_s": "ragnarok.mp3", "style_q": None}
    copy = lambda sm: {k: f"copied-{v}" for k, v in sm.items() if v}
    tier = filter_core.build_filter_text({**cfg, "whitelist_enabled": False}, "poe1", base_text=POE1, base_tag="t",
                                         copy_sounds_fn=copy)
    wl = filter_core.build_filter_text({**cfg, "whitelist_enabled": True, "wl_v2": True}, "poe1", hub_data=HUB,
                                       base_text=POE1, copy_sounds_fn=copy, extra_names=EXTRA)
    assert 'CustomAlertSoundOptional "copied-ragnarok.mp3"' in tier["base_text"]
    seg = wl["generated_section"]
    seg = seg[seg.index("# tier S\n"):]
    seg = seg[:seg.index("\n\n")]
    assert 'CustomAlertSoundOptional "copied-ragnarok.mp3"' in seg and "PlayAlertSound 6" in seg
    assert w.sound_requests({"sound_a": "a.mp3", "wl_tier_style": {"A": {"sound": {"kind": "file", "file": "own.mp3"}}}})["A"] == "a.mp3"


def _svc_cfg(tmp_path, fg):
    from types import SimpleNamespace
    return SimpleNamespace(get=lambda k, d=None: dict(fg, game_dir_poe2=str(tmp_path / "game")) if k == "filter_gen" else d,
                           app_dir=lambda: tmp_path / "app")


@pytest.mark.parametrize("v2", [False, True], ids=["legacy-whitelist", "wl_v2"])
def test_shared_sound_end_to_end_through_filter_service(tmp_path, v2):
    """NeverSink tab, then Whitelist tab, one sound set once: both files name the same sound file and
    the game folder holds exactly one copy of it (no "-2", no second copy)."""
    from unittest import mock
    from poe_price_trade import filter_service
    src = tmp_path / "src" / "ragnarok.mp3"
    src.parent.mkdir()
    src.write_bytes(b"sound")
    fg = {"sound_s": str(src), "whitelist_custom_poe2": ["Divine Orb"], "whitelist_gold": True, "wl_v2": v2}
    cfg = _svc_cfg(tmp_path, fg)
    with mock.patch.object(filter_service.neversink_source, "fetch_base_filter", return_value=(POE2, "t")), \
         mock.patch.object(filter_service.hub_client, "get_prices", return_value=hub(("Divine Orb", "Currency", None))), \
         mock.patch.object(filter_service.trade_names, "get_names", return_value=set()):
        tier = filter_service.generate_filter(cfg, "poe2", "p", mode="tier")
        wl = filter_service.generate_filter(cfg, "poe2", "p", mode="whitelist")
    t_text, w_text = tier["path"].read_text(encoding="utf-8"), wl["path"].read_text(encoding="utf-8")
    line = 'CustomAlertSoundOptional "ragnarok.mp3" 300'
    assert line in t_text and line in w_text
    assert [p.name for p in (tmp_path / "game").glob("*.mp3")] == ["ragnarok.mp3"]
    if v2:                                  # Divine Orb (S) is first matched by the tier S block, which has the sound
        seg = w_text[w_text.index("# tier S\n"):]
        assert line in seg[:seg.index("\n\n")] and '"Divine Orb"' in seg[:seg.index("\n\n")]
    else:
        assert "ragnarok-2" not in w_text


# ---------------------------------------------------------------------------
# Equipment category
# ---------------------------------------------------------------------------

GEAR = """\
Show # $type->6l $tier->any
	LinkedSockets 6
	Rarity Normal Magic Rare
	SetFontSize 29
	PlayAlertSound 4 300

Show # $type->rareid $tier->any
	Identified True
	Rarity Rare
	Class == "Rings" "Amulets"
	HasExplicitMod "Veiled"
	SetFontSize 35
	DisableDropSound True

Show # $type->decorators->rareeg $tier->any
	Rarity Rare
	Class == "Rings"
	SetFontSize 30
	Continue

Show # $type->leveling->rare->remaining $tier->any
	Rarity Rare
	AreaLevel <= 16
	SetFontSize 32

Hide # $type->hidelayer $tier->any
	Class == "Rings"

Show # $type->jewels->generic $tier->any
	Class == "Jewel"
	Rarity Rare
	SetFontSize 38

Show # $type->special->alwaysshow $tier->any
	AlwaysShow True
	Rarity Normal Magic Rare
	Class == "Rings"
	PlayAlertSound 3 300
"""


def _gear_segments(text):
    return [b for b in text.split("\n\n") if b.lstrip().startswith("# gear:")]


def test_gear_blocks_keep_every_condition_skip_decorators_and_hides():
    got = w.gear_blocks("poe1", MINI + GEAR)
    types = [t for _g, t, _c in got]
    assert types == ["6l", "rareid", "leveling->rare->remaining", "jewels->generic"]      # file order, no Continue / Hide
    conds = {t: " | ".join(c.strip() for c in cs) for _g, t, cs in got}
    assert "AreaLevel <= 16" in conds["leveling->rare->remaining"]                       # AreaLevel kept
    assert "HasExplicitMod" in conds["rareid"] and "SetFontSize" not in conds["rareid"]
    assert "DisableDropSound" not in conds["rareid"] and "PlayAlertSound" not in conds["6l"]


def test_gear_default_tiers_links_a_rest_b_and_style_replaced():
    text = build(base=MINI + GEAR)["text"]
    segs = {s.splitlines()[0]: s for s in _gear_segments(text)}
    links = [s for k, s in segs.items() if "6-link" in k][0]
    assert "tier A (6l)" in links and "LinkedSockets 6" in links
    for line in w.default_tier_lines(MINI + GEAR)["A"]:          # A's style (NeverSink's own second step) ...
        assert line in links
    assert "SetFontSize 29" not in links and "PlayAlertSound 4" not in links       # ... not the block's own look
    others = [s for k, s in segs.items() if "6-link" not in k]
    assert others and all(" - tier B (" in s.splitlines()[0] for s in others)


def test_gear_precedence_group_over_category_over_default():
    base = MINI + GEAR
    assert w.gear_tiers("poe1", {})["links"] == "A" and w.gear_tiers("poe1", {})["jewel"] == "B"
    cat = {"wl_cat_tier_poe1": {w.GEAR_CATEGORY: "S"}}
    t = w.gear_tiers("poe1", cat)
    assert t["links"] == "S" and t["jewel"] == "S"                                        # whole category beats defaults
    t = w.gear_tiers("poe1", {**cat, "wl_gear_tier_poe1": {"jewel": "C"}})
    assert t["jewel"] == "C" and t["links"] == "S"                                        # a group beats the whole category
    text = build(cfg=cat, base=base)["text"]
    assert all(" - tier S (" in s.splitlines()[0] for s in _gear_segments(text))


def test_gear_group_c_is_a_hide_copy_of_every_block():
    cfg = {"wl_cat_tier_poe1": {w.GEAR_CATEGORY: "C"}}
    text = build(cfg=cfg, base=MINI + GEAR)["text"]
    segs = _gear_segments(text)
    assert len(segs) == len(w.gear_blocks("poe1", MINI + GEAR))
    assert all(s.splitlines()[1] == "Hide" for s in segs)            # NeverSink's first-match order is kept
    assert any("LinkedSockets 6" in s for s in segs) and any("AreaLevel <= 16" in s for s in segs)
    assert "SetFontSize" not in "".join(segs)


def test_block_order_q_s_unique_tablet_map_gold_a_gem_b_hide_c_classes_typed_gear_hide():
    q = filter_core.build_quest_blocks("poe2", {"text": [1, 2, 3, 255]})
    cfg = {"whitelist_gem_uncut_poe2": {"Uncut Skill Gem": 3}, "wl_cat_tier_poe2": {"Essence": "C"},
           "whitelist_gold": True, "wl_map_on": True,
           "whitelist_custom_poe2": [{"name": "Ring", "rarities": ["Rare"], "tier": "A"}]}
    text = build("poe2", cfg, base=MINI + GEAR, quest=q)["text"]
    keys = ("# quest items", "# tier S" + chr(10), "# uniques", "# tablets", "# waystones", "# gold", "# tier A" + chr(10),
            "# uncut gem", "# tier B" + chr(10), "# tier C (", "special classes", "# typed names", "# gear:",
            "# hide everything else")
    pos = [text.index(k) for k in keys]
    assert pos == sorted(pos), dict(zip(keys, pos))
    assert text.rstrip().endswith("Hide")


def _blocks_matching(text, **item):
    """The first Show/Hide block of the generated filter that an item would match - a small evaluator for
    the conditions the engine writes (Class, BaseType == / contains, Rarity, AreaLevel, StackSize)."""
    cur = None
    chunks = []
    for line in text.splitlines():
        if line in ("Show", "Hide"):
            cur = [line]
            chunks.append(cur)
        elif cur is not None and line.strip() and not line.startswith("#"):
            cur.append(line.strip())
    rar_order = ["Normal", "Magic", "Rare", "Unique"]
    for chunk in chunks:
        ok = True
        for cond in chunk[1:]:
            kw, _, rest = cond.partition(" ")
            names = re.findall(r'"([^"]*)"', rest)
            if kw == "Class":
                ok = ok and item.get("cls") in names
            elif kw == "BaseType":
                exact = rest.startswith("==")
                ok = ok and any((item["base"] == n) if exact else (n.lower() in item["base"].lower()) for n in names)
            elif kw == "Rarity":
                ops = rest.split()
                if ops and ops[0] in (">=", "<=", "<", ">"):
                    a, b = rar_order.index(item["rarity"]), rar_order.index(ops[1])
                    ok = ok and {">=": a >= b, "<=": a <= b, "<": a < b, ">": a > b}[ops[0]]
                else:
                    ok = ok and item["rarity"] in ops
            elif kw == "AreaLevel":
                op, val = rest.split()
                a, b = item.get("area", 70), int(val)
                ok = ok and {">=": a >= b, "<=": a <= b, "<": a < b, ">": a > b, "==": a == b}[op]
        if ok:
            return chunk
    return None


def test_currency_keeps_its_tier_style_in_low_level_zones_and_typed_names_beat_gear():
    base = MINI + """
Show # $type->leveling->firstlevels $tier->any
	Rarity Normal
	AreaLevel <= 4
	SetFontSize 31

Show # $type->rareid $tier->any
	Rarity Rare
	Class == "Rings"
	SetFontSize 35
"""
    cfg = {"whitelist_custom_poe1": [{"name": "Coral", "rarities": ["Rare"], "tier": "S"}]}
    text = build(cfg=cfg, base=base)["text"]
    # Divine Orb is S: a Normal item in an act-1 zone must still land on the S block, not the early-level gear block
    hit = _blocks_matching(text, base="Divine Orb", cls="Stackable Currency", rarity="Normal", area=2)
    assert hit and hit[0] == "Show" and f'BaseType == "Divine Orb"' in " ".join(hit[1:])
    assert w.default_tier_lines(base)["S"][0].strip() in hit
    assert "SetFontSize 31" not in " ".join(hit)
    # a name typed by the player beats a gear block that would also take the item
    hit = _blocks_matching(text, base="Coral Ring", cls="Rings", rarity="Rare", area=70)
    assert hit and 'BaseType "Coral"' in hit and "SetFontSize 35" not in " ".join(hit)
    # without a typed name that Rare ring is the gear block's
    hit = _blocks_matching(build(base=base)["text"], base="Coral Ring", cls="Rings", rarity="Rare", area=70)
    assert hit and hit[0] == "Show" and 'Class == "Rings"' in hit
    # unselected Normal item early on: the early-level gear block does take it (B), never the S block
    hit = _blocks_matching(text, base="Iron Sword", cls="One Hand Swords", rarity="Normal", area=2)
    assert hit and "Rarity Normal" in hit


@pytest.mark.parametrize("game,base,hub_name", [("poe1", POE1, "Divine Orb"), ("poe2", POE2, "Divine Orb")], ids=["poe1", "poe2"])
def test_real_filters_tier_names_are_not_gear_base_types(game, base, hub_name):
    """Names the engine tiers S / A / B vs the BaseType names of the copied gear blocks (the S/A/B blocks come
    first, so an overlap would be harmless - but it would mean a currency was taken for gear)."""
    hubd = {"currency": [], "items": _snapshot(f"hub_{game}.json.gz")["items"]}
    res = w.build_whitelist_filter(game, {}, base, hubd, "", None, set(_snapshot(f"trade_names_{game}.json.gz")))
    shown = {n for n, t in res["tiers"].items() if t in "SAB"}
    gear = set()
    for _g, _t, conds in w.gear_blocks(game, base):
        for c in conds:
            if c.strip().startswith("BaseType"):
                gear |= set(re.findall(r'"([^"]*)"', c))
    overlap = shown & gear
    assert not any(n.endswith(("Orb", "Scrap", "Whetstone")) for n in overlap), sorted(overlap)
    print(game, "overlap:", sorted(overlap))


def test_poe2_alwaysshow_group_only_in_poe2_and_defaults_to_b():
    p2 = build("poe2", base=MINI + GEAR)["text"]
    seg = [s for s in _gear_segments(p2) if "AlwaysShow True" in s]
    assert len(seg) == 1 and "ของที่เกมบังคับโชว์" in seg[0] and " - tier B (" in seg[0]
    assert "Rarity Normal Magic Rare" in seg[0] and "PlayAlertSound 3" not in seg[0]
    assert "AlwaysShow" not in build("poe1", base=MINI + GEAR)["text"]
    assert "alwaysshow" in dict((g, 1) for g, _n, _d in w.GEAR_GROUPS["poe2"])
    assert "alwaysshow" not in [g for g, _n, _d in w.GEAR_GROUPS["poe1"]]


@pytest.mark.parametrize("game,base", [("poe1", POE1), ("poe2", POE2)], ids=["poe1", "poe2"])
def test_gear_real_filters_every_group_has_blocks_and_specials_are_not_gear(game, base):
    blocks = w.gear_blocks(game, base)
    found = {g for g, _t, _c in blocks}
    assert found == {g for g, _n, _d in w.GEAR_GROUPS[game]}
    assert all(not any(c.strip() == "Continue" for c in cs) for _g, _t, cs in blocks)
    classes = set()
    for _g, _t, cs in blocks:
        for c in cs:
            if c.strip().startswith("Class"):
                classes |= set(re.findall(r'"([^"]*)"', c))
    assert not classes & set(w.SPECIAL_CLASSES[game]), classes & set(w.SPECIAL_CLASSES[game])
    assert "Talismans" not in w.SPECIAL_CLASSES["poe2"]
    # the AreaLevel conditions of the story blocks are kept as written
    assert any("AreaLevel" in c for g, _t, cs in blocks if g == "story" for c in cs)
    res = build(game, base=base, hubd=hub(("Divine Orb", "Currency", None)), extra=None)
    assert res["gear_tiers"]["story"] == "B" and len(_gear_segments(res["text"])) == len(blocks)


def test_c_name_stays_hidden_before_special_classes_and_tablets_keep_the_tablet_style():
    hubd = hub(("Essence of Hatred", "Essence", None), ("Ritual Tablet", "Fragment", None),
               ("Tablet Unique X", "UniqueTablet", "Ritual Tablet"))
    cfg = {"wl_cat_tier_poe2": {"Essence": "C", "Fragment": "A"}}
    text = build("poe2", cfg, base=MINI, hubd=hubd, extra={"Essence of Hatred", "Ritual Tablet"})["text"]
    # a C name that also sits in a special class is hidden, the class block never gets it
    hit = _blocks_matching(text, base="Essence of Hatred", cls="Vault Keys", rarity="Normal")
    assert hit and hit[0] == "Hide"
    # a tablet named in tier A: Normal-Rare ones take the Tablet block (before the A names), Unique ones the unique block
    hit = _blocks_matching(text, base="Ritual Tablet", cls="Tablet", rarity="Rare")
    assert hit and 'Class == "Tablet"' in hit
    hit = _blocks_matching(text, base="Ritual Tablet", cls="Tablet", rarity="Unique")
    assert hit and "Rarity Unique" in hit and 'BaseType == "Ritual Tablet"' in hit


TABLETS = ("Ritual Tablet", "Expedition Tablet", "Abyss Tablet", "Breach Tablet", "Delirium Tablet")


def _tablet_text(extra_cfg=None):
    hubd = hub(*[(n, "Fragment", None) for n in TABLETS], ("Ritual Unique", "UniqueTablet", "Ritual Tablet"))
    cfg = {"wl_item_tier_poe2": {"Ritual Tablet": "S", "Expedition Tablet": "A", "Abyss Tablet": "B", "Breach Tablet": "C"},
           **(extra_cfg or {})}
    return build("poe2", cfg, base=MINI, hubd=hubd, extra=set(TABLETS))


def test_tablet_default_is_tablet_block_and_only_its_own_tier_moves_it():
    names = {n: "Fragment" for n in TABLETS}
    tiers = w.resolve_tiers("poe2", {"wl_cat_tier_poe2": {"Fragment": "C"}}, names, {n: "S" for n in TABLETS})
    assert set(tiers.values()) == {w.TABLET_DEFAULT}          # neither the category tier nor NeverSink's ladder moves them
    tiers = w.resolve_tiers("poe2", {"wl_item_tier_poe2": {"Abyss Tablet": "A"}}, names, {})
    assert tiers["Abyss Tablet"] == "A" and tiers["Ritual Tablet"] == w.TABLET_DEFAULT
    assert w.resolve_tiers("poe1", {}, {"Abyss Tablet": "Fragment"}, {})["Abyss Tablet"] == "B"     # poe2 only


def test_tablet_set_to_s_a_b_c_follows_the_tier_and_the_rest_keep_the_tablet_style():
    res = _tablet_text()
    text = res["text"]
    tab_style = filter_style_lines("Tablet")
    ev = lambda base, rarity="Rare": _blocks_matching(text, base=base, cls="Tablet", rarity=rarity)
    s_hit, a_hit, b_hit = ev("Ritual Tablet"), ev("Expedition Tablet"), ev("Abyss Tablet")
    for hit, tier in ((s_hit, "S"), (a_hit, "A"), (b_hit, "B")):
        assert hit[0] == "Show" and "Class == " + '"Tablet"' not in hit      # its own block, not the Tablet block
        for line in w.default_tier_lines(MINI)[tier]:
            assert line.strip() in hit, (tier, line)
    c_hit = ev("Breach Tablet")
    assert c_hit == ["Hide", 'BaseType == "Breach Tablet"']                    # hidden by the player
    rest = ev("Delirium Tablet")
    assert rest[0] == "Show" and 'Class == "Tablet"' in rest and "Rarity < Unique" in rest
    for line in tab_style:
        assert line in rest
    # a tablet nobody listed at all (new in the game) is shown the same way
    assert ev("Brand New Tablet") == rest
    # a unique tablet still goes to the Unique block, whatever tier its base has as a plain tablet
    u = ev("Ritual Tablet", rarity="Unique")
    assert u[0] == "Show" and "Rarity Unique" in u
    assert res["report"][w.TABLET_DEFAULT] == 1                                # Delirium (default)
    # each tablet is written once: the S/A/B/C ones are not also in the ordinary tier blocks
    assert text.count('"Abyss Tablet"') == 1 and text.count('"Expedition Tablet"') == 1


def filter_style_lines(key):
    return [l.strip() for l in w.filter_style.style_lines(w.filter_style.DEFAULT_STYLES[key])]
