"""tools/probe_poe2scout5.py — ดู raw JSON จาก poe2scout Currencies/Uniques"""
import json, urllib.request, urllib.parse

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
BASE = "https://poe2scout.com/api/poe2"
LEAGUE = "Runes of Aldur"
L = urllib.parse.quote(LEAGUE, safe="")

def get_raw(path):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status, r.read().decode("utf-8", errors="replace")

# ดู raw currencies
print("=== Currencies/ByCategory?Category=Currency (raw 500 chars) ===")
s, raw = get_raw(f"/Leagues/{L}/Currencies/ByCategory?Category=Currency&PerPage=5")
print(f"HTTP {s}")
print(raw[:500])

print("\n=== Currencies/ByCategory?Category=Rune (raw 500 chars) ===")
s, raw = get_raw(f"/Leagues/{L}/Currencies/ByCategory?Category=Rune&PerPage=5")
print(f"HTTP {s}")
print(raw[:500])

print("\n=== Uniques/ByCategory?Category=Weapon (raw 500 chars) ===")
s, raw = get_raw(f"/Leagues/{L}/Uniques/ByCategory?Category=Weapon&PerPage=5")
print(f"HTTP {s}")
print(raw[:500])

# ลอง Items endpoint แทน
print("\n=== Items?PerPage=5 (raw 600 chars) ===")
s, raw = get_raw(f"/Leagues/{L}/Items?PerPage=5")
print(f"HTTP {s}")
print(raw[:600])

# ลอง Items/Categories
print("\n=== Items/Categories (raw) ===")
s, raw = get_raw(f"/Leagues/{L}/Items/Categories")
print(f"HTTP {s}")
print(raw[:600])
