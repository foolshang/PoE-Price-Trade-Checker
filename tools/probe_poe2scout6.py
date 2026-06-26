"""tools/probe_poe2scout6.py — สรุป poe2scout structure + ลอง currency categories"""
import json, urllib.request, urllib.parse

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
BASE = "https://poe2scout.com/api/poe2"
LEAGUE = "Runes of Aldur"
L = urllib.parse.quote(LEAGUE, safe="")

def get(path):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

# 1) Items full structure — first 5
print("=== Items (first 5, full fields) ===")
data = get(f"/Leagues/{L}/Items?PerPage=5")
print(f"type={type(data).__name__} len={len(data) if isinstance(data, list) else '?'}")
for x in (data[:5] if isinstance(data, list) else []):
    print(json.dumps(x, ensure_ascii=False))

# 2) Items count total
print("\n=== Items total count ===")
# ลอง page=1 PerPage=1 และดู header หรือ total
data = get(f"/Leagues/{L}/Items?PerPage=1")
print(f"list len={len(data)}")  # ถ้าเป็น list อาจไม่มี total
# ลองดูว่า Items endpoint รองรับ pagination ไหม
data100 = get(f"/Leagues/{L}/Items?PerPage=100")
print(f"PerPage=100 → {len(data100)} items")

# 3) Items/Categories ดู UniqueCategories ทั้งหมด
print("\n=== Items/Categories full ===")
cats = get(f"/Leagues/{L}/Items/Categories")
print(json.dumps(cats, ensure_ascii=False, indent=2))

# 4) Currency categories — ลองทุก ApiId จาก Categories
print("\n=== Currencies — ลอง category names จาก Items/Categories ===")
# หา CurrencyCategories field
cur_cats = cats.get("CurrencyCategories", cats.get("currencyCategories", []))
print(f"CurrencyCategories: {cur_cats}")

# ลอง category ชื่อต่างๆ
for cat in ["currency", "rune", "essence", "fragment", "omen", "scarab", "delirium", "gem", "misc"]:
    data = get(f"/Leagues/{L}/Currencies/ByCategory?Category={urllib.parse.quote(cat)}&PerPage=3")
    items = data.get("Items", [])
    total = data.get("Total", 0)
    if total > 0:
        print(f"  OK  cat={cat!r:12s} total={total}")
        for x in items[:2]:
            print("     ", json.dumps(x, ensure_ascii=False)[:180])
    else:
        print(f"  --- cat={cat!r:12s} total=0")

# 5) Currencies/ByCategory?Category=currency — first item full
print("\n=== Currency full item structure ===")
data = get(f"/Leagues/{L}/Currencies/ByCategory?Category=currency&PerPage=3")
for x in data.get("Items", [])[:3]:
    print(json.dumps(x, ensure_ascii=False))
