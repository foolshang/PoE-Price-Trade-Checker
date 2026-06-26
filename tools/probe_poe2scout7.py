"""tools/probe_poe2scout7.py — currency categories + items ที่มีราคาจริง"""
import json, sys, io, urllib.request, urllib.parse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
BASE = "https://poe2scout.com/api/poe2"
LEAGUE = "Runes of Aldur"
L = urllib.parse.quote(LEAGUE, safe="")

def get(path):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

# 1) Items/Categories — ดู CurrencyCategories
print("=== Items/Categories ===")
cats = get(f"/Leagues/{L}/Items/Categories")
print(json.dumps(cats, ensure_ascii=False, indent=2))

# 2) ลอง currency categories หลายแบบ
print("\n=== Currencies/ByCategory ===")
for cat in ["currency", "Currency", "rune", "Rune", "essence", "fragment", "omen", "scarab", "gem"]:
    data = get(f"/Leagues/{L}/Currencies/ByCategory?Category={urllib.parse.quote(cat)}&PerPage=2")
    total = data.get("Total", 0)
    print(f"  {cat:12s} total={total}")
    if total > 0:
        for x in data.get("Items", [])[:2]:
            print(f"    {x.get('Text','?'):30s} price={x.get('CurrentPrice','?')} unit={x.get('PriceUnit','?')}")

# 3) Items ที่ราคา > 1 exalted (มีข้อมูลราคาจริง)
print("\n=== Unique Items with CurrentPrice > 1 (sample 10) ===")
data = get(f"/Leagues/{L}/Items")
priced = [x for x in data if x.get("CurrentPrice", 0) > 1.0]
print(f"total items={len(data)} priced>1ex={len(priced)}")
for x in sorted(priced, key=lambda x: x.get("CurrentPrice", 0), reverse=True)[:10]:
    print(f"  {x.get('CurrentPrice',0):8.2f}ex  {x.get('Name','?'):30s} [{x.get('CategoryApiId','?')}]")

# 4) Single item detail
print("\n=== Single Item detail ===")
if data:
    iid = data[0]["ItemId"]
    detail = get(f"/Leagues/{L}/Items/{iid}")
    print(json.dumps(detail, ensure_ascii=False, indent=2)[:600])
