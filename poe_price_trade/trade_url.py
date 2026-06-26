"""สร้าง URL หน้า trade ของ PoE แล้วเปิด browser — ไม่ยิง API, ไม่ต้องใช้ POESESSID."""
from __future__ import annotations
import json
import urllib.parse
import webbrowser

from .models import ParsedItem, Rarity

# dropdown ตัวที่ 3 ของหน้า trade. "online" = In Person (Online).
# พอได้ค่าจริงของ "Instant Buyout and In Person" จาก URL แล้ว มาแก้ตรงนี้/หรือ _apply_status()
STATUS_OPTION = "online"

_RARITY_OPTION = {
    Rarity.NORMAL: "normal",
    Rarity.MAGIC:  "magic",
    Rarity.RARE:   "rare",
    Rarity.UNIQUE: "unique",
}


def build_trade_url(item: ParsedItem, mod_db, league: str, profile, min_pct: float = 0.8) -> str:
    query: dict = {"status": {"option": STATUS_OPTION}, "stats": [], "filters": {}}

    # Type Filters: เลือก rarity ตามไอเท็มเสมอ (เฉพาะ gear — currency/gem ไม่มี rarity)
    rarity_opt = _RARITY_OPTION.get(item.rarity)
    if rarity_opt:
        query["filters"]["type_filters"] = {"filters": {"rarity": {"option": rarity_opt}}}

    if item.rarity == Rarity.UNIQUE:                 # unique → ค้นด้วยชื่อ
        query["name"] = item.item_name
        if item.base_type and item.base_type != item.item_name:
            query["type"] = item.base_type

    elif not item.identified:                         # ยังไม่ส่อง → base + ilvl
        if item.base_type:
            query["type"] = item.base_type
        if item.item_level:
            query["filters"]["misc_filters"] = {"filters": {"ilvl": {"min": item.item_level}}}

    else:                                             # rare/magic ส่องแล้ว → ตาม mod
        if item.base_type:
            query["type"] = item.base_type
        filters = []
        for mod in item.mods:
            sid = mod_db.find_stat_id(mod.text)
            if not sid:
                continue
            f = {"id": sid, "disabled": False}
            if mod.value is not None:
                f["value"] = {"min": round(mod.value * min_pct, 2)}
            filters.append(f)
        if filters:
            query["stats"].append({"type": "and", "filters": filters})

    payload = {"query": query, "sort": {"price": "asc"}}
    base = profile.trade_web_url.format(league=urllib.parse.quote(league, safe=""))
    return f"{base}?q=" + urllib.parse.quote(json.dumps(payload, separators=(",", ":")))


def open_trade(item, mod_db, league, profile) -> str:
    url = build_trade_url(item, mod_db, league, profile)
    webbrowser.open(url)
    return url
