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


def _parse_overview(data: dict, category: str, game_version: str) -> list[PriceEntry]:
    """PoE2 exchange + stash overview. primaryValue = ราคาใน divine, core.rates.exalted = ex ต่อ div.
    ใช้ core.rates ก่อน ถ้าไม่มีค่อย fallback หา exalted line เอง (กันโครงสร้างเปลี่ยน)."""
    core = data.get("core", {}) or {}
    rates = core.get("rates", {}) or {}
    ex_per_div = float(rates.get("exalted", 0) or 0)

    id_to_name: dict[str, str] = {}
    for it in data.get("items", []):
        if it.get("id"):
            id_to_name[it["id"]] = it.get("name") or it.get("text") or it["id"]

    if ex_per_div <= 0:
        for ln in data.get("lines", []):
            nm = (ln.get("name") or id_to_name.get(ln.get("id", ""), "")).lower()
            if nm in ("exalted orb", "exalted") and float(ln.get("primaryValue", 0) or 0) > 0:
                ex_per_div = 1.0 / float(ln["primaryValue"])
                break

    entries: list[PriceEntry] = []
    for ln in data.get("lines", []):
        pv = float(ln.get("primaryValue", 0) or 0)
        if pv <= 0:
            continue
        name = (ln.get("name")
                or id_to_name.get(ln.get("id", ""))
                or str(ln.get("itemId") or ln.get("id") or ""))
        if not name:
            continue
        entries.append(PriceEntry(
            item_name=name,
            normalized_name=normalize(name),
            chaos_value=0.0,
            divine_value=pv,
            exalted_value=(pv * ex_per_div) if ex_per_div > 0 else 0.0,
            listing_count=int(ln.get("listingCount") or ln.get("volumePrimaryValue") or 0),
            game_version=game_version,
            category=category,
            trade_id=ln.get("detailsId") or ln.get("id"),
        ))
    from . import debug
    debug.event(f"ninja parse {category}: entries={len(entries)} ex_per_div={round(ex_per_div,1)} "
                f"sample={[(e.item_name, round(e.exalted_value, 1)) for e in entries[:3]]}")
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

        elif cat.endpoint_type == "stash_overview":     # PoE2 equipment/atlas
            url = (
                f"{self._profile.ninja_stash_url}"
                f"?league={urllib.parse.quote(league)}&type={cat.api_type}"
            )
            data = _get(url)
            return _parse_overview(data, cat.name, gv)

        else:  # exchange_overview (PoE2 GENERAL)
            url = (
                f"{self._profile.ninja_currency_url}"
                f"?league={urllib.parse.quote(league)}&type={cat.api_type}"
            )
            data = _get(url)
            return _parse_overview(data, cat.name, gv)

    def fetch_all(self, league: str) -> PriceSnapshot:
        entries: list[PriceEntry] = []
        counts: dict[str, int] = {}
        for cat in self._profile.categories:
            try:
                batch = self.fetch_category(league, cat)
                counts[cat.name] = len(batch)
                entries.extend(batch)
                log.debug("Fetched %d entries for %s/%s", len(batch), cat.name, league)
            except Exception as e:
                counts[cat.name] = 0
                log.warning("Skip category %s: %s", cat.name, e)
        return PriceSnapshot(
            entries=entries,
            fetched_at=datetime.now(),
            league=league,
            game_version=self._profile.game_version,
            category_counts=counts,
        )

    def fetch_leagues(self) -> list[str]:
        """ดึงรายชื่อลีกจาก GGG trade API (probe confirmed: poe.ninja leagues → 404).
        Response: {"result": [{"id": "Mirage", "realm": "pc", ...}]}
        กรองเฉพาะ realm ที่ตรง + ตัด Ruthless ออก (ไม่มีข้อมูล poe.ninja)."""
        try:
            data = _get(self._profile.ninja_leagues_url)
            realm = self._profile.leagues_realm
            out = []
            for item in data.get("result", []):
                if item.get("realm") != realm:
                    continue
                name = item.get("id", "")
                if not name:
                    continue
                if "Ruthless" in name:
                    continue
                out.append(name)
            if out:
                return out
        except Exception as e:
            log.warning("League fetch failed: %s — using defaults", e)
        return list(self._profile.default_leagues)
