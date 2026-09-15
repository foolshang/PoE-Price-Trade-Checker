# PoE Price & Trade Checker — History (Project Changelog)

> รูปแบบ entry: วันที่ — สรุปสิ่งที่ทำ — ไฟล์ที่แตะ — สถานะ/ปัญหาค้าง
> เพิ่ม entry ใหม่ไว้ **บนสุด** เสมอ

---

## 2026-09-15 — F4 "Skill Mod Reference" prep, hidden behind flag (v0.7.5)

**Why:** Future replacement for F4 price-check — pick a skill, see popular mods
per slot (helmet/body/gloves/.../weapon), eventually a Passive section too. The
hub doesn't publish `skills[]`/`passives[]` yet, so this round is UI+data-layer
scaffolding only, tested against a mock file, wired behind a default-off flag
so the existing F4 flow (scan+hover price check) stays completely untouched.

**Added:**
- `config.py`: new `f4_mode` key, default `"price"` (old behavior). Setting it
  to `"skill_ref"` switches F4 to the new window instead.
- `skill_ref.py` (new): `SkillRefDB` data layer — `search_skills(prefix)`
  (autocomplete), `mods_for_skill(name)` (skill → archetype → slot → mods),
  `passives_for_skill(name)` (phase-2 stub, always `[]`). `source="mock"` reads
  `%LOCALAPPDATA%\PoePriceTrade\mock\skill_meta_mock.json`; `source="hub"` is an
  intentional `NotImplementedError` stub — see the `TODO(hub)` block at the top
  of the file for exactly what's missing hub-side before that can be wired up.
- `skill_ref_window.py` (new): `SkillRefWindow`, a `Toplevel` styled like
  `mod_picker.py`'s `ModPickerWindow` — skill entry with live dropdown
  (`search_skills` on every keystroke), mod table grouped by slot/rank once a
  skill is picked, and a static "Passive — รอข้อมูลจาก hub" placeholder section.
- `tools/skill_meta_mock.json` (new): 4 skills / 3 archetypes (attack-bow,
  attack-melee, spell-lightning) / ~15 mods across several slots, enough to
  exercise autocomplete + the per-slot table.
- `app.py`: `_on_f4_scan` gained a one-line guard at the top — if
  `config.f4_mode == "skill_ref"`, open `SkillRefWindow` and return; otherwise
  falls through to the existing scan+hover code completely unchanged (no other
  line in the existing F4 path was touched).

**Verified:**
- `SkillRefDB` exercised directly against the mock file (search/mods/passives
  incl. unknown-skill case) — correct.
- `SkillRefWindow` driven programmatically (set skill var, select, check
  suggestion list + rendered table + close callback) — correct.
- Built v0.7.5 from the existing `.spec`, ran the real exe: confirmed the
  window title bar shows `v0.7.5`; with `f4_mode` temporarily flipped to
  `"skill_ref"` in the real config and the mock file copied into
  `%LOCALAPPDATA%\PoePriceTrade\mock\`, a real F4 keypress (OS-level
  `RegisterHotKey`, confirmed via `SendKeys` + window enumeration, not just
  simulated in-process) opened the "Skill Mod Reference" window as expected.
  Reverted `config.json` to its original state afterward (`f4_mode` absent →
  defaults back to `"price"`) — the user's live config/session were not left
  in the new mode.

**Known gap:** hub has no `skills[]`/`passives[]` yet — see `TODO(hub)` in
`skill_ref.py`. Do not flip the default `f4_mode` to `"skill_ref"` or point
`source` at `"hub"` until the hub side ships that data.

---

## 2026-09-14 — Category-based search for rare/magic with stats (v0.7.4, phase 2/2)

**Why:** Phase 1 (v0.7.3) fixed most "item not found" cases by canonicalizing
the base name and searching all-rarity (`nonunique`), but an identified
rare/magic item with mods still pinned an exact base type — a base that
resolves to the wrong subtype, or any residual base-name mismatch the
canonical DB doesn't cover, still zeroes out results. EE2's other fix for
this is to drop the base entirely for these items and search by trade's
broader item **category** (e.g. "Warstaff") instead, relying on the stat
filters to narrow things down.

**Fix:**
- `profiles.py`: added `item_class_category` to `GameProfile` — a
  `{normalized item class: trade category id}` map, populated per game
  (PoE2 gets the full weapon/armour/accessory/jewel/flask/map set including
  PoE2-only classes like Warstaff/Crossbow/Spear/Flail/Focus/Waystone;
  PoE1 gets the classes that exist there). Category ids are the same
  `weapon.*`/`armour.*`/`accessory.*` ids EE2 uses.
- `trade_url.py`: in the identified rare/magic branch, stat filters are now
  computed first; if any resolved **and** the item's class has a category
  mapping, the query drops `type` entirely and searches
  `category=<id> + rarity=nonunique + stats` instead. Otherwise it falls
  back to phase 1's behavior (canonical base + `nonunique`, stats if any) —
  so an unmapped item class or an item with zero resolved stats never loses
  functionality, it just doesn't get the wider category search.

**Verified before build:** throwaway script covering all four paths —
mapped class + resolved stats → category query (no `type`, has `stats`);
unmapped class → base fallback; mapped class but no resolved stats → base
fallback with no `stats` key; PoE1 mapped class → category query. Also
re-ran phase 1's unique/unidentified assertions to confirm no regression.
Confirmed in the built exe that price/hub loading and startup are
unaffected.

---

## 2026-09-14 — Base canonical DB + rarity nonunique: fix F5 "item not found" (v0.7.3, phase 1/2)

**Why:** F5 trade search sent the raw clipboard base/unique name and the
item's exact rarity straight into the query. A quality prefix ("Superior
..."), a base name that doesn't match trade's own spelling, or querying an
exact rarity when the listing is actually a different one of
normal/magic/rare all silently produced a trade search with zero results —
same root causes Exiled-Exchange-2 (EE2) already solved via its
findInDatabase() + rarity="nonunique" approach. Phase 1 of 2 (phase 2 =
category-based search for rare items with mods, still to come).

**Fix:**
- New `base_db.py` (`BaseDB`): loads GGG's `trade(2)/data/items` endpoint
  per game, caches to disk (same pattern/TTL as `mod_db.py`'s stats cache),
  and resolves a raw base/unique name to trade's canonical spelling —
  exact match first (so a base that genuinely starts with a quality-like
  word, e.g. "Exceptional Verisium", isn't mangled), then quality-prefix
  stripped, then fuzzy match; falls back to the raw name untouched if
  nothing resolves or the fetch fails.
- `profiles.py`: added `trade_items_url` to `GameProfile`, pointing at each
  game's own `data/items` endpoint.
- `trade_url.py`: `build_trade_url`/`open_trade` take an optional `base_db`
  and resolve `query["type"]`/`query["name"]` through it before building
  the query; identified normal/magic/rare items now search
  `rarity=nonunique` (all three levels at once) instead of pinning the
  exact rarity, matching EE2's relaxed default.
- `app.py`: constructs and loads a `BaseDB` alongside the existing
  per-profile `ModDatabase` (both places `_mod_db` is created/reset), and
  passes it into both `open_trade` call sites.

**Verified before build:** mock-data lookup tests (prefix strip, exact
priority, fuzzy fallback), a live fetch against PoE2's real endpoint (3129
base/type entries, 464 unique names, correct resolution), and
`build_trade_url` payload shape for rare/unique/unidentified branches — all
via throwaway scripts, no test files added. Confirmed in the built exe:
previously-unfindable rares now resolve, unique/unidentified search
unaffected.

---

## 2026-09-14 — Mod Picker: min-value prefill matches the game's mod number (v0.7.2)

**Why:** F5's mod-picker window (`mod_picker.py`) prefilled the min-value
search box as `mod.value × 0.8` rounded to 2 decimals — a deliberate search
buffer, but the result no longer matched the number actually printed on the
mod in-game, which read as wrong rather than as an intentional buffer.

**Fix (mod_picker.py):** min-value box now prefills with the mod's own
parsed value, formatted with `:g` instead of `round()` — whole-number mods
show without a trailing decimal (47.0 → "47"), while mods that genuinely
roll with a decimal in-game (e.g. 6.5%) keep it, since `round()` would have
silently changed them away from the in-game number. Removed the now-unused
`_MIN_PCT` constant. Users who want a search buffer can still widen the
range manually in the box.

---

## 2026-08-08 — Currency anchor candidate lists: fix recurring resolution failures (v0.7.1)

**Why:** Switching PoE1 to strictness 3 (STRICT) broke tier C's currency
anchor again — same failure mode as the 2026-07-27 "Orb of Augmentation"
incident (v0.6.3-0.6.4), just at a different strictness level. Root cause is
systemic, not a one-off wrong name: `_DEFAULT_RULES["anchors"]` used a single
fixed BaseType per tier, and that's inherently fragile across 14 real
NeverSink files (2 games x 7 strictness levels 0-6) — the same tier's
representative item sits in a different block (or no ordinary Show block at
all) depending on game/strictness.

**Fix (filter_gen.py):**
- `_DEFAULT_RULES["anchors"]` changed from `{tier: name}` to `{tier: [name,
  ...]}` — an ordered list of fallback candidates per tier, tried in order
  via the new `_resolve_anchor()` helper. Plain strings are still accepted
  everywhere an anchor is passed (treated as a one-item list), so existing
  overrides/tests using a bare string keep working.
- `merge_currency_into_base()` now resolves each of S/A/B/C independently
  instead of all-or-nothing: a tier whose candidates all fail to resolve is
  skipped (left exactly as NeverSink's base filter already has it) without
  failing the merge for the other tiers. `applied=False` only when *none* of
  the four tiers resolve at all.
- New `resolve_anchors(base_text, anchors)` — standalone per-tier resolution
  status ({tier: resolved_name_or_None}), used by `build_filter()` (now
  returns a 4-tuple including this) and by the new verification script.
- `apply_base_filter_sounds()` / `resolve_real_styles()` updated to resolve
  through the same candidate-list logic.
- `app.py`'s Generate log message now reports which tiers resolved and which
  were skipped, instead of one lumped ok/warn line.

**Candidate lists (verified against all 14 real files, see below):**
```
S: ["Divine Orb", "Mirror of Kalandra"]
A: ["Exalted Orb", "Chaos Orb"]
B: ["Chaos Orb", "Vaal Orb", "Regal Orb"]
C: ["Orb of Transmutation", "Orb of Augmentation", "Scroll of Wisdom",
    "Orb of Alchemy", "Chromatic Orb"]
