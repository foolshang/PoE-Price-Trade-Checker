# PoE Price & Trade Checker — History (Project Changelog)

> รูปแบบ entry: วันที่ — สรุปสิ่งที่ทำ — ไฟล์ที่แตะ — สถานะ/ปัญหาค้าง
> เพิ่ม entry ใหม่ไว้ **บนสุด** เสมอ

---

## 2026-06-24 — bug fixes จาก live run (session 3)

**สรุป:** รัน app จริง พบและแก้ 2 bugs + เพิ่ม screen size logging

**ปัญหาที่แก้:**
- `config.py`: เปลี่ยน `encoding="utf-8"` → `"utf-8-sig"` แก้ `Config load failed: Unexpected UTF-8 BOM` — config.json บน Windows อาจมี BOM ทำให้ json.load() ล้มเหลวและ settings ไม่ถูก save/load
- `app.py` + `capture.py`: เพิ่ม `get_screen_size()` และ log จอที่ startup (`จอ 3440×1440 DPI×1.00`) — ยืนยันว่า detect ถูก
- `app.py`: เพิ่ม single-instance mutex (`PoePriceTrade_SingleInstance`) — ป้องกัน 2 instance รันพร้อมกัน ซึ่งทำให้ `RegisterHotKey failed err=1409` ทุก hotkey

**ยืนยันจาก live log:**
- Screen: 3440×1440 DPI scale: 1.00 ✓
- Hotkeys registered (ไม่มี failure) ✓
- Loaded 48 price entries (poe.ninja Runes of Aldur) ✓
- Scan ทำงาน ✓

**ไฟล์ที่แก้:**
```
poe_price_trade/config.py, app.py, capture.py
```

**ค้างอยู่:**
- ทดสอบ overlay ขณะเล่นเกมจริง (windowed fullscreen 3440×1440)
- Trade API ยังไม่ได้ทดสอบด้วย POESESSID จริง

---

## 2026-06-23 — แก้ UI + bug fixes (session 2)

**สรุป:** แก้ปัญหาราคาไม่แสดง + เพิ่ม status log + ลบ currency selector

**ปัญหาที่แก้:**
- `clipboard.py`: เพิ่ม `.restype = ctypes.c_void_p` ให้ GlobalLock/GlobalAlloc/GetClipboardData — แก้ access violation บน 64-bit Windows
- `ninja_client.py`: เขียน `_parse_exchange_overview()` ใหม่ทั้งหมด รองรับ PoE2 JSON จริง (`core.items`, `core.rates.chaos`, `lines[].primaryValue`) — ก่อนหน้านี้ได้ 0 entries
- `ocr/windows_ocr.py`: ติดตั้ง `winrt-Windows.Foundation.Collections` — แก้ `No module named 'winrt.windows.foundation.collections'`
- `tests/sample_data/sample_items.txt`: เปลี่ยน delimiter เป็น `##MARKER##` — แก้ parse ไม่ผ่านเพราะ `----` ชนกับ `--------` ใน PoE item text
- `app.py`: ลบ `_currency_var` + currency radio buttons ออก; แทนที่ด้วย `_log_text` widget (6 บรรทัด, color tags); ลบ `_on_f6_currency` + F6 hotkey; แสดงสถานะ real-time ทุกขั้นตอน
- `requirements.txt`: เพิ่ม `winrt-Windows.Foundation.Collections>=2.0`

**ไฟล์ที่แก้:**
```
poe_price_trade/app.py, clipboard.py, ninja_client.py,
ocr/windows_ocr.py, requirements.txt,
tests/sample_data/sample_items.txt, tests/test_item_parser.py
```

**ค้างอยู่:**
- ทดสอบ overlay บนเครื่องจริงขณะเล่นเกม
- Trade API ยังไม่ได้ทดสอบด้วย POESESSID จริง

---

## 2026-06-23 — เขียนโค้ดทั้งหมดครั้งแรก (Phase A1–B6 ทั้งหมด)

**สรุป:** สร้าง project ใหม่ทั้งหมดตาม PLAN.md ครบทั้ง Phase 1 (A1–A6) และ Phase 2 (B1–B6)

