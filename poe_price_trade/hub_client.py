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


def hub_chaos_value(entry: dict) -> float:
    """An entry's price in chaos from a hub prices payload (SPEC 8.1). The hub's
    `chaos_value` is an additive field: PoE2 entries carry it (their `value` is
    in exalted), PoE1 entries don't (their `value` already IS chaos,
    value_currency == "chaos"). Absent and not chaos -> 0.0, never a guess."""
    chaos = entry.get("chaos_value")
    if chaos is not None:
        return float(chaos)
    if entry.get("value_currency") == "chaos":
        return float(entry.get("value") or 0.0)
    return 0.0


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


def get_meta(game: str) -> Optional[dict]:
    """{game}/meta/latest.json — mod-popularity data (build frequency per slot/
    archetype/stat_id). PoE2-only on the hub as of this writing; poe1 simply 404s.
    Returns None on any failure so callers can degrade silently (SPEC 8.2)."""
    try:
        return _get(f"{game}/meta/latest.json")
    except Exception as e:
        log.warning("hub meta fetch failed (%s): %s", game, e)
        return None


def get_passives(game: str) -> Optional[dict]:
    """{game}/passives/latest.json — notable/keystone passive popularity per
    (skill_type, skill, level_bracket). Returns None on any failure so callers
    can degrade silently, same posture as get_meta."""
    try:
        return _get(f"{game}/passives/latest.json")
    except Exception as e:
        log.warning("hub passives fetch failed (%s): %s", game, e)
        return None


def get_gems(game: str) -> Optional[dict]:
    """{game}/gems.json — gem list for autocomplete. Returns None on any
    failure so callers can degrade (free-type without suggestions)."""
    try:
        return _get(f"{game}/gems.json")
    except Exception as e:
        log.warning("hub gems fetch failed (%s): %s", game, e)
        return None


def get_skills_index(game: str) -> Optional[dict]:
    """{game}/skills/index.json — routes a consumer to each skill's own mod
    file (skill_ref.py). Returns None on any failure so callers can degrade
    silently, same posture as get_meta/get_passives."""
    try:
        return _get(f"{game}/skills/index.json")
    except Exception as e:
        log.warning("hub skills index fetch failed (%s): %s", game, e)
        return None


def get_skill_file(path: str) -> Optional[dict]:
    """Fetch a per-skill mod file by its exact hub-relative path, as given by
    a skills/index.json entry's "path" field (e.g.
    'poe2/skills/main/earthquake.json'). Returns None on any failure."""
    try:
        return _get(path)
    except Exception as e:
        log.warning("hub skill file fetch failed (%s): %s", path, e)
        return None


def get_skills_dictionary(game: str) -> Optional[dict]:
    """{game}/skills/dictionary.json — stat_id -> display text, for the mod
    rows in a per-skill file. Returns None on any failure."""
    try:
        return _get(f"{game}/skills/dictionary.json")
    except Exception as e:
        log.warning("hub skills dictionary fetch failed (%s): %s", game, e)
        return None


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
