"""Mode A: Capture screen → OCR → fuzzy-match → return ScanResults."""
from __future__ import annotations
import logging
from typing import Optional

from .capture import capture_screen, bgra_to_bmp
from .models import ScanResult
from .repository import PriceRepository
from .ocr.windows_ocr import WindowsOcrEngine
from .ocr.base import OcrResult, WordResult

log = logging.getLogger(__name__)

_MIN_WORD_LEN = 3
_MAX_WORD_LEN = 60


class Scanner:
    def __init__(self, repository: PriceRepository, dpi_scale: float = 1.0):
        self._repo = repository
        self._dpi = dpi_scale
        self._ocr = WindowsOcrEngine(language="en")

    def scan(self, threshold: float = 0.80) -> list[ScanResult]:
        """Capture current screen, OCR it, match every word/phrase against price DB."""
        if not self._repo.is_ready():
            log.warning("Scan called before repository is ready")
            return []

        bgra, w, h = capture_screen()
        log.debug("Captured %dx%d", w, h)

        bmp = bgra_to_bmp(bgra, w, h)
        ocr_result: OcrResult = self._ocr.recognize(bmp)
        log.debug("OCR: %d lines, %d words", len(ocr_result.lines), len(ocr_result.words))

        results: list[ScanResult] = []
        seen: set[str] = set()

        # Try matching multi-word phrases (2-word, 3-word) then single words
        for line in ocr_result.lines:
            words = line.words
            n = len(words)
            for window in (3, 2, 1):
                for i in range(n - window + 1):
                    phrase_words = words[i:i + window]
                    phrase = " ".join(pw.text for pw in phrase_words)
                    if len(phrase) < _MIN_WORD_LEN or len(phrase) > _MAX_WORD_LEN:
                        continue

                    key = phrase.lower()
                    if key in seen:
                        continue

                    entry = self._repo.lookup(phrase, threshold)
                    if entry is not None:
                        seen.add(key)
                        # Bounding box spans all words in the phrase
                        first_bb = phrase_words[0].bbox
                        last_bb = phrase_words[-1].bbox
                        px = first_bb.x
                        py = first_bb.y
                        pw = last_bb.right - first_bb.x
                        ph = max(bb.bbox.height for bb in phrase_words)

                        # Convert physical px → logical px for overlay
                        lx = int(px / self._dpi)
                        ly = int(py / self._dpi)
                        lw = int(pw / self._dpi)
                        lh = int(ph / self._dpi)

                        results.append(ScanResult(
                            item_name=entry.item_name,
                            price_entry=entry,
                            bbox_x=lx,
                            bbox_y=ly,
                            bbox_w=lw,
                            bbox_h=lh,
                            confidence=1.0,
                        ))
                        log.debug("Match: '%s' → '%s' (%.2fc)", phrase, entry.item_name, entry.chaos_value)

        log.info("Scan done: %d matches", len(results))
        return results
