"""Tests for filter_gen.py — fixtures shaped like the live hub payload
(category/base/chaos_value fields), same unittest.mock.patch style as
test_hub_client.py where applicable."""
from datetime import datetime, timedelta, timezone

import pytest

from poe_price_trade import filter_gen


def _rules(**overrides):
    r = {
        "tiers": [
            {"name": "S", "min_chaos": 150, "border": "255 0 0", "text": "255 0 0",
             "bg": "255 255 255", "size": 45, "sound": "6 300", "beam": "Red", "icon": "0 Red Star"},
            {"name": "A", "min_chaos": 20, "border": "255 170 0", "text": "255 170 0",
             "bg": "0 0 0", "size": 45, "sound": "1 300", "beam": "Yellow", "icon": "1 Yellow Circle"},
            {"name": "B", "min_chaos": 5, "border": "0 200 255", "text": "0 200 255",
             "bg": "0 0 0", "size": 40, "sound": None, "beam": None, "icon": "2 Blue Circle"},
            {"name": "C", "min_chaos": 1, "border": "150 150 150", "text": "200 200 200",
             "bg": "0 0 0", "size": 35, "sound": None, "beam": None, "icon": None},
        ],
        "sound_volume": 300,
    }
    r.update(overrides)
    return r


def _hub_data(**overrides):
    data = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "league": "Test League",
        "currency": [
            {"category": "Currency", "name": "Divine Orb", "base": None, "chaos_value": 200.0},
            {"category": "Currency", "name": "Chaos Orb", "base": None, "chaos_value": 1.0},
            {"category": "Fragment", "name": "Sacrifice Fragment", "base": None, "chaos_value": 25.0},
            {"category": "Essence", "name": "Deafening Essence of Greed", "base": None, "chaos_value": 0.1},
            {"category": "UncutGem", "name": "Uncut Skill Gem (Level 20)", "base": None, "chaos_value": 999.0},
            {"category": "SkillGem", "name": "Uncut Spirit Gem (Level 1)", "base": None, "chaos_value": 0.01},
        ],
        "items": [
            {"category": "UniqueWeapon", "name": "Widowmaker", "base": "Royal Axe", "chaos_value": 300.0},
            {"category": "UniqueArmour", "name": "Kaom's Heart", "base": "Glorious Plate", "chaos_value": 10.0},
            {"category": "BaseType", "name": "Vaal Regalia", "base": "Vaal Regalia", "chaos_value": 50000.0},
        ],
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# bucket_currency
# ---------------------------------------------------------------------------

def test_bucket_currency_tiers_by_chaos_uniformly_across_categories():
    tiers = filter_gen.bucket_currency(_hub_data(), _rules())
    assert tiers["S"] == ["Divine Orb"]
    assert tiers["A"] == ["Sacrifice Fragment"]
    assert tiers["C"] == ["Chaos Orb"]
    # below every tier's threshold (0.1c < C's min_chaos=1) — simply absent,
    # not routed anywhere: currency below all tiers is left 100% untouched,
    # not dimmed (see bucket_currency docstring, 2026-07-27 fix)
    all_names = {n for names in tiers.values() for n in names}
    assert "Deafening Essence of Greed" not in all_names


def test_bucket_currency_excludes_gem_categories():
    tiers = filter_gen.bucket_currency(_hub_data(), _rules())
    all_names = {n for names in tiers.values() for n in names}
    assert "Uncut Skill Gem (Level 20)" not in all_names
    assert "Uncut Spirit Gem (Level 1)" not in all_names


def test_bucket_currency_dedups_by_max_chaos_value():
    data = _hub_data(currency=[
        {"category": "Currency", "name": "Orb of X", "base": None, "chaos_value": 2.0},
        {"category": "Currency", "name": "Orb of X", "base": None, "chaos_value": 30.0},
    ])
    tiers = filter_gen.bucket_currency(data, _rules())
    assert tiers["A"] == ["Orb of X"]


def test_bucket_currency_below_lowest_tier_is_left_untouched_not_dimmed():
    """No fallback bucket any more (pre-2026-07-27 behavior dumped anything
    between hide_below and the lowest tier's own threshold into tier C, or
    into a self-generated "dim" block below that) — a name that doesn't
    clearly qualify for a real tier is simply absent from the result,
    100% left wherever NeverSink's own base filter already has it."""
    data = _hub_data(currency=[
        {"category": "Currency", "name": "Odd Orb", "base": None, "chaos_value": 0.7},
    ])
    tiers = filter_gen.bucket_currency(data, _rules())
    assert not any(names for names in tiers.values())


# ---------------------------------------------------------------------------
# bucket_uniques
# ---------------------------------------------------------------------------

def test_bucket_uniques_only_unique_categories_keyed_by_base():
    tiers = filter_gen.bucket_uniques(_hub_data(), _rules())
    assert tiers["S"] == ["Royal Axe"]
    assert tiers["B"] == ["Glorious Plate"]
    all_bases = {b for names in tiers.values() for b in names}
    assert "Vaal Regalia" not in all_bases


def test_bucket_uniques_dedups_by_max_chaos_per_basetype():
    data = _hub_data(items=[
        {"category": "UniqueWeapon", "name": "Foo", "base": "Rusty Sword", "chaos_value": 3.0},
        {"category": "UniqueWeapon", "name": "Bar", "base": "Rusty Sword", "chaos_value": 25.0},
    ])
    tiers = filter_gen.bucket_uniques(data, _rules())
    assert tiers["A"] == ["Rusty Sword"]


