"""Price cache: loads from poe.ninja, auto-refreshes every 30 min, answers lookups."""
from __future__ import annotations
import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from .matcher import ItemMatcher
from .models import PriceEntry, PriceSnapshot
from .ninja_client import NinjaClient
from .normalizer import normalize
from .profiles import GameProfile

log = logging.getLogger(__name__)

_CACHE_TTL = 1800  # 30 minutes

# normalized item name → display suffix for exchange-rate tracking
_RATE_MAP: dict[str, str] = {
    "divine orb":     "div",
    "chaos orb":      "c",
    "alch":           "alch",   # PoE2 short name
    "orb of alchemy": "alch",   # PoE1 full name
}


class PriceRepository:
    def __init__(self, profile: GameProfile, cache_dir: Optional[Path] = None):
        self._profile = profile
        self._client = NinjaClient(profile)
        self._snapshot: Optional[PriceSnapshot] = None
        self._matcher: Optional[ItemMatcher] = None
        self._lock = threading.Lock()
        self._cache_dir = cache_dir
        self._divine_chaos_rate: float = 200.0
        self._key_rates: dict[str, float] = {"div": 200.0, "c": 1.0}
        self._loading = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, league: str, force: bool = False) -> None:
        """Fetch all categories from poe.ninja and build matcher. Blocks until done."""
        with self._lock:
            if not force and self._snapshot and not self._snapshot.is_stale(_CACHE_TTL):
                return
            self._loading = True

        try:
            # Try disk cache first
            if not force:
                cached = self._load_disk_cache(league)
                if cached and not cached.is_stale(_CACHE_TTL):
                    with self._lock:
                        self._apply_snapshot(cached)
                        self._loading = False
                    return

            log.info("Fetching prices from poe.ninja — league=%s gv=%s", league, self._profile.game_version)
            snapshot = self._client.fetch_all(league)
            with self._lock:
                self._apply_snapshot(snapshot)
                self._loading = False
            self._save_disk_cache(snapshot, league)
            log.info("Loaded %d price entries", len(snapshot.entries))
        except Exception as e:
            with self._lock:
                self._loading = False
            log.error("Failed to load prices: %s", e)
            raise

    def load_async(self, league: str, on_done=None, on_error=None) -> None:
        """Non-blocking load in background thread."""
        def _run():
            try:
                self.load(league)
                if on_done:
                    on_done(self._snapshot)
            except Exception as exc:
                if on_error:
                    on_error(exc)
        threading.Thread(target=_run, daemon=True).start()

    def lookup(self, ocr_text: str, threshold: float = 0.80) -> Optional[PriceEntry]:
        with self._lock:
            if self._matcher is None:
                return None
            return self._matcher.find(ocr_text, threshold)

    def entry_count(self) -> int:
        with self._lock:
            return len(self._matcher) if self._matcher else 0

    def is_ready(self) -> bool:
        with self._lock:
            return self._matcher is not None

    def divine_chaos_rate(self) -> float:
        with self._lock:
            return self._divine_chaos_rate

    def key_rates(self) -> dict[str, float]:
        """Return {display_suffix: chaos_value} for smart price formatting."""
        with self._lock:
            return dict(self._key_rates)

    def snapshot(self) -> Optional[PriceSnapshot]:
        with self._lock:
            return self._snapshot

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _apply_snapshot(self, snapshot: PriceSnapshot) -> None:
        self._snapshot = snapshot
        self._matcher = ItemMatcher(snapshot.entries)
        rates: dict[str, float] = {"c": 1.0}
        for e in snapshot.entries:
            suffix = _RATE_MAP.get(normalize(e.item_name))
            if suffix and e.chaos_value > 0:
                rates[suffix] = e.chaos_value
        if "div" in rates:
            self._divine_chaos_rate = rates["div"]
        self._key_rates = rates

    def _cache_path(self, league: str) -> Optional[Path]:
        if self._cache_dir is None:
            return None
        name = f"ninja_{self._profile.game_version}_{league.replace(' ', '_')}.json"
        return self._cache_dir / name

    def _save_disk_cache(self, snapshot: PriceSnapshot, league: str) -> None:
        path = self._cache_path(league)
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "fetched_at": snapshot.fetched_at.isoformat(),
                "league": snapshot.league,
                "game_version": snapshot.game_version,
                "entries": [
                    {
                        "item_name": e.item_name,
                        "normalized_name": e.normalized_name,
                        "chaos_value": e.chaos_value,
                        "divine_value": e.divine_value,
                        "listing_count": e.listing_count,
                        "category": e.category,
                        "trade_id": e.trade_id,
                        "icon_url": e.icon_url,
                    }
                    for e in snapshot.entries
                ],
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            log.warning("Cache write failed: %s", e)

    def _load_disk_cache(self, league: str) -> Optional[PriceSnapshot]:
        path = self._cache_path(league)
        if path is None or not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            entries = [
                PriceEntry(
                    item_name=e["item_name"],
                    normalized_name=e["normalized_name"],
                    chaos_value=e["chaos_value"],
                    divine_value=e["divine_value"],
                    listing_count=e["listing_count"],
                    game_version=data["game_version"],
                    category=e["category"],
                    trade_id=e.get("trade_id"),
                    icon_url=e.get("icon_url"),
                )
                for e in data["entries"]
            ]
            return PriceSnapshot(
                entries=entries,
                fetched_at=datetime.fromisoformat(data["fetched_at"]),
                league=data["league"],
                game_version=data["game_version"],
            )
        except Exception as e:
            log.warning("Cache read failed: %s", e)
            return None
