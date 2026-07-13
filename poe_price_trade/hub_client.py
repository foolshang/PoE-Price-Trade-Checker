"""Fetch prices from poe-data-hub (Firebase Storage) — replaces poe.ninja/poe2scout
as the price source. Stdlib only, no external deps.

Schema reference: D:\\Projects\\Poe_Hub\\SPEC.md (sections 8.1, 8.1a/b/c)."""
from __future__ import annotations
import json
import logging
import urllib.error
import urllib.request
from typing import Optional

log = logging.getLogger(__name__)

HUB_BASE_URL = "https://storage.googleapis.com/poe-data-hub"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}
_TIMEOUT = 15


def _get(path: str) -> dict:
    url = f"{HUB_BASE_URL}/{path}"
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"hub HTTP {e.code}: {url}") from e
    except Exception as e:
        raise RuntimeError(f"hub fetch failed ({url}): {e}") from e


def get_index(game: str) -> Optional[dict]:
    """{game}/prices/index.json — routes a consumer to main/hardcore/event league
    files (SPEC 8.1b). Returns None if the hub is unreachable or the index doesn't
    exist yet — callers must treat that as "not published", not as a hard error."""
    try:
        return _get(f"{game}/prices/index.json")
    except Exception as e:
        log.warning("hub index fetch failed (%s): %s", game, e)
        return None


def get_prices(path: str) -> dict:
    """Fetch a published prices file by its exact hub-relative path
    (e.g. 'poe2/prices/latest.json', 'poe1/prices/hardcore/latest.json')."""
    return _get(path)


def get_league_files(game: str) -> dict:
    """Reshape index.json into the league->file routing table a consumer needs:

        {"main":     {"league": str, "path": str},
         "hardcore": {"league": str, "path": str} | None,
         "events":   [{"league": str, "path": str}, ...]}

    `hardcore` is None both when index.json says so (SPEC 8.1c: no HC variant found
    this cycle) and when index.json itself is unavailable — never guessed/probed.

    Falls back to latest.json's own "league" field (main only, no hardcore/events)
    if index.json can't be fetched, so the app stays usable during a brief hub gap.
    """
    index = get_index(game)
    if index:
        main = index.get("main") or {}
        main_path = main.get("path") or f"{game}/prices/latest.json"
        hardcore = index.get("hardcore")
        events = [
            {"league": e["league"], "path": e["path"]}
            for e in index.get("events", [])
            if e.get("league") and e.get("path")
        ]
        return {
            "main": {"league": main.get("league"), "path": main_path},
            "hardcore": ({"league": hardcore["league"], "path": hardcore["path"]}
                         if hardcore and hardcore.get("league") and hardcore.get("path")
                         else None),
            "events": events,
        }

    latest_path = f"{game}/prices/latest.json"
    try:
        latest = get_prices(latest_path)
        league_name = latest.get("league")
    except Exception as e:
        log.warning("hub latest.json fallback fetch failed (%s): %s", game, e)
        league_name = None
    return {"main": {"league": league_name, "path": latest_path}, "hardcore": None, "events": []}