```
S/A/B's first candidate alone already resolves on all 14 files (Divine/
Exalted/Chaos Orb are never hidden at any real strictness); the rest is
defensive slack. C is the tier that actually needs the fallback chain:
"Orb of Transmutation" only holds through SEMI-STRICT (0-2); STRICT+ (3-5)
falls through to "Orb of Alchemy"; PoE1's UBER-PLUS-STRICT (6) hides every
dedicated low-currency block outright, so C only resolves there via
"Chromatic Orb" (still bundled into the same Show block as Chaos/Exalted
Orb at that strictness, rather than hidden).

**Verification — new `tools/verify_anchors.py`:** downloads all 14 real
NeverSink base filters (both games, strictness 0-6) through the app's own
`neversink_source.fetch_base_filter`, resolves every tier's anchor on each
via `filter_gen.resolve_anchors`, and fails loudly (non-zero exit, full
per-file/per-tier matrix printed) unless every tier resolves on every file.
Run for real against the live GitHub releases (not a single cached file) as
part of this fix:

```
14 file(s) checked, 0 tier-resolution failure(s), 0 fetch failure(s)
OK: every tier resolved on all 14 real NeverSink files.
```

**Files touched:** `poe_price_trade/filter_gen.py`, `poe_price_trade/app.py`,
`tests/test_filter_gen.py`, `tools/verify_anchors.py` (new),
`poe_price_trade/__init__.py` (version bump)

**Tests:** 84/84 in `test_filter_gen.py`, 230/230 across the full suite.
Rewrote the tests that encoded the old all-or-nothing behavior
(`test_merge_currency_into_base_falls_back_when_an_anchor_is_unresolvable`,
`test_build_filter_anchor_unresolvable_never_emits_our_own_currency`,
`test_build_filter_partial_real_styles_even_when_surgery_fails`) into
pairs that instead assert the new per-tier-skip behavior (one tier
unresolvable doesn't sink the others) and the true all-unresolvable case.

**Pending:** in-game F5/F4 regression pass not re-run this session (no
Filter Generator UI surface changed, only the anchor resolution logic
underneath it — covered by the real-data verification script instead).

---

## 2026-08-01 — System tray support: minimize-to-tray, auto-regen notification (v0.7.0)

**เหตุผล:** ผู้ใช้อยากได้พฤติกรรมแบบ Discord — X/minimize ย่อลง tray แทนปิด
โปรแกรม (มี setting เลือกได้ว่า X = ปิดจริงหรือย่อ) และแจ้งเตือนตอน auto-regen
เขียน filter ใหม่สำเร็จ ("Filter updated (N items changed tier) — reload in
game") เพราะปกติมีแค่ log line ในหน้าต่างที่ผู้ใช้อาจไม่ได้มองอยู่

**ทดสอบก่อนตัดสินใจสถาปัตยกรรม:** ยิง `pystray` balloon จริงตอน PoE รัน
fullscreen บนเครื่อง dev — **balloon ไม่ขึ้น** (Windows Focus Assist "when
playing a game" ระงับไว้ เห็นแค่ tooltip ไอคอนเวลา hover) เพราะฉะนั้น balloon
เป็นได้แค่ช่องทางรอง ช่องทางหลักต้องเป็น in-game overlay ที่ใช้ร่วมกับ F4
hover (`overlay.py`'s `PriceOverlay` — topmost + click-through, พิสูจน์แล้วว่า
render ทับเกม fullscreen ได้จริง)

**เลือก `pystray`+`Pillow`** แทน raw `ctypes`/`Shell_NotifyIcon` หลังเทียบ
tradeoff กับ user โดยตรง (tray icon ต้องมี hidden window + message loop +
WNDPROC + popup menu ของตัวเอง ซับซ้อนกว่า DPAPI/SHGetKnownFolderPath ที่มีอยู่
เดิมมาก) — เป็น exception ที่สองต่อจาก `winrt` (OCR) ในกฎ stdlib-only เดิม

**Safety net (ผู้ใช้ขอเพิ่มก่อนอนุมัติ plan):** `TrayIcon.start()` คืน
`bool` — ถ้า tray init ล้มเหลว (ทดสอบจริงด้วยการลบ `icon.ico`) `App` เก็บเป็น
`self._tray_ok = False` แล้ว X-button/minimize **fallback กลับไปพฤติกรรมเดิม
ก่อนมี feature นี้ทันที** (X = ปิดจริงเสมอ, minimize = taskbar ปกติ) ไม่ใช่
ทำให้หน้าต่างหายแบบเรียกคืนไม่ได้ — ยืนยันแล้วทั้งระดับ `tray.py` เดี่ยวๆ และ
ระดับแอปเต็ม (log แสดง `Tray icon unavailable — falling back...` ถูกต้อง)

**`WM_TASKBARCREATED` (Explorer restart):** เช็คซอร์สโค้ด `pystray` 0.19.5
ที่ติดตั้งจริงแล้ว (`pystray/_win32.py:46,227,258`) — มี handler จัดการเองอยู่
แล้ว (re-register ไอคอนเอง + opt-in ผ่าน `ChangeWindowMessageFilterEx` ให้รับ
broadcast ได้แม้รันแบบ elevated) **ไม่ใช่ known limitation** ตามที่กังวลไว้
ตอนแรก ไม่ต้องเขียนโค้ดจัดการเพิ่ม

**ไฟล์ที่แตะ:**
- `poe_price_trade/tray.py` (ใหม่) — wrap `pystray.Icon`, `start()`คืน
  success/fail จริง (รอ `setup` callback ผ่าน `threading.Event` + timeout 2s),
  `set_pending()` สลับไอคอน badge จุดแดง, `notify()` best-effort ไม่มีวัน raise
- `tools/build_icon.py` (ใหม่) + `poe_price_trade/assets/icon.ico` (ใหม่,
  generate ด้วย Pillow, ไม่มี asset ภายนอก)
- `app.py` — `_on_close_button`/`_on_unmap` เช็ค `self._tray_ok` ก่อนเสมอ,
  auto-regen notification (`_filter_regen_check` → `_do_generate_filter`
  รับ `notify_change_count` optional → `_on_auto_regen_notify`) ยิงเฉพาะ path
  auto-regen เท่านั้น ไม่ยิงตอน manual generate (ทั้งปุ่มในแอปและเมนู tray)
- `filter_gen.py` — เพิ่ม `tier_mapping()` (แยกออกมาจาก `signature()` เดิม)
  และ `diff_mapping_count()` สำหรับนับ "N items changed tier" จริง (hash
  เดิมบอกได้แค่ "เปลี่ยนหรือไม่เปลี่ยน" นับจำนวนไม่ได้)
- `config.py` (`close_action` default), `settings.py` (Advanced tab),
  `requirements.txt` (`pystray`, `Pillow`), `.spec` (icon= + datas + pystray
  hiddenimport — ปรากฏว่า `pyinstaller-hooks-contrib` มี hook ของ `pystray`
  เองอยู่แล้วด้วย เจอตอน build จริง)

**บั๊กที่เจอจาก manual build จริง (คุ้มมากที่ทดสอบก่อนถือว่าเสร็จ):**
`_asset_path()` ตอน frozen ใช้ `sys._MEIPASS/assets/icon.ico` แต่ PyInstaller
onefile เก็บ `datas` ตาม path สัมพัทธ์จาก source จริง (`poe_price_trade/assets/`)
ทำให้ exe จริงหา icon ไม่เจอ (`_MEI.../assets/icon.ico` ไม่มีจริง ต้องเป็น
`_MEI.../poe_price_trade/assets/icon.ico`) — source run ไม่เจอปัญหานี้เพราะ
`Path(__file__).parent` ไม่มี prefix `poe_price_trade` อยู่แล้ว ดังนั้น
"รันจาก source ผ่าน" ไม่ได้แปลว่า exe จริงจะผ่านด้วย ต้อง build+รัน exe จริง
เพื่อยืนยัน แก้แล้ว build ใหม่ยืนยันว่า tray init สำเร็จจากทั้ง source และ exe

**Tests:** เพิ่ม `test_tier_mapping_matches_what_signature_hashes`,
`test_diff_mapping_count_*` (4 เคส: identical/wobble/tier-change/add-remove)
ใน `test_filter_gen.py`, `test_state_round_trip_last_mapping` ใน
`test_filter_output.py` — รวม 228/228 passed

**ยังไม่ทดสอบ (ต้องมือจริงกดใน UI):** left-click restore, right-click menu
ทั้ง 4 item, การันตี fullscreen overlay ทับเกมจริงตอน auto-regen (ช่องทางหลัก
ที่ทั้ง feature นี้มีไว้เพื่อสิ่งนี้), cold-start suppress-first-notification —
รายการเต็มอยู่ใน plan file ตอน implement (`sparkling-purring-balloon.md`)

---

## 2026-07-27 (ต่ออีกรอบ) — filter_gen_rules.json merge แทน wholesale replace (v0.6.4)

**สาเหตุที่ user สั่งให้แก้:** การแก้ anchor C ใน v0.6.3 ใช้ได้เฉพาะเครื่องที่
ไม่เคยกด "Save Settings"/"Generate" มาก่อน — เครื่องไหนเคยกด `load_rules()`
เดิม replace ทั้ง dict เมื่อไฟล์ valid ทำให้ค่าที่ save ไว้ตอนเก่า (รวม
`anchors` ที่ UI ไม่เคยมีให้แก้เลย) บัง default ที่แก้ใหม่ไว้ตลอดไป ต้องแก้ที่
root ไม่ใช่แค่ลบไฟล์ user รายคน

**แก้ (`filter_gen.py`):**
- `load_rules()`: เปลี่ยนจาก wholesale replace เป็น **merge เฉพาะ
  `tiers[].min_chaos`** — ฟิลด์เดียวที่ Filter Generator UI จริงๆ ให้แก้ได้
  ("Tier thresholds (chaos, fallback)") ฟิลด์อื่นทั้งหมด (`anchors`, สี,
  เสียง, `min_divine_pct`, `max_count`, `divine_sanity_floor`) มาจาก
  `_DEFAULT_RULES` ของโค้ดปัจจุบันเสมอ ไม่มีทางถูกไฟล์เก่าบังได้อีกต่อไป
  ไฟล์ที่ไม่มี/อ่านไม่ได้/ไม่ใช่ JSON object ถือเป็น "ไม่มี override" เหมือนเดิม
  ไม่ throw
- `save_rules()`: เขียนแค่ `{"tiers": [{"name", "min_chaos"}, ...]}` ไม่ dump
  `rules` ทั้งก้อนอีกต่อไป — `filter_window.py` **ไม่ต้องแก้เลย** เพราะยังส่ง
  `self._rules` ทั้งก้อนมาเหมือนเดิม แต่ `save_rules` เป็นคนเลือกเองว่าจะเก็บ
  แค่ส่วนไหน (single source of truth เรื่อง schema อยู่ที่ `filter_gen.py`)
- ผลคือไฟล์เก่าที่ค้าง `anchors.C = "Orb of Augmentation"`/`hide_below`
  ทุกเครื่องที่เคยกด Save **self-heal อัตโนมัติ** ตั้งแต่ครั้งแรกที่เปิด v0.6.4
  โดยไม่ต้องลบไฟล์เอง — ยืนยันจริงบนเครื่อง dev: เขียนไฟล์ stale ตัวเดิม
  เป๊ะกลับไปที่ `%LOCALAPPDATA%\PoePriceTrade\filter_gen_rules.json` แล้ว
  `load_rules()` คืน `anchors["C"] == "Orb of Transmutation"` ถูกต้อง (ไม่ใช่
  ค่าเก่าในไฟล์) แล้วลบไฟล์ทดสอบทิ้ง

**Tests:** อัปเดต `test_save_then_load_rules_roundtrip` (roundtrip แค่
`min_chaos` แล้ว ไม่ใช่ `divine_sanity_floor`), เพิ่ม
`test_save_rules_only_persists_tier_min_chaos`,
`test_load_rules_ignores_everything_except_tier_min_chaos` (จำลอง stale file
เป๊ะจาก incident จริง ยืนยันว่าไม่บัง default ใหม่) — รวม 222/222 passed

**ไฟล์ที่แก้:** `filter_gen.py` (`load_rules`/`save_rules`),
`tests/test_filter_gen.py`, `__init__.py` (v0.6.3 → v0.6.4)

---

## 2026-07-27 (ต่อ) — แก้ PoE1 anchor resolution ไม่เจอ (root-caused ด้วยไฟล์จริง, v0.6.3)

**บั๊กที่ user รายงาน:** v0.6.2 รันจริงแล้ว (ยืนยันจาก title bar) กด Generate
บน PoE1 ยังขึ้น "รวม currency เข้ากับ base ไม่ได้ (หา anchor block ไม่เจอ)"
เหมือนเดิม user สั่งห้ามเดา ให้ debug จากไฟล์จริงที่ checker cache ไว้เท่านั้น

**Diagnostic ตามลำดับที่ user สั่ง:**
1. โหลด `%LOCALAPPDATA%\PoePriceTrade\cache\neversink\poe1\8.20.0b_2.filter`
   (ไฟล์ cache จริงที่ runtime ใช้ อ่านจาก `last_check.json` ยืนยัน tag ตรงกับ
   ที่ generate จริงใช้) grep หา Divine/Exalted/Chaos/Orb of Augmentation
   ทุก block จริง
2. รัน `filter_gen._parse_blocks`/`_find_anchor_block` ปัจจุบันกับไฟล์นั้นตรงๆ
   พบว่า S/A/B (Divine/Exalted/Chaos Orb) resolve ได้ปกติ (ข้าม
   StackSize-gated block ถูกต้อง) แต่ **tier C anchor เดิม ("Orb of
   Augmentation") resolve ไม่ได้เลย** — ใน filter จริงของ PoE1, "Orb of
   Augmentation" ปรากฏแค่ใน block ที่มี `StackSize >= N` (leveling/
   stackedsupplieslow, ถูกกันออกโดย `_block_matches_plain_single_item`
   ถูกต้องแล้ว) กับ block `Hide` สุดท้าย (`$tier->t9armour`) เท่านั้น — ไม่มี
   Show block เปล่าๆ ที่มีชื่อนี้เลยสักที่ ("Orb of Augmentation" verified
   live 2026-07-24 กับไฟล์ PoE2 เท่านั้น ไม่เคยเช็คกับ PoE1 มาก่อน)
3. **แก้ตามที่เห็นจริง:** เปลี่ยน `anchors["C"]` จาก "Orb of Augmentation" →
   "Orb of Transmutation" — ยืนยันกับไฟล์จริงทั้งสองเกม: PoE1 มี Show block
   จริง (`$tier->t8trans`, สีแทน ไม่มีเสียง) ที่มีชื่อนี้ตรงๆ ส่วน PoE2 ชื่อนี้
   อยู่ **ใน block เดียวกัน** กับ "Orb of Augmentation" เป๊ะ (`$tier->
   supplymagic`) — เปลี่ยนแล้ว resolve ไป block เดิมทุกประการ ไม่กระทบ PoE2
   เลย (zero-risk swap, ยืนยันด้วยไฟล์จริงทั้งคู่ ไม่ใช่เดา)
4. **Test fixture ตัดจากไฟล์จริง** (`tests/test_filter_gen.py`) —
   `_REAL_POE1_SEMI_STRICT_EXCERPT` (บรรทัด 14912-15484 ของ
   `8.20.0b_2.filter`, ครอบทุก StackSize-gated block + block เป้าหมายจริง
   ของ S/A/B/C + Hide สุดท้าย) และ `_REAL_POE2_SEMI_STRICT_EXCERPT`
   (บรรทัด 3406-3479 ของ `0.10.3_2.filter`) — ก็อปมาตรงๆ ไม่ตัดต่อ/ปรับแต่ง
   เพิ่มเทส `test_find_anchor_block_resolves_all_default_anchors_on_real_
   poe1/poe2_filter`, `test_merge_currency_into_base_surgery_applies_on_
   real_poe1/poe2_filter`, `test_default_anchor_c_is_orb_of_transmutation_
   not_augmentation` — รันก่อนแก้โค้ดยืนยันว่า fail จริงตรงกับอาการที่ user
   รายงาน (3 เทส fail, PoE1 anchor C resolve ไม่ได้) แล้วแก้โค้ดแล้ว pass
   ทั้ง 5 เทสใหม่ ปรับเทสเดิม 3 ตัวที่จำลอง "anchor unresolvable" ให้ break
   ชื่อ "Orb of Transmutation" แทน "Orb of Augmentation" (ของเดิม break ผิด
   ชื่อไปแล้วหลังเปลี่ยน default — เทสไม่ได้ทดสอบอะไรจริงอีกต่อไปถ้าไม่แก้)
5. **รันจริงยืนยันบนเครื่อง dev (ไม่ใช่แค่ unit test):** จำลอง
   `app.py._do_generate_filter(gv="poe1")` ทุกขั้นตอนตรงๆ ด้วย config/cache
   จริง (`%LOCALAPPDATA%\PoePriceTrade`) + hub data สดจริงทาง network
   (`hub_client.get_prices("poe1/prices/latest.json")`, 837 currency
   entries, generated_at 2026-07-27T16:08:37Z) — **`surgery_applied =
   True`** ไม่มี warning "หา anchor block ไม่เจอ" อีกแล้ว Divine Orb/Orb of
   Transmutation ยืนยันอยู่ block จริงของ NeverSink ใน merged output

**เจอเพิ่มระหว่าง verify (นอก scope เดิมแต่บล็อกการ verify จริง):**
`%LOCALAPPDATA%\PoePriceTrade\filter_gen_rules.json` มี override เก่าค้างอยู่
(บันทึกจากตอน user กด "Save Settings"/"Generate" บน build เก่าก่อนหน้านี้ —
`_save()` ใน `filter_window.py` เขียนทั้ง `self._rules` ทับกลับไปดิสก์ทุกครั้ง
รวม `anchors` ที่ไม่มี UI ให้แก้เลย) ค่าที่ค้างอยู่ตรงกับ default เก่าทุก field
(`anchors.C = "Orb of Augmentation"`, `hide_below` ที่ถูกลบไปแล้วจาก v0.6.2)
— `load_rules()` replace ทั้ง dict เมื่อไฟล์ valid จึงบัง fix นี้ไว้เงียบๆ ต่อไป
เรื่อยๆ ถ้าไม่ล้าง ลบไฟล์นี้ทิ้งบนเครื่อง dev เพื่อให้ verify ข้อ 5 สะท้อน
โค้ดจริง (ไม่ใช่ค่าที่ค้าง) ไม่ได้แก้ logic การ save/merge ของ
`load_rules`/`save_rules` เพราะไม่ใช่สิ่งที่ user สั่งให้แก้ในรอบนี้ — ถ้า user
เจอ anchor ผิดแบบเดิมอีกหลัง save settings บน build เก่า สาเหตุคือไฟล์นี้
เช่นกัน (ลบทิ้งแล้ว regenerate ใหม่ได้)

**ไฟล์ที่แก้:** `filter_gen.py` (`_DEFAULT_RULES["anchors"]["C"]` + comment),
`tests/test_filter_gen.py` (fixture จริง + เทสใหม่ 5 ตัว + แก้เทสเดิม 3 ตัว),
`__init__.py` (v0.6.2 → v0.6.3)

**Tests:** 220/220 passed (ทั้ง repo) + real end-to-end run ยืนยันแยกต่างหาก
ตามข้อ 5 ข้างบน (ไม่ใช่แค่ unit test)

---

## 2026-07-27 — แก้ dim bucket กิน currency จริงในเกม (dead-economy incident, v0.6.2)

**บั๊กที่ user รายงาน (แนบสกรีนช็อต):** Chaos Orb จากไฟล์ generated กลายเป็น
ตัวเทาจางไม่มีกรอบ แต่ NeverSink แท้ strictness เดียวกันเป็นพื้นส้มเด่น + beam
สาเหตุ: `bucket_currency()` เดิมยังมี fallback bucket "hidden" สำหรับ currency
ที่ต่ำกว่า `hide_below` — bucket นี้ไปออกที่ `emit_dim_section()` ซึ่งอยู่ใน
`generated_section` ที่เขียนไว้**ก่อน** `base_text` เสมอ (first-match-wins)
snapshot จริงที่ user เจอเป็น dead/end-of-league (Divine 8.76c, Mirror of
Kalandra ~42211c) ทำให้ `min_divine_pct` threshold ของทุก tier หดลงใกล้ 0 และ
Chaos Orb เองรายงาน chaos_value เกือบ 0 ในสภาพเศรษฐกิจแบบนี้ ตกไปอยู่ใต้
`hide_below` (0.5) → เข้า dim bucket → ทับ block จริงของ NeverSink ที่ควรเด่น
อยู่แล้ว

**แก้ 3 จุดตามที่ user สั่ง (`filter_gen.py`):**

1. **ตัด currency ออกจาก dim bucket ทั้งหมด** — `bucket_currency()` ไม่มี
   "hidden" list อีกต่อไป (signature เปลี่ยนจาก `tuple[dict, list]` เหลือ
   แค่ `dict`) ชื่อที่ไม่เข้าเกณฑ์ tier ไหนเลย **ไม่ถูกแตะเลย** ไม่ merge ไม่
   dim ปล่อยตามตำแหน่งเดิมใน NeverSink base filter 100% ลบ `emit_dim_section()`
   ทั้งฟังก์ชันและ `hide_below` field ทิ้ง (ไม่ใช่แค่เลิกเรียก — ตามธรรมเนียม
   เดิมของโปรเจกต์ที่เคยทำกับ `emit_currency_section()`/"Unique fallback")
   รวมถึงลบ UI field "Dim below (chaos)" ออกจาก `filter_window.py` ด้วย เพราะ
   ไม่มีผลอะไรแล้ว
2. **Never-demote guard ใน `merge_currency_into_base()`** — ก่อนย้ายชื่อเข้า
   block เป้าหมาย เทียบกับ block ที่ชื่อนั้นอยู่แล้ว (จาก anchor blocks S/A/B/C
   เดิม อ่านจาก `base_text` ที่ยังไม่ถูกแก้เลย กันไม่ให้ ratchet ข้ามรอบ
   generate) ถ้า tier ที่ hub คำนวณได้ **เด่นน้อยกว่า** ที่มันอยู่แล้ว ปฏิเสธ
   การย้าย เก็บไว้ที่ tier เดิมแทน — งานของเราคือยกของแพงขึ้น ไม่ใช่กดของถูกลง
   ตามที่ user สั่งตรงๆ ผลข้างเคียง: เทสต์เดิม 2 ตัวที่ทดสอบ "ย้ายลง tier"
   (ซึ่งขัดกับ spec ใหม่) ถูกเปลี่ยนเป็นเทสต์ guard แทน
3. **Sanity check ก่อน merge (`divine_sanity_floor`, ค่าเริ่มต้น 15c)** —
   `_resolve_divine_chaos_for_tiering()` (ใหม่): ถ้า Divine Orb ของ snapshot
   ต่ำกว่า floor นี้ ถือว่าเป็น dead/anomalous economy → log warning + ปิด
   `min_divine_pct` tiering สำหรับรอบ generate นั้น (fallback ไป absolute
   `min_chaos` แทน ซึ่งเสถียรไม่ผันตาม Divine ที่พัง) ใช้ทั้งใน
   `bucket_currency`/`bucket_uniques` (ทั้งคู่เจอปัญหาเดียวกันได้ — diagnostic
   2026-07-25 เจอว่า flood ทั้ง currency และ unique พร้อมกัน) ปรับ floor ได้ผ่าน
   `filter_gen_rules.json`

**ขอบเขตที่ตั้งใจไม่แตะ:** never-demote guard ใช้กับ currency (`merge_currency
_into_base`) เท่านั้น ไม่ได้ขยายไป unique section — unique bucketing เป็น
self-generated (ไม่ใช่ surgical merge จาก baseline จริง) การจะเช็ค "NeverSink
เคยจัดให้เด่นกว่านี้ไหม" ต้อง simulate first-match-wins กับ block ชื่อ unique
เฉพาะทุกตัวซึ่งเป็นงานคนละขนาดจากบั๊กที่รายงานจริง (which เป็น currency
ล้วนๆ) — ถ้าเจอปัญหาเดียวกันฝั่ง unique ค่อยแยกทำเป็นงานใหม่

**Tests:** อัปเดต `tests/test_filter_gen.py` — ลบเทส `emit_dim_section` ทั้งชุด
(3 เคส), แก้ `bucket_currency` call site ทุกจุดให้ตรง signature ใหม่, เพิ่ม
เทส dead-economy sanity check (`_resolve_divine_chaos_for_tiering`,
`bucket_currency` fallback ไป absolute), เทส guard (ปฏิเสธการลด tier แต่ไม่
บล็อกการเลื่อนขึ้น), เทส end-to-end จำลอง incident จริง (Divine 8.76c + Chaos
Orb chaos_value ~0) ยืนยันว่า Chaos Orb ไม่ปรากฏใน `generated_section` เลยและ
ยังอยู่ block เดิมของ NeverSink ครบ — รวม 215/215 passed (ทั้ง repo) ยืนยัน
ด้วย manual script จำลอง snapshot จริงอีกรอบ (นอก pytest): Chaos Orb ไม่โผล่ใน
section, ยังอยู่ block "B" เดิม, Divine Orb ไม่ถูกลดจาก S เป็น B

**ไฟล์ที่แก้:** `filter_gen.py` (หลัก), `filter_window.py` (ลบ UI field),
`tests/test_filter_gen.py`, `__init__.py` (v0.6.1 → v0.6.2)

---

## 2026-07-25 (ต่ออีกรอบ) — ทดสอบจริงในเกม: Plan B ผ่าน

user ทดสอบ `dist/PoE-Price-Trade-Checker.exe` (v0.6.1) กับเกมจริง — **ผ่าน**
เสียง/สี/ความเด่นของ currency (merge เข้า NeverSink base โดยตรง) และ unique
(style จริงจาก anchor block + ตัด fallback block ที่เคยตัดหน้า) ตรงกับที่
ควรจะเป็นแล้ว ปิดงาน Plan B เต็มรูปแบบ (entry ด้านล่าง: diagnostic + kill
fallback + real style + tier ตามสัดส่วน Divine + max_count cascade + rebuild)
สมบูรณ์

---

## 2026-07-25 (ต่อ) — Plan B เต็มรูปแบบ: kill ทุก fallback, style จริง, tier ตามสัดส่วน Divine

**ต่อจาก diagnostic entry ด้านล่าง** — พบ 2 สาเหตุ (สี A/B/C hardcode ผิด, และ
`Show # Unique fallback` ตัดหน้า unique block จริงของ NeverSink ทุกชิ้น) แก้
ทั้งคู่ในรอบเดียวตามที่ user สั่งให้เดินหน้า Plan B เต็มรูปแบบ

