"""Fuzzy-match OCR text against a list of known item names (offline, no deps)."""
from __future__ import annotations
import difflib
from typing import Optional

from .models import PriceEntry
from .normalizer import normalize_ocr


class ItemMatcher:
    def __init__(self, entries: list[PriceEntry]):
        self._entries = entries
        self._norm_map: dict[str, PriceEntry] = {}
        for e in entries:
            key = e.normalized_name
            # Keep highest-listing-count entry when names collide
            if key not in self._norm_map or e.listing_count > self._norm_map[key].listing_count:
                self._norm_map[key] = e
        self._keys = list(self._norm_map.keys())

    def find(self, ocr_text: str, threshold: float = 0.80) -> Optional[PriceEntry]:
        """Return the best matching PriceEntry or None if below threshold."""
        query = normalize_ocr(ocr_text)
        if not query:
            return None

        # Exact match first
        if query in self._norm_map:
            return self._norm_map[query]

        # Closest fuzzy match
        matches = difflib.get_close_matches(query, self._keys, n=1, cutoff=threshold)
        if matches:
            return self._norm_map[matches[0]]

        return None

    def find_all(self, ocr_text: str, threshold: float = 0.70, limit: int = 5) -> list[tuple[float, PriceEntry]]:
        """Return up to `limit` (score, entry) pairs sorted by score descending."""
        query = normalize_ocr(ocr_text)
        if not query:
            return []

        scored: list[tuple[float, str]] = [
            (difflib.SequenceMatcher(None, query, key).ratio(), key)
            for key in self._keys
        ]
        scored.sort(reverse=True)
        results = []
        for score, key in scored[:limit]:
            if score >= threshold:
                results.append((score, self._norm_map[key]))
        return results

    def __len__(self) -> int:
        return len(self._keys)
