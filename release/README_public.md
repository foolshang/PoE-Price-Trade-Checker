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
- **เสียงแจ้งเตือน tier S / A / B** — เลือกไฟล์เสียงของคุณเอง (mp3 / wav / ogg) ปุ่ม **Clear** = กลับไปใช้เสียงของ NeverSink
  โปรแกรมก๊อปไฟล์ไปไว้ในโฟลเดอร์ filter ให้ **ใช้ชื่อไฟล์เดิม** (tier C เงียบเสมอ)
  เสียง S / A / B / Q ตั้งที่แท็บนี้ที่เดียว และใช้ร่วมกับแท็บ Whitelist
- **ของเควส (Q)** — ของเควสโชว์เสมอทั้ง 2 แท็บ — ตั้งสไตล์ Q (สี เสียง) ได้ที่แท็บนี้ (ไม่ตั้ง = ใช้สไตล์ของ NeverSink)
- **Regenerate เมื่อ NeverSink อัปเดต** — ติ๊กไว้ แล้วเปิดโปรแกรมทีไรจะเช็ค NeverSink และสร้าง filter ใหม่ให้เมื่อมีเวอร์ชันใหม่
  (หรือกด **Refresh NeverSink Base** เพื่อดึงใหม่เอง)

---

## แท็บ Whitelist — โชว์เฉพาะที่เลือก ซ่อนที่เหลือทั้งหมด

ทุกอย่างอยู่ใน **tier S / A / B / C** (C = ซ่อน) โดย **ค่าเริ่มต้นมาจาก NeverSink ระดับ 2 (Semi-Strict)**
แล้วคุณปรับเองได้ทีละชิ้น ทีละหมวด หรือทีละ block

**วิธีใช้**
1. **เลือก tier** (S / A / B) ที่ต้องการก่อน
2. ตั้ง **สไตล์ของ tier** (สี ขนาด ไอคอน ลำแสง) — ใช้ร่วมกันทุกไอเท็มใน tier นั้น
   (เสียง S / A / B ตั้งที่แท็บ NeverSink)
3. เลือก **หมวด** แล้วติ๊ก/เอาติ๊กไอเท็ม — ติ๊ก = ย้ายเข้า tier ที่เลือก เอาติ๊กออก = C (ซ่อน)
   หรือใช้ปุ่ม *ทั้งหมวด → tier นี้* / *ทั้งหมวด → C* / *รีเซ็ต* ได้
4. กด **Generate Now**

**หมวดที่มี**
- **ไอเท็มตามชื่อ** — Currency, Fragment, Rune, Essence, Omen, Catalyst, Scarab, Fossil, Div Card ฯลฯ
  (ตามเกม) รวมถึง Runegraft, Vial, Corpse, Wombgift, Relic
- **Unique** — ตั้ง tier ต่อ unique (ผูกกับ base) หรือทั้งหมวด
- **Tablet** (PoE2) · **กุญแจ/ของพิเศษ** (ตาม class)
- **อุปกรณ์** แยกเป็นหมวดย่อย (เนื้อเรื่อง/เลเวลลิ่ง, 6-link, Jewel, Flask, Rare ตาม ilvl, Exotic base, ฐานคราฟต์ ฯลฯ)
  แต่ละหมวดแสดง block ของ NeverSink ทีละ block ด้วยชื่ออ่านง่าย (เช่น "Rare แหวน ilvl ≥ 82")
  ติ๊กหรือย้าย tier ได้ทีละ block ลำดับชนะ: block ที่ตั้งเอง › ทั้งหมวด › ค่าเริ่มต้น
- **Gem ทั่วไป** (PoE1) แสดงเป็น block ตาม level / quality / โซน

**ตั้งตาม rarity** — หมวด Jewel, Flask (PoE1) และ Flask / Charm (PoE2) มีช่อง Normal / Magic / Rare
เลือก ตาม NeverSink / S / A / B / C ต่อ rarity ได้ (ชนะ block รายตัวในหมวดนั้น · Unique ไปตั้งที่หมวด Unique)
ค่าเริ่มต้น "ตาม NeverSink" ไม่เปลี่ยนอะไร · ตั้ง C = ซ่อนทุกชิ้นของ rarity นั้น รวมตัวที่ mod ดีด้วย

**ของเควส** โชว์เสมอทั้ง 2 แท็บ — ตั้งสไตล์ Q ได้ที่แท็บ NeverSink (ไม่ตั้ง = ใช้สไตล์ของ NeverSink)

**ส่วนแยก**
- **Gold** — ติ๊ก = โชว์เมื่อจำนวน ≥ N (น้อยกว่าซ่อน) · ไม่ติ๊ก = โชว์ตามเกม
- **Map / Waystone** — โชว์เมื่อ tier ≥ N และ rarity ≥ ที่เลือก (ไม่ติ๊ก = โชว์ตามเกม)
- **Tablet** (PoE2) · **Gem** (PoE2: Uncut Skill / Support / Spirit + level ขั้นต่ำ · PoE1: พิมพ์ชื่อ gem)
- **ชื่อที่พิมพ์เอง** — พิมพ์ชื่อ base (เช่น `heavy belt`) + เลือก rarity + tier

**จำนวนขั้นต่ำ (stack)** — ตั้ง "โชว์เมื่อจำนวน ≥ N" ต่อ tier หรือต่อชิ้นได้
(ของที่ NeverSink โชว์เฉพาะตอนเป็นกอง จะใช้เกณฑ์ของ NeverSink เป็นค่าเริ่มต้น)

**สไตล์** — แก้สีตัวอักษร / กรอบ / พื้นหลัง ขนาด ไอคอน ลำแสง ได้ และตั้ง **ความทึบ** ของแต่ละสี
(255 = ทึบ, 0 = โปร่งใส) · เสียงของ Gold / Map / Tablet ตั้งได้ในสไตล์ของตัวเอง · เสียง S / A / B ตั้งที่แท็บ NeverSink

**เปิด filter เก่ามาแก้** — ปุ่ม **เปิด filter…** เปิดไฟล์ที่ **แท็บ Whitelist ของโปรแกรมนี้** สร้างไว้ได้
(ค่าที่ตั้งฝังอยู่ในไฟล์ท้ายไฟล์ เป็นบรรทัด comment ที่เกมไม่สนใจ) ชื่อ filter จะตามชื่อไฟล์ที่เปิด
แก้แล้วกด Generate เพื่อเขียนทับไฟล์นั้น (โปรแกรมถามก่อนทับ)
ไฟล์จากรุ่นเก่าที่ยังไม่มีค่าฝังก็เปิดได้ — โปรแกรมอ่านกลับจาก block แล้วบอกใน Status ว่าส่วนไหนเดา
ไฟล์ที่ไม่ได้สร้างจากโปรแกรมนี้ หรือสร้างจากแท็บ NeverSink เปิดแก้ไม่ได้

---

## ต้องมีอะไร

- Windows 10/11
- Path of Exile 1 หรือ 2 (ติดตั้งแล้ว)
- อินเทอร์เน็ต — ดึง NeverSink filter และรายชื่อไอเท็มตอนเปิดโปรแกรม / generate (ไม่ใช้ราคาในการจัด tier)

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
