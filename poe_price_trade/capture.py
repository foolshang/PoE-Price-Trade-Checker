"""Screen capture using GDI (ctypes). Returns raw BGRA bytes at native resolution.
Call set_dpi_aware() once at app startup so coordinates match the physical display."""
from __future__ import annotations
import ctypes
import ctypes.wintypes
import logging

log = logging.getLogger(__name__)

# GDI constants
_SRCCOPY = 0x00CC0020
_DIB_RGB_COLORS = 0
_BI_RGB = 0


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize",          ctypes.c_uint32),
        ("biWidth",         ctypes.c_int32),
        ("biHeight",        ctypes.c_int32),
        ("biPlanes",        ctypes.c_uint16),
        ("biBitCount",      ctypes.c_uint16),
        ("biCompression",   ctypes.c_uint32),
        ("biSizeImage",     ctypes.c_uint32),
        ("biXPelsPerMeter", ctypes.c_int32),
        ("biYPelsPerMeter", ctypes.c_int32),
        ("biClrUsed",       ctypes.c_uint32),
        ("biClrImportant",  ctypes.c_uint32),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", ctypes.c_uint32 * 3),
    ]


def set_dpi_aware() -> None:
    """Call once at startup. Makes all pixel operations use physical coordinates."""
    try:
        # Per-Monitor v2 (Win10 1703+)
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        log.debug("DPI awareness: Per-Monitor v2")
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
            log.debug("DPI awareness: Per-Monitor")
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
            log.debug("DPI awareness: System DPI")


def get_dpi_scale() -> float:
    """Physical DPI divided by 96 (standard DPI). E.g. 1.25 at 125% scaling."""
    dc = ctypes.windll.user32.GetDC(None)
    dpi = ctypes.windll.gdi32.GetDeviceCaps(dc, 88)  # LOGPIXELSX
    ctypes.windll.user32.ReleaseDC(None, dc)
    return dpi / 96.0


def get_screen_size() -> tuple[int, int]:
    """Return primary monitor physical size (width, height) in pixels."""
    user32 = ctypes.windll.user32
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def get_cursor_pos() -> tuple[int, int]:
    """Return current cursor position in physical pixels."""
    class _POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    pt = _POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def capture_region(x: int, y: int, w: int, h: int) -> tuple[bytes, int, int]:
    """Capture a rectangular subregion of the primary display."""
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    screen_dc = user32.GetDC(None)
    mem_dc = gdi32.CreateCompatibleDC(screen_dc)
    bitmap = gdi32.CreateCompatibleBitmap(screen_dc, w, h)
    gdi32.SelectObject(mem_dc, bitmap)
    gdi32.BitBlt(mem_dc, 0, 0, w, h, screen_dc, x, y, _SRCCOPY)

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = -h
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = _BI_RGB

    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem_dc, bitmap, 0, h, buf, ctypes.byref(bmi), _DIB_RGB_COLORS)

    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(None, screen_dc)

    return bytes(buf), w, h


def capture_screen() -> tuple[bytes, int, int]:
    """Capture primary display. Returns (bgra_bytes, width_px, height_px)."""
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    screen_dc = user32.GetDC(None)
    mem_dc = gdi32.CreateCompatibleDC(screen_dc)

    width = user32.GetSystemMetrics(0)    # SM_CXSCREEN
    height = user32.GetSystemMetrics(1)   # SM_CYSCREEN

    bitmap = gdi32.CreateCompatibleBitmap(screen_dc, width, height)
    gdi32.SelectObject(mem_dc, bitmap)
    gdi32.BitBlt(mem_dc, 0, 0, width, height, screen_dc, 0, 0, _SRCCOPY)

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = width
    bmi.bmiHeader.biHeight = -height   # negative = top-down
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = _BI_RGB

    buf_size = width * height * 4
    buf = ctypes.create_string_buffer(buf_size)
    gdi32.GetDIBits(mem_dc, bitmap, 0, height, buf, ctypes.byref(bmi), _DIB_RGB_COLORS)

    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(None, screen_dc)

    return bytes(buf), width, height


def bgra_to_bmp(bgra: bytes, width: int, height: int) -> bytes:
    """Wrap raw BGRA bytes in a BMP file header for use with BitmapDecoder."""
    import struct
    pixel_offset = 54
    file_size = pixel_offset + len(bgra)
    file_hdr = struct.pack("<2sIHHI", b"BM", file_size, 0, 0, pixel_offset)
    info_hdr = struct.pack(
        "<IiiHHIIiiII",
        40, width, -height, 1, 32, 0, len(bgra), 0, 0, 0, 0,
    )
    return file_hdr + info_hdr + bgra