**1. Currency: ไม่มี fallback ของเราเองอีกต่อไป (`filter_gen.py`)** — ถาม
user แล้วยืนยัน: ถ้า `merge_currency_into_base` resolve anchor ไม่ได้
(edge case) **ไม่เติมอะไรแทนเลย** ปล่อย currency ในไฟล์ NeverSink ไว้แบบเดิม
100% (log warning) ลบ `emit_currency_section()`/`generate_section()` ทิ้งทั้ง
ฟังก์ชัน (ไม่ใช่แค่เลิกเรียก — ลบไปเลยกันหลงเรียกใช้ในอนาคต) `build_filter()`
ไม่มี branch fallback ที่ emit currency Show block ของเราเองอีกเลยไม่ว่ากรณีใด

**2. Uniques: ตัด `Unique fallback` block, ห้ามวางก่อน real rule ของ NeverSink
โดยไม่มี BaseType คุม** — เจอใน diagnostic ว่า block นี้ (`Rarity == Unique`
เงื่อนไขเดียว ไม่มี BaseType) ที่อยู่ก่อน `base_text` เสมอ (first-match-wins)
ตัดหน้า unique พิเศษจริงของ NeverSink ทั้งหมด (T1/T2 by name,
`TwiceCorrupted`/`HasVaalUniqueMod`→ม่วง beam ฯลฯ) ถาม user แล้วยืนยัน: ตัด
block นี้ทิ้ง เหลือแค่ tier ที่มีราคาจริง (S/A/B ตาม BaseType) generated_section
ที่เหลือปลอดภัยที่จะวางก่อน `base_text` ต่อไปได้เพราะไม่มีเงื่อนไขกว้างเกินคุม
ของเราเองเหลืออยู่แล้ว — bases ที่ไม่ติด tier ราคาที่รู้จัก ปล่อยให้ NeverSink
จัดการเองทั้งหมด (หลักการเดียวกับ currency: override เฉพาะที่เรามีข้อมูลจริง
ดีกว่า)

