"""Tests for filter_gen.py — fixtures shaped like the live hub payload
(category/base/chaos_value fields), same unittest.mock.patch style as
test_hub_client.py where applicable."""
import hashlib
import json
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
# tier_mapping / diff_mapping_count (auto-regen notification's "N items
# changed tier" count — see app.py's _filter_regen_check)
# ---------------------------------------------------------------------------

def test_tier_mapping_matches_what_signature_hashes():
    data = _hub_data()
    rules = _rules()
    mapping = filter_gen.tier_mapping(data, rules)
    blob = json.dumps(mapping, sort_keys=True)
    expected_sig = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    assert filter_gen.signature(data, rules) == expected_sig


def test_diff_mapping_count_zero_for_identical_mappings():
    mapping = filter_gen.tier_mapping(_hub_data(), _rules())
    assert filter_gen.diff_mapping_count(mapping, dict(mapping)) == 0


def test_diff_mapping_count_zero_for_price_wobble_within_same_tier():
    rules = _rules()
    data_a = _hub_data()
    data_b = _hub_data(currency=[
        {"category": "Currency", "name": "Divine Orb", "base": None, "chaos_value": 205.0},  # still S
        {"category": "Currency", "name": "Chaos Orb", "base": None, "chaos_value": 1.0},
        {"category": "Fragment", "name": "Sacrifice Fragment", "base": None, "chaos_value": 25.0},
        {"category": "Essence", "name": "Deafening Essence of Greed", "base": None, "chaos_value": 0.1},
    ])
    old = filter_gen.tier_mapping(data_a, rules)
    new = filter_gen.tier_mapping(data_b, rules)
    assert filter_gen.diff_mapping_count(old, new) == 0


def test_diff_mapping_count_counts_tier_change():
    rules = _rules()
    data_a = _hub_data()
    data_b = _hub_data(currency=[
        {"category": "Currency", "name": "Divine Orb", "base": None, "chaos_value": 3.0},  # S -> B
        {"category": "Currency", "name": "Chaos Orb", "base": None, "chaos_value": 1.0},
        {"category": "Fragment", "name": "Sacrifice Fragment", "base": None, "chaos_value": 25.0},
        {"category": "Essence", "name": "Deafening Essence of Greed", "base": None, "chaos_value": 0.1},
    ])
    old = filter_gen.tier_mapping(data_a, rules)
    new = filter_gen.tier_mapping(data_b, rules)
    assert filter_gen.diff_mapping_count(old, new) == 1


def test_diff_mapping_count_counts_additions_and_removals():
    old = {"c:Divine Orb": "S", "c:Exalted Orb": "A"}
    new = {"c:Divine Orb": "S", "c:Chaos Orb": "B"}  # Exalted removed, Chaos added
    assert filter_gen.diff_mapping_count(old, new) == 2


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
    """min_chaos is the only field the Filter Generator UI actually edits —
    the only thing save_rules/load_rules round-trip."""
    rules = _rules()
    rules["tiers"][0]["min_chaos"] = 999.0  # tier S
    filter_gen.save_rules(tmp_path, rules)
    loaded = filter_gen.load_rules(tmp_path)
    assert loaded["tiers"][0]["min_chaos"] == 999.0


def test_save_rules_only_persists_tier_min_chaos(tmp_path):
    """save_rules is deliberately not a wholesale dump of `rules` — anchors,
    colors, sound, divine_sanity_floor etc. are all code-owned and must
    never end up in the on-disk override file at all."""
    rules = _rules()
    filter_gen.save_rules(tmp_path, rules)
    written = json.loads((tmp_path / "filter_gen_rules.json").read_text(encoding="utf-8"))
    assert set(written.keys()) == {"tiers"}
    assert all(set(t.keys()) == {"name", "min_chaos"} for t in written["tiers"])


def test_load_rules_ignores_everything_except_tier_min_chaos(tmp_path):
    """The actual fix for the 2026-07-27 stale-anchor incident: a full
    legacy-format saved file (old anchors, retired hide_below field, tier
    colors...) must never be able to freeze anything except each tier's
    min_chaos — every other field always comes from the current code's
    _DEFAULT_RULES, so a future default fix (like the anchor swap) can never
    be silently shadowed by an old save again."""
    stale = {
        "tiers": [{"name": "S", "min_chaos": 200.0, "border": "1 1 1"}],
        "hide_below": 0.5,  # retired field
        "anchors": {"S": "Divine Orb", "A": "Exalted Orb", "B": "Chaos Orb",
                    "C": "Orb of Augmentation"},  # the exact stale value from the incident
        "divine_sanity_floor": 999.0,
    }
    (tmp_path / "filter_gen_rules.json").write_text(json.dumps(stale), encoding="utf-8")
    rules = filter_gen.load_rules(tmp_path)
    assert rules["tiers"][0]["min_chaos"] == 200.0        # the one thing that does override
    assert rules["anchors"]["C"][0] == "Orb of Transmutation"  # current code default, not the stale value
    assert rules["divine_sanity_floor"] == 15.0            # current code default, not the stale value
    assert "hide_below" not in rules


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


