# PLAN.md — PoE Price & Trade Checker (Working Copy)

> Working copy ใน project folder — status table อัปเดตที่นี่
> เอกสาร full spec อยู่ที่ D:\Browser\PLAN.md (read-only reference)

---

## 0.1 ตารางสถานะงาน (Task Status)

| ID | งาน | สถานะ |
|----|------|:----:|
| A1 | price core (client poe1+poe2 / normalizer / matcher / repository+cache) | ✅ เสร็จ (2026-06-23 / session 1) |
| A2 | GameProfile abstraction (แยกภาค) | ✅ เสร็จ (2026-06-23 / session 1) |
| A3 | capture (GDI) + OCR (winrt) + scan | ✅ เสร็จ (2026-06-23 / session 1) |
| A4 | overlay โปร่งแสง + วาดราคา (ตำแหน่งตามข้อ 4) | ✅ เสร็จ (2026-06-23 / session 1) |
| A5 | hotkey F9/F6 + settings F8 (ภาค→ลีก→หน่วยเงิน→ความทึบ) | ✅ เสร็จ (2026-06-23 / session 1) |
| A6 | เทสต์ core offline + build exe | ✅ เสร็จ (2026-06-23 / session 1) |
| B1 | clipboard reader + item parser (poe1/poe2) | ✅ เสร็จ (2026-06-23 / session 1) |
| B2 | mod→stat-id mapping (ดึงตาราง stat จาก GGG) | ✅ เสร็จ (2026-06-23 / session 1) |
| B3 | logic สร้าง trade search (min value พอดี) | ✅ เสร็จ (2026-06-23 / session 1) |
| B4 | auth POESESSID + Cloudflare + search→fetch | ✅ เสร็จ (2026-06-23 / session 1) |
| B5 | trade list panel + เปิด browser + ก๊อป whisper | ✅ เสร็จ (2026-06-23 / session 1) |
| B6 | hotkey F5 + ผูกเข้า overlay | ✅ เสร็จ (2026-06-23 / session 1) |

---

## โครงไฟล์จริง

```
D:\Projects\PoE_Price-Trade_Checker\
  poe_price_trade/
    __init__.py        version
    models.py          PriceEntry / PriceSnapshot / ParsedItem / TradeListing / ScanResult
    profiles.py        GameProfile + POE1_PROFILE + POE2_PROFILE
    normalizer.py      normalize() / normalize_ocr()
    ninja_client.py    NinjaClient — ดึงราคาจาก poe.ninja (PoE1+PoE2)
    matcher.py         ItemMatcher — fuzzy match ด้วย difflib
    repository.py      PriceRepository — cache 30 นาที + disk cache
    config.py          AppConfig — JSON config + DPAPI POESESSID
    capture.py         capture_screen() — GDI BitBlt + DPI aware
    ocr/
      base.py          OcrResult / WordResult / BoundingBox
      windows_ocr.py   WindowsOcrEngine — winrt async OCR
    scan.py            Scanner — capture+OCR+match → ScanResult[]
    clipboard.py       read_text() / write_text() — Windows clipboard
    item_parser.py     parse_item() — clipboard text → ParsedItem
    mod_db.py          ModDatabase — GGG stats endpoint + cache
    trade_search.py    build_query() — JSON สำหรับ trade API
    trade_client.py    TradeClient — search→fetch + SessionExpiredError
    trade_panel.py     TradePanel — tkinter list panel + browser + whisper
    overlay.py         PriceOverlay — transparent click-through window
    hotkeys.py         HotkeyManager — RegisterHotKey background thread
    settings.py        SettingsWindow — F8 settings UI
    app.py             App — main class
    __main__.py        CLI entry
  tests/
    sample_data/       ninja_poe1_currency.json / ninja_poe2_currency.json / sample_items.txt
    test_normalizer.py
    test_matcher.py
    test_ninja_client.py
    test_item_parser.py
    test_repository.py
  run.py               entry point (PyInstaller)
  requirements.txt
  .gitignore
  PLAN.md              (this file)
  history.md
```

## การตัดสินใจที่ทำเองใน session 1

- **folder**: ใช้ `D:\Projects\PoE_Price-Trade_Checker` (current working dir ที่มีอยู่แล้ว)
- **PoE1+PoE2 ทั้งคู่ตั้งแต่แรก**: GameProfile abstraction รองรับทั้ง 2 ภาคตั้งแต่ A1
- **Mode B mod selection**: default = ส่ง query ไม่มี mod filter (แสดงทุก listing) — user เลือก mod ผ่าน UI ในอนาคต (extension ใน B3)
- **winrt packages**: ใช้ `winrt-runtime` + `winrt-Windows.*` individual packages (Python 3.13 compatible)
- **OCR BMP format**: ส่ง 32-bit BMP (GDI BGRA ตรง) ผ่าน BitmapDecoder → SoftwareBitmap

## สิ่งที่ต้องตั้งค่าก่อนรัน

1. ติดตั้ง Python packages: `pip install -r requirements.txt`
2. ใส่ POESESSID ในหน้า Settings (F8) → Trade Auth tab (สำหรับ Mode B)
3. ตรวจสอบ poe.ninja endpoints ใน `profiles.py` ก่อนใช้งานจริง (อาจ outdated)
