#!/usr/bin/env python3
"""build_mod_meta.py — precompute mod tier ladders สำหรับ PoE-Price-Trade-Checker

ดึง base_items.json + mods.json จาก repoe-fork/{poe1,poe2} (community datamine)
แล้ว precompute เป็น mod_meta_{game}.json ก้อนเล็ก สำหรับให้ตัวโปรแกรมตรวจ tier
ของ mod บน item จริง (offline, ไม่ยิง API เกมเลย)

ใช้:
    python tools/build_mod_meta.py --game poe2          # ดึงจาก GitHub
    python tools/build_mod_meta.py --game poe1 --local DIR  # ใช้ไฟล์ที่โหลดไว้แล้ว
ผลลัพธ์:
    mod_meta_{game}.json → เอาไปวางที่ %LOCALAPPDATA%\\PoePriceTrade\\mod_meta_{game}.json
    (คนละไฟล์ต่อเกม — base_type ชนกันข้ามเกมได้ เช่น ทั้งคู่มี base "Leather Belt")

โครงสร้าง output:
{
  "generated": "...", "source": "repoe-fork/poe2@master",
  "bases":   { "Warmonger Bow": {"class": "Bow", "drop_level": 77, "ts": 3}, ... },
  "tagsets": { "3": [ family, ... ] },
  family = {
    "gen": "prefix"|"suffix",
    "text": "#% increased physical damage",       # normalized (ตัวเลข→#, ตัด markup)
    "stats": ["local_physical_damage_+%"],
    "tiers": [ {"lvl": 82, "rng": [[170,179]]}, ... ],  # เรียง tier สูง→ต่ำ (index 0 = T1)
    "tags": ["physical", "physical_damage", "damage"]   # RePoE implicit_tags — สำหรับ metacraft
                                                          # green badge (จับคู่ mod หมวดเดียวกัน)
  }
}

สำคัญ: spawn_weights ของ RePoE เป็นแบบ FIRST-MATCH — tag แรกใน list ที่อยู่ใน
tags ของ base เป็นตัวตัดสิน (weight 0 = roll ไม่ได้ แม้ tag ถัดไปจะ weight > 0)

Domain allowlist ต่อเกม: PoE2 ใช้ domain "item"/"misc" พอ (jewel ปกติเป็น misc
ทั้งหมด) แต่ PoE1 มี jewel พิเศษแยก domain ของตัวเอง — abyss jewel ("abyss_jewel")
และ cluster jewel ("affliction_jewel") ไม่ถูกนับถ้าใช้ allowlist ของ PoE2 ตรงๆ
(ยืนยันจาก repoe-fork/poe1 raw data จริง 2026-07-17: Murderous/Searching/
Hypnotic/Ghastly Eye Jewel อยู่ domain "abyss_jewel", Small/Medium/Large
Cluster Jewel อยู่ domain "affliction_jewel", ทั้ง base_items และ mods ที่
spawn บนมันเอง — ต้องเปิดทั้งสอง domain ให้ PoE1 ไม่งั้น jewel พวกนี้หลุด
mod_meta ไปเงียบๆ)
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):     # Windows console (cp1252) ตาย เจอข้อความไทย
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

RAW_TMPL = "https://raw.githubusercontent.com/repoe-fork/{game}/master/data/"
FILES = ("base_items.json", "mods.json")

_DOMAIN_ALLOW = {
    "poe2": {"item", "misc"},
    "poe1": {"item", "misc", "abyss_jewel", "affliction_jewel"},
}

_MARKUP_PIPE = re.compile(r"\[([^\]|]*)\|([^\]]*)\]")   # [Internal|Display] → Display
_MARKUP_ONE = re.compile(r"\[([^\]]*)\]")                # [Word] → Word
_NUM = re.compile(r"[-+]?\(?\d+(?:\.\d+)?(?:-\d+(?:\.\d+)?)?\)?")


def norm_text(t: str | None) -> str:
    """normalize ให้เทียบกับ clipboard ได้: ตัด markup + ตัวเลข/ช่วงตัวเลข → #"""
    t = t or ""
    t = _MARKUP_PIPE.sub(r"\2", t)
    t = _MARKUP_ONE.sub(r"\1", t)
    t = _NUM.sub("#", t)
    return " ".join(t.lower().split())