def test_bucket_uniques_skips_entries_without_base():
    data = _hub_data(items=[
        {"category": "UniqueWeapon", "name": "Foo", "base": None, "chaos_value": 300.0},
    ])
    tiers = filter_gen.bucket_uniques(data, _rules())
    assert not any(tiers.values())


# ---------------------------------------------------------------------------
# tier_of — min_divine_pct self-scaling (task 4: early-league-aware tiering)
# ---------------------------------------------------------------------------

def _pct_tiers_cfg():
    return [
        {"name": "S", "min_divine_pct": 0.20, "min_chaos": 150},
        {"name": "A", "min_divine_pct": 0.05, "min_chaos": 20},
        {"name": "B", "min_divine_pct": 0.01, "min_chaos": 5},
        {"name": "C", "min_divine_pct": 0.002, "min_chaos": 1},
    ]


def test_tier_of_uses_divine_pct_when_divine_chaos_known():
    tiers_cfg = _pct_tiers_cfg()
    # divine=40c (cheap, day-1-like economy) — 30c is 75% of divine, well past S's 20%
    assert filter_gen.tier_of(30.0, tiers_cfg, divine_chaos=40.0)["name"] == "S"


def test_tier_of_absolute_min_chaos_would_have_missed_the_same_item():
    # sanity check this really is the "wait for 150c" problem pct scaling fixes
    tiers_cfg = _pct_tiers_cfg()
    tier = filter_gen.tier_of(30.0, tiers_cfg, divine_chaos=None)
    assert tier is None or tier["name"] != "S"


def test_tier_of_scales_up_as_divine_gets_more_expensive():
    tiers_cfg = _pct_tiers_cfg()
    # same 30c item, late-league divine at 300c — now only 10% of divine
    tier = filter_gen.tier_of(30.0, tiers_cfg, divine_chaos=300.0)
    assert tier["name"] != "S"


def test_tier_of_falls_back_to_min_chaos_when_divine_unresolved():
    tiers_cfg = _pct_tiers_cfg()
    assert filter_gen.tier_of(150.0, tiers_cfg, divine_chaos=None)["name"] == "S"
    tier = filter_gen.tier_of(149.0, tiers_cfg, divine_chaos=None)
    assert tier is None or tier["name"] != "S"


def test_tier_of_falls_back_to_min_chaos_when_tier_has_no_pct():
    tiers_cfg = [{"name": "S", "min_chaos": 150}]
    assert filter_gen.tier_of(150.0, tiers_cfg, divine_chaos=999.0)["name"] == "S"
    assert filter_gen.tier_of(149.0, tiers_cfg, divine_chaos=999.0) is None


# ---------------------------------------------------------------------------
# _resolve_divine_chaos
# ---------------------------------------------------------------------------

def test_resolve_divine_chaos_reads_currency_entry():
    assert filter_gen._resolve_divine_chaos(_hub_data()) == 200.0


def test_resolve_divine_chaos_none_when_missing():
    data = _hub_data(currency=[
        {"category": "Currency", "name": "Chaos Orb", "base": None, "chaos_value": 1.0},
    ])
    assert filter_gen._resolve_divine_chaos(data) is None


def test_resolve_divine_chaos_none_when_zero():
    data = _hub_data(currency=[
        {"category": "Currency", "name": "Divine Orb", "base": None, "chaos_value": 0.0},
    ])
    assert filter_gen._resolve_divine_chaos(data) is None


# ---------------------------------------------------------------------------
# bucket_currency self-scales with min_divine_pct (integration of the above)
# ---------------------------------------------------------------------------

def _pct_rules(**overrides):
    r = _rules(tiers=_pct_tiers_cfg())
    r.update(overrides)
    return r


def test_bucket_currency_30_40c_reaches_top_tier_on_a_cheap_divine_day():
    data = _hub_data(currency=[
        {"category": "Currency", "name": "Divine Orb", "base": None, "chaos_value": 40.0},
        {"category": "Currency", "name": "Some Orb", "base": None, "chaos_value": 35.0},
    ])
    tiers = filter_gen.bucket_currency(data, _pct_rules())
    assert "Some Orb" in tiers["S"]


def test_bucket_currency_same_price_no_longer_top_tier_once_divine_inflates():
    data = _hub_data(currency=[
        {"category": "Currency", "name": "Divine Orb", "base": None, "chaos_value": 300.0},
        {"category": "Currency", "name": "Some Orb", "base": None, "chaos_value": 35.0},
    ])
    tiers = filter_gen.bucket_currency(data, _pct_rules())
    assert "Some Orb" not in tiers.get("S", [])


# ---------------------------------------------------------------------------
# _resolve_divine_chaos_for_tiering / dead-economy sanity check (task 2026-07-27:
# a dead/end-of-league snapshot with an anomalously cheap Divine Orb collapses
# every min_divine_pct threshold toward zero, which can both flood tiers with
# spurious promotions and — before the bucket_currency fix above — push
# ordinary currency below even the lowest tier into a dim/self-generated
# block that visually overrode NeverSink's real, prominent rule for it)
# ---------------------------------------------------------------------------

def test_resolve_divine_chaos_for_tiering_returns_raw_value_when_healthy():
    assert filter_gen._resolve_divine_chaos_for_tiering(_hub_data(), _rules()) == 200.0


def test_resolve_divine_chaos_for_tiering_none_when_below_sanity_floor(caplog):
    data = _hub_data(currency=[
        {"category": "Currency", "name": "Divine Orb", "base": None, "chaos_value": 8.76},
    ])
    assert filter_gen._resolve_divine_chaos_for_tiering(data, _rules()) is None
    assert "sanity floor" in caplog.text.lower()


