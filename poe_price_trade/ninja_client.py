"""Fetch prices from poe.ninja. Supports PoE1 (currencyoverview/itemoverview)
and PoE2 (exchange/current/overview). No external deps — stdlib only."""
from __future__ import annotations
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Optional

from .models import GameVersion, PriceEntry, PriceSnapshot
from .normalizer import normalize
from .profiles import CategoryConfig, GameProfile

log = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://poe.ninja/",
    "Accept": "application/json, */*",
    "Accept-Language": "en-US,en;q=0.9",
}
_TIMEOUT = 15


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = resp.read()
            return json.loads(data)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"poe.ninja HTTP {e.code}: {url}") from e
    except Exception as e:
        raise RuntimeError(f"poe.ninja fetch failed ({url}): {e}") from e


def _parse_currency_overview(data: dict, category: str, game_version: str) -> list[PriceEntry]:
    """PoE1 currencyoverview JSON: {"lines": [{"currencyTypeName": ..., "chaosEquivalent": ...}]}"""
    entries = []
    divine_chaos = 1.0

    lines = data.get("lines", [])
    # Find divine-orb rate to compute divine_value
    for line in lines:
        name = line.get("currencyTypeName", "")
        if name.lower() in ("divine orb",):
            divine_chaos = line.get("chaosEquivalent", 1.0) or 1.0

    # Build detail index for icon/tradeId
    details: dict[str, dict] = {}
    for d in data.get("currencyDetails", []):
        n = d.get("name", "")
        if n:
            details[n] = d

    for line in lines:
        name = line.get("currencyTypeName", "").strip()
        if not name:
            continue
        chaos = float(line.get("chaosEquivalent", 0) or 0)
        detail = details.get(name, {})
        entries.append(PriceEntry(
            item_name=name,
            normalized_name=normalize(name),
            chaos_value=chaos,
            divine_value=chaos / divine_chaos if divine_chaos else 0.0,
            listing_count=int(line.get("count", 0) or 0),
            game_version=game_version,
            category=category,
            trade_id=detail.get("tradeId"),
            icon_url=detail.get("icon"),
        ))
    return entries


def _parse_item_overview(data: dict, category: str, game_version: str) -> list[PriceEntry]:
    """PoE1 itemoverview JSON: {"lines": [{"name": ..., "chaosValue": ..., "divineValue": ...}]}"""
    entries = []
    for line in data.get("lines", []):
        name = line.get("name", "").strip()
        if not name:
            continue
        chaos = float(line.get("chaosValue", 0) or 0)
        divine = float(line.get("divineValue", 0) or 0)
        entries.append(PriceEntry(
            item_name=name,
            normalized_name=normalize(name),
            chaos_value=chaos,
            divine_value=divine,
            listing_count=int(line.get("listingCount", 0) or 0),
            game_version=game_version,
            category=category,
            trade_id=line.get("detailsId"),
            icon_url=line.get("icon"),
        ))
    return entries


def _parse_exchange_overview(data: dict, category: str, game_version: str) -> list[PriceEntry]:
    """PoE2 exchange overview. Tries 'lines' key first (same as PoE1), then 'result' dict.
    Since the PoE2 endpoint is not guaranteed stable, fall back gracefully."""
    # Try lines-based format (same as PoE1 — poe.ninja may use this for PoE2 too)
    if "lines" in data:
        # Could be currencyoverview or itemoverview format
        lines = data["lines"]
        if lines and "currencyTypeName" in lines[0]:
            return _parse_currency_overview(data, category, game_version)
        if lines and "name" in lines[0]:
            return _parse_item_overview(data, category, game_version)
        # Generic fallback: try both name fields
        return _parse_item_overview(data, category, game_version)

    # Try result-dict format: {"result": {"ItemName": {"value": ..., "text": ...}}}
    entries = []
    for name, info in data.get("result", {}).items():
        chaos = float(info.get("value", 0) or 0)
        divine = float(info.get("divineValue", 0) or 0)
        entries.append(PriceEntry(
            item_name=info.get("text", name).strip(),
            normalized_name=normalize(info.get("text", name)),
            chaos_value=chaos,
            divine_value=divine,
            listing_count=int(info.get("listingCount", 0) or 0),
            game_version=game_version,
            category=category,
            trade_id=info.get("id"),
            icon_url=info.get("image"),
        ))
    return entries


class NinjaClient:
    def __init__(self, profile: GameProfile):
        self._profile = profile

    def fetch_category(self, league: str, cat: CategoryConfig) -> list[PriceEntry]:
        gv = self._profile.game_version

        if cat.endpoint_type == "currencyoverview":
            url = (
                f"{self._profile.ninja_currency_url}"
                f"?league={urllib.parse.quote(league)}&type={cat.api_type}&language=en"
            )
            data = _get(url)
            return _parse_currency_overview(data, cat.name, gv)

        elif cat.endpoint_type == "itemoverview":
            url = (
                f"{self._profile.ninja_item_url}"
                f"?league={urllib.parse.quote(league)}&type={cat.api_type}&language=en"
            )
            data = _get(url)
            return _parse_item_overview(data, cat.name, gv)

        else:  # exchange_overview (PoE2)
            url = (
                f"{self._profile.ninja_currency_url}"
                f"?league={urllib.parse.quote(league)}&type={cat.api_type}"
            )
            data = _get(url)
            return _parse_exchange_overview(data, cat.name, gv)

    def fetch_all(self, league: str) -> PriceSnapshot:
        entries: list[PriceEntry] = []
        for cat in self._profile.categories:
            try:
                batch = self.fetch_category(league, cat)
                entries.extend(batch)
                log.debug("Fetched %d entries for %s/%s", len(batch), cat.name, league)
            except Exception as e:
                log.warning("Skip category %s: %s", cat.name, e)
        return PriceSnapshot(
            entries=entries,
            fetched_at=datetime.now(),
            league=league,
            game_version=self._profile.game_version,
        )

    def fetch_leagues(self) -> list[str]:
        try:
            data = _get(self._profile.ninja_leagues_url)
            return [item.get("id", "") for item in data if item.get("id")]
        except Exception as e:
            log.warning("League fetch failed: %s — using defaults", e)
            return list(self._profile.default_leagues)
