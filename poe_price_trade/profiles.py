"""GameProfile: abstracts all per-game-version differences."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CategoryConfig:
    name: str
    endpoint_type: str   # "currencyoverview" | "itemoverview" | "exchange_overview"
    api_type: str        # value passed as ?type= to poe.ninja


@dataclass
class GameProfile:
    game_version: str

    # poe.ninja endpoints
    ninja_currency_url: str
    ninja_item_url: str
    categories: list[CategoryConfig]

    # PoE official trade endpoints
    trade_search_url: str
    trade_fetch_url: str
    trade_stats_url: str

    # League fetch (from poe.ninja or hardcoded fallback)
    ninja_leagues_url: str
    default_leagues: list[str]

    display_name: str = ""

    def get_category(self, name: str) -> Optional[CategoryConfig]:
        return next((c for c in self.categories if c.name == name), None)

    def is_poe2(self) -> bool:
        return self.game_version == "poe2"


POE1_PROFILE = GameProfile(
    game_version="poe1",
    display_name="Path of Exile 1",
    ninja_currency_url="https://poe.ninja/api/data/currencyoverview",
    ninja_item_url="https://poe.ninja/api/data/itemoverview",
    categories=[
        CategoryConfig("Currency",        "currencyoverview", "Currency"),
        CategoryConfig("Fragment",        "currencyoverview", "Fragment"),
        CategoryConfig("Oil",             "currencyoverview", "Oil"),
        CategoryConfig("Incubator",       "currencyoverview", "Incubator"),
        CategoryConfig("Scarab",          "currencyoverview", "Scarab"),
        CategoryConfig("Fossil",          "currencyoverview", "Fossil"),
        CategoryConfig("Resonator",       "currencyoverview", "Resonator"),
        CategoryConfig("Essence",         "currencyoverview", "Essence"),
        CategoryConfig("DivinationCard",  "currencyoverview", "DivinationCard"),
        CategoryConfig("DeliriumOrb",     "currencyoverview", "DeliriumOrb"),
        CategoryConfig("Artifact",        "currencyoverview", "Artifact"),
        CategoryConfig("Beast",           "currencyoverview", "Beast"),
        CategoryConfig("UniqueWeapon",    "itemoverview",     "UniqueWeapon"),
        CategoryConfig("UniqueArmour",    "itemoverview",     "UniqueArmour"),
        CategoryConfig("UniqueAccessory", "itemoverview",     "UniqueAccessory"),
        CategoryConfig("UniqueFlask",     "itemoverview",     "UniqueFlask"),
        CategoryConfig("UniqueJewel",     "itemoverview",     "UniqueJewel"),
        CategoryConfig("SkillGem",        "itemoverview",     "SkillGem"),
        CategoryConfig("ClusterJewel",    "itemoverview",     "ClusterJewel"),
        CategoryConfig("Map",             "itemoverview",     "Map"),
        CategoryConfig("UniqueMap",       "itemoverview",     "UniqueMap"),
        CategoryConfig("BaseType",        "itemoverview",     "BaseType"),
    ],
    trade_search_url="https://www.pathofexile.com/api/trade/search/{league}",
    trade_fetch_url="https://www.pathofexile.com/api/trade/fetch/{ids}",
    trade_stats_url="https://www.pathofexile.com/api/trade/data/stats",
    ninja_leagues_url="https://poe.ninja/api/data/leagues",
    default_leagues=["Standard", "Hardcore", "Settlers", "HC Settlers"],
)

# NOTE: PoE2 endpoints — verify at https://poe.ninja before first run.
# PLAN.md §5.1 specifies: /poe2/api/economy/exchange/current/overview?league=<>&type=<>
# The JSON structure may differ from PoE1; ninja_client.py handles both formats.
POE2_PROFILE = GameProfile(
    game_version="poe2",
    display_name="Path of Exile 2",
    ninja_currency_url="https://poe.ninja/poe2/api/economy/exchange/current/overview",
    ninja_item_url="https://poe.ninja/poe2/api/economy/exchange/current/overview",
    categories=[
        CategoryConfig("Currency",            "exchange_overview", "Currency"),
        CategoryConfig("Fragment",            "exchange_overview", "Fragment"),
        CategoryConfig("DistilledEmotion",    "exchange_overview", "DistilledEmotion"),
        CategoryConfig("Catalyst",            "exchange_overview", "Catalyst"),
        CategoryConfig("Essence",             "exchange_overview", "Essence"),
        CategoryConfig("Rune",                "exchange_overview", "Rune"),
        CategoryConfig("SoulCore",            "exchange_overview", "SoulCore"),
        CategoryConfig("BreachSplinter",      "exchange_overview", "BreachSplinter"),
        CategoryConfig("DivinationCard",      "exchange_overview", "DivinationCard"),
        CategoryConfig("UniqueWeapon",        "exchange_overview", "UniqueWeapon"),
        CategoryConfig("UniqueArmour",        "exchange_overview", "UniqueArmour"),
        CategoryConfig("UniqueAccessory",     "exchange_overview", "UniqueAccessory"),
        CategoryConfig("UniqueFlask",         "exchange_overview", "UniqueFlask"),
        CategoryConfig("UniqueJewel",         "exchange_overview", "UniqueJewel"),
        CategoryConfig("SkillGem",            "exchange_overview", "SkillGem"),
        CategoryConfig("Map",                 "exchange_overview", "Map"),
        CategoryConfig("UniqueMap",           "exchange_overview", "UniqueMap"),
    ],
    trade_search_url="https://www.pathofexile.com/api/trade2/search/{league}",
    trade_fetch_url="https://www.pathofexile.com/api/trade2/fetch/{ids}",
    trade_stats_url="https://www.pathofexile.com/api/trade2/data/stats",
    ninja_leagues_url="https://poe.ninja/api/data/leagues",
    default_leagues=["Standard", "Hardcore", "Dawn of the Hunt", "HC Dawn of the Hunt"],
)

PROFILES: dict[str, GameProfile] = {
    "poe1": POE1_PROFILE,
    "poe2": POE2_PROFILE,
}