def can_spawn(mod: dict, base_tags: set[str]) -> bool:
    for sw in mod.get("spawn_weights", []):
        if sw.get("tag") in base_tags:
            return sw.get("weight", 0) > 0    # first match ตัดสิน
    return False


def load(local: Path | None, game: str) -> tuple[dict, dict]:
    out = []
    for name in FILES:
        if local:
            data = json.loads((local / name).read_text(encoding="utf-8"))
        else:
            url = RAW_TMPL.format(game=game) + name
            print(f"ดึง {url} …", file=sys.stderr)
            with urllib.request.urlopen(url, timeout=60) as r:
                data = json.loads(r.read())
        out.append(data)
    return out[0], out[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", choices=("poe1", "poe2"), default="poe2")
    ap.add_argument("--local", type=Path, default=None,
                    help="โฟลเดอร์ที่มี base_items.json/mods.json อยู่แล้ว")
    ap.add_argument("-o", "--out", type=Path, default=None)
    args = ap.parse_args()
    out_path = args.out or Path(f"mod_meta_{args.game}.json")
    domains = _DOMAIN_ALLOW[args.game]

    bases_raw, mods_raw = load(args.local, args.game)

    # 1) จัดกลุ่ม base ตาม (domain, tag-tuple) — class เดียวมีได้หลาย tag-set เช่น
    #    Helmet 65 แบบ. domain ต้องรวมเป็น key ด้วย ไม่ใช่แค่ tags: PoE1 เพิ่ม
    #    abyss_jewel/affliction_jewel เข้ามาแล้วพบว่า base หลาย domain ใช้ tag
    #    "default"/"jewel" ร่วมกัน (generic catch-all) — ถ้าคีย์แค่ tags เฉยๆ
    #    mod ของ abyss จะรั่วไปติด cluster ตาม "default" ที่ base ทั้งคู่มี ทั้งที่
    #    คนละ domain กันจริง ๆ (ยืนยันจากข้อมูลจริง: "+X to Armour" ของ abyss
    #    ["Lacquered"/"Fortified"/...] แมตช์ผ่าน tag "default" ซึ่ง Large Cluster
    #    Jewel ก็มี "default" อยู่ใน tags ด้วยเหมือนกัน — ต้องกัน domain ให้ตรง
    #    ก่อนเช็ค tag weight)
    tagset_id: dict[tuple, int] = {}
    bases_out: dict[str, dict] = {}
    for v in bases_raw.values():
        name = v.get("name") or ""
        domain = v.get("domain", "item")
        if not name or domain not in domains:
            # "misc" = jewel bases (Ruby/Emerald/Sapphire/...) — ยืนยันแล้วว่า misc มีแต่ jewel
            # PoE1 เพิ่ม "abyss_jewel"/"affliction_jewel" — ดู allowlist ด้านบน
            continue
        key = (domain, tuple(v.get("tags", [])))
        if key not in tagset_id:
            tagset_id[key] = len(tagset_id)
        # ชื่อ base ซ้ำกันได้ข้าม class (หายาก) — ตัวหลังทับตัวแรก ยอมรับได้
        bases_out[name] = {"class": v.get("item_class", ""),
                           "drop_level": v.get("drop_level", 0),
                           "ts": tagset_id[key]}

    # 2) กรอง mod ที่สนใจ: explicit prefix/suffix บน item ปกติ (รวม abyss/cluster
    #    jewel affixes ของ PoE1 ที่อยู่คนละ domain จาก jewel ปกติ)
    cand = [m for m in mods_raw.values()
            if m.get("generation_type") in ("prefix", "suffix")
            and m.get("domain", "item") in domains
            and m.get("stats")]
    cand_by_domain: dict[str, list] = defaultdict(list)
    for m in cand:
        cand_by_domain[m.get("domain", "item")].append(m)

    # 3) ต่อ tag-set: จัด family (gen, stat ids, normalized text) → tier ladder
    tagsets_out: dict[str, list] = {}
    seen_content: dict[str, str] = {}   # dedupe tag-set ที่ mod pool เหมือนกันเป๊ะ
    ts_alias: dict[int, int] = {}
    for (domain, tt), tid in tagset_id.items():
        ts = set(tt)
        fams: dict[tuple, list] = defaultdict(list)
        fam_tags: dict[tuple, list] = {}
        for m in cand_by_domain[domain]:   # domain match first — ดู comment ข้อ 1
            if not can_spawn(m, ts):
                continue
            stats = m["stats"]
            key = (m["generation_type"],
                   tuple(s.get("id", "") for s in stats),
                   norm_text(m.get("text", "")))
            fams[key].append((m.get("required_level", 0),
                              [[s.get("min", 0), s.get("max", 0)] for s in stats]))
            # tags เหมือนกันทุก tier ของ family เดียวกัน (mod line เดียวกันแค่ค่าต่าง) —
            # เก็บจาก entry แรกที่เจอพอ
            fam_tags.setdefault(key, sorted(m.get("implicit_tags") or []))
        fam_list = []
        for (gen, sids, text), tiers in fams.items():
            tiers.sort(key=lambda t: -t[0])
            fam_list.append({"gen": gen, "text": text, "stats": list(sids),
                             "tiers": [{"lvl": lv, "rng": rng} for lv, rng in tiers],
                             "tags": fam_tags[(gen, sids, text)]})
        fam_list.sort(key=lambda f: (f["gen"], f["text"]))
        blob = json.dumps(fam_list, sort_keys=True)
        if blob in seen_content:
            ts_alias[tid] = int(seen_content[blob])
        else:
            seen_content[blob] = str(tid)
            tagsets_out[str(tid)] = fam_list

    for b in bases_out.values():          # ชี้ base ไป tag-set ตัวจริงหลัง dedupe
        b["ts"] = ts_alias.get(b["ts"], b["ts"])

    _validate(args.game, bases_out, tagsets_out)   # ห้าม “build สำเร็จแต่ข้อมูลกลวง” เงียบ ๆ

    meta = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": f"repoe-fork/{args.game}@master",
            "bases": bases_out, "tagsets": tagsets_out}
    out_path.write_text(json.dumps(meta, ensure_ascii=False, separators=(",", ":")),
                        encoding="utf-8")
    size = out_path.stat().st_size / 1e6
    print(f"เขียน {out_path}  ({size:.1f} MB)  bases={len(bases_out)} "
          f"tagsets={len(tagsets_out)} (dedupe จาก {len(tagset_id)})")


