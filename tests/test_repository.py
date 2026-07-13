"""Offline tests for PriceRepository — uses mocked hub_client (no network)."""
from datetime import datetime
from unittest.mock import patch

import pytest

from poe_price_trade.models import PriceEntry, PriceSnapshot
from poe_price_trade.profiles import POE1_PROFILE, POE2_PROFILE
from poe_price_trade.repository import PriceRepository


def _make_snapshot(entries=None):
    if entries is None:
        entries = [
            PriceEntry("Divine Orb", "divine orb", 200.0, 1.0, 300, "poe1", "Currency", "divine"),
            PriceEntry("Chaos Orb",  "chaos orb",  1.0,   0.005, 500, "poe1", "Currency", "chaos"),
            PriceEntry("Exalted Orb","exalted orb",50.0,  0.25, 150, "poe1", "Currency", "exalted"),
        ]
    return PriceSnapshot(entries=entries, fetched_at=datetime.now(), league="Standard", game_version="poe1")


@pytest.fixture
def repo_with_data(tmp_path):
    repo = PriceRepository(POE1_PROFILE, cache_dir=tmp_path)
    snapshot = _make_snapshot()
    repo._apply_snapshot(snapshot)
    return repo


def test_lookup_exact(repo_with_data):
    result = repo_with_data.lookup("Divine Orb")
    assert result is not None
    assert result.chaos_value == 200.0


def test_lookup_fuzzy(repo_with_data):
    result = repo_with_data.lookup("Chaos 0rb", threshold=0.70)
    assert result is not None
    assert "Chaos" in result.item_name


def test_lookup_miss(repo_with_data):
    result = repo_with_data.lookup("nonsense item xyz", threshold=0.90)
    assert result is None


def test_is_ready(repo_with_data):
    assert repo_with_data.is_ready()


def test_divine_chaos_rate(repo_with_data):
    assert repo_with_data.divine_chaos_rate() == 200.0


def test_disk_cache_roundtrip(tmp_path):
    repo = PriceRepository(POE1_PROFILE, cache_dir=tmp_path)
    snapshot = _make_snapshot()
    repo._save_disk_cache(snapshot, "Standard")
    loaded = repo._load_disk_cache("Standard")
    assert loaded is not None
    assert len(loaded.entries) == 3
    names = {e.item_name for e in loaded.entries}
    assert "Divine Orb" in names


def test_load_uses_disk_cache(tmp_path):
    # Pre-populate cache
    repo1 = PriceRepository(POE1_PROFILE, cache_dir=tmp_path)
    repo1._save_disk_cache(_make_snapshot(), "Standard")

    # Second repo should load from cache without hitting the hub, since the
    # cached snapshot isn't stale (freshly written above).
    repo2 = PriceRepository(POE1_PROFILE, cache_dir=tmp_path)
    with patch("poe_price_trade.repository.hub_client.get_prices",
               side_effect=AssertionError("Should not hit network")):
        repo2.load("Standard", "poe1/prices/latest.json")  # should not raise
    assert repo2.is_ready()


def test_entry_count(repo_with_data):
    assert repo_with_data.entry_count() == 3


# ------------------------------------------------------------------
# hub payload reshaping — real-shaped fixtures per the migration survey
# ------------------------------------------------------------------

def _hub_payload(**overrides):
    payload = {
        "schema_version": 2,
        "generated_at": "2026-07-13T12:00:00Z",
        "league": "Mirage",
        "sources": {"ninja": "ok"},
        "sample": {"per_category": {"ninja": {"Currency": {"ok": True, "count": 2}}}},
        "currency": [
            {
                "category": "Currency", "name": "Divine Orb", "base": None,
                "value": 200.0, "value_currency": "chaos", "divine_value": 1.0,
                "source": "ninja", "listing_count": 12345,
                "trade_id": "divine-orb", "icon_url": "/gen/image/divine.png",
            },
        ],
        "items": [],
    }
    payload.update(overrides)
    return payload


def test_entries_from_hub_payload_poe1_chaos_primary():
    repo = PriceRepository(POE1_PROFILE)
    entries = repo._entries_from_hub_payload(_hub_payload())
    assert len(entries) == 1
    e = entries[0]
    assert e.item_name == "Divine Orb"
    assert e.chaos_value == 200.0
    assert e.divine_value == 1.0
    assert e.exalted_value == 0.0
    assert e.stale is False


