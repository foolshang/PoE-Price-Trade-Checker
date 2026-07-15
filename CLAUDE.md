# PoE Price & Trade Checker — CLAUDE.md

## แหล่งข้อมูลราคา

ราคาทั้งหมด (F4 scan/hover) มาจาก **poe-data-hub เท่านั้น** — ห้ามยิง
poe.ninja หรือ poe2scout.com ตรงจากโค้ดฝั่งนี้อีก (เคยทำแบบนั้นก่อน v0.2.0,
เลิกแล้วหลังย้ายมาใช้ hub เป็น consumer ตัวที่ 2 ต่อจาก Discord bot)

- Base URL: `https://storage.googleapis.com/poe-data-hub`
- Client: `poe_price_trade/hub_client.py`
- ใช้งาน: `poe_price_trade/repository.py` (`PriceRepository`) — ดึงลีกทั้งหมด
  (main/hardcore/events) จาก `{game}/prices/index.json` แล้ว fetch ไฟล์ราคา
  ของลีกที่ผู้ใช้เลือกตาม path ที่ index.json บอก
- Schema อ้างอิง: `D:\Projects\Poe_Hub\SPEC.md` (section 8.1 = prices schema,
  8.1a = event leagues, 8.1b = index.json, 8.1c = hardcore variant) — hub repo
  เป็นเจ้าของ schema ตัวจริง ห้ามเดา/จำจาก chat history
- hub อัปเดตทุก 20 นาที, `Cache-Control: max-age=300` — cache ฝั่ง Checker ใช้
  TTL 5 นาที คู่กับ disk cache ต่อ (game_version, league)

## ขอบเขตที่ hub ไม่รองรับ (ตั้งใจ)

Standard / Hardcore Standard (permanent league) ไม่มีราคาเลยทั้งสองเกม — hub
binding condition 5 (ไม่มีผู้ใช้จริง ไม่ใช่ข้อจำกัดทางเทคนิค) League dropdown
ของ Checker จึงมีแค่ main challenge league + HC variant ของ main (ถ้ามี) +
event league ที่กำลังเปิดอยู่ (ถ้ามี) — ไม่มี Standard/Hardcore ให้เลือกอีกแล้ว

## ไม่เกี่ยวกับราคา (ห้ามสับสน)

F5 (trade browser) ไม่ใช้ข้อมูลราคาเลย — `trade_url.py` สร้าง query จาก
`ParsedItem` (ชื่อ/base/mods) ผ่าน `mod_db.py` (stat id จาก GGG trade API
`trade(2)/data/stats` โดยตรง คนละ pipeline กับ hub) tier/money badge (F5 popup)
ใช้ `meta_db.py` ← `mod_meta.json` (ไฟล์ local, build จาก RePoE datamine ด้วย
`tools/build_mod_meta.py` — **ไม่เกี่ยวกับ hub เลย**)

## Mod Badge (F5 popup, PoE2 only, v0.3.0+, phase 2 = v0.4.0)

จุดสี (● แดง/ทอง/เขียว/ไม่มีจุด=ขาว) หน้าแต่ละบรรทัด mod บอกความนิยม+ประโยชน์
ของ mod นั้น มาจาก `poe2/meta/latest.json` ของ hub (`poe_price_trade/mod_badge.py`,
`ModBadgeDB`) — คนละไฟล์คนละ concept กับ tier/money badge เดิม (`meta_db.py`,
local RePoE data) ทั้งสองแสดงในแถวเดียวกันของ popup ได้พร้อมกัน schema อ้างอิง
SPEC.md section 8.2 ของ hub repo — **มี style เดียว (dot) เท่านั้น** (ตัด
text/frame ออกแล้วหลัง user ทดสอบจริงแล้วเลือก dot v0.4.0)

- **สี**: แดง > ทอง > เขียว > ขาว (ให้สีสูงสุดที่เข้าเกณฑ์) แดง/ทอง = popularity
  จาก hub โดยตรง (rank/usage_pct) เขียว = "metacraft material" — mod ที่ตัวเอง
  ไม่ติดแดง/ทอง แต่แชร์ RePoE `implicit_tags` กับ mod แดง/ทองของ slot+archetype
  เดียวกัน (`ModBadgeDB.tag_color()`) — ข้อมูล tags ต้อง capture เพิ่มเองใน
  `tools/build_mod_meta.py` (RePoE ของเดิมไม่เก็บ tags ไว้ ต้อง regenerate
  `mod_meta.json` ใหม่ — เป็น local tooling gap ไม่ใช่ hub gap)
- **▲/▼ roll indicator**: T1 (roll สูงสุดแล้ว) ไม่ติดลูกศรเลย tier ต่ำกว่า T1
  เทียบ roll กับช่วง RePoE ของ tier นั้น (`MetaDB.tier_range()`) ถ้าไม่รู้ tier
  fallback ไปเทียบกับ `value_min`/`value_max` ที่ hub สังเกตจาก build จริงแทน
  (`ModBadgeDB.roll_indicator_fallback()`) เกณฑ์ top/bottom % ปรับได้ (`roll_pct`,
  default 0.25)
- **P/S marker**: ต้องมี `ModValue.affix` (prefix/suffix) ที่ populate จาก
  header `{ Prefix/Suffix Modifier ... }` ใน `item_parser.py` — เพิ่งเพิ่มใน
  v0.4.0 (ก่อนหน้านี้มีแค่ `ParsedItem.prefix_count`/`suffix_count` รวม ไม่มี
  per-mod flag) บรรทัดสรุปท้าย popup ใช้ format "Prefix x/max · Suffix y/max"
  เพดานจาก `mod_badge.affix_cap(item_class)` (3/3 ปกติ, 1/1 สำหรับ jewel PoE2)
- stat_id resolution ใช้ `mod_db.py`'s `find_stat_id()` เป็นหลัก (namespace
  เดียวกับ hub, verified live) — `stat_dictionary` ของ hub เป็นแค่ fallback
  เมื่อ mod_db resolve ไม่ได้ ไม่ใช่ตัวหลัก
- เกณฑ์สี/threshold/roll_pct ปรับได้ผ่าน `mod_badge_rules.json` ใน app dir
  (override pattern เดียวกับ `money_mods.json` ของ meta_db.py) archetype เป็น
  setting ปกติใน config.json (`mod_badge_archetype`)
- PoE1: hub ไม่มี `poe1/meta/latest.json` เลย → `ModBadgeDB.available()` เป็น
  False เสมอ → badge ไม่ขึ้นแบบเงียบๆ ไม่ error — by design ไม่ใช่บั๊ก