def test_resolve_divine_chaos_for_tiering_respects_rules_override():
    data = _hub_data(currency=[
        {"category": "Currency", "name": "Divine Orb", "base": None, "chaos_value": 20.0},
    ])
    assert filter_gen._resolve_divine_chaos_for_tiering(data, _rules(divine_sanity_floor=25.0)) is None
    assert filter_gen._resolve_divine_chaos_for_tiering(data, _rules(divine_sanity_floor=10.0)) == 20.0


def test_bucket_currency_dead_economy_falls_back_to_absolute_min_chaos(caplog):
    """Reproduces the real 2026-07-27 incident: Divine crashed to 8.76c
    (Mirror of Kalandra still ~4800x that) — %-of-Divine tiering must be
    disabled for this run so Mirror is still promoted (via absolute
    min_chaos) while near-worthless Chaos Orb is left untouched instead of
    being misclassified as trash."""
    data = _hub_data(currency=[
        {"category": "Currency", "name": "Divine Orb", "base": None, "chaos_value": 8.76},
        {"category": "Currency", "name": "Mirror of Kalandra", "base": None, "chaos_value": 42211.0},
        {"category": "Currency", "name": "Chaos Orb", "base": None, "chaos_value": 0.001},
    ])
    tiers = filter_gen.bucket_currency(data, _pct_rules())
    assert "Mirror of Kalandra" in tiers["S"]
    all_names = {n for names in tiers.values() for n in names}
    assert "Chaos Orb" not in all_names
    assert "sanity floor" in caplog.text.lower()


# ---------------------------------------------------------------------------
# _apply_max_count — caps a tier's population, cascades overflow downward
# (guards against a real failure mode: Divine Orb priced far below the true
# top of the economy floods a percent-of-Divine tier with hundreds of names —
# see 2026-07-25 diagnostic in history.md)
# ---------------------------------------------------------------------------

def test_apply_max_count_keeps_top_n_by_chaos_value():
    bucketed = {"S": ["a", "b", "c"]}
    chaos = {"a": 10.0, "b": 30.0, "c": 20.0}
    tiers_cfg = [{"name": "S", "max_count": 2}, {"name": "A", "max_count": None}]
    result = filter_gen._apply_max_count(bucketed, chaos, tiers_cfg)
    assert result["S"] == ["b", "c"]


def test_apply_max_count_cascades_overflow_to_next_tier():
    bucketed = {"S": ["a", "b", "c"]}
    chaos = {"a": 10.0, "b": 30.0, "c": 20.0}
    tiers_cfg = [{"name": "S", "max_count": 2}, {"name": "A", "max_count": None}]
    result = filter_gen._apply_max_count(bucketed, chaos, tiers_cfg)
    assert result["A"] == ["a"]


def test_apply_max_count_no_cap_passes_through_unchanged():
    bucketed = {"S": ["a", "b", "c"]}
    chaos = {"a": 10.0, "b": 30.0, "c": 20.0}
    tiers_cfg = [{"name": "S", "max_count": None}]
    result = filter_gen._apply_max_count(bucketed, chaos, tiers_cfg)
    assert set(result["S"]) == {"a", "b", "c"}


def test_apply_max_count_overflow_from_lowest_tier_is_kept_not_dropped():
    bucketed = {"C": ["a", "b", "c"]}
    chaos = {"a": 10.0, "b": 30.0, "c": 20.0}
    tiers_cfg = [{"name": "C", "max_count": 1}]
    result = filter_gen._apply_max_count(bucketed, chaos, tiers_cfg)
    assert set(result["C"]) == {"a", "b", "c"}


# ---------------------------------------------------------------------------
# emit
#
# No more emit_dim_section — a self-generated low-value "dim" block for
# currency was removed 2026-07-27: it was written into generated_section
# *before* base_text, so on a dead/anomalous economy snapshot where cheap
# prices pushed ordinary top-shelf currency (Chaos Orb itself, in the live
# incident) below the dim cutoff, that block silently overrode NeverSink's
# own prominent rule for it. Currency below every real tier is now left
# 100% untouched (see bucket_currency) instead of being routed anywhere.
# ---------------------------------------------------------------------------

def test_emit_unique_section_uses_rarity_and_basetype_no_fallback_block():
    tiers = filter_gen.bucket_uniques(_hub_data(), _rules())
    lines = filter_gen.emit_unique_section(tiers, _rules())
    text = "\n".join(lines)
    assert "Rarity == Unique" in text
    assert 'BaseType == "Royal Axe"' in text
    # no more blanket catch-all — it used to shadow every real NeverSink
    # unique rule since generated_section is written before base_text
    # (see 2026-07-25 diagnostic in history.md)
    assert "Unique fallback" not in text


def test_emit_unique_section_c_tier_never_emitted_and_has_no_home():
    data = _hub_data(items=[
        {"category": "UniqueWeapon", "name": "Junk", "base": "Rusty Sword", "chaos_value": 1.5},
    ])
    tiers = filter_gen.bucket_uniques(data, _rules())
    lines = filter_gen.emit_unique_section(tiers, _rules())
    text = "\n".join(lines)
    # left for NeverSink's own base filter to handle — no generated opinion at all
    assert "Rusty Sword" not in text


def test_emit_unique_section_uses_real_style_when_given():
    tiers = filter_gen.bucket_uniques(_hub_data(), _rules())
    real_styles = {"S": ["    SetTextColor 0 0 0 255", "    SetBorderColor 0 0 0 255",
                         "    SetBackgroundColor 245 139 87 255", "    SetFontSize 42"]}
    lines = filter_gen.emit_unique_section(tiers, _rules(), real_styles)
    text = "\n".join(lines)
    assert "SetBackgroundColor 245 139 87 255" in text
    assert "SetBorderColor 255 0 0" not in text  # hardcoded fallback not used for tier S


