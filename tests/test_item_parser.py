"""Offline tests for item_parser — no imports that require Windows APIs."""
from pathlib import Path
import pytest
from poe_price_trade.item_parser import parse_item
from poe_price_trade.models import Rarity

SAMPLE_FILE = Path(__file__).parent / "sample_data" / "sample_items.txt"


def _load_item(marker: str) -> str:
    """Items are delimited by ##MARKER## lines."""
    text = SAMPLE_FILE.read_text(encoding="utf-8")
    parts = text.split(f"##{marker}##")
    if len(parts) < 2:
        return ""
    # Take text up to the next ##...## marker
    section = parts[1]
    next_marker = section.find("##")
    if next_marker >= 0:
        section = section[:next_marker]
    return section.strip()


RARE_TEXT = _load_item("RARE_ITEM")
CURRENCY_TEXT = _load_item("CURRENCY")
UNIQUE_TEXT = _load_item("UNIQUE")


def test_parse_rare_item():
    item = parse_item(RARE_TEXT, "poe1")
    assert item is not None
    assert item.rarity == Rarity.RARE
    assert "Astral Plate" in item.base_type or "Dire Carapace" in item.item_name


def test_parse_rare_item_level():
    item = parse_item(RARE_TEXT, "poe1")
    assert item is not None
    assert item.item_level == 85


def test_parse_rare_mods():
    item = parse_item(RARE_TEXT, "poe1")
    assert item is not None
    assert len(item.mods) > 0
    # Should have resistance mods
    mod_texts = [m.text for m in item.mods]
    assert any("Resistance" in t for t in mod_texts)


def test_parse_currency_item():
    item = parse_item(CURRENCY_TEXT, "poe1")
    assert item is not None
    assert item.rarity == Rarity.CURRENCY
    assert "Chaos Orb" in item.item_name


def test_parse_unique_item():
    item = parse_item(UNIQUE_TEXT, "poe1")
    assert item is not None
    assert item.rarity == Rarity.UNIQUE
    assert "Dying Sun" in item.item_name


def test_parse_none_on_empty():
    assert parse_item("", "poe1") is None


def test_parse_none_on_non_item():
    assert parse_item("Hello world, this is not an item", "poe1") is None


def test_poe2_game_version():
    item = parse_item(RARE_TEXT, "poe2")
    assert item is not None
    assert item.game_version == "poe2"


def test_mod_values_extracted():
    item = parse_item(RARE_TEXT, "poe1")
    assert item is not None
    # At least one mod should have a numeric value
    assert any(m.value is not None for m in item.mods)
