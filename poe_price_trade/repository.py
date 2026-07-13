"""Price cache: loads from poe-data-hub (Firebase-published JSON), auto-refreshes
every 5 minutes. Desktop app runs in short bursts, not as a service — see
_load()'s "apply stale disk cache first, refresh in background" flow below."""
from __future__ import annotations
import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import debug, hub_client
from .matcher import ItemMatcher
from .models import PriceEntry, PriceSnapshot
from .normalizer import normalize
from .profiles import GameProfile

log = logging.getLogger(__name__)

_CACHE_TTL = 300  # 5 minutes — matches the hub's Cache-Control: max-age=300



class PriceRepository:
    def __init__(self, profile: GameProfile, cache_dir: Optional[Path] = None):
        self._profile = profile
        self._snapshot: Optional[PriceSnapshot] = None
        self._matcher: Optional[ItemMatcher] = None
        self._lock = threading.Lock()
        self._cache_dir = cache_dir
        self._divine_chaos_rate: float = 200.0
        self._loading = False
        self._degraded: list[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, league: str, path: str, force: bool = False) -> None:
        """Fetch a hub prices file (by its exact hub-relative path) and build the
        matcher. Blocks until done.

        Two-phase: apply whatever disk cache exists for this league immediately
        (even if stale) so the app has *something* to match against right away,
        then attempt a hub refresh. If the refresh fails and we already applied a
        disk cache, keep serving it instead of raising — a desktop app that only
        runs in short bursts shouldn't go blank just because the hub had a blip.
        """
        with self._lock:
            if (not force and self._snapshot and self._snapshot.league == league
                    and not self._snapshot.is_stale(_CACHE_TTL)):
                return
            self._loading = True

        cached = self._load_disk_cache(league)
        if cached:
            with self._lock:
                self._apply_snapshot(cached)

        if not force and cached and not cached.is_stale(_CACHE_TTL):
            with self._lock:
                self._loading = False
            return

        try:
            log.info("Fetching prices from hub — league=%s gv=%s path=%s",
                     league, self._profile.game_version, path)
            data = hub_client.get_prices(path)
            entries = self._entries_from_hub_payload(data)
            snapshot = PriceSnapshot(
                entries=entries,
                fetched_at=datetime.now(),
                league=league,
                game_version=self._profile.game_version,
            )
            degraded = self._compute_degraded(data)

            with self._lock:
                self._degraded = degraded
                self._apply_snapshot(snapshot)
                self._loading = False
            self._save_disk_cache(snapshot, league)
            log.info("Loaded %d price entries total (hub)", len(snapshot.entries))
        except Exception as e:
            with self._lock:
                self._loading = False
            if cached:
                log.warning("hub refresh failed, keeping disk cache (%s): %s", league, e)
                debug.event(f"hub refresh FAILED league={league}: {e} — serving stale disk cache")
            else:
                log.error("Failed to load prices from hub: %s", e)
                raise

    def load_async(self, league: str, path: str, on_done=None, on_error=None) -> None:
        """Non-blocking load in background thread."""
        def _run():
            try:
                self.load(league, path)
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

    def snapshot(self) -> Optional[PriceSnapshot]:
        with self._lock:
            return self._snapshot

    def degraded(self) -> list[str]:
        """คืนรายชื่อ 'source:category' ที่ hub รายงาน sample.per_category ok=false
        รอบล่าสุด (fetch/validate ล้มรอบนี้ — entries เก่ายังถูก merge ไว้ให้แล้วฝั่ง hub)."""
        with self._lock:
            return list(self._degraded)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _entries_from_hub_payload(self, data: dict) -> list[PriceEntry]:
        """Merge hub's currency[] + items[] into one PriceEntry list.

        `value`/`value_currency` is always chaos for poe1, exalted for poe2
        (hub SPEC 8.1) — chaos_value/exalted_value are additive fields the hub
        includes when available; fall back to `value` itself when the matching
        additive field is absent but value_currency already tells us the unit.
        """
        gv = self._profile.game_version
        entries: list[PriceEntry] = []
        for section in ("currency", "items"):
            for it in data.get(section, []):
                name = (it.get("name") or "").strip()
                if not name:
                    continue
                value = float(it.get("value") or 0)
                vc = it.get("value_currency", "")

                chaos = it.get("chaos_value")
                chaos_value = float(chaos) if chaos is not None else (value if vc == "chaos" else 0.0)

                exalted = it.get("exalted_value")
                exalted_value = float(exalted) if exalted is not None else (value if vc == "exalted" else 0.0)

                entries.append(PriceEntry(
                    item_name=name,
                    normalized_name=normalize(name),
                    chaos_value=chaos_value,
                    divine_value=float(it.get("divine_value") or 0),
                    listing_count=int(it.get("listing_count") or 0),
                    game_version=gv,
                    category=it.get("category", ""),
                    trade_id=it.get("trade_id"),
                    icon_url=it.get("icon_url"),
                    exalted_value=exalted_value,
                    stale=bool(it.get("stale", False)),
                ))
        return entries

    @staticmethod
    def _compute_degraded(data: dict) -> list[str]:
        out: list[str] = []
        per_cat = (data.get("sample") or {}).get("per_category") or {}
        for source, cats in per_cat.items():
            for cat, info in cats.items():
                if not info.get("ok", True):
                    out.append(f"{source}:{cat}")
        return out

    def _apply_snapshot(self, snapshot: PriceSnapshot) -> None:
        self._snapshot = snapshot
        self._matcher = ItemMatcher(snapshot.entries)
        for e in snapshot.entries:
            if normalize(e.item_name) == "divine orb" and e.chaos_value > 1:
                self._divine_chaos_rate = e.chaos_value
                break

    def _cache_path(self, league: str) -> Optional[Path]:
        if self._cache_dir is None:
            return None
        name = f"hub_{self._profile.game_version}_{league.replace(' ', '_')}.json"
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
                        "exalted_value": e.exalted_value,
                        "listing_count": e.listing_count,
                        "category": e.category,
                        "trade_id": e.trade_id,
                        "icon_url": e.icon_url,
                        "stale": e.stale,
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
                    exalted_value=e.get("exalted_value", 0.0),
                    listing_count=e["listing_count"],
                    game_version=data["game_version"],
                    category=e["category"],
                    trade_id=e.get("trade_id"),
                    icon_url=e.get("icon_url"),
                    stale=e.get("stale", False),
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
