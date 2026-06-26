# PoE Price & Trade Checker — History (Project Changelog)

> รูปแบบ entry: วันที่ — สรุปสิ่งที่ทำ — ไฟล์ที่แตะ — สถานะ/ปัญหาค้าง
> เพิ่ม entry ใหม่ไว้ **บนสุด** เสมอ

---

## 2026-06-26 — Always-on session log (session 8)

**Commit:** `0467034`

**ไฟล์ที่แก้:**

- **`poe_price_trade/debug.py`** — เปลี่ยนจาก "เปิดได้เฉพาะ `DEBUG=True`" → event log ทำงานเสมอในทุก build
  - `setup()` สร้าง `debug_logs/` และเริ่ม session list เสมอ; `DEBUG=True` เพิ่ม verbose `FileHandler` เท่านั้น
  - `event()` append เสมอ (ลบ `if not DEBUG: return` ออก)
  - `write_summary()` เขียน `session_YYYYMMDD_HHMMSS.md` + `last_session.md` เสมอ; rotate เก็บ 10 session ล่าสุด
  - ชื่อ header เปลี่ยนเป็น `"PoE Price & Trade Checker — Session Log"`

**ผลที่ได้:**
- ทุกครั้งที่เปิดโปรแกรม (รวม .exe production) เขียน log ใน `%LOCALAPPDATA%\PoePriceTrade\debug_logs\`
- ดู `last_session.md` ได้เลยโดยไม่ต้องหา timestamp
- ตัวอย่าง session log จริง: startup, ninja 497 entries, F4 scan 3/6 items, hover, motion auto-clear, F5 trade URL

---

## 2026-06-26 — ปรับ PoE2 price display + trade URL rarity filter (session 7)

**Commits:** `2d0577e` → `e8b67cb` → `1d30b90` → `8d356e5`

**ไฟล์ที่แก้:**

- **`poe_price_trade/models.py`** — `PriceEntry` เพิ่ม `exalted_value: float = 0.0`; `format_price()` PoE2 แสดงหน่วย ex แทน c (e.g. "12.50ex", "1.23 div (45ex)", "?")
- **`poe_price_trade/ninja_client.py`** — `_parse_exchange_overview()` เขียนใหม่: ใช้ anchor-ratio (หา `primaryValue` ของ divine/exalted จาก response โดยตรง) แทน `core.rates` — ถูกต้องไม่ว่า reference currency จะเปลี่ยน; เพิ่ม `exalted_value` ใน `PriceEntry`; เพิ่ม `debug.event()` log sample
- **`poe_price_trade/trade_url.py`** — เพิ่ม `STATUS_OPTION = "online"` constant + comment; เพิ่ม `_RARITY_OPTION` dict; ใส่ `type_filters.rarity` ใน URL query ทุกครั้ง (เฉพาะ gear ที่มี rarity)

**ลบ (chore):**
- `poe_price_trade/trade_search.py` — ไม่มีที่ import แล้ว
- `PLAN.md` — plan 8 STEP เสร็จหมดแล้ว
- `build/`, `.pytest_cache/`, `__pycache__/`, `tools/probe_*_result.txt`

**ค้างอยู่:**
- หาค่า string จริงของ "Instant Buyout and In Person" จาก trade URL แล้วใส่ `STATUS_OPTION`
- PoE2 `chaos_value` ยัง `0.0` (ไม่มี chaos rate ใน exchange overview) — ถ้าอยากได้ต้องดึง chaos anchor แยก

---

## 2026-06-26 — Refactor ใหญ่ STEP 0-8 + build exe (session 6)

**สรุป:** ยุบสถาปัตยกรรมจาก 4 ทางเข้า → 2 ทางเข้า (F4 scan+hover, F5 browser trade) ลบ POESESSID/trade API dependency ทั้งหมด

**Probe results (STEP 0):**
- poe.ninja leagues endpoint → 404; เปลี่ยนไปใช้ GGG trade/trade2 API แทน
- PoE2 ninja endpoint (exchange/current/overview) → ✅ ใช้ได้ ไม่ต้องแก้ parser
- PoE2 league ปัจจุบัน: "Runes of Aldur"; PoE1: "Mirage"
- Trade URL `?q=` → ✅ browser โหลด + search อัตโนมัติ

**ฟีเจอร์ใหม่:**

1. **F4 scan → hover reveal** (`app.py`, `scan.py`, `overlay.py`):
   - กด F4 → scan จอทั้งหมด 1 ครั้ง → เก็บ bbox ทุก item ที่เจอ
   - เลื่อน hover ไปบน item → ราคาขึ้น (ไม่ OCR ซ้ำ แค่เช็ค cursor ใน bbox)
   - Safety timer 25s auto-clear
   - DPI fix: ลบ `/dpi_scale` division ออก ใช้ physical px ตรง

2. **auto-clear ตอนเดิน** (`motion.py` ใหม่):
   - frame-diff บน grid 64px; 35% pixel เปลี่ยน 2 เฟรมติด = เดิน → clear ทันที
   - Esc hotkey clear ด้วยมือ

3. **F5 browser trade** (`trade_url.py` ใหม่):
   - ชี้ item → F5 → build URL `?q=` → เปิด browser หน้า trade พร้อม filter
   - unique → ค้นด้วยชื่อ; rare ส่องแล้ว → ใส่ mod filter; unidentified → base+ilvl
   - Status: `"any"` (buyout and in person)
   - **ไม่มี API call, ไม่มี POESESSID**

4. **Auto-league** (`ninja_client.py`, `profiles.py`, `app.py`):
   - ดึงลีกจาก GGG trade API ตอนเปิดโปรแกรม
   - เลือก challenge league SC/HC อัตโนมัติตาม prefer_hardcore setting

5. **format_price()** (`models.py`):
   - แสดงทั้งสองหน่วย เช่น "1.23 div (11c)"

6. **สี overlay ตาม PoE rarity** (`overlay.py`):
   - Currency/Rune/Essence = `#AA9E82` (tan), Unique = `#AF6025` (orange)
   - Gem = `#1BA29B` (teal), Divination Card = `#C8C8C8` (white)

