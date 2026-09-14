"""สร้าง URL หน้า trade ของ PoE แล้วเปิด browser — ไม่ยิง API, ไม่ต้องใช้ POESESSID."""
from __future__ import annotations
import json
import urllib.parse
import webbrowser

from .models import ParsedItem, Rarity

# dropdown ตัวที่ 3 ของหน้า trade. "online" = In Person (Online).
# ค่าจาก payload จริง (Network tab): "available" = Instant Buyout and In Person,
# "online" = In Person เท่านั้น — อยากกลับไปแบบเดิมแก้บรรทัดนี้บรรทัดเดียว
STATUS_OPTION = "available"

_RARITY_OPTION = {
    Rarity.NORMAL: "normal",
    Rarity.MAGIC:  "magic",
    Rarity.RARE:   "rare",
    Rarity.UNIQUE: "unique",
}


def build_trade_url(item: ParsedItem, mod_db, league: str, profile, min_pct: float = 0.8,
                    custom_stats: list | None = None, base_db=None) -> str:
    query: dict = {"status": {"option": STATUS_OPTION}}
    filters: dict = {}

    def _base() -> str:
        # base/div/gem/currency -> canonical (กันหาไม่เจอเพราะ quality prefix/ชื่อเพี้ยน)
        return base_db.resolve_type(item.base_type) if base_db else item.base_type

    def _name() -> str:
        # unique name -> canonical
        return base_db.resolve_name(item.item_name) if base_db else item.item_name

    if not item.identified:
        # ของไม่ส่องทุกชนิด (unique/rare/magic) → ค้นด้วย base + rarity + identified=no
        # (ไม่มี mod/ชื่อ unique ให้ค้น เพราะเกมยังไม่เผยจนกว่าจะส่อง)
        if item.base_type:
            query["type"] = _base()
        rarity_opt = _RARITY_OPTION.get(item.rarity)
        if rarity_opt:
            filters["type_filters"] = {"filters": {"rarity": {"option": rarity_opt}}}
        filters["misc_filters"] = {"filters": {"identified": {"option": False}}}

    elif item.rarity == Rarity.UNIQUE:
        # unique ส่องแล้ว → ค้นด้วยชื่อ + base
        query["name"] = _name()
        if item.base_type and item.base_type != item.item_name:
            query["type"] = _base()

    else:                                             # rare/magic ส่องแล้ว → ตาม mod
        if item.base_type:
            query["type"] = _base()
        # EE2: normal/magic/rare ค้นด้วย nonunique (รวม 3 ระดับ — เจอกว้างกว่าผูก rarity เป๊ะ)
        filters["type_filters"] = {"filters": {"rarity": {"option": "nonunique"}}}
        if custom_stats is not None:
            # popup (mod_picker) ส่ง filter ที่ผู้ใช้ติ๊กเลือกมาแล้ว — ใช้ตามนั้นเป๊ะ
            stat_filters = [f for f in custom_stats if f.get("id")]
        else:
            stat_filters = []
            for mod in item.mods:
                sid = mod_db.find_stat_id(mod.text, getattr(mod, "mod_type", None))
                if not sid:
                    continue
                f = {"id": sid, "disabled": False}
                if mod.value is not None:
                    f["value"] = {"min": round(mod.value * min_pct, 2)}
                stat_filters.append(f)
        if stat_filters:
            query["stats"] = [{"type": "and", "filters": stat_filters}]

    if filters:                                       # ใส่ filters เฉพาะตอนมีจริง (กัน {} ว่าง)
        query["filters"] = filters

    payload = {"query": query, "sort": {"price": "asc"}}
    base = profile.trade_web_url.format(league=urllib.parse.quote(league, safe=""))
    return f"{base}?q=" + urllib.parse.quote(json.dumps(payload, separators=(",", ":")))


def open_trade(item, mod_db, league, profile, custom_stats=None, base_db=None) -> str:
    url = build_trade_url(item, mod_db, league, profile, custom_stats=custom_stats, base_db=base_db)
    webbrowser.open(url)
    return url