def test_merge_currency_into_base_skips_tier_whose_anchor_is_unresolvable_but_merges_others(caplog):
    """The 2026-08-08 fix: a tier's anchor candidates all failing to resolve
    must not sink the whole merge (the original bug — switching PoE1 to
    strictness 3 broke tier C's anchor and the *entire* currency merge
    silently stopped, including for S/A/B which resolved fine). C's block
    here uses names that don't match any of tier C's default candidates;
    S/A/B are untouched and still resolve."""
    base = _PLAN_B_BASE_FILTER.replace(
        'BaseType == "Orb of Augmentation" "Orb of Transmutation"',
        'BaseType == "Made Up Currency A" "Made Up Currency B"')
    tiers = _default_currency_tiers()
    tiers["C"] = ["Made Up Currency A", "Made Up Currency B"]  # already correctly placed, no-op
    tiers["B"] = ["Chaos Orb"]                                 # Regal Orb leaves B...
    tiers["A"] = ["Exalted Orb", "Ancient Orb", "Regal Orb"]   # ...and joins A — real merge work

    new_text, applied = filter_gen.merge_currency_into_base(base, tiers, _rules())
    assert applied is True  # S/A/B resolved and merged even though C's anchor didn't

    a_line = next(l for l in new_text.splitlines() if l.strip().startswith("BaseType") and "Exalted Orb" in l)
    assert "Regal Orb" in a_line
    # C's block is left byte-identical — its anchor never resolved, so it's
    # treated the same as any other untiered NeverSink block
    assert 'BaseType == "Made Up Currency A" "Made Up Currency B"' in new_text
    assert "tier C" in caplog.text


def test_merge_currency_into_base_returns_false_only_when_no_tier_resolves_at_all():
    base = """\
Show # no recognizable currency names at all
\tBaseType == "Made Up Orb"
\tSetFontSize 30
"""
    tiers = {"S": ["Divine Orb"]}
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
    section, merged_base, applied, anchor_status = filter_gen.build_filter(
        _hub_data(), _rules(), _PLAN_B_BASE_FILTER)
    assert applied is True
    assert all(anchor_status.values())  # every tier resolved on this real-shaped fixture
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
    section, merged_base, applied, anchor_status = filter_gen.build_filter(
        data, _pct_rules(), _PLAN_B_BASE_FILTER)
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
    section, merged_base, applied, anchor_status = filter_gen.build_filter(_hub_data(), _rules(), None)
    assert applied is False
    assert merged_base is None
    assert all(v is None for v in anchor_status.values())
    # Plan B, in full: no fallback that emits our own currency Show blocks —
    # not even when there's no base filter to merge into at all.
    assert "Hub currency tier" not in section
    assert "Uniques by basetype ceiling" in section  # still self-generated


def test_build_filter_all_anchors_unresolvable_never_emits_our_own_currency(caplog):
    base = """\
Show # no recognizable currency names at all
\tBaseType == "Made Up Orb"
\tSetFontSize 30
"""
    section, merged_base, applied, anchor_status = filter_gen.build_filter(_hub_data(), _rules(), base)
    assert applied is False
    assert merged_base == base  # left completely untouched, not partially merged
    assert all(v is None for v in anchor_status.values())
    assert "Hub currency tier" not in section
    assert "tier" in caplog.text.lower()  # warned per-tier, not silent


def test_build_filter_one_tier_unresolvable_still_merges_the_others(caplog):
    """The 2026-08-08 fix at the build_filter level: tier C's anchor being
    unresolvable must not sink S/A/B, and anchor_status must say *which*
    tier failed instead of one lumped pass/fail."""
    base = _PLAN_B_BASE_FILTER.replace(
        'BaseType == "Orb of Augmentation" "Orb of Transmutation"',
        'BaseType == "Made Up Currency A" "Made Up Currency B"')
    section, merged_base, applied, anchor_status = filter_gen.build_filter(_hub_data(), _rules(), base)
    assert applied is True  # S/A/B still merged
    assert anchor_status["S"] and anchor_status["A"] and anchor_status["B"]
    assert anchor_status["C"] is None
    assert "Hub currency tier" not in section
    # Divine Orb (tier S in _hub_data) still ends up in tier S's own block
    s_line = next(l for l in merged_base.splitlines() if l.strip().startswith("BaseType") and "Divine Orb" in l)
    assert "Divine Orb" in s_line


def test_build_filter_uses_real_style_for_uniques_when_surgery_succeeds():
    section, merged_base, applied, anchor_status = filter_gen.build_filter(
        _hub_data(), _rules(), _PLAN_B_BASE_FILTER)
    assert applied is True
    # _hub_data()'s uniques bucket to S ("Royal Axe") and B ("Glorious Plate")
    # only. _PLAN_B_BASE_FILTER's real blocks use SetTextColor 255 0 0 (S) /
    # 0 200 255 (B) with no background override at all — our hardcoded
    # fallback (_rules()) always sets one, so its absence here proves the
    # real ripped style won over the hardcoded fallback.
    assert "SetTextColor 255 0 0" in section  # real tier S
    assert "SetTextColor 0 200 255" in section  # real tier B
    assert "SetBackgroundColor" not in section


