"""tools/probe_ninja_poe2_uniques.py — หา endpoint + type ของ unique/equipment PoE2"""
import json, urllib.request, urllib.parse, urllib.error
LEAGUE = "Runes of Aldur"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
L = urllib.parse.quote(LEAGUE)

# poe.ninja PoE2 unique — ลองหลาย path/type ที่เป็นไปได้
URLS = [
    f"https://poe.ninja/poe2/api/economy/items/overview?league={L}&type=Weapon",
    f"https://poe.ninja/poe2/api/economy/items/overview?league={L}&type=UniqueWeapon",
    f"https://poe.ninja/poe2/api/economy/items/overview?league={L}&type=Armour",
    f"https://poe.ninja/poe2/api/economy/items/overview?league={L}&type=Accessory",
    f"https://poe.ninja/poe2/api/economy/items/overview?league={L}&type=Jewel",
    f"https://poe.ninja/poe2/api/economy/exchange/current/overview?league={L}&type=Weapon",
    # poe2scout API (เช็คว่ามี + โครงสร้าง)
    "https://poe2scout.com/api/items?category=unique",
    "https://poe2scout.com/api/currency",
]
for url in URLS:
    print("=" * 70); print(url)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
            keys = list(data.keys()) if isinstance(data, dict) else f"list[{len(data)}]"
            print("HTTP", r.status, "| keys:", keys)
            lines = data.get("lines") if isinstance(data, dict) else (data if isinstance(data, list) else [])
            if lines:
                print("first:", json.dumps(lines[0], ensure_ascii=False)[:400])
    except urllib.error.HTTPError as e:
        print("HTTP ERROR", e.code)
    except Exception as e:
        print("FAIL", type(e).__name__, str(e)[:120])
    print()