def test_emit_unique_section_falls_back_to_hardcoded_style_when_tier_missing_from_real_styles():
    tiers = filter_gen.bucket_uniques(_hub_data(), _rules())
    lines = filter_gen.emit_unique_section(tiers, _rules(), real_styles={})
    text = "\n".join(lines)
    assert "SetBorderColor 255 0 0" in text  # _rules()'s hardcoded tier S border


def test_emit_unique_section_sound_map_overrides_real_style_sound():
    tiers = filter_gen.bucket_uniques(_hub_data(), _rules())
    real_styles = {"S": ["    SetBorderColor 0 0 0 255", "    PlayAlertSound 6 300"]}
    lines = filter_gen.emit_unique_section(tiers, _rules(), real_styles,
                                           sound_map={"S": "poe-checker-S.mp3"})
    text = "\n".join(lines)
    assert 'CustomAlertSound "poe-checker-S.mp3" 300' in text
    assert "PlayAlertSound 6 300" not in text
    assert "SetBorderColor 0 0 0 255" in text  # rest of the real style is untouched


# ---------------------------------------------------------------------------
# resolve_real_styles
# ---------------------------------------------------------------------------

def test_resolve_real_styles_rips_full_style_set_from_anchor_block():
    styles = filter_gen.resolve_real_styles(_SAMPLE_BASE_FILTER, {"S": "Divine Orb"})
    assert styles["S"] == [
        "    SetBorderColor 255 0 0",
        "    SetTextColor 255 0 0",
        "    PlayAlertSound 6 300",
        "    MinimapIcon 0 Red Star",
    ]


def test_resolve_real_styles_omits_tier_whose_anchor_does_not_resolve():
    styles = filter_gen.resolve_real_styles(_SAMPLE_BASE_FILTER, {"S": "Mirror of Kalandra"})
    assert "S" not in styles


def test_resolve_real_styles_no_base_text_returns_empty():
    assert filter_gen.resolve_real_styles(None, {"S": "Divine Orb"}) == {}


# ---------------------------------------------------------------------------
# is_stale
# ---------------------------------------------------------------------------

def test_is_stale_fresh_snapshot_not_stale():
    data = _hub_data(generated_at=datetime.now(timezone.utc).isoformat())
    assert filter_gen.is_stale(data, 24) is False


def test_is_stale_old_snapshot_is_stale():
    old = datetime.now(timezone.utc) - timedelta(hours=48)
    data = _hub_data(generated_at=old.isoformat())
    assert filter_gen.is_stale(data, 24) is True


def test_is_stale_missing_timestamp_treated_as_stale():
    data = _hub_data(generated_at=None)
    assert filter_gen.is_stale(data, 24) is True


# ---------------------------------------------------------------------------
# signature
# ---------------------------------------------------------------------------

def test_signature_stable_for_identical_bucketing():
    data = _hub_data()
    sig1 = filter_gen.signature(data, _rules())
    sig2 = filter_gen.signature(data, _rules())
    assert sig1 == sig2


def test_signature_unaffected_by_price_wobble_within_same_tier():
    data_a = _hub_data()
    data_b = _hub_data(currency=[
        {"category": "Currency", "name": "Divine Orb", "base": None, "chaos_value": 205.0},  # still S
        {"category": "Currency", "name": "Chaos Orb", "base": None, "chaos_value": 1.0},
        {"category": "Fragment", "name": "Sacrifice Fragment", "base": None, "chaos_value": 25.0},
        {"category": "Essence", "name": "Deafening Essence of Greed", "base": None, "chaos_value": 0.1},
    ])
    sig_a = filter_gen.signature(data_a, _rules())
    sig_b = filter_gen.signature(data_b, _rules())
    assert sig_a == sig_b


def test_signature_changes_when_a_name_actually_changes_tier():
    data_a = _hub_data()
    data_b = _hub_data(currency=[
        {"category": "Currency", "name": "Divine Orb", "base": None, "chaos_value": 3.0},  # S -> B now
        {"category": "Currency", "name": "Chaos Orb", "base": None, "chaos_value": 1.0},
        {"category": "Fragment", "name": "Sacrifice Fragment", "base": None, "chaos_value": 25.0},
        {"category": "Essence", "name": "Deafening Essence of Greed", "base": None, "chaos_value": 0.1},
    ])
    sig_a = filter_gen.signature(data_a, _rules())
    sig_b = filter_gen.signature(data_b, _rules())
    assert sig_a != sig_b


# ---------------------------------------------------------------------------
# load_rules / save_rules
# ---------------------------------------------------------------------------

def test_load_rules_no_config_dir_returns_defaults():
    rules = filter_gen.load_rules(None)
    assert rules["tiers"][0]["name"] == "S"


def test_load_rules_missing_file_returns_defaults(tmp_path):
    rules = filter_gen.load_rules(tmp_path)
    assert rules["divine_sanity_floor"] == 15.0


def test_save_then_load_rules_roundtrip(tmp_path):
    rules = _rules(divine_sanity_floor=25.0)
    filter_gen.save_rules(tmp_path, rules)
    loaded = filter_gen.load_rules(tmp_path)
    assert loaded["divine_sanity_floor"] == 25.0


# ---------------------------------------------------------------------------
# apply_base_filter_sounds — inherit default S/A/B sound from the base filter
# ---------------------------------------------------------------------------