def test_build_filter_unique_styles_still_use_whatever_tiers_resolve_when_one_tier_fails():
    # C's anchor is broken; S/A/B still resolve fine. resolve_real_styles was
    # already per-tier before this fix — this pins that behavior unchanged
    # now that merge_currency_into_base is per-tier too (2026-08-08).
    base = _PLAN_B_BASE_FILTER.replace(
        'BaseType == "Orb of Augmentation" "Orb of Transmutation"',
        'BaseType == "Made Up Currency A" "Made Up Currency B"')
    section, merged_base, applied, anchor_status = filter_gen.build_filter(_hub_data(), _rules(), base)
    assert applied is True
    assert anchor_status["C"] is None
    assert "SetTextColor 255 0 0" in section  # real tier S style, not the hardcoded fallback
    assert "SetBackgroundColor" not in section


# ---------------------------------------------------------------------------
# Real NeverSink data regression: PoE1's anchor resolution (2026-07-27 live
# incident -- user ran v0.6.2, Generate on PoE1 still logged app.py's
# "รวม currency เข้ากับ base ไม่ได้ (หา anchor block ไม่เจอ)" warning). Root
# cause, found by running _find_anchor_block against the actual cached PoE1
# Semi-Strict filter (LOCALAPPDATA/PoePriceTrade/cache/neversink/poe1/8.20.0b_2.filter,
# tag 8.20.0b, strictness 2): tier C's default anchor ("Orb of Augmentation")
# was chosen and verified only against PoE2's filter. In PoE1's real filter,
# "Orb of Augmentation" only ever appears inside StackSize-gated "leveling"/
# "stackedsupplieslow" blocks (excluded by _block_matches_plain_single_item)
# and the final catch-all Hide block ($tier->t9armour) -- never in an
# ordinary Show block -- so _find_anchor_block correctly returns None for
# it, and merge_currency_into_base aborts the whole surgery (all-or-nothing
# across S/A/B/C) because one anchor of four can't resolve.
#
# "Orb of Transmutation" resolves cleanly in both real files: PoE1's real
# lowest ordinary currency tier ($tier->t8trans, tan/no sound) genuinely
# lists it, and in PoE2's real file it sits in the *same* block as
# "Orb of Augmentation" ($tier->supplymagic) -- so switching anchors["C"] to
# "Orb of Transmutation" resolves the exact same PoE2 block as before
# (verified: both names -> identical block start in the real 0.10.3 file)
# while newly resolving correctly on PoE1 too. Not a parser bug -- PoE1's
# filter genuinely doesn't give Orb of Augmentation an ordinary Show rule at
# Semi-Strict, it's simply Hidden as worthless leveling clutter.
#
# Fixtures below are verbatim cuts (not synthetic) from the real cached
# files: PoE1 lines 14912-15484 of 8.20.0b_2.filter (every currency block
# from the first StackSize-gated Exalted/Chaos Orb block through the real
# S/A/B/C target blocks and the trailing Hide catch-all), PoE2 lines
# 3406-3479 of 0.10.3_2.filter (the real S/A/B/C block group).
# ---------------------------------------------------------------------------