**3. Style จริงแทน hardcode (`resolve_real_styles`, ใหม่)** — ตามที่ diagnostic
พบว่า A/B/C hardcode ผิดแทบทุกแกน (สี/bg/beam/icon) ใหม่: `resolve_real_styles
(base_text, anchors)` ใช้ anchor resolution เดียวกับ currency merge ดึง
border/text/background/font/beam/icon/sound เต็มชุดจาก block จริงของแต่ละ
tier มาใช้กับ `emit_unique_section`/`emit_dim_section` โดยตรง (dim bucket ใช้
style ของ tier C จริง — "block ระดับใกล้เคียง" ตามที่ user สั่ง) ไม่ all-or-
nothing แบบ currency merge — tier ไหน resolve ไม่ได้แค่ tier นั้น fallback ไป
hardcode เดิม (`_style_lines`) ยืนยันกับ real hub+NeverSink data จริง: unique
tier A ได้ `SetBackgroundColor 245 139 87` (ส้ม) ตรงกับ Exalted Orb block จริง
เป๊ะ แทนที่ hardcode เดิม (ดำ)

**4. Tier mapping เป็น % ของ Divine แทน absolute chaos (`min_divine_pct`)**
— threshold ของแต่ละ tier เปลี่ยนจาก `min_chaos` ตายตัว (150/20/5/1) เป็น
สัดส่วนของราคา Divine Orb **สดจาก snapshot เดียวกัน** (`_resolve_divine_chaos`)
แก้ปัญหาที่ user ระบุตรงๆ: วันแรกของลีก Divine อาจถูก (เช่น 40c) ของ 30-40c
ที่เกือบเท่า Divine ควรถึง tier บนทันที ไม่ใช่รอ absolute 150c — และปลายลีก
Divine แพงขึ้น (300c+) ของราคาเท่าเดิม (30-40c) ก็ไม่ใช่ tier บนอีกต่อไปแบบ
อัตโนมัติ (ไม่ต้องปรับ threshold มือ) `min_chaos` เดิมเก็บไว้เป็น fallback
เฉพาะตอน resolve ราคา Divine จาก snapshot ไม่ได้เท่านั้น ปรับได้ผ่าน
`filter_gen_rules.json` เหมือนเดิม (ไม่ได้เพิ่ม UI ใหม่ — เปลี่ยน label ใน
Filter Generator window ให้บอกว่าช่อง "Tier thresholds" เป็น fallback แล้ว)

**บั๊กที่เจอจากการทดสอบกับ hub จริง (ไม่ได้อยู่ใน scope เดิม แต่ต้องแก้ก่อน
ปล่อย):** ลอง % ของ Divine กับ snapshot จริง (`poe2/prices/latest.json`,
league "Runes of Aldur") เจอ Divine = **8.76c** (ถูกกว่าที่คาดมาก) ขณะที่
Mirror of Kalandra = 42211c (~4800 เท่าของ Divine) — Divine ไม่ใช่ "จุดสูงสุด
ของเศรษฐกิจ" เสมอไปจริงๆ ทำให้ threshold % ล้วนๆ (เช่น S=20%×8.76=1.75c) ดัน
ชื่อเข้า tier S ถึง **169 ชื่อ** (ทั้ง currency และ unique) ทำให้ block จริงของ
NeverSink (ปกติมีแค่ ~14 ชื่อ) ถูก dilute จนความเด่นหายไปหมด ขัดกับเป้าหมาย
เรื่อง "ความเด่น" ที่ user ตามหาอยู่พอดี — เพิ่ม `max_count` ต่อ tier (S=20,
A=40, B=80, C=ไม่จำกัด) ใน `_apply_max_count()`: keep top-N ตาม chaos_value
จริง ส่วนเกิน cascade ลง tier ถัดไป (ไม่หายไปไหน) ยืนยันซ้ำกับ snapshot จริง
เดิม: หลังแก้ S=20/A=40/B=80/C=340 (รับ overflow ทั้งหมด) ตรงกับขนาด block จริง
ของ NeverSink มากขึ้นมาก

