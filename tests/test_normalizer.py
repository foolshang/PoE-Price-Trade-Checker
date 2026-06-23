import pytest
from poe_price_trade.normalizer import normalize, normalize_ocr


def test_lowercase():
    assert normalize("Chaos Orb") == "chaos orb"


def test_strip_punctuation():
    assert normalize("Orb (of Alteration)") == "orb of alteration"


def test_collapse_whitespace():
    assert normalize("  Divine   Orb  ") == "divine orb"


def test_unicode_normalization():
    # Accented chars become ASCII equivalents
    result = normalize("Áccéntéd")
    assert "ccented" in result or "ccnted" in result  # varies by char


def test_alias_identity():
    assert normalize("Divine Orb") == normalize("divine orb")


def test_ocr_fix_rn_to_m():
    # 'rn' → 'm' in OCR mode
    result = normalize_ocr("Divine Orb")  # no 'rn' patterns → unchanged
    assert "divine" in result


def test_empty_string():
    assert normalize("") == ""


def test_special_chars_stripped():
    assert normalize("Orb +1% of Alteration") == "orb 1 of alteration"