_SAMPLE_BASE_FILTER = """\
Show # top currency
\tBaseType == "Divine Orb"
\tSetBorderColor 255 0 0
\tSetTextColor 255 0 0
\tPlayAlertSound 6 300
\tMinimapIcon 0 Red Star

Show # exalted orb, different sound on purpose (keeps tier S/A independent in tests)
\tBaseType == "Exalted Orb"
\tSetBorderColor 255 60 0
\tPlayAlertSound 5 280

Show # mid currency, custom sound
\tBaseType == "Chaos Orb"
\tSetBorderColor 0 200 255
\tCustomAlertSound "ping.mp3" 250

Show # styled but no sound line at all
\tBaseType == "Silver Coin"
\tSetBorderColor 100 100 100

Hide # junk, never shown
\tBaseType == "Scroll of Wisdom"
\tSetFontSize 10
"""


def test_apply_base_filter_sounds_inherits_playalertsound():
    rules = filter_gen.apply_base_filter_sounds(_rules(), _SAMPLE_BASE_FILTER)
    s_tier = next(t for t in rules["tiers"] if t["name"] == "S")
    assert s_tier["sound"] == {"kind": "PlayAlertSound", "raw": "6 300"}


def test_apply_base_filter_sounds_inherits_customalertsound():
    rules = filter_gen.apply_base_filter_sounds(
        _rules(), _SAMPLE_BASE_FILTER, anchors={"B": "Chaos Orb"})
    b_tier = next(t for t in rules["tiers"] if t["name"] == "B")
    assert b_tier["sound"] == {"kind": "CustomAlertSound", "raw": '"ping.mp3" 250'}


def test_apply_base_filter_sounds_falls_back_when_anchor_missing(caplog):
    rules = filter_gen.apply_base_filter_sounds(
        _rules(), _SAMPLE_BASE_FILTER, anchors={"A": "Mirror of Kalandra"})
    a_tier = next(t for t in rules["tiers"] if t["name"] == "A")
    assert a_tier["sound"] == "1 300"  # unchanged rules-file default
    assert "not found" in caplog.text.lower() or "not found" in caplog.text


def test_apply_base_filter_sounds_falls_back_when_anchor_only_in_hide_rule(caplog):
    rules = filter_gen.apply_base_filter_sounds(
        _rules(), _SAMPLE_BASE_FILTER, anchors={"S": "Scroll of Wisdom"})
    s_tier = next(t for t in rules["tiers"] if t["name"] == "S")
    assert s_tier["sound"] == "6 300"  # unchanged rules-file default
    assert caplog.text  # a warning was logged


def test_apply_base_filter_sounds_falls_back_when_show_block_has_no_sound_line():
    rules = filter_gen.apply_base_filter_sounds(
        _rules(), _SAMPLE_BASE_FILTER, anchors={"A": "Silver Coin"})
    a_tier = next(t for t in rules["tiers"] if t["name"] == "A")
    assert a_tier["sound"] == "1 300"  # unchanged rules-file default


def test_apply_base_filter_sounds_no_base_text_falls_back_for_all_anchors():
    rules = filter_gen.apply_base_filter_sounds(_rules(), None)
    for name, expected in (("S", "6 300"), ("A", "1 300"), ("B", None)):
        t = next(t for t in rules["tiers"] if t["name"] == name)
        assert t["sound"] == expected


def test_apply_base_filter_sounds_leaves_tier_c_untouched():
    rules = filter_gen.apply_base_filter_sounds(_rules(), _SAMPLE_BASE_FILTER)
    c_tier = next(t for t in rules["tiers"] if t["name"] == "C")
    assert c_tier["sound"] is None


def test_apply_base_filter_sounds_does_not_mutate_input_rules():
    original = _rules()
    filter_gen.apply_base_filter_sounds(original, _SAMPLE_BASE_FILTER)
    s_tier = next(t for t in original["tiers"] if t["name"] == "S")
    assert s_tier["sound"] == "6 300"  # untouched — apply_base_filter_sounds returned a copy


def test_apply_base_filter_sounds_respects_anchors_override_in_rules():
    rules_with_custom_anchors = _rules(anchors={"S": "Chaos Orb"})
    rules = filter_gen.apply_base_filter_sounds(rules_with_custom_anchors, _SAMPLE_BASE_FILTER)
    s_tier = next(t for t in rules["tiers"] if t["name"] == "S")
    assert s_tier["sound"] == {"kind": "CustomAlertSound", "raw": '"ping.mp3" 250'}


def test_emit_unique_section_inherited_sound_used_in_hardcoded_fallback():
    # apply_base_filter_sounds is now only relevant as the last-resort fallback
    # feeding _style_lines when a unique tier's real style can't be ripped —
    # currency itself never touches this any more.
    rules = filter_gen.apply_base_filter_sounds(_rules(), _SAMPLE_BASE_FILTER)
    tiers = filter_gen.bucket_uniques(_hub_data(), rules)
    lines = filter_gen.emit_unique_section(tiers, rules, real_styles={})
    text = "\n".join(lines)
    assert "PlayAlertSound 6 300" in text


_STACKSIZE_GATED_BASE_FILTER = """\
Show # bulk stack bonus — doesn't apply to a lone dropped item
\tBaseType == "Divine Orb"
\tStackSize >= 4
\tSetBorderColor 255 255 255
\tPlayAlertSound 9 300

Show # ordinary single-item rule
\tBaseType == "Divine Orb"
\tSetBorderColor 255 0 0
\tPlayAlertSound 6 300
"""

_AREALEVEL_GATED_BASE_FILTER = """\
Show # only in high-level areas — not a plain item property
\tBaseType == "Exalted Orb"
\tAreaLevel >= 65
\tSetBorderColor 255 255 255
\tPlayAlertSound 9 300

Show # ordinary single-item rule
\tBaseType == "Exalted Orb"
\tSetBorderColor 255 0 0
\tPlayAlertSound 5 280
"""

