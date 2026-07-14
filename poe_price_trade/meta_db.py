"""MetaDB — tier ladder + money-mod annotation (offline)

โหลด mod_meta.json (สร้างด้วย tools/build_mod_meta.py จาก RePoE datamine)
จาก %LOCALAPPDATA%\\PoePriceTrade\\ — ไม่มีไฟล์ = feature จำกัดแบบเงียบๆ

ให้ 2 อย่าง:
1. tier ของ mod: อ่านจาก header เกม { ... (Tier: N) } เป็นหลัก + จำนวน tier
   ทั้งหมดจาก meta (T1/6 ความหมายต่างจาก T1/2) + คำนวณเองเมื่อ header ไม่บอก
2. money flag: mod เข้าข่าย "ขายได้" ตามกติกา _DEFAULT_MONEY
   (override ได้ด้วยไฟล์ money_mods.json ใน app dir — แก้ meta ไม่ต้อง build exe)
"""
from __future__ import annotations
import json
import logging
import re
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# normalize ต้องตรงกับ build_mod_meta.py เป๊ะ: ตัวเลข/ช่วง/เครื่องหมาย → #
# สำคัญ: ตัดช่วง roll ที่เกมพิมพ์ติดค่า เช่น 40(39-42)% ทิ้งก่อน — ไม่งั้นได้ "##%" ไม่ตรง family
_ROLL_RANGE = re.compile(r"\(\d+(?:\.\d+)?-\d+(?:\.\d+)?\)")
_NUMISH = re.compile(r"[-+]?\(?\d+(?:\.\d+)?(?:-\d+(?:\.\d+)?)?\)?")


def _norm(t: str) -> str:
    return " ".join(_NUMISH.sub("#", _ROLL_RANGE.sub("", t)).lower().split())


WEAPON_CLASSES = {
    "Bows", "Crossbows", "Wands", "Staves", "Quarterstaves", "Spears",
    "One Hand Maces", "Two Hand Maces", "Sceptres", "Flails",
    "One Hand Swords", "Two Hand Swords", "One Hand Axes", "Two Hand Axes",
    "Claws", "Daggers",
}

# กติกา mod เงิน — "contains" เทียบกับข้อความ normalize แล้ว (ตัวเลข = #)
# classes: None = ทุก class | "WEAPON" = อาวุธ | list = เฉพาะ class ในลิสต์
# max_tier: ต้องรู้ tier และ tier <= ค่านี้ถึงนับ | None = ไม่สน tier
_DEFAULT_MONEY: list[dict] = [
    {"contains": "movement speed",              "classes": ["Boots"], "max_tier": 2},
    {"contains": "to level of all",             "classes": None,      "max_tier": None},
    {"contains": "increased physical damage",   "classes": "WEAPON",  "max_tier": 2},
    {"contains": "adds # to # physical damage", "classes": "WEAPON",  "max_tier": 2},
    {"contains": "increased attack speed",      "classes": "WEAPON",  "max_tier": 2},
    {"contains": "increased cast speed",        "classes": "WEAPON",  "max_tier": 2},
    {"contains": "increased spell damage",      "classes": "WEAPON",  "max_tier": 2},
    {"contains": "additional arrow",            "classes": None,      "max_tier": None},
    {"contains": "additional projectile",       "classes": None,      "max_tier": None},
    {"contains": "to maximum life",             "classes": None,      "max_tier": 2},
    {"contains": "to chaos resistance",         "classes": None,      "max_tier": None},
    {"contains": "rarity of items found",       "classes": None,      "max_tier": None},
    {"contains": "to spirit",                   "classes": None,      "max_tier": None},
]