**ยืนยันกับ hub + NeverSink จริงทั้งชุด (poe2, semi-strict, tag 0.10.3,
league จริง):** `build_filter()` → `applied=True`, generated_section ไม่มี
`"Unique fallback"` และไม่มี `"Hub currency tier"` เหลือเลย, unique tier A ได้
style สีส้ม/ดำจริงตรงกับ Exalted Orb block, currency tier count หลัง
max_count = S20/A40/B80/C340 (จากทั้งหมด 526 ชื่อ หลัง dedup+exclude)

**Tests:** เขียนใหม่/เพิ่มใน `test_filter_gen.py` — ลบเทสที่อ้าง
`emit_currency_section`/`generate_section` (ฟังก์ชันถูกลบ), เพิ่มเทส
`resolve_real_styles`, `tier_of` แบบ pct (รวมเคส "30-40c วันแรกต้องถึง S"
เทียบกับ absolute เดิมที่จะพลาด), `_resolve_divine_chaos`, `_apply_max_count`
(cap, cascade, ไม่ cap, เกิน tier ต่ำสุดแล้วไม่หาย), `build_filter` ไม่ emit
currency ของตัวเองในทุกกรณี (รวม anchor unresolvable + ไม่มี base เลย),
partial real_styles ตอน surgery fail บางส่วน — รวม 212/212 passed (ทั้ง repo)

**ไฟล์ที่แก้:** `filter_gen.py` (หลัก), `app.py` (comment update + ข้อความ log
ตอน surgery ล้มเหลว), `filter_window.py` (label ช่อง tier threshold),
`tests/test_filter_gen.py`

**Build workflow ถาวร (ตามที่ user สั่งให้ทำทุกครั้งจากนี้ไป):** title bar
ใส่เลขเวอร์ชันไว้แล้วตั้งแต่ v0.3.0 (`app.py` บรรทัด `self._root.title(f"...
v{__version__}")`) — ไม่ต้องเพิ่มใหม่ บั๊มเวอร์ชัน `__init__.py` →
**v0.6.1** (patch บน v0.6.0 เดิม ยังเป็นฟีเจอร์ Filter Generator ตัวเดียวกัน)
ลบ `build/`/`dist/`/`__pycache__` เก่า → `pyinstaller
PoE-Price-Trade-Checker.spec` → **`dist/PoE-Price-Trade-Checker.exe`
(13.85 MB)** ยืนยันว่าไม่ใช่ build ค้าง (stale) โดยแกะ PYZ ข้างใน exe จริง
(`PyInstaller.archive.readers.CArchiveReader`/`ZlibArchiveReader`, วิธีเดียว
กับที่เจอปัญหานี้มาก่อนเมื่อ 2026-07-17) ยืนยัน `resolve_real_styles`/
`_apply_max_count`/`min_divine_pct` อยู่ใน `filter_gen` module จริงในไฟล์ exe,
`emit_currency_section`/"Unique fallback" ไม่เหลือแล้ว, และ version const
ในไฟล์ = `"0.6.1"` ตรงกับที่บั๊ม — ไม่มี process เก่าค้างอยู่ก่อน build
(เช็คด้วย `tasklist` แล้ว ไม่ต้อง kill)

---

## 2026-07-25 — Diagnostic: ทำไม Plan A (anchor sound) ถึงไม่พอ

**บริบท:** user รัน `.py` เวอร์ชันล่าสุดตรงๆ (ตัดประเด็น exe เก่า) แล้วรายงานว่า
เสียง/สี/ความเด่นของไอเทมมีราคายังไม่ตรงของจริง แม้ merge_currency_into_base
(Plan B ของ currency, entry ก่อนหน้า) จะ implement + verify ด้วย diff จริงแล้ว
ก่อนเดินหน้าต่อ ให้รัน diagnostic จริงเทียบ Plan A (anchor sound inheritance)
กับ block จริงแบบไม่มีเงื่อนไข เพื่อบันทึกว่า Plan A พลาดตรงไหนกันแน่

**วิธีตรวจ:** ดึง NeverSink PoE2 filter จริง (tag 0.10.3, semi-strict) +
`apply_base_filter_sounds` resolve เสียงแบบ Plan A แล้ว print
`_style_lines()` (สิ่งที่ Plan A จะ emit จริงถ้าไม่ใช้ Plan B) เทียบกับ
`_find_anchor_block` แกะ block จริงของ anchor แต่ละ tier แบบเต็ม (border/text/
background/font/beam/icon/sound) ไม่ใช่แค่เสียง

**ผลลัพธ์ (สรุปเป็นตาราง):**

| Tier | Anchor | Plan A (hardcode) | ของจริงจากไฟล์ |
|---|---|---|---|
| S | Divine Orb | border/text แดง `255 0 0`, bg ขาว, size 45, beam Red, icon `0 Red Star` | ตรงเป๊ะ (ตัวนี้ตัวเดียวที่ hardcode ไว้ตรงบังเอิญ) |
| A | Exalted Orb | border/text ส้ม `255 170 0`, bg ดำ, size 45, beam Yellow, icon `1 Yellow Circle` | text/border **ดำ**, bg `245 139 87` (ส้มอมชมพู), size **42**, beam **White**, icon เหมือนกัน |
| B | Chaos Orb | border/text ฟ้า `0 200 255`, bg ดำ, size 40, ไม่มี beam, icon `2 Blue Circle` | text/border **ดำ**, bg `245 105 90` (แดงอมส้ม), size **42**, beam **Yellow**, icon `1 Yellow Circle` (คนละอัน) |
| C | Orb of Augmentation | border เทา `150 150 150`, text เทาอ่อน `200 200 200`, bg ดำ, size 35 | text/border สีแทน `220 175 132`, **ไม่มี background override เลย**, size 38 |

**สรุป:** Plan A (`apply_base_filter_sounds`) สืบทอดแค่ "ค่าเสียง" จาก
NeverSink จริง — border/text/background/beam/icon ทั้งหมดเป็นค่า hardcode ของ
เราเองที่ไม่เคยเทียบกับไฟล์จริงเลยนอกจาก tier S ที่บังเอิญตรง A/B/C ผิดแทบทุก
แกน (สีตรงข้ามกันเลยด้วยซ้ำ — เราใช้ดำ NeverSink ใช้ขาว/ดำสลับกัน, ไอคอน B ผิด
เป็นคนละแบบ) เป็นสาเหตุตรงของอาการ "สีผิด" ที่ user รายงาน — **แต่ยังไม่ใช่
สาเหตุทั้งหมด**

**เจอเพิ่มระหว่างตรวจ (นอกขอบเขต task 1 เดิม แต่กระทบโดยตรง):**
`filter_output.write_filter()` เขียน `generated_section` (dim currency + our
own unique blocks) **ก่อน** `base_text` เสมอ — เพราะ filter เป็น
first-match-wins บรรทัด `Show # Unique fallback` (เงื่อนไขแค่
`Rarity == Unique` ไม่มี BaseType เลย) ที่เราเองสร้าง จะ**ตัดหน้า unique ทุก
ชิ้นในเกม** ก่อนที่ block จริงของ NeverSink (ที่แยกละเอียดมาก — T1/T2 by name,
`TwiceCorrupted`→ม่วง beam, `HasVaalUniqueMod`→ม่วง beam, ring มีซ็อกเก็ต→ดาว
เหลือง ฯลฯ ยืนยันจากไฟล์จริงว่ามีจริง) จะได้ทำงานเลย — ตรวจแล้วว่า block พวกนี้
เป็น dead code ทั้งหมดตอนนี้ ถูกแทนด้วยกรอบทองแดงเรียบๆ ของเราเอง **นี่น่าจะ
เป็นสาเหตุหลักของ "ความเด่นผิดทั้งชุด" มากกว่าสีของ currency เสียอีก** เพราะ
กระทบ unique ทุกชิ้นไม่ว่าจะอยู่ใน tier ราคาที่เรารู้จักหรือไม่

**ไฟล์ที่แตะ:** ไม่มี (diagnostic only, สคริปต์ชั่วคราวรันนอก repo) — ผลจะถูก
ใช้เป็นหลักฐานสำหรับงานถัดไป (Plan B เต็มรูปแบบ + แก้ ordering bug)

---

## 2026-07-24 (ต่อ) — Filter Generator: Plan B — merge currency เข้า NeverSink base โดยตรง

**สาเหตุ:** user ทดสอบในเกมแล้วเสียงยังไม่ตรงของจริงแม้แก้ anchor sound
inheritance (turn ก่อนหน้า) แล้ว — สาเหตุจริงคือสถาปัตยกรรมเดิม copy แค่
"ค่าเสียง" จาก NeverSink มาใส่ rule ของเราเอง (Show block ใหม่ที่เรา emit เอง)
ยังทำให้ item ไม่ได้อยู่ใต้ rule ตัวจริงของ NeverSink (style/sound/เงื่อนไข
อื่นๆ ต้นฉบับ) เลย — ต่อให้ copy เสียงถูกก็ยังมีความเสี่ยง drift จากของจริง

**เปลี่ยนสถาปัตยกรรม (Plan B) ตามที่ user สั่ง:** เลิก emit currency Show
block ของเราเองทั้งหมด เปลี่ยนเป็นแก้ base filter ของ NeverSink **in-place**
แทน — ย้ายชื่อ BaseType ของแต่ละ currency item เข้าไปอยู่ใน block ของ
NeverSink เองตรงๆ ตาม tier ที่ hub คำนวณได้ (uniques + dim-ของถูก ยังใช้วิธี
generated section เดิม ไม่กระทบ)

- `filter_gen.py`: เพิ่ม `_Block`/`_parse_blocks`/`_find_anchor_block` —
  refactor กลไก resolve anchor block ให้ `_find_anchor_sound` (จาก turn ก่อน)
  กับฟีเจอร์ใหม่ใช้ตัวเดียวกัน ("representative block" ของแต่ละ tier ต้อง
  หมายถึงสิ่งเดียวกันทุกที่ ตามที่ user ระบุ)
- `anchors` เพิ่ม tier "C" = "Orb of Augmentation" (verified จริงว่าอยู่ใน
  block ต่ำสุดของ NeverSink — font เล็ก สีจาง ไม่มีเสียง — เลือกเป็น anchor
  ตัวเดียวกับ S/A/B แทนที่จะ heuristic เดา "block จางสุด" จากสี ซึ่งเสี่ยง
  ผิดพลาดกว่ามาก ยืนยันจากไฟล์จริงว่า block ที่ไม่มี BaseType condition เลย
  (catch-all) จริงๆ แล้วเป็น "unknown item" warning สีสด ไม่ใช่ tier ต่ำ —
  ถ้าใช้ตัวนั้นจะทำให้ของถูกเด้งเสียง/สีฉูดฉาดผิดทาง)
