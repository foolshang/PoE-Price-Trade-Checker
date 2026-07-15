"""Mod Badge: color-code F5 popup mod rows by real-build usage popularity.

Source: poe-data-hub's poe2/meta/latest.json (PoE2-only — the hub has no PoE1
equivalent yet; poe1/meta/latest.json 404s, which we treat as "no badges",
never an error). Schema: D:\\Projects\\Poe_Hub\\SPEC.md section 8.2.

Stat-id resolution reuses mod_db.py's existing GGG-trade-stats-based fuzzy
matcher instead of re-matching against the hub's own stat_dictionary — the
two use the *same* GGG stat_id namespace (verified live 2026-07-14:
"explicit.stat_3299347043" == "# to maximum Life" identically on both sides),
so mod_db.find_stat_id() is tried first. stat_dictionary is only consulted as
a fallback for the (presumably rare) mods GGG's own trade-stats endpoint
doesn't resolve but the hub's build-scrape still recorded — one stat_id can
have several templates and, per the hub's own schema note, a template can
(rarely) map to more than one stat_id, so the fallback index is list-valued
in both directions and never collapses to a plain overwriting dict.
"""
from __future__ import annotations
import difflib
import json
import logging
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from . import hub_client
from .meta_db import WEAPON_CLASSES
from .mod_db import _normalize_mod

log = logging.getLogger(__name__)

_CACHE_TTL = timedelta(hours=8)   # hub publishes meta ~once/day

# item_class (clipboard "Item Class:" text) -> hub slot key. Both singular and
# plural forms listed since the exact PoE2 wording for several of these isn't
# nailed down from a real sample yet — cheap to cover both, wrong on this
# silently loses badges rather than crashing either way.
_SLOT_MAP: dict[str, str] = {
    "Helmet": "helmet", "Helmets": "helmet",
    "Body Armour": "body", "Body Armours": "body",
    "Glove": "gloves", "Gloves": "gloves",
    "Boot": "boots", "Boots": "boots",
    "Belt": "belt", "Belts": "belt",
    "Ring": "ring", "Rings": "ring",
    "Amulet": "amulet", "Amulets": "amulet",
    "Quiver": "quiver", "Quivers": "quiver",
    "Focus": "focus", "Foci": "focus",
    "Shield": "offhand", "Shields": "offhand",
    "Buckler": "offhand", "Bucklers": "offhand",
    "Charm": "charm", "Charms": "charm",
    "Life Flask": "flask", "Life Flasks": "flask",
    "Mana Flask": "flask", "Mana Flasks": "flask",
}
_JEWEL_CLASSES = {"Jewel", "Jewels"}
_JEWEL_SLUG = re.compile(r"[^a-z0-9]+")

_DEFAULT_RULES: dict = {
    "red":  {"max_rank": 5,  "min_usage_pct": 50.0},
    "gold": {"max_rank": 15, "min_usage_pct": 15.0},
    "colors": {"red": "#FF4444", "gold": "#FFB800", "green": "#4CAF50"},
    "roll_pct": 0.25,   # top/bottom X% of a mod's roll range -> ▲/▼
}


def slot_for_item(item_class: str, base_type: str) -> Optional[str]:
    """(item_class, base_type) from a parsed clipboard item -> hub slot key,
    or None for classes the hub has no popularity meta for (currency, gems,
    maps, ...). Jewel base -> "jewel:<slug>" mirrors the hub's own
    _slugify_jewel_base exactly (src/fetchers/ninja_chars.py in the hub repo):
    lowercase, strip everything but a-z0-9."""
    if item_class in _JEWEL_CLASSES:
        slug = _JEWEL_SLUG.sub("", base_type.lower())
        return f"jewel:{slug}" if slug else None
    if item_class in WEAPON_CLASSES:
        return "weapon"
    return _SLOT_MAP.get(item_class)


def affix_cap(item_class: str) -> int:
    """Max prefix (== max suffix) slots for this item class. PoE2 jewels are
    capped at 1/1, unlike regular gear's 3/3."""
    return 1 if item_class in _JEWEL_CLASSES else 3


def _pct_position(value: float, lo: float, hi: float) -> Optional[float]:
    if hi <= lo:
        return None
    return (value - lo) / (hi - lo)


def _arrow(pct: float, top_bottom_pct: float) -> Optional[str]:
    if pct >= 1 - top_bottom_pct:
        return "▲"
    if pct <= top_bottom_pct:
        return "▼"
    return None


def tier_roll_arrow(values: tuple, rng: Optional[list], top_bottom_pct: float = 0.25) -> Optional[str]:
    """RePoE-tier-based roll indicator: `values`/`rng` are paired index-by-index
    (hybrid mods have more than one of each) — averages the percentile position
    across all of them. None if nothing to compare (e.g. tier 1 — caller should
    skip calling this at all for tier 1, "already maxed" needs no arrow)."""
    if not values or not rng:
        return None
    pcts = [p for v, pair in zip(values, rng)
            if (p := _pct_position(v, pair[0], pair[1])) is not None]
    if not pcts:
        return None
    return _arrow(sum(pcts) / len(pcts), top_bottom_pct)


