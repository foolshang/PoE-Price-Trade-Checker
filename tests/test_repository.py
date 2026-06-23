"""Offline tests for PriceRepository — uses mocked NinjaClient."""
import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from poe_price_trade.models import PriceEntry, PriceSnapshot
from poe_price_trade.profiles import POE1_PROFILE
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

    # Second repo should load from cache without hitting network
    repo2 = PriceRepository(POE1_PROFILE, cache_dir=tmp_path)
    with patch.object(repo2._client, "fetch_all", side_effect=AssertionError("Should not hit network")):
        repo2.load("Standard")  # should not raise
    assert repo2.is_ready()


def test_entry_count(repo_with_data):
    assert repo_with_data.entry_count() == 3
