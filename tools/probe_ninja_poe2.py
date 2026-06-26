"""ลองหลาย endpoint/พารามิเตอร์ของ poe.ninja PoE2 เทียบกัน
แก้ LEAGUE ให้ตรงลีกปัจจุบันก่อนรัน (ดูจาก probe_leagues)"""
import json, urllib.request, urllib.parse, urllib.error

LEAGUE = "Return of the Ancients"   # <-- แก้ให้ตรงผลจาก probe_leagues
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
L = urllib.parse.quote(LEAGUE)

CANDIDATES = [
    ("A: code ปัจจุบัน (exchange/current/overview)",
     f"https://poe.ninja/poe2/api/economy/exchange/current/overview?league={L}&type=Currency"),
    ("B: currencyexchange + leagueName/overviewName",
     f"https://poe.ninja/poe2/api/economy/currencyexchange/overview?leagueName={L}&overviewName=Currency"),
    ("C: currencyoverview แบบ poe1 path บน poe2",
     f"https://poe.ninja/poe2/api/data/currencyoverview?league={L}&type=Currency"),
    ("D: itemoverview แบบ poe1",
     f"https://poe.ninja/poe2/api/data/itemoverview?league={L}&type=Currency"),
]

for label, url in CANDIDATES:
    print("=" * 70)
    print(label)
    print(url)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
            print("HTTP", r.status, "| top-level keys:", list(data.keys()))
            lines = data.get("lines") or data.get("entries") or []
            if lines:
                print("first line keys:", list(lines[0].keys()))
                print("first line:", json.dumps(lines[0], ensure_ascii=False)[:400])
            else:
                print("NO 'lines'. dump:", json.dumps(data, ensure_ascii=False)[:600])
    except urllib.error.HTTPError as e:
        print("HTTP ERROR", e.code)
    except Exception as e:
        print("FAIL", type(e).__name__, e)
    print()
