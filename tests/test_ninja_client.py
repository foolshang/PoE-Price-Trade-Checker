"""Offline tests for poe.ninja JSON parsing — no network calls."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from poe_price_trade.ninja_client import (
    _parse_currency_overview,
    _parse_item_overview,
    _parse_exchange_overview,
    NinjaClient,
)
from poe_price_trade.profiles import POE1_PROFILE, POE2_PROFILE

SAMPLE_DIR = Path(__file__).parent / "sample_data"


@pytest.fixture
def poe1_currency_data():
    with open(SAMPLE_DIR / "ninja_poe1_currency.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def poe2_currency_data():
    with open(SAMPLE_DIR / "ninja_poe2_currency.json", encoding="utf-8") as f:
        return json.load(f)


def test_parse_poe1_currency(poe1_currency_data):
    entries = _parse_currency_overview(poe1_currency_data, "Currency", "poe1")
    assert len(entries) == 5
    chaos = next(e for e in entries if e.item_name == "Chaos Orb")
    assert chaos.chaos_value == 1.0
    divine = next(e for e in entries if e.item_name == "Divine Orb")
    assert divine.chaos_value == 200.0
    assert divine.game_version == "poe1"


def test_parse_poe1_divine_value_computed(poe1_currency_data):
    entries = _parse_currency_overview(poe1_currency_data, "Currency", "poe1")
    chaos = next(e for e in entries if e.item_name == "Chaos Orb")
    # chaos_value=1, divine=200 → divine_value = 1/200 = 0.005
    assert abs(chaos.divine_value - 0.005) < 0.001


def test_parse_poe1_trade_id(poe1_currency_data):
    entries = _parse_currency_overview(poe1_currency_data, "Currency", "poe1")
    divine = next(e for e in entries if e.item_name == "Divine Orb")
    assert divine.trade_id == "divine"


def test_parse_poe2_currency(poe2_currency_data):
    entries = _parse_currency_overview(poe2_currency_data, "Currency", "poe2")
    assert len(entries) == 4
    divine = next(e for e in entries if e.item_name == "Divine Orb")
    assert divine.chaos_value == 150.0
    assert divine.game_version == "poe2"


def test_exchange_overview_falls_back_to_currency(poe2_currency_data):
    entries = _parse_exchange_overview(poe2_currency_data, "Currency", "poe2")
    assert len(entries) == 4


def test_normalized_name_is_lowercase(poe1_currency_data):
    entries = _parse_currency_overview(poe1_currency_data, "Currency", "poe1")
    for e in entries:
        assert e.normalized_name == e.normalized_name.lower()


def test_ninja_client_fetch_all_offline(poe1_currency_data):
    """NinjaClient.fetch_all with mocked _get — no network."""
    client = NinjaClient(POE1_PROFILE)
    with patch("poe_price_trade.ninja_client._get", return_value=poe1_currency_data):
        snapshot = client.fetch_all("Settlers")
    assert snapshot.game_version == "poe1"
    assert snapshot.league == "Settlers"
    # We mocked all categories to return same fixture, so should have many entries
    assert len(snapshot.entries) > 0
