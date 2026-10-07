"""Offline tests for hub_client's index.json -> league routing reshape.
Fixture shapes match D:\\Projects\\Poe_Hub\\SPEC.md 8.1b exactly (including
the phase-9 `hardcore` key and its null case)."""
from unittest.mock import patch

from poe_price_trade import hub_client


def _index(**overrides):
    idx = {
        "schema_version": 1,
        "generated_at": "2026-07-13T15:32:25Z",
        "main": {
            "league": "Mirage",
            "path": "poe1/prices/latest.json",
            "generated_at": "2026-07-13T15:30:41Z",
        },
        "events": [],
        "hardcore": {
            "league": "Hardcore Mirage",
            "path": "poe1/prices/hardcore/latest.json",
            "generated_at": "2026-07-13T15:32:21Z",
        },
    }
    idx.update(overrides)
    return idx


def test_get_league_files_with_hardcore_and_event():
    idx = _index(events=[{
        "league": "Ancestors",
        "path": "poe1/prices/events/ancestors.json",
        "generated_at": "2026-07-13T15:31:33Z",
    }])
    with patch("poe_price_trade.hub_client._get", return_value=idx):
        result = hub_client.get_league_files("poe1")

    assert result["main"] == {"league": "Mirage", "path": "poe1/prices/latest.json"}
    assert result["hardcore"] == {"league": "Hardcore Mirage", "path": "poe1/prices/hardcore/latest.json"}
    assert result["events"] == [{"league": "Ancestors", "path": "poe1/prices/events/ancestors.json"}]


def test_get_league_files_hardcore_null_falls_back_to_none():
    idx = _index(hardcore=None)
    with patch("poe_price_trade.hub_client._get", return_value=idx):
        result = hub_client.get_league_files("poe2")

    assert result["hardcore"] is None
    assert result["main"]["league"] == "Mirage"


def test_get_league_files_index_unavailable_falls_back_to_latest_league_field():
    def _fake_get(path: str):
        if path.endswith("index.json"):
            raise RuntimeError("hub HTTP 404")
        assert path == "poe2/prices/latest.json"
        return {"schema_version": 2, "league": "Runes of Aldur", "currency": [], "items": []}

    with patch("poe_price_trade.hub_client._get", side_effect=_fake_get):
        result = hub_client.get_league_files("poe2")

    assert result["main"] == {"league": "Runes of Aldur", "path": "poe2/prices/latest.json"}
    assert result["hardcore"] is None
    assert result["events"] == []


def test_get_league_files_totally_unreachable_returns_none_league():
    with patch("poe_price_trade.hub_client._get", side_effect=RuntimeError("network down")):
        result = hub_client.get_league_files("poe1")

    assert result["main"]["league"] is None
    assert result["hardcore"] is None
    assert result["events"] == []


def test_get_index_returns_none_on_failure_not_raise():
    with patch("poe_price_trade.hub_client._get", side_effect=RuntimeError("boom")):
        assert hub_client.get_index("poe1") is None


def test_get_prices_fetches_exact_path():
    with patch("poe_price_trade.hub_client._get", return_value={"league": "Mirage"}) as m:
        data = hub_client.get_prices("poe1/prices/hardcore/latest.json")
    m.assert_called_once_with("poe1/prices/hardcore/latest.json")
    assert data["league"] == "Mirage"


def test_hub_chaos_value_rule():
    f = hub_client.hub_chaos_value
    assert f({"value": 5.0, "value_currency": "chaos"}) == 5.0                          # poe1: value is chaos
    assert f({"value": 5.0, "value_currency": "exalted", "chaos_value": 2.5}) == 2.5      # poe2: the additive field
    assert f({"value": 5.0, "value_currency": "chaos", "chaos_value": 7.0}) == 7.0        # additive field wins
    assert f({"value": 5.0, "value_currency": "exalted"}) == 0.0                          # no conversion is guessed
    assert f({}) == 0.0 and f({"chaos_value": None, "value": None, "value_currency": "chaos"}) == 0.0


def test_repository_prices_poe1_payloads_in_chaos(tmp_path):
    from poe_price_trade.profiles import POE1_PROFILE
    from poe_price_trade.repository import PriceRepository
    payload = {"currency": [{"category": "Currency", "name": "Divine Orb", "value": 371.8,
                             "value_currency": "chaos", "divine_value": 1.0}],
               "items": [{"category": "UniqueWeapon", "name": "Widowmaker", "base": "Royal Axe", "value": 300.0,
                          "value_currency": "chaos", "divine_value": 0.8}]}
    repo = PriceRepository(POE1_PROFILE, cache_dir=tmp_path)
    by = {e.item_name: e.chaos_value for e in repo._entries_from_hub_payload(payload)}
    assert by == {"Divine Orb": 371.8, "Widowmaker": 300.0}
