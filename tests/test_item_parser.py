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


# ------------------------------------------------------------------
# Header-less clipboard (no { ... Modifier } at all) -- confirmed live
# 2026-07-17 against a real PoE1 client that has no "Advanced Mod
# Description" option to enable in the first place. Real capture from
# debug_logs/last_raw_item.txt (rare "Kraken Grip" Eelskin Gloves).
# ------------------------------------------------------------------

NO_HEADER_RARE_TEXT = """Item Class: Gloves
Rarity: Rare
Kraken Grip
Eelskin Gloves
--------
Evasion Rating: 266 (augmented)
--------
Requirements:
Level: 64
Dex: 56
--------
Sockets: R-R-B-B
--------
Item Level: 82
--------
0.2% of Lightning Damage Leeched as Life (implicit)
15% chance to Unnerve Enemies for 4 seconds on Hit (implicit)
--------
Adds 2 to 22 Lightning Damage to Attacks
+135 to Evasion Rating
+58 to maximum Life
Regenerate 31.6 Life per second
+39% to Cold Resistance
+34% to Chaos Resistance
Searing Exarch Item
Eater of Worlds Item
"""


def test_no_header_item_flags_mods_have_headers_false():
    item = parse_item(NO_HEADER_RARE_TEXT, "poe1")
    assert item is not None
    assert item.mods_have_headers is False


def test_no_header_item_prefix_suffix_count_unknown_not_zero_lie():
    # can't classify without a header -- must come out 0, not a guessed value,
    # so the caller (MetaDB.infer_affixes) knows there's real work to do
    item = parse_item(NO_HEADER_RARE_TEXT, "poe1")
    assert item.prefix_count == 0
    assert item.suffix_count == 0
    assert all(m.affix == "" for m in item.mods if m.mod_type == "explicit")


def test_no_header_item_implicit_lines_tagged_and_excluded_from_explicit():
    item = parse_item(NO_HEADER_RARE_TEXT, "poe1")
    implicits = [m for m in item.mods if m.mod_type == "implicit"]
    assert len(implicits) == 2
    # "(implicit)" suffix stripped from the stored text -- must match RePoE
    # family text later, which never has it
    assert all(not m.text.endswith("(implicit)") for m in implicits)
    assert any("Leeched as Life" in m.text for m in implicits)


def test_no_header_item_influence_labels_not_treated_as_mods():
    item = parse_item(NO_HEADER_RARE_TEXT, "poe1")
    texts = [m.text for m in item.mods]
    assert not any("Searing Exarch Item" in t or "Eater of Worlds Item" in t for t in texts)


def test_no_header_item_explicit_mods_get_distinct_groups():
    # each fallback mod line is its own group -- a shared group=-1 for every
    # mod would wrongly merge them all into one "hybrid" mod for annotate()
    item = parse_item(NO_HEADER_RARE_TEXT, "poe1")
    explicit_groups = [m.group for m in item.mods if m.mod_type == "explicit"]
    assert len(explicit_groups) == len(set(explicit_groups))


HEADER_DRIVEN_TEXT = """Item Class: Boots
Rarity: Rare
Legend's Fortress Sabatons
Fortress Sabatons
--------
Armour: 293 (augmented)
--------
Item Level: 80
--------
{ Prefix Modifier "Legend's" (Tier: 1) — Armour, Evasion }
99(92-100)% increased Armour and Evasion
{ Suffix Modifier "of Grounding" (Tier: 1) — Elemental, Lightning, Ailment }
56(56-60)% reduced Shock duration on you
"""


def test_header_driven_item_unaffected_mods_have_headers_true():
    item = parse_item(HEADER_DRIVEN_TEXT, "poe1")
    assert item is not None
    assert item.mods_have_headers is True
    assert item.prefix_count == 1
    assert item.suffix_count == 1
