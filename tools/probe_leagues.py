import json, urllib.request, urllib.error, io, pathlib, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

CANDIDATES = [
    ("poe.ninja PoE1 leagues", "https://poe.ninja/api/data/leagues"),
    ("poe.ninja PoE2 leagues", "https://poe.ninja/poe2/api/data/leagues"),
    ("GGG trade PoE1",  "https://www.pathofexile.com/api/trade/data/leagues"),
    ("GGG trade2 PoE2", "https://www.pathofexile.com/api/trade2/data/leagues"),
]

buf = io.StringIO()

def p(*a, **kw):
    print(*a, **kw)
    print(*a, **kw, file=buf)

for label, url in CANDIDATES:
    p("=" * 70)
    p(label, "->", url)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode("utf-8", "replace")
            p("HTTP", r.status)
            p(body[:1500])
    except urllib.error.HTTPError as e:
        p("HTTP ERROR", e.code, e.read()[:300])
    except Exception as e:
        p("FAIL", type(e).__name__, e)
    p()

out = pathlib.Path(__file__).parent / "probe_leagues_result.txt"
out.write_text(buf.getvalue(), encoding="utf-8")
print(f"\n>>> Result saved: {out}")
input("Press Enter to close...")