_REAL_POE1_SEMI_STRICT_EXCERPT = """Show # %D8 $type->currency->stackedsix $tier->t2

	StackSize >= 6

	Class == "Stackable Currency"

	BaseType == "Abrasive Catalyst" "Accelerating Catalyst" "Astragali" "Blessed Orb" "Burial Medallion" "Chaos Orb" "Chromatic Orb" "Exalted Orb" "Exotic Coinage" "Gemcutter's Prism" "Glassblower's Bauble" "Grand Eldritch Ember" "Grand Eldritch Ichor" "Greater Eldritch Ember" "Greater Eldritch Ichor" "Instilling Orb" "Intrinsic Catalyst" "Lesser Eldritch Ember" "Lesser Eldritch Ichor" "Orb of Fusing" "Orb of Regret" "Orb of Unmaking" "Stacked Deck" "Tempering Catalyst" "Unstable Catalyst" "Vaal Orb"

	SetFontSize 45

	SetTextColor 255 255 255 255

	SetBorderColor 255 255 255 255

	SetBackgroundColor 240 90 35 255

	PlayAlertSound 1 300

	PlayEffect Red

	MinimapIcon 0 Red Circle



Show # %D7 $type->currency->stackedsix $tier->t3

	StackSize >= 6

	Class == "Stackable Currency"

	BaseType == "Enkindling Orb" "Imbued Catalyst" "Noxious Catalyst" "Orb of Binding" "Orb of Scouring" "Regal Orb" "Scrap Metal" "Turbulent Catalyst"

	SetFontSize 45

	SetTextColor 0 0 0 255

	SetBorderColor 0 0 0 255

	SetBackgroundColor 240 90 35 255

	PlayAlertSound 2 300

	PlayEffect Yellow

	MinimapIcon 1 Yellow Circle



Show # %D6 $type->currency->stackedsix $tier->t4

	StackSize >= 6

	Class == "Stackable Currency"

	BaseType == "Blacksmith's Whetstone" "Orb of Alteration" "Orb of Chance"

	SetFontSize 45

	SetTextColor 0 0 0 255

	SetBorderColor 0 0 0 255

	SetBackgroundColor 249 150 25 255

	PlayAlertSound 2 300

	PlayEffect White

	MinimapIcon 2 White Circle



Show # %DS4 $type->currency->stackedsix $tier->t5

	StackSize >= 6

	Class == "Stackable Currency"

	BaseType == "Armourer's Scrap" "Jeweller's Orb" "Orb of Alchemy"

	SetFontSize 45

	SetTextColor 0 0 0 255

	SetBorderColor 0 0 0 255

	SetBackgroundColor 213 159 0 255

	PlayAlertSound 2 300

	PlayEffect White

	MinimapIcon 2 White Circle



#Show # %DS3 $type->currency->stackedsix $tier->t6

#	StackSize >= 6

#	Class == "Stackable Currency"

#	SetFontSize 45

#	SetTextColor 0 0 0 255

#	SetBorderColor 0 0 0 255

#	SetBackgroundColor 210 178 135 255

#	PlayAlertSound 2 300

#	PlayEffect Grey

#	MinimapIcon 2 Grey Circle



Show # %DS2 $type->currency->stackedsix $tier->t7

	StackSize >= 6

	Class == "Stackable Currency"

	BaseType == "Alchemy Shard" "Alteration Shard"

	SetFontSize 45

	SetTextColor 0 0 0 255

	SetBorderColor 0 0 0 255

	SetBackgroundColor 210 178 135 255



#------------------------------------

#   [3906] Stacked Currencies: 3x

#------------------------------------



Show # %D9 $type->currency->stackedthree $tier->t1

	StackSize >= 3

	Class == "Stackable Currency"

	BaseType == "Ancient Orb" "Dextral Catalyst" "Fertile Catalyst" "Fracturing Shard" "Orb of Annulment" "Prismatic Catalyst" "Sinistral Catalyst"

	SetFontSize 45

	SetTextColor 255 0 0 255

	SetBorderColor 255 0 0 255

	SetBackgroundColor 255 255 255 255

	PlayAlertSound 6 300

	PlayEffect Red

	MinimapIcon 0 Red Star



Show # %D8 $type->currency->stackedthree $tier->t2

	StackSize >= 3

	Class == "Stackable Currency"

	BaseType == "Accelerating Catalyst" "Blessed Orb" "Exalted Orb" "Exotic Coinage" "Gemcutter's Prism" "Grand Eldritch Ember" "Grand Eldritch Ichor" "Greater Eldritch Ember" "Instilling Orb" "Orb of Unmaking" "Stacked Deck" "Tempering Catalyst" "Unstable Catalyst"

	SetFontSize 45

	SetTextColor 255 255 255 255

	SetBorderColor 255 255 255 255

	SetBackgroundColor 240 90 35 255

	PlayAlertSound 1 300

	PlayEffect Red

	MinimapIcon 0 Red Circle



Show # %D7 $type->currency->stackedthree $tier->t3

	StackSize >= 3

	Class == "Stackable Currency"

	BaseType == "Abrasive Catalyst" "Astragali" "Burial Medallion" "Chaos Orb" "Chromatic Orb" "Glassblower's Bauble" "Greater Eldritch Ichor" "Intrinsic Catalyst" "Lesser Eldritch Ember" "Lesser Eldritch Ichor" "Orb of Fusing" "Orb of Regret" "Scrap Metal" "Vaal Orb"

	SetFontSize 45

	SetTextColor 0 0 0 255

	SetBorderColor 0 0 0 255

	SetBackgroundColor 240 90 35 255

	PlayAlertSound 2 300

	PlayEffect Yellow

	MinimapIcon 1 Yellow Circle



Show # %D6 $type->currency->stackedthree $tier->t4

	StackSize >= 3

	Class == "Stackable Currency"

	BaseType == "Enkindling Orb" "Imbued Catalyst" "Noxious Catalyst" "Orb of Binding" "Orb of Scouring" "Regal Orb" "Turbulent Catalyst"

	SetFontSize 45

	SetTextColor 0 0 0 255

	SetBorderColor 0 0 0 255

	SetBackgroundColor 249 150 25 255

	PlayAlertSound 2 300

	PlayEffect White

	MinimapIcon 2 White Circle



Show # %DS4 $type->currency->stackedthree $tier->t5

	StackSize >= 3

	Class == "Stackable Currency"

	BaseType == "Blacksmith's Whetstone" "Jeweller's Orb" "Orb of Alchemy" "Orb of Alteration" "Orb of Chance"

	SetFontSize 45

	SetTextColor 0 0 0 255

	SetBorderColor 0 0 0 255

	SetBackgroundColor 213 159 0 255

	PlayAlertSound 2 300

	PlayEffect White

	MinimapIcon 2 White Circle



Show # %DS3 $type->currency->stackedthree $tier->t6

	StackSize >= 3

	Class == "Stackable Currency"

	BaseType == "Armourer's Scrap"

	SetFontSize 45

	SetTextColor 0 0 0 255

	SetBorderColor 0 0 0 255

	SetBackgroundColor 210 178 135 255

	PlayAlertSound 2 300

	PlayEffect Grey

	MinimapIcon 2 Grey Circle



Show # %DS2 $type->currency->stackedthree $tier->t7

	StackSize >= 3

	Class == "Stackable Currency"

	BaseType == "Alchemy Shard" "Alteration Shard"

	SetFontSize 45

	SetTextColor 0 0 0 255

	SetBorderColor 0 0 0 255

	SetBackgroundColor 210 178 135 255



# !! Waypoint c9.currency.heistcoins : "Tierlist - Currency - Heist Coins" : "Heist, Expedition, Sanctum"

#------------------------------------

#   [3907] Heist Coins

#------------------------------------



Show # %H5 $type->currency->heist $tier->highstack

	StackSize >= 400

	Class == "Stackable Currency"

	BaseType == "Rogue's Marker"

	SetFontSize 45

	SetTextColor 255 178 135 255

	SetBorderColor 255 178 135 255

	SetBackgroundColor 150 90 70 255

	PlayEffect Orange



Show # %H4 $type->currency->heist $tier->any

	Class == "Stackable Currency"

	BaseType == "Rogue's Marker"

	SetFontSize 45

	SetTextColor 255 178 135 255

	SetBorderColor 255 178 135 255

	SetBackgroundColor 20 20 0 255

	PlayEffect Orange Temp



Hide # $type->currency->heist $tier->exhide

	Class == "Stackable Currency"

	BaseType == "Rogue's Marker"

	SetFontSize 35

	SetBorderColor 0 0 0



Show # $type->currency->leagueexclusive $tier->silvercoin

	BaseType == "Silver Coin"

	SetFontSize 45

	SetTextColor 0 0 0 255

	SetBorderColor 0 0 0 255

	SetBackgroundColor 120 200 160 255

	PlayAlertSound 2 300

	PlayEffect Yellow

	MinimapIcon 1 Yellow Moon



#===============================================================================================================

# [[4000]] Currency - Regular Currency Tiering

#===============================================================================================================

# !! Waypoint c9.currency.single : "Tierlist - Currency - General" : "Currency and Currency-Likes"



Show # $type->currency $tier->t1exalted

	Class == "Stackable Currency"

	BaseType == "Albino Rhoa Feather" "Awakener's Orb" "Crusader's Exalted Orb" "Dextral Catalyst" "Divine Orb" "Eternal Orb" "Foulborn Exalted Orb" "Fracturing Orb" "Hinekora's Lock" "Hunter's Exalted Orb" "Mirror of Kalandra" "Mirror Shard" "Reflecting Mist" "Sacred Crystallised Lifeforce" "Valdo's Puzzle Box" "Veiled Exalted Orb" "Warlord's Exalted Orb"

	SetFontSize 45

	SetTextColor 255 0 0 255

	SetBorderColor 255 0 0 255

	SetBackgroundColor 255 255 255 255

	PlayAlertSound 6 300

	PlayEffect Red

	MinimapIcon 0 Red Star



Show # %H8 $type->currency $tier->t2divine

	Class == "Stackable Currency"

	BaseType == "Ancient Orb" "Chaotic Astrolabe" "Coin of Knowledge" "Coin of Power" "Coin of Skill" "Crystallised Rancour" "Deceptive Astrolabe" "Elder's Exalted Orb" "Eldritch Chaos Orb" "Eldritch Exalted Orb" "Eldritch Orb of Annulment" "Exceptional Eldritch Ember" "Exceptional Eldritch Ichor" "Fertile Catalyst" "Flesh of Xesht" "Fracturing Shard" "Fruiting Astrolabe" "Fungal Astrolabe" "Grasping Astrolabe" "Imperial Enshrouding Crystal" "Karui Enshrouding Crystal" "Lightless Astrolabe" "Maraketh Enshrouding Crystal" "Maven's Chisel of Avarice" "Maven's Chisel of Divination" "Maven's Chisel of Proliferation" "Maven's Chisel of Scarabs" "Memory of Loneliness" "Memory of Reverence" "Memory of Trauma" "Message in a Bottle" "Nameless Astrolabe" "Orb of Annulment" "Orb of Conflict" "Orb of Dominance" "Orb of Intention" "Orb of Remembrance" "Orb of Unravelling" "Prismatic Catalyst" "Redeemer's Exalted Orb" "Refracting Fog" "Ritual Vessel" "Runic Astrolabe" "Sacred Orb" "Shaper's Exalted Orb" "Sinistral Catalyst" "Tailoring Orb" "Tainted Catalyst" "Tainted Chaos Orb" "Tainted Divine Teardrop" "Tainted Exalted Orb" "Tainted Mythic Orb" "Tainted Orb of Fusing" "Tempering Orb" "Templar Astrolabe" "Templar Enshrouding Crystal" "Timeless Astrolabe" "Vaal Enshrouding Crystal" "Veiled Chaos Orb" "Volatile Vaal Orb"

	SetFontSize 45

	SetTextColor 255 255 255 255

	SetBorderColor 255 255 255 255

	SetBackgroundColor 240 90 35 255

	PlayAlertSound 1 300

	PlayEffect Red

	MinimapIcon 0 Red Circle



Show # %H7 $type->currency $tier->t3annul

	Class == "Stackable Currency"

	BaseType == "Accelerating Catalyst" "Blessed Orb" "Crescent Splinter" "Exalted Orb" "Exotic Coinage" "Foulborn Orb of Augmentation" "Foulborn Regal Orb" "Gemcutter's Prism" "Grand Eldritch Ember" "Grand Eldritch Ichor" "Greater Eldritch Ember" "Instilling Orb" "Maven's Chisel of Procurement" "Orb of Unmaking" "Stacked Deck" "Tainted Chromatic Orb" "Tempering Catalyst" "Unstable Catalyst"

	SetFontSize 45

	SetTextColor 0 0 0 255

	SetBorderColor 0 0 0 255

	SetBackgroundColor 240 90 35 255

	PlayAlertSound 2 300

	PlayEffect Yellow

	MinimapIcon 1 Yellow Circle



Show # %H6 $type->currency $tier->t4chaos

	Class == "Stackable Currency"

	BaseType == "Abrasive Catalyst" "Astragali" "Burial Medallion" "Chaos Orb" "Chromatic Orb" "Coin of Desecration" "Glassblower's Bauble" "Greater Eldritch Ichor" "Intrinsic Catalyst" "Lesser Eldritch Ember" "Lesser Eldritch Ichor" "Orb of Fusing" "Orb of Regret" "Ritual Splinter" "Scrap Metal" "Tainted Armourer's Scrap" "Tainted Blacksmith's Whetstone" "Tainted Jeweller's Orb" "Vaal Orb" "Veiled Scarab"

	SetFontSize 45

	SetTextColor 0 0 0 255

	SetBorderColor 0 0 0 255

	SetBackgroundColor 249 150 25 255

	PlayAlertSound 2 300

	PlayEffect White

	MinimapIcon 2 White Circle



Show # %HS4 $type->currency $tier->t5alchemy

	Class == "Stackable Currency"

	BaseType == "Coin of Restoration" "Enkindling Orb" "Imbued Catalyst" "Noxious Catalyst" "Orb of Alchemy" "Orb of Binding" "Orb of Scouring" "Regal Orb" "Turbulent Catalyst"

	SetFontSize 45

	SetTextColor 0 0 0 255

	SetBorderColor 0 0 0 255

	SetBackgroundColor 213 159 0 255

	PlayAlertSound 2 300

	PlayEffect White

	MinimapIcon 2 White Circle



Show # %HS3 $type->currency $tier->t6chrom

	Class == "Stackable Currency"

	BaseType == "Blacksmith's Whetstone" "Orb of Alteration" "Orb of Chance"

	SetFontSize 45

	SetTextColor 0 0 0 255

	SetBorderColor 0 0 0 255

	SetBackgroundColor 210 178 135 255

	PlayAlertSound 2 300

	PlayEffect Grey

	MinimapIcon 2 Grey Circle



Show # %HS2 $type->currency $tier->t7chance

	Class == "Stackable Currency"

	BaseType == "Armourer's Scrap" "Jeweller's Orb"

	SetFontSize 45

	SetTextColor 0 0 0 255

	SetBorderColor 0 0 0 255

	SetBackgroundColor 210 178 135 255



Show # %HS1 $type->currency $tier->t8trans

	Class == "Stackable Currency"

	BaseType == "Alchemy Shard" "Alteration Shard" "Orb of Transmutation"

	SetFontSize 45

	SetTextColor 190 178 135 255

	SetBorderColor 190 178 135 255

	SetBackgroundColor 20 20 0 255



Hide # %H1 $type->currency $tier->t9armour

	Class == "Stackable Currency"
"""

