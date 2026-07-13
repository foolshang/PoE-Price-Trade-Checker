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
`trade(2)/data/stats` โดยตรง คนละ pipeline กับ hub) mod badge/tier annotation
(F5 popup) ใช้ `meta_db.py` ← `mod_meta.json` (ไฟล์ local, build จาก RePoE
datamine ด้วย `tools/build_mod_meta.py` — **ไม่เกี่ยวกับ hub เลย**) hub มี
`poe2/meta/latest.json` ของตัวเองด้วยเช่นกัน (mod frequency จาก build จริง)
แต่เป็นคนละงาน คนละไฟล์กับ `mod_meta.json` นี้ — ยังไม่ได้พิจารณาย้ายมาใช้ตัวนั้น