- `merge_currency_into_base()`: สำหรับแต่ละ item ใน currency_tiers — ลบชื่อ
  ออกจาก BaseType list ของทุก block **ที่อยู่ก่อนหน้า target block ในไฟล์**
  (ไม่ใช่ block ที่ตามหลัง เพราะ first-match-wins ทำให้ block ทีหลังเป็น
  dead code อยู่แล้วโดยธรรมชาติ ไม่ต้องไปแตะ) แล้วเพิ่มชื่อเข้า BaseType list
  ของ target block ถ้ายังไม่มี แก้เฉพาะบรรทัด BaseType เท่านั้น ไม่แตะ
  style/sound/เงื่อนไขอื่นเลย — ถ้า anchor ของ S/A/B/C ตัวไหน resolve ไม่ได้
  (block หาไม่เจอ) fallback กลับไปใช้วิธี emit ของเราเองแบบเดิมทั้งหมด (กัน
  สถานะครึ่งๆ กลางๆ ที่บาง tier ใช้ base บาง tier ใช้ของเราเอง)
- `emit_dim_section()` แยกออกจาก `emit_currency_section()` — ส่วน dim/ของถูก
  emit ได้ทั้งสองโหมด (surgery/fallback) โดยไม่ต้อง duplicate โค้ด
- `build_filter()`: orchestrator ตัวใหม่ — ตัดสินใจ surgery vs fallback แล้ว
  คืน `(generated_section, merged_base_text, applied)` ผลข้างเคียงสำคัญ: โหมด
  surgery แล้ว **sound_map ที่ user ตั้งเองใน UI ไม่มีผลกับ currency อีกต่อ
  ไป** (เพราะห้ามแตะ sound ของ block ใดๆ ตาม spec ข้อ 4) — ยังมีผลกับ
  uniques เหมือนเดิม (unique section ไม่เกี่ยวกับ surgery เลย)
- `app.py`: `_do_generate_filter` เปลี่ยนมาเรียก `build_filter()` แทน
  `generate_section()` ตรงๆ, log แจ้ง user ว่า merge สำเร็จหรือ fallback

**ยืนยันกับไฟล์ PoE2 จริง (semi-strict, tag 0.10.3):** `applied=True`,
เปลี่ยน 21 บรรทัดทั้งหมดเป็นบรรทัด `BaseType` ล้วน (ไม่มีบรรทัดอื่นถูกแตะเลย
— เช็ค diff เต็มไฟล์แล้ว), จำนวนบรรทัดทั้งไฟล์เท่าเดิม (ไม่มีการแทรก/ลบ
บรรทัด), section ที่ generate เองไม่มี currency Show block ของเราเองอีกแล้ว
(มีแต่ uniques + dim bucket)

**Tests:** +19 เคสใหม่ครอบ `merge_currency_into_base`/`build_filter` — ย้าย
tier ขึ้น/ลง (ใช้ fixture ที่จำลอง block order จริงของ NeverSink คือ S,B,A,C
ไม่เรียงตาม rank เพื่อให้ทดสอบ cleanup จริงๆ ไม่ใช่ false positive จาก
fixture ที่เรียงตรงกับ rank พอดี — เจอบั๊กใน test เองระหว่างเขียน เพราะ
fixture แรกที่เขียนเรียง S,A,B,C ตรงเป๊ะทำให้ "ย้ายขึ้น" กลายเป็น backward-
position move ที่ไม่ต้อง cleanup จริง ไม่ได้ทดสอบอะไรเลย), item ใหม่ไม่มีใน
base, item ที่อยู่ถูกที่แล้วต้อง byte-identical ทุก bit, diff เช็คว่าเปลี่ยน
เฉพาะบรรทัด BaseType, fallback เมื่อ anchor resolve ไม่ได้, position-based
(ไม่ใช่ rank-based) removal ตาม quirk ของไฟล์จริง — รวม 193/193 passed

---

## 2026-07-24 — เพิ่ม Economy Filter Generator (v0.6.0)

**ฟีเจอร์ใหม่:** generate loot filter จาก NeverSink (โครงสร้าง/rare gear) +
poe-data-hub (ราคาสด currency/fragments/essences/div cards/uniques ติดสีตาม
tier) + เสียง alert ที่ผู้ใช้ตั้งเอง เขียนไปที่
`Documents\My Games\Path of Exile(2)\poe-checker.filter` พร้อม auto-regen เมื่อ
ราคาเปลี่ยน tier จริง โมดูลใหม่ทั้งหมด — ไม่แตะ pipeline ราคา F4/F5 เดิมเลย
(`filter_gen.py`, `neversink_source.py`, `filter_output.py`, `filter_window.py`).

**สิ่งที่ต่างจาก spec/`poe_filter_gen.py` ต้นแบบ หลังเช็คของจริง (ไม่ใช่เดา):**

1. `PriceRepository`/`PriceEntry` ทิ้ง field `base` (จำเป็นสำหรับ unique tier
   by basetype) และ flatten currency[]+items[] รวมกัน — filter generator ดึง
   hub JSON ดิบเองผ่าน `hub_client.get_prices()` ตรงๆ **ไม่ผ่าน**
   `PriceRepository` เลย ไม่แตะ `repository.py`/`models.py`/`hub_client.py`

2. category taxonomy จริงของ hub ใหญ่/ไม่แน่นอนกว่าที่ spec เขียนไว้มาก
   (poe2 currency[] มี 16 category label, poe1 มี 10 ต่างกัน) — เลยไม่ hardcode
   allowlist แต่ tier ทุก entry ใน `currency[]` เหมือนกันหมดแทน (generalize
   จาก spec ไม่ใช่ตัดขอบเขต) ยกเว้น `items[]` ที่มี non-unique เจือปนเยอะ
   (poe1 `BaseType` category เดียวมี 7500+ entries) — เอาเฉพาะ category ที่
   ขึ้นต้นด้วย "Unique" มาทำ unique-by-basetype เท่านั้น

3. **exclude `UncutGem`/`LineageGem`/`SkillGem` ออกจาก generated section**
   (ตาม user สั่งหลังรีวิว) — hub เก็บชื่อ gem แบบผูก level ไว้ในตัว
   ("Uncut Skill Gem (Level 20)" vs "...(Level 1)") ซึ่งเป็นชื่อสำหรับตั้งราคา
   ของ poe.ninja ไม่ใช่ BaseType จริงในเกม (BaseType จริงคือ "Uncut Skill Gem"
   เฉยๆ level เป็นคนละ filter condition คือ GemLevel ที่ generator นี้ไม่ได้
   ทำ) — ถ้าไม่ exclude จะได้ `BaseType ==` ที่ไม่ match ของจริงเลย แถม gem
   level ต่ำๆ (แทบไม่มีค่า) จะติด tier สูงไปด้วยเพราะ dedupe by max-value
   ข้าม level เดียวกัน → เสียง tier-S ดังทุก uncut gem ตกพื้นต้นลีก ปล่อยให้
   NeverSink filter เดิมจัดการ gem ไปแทน

4. NeverSink GitHub release ไม่มี asset แนบเลย (`assets: []` ทั้งสอง repo) —
   ไฟล์ `.filter` อยู่ในตัว repo ที่ release tag เอง (`raw.githubusercontent.com`)
   ยืนยัน filename จริง 2 เกม/7 strictness level ตรงกับที่ spec ระบุ (0-SOFT ถึง
   6-UBER-PLUS-STRICT)

5. filter จริงของ NeverSink (โหลดมาเช็คจริง ไม่ใช่ poe_filter_gen.py เดา) ไม่มี
   `Class` ที่ตรงกับ hub category เลย (Fragment/Rune/Omen ไม่มี Class ของตัวเอง)
   — currency-type rule ใช้ `BaseType` ล้วนไม่มี `Class` เงื่อนไข generated
   section เลยตัด `Class` ทิ้งไปด้วย (ง่ายกว่าต้นฉบับ ไม่ต้องรู้ชื่อ Class ต่อเกม)

**auto-regen:** poll ทุก 15 นาทีผ่าน `root.after` แต่ callback เองไม่ทำ network
call เลย (user ท้วงหลังรีวิว — เช็ค signature ต้อง fetch hub ก่อน ถ้ารันตรงบน
Tk thread UI จะค้างทุก 15 นาที) — แค่ spawn daemon thread แล้ว thread เป็นคน
reschedule tick ถัดไปเองผ่าน `after_idle` หลังทำงานเสร็จ กัน poll ซ้อนกันตอน
fetch ค้าง

**ยืนยันจริง:** รัน generate flow เต็ม (`neversink_source.fetch_base_filter` +
`hub_client.get_prices` + `filter_gen.generate_section` +
`filter_output.write_filter`) กับ live hub/GitHub จริงลง scratch dir — ได้
`poe-checker.filter` 274KB ตรวจแล้วว่า currency section ใช้ `BaseType ==` ไม่มี
`Class`, gem category ไม่หลุดเข้า generated section (เจอ "Uncut Skill Gem" แค่
ในส่วน base filter ของ NeverSink เอง), unique section มี `Rarity == Unique` +
fallback block ครบ, base filter ต่อท้ายถูกต้อง

**Tests:** 169/169 passed (เพิ่ม 45 เคสใหม่ — `test_filter_gen.py`,
`test_neversink_source.py`, `test_filter_output.py`)

**แก้เพิ่ม (ต่อวันเดียวกัน):** user ทดสอบในเกมจริงแล้วบอกเสียง Divine Orb drop
เบาไป — เปลี่ยน default sound ของ tier S/A/B (currency) จาก hardcoded
`PlayAlertSound` เดิม ("6 300"/"1 300"/ไม่มี) มาเป็น **สืบทอดจาก base filter
ของ NeverSink เอง** แทน: parse base filter ที่โหลดมาแล้ว (`filter_gen.py`
เพิ่ม `apply_base_filter_sounds()` + block parser `_iter_filter_blocks()`)
หา anchor item ต่อ tier (S=Divine Orb, A=Exalted Orb, B=Chaos Orb, ปรับได้ผ่าน
`rules["anchors"]` ใน `filter_gen_rules.json`) แล้วดึง
`PlayAlertSound`/`CustomAlertSound` + volume จาก**บล็อกแรกที่ match ชื่อนั้น**
(เคารพ first-match-wins แบบ filter จริง — ถ้าบล็อกแรกที่ match เป็น Hide ถือว่า
ไม่เจอ เพราะไอเทมนั้นจะไม่มีเสียงจริงในเกมอยู่แล้ว) parse ไม่เจอ (anchor หาย/
อยู่ใน Hide/บล็อก Show ไม่มีบรรทัดเสียงเลย/ไม่มี base filter ให้ parse) →
fallback กลับไปใช้ค่าเดิมใน rules file + log warning เสียง custom ที่ผู้ใช้ตั้ง
เองใน UI (`sound_map`) ยัง override ทับทุกกรณีเหมือนเดิม (ไม่กระทบ)
ยืนยันกับ NeverSink PoE2 filter จริง (tag 0.10.3): S→"6 300" (เท่าเดิม),
A→"2 300", B→"2 300" (ทั้งคู่ต่างจาก default เดิม) ไม่มี anchor ไหน parse
ไม่เจอ Tests: +11 เคสใน `test_filter_gen.py` ครอบ parse เจอ (PlayAlertSound/
CustomAlertSound), ไม่เจอเลย, เจอแต่ใน Hide, เจอ Show แต่ไม่มีบรรทัดเสียง,
ไม่มี base filter, tier C ไม่ถูกแตะ, ไม่ mutate input, anchors override, และ
sound_map ยัง override เสียงที่สืบทอดมาได้ — รวม 180/180 passed

