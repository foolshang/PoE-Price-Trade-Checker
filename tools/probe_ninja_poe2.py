import json, urllib.request, urllib.parse, urllib.error, io, pathlib, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

LEAGUE = "Runes of Aldur"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
L = urllib.parse.quote(LEAGUE)

CANDIDATES = [
    ("A: current code (exchange/current/overview)",
     f"https://poe.ninja/poe2/api/economy/exchange/current/overview?league={L}&type=Currency"),
    ("B: currencyexchange leagueName/overviewName",
     f"https://poe.ninja/poe2/api/economy/currencyexchange/overview?leagueName={L}&overviewName=Currency"),
    ("C: currencyoverview poe1-style path on poe2",
     f"https://poe.ninja/poe2/api/data/currencyoverview?league={L}&type=Currency"),
    ("D: itemoverview poe1-style",
     f"https://poe.ninja/poe2/api/data/itemoverview?league={L}&type=Currency"),
]

buf = io.StringIO()

def p(*a, **kw):
    print(*a, **kw)
    print(*a, **kw, file=buf)

for label, url in CANDIDATES:
    p("=" * 70)
    p(label)
    p(url)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
            p("HTTP", r.status, "| top-level keys:", list(data.keys()))
            lines = data.get("lines") or data.get("entries") or []
            if lines:
                p("first line keys:", list(lines[0].keys()))
                p("first line:", json.dumps(lines[0], ensure_ascii=False)[:400])
            else:
                p("NO 'lines'. dump:", json.dumps(data, ensure_ascii=False)[:600])
    except urllib.error.HTTPError as e:
        p("HTTP ERROR", e.code)
    except Exception as e:
        p("FAIL", type(e).__name__, e)
    p()

out = pathlib.Path(__file__).parent / "probe_ninja_poe2_result.txt"
out.write_text(buf.getvalue(), encoding="utf-8")
print(f"\n>>> Result saved: {out}")
input("Press Enter to close...")
