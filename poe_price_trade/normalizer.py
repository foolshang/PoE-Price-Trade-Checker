"""Normalize item names so OCR output and API names can be compared."""
import re
import unicodedata


_WHITESPACE = re.compile(r'\s+')
_NON_ALNUM = re.compile(r"[^a-z0-9 '\-]")

# Common OCR substitutions: (wrong, correct)
_OCR_FIXES: list[tuple[str, str]] = [
    ("rn", "m"),   # 'rn' often misread as 'm'
    ("0", "o"),    # digit zero → letter o in names
    ("1", "l"),    # digit 1 → letter l
    ("vv", "w"),
]

# Words that differ between PoE copy text and poe.ninja display names
_ALIAS: dict[str, str] = {
    "exalted orb": "exalted orb",
    "divine orb": "divine orb",
    "mirror of kalandra": "mirror of kalandra",
    "chaos orb": "chaos orb",
}


def normalize(name: str, apply_ocr_fixes: bool = False) -> str:
    """Return a stable lowercase key for fuzzy comparison."""
    text = unicodedata.normalize("NFKD", name)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = _NON_ALNUM.sub(" ", text)
    text = _WHITESPACE.sub(" ", text).strip()

    if apply_ocr_fixes:
        for wrong, correct in _OCR_FIXES:
            text = text.replace(wrong, correct)

    return _ALIAS.get(text, text)


def normalize_ocr(text: str) -> str:
    return normalize(text, apply_ocr_fixes=True)
