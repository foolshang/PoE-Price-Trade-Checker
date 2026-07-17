"""BUG 3: magic item ชื่อรวม affix name → ต้อง resolve base ก่อนสร้าง trade query."""
import json

from poe_price_trade.item_parser import parse_item
from poe_price_trade.meta_db import MetaDB

TEXT = """Item Class: Boots
Rarity: Magic
Legend's Fortress Sabatons of Grounding
--------
Armour: 293 (augmented)
Evasion Rating: 267 (augmented)
--------
Requires: Level 75, 56 Str, 56 Dex
--------
Sockets: S
--------
Item Level: 80
--------
{ Prefix Modifier "Legend's" (Tier: 1) — Armour, Evasion }
99(92-100)% increased Armour and Evasion
{ Suffix Modifier "of Grounding" (Tier: 1) — Elemental, Lightning, Ailment }
56(56-60)% reduced Shock duration on you
"""


def test_magic_parse():
    it = parse_item(TEXT, "poe2")
    assert it is not None
    assert it.rarity == "Magic"
    assert it.identified is True
    # parser ยังให้ชื่อเต็ม (การ resolve เป็นหน้าที่ MetaDB ในชั้น app)
    assert it.base_type == "Legend's Fortress Sabatons of Grounding"
    ex = [m for m in it.mods if m.mod_type == "explicit"]
    assert len(ex) == 2 and ex[0].tier == 1 and ex[1].tier == 1


def test_resolve_base(tmp_path):
    (tmp_path / "mod_meta_poe2.json").write_text(json.dumps({
        "bases": {"Fortress Sabatons": {"class": "Boots", "drop_level": 75, "ts": 0},
                  "Sabatons": {"class": "Boots", "drop_level": 10, "ts": 0}},
        "tagsets": {},
    }), encoding="utf-8")
    db = MetaDB(tmp_path, "poe2")
    # เลือกตัวยาวสุดที่ฝังอยู่ในชื่อ (ไม่ใช่ "Sabatons" ที่สั้นกว่า)
    assert db.resolve_base("Legend's Fortress Sabatons of Grounding") == "Fortress Sabatons"
    assert db.resolve_base("Fortress Sabatons") == "Fortress Sabatons"
    assert db.resolve_base("Boots of Nothing") is None


def test_resolve_base_without_meta(tmp_path):
    db = MetaDB(tmp_path, "poe2")          # ไม่มีไฟล์ meta
    assert db.resolve_base("Legend's Fortress Sabatons of Grounding") is None