**แก้เพิ่มอีกรอบ:** user สงสัยว่าเสียงที่ดึงมาไม่ตรงของจริง เพราะ
`_find_anchor_sound` เดิมหยิบ "บล็อกแรกที่ BaseType ตรง" โดยไม่ดูเงื่อนไขอื่น
— ถ้า block แรกมี narrowing condition (StackSize >= n ที่ n>1, AreaLevel,
ItemLevel, Sockets, Quality ฯลฯ) ไอเทมเม็ดเดียวดรอปจริงจะไม่เข้าเงื่อนไขนั้น
เลย ทำให้ดึงเสียงผิด block เพิ่ม `_block_matches_plain_single_item()` —
whitelist เงื่อนไข Class/BaseType/Rarity (+ StackSize เฉพาะกรณีที่ไอเทมเม็ด
เดียวยังผ่าน เช่น `<= 1`) เงื่อนไขอื่นที่ไม่รู้จักถือเป็น narrowing หมด (กัน
false positive ดีกว่า blacklist เฉพาะที่คิดออก) `_find_anchor_sound` ข้าม
(ไม่ใช่หยุด) block ที่ narrowing แล้วไล่หา block ถัดไปในลำดับไฟล์เดิมต่อ

**ตรวจกับไฟล์ PoE2 จริงอีกรอบ (ครบทั้ง 7 strictness level):** resolve ได้
S=6/300, A=2/300, B=2/300 **เหมือนเดิมทุกระดับ** — เช็คบล็อกจริงของ Divine/
Exalted/Chaos Orb ในไฟล์ (Semi-Strict) แล้วพบว่ามีแค่ `Class`+`BaseType` ไม่มี
narrowing condition นำหน้าอยู่แล้วในทุกกรณีนี้ กล่าวคือ **fix นี้ป้องกันเคส
ที่ user สงสัยไว้ได้จริง (ยืนยันด้วย synthetic test 3 เคสใหม่) แต่ไม่ใช่สาเหตุ
ของความคลาดเคลื่อนที่เจอจริงในเกม** — เสียงที่ดึงมาสำหรับ 3 anchor นี้ถูกต้อง
ตรงกับ block ปกติอยู่แล้วทั้งก่อนและหลัง fix ถ้า user ยังได้ยินเสียงไม่ตรง
สาเหตุน่าจะอยู่ที่อื่น (เช่น sound id ในเกมจริงกับที่ควรจะเป็นตามไฟล์ filter
ไม่ตรงกัน หรือ path/cache เก่าที่ยังไม่ regenerate) — รอ user ทดสอบซ้ำแล้ว
รายงานเพิ่ม Tests: +3 เคสใหม่ (StackSize>=n ข้าม, AreaLevel ข้าม, StackSize<=1
ไม่ข้าม) รวม 183/183 passed

---

## 2026-07-17 (ต่อ) — แก้ P/S = 0/n ทุกชิ้นบน PoE1 (v0.5.1)

**อาการ:** ทดสอบจริงหลัง v0.5.0 — PoE2 นับ P/S ถูกปกติ, PoE1 ขึ้น `0/n`
ทุกชิ้นไม่เว้น สมมติฐานแรกคือ `mod_meta_poe1.json` ที่เพิ่ง build ใหม่มีปัญหา

**ไล่ตามที่ user สั่ง (เช็คจริง ไม่เดา) แล้วพบว่าสมมติฐานนั้นผิด:**
1. เทียบโครง `mod_meta_poe1.json` กับ `mod_meta_poe2.json` — เหมือนกันเป๊ะ
2. lookup mod ยอดฮิต PoE1 ผ่าน real code path — เจอปกติ (เช็คไปแล้วตอน build
   เฟสก่อนหน้า ยืนยันซ้ำ)
3. **`prefix_count`/`suffix_count`/ตัวอักษร P/S ไม่ได้อ่านจาก mod_meta.json
   เลย** — `item_parser.py` นับจาก header `{ Prefix Modifier ... }` /
   `{ Suffix Modifier ... }` ใน clipboard text ล้วนๆ ไม่เกี่ยวกับ RePoE data
   เลย ดังนั้นถ้าไฟล์ meta พังจริง PoE2 ต้องพังแบบเดียวกันด้วย แต่ไม่พัง
4. ขอ raw clipboard จริงจาก user (`debug_logs/last_raw_item.txt`, rare
   "Kraken Grip" Eelskin Gloves) — **ไม่มี header `{ ... Modifier }` เลย
   สักบรรทัด** เทียบกับ PoE2 ที่มีครบ — ยืนยันกับ user ต่อว่า PoE1 ไม่มี
   ตัวเลือก "Advanced Mod Description" ให้เปิดด้วยซ้ำ (ไม่ใช่แค่ setting ปิด)
   → client บางตัวไม่ส่งข้อมูลนี้มาทาง clipboard เลยเป็นเรื่องปกติ ไม่ใช่บั๊ก
   ของเรา แต่ต้องรองรับ

**สาเหตุจริง:** `item_parser.py` คำนวณ `prefix_count`/`suffix_count`/
`m.affix`/`m.tier` จาก header เท่านั้น ไม่มี fallback path ไหนเติมให้เลยตอน
clipboard ไม่มี header — เจอ 0 เสมอตรงกับอาการเป๊ะ (ไม่เกี่ยวกับ
`mod_meta_poe1.json` ตามที่สงสัยไว้ตอนแรก เพราะงั้น**ไม่ได้แก้ที่ build
script** ตามที่ user สั่งไว้เดิม — เปลี่ยนแผนหลังเจอหลักฐานจริงขัดกับ
สมมติฐาน)

**แก้:**
- `models.py`: เพิ่ม `ParsedItem.mods_have_headers: bool` — บอก caller ว่า
  header parsing เชื่อถือได้ไหม
- `item_parser.py`: fallback path (ตอนไม่มี header) เดิมมีบั๊กอยู่แล้วสองจุด
  ที่ไม่เคยโดนทดสอบมาก่อน (เจอระหว่างแก้นี้): (1) implicit ที่ต่อท้ายด้วย
  "(implicit)" เฉยๆ โดนนับเป็น explicit ผิด — เพิ่ม `_IMPLICIT_LINE` แยกออก
  เหมือน `_RUNE_LINE` เดิม (2) mod ทุกตัวใน fallback ใช้ `group=-1` ร่วมกัน
  หมด ทำให้ `MetaDB.annotate()` เอาไปรวมเป็น "hybrid mod" ก้อนเดียวผิดๆ ทั้ง
  item — แก้เป็น group ของใครของมัน
- `meta_db.py`: `MetaDB.infer_affixes(item)` ใหม่ — จับคู่ข้อความ mod กับ
  RePoE family list ของ base นั้น (กลไกเดียวกับ `tier_range()`) อ่าน
  prefix/suffix ตรงจาก field `"gen"` ของ RePoE เอง (ข้อมูลจริง ไม่ใช่เดา)
  แล้ว mutate `item.mods[].affix` + คำนวณ `prefix_count`/`suffix_count`
  ใหม่ — พลาดเฉพาะ mod แบบ hybrid 2 บรรทัดจริงๆ ที่ไม่มี header บอกว่าเป็น
  มอดเดียวกัน (graceful miss เหมือนฟีเจอร์อื่นในไฟล์นี้)
- `app.py`: เรียก `infer_affixes()` หลัง parse ทันทีเมื่อ
  `item.mods_have_headers is False`

**เพิ่มตามข้อ 5 เดิม (validation กัน build กลวงในอนาคต แม้ไม่ใช่สาเหตุรอบนี้):**
`tools/build_mod_meta.py` เพิ่ม `_validate()` เช็คหลัง build ก่อนเขียนไฟล์ —
bases/families ต้องไม่น้อยผิดปกติ, ต้องมีทั้ง prefix และ suffix (ไม่ใช่ฝั่ง
เดียวหายหมด — เคสแบบ domain-crossing bug ที่เจอไปแล้ว), tag coverage ต้อง
>= 30% — fail ทันที (`sys.exit(1)`) ถ้าไม่ผ่าน ไม่เขียนไฟล์ออกมาให้กลวง

**Tests:** 124/124 passed (`test_item_parser.py` เพิ่ม 7 เคสใหม่ — ใช้ raw
text จริงจาก user เป็น fixture ตรงๆ, `test_meta_db.py` เพิ่ม 5 เคสสำหรับ
`infer_affixes`)

**ไฟล์ที่แก้:** `models.py`, `item_parser.py`, `meta_db.py`, `app.py`,
`tools/build_mod_meta.py`

**Build:** rebuild exe แล้ว (v0.5.1) เปิดทิ้งไว้ให้ user ทดสอบซ้ำ — รอผล F5
รอบใหม่กับ rare item เดิม

**Deploy incident ระหว่างทดสอบ (2026-07-17 คืน):** รอบแรกที่ user ทดสอบ v0.5.1
ยัง `0/n` เหมือนเดิม — สงสัย `mod_meta_poe1.json` อีกรอบ (ตามที่ user ไล่ให้
เช็คข้อ 3 "exe ที่รันอยู่คือ build จริงไหม") สืบแล้วพบว่า **exe ที่ user
ทดสอบเป็น build เก่า** — ตอนสงสัยว่า PyInstaller build อาจ stale เลยสั่ง
`Stop-Process` เพื่อ `--clean` rebuild ใหม่ แต่ลืม relaunch โปรแกรมกลับ ทำให้
user ทดสอบซ้ำกับ process ที่ค้างจาก build ก่อนหน้า — ไม่ใช่บั๊กโค้ด เป็น
ความผิดพลาดตอน deploy ของผมเอง

ระหว่างไล่ก็เจอว่าการเช็ค "exe มีโค้ดใหม่ไหม" ด้วยการ grep string ตรงๆ ในไฟล์
exe **ใช้ไม่ได้** (โค้ด python ถูก zlib-compress อยู่ใน PYZ archive ข้างใน)
ให้ผลลบลวงทั้งคู่ — ต้องแกะ `PyInstaller.archive.readers.CArchiveReader` +
เดิน `co_consts`/`co_names` แบบ recursive (รวม tuple ของ kwarg names) ถึงจะ
เชื่อถือได้จริงว่าโค้ดไหนอยู่ใน exe จริง — ใช้วิธีนี้ยืนยันได้ว่า build ล่าสุด
มี `infer_affixes`/`mods_have_headers` ครบก่อนให้ user ทดสอบรอบใหม่

