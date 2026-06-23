import pytest
from poe_price_trade.matcher import ItemMatcher
from poe_price_trade.models import PriceEntry


def _make_entries():
    names = ["Chaos Orb", "Divine Orb", "Orb of Alteration", "Mirror of Kalandra", "Exalted Orb"]
    return [
        PriceEntry(
            item_name=n,
            normalized_name=n.lower(),
            chaos_value=float(i + 1),
            divine_value=float(i + 1) / 200,
            listing_count=100,
            game_version="poe1",
            category="Currency",
        )
        for i, n in enumerate(names)
    ]


@pytest.fixture
def matcher():
    return ItemMatcher(_make_entries())


def test_exact_match(matcher):
    result = matcher.find("Chaos Orb")
    assert result is not None
    assert result.item_name == "Chaos Orb"


def test_fuzzy_match(matcher):
    # 'Chaos 0rb' (zero instead of O) — OCR common mistake
    result = matcher.find("Chaos 0rb", threshold=0.70)
    assert result is not None
    assert "Chaos" in result.item_name


def test_no_match_below_threshold(matcher):
    result = matcher.find("xyzzy nonsense foobar", threshold=0.90)
    assert result is None


def test_case_insensitive(matcher):
    result = matcher.find("divine orb")
    assert result is not None
    assert result.item_name == "Divine Orb"


def test_partial_name(matcher):
    result = matcher.find("Mirror Kalandra", threshold=0.70)
    # Mirror of Kalandra is close enough
    assert result is not None


def test_find_all_returns_sorted(matcher):
    results = matcher.find_all("Orb", threshold=0.3, limit=5)
    scores = [s for s, _ in results]
    assert scores == sorted(scores, reverse=True)


def test_len(matcher):
    assert len(matcher) == 5