_REAL_POE2_SEMI_STRICT_EXCERPT = """Show # $type->currency $tier->s !apex_stier
	Class == "Incubators" "Stackable Currency"
	BaseType == "Albino Rhoa Feather" "Altered Collarbone" "Ancient Collarbone" "Ancient Jawbone" "Ancient Rib" "Divine Orb" "Fracturing Orb" "Hinekora's Lock" "Mirror of Kalandra" "Orb of Extraction" "Perfect Chaos Orb" "Perfect Exalted Orb" "Perfect Jeweller's Orb" "Vaal Cultivation Orb"
	SetFontSize 45
	SetTextColor 255 0 0 255
	SetBorderColor 255 0 0 255
	SetBackgroundColor 255 255 255 255
	PlayAlertSound 6 300
	PlayEffect Red
	MinimapIcon 0 Red Star

Show # %H8 $type->currency $tier->a !currency_a
	Class == "Incubators" "Stackable Currency"
	BaseType == "Architect's Orb" "Core Destabiliser" "Crystallised Corruption" "Kamasa's Orb of Sacrifice" "Kopec's Orb of Sacrifice" "Orb of Annulment" "Orb of Chance" "Perfect Regal Orb" "Preserved Collarbone" "Preserved Cranium" "Vaal Armourer's Infuser" "Vaal Blacksmith's Infuser" "Vaal Catalysing Infuser" "Yaomac's Orb of Sacrifice" "Yugul's Orb of Sacrifice"
	SetFontSize 45
	SetTextColor 255 255 255 255
	SetBorderColor 255 255 255 255
	SetBackgroundColor 245 105 90 255
	PlayAlertSound 1 300
	PlayEffect Red
	MinimapIcon 0 Red Circle

Show # %H7 $type->currency $tier->b !currency_b
	Class == "Incubators" "Stackable Currency"
	BaseType == "Ancient Infuser" "Chaos Orb" "Greater Chaos Orb" "Greater Exalted Orb" "Perfect Orb of Augmentation" "Perfect Orb of Transmutation" "Preserved Rib"
	SetFontSize 42
	SetTextColor 0 0 0 255
	SetBorderColor 0 0 0 255
	SetBackgroundColor 245 105 90 255
	PlayAlertSound 2 300
	PlayEffect Yellow
	MinimapIcon 1 Yellow Circle

Show # %H6 $type->currency $tier->c !currency_c
	Class == "Incubators" "Stackable Currency"
	BaseType == "Chance Shard" "Exalted Orb" "Gemcutter's Prism" "Glassblower's Bauble" "Gnawed Collarbone" "Greater Jeweller's Orb" "Greater Orb of Transmutation" "Greater Regal Orb" "Orb of Alchemy" "Vaal Arcanist's Infuser" "Vaal Orb"
	SetFontSize 42
	SetTextColor 0 0 0 255
	SetBorderColor 0 0 0 255
	SetBackgroundColor 245 139 87 255
	PlayAlertSound 2 300
	PlayEffect White
	MinimapIcon 1 Yellow Circle

Show # %H5 $type->currency $tier->d !currency_d
	Class == "Incubators" "Stackable Currency"
	BaseType == "Armourer's Scrap" "Artificer's Orb" "Blacksmith's Whetstone" "Gnawed Jawbone" "Gnawed Rib" "Greater Orb of Augmentation" "Preserved Jawbone" "Regal Orb" "Vaal Siphoner"
	SetFontSize 40
	SetTextColor 0 0 0 255
	SetBorderColor 0 0 0 255
	SetBackgroundColor 240 180 100 255
	PlayAlertSound 2 300
	PlayEffect White
	MinimapIcon 2 White Circle

Show # %H3 $type->currency $tier->e !currency_e
	Class == "Incubators" "Stackable Currency"
	BaseType == "Arcanist's Etcher" "Lesser Jeweller's Orb"
	SetFontSize 40
	SetTextColor 240 207 132
	SetBorderColor 240 207 132
	PlayEffect White Temp
	MinimapIcon 2 Grey Circle

Show # %H2 $type->currency $tier->supplymagic !currency_supply2
	Class == "Incubators" "Stackable Currency"
	BaseType == "Alchemy Shard" "Artificer's Shard" "Orb of Augmentation" "Orb of Transmutation" "Regal Shard"
	SetFontSize 38
	SetTextColor 220 175 132
	SetBorderColor 220 175 132

Hide # %H1 $type->currency $tier->supplieslow !currency_supply4
	Class == "Incubators" "Stackable Currency"
	BaseType == "Scroll of Wisdom" "Transmutation Shard"
"""


