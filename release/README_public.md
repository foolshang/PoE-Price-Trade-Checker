# PoE Filter Generator (PoE1 & PoE2)

เครื่องมือสร้าง **loot filter** สำหรับ Path of Exile 1 และ 2 แบบ standalone —
ไฟล์เดียว ไม่ต้องติดตั้ง ไม่ต้องลง Python

รองรับทั้ง **PoE1** และ **PoE2** สลับได้ในหน้าต่างเดียว มี 2 แท็บ:
**NeverSink** (ใช้ tier ของ NeverSink ตรงๆ) และ **Whitelist** (โชว์เฉพาะที่คุณเลือก ซ่อนที่เหลือ)

---

## โหลด

👉 **[ดาวน์โหลดตัวล่าสุด (PoE-Filter-Generator.exe)](https://github.com/foolshang/PoE-Filter-Generator/releases/latest/download/PoE-Filter-Generator.exe)**

หรือเข้าหน้า [Releases](https://github.com/foolshang/PoE-Filter-Generator/releases) เพื่อเลือกเวอร์ชัน

> **Windows เท่านั้น** · ไฟล์เดียวจบ ดับเบิลคลิกรันได้เลย

### ใช้บนเว็บ (ไม่ต้องโหลดอะไร)

👉 **[เปิดเวอร์ชันเว็บ](https://foolshang.github.io/PoE-Filter-Generator/)** — ฟังก์ชันเดียวกับโปรแกรม (แท็บ NeverSink และ Whitelist)

- **Chrome / Edge:** เลือกโฟลเดอร์เกมได้ โปรแกรมเขียนไฟล์ `.filter` และไฟล์เสียงลงโฟลเดอร์ให้เลย
  ครั้งแรกต้องเลือกโฟลเดอร์ filter ของแต่ละภาคเองหนึ่งครั้ง
  (PoE1 = `Documents\My Games\Path of Exile` · PoE2 = `Documents\My Games\Path of Exile 2`)
- **Firefox / Safari:** เลือกโฟลเดอร์ไม่ได้ ใช้การดาวน์โหลดไฟล์แล้วนำไปวางในโฟลเดอร์เกมเอง

### ครั้งแรกที่รัน Windows อาจเตือน
ไฟล์ไม่ได้ sign ดิจิทัล → Windows SmartScreen จะขึ้น "Windows protected your PC"
กด **More info → Run anyway** ครั้งเดียว ครั้งต่อไปไม่ถามอีก

---

## ใช้ยังไง

1. เปิดโปรแกรม → เลือกภาค **PoE1 / PoE2** ด้านบน
2. เลือกแท็บ **NeverSink** หรือ **Whitelist** (อธิบายด้านล่าง) แล้วตั้งค่าที่ต้องการ
3. ตั้ง **Game folder** (เว้นว่าง = หาโฟลเดอร์เกมให้อัตโนมัติ)
4. ตั้ง **ชื่อ filter** (ค่าเริ่มต้น: แท็บ NeverSink = `poe-checker` · แท็บ Whitelist = `poe-checker-whitelist`
   ตั้งเองได้ มีหลายไฟล์ในโฟลเดอร์เดียวกันได้ไม่ทับกัน)
5. กด **Generate Now**
6. ในเกม: **Options → Game → เลือก filter แล้ว reload**

ค่าที่ตั้งจำไว้ให้เมื่อกด **Save Settings** หรือ Generate

---

## แท็บ NeverSink — ใช้ tier ของ NeverSink ตรงๆ

สร้าง filter จาก [NeverSink's Indepth Loot Filter](https://github.com/NeverSinkDev/NeverSink-Filter)
โดยไม่ใช้ราคาเลย — tier ทั้งหมดมาจากที่ NeverSink จัดไว้

- **Strictness** เลือกได้ 0–6 (Soft ถึง Uber-Plus-Strict)
- **เสียงแจ้งเตือน 6 ช่อง** — เลือกไฟล์เสียงของคุณเอง (mp3 / wav / ogg) แทนเสียงของ NeverSink
  ทีละระดับ · ปุ่ม **Clear** = กลับไปใช้เสียงของ NeverSink

  | ช่อง | ใช้กับ |
  |---|---|
  | เสียง 1 | ของระดับสูงสุด |
  | เสียง 2 | ของระดับรองลงมา |
  | เสียง 3 | ของระดับกลาง |
  | เสียง 4 | อุปกรณ์ที่ NeverSink ไฮไลต์ (Rare / Magic ที่ mod ดี, Exotic, ฐานคราฟต์, Heist), Unique ระดับรอง และของที่เหลือในหมวด |
  | เสียง 5 | แมพ / Waystone tier ต่ำ–กลาง (PoE1 รวม Heist blueprint บางแบบ) |
  | เสียง 6 | แมพ / Waystone tier สูง (PoE1 รวม Heist และ Expedition Logbook) |

  โปรแกรมก๊อปไฟล์เสียงไปไว้ในโฟลเดอร์ filter ให้ โดย **ใช้ชื่อไฟล์เดิม**
- **ของเควส (Q)** — ของเควสโชว์เสมอทั้ง 2 แท็บ · ตั้งสีและเสียงของ Q ได้ที่แท็บนี้ (ใช้ร่วมกันทั้ง 2 แท็บ)
- **Regenerate เมื่อ NeverSink อัปเดต** — ติ๊กไว้ แล้วเปิดโปรแกรมทีไรจะเช็ค NeverSink และสร้าง filter ใหม่ให้เมื่อมีเวอร์ชันใหม่
  (หรือกด **Refresh NeverSink Base** เพื่อดึงใหม่เอง)

---

## แท็บ Whitelist — โชว์เฉพาะที่เลือก ซ่อนที่เหลือทั้งหมด

ทุกอย่างอยู่ใน **tier S / A / B / C / D**
- **S / A / B / C = โชว์** — แต่ละ tier มีสไตล์ (สี ความทึบ ขนาด ไอคอน ลำแสง) เสียง และจำนวนขั้นต่ำของตัวเอง
- **D = ซ่อน**

**ค่าเริ่มต้น** มาจากการจัดอันดับของ NeverSink ระดับ 2 (Semi-Strict):
ของแพงสุดเป็น **S** ไล่ลงมาจนถึง **C** · ของที่ NeverSink ซ่อนเป็น **D** · ชื่อที่ NeverSink ไม่ได้จัดไว้เป็น **B**
แล้วคุณปรับเองได้ทีละชิ้น หรือทีละหมวด

แท็บนี้แบ่งเป็นแท็บย่อย: **[ไอเท็ม / หมวด] [Gold] [Map / Waystone] [Tablet] [Gem] [พิมพ์เอง]**
(Tablet มีเฉพาะ PoE2) · Gold / Map-Waystone / Tablet / Gem มีสไตล์และเสียงของตัวเองในแท็บย่อยของมัน · แท็บไอเท็ม/หมวดและพิมพ์เองใช้สไตล์ของ tier
สไตล์ทั้งหมดแก้ได้ในหน้าเลย ไม่เปิดหน้าต่างใหม่

### ไอเท็ม / หมวด

**วิธีใช้**
1. **เลือก tier** (S / A / B / C) ที่ต้องการ แล้วตั้ง **สไตล์และเสียง** ของ tier นั้น (อยู่ใต้ปุ่มเลือก tier)
2. เลือก **หมวด** แล้วติ๊ก/เอาติ๊กไอเท็ม — ติ๊ก = ย้ายเข้า tier ที่เลือก · เอาติ๊กออก = D (ซ่อน)
   หรือใช้ปุ่ม *ทั้งหมวด → tier นี้* / *ทั้งหมวด → D (ซ่อน)* / *รีเซ็ต*
3. กด **Generate Now**

**หมวดที่มี**
- **ไอเท็มตามชื่อ** — Currency, Fragment, Rune, Essence, Omen, Catalyst, Scarab, Fossil, Div Card ฯลฯ
  (ตามเกม) รวมถึง Runegraft, Vial, Corpse, Wombgift, Relic
- **Unique** — ตั้ง tier ต่อ unique (ผูกกับ base) หรือทั้งหมวด
- **Tablet** (PoE2)
- **Flask / Charm** (PoE1: **Flask / Tincture**) — แต่ละแถวเลือกได้:
  - **ค่าเริ่มต้น** = ตาม NeverSink
  - **ตั้งค่าเอง** = เลือก tier ให้ Normal / Magic
- **อุปกรณ์ตาม class** — แท็บ **[อาวุธ] [เกราะ] [เครื่องประดับ] [อื่นๆ]** แถวละ 1 class
  (เช่น Bows, Boots, Rings, Jewels)
  - แต่ละแถวเลือก **ค่าเริ่มต้น** (ตาม NeverSink) หรือ **ตั้งค่าเอง** (เลือก tier ให้ Normal / Magic / Rare)
  - ช่อง **ตั้งทั้งกลุ่ม** ด้านบนของแต่ละแท็บ ใช้ตั้งทุก class ในกลุ่มพร้อมกัน

> **ตั้งค่าเองแล้วมีผลกับทุกชิ้น** ของ class + rarity นั้น รวมของดีที่ NeverSink จัดไว้
> (เช่น ตั้ง Rare Boots = D → rare boots หายทั้งหมด รวมตัวที่ base หรือ mod ดี)
> Unique ไม่โดน — ไปตั้งที่หมวด Unique

**อุปกรณ์ทุกกลุ่มใช้ block ของ NeverSink (เงื่อนไข สไตล์ เสียง) เมื่อแถว class ยังเป็นค่าเริ่มต้น**
ถ้าตั้งค่าเองในอุปกรณ์ตาม class จะทับทุกชิ้นของ class + rarity นั้น กลุ่มที่ใช้ block ของ NeverSink ตามเดิม:

| กลุ่ม | เกม |
|---|---|
| เนื้อเรื่อง / เลเวลลิ่ง | ทั้งคู่ |
| Jewel (abyss / cluster / ทั่วไป / พิเศษ) | ทั้งคู่ |
| Flask / Tincture / Charm endgame | ทั้งคู่ |
| Rare ตาม ilvl | ทั้งคู่ |
| Exotic base / mod | ทั้งคู่ |
| ฐานคราฟต์ | ทั้งคู่ |
| 6-link / 5-link | PoE1 |
| Influenced | PoE1 |
| Heist (cloak / brooch / gear / tool) | PoE1 |
| Rare ที่ระบุแล้วมี mod ดี | PoE1 |
| Magic ที่ระบุแล้วมี mod ดี | PoE1 |
| Memory Strand / Gear พิเศษ | PoE1 |
| Magic / Rare ตามเลเวลโซน | PoE2 |
| เครื่องประดับ (jewellery) | PoE2 |
| Salvage (Quality / Sockets) | PoE2 |
| ของที่เกมบังคับโชว์ (AlwaysShow) | PoE2 |

**ใช้ของ NeverSink เสมอ (ไม่มีให้ตั้งในแท็บนี้):**
- **กุญแจ / ของพิเศษ** (เช่น Vault Keys, Relics, Blueprints, Contracts, Corpses, Wombgifts ตามเกม)
- **Gem ทั่วไป** (PoE1 — Gem ของ PoE2 ตั้งที่แท็บย่อย Gem)

**จำนวนขั้นต่ำ (stack)** — ตั้ง "โชว์เมื่อจำนวน ≥ N" ต่อ tier หรือต่อชิ้นได้
(ของที่ NeverSink โชว์เฉพาะตอนเป็นกอง จะใช้เกณฑ์ของ NeverSink เป็นค่าเริ่มต้น)

### แท็บย่อยอื่น
- **Gold** — ติ๊ก = โชว์เมื่อจำนวน ≥ N (น้อยกว่าซ่อน) · ไม่ติ๊ก = โชว์ตามเกม
- **Map / Waystone** — โชว์เมื่อ tier ≥ N และ rarity ≥ ที่เลือก (ไม่ติ๊ก = โชว์ตามเกม)
- **Tablet** (PoE2) — สไตล์ของ Tablet ที่ไม่ได้ตั้ง tier รายชิ้น
- **Gem** — PoE2: Uncut Skill / Spirit / Support + level ขั้นต่ำ · PoE1: พิมพ์ชื่อ gem
- **พิมพ์เอง** — พิมพ์ชื่อ base (เช่น `heavy belt`) + เลือก rarity + tier

Gold / Map-Waystone / Tablet / Gem มีสไตล์และเสียงของตัวเองในแท็บย่อยของมัน · แท็บไอเท็ม/หมวดและพิมพ์เองใช้สไตล์ของ tier

### สไตล์และเสียง
- แก้สีตัวอักษร / กรอบ / พื้นหลัง ขนาด ไอคอน ลำแสง ได้ และตั้ง **ความทึบ** ของแต่ละสี (255 = ทึบ, 0 = โปร่งใส)
- **เสียงของแท็บ Whitelist แยกจากแท็บ NeverSink** — tier S / A / B / C, Gold, Map, Tablet, Gem มีเสียงของตัวเอง
  · ใช้ร่วมกับแท็บ NeverSink แค่เสียงของเควส (Q)

### เปิด filter เก่ามาแก้
ปุ่ม **เปิด filter…** เปิดไฟล์ที่ **แท็บ Whitelist ของโปรแกรมนี้** สร้างไว้ได้
(ค่าที่ตั้งฝังอยู่ท้ายไฟล์ เป็นบรรทัด comment ที่เกมไม่สนใจ) ชื่อ filter จะตามชื่อไฟล์ที่เปิด
แก้แล้วกด Generate เพื่อเขียนทับไฟล์นั้น (โปรแกรมถามก่อนทับ)
ไฟล์จากรุ่นเก่าที่ยังไม่มีค่าฝังก็เปิดได้ — โปรแกรมอ่านกลับจาก block แล้วบอกใน Status ว่าส่วนไหนเดา
ไฟล์ที่ไม่ได้สร้างจากโปรแกรมนี้ หรือสร้างจากแท็บ NeverSink เปิดแก้ไม่ได้

---

## อัปเดตจากรุ่นเก่า

โปรแกรมแปลงค่าที่เก็บไว้ให้ครั้งเดียวตอนเปิด และแจ้งใน Status:
- **tier C เดิม (เคยแปลว่าซ่อน) → D** · S / A / B ที่ตั้งไว้คงเดิม · ของที่ไม่ได้ตั้งเองย้าย tier ตามค่าเริ่มต้นใหม่
- **เสียง S / A / B เดิม** → เสียง 1 / 2 / 3 ของแท็บ NeverSink และเสียงของ tier S / A / B ของแท็บ Whitelist
- หมวดอุปกรณ์แบบเดิมที่ถูกตัดออก → กลับไปใช้ของ NeverSink

---

## ต้องมีอะไร

- Windows 10/11
- Path of Exile 1 หรือ 2 (ติดตั้งแล้ว)
- อินเทอร์เน็ต — ดึง NeverSink filter และรายชื่อไอเท็มตอนเปิดโปรแกรม / generate **ไม่ดึงราคา**

---

## แก้ปัญหา

**Generate แล้วขึ้น error เขียนไฟล์ไม่ได้ (เช่น `[Errno 9]` / Bad file descriptor)**
สาเหตุที่พบบ่อยคือ **Windows Defender "Controlled Folder Access"** (ระบบกัน ransomware)
บล็อกไม่ให้โปรแกรมหน้าใหม่เขียนไฟล์ลงโฟลเดอร์ Documents / My Games วิธีแก้:
1. Windows Security → **Virus & threat protection** → **Ransomware protection** →
   **Controlled folder access** → **Allow an app through Controlled folder access** →
   เพิ่ม `PoE-Filter-Generator.exe`
2. หรือกด **Browse...** ที่ช่อง *Game folder override* ในโปรแกรม แล้วเลือกโฟลเดอร์
   filter ของเกมเอง (โฟลเดอร์ที่ไม่ถูกบล็อก)

> ค่าเริ่มต้นของ Windows คือ "ปิด" CFA — ส่วนใหญ่จะไม่เจอปัญหานี้ แต่ถ้าคุณเปิดไว้ ใช้วิธีด้านบน

---

## หมายเหตุ

- ต่อยอดจาก **[NeverSink Filter](https://github.com/NeverSinkDev/NeverSink-Filter)** (เครดิต NeverSink) — tier เริ่มต้นและรูปแบบ block มาจาก filter ของเขา
- โปรแกรมนี้**ไม่มีส่วนเกี่ยวข้อง**กับ Grinding Gear Games
- filter ที่สร้างจะ**เขียนทับ**ไฟล์ชื่อเดียวกันในโฟลเดอร์ filter ของเกม — ตรวจชื่อไฟล์ก่อนถ้ามี filter เดิมอยู่

---

*เป็นเครื่องมือส่วนตัวแจกให้ใช้ฟรี — เจอบั๊กหรืออยากได้อะไรเพิ่ม แจ้งได้ที่หน้า Issues*
