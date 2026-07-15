# PoE Price & Trade Checker — History (Project Changelog)

> รูปแบบ entry: วันที่ — สรุปสิ่งที่ทำ — ไฟล์ที่แตะ — สถานะ/ปัญหาค้าง
> เพิ่ม entry ใหม่ไว้ **บนสุด** เสมอ

---

## 2026-07-16 — Mod Badge เฟส 2: roll indicator + metacraft สีเขียว + P/S (v0.4.0)

**เหตุผล:** ปรับจากการใช้จริงหลังเฟส 1 (user ทดสอบแล้วเลือก "dot" ตัด
text/frame ทิ้ง) + เพิ่ม 3 ความสามารถใหม่ที่คุยไว้ตอนวางแผน archetype
infrastructure: roll quality indicator, metacraft สีเขียว, prefix/suffix marker

**1. Badge style เหลือ dot อย่างเดียว** — ลบ `mod_badge_style` ออกทั้ง
`config.py`/`settings.py`/`mod_picker.py` (`ModPickerWindow`/`_add_row` ไม่รับ
`badge_style` แล้ว, dot (`●`) เดียว, สีเพิ่ม "เขียว" #4CAF50 เป็นตัวที่ 3

**2. Roll indicator (▲/▼)** — `MetaDB.tier_range()` ใหม่ (ดึงช่วง roll ของ
family+tier จาก RePoE), `mod_badge.tier_roll_arrow()` (คำนวณ percentile จาก
ช่วงนั้น), `ModBadgeDB.roll_indicator_fallback()` (fallback ไป hub's
value_min/value_max เมื่อไม่รู้ tier) T1 ไม่ติดลูกศรเลยตามที่ user ระบุ
(สุดแล้ว ไม่มีอะไรต้องบอกเพิ่ม) เกณฑ์ `roll_pct` (default 0.25) อยู่ใน
`mod_badge_rules.json`

**3. Metacraft สีเขียว** — เช็คข้อมูลก่อนตามที่สั่ง: พบว่า RePoE raw
`mods.json` (`repoe-fork/poe2`) มี `implicit_tags` จริง (89 ค่า distinct
รวม life/attack/caster/resistance ฯลฯ) แต่ `tools/build_mod_meta.py` เดิม
**ไม่เก็บ** field นี้ไว้ใน `mod_meta.json` เลย — เป็น local tooling gap
ไม่ใช่ hub gap แก้ได้เองไม่ต้องเปิดงานฝั่ง hub: แก้ `build_mod_meta.py` ให้
capture `tags` ต่อ family, regenerate `mod_meta.json` ใหม่ (bases/tagsets
count ไม่เปลี่ยน, tier/roll data เดิม 100% ไม่มี regression, 1952/2239
families ได้ tags) แล้ว deploy ทับไฟล์เดิมใน
`%LOCALAPPDATA%\PoePriceTrade\mod_meta.json`

ตรวจ text-normalization compatibility ระหว่าง `build_mod_meta.py`'s
`norm_text()` กับ hub's stat_dictionary/GGG stat text ก่อนเชื่อถือ cross-
reference ได้ — overlap 82.3% (256/311 family text ตรงกันเป๊ะ ที่พลาดส่วนใหญ่
เป็น hybrid multi-stat mod ที่ meta_db.py รวมหลายบรรทัดเป็น text เดียว)
ยอมรับได้เพราะ design เป็น graceful-miss (ไม่ match = ไม่ติดเขียว ไม่ error)

Implementation: `ModBadgeDB._stat_to_templates` (reverse ของ
`_template_index`), `MetaDB.tags_for_template()`/`_global_tags()` (global
text→tags index ข้าม tagset เพราะ tags เป็นคุณสมบัติของ mod line ไม่ใช่ของ
base type), `ModBadgeDB.tag_color()` (แดง>ทอง>เขียว>ขาว, เขียว = white mod
ที่แชร์ tag กับ mod แดง/ทองของ slot+archetype เดียวกัน ผ่าน `_hot_tags()`
cache ต่อ (slot,archetype))

**4. Prefix/Suffix** — เพิ่ม `ModValue.affix` field ใหม่ (`models.py`) +
populate จาก header ใน `item_parser.py` (เดิมมีแค่ `ParsedItem.prefix_count`/
`suffix_count` รวม ไม่มี per-mod flag) ตัวอักษร P/S เล็กๆ คู่กับลูกศรใน
`mod_picker.py` `MetaDB.summary()` เปลี่ยน format เป็น "Prefix x/max · Suffix
y/max" รับ `prefix_cap`/`suffix_cap` param ใหม่ (แทน hardcode 3) —
`mod_badge.affix_cap(item_class)` คืน 1 สำหรับ jewel, 3 สำหรับที่เหลือ (คง
meta_db.py เป็น hub-independent ไว้ตามเดิม ไม่ import mod_badge.py)

**ไฟล์ที่แก้:** `models.py`, `item_parser.py`, `meta_db.py`, `mod_badge.py`,
`mod_picker.py`, `app.py` (`_compute_mod_extras` แทนที่ `_compute_mod_badges`
เดิม คำนวณทั้ง badge_colors+roll_arrows พร้อมกันในรอบเดียว), `config.py`,
`settings.py`, `tools/build_mod_meta.py`

**Tests:** 105/105 passed (`test_meta_db.py` ใหม่ 10 เคส, `test_mod_badge.py`
เพิ่ม 15 เคส, `test_poe2_parser.py` เพิ่ม 2 เคสสำหรับ `affix` field)

**Smoke test กับข้อมูลจริงครบทุกชั้น (2026-07-16):** parse
`sample_poe2_rare.txt` จริง → P/S ครบ 4 prefix/3 suffix ถูกต้อง → T1 (Armour%,
Life) ไม่มีลูกศรถูกต้อง → tier อื่นมีลูกศรตามช่วง roll จริง → สีสมเหตุสมผล
(Life=แดง, Armour%/flat Armour=เขียวเพราะแชร์ tag กับ Life, Fire
Resist=แดง) ทดสอบ jewel synthetic ด้วย (Item Class: Jewels, base "Emerald")
→ slot resolve เป็น "jewel:emerald" ถูกต้อง, affix_cap=1 ถูกต้อง ยังไม่ได้
ทดสอบ popup จริงในเกม (รอ user)

---

## 2026-07-14 — Mod Badge เฟส 1: สีบอกความนิยม mod ใน F5 popup (PoE2, v0.3.0)

**เหตุผล:** hub มี `poe2/meta/latest.json` (mod frequency จาก build จริงบน
poe.ninja) — ต่อยอดจาก tier/money badge เดิมใน F5 popup ให้เห็นด้วยว่า mod
ไหน "คนนิยมใส่จริง" (แดง = ยอดฮิตมาก, ทอง = พอมีคนใส่, ขาว = ไม่ค่อยมี/match
stat_id ไม่ได้) แยกจาก tier ladder (ที่บอกแค่ค่า roll สูง/ต่ำ ไม่ใช่ความนิยม)

**ตัดสินใจสำคัญระหว่างคุย survey กับ user:**
1. **โชว์ที่ F5 popup ไม่ใช่ F4 overlay** — F4 hover-OCR อ่านแค่ชื่อ item เพื่อ
   ราคา ไม่เคย parse mod เลย ส่วน F5 (Ctrl+C) ได้ mod text ที่แม่นยำ 100% จาก
   clipboard อยู่แล้ว ต่อยอดจาก `mod_picker.py` ที่มี tier/money badge อยู่แล้ว
   ง่ายกว่าและแม่นกว่า — F4 hover-OCR mod parsing เก็บไว้เป็น backlog เฟสถัดไป
2. **reuse `mod_db.py` แทนเขียน stat_dictionary matcher ใหม่** — verified live
   ว่า `mod_db.find_stat_id()` (จาก GGG `trade2/data/stats`, ใช้กับ F5 อยู่แล้ว)
   คืน stat_id namespace เดียวกับ hub เป๊ะ (`explicit.stat_3299347043` = "#
   to maximum Life" ตรงกันทั้งสองฝั่ง) — hub's `stat_dictionary` เหลือแค่เป็น
   fallback เมื่อ mod_db resolve ไม่ได้ ไม่ใช่ตัวหลัก

**ไฟล์ใหม่:**
- `poe_price_trade/mod_badge.py` — `ModBadgeDB` (disk cache TTL 8h อิง
  `generated_at` ของ payload เอง ไม่ใช่ wall-clock ตอน load — เจอบั๊ก
  self-defeating cache ระหว่างเขียน ที่ mark stale cache ว่า fresh ทันทีที่
  index() ก่อน fix), `slot_for_item()` (item_class/base_type → hub slot key
  รวม jewel color slug ที่ port มาจาก hub's `_slugify_jewel_base` ตรงๆ),
  `resolve_stat_id()` (mod_db ก่อน → stat_dictionary fallback แบบ
  exact-then-fuzzy เหมือน mod_db เอง เพราะ `_normalize_mod` ไม่ตัด "+" หน้า
  mod text จริงในเกม)

**ไฟล์ที่แก้:**
- `poe_price_trade/hub_client.py` — เพิ่ม `get_meta(game)`
- `poe_price_trade/meta_db.py` — เปลี่ยน `_WEAPON_CLASSES` → `WEAPON_CLASSES`
  (public) ให้ `mod_badge.py` reuse ได้ (เป็น PoE2 weapon class set ที่ validate
  แล้วจาก money-mod feature v0.1.6)
- `poe_price_trade/mod_picker.py` — `ModPickerWindow`/`_add_row` รับ
  `badge_colors`/`badge_style` เพิ่ม, 3 style: dot (● แยก widget ซ้ายมือ ไม่ทับ
  สีบรรทัด), text (ย้อม fg ทั้งบรรทัด), frame (`highlightthickness` border)
- `poe_price_trade/app.py` — `ModBadgeDB` instance เดียว ไม่ recreate ตอนสลับ
  game version (PoE2-only อยู่แล้ว ไม่ผูกกับ profile), `_compute_mod_badges()`
  คำนวณแยกจาก `rows`'s stat_id เดิมโดยสิ้นเชิง (**ไม่แตะ F5 trade query
  pipeline** — badge resolution เป็น pipeline คู่ขนาน ไม่ overwrite `sid` เดิม)
- `poe_price_trade/config.py`/`settings.py` — `mod_badge_style`,
  `mod_badge_archetype` (dropdown ใหม่ในแท็บ Game)

**ขอบเขต:** เฉพาะ rare (unique/magic ไม่มีความหมายเรื่องความนิยม), PoE1 ไม่มี
`poe1/meta/latest.json` บน hub เลย → `available()` False เสมอ → ไม่ติด badge
เงียบๆ ไม่ error, threshold ปรับได้ผ่าน `mod_badge_rules.json` (override pattern
เดียวกับ `money_mods.json` เดิม)

**Tests:** 78/78 passed (`tests/test_mod_badge.py` ใหม่ 22 เคส — slot mapping
รวม jewel, duplicate stat_id ใน stat_dictionary แบบ list-valued ทั้งสองทิศทาง,
archetype fallback ไป "all", disk cache staleness ผูกกับ `generated_at`,
graceful degrade ไม่มี network/cache)

**Smoke test กับ hub+mod_db จริง (2026-07-14):** parse `sample_poe2_rare.txt`
จริง (Knightly Mitts, 7 explicit mods) → slot resolve เป็น "gloves" ถูกต้อง →
stat_id resolve ครบทุก mod (รวมที่มี roll range แบบ "40(39-42)%") → badge สม
เหตุสมผลตามความรู้ meta จริง: Life/Mana = แดง (ยอดฮิต), Resistance = ทอง,
flat Armour/Armour% = ขาว ยังไม่ได้ทดสอบ F5 popup จริงในเกม (ต้องรอ user)

---

## 2026-07-14 — ย้ายแหล่งราคาจาก poe.ninja/poe2scout → poe-data-hub (v0.2.0)

**เหตุผล:** poe-data-hub (sibling project, `D:\Projects\Poe_Hub`) เป็นตัวเดียวที่ยิง
poe.ninja/poe2scout.com แล้ว — Discord bot ย้ายไปใช้ hub เสร็จแล้ว, Checker คือ
consumer ตัวที่ 2 ก่อนย้ายทำ survey เต็ม (แยก field/หมวด/ลีก 3 กลุ่ม: hub มีครบ /
ต้อง reshape / hub ยังไม่มี) พบว่า hub ยังขาด PoE1 16/22 หมวด กับ Standard/Hardcore/
HC-variant league ทั้งหมด → hub ทำ phase 9 เติมให้ครบก่อน Checker ย้ายจริง (ดู
`D:\Projects\Poe_Hub\SPEC.md` phase 9)

**ไฟล์ใหม่:**
- `poe_price_trade/hub_client.py` — stdlib fetch `{game}/prices/index.json` +
  `get_league_files()` reshape เป็น main/hardcore/events routing table (port
  จาก `Bot-Poe-Discord/poe-discord-bot/hub_client.py` ปรับให้ไม่ใช้ `requests`
  เพื่อคง stdlib-only ตามธรรมเนียมเดิมของโปรเจกต์)

**ไฟล์ที่แก้:**
- **`poe_price_trade/repository.py`** — `PriceRepository.load(league, path, force)`
  รับ hub path ตรงๆ (ไม่ประกอบ URL เอง), รวม `currency[]+items[]` เป็น entries
  เดียว, `chaos_value`/`exalted_value` ใช้ additive field จาก hub ถ้ามี ไม่งั้น
  derive จาก `value`+`value_currency`, `listing_count` หาย → 0, ลบ
  `_merge_poe2scout()`/`_norm_cat()` (hub merge ninja+scout ให้แล้ว), TTL
  1800→300s + cache key รวม league เข้าไปด้วย (เดิมเช็คแค่ TTL ไม่เช็คว่า
  snapshot เป็นของลีกไหน), `load()` เป็น 2 phase: apply disk cache (แม้ stale)
  ก่อนเสมอ → ค่อย refresh จาก hub เบื้องหลัง — hub ล่มชั่วคราวไม่ทำให้แอพว่างเปล่า
- **`poe_price_trade/app.py`** — league selection ย้ายจาก GGG trade API มาเป็น
  `hub_client.get_league_files()`, `prefer_hardcore` อ่าน key `hardcore` จาก
  index ตรงๆ (`null` → fallback ไป main + log warning ใน UI แทน substring-match
  แบบเดิม), เก็บ `_league_paths` (league name → hub path) ให้ `_load_prices_async`
  ใช้ต่อ
- **`poe_price_trade/models.py`** — เพิ่ม `PriceEntry.stale: bool` (ของใหม่จาก
  hub, entry เป็นของรอบ fetch ก่อนหน้าเพราะ source ล่มรอบนี้), ลบ
  `PriceSnapshot.category_counts` (ไม่มีใครสร้าง/ใช้แล้วหลังลบ ninja_client)
- **`poe_price_trade/overlay.py`** — prefix `~` หน้าราคาเมื่อ `price_entry.stale`
- **`poe_price_trade/profiles.py`** — ลบ `CategoryConfig`/`categories`/
  `ninja_*_url`/`leagues_realm`/`get_category()`/`is_poe2()` (ตายหมดหลังลบ
  ninja_client) เหลือแค่ trade endpoints (F5/mod_db ยังใช้) + `default_leagues`
  (fallback ตอน cold-start ไม่มี network/cache เลย)

**ไฟล์ที่ลบ:** `poe_price_trade/ninja_client.py`, `poe_price_trade/poe2scout_client.py`,
`tests/test_ninja_client.py`, `tests/sample_data/ninja_poe{1,2}_currency.json`

**ห้ามแตะ (ยืนยันจาก survey ว่าไม่เกี่ยว):** `trade_url.py`/F5 pipeline ทั้งเส้น
(ไม่เคยอ่าน `PriceEntry.trade_id` เลย สร้าง query จาก mod/name/base ผ่าน
`mod_db.py` คนละชุดข้อมูล), OCR, `overlay.py` format logic, `mod_db.py`

**ผลกระทบ user-visible:** Standard/Hardcore (permanent league) หายจาก league
dropdown ทั้งสองเกม — hub ตั้งใจไม่ดึงราคาลีกพวกนี้ (ไม่มีผู้ใช้จริง, hub binding
condition 5) เหลือแค่ main challenge + HC variant ของ main (ถ้ามี) + event league
ที่เปิดอยู่ (ถ้ามี)

**Tests:** 56/56 passed (เพิ่ม `tests/test_hub_client.py` ใหม่ + เขียน
`tests/test_repository.py` ใหม่บางส่วนให้ mock `hub_client` แทน `NinjaClient`,
คลุมเคส hardcore null, listing_count หาย, ชื่อซ้ำ dedupe, stale flag, degraded
จาก `sample.per_category`)

**Smoke test กับ hub จริง (2026-07-14):** poe1 Mirage 3462 entries / Hardcore
Mirage 1052 entries, poe2 Runes of Aldur 1099 entries / HC Runes of Aldur 1083
entries — `degraded()` ว่างทั้งคู่ (ไม่มีหมวดไหน `ok:false`) lookup ตรวจแล้ว:
Divine Orb, Chaos Orb, Mageblood (poe1 unique), Runeseeker's Call (poe2 unique)
ราคาสมเหตุสมผล ยังไม่ได้ทดสอบ F4 hover กับไอเทมจริงในเกม (ต้องรอ user เปิดเกม)

---

## 2026-07-04 — Patch C.1+C.2: fix magic base resolution + jewel meta (session 11, v0.1.7)

**Commit:** `89e3dc0` (C.1) + release tag `v0.1.7`; C.2 ยังไม่ commit (แก้เฉพาะ `tools/build_mod_meta.py`, ไม่ต้อง build exe ใหม่)

**BUG 3 (C.1):** magic ที่ส่องแล้วชื่อบรรทัดเดียวรวม affix name เช่น "Legend's Fortress
Sabatons of Grounding" (base จริง = "Fortress Sabatons") — parser ใช้ทั้งก้อนเป็น
base_type → query type ไม่มีอยู่จริง → trade ขึ้น "Failed to load search state.
The search is no longer valid." พลอยทำให้ tier/money annotation หา base ไม่เจอเงียบๆ ด้วย

**ไฟล์ที่แก้ (C.1):**
- **`poe_price_trade/meta_db.py`** — เพิ่ม `resolve_base(name)`: หา base ที่ยาวที่สุดที่ฝังอยู่ในชื่อ (word-boundary ด้วยการ pad ช่องว่าง) เทียบกับรายชื่อ base ใน `mod_meta.json`
- **`poe_price_trade/app.py`** — fix `item.base_type` ทันทีหลัง parse สำหรับ magic ที่ identified แล้ว: resolve ได้ → แทนที่ด้วย base จริง, resolve ไม่ได้ → ตัด type ออกจาก query (ค้นด้วย rarity+stats ยัง valid ดีกว่า error ทั้งหน้า); เพิ่ม `_get_meta_db()` helper แบบ lazy ใช้ร่วมกันทั้ง F5 branch
- **`tests/test_poe2_magic.py`** (NEW) — คลุม parse magic ชื่อรวม affix, resolve_base (เลือกตัวยาวสุด), resolve_base ไม่มี meta file

**BUG (C.2):** jewel (Ruby/Emerald/Sapphire/Diamond/Timeless + Time-Lost 4 แบบ) หายจาก
`mod_meta.json` ทั้งฝั่ง base และ mod เพราะใน RePoE ทั้งคู่อยู่ domain `"misc"` แต่ script
filter เอาเฉพาะ domain `"item"` — F5 กับ jewel เลย resolve base ไม่ได้ (ค้นแบบไม่มี type)

**ไฟล์ที่แก้ (C.2):**
- **`tools/build_mod_meta.py`** — base filter + mod filter รับ domain `"item"` หรือ `"misc"` (ยืนยันแล้วว่า misc ฝั่ง base มีแต่ jewel ล้วน ไม่มีขยะติดมา)

**ผลลัพธ์:**
```
tools/build_mod_meta.py → mod_meta.json: bases=1782, tagsets=78 (เดิม 1773/70 — เพิ่ม jewel 9 bases + tagsets)
regenerate แล้ว tagset ของ gear เดิมไม่เปลี่ยนแม้แต่ byte เดียว (regression = ศูนย์)
tests/: 42/42 passed (เพิ่ม test_poe2_magic.py 3 เคสใหม่)
```

**Build+Release (C.1):** ลบ build/dist/`__pycache__` เก่า → build จาก `.spec` เดิม →
`dist/PoE-Price-Trade-Checker.exe` (13.8 MB) → tag `v0.1.7` → GitHub Release
(https://github.com/foolshang/PoE-Price-Trade-Checker/releases/tag/v0.1.7) แนบ exe

**C.2 ไม่ rebuild exe:** `mod_meta.json` เป็นไฟล์ภายนอก โหลดจาก
`%LOCALAPPDATA%\PoePriceTrade\` ตรงๆ — regenerate แล้ว copy ทับไฟล์เดิม, exe v0.1.7
เดิมใช้ได้เลยแค่ปิด-เปิดใหม่

**ค้างอยู่:**
- ยังไม่ได้ทดสอบ F5 บนเกมจริง: magic boots เดิม (type ต้องเป็น "Fortress Sabatons"),
  Iconic Ruby (type ต้องเป็น "Ruby"), jewel rare (ถ้ามี), gear เดิม (regression check)

---

## 2026-07-04 — Patch C: tier badge + money-mod highlighter + parser fixes (session 10, v0.1.6)

**ปัญหา (พิสูจน์จาก clipboard จริง):**
- BUG 1: hybrid mod สองบรรทัดใต้ header เดียว (เช่น Armour% + Life ของ "Crocodile's") — บรรทัดที่สองถูกทิ้งเงียบๆ เพราะ parser reset `pending` หลัง mod แรก
- BUG 2: rare ที่มี quality + base สองคำ ("Knightly Mitts") — กฎตัด quality prefix กินคำแรกของ base ("Knightly") ทิ้ง เหลือ "Mitts" → trade query พัง เพราะเกมไม่เติม "Superior" ใน base line ของ rare

**ไฟล์ใหม่/แก้:**

- **`poe_price_trade/models.py`** — `ModValue` เพิ่ม `values`/`tier`/`group`; `ParsedItem` เพิ่ม `prefix_count`/`suffix_count`
- **`poe_price_trade/item_parser.py`**:
  - แก้ BUG 1: header block ไม่ reset `pending` หลัง mod แรก → เก็บได้หลายบรรทัดต่อ header เดียว (group เดียวกัน)
  - แก้ BUG 2: ตัด quality prefix เฉพาะขึ้นต้นด้วยคำ prefix จริง (Superior/Anomalous/Divergent/Phantasmal) แทนตัดคำแรกแบบเดา
  - อ่าน Tier จาก header `(Tier: N)`, เก็บ rune mods (`+X to Y (rune)`) เป็น type แยก, นับ prefix/suffix ที่ใช้ไป, ตัดช่วง roll `(a-b)` ก่อนดึงค่าตัวเลข
- **`poe_price_trade/meta_db.py`** (NEW) — โหลด `mod_meta.json` (offline, จาก `%LOCALAPPDATA%\PoePriceTrade\`) ให้ tier ladder (T_/total) + money-mod flag ตามกติกา `_DEFAULT_MONEY` (override ได้ด้วย `money_mods.json`); ไม่มีไฟล์ meta = feature จำกัดแบบเงียบๆ
- **`poe_price_trade/mod_picker.py`** — badge `[T_/_]` + 💰 สีทองหน้าข้อความ mod เงิน + บรรทัดสรุปเขียวใต้หัว popup (เช่น "💰 mod เงิน ×2 · T1 ×1 · suffix ว่าง 1 · ilvl 78")
- **`poe_price_trade/app.py`** — F5 picker branch เรียก `MetaDB.annotate()` แล้วส่ง annotation เข้า popup
- **`tools/build_mod_meta.py`** (NEW) — precompute `mod_meta.json` จาก RePoE fork (`repoe-fork/poe2`) datamine: base → tag-set → mod family → tier ladder (level + value range ต่อ tier)
- **`tests/sample_data/sample_poe2_rare.txt`** + **`tests/test_poe2_parser.py`** (NEW) — fixture clipboard PoE2 จริง (hybrid + Tier header + rune + quality) ครอบทั้ง 2 bug ข้างบน

**ผลลัพธ์:**
```
tools/build_mod_meta.py → mod_meta.json: bases=1773, tagsets=70 (dedupe จาก 426), 0.58MB
tests/test_poe2_parser.py: 7/7 passed
tests/ (ไม่รวม test_ninja_client.py ที่พังอยู่ก่อนแล้ว, ไม่เกี่ยวกับ patch นี้): 39/39 passed
```

**Build:** ลบ `%LOCALAPPDATA%\PoePriceTrade\cache\` เก่า → build จาก `.spec` เดิม → `dist/PoE-Price-Trade-Checker.exe` (13.1 MB)

**Fix ระหว่างทาง:** `build_mod_meta.py` เขียนไฟล์ถูกแล้วแต่ crash ตอน print ข้อความไทยบน console cp1252 (Windows) — เพิ่ม `sys.stdout/stderr.reconfigure(encoding="utf-8")` กันไว้

**ค้างอยู่:**
- ยังไม่ได้ทดสอบ F5 popup กับเกมจริง (checklist: tier badge ตรงเกม, 💰 สีทอง, hybrid 2 บรรทัดขึ้นครบ, บรรทัดสรุป, ลบ mod_meta.json ชั่วคราวแล้ว popup ยัง fallback ได้)
- `tests/test_ninja_client.py` พังอยู่ก่อน patch นี้ (`_parse_exchange_overview` ไม่มีใน `ninja_client.py`) — ไม่เกี่ยวกับ patch นี้ แต่ควรแก้ในรอบถัดไป

---

## 2026-06-26 — poe2scout integration: PoE2 uniques + 15 currency categories (session 9)

**Commit:** `edd375f`

**ปัญหา:** poe.ninja PoE2 มีข้อมูลแค่ Currency (49) + Delirium (26) = 75 items ไม่มี unique เลย

**Probe (tools/probe_poe2scout*.py):**
- `poe2scout.com` มี FastAPI public (ไม่ต้อง key) — OpenAPI spec ที่ `/api/openapi.json`
- Realm = `poe2`, endpoint pattern: `GET /api/poe2/Leagues/{league}/...`
- ราคาหน่วย **exalted**; convert เป็น divine ด้วย `DivinePrice` จาก `/Leagues`
- Runes of Aldur: DivinePrice = 357.43 ex/div

**ไฟล์ใหม่/แก้:**

- **`poe_price_trade/poe2scout_client.py`** (NEW):
  - `fetch_all(league)` → ดึง 15 currency categories + unique items → list[PriceEntry]
  - Currency categories: runes, essences, fragments, soul cores, omens, expedition, catalyst, breach, abyss, uncut gems, lineage support gems, incursion, idols, verisium, vaal (skip currency+delirium — poe.ninja ครอบแล้ว)
  - Unique categories: weapon, armour, accessory, jewel, flask, map, sanctum
  - Fix: skip items ที่ `CategoryApiId` ไม่อยู่ใน `_UNIQUE_CATEGORY` (กรอง currency items ที่ปนมา)

- **`poe_price_trade/repository.py`**:
  - `_merge_poe2scout()` — fetch poe2scout หลัง poe.ninja, dedup ด้วย `normalized_name` (poe.ninja เป็น primary)
  - Disk cache เพิ่ม `exalted_value` field (backward-compat: `.get("exalted_value", 0.0)`)

- **`poe_price_trade/overlay.py`**:
  - เพิ่ม explicit color สำหรับ category ใหม่ (Rune, Essence, SoulCore, Omen ฯลฯ) ทั้งหมดเป็น currency tan

**ผลลัพธ์ (Runes of Aldur):**
```
poe.ninja:   75 entries (Currency 49 + Delirium 26)
poe2scout: 1023 entries (Rune 142, Essence 82, Unique 425+, ...)
รวม:       ~1098 entries
```

**ค้างอยู่:**
- ลบ disk cache เก่าก่อนรัน (ไม่มี exalted_value) หรือรอให้หมดอายุเองใน 30 นาที
- rebuild .exe ให้รวม poe2scout_client.py

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
