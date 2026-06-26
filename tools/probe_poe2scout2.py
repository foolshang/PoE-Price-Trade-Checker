"""tools/probe_poe2scout2.py — probe poe2scout API endpoints หลังรู้ OpenAPI spec"""
import json, urllib.request, urllib.parse, urllib.error

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
BASE = "https://poe2scout.com/api"
REALM = "poe2/poe2"   # slash เป็น path separator ไม่ encode
LEAGUE = "Runes of Aldur"
L = urllib.parse.quote(LEAGUE, safe="")

def get(path):
    url = BASE + path
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}

# 1) Leagues
print("=== Leagues ===")
s, data = get(f"/{REALM}/Leagues")
print(f"HTTP {s}")
if isinstance(data, list):
    for x in data[:6]: print(" ", x)
else:
    print(json.dumps(data, ensure_ascii=False)[:400])

# 2) ExchangeSnapshot
print("\n=== ExchangeSnapshot ===")
s, data = get(f"/{REALM}/Leagues/{L}/ExchangeSnapshot")
print(f"HTTP {s} | type={type(data).__name__}")
if isinstance(data, list):
    print(f"count={len(data)}")
    print("first:", json.dumps(data[0], ensure_ascii=False)[:300] if data else "[]")
else:
    keys = list(data.keys()) if isinstance(data, dict) else data
    print("keys:", keys)
    print(json.dumps(data, ensure_ascii=False)[:400])

# 3) ReferenceCurrencies
print("\n=== ReferenceCurrencies ===")
s, data = get(f"/{REALM}/Leagues/{L}/ReferenceCurrencies")
print(f"HTTP {s}")
print(json.dumps(data, ensure_ascii=False)[:400])

# 4) Items/Categories
print("\n=== Items/Categories ===")
s, data = get(f"/{REALM}/Leagues/{L}/Items/Categories")
print(f"HTTP {s}")
print(json.dumps(data, ensure_ascii=False)[:600])

# 5) Uniques/ByCategory — ลอง category ต่างๆ
print("\n=== Uniques/ByCategory ===")
for cat in ["", "Weapon", "Armour", "Accessory", "Jewel", "Flask"]:
    cat_q = f"?Category={urllib.parse.quote(cat)}" if cat else ""
    s, data = get(f"/{REALM}/Leagues/{L}/Uniques/ByCategory{cat_q}&PerPage=3")
    count = len(data) if isinstance(data, list) else data.get("total", data.get("count", "?"))
    first = data[0] if isinstance(data, list) and data else (data.get("items", data.get("data", [{}]))[0] if isinstance(data, dict) else {})
    print(f"HTTP {s} cat={cat!r:10s} count={count}")
    if first: print("  first:", json.dumps(first, ensure_ascii=False)[:250])

# 6) Currencies/ByCategory
print("\n=== Currencies/ByCategory ===")
s, data = get(f"/{REALM}/Leagues/{L}/Currencies/ByCategory?PerPage=3")
print(f"HTTP {s} | type={type(data).__name__}")
if isinstance(data, list) and data:
    print("first:", json.dumps(data[0], ensure_ascii=False)[:300])
elif isinstance(data, dict):
    print(json.dumps(data, ensure_ascii=False)[:400])
