"""Real item names from GGG's trade data (trade(2)/data/items), cached on disk.

Used by the whitelist filter as a second opinion on names NeverSink's base filter does not use: a
`BaseType ==` line with a name the game does not know makes it reject the whole filter. Desktop only
(network + disk); the pure filter engine just receives the set. Never raises - no data = empty set.
"""
from __future__ import annotations
import json
import logging
import time
import urllib.request
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

URLS = {
    "poe1": "https://www.pathofexile.com/api/trade/data/items",
    "poe2": "https://www.pathofexile.com/api/trade2/data/items",
}
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
TTL_SECONDS = 7 * 86400


def names_from_payload(data: dict) -> set:
    out = set()
    for grp in (data or {}).get("result", []) or []:
        for e in grp.get("entries", []) or []:
            for k in ("name", "type", "text"):
                if e.get(k):
                    out.add(str(e[k]))
    return out


def get_names(game: str, cache_dir: Optional[Path]) -> set:
    path = Path(cache_dir) / f"trade_items_{game}.json" if cache_dir else None
    cached = None
    try:
        if path and path.exists():
            cached = json.loads(path.read_text(encoding="utf-8"))
            if time.time() - path.stat().st_mtime < TTL_SECONDS:
                return set(cached)
    except Exception as e:
        log.warning("trade names cache read failed: %s", e)
    try:
        req = urllib.request.Request(URLS[game], headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            names = names_from_payload(json.loads(resp.read()))
        if names and path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(sorted(names), ensure_ascii=False), encoding="utf-8")
        if names:
            return names
    except Exception as e:
        log.warning("trade names fetch failed: %s", e)
    return set(cached or ())
