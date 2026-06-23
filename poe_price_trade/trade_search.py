"""Build the JSON query body for the PoE official trade search API."""
from __future__ import annotations
from typing import Optional

from .models import ParsedItem, Rarity


def build_query(
    item: ParsedItem,
    selected_stat_ids: list[tuple[str, Optional[float]]],
    league: str,
) -> dict:
    """
    Build a trade search query.

    selected_stat_ids: list of (stat_id, min_value) pairs the user wants to filter on.
                       min_value=None means "mod must be present, any value".
    Returns the JSON body for POST /api/trade[2]/search/<league>.
    """
    query: dict = {
        "query": {
            "status": {"option": "online"},
            "stats": [],
            "filters": {},
        },
        "sort": {"price": "asc"},
    }

    q = query["query"]

    # Item type filter
    if item.rarity in (Rarity.NORMAL, Rarity.MAGIC, Rarity.RARE):
        q["filters"]["type_filters"] = {
            "filters": {
                "rarity": {"option": item.rarity.lower()},
            }
        }
        if item.base_type:
            q["type"] = item.base_type

    elif item.rarity == Rarity.UNIQUE:
        q["name"] = item.item_name
        q["type"] = item.base_type

    # Item level filter (optional: only add if ilvl > 0)
    if item.item_level > 0:
        q["filters"].setdefault("misc_filters", {"filters": {}})
        q["filters"]["misc_filters"]["filters"]["ilvl"] = {"min": item.item_level}

    # Mod filters
    if selected_stat_ids:
        stat_group = {
            "type": "and",
            "filters": [],
        }
        for stat_id, min_val in selected_stat_ids:
            filt: dict = {"id": stat_id, "disabled": False}
            if min_val is not None:
                filt["value"] = {"min": min_val}
            stat_group["filters"].append(filt)
        q["stats"].append(stat_group)

    return query
