"""Fetch PoE2 prices from poe2scout.com — fills gaps not covered by poe.ninja.

Endpoints used (probe 2026-06-26):
  GET /poe2/Leagues                                   → DivinePrice per league
  GET /poe2/Leagues/{league}/Currencies/ByCategory    → currency / runes / essences / etc.
  GET /poe2/Leagues/{league}/Items                    → all unique items (1275+)

Price unit: exalted (CurrentPrice). Convert: divine_value = CurrentPrice / DivinePrice.
"""
from __future__ import annotations
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from .models import PriceEntry
from .normalizer import normalize

log = logging.getLogger(__name__)

_BASE    = "https://poe2scout.com/api/poe2"
_TIMEOUT = 15
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# poe2scout CurrencyCategory ApiId → our PriceEntry category
_CUR_CATEGORY: dict[str, str] = {
    "fragments":          "Fragment",
    "runes":              "Rune",
    "essences":           "Essence",
    "ultimatum":          "SoulCore",
    "expedition":         "Artifact",
    "ritual":             "Omen",
    "vaultkeys":          "Fragment",
    "breach":             "Catalyst",
    "abyss":              "AbyssalBone",
    "uncutgems":          "UncutGem",
    "lineagesupportgems": "SkillGem",
    "incursion":          "Artifact",
    "idol":               "Idol",
    "verisium":           "Verisium",
    "vaal":               "Currency",
    # "currency" and "delirium" skipped — poe.ninja already covers them with more data
}

# poe2scout UniqueCategory ApiId → our PriceEntry category
_UNIQUE_CATEGORY: dict[str, str] = {
    "accessory": "UniqueAccessory",
    "armour":    "UniqueArmour",
    "weapon":    "UniqueWeapon",
    "jewel":     "UniqueJewel",
    "flask":     "UniqueFlask",
    "map":       "UniqueMap",
    "sanctum":   "UniqueAccessory",
}


def _get(path: str) -> object:
    req = urllib.request.Request(_BASE + path, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"poe2scout HTTP {e.code}: {_BASE + path}") from e
    except Exception as e:
        raise RuntimeError(f"poe2scout fetch failed: {e}") from e


def _divine_price(league: str) -> float:
    """ราคา Divine ใน exalted สำหรับลีกนี้ — ใช้แปลง CurrentPrice → divine_value."""
    try:
        for item in _get("/Leagues"):
            if item.get("Value") == league:
                return float(item.get("DivinePrice") or 1.0)
    except Exception as e:
        log.warning("poe2scout: DivinePrice fetch failed: %s", e)
    return 1.0


def _fetch_currencies(league: str, div_price: float) -> list[PriceEntry]:
    L = urllib.parse.quote(league, safe="")
    entries: list[PriceEntry] = []
    for cat_api, cat_name in _CUR_CATEGORY.items():
        try:
            page = 1
            while True:
                data = _get(f"/Leagues/{L}/Currencies/ByCategory"
                            f"?Category={urllib.parse.quote(cat_api)}&Page={page}&PerPage=100")
                items = data.get("Items", [])
                for x in items:
                    ex_val = float(x.get("CurrentPrice") or 0)
                    name   = x.get("Text") or x.get("Name") or ""
                    if not name or ex_val <= 0:
                        continue
                    entries.append(PriceEntry(
                        item_name=name,
                        normalized_name=normalize(name),
                        chaos_value=0.0,
                        divine_value=ex_val / div_price if div_price else 0.0,
                        exalted_value=ex_val,
                        listing_count=int(x.get("ListingCount") or 0),
                        game_version="poe2",
                        category=cat_name,
                        trade_id=x.get("ApiId") or None,
                        icon_url=x.get("IconUrl") or None,
                    ))
                if page >= data.get("Pages", 1):
                    break
                page += 1
        except Exception as e:
            log.warning("poe2scout: skip currency cat=%s: %s", cat_api, e)
    return entries


def _fetch_uniques(league: str, div_price: float) -> list[PriceEntry]:
    L = urllib.parse.quote(league, safe="")
    entries: list[PriceEntry] = []
    try:
        items = _get(f"/Leagues/{L}/Items")
        if not isinstance(items, list):
            return entries
        for x in items:
            ex_val = float(x.get("CurrentPrice") or 0)
            name   = x.get("Name") or x.get("Text") or ""
            if not name or ex_val <= 0:
                continue
            cat_api  = x.get("CategoryApiId", "")
            cat_name = _UNIQUE_CATEGORY.get(cat_api)
            if cat_name is None:
                continue  # skip currency/misc items ที่ปนมาใน /Items endpoint
            entries.append(PriceEntry(
                item_name=name,
                normalized_name=normalize(name),
                chaos_value=0.0,
                divine_value=ex_val / div_price if div_price else 0.0,
                exalted_value=ex_val,
                listing_count=0,
                game_version="poe2",
                category=cat_name,
                trade_id=None,
                icon_url=x.get("IconUrl") or None,
            ))
    except Exception as e:
        log.warning("poe2scout: fetch uniques failed: %s", e)
    return entries


def fetch_all(league: str) -> list[PriceEntry]:
    """ดึงข้อมูลทั้งหมดจาก poe2scout แล้วคืน PriceEntry list."""
    div_price = _divine_price(league)
    log.info("poe2scout: league=%s DivinePrice=%.2f ex/div", league, div_price)
    currencies = _fetch_currencies(league, div_price)
    uniques    = _fetch_uniques(league, div_price)
    log.info("poe2scout: currencies=%d uniques=%d", len(currencies), len(uniques))
    return currencies + uniques


def fetch_category_ids(league: str) -> set[str]:
    """คืน set ของ CategoryApiId ที่มีอยู่ใน poe2scout (เซนเซอร์จับหมวดใหม่).
    ดึงจาก /Items เพื่อเก็บ CategoryApiId ของ unique items."""
    L = urllib.parse.quote(league, safe="")
    cats: set[str] = set()
    try:
        items = _get(f"/Leagues/{L}/Items")
        if isinstance(items, list):
            for x in items:
                c = x.get("CategoryApiId")
                if c:
                    cats.add(str(c).lower())
    except Exception as e:
        log.debug("poe2scout fetch_category_ids failed: %s", e)
    return cats
