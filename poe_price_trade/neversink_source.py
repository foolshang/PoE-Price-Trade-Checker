"""NeverSink base filter — GitHub fetch + cache. Stdlib urllib only, same
style as hub_client.py (no `gh` CLI / token — that's only available in the
dev shell, not the shipped app).

NeverSink's GitHub releases carry no binary assets (`gh api .../releases/latest
--jq .assets` returns `[]` for both repos, verified live) — the .filter files
live in the repo itself at the release tag. Filenames confirmed live
2026-07-24 against both repos' latest tags:
  poe1: "NeverSink's filter - {N}-{LEVEL}.filter"
  poe2: "NeverSink's filter 2 - {N}-{LEVEL}.filter"
LEVELS below is the real 0-6 strictness ladder from those repos.
"""
from __future__ import annotations
import json
import logging
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import filter_core

log = logging.getLogger(__name__)

REPO = filter_core.NEVERSINK_REPO
LEVELS = filter_core.NEVERSINK_LEVELS
DEFAULT_STRICTNESS = 2  # Semi-Strict

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}
_TIMEOUT = 15
_CHECK_INTERVAL_HOURS = 24  # GitHub release check cadence — Refresh button (force=True) bypasses this


_filename = filter_core.neversink_filename


def get_latest_tag(game: str) -> Optional[str]:
    if game not in REPO:
        return None
    url = filter_core.neversink_latest_api_url(game)
    req = urllib.request.Request(url, headers={**_HEADERS, "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read())
        return data.get("tag_name")
    except Exception as e:
        log.warning("NeverSink release lookup failed (%s): %s", game, e)
        return None


def _download_file(game: str, tag: str, strictness: int) -> str:
    url = filter_core.neversink_file_url(game, tag, strictness)
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _game_cache_dir(cache_dir: Path, game: str) -> Path:
    d = cache_dir / "neversink" / game
    d.mkdir(parents=True, exist_ok=True)
    return d


def _last_check_path(cache_dir: Path, game: str) -> Path:
    return _game_cache_dir(cache_dir, game) / "last_check.json"


def _load_last_check(cache_dir: Path, game: str) -> dict:
    try:
        return json.loads(_last_check_path(cache_dir, game).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_last_check(cache_dir: Path, game: str, tag: str) -> None:
    try:
        payload = {"tag": tag, "checked_at": datetime.now(timezone.utc).isoformat()}
        _last_check_path(cache_dir, game).write_text(json.dumps(payload), encoding="utf-8")
    except Exception as e:
        log.warning("NeverSink last_check save failed: %s", e)


def _cached_filter_path(cache_dir: Path, game: str, tag: str, strictness: int) -> Path:
    return _game_cache_dir(cache_dir, game) / f"{tag}_{strictness}.filter"


def _find_any_cached(cache_dir: Path, game: str, strictness: int) -> Optional[Path]:
    """Last-resort fallback when GitHub is unreachable and there's no cache
    for the currently-known tag: any previously cached file for this
    strictness, regardless of tag."""
    matches = sorted(_game_cache_dir(cache_dir, game).glob(f"*_{strictness}.filter"))
    return matches[-1] if matches else None


def fetch_base_filter(game: str, strictness: int, cache_dir: Path,
                       force: bool = False) -> tuple:
    """(filter_text, tag_used) — filter_text is None if nothing could be
    fetched or found in cache at all (caller must skip the base-filter merge
    then, per the failure-mode table: "GitHub ดึงไม่ได้ → ใช้ base จาก cache
    + แจ้ง version ที่ใช้", "ทั้งคู่ไม่มี → ไม่เขียนทับไฟล์เดิม"). Never raises."""
    last = _load_last_check(cache_dir, game)
    stale_check = True
    checked_at = last.get("checked_at")
    if checked_at:
        try:
            dt = datetime.fromisoformat(checked_at)
            stale_check = (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0 > _CHECK_INTERVAL_HOURS
        except Exception:
            stale_check = True

    tag = last.get("tag")
    if force or stale_check or not tag:
        fresh_tag = get_latest_tag(game)
        if fresh_tag:
            tag = fresh_tag
            _save_last_check(cache_dir, game, tag)
        # fresh_tag being None just means "keep whatever tag we already knew" —
        # not a hard failure, disk cache for that tag may still be usable below.

    if tag:
        cached_path = _cached_filter_path(cache_dir, game, tag, strictness)
        if cached_path.exists() and not force:
            try:
                return cached_path.read_text(encoding="utf-8"), tag
            except Exception as e:
                log.warning("NeverSink cache read failed: %s", e)
        try:
            text = _download_file(game, tag, strictness)
            try:
                cached_path.write_text(text, encoding="utf-8")
            except Exception as e:
                log.warning("NeverSink cache write failed: %s", e)
            return text, tag
        except Exception as e:
            log.warning("NeverSink download failed (%s tag=%s): %s", game, tag, e)
            if cached_path.exists():
                try:
                    return cached_path.read_text(encoding="utf-8"), tag
                except Exception:
                    pass

    fallback = _find_any_cached(cache_dir, game, strictness)
    if fallback:
        fallback_tag = fallback.stem.rsplit("_", 1)[0]
        try:
            return fallback.read_text(encoding="utf-8"), fallback_tag
        except Exception as e:
            log.warning("NeverSink fallback cache read failed: %s", e)
    return None, None
