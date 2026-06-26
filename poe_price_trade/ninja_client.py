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
    """PoE2 exchange/current/overview. primaryValue = ค่าไอเท็มเทียบ reference currency.
    คิดเป็นอัตราส่วน: หารด้วย primaryValue ของ Divine/Exalted เพื่อได้หน่วยจริง (กันพลาดไม่ว่า reference จะเป็นอะไร)."""
    id_to_name: dict[str, str] = {}
    for it in data.get("items", []):
        if it.get("id"):
            id_to_name[it["id"]] = it.get("name") or it.get("text") or it["id"]

    pv: dict[str, float] = {}
    for ln in data.get("lines", []):
        if ln.get("id"):
            pv[ln["id"]] = float(ln.get("primaryValue", 0) or 0)

    def anchor(*keys: str) -> float:
        for k in keys:
            if pv.get(k, 0) > 0:
                return pv[k]
        for iid, nm in id_to_name.items():           # fallback หาโดยชื่อ
            if nm.lower() in keys and pv.get(iid, 0) > 0:
                return pv[iid]
        return 0.0

    pv_div   = anchor("divine", "divine orb")
    pv_exalt = anchor("exalted", "exalt", "exalted orb")

    entries = []
    for ln in data.get("lines", []):
        iid = ln.get("id", "")
        v = float(ln.get("primaryValue", 0) or 0)
        if not iid or v <= 0:
            continue
        name = id_to_name.get(iid) or iid.replace("-", " ").title()
        entries.append(PriceEntry(
            item_name=name,
            normalized_name=normalize(name),
            chaos_value=0.0,
            divine_value=(v / pv_div) if pv_div > 0 else 0.0,
            exalted_value=(v / pv_exalt) if pv_exalt > 0 else 0.0,
            listing_count=int(ln.get("volumePrimaryValue", 0) or 0),
            game_version=game_version,
            category=category,
            trade_id=iid,
        ))
    from . import debug
    debug.event(f"ninja parse {category}: entries={len(entries)} pv_div={pv_div} pv_exalt={pv_exalt} "
                f"sample={[ (e.item_name, round(e.exalted_value,2)) for e in entries[:4] ]}")
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
