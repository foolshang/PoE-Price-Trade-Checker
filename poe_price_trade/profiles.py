"""GameProfile: abstracts all per-game-version differences.

Prices no longer come from poe.ninja/poe2scout directly (see hub_client.py) —
this profile now only carries what's still needed: the GGG trade stats
endpoint (mod_db.py, F5 stat-id lookup), the web trade URL (F5 browser open),
and a last-resort offline fallback league name."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class GameProfile:
    game_version: str

    # PoE official trade endpoints
    trade_search_url: str   # ไม่ใช้แล้วหลัง STEP 6 (F5 เปิด browser แทนยิง API)
    trade_fetch_url: str    # ไม่ใช้แล้วหลัง STEP 6
    trade_stats_url: str    # ใช้จริง — mod_db.py ดึง stat id

    # ค่าตั้งต้นก่อนติดต่อ hub ได้ (cold start / hub ล่มรอบแรกไม่มี disk cache เลย)
    default_leagues: list[str]

    # Web trade URL สำหรับเปิด browser (F5) — ไม่ใช่ /api
    trade_web_url: str = ""

    trade_items_url: str = ""  # ใช้จริง — base_db.py ดึงชื่อ base/unique canonical

    display_name: str = ""


POE1_PROFILE = GameProfile(
    game_version="poe1",
    display_name="Path of Exile 1",
    trade_search_url="https://www.pathofexile.com/api/trade/search/{league}",
    trade_fetch_url="https://www.pathofexile.com/api/trade/fetch/{ids}",
    trade_stats_url="https://www.pathofexile.com/api/trade/data/stats",
    default_leagues=["Mirage", "Hardcore Mirage"],
    trade_web_url="https://www.pathofexile.com/trade/search/{league}",
    trade_items_url="https://www.pathofexile.com/api/trade/data/items",
)

POE2_PROFILE = GameProfile(
    game_version="poe2",
    display_name="Path of Exile 2",
    trade_search_url="https://www.pathofexile.com/api/trade2/search/{league}",
    trade_fetch_url="https://www.pathofexile.com/api/trade2/fetch/{ids}",
    trade_stats_url="https://www.pathofexile.com/api/trade2/data/stats",
    default_leagues=["Runes of Aldur", "HC Runes of Aldur"],
    trade_web_url="https://www.pathofexile.com/trade2/search/{league}",
    trade_items_url="https://www.pathofexile.com/api/trade2/data/items",
)

PROFILES: dict[str, GameProfile] = {
    "poe1": POE1_PROFILE,
    "poe2": POE2_PROFILE,
}