7. **Debug logging** (`debug.py` ใหม่):
   - `DEBUG=False` ใน production; ตั้ง `True` ระหว่าง dev → session log + last_session.md

8. **scan window 4 คำ** (`scan.py`):
   - เพิ่ม window ขนาด 4 คำ ครอบคลุมชื่อยาว เช่น "Ancient Rune of Animosity"

**ไฟล์ใหม่:**
```
poe_price_trade/debug.py, motion.py, trade_url.py
tools/probe_leagues.py, probe_ninja_poe2.py, probe_trade_url.py
```

**ไฟล์ที่ลบ:**
```
poe_price_trade/trade_client.py, trade_panel.py
```

**ไฟล์ที่แก้:**
```
poe_price_trade/app.py (rewrite), profiles.py, ninja_client.py,
config.py, models.py, scan.py, overlay.py, hotkeys.py, settings.py,
capture.py (ใช้ get_screen_size ใน overlay)
```

**Build:**
- `dist/PoE-Price-Trade-Checker.exe` (14 MB, --onefile --noconsole)
- `DEBUG=False` ก่อน build

**ค้างอยู่:**
- ทดสอบ OCR match rate ใน inventory (by design: F4 อ่าน ground label เท่านั้น; inventory ใช้ F5)
- ปรับ motion threshold ถ้า auto-clear ไวหรือช้าเกินไป (_FRAC_THRESH, _DIFF_THRESH ใน motion.py)

---

## 2026-06-24 — trade fallback + hover redesign (session 5)

**สรุป:** เพิ่ม PoE trade API fallback เมื่อ poe.ninja ไม่มีข้อมูล (unique items, gems, ฯลฯ) + redesign hover mode ใช้ Ctrl+C แทน OCR

**ฟีเจอร์ใหม่:**

1. **Trade fallback** (`app.py`):
   - เมื่อ Ctrl+C item → ค้น poe.ninja ก่อน (เร็ว) → ถ้าไม่เจอ → ค้น trade.pathofexile.com โดยตรง
   - ครอบคลุม unique weapon/armour/gem ทุก item ที่ poe.ninja ไม่มี
   - แสดงราคาถูกสุดจาก 5 listing แรก ในรูปแบบเดียวกับ poe.ninja (div/chaos)
   - `_quick_trade_lookup_async()` + `_make_price_entry_from_listing()` (convert TradeListing → PriceEntry)
   - ถ้าไม่มี POESESSID: แจ้งให้ตั้งใน Settings แทน error

2. **Hover mode redesign** (`app.py`):
   - เปลี่ยนจาก OCR + poe.ninja → simulate Ctrl+C + poe.ninja + trade fallback
   - ครอบคลุม item ทุกประเภท (currency, unique, gem, rare)
   - gen-guarded: ถ้าเมาส์ขยับระหว่าง trade lookup → ไม่แสดงผลเก่า
   - `_trigger_hover_price(cx, cy, gen)` แทน `_trigger_hover_scan()`

3. **Clipboard monitor** (`app.py`):
   - เพิ่ม `_hover_ctrl_c_ts` timestamp suppression (0.8s) — ป้องกัน double-process เมื่อ hover trigger Ctrl+C
   - Reset `_last_auto_item = ""` เมื่อเมาส์ขยับ — re-hover บน item เดิมแสดงราคาได้ใหม่

