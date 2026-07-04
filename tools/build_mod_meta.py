#!/usr/bin/env python3
"""build_mod_meta.py — precompute mod tier ladders สำหรับ PoE-Price-Trade-Checker

ดึง base_items.json + mods.json จาก repoe-fork/poe2 (community datamine, 0.5)
แล้ว precompute เป็น mod_meta.json ก้อนเล็ก สำหรับให้ตัวโปรแกรมตรวจ tier ของ mod
บน item จริง (offline, ไม่ยิง API เกมเลย)

ใช้:
    python tools/build_mod_meta.py                 # ดึงจาก GitHub
    python tools/build_mod_meta.py --local DIR     # ใช้ไฟล์ที่โหลดไว้แล้ว
ผลลัพธ์:
    mod_meta.json → เอาไปวางที่ %LOCALAPPDATA%\\PoePriceTrade\\mod_meta.json

โครงสร้าง output:
{
  "generated": "...", "source": "repoe-fork/poe2@master",
  "bases":   { "Warmonger Bow": {"class": "Bow", "drop_level": 77, "ts": 3}, ... },
  "tagsets": { "3": [ family, ... ] },
  family = {
    "gen": "prefix"|"suffix",
    "text": "#% increased physical damage",       # normalized (ตัวเลข→#, ตัด markup)
    "stats": ["local_physical_damage_+%"],
    "tiers": [ {"lvl": 82, "rng": [[170,179]]}, ... ]   # เรียง tier สูง→ต่ำ (index 0 = T1)
  }
}

สำคัญ: spawn_weights ของ RePoE เป็นแบบ FIRST-MATCH — tag แรกใน list ที่อยู่ใน
tags ของ base เป็นตัวตัดสิน (weight 0 = roll ไม่ได้ แม้ tag ถัดไปจะ weight > 0)
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

RAW = "https://raw.githubusercontent.com/repoe-fork/poe2/master/data/"
FILES = ("base_items.json", "mods.json")

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


def load(local: Path | None) -> tuple[dict, dict]:
    out = []
    for name in FILES:
        if local:
            data = json.loads((local / name).read_text(encoding="utf-8"))
        else:
            url = RAW + name
            print(f"ดึง {url} …", file=sys.stderr)
            with urllib.request.urlopen(url, timeout=60) as r:
                data = json.loads(r.read())
        out.append(data)
    return out[0], out[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", type=Path, default=None,
                    help="โฟลเดอร์ที่มี base_items.json/mods.json อยู่แล้ว")
    ap.add_argument("-o", "--out", type=Path, default=Path("mod_meta.json"))
    args = ap.parse_args()

    bases_raw, mods_raw = load(args.local)

    # 1) จัดกลุ่ม base ตาม tag-tuple (class เดียวมีได้หลาย tag-set เช่น Helmet 65 แบบ)
    tagset_id: dict[tuple, int] = {}
    bases_out: dict[str, dict] = {}
    for v in bases_raw.values():
        name = v.get("name") or ""
        if not name or v.get("domain", "item") not in ("item", "misc"):
            # "misc" = jewel bases (Ruby/Emerald/Sapphire/...) — ยืนยันแล้วว่า misc มีแต่ jewel
            continue
        tt = tuple(v.get("tags", []))
        if tt not in tagset_id:
            tagset_id[tt] = len(tagset_id)
        # ชื่อ base ซ้ำกันได้ข้าม class (หายาก) — ตัวหลังทับตัวแรก ยอมรับได้
        bases_out[name] = {"class": v.get("item_class", ""),
                           "drop_level": v.get("drop_level", 0),
                           "ts": tagset_id[tt]}

    # 2) กรอง mod ที่สนใจ: explicit prefix/suffix บน item ปกติ
    cand = [m for m in mods_raw.values()
            if m.get("generation_type") in ("prefix", "suffix")
            and m.get("domain", "item") in ("item", "misc")   # misc = jewel affixes
            and m.get("stats")]

    # 3) ต่อ tag-set: จัด family (gen, stat ids, normalized text) → tier ladder
    tagsets_out: dict[str, list] = {}
    seen_content: dict[str, str] = {}   # dedupe tag-set ที่ mod pool เหมือนกันเป๊ะ
    ts_alias: dict[int, int] = {}
    for tt, tid in tagset_id.items():
        ts = set(tt)
        fams: dict[tuple, list] = defaultdict(list)
        for m in cand:
            if not can_spawn(m, ts):
                continue
            stats = m["stats"]
            key = (m["generation_type"],
                   tuple(s.get("id", "") for s in stats),
                   norm_text(m.get("text", "")))
            fams[key].append((m.get("required_level", 0),
                              [[s.get("min", 0), s.get("max", 0)] for s in stats]))
        fam_list = []
        for (gen, sids, text), tiers in fams.items():
            tiers.sort(key=lambda t: -t[0])
            fam_list.append({"gen": gen, "text": text, "stats": list(sids),
                             "tiers": [{"lvl": lv, "rng": rng} for lv, rng in tiers]})
        fam_list.sort(key=lambda f: (f["gen"], f["text"]))
        blob = json.dumps(fam_list, sort_keys=True)
        if blob in seen_content:
            ts_alias[tid] = int(seen_content[blob])
        else:
            seen_content[blob] = str(tid)
            tagsets_out[str(tid)] = fam_list

    for b in bases_out.values():          # ชี้ base ไป tag-set ตัวจริงหลัง dedupe
        b["ts"] = ts_alias.get(b["ts"], b["ts"])

    meta = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": "repoe-fork/poe2@master",
            "bases": bases_out, "tagsets": tagsets_out}
    args.out.write_text(json.dumps(meta, ensure_ascii=False, separators=(",", ":")),
                        encoding="utf-8")
    size = args.out.stat().st_size / 1e6
    print(f"เขียน {args.out}  ({size:.1f} MB)  bases={len(bases_out)} "
          f"tagsets={len(tagsets_out)} (dedupe จาก {len(tagset_id)})")


if __name__ == "__main__":
    main()
