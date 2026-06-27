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
    exalted_value: float = 0.0   # PoE2 ฐานเป็น exalted

    def format_price(self) -> str:
        d = self.divine_value
        if self.game_version == "poe2":
            e = self.exalted_value
            if d >= 1:
                main = f"{round(d)} div" if d >= 100 else (f"{d:.1f} div" if d >= 10 else f"{d:.2f} div")
                return f"{main} ({round(e)}ex)" if e > 0 else main
            if e >= 10:   return f"{round(e)}ex"
            if e >= 1:    return f"{e:.1f}ex"
            if e > 0:     return f"{e:.2f}ex"
            return f"{d:.3f} div" if d > 0 else "?"
        else:
            c = self.chaos_value
            if d >= 1:
                main = f"{round(d)} div" if d >= 10 else f"{d:.1f} div"
                return f"{main} ({round(c)}c)"
            if c >= 1000: return f"{c/1000:.1f}k c"
            if c >= 10:   return f"{round(c)}c"
            if c >= 1:    return f"{c:.1f}c"
            return f"{c:.2f}c"


@dataclass
class PriceSnapshot:
    entries: list[PriceEntry]
    fetched_at: datetime
    league: str
    game_version: str
    category_counts: dict[str, int] = field(default_factory=dict)

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