**ไฟล์ที่แก้:**
```
poe_price_trade/app.py
```

**ค้างอยู่:**
- ทดสอบ overlay ขณะเล่นเกมจริง (windowed fullscreen 3440×1440)
- Trade API ยังไม่ได้ทดสอบด้วย POESESSID จริง

---

## 2026-06-24 — hover mode + F5 auto Ctrl+C + launcher + categories เพิ่ม (session 4b)

**สรุป:** เพิ่ม hover mode, auto Ctrl+C ใน F5, สร้าง launcher ไม่ต้องมี CMD, เพิ่ม categories ใน poe.ninja ครบ 497 entries

**ฟีเจอร์ใหม่:**

1. **Hover mode** (`app.py`, `scan.py`, `capture.py`):
   - เมาส์นิ่ง 0.4s → auto scan region รอบ cursor → แสดงราคาจาก poe.ninja
   - gen-guarded (increment `_hover_gen` ทุกครั้งเมาส์ขยับ) ป้องกันผล OCR เก่าโผล่
   - `capture_region(x, y, w, h)` + `get_cursor_pos()` ใน capture.py
   - `Scanner.scan_region(cx, cy, threshold)` ใน scan.py

2. **F5 auto Ctrl+C** (`app.py`):
   - `_simulate_ctrl_c()` ส่ง Ctrl+C ไปที่เกม → อ่าน clipboard หลัง 0.18s
   - ชี้ item แล้วกด F5 เพียงอย่างเดียว ไม่ต้องกด Ctrl+C เอง

3. **Launcher** (`launch.vbs` + desktop shortcut):
   - `launch.vbs` ใช้ pythonw.exe → ไม่มีหน้าต่าง CMD โผล่
   - Desktop shortcut: `PoE Price Checker.lnk` → double-click เปิดได้เลย

4. **PoE2 categories เพิ่ม** (`profiles.py`):
   - เพิ่ม Abyss (AbyssalBones 15), UncutGems (42), Idols (28), Expedition (24), Verisium (23)
   - รวมทั้งหมด: 497 entries (Currency+Fragments+Abyss+UncutGems+Essences+SoulCores+Idols+Runes+Expedition+Breach+Verisium)

5. **price display** (`models.py`):
   - PoE2: แสดง chaos สำหรับ item ถูก (< 1 div) แทนที่จะแสดง div เพียงอย่างเดียว
   - เพิ่ม `< 0.01c` branch สำหรับ item ถูกมาก

**ไฟล์ที่แก้:**
```
poe_price_trade/app.py, scan.py, capture.py, models.py, profiles.py
launch.vbs (ใหม่)
```

---

## 2026-06-24 — แก้ PoE2 poe.ninja endpoints (session 4)

**สรุป:** แก้ปัญหา `Scan done: 0 matches` เกือบตลอดเวลา เพราะ PoE2 categories ใช้ API type name ผิด

**ปัญหาที่แก้:**
- `profiles.py`: เปลี่ยน PoE2 category type names เป็น plural form ที่ถูกต้อง (poe.ninja PoE2 API ต้องการ plural)
  - `Rune` → `Runes` (142 entries), `Essence` → `Essences` (82), `SoulCore` → `SoulCores` (42)
  - `BreachSplinter` → `Breach` (28), `Fragment` → `Fragments` (22)
  - ลบ categories ที่ไม่มีข้อมูลใน exchange API: UniqueWeapon, UniqueArmour, UniqueAccessory, UniqueFlask, UniqueJewel, SkillGem, Map, UniqueMap, DivinationCard, Catalyst, DistilledEmotion
- `ninja_client.py`: แก้ `_parse_exchange_overview()` ให้ใช้ top-level `items` list สำหรับ name lookup แทน `core.items` (ซึ่งมีแค่ 3 reference currencies)

**ผลลัพธ์:** เพิ่ม price entries จาก 49 → 365 entries
- Currency: 49, Rune: 142, Essence: 82, SoulCore: 42, Breach: 28, Fragment: 22

**ไฟล์ที่แก้:**
```
poe_price_trade/profiles.py, ninja_client.py
```

**หมายเหตุ:** PoE2 poe.ninja exchange API ไม่มีข้อมูล Unique items, Maps, Gems — มีแค่ currency-like items ที่อยู่ใน in-game currency exchange

**ค้างอยู่:**
- ทดสอบ overlay ขณะเล่นเกมจริง (windowed fullscreen 3440×1440)
- Trade API ยังไม่ได้ทดสอบด้วย POESESSID จริง

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
