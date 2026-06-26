"""Mode A: Capture screen → OCR → fuzzy-match → return ScanResults."""
from __future__ import annotations
import logging
from typing import Optional

from .capture import capture_screen, capture_region, get_screen_size, bgra_to_bmp
from .models import ScanResult
from .repository import PriceRepository
from .ocr.windows_ocr import WindowsOcrEngine
from .ocr.base import OcrResult, WordResult

log = logging.getLogger(__name__)

_MIN_WORD_LEN = 3
_MAX_WORD_LEN = 60


class Scanner:
    def __init__(self, repository: PriceRepository):
        self._repo = repository
        self._ocr = WindowsOcrEngine(language="en")

    def scan(self, threshold: float = 0.80) -> list[ScanResult]:
        """Capture full screen, OCR it, match every word/phrase against price DB."""
        if not self._repo.is_ready():
            log.warning("Scan called before repository is ready")
            return []

        bgra, w, h = capture_screen()
        log.debug("Captured %dx%d", w, h)

        bmp = bgra_to_bmp(bgra, w, h)
        ocr_result: OcrResult = self._ocr.recognize(bmp)
        log.debug("OCR: %d lines, %d words", len(ocr_result.lines), len(ocr_result.words))

        results = self._match_ocr(ocr_result, offset_x=0, offset_y=0, threshold=threshold)
        log.info("Scan done: %d matches", len(results))
        return results

    def scan_region(self, cx: int, cy: int, threshold: float = 0.80) -> list[ScanResult]:
        """Capture a region around cursor (physical px), OCR and match.
        Used by hover mode — much faster than full-screen scan."""
        if not self._repo.is_ready():
            return []

        sw, sh = get_screen_size()
        rx, ry = 500, 350  # half-width/height of capture area
        x = max(0, cx - rx)
        y = max(0, cy - ry)
        w = min(sw, cx + rx) - x
        h = min(sh, cy + ry) - y
        if w <= 0 or h <= 0:
            return []

        bgra, w, h = capture_region(x, y, w, h)
        bmp = bgra_to_bmp(bgra, w, h)
        ocr_result: OcrResult = self._ocr.recognize(bmp)

        results = self._match_ocr(ocr_result, offset_x=x, offset_y=y, threshold=threshold)
        log.debug("Hover scan at (%d,%d): %d matches", cx, cy, len(results))
        return results

    def _match_ocr(self, ocr_result: OcrResult, offset_x: int, offset_y: int,
                   threshold: float) -> list[ScanResult]:
        """Match OCR result against price DB. offset_x/y converts region coords to screen coords."""
        results: list[ScanResult] = []
        seen: set[str] = set()

        for line in ocr_result.lines:
            words = line.words
            n = len(words)
            for window in (3, 2):
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
                        first_bb = phrase_words[0].bbox
                        last_bb = phrase_words[-1].bbox
                        # Add region origin to get screen-space coordinates
                        px = first_bb.x + offset_x
                        py = first_bb.y + offset_y
                        pw = last_bb.right - first_bb.x
                        ph = max(bb.bbox.height for bb in phrase_words)

                        results.append(ScanResult(
                            item_name=entry.item_name,
                            price_entry=entry,
                            bbox_x=px,
                            bbox_y=py,
                            bbox_w=pw,
                            bbox_h=ph,
                            confidence=1.0,
                        ))
                        log.debug("Match: '%s' → '%s'", phrase, entry.item_name)

        return results
