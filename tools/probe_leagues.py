"""รันเพื่อหาว่า endpoint ไหนคืนรายชื่อลีกปัจจุบันได้ และโครงสร้างหน้าตายังไง"""
import json, urllib.request, urllib.error

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

CANDIDATES = [
    ("poe.ninja PoE1 leagues", "https://poe.ninja/api/data/leagues"),
    ("poe.ninja PoE2 leagues", "https://poe.ninja/poe2/api/data/leagues"),
    ("GGG trade PoE1",  "https://www.pathofexile.com/api/trade/data/leagues"),
    ("GGG trade2 PoE2", "https://www.pathofexile.com/api/trade2/data/leagues"),
]

for label, url in CANDIDATES:
    print("=" * 70)
    print(label, "->", url)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode("utf-8", "replace")
            print("HTTP", r.status)
            print(body[:1500])
    except urllib.error.HTTPError as e:
        print("HTTP ERROR", e.code, e.read()[:300])
    except Exception as e:
        print("FAIL", type(e).__name__, e)
    print()
