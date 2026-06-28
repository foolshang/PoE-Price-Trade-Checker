"""Mod→stat-id database. Fetches the official stats endpoint from GGG and
caches to disk. Used to map human-readable mod text to trade API stat IDs."""
from __future__ import annotations
import difflib
import json
import logging
import re
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .profiles import GameProfile

log = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}
_CACHE_TTL_DAYS = 7
_VALUE_PLACEHOLDER = re.compile(r"#|\d+(?:\.\d+)?(?:%)?")


def _normalize_mod(text: str) -> str:
    """Replace numeric values with '#' for fuzzy comparison."""
    return _VALUE_PLACEHOLDER.sub("#", text).lower().strip()


class ModDatabase:
    def __init__(self, profile: GameProfile, cache_dir: Optional[Path] = None):
        self._profile = profile
        self._cache_dir = cache_dir
        # {normalized_text: stat_id}
        self._index: dict[str, str] = {}
        self._typed_index: dict[tuple[str, str], str] = {}  # (text, type) → id
        self._label_index: dict[str, str] = {}  # label → stat_id
        self._raw_stats: list[dict] = []

    def load(self, force: bool = False) -> None:
        """Load stats from GGG trade API. Tries disk cache first."""
        if not force:
            cached = self._load_cache()
            if cached:
                self._build_index(cached)
                return

        log.info("Fetching stat ids from GGG (%s)", self._profile.trade_stats_url)
        req = urllib.request.Request(self._profile.trade_stats_url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())

        stats = self._flatten_stats(data)
        self._save_cache(stats)
        self._build_index(stats)
        log.info("Loaded %d stat ids", len(self._index))

    def _flatten_stats(self, data: dict) -> list[dict]:
        flat = []
        for group in data.get("result", []):
            for entry in group.get("entries", []):
                flat.append({
                    "id": entry.get("id", ""),
                    "text": entry.get("text", ""),
                    "type": group.get("id", ""),
                })
        return flat

    # ลำดับความสำคัญ — ใช้ตอน "ไม่รู้ type" (fallback flat index)
    _TYPE_PRIORITY = {
        "explicit": 0, "implicit": 1, "fractured": 2, "rune": 3,
        "enchant": 4, "scourge": 5, "crafted": 6, "veiled": 7, "pseudo": 8,
    }

    def _build_index(self, stats: list[dict]) -> None:
        self._raw_stats = stats
        self._index = {}            # flat (prioritized) — ใช้ตอนไม่รู้ type
        self._typed_index = {}      # (normalized, type) → id — type-aware
        chosen_pri: dict[str, int] = {}
        for stat in stats:
            sid = stat.get("id", "")
            text = stat.get("text", "")
            typ = stat.get("type", "")
            if not (sid and text):
                continue
            normalized = _normalize_mod(text)
            self._typed_index[(normalized, typ)] = sid
            pri = self._TYPE_PRIORITY.get(typ, 99)
            if normalized not in self._index or pri < chosen_pri[normalized]:
                self._index[normalized] = sid
                chosen_pri[normalized] = pri
        log.debug("Built mod index: %d flat / %d typed",
                  len(self._index), len(self._typed_index))

    def find_stat_id(self, mod_text: str, mod_type: Optional[str] = None,
                     threshold: float = 0.75) -> Optional[str]:
        """หา stat id ที่ตรงกับ mod_text — เทียบ type ให้ตรงก่อน (มี fallback)."""
        norm = _normalize_mod(mod_text)

        # 1) exact ภายใน type เดียวกัน (explicit→explicit, desecrated→desecrated)
        if mod_type and (norm, mod_type) in self._typed_index:
            return self._typed_index[(norm, mod_type)]

        # 2) exact แบบ prioritized (ไม่รู้ type หรือ type ไม่ตรง)
        if norm in self._index:
            return self._index[norm]

        # 3) fuzzy ภายใน type เดียวกัน
        if mod_type:
            type_keys = [k[0] for k in self._typed_index if k[1] == mod_type]
            m = difflib.get_close_matches(norm, type_keys, n=1, cutoff=threshold)
            if m:
                return self._typed_index[(m[0], mod_type)]

        # 4) fuzzy แบบ prioritized
        m = difflib.get_close_matches(norm, list(self._index.keys()), n=1, cutoff=threshold)
        if m:
            return self._index[m[0]]

        return None

    def _cache_path(self) -> Optional[Path]:
        if self._cache_dir is None:
            return None
        return self._cache_dir / f"stats_{self._profile.game_version}.json"

    def _save_cache(self, stats: list[dict]) -> None:
        path = self._cache_path()
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {"fetched_at": datetime.now().isoformat(), "stats": stats}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception as e:
            log.warning("Mod DB cache write failed: %s", e)

    def _load_cache(self) -> Optional[list[dict]]:
        path = self._cache_path()
        if path is None or not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            fetched_at = datetime.fromisoformat(data["fetched_at"])
            if datetime.now() - fetched_at > timedelta(days=_CACHE_TTL_DAYS):
                return None
            return data["stats"]
        except Exception as e:
            log.warning("Mod DB cache read failed: %s", e)
            return None
