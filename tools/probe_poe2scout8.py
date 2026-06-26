"""tools/probe_poe2scout8.py — ยืนยันราคาจาก currency categories จริง + unique top prices"""
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

# league divine price
leagues = get("/Leagues")
league_info = next((x for x in leagues if x.get("Value") == LEAGUE), {})
div_price = league_info.get("DivinePrice", 1.0)
print(f"DivinePrice (ex per div) = {div_price}")

# currency categories ที่ถูกต้องจาก openapi
ALL_CUR_CATS = [
    "currency", "fragments", "runes", "essences", "ultimatum",
    "expedition", "ritual", "vaultkeys", "breach", "abyss",
    "uncutgems", "lineagesupportgems", "delirium", "incursion",
    "idol", "verisium", "vaal"
]
print("\n=== Currencies/ByCategory — all categories ===")
for cat in ALL_CUR_CATS:
    data = get(f"/Leagues/{L}/Currencies/ByCategory?Category={urllib.parse.quote(cat)}&PerPage=3")
    total = data.get("Total", 0)
    if total > 0:
        print(f"  OK  {cat:25s} total={total}")
        for x in data.get("Items", [])[:2]:
            ex_val = x.get("CurrentPrice") or 0
            div_val = ex_val / div_price if div_price else 0
            name = x.get("Text") or x.get("Name") or "?"
            print(f"       {name:35s} {ex_val:.2f}ex = {div_val:.3f}div")
    else:
        print(f"  --- {cat:25s} total=0")

# unique top 15 by price
print("\n=== Top 15 Unique Items by price ===")
items = get(f"/Leagues/{L}/Items")
priced = [(x.get("CurrentPrice") or 0, x) for x in items if (x.get("CurrentPrice") or 0) > 1.0]
priced.sort(reverse=True)
for ex_val, x in priced[:15]:
    div_val = ex_val / div_price if div_price else 0
    name = str(x.get("Name") or x.get("Text") or "?")
    cat = str(x.get("CategoryApiId") or "?")
    print(f"  {ex_val:8.1f}ex = {div_val:7.2f}div  {name:35s} [{cat}]")

print(f"\ntotal unique items={len(items)} priced>1ex={len(priced)}")