_STACKSIZE_COMPATIBLE_BASE_FILTER = """\
Show # StackSize <= 1 still matches a lone item — not narrowing
\tBaseType == "Chaos Orb"
\tStackSize <= 1
\tSetBorderColor 255 0 0
\tPlayAlertSound 7 300

Show # would-be ordinary rule, never reached for a lone item
\tBaseType == "Chaos Orb"
\tSetBorderColor 0 0 0
\tPlayAlertSound 2 300
"""


def test_apply_base_filter_sounds_skips_stacksize_gated_block():
    rules = filter_gen.apply_base_filter_sounds(
        _rules(), _STACKSIZE_GATED_BASE_FILTER, anchors={"S": "Divine Orb"})
    s_tier = next(t for t in rules["tiers"] if t["name"] == "S")
    assert s_tier["sound"] == {"kind": "PlayAlertSound", "raw": "6 300"}


def test_apply_base_filter_sounds_skips_arealevel_gated_block():
    rules = filter_gen.apply_base_filter_sounds(
        _rules(), _AREALEVEL_GATED_BASE_FILTER, anchors={"A": "Exalted Orb"})
    a_tier = next(t for t in rules["tiers"] if t["name"] == "A")
    assert a_tier["sound"] == {"kind": "PlayAlertSound", "raw": "5 280"}


def test_apply_base_filter_sounds_stacksize_compatible_with_single_item_is_not_skipped():
    rules = filter_gen.apply_base_filter_sounds(
        _rules(), _STACKSIZE_COMPATIBLE_BASE_FILTER, anchors={"B": "Chaos Orb"})
    b_tier = next(t for t in rules["tiers"] if t["name"] == "B")
    # "StackSize <= 1" still matches a lone drop, so the *first* block counts —
    # not the later "ordinary" one.
    assert b_tier["sound"] == {"kind": "PlayAlertSound", "raw": "7 300"}


def test_load_rules_malformed_override_falls_back_to_defaults(tmp_path):
    (tmp_path / "filter_gen_rules.json").write_text('{"not_tiers": true}', encoding="utf-8")
    rules = filter_gen.load_rules(tmp_path)
    assert rules["tiers"][0]["name"] == "S"


# ---------------------------------------------------------------------------
# merge_currency_into_base — Plan B: relocate BaseTypes directly into
# NeverSink's own blocks instead of emitting our own currency Show blocks
# ---------------------------------------------------------------------------

# Block order deliberately S, B, A, C (not rank order) — matches a real quirk
# found live in NeverSink's actual PoE2 filter, where the internal block
# order doesn't follow S/A/B/C rank at all. Using that order here means the
# "up" tier test move below is a genuine forward-position move that exercises
# real old-block cleanup, instead of accidentally landing on the "target is
# earlier, no cleanup needed" case every time. There's no "down" tier move
# test any more — merge_currency_into_base now refuses to demote an item
# below its existing NeverSink placement (see the guard tests below).
_PLAN_B_BASE_FILTER = """\
Show # tier S
\tBaseType == "Divine Orb" "Mirror of Kalandra"
\tSetFontSize 45
\tSetTextColor 255 0 0
\tPlayAlertSound 6 300

Show # tier B
\tBaseType == "Chaos Orb" "Regal Orb"
\tSetFontSize 40
\tSetTextColor 0 200 255
\tPlayAlertSound 2 280

Show # tier A
\tBaseType == "Exalted Orb" "Ancient Orb"
\tSetFontSize 42
\tSetTextColor 255 170 0
\tPlayAlertSound 2 300

Show # tier C
\tBaseType == "Orb of Augmentation" "Orb of Transmutation"
\tSetFontSize 35
\tSetTextColor 150 150 150
"""


def _default_currency_tiers():
    """The tier assignment that exactly matches _PLAN_B_BASE_FILTER's current
    layout — a no-op input for merge_currency_into_base."""
    return {
        "S": ["Divine Orb", "Mirror of Kalandra"],
        "A": ["Exalted Orb", "Ancient Orb"],
        "B": ["Chaos Orb", "Regal Orb"],
        "C": ["Orb of Augmentation", "Orb of Transmutation"],
    }


def test_merge_currency_into_base_moves_item_up_a_tier():
    tiers = _default_currency_tiers()
    tiers["B"] = ["Chaos Orb"]                       # Regal Orb leaves B...
    tiers["A"] = ["Exalted Orb", "Ancient Orb", "Regal Orb"]  # ...and joins A

    new_text, applied = filter_gen.merge_currency_into_base(_PLAN_B_BASE_FILTER, tiers, _rules())
    assert applied is True

    b_line = next(l for l in new_text.splitlines() if l.strip().startswith("BaseType") and "Chaos Orb" in l)
    a_line = next(l for l in new_text.splitlines() if l.strip().startswith("BaseType") and "Exalted Orb" in l)
    assert "Regal Orb" not in b_line
    assert "Regal Orb" in a_line
    # untouched blocks (S, C) must be byte-identical to the original
    assert 'BaseType == "Divine Orb" "Mirror of Kalandra"' in new_text
    assert 'BaseType == "Orb of Augmentation" "Orb of Transmutation"' in new_text


