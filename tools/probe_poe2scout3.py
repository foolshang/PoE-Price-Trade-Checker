"""tools/probe_poe2scout3.py — probe poe2scout ด้วย realm=poe2 ที่ถูกต้อง"""
import json, urllib.request, urllib.parse

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
BASE = "https://poe2scout.com/api/poe2"

def get(path):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def pp(data, limit=3, width=200):
    rows = data if isinstance(data, list) else data.get("items", data.get("data", [data]))
    print(f"  count={len(rows) if isinstance(rows, list) else '?'}")
    for x in (rows[:limit] if isinstance(rows, list) else [rows]):
        print(" ", json.dumps(x, ensure_ascii=False)[:width])

# 1) Leagues
print("=== Leagues ===")
leagues = get("/Leagues")
for x in leagues:
    cur = " <-- current" if x.get("IsCurrent") else ""
    print(f"  {x['Value']:35s} base={x.get('BaseCurrencyText','?')} divPrice={x.get('DivinePrice','?')}{cur}")

cur_league = next((x["Value"] for x in leagues if x.get("IsCurrent")), leagues[0]["Value"])
L = urllib.parse.quote(cur_league, safe="")
print(f"\nUsing: {cur_league}")

# 2) ExchangeSnapshot
print("\n=== ExchangeSnapshot ===")
pp(get(f"/Leagues/{L}/ExchangeSnapshot"))

# 3) ReferenceCurrencies
print("\n=== ReferenceCurrencies ===")
data = get(f"/Leagues/{L}/ReferenceCurrencies")
print(json.dumps(data, ensure_ascii=False)[:400])

# 4) Currencies/ByCategory
print("\n=== Currencies/ByCategory ===")
data = get(f"/Leagues/{L}/Currencies/ByCategory?PerPage=3")
print(f"  type={type(data).__name__} keys={list(data.keys()) if isinstance(data, dict) else len(data)}")
pp(data)

# 5) Uniques/ByCategory — ลองทุก category
print("\n=== Uniques/ByCategory ===")
for cat in ["", "Weapon", "Armour", "Accessory", "Jewel", "Flask"]:
    q = f"?PerPage=2" + (f"&Category={urllib.parse.quote(cat)}" if cat else "")
    data = get(f"/Leagues/{L}/Uniques/ByCategory{q}")
    rows = data if isinstance(data, list) else data.get("items", data.get("data", []))
    keys = list(data.keys()) if isinstance(data, dict) else "list"
    print(f"  cat={cat!r:12s} type={type(data).__name__} keys/len={keys}")
    for x in rows[:2]:
        print("   ", json.dumps(x, ensure_ascii=False)[:250])

# 6) Items/Categories
print("\n=== Items/Categories ===")
data = get(f"/Leagues/{L}/Items/Categories")
print(json.dumps(data, ensure_ascii=False)[:600])
