#!/usr/bin/env python3
"""build_icon.py — one-off generator for poe_price_trade/assets/icon.ico.

Not invoked at runtime (same role as build_mod_meta.py) — run manually,
commit the generated .ico. Draws a simple coin glyph in the app's existing
accent color (see app.py's BG/FG/ACC constants) so the tray/taskbar icon
matches the rest of the UI without needing an external image asset.

Usage:
    python tools/build_icon.py
"""
from __future__ import annotations
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_BG = (28, 28, 28, 255)      # #1C1C1C — matches app.py's window background
_ACC = (200, 160, 80, 255)   # #C8A050 — matches app.py's accent color
_DARK = (28, 20, 20, 255)

_SIZE = 256
_OUT = Path(__file__).resolve().parent.parent / "poe_price_trade" / "assets" / "icon.ico"


def _build_base_image() -> Image.Image:
    img = Image.new("RGBA", (_SIZE, _SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = 8
    d.ellipse((pad, pad, _SIZE - pad, _SIZE - pad), fill=_ACC, outline=_DARK, width=6)

    try:
        font = ImageFont.truetype("segoeuib.ttf", 150)
    except Exception:
        font = ImageFont.load_default()

    text = "P"
    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((_SIZE - tw) / 2 - bbox[0], (_SIZE - th) / 2 - bbox[1]), text,
           font=font, fill=_DARK)
    return img


def main() -> None:
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    img = _build_base_image()
    img.save(_OUT, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
    print(f"Wrote {_OUT}")


if __name__ == "__main__":
    main()
