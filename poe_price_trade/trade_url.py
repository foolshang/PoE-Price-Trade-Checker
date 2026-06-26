"""สร้าง URL หน้า trade ของ PoE แล้วเปิด browser — ไม่ยิง API, ไม่ต้องใช้ POESESSID."""
from __future__ import annotations
import json
import urllib.parse
import webbrowser

from .models import ParsedItem, Rarity


def build_trade_url(item: ParsedItem, mod_db, league: str, profile,
                    min_pct: float = 0.8) -> str:
    q: dict = {
        "query": {"status": {"option": "online"}, "stats": [], "filters": {}},
        "sort": {"price": "asc"},
    }
    query = q["query"]

    if item.rarity == Rarity.UNIQUE:
        query["name"] = item.item_name
        if item.base_type and item.base_type != item.item_name:
            query["type"] = item.base_type

    elif not item.identified:
        if item.base_type:
            query["type"] = item.base_type
        if item.item_level:
            query["filters"]["misc_filters"] = {
                "filters": {"ilvl": {"min": item.item_level}}
            }

    else:  # rare/magic ส่องแล้ว
        if item.base_type:
            query["type"] = item.base_type
        filters = []
        for mod in item.mods:
            sid = mod_db.find_stat_id(mod.text)
            if not sid:
                continue
            f: dict = {"id": sid, "disabled": False}
            if mod.value is not None:
                f["value"] = {"min": round(mod.value * min_pct, 2)}
            filters.append(f)
        if filters:
            query["stats"].append({"type": "and", "filters": filters})

    base = profile.trade_web_url.format(league=urllib.parse.quote(league, safe=""))
    payload = urllib.parse.quote(json.dumps(q, separators=(",", ":")))
    return f"{base}?q={payload}"


def open_trade(item: ParsedItem, mod_db, league: str, profile) -> str:
    url = build_trade_url(item, mod_db, league, profile)
    webbrowser.open(url)
    return url
