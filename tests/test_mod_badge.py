"""Offline tests for mod_badge.py — mock hub_client, no network.
Fixture field names match a real poe2/meta/latest.json pull (2026-07-14)."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from poe_price_trade.mod_badge import ModBadgeDB, slot_for_item, _build_template_index


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _meta_payload(generated_at=None, mods=None, stat_dictionary=None):
    return {
        "schema_version": 2,
        "generated_at": generated_at if generated_at is not None else _now_iso(),
        "league": "Runes of Aldur",
        "mods": mods if mods is not None else [],
        "stat_dictionary": stat_dictionary if stat_dictionary is not None else [],
    }


# ------------------------------------------------------------------
# slot_for_item
# ------------------------------------------------------------------

def test_slot_for_item_regular_gear():
    assert slot_for_item("Gloves", "Knightly Mitts") == "gloves"
    assert slot_for_item("Boots", "Slink Boots") == "boots"
    assert slot_for_item("Amulets", "Jade Amulet") == "amulet"


def test_slot_for_item_weapon_class():
    assert slot_for_item("Bows", "Composite Bow") == "weapon"
    assert slot_for_item("Two Hand Swords", "Longsword") == "weapon"


def test_slot_for_item_jewel_base_slug_matches_hub_convention():
    # mirrors hub's _slugify_jewel_base: lowercase, strip non a-z0-9
    assert slot_for_item("Jewel", "Emerald") == "jewel:emerald"
    assert slot_for_item("Jewels", "Ruby") == "jewel:ruby"
    assert slot_for_item("Jewel", "Timeless Jewel") == "jewel:timelessjewel"
    assert slot_for_item("Jewel", "Time-Lost Sapphire") == "jewel:timelostsapphire"


def test_slot_for_item_unknown_class_returns_none():
    assert slot_for_item("Stackable Currency", "Chaos Orb") is None
    assert slot_for_item("Maps", "Crypt Map") is None


# ------------------------------------------------------------------
# _build_template_index — duplicate stat_id in stat_dictionary
# ------------------------------------------------------------------

def test_build_template_index_groups_multiple_templates_per_stat_id():
    # one stat_id, two different templates (e.g. positive/negative phrasing) --
    # must not silently overwrite either direction
    sd = [
        {"stat_id": "explicit.stat_1", "template": "#% increased Armour", "mod_kind": "explicit"},
        {"stat_id": "explicit.stat_1", "template": "#% reduced Armour", "mod_kind": "explicit"},
        {"stat_id": "explicit.stat_2", "template": "# to maximum Life", "mod_kind": "explicit"},
    ]
    idx = _build_template_index(sd)
    assert idx["#% increased armour"] == ["explicit.stat_1"]
    assert idx["#% reduced armour"] == ["explicit.stat_1"]
    assert idx["# to maximum life"] == ["explicit.stat_2"]


def test_build_template_index_same_template_multiple_stat_ids_stays_ambiguous():
    sd = [
        {"stat_id": "explicit.stat_a", "template": "#% to Fire Resistance", "mod_kind": "explicit"},
        {"stat_id": "explicit.stat_b", "template": "#% to Fire Resistance", "mod_kind": "explicit"},
    ]
    idx = _build_template_index(sd)
    assert set(idx["#% to fire resistance"]) == {"explicit.stat_a", "explicit.stat_b"}


# ------------------------------------------------------------------
# ModBadgeDB.resolve_stat_id — mod_db first, stat_dictionary fallback
# ------------------------------------------------------------------

def test_resolve_stat_id_prefers_mod_db():
    db = ModBadgeDB()
    db._index(_meta_payload(stat_dictionary=[
        {"stat_id": "explicit.stat_fallback", "template": "# to maximum Life", "mod_kind": "explicit"},
    ]))
    mod_db = MagicMock()
    mod_db.find_stat_id.return_value = "explicit.stat_3299347043"
    sid = db.resolve_stat_id("+47 to maximum Life", "explicit", mod_db)
    assert sid == "explicit.stat_3299347043"


def test_resolve_stat_id_falls_back_to_stat_dictionary_when_unambiguous():
    db = ModBadgeDB()
    db._index(_meta_payload(stat_dictionary=[
        {"stat_id": "explicit.stat_fallback", "template": "# to maximum Life", "mod_kind": "explicit"},
    ]))
    mod_db = MagicMock()
    mod_db.find_stat_id.return_value = None
    sid = db.resolve_stat_id("+47 to maximum Life", "explicit", mod_db)
    assert sid == "explicit.stat_fallback"


def test_resolve_stat_id_ambiguous_fallback_returns_none():
    db = ModBadgeDB()
    db._index(_meta_payload(stat_dictionary=[
        {"stat_id": "explicit.stat_a", "template": "#% to Fire Resistance", "mod_kind": "explicit"},
        {"stat_id": "explicit.stat_b", "template": "#% to Fire Resistance", "mod_kind": "explicit"},
    ]))
    mod_db = MagicMock()
    mod_db.find_stat_id.return_value = None
    sid = db.resolve_stat_id("+36% to Fire Resistance", "explicit", mod_db)
    assert sid is None


# ------------------------------------------------------------------
# badge_color — rank/usage thresholds, archetype fallback
# ------------------------------------------------------------------

_SAMPLE_MODS = [
    {"slot": "helmet", "archetype": "all", "stat_id": "s.red_rank", "rank_in_slot": 1, "usage_pct": 20.0},
    {"slot": "helmet", "archetype": "all", "stat_id": "s.red_usage", "rank_in_slot": 40, "usage_pct": 55.0},
    {"slot": "helmet", "archetype": "all", "stat_id": "s.gold_rank", "rank_in_slot": 10, "usage_pct": 8.0},
    {"slot": "helmet", "archetype": "all", "stat_id": "s.white", "rank_in_slot": 50, "usage_pct": 1.0},
    {"slot": "helmet", "archetype": "attack-melee", "stat_id": "s.melee_only", "rank_in_slot": 2, "usage_pct": 60.0},
]


def _db_with_sample():
    db = ModBadgeDB()
    db._index(_meta_payload(mods=_SAMPLE_MODS))
    return db


def test_badge_color_red_by_rank():
    db = _db_with_sample()
    assert db.badge_color("s.red_rank", "helmet", "all") == "#FF4444"


def test_badge_color_red_by_usage_pct():
    db = _db_with_sample()
    assert db.badge_color("s.red_usage", "helmet", "all") == "#FF4444"


def test_badge_color_gold():
    db = _db_with_sample()
    assert db.badge_color("s.gold_rank", "helmet", "all") == "#FFB800"


def test_badge_color_white_none():
    db = _db_with_sample()
    assert db.badge_color("s.white", "helmet", "all") is None


def test_badge_color_unmatched_stat_id_is_none():
    db = _db_with_sample()
    assert db.badge_color("s.does_not_exist", "helmet", "all") is None


def test_badge_color_archetype_specific_row_used_when_present():
    db = _db_with_sample()
    assert db.badge_color("s.melee_only", "helmet", "attack-melee") == "#FF4444"


def test_badge_color_archetype_fallback_to_all_when_no_specific_row():
    db = _db_with_sample()
    # s.red_rank only has an "all" row -- selecting attack-melee must still find it
    assert db.badge_color("s.red_rank", "helmet", "attack-melee") == "#FF4444"


def test_badge_color_custom_rules_override():
    db = ModBadgeDB()
    db._index(_meta_payload(mods=_SAMPLE_MODS))
    db._rules = {
        "red": {"max_rank": 1, "min_usage_pct": 99.0},
        "gold": {"max_rank": 2, "min_usage_pct": 90.0},
        "colors": {"red": "#111111", "gold": "#222222"},
    }
    # rank 10 no longer qualifies for gold under the tightened custom rule
    assert db.badge_color("s.gold_rank", "helmet", "all") is None
    assert db.badge_color("s.red_rank", "helmet", "all") == "#111111"


# ------------------------------------------------------------------
# load() — disk cache, staleness, graceful degrade
# ------------------------------------------------------------------

def test_load_uses_fresh_disk_cache_without_hitting_hub(tmp_path):
    db = ModBadgeDB(cache_dir=tmp_path)
    db._save_disk_cache(_meta_payload(mods=_SAMPLE_MODS))
    with patch("poe_price_trade.mod_badge.hub_client.get_meta",
               side_effect=AssertionError("should not hit network")):
        db.load()
    assert db.available()
    assert db.badge_color("s.red_rank", "helmet", "all") == "#FF4444"


def test_load_refetches_when_disk_cache_stale(tmp_path):
    db = ModBadgeDB(cache_dir=tmp_path)
    old = (datetime.now(timezone.utc) - timedelta(hours=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    db._save_disk_cache(_meta_payload(generated_at=old, mods=[]))
    fresh = _meta_payload(mods=_SAMPLE_MODS)
    with patch("poe_price_trade.mod_badge.hub_client.get_meta", return_value=fresh) as m:
        db.load()
    m.assert_called_once_with("poe2")
    assert db.badge_color("s.red_rank", "helmet", "all") == "#FF4444"


def test_load_falls_back_to_stale_disk_cache_when_hub_unreachable(tmp_path):
    db = ModBadgeDB(cache_dir=tmp_path)
    old = (datetime.now(timezone.utc) - timedelta(hours=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    db._save_disk_cache(_meta_payload(generated_at=old, mods=_SAMPLE_MODS))
    with patch("poe_price_trade.mod_badge.hub_client.get_meta", return_value=None):
        db.load()
    assert db.available()   # stale but present beats nothing


def test_load_no_cache_no_network_degrades_silently(tmp_path):
    db = ModBadgeDB(cache_dir=tmp_path)
    with patch("poe_price_trade.mod_badge.hub_client.get_meta", return_value=None):
        db.load()   # must not raise
    assert not db.available()
    assert db.badge_color("s.anything", "helmet", "all") is None


# ------------------------------------------------------------------
# mod_badge_rules.json override
# ------------------------------------------------------------------

def test_config_dir_rules_override_loaded(tmp_path):
    import json
    (tmp_path / "mod_badge_rules.json").write_text(json.dumps({
        "red": {"max_rank": 1, "min_usage_pct": 99.0},
        "gold": {"max_rank": 2, "min_usage_pct": 90.0},
        "colors": {"red": "#ABCDEF", "gold": "#FEDCBA"},
    }), encoding="utf-8")
    db = ModBadgeDB(config_dir=tmp_path)
    db._index(_meta_payload(mods=_SAMPLE_MODS))
    assert db.badge_color("s.red_rank", "helmet", "all") == "#ABCDEF"
    assert db.badge_color("s.gold_rank", "helmet", "all") is None   # tightened rule excludes it
