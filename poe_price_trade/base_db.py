"""base_db.py — resolve a raw item base/unique name from clipboard text into
trade's canonical English name, so minor wording differences (a quality
prefix like "Superior", localized/inconsistent spelling) don't silently
produce a trade search with zero results.

Same idea as Exiled-Exchange-2's findInDatabase(): look the raw name up
against GGG's own trade item list before using it in a query, rather than
trusting whatever the clipboard text says outright.

- 2 indexes: _type (base/div card/gem/currency/beast) + _name (unique/specific)
- lookup order: exact -> strip quality prefix -> fuzzy
- exact always tried first, so a base whose real name starts with what looks
  like a quality prefix (e.g. "Exceptional Verisium") isn't mangled
- fetched from the GGG trade items endpoint (per game) and cached to disk,
  same pattern as mod_db.py's stats cache
- English only — no multi-language matching
"""
from __future__ import annotations
import difflib
import json
import logging
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

# quality prefix ที่เกมเติมตอนมี quality (ตัดหลัง exact match ไม่เจอ)
_QUAL_PREFIX = ("superior ", "anomalous ", "divergent ", "phantasmal ")


def _norm(s: str) -> str:
    return "".join(c for c in s.lower() if c.isalnum())


def _strip_qual(s: str) -> str:
    low = s.lower()
    for p in _QUAL_PREFIX:
        if low.startswith(p):
            return s[len(p):]
    return s


class BaseDB:
    """ฐานชื่อ item มาตรฐานของ trade (ต่อ 1 เกม) — eng only."""

    def __init__(self, profile: GameProfile, cache_dir: Optional[Path] = None):
        self._profile = profile
        self._cache_dir = cache_dir
        self._type: dict[str, str] = {}   # norm -> canonical (base/div card/gem/currency/beast)
        self._name: dict[str, str] = {}   # norm -> canonical (unique/specific name)
        self._loaded = False

    def load(self, force: bool = False) -> None:
        """Load item names from GGG trade API. Tries disk cache first."""
        if self._loaded and not force:
            return
        data = None if force else self._load_cache()
        if data is None:
            data = self._fetch()
        if data:
            self._build(data)
        self._loaded = True

    def _cache_path(self) -> Optional[Path]:
        if self._cache_dir is None:
            return None
        return self._cache_dir / f"items_{self._profile.game_version}.json"

    def _load_cache(self) -> Optional[dict]:
        path = self._cache_path()
        if path is None or not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                cached = json.load(f)
            fetched_at = datetime.fromisoformat(cached["fetched_at"])
            if datetime.now() - fetched_at > timedelta(days=_CACHE_TTL_DAYS):
                return None
            return cached["data"]
        except Exception as e:
            log.warning("base_db: cache read failed: %s", e)
            return None

    def _fetch(self) -> Optional[dict]:
        if not self._profile.trade_items_url:
            return None
        try:
            req = urllib.request.Request(self._profile.trade_items_url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            self._save_cache(data)
            log.info("base_db: fetch สำเร็จ (%s)", self._profile.trade_items_url)
            return data
        except Exception as e:
            log.warning("base_db: fetch ล้มเหลว — จะใช้ชื่อดิบแทน (%s)", e)
            return None

    def _save_cache(self, data: dict) -> None:
        path = self._cache_path()
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"fetched_at": datetime.now().isoformat(), "data": data}, f)
        except Exception as e:
            log.warning("base_db: cache write failed: %s", e)

    def _build(self, data: dict) -> None:
        self._type = {}
        self._name = {}
        # GGG: {"result":[{"label":..,"entries":[{"type":"..","name":"..?"}]}]}
        for group in data.get("result", []):
            for e in group.get("entries", []):
                t = e.get("type")
                if t:
                    self._type[_norm(t)] = t
                n = e.get("name")           # มีเฉพาะ unique/specific
                if n:
                    self._name[_norm(n)] = n
        log.info("base_db: index type=%d name=%d", len(self._type), len(self._name))

    def _lookup(self, raw: str, idx: dict) -> str:
        if not raw or not idx:
            return raw
        n = _norm(raw)
        if n in idx:                         # ① exact (กัน "Exceptional Verisium" โดนตัด)
            return idx[n]
        stripped = _strip_qual(raw)          # ② ตัด quality prefix แล้วลองใหม่
        if stripped != raw:
            ns = _norm(stripped)
            if ns in idx:
                return idx[ns]
        m = difflib.get_close_matches(n, idx.keys(), n=1, cutoff=0.85)  # ③ fuzzy
        return idx[m[0]] if m else raw

    def resolve_type(self, raw: str) -> str:
        """base / div card / gem / currency / beast -> canonical."""
        return self._lookup(raw, self._type)

    def resolve_name(self, raw: str) -> str:
        """unique / specific name -> canonical."""
        return self._lookup(raw, self._name)
