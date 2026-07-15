"""Tests for MetaDB's tier_range / tags_for_template / summary — offline,
self-contained fixture (field shapes match a real mod_meta.json pull, verified
against "Knightly Mitts" 2026-07-16)."""
import json

import pytest

from poe_price_trade.meta_db import MetaDB

_FIXTURE = {
    "generated": "2026-07-16T00:00:00+00:00",
    "source": "test-fixture",
    "bases": {
        "Knightly Mitts": {"class": "Gloves", "drop_level": 65, "ts": 1},
        "Ruby": {"class": "Jewel", "drop_level": 20, "ts": 2},
    },
    "tagsets": {
        "1": [
            {
                "gen": "prefix", "text": "# to maximum life",
                "stats": ["base_maximum_life"],
                "tiers": [
                    {"lvl": 60, "rng": [[120, 149]]},
                    {"lvl": 54, "rng": [[100, 119]]},
                    {"lvl": 1, "rng": [[10, 19]]},
                ],
                "tags": ["life", "resource"],
            },
            {
                "gen": "suffix", "text": "#% to fire resistance",
                "stats": ["fire_resistance"],
                "tiers": [
                    {"lvl": 40, "rng": [[36, 40]]},
                    {"lvl": 1, "rng": [[10, 15]]},
                ],
                "tags": ["elemental", "elemental_resistance", "fire", "fire_resistance", "resistance"],
            },
        ],
        "2": [
            {
                "gen": "prefix", "text": "#% increased spell damage",
                "stats": ["spell_damage_+%"],
                "tiers": [{"lvl": 1, "rng": [[10, 20]]}],
                "tags": ["caster", "caster_damage", "damage"],
            },
        ],
    },
}


@pytest.fixture
def db(tmp_path):
    (tmp_path / "mod_meta.json").write_text(json.dumps(_FIXTURE), encoding="utf-8")
    return MetaDB(tmp_path)


def test_tier_range_known_tier(db):
    rng = db.tier_range("Knightly Mitts", "+47 to maximum Life", tier=3)
    assert rng == [[10, 19]]


def test_tier_range_tier1_is_first_entry(db):
    rng = db.tier_range("Knightly Mitts", "+47 to maximum Life", tier=1)
    assert rng == [[120, 149]]


def test_tier_range_unknown_base_returns_none(db):
    assert db.tier_range("Nonexistent Base", "+47 to maximum Life", tier=1) is None


def test_tier_range_tier_zero_returns_none(db):
    assert db.tier_range("Knightly Mitts", "+47 to maximum Life", tier=0) is None


def test_tier_range_tier_beyond_ladder_returns_none(db):
    assert db.tier_range("Knightly Mitts", "+47 to maximum Life", tier=99) is None


def test_tags_for_template_known(db):
    assert db.tags_for_template("# to maximum life") == {"life", "resource"}
    assert "fire" in db.tags_for_template("#% to fire resistance")


def test_tags_for_template_unknown_returns_empty_set(db):
    assert db.tags_for_template("#% totally unknown mod") == set()


def test_tags_for_template_works_across_tagsets_not_just_current_base(db):
    """tags are mod-line-intrinsic, not base-type-specific -- a jewel-only mod's
    tags must still resolve even though we're not querying via a jewel base."""
    assert "caster" in db.tags_for_template("#% increased spell damage")


def test_summary_prefix_suffix_format_and_custom_caps():
    class FakeItem:
        rarity = "Rare"
        item_level = 78
        prefix_count = 2
        suffix_count = 1
    s = MetaDB.summary(FakeItem(), {}, prefix_cap=3, suffix_cap=3)
    assert "Prefix 2/3" in s
    assert "Suffix 1/3" in s


def test_summary_jewel_cap_1_1():
    class FakeItem:
        rarity = "Rare"
        item_level = 20
        prefix_count = 1
        suffix_count = 0
    s = MetaDB.summary(FakeItem(), {}, prefix_cap=1, suffix_cap=1)
    assert "Prefix 1/1" in s
    assert "Suffix 0/1" in s
