"""tools/probe_ninja_catalog.py — ครบทั้ง GENERAL + EQUIPMENT + ATLAS"""
import re, urllib.request, urllib.error
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
L = "Runes%20of%20Aldur"

def get(url, accept="application/json"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return 0, str(e)

EXCHANGE = "https://poe.ninja/poe2/api/economy/exchange/current/overview?league={L}&type={T}"
ITEM_PATHS = [
    "https://poe.ninja/poe2/api/economy/itemoverview?league={L}&type={T}",
    "https://poe.ninja/poe2/api/data/itemoverview?league={L}&type={T}",
]

# GENERAL — หลาย type-string ต่อหมวด กันเดาผิด
GENERAL = {
    "Currency": ["Currency"], "Fragments": ["Fragment", "Fragments"],
    "Abyssal Bones": ["AbyssalBone", "Abyss", "AbyssalBones", "Bone"],
    "Uncut Gems": ["UncutGem", "UncutGems", "UncutSkillGem"],
    "Lineage Gems": ["LineageSupportGem", "LineageGem", "Lineage"],
    "Essences": ["Essence", "Essences"], "Soul Cores": ["SoulCore", "SoulCores"],
    "Idols": ["Idol", "Idols"], "Runes": ["Rune", "Runes"],
    "Omens": ["Omen", "Omens"], "Expedition": ["Expedition", "ExpeditionCurrency"],
    "Liquid Emotions": ["Delirium", "LiquidEmotion", "DeliriumInstill"],
    "Catalysts": ["Catalyst", "Catalysts"], "Verisium": ["Verisium", "VerisiumOre"],
}
# EQUIPMENT + ATLAS
ITEMS = {
    "Unique Weapons": ["UniqueWeapon"], "Unique Armours": ["UniqueArmour"],
    "Unique Accessories": ["UniqueAccessory"], "Unique Flasks": ["UniqueFlask"],
    "Unique Charms": ["UniqueCharm"], "Unique Jewels": ["UniqueJewel"],
    "Unique Relics": ["UniqueRelic"], "Unique Tablets": ["UniqueTablet", "UniqueMap"],
    "Precursor Tablets": ["PrecursorTablet", "Tablet"],
}

def try_types(label, types, templates):
    for t in types:
        for tmpl in templates:
            s, body = get(tmpl.format(L=L, T=t))
            n = body.count('"name"') if s == 200 else 0
            lines = body.count('"primaryValue"') + body.count('"chaosValue"') if s == 200 else 0
            if s == 200 and (n > 0 or lines > 0):
                ep = "exchange" if "exchange" in tmpl else "item"
                print(f"  OK  {label:20s} type={t:18s} ep={ep:8s} hits~{max(n,lines)}")
                return True
    return False

print("=== GENERAL ===")
miss = []
for label, types in GENERAL.items():
    if not try_types(label, types, [EXCHANGE] + ITEM_PATHS):
        print(f"  --  {label:20s} (ไม่เจอ — ลอง type อื่น)"); miss.append(label)

print("\n=== EQUIPMENT + ATLAS ===")
for label, types in ITEMS.items():
    if not try_types(label, types, ITEM_PATHS + [EXCHANGE]):
        print(f"  --  {label:20s} (ไม่เจอ)"); miss.append(label)

print("\nหมวดที่ยังหา type ไม่เจอ:", miss)
print("(ถ้า 403 ทุกตัว = ต้องรันบนเครื่องจริง ไม่ใช่ sandbox)")
