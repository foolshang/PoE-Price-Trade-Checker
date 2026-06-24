"""Data models shared across the application."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


class GameVersion:
    POE1 = "poe1"
    POE2 = "poe2"


class Rarity:
    NORMAL = "Normal"
    MAGIC = "Magic"
    RARE = "Rare"
    UNIQUE = "Unique"
    CURRENCY = "Currency"
    GEM = "Gem"
    DIVINATION = "Divination Card"


@dataclass
class PriceEntry:
    item_name: str
    normalized_name: str
    chaos_value: float
    divine_value: float
    listing_count: int
    game_version: str
    category: str
    trade_id: Optional[str] = None
    icon_url: Optional[str] = None

    def format_price(self, rates: dict[str, float]) -> str:
        """Pick the most natural in-game currency denomination.
        rates: {display_suffix -> chaos_value}, e.g. {"div": 8.7, "c": 1.0, "alch": 0.025}
        """
        c = self.chaos_value
        div_rate  = rates.get("div",  rates.get("divine", 200.0))
        alch_rate = rates.get("alch", 0.0)

        if c >= div_rate:
            v = c / div_rate
            if v >= 1000: return f"{v/1000:.1f}k div"
            if v >= 10:   return f"{round(v)} div"
            return f"{v:.1f} div"

        if c >= 1.0:
            if c >= 1000: return f"{c/1000:.1f}k c"
            if c >= 10:   return f"{round(c)}c"
            return f"{c:.1f}c"

        if alch_rate > 0 and c >= alch_rate * 0.5:
            v = c / alch_rate
            if v >= 10: return f"{round(v)} alch"
            return f"{v:.1f} alch"

        return f"{c:.2f}c"


@dataclass
class PriceSnapshot:
    entries: list[PriceEntry]
    fetched_at: datetime
    league: str
    game_version: str

    def is_stale(self, max_age_seconds: int = 1800) -> bool:
        age = (datetime.now() - self.fetched_at).total_seconds()
        return age > max_age_seconds


@dataclass
class ScanResult:
    item_name: str
    price_entry: Optional[PriceEntry]
    bbox_x: int
    bbox_y: int
    bbox_w: int
    bbox_h: int
    confidence: float = 0.0


@dataclass
class ModValue:
    stat_id: str
    text: str
    value: Optional[float] = None
    value_min: Optional[float] = None
    value_max: Optional[float] = None


@dataclass
class ParsedItem:
    item_name: str
    base_type: str
    rarity: str
    item_level: int
    quality: int
    mods: list[ModValue]
    game_version: str
    raw_text: str
    item_class: str = ""
    corrupted: bool = False
    identified: bool = True


@dataclass
class TradeListing:
    price_amount: float
    price_currency: str
    seller: str
    item_level: int
    mods: list[str]
    whisper: str
    listing_id: str = ""