class MetaDB:
    def __init__(self, app_dir: Path):
        self._path = app_dir / "mod_meta.json"
        self._money_path = app_dir / "money_mods.json"
        self._meta: Optional[dict] = None
        self._money = _DEFAULT_MONEY
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            self._meta = json.loads(self._path.read_text(encoding="utf-8"))
            log.info("mod_meta loaded: bases=%d tagsets=%d",
                     len(self._meta.get("bases", {})), len(self._meta.get("tagsets", {})))
        except FileNotFoundError:
            log.info("mod_meta.json ไม่พบ (%s) — tier/money annotation จำกัด", self._path)
        except Exception as e:
            log.warning("mod_meta load fail: %s", e)
        try:
            self._money = json.loads(self._money_path.read_text(encoding="utf-8"))
            log.info("money_mods.json override: %d rules", len(self._money))
        except FileNotFoundError:
            pass
        except Exception as e:
            log.warning("money_mods load fail: %s", e)

    def available(self) -> bool:
        return self._meta is not None

    def resolve_base(self, name: str) -> Optional[str]:
        """หา base จริงที่ฝังอยู่ในชื่อ magic item — เทียบกับรายชื่อ base ใน meta
        เลือกตัวที่ยาวที่สุด (word boundary ด้วยการ pad ช่องว่าง)

        เช่น "Legend's Fortress Sabatons of Grounding" → "Fortress Sabatons"
        ไม่เจอ/ไม่มี meta → None (ผู้เรียกควรตัด type ออกจาก query)"""
        self.load()
        if not self._meta or not name:
            return None
        padded = f" {name} "
        best = ""
        for base in self._meta.get("bases", {}):
            if len(base) > len(best) and f" {base} " in padded:
                best = base
        return best or None

    def _families(self, base_type: str) -> Optional[list]:
        if not self._meta:
            return None
        b = self._meta.get("bases", {}).get(base_type)
        if not b:
            return None
        return self._meta.get("tagsets", {}).get(str(b.get("ts")))

    def annotate(self, item) -> dict:
        """คืน {group_no: {"tier","total","cap","money"}} — group = header block เดียวกัน"""
        self.load()
        fams = self._families(item.base_type)
        groups: dict[int, list] = {}
        for m in item.mods:
            groups.setdefault(getattr(m, "group", -1), []).append(m)

        out: dict[int, dict] = {}
        for g, ms in groups.items():
            mod_type = getattr(ms[0], "mod_type", "explicit")
            text = " ".join(mm.text for mm in ms)          # hybrid → join เป็น family เดียว
            values = [v for mm in ms for v in getattr(mm, "values", ())]
            tier = getattr(ms[0], "tier", 0)
            total = cap = 0
            # rune/enchant/implicit ไม่ใช่ affix ปกติ — ไม่เทียบ tier ladder
            if fams and mod_type in ("explicit", "desecrated", "fractured"):
                n = _norm(text)
                for f in fams:
                    if f["text"] == n:
                        total = len(f["tiers"])
                        usable = [t for t in f["tiers"] if t["lvl"] <= item.item_level]
                        cap = (total - len(usable) + 1) if usable else 0
                        if not tier:                        # header ไม่บอก → คำนวณจากค่า roll
                            for i, t in enumerate(f["tiers"]):
                                if (t["lvl"] <= item.item_level
                                        and len(values) == len(t["rng"])
                                        and all(r[0] <= v <= r[1]
                                                for v, r in zip(values, t["rng"]))):
                                    tier = i + 1
                                    break
                        break
            out[g] = {"tier": tier, "total": total, "cap": cap,
                      "money": self._is_money(text, item.item_class, tier, mod_type)}
        return out

    def _is_money(self, text: str, item_class: str, tier: int, mod_type: str) -> bool:
        if mod_type in ("rune", "enchant"):
            return False
        n = _norm(text)
        for rule in self._money:
            c = rule.get("classes")
            if c == "WEAPON":
                if item_class not in WEAPON_CLASSES:
                    continue
            elif c and item_class not in c:
                continue
            if rule.get("contains", "") not in n:
                continue
            mt = rule.get("max_tier")
            if mt is not None and (not tier or tier > mt):
                continue
            return True
        return False

    @staticmethod
    def summary(item, ann: dict) -> str:
        money = sum(1 for i in ann.values() if i.get("money"))
        t1 = sum(1 for i in ann.values() if i.get("tier") == 1)
        parts: list[str] = []
        if money:
            parts.append(f"💰 mod เงิน ×{money}")
        if t1:
            parts.append(f"T1 ×{t1}")
        if item.rarity == "Rare":
            open_p = max(0, 3 - getattr(item, "prefix_count", 0))
            open_s = max(0, 3 - getattr(item, "suffix_count", 0))
            slot = []
            if open_p:
                slot.append(f"prefix ว่าง {open_p}")
            if open_s:
                slot.append(f"suffix ว่าง {open_s}")
            if slot:
                parts.append(" · ".join(slot))
        parts.append(f"ilvl {item.item_level}")
        return "  ·  ".join(parts)