def test_find_anchor_block_resolves_all_default_anchors_on_real_poe1_filter():
    lines = _REAL_POE1_SEMI_STRICT_EXCERPT.split("\n")
    blocks = filter_gen._parse_blocks(lines)
    for tier_name, candidates in filter_gen._DEFAULT_RULES["anchors"].items():
        resolved = filter_gen._resolve_anchor(blocks, lines, candidates)
        assert resolved is not None, f"tier {tier_name} candidates {candidates!r} all failed to resolve on real PoE1 data"
        assert resolved[0].block_type == "Show"


def test_find_anchor_block_resolves_all_default_anchors_on_real_poe2_filter():
    lines = _REAL_POE2_SEMI_STRICT_EXCERPT.split("\n")
    blocks = filter_gen._parse_blocks(lines)
    for tier_name, candidates in filter_gen._DEFAULT_RULES["anchors"].items():
        resolved = filter_gen._resolve_anchor(blocks, lines, candidates)
        assert resolved is not None, f"tier {tier_name} candidates {candidates!r} all failed to resolve on real PoE2 data"
        assert resolved[0].block_type == "Show"


def test_merge_currency_into_base_surgery_applies_on_real_poe1_filter():
    """The actual regression: before the anchors["C"] fix, this returned
    applied=False (tier C anchor unresolvable) and currency was left 100%
    untouched in the real PoE1 base filter, every Generate run."""
    tiers = {"S": ["Divine Orb"], "A": ["Exalted Orb"], "B": ["Chaos Orb"],
             "C": ["Orb of Transmutation"]}
    new_text, applied = filter_gen.merge_currency_into_base(
        _REAL_POE1_SEMI_STRICT_EXCERPT, tiers, filter_gen.load_rules(None))
    assert applied is True


