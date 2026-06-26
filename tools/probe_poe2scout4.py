"""tools/probe_poe2scout4.py — probe Currencies + Uniques ด้วย params ถูกต้อง"""
import json, urllib.request, urllib.parse, urllib.error

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
BASE = "https://poe2scout.com/api/poe2"
LEAGUE = "Runes of Aldur"
L = urllib.parse.quote(LEAGUE, safe="")

def get(path):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return e.code, {"error": body[:300]}

# ดู required params จาก openapi
print("=== OpenAPI params for Currencies/ByCategory ===")
s, spec = get("/../openapi.json".replace("poe2", "").replace("//", "/").replace("api/", "api"))
# ดึงตรงๆ แทน
req = urllib.request.Request(
    "https://poe2scout.com/api/openapi.json",
    headers={"User-Agent": UA, "Accept": "application/json"}
)
with urllib.request.urlopen(req, timeout=15) as r:
    spec = json.loads(r.read())

for path_key in ["/{Realm}/Leagues/{LeagueName}/Currencies/ByCategory",
                 "/{Realm}/Leagues/{LeagueName}/Uniques/ByCategory"]:
    params = spec["paths"].get(path_key, {}).get("get", {}).get("parameters", [])
    print(f"\n{path_key}")
    for p in params:
        req_flag = " [REQUIRED]" if p.get("required") else ""
        schema = p.get("schema", {})
        default = schema.get("default", "—")
        print(f"  {p['name']:25s} required={p.get('required',False)} default={default}{req_flag}")

# ลอง Currencies/ByCategory ด้วย Category ต่างๆ
print("\n=== Currencies/ByCategory ===")
for cat in ["Currency", "Fragment", "Rune", "Essence", "Delirium", "Omen", "Scarab", "Map", "Misc"]:
    q = f"?Category={urllib.parse.quote(cat)}&PerPage=3"
    s, data = get(f"/Leagues/{L}/Currencies/ByCategory{q}")
    rows = data if isinstance(data, list) else data.get("items", data.get("data", []))
    print(f"  HTTP {s} cat={cat:12s} rows={len(rows) if isinstance(rows, list) else data}")
    if isinstance(rows, list) and rows:
        print("   first:", json.dumps(rows[0], ensure_ascii=False)[:200])

# ลอง Uniques/ByCategory
print("\n=== Uniques/ByCategory ===")
for cat in ["", "Weapon", "Armour", "Accessory", "Jewel", "Flask", "Map"]:
    q = f"?PerPage=3" + (f"&Category={urllib.parse.quote(cat)}" if cat else "")
    s, data = get(f"/Leagues/{L}/Uniques/ByCategory{q}")
    rows = data if isinstance(data, list) else data.get("items", data.get("data", []))
    print(f"  HTTP {s} cat={cat!r:12s} rows={len(rows) if isinstance(rows, list) else data}")
    if isinstance(rows, list) and rows:
        print("   first:", json.dumps(rows[0], ensure_ascii=False)[:250])
