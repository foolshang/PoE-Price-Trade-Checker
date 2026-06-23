"""Windows OCR engine via WinRT (winrt-Windows.Media.Ocr package).
Requires: pip install winrt-runtime winrt-Windows.Media.Ocr winrt-Windows.Graphics.Imaging
          winrt-Windows.Storage.Streams winrt-Windows.Globalization winrt-Windows.Foundation
"""
from __future__ import annotations
import asyncio
import logging

from .base import BoundingBox, LineResult, OcrResult, WordResult

log = logging.getLogger(__name__)


def _import_winrt():
    """Lazy import so the rest of the app loads even without winrt installed."""
    try:
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.graphics.imaging import BitmapDecoder, BitmapPixelFormat, BitmapAlphaMode, SoftwareBitmap
        from winrt.windows.storage.streams import InMemoryRandomAccessStream, DataWriter
        from winrt.windows.globalization import Language
        return OcrEngine, BitmapDecoder, BitmapPixelFormat, BitmapAlphaMode, SoftwareBitmap, InMemoryRandomAccessStream, DataWriter, Language
    except ImportError as e:
        raise ImportError(
            "winrt packages not installed. Run:\n"
            "  pip install winrt-runtime winrt-Windows.Media.Ocr "
            "winrt-Windows.Graphics.Imaging winrt-Windows.Storage.Streams "
            "winrt-Windows.Globalization winrt-Windows.Foundation"
        ) from e


async def _recognize_async(bmp_bytes: bytes, language: str = "en") -> OcrResult:
    (OcrEngine, BitmapDecoder, BitmapPixelFormat, BitmapAlphaMode,
     SoftwareBitmap, InMemoryRandomAccessStream, DataWriter, Language) = _import_winrt()

    lang = Language(language)
    engine = OcrEngine.try_create_from_language(lang)
    if engine is None:
        engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        raise RuntimeError("Could not create OCR engine. Ensure Windows OCR is enabled for English.")

    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(bytearray(bmp_bytes))
    await writer.store_async()
    writer.detach_stream()
    stream.seek(0)

    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()

    result = await engine.recognize_async(bitmap)

    lines: list[LineResult] = []
    for ocr_line in result.lines:
        words: list[WordResult] = []
        for w in ocr_line.words:
            r = w.bounding_rect
            words.append(WordResult(
                text=w.text,
                bbox=BoundingBox(r.x, r.y, r.width, r.height),
            ))
        text = " ".join(w.text for w in words)
        lines.append(LineResult(text=text, words=words))

    return OcrResult(lines=lines)


class WindowsOcrEngine:
    def __init__(self, language: str = "en"):
        self._language = language

    def recognize(self, bmp_bytes: bytes) -> OcrResult:
        """Synchronous wrapper around the async WinRT OCR call."""
        return asyncio.run(_recognize_async(bmp_bytes, self._language))