def test_merge_currency_into_base_refuses_to_demote_below_neversink_baseline(caplog):
    """The never-demote guard (2026-07-27, added after a dead-economy
    snapshot's near-zero prices could otherwise push ordinary currency below
    its NeverSink default): hub data saying Ancient Orb now belongs in C is
    refused — it stays at its existing NeverSink placement (A), byte-for-
    byte untouched, instead of being relocated to the less prominent block."""
    tiers = _default_currency_tiers()
    tiers["A"] = ["Exalted Orb"]                                    # hub wants Ancient Orb out of A...
    tiers["C"] = ["Orb of Augmentation", "Orb of Transmutation", "Ancient Orb"]  # ...and into C

    new_text, applied = filter_gen.merge_currency_into_base(_PLAN_B_BASE_FILTER, tiers, _rules())
    assert applied is True

    a_line = next(l for l in new_text.splitlines() if l.strip().startswith("BaseType") and "Exalted Orb" in l)
    c_line = next(l for l in new_text.splitlines() if l.strip().startswith("BaseType") and "Orb of Augmentation" in l)
    assert "Ancient Orb" in a_line       # guard kept it at its NeverSink baseline
    assert "Ancient Orb" not in c_line
    assert "kept" in caplog.text.lower()


def test_merge_currency_into_base_guard_does_not_block_promotions():
    """The guard only refuses *demotions* — an item hub data says deserves a
    *more* prominent tier than its NeverSink baseline still moves freely
    (this is the same scenario as test_merge_currency_into_base_moves_item_up_a_tier,
    asserted again here explicitly alongside the guard tests for clarity)."""
    tiers = _default_currency_tiers()
    tiers["B"] = ["Chaos Orb"]                                # Regal Orb leaves B (baseline)...
    tiers["A"] = ["Exalted Orb", "Ancient Orb", "Regal Orb"]  # ...and is promoted into A

    new_text, applied = filter_gen.merge_currency_into_base(_PLAN_B_BASE_FILTER, tiers, _rules())
    assert applied is True
    a_line = next(l for l in new_text.splitlines() if l.strip().startswith("BaseType") and "Exalted Orb" in l)
    assert "Regal Orb" in a_line


def test_merge_currency_into_base_adds_item_not_in_base_at_all():
    tiers = _default_currency_tiers()
    tiers["S"].append("Hinekora's Lock")  # never appears anywhere in the fixture

    new_text, applied = filter_gen.merge_currency_into_base(_PLAN_B_BASE_FILTER, tiers, _rules())
    assert applied is True

    s_line = next(l for l in new_text.splitlines() if l.strip().startswith("BaseType") and "Divine Orb" in l)
    assert "Hinekora's Lock" in s_line
    # every other block must be untouched
    for original_line in _PLAN_B_BASE_FILTER.splitlines():
        if "Exalted Orb" in original_line or "Chaos Orb" in original_line or "Orb of Augmentation" in original_line:
            assert original_line in new_text


def test_merge_currency_into_base_leaves_correctly_placed_items_byte_identical():
    tiers = _default_currency_tiers()  # already matches the fixture exactly
    new_text, applied = filter_gen.merge_currency_into_base(_PLAN_B_BASE_FILTER, tiers, _rules())
    assert applied is True
    assert new_text == _PLAN_B_BASE_FILTER


def test_merge_currency_into_base_diff_only_touches_basetype_lines():
    tiers = _default_currency_tiers()
    tiers["B"] = ["Chaos Orb"]
    tiers["A"] = ["Exalted Orb", "Ancient Orb", "Regal Orb"]

    new_text, applied = filter_gen.merge_currency_into_base(_PLAN_B_BASE_FILTER, tiers, _rules())
    assert applied is True

    old_lines = _PLAN_B_BASE_FILTER.split("\n")
    new_lines = new_text.split("\n")
    assert len(old_lines) == len(new_lines)  # surgery never inserts/deletes lines

    diff_count = 0
    for old_line, new_line in zip(old_lines, new_lines):
        if old_line == new_line:
            continue
        diff_count += 1
        assert old_line.strip().startswith("BaseType")
        assert new_line.strip().startswith("BaseType")
    assert diff_count == 2  # the B and A BaseType lines, nothing else


def test_merge_currency_into_base_falls_back_when_an_anchor_is_unresolvable():
    # base filter has no "Orb of Augmentation" anywhere -> C's anchor can't be resolved
    base = _PLAN_B_BASE_FILTER.replace("Orb of Augmentation", "Orb of Alteration")
    tiers = _default_currency_tiers()
    new_text, applied = filter_gen.merge_currency_into_base(base, tiers, _rules())
    assert applied is False
    assert new_text == base


def test_merge_currency_into_base_removal_is_position_based_not_rank_based():
    """Mirrors a real quirk found in NeverSink's actual PoE2 filter: tier B's
    block can appear *before* tier C's in file order (their internal naming
    doesn't follow our S/A/B/C rank order). An item *promoted* into an
    earlier-positioned target (C -> B here — still an upgrade, so the
    never-demote guard doesn't interfere) is removed from a later block only
    if that later block is scanned — a block *after* the target is
    intentionally left alone since first-match-wins means it can never fire
    anyway."""
    base = """\
Show # tier S
\tBaseType == "Divine Orb"
\tSetFontSize 45

Show # tier B (earlier in file than C, like the real NeverSink layout)
\tBaseType == "Chaos Orb"
\tSetFontSize 40

Show # tier A
\tBaseType == "Exalted Orb"
\tSetFontSize 42

Show # tier C
\tBaseType == "Orb of Augmentation" "Orb of Transmutation"
\tSetFontSize 35
"""
    tiers = {
        "S": ["Divine Orb"], "B": ["Chaos Orb", "Orb of Transmutation"],  # promoted C -> B
        "A": ["Exalted Orb"], "C": ["Orb of Augmentation"],
    }
    new_text, applied = filter_gen.merge_currency_into_base(base, tiers, _rules())
    assert applied is True

    b_line = next(l for l in new_text.splitlines() if l.strip().startswith("BaseType") and "Chaos Orb" in l)
    c_line = next(l for l in new_text.splitlines() if l.strip().startswith("BaseType") and "Orb of Augmentation" in l)
    assert "Orb of Transmutation" in b_line
    # C's block comes *after* B's target in file order, so it's left alone —
    # harmless dead text since B's earlier block already wins first-match-wins.
    assert "Orb of Transmutation" in c_line