def test_merge_currency_into_base_surgery_still_applies_on_real_poe2_filter():
    """Same real-data check on PoE2 -- guards against the C-anchor fix
    accidentally regressing the game it was originally verified against."""
    tiers = {"S": ["Divine Orb"], "A": ["Exalted Orb"], "B": ["Chaos Orb"],
             "C": ["Orb of Transmutation"]}
    new_text, applied = filter_gen.merge_currency_into_base(
        _REAL_POE2_SEMI_STRICT_EXCERPT, tiers, filter_gen.load_rules(None))
    assert applied is True


def test_default_anchor_c_is_orb_of_transmutation_not_augmentation():
    """Pins the actual fix: Orb of Transmutation resolves in both real
    files, Orb of Augmentation only resolves on PoE2 (see module comment
    above) -- using the latter as the *first-choice* default breaks PoE1
    entirely. It's still first in tier C's candidate list; the rest are
    fallbacks for stricter NeverSink levels (2026-08-08, see
    tools/verify_anchors.py)."""
    assert filter_gen._DEFAULT_RULES["anchors"]["C"][0] == "Orb of Transmutation"


def test_whitelist_section_contains_selected_and_trailing_hide():
    out = filter_gen.build_whitelist_section(["Divine Orb", "Mirror of Kalandra"])
    assert out.startswith("# ") and "Show" in out
    assert '"Divine Orb"' in out and '"Mirror of Kalandra"' in out
    assert out.rstrip().splitlines()[-1] == "Hide"