เพิ่ม diagnostic ชั่วคราว (`debug_logs/infer_debug.txt`, เขียนทุก F5 ที่ไม่มี
header — base_type, prefix/suffix count, affix ต่อ mod) ตามที่ user สั่ง
เพื่อยืนยันแบบเห็นข้อมูลจริงไม่ใช่เดา — **ทดสอบผ่าน** (`Cobalt Jewel`:
Prefix 2/2 · Suffix 2/2 ถูกต้อง) ลบ diagnostic ทิ้งหลังยืนยันแล้วตามที่บอกไว้
ตอนใส่ว่าเป็นของชั่วคราว

**สรุปกับ Phase 3 เดิม:** เฟส 3 (PoE2-parity) + hotfix P/S นี้ ปิดงานสมบูรณ์
ทั้งคู่ — F5 กับ rare/jewel PoE1 ใช้งานได้ครบทุกฟีเจอร์ (สี, tier, ▲▼, P/S)
ตรวจสอบจริงในเกมแล้ว

---

## 2026-07-17 — Mod Badge เฟส 3: เปิดให้ PoE1 เท่า PoE2 (v0.5.0)

**เหตุผล:** ลีกใหม่ PoE1 เปิด 2026-07-25 ต้องพร้อมก่อนนั้น — ปลดเงื่อนไข
PoE2-only ที่ค้างจากเฟส 1/2 ออกทั้งหมด ให้ badge/roll indicator/สีเขียว/P/S
ทำงานกับ PoE1 เหมือน PoE2 ทุกจุด

**เช็คก่อนเริ่ม (ตามที่สั่ง — ไม่เดา):**
- `poe1/meta/latest.json` **live บน hub แล้วตั้งแต่ 2026-07-15** (ยืนยันจาก
  `D:\Projects\Poe_Hub\SPEC.md` section 8.2 + curl จริง 2026-07-17 —
  `generated_at` ล่าสุด 2026-07-16T20:44:28Z) ไม่ใช่ "ยังไม่มี" ตามที่สงสัยไว้
  ตอนสั่งงาน — `hub_client.get_meta(game)` เป็น generic ต่อเกมอยู่แล้วตั้งแต่
  เฟส 1 ไม่ต้องแก้ฝั่งนั้นเลย
- stat_id resolver (`mod_db.py`) เป็น per-`GameProfile` อยู่แล้ว —
  `POE1_PROFILE.trade_stats_url` ชี้ `trade/data/stats` (ของ PoE1) ถูกต้อง
  ตั้งแต่แรก, `self._mod_db` ถูก recreate ตอนสลับเกมใน
  `_on_game_version_changed()` อยู่แล้ว — ข้อ 2 ที่สั่งไว้ผ่านอยู่แล้วไม่ต้องแก้
- tier/tag data: ดึง `repoe-fork/poe1` (org เดียวกับที่ใช้อยู่, schema ตรงกัน
  100%) มาลอง build — **tag coverage 93.5%** (2301/2462 families) สูงกว่า
  PoE2 (87.2%, 1952/2239) จริงตามที่ user คาดไว้

**สิ่งที่แก้จริง:**
1. `app.py`: ลบเงื่อนไข `game_version == "poe2"` ออก 2 จุด (`_mod_badge.load()`,
   `_compute_mod_extras`) — เหลือแค่ `item.rarity != Rarity.RARE` gate
   `_get_meta_db()` แก้เป็น recreate `MetaDB` ใหม่เมื่อ game_version เปลี่ยน
   (เดิม cache ตัวเดียวตลอดชีวิตโปรแกรม)
2. `mod_badge.py`: `load()`/`affix_cap()` รับ `game` param (default "poe2"
   กัน call site เดิมพัง), cache แยกไฟล์ต่อเกม
   (`mod_badge_meta_{game}.json`) — instance เดียวใช้ร่วมกันได้ ไม่ต้อง
   recreate ตอนสลับเกม (`load(game)` re-index ทับของเดิมเอง)
3. `slot_for_item()`: port hub's `_slugify_jewel_base` เวอร์ชันเต็ม (ตัด
   cluster-size prefix + คำว่า "Jewel") แทนตัด non-alnum เฉยๆ — **แก้บั๊กเดิม
   ที่มีอยู่แล้วในทั้งสองเกม**: "Timeless Jewel" เคยได้ slug
   `jewel:timelessjewel` ซึ่งไม่ตรงกับ hub key จริง (`jewel:timeless`) เลย
   ทำให้ badge ไม่เคยติด Timeless Jewel มาตั้งแต่เฟส 1 — เจอตอนเทียบกับ
   payload จริงของทั้งสองเกม
4. `affix_cap()`: PoE1 jewel (ทุกแบบ: ปกติ/abyss/cluster) = 2/2 (4 รวม แทน
   6 ปกติ) ต่างจาก PoE2 jewel ที่ 1/1 — **RePoE ไม่มี field นี้เลย** (ช่องว่าง
   เดียวกับตอน PoE2 ที่ก็ไม่ได้มาจาก datamine) ต้องยืนยันผ่าน web search แทน
   (poewiki โดน anti-bot บล็อก 403 ตรงๆ ไม่ได้ ใช้ผลรวมจากหลายแหล่ง fan
   community แทน) — **ความเชื่อมั่นสูงแต่ไม่ 100%** ให้ user double-check ตอน
   ทดสอบจริงกับ jewel ในเกม
5. `tools/build_mod_meta.py`: เพิ่ม `--game {poe1,poe2}`, output แยกไฟล์
   `mod_meta_{game}.json`, domain allowlist ต่อเกม (PoE1 เพิ่ม
   `abyss_jewel`/`affliction_jewel` — abyss jewel 4 แบบ + cluster jewel 3
   ไซส์อยู่คนละ domain จาก jewel ปกติ ไม่งั้นหลุดจาก mod_meta ไปเงียบๆ)
6. `meta_db.py`: `MetaDB(app_dir, game_version)` แยกไฟล์ต่อเกมจริง (กัน
   base_type ชนกันข้ามเกม)

**บั๊กที่เจอระหว่างทำ (ไม่ได้อยู่ใน scope เดิม แต่กระทบทั้งสองเกม เลยแก้ไปด้วย):**
- **Domain-crossing ใน `can_spawn()`**: ตอนเพิ่ม `abyss_jewel`/
  `affliction_jewel` เข้า allowlist พบว่า mod ของ abyss jewel รั่วเข้าไปติด
  cluster jewel (เช่น "+X to Armour" ของ abyss ไปโผล่ใน cluster's mod pool)
  เพราะ base ทั้งคู่มี tag "default"/"jewel" ร่วมกัน แต่ตัวเช็คเดิมดู tag
  อย่างเดียวไม่เช็ค domain — แก้โดย key tagset เป็น `(domain, tags)` แทน
  `tags` เฉยๆ แล้วกรอง mod candidate ด้วย domain ก่อนเช็ค tag (ทำให้ PoE1
  `mod_meta_poe1.json` เล็กลงจาก 2.4MB เหลือ 0.7MB หลังแก้ — ก่อนแก้มี mod
  ปนเปื้อนเยอะมาก) ยืนยันว่า PoE2 output **ไม่เปลี่ยนเลย** (bases=1782
  tagsets=78 เท่าเดิมทั้งก่อน-หลัง) เพราะ PoE2 มีแค่ domain "item"/"misc" ที่
  ไม่ชนกันอยู่แล้ว
- **"+" prefix ไม่ถูกตัดตอน normalize hub template**: `_normalize_mod`
  (mod_db.py) แทนที่ "#"/ตัวเลขล้วนๆ แต่ไม่แตะ "+" ที่นำหน้า "#" — hub
  template บางตัวมี "+" ติด (`"+# to maximum Life"` — ยืนยันจาก payload จริง
  ของ PoE1, PoE2 มี 249 ตัวที่เป็นแบบนี้เหมือนกัน) แต่ `mod_meta_{game}.json`
  ไม่มี "+" ติดเลย (ตัดพร้อมตัวเลขตั้งแต่ `build_mod_meta.py`) ทำให้
  `tags_for_template()` ไม่เจอ tag ของ stat พวกนี้เลยแบบเงียบๆ (สีเขียว
  metacraft ไม่ติดทั้งที่ควรติด) — แก้จุดเดียวใน `mod_badge.py::_index()`
  (ตัด "+" เฉพาะตอนสร้าง `_stat_to_templates` ที่ใช้หา tag เท่านั้น ไม่แตะ
  `_template_index`/`_normalize_mod`/mod_db.py/F5 trade pipeline) ผลลัพธ์:
  tag-resolvable mod rows ของ PoE1 จาก 30.0% → 60.2% (ทดสอบผ่าน real code
  path จริง ไม่ใช่แค่ mock)

**Deploy:** build `mod_meta_poe1.json` (0.7MB, bases=972, tagsets=69) +
`mod_meta_poe2.json` (0.8MB, bases=1782, tagsets=78, เนื้อหาเหมือนเดิมเป๊ะ
แค่เปลี่ยนชื่อไฟล์) วางที่ `%LOCALAPPDATA%\PoePriceTrade\` ลบ `mod_meta.json`
เดิม (ชื่อเก่าไม่ใช้แล้ว)

**ไฟล์ที่แก้:** `app.py`, `mod_badge.py`, `meta_db.py`, `settings.py` (ลบ
"PoE2 only" ออกจาก label), `tools/build_mod_meta.py`, `.gitignore`

**Tests:** 113/113 passed (`test_mod_badge.py` เพิ่ม ~12 เคสใหม่ — jewel slug
ทุกแบบของ PoE1, affix_cap ต่อเกม, load/cache แยกเกม, regression เคสของบั๊ก
"+" — `test_meta_db.py` เพิ่มเคส per-game file separation)

**Build:** rebuild exe แล้ว (v0.5.0) เปิดทิ้งไว้ให้ user ทดสอบ — **ยังไม่ได้
ทดสอบ F5 จริงกับ PoE1 rare gear/jewel ในเกม (รอ user, กำลังเล่น event
Ancestors อยู่พอดี)**

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
→ slot resolve เป็น "jewel:emerald" ถูกต้อง, affix_cap=1 ถูกต้อง

**ทดสอบจริงในเกม (2026-07-17):** user กด F5 กับ rare gear และ jewel จริงใน
PoE2 ผ่าน `dist/PoE-Price-Trade-Checker.exe` (build ตรงกับ commit `3a93e04`)
— user ยืนยันผ่านทั้งหมด (จุดสี, ลูกศร ▲/▼, P/S marker, บรรทัดสรุป
Prefix/Suffix) เฟส 2 ปิดงานสมบูรณ์

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
