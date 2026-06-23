"""Official PoE trade API client. Requires POESESSID for authentication.
Handles Cloudflare-compatible headers. Raises SessionExpiredError on 401/403."""
from __future__ import annotations
import json
import logging
import time
import urllib.error
import urllib.request
from typing import Optional

from .models import TradeListing
from .profiles import GameProfile

log = logging.getLogger(__name__)

_MAX_FETCH_IDS = 10  # API limit per fetch call
_RATE_LIMIT_SLEEP = 0.5  # seconds between batch fetches


class SessionExpiredError(Exception):
    """Raised when POESESSID is invalid or expired (401/403)."""


class TradeError(Exception):
    pass


def _make_headers(session_id: Optional[str]) -> dict:
    h = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json",
        "Origin": "https://www.pathofexile.com",
        "Referer": "https://www.pathofexile.com/",
        "X-Requested-With": "XMLHttpRequest",
    }
    if session_id:
        h["Cookie"] = f"POESESSID={session_id}"
    return h


def _http_post(url: str, body: dict, session_id: Optional[str]) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=_make_headers(session_id), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise SessionExpiredError("POESESSID expired or invalid") from e
        body_text = e.read().decode("utf-8", errors="replace")
        raise TradeError(f"Trade API POST {e.code}: {body_text[:300]}") from e


def _http_get(url: str, session_id: Optional[str]) -> dict:
    req = urllib.request.Request(url, headers=_make_headers(session_id))
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise SessionExpiredError("POESESSID expired or invalid") from e
        raise TradeError(f"Trade API GET {e.code}: {url}") from e


def _parse_listing(result: dict) -> TradeListing:
    listing = result.get("listing", {})
    item = result.get("item", {})

    price = listing.get("price", {})
    amount = float(price.get("amount", 0))
    currency = price.get("currency", "chaos")
    seller = listing.get("account", {}).get("name", "")
    whisper = listing.get("whisper", "")
    ilvl = item.get("ilvl", 0)
    listing_id = result.get("id", "")

    mods: list[str] = []
    for mod_type in ("explicitMods", "implicitMods", "craftedMods", "fracturedMods"):
        mods.extend(item.get(mod_type, []))

    return TradeListing(
        price_amount=amount,
        price_currency=currency,
        seller=seller,
        item_level=ilvl,
        mods=mods,
        whisper=whisper,
        listing_id=listing_id,
    )


class TradeClient:
    def __init__(self, profile: GameProfile, session_id: Optional[str] = None):
        self._profile = profile
        self._session_id = session_id

    def update_session(self, session_id: Optional[str]) -> None:
        self._session_id = session_id

    def search(self, query: dict, league: str) -> tuple[str, list[str]]:
        """POST search query. Returns (query_id, list_of_result_ids)."""
        url = self._profile.trade_search_url.format(league=league)
        log.debug("Trade search: %s", url)
        resp = _http_post(url, query, self._session_id)
        query_id = resp.get("id", "")
        result_ids = resp.get("result", [])
        total = resp.get("total", len(result_ids))
        log.info("Trade search: %d results (id=%s)", total, query_id)
        return query_id, result_ids

    def fetch(self, result_ids: list[str], query_id: str) -> list[TradeListing]:
        """Fetch listing details for up to _MAX_FETCH_IDS ids per call."""
        listings: list[TradeListing] = []
        ids_to_fetch = result_ids[:_MAX_FETCH_IDS]

        for i in range(0, len(ids_to_fetch), _MAX_FETCH_IDS):
            batch = ids_to_fetch[i:i + _MAX_FETCH_IDS]
            ids_str = ",".join(batch)
            url = self._profile.trade_fetch_url.format(ids=ids_str)
            url += f"?query={query_id}"
            log.debug("Trade fetch batch %d ids", len(batch))
            resp = _http_get(url, self._session_id)
            for item in resp.get("result", []):
                try:
                    listings.append(_parse_listing(item))
                except Exception as e:
                    log.warning("Failed to parse listing: %s", e)
            if i + _MAX_FETCH_IDS < len(ids_to_fetch):
                time.sleep(_RATE_LIMIT_SLEEP)

        return listings

    def search_and_fetch(self, query: dict, league: str) -> list[TradeListing]:
        """Convenience: search then fetch first page of results."""
        query_id, result_ids = self.search(query, league)
        if not result_ids:
            return []
        return self.fetch(result_ids, query_id)