**Phase ที่ทำ:**
- **A1** price core: `ninja_client.py` + `normalizer.py` + `matcher.py` + `repository.py` + `models.py`
- **A2** GameProfile: `profiles.py` — POE1_PROFILE + POE2_PROFILE แยก endpoints + categories ครบ
- **A3** capture + OCR + scan: `capture.py` (GDI BitBlt, DPI-aware) + `ocr/base.py` + `ocr/windows_ocr.py` (winrt async) + `scan.py`
- **A4** overlay: `overlay.py` — transparent click-through (WS_EX_LAYERED|WS_EX_TRANSPARENT) + PriceLabel (shadow + gold text)
- **A5** hotkeys + settings: `hotkeys.py` (RegisterHotKey background thread) + `settings.py` (notebook UI: Game/Hotkeys/Trade Auth/Advanced)
- **A6** tests offline + entry points: `tests/` (5 test files + sample data) + `run.py` + `requirements.txt`
- **B1** clipboard + item parser: `clipboard.py` (ctypes) + `item_parser.py` (PoE1/PoE2 clipboard format)
- **B2** mod DB: `mod_db.py` — fetch GGG stats endpoint + disk cache 7 วัน + fuzzy match
- **B3** trade search query: `trade_search.py` — build_query() รองรับ selected stat_ids + min_value
- **B4** trade client + auth: `trade_client.py` — POESESSID cookie + Cloudflare headers + SessionExpiredError
- **B5** trade panel: `trade_panel.py` — tkinter Treeview แสดง listings + Open Browser + Copy Whisper
- **B6** hotkey F5 + wiring: ทั้งหมดเชื่อมใน `app.py` (F5→parse clipboard→trade search→show panel)

**ไฟล์ที่สร้าง (ใหม่ทั้งหมด):**
```
poe_price_trade/__init__.py, models.py, profiles.py, normalizer.py,
ninja_client.py, matcher.py, repository.py, config.py, capture.py,
ocr/__init__.py, ocr/base.py, ocr/windows_ocr.py, scan.py,
clipboard.py, item_parser.py, mod_db.py, trade_search.py,
trade_client.py, trade_panel.py, overlay.py, hotkeys.py,
settings.py, app.py, __main__.py
run.py, requirements.txt, .gitignore, PLAN.md, history.md
tests/__init__.py, tests/test_normalizer.py, tests/test_matcher.py,
tests/test_ninja_client.py, tests/test_item_parser.py, tests/test_repository.py
tests/sample_data/ninja_poe1_currency.json, ninja_poe2_currency.json, sample_items.txt
```

**การตัดสินใจที่ทำเอง:**
- ใช้ `D:\Projects\PoE_Price-Trade_Checker` (current working dir ที่ Claude Code เปิดอยู่) แทน `D:\Projects\poe_price_trade`
- รองรับ PoE1+PoE2 ทั้งคู่ตั้งแต่ A1 (ไม่รอทำ PoE2 ก่อน)
- Mode B default = ไม่ filter mod (แสดง listing ทั้งหมด) ง่ายกว่าและ user เลือกเองได้
- `winrt-runtime` + individual `winrt-Windows.*` packages สำหรับ Python 3.13

**สิ่งที่ต้องทดสอบบนเครื่องจริง:**
- OCR ทำงานได้บน Windows จริง (ต้องติดตั้ง winrt packages)
- Overlay แสดง + click-through (ต้องรันบน Windows + เกม)
- Hotkey ทำงานขณะเกมอยู่ใน foreground
- Trade API ด้วย POESESSID จริง (Cloudflare อาจ block)

**ค้างอยู่:**
- ยังไม่ทดสอบบนเครื่องจริง — รอ user รัน `python run.py` แล้วรายงาน
- PoE2 ninja endpoint อาจ outdated — ให้ตรวจสอบ `profiles.py` ก่อนใช้จริง
- Mode B: UI สำหรับเลือก mod (B3) ยังเป็น pass-all — อาจ extend ใน session ถัดไป

---