# ---------------------------------------------------------------------------
# build_filter — top-level orchestrator (surgery vs fallback)
# ---------------------------------------------------------------------------

def test_build_filter_uses_surgery_when_anchors_resolve():
    section, merged_base, applied = filter_gen.build_filter(_hub_data(), _rules(), _PLAN_B_BASE_FILTER)
    assert applied is True
    assert "Show # Hub currency tier" not in section  # no self-emitted currency blocks
    assert "Uniques by basetype ceiling" in section
    assert merged_base is not None
    # Divine Orb (tier S in _hub_data) ends up in tier S's own block
    s_line = next(l for l in merged_base.splitlines() if l.strip().startswith("BaseType") and "Divine Orb" in l)
    assert "Divine Orb" in s_line


def test_build_filter_dead_economy_never_dims_currency_and_never_demotes_divine(caplog):
    """Reproduces the reported live incident end-to-end: Divine crashed to
    8.76c (dead/end-of-league snapshot), and Chaos Orb/Regal Orb's own
    reported chaos_value collapsed to near-zero along with it. Before the
    2026-07-27 fix, near-zero currency fell into a self-generated "dim"
    block (gray, no border) written *before* base_text, silently overriding
    NeverSink's real, prominent block for it — and even with that fixed,
    Divine's own absolute-fallback tier (min_chaos=5 <= 8.76 -> B) would
    still have been a demotion from its NeverSink baseline (S) without the
    never-demote guard."""
    data = _hub_data(currency=[
        {"category": "Currency", "name": "Divine Orb", "base": None, "chaos_value": 8.76},
        {"category": "Currency", "name": "Mirror of Kalandra", "base": None, "chaos_value": 42211.0},
        {"category": "Currency", "name": "Chaos Orb", "base": None, "chaos_value": 0.001},
        {"category": "Currency", "name": "Regal Orb", "base": None, "chaos_value": 0.0005},
    ])
    section, merged_base, applied = filter_gen.build_filter(data, _pct_rules(), _PLAN_B_BASE_FILTER)
    assert applied is True

    # currency is 100% merge-only — it must never appear in the self-generated
    # section at all, dimmed or otherwise (task: "Chaos Orb กับ orb พื้นฐานทุกตัว
    # ต้องไม่ปรากฏใน generated section เลย")
    for orb in ("Chaos Orb", "Regal Orb", "Divine Orb", "Mirror of Kalandra"):
        assert orb not in section

    # near-zero dead-economy price disqualifies Chaos/Regal from every real
    # tier — left byte-identical in NeverSink's own existing (prominent) block
    assert 'BaseType == "Chaos Orb" "Regal Orb"' in merged_base

    # Divine's absolute-fallback tier (B) would demote it below its NeverSink
    # baseline (S) — the guard refuses that, so the S block is untouched
    assert 'BaseType == "Divine Orb" "Mirror of Kalandra"' in merged_base

    assert "sanity floor" in caplog.text.lower()


def test_build_filter_no_base_text_never_emits_our_own_currency():
    section, merged_base, applied = filter_gen.build_filter(_hub_data(), _rules(), None)
    assert applied is False
    assert merged_base is None
    # Plan B, in full: no fallback that emits our own currency Show blocks —
    # not even when there's no base filter to merge into at all.
    assert "Hub currency tier" not in section
    assert "Uniques by basetype ceiling" in section  # still self-generated


def test_build_filter_anchor_unresolvable_never_emits_our_own_currency(caplog):
    base = _PLAN_B_BASE_FILTER.replace("Orb of Augmentation", "Orb of Alteration")
    section, merged_base, applied = filter_gen.build_filter(_hub_data(), _rules(), base)
    assert applied is False
    assert merged_base == base  # left completely untouched, not partially merged
    assert "Hub currency tier" not in section
    assert "currency" in caplog.text.lower()  # warned, not silent


def test_build_filter_uses_real_style_for_uniques_when_surgery_succeeds():
    section, merged_base, applied = filter_gen.build_filter(_hub_data(), _rules(), _PLAN_B_BASE_FILTER)
    assert applied is True
    # _hub_data()'s uniques bucket to S ("Royal Axe") and B ("Glorious Plate")
    # only. _PLAN_B_BASE_FILTER's real blocks use SetTextColor 255 0 0 (S) /
    # 0 200 255 (B) with no background override at all — our hardcoded
    # fallback (_rules()) always sets one, so its absence here proves the
    # real ripped style won over the hardcoded fallback.
    assert "SetTextColor 255 0 0" in section  # real tier S
    assert "SetTextColor 0 200 255" in section  # real tier B
    assert "SetBackgroundColor" not in section


def test_build_filter_partial_real_styles_even_when_surgery_fails():
    # C's anchor is broken (so currency surgery fails all-or-nothing), but
    # S/B's anchors still resolve fine — resolve_real_styles isn't
    # all-or-nothing like merge_currency_into_base, so uniques should still
    # get their real look for the tiers that do resolve.
    base = _PLAN_B_BASE_FILTER.replace("Orb of Augmentation", "Orb of Alteration")
    section, merged_base, applied = filter_gen.build_filter(_hub_data(), _rules(), base)
    assert applied is False
    assert "SetTextColor 255 0 0" in section  # real tier S style, not the hardcoded fallback
    assert "SetBackgroundColor" not in section