def test_whitelist_section_empty_selection_returns_empty():
    assert filter_gen.build_whitelist_section([]) == ""


def test_whitelist_currencies_cover_both_games():
    assert set(filter_gen.WHITELIST_CURRENCIES) == {"poe1", "poe2"}
    for entries in filter_gen.WHITELIST_CURRENCIES.values():
        for label, bts in entries:
            assert label != "Gold" and bts
    assert filter_gen.GOLD_BASETYPES == ["Gold"]


def test_whitelist_two_blocks_when_unique_bases_given():
    out = filter_gen.build_whitelist_section(["Divine Orb"], ["Shortsword"])
    assert out.count("Show") == 2
    assert "Rarity Unique" in out and '"Shortsword"' in out
    assert out.rstrip().splitlines()[-1] == "Hide"
    assert filter_gen.build_whitelist_section([], []) == ""


def test_names_in_categories_ignores_price_and_case():
    hub = {"currency": [
        {"category": "Rune", "name": "Adept Rune", "divine_value": 0.0},
        {"category": "Omen", "name": "Omen of Chance"},
    ]}
    assert filter_gen.names_in_categories(hub, ["rune"]) == ["Adept Rune"]


def test_whitelist_three_blocks_with_typed_contains():
    out = filter_gen.build_whitelist_section(["Divine Orb"], ["Shortsword"], ["Heavy Belt"])
    assert out.count("Show") == 3
    assert '    BaseType "Heavy Belt"' in out          # no == -> substring match
    assert '    BaseType == "Divine Orb"' in out
    assert out.rstrip().splitlines()[-1] == "Hide"
    assert filter_gen.build_whitelist_section([], [], ["x"]) != ""


def test_expand_categories_applies_exclude_per_category():
    hub = {"currency": [
        {"category": "Rune", "name": "Adept Rune"},
        {"category": "Rune", "name": "Lesser Rune"},
        {"category": "Omen", "name": "Omen of Chance"},
    ]}
    got = filter_gen.expand_categories(hub, ["Rune", "Omen"], {"Rune": ["Adept Rune"]})
    assert sorted(got) == ["Lesser Rune", "Omen of Chance"]


def test_expand_categories_without_exclude_shows_whole_category():
    hub = {"currency": [{"category": "Rune", "name": "Adept Rune"},
                        {"category": "Rune", "name": "Lesser Rune"}]}
    assert sorted(filter_gen.expand_categories(hub, ["Rune"])) == ["Adept Rune", "Lesser Rune"]
    assert sorted(filter_gen.expand_categories(hub, ["Rune"], {})) == ["Adept Rune", "Lesser Rune"]


def test_typed_names_legacy_strings_have_no_rarity_line():
    out = filter_gen.build_whitelist_section([], None, ["Heavy Belt", "Sapphire"])
    assert out.count("Show") == 1
    assert '    BaseType "Heavy Belt" "Sapphire"' in out
    assert "Rarity" not in out


def test_typed_names_split_blocks_by_rarity_set():
    out = filter_gen.build_whitelist_section([], None, [
        {"name": "Heavy Belt", "rarities": ["Normal"]},
        {"name": "Vaal Regalia", "rarities": ["Unique", "Rare"]},
    ])
    assert out.count("Show") == 2
    assert "    Rarity Normal" in out and "    Rarity Rare Unique" in out
    assert out.index('"Heavy Belt"') < out.index('"Vaal Regalia"')
    assert out.rstrip().splitlines()[-1] == "Hide"


def test_typed_names_empty_rarities_fall_back_to_any():
    out = filter_gen.build_whitelist_section([], None, [{"name": "Heavy Belt", "rarities": []}])
    assert "Rarity" not in out and '"Heavy Belt"' in out