def _build_template_index(stat_dictionary: list[dict]) -> dict[str, list[str]]:
    """normalized template -> [stat_id, ...]. List-valued both ways on purpose:
    a stat_id can have multiple templates, and (per hub SPEC 8.2) a template can
    rarely map to more than one stat_id — collapsing either direction into a
    plain dict would silently drop a collision instead of surfacing it."""
    index: dict[str, list[str]] = {}
    for entry in stat_dictionary:
        tmpl = entry.get("template", "")
        sid = entry.get("stat_id", "")
        if not tmpl or not sid:
            continue
        key = _normalize_mod(tmpl)
        ids = index.setdefault(key, [])
        if sid not in ids:
            ids.append(sid)
    return index


class ModBadgeDB:
    def __init__(self, cache_dir: Optional[Path] = None, config_dir: Optional[Path] = None):
        self._cache_dir = cache_dir
        self._config_dir = config_dir
        self._lock = threading.Lock()
        self._by_key: dict[tuple[str, str, str], dict] = {}   # (slot, archetype, stat_id) -> mod row
        self._template_index: dict[str, list[str]] = {}
        self._stat_to_templates: dict[str, list[str]] = {}    # stat_id -> [normalized template, ...]
        self._hot_tags_cache: dict[tuple[str, str], set] = {}  # (slot, archetype) -> red/gold tags
        self._rules = _DEFAULT_RULES
        self._load_rules()

    # ------------------------------------------------------------------

    def _load_rules(self) -> None:
        if self._config_dir is None:
            return
        path = self._config_dir / "mod_badge_rules.json"
        try:
            self._rules = json.loads(path.read_text(encoding="utf-8"))
            log.info("mod_badge_rules.json override loaded")
        except FileNotFoundError:
            pass
        except Exception as e:
            log.warning("mod_badge_rules load fail: %s", e)

    def available(self) -> bool:
        with self._lock:
            return bool(self._by_key)

    def rule(self, key: str, default):
        return self._rules.get(key, default)

    def load(self, force: bool = False) -> None:
        """Fetch poe2/meta/latest.json (disk-cached, staleness judged by the
        payload's own generated_at — TTL ~8h, hub publishes ~once/day). Any
        failure — network down, hub has no meta for this game — degrades to
        "no badges", never raises; the caller (F5 flow) must keep working
        either way. Mirrors ModDatabase.load()'s disk-cache-first shape."""
        if not force:
            cached = self._load_disk_cache()
            if cached and not self._is_stale(cached):
                self._index(cached)
                return

        data = hub_client.get_meta("poe2")
        if data is None:
            cached = self._load_disk_cache()   # network failed -> fall back to disk even if stale
            if cached:
                self._index(cached)
            else:
                log.info("mod badge meta unavailable — badges disabled this session")
            return

        self._index(data)
        self._save_disk_cache(data)

    @staticmethod
    def _is_stale(data: dict) -> bool:
        gen_raw = data.get("generated_at")
        if not gen_raw:
            return True
        try:
            gen = datetime.fromisoformat(gen_raw.replace("Z", "+00:00"))
        except ValueError:
            return True
        return datetime.now(timezone.utc) - gen > _CACHE_TTL

    def _index(self, data: dict) -> None:
        by_key: dict[tuple[str, str, str], dict] = {}
        for m in data.get("mods", []):
            key = (m.get("slot", ""), m.get("archetype", ""), m.get("stat_id", ""))
            by_key[key] = m
        template_index = _build_template_index(data.get("stat_dictionary", []))
        stat_to_templates: dict[str, list[str]] = {}
        for tmpl, ids in template_index.items():
            for sid in ids:
                stat_to_templates.setdefault(sid, []).append(tmpl)
        with self._lock:
            self._by_key = by_key
            self._template_index = template_index
            self._stat_to_templates = stat_to_templates
            self._hot_tags_cache = {}   # stale after any re-index
        log.info("mod badge meta loaded: %d rows, %d templates", len(by_key), len(template_index))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve_stat_id(self, mod_text: str, mod_type: Optional[str], mod_db) -> Optional[str]:
        """mod_db's own GGG-trade-stats resolver first (same namespace as the
        hub, proven in production for F5 already); hub's stat_dictionary only
        as a fallback, and only when unambiguous (exactly one candidate) —
        guessing among several would risk a wrong badge, worse than none.

        Exact-then-fuzzy on the normalized template, same shape as mod_db's own
        find_stat_id — needed because _normalize_mod doesn't strip the leading
        "+" real game text has ("+47 to maximum Life") but hub templates don't
        ("# to maximum Life"); mod_db's own fuzzy fallback is why *it* already
        handles this in production, so this fallback needs the same trick."""
        sid = mod_db.find_stat_id(mod_text, mod_type)
        if sid:
            return sid
        norm = _normalize_mod(mod_text)
        candidates = self._template_index.get(norm, [])
        if not candidates:
            close = difflib.get_close_matches(norm, list(self._template_index.keys()), n=1, cutoff=0.85)
            if close:
                candidates = self._template_index[close[0]]
        return candidates[0] if len(candidates) == 1 else None

    def badge_color(self, stat_id: str, slot: str, archetype: str) -> Optional[str]:
        """None = white / no badge (unmatched, or not popular enough)."""
        if not stat_id or not slot:
            return None
        row = self._row(stat_id, slot, archetype)
        if row is None:
            return None
        rank = row.get("rank_in_slot")
        usage = row.get("usage_pct") or 0.0

        red = self._rules.get("red", {})
        if (rank is not None and rank <= red.get("max_rank", 5)) or usage >= red.get("min_usage_pct", 50.0):
            return self._rules.get("colors", {}).get("red", "#FF4444")

        gold = self._rules.get("gold", {})
        if (rank is not None and rank <= gold.get("max_rank", 15)) or usage >= gold.get("min_usage_pct", 15.0):
            return self._rules.get("colors", {}).get("gold", "#FFB800")

        return None

    def _row(self, stat_id: str, slot: str, archetype: str) -> Optional[dict]:
        with self._lock:
            row = self._by_key.get((slot, archetype, stat_id))
            if row is None and archetype != "all":
                row = self._by_key.get((slot, "all", stat_id))
            return row

    def roll_indicator_fallback(self, stat_id: str, slot: str, archetype: str,
                                values: tuple, top_bottom_pct: Optional[float] = None) -> Optional[str]:
        """Roll quality arrow when RePoE tier is unknown — uses the hub meta
        row's own value_min/value_max (the range of values actually seen across
        sampled builds) as a proxy range instead. Averages `values` to a single
        number since the hub range isn't per-value like the RePoE tier ladder."""
        if not values:
            return None
        row = self._row(stat_id, slot, archetype)
        if row is None:
            return None
        lo, hi = row.get("value_min"), row.get("value_max")
        if lo is None or hi is None:
            return None
        pct = _pct_position(sum(values) / len(values), lo, hi)
        if pct is None:
            return None
        return _arrow(pct, top_bottom_pct if top_bottom_pct is not None else self.rule("roll_pct", 0.25))

    def tag_color(self, stat_id: str, slot: str, archetype: str, meta_db) -> Optional[str]:
        """Full badge decision: red > gold > green > None (white).

        green = this mod isn't itself red/gold, but shares a RePoE implicit_tag
        with some mod that *is* red/gold for (slot, archetype) — i.e. "not the
        popular roll itself, but the right family to lock and reroll around."
        `meta_db` is a MetaDB instance (dependency-injected rather than owned
        here — this module stays hub-only, meta_db.py stays RePoE-only)."""
        base = self.badge_color(stat_id, slot, archetype)
        if base:
            return base
        my_tags = self._tags_for_stat(stat_id, meta_db)
        if not my_tags:
            return None
        hot = self._hot_tags(slot, archetype, meta_db)
        if my_tags & hot:
            return self._rules.get("colors", {}).get("green", "#4CAF50")
        return None

    def _tags_for_stat(self, stat_id: str, meta_db) -> set:
        tags: set = set()
        for tmpl in self._stat_to_templates.get(stat_id, []):
            tags |= meta_db.tags_for_template(tmpl)
        return tags

    def _hot_tags(self, slot: str, archetype: str, meta_db) -> set:
        key = (slot, archetype)
        with self._lock:
            cached = self._hot_tags_cache.get(key)
        if cached is not None:
            return cached
        with self._lock:
            stat_ids = {sid for (s, a, sid) in self._by_key if s == slot and a in (archetype, "all")}
        tags: set = set()
        for sid in stat_ids:
            if self.badge_color(sid, slot, archetype):   # red or gold only
                tags |= self._tags_for_stat(sid, meta_db)
        with self._lock:
            self._hot_tags_cache[key] = tags
        return tags

    # ------------------------------------------------------------------
    # Disk cache (raw hub payload — same convention as PriceRepository)
    # ------------------------------------------------------------------

    def _cache_path(self) -> Optional[Path]:
        if self._cache_dir is None:
            return None
        return self._cache_dir / "mod_badge_meta_poe2.json"

    def _save_disk_cache(self, data: dict) -> None:
        path = self._cache_path()
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data), encoding="utf-8")
        except Exception as e:
            log.warning("mod badge cache write failed: %s", e)

    def _load_disk_cache(self) -> Optional[dict]:
        path = self._cache_path()
        if path is None or not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("mod badge cache read failed: %s", e)
            return None