def test_entries_from_hub_payload_poe2_exalted_primary_and_chaos_value():
    repo = PriceRepository(POE2_PROFILE)
    payload = _hub_payload(currency=[{
        "category": "Currency", "name": "Chaos Orb", "base": None,
        "value": 63.77, "value_currency": "exalted", "divine_value": 0.1232,
        "chaos_value": 1.0, "source": "ninja", "listing_count": 217834,
        "trade_id": "chaos-orb", "icon_url": "https://web.poecdn.com/x.png",
    }])
    entries = repo._entries_from_hub_payload(payload)
    e = entries[0]
    assert e.exalted_value == 63.77
    assert e.chaos_value == 1.0   # additive chaos_value field, not derived from value


def test_entries_from_hub_payload_missing_listing_count_defaults_zero():
    repo = PriceRepository(POE2_PROFILE)
    payload = _hub_payload(currency=[{
        "category": "Currency", "name": "Glassblower's Bauble", "base": None,
        "value": 1.99, "value_currency": "exalted", "divine_value": 0.0038,
        "source": "ninja",   # no listing_count key at all
        "trade_id": "glassblowers-bauble", "icon_url": None,
    }])
    entries = repo._entries_from_hub_payload(payload)
    assert entries[0].listing_count == 0


def test_entries_from_hub_payload_stale_flag_propagates():
    repo = PriceRepository(POE1_PROFILE)
    payload = _hub_payload(currency=[{
        "category": "Currency", "name": "Chaos Orb", "base": None,
        "value": 1.0, "value_currency": "chaos", "divine_value": 0.005,
        "source": "ninja", "listing_count": 500,
        "trade_id": "chaos-orb", "icon_url": None, "stale": True,
    }])
    entries = repo._entries_from_hub_payload(payload)
    assert entries[0].stale is True


def test_entries_from_hub_payload_duplicate_names_dedupe_keeps_highest_listing_count():
    """currency[]+items[] can carry the same `name` twice (link/variant rows) —
    ItemMatcher's existing normalized_name dedup (highest listing_count wins)
    handles this exactly as it did for raw poe.ninja lines."""
    repo = PriceRepository(POE1_PROFILE)
    payload = _hub_payload(items=[
        {
            "category": "UniqueWeapon", "name": "The Winds of Fate", "base": "Foul Staff",
            "value": 110266.0, "value_currency": "chaos", "divine_value": 202.1,
            "source": "ninja", "listing_count": 9,
            "trade_id": "the-winds-of-fate-foul-staff-6l", "icon_url": None,
        },
        {
            "category": "UniqueWeapon", "name": "The Winds of Fate", "base": "Foul Staff",
            "value": 107210.0, "value_currency": "chaos", "divine_value": 196.5,
            "source": "ninja", "listing_count": 40,
            "trade_id": "the-winds-of-fate-foul-staff", "icon_url": None,
        },
    ])
    entries = repo._entries_from_hub_payload(payload)
    assert len(entries) == 3   # divine orb + both variants still both present pre-dedupe

    from poe_price_trade.matcher import ItemMatcher
    matcher = ItemMatcher(entries)
    result = matcher.find("The Winds of Fate")
    assert result is not None
    assert result.listing_count == 40   # matcher kept the higher-listing_count variant


def test_compute_degraded_reads_sample_per_category():
    payload = _hub_payload(sample={
        "per_category": {
            "ninja": {
                "Currency": {"ok": True, "count": 137},
                "UniqueWeapon": {"ok": False, "count": 0},
            },
            "scout": {"Currency": {"ok": True, "count": 90}},
        }
    })
    degraded = PriceRepository._compute_degraded(payload)
    assert degraded == ["ninja:UniqueWeapon"]


def test_load_from_hub_mocked_and_sets_degraded(tmp_path):
    repo = PriceRepository(POE1_PROFILE, cache_dir=tmp_path)
    payload = _hub_payload(sample={
        "per_category": {"ninja": {"UniqueWeapon": {"ok": False, "count": 0}}}
    })
    with patch("poe_price_trade.repository.hub_client.get_prices", return_value=payload):
        repo.load("Mirage", "poe1/prices/latest.json")
    assert repo.is_ready()
    assert repo.entry_count() == 1
    assert repo.degraded() == ["ninja:UniqueWeapon"]


def test_load_falls_back_to_stale_disk_cache_on_hub_failure(tmp_path):
    repo = PriceRepository(POE1_PROFILE, cache_dir=tmp_path)
    old_snapshot = _make_snapshot()
    repo._save_disk_cache(old_snapshot, "Mirage")

    with patch("poe_price_trade.repository.hub_client.get_prices",
               side_effect=RuntimeError("hub down")):
        repo.load("Mirage", "poe1/prices/latest.json", force=True)  # should not raise

    assert repo.is_ready()
    assert repo.entry_count() == 3   # still serving the old disk-cached snapshot