def _validate(game: str, bases_out: dict, tagsets_out: dict) -> None:
    """Sanity floor ก่อนเขียนไฟล์ — จับเคส "build สำเร็จ (exit 0) แต่ข้อมูลกลวง"
    (เช่น domain allowlist ผิด, RePoE source เปลี่ยน schema, filter กรองเหลือศูนย์)
    แบบที่ไม่โผล่เป็น exception ให้เห็นเอง fail ดังตั้งแต่ build ดีกว่าไป debug จาก
    อาการปลายทางใน UI (ประสบการณ์จริง 2026-07-17: ปัญหาจริงรอบนั้นไม่ได้อยู่ตรงนี้ —
    เป็น client ไม่ส่ง header เลย — แต่เช็คนี้ยังคุ้มเก็บไว้กันเคสไฟล์ mod_meta เองพังจริง
    ในอนาคต ทั้งสองเกม)."""
    families = [f for fams in tagsets_out.values() for f in fams]
    errors = []
    if len(bases_out) < 50:
        errors.append(f"bases={len(bases_out)} น้อยผิดปกติ (ควร >= 50)")
    if len(families) < 50:
        errors.append(f"families={len(families)} น้อยผิดปกติ (ควร >= 50)")
    if families:
        prefixes = sum(1 for f in families if f["gen"] == "prefix")
        suffixes = sum(1 for f in families if f["gen"] == "suffix")
        if prefixes == 0 or suffixes == 0:
            errors.append(f"prefix={prefixes} suffix={suffixes} — ฝั่งใดฝั่งหนึ่งหายไปหมด")
        tagged = sum(1 for f in families if f.get("tags"))
        coverage = tagged / len(families)
        if coverage < 0.30:
            errors.append(f"tag coverage {coverage:.1%} ต่ำผิดปกติ (ควร >= 30%)")
    if errors:
        print(f"✗ validation ล้มเหลวสำหรับ --game {game}:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
