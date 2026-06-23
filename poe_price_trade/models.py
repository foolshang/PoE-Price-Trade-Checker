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

    def value_in(self, currency: str, divine_chaos_rate: float) -> float:
        if currency == "divine":
            return self.divine_value if self.divine_value else self.chaos_value / divine_chaos_rate
        if currency == "exalted":
            return self.chaos_value
        return self.chaos_value

    def format_price(self, currency: str, divine_chaos_rate: float) -> str:
        val = self.value_in(currency, divine_chaos_rate)
        suffix = {"divine": "div", "exalted": "ex", "chaos": "c"}.get(currency, "c")
        if val >= 1000:
            return f"{val/1000:.1f}k {suffix}"
        if val >= 10:
            return f"{val:.1f} {suffix}"
        return f"{val:.2f} {suffix}"


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
